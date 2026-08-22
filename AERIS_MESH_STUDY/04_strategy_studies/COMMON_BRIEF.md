# COMMON BRIEF — given to every strategy before it is built

Version 1 · created 2026-08-14 · authority: ADR-0011 §3

This document is **prior knowledge**, not a result. Every strategy study reads it in
full before its first line of implementation. It exists so that the last strategy
built does not win on hindsight: Stage 02's lessons were paid for once, and they are
general, so they belong to all six entrants equally.

Nothing here is a design instruction. It says *what has been measured*, not *what to
build*. Each strategy chooses its own blocking, tip closure and distribution laws
(ADR-0011 §2). A strategy is free to contradict any item below — but it must then say
so in its `STUDY.md` and measure the outcome, because each item is an experimental
result that cost this study time.

---

## The objective these lessons serve

One structured meshing method that runs unattended, robustly, across the production
design space. A catalogue of well-documented failures is not the deliverable. If a
strategy is close to passing, finish it.

---

## 1. Inner boundaries must be constructed from the section, not by displacing the outer ring

The working construction is

```
inner = camber + width_frac * (surface - camber)
```

a **convex combination** of the camber line and the actual surface. It lies inside the
section *by construction*, for any `width_frac` in (0, 1), on any section, cambered or
not.

About **fifteen** constructions that instead derived the inner boundary by displacing
the outer ring were built, measured and rejected in Stage 02. All failed the same way:

| construction | outcome |
|---|---|
| uniform shrink toward centroid | inner ring leaves the section on the cambered lower surface |
| Laplacian smoothing of the ring, 0–400 iterations | no setting clears the fold |
| camber-directed offset of ring points | pinches to nothing at LE and TE, collapses the core block |
| inward-bisector offset | overshoots near the TE and inverts it completely |
| arc-length re-parameterisation of the inner ring | fold moves, does not clear |
| ring split at smooth stations / at the TE corners | fold relocates between arcs |
| wrap points 12–33, radial points 7–11 | monotone in neither direction |
| piecewise TE-base point allocation | no effect on the fold |
| cosine → uniform distribution around the ring | no effect on the fold |
| **elliptic (Winslow) smoothing** | made it **worse**: −0.0363 → −0.0499 |

A displaced outer ring carries **no guarantee** of remaining inside the section. That
is the whole difference. If a strategy needs an interior boundary curve, deriving it
from the section geometry is the property that matters, not the smoothness of the
derivation.

## 2. Inset the inner rectangle chordwise

If the inner rectangle spans the full chord of the cap, the collar end edges run
**collinear with the rectangle's short sides**, which degenerates the corner cells to
zero Jacobian. A small chordwise inset (0.02 in the S1 realisation) makes those end
edges slant and removes the degeneracy.

This is the same failure class as ADR-0006's ~180° cap4 corner: a block corner placed
where the two meeting edges are collinear. **Block corners belong on genuine geometric
features** — the leading edge, the two blunt trailing-edge base corners, section
extremes — never on an arbitrary x/c station of a smooth contour.

## 3. Cell-size range and min-cell/`s0` predict marchability; scaled Jacobian does not

This is the single most expensive lesson of Stage 02 and it was missed for the entire
stage. Recorded as **ADR-0010**.

| surface | min scaled Jac | cell-size range | min cell / `s0` | march |
|---|---:|---:|---:|---|
| cap4 (the control) | **+0.0046** | **153×** | **48.7** | completes, 54/128 bad layers |
| S1 as first built | **+0.3250** | 3462× | 0.9 | **explodes at layer 2**, coordinates to 1e+24 m |
| S1 after redistribution | +0.045 | **99×** | 15.4 | **0/128 bad layers, min quality +0.224** |

cap4's cell *shape* is ~70× worse than S1's first surface and it marches. S1's shape
was excellent and it could not march at all. The mechanism is visible in the march
log: at layer 2 the linear solver hits `kspMaxIts = 1500`, returns a small negative
volume (−9.4e−09), then diverges by roughly twelve orders of magnitude per layer. **An
implicit hyperbolic solve is conditioned by the RANGE of cell sizes, not by individual
cell shape.**

The two objectives trade monotonically, so they cannot both be maximised:

