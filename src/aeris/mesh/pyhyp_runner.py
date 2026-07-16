"""
In-process pyHyp volume mesh extruder.

Wraps pyHyp's Python API. The caller must be running inside the mach-aero
conda environment — pyHyp cannot be imported if the env is not active.
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import os
import time
from pathlib import Path


# `coarsen` decimates the INPUT surface before marching (coarsen=4 keeps every
# 8th surface point).  With the mid4 topology the flat wing-tip O-grid cap has
# cells ~1e3-1e4x smaller than the OML cells; empirically only coarsen=4
# decimates that jump enough for the hyperbolic marcher to produce a valid
# (positive-volume) volume mesh, so mid4 in-plane resolution is topology-
# limited.  The cap4 (camber-split, M6-style) topology removes that limit: it
# marches valid volumes at coarsen=1 (full in-plane resolution, validated at
# L1) but is incompatible with coarsening — decimation breaks its thin collar
# blocks.  Wall-NORMAL resolution is not limited in either topology: N up to
# 257 with s0 down to ~1e-5 m is validated valid.  Each level sets N and a
# default first-cell height as a fraction of characteristic length
# (overridable via s0); the coarsen values below apply to mid4/split8 runs.
GRID_LEVELS: dict[str, dict[str, object]] = {
    "L1": {"coarsen": 4, "N": 257, "s0_frac": 4.4e-6},   # fine wall-resolved RANS (y+ ~ 0.2)
    "L2": {"coarsen": 4, "N": 193, "s0_frac": 8.8e-6},   # standard wall-resolved RANS
    "L3": {"coarsen": 4, "N": 129, "s0_frac": 2.2e-5},   # DEFAULT — validated baseline
    "L4": {"coarsen": 4, "N": 37,  "s0_frac": 2.2e-5},   # coarse / quick topology check
}

DEFAULT_LEVEL = "L3"

# Geometry-adaptive first-cell height fallback: fraction of characteristic
# length used when a level has no s0_frac.  Empirically 2.2e-5 * char_len gives
# y+ ~ 1 for the small low-Re BWB (char ≈ 2.27 m, Re ≈ 1e6 → s0 ≈ 5e-5 m).
# Fixed micro-metre s0 values (the old per-coarsen table) were far too fine
# and folded the march immediately.
_S0_CHAR_FRACTION: float = 2.2e-5


def _parse_float_token(token: str) -> float:
    try:
        value = float(token)
    except ValueError:
        return math.nan
    return value if math.isfinite(value) else math.nan


def _invalid_cgns_path(output_cgns: Path) -> Path:
    return output_cgns.with_name(output_cgns.stem + ".invalid" + output_cgns.suffix)


def _write_volume_report(
    surface_dir: Path,
    *,
    status: str,
    output_cgns: Path,
    march_metrics: dict[str, object],
    error: str | None = None,
) -> Path:
    report = {
        "schema": "aeris.pyhyp_volume_report.v1",
        "status": status,
        "output_cgns": str(output_cgns),
        "march_metrics": march_metrics,
    }
    if error is not None:
        report["error"] = error
    path = surface_dir / "volume_report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _quarantine_invalid_cgns(output_cgns: Path) -> Path | None:
    if not output_cgns.exists():
        return None
    invalid_path = _invalid_cgns_path(output_cgns)
    try:
        invalid_path.unlink()
    except FileNotFoundError:
        pass
    output_cgns.rename(invalid_path)
    return invalid_path


def _parse_pyhyp_march_metrics(text: str) -> dict[str, object]:
    """Parse pyHyp's per-layer marching table.

    Validity is decided by *cell volume*, not cell quality:

    * A negative marched volume means an inverted (folded) cell — the mesh is
      unusable and no flow solver will run on it.  This is the hard failure
      criterion (``passed``).
    * A negative scaled *quality* with a still-positive volume means a skewed
      but non-inverted cell — common at blunt trailing-edge / wing-tip corners.
      The mesh remains usable; this is reported as a warning
      (``quality_warning``) rather than a hard failure, matching MDO Lab
      practice for BWB tip meshes.
    """
    rows: list[dict[str, float | int | bool]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 10 or not parts[0].isdigit():
            continue
        min_quality = _parse_float_token(parts[8])
        min_volume = _parse_float_token(parts[9])
        volume_valid = math.isfinite(min_volume) and min_volume > 0.0
        quality_ok = math.isfinite(min_quality) and min_quality > 0.0
        rows.append(
            {
                "grid_level": int(parts[0]),
                "min_quality": min_quality,
                "min_volume": min_volume,
                "volume_valid": volume_valid,
                "quality_ok": quality_ok,
                # kept for backward compatibility: overall per-row validity
                "valid": volume_valid and quality_ok,
            }
        )

    if not rows:
        return {
            "rows": [],
            "min_quality": None,
            "min_volume": None,
            "passed": None,
            "quality_warning": None,
        }

    min_quality = min(float(row["min_quality"]) for row in rows)
    min_volume = min(float(row["min_volume"]) for row in rows)
    first_invalid_layer = next(
        (int(row["grid_level"]) for row in rows if not bool(row["volume_valid"])),
        None,
    )
    first_low_quality_layer = next(
        (int(row["grid_level"]) for row in rows if not bool(row["quality_ok"])),
        None,
    )
    low_quality_layers = sum(1 for row in rows if not bool(row["quality_ok"]))
    passed = first_invalid_layer is None
    return {
        "rows": rows,
        "min_quality": min_quality,
        "min_volume": min_volume,
        "first_invalid_layer": first_invalid_layer,
        "first_low_quality_layer": first_low_quality_layer,
        "low_quality_layers": low_quality_layers,
        "layer_count": len(rows),
        "quality_warning": first_low_quality_layer is not None,
        "passed": passed,
    }


def _build_options(
    surface_plot3d: Path,
    *,
    level: str,
    characteristic_length: float,
    # wall / marching
    s0: float | None,
    march_dist_factor: float,
    # normal-direction grid
    n_grid: int | None,
    n_coarsen: int | None,
    # stability / smoothing
    c_max: float,
    theta: float,
    vol_coef: float,
    # far-field explicit / implicit smoothing amplitudes
    eps_e_far: float,
    eps_i_far: float,
    # volume smoothing / rigid-march controls
    vol_smooth_iter: int,
    vol_blend: float,
    n_constant_start: int,
    # linear solver
    ksp_rel_tol: float,
    ksp_max_its: int,
) -> dict[str, object]:
    cfg = GRID_LEVELS[level]
    coarsen = n_coarsen if n_coarsen is not None else int(cfg["coarsen"])
    n_cells = n_grid   if n_grid   is not None else int(cfg["N"])
    if s0 is not None:
        wall_s0 = s0
    else:
        s0_frac = float(cfg.get("s0_frac", _S0_CHAR_FRACTION))
        wall_s0 = s0_frac * characteristic_length

    return {
        "inputFile": str(surface_plot3d),
        "fileType": "PLOT3D",  # pyHyp CGNS reader fails on cgnsutilities files
        "unattachedEdgesAreSymmetry": True,
        "outerFaceBC": "farfield",
        "autoConnect": True,
        "BC": {},
        "families": "wall",
        # normal-direction grid
        "N": n_cells,
        "coarsen": coarsen,
        # wall spacing & march distance
        "s0": wall_s0,
        "marchDist": march_dist_factor * characteristic_length,
        # pseudo-grid (automatic growth ratio)
        "ps0": -1.0,
        "pGridRatio": -1.0,
        # stability — gentle growth + rigid first layers keep the blunt-TE
        # wing-tip corner from folding on the first marching steps.
        "cMax": c_max,
        "theta": theta,
        "nConstantStart": n_constant_start,
        # volume smoothing — heavier than the MDO Lab BWB reference (150/0.0002)
        # because the Aeris tip cap has sharper local curvature.
        "volCoef": vol_coef,
        "volSmoothIter": vol_smooth_iter,
        "volBlend": vol_blend,
        # explicit / implicit far-field smoothing amplitudes
        "epsE": eps_e_far,
        "epsI": eps_i_far,
        # linear solver
        "kspRelTol": ksp_rel_tol,
        "kspMaxIts": ksp_max_its,
        "kspSubspaceSize": 50,
    }


def run_pyhyp(
    surface_dir: Path,
    *,
    level: str = DEFAULT_LEVEL,
    characteristic_length: float | None = None,
    # wall / marching
    s0: float | None = None,
    march_dist_factor: float = 25.0,
    # normal-direction grid overrides (None = use level defaults)
    n_grid: int | None = None,
    n_coarsen: int | None = None,
    # stability / smoothing  (robust Aeris BWB defaults — gentler than the
    # MDO Lab reference so the blunt-TE wing-tip corner survives marching)
    c_max: float = 0.7,
    theta: float = 3.0,
    vol_coef: float = 0.5,
    # explicit / implicit smoothing amplitudes
    eps_e_far: float = 4.0,
    eps_i_far: float = 8.0,
    # volume smoothing / rigid-march controls
    vol_smooth_iter: int = 800,
    vol_blend: float = 0.004,
    n_constant_start: int = 5,
    # linear solver
    ksp_rel_tol: float = 1.0e-8,
    ksp_max_its: int = 1500,
) -> dict[str, object]:
    """Run pyHyp on the PLOT3D surface in surface_dir.

    Uses surface.fmt (PLOT3D) as input — pyHyp's CGNS reader fails on
    files produced by cgnsutilities.

    Reads surface_report.json to infer characteristic_length when not given.
    Writes the volume CGNS to surface_dir/<wing_vol_{level}.cgns>.

    Parameters
    ----------
    level:
        Grid level preset (L1–L4).  Sets N, coarsen, and default s0 unless overridden.
    s0:
        First cell height from wall.  None = automatic per level (~y+1 at Re~1e6).
        For high-Re RANS: s0 = 5 * nu / u_tau ≈ chord * 5 / (Re * sqrt(Cf/2)).
    march_dist_factor:
        Farfield distance = march_dist_factor × characteristic_length.
        30–50 is typical for external aerodynamics.
    n_grid:
        Override number of normal-direction layers (ignores level preset).
    n_coarsen:
        Override coarsening factor (ignores level preset).
    c_max:
        Max allowable cell size ratio before the marcher backs off.
        Lower → smoother but slower.  1.0–3.0 typical.
    theta:
        Angle-based smoothing weight.  Higher → better orthogonality near
        curved surfaces.  2.0–5.0 typical.
    vol_coef:
        Volume smoothing coefficient.  0.1–0.5 typical.
    eps_e_far:
        Explicit smoothing amplitude at the farfield boundary.  4.0 default.
    eps_i_far:
        Implicit smoothing amplitude at the farfield boundary.  8.0 default.
    ksp_rel_tol:
        Relative convergence tolerance for the PETSc KSP linear solver.
    ksp_max_its:
        Maximum KSP iterations per marching step.
    """
    if level not in GRID_LEVELS:
        raise ValueError(f"Unknown level {level!r}. Choose from: {list(GRID_LEVELS)}")

    surface_plot3d = surface_dir / "surface.fmt"
    if not surface_plot3d.is_file():
        raise FileNotFoundError(
            f"Surface PLOT3D not found: {surface_plot3d}. Run surface build first."
        )

    if characteristic_length is None:
        report_path = surface_dir / "surface_report.json"
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text())
                characteristic_length = float(report["characteristic_length"])
            except (KeyError, ValueError, json.JSONDecodeError):
                characteristic_length = None
        if not characteristic_length or not (characteristic_length > 0):
            raise ValueError(
                "characteristic_length must be provided or readable from surface_report.json."
            )

    options = _build_options(
        surface_plot3d,
        level=level,
        characteristic_length=float(characteristic_length),
        s0=s0,
        march_dist_factor=march_dist_factor,
        n_grid=n_grid,
        n_coarsen=n_coarsen,
        c_max=c_max,
        theta=theta,
        vol_coef=vol_coef,
        eps_e_far=eps_e_far,
        eps_i_far=eps_i_far,
        vol_smooth_iter=vol_smooth_iter,
        vol_blend=vol_blend,
        n_constant_start=n_constant_start,
        ksp_rel_tol=ksp_rel_tol,
        ksp_max_its=ksp_max_its,
    )
    output_cgns = surface_dir / f"wing_vol_{level}.cgns"
    options["outputFile"] = str(output_cgns)

    try:
        from pyhyp import pyHyp as PyHyp  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "pyhyp is not importable. Activate the mach-aero conda environment."
        ) from exc

    t0 = time.perf_counter()
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        hyp = PyHyp(options=options)
        hyp.run()
        hyp.writeCGNS(str(output_cgns))
    elapsed = time.perf_counter() - t0

    stdout_text = stdout_buffer.getvalue()
    stderr_text = stderr_buffer.getvalue()
    stdout_path = surface_dir / "pyhyp_stdout.log"
    stderr_path = surface_dir / "pyhyp_stderr.log"
    stdout_path.write_text(stdout_text, encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")
    march_metrics = _parse_pyhyp_march_metrics(stdout_text + "\n" + stderr_text)

    if not output_cgns.is_file() or output_cgns.stat().st_size == 0:
        error = f"pyHyp did not write a valid output: {output_cgns}"
        _write_volume_report(surface_dir, status="missing_output", output_cgns=output_cgns, march_metrics=march_metrics, error=error)
        raise RuntimeError(error)
    if march_metrics.get("passed") is False:
        invalid_path = _quarantine_invalid_cgns(output_cgns)
        error = (
            "pyHyp produced invalid marched volume metrics: "
            f"min_volume={march_metrics.get('min_volume')}, "
            f"min_quality={march_metrics.get('min_quality')}, "
            f"first_invalid_layer={march_metrics.get('first_invalid_layer')}. "
            f"Invalid CGNS moved to {invalid_path}. Inspect {stdout_path}."
        )
        _write_volume_report(surface_dir, status="invalid", output_cgns=invalid_path or output_cgns, march_metrics=march_metrics, error=error)
        raise RuntimeError(error)
    _write_volume_report(surface_dir, status="valid", output_cgns=output_cgns, march_metrics=march_metrics)

    cfg = GRID_LEVELS[level]
    return {
        "level": level,
        "N": options["N"],
        "coarsen": options["coarsen"],
        "s0": options["s0"],
        "march_distance": options["marchDist"],
        "march_dist_factor": march_dist_factor,
        "characteristic_length": float(characteristic_length),
        "c_max": c_max,
        "theta": theta,
        "vol_coef": vol_coef,
        "eps_e_far": eps_e_far,
        "eps_i_far": eps_i_far,
        "vol_smooth_iter": vol_smooth_iter,
        "vol_blend": vol_blend,
        "n_constant_start": n_constant_start,
        "quality_warning": march_metrics.get("quality_warning"),
        "low_quality_layers": march_metrics.get("low_quality_layers"),
        "ksp_rel_tol": ksp_rel_tol,
        "ksp_max_its": ksp_max_its,
        "output_cgns": str(output_cgns),
        "output_size_bytes": int(output_cgns.stat().st_size),
        "elapsed_seconds": elapsed,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "march_metrics": march_metrics,
        # level preset for reference (may differ from actual N/coarsen if overridden)
        "level_preset_N": int(cfg["N"]),
        "level_preset_coarsen": int(cfg["coarsen"]),
    }


def subprocess_run_pyhyp(
    surface_dir: Path,
    *,
    level: str = DEFAULT_LEVEL,
    characteristic_length: float | None = None,
    python_executable: str | None = None,
    **volume_kwargs: object,
) -> dict[str, object]:
    """Run pyHyp as a subprocess using the mach-aero Python interpreter.

    Use this when the caller is in a different Python env (e.g. base conda
    with Python 3.13). All volume_kwargs are forwarded to run_pyhyp() inside
    the subprocess via a generated runner script.
    """
    import subprocess

    conda_prefix = os.environ.get(
        "MACH_AERO_CONDA_PREFIX",
        "/home/mike/miniconda3/envs/mach-aero",
    )
    python = python_executable or str(Path(conda_prefix) / "bin" / "python")

    runner = _write_subprocess_runner(
        surface_dir, level=level,
        characteristic_length=characteristic_length,
        **volume_kwargs,
    )

    t0 = time.perf_counter()
    result = subprocess.run(
        [python, str(runner)],
        capture_output=True,
        text=True,
        cwd=str(surface_dir),
    )
    elapsed = time.perf_counter() - t0

    stdout_path = surface_dir / "pyhyp_stdout.log"
    stderr_path = surface_dir / "pyhyp_stderr.log"
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")

    if result.returncode != 0:
        tail = result.stderr[-2000:] if result.stderr else "(no stderr)"
        raise RuntimeError(
            f"pyHyp subprocess exited {result.returncode}.\n{tail}\nLog: {stderr_path}"
        )

    march_metrics = _parse_pyhyp_march_metrics(result.stdout + "\n" + result.stderr)

    output_cgns = surface_dir / f"wing_vol_{level}.cgns"
    if not output_cgns.is_file() or output_cgns.stat().st_size == 0:
        error = f"pyHyp subprocess succeeded but output missing: {output_cgns}"
        _write_volume_report(
            surface_dir,
            status="missing_output",
            output_cgns=output_cgns,
            march_metrics=march_metrics,
            error=error,
        )
        raise RuntimeError(error)
    if march_metrics.get("passed") is False:
        invalid_path = _quarantine_invalid_cgns(output_cgns)
        error = (
            "pyHyp subprocess produced invalid marched volume metrics: "
            f"min_volume={march_metrics.get('min_volume')}, "
            f"min_quality={march_metrics.get('min_quality')}, "
            f"first_invalid_layer={march_metrics.get('first_invalid_layer')}. "
            f"Invalid CGNS moved to {invalid_path}. Inspect {stdout_path}."
        )
        _write_volume_report(
            surface_dir,
            status="invalid",
            output_cgns=invalid_path or output_cgns,
            march_metrics=march_metrics,
            error=error,
        )
        raise RuntimeError(error)
    _write_volume_report(
        surface_dir,
        status="valid",
        output_cgns=output_cgns,
        march_metrics=march_metrics,
    )

    cfg = GRID_LEVELS[level]
    return {
        "level": level,
        "coarsen": cfg["coarsen"],
        "N": volume_kwargs.get("n_grid") or cfg["N"],
        "s0": volume_kwargs.get("s0"),
        "march_distance": (
            float(volume_kwargs.get("march_dist_factor", 25.0)) * float(characteristic_length)
            if characteristic_length is not None
            else None
        ),
        "quality_warning": march_metrics.get("quality_warning"),
        "low_quality_layers": march_metrics.get("low_quality_layers"),
        "output_cgns": str(output_cgns),
        "output_size_bytes": int(output_cgns.stat().st_size),
        "elapsed_seconds": elapsed,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "march_metrics": march_metrics,
    }


def _write_subprocess_runner(
    surface_dir: Path,
    *,
    level: str = DEFAULT_LEVEL,
    characteristic_length: float | None = None,
    s0: float | None = None,
    march_dist_factor: float = 25.0,
    n_grid: int | None = None,
    n_coarsen: int | None = None,
    c_max: float = 0.7,
    theta: float = 3.0,
    vol_coef: float = 0.5,
    eps_e_far: float = 4.0,
    eps_i_far: float = 8.0,
    vol_smooth_iter: int = 800,
    vol_blend: float = 0.004,
    n_constant_start: int = 5,
    ksp_rel_tol: float = 1.0e-8,
    ksp_max_its: int = 1500,
) -> Path:
    """Write a standalone run_pyhyp.py into surface_dir with all options baked in."""
    if characteristic_length is not None:
        cl_repr = repr(float(characteristic_length))
    else:
        report_path = surface_dir / "surface_report.json"
        if report_path.is_file():
            try:
                data = json.loads(report_path.read_text())
                cl_repr = repr(float(data["characteristic_length"]))
            except (KeyError, ValueError):
                cl_repr = "None"
        else:
            cl_repr = "None"

    script = f'''\
#!/usr/bin/env python3
"""Auto-generated pyHyp runner — {surface_dir}"""
import json
from pathlib import Path

GRID_LEVELS = {json.dumps(GRID_LEVELS, indent=4)}
_S0_CHAR_FRACTION = {_S0_CHAR_FRACTION!r}

def main():
    level            = {level!r}
    characteristic_length = {cl_repr}
    s0_override      = {repr(s0)}
    march_dist_factor = {march_dist_factor!r}
    n_grid_override  = {repr(n_grid)}
    n_coarsen_override = {repr(n_coarsen)}
    c_max            = {c_max!r}
    theta            = {theta!r}
    vol_coef         = {vol_coef!r}
    eps_e_far        = {eps_e_far!r}
    eps_i_far        = {eps_i_far!r}
    vol_smooth_iter  = {vol_smooth_iter!r}
    vol_blend        = {vol_blend!r}
    n_constant_start = {n_constant_start!r}
    ksp_rel_tol      = {ksp_rel_tol!r}
    ksp_max_its      = {ksp_max_its!r}

    surface_plot3d = Path(__file__).parent / "surface.fmt"
    if characteristic_length is None:
        report = json.loads((Path(__file__).parent / "surface_report.json").read_text())
        characteristic_length = float(report["characteristic_length"])

    cfg     = GRID_LEVELS[level]
    coarsen = n_coarsen_override if n_coarsen_override is not None else int(cfg["coarsen"])
    n_cells = n_grid_override    if n_grid_override    is not None else int(cfg["N"])
    s0_frac = float(cfg.get("s0_frac", _S0_CHAR_FRACTION))
    wall_s0 = s0_override if s0_override is not None else s0_frac * characteristic_length

    options = {{
        "inputFile": str(surface_plot3d),
        "fileType": "PLOT3D",
        "unattachedEdgesAreSymmetry": True,
        "outerFaceBC": "farfield",
        "autoConnect": True,
        "BC": {{}}, "families": "wall",
        "N": n_cells, "coarsen": coarsen,
        "s0": wall_s0,
        "marchDist": march_dist_factor * characteristic_length,
        "ps0": -1.0, "pGridRatio": -1.0,
        "cMax": c_max, "theta": theta, "volCoef": vol_coef,
        "nConstantStart": n_constant_start,
        "volSmoothIter": vol_smooth_iter,
        "volBlend": vol_blend,
        "epsE": eps_e_far, "epsI": eps_i_far,
        "kspRelTol": ksp_rel_tol, "kspMaxIts": ksp_max_its, "kspSubspaceSize": 50,
        "outputFile": str(Path(__file__).parent / f"wing_vol_{{level}}.cgns"),
    }}

    from pyhyp import pyHyp as PyHyp
    hyp = PyHyp(options=options)
    hyp.run()
    hyp.writeCGNS(options["outputFile"])
    print(f"pyHyp done → {{options['outputFile']}}", flush=True)

if __name__ == "__main__":
    main()
'''
    runner = surface_dir / "run_pyhyp.py"
    runner.write_text(script, encoding="utf-8")
    return runner
