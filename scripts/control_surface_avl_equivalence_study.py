"""
control_surface_avl_equivalence_study.py

Purpose
-------
Deterministic AVL control-surface equivalence study for one BWB geometry.

This script builds ONE fixed geometry and runs THREE AVL cases:

1) no_cs
   Same airplane, no control surfaces at all.

2) cs_zero
   Same airplane, control surface present, AVL control input = 0.

3) cs_plus5
   Same airplane, same control surface, AVL control input = +5.

Why this exists
---------------
This is a forensic debug script. Its job is not to be pretty.
Its job is to answer these questions cleanly:

- Does adding a control surface at zero input change AVL results relative to no control surface?
- Does +5 deg control input produce different results from zero input?
- Does the exported airplane.avl actually change between cases?
- Are CONTROL blocks present where they should be?

Notes
-----
- Uses AVL through AeroSandbox's AVL wrapper base class.
- Preserves raw AVL files for inspection.
- Makes geometry deterministic by generating planform, twist, and dihedral once,
  then reusing them for all three cases.
- IMPORTANT:
  The actual control magnitude is applied through AVL OPER commands, not through
  the AeroSandbox-exported CONTROL gain.
"""

from __future__ import annotations

import copy
import difflib
import math
import re
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aerosandbox as asb
import matplotlib.pyplot as plt
import numpy as onp
from aerosandbox.aerodynamics.aero_3D.avl import AVL as AVLBase
from aerosandbox.geometry import Wing, WingXSec
from scipy.interpolate import CubicSpline


# =============================================================================
# USER SETTINGS
# =============================================================================

SEED = 42

# Geometry controls
N_POINTS = 10
N_SPL_INBOARD = 6
N_SPL_OUTBOARD = 3
CURVATURE_STRENGTH = 0.3

# Section / airfoil
AIRFOIL_NAME = "naca4412"

# Control surface controls
CONTROL_NAME = "elevon"
HINGE_POINT = 0.75
CONTROL_Y_START_FRAC = 0.60
CONTROL_Y_END_FRAC = 0.95
PLUS_DEFLECTION_DEG = 5.0

# AVL / operating point
AVL_COMMAND = shutil.which("avl") or "avl"
AVL_TIMEOUT_SEC = 30
ALPHA_DEG = 0.433476
BETA_DEG = 0.0
VELOCITY_MPS = 10.0
ALTITUDE_M = 0.0
P_RAD_S = 0.0
Q_RAD_S = 0.0
R_RAD_S = 0.0

# Output
WORKDIR = Path(__file__).resolve().parent / "avl_control_surface_equivalence_study"
SHOW_PLOT = True

# Comparison tolerances for "close enough"
ABS_TOL = {
    "CL": 1e-6,
    "CD": 1e-6,
    "CY": 1e-6,
    "Cl": 1e-6,
    "Cm": 1e-6,
    "Cn": 1e-6,
}
REL_TOL = 1e-4

# AVL paneling
PANEL_CFG = {
    "spanwise_resolution": 12,
    "chordwise_resolution": 8,
    "spanwise_spacing": "equal",
    "chordwise_spacing": "cosine",
}


# =============================================================================
# DATA CONTAINERS
# =============================================================================

@dataclass
class FixedGeometryData:
    planform: dict[str, Any]
    twist_array_deg: onp.ndarray
    dihedral_array_deg: onp.ndarray


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def generate_spline_linear(
    y_vals: onp.ndarray,
    x_vals: onp.ndarray,
    split_index: int,
    curvature_strength: float,
) -> tuple[onp.ndarray, onp.ndarray]:
    y_spline = onp.linspace(onp.min(y_vals), y_vals[split_index], N_SPL_INBOARD)

    spline_func = CubicSpline(y_vals, x_vals, bc_type="clamped")
    x_spline_full = spline_func(y_spline)

    x_linear_baseline = onp.interp(
        y_spline,
        [onp.min(y_vals), y_vals[split_index]],
        [x_vals[0], x_vals[split_index]],
    )

    x_spline = x_linear_baseline + curvature_strength * (
        x_spline_full - x_linear_baseline
    )

    y_linear = onp.linspace(y_vals[split_index], y_vals[-1], N_SPL_OUTBOARD)
    x_linear = onp.interp(
        y_linear,
        [y_vals[split_index], y_vals[-1]],
        [x_vals[split_index], x_vals[-1]],
    )

    return (
        onp.concatenate((y_spline, y_linear[1:])),
        onp.concatenate((x_spline, x_linear[1:])),
    )


