# S2 — cross-field tip meshing

**Status: REJECTED 2026-08-15** on the user's signal — built, measured, and failing
a frozen hard gate. Unranked under ADR-0011 §6.3.

**Rejected on measurement, not prediction.** That distinction matters here: ADR-0006
(S0 "not tunable") and ADR-0009 (S2 "no concrete route") were both wrong because
they reasoned from assumption. This rejection rests on block counts of 27, 27, 31,
37, 37, 39 across six geometries — data, reproducible with `strategy_s2.py`.

**Status: BUILT, and it fails the determinism hard gate.** Block count varies
27–39 across geometries; ADR-0011 §6.1 requires a deterministic block count and
connectivity signature. Not a quality failure — a topology-stability failure, which
is precisely what RUNBOOK §6 S2 asked to be measured.

**Strategy ID:** `S2_CROSS_FIELD_TIP`
**Source:** Yanchao Yu et al., *Automatic Multiblock Mesh Generation for 3D-Wing
Aerodynamic Analysis*, Complex System Modeling and Simulation, June 2026,
6(2): 151–163, §§3.1–3.3 and Algorithms 1–2.
**Governing decision:** ADR-0012 (reinstated S2; supersedes ADR-0009).

---

## 1. What the paper states versus what had to be invented

| aspect | the paper states | status here |
|---|---|---|
| tip geometry | §3.2 builds a **rounded NURBS tip** from control points | **deliberately not used** — RUNBOOK §6 S2: *"Do not automatically copy the paper's rounded NURBS geometry."* S2 applies the paper's *method* to AERIS's blunt tip section |
| triangulation, curvature-adaptive | §3.3 | gmsh |
| cross-field parameterisation → quads | §3.3, the hard component | **gmsh `Mesh.Algorithm = 11`** (quasi-structured quad) |
| Algorithm 1, shape-preserving smoothing | ε = 1e−3, T = 0.6, "within five iterations", min SJ **0.745** | not reached — the study stopped at the determinism gate |
| Algorithm 2, multiblock extraction | separatrices from singularities → flood fill; paper reports **7 blocks** | **implemented**; "opposite edge of e" is ambiguous and had to be interpreted (§3) |
| Eqs. 2–4, barycentric density mapping | mean-value coefficients, integer quantisation | not reached |

**Source read:** the full paper, in particular §§3.1–3.3, Algorithms 1–2, and the
reported results in §4.

## 2. ADR-0009's two grounds were both wrong

Recorded in ADR-0012 and repeated here because it cost the study a strategy:

* ADR-0009 said the quad-layout-to-block step "does not exist". **It is Algorithm 2,
  printed on page 157 of the paper the strategy is drawn from.**
* ADR-0009 said there was "no concrete route" from available tooling. **gmsh 4.15.2
  has been installed throughout** and provides the cross-field quad mesher.

## 3. "Opposite edge of e" — three readings, measured

The pseudocode's line `e ← opposite edge of e` does not say opposite *within a face*
or *through a vertex*. All three attempts are recorded because the difference is
enormous and only measurement separated them:

| reading | block sizes on a 337-quad mesh | verdict |
|---|---|---|
| arbitrary owner quad, stop when already marked | `[327, 1, 1, 1, 1]` | ❌ not a partition — one mega-block |
| **face-based**: opposite edge within the quad, walking face to face | 64–110 blocks | ❌ over-marks, shatters the domain |
| **vertex-based**: at each vertex take the edge opposite in cyclic order | `[90, 30, 30, 30, 30, 30, 14, 9]` | ✅ a credible partition |

The vertex-based reading is the standard definition of a separatrix and is the one
adopted. The first two are kept in the record because each *looked* plausible and
produced results that would have been reported as method failures had they not been
checked against what a partition should look like.

## 4. The result: topology is not deterministic

Six geometries of `lhs100_seed42`, tip section, target size 0.04c:

