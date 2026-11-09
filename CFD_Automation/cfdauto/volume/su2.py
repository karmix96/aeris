"""The .su2 file for SU2: the structured blocks as one unstructured hexahedral mesh.

The nodes of matched faces are welded by the topology (the orientation of each matched pair, topology.orient), not by
distance; the weld is then checked against the distances (the same number of distinct points). Every cell is a
hexahedron (VTK type 12, nodes i,j,k -> i+1 -> i+1,j+1 -> j+1, then the same at k+1: right-handed blocks give positive
volumes). The boundary faces are quadrilaterals (VTK 9) in three markers, wall, symmetry and farfield, ordered so their
normal points out of the domain.

    write_blocks(blocks, bcs, interfaces, path)    write_su2(vm, path)
    read_su2(path)                                 the file back: points, hexahedra, markers
    check_su2(blocks, bcs, interfaces, path)       check 15 (.su2): counts equal, no inside-out cell, every
                                                   boundary quad faces out, the points equal the block nodes
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import topology as tp

HEX, QUAD = 12, 9
MARKERS = (tp.WALL, tp.SYM, tp.FAR)


def _ids(blocks: dict) -> tuple[dict, int]:
    """Global node numbers per block (C order of i, j, k), before welding."""
    out, n = {}, 0
    for name, X in blocks.items():
        m = int(np.prod(X.shape[:3]))
        out[name] = np.arange(n, n + m).reshape(X.shape[:3])
        n += m
    return out, n


def weld(blocks: dict, interfaces: list, tol: float = 1e-10) -> tuple[dict, np.ndarray, int]:
    """(ids per block after welding (ni, nj, nk) -> 0..n-1, the points (n, 3), n): matched faces share their nodes."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    raw, n = _ids(blocks)
    pa, pb = [], []
    for a, fa, b, fb in interfaces:
        (t, s0, s1), err = tp.orient(tp.face(blocks[a], fa), tp.face(blocks[b], fb), tol)
        if t is None:
            raise ValueError(f"{a}.{fa} / {b}.{fb} do not match (largest distance {err:.3g})")
        ia = tp.face(raw[a][..., None], fa)[..., 0]
        ib = tp.face(raw[b][..., None], fb)[..., 0]
        ib = (ib.T if t else ib)[::s0, ::s1]
        pa.append(ia.ravel())
        pb.append(ib.ravel())
    pa, pb = np.concatenate(pa), np.concatenate(pb)
    g = coo_matrix((np.ones(len(pa), dtype=np.int8), (pa, pb)), shape=(n, n))
    _, comp = connected_components(g, directed=False)
    # number the points in the order of their first node
    first = np.full(comp.max() + 1, n, dtype=np.int64)
    np.minimum.at(first, comp, np.arange(n))
    order = np.argsort(first)
    new = np.empty_like(order)
    new[order] = np.arange(len(order))
    pid = new[comp]
    pts = np.empty((len(order), 3))
    flat = np.concatenate([X.reshape(-1, 3) for X in blocks.values()])
    pts[pid] = flat                                   # every member of a point lies at the same place (checked)
    spread = np.abs(flat - pts[pid]).max() if len(flat) else 0.0
    if spread > tol:
        raise ValueError(f"welded nodes {spread:.3g} apart")
    return {k: pid[v] for k, v in raw.items()}, pts, len(order)


def hexes(ids: np.ndarray) -> np.ndarray:
    """(n_cells, 8) node numbers of the hexahedra of one block, VTK order."""
    c = [ids[:-1, :-1, :-1], ids[1:, :-1, :-1], ids[1:, 1:, :-1], ids[:-1, 1:, :-1],
         ids[:-1, :-1, 1:], ids[1:, :-1, 1:], ids[1:, 1:, 1:], ids[:-1, 1:, 1:]]
    return np.stack([x.reshape(-1) for x in c], 1)


def quads(ids: np.ndarray, face: str) -> np.ndarray:
    """(n_faces, 4) node numbers of a block face's quads, ordered so the normal points out of the block."""
    F = tp.face(ids[..., None], face)[..., 0]              # (n_u, n_v): u, v the other two axes in order
    q = np.stack([F[:-1, :-1].ravel(), F[1:, :-1].ravel(), F[1:, 1:].ravel(), F[:-1, 1:].ravel()], 1)
    ax = "ijk".index(face[0])
    sign = (1, -1, 1)[ax] * (1 if face.endswith("Max") else -1)   # e_u x e_v = +e_i, -e_j, +e_k (right-handed)
    return q if sign > 0 else q[:, ::-1]


