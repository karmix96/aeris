"""The four geometry checks that refuse a wing. A refused wing is not written; the reason is.

(The fifth, "mesh on the loft within 1e-9 m", belongs to Stage 2.)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .params import TERule
from .planform import Planform
from .sections import Station, panel_dihedral_deg

TOL = {
    "chord_rel": 1e-3,       # 0.1 %
    "sweep_deg": 0.1,
    "twist_deg": 0.2,
    "dihedral_deg": 0.2,
    "te_m": 1e-6,            # 1 micron
    "flat_root_m": 1e-9,
    "closed_m": 1e-9,
}


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    reason: str = ""


def vector_to_loft(measured: dict, pf: Planform, stations: list[Station]) -> GateResult:
    """Measured chords, sweeps, twist and dihedral equal the design."""
    main = [s for s in stations if s.name in ("b0", "b1", "b2", "b3")]
    m_st, m_pa = measured["stations"], measured["panels"]
    checks = [
        ("chord", np.abs(np.array(m_st["chord_m"]) / pf.chord - 1.0), TOL["chord_rel"]),
        ("sweep", np.abs(np.array(m_pa["sweep_le_deg"]) - pf.sweep_le_deg), TOL["sweep_deg"]),
        ("twist", np.abs(np.array(m_st["twist_deg"]) - [s.twist_deg for s in main]), TOL["twist_deg"]),
        ("dihedral", np.abs(np.array(m_pa["dihedral_deg"])
                            - panel_dihedral_deg(np.array([s.y for s in main]), np.array([s.z_le for s in main]))),
         TOL["dihedral_deg"]),
    ]
    for name, err, tol in checks:
        if np.max(err) > tol:
            unit = "" if name == "chord" else " deg"
            return GateResult("vector_to_loft", False, f"{name} off by {np.max(err):.4g}{unit} (limit {tol}{unit})")
    return GateResult("vector_to_loft", True)


def trailing_edge(measured: dict, stations: list[Station], te: TERule) -> GateResult:
    """Built trailing-edge thickness equals the rule (or, in 'as_is' mode, the
    section's own edge) at every section."""
    for sec, st in zip(measured["sections"], stations):
        want = te.target_m(st.chord, st.airfoil.te_thickness)
        if abs(sec["te_thickness_m"] - want) > TOL["te_m"]:
            return GateResult("trailing_edge", False,
                              f"{sec['name']}: {sec['te_thickness_m'] * 1e3:.4f} mm, rule {want * 1e3:.4f} mm")
    return GateResult("trailing_edge", True)


def validity(loft, stations: list[Station], n_span: int = 101, n_chord: int = 201) -> GateResult:
    """Sections closed, upper above lower everywhere, root flat in y = 0, chords positive."""
    if any(s.chord <= 0 for s in stations):
        return GateResult("validity", False, "a chord is not positive")
    v = np.unique(np.concatenate([np.linspace(0, 1, n_span), loft.station_v]))
    u = np.linspace(0, 1, n_chord)
    uu, vv = np.meshgrid(u, v)
    up, lo = loft.upper(uu, vv), loft.lower(uu, vv)

    nose_gap = np.max(np.linalg.norm(up[:, 0] - lo[:, 0], axis=1))
    if nose_gap > TOL["closed_m"]:
        return GateResult("validity", False, f"upper and lower do not meet at the nose ({nose_gap:.3g} m)")
    base = loft.geo.surfs[2]
    for vi, a, b in zip(v, up[:, -1], lo[:, -1]):
        gap = max(np.linalg.norm(np.asarray(base(vi, 0.0)) - a), np.linalg.norm(np.asarray(base(vi, 1.0)) - b))
        if gap > TOL["closed_m"]:
            return GateResult("validity", False, f"trailing-edge base does not close the section at v={vi:.3f}")

    d = 0.5 * (up[:, -1] + lo[:, -1]) - up[:, 0]
    theta = np.arctan2(-d[:, 2], d[:, 0])
    normal = np.column_stack([np.sin(theta), np.zeros_like(theta), np.cos(theta)])
    t = np.einsum("ijk,ik->ij", up[:, 1:] - lo[:, 1:], normal)
    if np.min(t) <= 0:
        i, j = np.unravel_index(np.argmin(t), t.shape)
        return GateResult("validity", False, f"upper and lower surfaces cross at u={u[j + 1]:.3f}, v={v[i]:.3f}")

    root = np.concatenate([up[0], lo[0]])
    if np.max(np.abs(root[:, 1])) > TOL["flat_root_m"]:
        return GateResult("validity", False, f"root section leaves y = 0 by {np.max(np.abs(root[:, 1])):.3g} m")
    return GateResult("validity", True)


def repeatability(hash_a: str, hash_b: str) -> GateResult:
    if hash_a != hash_b:
        return GateResult("repeatability", False, "two builds gave different surfaces")
    return GateResult("repeatability", True)
