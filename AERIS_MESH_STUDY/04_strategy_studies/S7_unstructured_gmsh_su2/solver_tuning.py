"""Search SU2 settings for one that actually converges, on a mesh small enough to iterate.

The coarse mesh takes 8.7 s an iteration and needs hundreds, so one experiment is
hours and a search is impossible.  The smoke mesh is 42 745 cells and about a
second an iteration, which turns the same search into minutes per experiment.  The
settings that fix a stall generally transfer; the resolution that fixes an accuracy
claim does not, so nothing here is an accuracy result and the winner must be
re-confirmed at coarse resolution before it is believed.

The configuration S7 has been running is deliberately conservative - implicit Euler,
CFL capped at 100, ten linear iterations, LU-SGS - and never enabled the
Newton-Krylov path SU2 8 provides, which is the same class of method S6's policy
already names for ADflow.  That is the main hypothesis under test.

    python solver_tuning.py <case.json> [--iterations N] [--workers N] [--smoke]

`--smoke` runs every variant for a few iterations only, to prove each one starts
before a long run is committed to.

## Confirming the winner at coarse resolution

The search above selected Newton-Krylov on a 42 745-cell laptop mesh, which is a
solver diagnostic and not a production result.  Confirming it at `coarse`
(1.55 M cells) is a different job in every practical respect - it needs MPI, it
needs hours rather than minutes, it must not run ten variants, and it must not
run them side by side, because each rank reads the whole mesh before partitioning
and eight ranks on 2.5 M cells was OOM-killed on 16 GiB.  So the same variant
definitions and the same history parser are reused, and the execution is
parameterised instead of copied into a second script:

    python solver_tuning.py <case.json> --shortlist --ranks 4 --iterations 6000

`--shortlist` selects the three variants `ROADMAP.md` names, cheapest first.
`--from-case-dir` builds the `case.json` out of a finished S7 case directory so
the mesh path and the reference values are read from that geometry rather than
typed - `coarse_yplus_probe.py` and `convergence_matrix.py` both carry index 0's
references as literals, which is silently wrong the moment another design is run.

The run root holds an immutable request identity.  Re-running the identical
command resumes: completed variants are reloaded from their `result.json` and
only unfinished work runs again.  A different request against the same root is
refused rather than mixed, and a partial variant directory is reported rather
than silently deleted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

# Every variant carries multigrid: it was the clear winner of the earlier search
# and the question now is what else is needed on top of it.
MULTIGRID: dict[str, Any] = {
    "MGLEVEL": 3,
    "MGCYCLE": "V_CYCLE",
    "MG_PRE_SMOOTH": "( 1, 2, 3, 3 )",
    "MG_POST_SMOOTH": "( 0, 0, 0, 0 )",
    "MG_CORRECTION_SMOOTH": "( 0, 0, 0, 0 )",
    "MG_DAMP_RESTRICTION": 0.75,
    "MG_DAMP_PROLONGATION": 0.75,
}

# Newton-Krylov replaces the fixed-CFL implicit march with an inexact Newton
# solve, which is what usually breaks a residual stall of this shape.
NEWTON_KRYLOV: dict[str, Any] = {"NEWTON_KRYLOV": "YES"}

# A stronger preconditioner and more Krylov iterations: ten is few for an implicit
# RANS step, and an under-solved linear system stalls the outer iteration.
STRONG_LINEAR: dict[str, Any] = {
    "LINEAR_SOLVER_PREC": "ILU",
    "LINEAR_SOLVER_ILU_FILL_IN": 0,
    "LINEAR_SOLVER_ITER": 25,
}

# The CFL ceiling of 100 is modest for an implicit scheme; the ramp is what makes
# the residual crawl for hundreds of iterations before it moves.
HIGH_CFL: dict[str, Any] = {
    "CFL_NUMBER": 25.0,
    "CFL_ADAPT_PARAM": "( 0.1, 2.0, 1.0, 1000.0 )",
}

# Line-implicit preconditioning, and the reason it belongs here.
#
# Both shortlisted variants plateau at about 2.1 orders on the coarse mesh, from
# opposite directions - one with an aggressive CFL, one with a strong linear
# solve - so the limit is not the accelerator.  The levels say why: laptop_smoke,
# where the whole ten-variant matrix ran, has a wall-normal aspect ratio of 70
# and a first cell around a millimetre that does not resolve the boundary layer.
# Every production level sits at 8 333, with prisms measured to 14 064.
#
# Extreme wall-normal stretching is the classic source of stiffness in an
# implicit RANS solve, and LINELET is the classic answer: it solves implicitly
# ALONG the lines of stretched cells rather than treating each cell in
# isolation, which is the same class of method S6's ADflow policy already names.
# SU2 8.5.0 provides it as a LINEAR_SOLVER_PREC option, verified present in the
# pinned binary ("Using a linelet preconditioning", "Computed linelet structure").
#
# This was never in the matrix, because at an aspect ratio of 70 there is nothing
# for it to do.
LINELET: dict[str, Any] = {
    "LINEAR_SOLVER_PREC": "LINELET",
    "LINEAR_SOLVER_ITER": 25,
}

# POLICY.yaml su2.convergence, quoted not redefined.  A variant is only
# interesting if it can satisfy BOTH; see the stop-residual note in main().
GATE_DROP_ORDERS = 6.0
GATE_FINAL_LOG10 = -8.0

VARIANTS: dict[str, dict[str, Any]] = {
    "A_baseline": {**MULTIGRID},
    "B_newton_krylov": {**MULTIGRID, **NEWTON_KRYLOV},
    "C_strong_linear": {**MULTIGRID, **STRONG_LINEAR},
    "D_high_cfl": {**MULTIGRID, **HIGH_CFL},
    "E_quasi_newton": {**MULTIGRID, "QUASI_NEWTON_NUM_SAMPLES": 10},
    "F_nk_linear": {**MULTIGRID, **NEWTON_KRYLOV, **STRONG_LINEAR},
    "G_nk_cfl": {**MULTIGRID, **NEWTON_KRYLOV, **HIGH_CFL},
    "H_linear_cfl": {**MULTIGRID, **STRONG_LINEAR, **HIGH_CFL},
    "I_combined": {**MULTIGRID, **NEWTON_KRYLOV, **STRONG_LINEAR, **HIGH_CFL},
    # No multigrid, to check it is still earning its place once the rest improves.
    "J_nk_no_mg": {**NEWTON_KRYLOV, **STRONG_LINEAR, **HIGH_CFL},
    # Added 2026-09-01, after both shortlisted variants plateaued at ~2.1 orders
    # on a mesh 119x more anisotropic than the one they were selected on.
    "K_linelet": {**MULTIGRID, **LINELET},
    "L_nk_linelet": {**MULTIGRID, **NEWTON_KRYLOV, **LINELET},
    "M_nk_linelet_cfl": {**MULTIGRID, **NEWTON_KRYLOV, **LINELET, **HIGH_CFL},
    # Added 2026-09-04. Every variant screened so far carries MULTIGRID, and all
    # of them plateau between 1.4 and 2.1 orders on the production mesh whatever
    # else changes. Agglomeration multigrid on a boundary layer whose prism
    # aspect ratio runs to 13 773 is a known way to stall an otherwise healthy
    # solve, so LINELET without multigrid is the one cell of the matrix that has
    # never been tested. J_nk_no_mg is the existing no-multigrid control, but it
    # uses ILU rather than LINELET, so it cannot separate the two effects.
    "N_linelet_no_mg": {**LINELET},
    "O_nk_linelet_no_mg": {**NEWTON_KRYLOV, **LINELET},
    # Added 2026-09-04. Every variant from A to O varies the linear solver, the
    # preconditioner, multigrid or the CFL ramp, and not one of them touches the
    # spatial discretisation. All of them plateau between 1.4 and 2.1 orders,
    # which is what a limiter that never stops switching does to an otherwise
    # healthy solve, and it would be immune to every knob tried so far.
    #
    # The case is Mach 0.2. A slope limiter is there to stop oscillations at
    # shocks and there are none, so P removes it outright. Q keeps it but freezes
    # it, which is the standard remedy where a limiter is genuinely wanted.
    "P_nolimiter": {**NEWTON_KRYLOV, **LINELET, "SLOPE_LIMITER_FLOW": "NONE"},
    "Q_limiter_frozen": {**NEWTON_KRYLOV, **LINELET, "LIMITER_ITER": 1000},
    # Added 2026-09-04, after P and Q showed the limiter is load-bearing rather
    # than obstructive: removing it diverges, and freezing it diverges within 20
    # iterations of the freeze. So the reconstruction genuinely needs limiting,
    # and the question becomes which limiter behaves on a boundary layer whose
    # prism aspect ratio reaches 13 773.
    #
    # Venkatakrishnan's epsilon scales with a cell length that is ambiguous on a
    # highly stretched cell. The Wang variant normalises by the local solution
    # range instead, which is the standard remedy on stretched unstructured
    # meshes. R keeps the coefficient, S loosens it.
    "R_venkat_wang": {**NEWTON_KRYLOV, **LINELET,
                      "SLOPE_LIMITER_FLOW": "VENKATAKRISHNAN_WANG"},
    "S_venkat_loose": {**NEWTON_KRYLOV, **LINELET, "VENKAT_LIMITER_COEFF": 0.05},
    # Added 2026-09-04. The mesh that converges and the mesh that does not differ
    # by 119x in prism aspect ratio, 70 against 8340, because the wall-resolved
    # layer puts the first cell 196x closer to the wall. Aspect ratios of that
    # order are ordinary for wall-resolved RANS, so the question is why this
    # solve cannot take them.
    #
    # NUM_METHOD_GRAD is set nowhere in this study, so SU2 uses its GREEN_GAUSS
    # default, and Green-Gauss gradients lose accuracy on strongly stretched
    # cells in exactly this way. Least squares is the standard remedy and has
    # never been tried, because no variant here has ever varied a spatial
    # setting.
    "T_lsq_grad": {**NEWTON_KRYLOV, **LINELET,
                   "NUM_METHOD_GRAD": "WEIGHTED_LEAST_SQUARES"},
    "U_lsq_grad_nolim": {**NEWTON_KRYLOV, **LINELET,
                         "NUM_METHOD_GRAD": "WEIGHTED_LEAST_SQUARES",
                         "VENKAT_LIMITER_COEFF": 0.05},
}

# The anisotropy shortlist: what to screen on a PRODUCTION mesh, since the
# laptop-mesh matrix has been shown not to transfer.  `K_linelet` isolates the
# preconditioner without Newton-Krylov, so the two effects can be told apart.
ANISOTROPY_SHORTLIST: tuple[str, ...] = ("L_nk_linelet", "K_linelet", "M_nk_linelet_cfl")

# The coarse confirmation ROADMAP.md prescribes, cheapest first.  Four variants
# passed both gates on the laptop mesh and agreed on CL/CD/CMy to 5e-7, so the
# question at coarse is not which is most accurate but which still converges at
# 36x the cell count.  `J_nk_no_mg` is excluded because its 6 000-row history is
# byte-identical to `I_combined` - multigrid is bypassed under NEWTON_KRYLOV -
# so running it would buy a duplicate at coarse cost.
SHORTLIST: tuple[str, ...] = (
    # Fewest options changed from the frozen block, and the fastest wall time of
    # the passing set.
    "G_nk_cfl",
    # Deepest drop on the laptop (6.906) and the most headroom if coarse
    # converges more slowly.
    "I_combined",
    # The fallback if the high CFL destabilises at production resolution.
    "F_nk_linear",
)

# Memory has two parts and only one of them divides.  Every rank reads the WHOLE
# mesh before partitioning, so that part is replicated; the solver state belongs
# to a rank's own partition, so that part is divided.  A single coefficient
# cannot describe both, and the single coefficient this module used to carry
# (1.20 GiB per million cells, from the 8-rank OOM) under-predicted a
# single-rank run by 49 per cent - 1.86 GiB forecast against 2.78 measured.
#
#   per rank GiB = cells_M * (MESH + STATE / ranks)
#
# Fitted to two measurements:
#   1 rank,  1.549 M cells, LU_SGS/10 : 2 847 MiB  (measured 2026-08-31)
#   8 ranks, 2.500 M cells, LU_SGS/10 : ~3 000 MiB (the recorded OOM)
MESH_GIB_PER_MILLION_CELLS = 1.115
SOLVER_STATE_GIB_PER_MILLION_CELLS = 0.680

# The state term depends on the numerical method, which the single coefficient
# also hid.  ILU with 25 Krylov vectors stores far more than LU_SGS with 10:
# F_nk_linear measured 4 360 MiB against G_nk_cfl's 2 847 on the same mesh, both
# at one rank.  Variants carrying STRONG_LINEAR use this instead.
SOLVER_STATE_GIB_PER_MILLION_CELLS_STRONG_LINEAR = 1.634

# Retained so callers and tests can still speak of one number: what a rank costs
# in the 8-rank configuration the original datum came from.
GIB_PER_RANK_PER_MILLION_CELLS = MESH_GIB_PER_MILLION_CELLS + (
    SOLVER_STATE_GIB_PER_MILLION_CELLS / 8.0
)


def gib_per_rank(cells: float, ranks: int, *, strong_linear: bool = False) -> float:
    """Peak RSS of one rank: replicated mesh plus its share of solver state."""
    state = (
        SOLVER_STATE_GIB_PER_MILLION_CELLS_STRONG_LINEAR
        if strong_linear
        else SOLVER_STATE_GIB_PER_MILLION_CELLS
    )
    return (cells / 1.0e6) * (MESH_GIB_PER_MILLION_CELLS + state / max(int(ranks), 1))


def variant_is_strong_linear(name: str) -> bool:
    """Does this variant carry a heavy linear solve, and so the larger state?

    ILU and LINELET both store a preconditioner over 25 Krylov vectors, so both
    are budgeted at the measured ILU rate rather than the LU_SGS one.
    """
    return VARIANTS.get(name, {}).get("LINEAR_SOLVER_PREC") in ("ILU", "LINELET")

# Leave the operating system its working set rather than planning to the last
# byte; an OOM kill loses the whole run, and at coarse that is hours.
MEMORY_HEADROOM_FRACTION = 0.85

# Above this the run is a production job, not a laptop diagnostic: it is
# sequential by default and the memory plan is enforced rather than reported.
PRODUCTION_CELL_THRESHOLD = 250_000


def case_from_directory(case_dir: Path) -> dict[str, Any]:
    """Build a solver-tuning case out of a finished S7 case directory.

    The mesh path, the cell count and the reference values are all read from the
    artifacts that geometry produced, so pointing this at another design cannot
    silently reuse index 0's numbers.  `coarse_yplus_probe.py` and
    `convergence_matrix.py` both carry index 0's `area_ref` and `chord_ref` as
    literals; that is correct only for index 0 and there is nothing in either
    file that would notice.

    The reference values are the WHOLE-WING ones as `geometry_summary.json`
    records them.  They are not halved here: `su2_pipeline.fixed_su2_options`
    halves `REF_AREA` itself when the mesh carries a symmetry marker, and halving
    twice would report CL and CD at a quarter of their true value on a run that
    looked entirely healthy.
    """
    case_dir = Path(case_dir).resolve()
    summary_path = case_dir / "geometry_summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"no geometry_summary.json under {case_dir}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    # pyGeo is the primary realisation backend and the master geometry; prefer
    # its reference values and fall back only if an older summary lacks them.
    references = summary.get("pygeo_reference_values") or summary.get("reference_values")
    if not references:
        raise ValueError(f"{summary_path} carries no reference values")

    meshes = sorted(case_dir.glob("*/mesh.su2"))
    if len(meshes) != 1:
        found = ", ".join(str(m.relative_to(case_dir)) for m in meshes) or "none"
        raise ValueError(
            f"expected exactly one accepted mesh.su2 under {case_dir}; found {found}. "
            "An attempt directory is immutable, so resolve which attempt is meant "
            "rather than guessing."
        )
    mesh = meshes[0]

    cells: int | None = None
    audit_path = case_dir / "audit.json"
    if audit_path.is_file():
        counts = json.loads(audit_path.read_text(encoding="utf-8")).get("counts", {})
        if "volume_cells" in counts:
            cells = int(counts["volume_cells"])
    if cells is None:
        raise ValueError(
            f"no audited cell count under {case_dir}; the memory plan needs it, "
            "and an unaudited mesh is not something to spend coarse solver hours on"
        )

    return {
        "mesh": str(mesh),
        "cells": cells,
        "area_ref": float(references["area_m2"]),
        "chord_ref": float(references["mean_aerodynamic_chord_m"]),
        "source_case_dir": str(case_dir),
    }


def available_memory_gib() -> float | None:
    """Read MemAvailable, which is what the kernel thinks can be handed out."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / (1024.0 * 1024.0)
    except (OSError, ValueError, IndexError):
        return None
    return None


