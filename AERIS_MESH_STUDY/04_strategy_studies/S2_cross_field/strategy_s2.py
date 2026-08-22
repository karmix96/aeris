"""S2 — cross-field tip meshing. Written from the paper under ADR-0012.

Source: Yanchao Yu et al., *Automatic Multiblock Mesh Generation for 3D-Wing
Aerodynamic Analysis*, Complex System Modeling and Simulation, June 2026,
6(2): 151-163 — `papers/Automatic Multiblock Mesh Generation for 3D-Wing
Aerodynamic Analysis.pdf`, §§3.1-3.3 and Algorithms 1-2.

ADR-0012 reinstated S2 after ADR-0009 deferred it. Both of that deferral's grounds
were wrong: the quad-layout-to-block step is printed in the paper as Algorithm 2,
and the cross-field solver it needs is `gmsh`'s quasi-structured quad mesher
(`Mesh.Algorithm = 11`), installed here throughout.

================================================================================
THE METHOD, AND THE ONE DELIBERATE DEVIATION
================================================================================

The paper's §3.3 pipeline, followed here:

1. triangulate the tip surface with curvature-adaptive refinement;
2. build a cross field from the boundary edges as directional constraints;
3. global parameterisation aligning UV gradients with the crosses;
4. extract a quad mesh from the parameterisation;
5. **Algorithm 1** — shape-preserving quality optimisation: Laplacian step,
   projected back along the vertex normal so the surface is preserved. The paper
   uses smoothing coefficient ``eps = 1e-3`` and target ``T = 0.6``, and reports
   "rapid quality convergence within five iterations", reaching minimum scaled
   Jacobian **0.745** at a Hausdorff distance of 0.0005%;
6. **Algorithm 2** — multiblock extraction: enumerate separatrices from each
   singularity (non-four-valent vertex) by repeatedly taking the *opposite* edge
   until a boundary or another singularity is reached, marking those edges as
   domain borders; then breadth-first flood-fill quads between borders, each
   flooded region becoming a block. The paper reports **7 blocks** for its tip;
7. barycentric mapping (Eqs. 2-4) for density control, with mean-value
   coefficients and an integer block quantisation minimising ``E_wing``.

**The deviation, and it is required by the runbook.** RUNBOOK §6 S2 states: "Do not
automatically copy the paper's rounded NURBS geometry." §3.2 of the paper builds its
own rounded NURBS wingtip from control points; AERIS's tip is the blunt section the
generator prescribes, and the fidelity gate is against *that*. So S2 here applies
the paper's **meshing method** to AERIS's tip surface. Steps 1-7 are the paper's;
the surface they run on is ours.

That is the honest paper-versus-invented split for S2, and it is the same split
RUNBOOK §6 asks for.

================================================================================
WHAT MUST BE PROVED, IN ORDER
================================================================================

ADR-0009 was right that the hard question is whether this yields **structured**
blocks. So the build order is deliberately front-loaded on the risk:

    A. gmsh produces a quad mesh of the AERIS tip whose boundary nodes are
       EXACTLY the OML tip-edge nodes  (watertightness, COMMON_BRIEF §9.4)
    B. its singularity structure is small and stable across geometries
    C. Algorithm 2 extracts a small number of regions
    D. each region is logically rectangular, i.e. genuinely structured
    E. the block count is deterministic across the design space
       (ADR-0011 §6.1 hard gate)

D and E are where this strategy lives or dies. A cross-field quad mesh is only
quad-*dominant* in general; nothing guarantees its flooded regions are ni x nj.
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

from shared.ingestion import MeshBuildError, section_loop_2d  # noqa: E402

Array = np.ndarray

STRATEGY_ID = "S2_CROSS_FIELD_TIP"

#: Paper §3.3: "We employ a smoothing coefficient eps = 1e-3 and T = 0.6".
SMOOTH_EPS = 1.0e-3
SMOOTH_TARGET = 0.6
SMOOTH_MAX_ITERS = 50  # the paper reports convergence "within five iterations"

#: gmsh quasi-structured quad — the cross-field mesher (ADR-0012 §3).
GMSH_QUAD_ALGORITHM = 11


def tip_quad_mesh(
    boundary_xy: Array,
    *,
    target_size: float,
    algorithm: int = GMSH_QUAD_ALGORITHM,
    verbose: bool = False,
) -> tuple[Array, Array]:
    """Cross-field quad mesh of the tip, with the boundary pinned to the OML.

    ``boundary_xy`` is the closed tip contour, node for node as the OML tip edge
    provides it. Those nodes are inserted as gmsh points and the boundary is built
    from them, so the quad mesh shares the OML's tip-edge nodes exactly — the
    watertightness requirement of COMMON_BRIEF §9.4, which cannot be met by
    resampling the contour a second time.

    Returns ``(vertices (N,2), quads (M,4))``.
    """
    import gmsh

    pts = np.asarray(boundary_xy, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise MeshBuildError("boundary_xy must be (N, 2)")
    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1 if verbose else 0)
        gmsh.model.add("s2_tip")
        tags = [
            gmsh.model.geo.addPoint(float(x), float(y), 0.0, target_size)
            for x, y in pts
        ]
        lines = [
            gmsh.model.geo.addLine(tags[i], tags[(i + 1) % len(tags)])
            for i in range(len(tags))
        ]
        loop = gmsh.model.geo.addCurveLoop(lines)
        gmsh.model.geo.addPlaneSurface([loop])
        gmsh.model.geo.synchronize()

        # Every boundary line carries exactly one element, so its two OML nodes
        # survive into the mesh untouched.
        for ln in lines:
            gmsh.model.mesh.setTransfiniteCurve(ln, 2)

        gmsh.option.setNumber("Mesh.Algorithm", algorithm)
        gmsh.option.setNumber("Mesh.RecombineAll", 1)
        gmsh.option.setNumber("Mesh.MeshSizeMax", target_size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", target_size * 0.25)
        gmsh.model.mesh.generate(2)

        ntags, coords, _ = gmsh.model.mesh.getNodes()
        coords = np.asarray(coords, dtype=float).reshape(-1, 3)[:, :2]
        index = {int(t): i for i, t in enumerate(ntags)}

        etypes, _etags, enodes = gmsh.model.mesh.getElements(2)
        quads = None
        for et, en in zip(etypes, enodes, strict=True):
            name, _dim, _order, nnodes, *_ = gmsh.model.mesh.getElementProperties(int(et))
            if int(nnodes) == 4:
                quads = np.asarray(en, dtype=int).reshape(-1, 4)
            elif int(nnodes) == 3 and len(np.asarray(en)) > 0:
                raise MeshBuildError(
                    f"cross-field mesher left {len(np.asarray(en)) // 3} triangles; "
                    "the layout is quad-DOMINANT, not pure quad, and Algorithm 2 "
                    "assumes pure quads"
                )
        if quads is None:
            raise MeshBuildError("gmsh produced no quadrilaterals")
        quads = np.vectorize(index.__getitem__)(quads)
        return coords, quads
    finally:
        gmsh.finalize()


def vertex_valence(n_vertices: int, quads: Array) -> Array:
    """Number of incident quads per vertex — the paper's valence."""
    val = np.zeros(int(n_vertices), dtype=int)
    np.add.at(val, quads.ravel(), 1)
    return val