def mesh(blocks: dict, bcs: dict, interfaces: list) -> dict:
    """The unstructured mesh: points, hexahedra, markers (name -> quads)."""
    ids, pts, n = weld(blocks, interfaces)
    cells = np.concatenate([hexes(ids[b]) for b in blocks])
    marks = {m: [] for m in MARKERS}
    for b, faces in bcs.items():
        for f, t in faces.items():
            marks[t].append(quads(ids[b], f))
    marks = {m: np.concatenate(v) if v else np.zeros((0, 4), int) for m, v in marks.items()}
    return {"points": pts, "cells": cells, "markers": marks}


def write_blocks(blocks: dict, bcs: dict, interfaces: list, path: Path) -> dict:
    """Write the .su2 file; returns its counts."""
    m = mesh(blocks, bcs, interfaces)
    pts, cells, marks = m["points"], m["cells"], m["markers"]
    path = Path(path)
    with open(path, "w") as f:
        f.write("% AERIS Stage 3 volume mesh: matched C-H multiblock as hexahedra; markers wall, symmetry, farfield\n")
        f.write("NDIME= 3\n")
        f.write(f"NELEM= {len(cells)}\n")
        idx = np.arange(len(cells), dtype=np.int64)
        for s in range(0, len(cells), 200_000):
            blk = np.hstack([np.full((min(200_000, len(cells) - s), 1), HEX, dtype=np.int64), cells[s: s + 200_000],
                             idx[s: s + 200_000, None]])
            np.savetxt(f, blk, fmt="%d")
        f.write(f"NPOIN= {len(pts)}\n")
        for s in range(0, len(pts), 200_000):
            p = pts[s: s + 200_000]
            np.savetxt(f, np.hstack([p, np.arange(s, s + len(p))[:, None]]), fmt=["%.17g", "%.17g", "%.17g", "%d"])
        f.write(f"NMARK= {len(MARKERS)}\n")
        for name in MARKERS:
            q = marks[name]
            f.write(f"MARKER_TAG= {name}\nMARKER_ELEMS= {len(q)}\n")
            np.savetxt(f, np.hstack([np.full((len(q), 1), QUAD, dtype=np.int64), q]), fmt="%d")
    return {"points": len(pts), "cells": len(cells), "markers": {k: len(v) for k, v in marks.items()},
            "bytes": path.stat().st_size}


def write_su2(vm, path: Path) -> dict:
    return write_blocks(vm.blocks, tp.boundary_conditions(), tp.interfaces(vm.info["cap_upper_face"]), path)


def read_su2(path: Path) -> dict:
    """Points (n, 3), hexahedra (m, 8), markers (name -> (k, 4)) of a .su2 file of hexahedra and quads."""
    import pandas as pd
    path = Path(path)
    head = {}
    with open(path) as f:
        line_no = 0
        for line in f:
            line_no += 1
            s = line.strip()
            if s.startswith("NDIME="):
                head["ndime"] = int(s.split("=")[1])
            elif s.startswith("NELEM="):
                head["nelem"] = (int(s.split("=")[1]), line_no)
                break
    ne, at = head["nelem"]
    read = lambda skip, n, cols: pd.read_csv(path, sep=" ", header=None, skiprows=skip, nrows=n, usecols=cols,
                                             engine="c", float_precision="round_trip").to_numpy()
    el = read(at, ne, range(10))
    if not np.all(el[:, 0] == HEX):
        raise ValueError("an element is not a hexahedron")
    # NPOIN follows the elements
    with open(path) as f:
        for _ in range(at + ne):
            next(f)
        npoin = int(next(f).split("=")[1])
    pts = read(at + ne + 1, npoin, range(3)).astype(float)
    marks = {}
    with open(path) as f:
        for _ in range(at + ne + 1 + npoin):
            next(f)
        nmark = int(next(f).split("=")[1])
        pos = at + ne + 1 + npoin + 1
        for _ in range(nmark):
            tag = next(f).split("=")[1].strip()
            k = int(next(f).split("=")[1])
            pos += 2
            rows = [next(f) for _ in range(k)]
            q = np.array([r.split() for r in rows], dtype=np.int64) if k else np.zeros((0, 5), np.int64)
            if k and not np.all(q[:, 0] == QUAD):
                raise ValueError(f"marker {tag}: an element is not a quadrilateral")
            marks[tag] = q[:, 1:5]
            pos += k
    return {"ndime": head["ndime"], "points": pts, "cells": el[:, 1:9].astype(np.int64), "markers": marks}


