"""Native AVL writer + runner driven directly from pyGeo sections.

Emits the ``.avl`` input (and per-section ``.af`` coordinate files) straight from
pyGeo realized ``ExtractedSection``s and runs the ``avl`` binary — WITHOUT ever
constructing an ``asb.Airplane`` / ``asb.Wing`` / ``asb.WingXSec``. This is the
AeroSandbox-Airplane-free replacement for ``build_aerosandbox_airplane`` +
``AeroSandboxAVLSolver`` on the pyGeo path.

AeroSandbox may still be imported in the process (NeuralFoil hard-depends on it,
and the reused strip helpers live in a module that imports it) — that is fine per
the target. The point is that *AERIS* never builds an AeroSandbox airplane object;
the AVL geometry is authored natively from the master pyGeo surface.

Reused, none of which construct an asb.Airplane:
  * ``inject_polar_cdcl``            — CDCL injection on the .avl text (asb-free)
  * ``aeris.aero.solvers.avl_output`` — every AVL dump parser (asb-free)
  * ``_compute_strip_profile_drag``  — strip profile-drag integration (data-only)

The viscous total follows the same definition as the ASB path:
    cd_total = cd_induced_AVL + cd_profile_NeuralFoil

Output capture: the runner dumps and parses the *complete* AVL output family —
totals (``ft``), surface forces (``fn``), strip forces (``fs``), shear/bending
(``vm``), body forces (``fb``), hinge moments (``hm``), stability-axis
derivatives + neutral point (``st``) and body-axis derivatives (``sb``) — and
writes them into ``native_avl_result.json`` alongside the raw files.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from aeris.aero.solvers.avl_output import (
    compute_derived_metrics,
    extract_body_axis_derivatives,
    extract_control_derivatives,
    extract_stability_axis_derivatives,
    parse_hinge_moments,
    parse_stability_file,
    parse_strip_shear_moment,
    parse_surface_forces,
    parse_totals_text,
    read_avl_strips,
    to_float_or_none,
)
from aeris.generators.bwb_segmented_v1.pygeo_adapter import realised_reference_metrics

# AVL totals key -> NativeAvlResult attribute.
_TOTALS_KEYS = {
    "CLtot": "cl",
    "CDtot": "cd",
    "CDind": "cd_ind",
    "CDvis": "cd_vis",
    "Cmtot": "cm",       # pitch moment (elevon δe authority)
    "Cltot": "cl_roll",  # roll moment  (differential elevon δa authority)
    "Cntot": "cn",       # yaw moment
    "CYtot": "cy",       # side force
    "CLff": "cl_ff",
    "CDff": "cd_ff",
    "CXtot": "cx",
    "CZtot": "cz",
    "e": "span_efficiency",
    "Sref": "s_ref",
    "Cref": "c_ref",
    "Bref": "b_ref",
}


@dataclass
class NativeAvlResult:
    status: str
    cl: float | None = None
    cd: float | None = None            # promoted to viscous total when available
    cd_ind: float | None = None
    cd_vis: float | None = None        # AVL's own injected-CDCL viscous drag
    cd_ff: float | None = None
    cl_ff: float | None = None
    cm: float | None = None            # pitch moment
    cl_roll: float | None = None       # roll moment (differential elevon authority)
    cn: float | None = None            # yaw moment
    cy: float | None = None            # side force
    cx: float | None = None            # body-axis X force
    cz: float | None = None            # body-axis Z force
    cd_profile: float | None = None    # NeuralFoil strip-integrated profile drag
    cd_total: float | None = None      # cd_ind + cd_profile
    l_over_d: float | None = None
    l_over_d_viscous: float | None = None

    # --- efficiency / stability ------------------------------------------
    span_efficiency: float | None = None   # AVL Trefftz-plane e
    x_np: float | None = None              # neutral point Xnp
    x_np_over_c_ref: float | None = None   # (Xnp - Xref)/Cref, always defined
    static_margin: float | None = None     # only when the moment ref IS the CG
    stability_axis_derivatives: dict[str, float | None] = field(default_factory=dict)
    body_axis_derivatives: dict[str, float | None] = field(default_factory=dict)
    control_derivatives: dict[str, dict[str, Any]] = field(default_factory=dict)
    derived_metrics: dict[str, float | None] = field(default_factory=dict)
    hinge_moments: dict[str, float] = field(default_factory=dict)
    surface_forces: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    # --- reference values / discretisation --------------------------------
    s_ref: float | None = None
    c_ref: float | None = None
    b_ref: float | None = None
    n_sections: int = 0
    n_strips: int | None = None
    n_vortices: int | None = None
    n_surfaces: int | None = None

    n_cdcl_injected: int = 0
    n_extrapolated_strips: int | None = None
    totals_raw: dict[str, float] = field(default_factory=dict)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    solver_metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    artifact_dir: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        """JSON-safe dict of every captured field (no DataFrames stored)."""
        return json.loads(json.dumps(asdict(self), default=str))


def _atmosphere(altitude_m: float) -> tuple[float, float]:
    """(density, speed_of_sound). Uses asb.Atmosphere (a physics utility, not an
    Airplane) for exactness; falls back to sea-level ISA if unavailable."""
    try:
        import aerosandbox as asb

        atm = asb.Atmosphere(altitude=float(altitude_m))
        return float(atm.density()), float(atm.speed_of_sound())
    except Exception:
        return 1.225, 340.294


def _max_thickness_over_chord(coords: np.ndarray) -> float:
    """t/c from a normalised Selig loop, for the CLAF lift-slope correction."""
    c = np.asarray(coords, dtype=float)
    xs = np.unique(np.round(c[:, 0], 6))
    t_max = 0.0
    for x in xs:
        ys = c[np.isclose(c[:, 0], x, atol=1e-6), 1]
        if ys.size >= 2:
            t_max = max(t_max, float(ys.max() - ys.min()))
    return t_max


def _section_coords(section: object, cst_points: int, representation: str) -> np.ndarray:
    if representation == "cst":
        return np.asarray(section.cst.coordinates(n_per_surface=cst_points), dtype=float)
    return np.asarray(getattr(section, "direct_coordinates"), dtype=float)


def write_native_avl(
    sections: Sequence[object],
    avl_path: Path,
    *,
    name: str = "pygeo_bwb",
    mach: float = 0.0,
    symmetric: bool = True,
    # DECISION-0009: 24 chordwise, cosine. At 8 the elevon hinge at x/c=0.75 fell
    # 0.059c from the nearest panel edge and CL_delta carried ~7.7% error -- the
    # largest discretisation error in the low-fi chain. Cosine is kept (uniform
    # halves the elevon error but degrades Xnp/Cmq by 14-15x).
    nchordwise: int = 24,
    cspace: float = 1.0,
    spanwise_panels_per_section: int = 4,
    representation: str = "cst",
    cst_points: int = 80,
    control: dict[str, Any] | None = None,
    moment_reference_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict[str, Any]:
    """Write a .avl (+ per-section .af coordinate files) from pyGeo sections.

    Returns reference values {s_ref, c_ref, b_ref}. Each SECTION gets an all-zero
    CDCL placeholder for inject_polar_cdcl to fill.

    ``moment_reference_m`` is AVL's Xref/Yref/Zref — the point moments are taken
    about. Default (0,0,0) is the geometry origin; pass the CG to make Cm and the
    static margin physically meaningful.
    """
    avl_path = Path(avl_path)
    avl_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(sections, key=lambda s: float(s.y_m))
    if len(ordered) < 2:
        raise ValueError("native AVL writer needs at least two sections")

    ref = realised_reference_metrics(ordered, symmetric=symmetric)
    s_ref = float(ref["s_ref_xy_m2"])
    c_ref = float(ref["c_ref_m"])
    b_ref = float(ref["b_ref_y_m"])

    iysym = 0  # AVL image symmetry off; the wing is mirrored via YDUPLICATE below
    lines: list[str] = [
        name,
        "#Mach",
        f"{float(mach)}",
        "#IYsym   IZsym   Zsym",
        f"{iysym}       0   0",
        "#Sref    Cref    Bref",
        f"{s_ref} {c_ref} {b_ref}",
        "#Xref    Yref    Zref",
        " ".join(f"{float(v):.8g}" for v in moment_reference_m),
        "# CDp",
        "0",
        "#" + "=" * 79,
        "SURFACE",
        name,
        "#Nchordwise  Cspace  [Nspanwise   Sspace]",
        f"{int(nchordwise)}   {cspace}",
        "",
    ]
    if symmetric:
        lines += ["YDUPLICATE", "0", ""]
    lines += [
        "CDCL",
        "#CL1  CD1  CL2  CD2  CL3  CD3",
        "0 0 0 0 0 0",
        "",
    ]

    ctrl_name = str(control.get("name", "control")) if control else None
    ctrl_hinge = float(control.get("hinge_point", 0.75)) if control else 0.75
    ctrl_start = float(control.get("start_frac", 0.0)) if control else 0.0
    ctrl_end = float(control.get("end_frac", 1.0)) if control else 1.0

    n_controlled = 0
    for i, sec in enumerate(ordered):
        coords = _section_coords(sec, cst_points, representation)
        af_path = Path(f"{avl_path}.af{i}")
        _write_selig(af_path, coords)

        le = np.asarray(sec.le_xyz_m, dtype=float).reshape(3)
        chord = float(sec.chord_m)
        ainc = float(sec.twist_deg)
        claf = 1.0 + 0.77 * _max_thickness_over_chord(coords)

        lines += [
            "#" + "-" * 50,
            "SECTION",
            "#Xle    Yle    Zle     Chord   Ainc  [Nspanwise   Sspace]",
            f"{le[0]:.8g} {le[1]:.8g} {le[2]:.8g} {chord:.8g} {ainc:.8g} "
            f"  {int(spanwise_panels_per_section)}   0",
            "",
            "AFIL",
            str(af_path),
            "",
            "CLAF",
            f"{claf}",
            "",
        ]
        # Control surface on every section INSIDE the elevon span band, both
        # boundary sections included. AVL interpolates the control gain linearly
        # between consecutive sections, so a band edge is only sharp when the
        # bounding section itself declares the control — tagging only the
        # inboard section of each interval lets the gain taper 1->0 across the
        # outboard-most interval and silently loses part of the elevon.
        #
        # Two AVL controls on the same hinge so the elevon does BOTH:
        #   <name>_sym  (SgnDup +1) = symmetric pitch  -> AVL d1
        #   <name>_diff (SgnDup -1) = differential roll -> AVL d2
        # Net: right = de_sym + da_diff, left = de_sym - da_diff.
        frac = float(getattr(sec, "span_fraction", le[1]))
        if control and ctrl_start - 1e-9 <= frac <= ctrl_end + 1e-9:
            lines += [
                "CONTROL",
                "#name, gain, Xhinge, XYZhvec, SgnDup",
                f"{ctrl_name}_sym 1 {ctrl_hinge} 0 0 0  1",
                "",
                "CONTROL",
                f"{ctrl_name}_diff 1 {ctrl_hinge} 0 0 0 -1",
                "",
            ]
            n_controlled += 1
        lines += [
            "CDCL",
            "#CL1  CD1  CL2  CD2  CL3  CD3",
            "0 0 0 0 0 0",
            "",
        ]

    avl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "s_ref": s_ref, "c_ref": c_ref, "b_ref": b_ref,
        "has_control": bool(control), "n_controlled_sections": n_controlled,
    }


def _write_selig(path: Path, coords: np.ndarray) -> None:
    c = np.asarray(coords, dtype=float)
    path.write_text(
        "\n".join(f"{x:.6f} {y:.6f}" for x, y in c) + "\n", encoding="utf-8"
    )


def _parse_discretisation(text: str) -> dict[str, int]:
    """# Surfaces / # Strips / # Vortices, as AVL reports them in every dump."""
    out: dict[str, int] = {}
    for label, key in (
        ("Surfaces", "n_surfaces"),
        ("Strips", "n_strips"),
        ("Vortices", "n_vortices"),
    ):
        m = re.search(rf"#\s*{label}\s*=\s*(\d+)", text)
        if m:
            out[key] = int(m.group(1))
    return out


