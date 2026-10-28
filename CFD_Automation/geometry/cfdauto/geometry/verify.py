"""Numbers that show the built surface is the intended wing (pictures are not proof).

Three checks for every wing, and one against outside data where it exists:

1. section_fidelity  The loft, cut at each station, against the ORIGINAL airfoil
                     points (file or formula), not the resampled copy. Distance
                     normal to the chord, in % of local chord.
2. planform_edges    The loft's leading and trailing edges against the exact
                     straight lines through the stations, in % of local chord.
3. ruled_panels      Between two stations the surface must be the straight-line
                     blend of the two sections (what a builder makes, and what
                     OpenVSP "linear" skinning makes).
4. compare_points    Any outside surface (CAD file, scan, another dataset's
                     surface points) against the loft: the distance from each
                     outside point to our surface, % of local chord. Used for the
                     ONERA M6 against its CATIA model (AileM6_with_sharp_TE.igs).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import airfoils
from .loft import Loft, edge_error_pct, section_points
from .sections import Station

GEOMETRY_ROOT = Path(__file__).resolve().parents[2]
AERIS_EXTERNAL = GEOMETRY_ROOT.parents[1] / "AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/external"


def _unit_chord(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Raw Selig points -> (upper, lower), each x/c ascending, leading edge at 0, TE midpoint at (1, 0).

    The same normalisation load_airfoil applies, done here on its own.
    """
    te = 0.5 * (pts[0] + pts[-1])
    i = int(np.argmax(np.linalg.norm(pts - te, axis=1)))
    d = te - pts[i]
    ang = np.arctan2(d[1], d[0])
    rot = np.array([[np.cos(ang), np.sin(ang)], [-np.sin(ang), np.cos(ang)]])
    p = (pts - pts[i]) @ rot.T / np.linalg.norm(d)
    up, lo = p[: i + 1][::-1], p[i:]
    if np.mean(up[:, 1]) < np.mean(lo[:, 1]):
        up, lo = lo, up
    return up, lo


def _section_frame(st: Station, pts3: np.ndarray) -> np.ndarray:
    """3-D points of a station -> (x/c, y/c) in the section's own frame."""
    t = np.radians(st.twist_deg)
    dx, dz = pts3[:, 0] - st.x_le, pts3[:, 2] - st.z_le
    xi = dx * np.cos(t) - dz * np.sin(t)
    eta = dx * np.sin(t) + dz * np.cos(t)
    return np.column_stack([xi, eta]) / st.chord


def section_fidelity(loft: Loft, stations: list[Station], exclude_aft_of: float | None = None,
                     n: int = 40001) -> list[dict]:
    """Max distance between the loft section and the original airfoil points, % chord.

    The stations' own sections may have an opened trailing edge (rule mode); pass
    exclude_aft_of (e.g. the rule's open_from_xc) to compare only ahead of it.
    Single-point typos in the file (airfoils.suspect_points) are left out of the error and
    listed under "suspect_points" (x/c, side), so a bad file is reported, not copied.
    """
    out = []
    u = np.linspace(0.0, 1.0, n)
    for st, v in zip(stations, loft.station_v):
        name = st.airfoil.name
        if "|" in name:           # blended sections (inserted points) have no file
            continue
        up_ref, lo_ref = _unit_chord(airfoils.raw_points(name))
        vv = np.full_like(u, v)
        up = _section_frame(st, loft.upper(u, vv))
        lo = _section_frame(st, loft.lower(u, vv))
        errs, bad = [], []
        for side, ref, got in (("upper", up_ref, up), ("lower", lo_ref, lo)):
            keep = (ref[:, 0] > 1e-4) & (ref[:, 0] < 1 - 1e-4)
            sus = airfoils.suspect_points(ref)
            keep[sus] = False
            bad += [(round(float(ref[i, 0]), 5), side) for i in sus]
            if exclude_aft_of is not None:
                keep &= ref[:, 0] < exclude_aft_of
            order = np.argsort(got[:, 0])
            y = np.interp(ref[keep, 0], got[order, 0], got[order, 1])
            errs.append(np.abs(y - ref[keep, 1]))
        e = np.concatenate(errs)
        out.append({"station": st.name, "airfoil": name, "max_pct_chord": float(100 * e.max()),
                    "rms_pct_chord": float(100 * np.sqrt(np.mean(e ** 2))), "points": int(e.size),
                    "suspect_points": bad})
    return out


