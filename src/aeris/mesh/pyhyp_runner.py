"""
In-process pyHyp volume mesh extruder.

Wraps pyHyp's Python API. The caller must be running inside the mach-aero
conda environment — pyHyp cannot be imported if the env is not active.
"""

from __future__ import annotations

import contextlib
import io
import json
import time
from pathlib import Path

# Option definitions, grid levels, the single options builder, and the
# subprocess execution machinery live in aeris.cfd.meshing.* (the aeris.cfd
# suite core).  The names are re-exported here for backward compatibility.
from aeris.cfd.meshing.pyhyp_extrude import (
    parse_pyhyp_march_metrics,
    quarantine_invalid_cgns,
    run_pyhyp_subprocess,
    write_pyhyp_run_inputs,
    write_volume_report,
)
from aeris.cfd.meshing.pyhyp_options import (
    DEFAULT_LEVEL,
    GRID_LEVELS,
    build_pyhyp_options,
)
from aeris.cfd.options.manifest import write_effective_options_manifest

__all__ = [
    "GRID_LEVELS",
    "DEFAULT_LEVEL",
    "run_pyhyp",
    "subprocess_run_pyhyp",
]

# Back-compat private aliases (implementations moved to aeris.cfd).
_parse_pyhyp_march_metrics = parse_pyhyp_march_metrics
_write_volume_report = write_volume_report
_quarantine_invalid_cgns = quarantine_invalid_cgns


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
    """Back-compat wrapper over aeris.cfd.meshing.pyhyp_options.build_pyhyp_options."""
    return build_pyhyp_options(
        surface_plot3d,
        level=level,
        characteristic_length=characteristic_length,
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
    ).values


def _resolve_characteristic_length(surface_dir: Path, characteristic_length: float | None) -> float:
    """Return the given length or read it from surface_report.json."""
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
    return float(characteristic_length)


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
    # stability / smoothing  (None = aeris defaults from PYHYP_SCHEMA — the
    # robust Aeris BWB values, gentler than the MDO Lab reference so the
    # blunt-TE wing-tip corner survives marching)
    c_max: float | None = None,
    theta: float | None = None,
    vol_coef: float | None = None,
    # explicit / implicit smoothing amplitudes
    eps_e_far: float | None = None,
    eps_i_far: float | None = None,
    # volume smoothing / rigid-march controls
    vol_smooth_iter: int | None = None,
    vol_blend: float | None = None,
    n_constant_start: int | None = None,
    # linear solver
    ksp_rel_tol: float | None = None,
    ksp_max_its: int | None = None,
    # raw pass-through: any native pyHyp option, verbatim, merged last
    pyhyp_options: dict[str, object] | None = None,
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

    characteristic_length = _resolve_characteristic_length(surface_dir, characteristic_length)

    output_cgns = surface_dir / f"wing_vol_{level}.cgns"
    effective = build_pyhyp_options(
        surface_plot3d,
        level=level,
        characteristic_length=characteristic_length,
        output_file=output_cgns,
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
        pyhyp_options=pyhyp_options,
    )
    options = effective.values
    write_effective_options_manifest(
        surface_dir / "pyhyp_effective_options.json",
        effective=effective,
        input_files={"surface": surface_plot3d},
    )

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
            "pyHyp produced invalid marched volume metrics: "
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
        surface_dir, status="valid", output_cgns=output_cgns, march_metrics=march_metrics
    )

    cfg = GRID_LEVELS[level]
    return {
        "level": level,
        "N": options["N"],
        "coarsen": options["coarsen"],
        "s0": options["s0"],
        "march_distance": options["marchDist"],
        "march_dist_factor": march_dist_factor,
        "characteristic_length": float(characteristic_length),
        "c_max": options["cMax"],
        "theta": options["theta"],
        "vol_coef": options["volCoef"],
        "eps_e_far": options["epsE"],
        "eps_i_far": options["epsI"],
        "vol_smooth_iter": options["volSmoothIter"],
        "vol_blend": options["volBlend"],
        "n_constant_start": options["nConstantStart"],
        "quality_warning": march_metrics.get("quality_warning"),
        "low_quality_layers": march_metrics.get("low_quality_layers"),
        "ksp_rel_tol": options["kspRelTol"],
        "ksp_max_its": options["kspMaxIts"],
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
    with Python 3.13). All volume_kwargs are forwarded to
    build_pyhyp_options(); execution is delegated to
    aeris.cfd.meshing.pyhyp_extrude.run_pyhyp_subprocess.
    """
    surface_dir = surface_dir.resolve()
    characteristic_length = _resolve_characteristic_length(surface_dir, characteristic_length)
    effective = build_pyhyp_options(
        surface_dir / "surface.fmt",
        level=level,
        characteristic_length=characteristic_length,
        output_file=surface_dir / f"wing_vol_{level}.cgns",
        **volume_kwargs,  # type: ignore[arg-type]
    )
    report = run_pyhyp_subprocess(surface_dir, effective, python_executable=python_executable)
    return {"level": level, **report}


def _write_subprocess_runner(
    surface_dir: Path,
    *,
    level: str = DEFAULT_LEVEL,
    characteristic_length: float | None = None,
    s0: float | None = None,
    march_dist_factor: float = 25.0,
    n_grid: int | None = None,
    n_coarsen: int | None = None,
    c_max: float | None = None,
    theta: float | None = None,
    vol_coef: float | None = None,
    eps_e_far: float | None = None,
    eps_i_far: float | None = None,
    vol_smooth_iter: int | None = None,
    vol_blend: float | None = None,
    n_constant_start: int | None = None,
    ksp_rel_tol: float | None = None,
    ksp_max_its: int | None = None,
    pyhyp_options: dict[str, object] | None = None,
) -> Path:
    """Resolve options once, write pyhyp_options.json + a static runner script.

    The runner bakes in nothing — it loads the JSON next to it, so the
    options a subprocess run uses are byte-identical to the in-process path
    and the pair stays standalone re-runnable for debugging.
    """
    surface_dir = surface_dir.resolve()
    characteristic_length = _resolve_characteristic_length(surface_dir, characteristic_length)
    effective = build_pyhyp_options(
        surface_dir / "surface.fmt",
        level=level,
        characteristic_length=characteristic_length,
        output_file=surface_dir / f"wing_vol_{level}.cgns",
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
        pyhyp_options=pyhyp_options,
    )
    return write_pyhyp_run_inputs(surface_dir, effective)
