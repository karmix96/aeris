"""The C-H block layout: blocks, faces, boundary conditions and the matched faces between blocks.

Thirteen blocks (decision 73; decisions/volume_rules.md, section 2). In one station plane, six blocks (plane.py):

    WU   upper wake      i: outflow -> trailing edge along the upper wake line   j: up to the far field
    CU   upper side      i: ring 0 (upper trailing-edge corner) -> the start of the nose arc
    CN   nose arc        i: the n_base ring nodes of the tip cap's nose arc
    CL   lower side      i: the end of the nose arc -> ring 2 n_side - 2 (lower corner)
    WL   lower wake      i: trailing edge -> outflow along the lower wake line    j: down to the far field
    B    base            i: across the base, lower -> upper wake line             j: along the wake

stacked along the semi-span (k, root -> tip: *_in) and past the tip (k, tip -> far field: *_out), and the tip
cap swept outboard (CAP). Every block is right-handed (e_i x e_j . e_k > 0; k along +y).

Every face is one boundary condition or matched node to node with one face of one other block (no partial faces),
so the CGNS file and the .su2 markers follow from this table alone.
"""

from __future__ import annotations

WALL, FAR, SYM = "wall", "farfield", "symmetry"
PLANE = ("WU", "CU", "CN", "CL", "WL", "B")
FACES = ("iMin", "iMax", "jMin", "jMax", "kMin", "kMax")


def block_names() -> list[str]:
    return [f"{b}_in" for b in PLANE] + [f"{b}_out" for b in PLANE] + ["CAP"]


def boundary_conditions() -> dict[str, dict[str, str]]:
    """block -> face -> wall / farfield / symmetry; the faces not listed are matched (interfaces())."""
    bc: dict[str, dict[str, str]] = {}
    for side in ("in", "out"):
        k0 = SYM if side == "in" else None
        for b in ("CU", "CN", "CL"):
            bc[f"{b}_{side}"] = {"jMax": FAR}
            if side == "in":
                bc[f"{b}_{side}"]["jMin"] = WALL
        bc[f"WU_{side}"] = {"iMin": FAR, "jMax": FAR}
        bc[f"WL_{side}"] = {"iMax": FAR, "jMax": FAR}
        bc[f"B_{side}"] = {"jMax": FAR}
        if side == "in":
            bc["B_in"]["jMin"] = WALL
        for b in PLANE:
            if k0:
                bc[f"{b}_{side}"]["kMin"] = k0
            else:
                bc[f"{b}_{side}"]["kMax"] = FAR
    bc["CAP"] = {"kMin": WALL, "kMax": FAR}
    return bc


def interfaces(cap_upper: str = "jMin") -> list[tuple[str, str, str, str]]:
    """(block a, face a, block b, face b): matched faces (the orientation is found from the nodes). cap_upper: the
    CAP face on the upper side (Stage 2 stores the cap with j from the upper side when it flipped it: jMin)."""
    cap_lower = "jMax" if cap_upper == "jMin" else "jMin"
    out = []
    for side in ("in", "out"):
        s = f"_{side}"
        out += [("WU" + s, "iMax", "CU" + s, "iMin"),     # the j-line from the upper trailing-edge corner
                ("CU" + s, "iMax", "CN" + s, "iMin"),
                ("CN" + s, "iMax", "CL" + s, "iMin"),
                ("CL" + s, "iMax", "WL" + s, "iMin"),     # the j-line from the lower corner
                ("WU" + s, "jMin", "B" + s, "iMax"),      # the upper wake line
                ("WL" + s, "jMin", "B" + s, "iMin")]      # the lower wake line
    for b in PLANE:                                        # the tip plane
        out.append((f"{b}_in", "kMax", f"{b}_out", "kMin"))
    out += [("CU_out", "jMin", "CAP", cap_upper),         # the cap's upper side
            ("CN_out", "jMin", "CAP", "iMin"),            # its nose arc
            ("CL_out", "jMin", "CAP", cap_lower),         # its lower side
            ("B_out", "jMin", "CAP", "iMax")]             # its base side
    return out


def check_complete(shapes: dict[str, tuple[int, int, int]], cap_upper: str = "jMin") -> list[str]:
    """Every face of every block has exactly one owner (a BC or one interface). Returns the problems."""
    bc = boundary_conditions()
    seen: dict[tuple[str, str], str] = {}
    problems = []
    for b, faces in bc.items():
        for f, t in faces.items():
            seen[(b, f)] = t
    for a, fa, b, fb in interfaces(cap_upper):
        for key in ((a, fa), (b, fb)):
            if key in seen:
                problems.append(f"{key} has two owners: {seen[key]} and an interface")
            seen[key] = "interface"
    for b in shapes:
        for f in FACES:
            if (b, f) not in seen:
                problems.append(f"{b} {f} is open")
    return problems


def face(arr, name: str):
    """The nodes of one face of a block (ni, nj, nk, 3): iMin/iMax -> (nj, nk, 3), jMin/jMax -> (ni, nk, 3),
    kMin/kMax -> (ni, nj, 3)."""
    ax = "ijk".index(name[0])
    idx = 0 if name.endswith("Min") else -1
    return arr.take(idx, axis=ax)


TRANSFORMS = [(t, fa, fb) for t in (False, True) for fa in (1, -1) for fb in (1, -1)]


def orient(fa, fb, tol: float):
    """The orientation (transpose, flip of axis 0, flip of axis 1) that maps face fb onto fa node for node, and the
    largest distance; None if no orientation fits within tol."""
    best = (None, float("inf"))
    for t, s0, s1 in TRANSFORMS:
        g = fb.transpose(1, 0, 2) if t else fb
        if g.shape != fa.shape:
            continue
        g = g[::s0, ::s1]
        err = float(abs(g - fa).max())
        if err < best[1]:
            best = ((t, s0, s1), err)
    return best if best[1] <= tol else (None, best[1])
