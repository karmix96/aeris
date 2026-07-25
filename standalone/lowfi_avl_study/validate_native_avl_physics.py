"""Independent PHYSICS validation of the native AVL writer — not code-to-code.

Why this exists
---------------
Task 3 compared the native path against the AeroSandbox path and found <0.1 %
agreement on undeflected geometry. That bounds implementation error but cannot
detect a SHARED error, and two shared errors are structurally invisible to it:

  * both paths share `inject_polar_cdcl` and `_compute_strip_profile_drag`;
  * both read `section.twist_deg`, `x_le`, `z_le` from the SAME source, so a sign
    or reference-axis error would be identically wrong in both and agree to 1e-7.

So this validates the writer against CLOSED-FORM AERODYNAMICS and against sign
conventions, on wings whose answers are known independently of any code in this
repository.

The sections are built by a local `SyntheticSection` stub, so these cases exercise
`write_native_avl` / `run_native_avl_case` with no pyGeo involvement at all — which
also demonstrates the writer is genuinely decoupled from the geometry backend.

Cases
-----
A  ELLIPTIC untwisted planform, symmetric airfoil, AR 6.
   Known answer: span efficiency e = 1.0 exactly (elliptic loading is the
   minimum-induced-drag distribution). This is the single most demanding check on
   the geometry encoding — span, chord distribution, area and the Trefftz-plane
   integration must all be right for e to come out at 1.

B  RECTANGULAR untwisted planform, symmetric airfoil, AR 6.
   Known answers: CL(alpha=0) = 0 (symmetric, untwisted);
   CL_alpha ~ Helmbold 2*pi*AR/(2+sqrt(AR^2+4)) = 4.53 /rad;
   neutral point at the quarter chord, Xnp/c = 0.25 (unswept, straight wing).

C  TWIST sign convention. Same rectangular wing with -5 deg (washout) and
   +5 deg (wash-in) linear tip twist. Physics: washout must REDUCE CL and must
   reduce the TIP strip cl relative to the root; wash-in must do the opposite.

D  DIHEDRAL sign convention. Rectangular wing with +10 deg dihedral must make
   Clb (roll-due-to-sideslip) MORE NEGATIVE — the classic dihedral effect.

E  SWEEP sign convention. Rectangular wing swept AFT 30 deg must move the
   neutral point AFT (larger Xnp).

Usage:
    python standalone/lowfi_avl_study/validate_native_avl_physics.py
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "lowfi_avl_study" / "physics_validation"

N_SECTIONS = 41          # fine, so discretisation is not the limiting error
NCHORDWISE = 12
SPANWISE_PER_SECTION = 3
VELOCITY = 28.0


# --------------------------------------------------------------------------
# A minimal stand-in for pyGeo's ExtractedSection: only what the writer reads.
# --------------------------------------------------------------------------
def naca_symmetric(thickness: float = 0.12, n: int = 80) -> np.ndarray:
    """NACA 00xx coordinates, closed loop TE -> upper -> LE -> lower -> TE.

    Closed-form (Jacobs/Ward/Pinkerton thickness distribution) so the airfoil is
    independent of the repository's airfoil database.
    """
    beta = np.linspace(0.0, math.pi, n)
    x = 0.5 * (1.0 - np.cos(beta))
    yt = (thickness / 0.2) * (
        0.2969 * np.sqrt(np.clip(x, 0.0, None))
        - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1015 * x**4
    )
    upper = np.column_stack([x, yt])[::-1]     # TE -> LE
    lower = np.column_stack([x, -yt])[1:]      # LE -> TE
    return np.vstack([upper, lower])


class _CST:
    def __init__(self, coords: np.ndarray) -> None:
        self._coords = coords

    def coordinates(self, n_per_surface: int = 80) -> np.ndarray:
        return self._coords


@dataclass
class SyntheticSection:
    y_m: float
    chord_m: float
    x_le_m: float = 0.0
    z_le_m: float = 0.0
    twist_deg: float = 0.0
    span_fraction: float = 0.0
    thickness: float = 0.12

    def __post_init__(self) -> None:
        self.cst = _CST(naca_symmetric(self.thickness))
        self.direct_coordinates = self.cst.coordinates()

    @property
    def le_xyz_m(self) -> np.ndarray:
        return np.array([self.x_le_m, self.y_m, self.z_le_m], dtype=float)


def build_wing(
    *,
    planform: str,
    aspect_ratio: float = 6.0,
    tip_twist_deg: float = 0.0,
    dihedral_deg: float = 0.0,
    sweep_deg: float = 0.0,
    n: int = N_SECTIONS,
) -> list[SyntheticSection]:
    """Analytic half-wing. Reference area/span chosen so AR is exact."""
    semi = 1.0
    if planform == "rectangular":
        # S = 2*semi*c  and AR = (2*semi)^2/S  =>  c = 2*semi/AR
        c_root = 2.0 * semi / aspect_ratio
        chord = lambda eta: c_root * np.ones_like(eta)  # noqa: E731
    elif planform == "elliptic":
        # S = 2 * (pi/4) * c0 * semi ; AR = (2 semi)^2 / S => c0 = 8 semi/(pi AR)
        c0 = 8.0 * semi / (math.pi * aspect_ratio)
        chord = lambda eta: c0 * np.sqrt(np.clip(1.0 - eta**2, 0.0, None))  # noqa: E731
    else:
        raise ValueError(planform)

    eta = np.linspace(0.0, 1.0, n)
    # Keep the outermost station off the exact elliptic tip so the chord stays
    # finite; AVL cannot take a zero-chord section.
    if planform == "elliptic":
        eta = np.linspace(0.0, 0.999, n)

    chords = chord(eta)
    y = eta * semi
    tan_dih = math.tan(math.radians(dihedral_deg))
    tan_sw = math.tan(math.radians(sweep_deg))

    sections = []
    for e, yy, cc in zip(eta, y, chords):
        sections.append(SyntheticSection(
            y_m=float(yy), chord_m=float(cc),
            x_le_m=float(yy * tan_sw),
            z_le_m=float(yy * tan_dih),
            twist_deg=float(tip_twist_deg * e),
            span_fraction=float(e),
        ))
    return sections


def run(sections, tag: str, alpha: float) -> dict:
    from aeris.aero.models import FlightCondition
    from aeris.aero.solvers.native_avl import run_native_avl_case

    fc = FlightCondition(alpha_deg=alpha, beta_deg=2.0, velocity_mps=VELOCITY,
                         altitude_m=0.0)
    res = run_native_avl_case(
        sections, flight_condition=fc, output_dir=OUT / tag,
        nchordwise=NCHORDWISE, spanwise_panels_per_section=SPANWISE_PER_SECTION,
        name="validate",
    )
    stab = res.stability_axis_derivatives or {}
    out = {
        "status": res.status, "alpha_deg": alpha,
        "CL": res.cl, "CDind": res.cd_ind, "Cm": res.cm,
        "e": res.span_efficiency, "Xnp": res.x_np,
        "Xnp_over_cref": res.x_np_over_c_ref,
        "CLa": stab.get("CLa"), "Cma": stab.get("Cma"), "Clb": stab.get("Clb"),
        "s_ref": res.s_ref, "b_ref": res.b_ref, "c_ref": res.c_ref,
        "aspect_ratio": (res.b_ref ** 2 / res.s_ref) if res.s_ref else None,
        "strips_csv": res.artifact_paths.get("strips_parsed"),
    }
    return out


def strip_cl_profile(csv_path: str) -> tuple[float, float]:
    """(root-region cl, tip-region cl) from the parsed strip table, y >= 0 half."""
    df = pd.read_csv(csv_path)
    df = df[df["y_le"] >= 0].sort_values("y_le")
    n = len(df)
    root = float(df["cl_local"].iloc[: max(1, n // 10)].mean())
    tip = float(df["cl_local"].iloc[-max(1, n // 10):].mean())
    return root, tip


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    AR = 6.0
    helmbold = 2 * math.pi * AR / (2 + math.sqrt(AR**2 + 4))
    lifting_line = (2 * math.pi) / (1 + (2 * math.pi) / (math.pi * AR))

    results: dict = {"reference_values": {
        "aspect_ratio": AR,
        "helmbold_CLa_per_rad": helmbold,
        "lifting_line_CLa_per_rad_e1": lifting_line,
    }}
    checks: list[dict] = []

    def check(name, value, expected, tol, note, kind="abs"):
        if value is None:
            ok, err = False, None
        elif kind == "abs":
            err = abs(value - expected)
            ok = err <= tol
        else:
            err = abs(value - expected) / abs(expected)
            ok = err <= tol
        checks.append({"check": name, "value": value, "expected": expected,
                       "tolerance": tol, "kind": kind, "error": err,
                       "pass": bool(ok), "note": note})

    # ---- A: elliptic wing, e must be 1 -----------------------------------
    ell = build_wing(planform="elliptic", aspect_ratio=AR)
    a = run(ell, "A_elliptic", alpha=5.0)
    results["A_elliptic"] = a
    check("A: AR encoded correctly", a["aspect_ratio"], AR, 0.03, "rel", kind="rel")
    check("A: elliptic span efficiency e = 1", a["e"], 1.0, 0.05,
          "elliptic loading is the minimum-induced-drag distribution; "
          "e=1 requires span, chord distribution, area AND the Trefftz "
          "integration all to be encoded correctly")

    # ---- B: rectangular wing, closed-form CLa / Xnp / CL(0) ---------------
    rect0 = build_wing(planform="rectangular", aspect_ratio=AR)
    b0 = run(rect0, "B_rect_alpha0", alpha=0.0)
    b5 = run(rect0, "B_rect_alpha5", alpha=5.0)
    results["B_rect_alpha0"] = b0
    results["B_rect_alpha5"] = b5
    check("B: symmetric untwisted CL(alpha=0) = 0", b0["CL"], 0.0, 5e-3,
          "NACA 0012, no twist, no camber => zero lift at zero incidence")
    check("B: CLa vs Helmbold", b5["CLa"], helmbold, 0.10,
          f"Helmbold low-AR formula gives {helmbold:.3f} /rad; AVL should sit "
          "between Helmbold and the lifting-line value", kind="rel")
    check("B: unswept neutral point at quarter chord", b5["Xnp_over_cref"], 0.25,
          0.05, "straight unswept wing: aerodynamic centre at c/4")

    # ---- C: twist sign convention ----------------------------------------
    wash_out = run(build_wing(planform="rectangular", aspect_ratio=AR,
                              tip_twist_deg=-5.0), "C_washout", alpha=5.0)
    wash_in = run(build_wing(planform="rectangular", aspect_ratio=AR,
                             tip_twist_deg=+5.0), "C_washin", alpha=5.0)
    results["C_washout"] = wash_out
    results["C_washin"] = wash_in
    checks.append({
        "check": "C: washout REDUCES CL (twist sign)",
        "value": wash_out["CL"], "expected": f"< {b5['CL']}", "tolerance": None,
        "kind": "ordering", "error": None,
        "pass": bool(wash_out["CL"] < b5["CL"]),
        "note": "negative tip twist = nose-down at the tip = less lift. This is "
                "INVISIBLE to a code-to-code check because both writers read the "
                "same twist_deg field.",
    })
    checks.append({
        "check": "C: wash-in INCREASES CL (twist sign)",
        "value": wash_in["CL"], "expected": f"> {b5['CL']}", "tolerance": None,
        "kind": "ordering", "error": None,
        "pass": bool(wash_in["CL"] > b5["CL"]), "note": "mirror of the above",
    })
    if wash_out.get("strips_csv") and b5.get("strips_csv"):
        r_base, t_base = strip_cl_profile(b5["strips_csv"])
        r_wo, t_wo = strip_cl_profile(wash_out["strips_csv"])
        results["C_strip_loading"] = {
            "untwisted_root_cl": r_base, "untwisted_tip_cl": t_base,
            "washout_root_cl": r_wo, "washout_tip_cl": t_wo,
            "tip_cl_change": t_wo - t_base, "root_cl_change": r_wo - r_base,
        }
        checks.append({
            "check": "C: washout unloads the TIP specifically",
            "value": t_wo - t_base, "expected": "< 0 and more negative than root",
            "tolerance": None, "kind": "ordering", "error": None,
            "pass": bool((t_wo - t_base) < 0 and (t_wo - t_base) < (r_wo - r_base)),
            "note": "spanwise loading must shift inboard, not just scale down — "
                    "checks the twist is applied PER SECTION, not globally",
        })

    # ---- D: dihedral sign convention -------------------------------------
    dih = run(build_wing(planform="rectangular", aspect_ratio=AR,
                         dihedral_deg=10.0), "D_dihedral", alpha=5.0)
    results["D_dihedral"] = dih
    checks.append({
        "check": "D: dihedral makes Clb MORE NEGATIVE (dihedral effect)",
        "value": dih["Clb"], "expected": f"< {b5['Clb']}", "tolerance": None,
        "kind": "ordering", "error": None,
        "pass": bool(dih["Clb"] is not None and b5["Clb"] is not None
                     and dih["Clb"] < b5["Clb"]),
        "note": "classic result: positive dihedral increases roll stiffness in "
                "sideslip. Checks the z_le sign convention.",
    })

    # ---- E: sweep sign convention ----------------------------------------
    swept = run(build_wing(planform="rectangular", aspect_ratio=AR,
                           sweep_deg=30.0), "E_swept", alpha=5.0)
    results["E_swept"] = swept
    checks.append({
        "check": "E: aft sweep moves the neutral point AFT",
        "value": swept["Xnp"], "expected": f"> {b5['Xnp']}", "tolerance": None,
        "kind": "ordering", "error": None,
        "pass": bool(swept["Xnp"] is not None and b5["Xnp"] is not None
                     and swept["Xnp"] > b5["Xnp"]),
        "note": "checks the x_le sign convention",
    })
    checks.append({
        "check": "E: aft sweep reduces CLa",
        "value": swept["CLa"], "expected": f"< {b5['CLa']}", "tolerance": None,
        "kind": "ordering", "error": None,
        "pass": bool(swept["CLa"] < b5["CLa"]),
        "note": "cos(sweep) effect on the effective section lift slope",
    })

    results["checks"] = checks
    n_pass = sum(1 for c in checks if c["pass"])
    results["n_checks"] = len(checks)
    results["n_pass"] = n_pass
    (OUT / "physics_validation.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )

    L = ["Independent PHYSICS validation of the native AVL writer",
         "(synthetic analytic wings, no pyGeo; closed-form reference answers)",
         f"AR = {AR}   Helmbold CLa = {helmbold:.4f} /rad   "
         f"lifting-line (e=1) = {lifting_line:.4f} /rad", ""]
    L.append(f"{'PASS':>5}  {'check':<48}{'value':>12}{'expected':>16}{'err':>10}")
    for c in checks:
        exp = c["expected"]
        exp_s = f"{exp:.4f}" if isinstance(exp, float) else str(exp)[:16]
        val_s = f"{c['value']:.5f}" if isinstance(c["value"], float) else str(c["value"])
        err_s = "-" if c["error"] is None else f"{c['error']:.2e}"
        L.append(f"{'ok' if c['pass'] else 'FAIL':>5}  {c['check']:<48}"
                 f"{val_s:>12}{exp_s:>16}{err_s:>10}")
    L += ["", f"{n_pass}/{len(checks)} checks passed", ""]
    if "C_strip_loading" in results:
        s = results["C_strip_loading"]
        L += ["Spanwise loading under washout (strip cl):",
              f"  untwisted:  root {s['untwisted_root_cl']:.4f}  "
              f"tip {s['untwisted_tip_cl']:.4f}",
              f"  -5 deg tip: root {s['washout_root_cl']:.4f}  "
              f"tip {s['washout_tip_cl']:.4f}",
              f"  change:     root {s['root_cl_change']:+.4f}  "
              f"tip {s['tip_cl_change']:+.4f}"]
    L += ["", "Key measured values:",
          f"  elliptic wing e            = {results['A_elliptic']['e']}",
          f"  rectangular CL(alpha=0)    = {results['B_rect_alpha0']['CL']}",
          f"  rectangular CLa            = {results['B_rect_alpha5']['CLa']}",
          f"  rectangular Xnp/cref       = {results['B_rect_alpha5']['Xnp_over_cref']}",
          f"  Clb  unswept / +10deg dih  = {b5['Clb']} / {dih['Clb']}",
          f"  Xnp  unswept / 30deg sweep = {b5['Xnp']} / {swept['Xnp']}"]

    text = "\n".join(L)
    print(text)
    (OUT / "physics_validation.txt").write_text(text + "\n", encoding="utf-8")
    print(f"\nwrote {OUT / 'physics_validation.json'}")


if __name__ == "__main__":
    main()