def memory_plan(
    cells: int, ranks: int, workers: int, *, strong_linear: bool = False
) -> dict[str, Any]:
    """Estimate peak RSS for the whole run and say whether it fits.

    Concurrency multiplies both ways: `workers` variants each running `ranks`
    MPI processes, and every one of those processes holds the full mesh.  The
    laptop OOM was exactly this arithmetic ignored.

    `floor_gib` is what one rank costs with the solver state divided to nothing.
    Because the mesh is replicated it cannot be reduced by adding ranks, so a
    level whose floor exceeds the host budget is unsolvable there at any
    decomposition - which is what rules `fine` out on this machine.
    """
    processes = int(ranks) * int(workers)
    per_rank = gib_per_rank(cells, ranks, strong_linear=strong_linear)
    required = per_rank * processes
    available = available_memory_gib()
    budget = None if available is None else available * MEMORY_HEADROOM_FRACTION
    return {
        "cells": int(cells),
        "ranks": int(ranks),
        "workers": int(workers),
        "concurrent_processes": processes,
        "strong_linear": bool(strong_linear),
        "gib_per_rank": round(per_rank, 2),
        "floor_gib": round((cells / 1.0e6) * MESH_GIB_PER_MILLION_CELLS, 2),
        "estimated_peak_gib": round(required, 2),
        "available_gib": None if available is None else round(available, 2),
        "budget_gib": None if budget is None else round(budget, 2),
        "fits": None if budget is None else required <= budget,
    }