| geometry | quads | singularities | **blocks** |
|---|---:|---:|---:|
| 000 | 337 | 7 | **31** |
| 001 | 353 | 5 | **27** |
| 002 | 287 | 6 | **37** |
| 003 | 347 | 7 | **39** |
| 004 | 353 | 5 | **27** |
| 005 | 287 | 6 | **37** |

    block counts: 31, 27, 37, 39, 27, 37     paper: 7     deterministic: FALSE

**ADR-0011 §6.1 hard gate 5** requires a deterministic block count and connectivity
signature across all geometries. RUNBOOK §2.1 separately disqualifies drifting
connectivity from the production design space. S2 fails both.

RUNBOOK §6 S2 named this risk in advance: *"Record singularity count and block graph.
**Topology drift across geometries is a production failure.**"* It is the one thing
the runbook told this strategy to measure, and it is what the strategy does.

**The variation is not noise.** Geometries 001/004 give identical results, as do
002/005 — the tip airfoil is the same section and only its scale differs, so the
cross field is reproducible. The block count tracks the tip section's shape, and the
design space varies that shape, so the topology varies with it.

## 5. Two further gate problems, found before stopping

**Non-conformal tip interface.** All 61 OML tip-edge nodes survive the mesher exactly
(< 1e−12), which is the watertightness condition. But gmsh's quasi-structured
pipeline re-meshes the boundary curves and inserts 61 *additional* nodes — 122 on the
cap boundary against the OML's 61. That is a hanging-node interface, which pyHyp
will not accept. `setTransfiniteCurve(line, 2)` did not prevent it; algorithm 11
re-meshes curves by design.

**Algorithm 8 is unusable.** The alternative quad algorithm leaves 11–53 triangles,
and Algorithm 2 assumes a pure quad mesh.

## 6. Why the study stopped here

COMMON_BRIEF §4: *"If the next reasonable action is a guess rather than a measured
hypothesis, say so plainly and stop."*

The determinism gate is failed, the cause is identified (the cross field's
singularity structure depends on the section shape, which the design space varies),
and no parameter of the method addresses it — the singularity count is an output of
the cross-field solve, not an input. Making it deterministic would require
constraining the cross field to prescribed singularity positions, which gmsh does not
expose and the paper does not describe.

Blocks 27–39 also compare badly with S1's 13 and S0's 9 on cell-count grounds, and
the paper's own reported minimum volume hex scaled Jacobian was **0.0539** — the
concern ADR-0009 raised that does still stand.

## 7. Effort ledger

| metric | value |
|---|---:|
| distinct construction attempts | 4 |
| sessions | 1 |
| marches run | 0 |

## 8. State and next action

**Where this stands:** implemented as far as Algorithm 2, which is far enough to
answer the question the runbook posed. It produces a valid quad blocking of AERIS's
tip and that blocking is **not stable across the design space**.

**Next action, if resumed:** the only route to a deterministic topology is a
constrained cross field with prescribed singularities. That is a research component
in its own right, not a parameter change, and it should be scoped as such before any
further effort is spent.

### Why it was rejected rather than pursued

1. **Determinism is an output, not an input.** The singularity count comes out of the
   cross-field solve. No parameter of gmsh's mesher or of Algorithm 2 reaches it.
   Fixing it means constraining the cross field to prescribed singularities — not
   described in the paper, not exposed by gmsh.
2. **A second independent gate failure** — the 122-vs-61 hanging-node cap boundary —
   would still need solving afterwards.
3. **Poor position even if both were solved:** 27-39 blocks against S1's 13, and the
   paper's own reported minimum volume hex scaled Jacobian of **0.0539**, barely
   above the `> 0` hard gate. The method's advertised strength is tip surface
   appearance; this study ranks on volume quality and robustness.
4. **The runbook pre-declared this outcome.** RUNBOOK §6 S2: "Topology drift across
   geometries is a production failure." S2 drifts. That is the runbook's own
   criterion, applied as written.

**What S2 contributed to the study:** it corrected ADR-0009, established that the
cross-field route is buildable with the installed toolchain, and produced a measured
reason for exclusion where the study previously had only an assumed one.