| S1 configuration | cell-size range | min scaled Jac |
|---|---:|---:|
| te_base 9, collar 5 | 1068× | +0.3250 |
| te_base 5, collar 3 | 534× | +0.3119 |
| te_base 3, collar 3 | 396× | +0.1363 |
| cap4 | **153×** | +0.0046 |

Every gain in minimum scaled Jacobian during the tip-fold hunt came from **subdividing
the tip more finely**, which improves shape and shrinks the smallest cell. The
smallest cell is what breaks the march.

**Practical consequence:** measure `min_cell_edge_m` against pyHyp's first-layer height
`s0`, and the ratio `max_cell / min_cell` over the staged surface, *before* asking for
a march. `qc_blocks` reports both. Both are reported metrics under ADR-0011 §6.

**Known limit of this model, stated honestly.** Cell-size range predicts *catastrophic
explosion*. It does **not** predict *marginal single-layer failure*. When `lhs7_01`
failed at epsE 2.0 at the `fine` level (min quality −0.210 in one layer), three
hypotheses were tested and none held: lhs7_01 had the second-*best* cell-size range
(88×) while the worst (190×) passed; its max adjacent-normal angle was mid-range; and
two other geometries with the same twist reversal both passed. The bad cell was at
layer 0, the first cell off the wall, with **positive** volume and negative quality. No
surface metric currently known to this study predicts that failure.

## 4. Consistent outward normals is a real gate, and per-block checks cannot see it

pyHyp rejects the surface at **input**, in about two seconds, with

```
ERROR: Normal directions may be wrong
```

Watertight plus positive scaled Jacobian is **not** sufficient. Each block can be
individually well-formed while its neighbour faces the other way — S1's first staged
surface had all five tip blocks pointing inward (outward-dot ≈ −0.985) against the OML
blocks pointing outward, and every per-block winding check passed.

Orientation must be **propagated across shared edges**: two correctly oriented
neighbours traverse a shared edge in *opposite* directions, so a breadth-first walk
from a seed block fixes every relative orientation. The surface is then flipped
globally if its enclosed signed volume (divergence theorem) is negative, so the
normals point outward rather than merely agreeing.

`shared/qc.py::orient_blocks_consistently` implements this and is available to every
strategy. It reports `blocks_reached_by_edge_walk`; if that is less than the block
count, the surface is disconnected and the result is not trustworthy.

## 5. Verify the verifier

**Five instrument bugs were found in Stage 02, each reporting a false failure on a
sound mesh.** Before trusting any negative result, check the instrument.

| # | bug | false symptom |
|---|---|---|
| 1 | distance measured to sampled *points* instead of polyline *segments* | error floored at half the reference spacing — reported 0.0507% on an exact mesh |
| 2 | **open** reference contour, excluding the blunt base | TE base block reported 0.2516% off-surface — exactly half `te_thickness` |
| 3 | watertightness tested in the wrong direction (required every cap boundary node to lie on the OML edge) | cap-internal interfaces reported as holes |
| 4 | tip-edge nodes taken from *every* OML block's outboard edge | on segmented S3, a **0.58 m** gap reported on a sound mesh |
| 5 | determinism hashing block *dimensions*, when RUNBOOK §2.1 freezes **connectivity** and explicitly permits counts to adapt | S3 failed for doing exactly what the runbook permits |

A sixth, of the same class: the fidelity check **silently skipped** any block whose
spanwise dimension differed from the station count — which is exactly what a
spanwise-refined block looks like. It would have reported a refined mesh as
fidelity-perfect while its interpolated columns sat off the loft entirely. It now
records `skipped_spanwise_refined_blocks` and `fidelity_unverified_for_refined_blocks`
rather than skipping silently.

## 6. Identical failure across independent strategies indicates shared infrastructure

Four structurally different strategies failing *identically* — agreeing to 11–12
significant figures on scale-invariant metrics, with the same worst block — is not
four hard problems. It is one problem, upstream of all four.

A ~15-variant parameter search was the wrong instrument for that signal. The right
move was reading the implementation already proven in this codebase (see item 8).

