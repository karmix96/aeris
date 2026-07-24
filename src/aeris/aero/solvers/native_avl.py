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
  * ``read_avl_strips``              — strip-forces parse (pure pandas)
  * ``_compute_strip_profile_drag``  — strip profile-drag integration (data-only)

The viscous total follows the same definition as the ASB path:
    cd_total = cd_induced_AVL + cd_profile_NeuralFoil
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from aeris.generators.bwb_segmented_v1.pygeo_adapter import realised_reference_metrics

_TOTALS_KEYS = {
    "CLtot": "cl",
    "CDtot": "cd",
    "CDind": "cd_ind",
    "CDvis": "cd_vis",
    "Cmtot": "cm",
    "CLff": "cl_ff",
    "CDff": "cd_ff",
    "CYtot": "cy",
}


@dataclass
class NativeAvlResult:
    status: str
    cl: float | None = None
    cd: float | None = None            # promoted to viscous total when available
    cd_ind: float | None = None
    cd_vis: float | None = None        # AVL's own injected-CDCL viscous drag
    cd_ff: float | None = None
    cm: float | None = None
    cd_profile: float | None = None    # NeuralFoil strip-integrated profile drag
    cd_total: float | None = None      # cd_ind + cd_profile
    l_over_d: float | None = None
    l_over_d_viscous: float | None = None
    n_sections: int = 0
    n_cdcl_injected: int = 0
    n_extrapolated_strips: int | None = None
    solver_metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    artifact_dir: str | None = None


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
    nchordwise: int = 8,
    cspace: float = 1.0,
    spanwise_panels_per_section: int = 4,
    representation: str = "cst",
    cst_points: int = 80,
    control: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a .avl (+ per-section .af coordinate files) from pyGeo sections.

    Returns reference values {s_ref, c_ref, b_ref}. Each SECTION gets an all-zero
    CDCL placeholder for inject_polar_cdcl to fill.
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
        "0.0 0.0 0.0",
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
    ctrl_sgndup = 1 if (control and control.get("symmetric", True)) else -1

    n = len(ordered)
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
        # Control surface on interval sections within the elevon span band.
        frac = float(getattr(sec, "span_fraction", le[1]))
        if control and i != n - 1 and ctrl_start <= frac <= ctrl_end:
            lines += [
                "CONTROL",
                "#name, gain, Xhinge, XYZhvec, SgnDup",
                f"{ctrl_name} 1 {ctrl_hinge} 0 0 0 {ctrl_sgndup}",
                "",
            ]
        lines += [
            "CDCL",
            "#CL1  CD1  CL2  CD2  CL3  CD3",
            "0 0 0 0 0 0",
            "",
        ]

    avl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"s_ref": s_ref, "c_ref": c_ref, "b_ref": b_ref, "has_control": bool(control)}


def _write_selig(path: Path, coords: np.ndarray) -> None:
    c = np.asarray(coords, dtype=float)
    path.write_text(
        "\n".join(f"{x:.6f} {y:.6f}" for x, y in c) + "\n", encoding="utf-8"
    )


def _parse_totals(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for avl_key, our_key in _TOTALS_KEYS.items():
        m = re.search(rf"{avl_key}\s*=\s*(-?\d[\d.eE+\-]*)", text)
        if m:
            try:
                out[our_key] = float(m.group(1))
            except ValueError:
                pass
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
    avl_command: str = "avl",
    timeout_sec: int = 180,
    nchordwise: int = 8,
    spanwise_panels_per_section: int = 4,
    representation: str = "cst",
    cst_points: int = 80,
    name: str = "pygeo_bwb",
) -> NativeAvlResult:
    """Author a native .avl from pyGeo sections, run AVL, apply the viscous
    correction, and return the corrected result. No asb.Airplane is constructed."""
    from aeris.aero.solvers.avl_polar_injection import inject_polar_cdcl

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(sections, key=lambda s: float(s.y_m))

    fc = flight_condition
    velocity = float(getattr(fc, "velocity_mps", 28.0))
    altitude = float(getattr(fc, "altitude_m", 0.0))
    alpha = float(getattr(fc, "alpha_deg", 0.0))
    beta = float(getattr(fc, "beta_deg", 0.0))
    density, sound_speed = _atmosphere(altitude)
    mach = getattr(fc, "mach", None)
    if not mach:
        mach = velocity / sound_speed if sound_speed > 0 else 0.0
    mach = float(mach)

    avl_path = output_dir / "airplane.avl"
    ref = write_native_avl(
        ordered, avl_path, name=name, mach=mach, symmetric=True,
        nchordwise=nchordwise, spanwise_panels_per_section=spanwise_panels_per_section,
        representation=representation, cst_points=cst_points, control=control,
    )

    result = NativeAvlResult(status="PENDING", n_sections=len(ordered),
                             artifact_dir=str(output_dir))

    # Viscous CDCL injection (fills the zero placeholders) before running.
    if section_map is not None and polar_store is not None:
        try:
            result.n_cdcl_injected = inject_polar_cdcl(
                avl_path, section_map, polar_store, velocity, mach, altitude
            )
        except Exception as exc:  # pragma: no cover - injection guard
            result.warnings.append(f"CDCL injection failed: {exc}")

    # Keystrokes: OPER, set condition, execute, dump totals + strips.
    totals_file = "totals.txt"
    strip_file = "strips.txt"
    # AVL reads the operating Mach from the .avl header; velocity/density only
    # scale forces, not the coefficients we parse, so they are not set here.
    keys: list[str] = ["oper", f"a a {alpha}", f"b b {beta}"]
    if control:
        keys += ["d1", "d1", f"{control_input_deg}"]
    keys += ["x", "ft", totals_file, "fs", strip_file, "", "quit"]

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

    totals_path = output_dir / totals_file
    if not totals_path.exists():
        result.status = "FAILED"
        result.warnings.append("AVL did not write a totals file; see avl_stdout.txt")
        return result

    totals = _parse_totals(totals_path.read_text(encoding="utf-8"))
    result.cl = totals.get("cl")
    result.cd = totals.get("cd")
    result.cd_ind = totals.get("cd_ind")
    result.cd_vis = totals.get("cd_vis")
    result.cd_ff = totals.get("cd_ff")
    result.cm = totals.get("cm")
    if result.cl is not None and result.cd and result.cd > 0:
        result.l_over_d = result.cl / result.cd

    # Independent strip profile-drag integration + viscous total.
    strips_path = output_dir / strip_file
    if section_map is not None and polar_store is not None and strips_path.exists():
        try:
            from aeris.aero.solvers.aerosandbox_avl import (
                _compute_strip_profile_drag,
                read_avl_strips,
            )

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

    result.status = "SUCCESS" if result.cl is not None else "FAILED"
    return result
