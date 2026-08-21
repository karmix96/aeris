"""S4 — geometry-driven analytical multiblock. Written from scratch under ADR-0011.

Source: *Automatic Generation of 3D Parametric Multi-Block Topology and Structured
Mesh for Wings*, Applied Sciences 2026, 16, 7588 — `papers/applsci-16-07588.pdf`,
§§2.1-2.3.

================================================================================
WHY S4 IS STRUCTURALLY UNLIKE EVERYTHING BEFORE IT
================================================================================

RUNBOOK §6 S4: "Generate the volume directly using TFI/elliptic/Poisson methods;
**do not require pyHyp for this candidate**."

Every strategy so far builds a surface and hands it to pyHyp's hyperbolic march, and
all three were decided by the same thing: whether the first marching layer fits under
the smallest surface cell, and whether the spanwise cells match the tip cap at the
interface. S1 passes because its spanwise law matches that interface to ~1.0; S3
fails 30/30 on S1's own surface purely because its law does not; S0 never cleared it.

**S4 has no march.** The boundary-layer block is an explicit block with explicitly
placed outer vertices, so the near-wall spacing is constructed rather than advanced.
The failure modes that decided the other three do not apply, and S4's own failure
mode — named in `01_references/S4_analytic_multiblock_implementation_note.md` — is
different: "Bad Type 2 or Type 3 placement can create self-intersections or nearfield
block collapse even when the surface projection is valid."

That makes S4 the most genuinely independent entrant in the tournament, and it is the
reason it is worth building even this late.

================================================================================
THE METHOD (§2.2)
================================================================================

Four classes of control vertex:

    Type 1  on the wing surface
    Type 2  on the outer boundary of the boundary-layer mesh
    Type 3  on the outer boundary of the interior-field mesh
    Type 4  on the outer boundary of the far-field mesh

**Type 1** (§2.2.1a): airfoil profiles at root `s(u, 0)`, tip `s(u, 1)` and
intermediate sections `s(u, v_j)`, with **eight control vertices per profile**,
clustered "in the vicinity of the leading and trailing edges... so as to ensure the
mesh quality in these critical regions".

**Type 2** (§2.2.1b, Eq. 2): advance each Type 1 vertex along the outward surface
normal, `V2 = V1 + delta*n`, `delta = 0.06*c_local`, referenced to AIAA DPW
boundary-layer extents. Normals: Eqs. 3-5 at the root (2D tangent rotated 90 deg,
with the averaged TE correction), Eqs. 6-7 at intermediate sections (cross product of
the two surface tangents), Eq. 8 at the tip (blended with the spanwise direction).

**Type 3** (§2.2.1c, Eqs. 9-11): thickness, edgewise and chordwise extension, with
default coefficients eta1 = 0.6, eta2 = 0.1, mu1 = 1.6, eta3 = 4.0, mu2 = 2.0.

**Type 4**: the far field, 100-150 x MAC. **Deferred** — the implementation note is
explicit that "farfield extent must wait for the farfield independence study", and
ADR-0014 §4 records the resulting limit on comparing S4 with S1.

**Volume** (§2.3): boundary edges assemble from control edges, mesh domains from
boundary edges by 2D TFI (Eq. 20), mesh faces from domains, and blocks by 3D TFI
(Eqs. 21-23).

================================================================================
THE THIRD TIP CONSTRUCTION — S4'S ONE STRUCTURAL CONTRIBUTION
================================================================================

ADR-0013 §2 recorded a result reached three times independently: capping a thin
blunt-trailing-edge contour with structured quads requires an O-H ring whose
**opposite arcs carry equal point counts**, which forces the nose wrap and the 1.0 mm
base to the same size — and that there are "essentially two ways to satisfy it",
namely S0's and S1's. S3 could not find a third and was rescoped.

**There is a third, and the paper states the rule that unlocks it.** §2.3.1: *"A mesh
domain is defined by four boundary edges connected end-to-end, and **a single boundary
edge may consist of multiple control edges**."*

The equality the ring needs is between **boundary edges**, not between individual
arcs. Group the eight Type-1 arcs into four boundary edges of two arcs each and the
constraint becomes a pair of equalities between *sums*:

    E1 = A0 + A1   E2 = A2 + A3   E3 = A4 + A5   E4 = A6 + A7
    n0 + n1 = n4 + n5            n2 + n3 = n6 + n7

The base is A7. It is no longer opposite the nose wrap; it is opposite nothing on its
own. Its count is chosen on physical grounds — a 1.0 mm edge wants 3 to 5 points —
and the equality is absorbed by A6, a 0.25c arc where 4 points either way changes
nothing. That is what S0 and S1 both had to pay for and neither could avoid.

This is not a loophole. It is the paper's own topology rule, and it is the single
place where S4's method buys something the other two could not reach.

================================================================================
WHAT HAD TO BE INVENTED
================================================================================

* **The eight Type 1 positions.** §2.2.1a states there are eight per profile and
  that they cluster near the leading and trailing edges, but the distribution is
  given only in Figure 2b, which the text does not tabulate.
* **The blunt trailing edge.** The paper's profiles have a sharp TE; AERIS's is a
  1.0 mm constant-absolute base (DECISION-0004) with two real corners, so the TE
  needs two vertices where the paper needs one.
* **The spanwise law.** §2.2.1a leaves the intermediate-section distribution
  "flexibly set according to analysis requirements". S4 uses a uniform target cell
  and does **not** anchor the first spanwise cell to the tip cap. That anchoring is
  what makes S1 march; S4 does not march, so adopting it would be copying a fix for
  a problem S4 does not have. Whether the interface match still matters without a
  march is then a measurement rather than an assumption — see STUDY.md §6.
* **Type 3/4 coefficients** are the paper's defaults where used, and the far field is
  deferred; the note records both as uncalibrated for AERIS.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

STUDIES = Path(__file__).resolve().parents[1]
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.ingestion import (  # noqa: E402
    MeshBuildError,
    SurfaceBlock,
    _map_sides_to_wing,
    _resample_polyline,
    _tfi_patch,
    section_loop_2d,
)
from shared.qc import (  # noqa: E402
    orient_blocks_consistently,
    orient_patches_2d,
    winslow_smooth_2d,
)

Array = np.ndarray

STRATEGY_ID = "S4_ANALYTIC_MULTIBLOCK"

#: DECISION-0004 — constant absolute trailing edge, as everywhere else in the study.
TE_THICKNESS_ABS_M = 0.001

#: Paper §2.2.1b Eq. 2 — boundary-layer advance, as a fraction of local chord.
DELTA_BL_FRAC = 0.06

#: Paper §2.2.1c Eqs. 9-11 defaults. Reported, and used only where §4 of STUDY.md
#: says they are; the far field they were tuned for is out of scope here.
ETA1_THICKNESS = 0.6
ETA2_LE_OFFSET = 0.1
MU1_EDGEWISE = 1.6
ETA3_CHORDWISE = 4.0
MU2_SWEEP = 2.0

#: Type 1 chordwise fractions, upper and lower. §2.2.1a gives the count and the
#: clustering intent; the values are ours.
TYPE1_FRACTIONS = (0.05, 0.35, 0.75)

#: The eight arcs between consecutive Type 1 vertices, in ring order.
ARC_ORDER = (
    "upper_aft",    # A0  v0 (upper TE base corner) -> v1 (u 0.75)
    "upper_mid",    # A1  v1 -> v2 (u 0.35)
    "upper_fore",   # A2  v2 -> v3 (u 0.05)
    "nose",         # A3  v3 -> LE -> v4 (l 0.05)
    "lower_fore",   # A4  v4 -> v5 (l 0.35)
    "lower_mid",    # A5  v5 -> v6 (l 0.75)
    "lower_aft",    # A6  v6 -> v7 (lower TE base corner)
    "base",         # A7  v7 -> v0, the blunt base
)

#: §2.3.1 boundary edges. Ring corners are v0 (upper TE base corner), v3 (u 0.05),
#: v4 (l 0.05) and v6 (l 0.75), and the four edges assemble from 3, 1, 2 and 2
#: control edges respectively. The grouping is not free — see the module docstring
#: and STUDY.md §3 — it is the one arrangement that (a) keeps the nose arc and the
#: 1.0 mm base off opposite sides of the ring, and (b) maps each edge onto one side
#: of a rectangular core.
#: SELECTED, by exhaustive search over all admissible rings (`search_s4_ring.py`).
#: v6 is excluded because the section is **reflex** there — interior angle 180.9
#: degrees, identically on every geometry measured — and every ring containing it
#: folds exactly one core cell at -0.01523. Every ring without it is positive.
#: v7 is included because at 73 degrees it is the sharpest corner the section has.
RING_CORNERS = (1, 3, 5, 7)


def boundary_groups(ring: tuple[int, ...] = RING_CORNERS) -> tuple[tuple[str, ...], ...]:
    """The four §2.3.1 boundary edges implied by a choice of four ring corners.

    A ring corner is a Type 1 vertex index; boundary edge k collects the arcs from
    ring[k] up to ring[k+1]. Two choices are forbidden and the caller is told why:

    * ``{0, 7}`` both chosen isolates the 1.0 mm base as its own boundary edge,
      which forces its count equal to the opposite edge's — the constraint S0 and S1
      both pay and this blocking exists to escape.
    * ``{3, 4}`` both chosen isolates the nose arc the same way.
    """
    ring = tuple(sorted(int(r) for r in ring))
    if len(set(ring)) != 4 or not all(0 <= r < 8 for r in ring):
        raise MeshBuildError(f"ring corners must be four distinct indices in 0..7: {ring}")
    if 0 in ring and 7 in ring:
        raise MeshBuildError("ring corners {0, 7} isolate the blunt base as its own edge")
    if 3 in ring and 4 in ring:
        raise MeshBuildError("ring corners {3, 4} isolate the nose arc as its own edge")
    groups = []
    for k in range(4):
        a, b = ring[k], ring[(k + 1) % 4]
        idx = [i % 8 for i in range(a, a + ((b - a) % 8 or 8))]
        groups.append(tuple(ARC_ORDER[i] for i in idx))
    return tuple(groups)


BOUNDARY_EDGES = boundary_groups()

LEVELS = {
    "L1_coarse": dict(
        chord_points=57, base_points=3, nose_points=9, collar_points=5,
        target_cell_m=0.020, bl_points=17),
    "L2_smoke": dict(
        chord_points=81, base_points=3, nose_points=13, collar_points=7,
        target_cell_m=0.015, bl_points=25),
    "L3_medium": dict(
        chord_points=113, base_points=3, nose_points=17, collar_points=9,
        target_cell_m=0.010, bl_points=33),
    "L4_fine": dict(
        chord_points=153, base_points=5, nose_points=25, collar_points=13,
        target_cell_m=0.008, bl_points=49),
    "L5_production": dict(
        chord_points=225, base_points=5, nose_points=33, collar_points=17,
        target_cell_m=0.006, bl_points=65),
}

# ---------------------------------------------------------------------------
# §2.2.1a — Type 1 control vertices
# ---------------------------------------------------------------------------


def type1_vertices(coords: Array, le_index: int) -> tuple[Array, dict]:
    """The eight Type 1 control vertices on one profile (§2.2.1a).

    The paper gives the count and the clustering intent but tabulates the positions
    only in a figure. Chosen here, adapted to a blunt trailing edge:

        0  upper TE base corner        4  lower LE-adjacent  (x/c 0.05)
        1  upper aft   (x/c 0.75)      5  lower mid   (x/c 0.35)
        2  upper mid   (x/c 0.35)      6  lower aft   (x/c 0.75)
        3  upper LE-adjacent (0.05)    7  lower TE base corner

    The leading edge itself is deliberately NOT a control vertex: it sits inside the
    nose arc, which is what "control vertices ... in the vicinity of the leading and
    trailing edges" buys — a vertex ON a stagnation point would put a block corner
    where the surface turns hardest.
    """
    upper = coords[: le_index + 1][::-1]  # LE -> upper TE
    lower = coords[le_index:]  # LE -> lower TE
    x_le, x_te = float(upper[0, 0]), float(upper[-1, 0])
    chord = x_te - x_le
    if chord <= 0.0:
        raise MeshBuildError("section has non-positive chord")

    def _at(curve: Array, frac: float) -> Array:
        x = x_le + frac * chord
        return np.array([x, float(np.interp(x, curve[:, 0], curve[:, 1]))])

    fr = TYPE1_FRACTIONS
    verts = np.array(
        [
            upper[-1],
            _at(upper, fr[2]), _at(upper, fr[1]), _at(upper, fr[0]),
            _at(lower, fr[0]), _at(lower, fr[1]), _at(lower, fr[2]),
            lower[-1],
        ]
    )
    info = {
        "n_type1": len(verts),
        "chord": chord,
        "x_le": x_le,
        "x_te": x_te,
        "fractions": fr,
        "invented": "positions are ours; §2.2.1a gives only the count and the intent",
    }
    return verts, info


def surface_normals(coords: Array, le_index: int, verts: Array) -> Array:
    """Outward unit normals at the Type 1 vertices (§2.2.1b, Eqs. 3-5).

    Tangent from a neighbouring profile point, rotated 90 degrees: `n = (tau_y,
    -tau_x)`. At the trailing edge the paper's averaged correction is applied,
    `n' = (n + (1,0,0)) / |...|`, "avoiding abrupt changes in the normal direction".
    """
    loop = np.vstack([coords, coords[0]])
    normals = []
    for k, v in enumerate(verts):
        d = np.linalg.norm(loop[:-1] - v, axis=1)
        i = int(np.argmin(d))
        tau = loop[(i + 1) % len(coords)] - loop[i]
        nrm = np.linalg.norm(tau)
        if nrm < 1e-15:
            raise MeshBuildError("degenerate tangent while building Type 1 normals")
        tau = tau / nrm
        n = np.array([tau[1], -tau[0]])
        if k in (0, 7):  # the two blunt-TE corners
            n = n + np.array([1.0, 0.0])
            n = n / np.linalg.norm(n)
        # Outward test against the section centroid.
        if float(n @ (v - coords.mean(axis=0))) < 0.0:
            n = -n
        normals.append(n)
    return np.asarray(normals)


def type2_vertices(
    verts: Array, normals: Array, chord: float, *, delta_frac: float = DELTA_BL_FRAC
) -> tuple[Array, dict]:
    """Type 2 vertices: the boundary-layer outer boundary (§2.2.1b Eq. 2).

    `V_type2 = V_type1 + delta * n`, `delta = 0.06 * c_local`.

    The paper claims this delta keeps "a safe margin against normal-vector
    intersection". That claim is TESTED here rather than assumed, because the
    implementation note names bad Type 2 placement as S4's primary failure mode:
    the returned info reports whether any two advance segments cross.
    """
    delta = float(delta_frac) * float(chord)
    out = verts + delta * normals

    crossings = 0
    for i in range(len(verts)):
        for j in range(i + 1, len(verts)):
            p, r = verts[i], out[i] - verts[i]
            q, s = verts[j], out[j] - verts[j]
            denom = r[0] * s[1] - r[1] * s[0]
            if abs(denom) < 1e-15:
                continue
            t = ((q - p)[0] * s[1] - (q - p)[1] * s[0]) / denom
            u = ((q - p)[0] * r[1] - (q - p)[1] * r[0]) / denom
            if 1e-9 < t < 1.0 - 1e-9 and 1e-9 < u < 1.0 - 1e-9:
                crossings += 1

    info = {
        "delta_m": delta,
        "delta_frac_of_chord": float(delta_frac),
        "normal_crossings": crossings,
        "self_intersecting": crossings > 0,
    }
    return out, info


def type3_extension_distances(wing, *, eta1: float = ETA1_THICKNESS) -> dict:
    """Eqs. 9-11, reported. See STUDY.md §7 for why they are reported, not used.

    Eq. 9 `d_thickness = eta1*c_root + c_root*(max(sin th_root, sin th_tip) +
    max(Y_root, Y_intm, Y_tip))`, Eq. 10 `d_edgewise = mu1*b/2`, Eq. 11
    `d_chordwise = max(eta3*c_root, mu2*(z_edgewise*tan beta + c_tip))`.
    """
    xsecs = list(wing.xsecs)
    c_root = float(xsecs[0].chord)
    c_tip = float(xsecs[-1].chord)
    le = np.asarray([np.asarray(x.xyz_le, dtype=float) for x in xsecs])
    span_axis = int(np.argmax(np.ptp(le, axis=0)))
    half_span = float(np.ptp(le[:, span_axis]))
    twists = [float(getattr(x, "twist", 0.0)) for x in xsecs]
    vert_axis = [a for a in (0, 1, 2) if a != span_axis][
        int(np.argmin([np.ptp(le[:, a]) for a in (0, 1, 2) if a != span_axis]))
    ]
    deflect = float(np.max(np.abs(le[:, vert_axis] - le[0, vert_axis])) / max(c_root, 1e-12))

    d_thick = eta1 * c_root + c_root * (
        max(abs(np.sin(np.radians(twists[0]))), abs(np.sin(np.radians(twists[-1])))) + deflect
    )
    d_edge = MU1_EDGEWISE * half_span
    sweep = float(np.arctan2(abs(le[-1, 0] - le[0, 0]), max(half_span, 1e-12)))
    d_chord = max(ETA3_CHORDWISE * c_root, MU2_SWEEP * (d_edge * np.tan(sweep) + c_tip))
    return {
        "eta1": eta1, "eta2": ETA2_LE_OFFSET, "mu1": MU1_EDGEWISE,
        "eta3": ETA3_CHORDWISE, "mu2": MU2_SWEEP,
        "c_root": c_root, "c_tip": c_tip, "half_span": half_span,
        "d_thickness_m": float(d_thick),
        "d_edgewise_m": float(d_edge),
        "d_chordwise_m": float(d_chord),
        "note": "paper defaults; the far field they size is deferred (ADR-0014 §4)",
    }


# ---------------------------------------------------------------------------
# Blocking — the eight arcs and the §2.3.1 boundary-edge grouping
# ---------------------------------------------------------------------------


def section_arcs(coords: Array, le_index: int, verts: Array) -> dict[str, Array]:
    """Split the section contour at the eight Type 1 vertices."""
    loop = np.vstack([coords, coords[0]])  # closed, base is the final segment
    idx = []
    for v in verts:
        idx.append(int(np.argmin(np.linalg.norm(coords - v, axis=1))))
    if sorted(idx) != idx or len(set(idx)) != len(idx):
        raise MeshBuildError(f"Type 1 vertices are not in contour order: {idx}")

    arcs = {}
    for k, name in enumerate(ARC_ORDER[:-1]):
        a, b = idx[k], idx[k + 1]
        seg = coords[a : b + 1].copy()
        seg[0], seg[-1] = verts[k], verts[k + 1]
        if len(seg) < 2:
            raise MeshBuildError(f"arc {name} is degenerate")
        arcs[name] = seg
    # A7, the blunt base: a straight segment from the lower TE corner to the upper.
    arcs["base"] = np.vstack([loop[-2], loop[-1]])
    return arcs


def arc_counts(
    arcs: dict[str, Array], *, chord_points: int, base_points: int, nose_points: int,
    groups=None,
) -> dict[str, int]:
    """Point counts per arc, satisfying the two §2.3.1 boundary-edge equalities.

        |E_A| = |E_C|   ->   n0 + n1 + n2 - 2 = n4 + n5 - 1
        |E_B| = |E_D|   ->   n3             = n6 + n7 - 1

    Allocation is proportional to arc length; the base is then pinned at
    `base_points` on physical grounds — a 1.0 mm edge wants 3 to 5 points and
    nothing about the ring should be allowed to argue with that — and the two
    equalities are closed on `lower_mid` and `lower_aft`, both long arcs where four
    points either way changes nothing.

    **This is the whole point of S4's blocking.** In S0's and S1's rings the base
    sits opposite the nose wrap and the two counts are forced equal, which is what
    drives both of their cell-size ranges. Here the base's partner is a *sum*.
    """
    lengths = {
        k: float(np.sum(np.linalg.norm(np.diff(v, axis=0), axis=1))) for k, v in arcs.items()
    }
    groups = groups or BOUNDARY_EDGES
    # The nose and the base are pinned; the rest is proportional to arc length.
    # Allocating the nose by length would starve it — it is short, and it is the
    # leading edge. §2.2.1a puts control vertices near the leading and trailing edges
    # precisely "to ensure the mesh quality in these critical regions", which is a
    # statement about resolution, not about arc length. The first build allocated it
    # proportionally, gave it 5 points, and through the |E_B| = |E_D| equality
    # starved the entire aft collar with it.
    pinned = {"base": int(base_points), "nose": int(nose_points)}
    free = [k for k in ARC_ORDER if k not in pinned]
    total_len = sum(lengths[k] for k in free)
    budget = max(int(chord_points) - sum(pinned.values()), 6 * 3)
    n = {k: max(3, int(round(budget * lengths[k] / total_len))) for k in free}
    n.update(pinned)

    # Close each equality on the longest unpinned arc of the shorter side, so the
    # adjustment always lands where several points either way cannot matter.
    for a, b in ((0, 2), (1, 3)):
        ga, gb = groups[a], groups[b]
        adjustable = [k for k in gb if k not in pinned] or [k for k in ga if k not in pinned]
        if not adjustable:
            raise MeshBuildError(
                f"boundary edges {ga} and {gb} are both entirely pinned; their counts "
                "cannot be equalised"
            )
        target = adjustable[int(np.argmax([lengths[k] for k in adjustable]))]
        side = 1 if target in gb else -1
        pa = sum(n[k] for k in ga) - (len(ga) - 1)
        pb = sum(n[k] for k in gb) - (len(gb) - 1)
        n[target] += side * (pa - pb)

    if min(n.values()) < 3:
        raise MeshBuildError(f"arc allocation went below 3 points: {n}")
    e = boundary_edge_points(n, groups)
    if e[0] != e[2] or e[1] != e[3]:
        raise MeshBuildError(f"boundary edges do not pair: {e}")
    return n


def boundary_edge_points(counts: dict[str, int], groups=None) -> tuple[int, int, int, int]:
    """Points on each of the four §2.3.1 boundary edges (shared vertices once)."""
    groups = groups or BOUNDARY_EDGES
    return tuple(sum(counts[a] for a in g) - (len(g) - 1) for g in groups)


def resample_arcs(arcs: dict[str, Array], counts: dict[str, int]) -> dict[str, Array]:
    return {k: _resample_polyline(arcs[k], counts[k]) for k in ARC_ORDER}


# ---------------------------------------------------------------------------
# S4's tip closure — a four-corner O-H ring on the grouped boundary edges
# ---------------------------------------------------------------------------

TIP_BLOCK_NAMES = ("tip_upper", "tip_nose", "tip_lower", "tip_aft", "tip_core")


def _straight(p0: Array, p1: Array, n: int) -> Array:
    t = np.linspace(0.0, 1.0, int(n)).reshape(-1, 1)
    return (1.0 - t) * np.asarray(p0) + t * np.asarray(p1)


def shape_constrained_edge(
    source: Array, start: Array, end: Array, *, alpha: float = 1.0, window: float = 0.0
) -> Array:
    """Paper Eq. 18 — the "scaled copying method", in the section plane.

        X_i,tgt = (1-lam_i) X_start,tgt + lam_i X_end,tgt
                  + alpha * (d_tgt / ||d_src||) * dX_i,src

    `dX_i,src` is node i's offset from the source edge's own chord line, and
    `lam_i` its normalised arc length. The paper writes the correction with a
    *vector* `d_tgt` over a *scalar* `||d_src||`, which is only well defined once
    the frame change is made explicit: in 2D that is a rotation from `d_src` to
    `d_tgt` together with the length ratio, which is what is implemented here.

    This is why S4's collar blocks are not slivers. A straight inner edge under a
    curved boundary edge builds a patch whose cells shear steadily from one end to
    the other; an inner edge that *copies the boundary's shape* keeps the collar a
    near-uniform band. The first build of this tip used straight inner edges and
    scored min scaled Jacobian -0.037 with a 179.9 degree corner.
    """
    src = np.asarray(source, dtype=float)
    d_src = src[-1] - src[0]
    len_src = float(np.linalg.norm(d_src))
    if len_src <= 0.0:
        raise MeshBuildError("shape-constrained edge: source edge has zero length")

    seg = np.linalg.norm(np.diff(src, axis=0), axis=1)
    lam = np.concatenate([[0.0], np.cumsum(seg)])
    lam = lam / lam[-1]

    delta = src - (src[0] + np.outer(lam, d_src))

    d_tgt = np.asarray(end, dtype=float) - np.asarray(start, dtype=float)
    len_tgt = float(np.linalg.norm(d_tgt))
    theta = float(np.arctan2(d_tgt[1], d_tgt[0]) - np.arctan2(d_src[1], d_src[0]))
    rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    scale = float(alpha) * len_tgt / len_src

    if window:
        # A corner window on the copied deviation. Without it the inner edge leaves
        # its endpoint TANGENT to the boundary arc, so the core block inherits the
        # contour's interior angle there — and this section is smooth at six of its
        # eight control vertices, where that angle is 176 to 181 degrees. A corner
        # cell spanning 179 degrees scores sin(1 degree) = 0.017 at best, which is
        # precisely the ceiling measured before this was added.
        #
        # `(4 lam (1 - lam))**window` vanishes to second order at both ends, so the
        # edge leaves along the CHORD between the two core corners and the core's
        # corner angle becomes the one the four core corners define — a quantity the
        # construction chooses, rather than one the airfoil dictates.
        delta = delta * ((4.0 * lam * (1.0 - lam)) ** float(window))[:, None]

    return np.asarray(start, dtype=float) + np.outer(lam, d_tgt) + scale * (delta @ rot.T)


def core_centroid(res: dict[str, Array]) -> Array:
    """Area centroid of the closed section contour."""
    c = np.vstack([res[k] for k in ARC_ORDER])
    x, y = c[:, 0], c[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cross = x * yn - xn * y
    area = 0.5 * float(cross.sum())
    if abs(area) < 1e-15:
        return c.mean(axis=0)
    return np.array(
        [float(((x + xn) * cross).sum()) / (6.0 * area),
         float(((y + yn) * cross).sum()) / (6.0 * area)]
    )


def core_corners(
    res: dict[str, Array], *, core_shrink: float, corner_pull: float = 1.0, groups=None
) -> tuple[Array, Array]:
    """The four interior corners of the tip core: the ring corners, shrunk.

    ``c_k = C + s (v_k - C)`` about the section's area centroid ``C``.

    **Why a similarity and not something cleverer.** Two other placements were built
    and measured on `lhs100_seed42_000` first:

    * *Centroid shrink with straight inner edges* — min scaled Jacobian **-0.037**.
      A straight inner edge under a curved boundary edge shears the collar from one
      end to the other.
    * *A rectangle at fixed chord stations* (`fore_frac`, `aft_frac`, a fraction of
      local half-thickness) — min scaled Jacobian **-0.87**, and a 135-point sweep
      over its four parameters produced **no positive combination at all**. On a
      reflexed section the aft rectangle corners landed at y = +0.031 and +0.019
      while the trailing-edge ring corner they were meant to serve sits at y =
      +0.004, i.e. *below both of them*, so the two spokes of the aft collar crossed.
      The rectangle is a good shape and it was in the wrong place: a core corner has
      to be inward **from its own ring corner**, not at an absolute station.

    A similarity is the placement that cannot make that mistake — every core corner
    lies on the segment from its ring corner to the centroid, by construction. It is
    also the one placement for which Eq. 18 is *exact* rather than approximate:
    ``d_tgt = s d_src``, so the rotation term vanishes and ``alpha = 1`` reproduces
    the shrunken arc identically.
    """
    groups = groups or BOUNDARY_EDGES
    contour = np.vstack([res[k] for k in ARC_ORDER])
    centroid = core_centroid(res)
    corners = np.array([res[g[0]][0] for g in groups])
    core = centroid + float(core_shrink) * float(corner_pull) * (corners - centroid)
    if np.any(~np.isfinite(core)):
        raise MeshBuildError("core corners are not finite")
    del contour
    return core, centroid


def tip_domains_2d(
    res: dict[str, Array],
    *,
    collar_points: int,
    core_shrink: float = 0.75,
    corner_pull: float = 1.0,
    shape_window: float = 0.0,
    core_smooth_iters: int = 400,
    groups=None,
):
    """Five tip domains: four collars on the §2.3.1 boundary edges plus a core.

    Ring corners are v0 (the upper blunt-TE base corner), v2 (u 0.35), v4 (l 0.05)
    and v6 (l 0.75) — spread at 0.00, 0.32, 0.53 and 0.87 of the contour perimeter,
    which is as even as eight fixed control vertices allow.

    **Neither the nose arc nor the base is a boundary edge on its own.** The nose
    travels with `upper_fore` in E_B and the base with `lower_aft` in E_D, so the two
    equalities the ring imposes are between sums and the 1.0 mm base is free to carry
    the 3 points it physically wants. That is S4's one structural contribution and it
    is the reason this blocking exists.

    **The lower TE base corner, v7, is deliberately NOT a ring corner**, since making
    both base corners ring corners would put the base opposite the nose and force
    their counts equal — S1's construction exactly. The price is that v7 falls inside
    boundary edge E_D, so one collar carries a real 90 degree geometric corner in its
    interior. That price is measured, not assumed: see STUDY.md §5.
    """
    groups = groups or BOUNDARY_EDGES
    edges = [
        np.vstack([res[g[0]]] + [res[k][1:] for k in g[1:]]) for g in groups
    ]
    core, centroid = core_corners(
        res, core_shrink=core_shrink, corner_pull=corner_pull, groups=groups
    )
    # Eq. 18's alpha is set so the inner edge keeps the FULL `core_shrink` copy of the
    # boundary's shape while its endpoints are pulled in by `corner_pull` as well:
    # scale = alpha * |d_tgt| / |d_src| = (1/pull) * (shrink * pull) = shrink.
    #
    # That combination is the whole reason the cap closes. With `corner_pull = 1` the
    # inner edges are an exact similarity of the contour, so the core's interior angle
    # at each ring corner equals the CONTOUR's — which on a smooth stretch is 180
    # degrees, and in the discrete patch tips just past it into a reflex corner and one
    # folded cell. No amount of elliptic smoothing removes that: Winslow cannot move
    # boundary nodes, and a reflex corner in a structured patch always folds its corner
    # cell. Pulling the corners in further than the edges tilts both edges outward where
    # they meet, which makes the corner convex by construction.
    inner_edges = [
        shape_constrained_edge(
            edges[k], core[k], core[(k + 1) % 4],
            alpha=1.0 / float(corner_pull), window=shape_window,
        )
        for k in range(4)
    ]

    patches, names = [], []
    for k, edge in enumerate(edges):
        patches.append(
            _tfi_patch(
                bottom=edge, top=inner_edges[k],
                left=_straight(edge[0], core[k], collar_points),
                right=_straight(edge[-1], core[(k + 1) % 4], collar_points),
            )
        )
        names.append(TIP_BLOCK_NAMES[k])

    n_a, n_b = len(edges[0]), len(edges[1])
    core_patch = _tfi_patch(
        bottom=inner_edges[0][::-1], top=inner_edges[2],
        left=inner_edges[1], right=inner_edges[3][::-1],
    )
    # RUNBOOK §6 S4 names "TFI/elliptic/Poisson" as S4's toolset, and the core is
    # exactly where the elliptic half earns its place. TFI alone folds it: three of
    # the four core corners sit on smooth parts of the shrunken contour, so the patch
    # arrives with interior angles near 180 degrees and 7 crossed cells. Winslow's
    # map is harmonic in the computational coordinates and cannot fold on a convex
    # domain; the shrunken section is convex enough that it unfolds this one.
    if core_smooth_iters:
        core_patch = winslow_smooth_2d(core_patch, iterations=int(core_smooth_iters))
    patches.append(core_patch)
    names.append(TIP_BLOCK_NAMES[4])

    patches, flipped = orient_patches_2d(patches)
    info = {
        "topology": "grouped_boundary_edge_similarity_core_OH",
        "block_names": list(names),
        "boundary_groups": [list(g) for g in groups],
        "boundary_edge_points": [int(len(e)) for e in edges],
        "core_points": [int(n_a), int(n_b)],
        "collar_points": int(collar_points),
        "core_shrink": float(core_shrink),
        "corner_pull": float(corner_pull),
        "shape_window": float(shape_window),
        "core_smooth_iters": int(core_smooth_iters),
        "centroid": [float(centroid[0]), float(centroid[1])],
        "orientation_flipped": flipped,
        "source": "paper §2.3.1 (grouped boundary edges) + Eq. 18 (shape-constrained edges)",
    }
    return patches, info


def map_patch_2d_to_tip(wing, patch_2d: Array) -> Array:
    n_xsec = len(wing.xsecs)
    sides = [[patch_2d[i] for i in range(patch_2d.shape[0])] for _ in range(n_xsec)]
    return np.stack([m[:, -1, :] for m in _map_sides_to_wing(wing, sides)], axis=0)


# ---------------------------------------------------------------------------
# S4's spanwise law — uniform, deliberately NOT tip-anchored
# ---------------------------------------------------------------------------


def spanwise_fractions(lengths: list[float], *, target_cell: float) -> list[Array]:
    """Uniform cells at `target_cell` per interval. See the module docstring."""
    out = []
    for L in lengths:
        n = max(2, int(round(float(L) / float(target_cell))))
        out.append(np.linspace(0.0, 1.0, n + 1)[:-1])
    return out


def realise_spanwise(blocks: list[Array], fractions_per_interval) -> list[Array]:
    """Subdivide each native spanwise interval by its fraction list.

    `_map_sides_to_wing` returns ``(points_along_side, n_xsec, 3)``, so **spanwise is
    axis 1**, not axis 0. Subdividing axis 0 instead produces a mesh that looks
    plausible — it is watertight, it has the right block count — and is refined in
    the wrong direction entirely: the first build of S4 reported 79 spanwise cells
    while every block still had exactly the 17 native stations.
    """
    out = []
    for b in blocks:
        cols = []
        for j in range(b.shape[1] - 1):
            f = np.atleast_1d(fractions_per_interval[j]).reshape(1, -1, 1)
            cols.append(b[:, j][:, None, :] * (1.0 - f) + b[:, j + 1][:, None, :] * f)
        cols.append(b[:, -1][:, None, :])
        out.append(np.concatenate(cols, axis=1))
    return out


OML_NAMES = [f"oml_{k}" for k in ARC_ORDER]


def build_surface(
    wing,
    *,
    level: str = "L2_smoke",
    te_thickness_abs_m: float = TE_THICKNESS_ABS_M,
    ring_corners: tuple = RING_CORNERS,
    core_shrink: float = 0.75,
    corner_pull: float = 1.0,
    shape_window: float = 0.0,
    core_smooth_iters: int = 400,
    realise_law: bool = True,
    **overrides,
) -> tuple[list[SurfaceBlock], dict]:
    """S4's surface: 8 OML blocks on the Type 1 arcs plus the 5-domain tip."""
    if level not in LEVELS:
        raise MeshBuildError(f"unknown level {level!r}; known: {sorted(LEVELS)}")
    cfg = dict(LEVELS[level])
    cfg.update({k: v for k, v in overrides.items() if v is not None})

    groups = boundary_groups(ring_corners)

    xsecs = list(wing.xsecs)
    if len(xsecs) < 3:
        raise MeshBuildError("S4 needs at least three spanwise stations.")

    counts = None
    sides_by_xsec, tip_res, vertex_report = [], None, []
    for xsec in xsecs:
        coords, le_index = section_loop_2d(xsec, te_thickness_abs_m=te_thickness_abs_m)
        verts, v_info = type1_vertices(coords, le_index)
        normals = surface_normals(coords, le_index, verts)
        _t2, t2_info = type2_vertices(verts, normals, v_info["chord"])
        arcs = section_arcs(coords, le_index, verts)
        if counts is None:
            # One allocation for the whole wing: connectivity must not depend on the
            # section, or the block dimensions stop being a deterministic signature.
            counts = arc_counts(
                arcs,
                chord_points=cfg["chord_points"],
                base_points=cfg["base_points"],
                nose_points=cfg["nose_points"],
                groups=groups,
            )
        res = resample_arcs(arcs, counts)
        tip_res = res
        sides_by_xsec.append([res[k] for k in ARC_ORDER])
        vertex_report.append({"chord": v_info["chord"], **t2_info})

    oml = _map_sides_to_wing(wing, sides_by_xsec)

    le_line = np.asarray(
        wing.mesh_line(x_nondim=[0.0] * len(xsecs), z_nondim=[0.0] * len(xsecs), add_camber=False)
    )
    lengths = [float(np.linalg.norm(le_line[i + 1] - le_line[i])) for i in range(len(xsecs) - 1)]
    fracs = spanwise_fractions(lengths, target_cell=cfg["target_cell_m"])
    if realise_law:
        oml = realise_spanwise(oml, fracs)

    blocks = [
        SurfaceBlock(name=n, xyz=b, family="wall") for n, b in zip(OML_NAMES, oml, strict=True)
    ]
    cap_2d, cap_info = tip_domains_2d(
        tip_res,
        collar_points=cfg["collar_points"],
        core_shrink=core_shrink,
        corner_pull=corner_pull,
        shape_window=shape_window,
        core_smooth_iters=core_smooth_iters,
        groups=groups,
    )
    blocks += [
        SurfaceBlock(name=n, xyz=map_patch_2d_to_tip(wing, p), family="wall")
        for n, p in zip(cap_info["block_names"], cap_2d, strict=True)
    ]

    blocks, orientation = orient_blocks_consistently(blocks)
    info = {
        "strategy_id": STRATEGY_ID,
        "level": level,
        "level_settings": cfg,
        "te_thickness_abs_m": te_thickness_abs_m,
        "arc_counts": counts,
        "ring_corners": list(ring_corners),
        "boundary_groups": [list(g) for g in groups],
        "boundary_edge_points": list(boundary_edge_points(counts, groups)),
        "oml_block_names": OML_NAMES,
        "tip_block_names": cap_info["block_names"],
        "tip_closure": cap_info["topology"],
        "tip_cap_info": cap_info,
        "orientation": orientation,
        "type2": {
            "delta_frac_of_chord": DELTA_BL_FRAC,
            "self_intersecting_sections": sum(1 for r in vertex_report if r["self_intersecting"]),
            "sections": len(vertex_report),
        },
        "spanwise": {
            "law": "uniform_target_cell_not_tip_anchored",
            "target_cell_m": cfg["target_cell_m"],
            "segment_lengths_m": lengths,
            "cells_per_interval": [int(len(np.atleast_1d(f))) for f in fracs],
            "realised": bool(realise_law),
            "spanwise_cells": int(sum(len(np.atleast_1d(f)) for f in fracs))
            if realise_law else len(xsecs) - 1,
            "native_stations": len(xsecs),
        },
        "source": "Applied Sciences 2026, 16, 7588 §§2.2-2.3",
    }
    return blocks, info