Corollary for this restructure: because the six studies are now genuinely independent
(ADR-0011 §2), identical failure across them points at the **shared control module**
— ingestion, QC definitions, the pyHyp invocation, the geometry sets, or the verifier
— and that is where to look first.

## 7. Refinement is not uniformly harder

Going from the `smoke` level (N=129, coarsen=1) to `fine` (N=193, coarsen=1) at fixed
epsE, **8 of 10 geometries improved and 2 degraded**, one past zero. Refinement effects
are geometry-specific, not a global margin that can be absorbed by tightening
everything.

Two consequences:

- A value confirmed only at the coarse level is not confirmed. `epsE_common_start = 2.0`
  passed all ten at `smoke` and failed `lhs7_01` at `fine` (min quality −0.210). Without
  the confirmation step it would have been frozen into every downstream pyHyp strategy.
- **Verify that the "finer" level actually is finer.** The `L*` family uses `coarsen=4`.
  Only `smoke → fine → production` is a refinement ladder at full surface resolution.
  ADR-0008 originally named `L4` as the confirmation level, which is N=37 at coarsen=4
  — substantially *coarser* than the `smoke` calibration. It would have confirmed
  nothing. The error is recorded in ADR-0008 rather than silently patched.

## 8. A working implementation may already exist in git history

The tip closure that works came from commit **`bfaeaf1`** — *"cap4 camber-split tip cap
— full-resolution pyHyp march validated at L1"*. It was found after roughly fifteen
constructions had been built and rejected.

**Read the repository before opening a parameter search.** `git log --all --oneline`,
`git log -S<symbol>`, and the existing `src/aeris/mesh/` and `src/aeris/cfd/meshing/`
trees are cheaper than a sweep and more likely to be right.

---

## 9. Additional context every strategy should have

These are not from the mandated list in ADR-0011 §3; they are Stage 02 measurements
of the same general kind, recorded here so no strategy has to rediscover them.

**9.1 The blunt trailing edge shrinks 6× spanwise.** It is 4.70 mm wide at the root and
0.78 mm at the tip. Any *fixed* radial or chordwise point count across a face that
narrows like this manufactures microscopic cells at the narrow end — a fixed
`collar_points = 13` produced an 11.9 µm cell, below pyHyp's 13.4 µm first layer, and
the march inverted at layer 2. Counts that scale with local physical size do not have
this failure mode.

**9.2 Cosine chordwise clustering interacts badly with taper.** The tip chord is up to
5× smaller than the root, so identical cosine clustering makes the tip cells about 5×
finer again. Measured on `lhs7_00`: cosine gave a 396× cell-size range, uniform gave
**99×** — better than cap4's 153×. Resolving leading-edge curvature is a real
requirement and this trade will have to be revisited once marching is established; it
is recorded as a measurement, not as a recommendation to use uniform spacing.

**9.3 `characteristic_length` is the bounding-box DIAGONAL.** `aeris.mesh.surface`
computes it as `norm(ptp(points, axis=0))`, and pyHyp derives **both** `s0` and
`marchDist` from it. Using the x-extent instead (0.94 against the correct 1.5171) makes
every march inconsistent with every cap4 number this study compares against. Use
`shared/pyhyp_runner.py::characteristic_length`.

**9.4 Watertightness cannot be achieved by resampling the same contour twice.** A cap
that builds its own ring at its own point count never shares nodes with the OML tip
edge: an 11 mm hole, with every block passing QC individually. Whatever a strategy's
tip closure is, its outer boundary must be taken from the OML side curves *exactly*,
node for node.

**9.5 Spanwise interpolation has a measured fidelity cost.** Subdividing between the
generator's realised stations by linear blending deviates from the spline loft by
**1.99e−02 m ≈ 7.4% of chord** against a hard fidelity gate of 0.01% of chord. cap4
does this too (17 native stations refined to 255), so it is inherited practice rather
than a new sin, but it is a gate violation waiting to be called. The correct fix is
upstream — have the generator realise more sections; `pygeo.extraction.spanwise_sections`
is already 25 against the 17 the wing exposes — and that is Stage 03 geometry work.
`shared/qc.py::spanwise_interpolation_error` measures it. Any strategy that refines
spanwise must report this number.