def run_native_avl_case(
    sections: Sequence[object],
    *,
    flight_condition: Any,
    output_dir: Path,
    section_map: Any | None = None,
    polar_store: Any | None = None,
    control: dict[str, Any] | None = None,
    control_input_deg: float = 0.0,
    diff_input_deg: float = 0.0,
    avl_command: str = "avl",
    timeout_sec: int = 180,
    nchordwise: int = 24,          # DECISION-0009
    spanwise_panels_per_section: int = 4,
    cspace: float = 1.0,
    representation: str = "cst",
    cst_points: int = 80,
    name: str = "pygeo_bwb",
    moment_reference_m: tuple[float, float, float] = (0.0, 0.0, 0.0),
    moment_reference_is_cg: bool = False,
    save_element_forces: bool = False,
    write_result_json: bool = True,
) -> NativeAvlResult:
    """Author a native .avl from pyGeo sections, run AVL, apply the viscous
    correction, and return the corrected result. No asb.Airplane is constructed.

    Captures the complete AVL output family (totals, surface forces, strips,
    shear/bending, body forces, hinge moments, stability- and body-axis
    derivatives incl. Xnp and the per-control derivatives) into the result and,
    unless disabled, into ``native_avl_result.json``.
    """
    from aeris.aero.solvers.avl_polar_injection import inject_polar_cdcl

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(sections, key=lambda s: float(s.y_m))

    fc = flight_condition
    velocity = float(getattr(fc, "velocity_mps", 28.0))
    altitude = float(getattr(fc, "altitude_m", 0.0))
    alpha = float(getattr(fc, "alpha_deg", 0.0))
    beta = float(getattr(fc, "beta_deg", 0.0))
    p_rad_s = float(getattr(fc, "p_rad_s", 0.0) or 0.0)
    q_rad_s = float(getattr(fc, "q_rad_s", 0.0) or 0.0)
    r_rad_s = float(getattr(fc, "r_rad_s", 0.0) or 0.0)
    density, sound_speed = _atmosphere(altitude)
    mach = getattr(fc, "mach", None)
    if not mach:
        mach = velocity / sound_speed if sound_speed > 0 else 0.0
    mach = float(mach)

    avl_path = output_dir / "airplane.avl"
    ref = write_native_avl(
        ordered, avl_path, name=name, mach=mach, symmetric=True,
        nchordwise=nchordwise, spanwise_panels_per_section=spanwise_panels_per_section,
        cspace=cspace,
        representation=representation, cst_points=cst_points, control=control,
        moment_reference_m=moment_reference_m,
    )

    result = NativeAvlResult(status="PENDING", n_sections=len(ordered),
                             artifact_dir=str(output_dir))

    # Geometry guard: with YDUPLICATE the surface is mirrored about y=0, so an
    # innermost section at y>0 leaves a physical GAP of 2*y_min between the two
    # half-wings and AVL sheds a spurious inboard tip vortex pair.
    y_min = float(ordered[0].y_m)
    y_max = float(ordered[-1].y_m)
    if y_max > 0 and y_min / y_max > 1e-3:
        result.warnings.append(
            f"root section sits at y={y_min:.5f} m ({y_min / y_max:.2%} of semi-span); "
            "YDUPLICATE leaves a centreline gap and AVL will shed a spurious inboard "
            "tip vortex. Extract sections over the FULL span (span_margin=0)."
        )
    result.solver_metadata["root_gap_m"] = 2.0 * y_min
    result.solver_metadata["y_min_m"] = y_min
    result.solver_metadata["y_max_m"] = y_max

    # Viscous CDCL injection (fills the zero placeholders) before running.
    if section_map is not None and polar_store is not None:
        try:
            result.n_cdcl_injected = inject_polar_cdcl(
                avl_path, section_map, polar_store, velocity, mach, altitude
            )
        except Exception as exc:  # pragma: no cover - injection guard
            result.warnings.append(f"CDCL injection failed: {exc}")

    totals_file = "totals.txt"
    strip_file = "strips.txt"
    surface_file = "surface_forces.txt"
    element_file = "element_forces.txt"
    vm_file = "strip_shear_moment.txt"
    body_file = "body_forces.txt"
    hinge_file = "hinge_moments.txt"
    stability_file = "stability.txt"
    body_derivs_file = "body_derivs.txt"

    for stale in (totals_file, strip_file, surface_file, element_file, vm_file,
                  body_file, hinge_file, stability_file, body_derivs_file):
        try:
            (output_dir / stale).unlink()
        except FileNotFoundError:
            pass

    # Keystrokes mirror the AeroSandbox reference path so both solvers drive AVL
    # identically: graphics off, body-axis rate convention + derivative output,
    # explicit atmosphere/velocity, then the full dump family.
    keys: list[str] = [
        "plop", "g", "",
        "oper",
        "o", "r", "d", "",
        "m",
        f"mn {mach}",
        f"v {velocity}",
        f"d {density}",
        "g 9.81",
        "",
    ]
    b_ref = float(ref["b_ref"])
    c_ref = float(ref["c_ref"])
    p_bar = p_rad_s * b_ref / (2.0 * velocity) if velocity > 0 else 0.0
    q_bar = q_rad_s * c_ref / (2.0 * velocity) if velocity > 0 else 0.0
    r_bar = r_rad_s * b_ref / (2.0 * velocity) if velocity > 0 else 0.0
    keys += [
        f"a a {alpha}",
        f"b b {beta}",
        f"r r {p_bar}",
        f"p p {q_bar}",
        f"y y {r_bar}",
    ]
    if control:
        keys += ["d1", "d1", f"{control_input_deg}"]   # symmetric (pitch)
        keys += ["d2", "d2", f"{diff_input_deg}"]       # differential (roll)
    keys += ["x", "ft", totals_file, "fn", surface_file, "fs", strip_file]
    if save_element_forces:
        keys += ["fe", element_file]
    keys += [
        "vm", vm_file,
        "fb", body_file,
        "hm", hinge_file,
        "st", stability_file,
        "sb", body_derivs_file,
        "",
        "quit",
    ]

    keystrokes_path = output_dir / "keystrokes.txt"
    keystrokes_path.write_text("\n".join(keys) + "\n", encoding="utf-8")

    stdout_path = output_dir / "avl_stdout.txt"
    proc = None
    try:
        with open(stdout_path, "w") as log:
            proc = subprocess.Popen(
                [avl_command, avl_path.name], cwd=output_dir,
                stdin=subprocess.PIPE, stdout=log, stderr=log, text=True,
            )
            proc.communicate(input="\n".join(keys), timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        if proc is not None:
            proc.kill()
            proc.communicate()
        result.status = "TIMEOUT"
        result.warnings.append(f"AVL timed out after {timeout_sec}s")
        return result

    log_text = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    if "Strip array overflow" in log_text:
        result.warnings.append(
            "AVL strip array overflow (NSMAX=500) — reduce sections or spanwise panels."
        )
    if "MAKESURF: Array overflow" in log_text:
        result.warnings.append("AVL surface array overflow — geometry too dense.")

    totals_path = output_dir / totals_file
    if not totals_path.exists():
        result.status = "FAILED"
        result.warnings.append("AVL did not write a totals file; see avl_stdout.txt")
        return result

    totals_text = totals_path.read_text(encoding="utf-8")
    totals = parse_totals_text(totals_text)
    result.totals_raw = totals
    for avl_key, attr in _TOTALS_KEYS.items():
        setattr(result, attr, to_float_or_none(totals.get(avl_key)))
    for key, value in _parse_discretisation(totals_text).items():
        setattr(result, key, value)
    if result.cl is not None and result.cd and result.cd > 0:
        result.l_over_d = result.cl / result.cd

    # --- stability-axis derivatives, neutral point, control authority -------
    stability_path = output_dir / stability_file
    if stability_path.exists():
        stab_text = stability_path.read_text(encoding="utf-8")
        stab_parsed = parse_stability_file(stability_path)
        result.stability_axis_derivatives = extract_stability_axis_derivatives(stab_parsed)
        result.derived_metrics = compute_derived_metrics(result.stability_axis_derivatives)
        result.control_derivatives = extract_control_derivatives(stab_text, stab_parsed)
        result.x_np = to_float_or_none(stab_parsed.get("Xnp"))
        x_ref = to_float_or_none(totals.get("Xref")) or 0.0
        if result.x_np is not None and result.c_ref:
            result.x_np_over_c_ref = (result.x_np - x_ref) / result.c_ref
            # Static margin is (Xnp - Xcg)/Cref. It is only a static margin when
            # the AVL moment reference IS the CG — which the caller must assert
            # by passing moment_reference_is_cg=True. With the default Xref=0
            # (origin at the root LE) the same number is just Xnp in chords.
            if moment_reference_is_cg:
                result.static_margin = result.x_np_over_c_ref
            else:
                result.warnings.append(
                    "static_margin not computed: the AVL moment reference "
                    f"(Xref={x_ref:g}) is not declared to be the CG. "
                    f"Xnp/Cref aft of the reference = {result.x_np_over_c_ref:.4f}."
                )
    else:
        result.warnings.append("AVL did not write the stability (st) file")

    body_derivs_path = output_dir / body_derivs_file
    if body_derivs_path.exists():
        result.body_axis_derivatives = extract_body_axis_derivatives(
            parse_stability_file(body_derivs_path)
        )
    else:
        result.warnings.append("AVL did not write the body-derivative (sb) file")

    # --- hinge moments (actuator sizing) + per-surface breakdown -----------
    hinge_path = output_dir / hinge_file
    if hinge_path.exists():
        try:
            result.hinge_moments = parse_hinge_moments(hinge_path)
        except Exception as exc:  # pragma: no cover - parse guard
            result.warnings.append(f"hinge-moment parse failed: {exc}")

    surface_path = output_dir / surface_file
    if surface_path.exists():
        try:
            result.surface_forces = parse_surface_forces(surface_path)
        except Exception as exc:  # pragma: no cover - parse guard
            result.warnings.append(f"surface-force parse failed: {exc}")

    # --- spanwise loading + structural shear/bending -----------------------
    strips_path = output_dir / strip_file
    if strips_path.exists():
        try:
            strips_df = read_avl_strips(strips_path, alpha_deg=alpha)
            strips_csv = output_dir / "strips_parsed.csv"
            strips_df.to_csv(strips_csv, index=False)
            result.artifact_paths["strips_parsed"] = str(strips_csv)
        except Exception as exc:  # pragma: no cover - parse guard
            result.warnings.append(f"strip parse failed: {exc}")

    vm_path = output_dir / vm_file
    if vm_path.exists():
        try:
            vm_df = parse_strip_shear_moment(vm_path)
            if not vm_df.empty:
                vm_csv = output_dir / "strip_shear_moment.csv"
                vm_df.to_csv(vm_csv, index=False)
                result.artifact_paths["strip_shear_moment_parsed"] = str(vm_csv)
        except Exception as exc:  # pragma: no cover - parse guard
            result.warnings.append(f"shear/bending parse failed: {exc}")

    for label, path in (
        ("airplane_avl", avl_path), ("keystrokes", keystrokes_path),
        ("stdout", stdout_path), ("totals", totals_path),
        ("strips", strips_path), ("surface_forces", surface_path),
        ("strip_shear_moment", vm_path), ("body_forces", output_dir / body_file),
        ("hinge_moments", hinge_path), ("stability", stability_path),
        ("body_derivs", body_derivs_path),
    ):
        if path.exists():
            result.artifact_paths[label] = str(path)

    # Independent strip profile-drag integration + viscous total.
    if section_map is not None and polar_store is not None and strips_path.exists():
        try:
            from aeris.aero.solvers.aerosandbox_avl import _compute_strip_profile_drag

            strips_df = read_avl_strips(strips_path, alpha_deg=alpha)
            cd_prof, n_extrap = _compute_strip_profile_drag(
                strips_df, section_map, polar_store,
                s_ref=float(ref["s_ref"]), velocity_mps=velocity,
                mach=mach, altitude_m=altitude,
            )
            if cd_prof is not None:
                result.cd_profile = float(cd_prof)
                result.n_extrapolated_strips = int(n_extrap)
                cd_ind = result.cd_ind or 0.0
                result.cd_total = cd_ind + result.cd_profile
                if result.cl is not None and result.cd_total > 0:
                    result.l_over_d_viscous = result.cl / result.cd_total
                # Cross-check vs AVL's own injected-CDCL CDtot (audit).
                avl_cdtot = result.cd
                if avl_cdtot and avl_cdtot > 0 and result.cd_total > 0:
                    rel = abs(result.cd_total - avl_cdtot) / result.cd_total
                    result.solver_metadata["cd_avl_cdtot"] = avl_cdtot
                    result.solver_metadata[
                        "profile_drag_cd_total_vs_avl_cdtot_rel_diff"
                    ] = rel
                result.solver_metadata["profile_drag_n_extrapolated_strips"] = int(n_extrap)
                if n_extrap > 0:
                    result.warnings.append(
                        f"{n_extrap} strip(s) had cl outside the 2D polar range "
                        "(profile drag clamped)."
                    )
                # Promote the viscous-corrected total to the primary scalar.
                result.cd = result.cd_total
                if result.cl is not None and result.cd_total > 0:
                    result.l_over_d = result.cl / result.cd_total
        except Exception as exc:  # pragma: no cover - strip-drag guard
            result.warnings.append(f"strip profile-drag failed: {exc}")

    result.solver_metadata.update(
        {
            "avl_command": avl_command,
            "timeout_sec": timeout_sec,
            "paneling": {
                "nchordwise": int(nchordwise),
                "spanwise_panels_per_section": int(spanwise_panels_per_section),
                "cspace": float(cspace),
            },
            "representation": representation,
            "cst_points": int(cst_points),
            "viscous": bool(section_map is not None and polar_store is not None),
            "flight_condition": {
                "alpha_deg": alpha, "beta_deg": beta, "mach": mach,
                "velocity_mps": velocity, "altitude_m": altitude,
                "density_kg_m3": density,
                "p_rad_s": p_rad_s, "q_rad_s": q_rad_s, "r_rad_s": r_rad_s,
            },
            "control_input_deg": control_input_deg,
            "diff_input_deg": diff_input_deg,
            "moment_reference_m": list(moment_reference_m),
            "moment_reference_is_cg": bool(moment_reference_is_cg),
            "reference_values_from_geometry": ref,
        }
    )

    result.status = "SUCCESS" if result.cl is not None else "FAILED"

    if write_result_json:
        json_path = output_dir / "native_avl_result.json"
        json_path.write_text(
            json.dumps(result.to_json_dict(), indent=2, default=str), encoding="utf-8"
        )
        result.artifact_paths["native_avl_result_json"] = str(json_path)

    return result
