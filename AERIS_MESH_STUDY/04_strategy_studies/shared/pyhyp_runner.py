"""The pyHyp invocation and its argument construction — SHARED CONTROL.

ADR-0011 section 4: one invocation, used by all six strategies, so that a
difference in march outcome is a difference in surface and not a difference in how
pyHyp was called. Migrated in substance from
`03_cap4_epse/s1_volume_canary.py`, generalised to take any strategy's staged
blocks.

**Heavy compute is never launched from here.** `prepare` writes the staged
surfaces and the pyHyp run inputs and returns the commands; the user launches
them; `collect` reads the results back and applies the frozen checklist. That is a
standing invariant of this study (ADR-0011 section 11 / RUNBOOK working notes), not
a property of this module.

Three traps this module exists to hold, all paid for in Stage 02:

1. **`characteristic_length` is the bounding-box DIAGONAL**, `norm(ptp(pts))` —
   `aeris.mesh.surface` computes it that way and pyHyp derives *both* `s0` and
   `marchDist` from it. Using the x-extent instead (0.94 against the correct
   1.5171) makes every march inconsistent with every cap4 number this study
   compares against.
2. **The runner executes from its own directory**, so `inputFile` must be
   absolute. A relative path raises "Input file not found".
3. **Confirmation must be at a genuinely finer level.** `shared.gates` holds the
   ladder; `prepare` refuses a "confirmation" that is not finer than its
   calibration.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from aeris.cfd.meshing.pyhyp_extrude import (  # noqa: E402
    mach_aero_python,
    parse_pyhyp_march_metrics,
    write_pyhyp_run_inputs,
)
from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS as LEVELS  # noqa: E402
from aeris.cfd.meshing.pyhyp_options import build_pyhyp_options  # noqa: E402

from . import gates  # noqa: E402
from .qc import qc_blocks, write_surface_artifacts  # noqa: E402


def characteristic_length(blocks) -> float:
    """Bounding-box DIAGONAL of the staged surface. See trap 1 in the module doc."""
    pts = np.concatenate([b.xyz.reshape(-1, 3) for b in blocks], axis=0)
    return float(np.linalg.norm(np.ptp(pts, axis=0)))


def level_is_finer(candidate: str, than: str) -> bool:
    """True if ``candidate`` is a genuine refinement of ``than``.

    A level is finer only if it is at least as un-coarsened AND has at least as
    many normal-direction points, with at least one strictly better. The `L*`
    family uses coarsen=4, so `L4` (N=37) is COARSER than `smoke` (N=129) even
    though its name sorts later — the ADR-0008 error recorded in ADR-0011
    section 5.4.
    """
    a, b = LEVELS[candidate], LEVELS[than]
    no_worse = a["coarsen"] <= b["coarsen"] and a["N"] >= b["N"]
    strictly_better = a["coarsen"] < b["coarsen"] or a["N"] > b["N"]
    return no_worse and strictly_better


def prepare(
    *,
    strategy_id: str,
    geometry_id: str,
    blocks,
    out_dir: Path,
    level: str,
    epse_ladder=gates.EPSE_LADDER,
    confirming_level: str | None = None,
    s0_fraction_override: float | None = None,
    n_constant_start_override: int | None = None,
    vol_blend_override: float | None = None,
    c_max_override: float | None = None,
    vol_smooth_iter_override: int | None = None,
    vol_coef_override: float | None = None,
    theta_override: float | None = None,
    march_dist_factor_override: float | None = None,
) -> dict:
    """Stage one geometry's surface and write pyHyp run inputs for each epsE.

    Returns a manifest containing the shell commands for the user to launch.
    Raises before writing anything if the surface would not be accepted, so a
    known-bad surface never consumes march time.
    """
    if confirming_level is not None and not level_is_finer(level, confirming_level):
        raise ValueError(
            f"level {level!r} is not finer than {confirming_level!r} "
            f"({LEVELS[level]} vs {LEVELS[confirming_level]}); a confirmation at a "
            "coarser level confirms nothing (ADR-0011 section 5.4)"
        )
    if s0_fraction_override is not None and s0_fraction_override <= 0.0:
        raise ValueError("s0_fraction_override must be positive")

    qc = qc_blocks(blocks)
    if not qc["accepted_pre_pyhyp"]:
        raise ValueError(
            f"{geometry_id}: surface rejected before marching: {qc['failure_reasons']}"
        )

    char_len = characteristic_length(blocks)
    mach_py = str(mach_aero_python())
    manifest: dict = {
        "schema": "aeris.mesh_study.strategy_march_prepare.v1",
        "prepared_utc": datetime.now(timezone.utc).isoformat(),
        "adr": "ADR-0011-independent-strategy-studies.md",
        "strategy_id": strategy_id,
        "geometry_id": geometry_id,
        "level": level,
        "level_settings": dict(LEVELS[level]),
        "confirming_level": confirming_level,
        "epse_ladder": list(epse_ladder),
        "characteristic_length": char_len,
        "s0_fraction_override": s0_fraction_override,
        "n_constant_start_override": n_constant_start_override,
        "vol_blend_override": vol_blend_override,
        "c_max_override": c_max_override,
        "vol_smooth_iter_override": vol_smooth_iter_override,
        "vol_coef_override": vol_coef_override,
        "theta_override": theta_override,
        "march_dist_factor_override": march_dist_factor_override,
        "surface": {
            "block_count": qc["block_count"],
            "total_cells": qc["total_cells"],
            "global": qc["global"],
        },
        "cap4_reference": gates.CAP4_REFERENCE,
        "runs": [],
        "commands": [],
    }

    for eps in epse_ladder:
        sdir = Path(out_dir) / geometry_id / f"eps{str(eps).replace('.', '')}"
        sdir.mkdir(parents=True, exist_ok=True)
        arts = write_surface_artifacts(blocks, sdir)
        effective = build_pyhyp_options(
            Path(arts["surface_fmt"]["path"]).resolve(),  # trap 2: absolute
            level=level,
            characteristic_length=char_len,
            output_file=(sdir / "wing_vol.cgns").resolve(),
            eps_e_far=eps,
            eps_i_far=gates.EPSI_OVER_EPSE * eps,
            s0=(
                s0_fraction_override * char_len
                if s0_fraction_override is not None
                else None
            ),
            n_constant_start=n_constant_start_override,
            vol_blend=vol_blend_override,
            c_max=c_max_override,
            vol_smooth_iter=vol_smooth_iter_override,
            vol_coef=vol_coef_override,
            theta=theta_override,
            **(
                {}
                if march_dist_factor_override is None
                else {"march_dist_factor": march_dist_factor_override}
            ),
        )
        runner = write_pyhyp_run_inputs(sdir, effective)
        s0 = float(effective.values.get("s0", LEVELS[level]["s0_frac"] * char_len))
        march = gates.marchability_metrics(qc, s0)
        (sdir / "surface_report.json").write_text(
            json.dumps(
                {
                    "strategy_id": strategy_id,
                    "geometry_id": geometry_id,
                    "characteristic_length": char_len,
                    "accepted_pre_pyhyp": True,
                    "block_count": qc["block_count"],
                    "total_cells": qc["total_cells"],
                    "global": qc["global"],
                    "marchability": march,
                },
                indent=2,
            )
            + "\n"
        )
        # Redirect to `run_stdout.log`. `collect` falls back to parsing that log
        # when `volume_report.json` is absent, which it always is when the static
        # runner is launched directly — so a command without the redirect produces
        # a CGNS that cannot be scored. Found by running a 30-march campaign whose
        # results were unreadable afterwards.
        cmd = f"(cd {sdir} && {mach_py} {runner.name} > run_stdout.log 2>&1)"
        manifest["commands"].append(cmd)
        manifest["runs"].append(
            {
                "epsE": eps,
                "epsI": gates.EPSI_OVER_EPSE * eps,
                "dir": str(sdir),
                "runner": str(runner),
                "surface_fmt_sha256": arts["surface_fmt"]["sha256"],
                "s0": s0,
                "marchability": march,
            }
        )

    root = Path(out_dir) / geometry_id
    (root / "prepare_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _wall_clock_s(run_dir: Path) -> float | None:
    """March wall-clock, estimated from file mtimes.

    ADR-0011 section 6.2 requires wall-clock per march, and neither
    `volume_report.json` nor pyHyp's march log records it. This estimates it as
    (march log mtime - runner script mtime), which brackets the run because the
    runner is written by `prepare` and the log is closed at exit. It is an
    ESTIMATE and is labelled as one wherever it is reported; a run prepared long
    before it is launched will overstate it.
    """
    log = Path(run_dir) / "run_stdout.log"
    runner = Path(run_dir) / "run_pyhyp.py"
    if not (log.is_file() and runner.is_file()):
        return None
    return round(log.stat().st_mtime - runner.stat().st_mtime, 1)


def read_result(run_dir: Path) -> dict | None:
    """Read one march's result, or None if it has not been run.

    The static runner writes only the CGNS; `volume_report.json` comes from the
    `run_pyhyp_subprocess` wrapper, which is bypassed when the runner is launched
    directly. Falling back to the march log is what stops a completed run being
    reported as NOT_RUN.
    """
    run_dir = Path(run_dir)
    vr = run_dir / "volume_report.json"
    log = run_dir / "run_stdout.log"
    if vr.is_file():
        return json.loads(vr.read_text())
    if log.is_file():
        text = log.read_text()
        mm = parse_pyhyp_march_metrics(text)
        return {
            # A march still in progress, or killed, must never be scored. Without
            # this the checklist happily PASSED a truncated 95-layer run that had
            # simply not reached its bad layers yet.
            "march_completed": "pyHyp done" in text,
            "status": "valid" if mm.get("passed") else "invalid",
            "march_metrics": mm,
            "volume_audit": {
                "inverted_cells": 0 if mm.get("passed") else None,
                "min_volume": mm.get("min_volume"),
            },
            "source": "parsed from run_stdout.log",
        }
    return None


def collect(
    *,
    strategy_id: str,
    out_dir: Path,
    geometry_ids: list[str],
    level: str,
    epse_ladder=gates.EPSE_LADDER,
) -> dict:
    """Apply the frozen volume checklist and select this strategy's epsE.

    Selection rule, fixed by ADR-0008 and carried into ADR-0011 section 5.1: the
    **highest** ladder value passing every geometry. The ladder is not extended
    after a failure. Selection is not final until confirmed at a genuinely finer
    level.
    """
    rows = []
    for gid in geometry_ids:
        for eps in epse_ladder:
            sdir = Path(out_dir) / gid / f"eps{str(eps).replace('.', '')}"
            vol = read_result(sdir)
            if vol is None:
                rows.append({"geometry": gid, "epsE": eps, "state": "NOT_RUN"})
                continue
            ok, fails = gates.volume_gate_checklist(vol)
            m = vol.get("march_metrics") or {}
            rows.append(
                {
                    "geometry": gid,
                    "epsE": eps,
                    "state": "PASS" if ok else "FAIL",
                    "failures": fails,
                    "inverted_cells": (vol.get("volume_audit") or {}).get("inverted_cells"),
                    "low_quality_layers": m.get("low_quality_layers"),
                    "layer_count": m.get("layer_count"),
                    "min_quality": m.get("min_quality"),
                    "min_volume": m.get("min_volume"),
                    "wall_clock_s_estimated_from_mtimes": _wall_clock_s(sdir),
                }
            )

    passing_all = []
    for eps in epse_ladder:
        got = [r for r in rows if r["epsE"] == eps]
        if got and all(r["state"] == "PASS" for r in got):
            passing_all.append(eps)
    selected = max(passing_all) if passing_all else None

    quals = [
        row["min_quality"]
        for row in rows
        if row["state"] == "PASS" and row["min_quality"] is not None
    ]
    report = {
        "schema": "aeris.mesh_study.strategy_march_collect.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "adr": "ADR-0011-independent-strategy-studies.md",
        "strategy_id": strategy_id,
        "level": level,
        "geometries": geometry_ids,
        "epse_ladder": list(epse_ladder),
        "rows": rows,
        "epse_passing_all_geometries": passing_all,
        "epse_selected": selected,
        "selection_rule": (
            "highest ladder value passing the frozen volume checklist on every "
            "geometry; ladder never extended after a failure (ADR-0008 section 6)"
        ),
        "worst_case_min_quality": min(quals) if quals else None,
        "median_min_quality": float(np.median(quals)) if quals else None,
        "cap4_reference": gates.CAP4_REFERENCE,
        "not_final_until": (
            f"confirmed at a genuinely finer level than {level!r} "
            f"(ADR-0011 section 5.4)"
        ),
    }
    (Path(out_dir) / f"collect_{level}.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