**9.6 Deformation alone cannot meet the fidelity gate.** A frozen-topology RBF transfer
with machine-zero landmark residual (3.7e−15 m) still left the surface **2.35–3.50% of
chord** off the target OML — 250–350× the 0.01% gate. This is not a fitting failure;
the RBF reproduces its landmarks exactly and still cannot reproduce the surface between
them across this design space. Projection to the prescribed CAD is mandatory for any
deformation-based method, not a refinement.

**9.7 The generator does not realise a section at every semantic station.** `b1` gets
no realised section, so anchors driven from the contract stations snap to the nearest
realised section with a residual of 0.003–0.028 m. Report the residual; do not
interpolate a station into existence without measuring the fidelity cost (9.5).

**9.8 More dissipation is not monotonically better.** On `lhs7_08`, epsE 3.0 gave 9 bad
layers where 2.0 gave none. At the `fine` level the ordering across all ten geometries
was monotonic the *other* way: 1.5 → 10/10, 2.0 → 9/10, 3.0 → 6/10. Do not assume the
top of the ladder is the safe end.

**9.9 Off-protocol quick runs are worse than no runs.** A fast "does it march at all"
attempt at N=37 with hand-edited coarsening produced a CGNS whose coordinates reached
1e+17 m on a 1.18 m semi-span, and ParaView refused to render it. The settings, not the
topology, were the cause. Run the protocol or run nothing; a wrong number in the record
costs more than a missing one.

---

## 10. Amendment rule

Anything **general** learned during a strategy study is added to this brief, and **every
already-completed strategy is re-checked against the addition**. Anything
**method-specific** stays inside that strategy's `STUDY.md`. Record which, each time, in
the log below and in `status`.

Re-checking a frozen strategy against a new brief item does not reopen it for tuning.
It answers one question — does the new knowledge invalidate its recorded result? — and
the answer is recorded either way.

## 11. Added from S0 (2026-08-14) — general, applies to every strategy

**11.1 Point counts must scale with the chord FRACTION a block covers.** If a block
spans a fixed fraction of chord, its point count has to scale with the global
chordwise count or its cells drift out of proportion across the mesh family:

    block_points ~ chord_points * block_chord_fraction / (remaining fraction)

`MESH_FAMILY_V2.md` states this for cap4's wrap blocks and the code never applied
it. Applying it is what took S0 from a Jacobian-versus-range trade to **+0.191 at a
113× range, level-invariantly**. Before sweeping a block's point count, check
whether a scaling law for it already exists and is simply not wired up.

**11.2 The cell-size range's only lever is usually the CHORDWISE count.** On S0 the
largest cell is chordwise on the OML, so `spanwise_panels` 8 → 32 left the range at
232.4 exactly unchanged while the spanwise maximum fell 12.25 → 3.11 mm. Measure
which direction owns the maximum before trying to fix the range; **spanwise
refinement may be free with respect to marchability.**

**11.3 A block edge reaching from a tiny feature to a distant interior is stretched,
and no parameterisation fixes it.** S0's blunt base is 0.005 chord wide and its cap
interior sits ~0.12 chord away; every collar spanning that gap gave skewness
0.998–1.000. Matching the inner boundary to the outer arc-length distribution — the
standard cure for a sheared collar — changed the result by 0.0001. **A null result
from the standard cure is how you identify that the cause is geometric rather than
numerical.** The escape is to make the inner boundary follow the section closely
enough that the gap never opens.

**11.4 Refining is not free at a small tip.** Raising `chord_points` shrinks the
largest cell but also shrinks the tip cells, because the tip chord is a fraction of
the root's. S0's range improved L1 → L3 (232 → 140) and then **regressed at L4**
(210) with min-cell/`s0` falling 11.9 → 7.9. There is an optimum level; find it
rather than assuming finer is better.

**11.5 Shape metrics built in a normalised 2D section frame CANNOT vary across
geometries — do not read their constancy as robustness.** S0 reports min scaled
Jacobian +0.19113, skewness 0.878 and worst corner 168.38° *byte-identically* on all
ten development geometries and on seven design-space extremes including the
all-minimum and all-maximum planform corners. The cause is mundane: the limiting
cell is built in the normalised section frame, every geometry shares the tip airfoil
and the same *fractional* parameters, and the 3D mapping is a similarity transform —
under which all of these metrics are invariant.

