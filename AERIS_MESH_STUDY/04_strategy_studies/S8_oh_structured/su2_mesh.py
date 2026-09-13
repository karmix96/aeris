"""Write the S8 grid in SU2's own format, so a second solver can read it.

Why this exists: SU2's CGNS reader takes one zone per file and the S8 grid has
three (o_wing, o_out, cap_out), so the CGNS route cannot express our domain at
all. SU2's native format can: it is an unstructured list of hexahedra, which a
structured grid is a special case of.

The point of the exercise is a cross-check no amount of internal verification
can give: the SAME mesh, the SAME model, the SAME conditions, a DIFFERENT code.
Where ADflow and SU2 agree, the number is a property of the problem. Where they
disagree, one of them has something we would never otherwise see.

Node sharing matters more than it looks. The three blocks meet on faces whose
nodes are bitwise identical (measured: distance 0.0), and the O-ring's seam
closes on itself the same way. Deduplicating on exact coordinates therefore
welds the domain into one connected mesh; skipping it would produce three
blocks floating free, and a solver would happily run on the wreckage.

    python su2_mesh.py --blocks .../gci_C_blocks.npz --out .../gci_C.su2
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

#: the boundary table of write_cgns.py, which this must not contradict
BCS = {
    "o_wing": {"jMin": "wall", "jMax": "far", "kMin": "sym"},
    "o_out": {"jMax": "far", "kMax": "far"},
    "cap_out": {"kMin": "wall", "kMax": "far"},
}
ORDER = ("o_wing", "o_out", "cap_out")
HEX, QUAD = 12, 9          # VTK element types, which SU2 uses


def face_indices(shape: tuple[int, int, int], face: str):
    """The (i, j, k) index grid of one block face, as two spanning axes."""
    ni, nj, nk = shape
    if face == "jMin":
        return np.meshgrid(np.arange(ni), [0], np.arange(nk), indexing="ij")
    if face == "jMax":
        return np.meshgrid(np.arange(ni), [nj - 1], np.arange(nk), indexing="ij")
    if face == "kMin":
        return np.meshgrid(np.arange(ni), np.arange(nj), [0], indexing="ij")
    if face == "kMax":
        return np.meshgrid(np.arange(ni), np.arange(nj), [nk - 1], indexing="ij")
    raise ValueError(face)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--blocks", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    data = np.load(args.blocks)
    blocks = {name: data[name] for name in ORDER if name in data.files}

    # one global point list, shared nodes welded
    lookup: dict[tuple, int] = {}
    points: list[np.ndarray] = []
    ids: dict[str, np.ndarray] = {}
    for name, arr in blocks.items():
        flat = arr.reshape(-1, 3)
        index = np.empty(len(flat), dtype=np.int64)
        for n, p in enumerate(flat):
            key = (round(float(p[0]), 12), round(float(p[1]), 12), round(float(p[2]), 12))
            got = lookup.get(key)
            if got is None:
                got = len(points)
                lookup[key] = got
                points.append(p)
            index[n] = got
        ids[name] = index.reshape(arr.shape[:3])
        print(f"  {name}: {arr.shape[:3]} -> {len(points):,} unique points so far")

    # hexahedra, in the corner order SU2 expects
    hexes = []
    for name, arr in blocks.items():
        g = ids[name]
        c = [g[:-1, :-1, :-1], g[1:, :-1, :-1], g[1:, 1:, :-1], g[:-1, 1:, :-1],
             g[:-1, :-1, 1:], g[1:, :-1, 1:], g[1:, 1:, 1:], g[:-1, 1:, 1:]]
        hexes.append(np.stack([x.ravel() for x in c], axis=1))
    hexes = np.concatenate(hexes)

    # boundary quads, gathered per marker
    markers: dict[str, list[np.ndarray]] = {"wall": [], "far": [], "sym": []}
    for name, faces in BCS.items():
        if name not in ids:
            continue
        g = ids[name]
        for face, tag in faces.items():
            i, j, k = face_indices(g.shape, face)
            patch = g[i, j, k]
            patch = patch.squeeze()
            quads = np.stack([patch[:-1, :-1].ravel(), patch[1:, :-1].ravel(),
                              patch[1:, 1:].ravel(), patch[:-1, 1:].ravel()], axis=1)
            markers[tag].append(quads)
    markers = {tag: np.concatenate(q) for tag, q in markers.items() if q}

    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        fh.write("NDIME= 3\n")
        fh.write(f"NELEM= {len(hexes)}\n")
        for e in hexes:
            fh.write(f"{HEX} " + " ".join(str(int(v)) for v in e) + "\n")
        fh.write(f"NPOIN= {len(points)}\n")
        for p in points:
            fh.write(f"{p[0]:.16e} {p[1]:.16e} {p[2]:.16e}\n")
        fh.write(f"NMARK= {len(markers)}\n")
        for tag, quads in markers.items():
            fh.write(f"MARKER_TAG= {tag}\nMARKER_ELEMS= {len(quads)}\n")
            for q in quads:
                fh.write(f"{QUAD} " + " ".join(str(int(v)) for v in q) + "\n")
    report = {"schema": "aeris.s8.su2_mesh.v1", "source": str(args.blocks),
              "points": len(points), "hexahedra": int(len(hexes)),
              "markers": {t: int(len(q)) for t, q in markers.items()},
              "welded": int(sum(np.prod(a.shape[:3]) for a in blocks.values()) - len(points))}
    out.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"  wrote {out}: {len(points):,} points, {len(hexes):,} hexahedra, "
          f"{report['welded']:,} duplicate nodes welded")
    for t, q in markers.items():
        print(f"    {t}: {len(q):,} faces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