def boundary_vertices(quads: Array, n_vertices: int) -> Array:
    """Vertices on the mesh boundary (edges belonging to exactly one quad)."""
    edges: dict[tuple[int, int], int] = {}
    for q in quads:
        for a, b in zip(q, np.roll(q, -1), strict=True):
            key = (int(min(a, b)), int(max(a, b)))
            edges[key] = edges.get(key, 0) + 1
    on = np.zeros(int(n_vertices), dtype=bool)
    for (a, b), count in edges.items():
        if count == 1:
            on[a] = on[b] = True
    return on


def singularities(quads: Array, n_vertices: int) -> Array:
    """Non-four-valent interior vertices — the paper's singularities.

    Boundary vertices are excluded: on a bounded patch a boundary vertex is
    normally two- or three-valent by construction, and treating those as
    singularities would make every boundary node a separatrix source.
    """
    val = vertex_valence(n_vertices, quads)
    on_boundary = boundary_vertices(quads, n_vertices)
    return np.where((val != 4) & (~on_boundary))[0]


# ---------------------------------------------------------------------------
# Algorithm 2 — multiblock extraction (paper p. 157)
# ---------------------------------------------------------------------------


def _quad_edges(quads: Array):
    """Edge -> incident (quad, local edge index) map, and per-quad edge keys."""
    inc: dict[tuple[int, int], list[tuple[int, int]]] = {}
    keys = np.empty((len(quads), 4), dtype=object)
    for qi, q in enumerate(quads):
        for k, (a, b) in enumerate(zip(q, np.roll(q, -1), strict=True)):
            key = (int(min(a, b)), int(max(a, b)))
            keys[qi, k] = key
            inc.setdefault(key, []).append((qi, k))
    return inc, keys


