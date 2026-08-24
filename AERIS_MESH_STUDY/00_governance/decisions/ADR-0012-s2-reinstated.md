# ADR-0012 — S2 Reinstated: the cross-field tip is buildable with what is installed

Date: 2026-08-15
Status: Accepted

**Supersedes ADR-0009** (S2 formally deferred).
Restores S2 to the tournament under ADR-0011's ordinary per-strategy workflow.

---

## 1. What ADR-0009 decided, and on what basis

ADR-0009 deferred S2 after asking the right question:

> Does a cross-field / quad-extraction tip layout map to **structured multiblock**
> blocks that pyHyp can march and that CGNS can carry with per-block families?

It answered no, on two grounds:

1. **"The structured decomposition afterwards is the part that does not exist."**
   `igl` and `QEx` would supply the cross-field and the quad extraction, but
   converting a quad layout into logically-rectangular blocks was judged to be
   unsupplied by any available package and "a substantial piece of work".
2. **"There is no concrete route"** from the available tooling to a pyHyp-marchable
   structured multiblock tip.

Both grounds are now falsified, and the first was falsified by the source paper
itself at the time the ADR was written.

## 2. Ground 1 is wrong: the decomposition IS specified, in the paper

*Automatic Multiblock Mesh Generation for 3D-Wing Aerodynamic Analysis* (Yu et al.,
Complex System Modeling and Simulation, June 2026, 6(2): 151-163) gives the
quad-layout-to-block decomposition explicitly as **Algorithm 2, "Multiblock
extraction algorithm"**, on page 157:

> "We firstly mark domain borders by enumerating separatrices from singularities
> (non-four valenced points). Then we flood quads according to cell adjacency from a
> random one until it reaches domain borders in a breadth-first manner. Each flooded
> region is marked as a block. Repeating the flooding procedure until all quads are
> visited, yielding a valid blocking of the surface."

Pseudocode is printed in full: trace from each singularity by repeatedly taking the
*opposite* edge until reaching a boundary or another singularity, marking those
edges as domain borders; then breadth-first flood-fill the quads between borders,
each flooded region becoming a block. It is about forty lines of array code and
needs nothing beyond `numpy` and a queue.

**ADR-0009 asserted that this step "does not exist" while it was printed in the
paper the strategy is drawn from.** That is the load-bearing error. The missing
component was never the decomposition; it was the cross-field solver that produces
the quad mesh Algorithm 2 consumes.

## 3. Ground 2 is wrong: gmsh supplies the cross-field

`gmsh 4.15.2` is installed in the main `.venv` and has been throughout. It provides
`Mesh.Algorithm = 11`, the **quasi-structured quad** mesher — a cross-field-driven
quad meshing pipeline of exactly the class the paper describes. Verified on
2026-08-15:

    gmsh 4.15.2
      alg  8  Frontal-Delaunay quads   OK   element types: ['Quadrilateral 4']
      alg 11  quasi-structured quad    OK   element types: ['Quadrilateral 4']

`igl` / `QEx` / `meshio` / `shapely` remain uninstalled and are **not needed**:

| paper step | requirement | available |
|---|---|---|
| §3.3 triangulated tip, curvature-adaptive remeshing | surface mesher | **gmsh** |
| §3.3 cross-field parameterisation to quads | the hard part | **gmsh alg 11** |
| Algorithm 1, shape-preserving smoothing (eps 1e-3, T 0.6) | Laplacian + vertex normals | numpy |
| Algorithm 2, multiblock extraction | separatrix trace + flood fill | numpy |
| Eqs. 2-4, barycentric density mapping | sparse solve, mean-value coordinates | scipy.sparse |
| CGNS output with per-block families | writers | already in `shared/` |

## 4. The remaining ADR-0009 argument, and why it does not carry

ADR-0009 also noted that the paper's own minimum volume hex scaled Jacobian was
**0.0539**, "an order of magnitude below the 0.30 ranking target". That observation
stands and is worth carrying into S2's study, but it is an argument about how S2
will *rank*, not about whether it can be *built*.

ADR-0011 §6.3 already handles this: `0.30` is a ranking target, never a gate, and
the hard gate is `> 0`. A strategy expected to rank poorly is still run — that is
the same reasoning ADR-0011 §3.1 used to overturn ADR-0006's refusal to develop S0.
Declining to build an entrant because it is predicted to lose is how a tournament
stops being able to falsify its own expectations.

## 5. Decision

**S2 is reinstated** and runs under ADR-0011's ordinary workflow (§7.1 steps 1-8),
in its declared order position, with its own `STUDY.md` and effort ledger.

Implementation follows the paper: gmsh triangulation and cross-field quad meshing,
Algorithm 1 for smoothing, Algorithm 2 for block extraction, barycentric mapping for
density, then the shared pyHyp invocation and the frozen gates.

**The tournament is six entries, not five.**

## 6. Consequences

- ADR-0009's "the tournament resolves to one topology" consequence is withdrawn
  along with the deferral.
- No new dependency is introduced. If S2 later needs `igl`/`QEx`, that is a new
  decision with its own justification.
- The dependency audit in `00_governance/dependency_audit.yaml` records
  `igl / QEx / meshio / shapely` as blocking S2. That row is **wrong** and should be
  corrected to record gmsh as the enabling package.
- **A general lesson for this study, added to COMMON_BRIEF:** before recording a
  method as infeasible, check whether the source specifies the missing step, and
  check what the installed toolchain already provides. Both checks were available in
  Stage 02 and neither was made. This is the second signed ADR in this study whose
  central claim did not survive being measured — ADR-0006's "not tunable" was the
  first — and both failed the same way, by reasoning from an assumption instead of
  from the source or the code.

## 7. Evidence

- The paper, §3.3 and Algorithms 1-2, pp. 156-157
- gmsh algorithm availability, verified 2026-08-15 (§3 above)
- ADR-0009 (superseded here), ADR-0011 §3.1 and §6.3
- `AERIS_MESH_STUDY/status`