def _history(directory: Path) -> dict[str, Any]:
    path = directory / "history.csv"
    if not path.is_file():
        return {"error": "no history.csv"}
    rows = list(csv.reader(path.open()))
    if len(rows) < 3:
        return {"error": f"history has {len(rows)} rows"}
    header = [h.strip().strip('"') for h in rows[0]]

    def column(name: str) -> list[float]:
        if name not in header:
            return []
        out = []
        for row in rows[1:]:
            try:
                out.append(float(row[header.index(name)]))
            except (ValueError, IndexError):
                pass
        return out

    rms = column("rms[Rho]")
    if not rms:
        return {"error": "no rms[Rho] column"}
    cl, cd = column("CL"), column("CD")
    tail = cd[-100:] if len(cd) > 100 else cd
    return {
        "iterations": len(rms),
        "rms_final": rms[-1],
        "orders_dropped": rms[0] - rms[-1],
        "best_drop": rms[0] - min(rms),
        "cd_final": cd[-1] if cd else None,
        "cl_final": cl[-1] if cl else None,
        "cd_tail_spread": (max(tail) - min(tail)) if len(tail) > 1 else None,
        # The two frozen residual conditions, reported separately: they can fail
        # for opposite reasons and a single pass/fail hides which one bit.
        "gate_final_ok": rms[-1] <= GATE_FINAL_LOG10,
        "gate_orders_ok": (rms[0] - rms[-1]) >= GATE_DROP_ORDERS,
    }


