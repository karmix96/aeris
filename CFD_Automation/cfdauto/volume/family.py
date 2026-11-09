"""Check 13: the family. Between neighbouring levels every spacing refines by 1.3 (law 23).

    measures(vm)          the spacings of one mesh that check 13 compares, and its whole-number counts
    check13(by_level)     the ratios between neighbouring levels and the check (1.3 within 3 %)

Measured on the mesh, not taken from the rules:
    s0 per station        the first cell at mid-chord on the upper surface, every station (interpolated in y onto the
                          coarser level's stations, since the finer level has 1.3 times the stations)
    wall growth limit     the rule (g^(1/1.3) per level): the ratio of ln g
    band cell             the cross cell at the band's upper edge (interpolated there along the line), 0.5 local chord
                          behind the root's trailing edge
    first outboard gap    the first station gap past the tip
    first wake cell       the first streamwise cell behind the root's base
    cell at 1 c, wall     the wall-normal cell 1 local chord from the root's wall, at mid-chord on the upper surface
    cell at 1 c, wake     the streamwise cell 1 local chord behind the root's trailing edge
Named exceptions (reported, not judged): the base cells 8 / 10 / 14 / 18 (Stage 2) and the whole-number counts (layers,
wake nodes, outboard stations, stations, C-line nodes, cells).
"""

from __future__ import annotations

import numpy as np

from .checks import Check

JUDGED = ("s0", "wall_growth", "band_cell", "outboard_first_gap", "first_wake_cell", "cell_1c_wall", "cell_1c_wake")
COUNTS = ("n_layers", "n_wake", "n_out", "n_span", "n_c", "n_base", "cells")


def _spacing_at(line: np.ndarray, d: float) -> float:
    """The cell size of a grid line (n, 3) at arc length d from its first node."""
    h = np.linalg.norm(np.diff(line, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(h)])
    return float(np.interp(d, 0.5 * (s[1:] + s[:-1]), h))


def _mid_chord_index(G: np.ndarray, ring: np.ndarray) -> int:
    x_le, x_te = float(ring[:, 0].min()), float(ring[0, 0])
    return int(np.argmin(np.abs(G[:, 0, 0] - 0.5 * (x_le + x_te))))


def measures(vm) -> dict:
    """The spacings and counts of one mesh for check 13."""
    B, P = vm.blocks, vm._plane
    sts, dq, rl = P["sts"], P["dq"], P["rules"]
    CU = B["CU_in"]
    s0 = []
    for k, st in enumerate(sts):
        i = _mid_chord_index(CU[:, :, k], st.ring)
        s0.append(float(np.linalg.norm(CU[i, 1, k] - CU[i, 0, k])))
    root = sts[0]
    i = _mid_chord_index(CU[:, :, 0], root.ring)
    cell_1c_wall = _spacing_at(CU[i, :, 0], root.chord)
    wake = B["WU_in"][::-1, 0, 0]                       # the root's upper wake line, trailing edge -> outflow
    first_wake = float(np.linalg.norm(wake[1] - wake[0]))
    cell_1c_wake = _spacing_at(wake, root.chord)
    # the band: the cross cell at the band's upper edge (as check 11), on the two wake lines either side of 0.5 local
    # chord behind the root's trailing edge, interpolated to 0.5 local chord (the levels have different wake nodes)
    b = rl.band
    s_b = 0.5 * root.chord
    WU = B["WU_in"][:, :, 0]
    q1 = int(np.clip(np.searchsorted(dq[:, 0], s_b), 1, dq.shape[0] - 1))
    h_e = []
    for q in (q1 - 1, q1):
        line = WU[WU.shape[0] - 1 - q]                  # WU runs outflow -> trailing edge
        edge = root.wake.M[1] + float(b["margin_c"]) + float(dq[q, 0]) * np.tan(np.radians(float(b["alpha_hi_deg"])))
        h = np.linalg.norm(np.diff(line, axis=0), axis=1)
        a = np.concatenate([[0.0], np.cumsum(h)])
        a_edge = float(np.interp(edge, line[:, 2], a))  # z rises along the line through the band
        h_e.append(_spacing_at(line, a_edge))
    band = float(np.interp(s_b, dq[q1 - 1: q1 + 1, 0], h_e))
    info = vm.info
    return {
        "level": vm.level, "y": [s.y for s in sts], "s0": s0,
        "wall_growth": float(rl.setting("wall_growth")),
        "band_cell": band, "band_cell_rule": float(rl.band_cell(s_b)),
        "outboard_first_gap": float(info["y_out"][1] - info["y_out"][0]),
        "first_wake_cell": first_wake, "cell_1c_wall": cell_1c_wall, "cell_1c_wake": cell_1c_wake,
        "counts": {k: int(info[k]) for k in ("n_layers", "n_wake", "n_out", "n_span", "n_c", "n_base")} | {"cells": int(vm.cells)},
    }


def ratios(a: dict, b: dict) -> dict:
    """Coarse a over fine b: every judged spacing (s0 per station as its worst station) and every count (fine / coarse)."""
    out = {}
    y_a, y_b = np.array(a["y"]), np.array(b["y"])
    r = np.array(a["s0"]) / np.interp(y_a, y_b, np.array(b["s0"]))
    out["s0"] = float(r[np.argmax(np.abs(r - 1.3))])
    out["s0_min"], out["s0_max"] = float(r.min()), float(r.max())
    out["wall_growth"] = float(np.log(a["wall_growth"]) / np.log(b["wall_growth"]))
    for k in ("band_cell", "outboard_first_gap", "first_wake_cell", "cell_1c_wall", "cell_1c_wake"):
        out[k] = float(a[k] / b[k])
    out["counts"] = {k: b["counts"][k] / a["counts"][k] for k in COUNTS}
    return out


def check13(by_level: dict, ratio: float = 1.3, tol: float = 0.03) -> tuple[Check, dict]:
    """Check 13 over neighbouring levels present (VC, C, M, F order): the worst |r / 1.3 - 1| of the judged spacings."""
    levels = list(by_level)
    table, worst, where = {}, 0.0, ""
    for a, b in zip(levels[:-1], levels[1:]):
        r = ratios(by_level[a], by_level[b])
        table[f"{a}/{b}"] = r
        for k in JUDGED:
            e = abs(r[k] / ratio - 1.0)
            if e > worst:
                worst, where = e, f"{k} {a}/{b} = {r[k]:.4f}"
    ok = worst <= tol
    return Check(13, "family_ratios", ok, worst, f"every judged spacing {ratio:g} within {tol:.0%} between neighbouring levels",
                 where), table