def _corner_jacobians(P: np.ndarray, C: np.ndarray, chunk: int = 500_000) -> float:
    """The smallest corner Jacobian (triple product of the three edges at each of the 8 corners) over the hexahedra."""
    nb = {0: (1, 3, 4), 1: (2, 0, 5), 2: (3, 1, 6), 3: (0, 2, 7), 4: (7, 5, 0), 5: (4, 6, 1), 6: (5, 7, 2), 7: (6, 4, 3)}
    worst = np.inf
    for s in range(0, len(C), chunk):
        X = P[C[s: s + chunk]]                               # (m, 8, 3)
        for c, (a, b, d) in nb.items():
            e1, e2, e3 = X[:, a] - X[:, c], X[:, b] - X[:, c], X[:, d] - X[:, c]
            worst = min(worst, float(np.einsum("ij,ij->i", np.cross(e1, e2), e3).min()))
    return worst


def bounding_cells(C: np.ndarray, q: np.ndarray) -> np.ndarray:
    """For each quad (k, 4) the hexahedron (row of C) that has all four of its nodes; -1 where none has."""
    flat = C.ravel().astype(np.int64)
    order = np.argsort(flat, kind="stable")
    cell_of = (order // C.shape[1]).astype(np.int64)
    starts = np.searchsorted(flat[order], np.arange(int(flat.max()) + 2))
    s, e = starts[q[:, 0]], starts[q[:, 0] + 1]
    out = np.full(len(q), -1, dtype=np.int64)
    for d in range(int((e - s).max()) if len(q) else 0):
        has = s + d < e
        c = np.where(has, cell_of[np.minimum(s + d, len(cell_of) - 1)], -1)
        nodes = C[np.maximum(c, 0)]                                           # (k, 8)
        full = has & np.all((nodes[:, :, None] == q[:, None, 1:]).any(axis=1), axis=1)
        out = np.where((out < 0) & full, c, out)
    return out


def check_su2(blocks: dict, bcs: dict, interfaces: list, path: Path) -> dict:
    """Check 15 (.su2): the file read back has the expected points, hexahedra and marker quads; the points are the
    block nodes, and no two are closer than 1e-12 c (no face left unwelded); no hexahedron is inside out (every corner
    Jacobian > 0); every boundary quad bounds a hexahedron and faces out of it."""
    from scipy.spatial import cKDTree
    r = read_su2(path)
    want = mesh(blocks, bcs, interfaces)
    problems = []
    if r["ndime"] != 3:
        problems.append(f"NDIME {r['ndime']}")
    if len(r["points"]) != len(want["points"]):
        problems.append(f"{len(r['points'])} points, expected {len(want['points'])}")
    if len(r["cells"]) != len(want["cells"]):
        problems.append(f"{len(r['cells'])} hexahedra, expected {len(want['cells'])}")
    elif not np.array_equal(r["cells"], want["cells"]):
        problems.append("hexahedra differ from the blocks'")
    err = float(np.abs(r["points"] - want["points"]).max()) if len(r["points"]) == len(want["points"]) else np.inf
    if err > 0.0:
        problems.append(f"points differ from the block nodes by {err:.3g}")
    close = len(cKDTree(r["points"]).query_pairs(1e-12))
    if close:
        problems.append(f"{close} pairs of points closer than 1e-12 c (a face not welded)")
    jmin = _corner_jacobians(r["points"], r["cells"])
    if not jmin > 0:
        problems.append(f"an inside-out hexahedron (smallest corner Jacobian {jmin:.3g})")
    counts = {k: len(v) for k, v in r["markers"].items()}
    if counts != {k: len(v) for k, v in want["markers"].items()}:
        problems.append(f"markers {counts}, expected {({k: len(v) for k, v in want['markers'].items()})}")
    P, C = r["points"], r["cells"]
    inward = orphan = 0
    for name, q in r["markers"].items():
        cells_of = bounding_cells(C, q)
        orphan += int(np.sum(cells_of < 0))
        X = P[q]
        nrm = np.cross(X[:, 2] - X[:, 0], X[:, 3] - X[:, 1])
        away = X.mean(1) - P[C[np.maximum(cells_of, 0)]].mean(1)
        inward += int(np.sum((np.einsum("ij,ij->i", nrm, away) <= 0) & (cells_of >= 0)))
    if orphan:
        problems.append(f"{orphan} boundary quads bound no hexahedron")
    if inward:
        problems.append(f"{inward} boundary quads face into the domain")
    return {"points": len(r["points"]), "cells": len(r["cells"]), "markers": counts, "bytes": Path(path).stat().st_size,
            "smallest_corner_jacobian": jmin, "inward_quads": inward, "orphan_quads": orphan, "problems": problems,
            "passed": not problems}