def solver_command(ranks: int) -> list[str]:
    """Serial below two ranks, `mpirun -np N` at or above it.

    Launching one rank through mpirun works but is not what the laptop matrix
    ran, and the point of the coarse confirmation is to change resolution rather
    than to change several things at once.
    """
    if int(ranks) < 1:
        raise ValueError(f"ranks must be at least 1; got {ranks}")
    if int(ranks) == 1:
        return ["SU2_CFD", "case.cfg"]
    return ["mpirun", "-np", str(int(ranks)), "SU2_CFD", "case.cfg"]


def request_identity(
    case: dict[str, Any],
    variants: Sequence[str],
    iterations: int,
    ranks: int,
    stop_residual: float,
) -> dict[str, Any]:
    """What makes two runs against one root the same request.

    S7 attempts are immutable, so a root either continues the request it already
    holds or is refused.  Wall time and worker count are deliberately absent:
    they change how long the same experiment takes, not what it measures.
    """
    payload = {
        "mesh": str(case["mesh"]),
        "cells": int(case["cells"]),
        "area_ref": float(case["area_ref"]),
        "chord_ref": float(case["chord_ref"]),
        "variants": list(variants),
        "iterations": int(iterations),
        "ranks": int(ranks),
        "stop_residual": float(stop_residual),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["digest"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def claim_root(root: Path, identity: dict[str, Any]) -> None:
    """Write the request identity into the root, or refuse a different one."""
    path = root / "request.json"
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("digest") != identity["digest"]:
            raise SystemExit(
                f"{root} already holds request {existing.get('digest', '?')[:12]} "
                f"and this one is {identity['digest'][:12]}.  Use a new output "
                "root; an attempt directory is never repaired in place."
            )
        return
    path.write_text(json.dumps(identity, indent=2), encoding="utf-8")


def run_variant(
    name: str,
    root: Path,
    case: dict[str, Any],
    iterations: int,
    timeout_s: int,
    stop_residual: float,
    ranks: int = 1,
) -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from S7_unstructured_gmsh_su2 import su2_pipeline as su2

    directory = root / name
    result_path = directory / "result.json"
    if result_path.is_file():
        # Resume.  A variant that reached a recorded result is evidence and is
        # reloaded, never re-run: at coarse resolution re-running it silently
        # costs hours and produces the same numbers.
        report = json.loads(result_path.read_text(encoding="utf-8"))
        # But only a COMPLETE result is evidence.  Fail closed on anything that
        # did not finish, and on any record written before completeness was
        # tracked, rather than silently adopting a partial run as an answer.
        if report.get("error") or report.get("truncated"):
            raise SystemExit(
                f"{result_path} records an incomplete run "
                f"({report.get('error', 'truncated')}).  It is evidence to read, "
                "not a result to resume from; use a new output root."
            )
        if "completed_requested_iterations" not in report:
            raise SystemExit(
                f"{result_path} predates completeness tracking, so whether it "
                "finished cannot be established from it.  Inspect it and use a "
                "new output root."
            )
        if not report["completed_requested_iterations"] and not report.get(
            "stopped_at_solver_stop"
        ):
            raise SystemExit(f"{result_path} records a run that stopped short.")
        report["reused"] = True
        print(json.dumps(report), flush=True)
        return report
    if directory.exists():
        raise SystemExit(
            f"{directory} exists without a result.json, so a previous attempt was "
            "interrupted part way.  Investigate it or run against a new output "
            "root; S7 attempts are immutable and this one is not repaired in place."
        )
    directory.mkdir(parents=True)

    options = su2.fixed_su2_options(
        Path(case["mesh"]),
        flow={"mach": 0.2, "alpha": 2.0, "reynolds": 1.0e6, "temperature": 288.15},
        references={"area_ref": case["area_ref"], "chord_ref": case["chord_ref"]},
        iterations=iterations,
        restart=False,
    )
    options.update(VARIANTS[name])
    # Deliberately BELOW the acceptance bar.  fixed_su2_options derives
    # CONV_RESIDUAL_MINVAL from residual_log10_final_max, so the solver halts the
    # instant it touches the bar and the achievable drop is capped at
    # initial + 8 -- which is 5.4 orders here, against a gate of 6.0.  Measuring
    # what a variant CAN reach requires the stop to sit below what the gate asks.
    options["CONV_RESIDUAL_MINVAL"] = stop_residual
    (directory / "case.cfg").write_text(
        "\n".join(f"{k}= {v}" for k, v in options.items()) + "\n", encoding="utf-8"
    )

    command = solver_command(ranks)
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        code = completed.returncode
        (directory / "run.log").write_text(completed.stdout, encoding="utf-8")
        if completed.stderr:
            (directory / "run.err").write_text(completed.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired:
        code = -9
    report = {
        "variant": name,
        "exit": code,
        "wall_s": round(time.time() - started),
        "ranks": int(ranks),
        "cells": int(case.get("cells", 0)) or None,
        "iterations_requested": int(iterations),
        "solver_stop_residual": float(stop_residual),
        "command": command,
    }
    report.update(_history(directory))
    # A timed-out run holds real partial history and is worth keeping, but it is
    # not a result: without this the resume above would reload it as one.
    if code == -9:
        report["error"] = report.get("error", "timed out")
        report["timed_out"] = True
    # Exit code 0 is NOT evidence that the run finished what it was asked to do.
    # SU2 handles SIGTERM and exits cleanly, so a killed run reports exit 0 with
    # a partial history -- measured: G_nk_cfl terminated at iteration 1853 of
    # 8000 wrote exit 0 and nothing marking it short.  A run is complete only if
    # it did the iterations asked of it, or stopped early for the declared
    # reason of reaching the solver stop.
    achieved = int(report.get("iterations") or 0)
    reached_stop = (
        report.get("rms_final") is not None
        and float(report["rms_final"]) <= float(stop_residual)
    )
    report["stopped_at_solver_stop"] = bool(reached_stop)
    report["completed_requested_iterations"] = achieved >= int(iterations)
    if not report["completed_requested_iterations"] and not reached_stop:
        report["truncated"] = True
        report["error"] = report.get(
            "error", f"truncated: {achieved} of {iterations} iterations"
        )
    result_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    return report


def _print_table(results: Sequence[dict[str, Any]]) -> None:
    print("\n%-18s %6s %8s %9s %10s %11s %12s %8s %6s" % (
        "variant", "exit", "iters", "drop", "best_drop", "cd_final", "cd_spread",
        "wall_s", "gate"))
    for r in sorted(results, key=lambda x: -(x.get("best_drop") or -99)):
        if "error" in r:
            print("%-18s %6s  %s" % (r["variant"], r["exit"], r["error"]))
            continue
        gate = "PASS" if (r["gate_final_ok"] and r["gate_orders_ok"]) else "fail"
        print("%-18s %6d %8d %9.3f %10.3f %11.6f %12.2e %8s %6s" % (
            r["variant"], r["exit"], r["iterations"], r["orders_dropped"],
            r["best_drop"], r["cd_final"] or float("nan"),
            r["cd_tail_spread"] or float("nan"), r.get("wall_s", "?"), gate))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="case.json holding mesh path and references")
    parser.add_argument("--iterations", type=int, default=4000)
    parser.add_argument("--workers", type=int, default=None,
                        help="variants in parallel; defaults to 4 on a diagnostic "
                             "mesh and 1 at production resolution")
    parser.add_argument("--ranks", type=int, default=1, help="MPI ranks per variant")
    parser.add_argument("--timeout", type=int, default=7200)
    parser.add_argument("--smoke", action="store_true", help="30 iterations, prove each starts")
    parser.add_argument("--shortlist", action="store_true",
                        help=f"run only {', '.join(SHORTLIST)} (ROADMAP.md step 1)")
    parser.add_argument("--anisotropy-shortlist", action="store_true",
                        help=f"run only {', '.join(ANISOTROPY_SHORTLIST)}")
    parser.add_argument("--variants", type=str, default=None,
                        help="comma-separated variant names to run")
    parser.add_argument("--from-case-dir", type=Path, default=None,
                        help="build the case.json from a finished S7 case directory")
    parser.add_argument("--output", type=Path, default=None,
                        help="run root; defaults to <case>/../runs")
    parser.add_argument("--allow-overcommit", action="store_true",
                        help="run even when the memory plan does not fit")
    parser.add_argument(
        "--stop-residual",
        type=float,
        default=-12.0,
        help="CONV_RESIDUAL_MINVAL for the solver; must sit below the -8 gate bar",
    )
    args = parser.parse_args()

    if args.from_case_dir is not None:
        case = case_from_directory(args.from_case_dir)
        args.case.parent.mkdir(parents=True, exist_ok=True)
        args.case.write_text(json.dumps(case, indent=2), encoding="utf-8")
        print(f"wrote {args.case}: {json.dumps(case, indent=2)}")
    case = json.loads(args.case.read_text(encoding="utf-8"))

    if sum(bool(x) for x in (args.shortlist, args.variants, args.anisotropy_shortlist)) > 1:
        parser.error("pass only one of --shortlist, --anisotropy-shortlist, --variants")
    if args.anisotropy_shortlist:
        selected: tuple[str, ...] = ANISOTROPY_SHORTLIST
    elif args.shortlist:
        selected = SHORTLIST
    elif args.variants:
        selected = tuple(n.strip() for n in args.variants.split(",") if n.strip())
        unknown = [n for n in selected if n not in VARIANTS]
        if unknown:
            parser.error(f"unknown variant(s): {', '.join(unknown)}")
    else:
        selected = tuple(VARIANTS)

    iterations = 30 if args.smoke else args.iterations
    cells = int(case.get("cells", 0))
    if cells < 1:
        # Fail closed.  A missing cell count would plan zero memory, report a
        # comfortable fit, and hand the decision back as an OOM hours later.
        parser.error(
            f"{args.case} carries no cell count, so the memory plan cannot be "
            "computed.  Rebuild it with --from-case-dir, which reads the audited "
            "count from the case's audit.json."
        )
    production = cells >= PRODUCTION_CELL_THRESHOLD
    # Sequential by default once the mesh is a production one.  Four variants
    # side by side is right for a minutes-long laptop experiment and is how the
    # laptop matrix ran; at 1.55 M cells it is how a run gets OOM-killed.
    workers = args.workers if args.workers is not None else (1 if production else 4)

    # The largest of the selected variants sets the requirement.
    plan = memory_plan(
        cells,
        args.ranks,
        workers,
        strong_linear=any(variant_is_strong_linear(n) for n in selected),
    )
    print(json.dumps({"memory_plan": plan}, indent=2), flush=True)
    if plan["fits"] is False and not args.allow_overcommit:
        raise SystemExit(
            f"the memory plan needs about {plan['estimated_peak_gib']} GiB across "
            f"{plan['concurrent_processes']} solver processes and the budget is "
            f"{plan['budget_gib']} GiB of {plan['available_gib']} GiB available.  "
            "Lower --ranks or --workers, or pass --allow-overcommit deliberately.  "
            "Each rank reads the whole mesh before partitioning, so this is the "
            "arithmetic that OOM-killed the first coarse attempt."
        )
    if plan["fits"] is None:
        print("memory not readable on this platform; the plan is unenforced",
              flush=True)

    root = args.output or (args.case.parent / ("smoke" if args.smoke else "runs"))
    root.mkdir(parents=True, exist_ok=True)
    identity = request_identity(case, selected, iterations, args.ranks, args.stop_residual)
    claim_root(root, identity)

    def one(name: str) -> dict[str, Any]:
        return run_variant(
            name, root, case, iterations, args.timeout, args.stop_residual, args.ranks
        )

    if workers <= 1:
        results = [one(name) for name in selected]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, selected))
    (root / "matrix.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    _print_table(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