def generate_group_segments(
    rng: onp.random.Generator,
    n: int,
    total_length: float,
    variation: float = 0.25,
) -> onp.ndarray:
    mean_seg = total_length / n
    segments = rng.uniform(1 - variation, 1 + variation, n) * mean_seg
    segments = segments * (total_length / onp.sum(segments))
    return segments


def generate_group_sweep(
    rng: onp.random.Generator,
    n: int,
    fixed_s: float,
    variation: float = 0.1,
) -> onp.ndarray:
    return fixed_s * rng.uniform(1 - variation, 1 + variation, n)


def configure_avl_paneling(panel_cfg: dict[str, Any] | None = None) -> None:
    panel_cfg = panel_cfg or {}

    span_spacing = panel_cfg.get("spanwise_spacing", "equal")
    chord_spacing = panel_cfg.get("chordwise_spacing", "cosine")
    span_res = int(panel_cfg.get("spanwise_resolution", 4))
    chord_res = int(panel_cfg.get("chordwise_resolution", 8))

    if span_res <= 0 or chord_res <= 0:
        raise ValueError("AVL panel resolutions must be positive integers.")

    AVLBase.default_analysis_specific_options[Wing]["wing_level_spanwise_spacing"] = False
    AVLBase.default_analysis_specific_options[WingXSec]["spanwise_spacing"] = span_spacing
    AVLBase.default_analysis_specific_options[WingXSec]["spanwise_resolution"] = span_res
    AVLBase.default_analysis_specific_options[Wing]["chordwise_spacing"] = chord_spacing
    AVLBase.default_analysis_specific_options[Wing]["chordwise_resolution"] = chord_res


@contextmanager
def avl_paneling_context(panel_cfg: dict[str, Any] | None = None):
    original = AVLBase.default_analysis_specific_options
    snapshot = copy.deepcopy(original)
    try:
        configure_avl_paneling(panel_cfg=panel_cfg)
        yield
    finally:
        original.clear()
        original.update(snapshot)


def compute_le_curve(
    x0: float,
    y0: float,
    b_params: onp.ndarray,
    s_rad_params: onp.ndarray,
) -> tuple[onp.ndarray, onp.ndarray]:
    x_points = [x0]
    y_points = [y0]
    for b, s_rad in zip(b_params, s_rad_params):
        dx = b / onp.tan(s_rad)
        x_points.append(x_points[-1] - dx)
        y_points.append(y_points[-1] + b)
    return onp.array(x_points), onp.array(y_points)


def parse_avl_output_file(filepath: Path) -> dict[str, float]:
    text = filepath.read_text(encoding="utf-8")
    out: dict[str, float] = {}

    pattern = re.compile(r"([A-Za-z][A-Za-z0-9'/_\.-]*)\s*=\s*([-+0-9.Ee]+)")
    for line in text.splitlines():
        for match in pattern.finditer(line):
            key = match.group(1).strip()
            val = match.group(2).strip()
            try:
                out[key] = float(val)
            except ValueError:
                pass

    for key_to_lowerize in ["Alpha", "Beta", "Mach"]:
        if key_to_lowerize in out:
            out[key_to_lowerize.lower()] = out.pop(key_to_lowerize)

    for key in list(out.keys()):
        if "tot" in key:
            out[key.replace("tot", "")] = out.pop(key)

    return out