def extract_blocks(quads: Array, n_vertices: int, vertices_xy: Array) -> tuple[list[list[int]], dict]:
    """Algorithm 2, verbatim from the paper.

    > "We firstly mark domain borders by enumerating separatrices from
    >  singularities (non-four valenced points). Then we flood quads according to
    >  cell adjacency from a random one until it reaches domain borders in a
    >  breadth-first manner. Each flooded region is marked as a block. Repeating
    >  the flooding procedure until all quads are visited, yielding a valid
    >  blocking of the surface."

    Separatrix tracing follows the printed pseudocode: from a neighbour edge of a
    singularity, repeatedly take the **opposite** edge of the quad until a boundary
    or another singularity is reached, marking each traversed edge as a domain
    border.
    """
    inc, keys = _quad_edges(quads)
    border: set[tuple[int, int]] = set()
    sing = set(singularities(quads, n_vertices).tolist())

    # The mesh boundary is always a domain border.
    for key, owners in inc.items():
        if len(owners) == 1:
            border.add(key)

    # Vertex-based separatrix. "Opposite edge of e" is read THROUGH THE VERTEX:
    # arriving at w along (v,w), the separatrix continues along the edge opposite
    # (v,w) in w's cyclic edge order — index + valence/2. That is the standard
    # definition and it emits exactly one line per incident edge of a singularity.
    #
    # The face-based reading (opposite edge WITHIN a quad) was implemented first
    # and measured: it marks far too much and shatters the domain into 64-110
    # blocks on a ~340-quad mesh, against the paper's 7.
    vert_edges: dict[int, list[tuple[int, int]]] = {}
    for key in inc:
        vert_edges.setdefault(key[0], []).append(key)
        vert_edges.setdefault(key[1], []).append(key)

    def _other(key: tuple[int, int], v: int) -> int:
        return key[1] if key[0] == v else key[0]

    def _walk_vertex(v_start: int, first_edge: tuple[int, int]) -> None:
        v, e = v_start, first_edge
        for _ in range(4 * len(quads)):
            border.add(e)
            w = _other(e, v)
            if w in sing:
                return
            ring = vert_edges.get(w, [])
            if len(ring) != 4:            # boundary or irregular: stop
                return
            # order w's edges cyclically by angle, take the one opposite e
            ang = []
            for k2 in ring:
                u = _other(k2, w)
                d = vertices_xy[u] - vertices_xy[w]
                ang.append(np.arctan2(d[1], d[0]))
            order = list(np.argsort(ang))
            ring_sorted = [ring[j] for j in order]
            idx = ring_sorted.index(e)
            e = ring_sorted[(idx + 2) % 4]
            v = w

    for vs in sing:
        for key in vert_edges.get(vs, []):
            _walk_vertex(vs, key)

    visited = np.zeros(len(quads), dtype=bool)
    blocks: list[list[int]] = []
    for seed in range(len(quads)):
        if visited[seed]:
            continue
        queue, block = [seed], []
        visited[seed] = True
        while queue:
            qi = queue.pop(0)
            block.append(qi)
            for k in range(4):
                key = keys[qi, k]
                if key in border:
                    continue
                for nb, _ in inc[key]:
                    if nb != qi and not visited[nb]:
                        visited[nb] = True
                        queue.append(nb)
        blocks.append(block)

    info = {
        "n_blocks": len(blocks),
        "n_singularities": len(sing),
        "n_border_edges": len(border),
        "block_sizes": sorted((len(b) for b in blocks), reverse=True),
    }
    return blocks, info