Seventeen identical numbers are **one** measurement, not seventeen. **Cell-size
range and min-cell/`s0` are the only reported metrics that discriminate between
geometries** (S0: 93.3 to 233.3), and they are also the ones ADR-0010 says govern
the march. Report the invariance explicitly rather than presenting it as
independent confirmation.

**11.6 Check that a swept parameter is one the code actually reads.** ADR-0006
concluded cap4's tip corner was "not tunable" from a sweep of `split_x_fore` giving
results identical to 11–12 significant figures. cap4 never reads `split_x_fore`
(`surface.py:776` vs `:792`) — all three variants were the same mesh. Identical
results across a sweep are evidence of a null experiment at least as often as they
are evidence of a structural cause.

**11.7 Measure the worst over ALL blocks of a kind, not the first one.** S0's worst
tip corner was reported as 149.36° for a while because the measurement took the
first tip block instead of the maximum over all five. The true value is 168.38°.

## 12. Added from S4 (2026-08-16) — the tip-cap constraint, completed

ADR-0013 §2 recorded that an O-H ring on this section forces the nose wrap and the
1.0 mm base to equal point counts, and that there are "essentially two ways" to
satisfy it. S4 completes that result. Any strategy that has to cap this section
should read this **before** spending effort on a cap.

**12.1 There is a third construction, and it is the paper's own rule.** Applied
Sciences 16:7588 §2.3.1 — *"a single boundary edge may consist of multiple control
edges"*. The equality a structured ring needs is between **boundary edges**, not
between individual arcs. Group the arcs so the base travels inside a boundary edge
with a long neighbour, and the constraint becomes an equality between sums. S4's ring
reaches 23/22/23/22 boundary-edge points with the base at 3, chosen on physical
grounds rather than forced.

**12.2 The price is corner sharpness, and it is arithmetic.** The section has exactly
two sharp corners — the two blunt-TE base corners. A ring corner on both isolates the
base again, so at most one is usable, and the other three come from smooth contour.
The cap's minimum scaled Jacobian is then

    min scaled Jacobian  ~=  sin(180 deg - flattest ring corner)

Measured: flattest usable corner 179.31 deg, predicted 0.0120, measured **0.01198**.
It does **not** improve with refinement — 0.0124 from L1 to L5, a 16x cell-count
increase — because it is set by an angle.

**12.3 Interior angles at the eight Type 1 vertices, identical on every geometry
measured**, so this is a property of the airfoil family and not of one sample:

| v0 | v1 | v2 | v3 | v4 | v5 | v6 | v7 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 114.0° | 179.0° | 178.2° | 176.3° | 176.8° | 179.3° | **180.9°** | 73.2° |

**v6 is reflex.** Any ring corner there folds a core cell no matter what else is done:
`core_shrink` cannot help (a similarity preserves angles) and elliptic smoothing cannot
help (Winslow does not move boundary nodes, and a reflex corner in a structured patch
always folds its corner cell). **Measure the contour's interior angle at every
candidate ring corner before choosing one.** It is four lines of code and it would have
saved a 135-combination parameter sweep that had no positive result in it.

**12.4 The trade, for whoever builds next.** S0 and S1 keep the sharp corners — S1 by
*creating* them, with short end edges that cross the section — and pay in cell-size
range. S4 frees the base count and pays at the corners. A cap that beats both would
have to create sharp corners by construction *and* group the base, and no such
construction was found in six attempts.

**12.5 A gate written around one tool is not a gate.** ADR-0011 §6.1's volume half was
phrased in terms of pyHyp's report, and the first strategy that did not run pyHyp had
no way to be scored. ADR-0014 restates it in terms of the mesh. Write gates about the
artefact, not about the program that produced it.

### Amendment log

| date | item | general or method-specific | strategies re-checked |
|---|---|---|---|
| 2026-08-14 | v1 created from Stage 02 experience | general | none yet built |
| 2026-08-14 | §11.1–11.7 added from S0 | general | S0 (the source; already reflects them) |
| 2026-08-16 | §12.1–12.5 added from S4 | general | S4 (the source); S0/S1 unaffected — it explains their shape rather than changing it |
