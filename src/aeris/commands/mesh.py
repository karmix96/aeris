"""
CLI commands for structured CFD mesh generation.

Provides:
    aeris mesh pyhyp  — geometry config → surface mesh → pyHyp volume mesh

Architecture:
    - Thin CLI layer; all mesh math lives in aeris.mesh.*.
    - Geometry is built via the standard Aeris generator pipeline.
    - pyHyp is called in-process; the mach-aero conda env must be active.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

import typer
import yaml

from aeris.mesh.presets import (
    CAP_WIDTH_FRAC,
    CAP_WRAP_POINTS,
    CAP_WRAP_X,
    MARCH_POLICY,
    MESH_PRESETS,
)
from aeris.mesh.pyhyp_runner import DEFAULT_LEVEL, GRID_LEVELS, subprocess_run_pyhyp
from aeris.mesh.surface import (
    MeshBuildError,
    airplane_summary,
    export_surface_mesh,
    select_wing,
)

mesh_app = typer.Typer(
    help=(
        "Structured CFD mesh generation commands.\n\n"
        "Use:\n"
        "- 'pyhyp'  to build a structured surface + volume mesh from a geometry YAML config\n\n"
        "The mach-aero conda environment must be active for volume mesh extrusion."
    )
)


@mesh_app.callback()
def mesh_callback() -> None:
    """Mesh command group."""
    pass


def _build_wing(
    config_path: Path,
    *,
    wing_index: int,
    geometry_output_dir: Path,
    seed_override: int | None,
    save_plot: bool,
) -> tuple[object, object, str]:
    from aeris.common.config import load_yaml_config
    from aeris.geometry.config_resolver import resolve_generator_and_config
    from aeris.geometry.registry import get_geometry_generator

    raw_config = load_yaml_config(config_path)
    generator_id, generator_config = resolve_generator_and_config(raw_config)
    generator = get_geometry_generator(generator_id)

    seed = seed_override if seed_override is not None else generator_config.generator.seed
    design_sample = generator.sample_one(generator_config, seed=seed)

    geometry_output_dir.mkdir(parents=True, exist_ok=True)
    case = generator.run_full_case(
        sample=design_sample,
        config=generator_config,
        output_dir=geometry_output_dir,
        save_plot=save_plot,
    )

    airplane = getattr(getattr(case, "aerosandbox_result", None), "airplane", None)
    if airplane is None:
        raise MeshBuildError("The generator did not return an AeroSandbox Airplane object.")

    wing = select_wing(airplane, wing_index)
    return wing, airplane, generator_id


@mesh_app.command("pyhyp")
def mesh_pyhyp(
    # ── Input / output ────────────────────────────────────────────────────────
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        help="Path to the YAML geometry config file.",
    ),
    output_dir: Path = typer.Option(
        ...,
        "--output-dir",
        "-o",
        help="Directory where all mesh artifacts are written (persistent, not /tmp).",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite/--no-overwrite",
        help="Overwrite an existing output directory.",
    ),
    wing_index: int = typer.Option(
        0,
        "--wing-index",
        help="Which wing in the Airplane to mesh (0 = main wing).",
    ),
    seed: Optional[int] = typer.Option(
        None,
        "--seed",
        help="Override the geometry sampling seed from the config.",
    ),
    save_geometry_plot: bool = typer.Option(
        False,
        "--save-plot/--no-save-plot",
        help="Save the 2-D geometry summary plot from the generator.",
    ),
    preset: Optional[str] = typer.Option(
        None,
        "--preset",
        help=(
            "Named cap4 family preset: 'smoke' (49 pts/side, N 129 — cheap "
            "laptop-scale runs), 'fine' (71 pts/side, N 193), or 'production' "
            "(97 pts/side, N 257 — the validated DSE recipe).  Sets topology, "
            "points-per-side, spanwise-panels, cap parameters (via the "
            "documented scaling laws in aeris.cfd.presets data), and the "
            "volume level.  Explicitly passed flags WIN over the preset "
            "(CLI > preset > default authority order)."
        ),
    ),
    # ── Surface mesh ──────────────────────────────────────────────────────────
    points_per_side: Optional[int] = typer.Option(
        None,
        "--points-per-side",
        help=(
            "Points along each block edge in the chordwise and tip-radial "
            "directions.  Doubling this quadruples surface cells.  "
            "Min 9; default 97 (or the preset value) — it resolves the "
            "blunt-TE wing-tip corner finely enough for pyHyp to march "
            "without folding."
        ),
    ),
    spanwise_panels: Optional[int] = typer.Option(
        None,
        "--spanwise-panels",
        help=(
            "Spanwise panels per cross-section interval.  "
            "Total spanwise columns = (n_xsecs - 1) × panels.  "
            "Default 8 (or the preset value).  "
            "Increase for high-AR wings or tip-dominated flows."
        ),
    ),
    tip_radial_points: Optional[int] = typer.Option(
        None,
        "--tip-radial-points",
        help=(
            "Radial grid points in each tip-ring/collar block (from OML inward).  "
            "None = auto per topology: 9 for mid4/split8, 3 for cap4.  Few radial "
            "points keep tip-cap cells comparable in size to the OML cells, avoiding "
            "the surface-metric jump that folds the volume march.  For cap4, 3 is the "
            "only validated value — 5+ shrinks the collar cells 100-200x below OML "
            "size and the full-resolution march inverts."
        ),
    ),
    tip_inner_scale: float = typer.Option(
        0.60,
        "--tip-inner-scale",
        help=(
            "Scale factor (0.15–0.75) controlling how far the tip-ring inner boundary "
            "shrinks toward the tip centroid.  Smaller = tighter cap, larger = looser.  "
            "0.60 (looser) keeps the cap cells from collapsing."
        ),
    ),
    tip_dome_scale: float = typer.Option(
        0.0,
        "--tip-dome-scale",
        help=(
            "EXPERIMENTAL: dome the tip cap spanwise by this fraction of local "
            "half-thickness (0 = flat cap, the validated default).  A quarter-"
            "circle profile gives tangent continuity at the tip edge; improves "
            "surface quality at fine resolution but is incompatible with the "
            "coarsen=4 recipe (decimation breaks the rim profile)."
        ),
    ),
    tip_conformal_ring: bool = typer.Option(
        False,
        "--tip-conformal-ring/--tip-straight-ring",
        help=(
            "EXPERIMENTAL: build the tip-ring inner boundary as a scaled copy of "
            "the curved tip edge instead of straight chords.  Fixes the LE/TE ring "
            "fan but currently collapses the center patch — off by default."
        ),
    ),
    split_x_fore: float = typer.Option(
        0.20,
        "--split-x-fore",
        help=(
            "Fore x/c split for the mid-chord O-type topology.  Block corners land at "
            "x/c = split_x_fore and (1-split_x_fore) on both surfaces; the LE and TE live "
            "inside block interiors. Valid range 0.05-0.45."
        ),
    ),
    min_te_thickness: float = typer.Option(
        2.0e-3,
        "--min-te-thickness",
        help=(
            "Minimum blunt trailing-edge gap (in chord units) required before meshing.  "
            "Raises an error if the airfoil TE is too sharp for a structured mesh."
        ),
    ),
    min_scaled_jacobian: float = typer.Option(
        1.0e-2,
        "--min-scaled-jacobian",
        help=(
            "Minimum accepted surface scaled corner Jacobian before pyHyp.  "
            "Default 0.01: the blunt-TE tip cap is intrinsically skewed, and "
            "empirically pyHyp marches valid volumes down to ~0.01 for this "
            "topology.  This metric is advisory — volume validity is decided by "
            "pyHyp's marched cell volumes, not the surface Jacobian."
        ),
    ),
    oml_topology: Optional[str] = typer.Option(
        None,
        "--oml-topology",
        help=(
            "OML topology: 'mid4' for the stable 4-block surface (coarse levels, "
            "requires coarsen=4), 'split8' for doubled LE/TE blocks, 'cap4' for the "
            "camber-aligned tip cap (fine in-plane RANS; forces coarsen=1 and a "
            "3-point collar — validated at L1 full resolution).  "
            "Default mid4 (cap4 when a preset is used)."
        ),
    ),
    cap_width_frac: Optional[float] = typer.Option(
        None,
        "--cap-width-frac",
        help=(
            "cap4 only: width of the camber-strip center rectangle as a fraction of "
            "the local tip half-thickness (0.15-0.85).  0.5 is the validated default."
        ),
    ),
    cap_wrap_points: Optional[int] = typer.Option(
        None,
        "--cap-wrap-points",
        help=(
            "cap4 only: points across each narrow LE/TE wrap side of the tip section "
            "(min 5).  17 is the validated default."
        ),
    ),
    cap_wrap_x: Optional[float] = typer.Option(
        None,
        "--cap-wrap-x",
        help=(
            "cap4 only: chordwise x/c station of the wrap corners (0.01-0.15).  "
            "Corners sit at x/c = cap_wrap_x and 1-cap_wrap_x.  Default 0.015 "
            "(the validated value; the old 0.03 default folded the coarse march "
            "at the root TE base — measured 2026-07-17)."
        ),
    ),
    max_adjacent_normal_angle: float = typer.Option(
        180.0,
        "--max-adjacent-normal-angle",
        help=(
            "Maximum accepted angle in degrees between adjacent surface-cell normals.  "
            "Default 180 reports this metric without rejecting the current "
            "4-block topology; lower it for topology studies."
        ),
    ),
    # ── Volume mesh (pyHyp level preset) ─────────────────────────────────────
    run_pyhyp_flag: bool = typer.Option(
        True,
        "--run-pyhyp/--surface-only",
        help="Run pyHyp to extrude the volume mesh.  Use --surface-only to skip.",
    ),
    level: Optional[str] = typer.Option(
        None,
        "--level",
        help=(
            "pyHyp grid level preset — sets normal-direction layers (N), surface "
            "coarsening, and default wall spacing unless overridden.  "
            f"Choices: {list(GRID_LEVELS)}.  Default {DEFAULT_LEVEL} (or the "
            "family level when --preset is used).  Level presets use coarsen=4 "
            "with the mid4 topology (in-plane resolution is tip-topology-"
            "limited); the cap4 topology instead forces coarsen=1 (full "
            "in-plane resolution).  L1=fine wall-resolved RANS (N 257, y+~0.2), "
            "L2=standard RANS (N 193), L3=default baseline (N 129), L4=quick "
            "topology check (N 37).  All validated valid."
        ),
    ),
    # ── Volume mesh (wall spacing & farfield) ─────────────────────────────────
    s0: Optional[float] = typer.Option(
        None,
        "--s0",
        help=(
            "First cell height from the wall (metres).  "
            "None = automatic per level (~y⁺≈1 at Re≈1e6 on 1 m chord).  "
            "For high-Re RANS: s0 ≈ 5ν / u_τ ≈ chord × 5 / (Re × sqrt(Cf/2))."
        ),
    ),
    march_dist_factor: float = typer.Option(
        25.0,
        "--march-dist-factor",
        help=(
            "Farfield distance = factor × characteristic_length.  "
            "25 is the default (robust for this BWB).  "
            "Increase to 30–50 for external aerodynamics once the mesh is stable."
        ),
    ),
    # ── Volume mesh (normal-direction overrides) ──────────────────────────────
    n_grid: Optional[int] = typer.Option(
        None,
        "--n-grid",
        help=(
            "Override the number of normal-direction cell layers (ignores --level preset).  "
            "Typical values: 37 (coarse) → 257 (fine RANS)."
        ),
    ),
    n_coarsen: Optional[int] = typer.Option(
        None,
        "--n-coarsen",
        help=(
            "Override the coarsening factor (ignores --level preset).  "
            "1 = no coarsening (full resolution), 4 = aggressive coarsening."
        ),
    ),
    # ── Volume mesh (stability & smoothing) ───────────────────────────────────
    c_max: Optional[float] = typer.Option(
        None,
        "--c-max",
        help=(
            "Maximum allowable cell size ratio before the marcher reduces the step.  "
            "Default 0.7 (gentle, robust Aeris; MDO Lab BWB reference is 2.5); "
            "presets use the damped 0.5.  Lower → smoother but slower."
        ),
    ),
    theta: Optional[float] = typer.Option(
        None,
        "--theta",
        help=(
            "Angle-based smoothing weight.  Higher → better orthogonality near curved "
            "surfaces but higher cost.  Default 3.0; 2.0–5.0 typical."
        ),
    ),
    vol_coef: Optional[float] = typer.Option(
        None,
        "--vol-coef",
        help=(
            "Volume smoothing coefficient.  Higher → more aggressive cell size "
            "regularisation.  Default 0.5 (0.1–0.5 typical)."
        ),
    ),
    eps_e_far: Optional[float] = typer.Option(
        None,
        "--eps-e-far",
        help=(
            "Explicit smoothing amplitude.  Default 4.0 (presets use 6.0; MDO Lab "
            "BWB reference = 1.0); the extra smoothing keeps the tip march stable."
        ),
    ),
    eps_i_far: Optional[float] = typer.Option(
        None,
        "--eps-i-far",
        help=(
            "Implicit smoothing amplitude.  Default 8.0 (presets use 12.0; "
            "should stay ~2× eps-e-far)."
        ),
    ),
    vol_smooth_iter: Optional[int] = typer.Option(
        None,
        "--vol-smooth-iter",
        help=(
            "Volume smoothing iterations per marching step.  Default 800 (presets "
            "use 1200; MDO Lab BWB reference = 150); heavier smoothing "
            "regularises the sharp tip-cap curvature."
        ),
    ),
    vol_blend: Optional[float] = typer.Option(
        None,
        "--vol-blend",
        help=(
            "Global volume-smoothing blend factor.  Default 0.004 "
            "(MDO Lab BWB reference = 0.0002)."
        ),
    ),
    n_constant_start: Optional[int] = typer.Option(
        None,
        "--n-constant-start",
        help=(
            "Number of initial marching layers grown rigidly (no smoothing) to "
            "carry the mesh cleanly off sharp surface features.  Default 5 "
            "(presets use 3)."
        ),
    ),
    # ── Volume mesh (linear solver) ───────────────────────────────────────────
    ksp_rel_tol: Optional[float] = typer.Option(
        None,
        "--ksp-rel-tol",
        help=(
            "Relative convergence tolerance for the PETSc KSP linear solver used per "
            "marching step.  Default 1e-8; tighten to 1e-10 for marching instabilities."
        ),
    ),
    ksp_max_its: Optional[int] = typer.Option(
        None,
        "--ksp-max-its",
        help=(
            "Maximum KSP iterations per marching step.  Default 1500; raise if "
            "solver reports divergence on highly curved surfaces."
        ),
    ),
    pyhyp_option: list[str] = typer.Option(
        [],
        "--pyhyp-option",
        help=(
            "Raw native pyHyp option as KEY=VALUE, repeatable — full authority "
            "pass-through for ANY pyHyp option not covered by a flag "
            "(e.g. --pyhyp-option splay=0.25 --pyhyp-option cornerAngle=60.0).  "
            "Values are parsed as YAML scalars.  Raw keys win over flags and "
            "presets; the override is recorded in the provenance manifest."
        ),
    ),
) -> None:
    """Build a structured CFD mesh from an Aeris geometry YAML config.

    Pipeline:
    1. Generate AeroSandbox geometry from the config.
    2. Build a 9-block structured surface mesh (mid4/split8: 4 OML + 4 tip-ring
       + 1 tip-center; cap4: 4 OML + 4 collar + 1 camber-strip center).
    3. Export surface to CGNS, PLOT3D, VTK, and NPZ.
    4. (Optional) Run pyHyp to extrude a 3-D volume mesh.

    Artifacts are written to --output-dir (use a persistent path, not /tmp).
    Requires the mach-aero conda environment for volume extrusion (step 4).
    """
    config_path = Path(config).expanduser().resolve()
    if not config_path.is_file():
        typer.secho(f"[AERIS mesh] Config not found: {config_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    if preset is not None:
        if preset not in MESH_PRESETS:
            typer.secho(
                f"[AERIS mesh] Unknown preset {preset!r}. Valid: {list(MESH_PRESETS)}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        # Authority order: explicit CLI flag > preset > aeris default.  The
        # preset only fills values the user did not pass.
        p = MESH_PRESETS[preset]
        oml_topology = oml_topology if oml_topology is not None else "cap4"
        points_per_side = points_per_side if points_per_side is not None else p.points_per_side
        spanwise_panels = spanwise_panels if spanwise_panels is not None else p.spanwise_panels
        cap_width_frac = cap_width_frac if cap_width_frac is not None else p.cap_width_frac
        cap_wrap_points = cap_wrap_points if cap_wrap_points is not None else p.cap_wrap_points
        cap_wrap_x = cap_wrap_x if cap_wrap_x is not None else p.cap_wrap_x
        level = level if level is not None else p.name
        c_max = c_max if c_max is not None else float(MARCH_POLICY["c_max"])
        eps_e_far = eps_e_far if eps_e_far is not None else float(MARCH_POLICY["eps_e_far"])
        eps_i_far = eps_i_far if eps_i_far is not None else float(MARCH_POLICY["eps_i_far"])
        vol_smooth_iter = (
            vol_smooth_iter if vol_smooth_iter is not None else int(MARCH_POLICY["vol_smooth_iter"])
        )
        n_constant_start = (
            n_constant_start
            if n_constant_start is not None
            else int(MARCH_POLICY["n_constant_start"])
        )
        typer.echo(
            f"[AERIS mesh] Preset {p.name!r}: {p.description}\n"
            f"  cap4, points-per-side={points_per_side}, "
            f"spanwise-panels={spanwise_panels}, "
            f"cap-width-frac={cap_width_frac:.4f}, "
            f"cap-wrap-points={cap_wrap_points}, "
            f"cap-wrap-x={cap_wrap_x}, level={level}, "
            f"march policy={MARCH_POLICY}  (explicit flags win over the preset)"
        )

    # Legacy defaults for anything still unset (no preset, no explicit flag).
    if oml_topology is None:
        oml_topology = "mid4"
    if points_per_side is None:
        points_per_side = 97
    if spanwise_panels is None:
        spanwise_panels = 8
    if cap_width_frac is None:
        cap_width_frac = CAP_WIDTH_FRAC
    if cap_wrap_points is None:
        cap_wrap_points = CAP_WRAP_POINTS
    if cap_wrap_x is None:
        cap_wrap_x = CAP_WRAP_X
    if level is None:
        level = DEFAULT_LEVEL

    raw_pyhyp_options: dict[str, object] = {}
    for item in pyhyp_option:
        key, sep, value = item.partition("=")
        if not sep or not key:
            typer.secho(
                f"[AERIS mesh] --pyhyp-option must be KEY=VALUE, got {item!r}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        try:
            raw_pyhyp_options[key] = yaml.safe_load(value)
        except yaml.YAMLError as exc:
            typer.secho(
                f"[AERIS mesh] --pyhyp-option {key}: unparseable value {value!r} ({exc})",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2) from exc

    if level not in GRID_LEVELS:
        typer.secho(
            f"[AERIS mesh] Unknown grid level {level!r}. Valid: {list(GRID_LEVELS)}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if oml_topology not in {"mid4", "split8", "cap4"}:
        typer.secho(
            f"[AERIS mesh] Unknown OML topology {oml_topology!r}. " "Valid: mid4, split8, cap4.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if tip_radial_points is None:
        tip_radial_points = 3 if oml_topology == "cap4" else 9

    if oml_topology == "cap4" and run_pyhyp_flag:
        # The cap4 collar blocks are too thin to survive decimation: coarsen=4
        # breaks the collar rim and the march inverts.  cap4 is the
        # full-resolution topology — force coarsen=1 unless explicitly given.
        if n_coarsen is None:
            n_coarsen = 1
            typer.echo(
                "[AERIS mesh] cap4 topology: overriding level coarsening -> 1 "
                "(cap4 marches at full in-plane resolution)."
            )
        elif n_coarsen != 1:
            typer.secho(
                f"[AERIS mesh] cap4 topology is incompatible with --n-coarsen {n_coarsen}: "
                "decimation breaks the thin collar blocks and the march inverts. "
                "Use --n-coarsen 1, or switch to --oml-topology mid4 for coarsened runs.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)

    output_path = Path(output_dir).expanduser().resolve()
    if output_path.exists() and not overwrite:
        typer.secho(
            f"[AERIS mesh] Output directory already exists: {output_path}\n"
            "  Use --overwrite to replace it.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    if output_path.exists() and overwrite:
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    # ── Print header ──────────────────────────────────────────────────────────
    typer.echo(f"[AERIS mesh] Config          : {config_path}")
    typer.echo(f"[AERIS mesh] Output dir      : {output_path}")
    typer.echo(f"[AERIS mesh] Wing index      : {wing_index}")
    typer.echo("")
    typer.echo("[AERIS mesh] Surface mesh settings")
    typer.echo(f"  points-per-side    : {points_per_side}")
    typer.echo(f"  spanwise-panels    : {spanwise_panels}")
    typer.echo(f"  tip-radial-points  : {tip_radial_points}")
    typer.echo(f"  tip-inner-scale    : {tip_inner_scale}")
    typer.echo(f"  split-x-fore       : {split_x_fore}  (aft={1.0-split_x_fore:.2f})")
    typer.echo(f"  oml-topology       : {oml_topology}")
    if oml_topology == "cap4":
        typer.echo(f"  cap-width-frac     : {cap_width_frac}")
        typer.echo(f"  cap-wrap-points    : {cap_wrap_points}")
        typer.echo(f"  cap-wrap-x         : {cap_wrap_x}")
    typer.echo(f"  min-te-thickness   : {min_te_thickness}")
    typer.echo(f"  min-scaled-jacobian: {min_scaled_jacobian}")
    typer.echo(f"  max-normal-angle   : {max_adjacent_normal_angle} deg")
    if run_pyhyp_flag:

        def _show(value: object) -> object:
            return "aeris-default" if value is None else value

        typer.echo("")
        typer.echo(f"[AERIS mesh] Volume mesh settings  (level={level})")
        typer.echo(f"  s0                 : {'auto' if s0 is None else s0}")
        typer.echo(f"  march-dist-factor  : {march_dist_factor}  (= {march_dist_factor}×chord)")
        typer.echo(f"  n-grid             : {'from level' if n_grid is None else n_grid}")
        typer.echo(f"  n-coarsen          : {'from level' if n_coarsen is None else n_coarsen}")
        typer.echo(f"  c-max              : {_show(c_max)}")
        typer.echo(f"  theta              : {_show(theta)}")
        typer.echo(f"  vol-coef           : {_show(vol_coef)}")
        typer.echo(f"  eps-e-far          : {_show(eps_e_far)}")
        typer.echo(f"  eps-i-far          : {_show(eps_i_far)}")
        typer.echo(f"  ksp-rel-tol        : {_show(ksp_rel_tol)}")
        typer.echo(f"  ksp-max-its        : {_show(ksp_max_its)}")
        if raw_pyhyp_options:
            typer.echo(f"  raw pyhyp options  : {raw_pyhyp_options}")

    shutil.copy2(config_path, output_path / "input_config.yaml")

    # ── Step 1: Geometry ──────────────────────────────────────────────────────
    typer.echo("")
    typer.echo("[AERIS mesh] Step 1/3  Generate AeroSandbox geometry …")
    geometry_dir = output_path / "geometry"
    try:
        wing, airplane, generator_id = _build_wing(
            config_path,
            wing_index=wing_index,
            geometry_output_dir=geometry_dir,
            seed_override=seed,
            save_plot=save_geometry_plot,
        )
    except MeshBuildError as exc:
        typer.secho(f"\n[AERIS mesh] Geometry failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(
            f"\n[AERIS mesh] Unexpected geometry error: {type(exc).__name__}: {exc}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from exc

    try:
        summary = airplane_summary(airplane, wing_index=wing_index)
    except Exception:
        summary = {"error": "airplane_summary failed"}

    (output_path / "airplane_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    typer.echo(
        f"  Generator  : {generator_id}  |  "
        f"wing: {summary.get('selected_wing_name', '?')}  |  "
        f"xsecs: {summary.get('selected_wing_xsec_count', '?')}"
    )
    typer.echo(f"  Geometry   : {geometry_dir}")

    # ── Step 2: Surface mesh ──────────────────────────────────────────────────
    typer.echo("")
    typer.echo("[AERIS mesh] Step 2/3  Build structured surface mesh …")
    surface_dir = output_path / "surface"
    try:
        surface_report = export_surface_mesh(
            wing,
            surface_dir,
            points_per_block_side=points_per_side,
            spanwise_panels_per_section=spanwise_panels,
            tip_radial_points=tip_radial_points,
            tip_inner_scale=tip_inner_scale,
            tip_dome_scale=tip_dome_scale,
            tip_conformal_ring=tip_conformal_ring,
            split_x_fore=split_x_fore,
            minimum_te_thickness=min_te_thickness,
            minimum_scaled_jacobian=min_scaled_jacobian,
            maximum_adjacent_normal_angle_deg=max_adjacent_normal_angle,
            oml_topology=oml_topology,
            cap_width_frac=cap_width_frac,
            cap_wrap_points=cap_wrap_points,
            cap_wrap_x=cap_wrap_x,
        )
    except MeshBuildError as exc:
        typer.secho(f"\n[AERIS mesh] Surface build failed: {exc}", fg=typer.colors.RED, err=True)
        _write_smoke_manifest(output_path, status="surface_failed", error=str(exc))
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(
            f"\n[AERIS mesh] Unexpected surface error: {type(exc).__name__}: {exc}",
            fg=typer.colors.RED,
            err=True,
        )
        _write_smoke_manifest(
            output_path, status="surface_error", error=f"{type(exc).__name__}: {exc}"
        )
        raise typer.Exit(code=1) from exc

    block_count = int(surface_report.get("block_count", 0))
    char_len = float(surface_report.get("characteristic_length", 0.0))
    min_jac = float(surface_report.get("global", {}).get("min_scaled_corner_jacobian", 0.0))
    total_nodes = sum(b["nodes"] for b in surface_report.get("blocks", []))
    total_cells = sum(b["cells"] for b in surface_report.get("blocks", []))

    typer.echo(f"  Blocks     : {block_count}")
    typer.echo(f"  Nodes      : {total_nodes:,}  |  Cells: {total_cells:,}")
    typer.echo(f"  Char. len  : {char_len:.4f} m")
    typer.echo(
        f"  Min Jacobi : {min_jac:.4f}"
        + ("  low - increase --points-per-side or adjust --split-x-fore" if min_jac < 0.05 else "")
    )
    typer.echo(f"  Surface    : {surface_dir / 'surface.cgns'}")

    if not run_pyhyp_flag:
        _write_smoke_manifest(output_path, status="surface_only", surface_report=surface_report)
        typer.echo("")
        typer.echo("[AERIS mesh] --surface-only: skipping pyHyp volume extrusion.")
        typer.echo(f"[AERIS mesh] Done. Artifacts: {output_path}")
        return

    # ── Step 3: pyHyp volume mesh ─────────────────────────────────────────────
    typer.echo("")
    typer.echo(f"[AERIS mesh] Step 3/3  Run pyHyp ({level}) …")
    try:
        pyhyp_report = subprocess_run_pyhyp(
            surface_dir,
            level=level,
            characteristic_length=char_len,
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
            pyhyp_options=raw_pyhyp_options or None,
        )
    except ImportError as exc:
        typer.secho(
            f"\n[AERIS mesh] pyhyp not available: {exc}\n"
            "  Activate the mach-aero conda environment and re-run.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        _write_smoke_manifest(
            output_path, status="pyhyp_not_available", error=str(exc), surface_report=surface_report
        )
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.secho(
            f"\n[AERIS mesh] pyHyp failed: {type(exc).__name__}: {exc}",
            fg=typer.colors.RED,
            err=True,
        )
        _write_smoke_manifest(
            output_path,
            status="pyhyp_failed",
            error=f"{type(exc).__name__}: {exc}",
            surface_report=surface_report,
        )
        raise typer.Exit(code=1) from exc

    elapsed = float(pyhyp_report.get("elapsed_seconds", 0.0))
    size_mb = int(pyhyp_report.get("output_size_bytes", 0)) / (1024 * 1024)
    n_actual = pyhyp_report.get("N")
    s0_used = pyhyp_report.get("s0")
    march = pyhyp_report.get("march_distance")
    typer.echo(f"  Layers (N) : {n_actual}")
    typer.echo(f"  s0 (wall)  : {'auto' if s0_used is None else f'{s0_used:.3e} m'}")
    if isinstance(march, (int, float)):
        typer.echo(f"  March dist : {march:.3f} m  ({march/char_len:.0f}× chord)")
    typer.echo(f"  Volume CGNS: {pyhyp_report['output_cgns']}")
    typer.echo(f"  Size       : {size_mb:.1f} MB  |  Elapsed: {elapsed:.1f} s")

    if pyhyp_report.get("quality_warning"):
        n_low = pyhyp_report.get("low_quality_layers")
        typer.secho(
            f"  Quality    : WARNING — {n_low} marching layer(s) contain skewed "
            "(negative-quality) cells, typically at the blunt-TE wing-tip corner. "
            "Cell volumes are all positive, so the mesh is valid and solver-usable.",
            fg=typer.colors.YELLOW,
        )

    _write_smoke_manifest(
        output_path, status="success", surface_report=surface_report, pyhyp_report=pyhyp_report
    )
    typer.echo("")
    typer.secho("[AERIS mesh] SUCCESS", fg=typer.colors.GREEN)
    typer.echo(f"  All artifacts in: {output_path}")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_smoke_manifest(
    output_dir: Path,
    *,
    status: str,
    error: str | None = None,
    surface_report: dict | None = None,
    pyhyp_report: dict | None = None,
) -> None:
    manifest: dict[str, object] = {"schema": "aeris.mesh.smoke_manifest.v1", "status": status}
    if error is not None:
        manifest["error"] = error
    if surface_report is not None:
        manifest["surface"] = {
            "block_count": surface_report.get("block_count"),
            "characteristic_length": surface_report.get("characteristic_length"),
            "accepted_pre_pyhyp": surface_report.get("accepted_pre_pyhyp"),
            "cgns": str((output_dir / "surface" / "surface.cgns").resolve()),
        }
    if pyhyp_report is not None:
        manifest["volume"] = {
            "level": pyhyp_report.get("level"),
            "N": pyhyp_report.get("N"),
            "s0": pyhyp_report.get("s0"),
            "march_distance": pyhyp_report.get("march_distance"),
            "output_cgns": pyhyp_report.get("output_cgns"),
            "elapsed_seconds": pyhyp_report.get("elapsed_seconds"),
        }
    (output_dir / "smoke_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
