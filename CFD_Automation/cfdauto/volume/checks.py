"""Every Stage 3 check (decisions/volume_rules.md, V0: the limits were written before any mesh was judged).

A mesh ends as passed, refused (a refusing check failed: refusal.json says which, its value and its limit) or
needs review (every check passed, but a review flag is raised). Checks 13 (family ratios) and 15 (export round
trip) need more than one mesh or a written file: family_ratios() and the export tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from . import topology as tp

Array = np.ndarray


@dataclass
class Check:
    n: int
    name: str
    passed: bool
    value: float
    limit: str
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


# --- cell geometry -------------------------------------------------------------------------------------------

def corner_jacobians(X: Array, chunk: int = 8) -> tuple[float, float, int]:
    """(smallest corner Jacobian determinant, smallest scaled Jacobian, cells with a corner <= 0) of a block
    (ni, nj, nk, 3), processed in k-chunks. Corners in right-handed order: the edges from a corner go to its three
    neighbours in the cell, each signed so that +i, +j, +k are positive."""
    ni, nj, nk = X.shape[:3]
    jmin, sjmin, bad = np.inf, np.inf, 0
    for k0 in range(0, nk - 1, chunk):
        k1 = min(k0 + chunk, nk - 1)
        C = X[:, :, k0: k1 + 1]
        cellmin_sj = None
        cellmin_j = None
        for a in (0, 1):
            for b in (0, 1):
                for g in (0, 1):
                    P = C[a: ni - 1 + a, b: nj - 1 + b, g: (k1 - k0) + g]
                    ei = (C[1 - a: ni - a, b: nj - 1 + b, g: (k1 - k0) + g] - P) * (1 - 2 * a)
                    ej = (C[a: ni - 1 + a, 1 - b: nj - b, g: (k1 - k0) + g] - P) * (1 - 2 * b)
                    ek = (C[a: ni - 1 + a, b: nj - 1 + b, 1 - g: (k1 - k0) + 1 - g] - P) * (1 - 2 * g)
                    det = np.einsum("...i,...i->...", ei, np.cross(ej, ek))
                    nrm = (np.linalg.norm(ei, axis=-1) * np.linalg.norm(ej, axis=-1) * np.linalg.norm(ek, axis=-1))
                    sj = det / np.where(nrm > 0, nrm, 1.0)
                    cellmin_sj = sj if cellmin_sj is None else np.minimum(cellmin_sj, sj)
                    cellmin_j = det if cellmin_j is None else np.minimum(cellmin_j, det)
        jmin = min(jmin, float(cellmin_j.min()))
        sjmin = min(sjmin, float(cellmin_sj.min()))
        bad += int((cellmin_j <= 0).sum())
    return jmin, sjmin, bad


def cell_quality_map(X: Array) -> Array:
    """Smallest corner scaled Jacobian of every cell of a block (for figures and region reports)."""
    ni, nj, nk = X.shape[:3]
    out = None
    for a in (0, 1):
        for b in (0, 1):
            for g in (0, 1):
                P = X[a: ni - 1 + a, b: nj - 1 + b, g: nk - 1 + g]
                ei = (X[1 - a: ni - a, b: nj - 1 + b, g: nk - 1 + g] - P) * (1 - 2 * a)
                ej = (X[a: ni - 1 + a, 1 - b: nj - b, g: nk - 1 + g] - P) * (1 - 2 * b)
                ek = (X[a: ni - 1 + a, b: nj - 1 + b, 1 - g: nk - g] - P) * (1 - 2 * g)
                det = np.einsum("...i,...i->...", ei, np.cross(ej, ek))
                nrm = np.linalg.norm(ei, axis=-1) * np.linalg.norm(ej, axis=-1) * np.linalg.norm(ek, axis=-1)
                sj = det / np.where(nrm > 0, nrm, 1.0)
                out = sj if out is None else np.minimum(out, sj)
    return out


def growth_along(D: Array) -> Array:
    """Growth ratios (larger / smaller) between neighbouring cells of distances along axis 0."""
    h = np.diff(D, axis=0)
    r = h[1:] / h[:-1]
    return np.maximum(r, 1.0 / r)


# --- the checks ----------------------------------------------------------------------------------------------

def run_checks(vm) -> tuple[list[Check], list[str]]:
    P = vm._plane
    rl, surf, sts, lay, ps = P["rules"], P["surface"], P["sts"], P["lay"], P["ps"]
    B = vm.blocks
    ch = rl.checks
    out: list[Check] = []
    review: list[str] = []
    n_side = lay.n_side

    # 1. wall nodes = the Stage 2 surface
    errs = []
    for name in ("CU", "CN", "CL"):
        a, b = lay.blocks()[name]
        ra, rb = a - lay.i_te_up, b - lay.i_te_up
        errs.append(np.abs(B[f"{name}_in"][:, 0] - surf.wing[ra: rb + 1]).max())
    base = np.concatenate([surf.wing[2 * n_side - 2: 2 * n_side - 1], surf.wing[2 * n_side - 1:], surf.wing[:1]], 0)
    errs.append(np.abs(B["B_in"][:, 0] - base).max())
    errs.append(np.abs(B["CAP"][:, :, 0] - surf.cap).max())
    e1 = float(max(errs))
    out.append(Check(1, "wall_on_surface", e1 <= ch["wall_on_surface_c"], e1,
                     f"<= {ch['wall_on_surface_c']:g} c: every wall node is the Stage 2 node (wing, base, cap)"))

    # 2, 3. folded cells, cell quality
    jmin, sjmin, bad = np.inf, np.inf, 0
    per_block = {}
    for name, X in B.items():
        a, s, n = corner_jacobians(X)
        per_block[name] = {"min_det": a, "min_sj": s, "folded": n}
        jmin, sjmin, bad = min(jmin, a), min(sjmin, s), bad + n
    vm.info["quality_by_block"] = per_block
    out.append(Check(2, "no_folded_cell", bad == 0, float(bad),
                     "0 cells with a corner Jacobian <= 0 (every corner of every cell)",
                     f"smallest corner determinant {jmin:.3e}"))
    out.append(Check(3, "cell_quality", sjmin >= ch["min_scaled_jacobian"], sjmin,
                     f">= {ch['min_scaled_jacobian']} (smallest corner scaled Jacobian of every cell)"))

    # 4. wall orthogonality in the station plane (the first line against the ring's bisector normal)
    from .march import line_normals
    worst, worst_k, corners = 0.0, 0, []
    for k, st in enumerate(sts):
        ring = st.ring[: lay.n_air]
        nrm = line_normals(ring)
        G0 = np.concatenate([B["CU_in"][:, :, k], B["CN_in"][1:, :, k], B["CL_in"][1:, :, k]], 0)
        v = G0[:, 1, [0, 2]] - G0[:, 0, [0, 2]]
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        ang = np.degrees(np.arccos(np.clip((v * nrm).sum(1), -1, 1)))
        corners.append(float(max(ang[0], ang[-1])))
        a = float(ang[1:-1].max())
        if a > worst:
            worst, worst_k = a, k
    # the 3-D angle against the surface normal (reported: on a swept nose it is the sweep, decision 89)
    W = np.concatenate([B["CU_in"], B["CN_in"][1:], B["CL_in"][1:]], 0)
    e_i = np.gradient(W[:, 0], axis=0)
    e_k = np.gradient(W[:, 0], axis=1)
    n3 = np.cross(e_k, e_i)
    n3 /= np.linalg.norm(n3, axis=-1, keepdims=True)
    v3 = W[:, 1] - W[:, 0]
    v3 /= np.linalg.norm(v3, axis=-1, keepdims=True)
    a3 = np.degrees(np.arccos(np.clip((v3 * n3).sum(-1), -1, 1)))[1:-1]
    vm.info["wall_angle_3d_deg"] = {"median": float(np.median(a3)), "p95": float(np.percentile(a3, 95)),
                                    "max": float(a3.max())}
    vm.info["te_corner_angle_deg"] = float(max(corners))
    out.append(Check(4, "wall_orthogonality", worst <= ch["wall_angle_deg"], worst,
                     f"<= {ch['wall_angle_deg']} deg in the station plane at every wall node but the two "
                     "trailing-edge corners", f"station {worst_k}; corners up to {max(corners):.2f} deg; 3-D angle "
                     f"median {vm.info['wall_angle_3d_deg']['median']:.2f}, max {vm.info['wall_angle_3d_deg']['max']:.1f} deg"))

    # 5. first cell s0 per station (wing lines, the base lines)
    e5, e5b = 0.0, 0.0
    for k, st in enumerate(sts):
        h = np.linalg.norm(W[:, 1, k] - W[:, 0, k], axis=-1)
        e5 = max(e5, float(np.abs(h / st.s0 - 1.0).max()))
        hb = np.linalg.norm(B["B_in"][:, 1, k] - B["B_in"][:, 0, k], axis=-1)
        e5b = max(e5b, float(np.abs(hb / st.s0 - 1.0).max()))
    out.append(Check(5, "first_cell", max(e5, e5b) <= ch["s0_tol"], max(e5, e5b),
                     f"<= {ch['s0_tol']:.0%} off the station's s0 (law 13) on every wing and base line",
                     f"wing {e5:.2e}, base {e5b:.2e}"))

    # 6. growth along every wall-normal line (the level's limit inside the fine zone, the far limit beyond)
    tol = 1.0 + ch["growth_tol"]
    g_w, g_f = rl.wall_growth, rl.far_growth
    worst6 = 0.0
    note6 = ""
    for name in ("WU_in", "CU_in", "CN_in", "CL_in", "WL_in"):
        X = B[name]
        for k, st in enumerate(sts):
            L = X[:, :, k]
            d = np.concatenate([np.zeros((L.shape[0], 1)),
                                np.cumsum(np.linalg.norm(np.diff(L, axis=1), axis=2), axis=1)], 1)
            r = growth_along(d.T)                                   # (nj-1, ni)
            mid = 0.5 * (d[:, 1:-1] + d[:, 2:]).T
            lim = np.where(mid < rl.fine_zone_local_c * st.chord, g_w, g_f)
            q = float((r / lim).max())
            if q > worst6:
                worst6, note6 = q, f"{name} station {k}"
    out.append(Check(6, "growth", worst6 <= tol, worst6,
                     f"growth / limit <= {tol:.2f} on every line: {g_w:.4g} inside the fine zone "
                     f"({rl.fine_zone_local_c:g} local c), {g_f:.4g} beyond", note6))

    # 7. cells across the boundary layer (the station distribution, fractional)
    d = ps["d"]
    n_bl = []
    for k, st in enumerate(sts):
        dk = d[:, k]
        m = int(np.searchsorted(dk, st.delta)) - 1
        n_bl.append(m + (st.delta - dk[m]) / (dk[m + 1] - dk[m]))
    nmin = float(min(n_bl))
    vm.info["bl_cells_min"] = nmin
    out.append(Check(7, "bl_cells", nmin >= rl.bl_cells - 1e-9, nmin,
                     f">= {rl.bl_cells:.4g} cells across delta ({rl.raw['wall']['delta']['law']} flat plate at "
                     f"x = {rl.raw['wall']['delta']['x_c']:g} local c, from the local Re; decision 86)",
                     f"station {int(np.argmin(n_bl))}"))

    # 8. interfaces matched node to node
    e8, open_faces = 0.0, tp.check_complete({n: b.shape[:3] for n, b in B.items()}, vm.info["cap_upper_face"])
    orient = {}
    for a, fa, b, fb in tp.interfaces(vm.info["cap_upper_face"]):
        o, err = tp.orient(tp.face(B[a], fa), tp.face(B[b], fb), 1.0)
        orient[f"{a}.{fa}={b}.{fb}"] = None if o is None else list(o)
        e8 = max(e8, err if o is not None else np.inf)
    vm.info["interface_orientation"] = orient
    ok8 = e8 <= ch["interface_tol_c"] and not open_faces
    out.append(Check(8, "interfaces", ok8, e8, f"<= {ch['interface_tol_c']:g} c node to node; no open face",
                     "; ".join(open_faces)))

    # 9. symmetry plane
    e9 = float(max(np.abs(tp.face(B[f"{n}_in"], "kMin")[..., 1]).max() for n in tp.PLANE))
    out.append(Check(9, "symmetry_plane", e9 <= ch["symmetry_tol_c"], e9, f"|y| <= {ch['symmetry_tol_c']:g} c on every root face"))

    # 10. far field at least 80 c from the wing
    from scipy.spatial import cKDTree
    wall = np.concatenate([surf.wing.reshape(-1, 3), surf.cap.reshape(-1, 3)])
    tree = cKDTree(wall)
    far = []
    for b, faces in tp.boundary_conditions().items():
        for f, t in faces.items():
            if t == tp.FAR:
                far.append(tp.face(B[b], f).reshape(-1, 3))
    dmin = float(tree.query(np.concatenate(far))[0].min())
    out.append(Check(10, "far_field", dmin >= rl.far_distance, dmin, f">= {rl.far_distance:g} c from every wall node"))

    # 11. wake: the base's first cell (in 5), the streamwise growth, the band cells
    dq = P["dq"]
    gq = growth_along(dq)
    worst11 = 0.0
    band_worst = 0.0
    b = rl.band
    for k, st in enumerate(sts):
        s = 0.5 * (dq[1:-1, k] + dq[2:, k])
        lim = np.where(s < float(b["length_local_c"]) * st.chord, g_w, g_f)
        worst11 = max(worst11, float((gq[:, k] / lim).max()))
        # band: every wake line in the band, cells below the band edge <= the band cell there
        for name, up in (("WU_in", True), ("WL_in", False)):
            X = B[name][:, :, k]
            q = np.arange(X.shape[0])[::-1] if up else np.arange(X.shape[0])
            sq = dq[q, k]
            inb = (sq > 0) & (sq <= float(b["length_local_c"]) * st.chord)
            zc = st.wake.M[1]
            for ii in np.where(inb)[0]:
                line = X[ii]
                h = np.linalg.norm(np.diff(line, axis=0), axis=1)
                zmid = 0.5 * (line[1:, 2] + line[:-1, 2])
                edge = (zc + b["margin_c"] + sq[ii] * np.tan(np.radians(b["alpha_hi_deg"]))) if up else \
                       (zc - b["margin_c"] + sq[ii] * np.tan(np.radians(b["alpha_lo_deg"])))
                inside = zmid <= edge if up else zmid >= edge
                if inside.any():
                    band_worst = max(band_worst, float((h[inside] / rl.band_cell(sq[ii])).max()))
    vm.info["band_cell_ratio_max"] = band_worst
    out.append(Check(11, "wake", worst11 <= tol and band_worst <= tol, max(worst11, band_worst),
                     f"streamwise growth / limit <= {tol:.2f}; cells inside the band <= the band cell x {tol:.2f}",
                     f"growth {worst11:.4f}, band {band_worst:.4f}"))

    # 12. outboard: first gap = the tip gap, growth
    y = np.array([s.y for s in sts])
    yo = np.array(vm.info["y_out"])
    g0 = (yo[1] - yo[0]) / (y[-1] - y[-2])
    r12 = growth_along(yo - yo[0])
    mid = 0.5 * (yo[1:-1] + yo[2:]) - yo[0]
    lim = np.where(mid < rl.outboard_fine_zone, rl.outboard_growth, g_f)
    q12 = float((r12 / lim).max())
    ok12 = abs(g0 - 1.0) <= ch["s0_tol"] and q12 <= tol
    out.append(Check(12, "outboard", ok12, max(abs(g0 - 1.0), q12 - 1.0 if q12 > 1 else 0.0),
                     f"first gap = the tip gap within {ch['s0_tol']:.0%}; growth <= {rl.outboard_growth:.4g} out to "
                     f"{rl.outboard_fine_zone:g} c past the tip, <= {g_f:.4g} beyond (x {tol:.2f})",
                     f"first gap / tip gap {g0:.6f}, growth / limit {q12:.4f}"))

    # 14. cells and RAM (information)
    cells = vm.cells
    hosts = {h: cells <= v for h, v in ch["hosts"].items()}
    vm.info["fits"] = hosts
    out.append(Check(14, "cells_ram", True, float(cells),
                     f"RAM (ADflow) = {ch['ram_gib_base']} + {ch['ram_gib_per_mcell']} GiB per million cells",
                     f"{cells / 1e6:.3f} M cells, {rl.ram_gib(cells):.1f} GiB; desktop 16 GB: {hosts['desktop_16GB']}, "
                     f"+36 GB: {hosts['desktop_52GB']}"))

    # review flags
    if vm.info.get("rung", 0) > 0:
        review.append(f"R1: the plane grid needed the smoothing rung {vm.info['rung']} (kappa {vm.info['kappa']})")
    return out, review


def family_ratios(spacings: dict[str, dict[str, float]], ratio: float = 1.3) -> dict:
    """Check 13: every spacing refines by `ratio` between neighbouring levels. spacings: level -> name -> value."""
    levels = list(spacings)
    out = {}
    for a, b in zip(levels[:-1], levels[1:]):
        out[f"{a}/{b}"] = {k: spacings[a][k] / spacings[b][k] for k in spacings[a] if k in spacings[b]}
    return out