def ruled_panels(loft: Loft, stations: list[Station], n_u: int = 201, per_panel: int = 5) -> float:
    """Largest gap (% of local chord) between the loft and the straight-line blend of the two
    neighbouring sections, sampled inside every panel."""
    u = np.linspace(0.0, 1.0, n_u)
    worst = 0.0
    for k in range(len(stations) - 1):
        va, vb = loft.station_v[k], loft.station_v[k + 1]
        ua = loft.upper(u, np.full_like(u, va))
        ub = loft.upper(u, np.full_like(u, vb))
        la = loft.lower(u, np.full_like(u, va))
        lb = loft.lower(u, np.full_like(u, vb))
        for t in np.linspace(0, 1, per_panel + 2)[1:-1]:
            v = va + t * (vb - va)
            c = (1 - t) * stations[k].chord + t * stations[k + 1].chord
            gap = max(np.max(np.linalg.norm(loft.upper(u, np.full_like(u, v)) - ((1 - t) * ua + t * ub), axis=1)),
                      np.max(np.linalg.norm(loft.lower(u, np.full_like(u, v)) - ((1 - t) * la + t * lb), axis=1)))
            worst = max(worst, 100 * gap / c)
    return worst


def planform_edges(loft: Loft, stations: list[Station]) -> dict[str, float]:
    return edge_error_pct(loft, stations)


# --- outside data -------------------------------------------------------------------

def compare_points(loft: Loft, pts: np.ndarray, span_limit: float = 0.99, x_from: float = 0.0,
                   x_to: float = 1.0, n_u: int = 20001) -> dict:
    """Distance from outside surface points (x chordwise, y span, z up, metres) to the loft.

    Points are matched at their own span y. Points past span_limit x semi-span are left
    out (our tip is a flat cut). Distances are % of local chord; x_from/x_to keep a
    chordwise band (in x/c) when the outside geometry differs on purpose there (e.g. a
    sharp trailing edge).
    """
    from scipy.spatial import cKDTree

    tab = loft.span_table(4001)
    semi = tab[-1, 1]
    pts = np.asarray(pts, dtype=float)
    pts = pts[(pts[:, 1] >= 0) & (pts[:, 1] <= span_limit * semi)]
    u = np.linspace(0.0, 1.0, n_u)
    v_all = np.interp(pts[:, 1], tab[:, 1], tab[:, 0])
    key = np.round(v_all, 9)
    out = []
    for vk in np.unique(key):
        m = key == vk
        vv = np.full_like(u, vk)
        sec = np.vstack([loft.upper(u, vv), loft.lower(u, vv)])
        le, c = sec[0], np.ptp(sec[:, 0])
        xc = (pts[m, 0] - le[0]) / c
        band = (xc >= x_from) & (xc <= x_to)
        if not band.any():
            continue
        d, _ = cKDTree(sec[:, [0, 2]]).query(pts[m][band][:, [0, 2]])
        out.append(np.column_stack([pts[m, 1][band], xc[band], d / c]))
    r = np.vstack(out)
    return {"points": int(len(r)), "max_pct_chord": float(100 * r[:, 2].max()),
            "p99_pct_chord": float(100 * np.percentile(r[:, 2], 99)),
            "rms_pct_chord": float(100 * np.sqrt(np.mean(r[:, 2] ** 2))),
            "at_max": {"y_m": float(r[np.argmax(r[:, 2]), 0]), "x_over_c": float(r[np.argmax(r[:, 2]), 1])}}


def cad_points(path: str | Path, n: int = 300, scale: float = 1.0, surfaces: list[int] | None = None) -> np.ndarray:
    """Sample points on every (or the chosen) surface of an IGES/STEP file with gmsh."""
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        out = []
        for dim, tag in gmsh.model.getEntities(2):
            if surfaces is not None and tag not in surfaces:
                continue
            b = gmsh.model.getParametrizationBounds(dim, tag)
            uu, vv = np.meshgrid(np.linspace(b[0][0], b[1][0], n), np.linspace(b[0][1], b[1][1], n))
            xyz = gmsh.model.getValue(dim, tag, np.column_stack([uu.ravel(), vv.ravel()]).ravel())
            out.append(np.asarray(xyz).reshape(-1, 3))
        return np.vstack(out) * scale
    finally:
        gmsh.finalize()


M6_CAD = AERIS_EXTERNAL / "onera_m6" / "AileM6_with_sharp_TE.igs"


def onera_m6_vs_cad(loft: Loft, path: Path = M6_CAD) -> dict:
    """Our ONERA M6 against the CATIA model (mm; x chord, y span, z up).

    Surfaces 1 and 4 are the main upper and lower skins; the others are the
    sharp-trailing-edge closure and the rounded tip, which our wing does not have.
    """
    return compare_points(loft, cad_points(path, scale=1e-3, surfaces=[1, 4]))