def airplane_has_any_control_surface(airplane: asb.Airplane) -> bool:
    for wing in airplane.wings:
        for xsec in wing.xsecs:
            control_surfaces = getattr(xsec, "control_surfaces", None)
            if control_surfaces and len(control_surfaces) > 0:
                return True
    return False


def _rm(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def compute_force_moment_outputs(
    res: dict[str, Any],
    airplane: asb.Airplane,
    op_point: asb.OperatingPoint,
) -> dict[str, Any]:
    q_dyn = op_point.dynamic_pressure()
    s_ref = airplane.s_ref
    b_ref = airplane.b_ref
    c_ref = airplane.c_ref

    derived = dict(res)

    cl = float(derived.get("CL", 0.0))
    cd = float(derived.get("CD", 0.0))
    cy = float(derived.get("CY", 0.0))
    cl_roll = float(derived.get("Cl", 0.0))
    cm = float(derived.get("Cm", 0.0))
    cn = float(derived.get("Cn", 0.0))

    derived["L"] = q_dyn * s_ref * cl
    derived["D"] = q_dyn * s_ref * cd
    derived["Y"] = q_dyn * s_ref * cy

    derived["l_b"] = q_dyn * s_ref * b_ref * cl_roll
    derived["m_b"] = q_dyn * s_ref * c_ref * cm
    derived["n_b"] = q_dyn * s_ref * b_ref * cn

    return derived


def print_selected_results(title: str, res: dict[str, Any]) -> None:
    keys = ["CL", "CD", "CY", "Cl", "Cm", "Cn", "L", "D", "Y", "l_b", "m_b", "n_b"]
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    for k in keys:
        if k in res:
            print(f"{k.rjust(10)} : {res[k]}")


def print_deltas(title: str, a: dict[str, Any], b: dict[str, Any]) -> None:
    keys = ["CL", "CD", "CY", "Cl", "Cm", "Cn", "L", "D", "Y", "l_b", "m_b", "n_b"]
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    for k in keys:
        if k in a and k in b:
            print(f"{k.rjust(10)} : {b[k] - a[k]}")


def compare_scalar_dicts(
    name_a: str,
    a: dict[str, Any],
    name_b: str,
    b: dict[str, Any],
) -> None:
    keys = ["CL", "CD", "CY", "Cl", "Cm", "Cn"]
    print("\n" + "=" * 80)
    print(f"NUMERICAL COMPARISON: {name_a} vs {name_b}")
    print("=" * 80)

    for key in keys:
        va = float(a.get(key, 0.0))
        vb = float(b.get(key, 0.0))
        diff = vb - va
        scale = max(abs(va), abs(vb), 1.0)
        rel = abs(diff) / scale
        close = abs(diff) <= ABS_TOL[key] or rel <= REL_TOL
        verdict = "CLOSE" if close else "DIFFERENT"
        print(
            f"{key.rjust(4)} : "
            f"{name_a}={va:+.10f}  "
            f"{name_b}={vb:+.10f}  "
            f"delta={diff:+.10e}  "
            f"rel={rel:.3e}  "
            f"{verdict}"
        )


def extract_control_lines(avl_text: str) -> list[str]:
    return [line.rstrip() for line in avl_text.splitlines() if line.strip() == "CONTROL"]


def write_avl_diff_report(case_dirs: dict[str, Path], outpath: Path) -> None:
    no_cs_text = (case_dirs["no_cs"] / "airplane.avl").read_text(encoding="utf-8")
    cs_zero_text = (case_dirs["cs_zero"] / "airplane.avl").read_text(encoding="utf-8")
    cs_plus5_text = (case_dirs["cs_plus5"] / "airplane.avl").read_text(encoding="utf-8")

    no_cs_controls = extract_control_lines(no_cs_text)
    cs_zero_controls = extract_control_lines(cs_zero_text)
    cs_plus5_controls = extract_control_lines(cs_plus5_text)

    diff_1 = difflib.unified_diff(
        no_cs_text.splitlines(),
        cs_zero_text.splitlines(),
        fromfile="no_cs/airplane.avl",
        tofile="cs_zero/airplane.avl",
        lineterm="",
    )

    diff_2 = difflib.unified_diff(
        cs_zero_text.splitlines(),
        cs_plus5_text.splitlines(),
        fromfile="cs_zero/airplane.avl",
        tofile="cs_plus5/airplane.avl",
        lineterm="",
    )

    lines: list[str] = []
    lines.append("AVL CONTROL-SURFACE EXPORT REPORT")
    lines.append("=" * 80)
    lines.append("")
    lines.append("CONTROL lines found:")
    lines.append(f"no_cs   : {len(no_cs_controls)}")
    lines.extend([f"  {x}" for x in no_cs_controls] or ["  <none>"])
    lines.append(f"cs_zero : {len(cs_zero_controls)}")
    lines.extend([f"  {x}" for x in cs_zero_controls] or ["  <none>"])
    lines.append(f"cs_plus5: {len(cs_plus5_controls)}")
    lines.extend([f"  {x}" for x in cs_plus5_controls] or ["  <none>"])
    lines.append("")
    lines.append("=" * 80)
    lines.append("DIFF: no_cs -> cs_zero")
    lines.append("=" * 80)
    lines.extend(list(diff_1) or ["<no text differences>"])
    lines.append("")
    lines.append("=" * 80)
    lines.append("DIFF: cs_zero -> cs_plus5")
    lines.append("=" * 80)
    lines.extend(list(diff_2) or ["<no text differences>"])
    lines.append("")

    outpath.write_text("\n".join(lines), encoding="utf-8")


def ensure_avl_available() -> None:
    if shutil.which(AVL_COMMAND) is None and AVL_COMMAND == "avl":
        raise FileNotFoundError(
            "AVL executable not found on PATH. Install AVL or set AVL_COMMAND."
        )


# =============================================================================
# AVL WRAPPER
# =============================================================================

class AVLStudy(AVLBase):
    """
    Minimal AVL wrapper that preserves raw files and parses totals.

    IMPORTANT:
    control_input_deg is applied through AVL OPER commands when controls exist.
    """

    def _default_keystroke_file_contents(self, control_input_deg: float | None = None) -> list[str]:
        run_file_contents: list[str] = []

        run_file_contents += ["plop", "g", ""]
        run_file_contents += ["oper"]
        run_file_contents += ["o", "r", "d", "v", ""]

        run_file_contents += [
            "m",
            f"mn {float(self.op_point.mach())}",
            f"v {float(self.op_point.velocity)}",
            f"d {float(self.op_point.atmosphere.density())}",
            "g 9.81",
            "",
        ]

        p_bar = self.op_point.p * self.airplane.b_ref / (2 * self.op_point.velocity)
        q_bar = self.op_point.q * self.airplane.c_ref / (2 * self.op_point.velocity)
        r_bar = self.op_point.r * self.airplane.b_ref / (2 * self.op_point.velocity)

        run_file_contents += [
            f"a a {float(self.op_point.alpha)}",
            f"b b {float(self.op_point.beta)}",
            f"r r {float(p_bar)}",
            f"p p {float(q_bar)}",
            f"y y {float(r_bar)}",
        ]

        # IMPORTANT:
        # We now explicitly set the AVL control variable value.
        # This avoids relying on AeroSandbox to serialize deflection magnitude
        # into the exported CONTROL gain, which your study proved it does not do.
        if airplane_has_any_control_surface(self.airplane):
            value = 0.0 if control_input_deg is None else float(control_input_deg)
            run_file_contents += ["d1", "d1", f"{value}"]

        return run_file_contents

    def run_case(self, case_name: str, control_input_deg: float | None = None) -> dict[str, Any]:
        directory = Path(self.working_directory) / case_name
        directory.mkdir(parents=True, exist_ok=True)

        airplane_file = "airplane.avl"
        keystrokes_file = "keystrokes.txt"
        stdout_file = "avl_stdout.txt"
        totals_filename = "output.txt"
        stability_filename = "stability.txt"
        body_derivs_filename = "body_derivs.txt"
        strips_filename = "strips.txt"
        body_filename = "body.txt"
        hinge_filename = "hinge.txt"

        _rm(directory / totals_filename)
        _rm(directory / stability_filename)
        _rm(directory / body_derivs_filename)
        _rm(directory / strips_filename)
        _rm(directory / body_filename)
        _rm(directory / hinge_filename)
        _rm(directory / stdout_file)
        _rm(directory / keystrokes_file)

        has_cs = airplane_has_any_control_surface(self.airplane)
        print(
            f"[{case_name}] airplane_has_any_control_surface = {has_cs}, "
            f"control_input_deg = {control_input_deg}"
        )

        self.write_avl(directory / airplane_file)

        keystroke_lines = self._default_keystroke_file_contents(control_input_deg=control_input_deg)
        keystroke_lines += [
            "x",
            "ft", totals_filename,
            "fs", strips_filename,
            "fb", body_filename,
            "hm", hinge_filename,
            "st", stability_filename,
            "sb", body_derivs_filename,
            "",
            "quit",
        ]

        (directory / keystrokes_file).write_text(
            "\n".join(keystroke_lines),
            encoding="utf-8",
        )

        stdout_path = directory / stdout_file
        proc = None

        try:
            with open(stdout_path, "w", encoding="utf-8") as avl_log:
                proc = subprocess.Popen(
                    [self.avl_command, airplane_file],
                    cwd=directory,
                    stdin=subprocess.PIPE,
                    stdout=avl_log,
                    stderr=avl_log,
                    text=True,
                )
                proc.communicate(input="\n".join(keystroke_lines), timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            if proc is not None:
                proc.kill()
                proc.communicate()
            raise TimeoutError(
                f"AVL timed out after {self.timeout} s. See log: {stdout_path}"
            ) from exc

        log_text = stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else ""

        if "Strip array overflow" in log_text or "SDUPL: Strip array overflow" in log_text:
            raise RuntimeError("AVL strip array overflow. Reduce mesh density/sections.")
        if "MAKESURF: Array overflow" in log_text:
            raise RuntimeError("AVL surface array overflow. Geometry too dense for AVL.")
        if "Insufficient number of spanwise vortices to work with" in log_text:
            raise RuntimeError(
                "AVL spanwise paneling failure. Increase spanwise_resolution or reduce xsec count."
            )

        totals_path = directory / totals_filename
        if not totals_path.exists():
            raise FileNotFoundError(
                f"AVL did not write '{totals_filename}'. See log: {stdout_path}"
            )

        result = parse_avl_output_file(totals_path)
        result["_files"] = {
            "working_dir": str(directory),
            "airplane_avl": str(directory / airplane_file),
            "keystrokes": str(directory / keystrokes_file),
            "stdout": str(stdout_path),
            "totals": str(totals_path),
            "stability": str(directory / stability_filename),
            "body_derivs": str(directory / body_derivs_filename),
            "strips": str(directory / strips_filename),
            "body": str(directory / body_filename),
            "hinge": str(directory / hinge_filename),
        }
        return result


# =============================================================================
# GEOMETRY BUILD
# =============================================================================

def build_fixed_planform(rng: onp.random.Generator) -> dict[str, Any]:
    c1_min, c1_max = 1.2, 2.0
    c2_min_ratio, c2_max_ratio = 0.45, 0.65
    c3_min_ratio, c3_max_ratio = 0.30, 0.45
    c4_min_ratio, c4_max_ratio = 0.07, 0.2

    b_total_min, b_total_max = 1.2, 2.0
    c1_btot_ratio_min, c1_btot_ratio_max = c1_min / b_total_max, c1_max / b_total_min

    b3_min_lim = 0.45
    b3_max_lim = 0.55

    split_ratio_min = 0.35
    split_ratio_max = 0.55

    sw1_min, sw1_max = 25, 60
    sw2_min, sw2_max = 10, 60
    sw3_min, sw3_max = 0, 40

    c1 = rng.uniform(c1_min, c1_max)
    c2 = c1 * rng.uniform(c2_min_ratio, c2_max_ratio)
    c3 = c1 * rng.uniform(c3_min_ratio, c3_max_ratio)
    c4 = c1 * rng.uniform(c4_min_ratio, c4_max_ratio)

    b_total = c1 / rng.uniform(c1_btot_ratio_min, c1_btot_ratio_max)
    b3 = b_total * rng.uniform(b3_min_lim, b3_max_lim)

    remaining_b = b_total - b3
    split_ratio = rng.uniform(split_ratio_min, split_ratio_max)

    b1 = remaining_b * split_ratio
    b2 = remaining_b - b1

    sw1 = -rng.uniform(sw1_min, sw1_max)
    sw2 = -rng.uniform(sw2_min, sw2_max)
    sw3 = -rng.uniform(sw3_min, sw3_max)
    sw1_rad, sw2_rad, sw3_rad = onp.radians(90 - onp.array([sw1, sw2, sw3]))

    n1 = int(round((b1 / b_total) * (N_POINTS - 1)))
    n2 = int(round((b2 / b_total) * (N_POINTS - 1)))
    n3 = (N_POINTS - 1) - n1 - n2

    b_group1 = generate_group_segments(rng, n1, b1)
    b_group2 = generate_group_segments(rng, n2, b2)
    b_group3 = generate_group_segments(rng, n3, b3)
    b_le = onp.concatenate((b_group1, b_group2, b_group3))

    s_group1 = generate_group_sweep(rng, n1, sw1_rad)
    s_group2 = generate_group_sweep(rng, n2, sw2_rad)
    s_group3 = generate_group_sweep(rng, n3, sw3_rad)
    s_rad_le = onp.concatenate((s_group1, s_group2, s_group3))

    x0_le, y0_le = 0.0, 0.0
    x_le, y_le = compute_le_curve(x0_le, y0_le, b_le, s_rad_le)

    key_indices = [0, n1, n1 + n2, N_POINTS - 1]
    key_chords = onp.array([c1, c2, c3, c4])
    all_indices = onp.arange(N_POINTS)
    chords = onp.interp(all_indices, key_indices, key_chords)

    x_te = x_le + chords
    y_te = y_le.copy()

    split_idx = int(N_POINTS * 0.55)
    front_y_fine, front_x_fine = generate_spline_linear(
        y_le, x_le, split_idx, curvature_strength=CURVATURE_STRENGTH
    )
    rear_y_fine, rear_x_fine = generate_spline_linear(
        y_te, x_te, split_idx, curvature_strength=CURVATURE_STRENGTH
    )

    return {
        "N1": n1,
        "N2": n2,
        "N3": n3,
        "x_le": x_le,
        "y_le": y_le,
        "x_te": x_te,
        "y_te": y_te,
        "front_x_fine": front_x_fine,
        "front_y_fine": front_y_fine,
        "rear_x_fine": rear_x_fine,
        "rear_y_fine": rear_y_fine,
    }


def build_fixed_geometry(seed: int) -> FixedGeometryData:
    rng = onp.random.default_rng(seed)
    planform = build_fixed_planform(rng)

    y_le = planform["y_le"]
    front_y_fine = planform["front_y_fine"]

    n1 = planform["N1"]
    n2 = planform["N2"]
    group_boundary_y = onp.array([y_le[0], y_le[n1], y_le[n1 + n2], y_le[-1]])

    twist_boundaries = rng.uniform(-5.0, 5.0, size=4)
    dihedral_boundaries = onp.concatenate(([0.0], rng.uniform(-5.0, 5.0, size=3)))

    twist_array_deg = onp.interp(front_y_fine, group_boundary_y, twist_boundaries)
    dihedral_array_deg = onp.interp(front_y_fine, group_boundary_y, dihedral_boundaries)

    return FixedGeometryData(
        planform=planform,
        twist_array_deg=twist_array_deg,
        dihedral_array_deg=dihedral_array_deg,
    )


def plot_planform(planform: dict[str, Any]) -> None:
    front_x_fine = planform["front_x_fine"]
    front_y_fine = planform["front_y_fine"]
    rear_x_fine = planform["rear_x_fine"]
    rear_y_fine = planform["rear_y_fine"]
    x_le = planform["x_le"]
    y_le = planform["y_le"]
    x_te = planform["x_te"]

    plt.figure(figsize=(10, 6))
    for i in range(len(x_le)):
        plt.plot([x_le[i], x_te[i]], [y_le[i], y_le[i]], "k--", alpha=0.3)

    plt.plot(front_x_fine, front_y_fine, "g-", linewidth=2, label="LE")
    plt.plot(rear_x_fine, rear_y_fine, "m-", linewidth=2, label="TE")
    plt.plot(front_x_fine, -front_y_fine, "g--", linewidth=2)
    plt.plot(rear_x_fine, -rear_y_fine, "m--", linewidth=2)

    plt.title("Deterministic BWB Planform Used for AVL Control Study")
    plt.xlabel("x")
    plt.ylabel("y")
    plt.grid(True)
    plt.legend(loc="best")
    plt.axis("equal")
    plt.tight_layout()
    plt.show()


def build_airplane_from_fixed_geometry(
    fixed: FixedGeometryData,
    include_control_surface: bool,
) -> asb.Airplane:
    planform = fixed.planform
    front_x_fine = planform["front_x_fine"]
    front_y_fine = planform["front_y_fine"]
    rear_x_fine = planform["rear_x_fine"]

    twist_array = fixed.twist_array_deg
    dihedral_array = fixed.dihedral_array_deg

    y_max = float(onp.max(front_y_fine))
    y_min_cs = CONTROL_Y_START_FRAC * y_max
    y_max_cs = CONTROL_Y_END_FRAC * y_max

    airfoil = asb.Airfoil(AIRFOIL_NAME)
    num_sections = len(front_y_fine)

    wing_xsecs = []
    for i in range(num_sections):
        y_here = float(front_y_fine[i])

        add_cs_here = (
            include_control_surface
            and i < num_sections - 1
            and y_min_cs <= y_here <= y_max_cs
        )

        control_surfaces = []
        if add_cs_here:
            # IMPORTANT:
            # Keep deflection = 0.0 here.
            # The actual AVL control value is set later through OPER commands.
            control_surfaces = [
                asb.ControlSurface(
                    name=CONTROL_NAME,
                    trailing_edge=True,
                    hinge_point=HINGE_POINT,
                    deflection=0.0,
                    symmetric=True,
                )
            ]

        z_here = y_here * math.tan(math.radians(float(dihedral_array[i])))

        wing_xsecs.append(
            asb.WingXSec(
                xyz_le=[float(front_x_fine[i]), y_here, z_here],
                chord=float(rear_x_fine[i] - front_x_fine[i]),
                twist=float(twist_array[i]),
                airfoil=airfoil,
                control_surfaces=control_surfaces,
            )
        )

    case_name = "BWB_no_cs" if not include_control_surface else f"BWB_{CONTROL_NAME}_enabled"

    airplane = asb.Airplane(
        name=case_name,
        xyz_ref=[0.0, 0.0, 0.0],
        wings=[
            asb.Wing(
                name="BWB_Wing",
                symmetric=True,
                xsecs=wing_xsecs,
            )
        ],
    )
    return airplane


def make_op_point() -> asb.OperatingPoint:
    return asb.OperatingPoint(
        atmosphere=asb.Atmosphere(altitude=ALTITUDE_M),
        velocity=VELOCITY_MPS,
        alpha=ALPHA_DEG,
        beta=BETA_DEG,
        p=P_RAD_S,
        q=Q_RAD_S,
        r=R_RAD_S,
    )


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    ensure_avl_available()

    WORKDIR.mkdir(parents=True, exist_ok=True)
    print(f"Working directory: {WORKDIR}")

    fixed = build_fixed_geometry(SEED)

    if SHOW_PLOT:
        plot_planform(fixed.planform)

    no_cs_airplane = build_airplane_from_fixed_geometry(
        fixed=fixed,
        include_control_surface=False,
    )
    cs_airplane = build_airplane_from_fixed_geometry(
        fixed=fixed,
        include_control_surface=True,
    )

    op_point = make_op_point()

    avl_no_cs = AVLStudy(
        airplane=no_cs_airplane,
        op_point=op_point,
        working_directory=str(WORKDIR),
        avl_command=AVL_COMMAND,
        timeout=AVL_TIMEOUT_SEC,
        verbose=True,
    )
    avl_cs_zero = AVLStudy(
        airplane=cs_airplane,
        op_point=op_point,
        working_directory=str(WORKDIR),
        avl_command=AVL_COMMAND,
        timeout=AVL_TIMEOUT_SEC,
        verbose=True,
    )
    avl_cs_plus5 = AVLStudy(
        airplane=cs_airplane,
        op_point=op_point,
        working_directory=str(WORKDIR),
        avl_command=AVL_COMMAND,
        timeout=AVL_TIMEOUT_SEC,
        verbose=True,
    )

    with avl_paneling_context(PANEL_CFG):
        raw_no_cs = avl_no_cs.run_case("no_cs", control_input_deg=None)
        raw_cs_zero = avl_cs_zero.run_case("cs_zero", control_input_deg=0.0)
        raw_cs_plus5 = avl_cs_plus5.run_case("cs_plus5", control_input_deg=PLUS_DEFLECTION_DEG)

    res_no_cs = compute_force_moment_outputs(raw_no_cs, no_cs_airplane, op_point)
    res_cs_zero = compute_force_moment_outputs(raw_cs_zero, cs_airplane, op_point)
    res_cs_plus5 = compute_force_moment_outputs(raw_cs_plus5, cs_airplane, op_point)

    print_selected_results("CASE: no_cs", res_no_cs)
    print_selected_results("CASE: cs_zero", res_cs_zero)
    print_selected_results("CASE: cs_plus5", res_cs_plus5)

    print_deltas("DELTA: cs_zero - no_cs", res_no_cs, res_cs_zero)
    print_deltas("DELTA: cs_plus5 - cs_zero", res_cs_zero, res_cs_plus5)
    print_deltas("DELTA: cs_plus5 - no_cs", res_no_cs, res_cs_plus5)

    compare_scalar_dicts("no_cs", res_no_cs, "cs_zero", res_cs_zero)
    compare_scalar_dicts("cs_zero", res_cs_zero, "cs_plus5", res_cs_plus5)

    case_dirs = {
        "no_cs": Path(raw_no_cs["_files"]["working_dir"]),
        "cs_zero": Path(raw_cs_zero["_files"]["working_dir"]),
        "cs_plus5": Path(raw_cs_plus5["_files"]["working_dir"]),
    }

    report_path = WORKDIR / "avl_export_diff_report.txt"
    write_avl_diff_report(case_dirs, report_path)

    print("\nSaved AVL artifacts:")
    for case_name, case_dir in case_dirs.items():
        print(f"  {case_name:<8}: {case_dir}")

    print(f"\nAVL export diff report: {report_path}")

    print("\nWhat to inspect next:")
    print("1) no_cs/airplane.avl      -> should have no CONTROL blocks")
    print("2) cs_zero/airplane.avl    -> should have CONTROL blocks")
    print("3) cs_plus5/airplane.avl   -> should have CONTROL blocks")
    print("4) cs_zero/keystrokes.txt  -> should contain d1 / d1 / 0")
    print("5) cs_plus5/keystrokes.txt -> should contain d1 / d1 / 5")
    print("6) avl_export_diff_report.txt")
    print("7) each case's avl_stdout.txt and hinge.txt")


if __name__ == "__main__":
    main()