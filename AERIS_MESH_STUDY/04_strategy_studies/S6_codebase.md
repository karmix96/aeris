

===== FILE: ./COMMON_BRIEF.md =====

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


===== FILE: ./export_all_surfaces.py =====

"""Export every buildable strategy's surface on ONE geometry, into one folder.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/export_all_surfaces.py [--geom N]

Purpose: side-by-side ParaView inspection. Same geometry, same level, same
exporter (`shared/export_paraview.py`, ADR-0011 section 4), so the only thing that
differs between the files is the strategy's topology.

Not every strategy produces a surface:

  S0  yes    S1  yes    S3  yes (S1's surface with S3's spanwise sweep)   S4  yes
  S2  no     rejected on measurement; no deterministic block set to export
  S5  no     not started
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for _p in (str(REPO_ROOT / "src"), str(HERE), str(HERE / "S0_cap4"),
           str(HERE / "S1_tip_first"), str(HERE / "S3_station_sweep"),
           str(HERE / "S4_analytic_multiblock")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import strategy_s0 as S0  # noqa: E402
import strategy_s1 as S1  # noqa: E402
import strategy_s3 as S3  # noqa: E402
import strategy_s4 as S4  # noqa: E402
from shared import geometry_sets  # noqa: E402
from shared.export_paraview import write_vtk  # noqa: E402
from shared.qc import qc_blocks  # noqa: E402

from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import (  # noqa: E402
    BWBDesignSample,
    build_bwb_generator_config,
)
from aeris.generators.bwb_segmented_v1.planform import (  # noqa: E402
    generate_bwb_planform_from_sample,
)

OUT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/paraview_inspection/all_strategies_surface"
DEV_SET = "lhs100_seed42"
LEVEL = "L2_smoke"


def _group_boundary_y(geom: int):
    cfg = build_bwb_generator_config(
        yaml.safe_load((REPO_ROOT / "configs/geometry/bwb.yaml").read_text())
    )
    matrix = build_lhs_design_matrix(cfg, 100, np.random.default_rng(42))
    names = cfg.active_design_variable_names()
    sample = BWBDesignSample(**{k: float(v) for k, v in zip(names, matrix[geom], strict=True)})
    return generate_bwb_planform_from_sample(sample, cfg).group_boundary_y


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--geom", type=int, default=0)
    a = ap.parse_args()

    gid = geometry_sets.geometry_id(DEV_SET, a.geom)
    wing = geometry_sets.wing(DEV_SET, a.geom)
    OUT.mkdir(parents=True, exist_ok=True)

    builds = {
        "S0_cap4": lambda: S0.build_surface(wing, level=LEVEL),
        "S1_tip_first": lambda: S1.build_surface(wing, level=LEVEL),
        "S3_station_sweep": lambda: S3.build_surface(
            wing, _group_boundary_y(a.geom), level=LEVEL, sigma=1.0, layers_per_interval=30
        ),
        "S4_analytic_multiblock": lambda: S4.build_surface(wing, level=LEVEL),
    }

    print(f"geometry {gid}, level {LEVEL}\n")
    print(f"{'strategy':20s} {'blk':>4s} {'cells':>8s} {'minJac':>10s} {'range':>8s}  file")
    for name, build in builds.items():
        try:
            blocks, _info = build()
        except Exception as exc:  # a strategy that cannot build says so, and we go on
            print(f"{name:20s} BUILD FAILED: {exc}")
            continue
        qc = qc_blocks(blocks)
        path = OUT / f"{name}_{gid}_surface.vtk"
        write_vtk(path, blocks)
        print(
            f"{name:20s} {qc['block_count']:4d} {qc['total_cells']:8d} "
            f"{qc['global']['min_scaled_jacobian']:+10.5f} "
            f"{qc['cell_size_range']:8.1f}  {path.name}"
        )

    print(f"\n{OUT}")
    print("Open all files, colour by `scaled_jacobian`, Threshold -1..0 to isolate folds.")
    print("S2 rejected and S5 not started — nothing to export for either.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./migrate_from_stage02.py =====

"""One-shot migration of `04_strategy_prototypes/stage02_common.py` per ADR-0011 §4.1.

This script is kept as the **provenance record** of the migration, not as a build
step. It was run once, on 2026-08-14, to create `04_strategy_studies/shared/` and
`04_strategy_studies/S1_tip_first/s1_internals.py`.

Why a script rather than retyping: ADR-0011 requires that **metric definitions and
gate thresholds migrate unchanged**, so results stay comparable to what is already
recorded in `status`. Extracting the exact source text guarantees that; retyping
does not. Every function that moves is copied byte-for-byte, and the two deliberate
edits (stripping S1's chordwise defaults out of `feature_split_sides`) are applied
explicitly and printed, so they are auditable.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/migrate_from_stage02.py

Re-running it overwrites the generated modules with the Stage 02 originals and would
discard any subsequent edits. It is not idempotent with respect to later development
and should not be re-run.
"""

from __future__ import annotations

import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "04_strategy_prototypes" / "stage02_common.py"

# ADR-0011 section 4.1. Left column is the symbol, right column is where it goes.
SHARED_QC = [
    "winslow_smooth_2d",
    "orient_patches_2d",
    "_boundary_edges",
    "spanwise_interpolation_error",
    "orient_blocks_consistently",
    "qc_blocks",
    "worst_corner_angle_deg",
    "write_surface_artifacts",
]
SHARED_INGESTION = ["section_loop_2d", "feature_split_sides"]
S1_PRIVATE = [
    "geometric_progression_counts",
    "camber_and_thickness",
    "_point_at_x",
    "_arc_between_x",
    "butterfly_cap_2d",
    "_closed_arclength_fractions",
    "_match_closed_parameterisation",
    "oml_tip_ring_2d",
    "butterfly_from_ring",
    "map_2d_patch_to_tip",
    "realise_spanwise_law",
]


def extract(text: str) -> dict[str, str]:
    """Exact source text of every top-level function, keyed by name."""
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            out[node.name] = "".join(lines[node.lineno - 1 : node.end_lineno])
    return out


def strip_s1_chordwise_defaults(src: str) -> str:
    """The one deliberate edit: `feature_split_sides` must not choose a chordwise law.

    ADR-0011 section 4.1. `distribution` is a chordwise distribution law and
    `te_base_points` is a chordwise point allocation; both are per-strategy under
    the independence line. Stage 02 defaulted them to S1's answers, so importing
    the function unchanged would hand every strategy S1's blocking decision.
    """
    before = src
    src = src.replace(
        "    te_base_points: int = 3,\n    distribution: str = \"uniform\",\n    beta: float = 2.0,\n",
        "    te_base_points: int,\n    distribution: str,\n    beta: float = 2.0,\n",
    )
    if src == before:
        raise SystemExit(
            "feature_split_sides signature did not match the expected Stage 02 text; "
            "inspect it by hand rather than migrating silently."
        )
    # Replace the S1-specific defence of `uniform` with a neutral contract note.
    doc_start = src.index('    """Split a section')
    doc_end = src.index('    """', doc_start + 8) + len('    """\n')
    new_doc = '''    """Split a section into sides whose corners are all genuine features.

    Returns three sides in order: upper (LE -> upper TE), lower (LE -> lower TE),
    and the blunt TE base as its own short side. Corners land on the leading edge
    and on the two trailing-edge base corners - all real curvature features.

    SHARED CONTROL (ADR-0011 section 4). This function is ingestion: it turns the
    generator's section into side curves. It does NOT choose a chordwise law.
    ``distribution``, ``beta`` and ``te_base_points`` are **required** and must be
    supplied by the calling strategy, because chordwise clustering and point
    allocation are per-strategy under the independence line. Stage 02 defaulted
    these to S1's answers, which is exactly what ADR-0011 exists to prevent.

    COMMON_BRIEF section 9.2 records the measurement behind S1's own choice - on
    lhs7_00, cosine gave a 396x cell-size range and uniform gave 99x - as prior
    knowledge available to every strategy, not as a default.
    """
'''
    return src[:doc_start] + new_doc + src[doc_end:]


def main() -> int:
    text = SOURCE.read_text()
    fns = extract(text)
    missing = [
        n for n in SHARED_QC + SHARED_INGESTION + S1_PRIVATE if n not in fns
    ]
    if missing:
        raise SystemExit(f"symbols not found in {SOURCE}: {missing}")

    shared = HERE / "shared"
    shared.mkdir(parents=True, exist_ok=True)

    ingestion_header = '''"""Section ingestion — SHARED CONTROL (ADR-0011 section 4).

Every strategy reads the generator's sections through this module, so the
comparison measures meshing methods rather than section readers. Migrated
byte-for-byte from `04_strategy_prototypes/stage02_common.py` except for the
chordwise defaults stripped out of `feature_split_sides` per ADR-0011 section 4.1.

Do not add a blocking, distribution or tip-closure decision here. Those are
per-strategy.
"""

from __future__ import annotations

import numpy as np

from aeris.mesh.surface import (  # noqa: F401 - re-exported for strategies
    MeshBuildError,
    SurfaceBlock,
    _block_qc,
    _map_sides_to_wing,
    _open_trailing_edge,
    _resample_piecewise,
    _resample_polyline,
    _smooth_patch_interior,
    _split_counts,
    _tfi_patch,
    _write_npz,
    _write_plot3d_formatted,
)

Array = np.ndarray


'''
    parts = [ingestion_header, fns["section_loop_2d"], "\n\n", strip_s1_chordwise_defaults(fns["feature_split_sides"])]
    (shared / "ingestion.py").write_text("".join(parts))

    qc_header = '''"""QC metric definitions, orientation and artifact writing — SHARED CONTROL.

ADR-0011 section 4: QC metric *definitions*, gate thresholds, and the verifier are
shared so that a comparison between strategies is a comparison between meshing
methods and not between quality metrics. **Migrated unchanged** from
`04_strategy_prototypes/stage02_common.py`, so every number recorded in `status`
remains directly comparable.

`winslow_smooth_2d` is a generic operator and is shared under ADR-0011 section 4.1;
using it is a per-strategy decision. COMMON_BRIEF section 1 records that it made
S1's Stage 02 tip cap **worse** (-0.0363 -> -0.0499), which is a measurement about
that cap, not about the operator.
"""

from __future__ import annotations

import numpy as np

from .ingestion import Array, SurfaceBlock, _block_qc, _write_npz, _write_plot3d_formatted


'''
    body = []
    for name in SHARED_QC:
        body.append(fns[name])
        body.append("\n\n")
    (shared / "qc.py").write_text(qc_header + "".join(body).rstrip("\n") + "\n")

    s1 = HERE / "S1_tip_first"
    s1.mkdir(parents=True, exist_ok=True)
    s1_header = '''"""S1's private construction — tip closure and spanwise distribution.

ADR-0011 section 4.1 moved these out of the Stage 02 shared module. They are S1's
blocking decisions, not infrastructure: `butterfly_from_ring` is a tip closure,
`oml_tip_ring_2d` is tip staging, `realise_spanwise_law` and
`geometric_progression_counts` are a spanwise distribution law, and
`butterfly_cap_2d` / `camber_and_thickness` / `map_2d_patch_to_tip` are S1 cap
internals. Under the independence line no other strategy may import from this file.

Migrated byte-for-byte from `04_strategy_prototypes/stage02_common.py`. Docstrings
still describe the Stage 02 development history, including `butterfly_cap_2d`,
which is a **recorded negative result** kept for provenance and is not on S1's
working path.

NOTE for the S1 study: this file is the Stage 02 implementation. ADR-0011 requires
S1 to be re-implemented from scratch like every other strategy. Treat this as the
prior art to read and beat, not as the S1 entry.
"""

from __future__ import annotations

import numpy as np

from shared.ingestion import (
    Array,
    MeshBuildError,
    _map_sides_to_wing,
    _resample_piecewise,
    _resample_polyline,
    _smooth_patch_interior,
    _split_counts,
    _tfi_patch,
)
from shared.qc import orient_patches_2d


'''
    body = []
    for name in S1_PRIVATE:
        body.append(fns[name])
        body.append("\n\n")
    (s1 / "s1_stage02_prior_art.py").write_text(s1_header + "".join(body).rstrip("\n") + "\n")

    print(f"shared/ingestion.py      {len(SHARED_INGESTION)} symbols (1 edited)")
    print(f"shared/qc.py             {len(SHARED_QC)} symbols, unchanged")
    print(f"S1_tip_first/s1_stage02_prior_art.py  {len(S1_PRIVATE)} symbols, unchanged")
    moved = set(SHARED_QC) | set(SHARED_INGESTION) | set(S1_PRIVATE)
    left = sorted(set(fns) - moved)
    print(f"not migrated (private Stage 02 helpers): {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./README.md =====

# 04 — Six independent strategy studies

Authority: **ADR-0011**, `00_governance/decisions/ADR-0011-independent-strategy-studies.md`.
Prior knowledge for all six: **`COMMON_BRIEF.md`** — read it before implementing.

## The objective

One structured meshing method that runs unattended, robustly, across the production
design space. Not a well-documented catalogue of failures. If a strategy is close to
passing, finish it.

**Success:** a strategy that passes every hard gate on all ten geometries of
`round_c_lhs10_seed42` at its own calibrated settings, with laws that extend it to
the full DSE.

## Why this replaced `04_strategy_prototypes/`

Stage 02 ran the six strategies as variants of a shared implementation. The tip
closure was built once and inherited by all of them, so S3, S4 and S5 converged on
S1's cap and scored identically — S4 was bit-identical to S1 to `0.000e+00` on all
ten geometries. **The tournament compared one topology wearing four labels.**

Here, each strategy is implemented from scratch in its own folder, developed to the
best state it can reach, and only then compared on metrics frozen in advance.

`04_strategy_prototypes/` is retained **unchanged as the archived Stage 02 record**.
Nothing here imports from it.

## Layout

```
COMMON_BRIEF.md            Stage 02 lessons, given to all six up front
migrate_from_stage02.py    provenance record of the ADR-0011 section 4.1 migration
shared/                    the experimental control — see shared/__init__.py
  ingestion.py             section reading, 2D->3D mapping   (no chordwise defaults)
  qc.py                    QC metric DEFINITIONS, orientation, artifacts
  gates.py                 thresholds and the frozen checklists
  geometry_sets.py         locked sets; the hold-out is guarded
  pyhyp_runner.py          the pyHyp invocation; prepare / collect
  verify.py                the verifier, with all six instrument bugs fixed
  export_paraview.py       VTK with per-cell quality
S0_cap4/  S1_tip_first/  S2_cross_field/
S3_station_sweep/  S4_analytic_multiblock/  S5_frozen_rbf/
    <implementation>       written from scratch, per strategy
    STUDY.md               the log: paper-vs-invented, attempts, results, ledger
    artifacts/             this strategy's outputs
```

## The independence line, in one sentence

Geometry is generated the same way for every strategy; **how each turns it into
blocks is the experiment.** Blocking, tip closure, spanwise and chordwise laws,
smoothing and staging are per-strategy. Ingestion, QC definitions, thresholds, the
pyHyp invocation, the geometry sets and the verifier are shared.

If a strategy genuinely cannot work within that line, record it as a finding and
raise it. Do not resolve it by copying code across the line.

## Order and pace

**S0, S1, S2, S3, S4, S5** — declared in advance so it cannot be reordered after
seeing results. S2's feasibility question is resolved early, in parallel with S0.

**The user decides when a strategy is done.** No budget is declared in advance;
Claude Code reports state and waits. No strategy is started and none is frozen
without an explicit user signal. Because effort is not capped, it is **measured** —
each `STUDY.md` carries an effort ledger, mirrored into `status`, and reported
alongside results in every comparison table.

## Geometry sets

| set | role |
|---|---|
| `lhs100_seed42` | development and refinement — baseline, then a subset, then widen |
| `round_c_lhs10_seed42` | **HOLD-OUT. Untouched. No tuning, ever.** Run once, after freeze. |
| `epse_calibration_lhs10_seed7` | Stage 01/02 evidence basis; permitted only for a declared like-for-like comparison |

Robustness is ranked on the hold-out, never on the refinement set — otherwise the
top-ranked criterion becomes a proxy for effort.

## Usage

```python
import sys
from pathlib import Path
STUDIES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STUDIES.parents[1] / "src"))
sys.path.insert(0, str(STUDIES))

from shared import geometry_sets, gates, pyhyp_runner, verify
from shared.ingestion import section_loop_2d, feature_split_sides
from shared.qc import qc_blocks, orient_blocks_consistently
```

Heavy compute is prepared, never launched in-session: `pyhyp_runner.prepare` writes
the run inputs and returns the commands; the user launches them;
`pyhyp_runner.collect` reads them back and applies the frozen checklist.


===== FILE: ./RUN_LOG/README.md =====

# Run reports

Compact per-campaign summaries written by `../run_report.py`, kept in git because
the artifact trees they are drawn from get wiped between campaigns.

One Markdown and one JSON per run. Generate them on whichever machine runs the
campaign, push, and pull them back to read.


===== FILE: ./RUN_LOG/s7_solver_tuning_matrix.md =====

# S7 solver tuning matrix

2026-08-25 | SU2 8.5.0 Harrier, RANS-SA | 42,745 cells, `half_wing_symmetry_y0` | 6000 iterations | tier `laptop_diagnostic`, campaign claims forbidden

Ten solver configurations on one mesh, every variant carrying multigrid and adding
one thing on top.  `CONV_RESIDUAL_MINVAL` was set to -12.0 for the matrix,
below the acceptance bar, so each variant could reach whatever it was capable of
rather than halting on the gate itself.

Gates: drop >= 6.0 orders AND final <= -8.0, plus the force tail.

| variant | added to multigrid | wall s | drop | final rms | min at iter | monotonic | gates |
|---|---|---|---|---|---|---|---|
| `I_combined` | NK + ILU/25 + CFL 25 | 4802 | 6.906 | -9.508 | 5999 | yes | **pass** |
| `J_nk_no_mg` | NK + ILU/25 + CFL 25, no multigrid | 5067 | 6.906 | -9.508 | 5999 | yes | **pass** |
| `G_nk_cfl` | NK + CFL 25 | 4158 | 6.363 | -8.966 | 5999 | yes | **pass** |
| `F_nk_linear` | NK + ILU/25 | 4569 | 6.265 | -8.868 | 5999 | yes | **pass** |
| `B_newton_krylov` | NK alone | 4671 | 5.954 | -8.556 | 5999 | yes | fail by 0.046 |
| `D_high_cfl` | CFL 25 | 3142 | 1.798 | -4.401 | 927 | no | fail |
| `C_strong_linear` | ILU/25 | 3708 | 1.465 | -4.068 | 953 | no | fail |
| `A_baseline` | nothing | 2913 | 1.082 | -3.685 | 3604 | no | fail |
| `E_quasi_newton` | QUASI_NEWTON_NUM_SAMPLES | 2976 | 1.082 | -3.685 | 3604 | no | fail |
| `H_linear_cfl` | ILU/25 + CFL 25 | 4440 | 1.036 | -3.639 | 5961 | no | fail |

All ten ran the full 6 000 iterations; none stopped early.

## Forces

| variant | CL | CD | CMy | accepted |
|---|---|---|---|---|
| `I_combined` | 0.018883 | 0.087040 | -0.006617 | yes |
| `J_nk_no_mg` | 0.018883 | 0.087040 | -0.006617 | yes |
| `G_nk_cfl` | 0.018883 | 0.087040 | -0.006617 | yes |
| `F_nk_linear` | 0.018883 | 0.087040 | -0.006617 | yes |
| `B_newton_krylov` | 0.018882 | 0.087041 | -0.006617 | no |
| `D_high_cfl` | 0.019238 | 0.086840 | -0.006937 | no |
| `C_strong_linear` | 0.018811 | 0.087093 | -0.006777 | no |
| `A_baseline` | 0.019888 | 0.087070 | -0.007543 | no |
| `E_quasi_newton` | 0.019888 | 0.087070 | -0.007543 | no |
| `H_linear_cfl` | 0.019429 | 0.087381 | -0.006912 | no |

The four accepted variants agree on all three coefficients to within 5e-7 no
matter how the solver reached them.  The five rejected ones spread 5.54 % in CL,
0.62 % in CD and 10.74 % in CMy.  The gate separates exactly what it was written
to separate.

## Conclusions

1. **Newton-Krylov is the discriminating ingredient.**  Every variant carrying it
   is monotonic and still descending at the iteration cap; every variant without
   it limit-cycles, and none exceeds 3.02 orders of best drop.
2. **Necessary but not sufficient**: alone it reaches 5.954 orders and misses the
   gate by 0.046.  It needs the stronger linear solve or the higher CFL to clear
   six orders within 6 000 iterations; both together are fastest.
3. **The accelerators are coupled, not additive.**  CFL 25 is the worst variant
   without Newton-Krylov (`D_high_cfl`, 2.041 best drop) and the second best with
   it (`G_nk_cfl`, 6.363).
4. `QUASI_NEWTON_NUM_SAMPLES` is a **no-op**: `A_baseline` and `E_quasi_newton`
   differ by that one line and their 6 000-row histories are byte-identical.
5. Multigrid is **bypassed** under `NEWTON_KRYLOV`: `I_combined` and `J_nk_no_mg`
   differ by seven `MG*` options and their histories are byte-identical.
6. SU2 8.5.0 **never logs** Newton-Krylov activation - "Newton" and "Krylov"
   appear zero times in a run with `NEWTON_KRYLOV= YES`.  Only the residual
   history shows whether it took effect.

## Scope

This selects a solver configuration at 42 745 cells on a laptop.  It does **not**
establish convergence at production resolution: the coarse level is 1.55 M cells
and the matrix must be repeated there before any convergence claim.
`round_c_lhs10_seed42` was not touched.

The matrix also exposed a defect in the residual gate itself - the solver was
being stopped at the acceptance bar, capping the achievable drop at 5.42 orders
against a gate asking 6.0.  See the 2026-08-25 residual-gate amendment in
ADR-0017 and defect 11 in `STUDY.md`.


===== FILE: ./run_report.py =====

"""Summarise a campaign run into a small file that belongs in git.

The artifact trees are large and are wiped between campaigns, so a run that is
only recorded there is a run nobody can evaluate later.  This reads the
`case_result.json` files a campaign leaves behind and writes a compact Markdown
and JSON pair into `RUN_LOG/`, small enough to commit and pull back on another
machine.

    python run_report.py <artifacts_root> --name s7_stage0_multigrid
    python run_report.py <artifacts_root> --name s7_stage1 --push

`--push` commits and pushes the report only; it never touches the artifacts.
Safe to re-run while a campaign is still going: it reports whatever has landed so
far, which is what makes it usable as a live progress check.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RUN_LOG = HERE / "RUN_LOG"


def _dig(payload: Any, *path: str, default: Any = None) -> Any:
    """Follow a key path, returning default rather than raising on any miss."""
    current = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _collect(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("case_result.json")):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            rows.append({"case_id": str(path.parent.name), "unreadable": str(exc)})
            continue
        rows.append(
            {
                "case_id": result.get("case_id"),
                "index": result.get("development_index"),
                "level": result.get("grid_level"),
                "scope": result.get("acceptance_scope"),
                "accepted": result.get("accepted"),
                "cells": _dig(result, "cell_counts", "volume_cells"),
                "attempts": len(_dig(result, "gate_results", "mesh_attempts", default=[]) or []),
                "cl": _dig(result, "forces", "cl"),
                "cd": _dig(result, "forces", "cd"),
                "cmy": _dig(result, "forces", "cmy"),
                "y_plus_p95": _dig(result, "gate_results", "cfd", "y_plus_p95"),
                "y_plus_max": _dig(result, "gate_results", "cfd", "y_plus_max"),
                "residual_drop": _dig(result, "gate_results", "cfd", "orders_dropped"),
                "rss_bytes": _dig(result, "peak_memory", "rss_bytes"),
                "wall_s": result.get("wall_seconds"),
                "failure_reasons": result.get("failure_reasons") or [],
            }
        )
    return rows


def _fmt(value: Any, spec: str = "") -> str:
    if value is None:
        return "-"
    if spec and isinstance(value, (int, float)):
        return format(value, spec)
    return str(value)


def _render(rows: list[dict[str, Any]], name: str, root: Path) -> str:
    good = [r for r in rows if r.get("accepted")]
    bad = [r for r in rows if r.get("accepted") is False]
    lines = [
        f"# Run report: {name}",
        "",
        f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')} from `{root}`.",
        "",
        f"**{len(good)} accepted / {len(rows)} cases**"
        + (f", {len(bad)} failed" if bad else "")
        + ".",
        "",
    ]

    finished = [r for r in rows if r.get("residual_drop") is not None]
    if finished:
        drops = [r["residual_drop"] for r in finished]
        lines += [
            f"Residual drop over {len(finished)} solved cases: "
            f"min {min(drops):.3f}, median {statistics.median(drops):.3f}, "
            f"max {max(drops):.3f} orders.",
            "",
        ]

    cds = [r["cd"] for r in rows if isinstance(r.get("cd"), (int, float))]
    if len(cds) > 1:
        lines += [f"CD across {len(cds)} cases: {min(cds):.6f} to {max(cds):.6f}.", ""]

    lines += [
        "| case | lvl | ok | cells | att | y+ p95 | y+ max | drop | CL | CD | Cm |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                r.get("case_id", "?"),
                _fmt(r.get("level")),
                "yes" if r.get("accepted") else "NO",
                _fmt(r.get("cells"), ",d") if r.get("cells") else "-",
                _fmt(r.get("attempts")),
                _fmt(r.get("y_plus_p95"), ".4f"),
                _fmt(r.get("y_plus_max"), ".4f"),
                _fmt(r.get("residual_drop"), ".3f"),
                _fmt(r.get("cl"), ".5f"),
                _fmt(r.get("cd"), ".5f"),
                _fmt(r.get("cmy"), ".5f"),
            )
        )

    if bad:
        lines += ["", "## Failures", ""]
        for r in bad:
            reasons = ", ".join(r["failure_reasons"]) or "no reason recorded"
            lines.append(f"- `{r.get('case_id')}`: {reasons}")

    lines += [
        "",
        "## How to read this",
        "",
        "`ok` is the declared technical scope passing, not campaign readiness.",
        "`drop` is orders of residual reduction; the policy gate is six.",
        "A case still running simply has not written its result yet and is absent.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="campaign artifacts root to scan")
    parser.add_argument("--name", required=True, help="short label, becomes the filename")
    parser.add_argument("--push", action="store_true", help="commit and push the report")
    args = parser.parse_args()

    if not args.root.exists():
        print(f"no such path: {args.root}")
        return 1

    rows = _collect(args.root)
    if not rows:
        print(f"no case_result.json found under {args.root}")
        return 1

    RUN_LOG.mkdir(parents=True, exist_ok=True)
    md = RUN_LOG / f"{args.name}.md"
    js = RUN_LOG / f"{args.name}.json"
    md.write_text(_render(rows, args.name, args.root), encoding="utf-8")
    js.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    accepted = sum(1 for r in rows if r.get("accepted"))
    print(f"{accepted}/{len(rows)} accepted -> {md}")

    if args.push:
        message = f"Run report: {args.name} ({accepted}/{len(rows)} accepted)"
        for command in (
            ["git", "add", str(md), str(js)],
            ["git", "commit", "-q", "-m", message],
            ["git", "push"],
        ):
            done = subprocess.run(command, capture_output=True, text=True)
            if done.returncode != 0 and "nothing to commit" not in done.stdout:
                print("git step failed:", " ".join(command), done.stderr.strip())
                return 1
        print("pushed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./S6_bounded_mesh_atlas/atlas.py =====

"""Deterministic parameter-space atlas selection for S6."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

Array = np.ndarray


HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from shared.geometry_sets import _config, design_matrix, geometry_id  # noqa: E402

ATLAS_SCHEMA = "aeris.mesh.s6_bounded_atlas.v2"
MESH_DISTANCE_EXCLUDED = frozenset({"elevon_start_frac", "elevon_end_frac", "elevon_hinge_frac"})


def _range_pair(value: Any, *, sweep: bool = False) -> tuple[float, float]:
    low, high = float(value.min), float(value.max)
    return (-high, -low) if sweep else (low, high)


def design_bounds() -> tuple[list[str], Array, Array]:
    """Return active design names and their exact canonical bounds."""
    config = _config()
    names = config.active_design_variable_names()
    lows: list[float] = []
    highs: list[float] = []
    for name in names:
        if hasattr(config.planform_bounds, name):
            pair = _range_pair(
                getattr(config.planform_bounds, name),
                sweep=name.startswith("sw") and name.endswith("_deg"),
            )
        elif hasattr(config.section_bounds, name):
            pair = _range_pair(getattr(config.section_bounds, name))
        elif config.elevon_bounds is not None and hasattr(config.elevon_bounds, name):
            pair = _range_pair(getattr(config.elevon_bounds, name))
        else:
            raise KeyError(f"no canonical bounds found for active variable {name!r}")
        lows.append(pair[0])
        highs.append(pair[1])
    return names, np.asarray(lows), np.asarray(highs)


def mesh_distance_variable_names() -> list[str]:
    names, low, high = design_bounds()
    return [
        name
        for name, lo, hi in zip(names, low, high, strict=True)
        if hi > lo and name not in MESH_DISTANCE_EXCLUDED
    ]


def normalize_matrix(matrix: Array, names: Iterable[str]) -> Array:
    """Normalize the OML-active variables used for mesh-template distance."""
    expected, low, high = design_bounds()
    names = list(names)
    if names != expected:
        raise ValueError(f"design columns differ from canonical order: {names} != {expected}")
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape[-1] != len(expected):
        raise ValueError(f"design matrix has {matrix.shape[-1]} columns; expected {len(expected)}")
    if not np.all(np.isfinite(matrix)):
        raise ValueError("design matrix contains non-finite values")
    span = high - low
    varying = span > 0.0
    metric = np.asarray(
        [
            is_varying and name not in MESH_DISTANCE_EXCLUDED
            for name, is_varying in zip(names, varying, strict=True)
        ]
    )
    if not np.any(metric):
        raise ValueError("the S6 design space has no varying design variables")
    tolerance = 1.0e-10
    normalized_varying = (matrix[..., varying] - low[varying]) / span[varying]
    if np.any(normalized_varying < -tolerance) or np.any(normalized_varying > 1.0 + tolerance):
        raise ValueError("design matrix contains values outside the canonical bounds")
    fixed_tolerance = tolerance * np.maximum(1.0, np.abs(low[~varying]))
    if np.any(np.abs(matrix[..., ~varying] - low[~varying]) > fixed_tolerance):
        raise ValueError("design matrix changes a fixed canonical variable")
    normalized = (matrix[..., metric] - low[metric]) / span[metric]
    return np.clip(normalized, 0.0, 1.0)


def rms_distance(left: Array, right: Array) -> Array:
    """Root-mean-square distance per design variable."""
    delta = np.asarray(left) - np.asarray(right)
    return np.linalg.norm(delta, axis=-1) / math.sqrt(delta.shape[-1])


def farthest_point_indices(points: Array, count: int) -> list[int]:
    """Deterministic maximin template selection, seeded nearest the cube center."""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or not len(points):
        raise ValueError("points must be a non-empty (n, d) matrix")
    if not 1 <= count <= len(points):
        raise ValueError(f"template count must be within [1, {len(points)}]")
    center = np.full(points.shape[1], 0.5)
    first = int(np.argmin(rms_distance(points, center)))
    selected = [first]
    nearest = rms_distance(points, points[first])
    while len(selected) < count:
        nearest[np.asarray(selected)] = -1.0
        candidate = int(np.argmax(nearest))
        selected.append(candidate)
        nearest = np.minimum(nearest, rms_distance(points, points[candidate]))
    return selected


def build_atlas_manifest(
    *,
    set_name: str = "lhs100_seed42",
    template_count: int = 16,
    trust_radius_rms: float = 0.25,
) -> dict[str, Any]:
    """Select templates and assign every development geometry to its nearest one."""
    matrix, names = design_matrix(set_name)
    normalized = normalize_matrix(matrix, names)
    templates = farthest_point_indices(normalized, template_count)
    return build_manifest_for_indices(
        set_name=set_name,
        template_indices=templates,
        trust_radius_rms=trust_radius_rms,
        template_selection=("deterministic farthest-point maximin from cube-center seed"),
    )


def build_manifest_for_indices(
    *,
    set_name: str,
    template_indices: Iterable[int],
    trust_radius_rms: float,
    template_selection: str,
    enrichment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete atlas manifest from an explicit ordered template set."""
    matrix, names = design_matrix(set_name)
    normalized = normalize_matrix(matrix, names)
    metric_names = mesh_distance_variable_names()
    templates = [int(index) for index in template_indices]
    if not templates or len(templates) != len(set(templates)):
        raise ValueError("template indices must be non-empty and unique")
    if any(index < 0 or index >= len(normalized) for index in templates):
        raise ValueError("template indices must address the development set")
    template_points = normalized[templates]
    distances = np.stack([rms_distance(normalized, point) for point in template_points], axis=1)
    assignment = np.argmin(distances, axis=1)
    nearest = distances[np.arange(len(normalized)), assignment]

    rows = []
    for index in range(len(normalized)):
        slot = int(assignment[index])
        rows.append(
            {
                "geometry_index": index,
                "geometry_id": geometry_id(set_name, index),
                "template_slot": slot,
                "template_index": int(templates[slot]),
                "template_geometry_id": geometry_id(set_name, int(templates[slot])),
                "distance_rms": float(nearest[index]),
                "inside_trust_radius": bool(nearest[index] <= trust_radius_rms),
            }
        )

    manifest = {
        "schema": ATLAS_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "set_name": set_name,
        "design_variables": names,
        "distance_variables": metric_names,
        "distance": "euclidean distance divided by sqrt(number of active variables)",
        "template_selection": template_selection,
        "template_count": len(templates),
        "template_indices": templates,
        "template_geometry_ids": [geometry_id(set_name, index) for index in templates],
        "trust_radius_rms": trust_radius_rms,
        "coverage": {
            "geometries": len(normalized),
            "inside_radius": int(np.count_nonzero(nearest <= trust_radius_rms)),
            "fraction_inside_radius": float(np.mean(nearest <= trust_radius_rms)),
            "max_nearest_distance_rms": float(nearest.max()),
            "mean_nearest_distance_rms": float(nearest.mean()),
            "p95_nearest_distance_rms": float(np.quantile(nearest, 0.95)),
        },
        "assignments": rows,
    }
    if enrichment is not None:
        manifest["quality_enrichment"] = enrichment
    return manifest


def qualify_atlas_seeds(
    manifest: dict[str, Any],
    seed_report: dict[str, Any],
    *,
    production_floor: float = 0.10,
    minimum_templates: int,
) -> dict[str, Any]:
    """Prune failed production seeds without claiming atlas validation."""
    if manifest.get("schema") != ATLAS_SCHEMA:
        raise ValueError("atlas manifest schema is not current")
    if seed_report.get("schema") != "aeris.mesh.s6_seed_build.v1":
        raise ValueError("seed report schema is not current")
    if seed_report.get("level") != "production":
        raise ValueError("only a production seed report can qualify atlas seeds")
    if not 0.0 < production_floor <= 1.0:
        raise ValueError("production floor must be within (0, 1]")

    source = [int(index) for index in manifest["template_indices"]]
    reported = [int(index) for index in seed_report.get("indices", [])]
    if reported != source:
        raise ValueError("seed report was not produced from this atlas")
    rows = seed_report.get("rows", [])
    row_indices = [int(row["geometry_index"]) for row in rows]
    if row_indices != source or len(row_indices) != len(set(row_indices)):
        raise ValueError("seed report does not contain the complete ordered atlas")
    if int(seed_report.get("attempted", -1)) != len(source):
        raise ValueError("seed report attempted count is incomplete")
    if not 1 <= minimum_templates <= len(source):
        raise ValueError("minimum templates must be within the source atlas size")

    qualified: list[int] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        index = int(row["geometry_index"])
        audit = row.get("audit", {})
        quality = audit.get("quality", {})
        minimum = quality.get("min_scaled_quality")
        minimum_value = float(minimum) if minimum is not None else None
        reasons = list(audit.get("failure_reasons", []))
        valid = bool(
            row.get("state") == "PASS"
            and audit.get("state") == "PASS"
            and not reasons
            and minimum_value is not None
            and math.isfinite(minimum_value)
            and minimum_value >= production_floor
            and int(quality.get("inverted_cells", -1)) == 0
            and float(quality.get("min_volume", -1.0)) > 0.0
        )
        if valid:
            qualified.append(index)
            continue
        march_quality = audit.get("march_result", {}).get("march_metrics", {}).get("min_quality")
        rejected.append(
            {
                "geometry_index": index,
                "geometry_id": row.get("geometry_id"),
                "state": row.get("state"),
                "failure_reasons": reasons,
                "independent_min_scaled_quality": minimum_value,
                "pyhyp_min_quality": (float(march_quality) if march_quality is not None else None),
                "inverted_cells": quality.get("inverted_cells"),
            }
        )

    if len(qualified) < minimum_templates:
        raise ValueError(
            f"only {len(qualified)} production seeds qualify; minimum is {minimum_templates}"
        )
    qualification = {
        "method": "complete production seed report qualification",
        "volume_level": "production",
        "normal_points": seed_report.get("normal_points"),
        "eps_e": seed_report.get("eps_e"),
        "first_cell_fraction_characteristic": seed_report.get("first_cell_fraction_characteristic"),
        "wall_spacing_source": seed_report.get("wall_spacing_source"),
        "production_floor": production_floor,
        "source_template_indices": source,
        "qualified_indices": qualified,
        "qualified_seed_evidence": [
            {
                "geometry_index": int(row["geometry_index"]),
                "geometry_id": row.get("geometry_id"),
                "independent_min_scaled_quality": float(
                    row["audit"]["quality"]["min_scaled_quality"]
                ),
                "inverted_cells": int(row["audit"]["quality"]["inverted_cells"]),
                "cgns_sha256": row["audit"].get("cgns_sha256"),
                "surface_npz_sha256": row["audit"].get("surface_npz_sha256"),
            }
            for row in rows
            if int(row["geometry_index"]) in qualified
        ],
        "rejected": rejected,
        "requires_complete_development_revalidation": True,
        "freeze_ready": False,
    }
    result = build_manifest_for_indices(
        set_name=str(manifest["set_name"]),
        template_indices=qualified,
        trust_radius_rms=float(manifest["trust_radius_rms"]),
        template_selection=(
            "deterministic maximin pruned by complete production seed qualification"
        ),
    )
    if "quality_enrichment" in manifest:
        result["prior_quality_enrichment"] = manifest["quality_enrichment"]
    result["seed_qualification"] = qualification
    return result


def enrich_atlas_manifest(
    manifest: dict[str, Any],
    development_report: dict[str, Any],
    *,
    warning_quality: float = 0.15,
    maximum_attempts: int = 5,
    maximum_templates: int = 32,
    required_freeze_level: str = "production",
) -> dict[str, Any]:
    """Add deterministic seed cases for weak development-set atlas routes."""
    if manifest.get("schema") != ATLAS_SCHEMA:
        raise ValueError("atlas manifest schema is not current")
    if development_report.get("set_name") != manifest.get("set_name"):
        raise ValueError("development report and atlas use different geometry sets")
    if warning_quality <= 0.0 or maximum_attempts < 1:
        raise ValueError("quality and attempt thresholds must be positive")
    validation_level = development_report.get("volume_level")
    allowed_levels = {"smoke", "fine", "production"}
    if validation_level not in allowed_levels:
        raise ValueError("development report has no supported volume level")
    if required_freeze_level != "production":
        raise ValueError("S6 atlas freeze is permanently pinned to production")

    original = [int(index) for index in manifest["template_indices"]]
    if maximum_templates < len(original):
        raise ValueError("maximum templates is below the current atlas size")
    report_templates = [int(index) for index in development_report.get("template_indices", [])]
    if report_templates != original:
        raise ValueError("development report was not produced with this atlas")
    if int(development_report.get("candidate_count", 0)) < len(original):
        raise ValueError("development report did not try the complete atlas when needed")
    if float(development_report.get("preferred_quality", 0.0)) < warning_quality:
        raise ValueError("development routing quality target is below the warning quality")
    rows = development_report.get("rows", [])
    row_indices = [int(row["geometry_index"]) for row in rows]
    expected_indices = [int(row["geometry_index"]) for row in manifest["assignments"]]
    if len(row_indices) != len(set(row_indices)) or set(row_indices) != set(expected_indices):
        raise ValueError("development report does not cover the complete development set")

    candidates: list[dict[str, Any]] = []
    accepted_existing_warnings: list[dict[str, Any]] = []
    unresolved_existing: list[dict[str, Any]] = []
    seed_rejections = {
        int(row["geometry_index"]): row
        for row in manifest.get("seed_qualification", {}).get("rejected", [])
    }
    accepted_unbuildable_warnings: list[dict[str, Any]] = []
    unresolved_unbuildable: list[dict[str, Any]] = []
    for row in rows:
        index = int(row["geometry_index"])
        attempts = len(row.get("attempts", []))
        quality = row.get("accepted_min_scaled_quality")
        quality_value = float(quality) if quality is not None else None
        failed = row.get("state") != "PASS"
        weak_quality = (
            quality_value is None
            or not math.isfinite(quality_value)
            or quality_value < warning_quality
        )
        slow_route = attempts > maximum_attempts
        if not (failed or weak_quality or slow_route):
            continue
        candidate = {
            "geometry_index": index,
            "state": row.get("state"),
            "accepted_min_scaled_quality": quality_value,
            "attempt_count": attempts,
            "reasons": [
                reason
                for reason, active in (
                    ("no_accepted_template", failed),
                    ("quality_below_warning", weak_quality),
                    ("too_many_template_attempts", slow_route),
                )
                if active
            ],
        }
        if index in original:
            identity_considered = any(
                attempt.get("template_index") == index for attempt in row.get("attempts", [])
            )
            candidate["identity_fallback_considered"] = identity_considered
            candidate["all_templates_considered"] = attempts >= len(original)
            if failed or not identity_considered or (weak_quality and attempts < len(original)):
                unresolved_existing.append(candidate)
            else:
                accepted_existing_warnings.append(candidate)
        elif index in seed_rejections:
            candidate["seed_qualification_rejection"] = seed_rejections[index]
            candidate["all_templates_considered"] = attempts >= len(original)
            if failed or (weak_quality and attempts < len(original)):
                unresolved_unbuildable.append(candidate)
            else:
                accepted_unbuildable_warnings.append(candidate)
        else:
            candidates.append(candidate)

    def priority(row: dict[str, Any]) -> tuple[float, float, int, int]:
        quality = row["accepted_min_scaled_quality"]
        finite_quality = float(quality) if quality is not None and math.isfinite(quality) else -1.0
        return (
            0.0 if row["state"] != "PASS" else 1.0,
            finite_quality,
            -int(row["attempt_count"]),
            int(row["geometry_index"]),
        )

    candidates.sort(key=priority)
    capacity = maximum_templates - len(original)
    selected_candidates = candidates[:capacity]
    additions = [int(row["geometry_index"]) for row in selected_candidates]
    quality_ready = not candidates and not unresolved_existing and not unresolved_unbuildable
    enrichment = {
        "method": "development weak-case deterministic enrichment",
        "warning_quality": warning_quality,
        "maximum_attempts": maximum_attempts,
        "maximum_templates": maximum_templates,
        "validation_level": validation_level,
        "required_freeze_level": required_freeze_level,
        "source_template_indices": original,
        "candidate_count": len(candidates),
        "added_indices": additions,
        "selected_candidates": selected_candidates,
        "omitted_due_to_capacity": candidates[capacity:],
        "accepted_existing_template_warnings": accepted_existing_warnings,
        "unresolved_existing_template_cases": unresolved_existing,
        "known_unbuildable_seed_indices": sorted(seed_rejections),
        "accepted_known_unbuildable_warnings": accepted_unbuildable_warnings,
        "unresolved_known_unbuildable_cases": unresolved_unbuildable,
        "requires_revalidation": bool(additions),
        "quality_enrichment_complete": quality_ready,
        "requires_production_validation": bool(quality_ready and validation_level != "production"),
        "freeze_ready": bool(quality_ready and validation_level == "production"),
    }
    result = build_manifest_for_indices(
        set_name=str(manifest["set_name"]),
        template_indices=[*original, *additions],
        trust_radius_rms=float(manifest["trust_radius_rms"]),
        template_selection=(
            "initial deterministic maximin plus deterministic development weak-case enrichment"
        ),
        enrichment=enrichment,
    )
    for key in ("seed_qualification", "prior_quality_enrichment"):
        if key in manifest:
            result[key] = manifest[key]
    return result


def write_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def default(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if is_dataclass(value):
            return asdict(value)
        raise TypeError(type(value).__name__)

    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=default) + "\n",
        encoding="utf-8",
    )
    return path


===== FILE: ./S6_bounded_mesh_atlas/audit_validation.py =====

#!/usr/bin/env python3
"""Independently check a completed S6 development-validation report."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

REPORT_SCHEMA = "aeris.mesh.s6_atlas_development_validation.v2"
AUDIT_SCHEMA = "aeris.mesh.s6_atlas_development_report_audit.v2"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def audit_report(report_path: Path, *, expected_count: int | None = None) -> dict[str, Any]:
    """Check report invariants and return a compact, reproducible summary."""
    report_path = Path(report_path).resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    require(report.get("schema") == REPORT_SCHEMA, "unexpected report schema")
    require(
        report.get("campaign_equivalent_written_cgns_audit") is True,
        "written-CGNS audit flag is not true",
    )
    rows = report.get("rows")
    require(isinstance(rows, list), "rows must be a list")
    rows = rows if isinstance(rows, list) else []
    indices = [row.get("geometry_index") for row in rows]
    declared_indices = report.get("geometry_indices", [])
    require(indices == declared_indices, "row indices differ from declared geometry indices")
    require(len(indices) == len(set(indices)), "geometry indices are not unique")
    if expected_count is not None:
        require(len(rows) == expected_count, f"expected {expected_count} rows, found {len(rows)}")
    require(report.get("attempted") == len(rows), "attempted count does not match rows")

    template_indices = set(report.get("template_indices", []))
    candidate_count = int(report.get("candidate_count", 0))
    preferred_quality = float(report.get("preferred_quality", 0.15))
    selected_qualities: list[float] = []
    selected_wall_errors: list[float] = []
    selected_interface_errors: list[float] = []
    selected_fidelity_errors: list[float] = []
    selected_first_layer_min: list[float] = []
    selected_first_layer_p95: list[float] = []
    attempt_state_counts: Counter[str] = Counter()
    selected_template_counts: Counter[int] = Counter()
    preferred_misses: list[int] = []
    total_attempts = 0
    first_try = 0
    total_cells = 0
    cells_below_0_10 = 0
    cells_below_0_15 = 0
    minimum_volume: float | None = None
    identity_target_count = 0
    selected_identity_count = 0

    for row_number, row in enumerate(rows):
        label = f"row {row_number} geometry {row.get('geometry_index')}"
        attempts = row.get("attempts")
        if not isinstance(attempts, list):
            errors.append(f"{label}: attempts must be a list")
            attempts = []
        total_attempts += len(attempts)
        first_try += int(row.get("state") == "PASS" and len(attempts) == 1)
        require(
            candidate_count <= 0 or len(attempts) <= candidate_count,
            f"{label}: attempts exceed candidate_count",
        )
        attempt_state_counts.update(str(item.get("state")) for item in attempts)
        selected = [item for item in attempts if item.get("selected") is True]

        if row.get("state") != "PASS":
            require(not selected, f"{label}: failed row has a selected attempt")
            require(
                row.get("accepted_template_index") is None,
                f"{label}: failed row has an accepted template",
            )
            continue

        require(len(selected) == 1, f"{label}: PASS row must have exactly one selected attempt")
        if len(selected) != 1:
            continue
        attempt = selected[0]
        require(attempt.get("state") == "PASS", f"{label}: selected attempt is not PASS")
        template_index = attempt.get("template_index")
        require(template_index in template_indices, f"{label}: selected template is not in atlas")
        require(
            row.get("accepted_template_index") == template_index,
            f"{label}: accepted template differs from selected attempt",
        )

        quality = attempt.get("min_scaled_quality")
        require(_finite(quality), f"{label}: accepted quality is not finite")
        if _finite(quality):
            quality = float(quality)
            selected_qualities.append(quality)
            require(quality >= 0.10, f"{label}: accepted quality is below 0.10")
            require(
                math.isclose(
                    float(row.get("accepted_min_scaled_quality", float("nan"))),
                    quality,
                    rel_tol=0.0,
                    abs_tol=1.0e-14,
                ),
                f"{label}: row quality differs from selected attempt",
            )
            if quality < preferred_quality:
                preferred_misses.append(int(row["geometry_index"]))

        independent = attempt.get("independent_written_acceptance", {})
        require(
            independent.get("production_floor_passed") is True,
            f"{label}: independent written audit did not pass production floor",
        )
        require(
            independent.get("hard_gate_passed") is True,
            f"{label}: independent written hard gates did not pass",
        )
        independent_quality = independent.get("quality", {}).get("min_scaled_quality")
        require(
            _finite(independent_quality)
            and _finite(quality)
            and math.isclose(
                float(independent_quality),
                float(quality),
                rel_tol=0.0,
                abs_tol=1.0e-14,
            ),
            f"{label}: selected and independent written quality differ",
        )
        written_quality = independent.get("quality", {})
        require(written_quality.get("inverted_cells") == 0, f"{label}: inverted cells remain")
        volume = written_quality.get("min_volume")
        require(_finite(volume) and float(volume) > 0.0, f"{label}: minimum volume is not positive")
        if _finite(volume):
            minimum_volume = (
                float(volume) if minimum_volume is None else min(minimum_volume, float(volume))
            )
        row_total_cells = written_quality.get("total_cells")
        row_below_0_10 = written_quality.get("cells_below_0_10")
        row_below_0_15 = written_quality.get("cells_below_0_15")
        require(
            isinstance(row_total_cells, int) and row_total_cells > 0,
            f"{label}: total cell count is missing or invalid",
        )
        require(row_below_0_10 == 0, f"{label}: cells exist below the hard 0.10 floor")
        require(
            isinstance(row_below_0_15, int) and row_below_0_15 >= 0,
            f"{label}: cells-below-0.15 count is missing or invalid",
        )
        if isinstance(row_total_cells, int):
            total_cells += row_total_cells
        if isinstance(row_below_0_10, int):
            cells_below_0_10 += row_below_0_10
        if isinstance(row_below_0_15, int):
            cells_below_0_15 += row_below_0_15

        fidelity = attempt.get("surface_fidelity", {})
        require(fidelity.get("passed") is True, f"{label}: surface fidelity did not pass")
        fidelity_error = fidelity.get("max_fraction_of_local_chord")
        require(_finite(fidelity_error), f"{label}: surface fidelity value is not finite")
        if _finite(fidelity_error):
            selected_fidelity_errors.append(float(fidelity_error))

        wall_error = attempt.get("wall_error_m")
        interface_error = attempt.get("interface_max_mismatch_m")
        require(_finite(wall_error), f"{label}: wall error is not finite")
        require(_finite(interface_error), f"{label}: interface error is not finite")
        if _finite(wall_error):
            selected_wall_errors.append(float(wall_error))
            require(float(wall_error) <= 1.0e-10, f"{label}: wall error exceeds tolerance")
        if _finite(interface_error):
            selected_interface_errors.append(float(interface_error))
            require(
                float(interface_error) <= 1.0e-10,
                f"{label}: interface mismatch exceeds tolerance",
            )
        require(
            isinstance(attempt.get("interface_pair_count"), int)
            and attempt["interface_pair_count"] > 0,
            f"{label}: interface pair count is missing or invalid",
        )

        spacing = attempt.get("first_layer_spacing", {}).get("deformed", {})
        require(spacing.get("nonfinite_count") == 0, f"{label}: nonfinite first-layer spacing")
        require(spacing.get("nonpositive_count") == 0, f"{label}: nonpositive first-layer spacing")
        for key, values in (
            ("min_fraction_characteristic", selected_first_layer_min),
            ("p95_fraction_characteristic", selected_first_layer_p95),
        ):
            value = spacing.get(key)
            require(_finite(value), f"{label}: {key} is not finite")
            if _finite(value):
                values.append(float(value))

        accepted_hash = row.get("accepted_cgns_sha256")
        require(
            accepted_hash == attempt.get("candidate_cgns_sha256"),
            f"{label}: accepted CGNS hash differs from selected attempt",
        )
        candidate_path = Path(str(row.get("accepted_cgns", "")))
        retained = row.get("accepted_cgns_retained") is True
        if retained:
            require(candidate_path.is_file(), f"{label}: retained CGNS is missing")
            if candidate_path.is_file():
                require(
                    _sha256(candidate_path) == accepted_hash,
                    f"{label}: retained CGNS hash mismatch",
                )
        else:
            require(not candidate_path.exists(), f"{label}: pruned CGNS still exists")
        if isinstance(template_index, int):
            selected_template_counts[template_index] += 1
        identity_target_count += int(row.get("is_atlas_template_target") is True)
        selected_identity_count += int(row.get("selected_identity_deformation") is True)

    passed = sum(row.get("state") == "PASS" for row in rows)
    require(report.get("passed") == passed, "passed count does not match rows")
    expected_fraction = passed / len(rows) if rows else 0.0
    require(
        _finite(report.get("pass_fraction"))
        and math.isclose(float(report["pass_fraction"]), expected_fraction, abs_tol=1.0e-15),
        "pass fraction does not match rows",
    )
    if selected_qualities:
        require(
            math.isclose(
                float(report.get("worst_min_scaled_quality", float("nan"))),
                min(selected_qualities),
                rel_tol=0.0,
                abs_tol=1.0e-14,
            ),
            "reported worst quality does not match selected attempts",
        )

    quality_array = np.asarray(selected_qualities, dtype=float)
    summary = {
        "attempted": len(rows),
        "passed": passed,
        "first_try_passes": first_try,
        "total_template_attempts": total_attempts,
        "maximum_attempts_for_one_target": max(
            (len(row.get("attempts", [])) for row in rows), default=0
        ),
        "preferred_quality_miss_indices": preferred_misses,
        "identity_target_count": identity_target_count,
        "selected_identity_deformation_count": selected_identity_count,
        "attempt_state_counts": dict(sorted(attempt_state_counts.items())),
        "selected_template_counts": {
            str(key): value for key, value in sorted(selected_template_counts.items())
        },
        "quality": {
            "minimum": float(np.min(quality_array)) if quality_array.size else None,
            "p05": float(np.quantile(quality_array, 0.05)) if quality_array.size else None,
            "median": float(np.median(quality_array)) if quality_array.size else None,
            "mean": float(np.mean(quality_array)) if quality_array.size else None,
            "maximum": float(np.max(quality_array)) if quality_array.size else None,
            "minimum_volume": minimum_volume,
            "total_cells_across_selected_meshes": total_cells,
            "cells_below_0_10_across_selected_meshes": cells_below_0_10,
            "cells_below_0_15_across_selected_meshes": cells_below_0_15,
        },
        "maximum_wall_error_m": max(selected_wall_errors, default=None),
        "maximum_interface_mismatch_m": max(selected_interface_errors, default=None),
        "maximum_surface_fidelity_fraction_local_chord": max(
            selected_fidelity_errors, default=None
        ),
        "first_layer_fraction_characteristic": {
            "minimum_over_selected_meshes": min(selected_first_layer_min, default=None),
            "maximum_p95_over_selected_meshes": max(selected_first_layer_p95, default=None),
        },
    }
    integrity_passed = not errors
    all_targets_passed = bool(rows) and passed == len(rows)
    return {
        "schema": AUDIT_SCHEMA,
        "source_report": str(report_path),
        "source_report_sha256": _sha256(report_path),
        "passed": integrity_passed and all_targets_passed,
        "report_integrity_passed": integrity_passed,
        "all_targets_passed": all_targets_passed,
        "errors": errors,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    audit = audit_report(args.report, expected_count=args.expected_count)
    rendered = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if audit["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./S6_bounded_mesh_atlas/build_seeds.py =====

#!/usr/bin/env python3
"""Build and audit the maximin S1 seed volumes used by the S6 atlas."""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (HERE, REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from atlas import farthest_point_indices, normalize_matrix  # noqa: E402
from campaign import _run_with_timeout, indices_from_atlas_manifest  # noqa: E402
from deform import WALL_TOLERANCE_M, sha256, volume_interface_report  # noqa: E402
from resolution import epsilon_tag, first_cell_fraction  # noqa: E402
from S1_tip_first import strategy_s1  # noqa: E402
from shared.gates import EPSE_LADDER  # noqa: E402
from shared.geometry_sets import design_matrix, geometry_id, wing  # noqa: E402
from shared.pyhyp_runner import prepare, read_result  # noqa: E402
from shared.volume_qc import volume_report  # noqa: E402

from aeris.cfd.meshing.pyhyp_extrude import mach_aero_python  # noqa: E402
from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS  # noqa: E402
from aeris.cfd.meshing.volume_audit import read_volume_blocks  # noqa: E402

SCHEMA = "aeris.mesh.s6_seed_build.v1"
PRODUCTION_FLOOR = 0.10
ALLOWED_LEVELS = ("smoke", "fine", "production")


def _default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_default) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def selected_indices(template_count: int) -> list[int]:
    matrix, names = design_matrix("lhs100_seed42")
    return farthest_point_indices(normalize_matrix(matrix, names), template_count)


def _audit_run(run_dir: Path) -> dict[str, Any]:
    try:
        result = read_result(run_dir) or {}
    except Exception as error:
        return {
            "state": "FAIL",
            "failure_reasons": ["invalid_march_result"],
            "error_type": type(error).__name__,
            "error": str(error),
        }
    cgns = run_dir / "wing_vol.cgns"
    surface = run_dir / "surface_blocks.npz"
    if not cgns.is_file() or not surface.is_file():
        return {
            "state": "FAIL",
            "failure_reasons": ["missing_volume_or_surface"],
            "march_result": result,
        }

    try:
        volume = read_volume_blocks(cgns)
        quality = volume_report(volume)
        interfaces = volume_interface_report(volume)
    except Exception as error:
        return {
            "state": "FAIL",
            "failure_reasons": ["volume_audit_error"],
            "error_type": type(error).__name__,
            "error": str(error),
            "march_result": result,
        }
    reasons: list[str] = []
    if not result.get("march_completed", False):
        reasons.append("march_not_completed")
    if quality.get("inverted_cells") != 0:
        reasons.append("inverted_cells")
    if float(quality.get("min_volume", -1.0)) <= 0.0:
        reasons.append("nonpositive_volume")
    if float(quality.get("min_scaled_quality", -1.0)) < PRODUCTION_FLOOR:
        reasons.append("quality_below_production_floor")
    if interfaces["paired_face_count"] != 20:
        reasons.append("unexpected_interface_count")
    if interfaces["max_mismatch_m"] > WALL_TOLERANCE_M:
        reasons.append("nonconformal_interfaces")
    report = {
        "state": "PASS" if not reasons else "FAIL",
        "failure_reasons": reasons,
        "march_result": result,
        "cgns": str(cgns.resolve()),
        "cgns_sha256": sha256(cgns),
        "surface_npz": str(surface.resolve()),
        "surface_npz_sha256": sha256(surface),
        "quality": quality,
        "interfaces": interfaces,
    }
    del volume
    gc.collect()
    return report


def build(
    *,
    output: Path,
    level: str,
    indices: list[int],
    timeout_s: float,
    report_stem: str = "seed_build",
    eps_e: float = 2.0,
    first_cell_fraction_override: float | None = None,
) -> dict[str, Any]:
    if level not in ALLOWED_LEVELS:
        raise ValueError(f"unsupported seed level {level!r}")
    eps_tag = epsilon_tag(eps_e)
    policy_fraction = first_cell_fraction(level)
    selected_fraction = (
        policy_fraction
        if first_cell_fraction_override is None
        else float(first_cell_fraction_override)
    )
    if not np.isfinite(selected_fraction) or selected_fraction <= 0.0:
        raise ValueError("first-cell fraction must be finite and positive")
    if not indices or len(indices) != len(set(indices)):
        raise ValueError("seed indices must be non-empty and unique")
    if (
        not report_stem
        or Path(report_stem).name != report_stem
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
            for character in report_stem
        )
    ):
        raise ValueError("report stem must be a simple file-name component")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / f"{report_stem}_checkpoint.json"
    rows: list[dict[str, Any]] = []
    started = time.monotonic()

    for sequence, index in enumerate(indices, start=1):
        gid = geometry_id("lhs100_seed42", index)
        run_dir = output / gid / eps_tag
        case_started = time.monotonic()
        existing = _audit_run(run_dir) if run_dir.is_dir() else {"state": "MISSING"}
        returncode: int | None = None
        resumed = existing.get("state") == "PASS"
        if resumed:
            audit = existing
        else:
            try:
                geometry = wing("lhs100_seed42", index)
                blocks, _surface_info = strategy_s1.build_surface(geometry, level="L2_smoke")
                prepared = prepare(
                    strategy_id=strategy_s1.STRATEGY_ID,
                    geometry_id=gid,
                    blocks=blocks,
                    out_dir=output,
                    level=level,
                    epse_ladder=(eps_e,),
                    s0_fraction_override=selected_fraction,
                )
                run_dir = Path(prepared["runs"][0]["dir"]).resolve()
                runner = Path(prepared["runs"][0]["runner"]).resolve()
                returncode = _run_with_timeout(
                    [str(mach_aero_python()), str(runner)],
                    run_dir,
                    run_dir / "run_stdout.log",
                    timeout_s,
                )
                audit = _audit_run(run_dir)
            except Exception as error:
                audit = {
                    "state": "FAIL",
                    "failure_reasons": ["seed_build_error"],
                    "error_type": type(error).__name__,
                    "error": str(error),
                }

        row = {
            "sequence": sequence,
            "geometry_index": index,
            "geometry_id": gid,
            "level": level,
            "eps_e": eps_e,
            "normal_points": int(GRID_LEVELS[level]["N"]),
            "first_cell_fraction_characteristic": selected_fraction,
            "state": audit["state"],
            "resumed": resumed,
            "return_code": returncode,
            "elapsed_s": time.monotonic() - case_started,
            "audit": audit,
        }
        rows.append(row)
        _write_json(
            checkpoint_path,
            {
                "schema": SCHEMA,
                "level": level,
                "eps_e": eps_e,
                "first_cell_fraction_characteristic": selected_fraction,
                "indices": indices,
                "rows": rows,
            },
        )
        print(
            f"{sequence:03d}/{len(indices):03d} {gid} {row['state']} resumed={resumed}",
            flush=True,
        )

    passed = sum(row["state"] == "PASS" for row in rows)
    report = {
        "schema": SCHEMA,
        "level": level,
        "eps_e": eps_e,
        "normal_points": int(GRID_LEVELS[level]["N"]),
        "first_cell_fraction_characteristic": selected_fraction,
        "wall_spacing_source": (
            "policy" if first_cell_fraction_override is None else "explicit_calibration"
        ),
        "indices": indices,
        "attempted": len(rows),
        "passed": passed,
        "pass_fraction": passed / len(rows),
        "elapsed_s": time.monotonic() - started,
        "rows": rows,
    }
    _write_json(output / f"{report_stem}_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--level", choices=ALLOWED_LEVELS, required=True)
    parser.add_argument("--template-count", type=int, default=16)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--indices", type=int, nargs="+")
    selection.add_argument("--atlas-manifest", type=Path)
    parser.add_argument("--timeout-s", type=float, default=3600.0)
    parser.add_argument("--eps-e", type=float, choices=EPSE_LADDER, default=2.0)
    parser.add_argument("--first-cell-fraction", type=float)
    parser.add_argument("--report-stem", default="seed_build")
    args = parser.parse_args()
    indices = (
        indices_from_atlas_manifest(args.atlas_manifest)
        if args.atlas_manifest
        else args.indices or selected_indices(args.template_count)
    )
    report = build(
        output=args.output,
        level=args.level,
        indices=indices,
        timeout_s=args.timeout_s,
        report_stem=args.report_stem,
        eps_e=args.eps_e,
        first_cell_fraction_override=args.first_cell_fraction,
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "level",
                    "eps_e",
                    "first_cell_fraction_characteristic",
                    "indices",
                    "attempted",
                    "passed",
                    "elapsed_s",
                )
            },
            indent=2,
        )
    )
    return 0 if report["passed"] == report["attempted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./S6_bounded_mesh_atlas/campaign.py =====

#!/usr/bin/env python3
"""Resumable mesh-and-CFD campaign runner for S6."""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import math
import os
import signal
import socket
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (HERE, REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from atlas import (  # noqa: E402
    ATLAS_SCHEMA,
    MESH_DISTANCE_EXCLUDED,
    mesh_distance_variable_names,
    normalize_matrix,
    rms_distance,
)
from cfd_qc import wall_yplus_summary  # noqa: E402
from deform import (  # noqa: E402
    DEFORMATION_SCHEMA,
    WALL_TOLERANCE_M,
    acceptance_report,
    deform_volume_blocks,
    load_surface_blocks,
    sha256,
    validate_template_correspondence,
    volume_interface_report,
    write_volume_blocks,
    written_deformation_metadata,
)
from resolution import epsilon_tag  # noqa: E402
from S1_tip_first import strategy_s1  # noqa: E402
from shared.gates import EPSE_LADDER  # noqa: E402
from shared.geometry_sets import _config, design_matrix  # noqa: E402
from shared.pyhyp_runner import prepare, read_result  # noqa: E402
from shared.qc import write_surface_artifacts  # noqa: E402
from shared.volume_qc import volume_report  # noqa: E402
from strategy_s6 import STRATEGY_ID, build_surface  # noqa: E402

from aeris.cfd.case.spec import FlowConditions, SolveSpec  # noqa: E402
from aeris.cfd.meshing.pyhyp_extrude import mach_aero_python  # noqa: E402
from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS  # noqa: E402
from aeris.cfd.meshing.volume_audit import read_volume_blocks  # noqa: E402
from aeris.cfd.solvers.adflow.parse import parse_force_history  # noqa: E402
from aeris.cfd.solvers.base import get_solver_adapter  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample  # noqa: E402
from aeris.geometry.registry import get_geometry_generator  # noqa: E402

MANIFEST_SCHEMA = "aeris.mesh.s6_campaign_manifest.v2"
DEVELOPMENT_REPORT_SCHEMA = "aeris.mesh.s6_atlas_development_validation.v2"
HPC_PILOT_SCHEMA = "aeris.mesh.s6_hpc_pilot_package.v1"
REGISTRY_SCHEMA = "aeris.mesh.s6_template_registry.v8"
LEGACY_REGISTRY_SCHEMAS = frozenset({"aeris.mesh.s6_template_registry.v7"})
MESH_REPORT_SCHEMA = "aeris.mesh.s6_campaign_mesh.v2"
CFD_REPORT_SCHEMA = "aeris.mesh.s6_campaign_cfd_acceptance.v2"
DESIGN_REPORT_SCHEMA = "aeris.mesh.s6_design_run.v3"
DEFAULT_S1_ROOT = (
    REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies" / "S1_tip_first/L2_smoke/smoke"
)
ATLAS_VOLUME_LEVELS = ("smoke", "fine", "production")
LOCK_STALE_AFTER_S = 24.0 * 60.0 * 60.0
NK_SUBSPACE_SIZE = 20
PREFERRED_MIN_SCALED_QUALITY = 0.15
REGISTRY_ASSET_KEYS = (
    ("cgns", "cgns_sha256"),
    ("surface_npz", "surface_npz_sha256"),
    ("pyhyp_options", "pyhyp_options_sha256"),
)


class RegistryIntegrityError(RuntimeError):
    """A frozen template asset is missing or differs from its registry hash."""


def _combined_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted({Path(path).resolve() for path in paths}):
        if not path.is_file():
            raise FileNotFoundError(path)
        try:
            label = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            label = str(path)
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _mesh_implementation_paths() -> list[Path]:
    generator = REPO_ROOT / "src/aeris/generators/bwb_segmented_v1"
    mesh_core = REPO_ROOT / "src/aeris/mesh"
    meshing = REPO_ROOT / "src/aeris/cfd/meshing"
    sampling = REPO_ROOT / "src/aeris/dataset/sampling"
    shared = STUDIES / "shared"
    return [
        HERE / "campaign.py",
        HERE / "deform.py",
        HERE / "resolution.py",
        HERE / "strategy_s6.py",
        STUDIES / "S1_tip_first/strategy_s1.py",
        shared / "gates.py",
        shared / "geometry_sets.py",
        shared / "ingestion.py",
        shared / "pyhyp_runner.py",
        shared / "qc.py",
        shared / "volume_qc.py",
        REPO_ROOT / "configs/geometry/bwb.yaml",
        REPO_ROOT / "src/aeris/geometry/registry.py",
        *meshing.glob("*.py"),
        *mesh_core.glob("*.py"),
        *sampling.rglob("*.py"),
        *generator.glob("*.py"),
    ]


def _mesh_implementation_sha256() -> str:
    return _combined_sha256(_mesh_implementation_paths())


def _solver_implementation_sha256() -> str:
    adflow = REPO_ROOT / "src/aeris/cfd/solvers/adflow"
    return _combined_sha256(
        [
            HERE / "campaign.py",
            HERE / "cfd_qc.py",
            REPO_ROOT / "src/aeris/cfd/case/spec.py",
            REPO_ROOT / "src/aeris/cfd/solvers/base.py",
            REPO_ROOT / "src/aeris/cfd/presets/data/adflow_rans_ank_nk_v1.yaml",
            *adflow.glob("*.py"),
        ]
    )


def _default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_default) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _portable_repo_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_registry_asset_path(registry: dict[str, Any], registry_path: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    base = registry.get("asset_path_base")
    if base == "repository_root":
        root = REPO_ROOT.resolve()
    elif base == "registry_directory":
        root = Path(registry_path).resolve().parent
    else:
        raise RegistryIntegrityError(
            f"registry has relative asset path {value!r} without a supported path base"
        )
    return (root / candidate).resolve()


def _materialize_registry_assets(registry: dict[str, Any], registry_path: Path) -> dict[str, Any]:
    schema = registry.get("schema")
    if schema != REGISTRY_SCHEMA and schema not in LEGACY_REGISTRY_SCHEMAS:
        raise ValueError("not an S6 template registry")
    if schema == REGISTRY_SCHEMA and registry.get("asset_path_base") != "repository_root":
        raise RegistryIntegrityError("current registry must use repository_root asset paths")
    for template in registry.get("templates", []):
        for path_key, hash_key in REGISTRY_ASSET_KEYS:
            if path_key not in template or hash_key not in template:
                raise RegistryIntegrityError(
                    f"template {template.get('template_id')} lacks {path_key} provenance"
                )
            resolved = _resolve_registry_asset_path(registry, registry_path, template[path_key])
            if not resolved.is_file():
                raise RegistryIntegrityError(f"missing registry asset: {resolved}")
            template[path_key] = str(resolved)
    return registry


def _verify_template_assets(template: dict[str, Any]) -> None:
    for path_key, hash_key in REGISTRY_ASSET_KEYS:
        if path_key not in template and hash_key not in template:
            continue
        path = Path(template.get(path_key, ""))
        expected = template.get(hash_key)
        if not path.is_file() or not expected:
            raise RegistryIntegrityError(
                f"template {template.get('template_id')} has incomplete {path_key} provenance"
            )
        actual = sha256(path)
        if actual != expected:
            raise RegistryIntegrityError(
                f"template {template.get('template_id')} {path_key} hash mismatch"
            )


def verify_registry(registry_path: Path) -> dict[str, Any]:
    registry_path = Path(registry_path).resolve()
    registry = _materialize_registry_assets(_read_json(registry_path), registry_path)
    verified: list[dict[str, Any]] = []
    for template in registry["templates"]:
        _verify_template_assets(template)
        verified.append(
            {
                "template_id": template["template_id"],
                "geometry_index": int(template["geometry_index"]),
                "assets_verified": len(REGISTRY_ASSET_KEYS),
            }
        )
    return {
        "schema": "aeris.mesh.s6_template_registry_audit.v1",
        "passed": True,
        "registry": str(registry_path),
        "registry_sha256": sha256(registry_path),
        "template_count": len(verified),
        "templates": verified,
    }


def _safe_id(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in value)
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"unsafe empty identifier derived from {value!r}")
    return cleaned


def _process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _remove_stale_lock(path: Path, *, stale_after_s: float) -> bool:
    try:
        original_stat = path.stat()
    except FileNotFoundError:
        return True
    except OSError:
        return False

    try:
        fields = dict(
            token.split("=", 1)
            for token in path.read_text(encoding="utf-8").split()
            if "=" in token
        )
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        fields = {}

    stale = False
    if fields.get("host") == socket.gethostname() and fields.get("pid"):
        try:
            owner_alive = _process_is_alive(int(fields["pid"]))
        except ValueError:
            pass
        else:
            if owner_alive:
                return False
            stale = True
    if not stale:
        try:
            started = float(fields.get("started", original_stat.st_mtime))
        except ValueError:
            started = original_stat.st_mtime
        stale = time.time() - started > stale_after_s
    if not stale:
        return False

    try:
        current_stat = path.stat()
        if (current_stat.st_dev, current_stat.st_ino) != (
            original_stat.st_dev,
            original_stat.st_ino,
        ):
            return False
        path.unlink()
    except FileNotFoundError:
        pass
    return True


@contextmanager
def _case_lock(
    path: Path,
    *,
    wait_s: float = 7200.0,
    stale_after_s: float = LOCK_STALE_AFTER_S,
) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_s
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError as error:
            if _remove_stale_lock(path, stale_after_s=stale_after_s):
                continue
            if time.monotonic() >= deadline:
                raise RuntimeError(f"timed out waiting for case lock: {path}") from error
            time.sleep(2.0)
        else:
            break
    try:
        os.write(
            descriptor,
            (f"pid={os.getpid()} host={socket.gethostname()} started={time.time()}\n").encode(),
        )
        yield
    finally:
        os.close(descriptor)
        path.unlink(missing_ok=True)


def _existing_accepted_mesh(
    report_path: Path,
    *,
    manifest_sha256: str,
    registry_sha256: str,
    implementation_sha256: str,
) -> dict[str, Any] | None:
    if not report_path.is_file():
        return None
    existing = _read_json(report_path)
    accepted = existing.get("accepted_mesh") or {}
    mesh_path = Path(accepted.get("cgns", ""))
    expected = accepted.get("cgns_sha256")
    if (
        existing.get("schema") == MESH_REPORT_SCHEMA
        and existing.get("state") == "MESH_ACCEPTED"
        and existing.get("manifest_sha256") == manifest_sha256
        and existing.get("registry_sha256") == registry_sha256
        and existing.get("mesh_implementation_sha256") == implementation_sha256
        and mesh_path.is_file()
        and expected == sha256(mesh_path)
    ):
        return existing
    return None


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _finite(value: str | float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def sample_designs(*, count: int, seed: int, output: Path) -> dict[str, Any]:
    if count < 1:
        raise ValueError("count must be positive")
    from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix

    config = _config()
    names = config.active_design_variable_names()
    matrix = build_lhs_design_matrix(config, count, np.random.default_rng(seed))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["design_id", *names])
        for index, row in enumerate(matrix):
            writer.writerow(
                [f"lhs{count}_seed{seed}_{index:05d}", *(float(value) for value in row)]
            )
    temporary.replace(output)
    return {
        "designs_csv": str(output.resolve()),
        "designs_csv_sha256": sha256(output),
        "count": count,
        "seed": seed,
        "design_variables": names,
    }


def make_manifest(designs_csv: Path, flows_csv: Path, output: Path) -> dict[str, Any]:
    config = _config()
    names = config.active_design_variable_names()
    design_rows = _csv_rows(designs_csv)
    flow_rows = _csv_rows(flows_csv)
    if not design_rows or not flow_rows:
        raise ValueError("design and flow CSV files must both contain rows")

    design_records: list[tuple[str, dict[str, float]]] = []
    seen_designs: set[str] = set()
    for index, row in enumerate(design_rows):
        design_id = _safe_id(row.get("design_id") or f"design_{index:05d}")
        if design_id in seen_designs:
            raise ValueError(f"duplicate design_id {design_id!r}")
        missing = [name for name in names if row.get(name, "") == ""]
        if missing:
            raise ValueError(f"{design_id}: missing design variables {missing}")
        values = {name: _finite(row[name], f"{design_id}.{name}") for name in names}
        design_records.append((design_id, values))
        seen_designs.add(design_id)

    normalized_designs = normalize_matrix(
        np.asarray(
            [[values[name] for name in names] for _design_id, values in design_records],
            dtype=float,
        ),
        names,
    )
    designs = [
        {
            "design_id": design_id,
            "values": values,
            "normalized_design": normalized,
        }
        for (design_id, values), normalized in zip(design_records, normalized_designs, strict=True)
    ]

    flows: list[dict[str, Any]] = []
    seen_flows: set[str] = set()
    for index, row in enumerate(flow_rows):
        flow_id = _safe_id(row.get("flow_id") or f"flow_{index:05d}")
        if flow_id in seen_flows:
            raise ValueError(f"duplicate flow_id {flow_id!r}")
        flow = {
            "alpha": _finite(row.get("alpha", 2.0), f"{flow_id}.alpha"),
            "mach": _finite(row.get("mach", 0.2), f"{flow_id}.mach"),
            "reynolds": _finite(row.get("reynolds", 1.0e6), f"{flow_id}.reynolds"),
            "temperature": _finite(row.get("temperature", 288.15), f"{flow_id}.temperature"),
        }
        if flow["mach"] < 0.0 or flow["reynolds"] <= 0.0 or flow["temperature"] <= 0.0:
            raise ValueError(f"{flow_id}: invalid flow state {flow}")
        flows.append({"flow_id": flow_id, **flow})
        seen_flows.add(flow_id)

    cases = [
        {
            "case_index": len(flows) * design_index + flow_index,
            "case_id": _safe_id(f"{design['design_id']}__{flow['flow_id']}"),
            "design_id": design["design_id"],
            "flow_id": flow["flow_id"],
        }
        for design_index, design in enumerate(designs)
        for flow_index, flow in enumerate(flows)
    ]
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "strategy_id": STRATEGY_ID,
        "design_variables": names,
        "mesh_distance_excluded_variables": sorted(MESH_DISTANCE_EXCLUDED),
        "mesh_distance_variables": mesh_distance_variable_names(),
        "input_hashes": {
            "designs_csv": sha256(designs_csv),
            "flows_csv": sha256(flows_csv),
        },
        "counts": {
            "designs": len(designs),
            "flows": len(flows),
            "cases": len(cases),
        },
        "designs": designs,
        "flows": flows,
        "cases": cases,
    }
    _write_json(output, manifest)
    return manifest


def prepare_hpc_pilot(
    *,
    development_report_path: Path,
    atlas_manifest_path: Path,
    registry_path: Path,
    flows_path: Path,
    output: Path,
    count: int = 10,
    required_indices: tuple[int, ...] = (7, 89, 95),
) -> dict[str, Any]:
    """Package representative development cases without touching the hold-out."""
    if count < len(required_indices) or count > 100:
        raise ValueError("pilot count must include every required index and be at most 100")
    if len(required_indices) != len(set(required_indices)):
        raise ValueError("required pilot indices must be unique")

    development_report_path = Path(development_report_path).resolve()
    atlas_manifest_path = Path(atlas_manifest_path).resolve()
    registry_path = Path(registry_path).resolve()
    flows_path = Path(flows_path).resolve()
    output = Path(output).resolve()
    report = _read_json(development_report_path)
    atlas_manifest = _read_json(atlas_manifest_path)
    registry = _read_json(registry_path)

    if report.get("schema") != DEVELOPMENT_REPORT_SCHEMA:
        raise ValueError("pilot requires the current S6 development report")
    if report.get("set_name") != "lhs100_seed42" or report.get("volume_level") != "production":
        raise ValueError("pilot requires the production lhs100_seed42 development report")
    if report.get("attempted") != 100 or report.get("passed") != 100:
        raise ValueError("pilot requires a complete 100/100 development report")
    if atlas_manifest.get("schema") != ATLAS_SCHEMA:
        raise ValueError("pilot requires the current S6 atlas manifest")
    enrichment = atlas_manifest.get("quality_enrichment") or {}
    if not enrichment.get("freeze_ready") or enrichment.get("requires_revalidation"):
        raise ValueError("pilot requires a production-validated frozen-candidate atlas")
    report_provenance = enrichment.get("development_report") or {}
    if report_provenance.get("sha256") != sha256(development_report_path):
        raise ValueError("atlas manifest is not bound to the supplied development report")
    if registry.get("schema") != REGISTRY_SCHEMA:
        raise ValueError("pilot requires the current portable registry schema")
    registry_atlas = registry.get("atlas_manifest") or {}
    if registry_atlas.get("sha256") != sha256(atlas_manifest_path):
        raise ValueError("registry is not bound to the supplied atlas manifest")
    registry_audit = verify_registry(registry_path)

    matrix, names = design_matrix("lhs100_seed42")
    normalized = normalize_matrix(matrix, names)
    center = np.full(normalized.shape[1], 0.5)
    center_distance = rms_distance(normalized, center)
    rows = {int(row["geometry_index"]): row for row in report["rows"]}
    assignments = {int(row["geometry_index"]): row for row in atlas_manifest["assignments"]}
    expected = set(range(len(matrix)))
    if set(rows) != expected or set(assignments) != expected:
        raise ValueError("development report or atlas assignments are incomplete")
    if any(row.get("state") != "PASS" for row in rows.values()):
        raise ValueError("pilot selection cannot include a failed development row")

    selected: list[dict[str, Any]] = []
    selected_indices: set[int] = set()

    def take(candidates: list[int], reason: str, limit: int) -> None:
        added = 0
        for index in candidates:
            if len(selected) >= count or added >= limit:
                break
            if index in selected_indices:
                continue
            row = rows[index]
            assignment = assignments[index]
            selected.append(
                {
                    "pilot_index": len(selected),
                    "geometry_index": index,
                    "geometry_id": row["geometry_id"],
                    "selection_reason": reason,
                    "accepted_min_scaled_quality": float(row["accepted_min_scaled_quality"]),
                    "attempt_count": len(row["attempts"]),
                    "accepted_template_index": int(row["accepted_template_index"]),
                    "selected_identity_deformation": bool(row["selected_identity_deformation"]),
                    "center_distance_rms": float(center_distance[index]),
                    "nearest_atlas_distance_rms": float(assignment["distance_rms"]),
                }
            )
            selected_indices.add(index)
            added += 1

    regression_reasons = {
        7: "known_unbuildable_seed_alternate_route",
        89: "prior_16_template_hard_failure_regression",
        95: "final_preferred_quality_miss_and_long_route",
    }
    for index in required_indices:
        if index not in rows:
            raise ValueError(f"required pilot geometry {index} is absent")
        take([index], regression_reasons.get(index, "required_regression"), 1)

    quality_order = sorted(
        rows,
        key=lambda index: (float(rows[index]["accepted_min_scaled_quality"]), index),
    )
    routing_order = sorted(
        rows,
        key=lambda index: (
            -len(rows[index]["attempts"]),
            float(rows[index]["accepted_min_scaled_quality"]),
            index,
        ),
    )
    extreme_order = sorted(rows, key=lambda index: (-float(center_distance[index]), index))
    atlas_distance_order = sorted(
        rows,
        key=lambda index: (-float(assignments[index]["distance_rms"]), index),
    )
    easy_order = sorted(
        (
            index
            for index in rows
            if len(rows[index]["attempts"]) == 1
            and float(rows[index]["accepted_min_scaled_quality"])
            >= float(report["preferred_quality"])
        ),
        key=lambda index: (float(center_distance[index]), index),
    )
    take(quality_order, "lowest_accepted_quality", 2)
    take(routing_order, "largest_template_search", 1)
    take(extreme_order, "design_space_extreme", 2)
    take(atlas_distance_order, "largest_nearest_atlas_distance", 1)
    take(easy_order, "central_first_try_control", 1)
    take(sorted(rows), "deterministic_fill", count)
    if len(selected) != count:
        raise RuntimeError(f"selected {len(selected)} pilot geometries; expected {count}")

    output.mkdir(parents=True, exist_ok=True)
    designs_path = output / "designs.csv"
    temporary_designs = designs_path.with_name(f".{designs_path.name}.{os.getpid()}.tmp")
    with temporary_designs.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["design_id", *names])
        for entry in selected:
            index = entry["geometry_index"]
            writer.writerow([entry["geometry_id"], *(float(value) for value in matrix[index])])
    temporary_designs.replace(designs_path)

    packaged_flows = output / "flows.csv"
    temporary_flows = packaged_flows.with_name(f".{packaged_flows.name}.{os.getpid()}.tmp")
    temporary_flows.write_bytes(flows_path.read_bytes())
    temporary_flows.replace(packaged_flows)
    manifest_path = output / "manifest.json"
    manifest = make_manifest(designs_path, packaged_flows, manifest_path)

    registry_relative = _portable_repo_path(registry_path)
    package_relative = _portable_repo_path(output)
    if Path(registry_relative).is_absolute() or Path(package_relative).is_absolute():
        raise ValueError("HPC pilot registry and package must be inside the repository")
    submit_path = output / "verify_and_submit.sh"
    submit_text = f'''#!/usr/bin/env bash
set -euo pipefail
: "${{S6_REPO_ROOT:?Set S6_REPO_ROOT to the copied repository root}}"
cd "$S6_REPO_ROOT"
PYTHON="${{S6_PYTHON:-$S6_REPO_ROOT/.venv/bin/python}}"
RUNNER="AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py"
"$PYTHON" "$RUNNER" verify-registry \\
  --registry "{registry_relative}" \\
  --output "{package_relative}/registry_audit_on_hpc.json"
export S6_MANIFEST="$S6_REPO_ROOT/{package_relative}/manifest.json"
export S6_REGISTRY="$S6_REPO_ROOT/{registry_relative}"
export S6_CAMPAIGN_ROOT="${{S6_CAMPAIGN_ROOT:-$S6_REPO_ROOT/{package_relative}/runs}}"
export S6_KEEP_ACCEPTED_MESH=1
export S6_RETAIN_SURFACE_SOLUTION=1
sbatch --array=0-{count - 1}%2 \\
  AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/slurm_run_design_array.sh
'''
    temporary_submit = submit_path.with_name(f".{submit_path.name}.{os.getpid()}.tmp")
    temporary_submit.write_text(submit_text, encoding="utf-8")
    temporary_submit.chmod(0o755)
    temporary_submit.replace(submit_path)

    package = {
        "schema": HPC_PILOT_SCHEMA,
        "source_set": "lhs100_seed42",
        "holdout_accessed": False,
        "input_hashes": {
            "development_report": sha256(development_report_path),
            "atlas_manifest": sha256(atlas_manifest_path),
            "registry": sha256(registry_path),
            "flows": sha256(packaged_flows),
        },
        "registry_audit": {
            "passed": registry_audit["passed"],
            "template_count": registry_audit["template_count"],
        },
        "counts": manifest["counts"],
        "selected": selected,
        "artifacts": {
            "designs": _portable_repo_path(designs_path),
            "flows": _portable_repo_path(packaged_flows),
            "manifest": _portable_repo_path(manifest_path),
            "submit_script": _portable_repo_path(submit_path),
            "submit_script_sha256": sha256(submit_path),
        },
        "minimum_memory_per_design_gb": 64,
        "local_execution": "package_only_do_not_run_production_adflow_on_16gb_laptop",
    }
    _write_json(output / "pilot_package.json", package)
    return package


def _template_paths(index: int, root: Path, eps_e: float = 2.0) -> tuple[Path, Path]:
    directory = Path(root) / f"lhs100_seed42_{index:03d}" / epsilon_tag(eps_e)
    return directory / "wing_vol.cgns", directory / "surface_blocks.npz"


def indices_from_atlas_manifest(path: Path) -> list[int]:
    manifest = _read_json(path)
    if manifest.get("schema") != ATLAS_SCHEMA:
        raise ValueError("not a current S6 atlas manifest")
    if manifest.get("set_name") != "lhs100_seed42":
        raise ValueError("atlas manifest uses the wrong development set")
    indices = [int(index) for index in manifest.get("template_indices", [])]
    if not indices or len(indices) != len(set(indices)):
        raise ValueError("atlas manifest template indices must be non-empty and unique")
    return indices


def _volume_level_from_normal_points(normal_points: int) -> str:
    matches = [
        level for level in ATLAS_VOLUME_LEVELS if int(GRID_LEVELS[level]["N"]) == normal_points
    ]
    if len(matches) != 1:
        raise ValueError(f"normal point count {normal_points} is not a supported S6 atlas level")
    return matches[0]


def build_registry(
    *,
    indices: list[int],
    source_root: Path,
    output: Path,
    production_floor: float,
    preferred_quality: float = PREFERRED_MIN_SCALED_QUALITY,
    atlas_manifest_path: Path | None = None,
    eps_e: float = 2.0,
) -> dict[str, Any]:
    if not indices:
        raise ValueError("at least one template index is required")
    if not 0.0 < production_floor <= 1.0:
        raise ValueError("production floor must be in (0, 1]")
    if not production_floor <= preferred_quality <= 1.0:
        raise ValueError("preferred quality must be between production floor and 1")
    eps_tag = epsilon_tag(eps_e)
    atlas_provenance: dict[str, Any] | None = None
    if atlas_manifest_path is not None:
        atlas_manifest_path = Path(atlas_manifest_path).resolve()
        atlas_manifest = _read_json(atlas_manifest_path)
        if atlas_manifest.get("schema") != ATLAS_SCHEMA:
            raise ValueError("not a current S6 atlas manifest")
        if atlas_manifest.get("set_name") != "lhs100_seed42":
            raise ValueError("atlas manifest uses the wrong development set")
        manifest_indices = [int(index) for index in atlas_manifest.get("template_indices", [])]
        if manifest_indices != indices:
            raise ValueError("registry indices differ from the atlas manifest")
        enrichment = atlas_manifest.get("quality_enrichment") or {}
        atlas_provenance = {
            "path": _portable_repo_path(atlas_manifest_path),
            "sha256": sha256(atlas_manifest_path),
            "schema": atlas_manifest["schema"],
            "template_selection": atlas_manifest.get("template_selection"),
            "quality_enrichment": enrichment,
            "freeze_ready": bool(enrichment.get("freeze_ready", False)),
        }
    matrix, names = design_matrix("lhs100_seed42")
    normalized = normalize_matrix(matrix, names)
    templates: list[dict[str, Any]] = []
    volume_levels: set[str] = set()
    first_cell_fractions: list[float] = []
    for index in indices:
        cgns, surface_path = _template_paths(index, source_root, eps_e)
        options_path = cgns.parent / "pyhyp_options.json"
        prepare_path = cgns.parent.parent / "prepare_manifest.json"
        if not all(path.is_file() for path in (cgns, surface_path, options_path, prepare_path)):
            raise FileNotFoundError(f"missing template files for index {index}")
        native_options = _read_json(options_path)
        prepare_manifest = _read_json(prepare_path)
        characteristic_length = float(prepare_manifest["characteristic_length"])
        if characteristic_length <= 0.0:
            raise ValueError(f"template {index} has invalid characteristic length")
        first_cell_fraction = float(native_options["s0"]) / characteristic_length
        first_cell_fractions.append(first_cell_fraction)
        surface = load_surface_blocks(surface_path)
        volume = read_volume_blocks(cgns)
        normal_points = int(next(iter(volume.values())).shape[0])
        volume_level = _volume_level_from_normal_points(normal_points)
        volume_levels.add(volume_level)
        correspondence = validate_template_correspondence(volume, surface)
        quality = volume_report(volume)
        interfaces = volume_interface_report(volume)
        accepted = bool(
            correspondence["max_wall_error_m"] <= WALL_TOLERANCE_M
            and quality.get("inverted_cells") == 0
            and float(quality.get("min_volume", -1.0)) > 0.0
            and float(quality.get("min_scaled_quality", -1.0)) >= production_floor
            and interfaces["paired_face_count"] > 0
            and interfaces["max_mismatch_m"] <= WALL_TOLERANCE_M
        )
        if not accepted:
            raise ValueError(f"template {index} fails frozen mesh gates")
        templates.append(
            {
                "template_id": (f"s1_lhs100_seed42_{index:03d}_n{normal_points}_{eps_tag}"),
                "geometry_index": index,
                "design": {
                    name: float(value) for name, value in zip(names, matrix[index], strict=True)
                },
                "normalized_design": normalized[index],
                "cgns": _portable_repo_path(cgns),
                "cgns_sha256": sha256(cgns),
                "surface_npz": _portable_repo_path(surface_path),
                "surface_npz_sha256": sha256(surface_path),
                "surface_level": "smoke",
                "volume_level": volume_level,
                "pyhyp_options": _portable_repo_path(options_path),
                "pyhyp_options_sha256": sha256(options_path),
                "normal_points": normal_points,
                "first_cell_height_m": float(native_options["s0"]),
                "first_cell_fraction_characteristic": first_cell_fraction,
                "eps_e": eps_e,
                "span_cells": int(next(iter(surface.values())).shape[1] - 1),
                "quality": quality,
                "interfaces": interfaces,
            }
        )
        del volume, surface
        gc.collect()

    if len(volume_levels) != 1:
        raise ValueError(f"registry mixes volume levels: {sorted(volume_levels)}")
    volume_level = next(iter(volume_levels))
    if not np.allclose(
        first_cell_fractions,
        first_cell_fractions[0],
        rtol=1.0e-12,
        atol=0.0,
    ):
        raise ValueError("registry mixes first-cell-height laws")

    registry = {
        "schema": REGISTRY_SCHEMA,
        "strategy_id": STRATEGY_ID,
        "set_name": "lhs100_seed42",
        "mesh_distance_excluded_variables": sorted(MESH_DISTANCE_EXCLUDED),
        "mesh_distance_variables": mesh_distance_variable_names(),
        "production_floor": production_floor,
        "preferred_quality": preferred_quality,
        "volume_level": volume_level,
        "normal_points": int(GRID_LEVELS[volume_level]["N"]),
        "first_cell_fraction_characteristic": first_cell_fractions[0],
        "eps_e": eps_e,
        "asset_path_base": "repository_root",
        "source_root": _portable_repo_path(source_root),
        "atlas_manifest": atlas_provenance,
        "registry_status": (
            "frozen_candidate"
            if atlas_provenance and atlas_provenance["freeze_ready"]
            else "development"
        ),
        "template_count": len(templates),
        "templates": templates,
    }
    _write_json(output, registry)
    return registry


def _resolve_case(
    manifest: dict[str, Any], case_index: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("not an S6 campaign manifest")
    cases = manifest["cases"]
    if case_index < 0 or case_index >= len(cases):
        raise IndexError(f"case index {case_index} outside [0, {len(cases)})")
    case = cases[case_index]
    design = next(row for row in manifest["designs"] if row["design_id"] == case["design_id"])
    flow = next(row for row in manifest["flows"] if row["flow_id"] == case["flow_id"])
    return case, design, flow


def _rank_templates(
    registry: dict[str, Any], normalized_design: list[float]
) -> list[tuple[float, dict[str, Any]]]:
    target = np.asarray(normalized_design, dtype=float)
    rows = [
        (
            float(rms_distance(np.asarray(template["normalized_design"]), target)),
            template,
        )
        for template in registry["templates"]
    ]
    return sorted(rows, key=lambda row: (row[0], row[1]["template_id"]))


def _attempt_template(
    *,
    pygeo_result: Any,
    template: dict[str, Any],
    distance_rms: float,
    design_dir: Path,
    production_floor: float,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    _verify_template_assets(template)
    template_surface = load_surface_blocks(Path(template["surface_npz"]))
    span_cells = int(next(iter(template_surface.values())).shape[1] - 1)
    try:
        blocks, surface_info = build_surface(
            pygeo_result,
            level=template.get("surface_level", "smoke"),
            span_cells=span_cells,
        )
    except Exception as error:
        return (
            {
                "template_id": template["template_id"],
                "distance_rms": distance_rms,
                "state": "SURFACE_BUILD_ERROR",
                "error_type": type(error).__name__,
                "error": str(error),
            },
            None,
        )
    surface_qc = surface_info["surface_qc"]
    if not surface_qc["accepted_pre_pyhyp"] or not surface_info["fidelity"]["passed"]:
        return (
            {
                "template_id": template["template_id"],
                "distance_rms": distance_rms,
                "state": "FAIL_SURFACE_GATE",
                "surface_failure_reasons": surface_qc["failure_reasons"],
                "surface_fidelity": surface_info["fidelity"],
                "surface_interfaces": surface_qc["surface_interfaces"],
            },
            None,
        )
    target_surface = {block.name: np.asarray(block.xyz, dtype=float) for block in blocks}
    volume = read_volume_blocks(Path(template["cgns"]))
    deformed, metadata = deform_volume_blocks(volume, template_surface, target_surface)
    acceptance = acceptance_report(deformed, metadata, production_floor=production_floor)
    attempt = {
        "template_id": template["template_id"],
        "distance_rms": distance_rms,
        "state": "PASS" if acceptance["production_floor_passed"] else "FAIL",
        "surface_min_scaled_jacobian": surface_info["surface_qc"]["global"]["min_scaled_jacobian"],
        "surface_fidelity": surface_info["fidelity"],
        "deformation": metadata,
        "acceptance": acceptance,
    }
    if not acceptance["production_floor_passed"]:
        gc.collect()
        return attempt, None

    attempt_dir = design_dir / "template_attempts" / _safe_id(str(template["template_id"]))
    candidate = attempt_dir / "wing_vol.cgns"
    try:
        write_volume_blocks(Path(template["cgns"]), candidate, deformed)
        written = read_volume_blocks(candidate)
        written_metadata = written_deformation_metadata(written, target_surface, metadata)
        independent = acceptance_report(
            written, written_metadata, production_floor=production_floor
        )
    except Exception as error:
        candidate.unlink(missing_ok=True)
        attempt["state"] = "FAIL_WRITTEN_AUDIT"
        attempt["written_audit_error_type"] = type(error).__name__
        attempt["written_audit_error"] = str(error)
        gc.collect()
        return attempt, None
    attempt["independent_written_acceptance"] = independent
    attempt["independent_written_deformation"] = {
        "max_wall_error_m": written_metadata["max_wall_error_m"],
        "per_zone_max_wall_error_m": written_metadata["per_zone_max_wall_error_m"],
        "deformed_interfaces": written_metadata["deformed_interfaces"],
        "first_layer_spacing": written_metadata["first_layer_spacing"],
    }
    if not independent["production_floor_passed"]:
        candidate.unlink(missing_ok=True)
        attempt["state"] = "FAIL_WRITTEN_AUDIT"
        gc.collect()
        return attempt, None

    surface_artifacts = write_surface_artifacts(blocks, attempt_dir / "surface")
    _write_json(attempt_dir / "surface" / "surface_report.json", surface_info)
    candidate_hash = sha256(candidate)
    attempt["candidate_cgns"] = str(candidate.resolve())
    attempt["candidate_cgns_sha256"] = candidate_hash
    accepted = {
        "cgns": str(candidate.resolve()),
        "cgns_sha256": candidate_hash,
        "surface_artifacts": surface_artifacts,
        "reference_values": pygeo_result.reference_values,
        "template_id": template["template_id"],
        "distance_rms": distance_rms,
        "acceptance": independent,
        "deformation_replay": {
            "schema": DEFORMATION_SCHEMA,
            "implementation_sha256": sha256(HERE / "deform.py"),
            "template_cgns": template["cgns"],
            "template_cgns_sha256": template.get("cgns_sha256"),
            "template_surface_npz": template["surface_npz"],
            "template_surface_npz_sha256": template.get("surface_npz_sha256"),
            "target_surface_artifacts": surface_artifacts,
            "metadata": written_metadata,
        },
    }
    gc.collect()
    return attempt, accepted


def _accepted_quality(candidate: dict[str, Any]) -> float:
    return float(candidate["acceptance"]["quality"]["min_scaled_quality"])


def _finalize_best_candidate(
    candidates: list[dict[str, Any]],
    *,
    design_dir: Path,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidates:
        return None
    accepted = min(
        candidates,
        key=lambda candidate: (
            -_accepted_quality(candidate),
            float(candidate["distance_rms"]),
            str(candidate["template_id"]),
        ),
    )
    staged = Path(accepted["cgns"])
    final_cgns = design_dir / "wing_vol.cgns"
    staged_hash = accepted["cgns_sha256"]
    staged.replace(final_cgns)
    if sha256(final_cgns) != staged_hash:
        raise RuntimeError("selected mesh hash changed during finalization")
    accepted["staged_cgns"] = str(staged)
    accepted["cgns"] = str(final_cgns.resolve())

    selected_key = (accepted["template_id"], staged_hash)
    for attempt in attempts:
        written = attempt.get("independent_written_acceptance")
        attempt["selected"] = bool(
            written is not None
            and attempt.get("template_id") == selected_key[0]
            and attempt.get("candidate_cgns_sha256") == selected_key[1]
        )
    for candidate in candidates:
        if candidate is accepted:
            continue
        Path(candidate["cgns"]).unlink(missing_ok=True)
    return accepted


def _run_with_timeout(command: list[str], cwd: Path, log_path: Path, timeout_s: float) -> int:
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            return process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30.0)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            return 124


def _target_specific_template(
    *,
    geometry_case: Any,
    design_id: str,
    design_dir: Path,
    timeout_s: float,
    volume_level: str,
    s0_fraction: float,
    eps_e: float,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if geometry_case.wing is None:
        return None, {"state": "UNAVAILABLE", "reason": "AeroSandbox wing not built"}
    blocks, info = strategy_s1.build_surface(geometry_case.wing, level="L2_smoke")
    fallback_root = design_dir / "target_specific_s1"
    prepared = prepare(
        strategy_id=strategy_s1.STRATEGY_ID,
        geometry_id=design_id,
        blocks=blocks,
        out_dir=fallback_root,
        level=volume_level,
        epse_ladder=(eps_e,),
        s0_fraction_override=s0_fraction,
    )
    run_dir = Path(prepared["runs"][0]["dir"]).resolve()
    runner = Path(prepared["runs"][0]["runner"]).resolve()
    returncode = _run_with_timeout(
        [str(mach_aero_python()), str(runner)],
        run_dir,
        run_dir / "run_stdout.log",
        timeout_s,
    )
    result = read_result(run_dir) or {}
    state = {
        "state": "PASS" if returncode == 0 and result.get("march_completed") else "FAIL",
        "return_code": returncode,
        "march_result": result,
        "eps_e": eps_e,
        "first_cell_fraction_characteristic": s0_fraction,
    }
    cgns = run_dir / "wing_vol.cgns"
    surface_npz = run_dir / "surface_blocks.npz"
    if state["state"] != "PASS" or not cgns.is_file() or not surface_npz.is_file():
        return None, state
    template = {
        "template_id": f"target_specific_s1_{design_id}",
        "normalized_design": [],
        "cgns": str(cgns),
        "cgns_sha256": sha256(cgns),
        "surface_npz": str(surface_npz),
        "surface_npz_sha256": sha256(surface_npz),
        "surface_level": "smoke",
        "volume_level": volume_level,
        "eps_e": eps_e,
        "first_cell_fraction_characteristic": s0_fraction,
    }
    return template, state


def mesh_case(
    *,
    manifest_path: Path,
    registry_path: Path,
    campaign_root: Path,
    case_index: int,
    max_templates: int,
    allow_remesh: bool,
    remesh_timeout_s: float,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    registry_path = Path(registry_path).resolve()
    registry = _materialize_registry_assets(_read_json(registry_path), registry_path)
    volume_level = str(registry.get("volume_level", ""))
    if volume_level not in ATLAS_VOLUME_LEVELS:
        raise ValueError("registry has no supported volume_level")
    manifest_hash = sha256(manifest_path)
    registry_hash = sha256(registry_path)
    implementation_hash = _mesh_implementation_sha256()
    case, design, _flow = _resolve_case(manifest, case_index)
    design_dir = Path(campaign_root).resolve() / "geometries" / _safe_id(case["design_id"])
    report_path = design_dir / "mesh_report.json"
    if existing := _existing_accepted_mesh(
        report_path,
        manifest_sha256=manifest_hash,
        registry_sha256=registry_hash,
        implementation_sha256=implementation_hash,
    ):
        return existing
    with _case_lock(design_dir / ".mesh.lock"):
        if existing := _existing_accepted_mesh(
            report_path,
            manifest_sha256=manifest_hash,
            registry_sha256=registry_hash,
            implementation_sha256=implementation_hash,
        ):
            return existing

        started = time.monotonic()
        design_dir.mkdir(parents=True, exist_ok=True)
        sample = BWBDesignSample(**design["values"])
        geometry_case = get_geometry_generator("bwb_segmented").run_full_case(
            sample=sample,
            config=_config(),
            output_dir=design_dir / "geometry",
            save_plot=False,
            build_aerosandbox=allow_remesh,
        )
        if geometry_case.pygeo_result is None:
            raise RuntimeError("pyGeo did not produce the master geometry")

        ranked = _rank_templates(registry, design["normalized_design"])
        template_ranking = [
            {
                "rank": rank,
                "template_id": template["template_id"],
                "distance_rms": distance,
            }
            for rank, (distance, template) in enumerate(ranked, start=1)
        ]
        limit = len(ranked) if max_templates <= 0 else min(max_templates, len(ranked))
        attempts: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        preferred_quality = float(registry["preferred_quality"])
        for distance, template in ranked[:limit]:
            attempt_started = time.monotonic()
            try:
                attempt, candidate = _attempt_template(
                    pygeo_result=geometry_case.pygeo_result,
                    template=template,
                    distance_rms=distance,
                    design_dir=design_dir,
                    production_floor=float(registry["production_floor"]),
                )
            except RegistryIntegrityError:
                raise
            except Exception as error:
                attempt, candidate = (
                    {
                        "template_id": template["template_id"],
                        "distance_rms": distance,
                        "state": "TEMPLATE_ATTEMPT_ERROR",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    },
                    None,
                )
            attempt["elapsed_s"] = time.monotonic() - attempt_started
            attempts.append(attempt)
            if candidate is not None:
                candidates.append(candidate)
            if candidate is not None and _accepted_quality(candidate) >= preferred_quality:
                break

        fallback: dict[str, Any] | None = None
        best_quality = max(
            (_accepted_quality(candidate) for candidate in candidates),
            default=-1.0,
        )
        if best_quality < preferred_quality and allow_remesh:
            try:
                template, fallback = _target_specific_template(
                    geometry_case=geometry_case,
                    design_id=case["design_id"],
                    design_dir=design_dir,
                    timeout_s=remesh_timeout_s,
                    volume_level=volume_level,
                    s0_fraction=float(registry["first_cell_fraction_characteristic"]),
                    eps_e=float(registry["eps_e"]),
                )
            except Exception as error:
                template = None
                fallback = {
                    "state": "ERROR",
                    "error_type": type(error).__name__,
                    "error": str(error),
                }
            if template is not None:
                attempt_started = time.monotonic()
                try:
                    attempt, candidate = _attempt_template(
                        pygeo_result=geometry_case.pygeo_result,
                        template=template,
                        distance_rms=0.0,
                        design_dir=design_dir,
                        production_floor=float(registry["production_floor"]),
                    )
                except RegistryIntegrityError:
                    raise
                except Exception as error:
                    attempt, candidate = (
                        {
                            "template_id": template["template_id"],
                            "distance_rms": 0.0,
                            "state": "FALLBACK_ATTEMPT_ERROR",
                            "error_type": type(error).__name__,
                            "error": str(error),
                        },
                        None,
                    )
                attempt["elapsed_s"] = time.monotonic() - attempt_started
                attempts.append(attempt)
                if candidate is not None:
                    candidates.append(candidate)

        accepted = _finalize_best_candidate(
            candidates,
            design_dir=design_dir,
            attempts=attempts,
        )
        selected_quality = _accepted_quality(accepted) if accepted is not None else None

        report = {
            "schema": MESH_REPORT_SCHEMA,
            "strategy_id": STRATEGY_ID,
            "state": "MESH_ACCEPTED" if accepted is not None else "MESH_REJECTED",
            "design_id": case["design_id"],
            "design": design["values"],
            "manifest_sha256": manifest_hash,
            "registry_sha256": registry_hash,
            "mesh_implementation_sha256": implementation_hash,
            "production_floor": float(registry["production_floor"]),
            "preferred_quality": preferred_quality,
            "preferred_quality_met": bool(
                selected_quality is not None and selected_quality >= preferred_quality
            ),
            "template_ranking": template_ranking,
            "attempts": attempts,
            "target_specific_fallback": fallback,
            "accepted_mesh": accepted,
            "elapsed_s": time.monotonic() - started,
        }
        _write_json(report_path, report)
        return report


def _reported_file_matches(report: dict[str, Any], path_field: str, hash_field: str) -> bool:
    path_value = report.get(path_field)
    expected = report.get(hash_field)
    if not isinstance(path_value, str) or not isinstance(expected, str):
        return False
    path = Path(path_value)
    return path.is_file() and sha256(path) == expected


def _valid_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _surface_solution_provenance_matches(report: dict[str, Any]) -> bool:
    gate = report.get("wall_yplus_gate")
    retained = report.get("surface_solution_retained")
    if not isinstance(gate, dict) or not isinstance(retained, bool):
        return False
    path_value = gate.get("surface_cgns")
    expected = gate.get("surface_cgns_sha256")
    if isinstance(path_value, str) and _valid_sha256(expected):
        path = Path(path_value)
        if path.is_file():
            return sha256(path) == expected
        return not retained
    return bool(
        path_value is None
        and expected is None
        and not retained
        and report.get("state") == "CFD_REJECTED"
        and gate.get("failure_reasons") == ["missing_surface_solution"]
        and gate.get("candidate_count") == 0
    )


def _existing_cfd_result(
    path: Path,
    *,
    manifest_sha256: str,
    mesh_sha256: str,
    implementation_sha256: str,
    mpi_np: int,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    report = _read_json(path)
    return (
        report
        if report.get("schema") == CFD_REPORT_SCHEMA
        and report.get("state") in {"CFD_ACCEPTED", "CFD_REJECTED"}
        and report.get("manifest_sha256") == manifest_sha256
        and report.get("mesh_sha256") == mesh_sha256
        and report.get("solver_implementation_sha256") == implementation_sha256
        and report.get("mpi_processes") == mpi_np
        and _reported_file_matches(report, "solve_report", "solve_report_sha256")
        and _reported_file_matches(report, "solver_log", "solver_log_sha256")
        and _reported_file_matches(report, "wall_yplus_summary", "wall_yplus_summary_sha256")
        and _surface_solution_provenance_matches(report)
        else None
    )


def _existing_accepted_cfd(
    path: Path,
    *,
    manifest_sha256: str,
    mesh_sha256: str,
    implementation_sha256: str,
    mpi_np: int,
) -> dict[str, Any] | None:
    report = _existing_cfd_result(
        path,
        manifest_sha256=manifest_sha256,
        mesh_sha256=mesh_sha256,
        implementation_sha256=implementation_sha256,
        mpi_np=mpi_np,
    )
    return report if report and report["state"] == "CFD_ACCEPTED" else None


def _existing_accepted_design(
    *,
    campaign_root: Path,
    design_id: str,
    case_ids: list[str],
    manifest_sha256: str,
    registry_sha256: str,
    mesh_implementation_sha256: str,
    solver_implementation_sha256: str,
    mpi_np: int,
) -> dict[str, Any] | None:
    root = Path(campaign_root).resolve()
    report_path = root / "geometries" / _safe_id(design_id) / "design_run_report.json"
    if not report_path.is_file():
        return None
    report = _read_json(report_path)
    mesh_hash = report.get("mesh_sha256")
    if not (
        report.get("schema") == DESIGN_REPORT_SCHEMA
        and report.get("state") == "DESIGN_ACCEPTED"
        and report.get("manifest_sha256") == manifest_sha256
        and report.get("registry_sha256") == registry_sha256
        and report.get("mesh_implementation_sha256") == mesh_implementation_sha256
        and report.get("solver_implementation_sha256") == solver_implementation_sha256
        and report.get("mpi_processes") == mpi_np
        and isinstance(mesh_hash, str)
        and report.get("case_ids") == case_ids
    ):
        return None
    for case_id in case_ids:
        accepted = _existing_accepted_cfd(
            root / "cases" / _safe_id(case_id) / "cfd_acceptance.json",
            manifest_sha256=manifest_sha256,
            mesh_sha256=mesh_hash,
            implementation_sha256=solver_implementation_sha256,
            mpi_np=mpi_np,
        )
        if accepted is None:
            return None
    return report


def _archive_previous_solver_outputs(case_dir: Path) -> None:
    names = {
        "adflow_run.json",
        "adflow_run.log",
        "solve_report.json",
        "run_meta.json",
        "cfd_acceptance.json",
        "laptop_cfd_report.json",
        "wall_yplus_summary.json",
    }
    paths = [case_dir / name for name in names]
    paths.extend(case_dir.glob("aeris_cfd_*.cgns"))
    existing = [path for path in paths if path.exists()]
    if not existing:
        return
    attempts = case_dir / "previous_attempts"
    attempts.mkdir(parents=True, exist_ok=True)
    index = 0
    while (target := attempts / f"attempt_{index:03d}").exists():
        index += 1
    target.mkdir()
    for path in existing:
        path.replace(target / path.name)


FORCE_COEFFICIENT_FLOORS = {"cl": 0.10, "cd": 0.01}


def _force_tail_gate(
    log_path: Path,
    *,
    relative_range_max: float,
    coefficient_floors: dict[str, float] | None = None,
) -> dict[str, Any]:
    coefficient_floors = coefficient_floors or FORCE_COEFFICIENT_FLOORS
    history = parse_force_history(log_path.read_text(encoding="utf-8"))
    if len(history) < 10:
        return {"passed": False, "reason": "fewer_than_10_force_samples"}
    count = min(25, max(10, len(history) // 5))
    tail = history[-count:]
    absolute_ranges: dict[str, float] = {}
    ranges: dict[str, float] = {}
    for key in ("cl", "cd"):
        values = np.asarray([row[key] for row in tail], dtype=float)
        absolute_ranges[key] = float(np.ptp(values))
        denominator = max(abs(float(values.mean())), coefficient_floors[key])
        ranges[key] = absolute_ranges[key] / denominator
    return {
        "passed": all(value <= relative_range_max for value in ranges.values()),
        "tail_count": count,
        "absolute_ranges": absolute_ranges,
        "relative_ranges": ranges,
        "coefficient_floors": coefficient_floors,
        "limit": relative_range_max,
    }


def _wall_yplus_gate(workdir: Path) -> tuple[dict[str, Any], Path | None]:
    candidates = sorted(Path(workdir).glob("aeris_cfd*_surf.cgns"))
    if len(candidates) != 1:
        return (
            {
                "passed": False,
                "failure_reasons": [
                    "missing_surface_solution" if not candidates else "multiple_surface_solutions"
                ],
                "candidate_count": len(candidates),
            },
            None,
        )
    try:
        return wall_yplus_summary(candidates[0]), candidates[0]
    except Exception as error:
        return (
            {
                "passed": False,
                "failure_reasons": ["wall_yplus_read_error"],
                "error_type": type(error).__name__,
                "error": str(error),
                "surface_cgns": str(candidates[0].resolve()),
                "surface_cgns_sha256": sha256(candidates[0]),
            },
            candidates[0],
        )


def _force_plausibility_gate(forces: dict[str, float]) -> dict[str, Any]:
    required = ("cl", "cd", "cmy")
    missing = [name for name in required if name not in forces]
    nonfinite = [
        name for name in required if name in forces and not math.isfinite(float(forces[name]))
    ]
    positive_drag = not missing and not nonfinite and float(forces["cd"]) > 0.0
    reasons = []
    if missing:
        reasons.append("missing_force_coefficients")
    if nonfinite:
        reasons.append("nonfinite_force_coefficients")
    if not missing and not nonfinite and not positive_drag:
        reasons.append("nonpositive_drag")
    return {
        "passed": not reasons,
        "required": list(required),
        "missing": missing,
        "nonfinite": nonfinite,
        "positive_drag": positive_drag,
        "failure_reasons": reasons,
    }


def solve_case(
    *,
    manifest_path: Path,
    campaign_root: Path,
    case_index: int,
    mpi_np: int,
    dry_run: bool,
    retain_surface_solution: bool = False,
    retry_rejected: bool = False,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    case, _design, flow = _resolve_case(manifest, case_index)
    root = Path(campaign_root).resolve()
    design_dir = root / "geometries" / _safe_id(case["design_id"])
    mesh_report = _read_json(design_dir / "mesh_report.json")
    if mesh_report.get("state") != "MESH_ACCEPTED":
        raise RuntimeError(f"{case['design_id']} has no accepted S6 mesh")
    mesh = mesh_report["accepted_mesh"]
    mesh_path = Path(mesh["cgns"])
    if sha256(mesh_path) != mesh["cgns_sha256"]:
        raise RuntimeError("accepted mesh hash changed after mesh acceptance")
    manifest_hash = sha256(manifest_path)
    solver_implementation_hash = _solver_implementation_sha256()

    case_dir = root / "cases" / _safe_id(case["case_id"])
    acceptance_path = case_dir / "cfd_acceptance.json"
    if (
        not dry_run
        and (
            existing := _existing_cfd_result(
                acceptance_path,
                manifest_sha256=manifest_hash,
                mesh_sha256=mesh["cgns_sha256"],
                implementation_sha256=solver_implementation_hash,
                mpi_np=mpi_np,
            )
        )
        and (existing["state"] == "CFD_ACCEPTED" or not retry_rejected)
    ):
        return existing

    with _case_lock(case_dir / ".solve.lock"):
        if (
            not dry_run
            and (
                existing := _existing_cfd_result(
                    acceptance_path,
                    manifest_sha256=manifest_hash,
                    mesh_sha256=mesh["cgns_sha256"],
                    implementation_sha256=solver_implementation_hash,
                    mpi_np=mpi_np,
                )
            )
            and (existing["state"] == "CFD_ACCEPTED" or not retry_rejected)
        ):
            return existing

        refs = mesh["reference_values"]
        solve = SolveSpec(
            solver="adflow",
            preset="rans_ank_nk_v1",
            flow=FlowConditions(
                alpha=float(flow["alpha"]),
                mach=float(flow["mach"]),
                reynolds=float(flow["reynolds"]),
                temperature=float(flow["temperature"]),
            ),
            area_ref=0.5 * float(refs["area_m2"]),
            chord_ref=float(refs["mean_aerodynamic_chord_m"]),
            mpi_np=mpi_np,
            raw_options={
                "writeVolumeSolution": False,
                "writeSurfaceSolution": True,
                "monitorVariables": ["resrho", "resturb", "cl", "cd", "yplus"],
                "NKSubspaceSize": NK_SUBSPACE_SIZE,
            },
        )
        adapter = get_solver_adapter("adflow")
        if not dry_run:
            _archive_previous_solver_outputs(case_dir)
        prepared = adapter.prepare(solve, mesh_path, case_dir)
        if dry_run:
            return {
                "schema": CFD_REPORT_SCHEMA,
                "state": "CFD_PREPARED",
                "case_id": case["case_id"],
                "command": list(prepared.command),
            }

        started = time.monotonic()
        returncode = adapter.run(prepared)
        solver_report = adapter.parse(prepared.workdir)
        convergence = solver_report.convergence
        orders = convergence.get("orders_dropped")
        residual_passed = orders is not None and float(orders) >= 6.0
        force_plausibility = _force_plausibility_gate(solver_report.forces)
        finite_forces = not force_plausibility["missing"] and not force_plausibility["nonfinite"]
        force_gate = _force_tail_gate(
            prepared.workdir / prepared.log_name, relative_range_max=0.001
        )
        yplus_gate, surface_solution = _wall_yplus_gate(prepared.workdir)
        solve_report_path = prepared.workdir / "solve_report.json"
        solver_log_path = prepared.workdir / prepared.log_name
        wall_yplus_summary_path = prepared.workdir / "wall_yplus_summary.json"
        _write_json(wall_yplus_summary_path, yplus_gate)
        required_artifacts = {
            "solve_report": solve_report_path,
            "solver_log": solver_log_path,
            "wall_yplus_summary": wall_yplus_summary_path,
        }
        missing_artifacts = [
            name for name, path in required_artifacts.items() if not path.is_file()
        ]
        accepted = bool(
            returncode == 0
            and solver_report.status == "converged"
            and residual_passed
            and force_plausibility["passed"]
            and force_gate["passed"]
            and yplus_gate["passed"]
            and not missing_artifacts
        )
        surface_retained = bool(
            surface_solution is not None and (not accepted or retain_surface_solution)
        )
        report = {
            "schema": CFD_REPORT_SCHEMA,
            "state": "CFD_ACCEPTED" if accepted else "CFD_REJECTED",
            "case_id": case["case_id"],
            "design_id": case["design_id"],
            "flow_id": case["flow_id"],
            "manifest_sha256": manifest_hash,
            "mesh_sha256": mesh["cgns_sha256"],
            "solver_implementation_sha256": solver_implementation_hash,
            "mpi_processes": mpi_np,
            "solver_preset": "rans_ank_nk_v1",
            "nk_subspace_size": NK_SUBSPACE_SIZE,
            "solver_return_code": returncode,
            "solver_status": solver_report.status,
            "residual_orders_dropped": orders,
            "residual_gate_passed": residual_passed,
            "force_tail_gate": force_gate,
            "wall_yplus_gate": yplus_gate,
            "force_plausibility_gate": force_plausibility,
            "finite_forces": finite_forces,
            "forces": solver_report.forces,
            "artifact_provenance_gate": {
                "passed": not missing_artifacts,
                "missing": missing_artifacts,
            },
            "solve_report": str(solve_report_path),
            "solve_report_sha256": (
                sha256(solve_report_path) if solve_report_path.is_file() else None
            ),
            "solver_log": str(solver_log_path),
            "solver_log_sha256": (sha256(solver_log_path) if solver_log_path.is_file() else None),
            "wall_yplus_summary": str(wall_yplus_summary_path),
            "wall_yplus_summary_sha256": (
                sha256(wall_yplus_summary_path) if wall_yplus_summary_path.is_file() else None
            ),
            "surface_solution_retained": surface_retained,
            "elapsed_s": time.monotonic() - started,
        }
        _write_json(acceptance_path, report)
        if accepted and not retain_surface_solution and surface_solution is not None:
            surface_solution.unlink(missing_ok=True)
        return report


def run_design(
    *,
    manifest_path: Path,
    registry_path: Path,
    campaign_root: Path,
    design_index: int,
    max_templates: int,
    allow_remesh: bool,
    remesh_timeout_s: float,
    mpi_np: int,
    dry_run: bool,
    prune_accepted_mesh: bool,
    retain_surface_solution: bool = False,
    retry_rejected: bool = False,
) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    if design_index < 0 or design_index >= len(manifest["designs"]):
        raise IndexError(f"design index {design_index} outside [0, {len(manifest['designs'])})")
    design_id = manifest["designs"][design_index]["design_id"]
    case_indices = [
        int(case["case_index"]) for case in manifest["cases"] if case["design_id"] == design_id
    ]
    if not case_indices:
        raise ValueError(f"design {design_id} has no flow cases")
    case_ids = [str(manifest["cases"][index]["case_id"]) for index in case_indices]
    manifest_hash = sha256(manifest_path)
    registry_hash = sha256(registry_path)
    mesh_implementation_hash = _mesh_implementation_sha256()
    solver_implementation_hash = _solver_implementation_sha256()
    if not dry_run and (
        existing := _existing_accepted_design(
            campaign_root=campaign_root,
            design_id=design_id,
            case_ids=case_ids,
            manifest_sha256=manifest_hash,
            registry_sha256=registry_hash,
            mesh_implementation_sha256=mesh_implementation_hash,
            solver_implementation_sha256=solver_implementation_hash,
            mpi_np=mpi_np,
        )
    ):
        return existing

    mesh = mesh_case(
        manifest_path=manifest_path,
        registry_path=registry_path,
        campaign_root=campaign_root,
        case_index=case_indices[0],
        max_templates=max_templates,
        allow_remesh=allow_remesh,
        remesh_timeout_s=remesh_timeout_s,
    )
    results: list[dict[str, Any]] = []
    if mesh["state"] == "MESH_ACCEPTED":
        for case_index in case_indices:
            results.append(
                solve_case(
                    manifest_path=manifest_path,
                    campaign_root=campaign_root,
                    case_index=case_index,
                    mpi_np=mpi_np,
                    dry_run=dry_run,
                    retain_surface_solution=retain_surface_solution,
                    retry_rejected=retry_rejected,
                )
            )

    all_accepted = bool(results) and all(result["state"] == "CFD_ACCEPTED" for result in results)
    pruned = False
    if all_accepted and prune_accepted_mesh and not dry_run:
        mesh_path = Path(mesh["accepted_mesh"]["cgns"])
        if mesh_path.is_file() and sha256(mesh_path) == mesh["accepted_mesh"]["cgns_sha256"]:
            mesh_path.unlink()
            pruned = True

    report = {
        "schema": DESIGN_REPORT_SCHEMA,
        "state": (
            "DESIGN_ACCEPTED"
            if all_accepted
            else "MESH_REJECTED"
            if mesh["state"] == "MESH_REJECTED"
            else "DESIGN_INCOMPLETE"
            if dry_run
            else "CFD_REJECTED"
        ),
        "design_index": design_index,
        "design_id": design_id,
        "case_indices": case_indices,
        "case_ids": case_ids,
        "manifest_sha256": manifest_hash,
        "registry_sha256": registry_hash,
        "mesh_implementation_sha256": mesh_implementation_hash,
        "solver_implementation_sha256": solver_implementation_hash,
        "mpi_processes": mpi_np,
        "mesh_sha256": (
            mesh["accepted_mesh"]["cgns_sha256"] if mesh["state"] == "MESH_ACCEPTED" else None
        ),
        "mesh_state": mesh["state"],
        "case_states": [result["state"] for result in results],
        "accepted_mesh_pruned": pruned,
    }
    design_dir = Path(campaign_root).resolve() / "geometries" / _safe_id(design_id)
    _write_json(design_dir / "design_run_report.json", report)
    return report


def collect(campaign_root: Path, manifest_path: Path, output: Path) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("not an S6 campaign manifest")
    manifest_hash = sha256(manifest_path)
    root = Path(campaign_root).resolve()
    fields = [
        "case_index",
        "case_id",
        "design_id",
        "flow_id",
        "state",
        "cl",
        "cd",
        "cmy",
        "orders_dropped",
        "yplus_p95",
        "yplus_max",
    ]
    rows: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        row = {
            **case,
            "state": "NOT_RUN",
            "cl": None,
            "cd": None,
            "cmy": None,
            "orders_dropped": None,
            "yplus_p95": None,
            "yplus_max": None,
        }
        path = root / "cases" / _safe_id(case["case_id"]) / "cfd_acceptance.json"
        if not path.is_file():
            mesh_path = root / "geometries" / _safe_id(case["design_id"]) / "mesh_report.json"
            if mesh_path.is_file():
                mesh_report = _read_json(mesh_path)
                if mesh_report.get("manifest_sha256") != manifest_hash:
                    row["state"] = "STALE_RESULT"
                elif mesh_report.get("state") == "MESH_REJECTED":
                    row["state"] = "MESH_REJECTED"
            rows.append(row)
            continue
        report = _read_json(path)
        if report.get("manifest_sha256") != manifest_hash:
            row["state"] = "STALE_RESULT"
        else:
            row.update(
                {
                    "state": report["state"],
                    "cl": report.get("forces", {}).get("cl"),
                    "cd": report.get("forces", {}).get("cd"),
                    "cmy": report.get("forces", {}).get("cmy"),
                    "orders_dropped": report.get("residual_orders_dropped"),
                    "yplus_p95": report.get("wall_yplus_gate", {}).get("statistics", {}).get("p95"),
                    "yplus_max": report.get("wall_yplus_gate", {})
                    .get("statistics", {})
                    .get("maximum"),
                }
            )
        rows.append(row)
    states: dict[str, int] = {}
    for row in rows:
        states[row["state"]] = states.get(row["state"], 0) + 1
    report = {
        "schema": "aeris.mesh.s6_campaign_summary.v1",
        "manifest_sha256": manifest_hash,
        "counts": states,
        "rows": rows,
    }
    _write_json(output, report)
    csv_path = Path(output).with_suffix(".csv")
    temporary = csv_path.with_name(f".{csv_path.name}.{os.getpid()}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(csv_path)
    return report


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    manifest = commands.add_parser("make-manifest")
    sampling = commands.add_parser("sample-designs")
    sampling.add_argument("--count", type=int, required=True)
    sampling.add_argument("--seed", type=int, required=True)
    sampling.add_argument("--output", type=Path, required=True)

    manifest.add_argument("--designs", type=Path, required=True)
    manifest.add_argument("--flows", type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)

    pilot = commands.add_parser("prepare-hpc-pilot")
    pilot.add_argument("--development-report", type=Path, required=True)
    pilot.add_argument("--atlas-manifest", type=Path, required=True)
    pilot.add_argument("--registry", type=Path, required=True)
    pilot.add_argument(
        "--flows",
        type=Path,
        default=HERE / "examples/flows_single.csv",
    )
    pilot.add_argument("--output", type=Path, required=True)
    pilot.add_argument("--count", type=int, default=10)
    pilot.add_argument(
        "--required-indices",
        type=int,
        nargs="*",
        default=[7, 89, 95],
    )

    registry = commands.add_parser("build-registry")
    registry_selection = registry.add_mutually_exclusive_group(required=True)
    registry_selection.add_argument("--indices", type=int, nargs="+")
    registry_selection.add_argument("--atlas-manifest", type=Path)
    registry.add_argument("--source-root", type=Path, default=DEFAULT_S1_ROOT)
    registry.add_argument("--eps-e", type=float, choices=EPSE_LADDER, default=2.0)
    registry.add_argument("--production-floor", type=float, default=0.10)
    registry.add_argument(
        "--preferred-quality",
        type=float,
        default=PREFERRED_MIN_SCALED_QUALITY,
    )
    registry.add_argument("--output", type=Path, required=True)

    registry_audit = commands.add_parser("verify-registry")
    registry_audit.add_argument("--registry", type=Path, required=True)
    registry_audit.add_argument("--output", type=Path, required=True)

    mesh = commands.add_parser("mesh-case")
    mesh.add_argument("--manifest", type=Path, required=True)
    mesh.add_argument("--registry", type=Path, required=True)
    mesh.add_argument("--campaign-root", type=Path, required=True)
    mesh.add_argument("--case-index", type=int, required=True)
    mesh.add_argument("--max-templates", type=int, default=0)
    mesh.add_argument("--no-remesh", action="store_true")
    mesh.add_argument("--remesh-timeout-s", type=float, default=3600.0)

    solve = commands.add_parser("solve-case")
    solve.add_argument("--manifest", type=Path, required=True)
    solve.add_argument("--campaign-root", type=Path, required=True)
    solve.add_argument("--case-index", type=int, required=True)
    solve.add_argument("--np", type=int, default=4)
    solve.add_argument("--dry-run", action="store_true")
    solve.add_argument("--retain-surface-solution", action="store_true")
    solve.add_argument("--retry-rejected", action="store_true")

    design_run = commands.add_parser("run-design")
    design_run.add_argument("--manifest", type=Path, required=True)
    design_run.add_argument("--registry", type=Path, required=True)
    design_run.add_argument("--campaign-root", type=Path, required=True)
    design_run.add_argument("--design-index", type=int, required=True)
    design_run.add_argument("--max-templates", type=int, default=0)
    design_run.add_argument("--no-remesh", action="store_true")
    design_run.add_argument("--remesh-timeout-s", type=float, default=3600.0)
    design_run.add_argument("--np", type=int, default=4)
    design_run.add_argument("--dry-run", action="store_true")
    design_run.add_argument("--prune-accepted-mesh", action="store_true")
    design_run.add_argument("--retain-surface-solution", action="store_true")
    design_run.add_argument("--retry-rejected", action="store_true")

    run = commands.add_parser("run-case")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--registry", type=Path, required=True)
    run.add_argument("--campaign-root", type=Path, required=True)
    run.add_argument("--case-index", type=int, required=True)
    run.add_argument("--max-templates", type=int, default=0)
    run.add_argument("--no-remesh", action="store_true")
    run.add_argument("--remesh-timeout-s", type=float, default=3600.0)
    run.add_argument("--np", type=int, default=4)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--retain-surface-solution", action="store_true")
    run.add_argument("--retry-rejected", action="store_true")

    summary = commands.add_parser("collect")
    summary.add_argument("--manifest", type=Path, required=True)
    summary.add_argument("--campaign-root", type=Path, required=True)
    summary.add_argument("--output", type=Path, required=True)
    return parser


def _record_worker_error(args: argparse.Namespace, error: Exception) -> Path | None:
    campaign_root = getattr(args, "campaign_root", None)
    if campaign_root is None:
        return None
    index = getattr(args, "case_index", getattr(args, "design_index", "unknown"))
    path = (
        Path(campaign_root).resolve()
        / "worker_errors"
        / f"{_safe_id(args.command)}_{index}_{int(time.time())}_{os.getpid()}.json"
    )
    return _write_json(
        path,
        {
            "schema": "aeris.mesh.s6_worker_error.v1",
            "command": args.command,
            "index": index,
            "pid": os.getpid(),
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        },
    )


def main() -> int:
    args = make_parser().parse_args()
    try:
        if args.command == "sample-designs":
            result = sample_designs(count=args.count, seed=args.seed, output=args.output)
        elif args.command == "make-manifest":
            manifest_result = make_manifest(args.designs, args.flows, args.output)
            result = {
                "schema": manifest_result["schema"],
                "manifest": str(args.output.resolve()),
                "manifest_sha256": sha256(args.output),
                "counts": manifest_result["counts"],
            }
        elif args.command == "prepare-hpc-pilot":
            result = prepare_hpc_pilot(
                development_report_path=args.development_report,
                atlas_manifest_path=args.atlas_manifest,
                registry_path=args.registry,
                flows_path=args.flows,
                output=args.output,
                count=args.count,
                required_indices=tuple(args.required_indices),
            )
            result = {
                "schema": result["schema"],
                "package": str((args.output / "pilot_package.json").resolve()),
                "counts": result["counts"],
            }
        elif args.command == "build-registry":
            registry_result = build_registry(
                indices=(
                    indices_from_atlas_manifest(args.atlas_manifest)
                    if args.atlas_manifest
                    else args.indices
                ),
                source_root=args.source_root,
                output=args.output,
                production_floor=args.production_floor,
                preferred_quality=args.preferred_quality,
                atlas_manifest_path=args.atlas_manifest,
                eps_e=args.eps_e,
            )
            result = {
                "schema": registry_result["schema"],
                "registry": str(args.output.resolve()),
                "registry_sha256": sha256(args.output),
                "template_count": registry_result["template_count"],
                "volume_level": registry_result["volume_level"],
                "normal_points": registry_result["normal_points"],
                "production_floor": registry_result["production_floor"],
                "preferred_quality": registry_result["preferred_quality"],
                "registry_status": registry_result["registry_status"],
            }
        elif args.command == "verify-registry":
            result = verify_registry(args.registry)
            _write_json(args.output, result)
            result["output"] = str(args.output.resolve())
        elif args.command == "run-design":
            result = run_design(
                manifest_path=args.manifest,
                registry_path=args.registry,
                campaign_root=args.campaign_root,
                design_index=args.design_index,
                max_templates=args.max_templates,
                allow_remesh=not args.no_remesh,
                remesh_timeout_s=args.remesh_timeout_s,
                mpi_np=args.np,
                dry_run=args.dry_run,
                prune_accepted_mesh=args.prune_accepted_mesh,
                retain_surface_solution=args.retain_surface_solution,
                retry_rejected=args.retry_rejected,
            )
        elif args.command in {"mesh-case", "run-case"}:
            result = mesh_case(
                manifest_path=args.manifest,
                registry_path=args.registry,
                campaign_root=args.campaign_root,
                case_index=args.case_index,
                max_templates=args.max_templates,
                allow_remesh=not args.no_remesh,
                remesh_timeout_s=args.remesh_timeout_s,
            )
            if args.command == "run-case" and result["state"] == "MESH_ACCEPTED":
                result = solve_case(
                    manifest_path=args.manifest,
                    campaign_root=args.campaign_root,
                    case_index=args.case_index,
                    mpi_np=args.np,
                    dry_run=args.dry_run,
                    retain_surface_solution=args.retain_surface_solution,
                    retry_rejected=args.retry_rejected,
                )
        elif args.command == "solve-case":
            result = solve_case(
                manifest_path=args.manifest,
                campaign_root=args.campaign_root,
                case_index=args.case_index,
                mpi_np=args.np,
                dry_run=args.dry_run,
                retain_surface_solution=args.retain_surface_solution,
                retry_rejected=args.retry_rejected,
            )
        elif args.command == "collect":
            collect_result = collect(args.campaign_root, args.manifest, args.output)
            result = {
                "schema": collect_result["schema"],
                "summary": str(args.output.resolve()),
                "summary_csv": str(args.output.with_suffix(".csv").resolve()),
                "counts": collect_result["counts"],
            }
        else:
            raise RuntimeError("unhandled command: " + str(args.command))
    except Exception as error:
        try:
            error_path = _record_worker_error(args, error)
        except Exception:
            error_path = None
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "type": type(error).__name__,
                    "error": str(error),
                    "error_report": str(error_path) if error_path else None,
                }
            )
        )
        return 1
    print(json.dumps({"status": "OK", "result": result}, indent=2, default=_default))
    state = result.get("state") if isinstance(result, dict) else None
    return 2 if state in {"MESH_REJECTED", "CFD_REJECTED"} else 0


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./S6_bounded_mesh_atlas/cfd_qc.py =====

"""Independent post-solve quality checks for S6 CFD cases."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import h5py
import numpy as np

YPLUS_SCHEMA = "aeris.mesh.s6_wall_yplus.v1"
YPLUS_TARGET = 1.0
YPLUS_P95_MAX = 1.0
YPLUS_P99_MAX = 2.0
YPLUS_ABSOLUTE_MAX = 5.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wall_yplus_summary(
    surface_cgns: Path,
    *,
    target: float = YPLUS_TARGET,
    p95_max: float = YPLUS_P95_MAX,
    p99_max: float = YPLUS_P99_MAX,
    absolute_max: float = YPLUS_ABSOLUTE_MAX,
) -> dict[str, Any]:
    """Read YPlus only from ADflow no-slip wall zones and apply frozen limits."""
    surface_cgns = Path(surface_cgns).resolve()
    arrays: list[np.ndarray] = []
    zones: set[str] = set()

    with h5py.File(surface_cgns, "r") as handle:

        def collect(name: str, obj: Any) -> None:
            if not isinstance(obj, h5py.Dataset):
                return
            parts = name.split("/")
            zone = next(
                (part for part in parts if part.casefold().startswith("nswall")),
                None,
            )
            if zone is None or "yplus" not in {part.casefold() for part in parts}:
                return
            values = np.asarray(obj[()]).reshape(-1)
            if values.size:
                arrays.append(values.astype(float, copy=False))
                zones.add(zone)

        handle.visititems(collect)

    thresholds = {
        "target": float(target),
        "p95_max": float(p95_max),
        "p99_max": float(p99_max),
        "absolute_max": float(absolute_max),
    }
    if not arrays:
        return {
            "schema": YPLUS_SCHEMA,
            "passed": False,
            "failure_reasons": ["no_wall_yplus_fields"],
            "surface_cgns": str(surface_cgns),
            "surface_cgns_sha256": _sha256(surface_cgns),
            "thresholds": thresholds,
            "wall_zone_count": 0,
            "sample_count": 0,
        }

    values = np.concatenate(arrays)
    finite_mask = np.isfinite(values)
    finite = values[finite_mask]
    nonfinite_count = int(values.size - finite.size)
    negative_count = int(np.count_nonzero(finite < 0.0))
    if finite.size:
        statistics = {
            "minimum": float(np.min(finite)),
            "mean": float(np.mean(finite)),
            "p50": float(np.percentile(finite, 50.0)),
            "p95": float(np.percentile(finite, 95.0)),
            "p99": float(np.percentile(finite, 99.0)),
            "maximum": float(np.max(finite)),
            "fraction_at_or_below_target": float(np.mean(finite <= target)),
        }
    else:
        statistics = {
            key: None
            for key in (
                "minimum",
                "mean",
                "p50",
                "p95",
                "p99",
                "maximum",
                "fraction_at_or_below_target",
            )
        }

    failures: list[str] = []
    if nonfinite_count:
        failures.append("nonfinite_yplus")
    if negative_count:
        failures.append("negative_yplus")
    if not finite.size:
        failures.append("no_finite_yplus")
    else:
        if statistics["p95"] > p95_max:
            failures.append("p95_above_limit")
        if statistics["p99"] > p99_max:
            failures.append("p99_above_limit")
        if statistics["maximum"] > absolute_max:
            failures.append("maximum_above_limit")

    return {
        "schema": YPLUS_SCHEMA,
        "passed": not failures,
        "failure_reasons": failures,
        "surface_cgns": str(surface_cgns),
        "surface_cgns_sha256": _sha256(surface_cgns),
        "thresholds": thresholds,
        "wall_zone_count": len(zones),
        "dataset_count": len(arrays),
        "sample_count": int(values.size),
        "nonfinite_count": nonfinite_count,
        "negative_count": negative_count,
        "statistics": statistics,
    }


===== FILE: ./S6_bounded_mesh_atlas/deform.py =====

"""Bounded, column-preserving deformation of an S6 structured volume mesh."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from shared.volume_qc import volume_report  # noqa: E402

from aeris.cfd.meshing.volume_audit import (  # noqa: E402
    _iter_zone_coordinate_arrays,
    read_volume_blocks,
)

Array = np.ndarray
DEFORMATION_SCHEMA = "aeris.mesh.s6_bounded_deformation.v1"
WALL_TOLERANCE_M = 1.0e-10
PRODUCTION_MIN_SCALED_QUALITY = 0.10


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_surface_blocks(path: Path) -> dict[str, Array]:
    """Load surface blocks while preserving their Plot3D/NPZ insertion order."""
    with np.load(Path(path)) as archive:
        return {name: np.asarray(archive[name], dtype=float) for name in archive.files}


def _surface_points(blocks: dict[str, Array]) -> Array:
    if not blocks:
        raise ValueError("surface block set is empty")
    return np.concatenate([block.reshape(-1, 3) for block in blocks.values()])


def _characteristic_length(blocks: dict[str, Array]) -> float:
    points = _surface_points(blocks)
    length = float(np.linalg.norm(np.ptp(points, axis=0)))
    if not np.isfinite(length) or length <= 0.0:
        raise ValueError("surface characteristic length must be finite and positive")
    return length


def first_layer_spacing_report(
    blocks: dict[str, Array], *, characteristic_length_m: float
) -> dict[str, Any]:
    """Measure the realized wall-normal first edge without imposing a y+ gate."""
    if not np.isfinite(characteristic_length_m) or characteristic_length_m <= 0.0:
        raise ValueError("characteristic length must be finite and positive")
    per_zone: dict[str, dict[str, float | int]] = {}
    values: list[Array] = []
    for zone, nodes in blocks.items():
        if nodes.shape[0] < 2:
            raise ValueError(f"volume zone {zone} has no first off-wall layer")
        spacing = np.linalg.norm(nodes[1] - nodes[0], axis=-1).reshape(-1)
        values.append(spacing)
        finite = spacing[np.isfinite(spacing)]
        per_zone[zone] = {
            "count": int(spacing.size),
            "nonfinite_count": int(spacing.size - finite.size),
            "nonpositive_count": int(np.count_nonzero(finite <= 0.0)),
            "min_m": float(np.min(finite)) if finite.size else float("nan"),
            "median_m": float(np.median(finite)) if finite.size else float("nan"),
            "max_m": float(np.max(finite)) if finite.size else float("nan"),
        }
    combined = np.concatenate(values) if values else np.empty(0)
    finite = combined[np.isfinite(combined)]
    positive = finite[finite > 0.0]
    stats = {
        "count": int(combined.size),
        "nonfinite_count": int(combined.size - finite.size),
        "nonpositive_count": int(np.count_nonzero(finite <= 0.0)),
        "min_m": float(np.min(positive)) if positive.size else float("nan"),
        "p05_m": float(np.quantile(positive, 0.05)) if positive.size else float("nan"),
        "median_m": float(np.median(positive)) if positive.size else float("nan"),
        "p95_m": float(np.quantile(positive, 0.95)) if positive.size else float("nan"),
        "max_m": float(np.max(positive)) if positive.size else float("nan"),
        "characteristic_length_m": characteristic_length_m,
        "per_zone": per_zone,
    }
    for key in ("min_m", "p05_m", "median_m", "p95_m", "max_m"):
        stats[key.replace("_m", "_fraction_characteristic")] = stats[key] / characteristic_length_m
    return stats


def _root_le_and_scales(
    template_surface: dict[str, Array],
    target_surface: dict[str, Array],
) -> tuple[Array, Array, Array]:
    """Return template anchor, target anchor, and chord/span/chord scales."""

    def measurements(blocks: dict[str, Array]) -> tuple[Array, float, float]:
        points = _surface_points(blocks)
        y_min = float(points[:, 1].min())
        span = float(points[:, 1].max() - y_min)
        tolerance = max(1.0e-10, span * 1.0e-8)
        root = points[np.abs(points[:, 1] - y_min) <= tolerance]
        if len(root) < 2:
            raise ValueError("could not identify the root section")
        chord = float(root[:, 0].max() - root[:, 0].min())
        if chord <= 0.0 or span <= 0.0:
            raise ValueError("template and target must have positive root chord and span")
        anchor = root[int(np.argmin(root[:, 0]))].copy()
        return anchor, chord, span

    template_anchor, template_chord, template_span = measurements(template_surface)
    target_anchor, target_chord, target_span = measurements(target_surface)
    chord_scale = target_chord / template_chord
    scales = np.array([chord_scale, target_span / template_span, chord_scale])
    return template_anchor, target_anchor, scales


def _ordered_pairs(
    volume_blocks: dict[str, Array],
    surface_blocks: dict[str, Array],
) -> list[tuple[str, str]]:
    if len(volume_blocks) != len(surface_blocks):
        raise ValueError(
            f"block-count mismatch: volume={len(volume_blocks)}, surface={len(surface_blocks)}"
        )
    return list(zip(volume_blocks, surface_blocks, strict=True))


def validate_template_correspondence(
    volume_blocks: dict[str, Array],
    template_surface: dict[str, Array],
    *,
    tolerance_m: float = WALL_TOLERANCE_M,
) -> dict[str, Any]:
    """Prove that volume zone order and surface-block order are equivalent."""
    errors: dict[str, float] = {}
    for zone, surface_name in _ordered_pairs(volume_blocks, template_surface):
        volume = np.asarray(volume_blocks[zone], dtype=float)
        surface = np.asarray(template_surface[surface_name], dtype=float)
        expected_shape = (surface.shape[1], surface.shape[0], 3)
        if volume[0].shape != expected_shape:
            raise ValueError(
                f"{zone}/{surface_name} wall shape {volume[0].shape} "
                f"does not match {expected_shape}"
            )
        errors[zone] = float(np.max(np.abs(volume[0] - surface.transpose(1, 0, 2))))
    maximum = max(errors.values(), default=float("inf"))
    if maximum > tolerance_m:
        raise ValueError(f"template CGNS wall does not match template surface: {maximum:.3e} m")
    return {"max_wall_error_m": maximum, "per_zone_max_wall_error_m": errors}


def _common_layer_fraction(blocks: dict[str, Array]) -> Array:
    """One physical-distance weight shared by every block and interface node."""
    layer_spacings = []
    n_layers: int | None = None
    for nodes in blocks.values():
        if n_layers is None:
            n_layers = int(nodes.shape[0])
        elif nodes.shape[0] != n_layers:
            raise ValueError("all connected blocks must have the same layer count")
        segment = np.linalg.norm(np.diff(nodes, axis=0), axis=-1)
        layer_spacings.append(np.median(segment.reshape(segment.shape[0], -1), axis=1))
    if n_layers is None or n_layers < 2:
        raise ValueError("volume needs at least one block with two marching layers")
    spacing = np.median(np.stack(layer_spacings), axis=0)
    cumulative = np.concatenate([[0.0], np.cumsum(spacing)])
    if cumulative[-1] <= 0.0:
        raise ValueError("volume has zero wall-to-farfield distance")
    return (cumulative / cumulative[-1]).reshape(-1, 1, 1)


def volume_interface_report(
    blocks: dict[str, Array],
    *,
    wall_pair_tolerance_m: float = 1.0e-8,
) -> dict[str, Any]:
    """Measure every inter-block side face found from its common wall edge."""
    faces: list[dict[str, Any]] = []
    for zone, nodes in blocks.items():
        candidates = {
            "i0": nodes[:, :, 0, :],
            "i1": nodes[:, :, -1, :],
            "j0": nodes[:, 0, :, :],
            "j1": nodes[:, -1, :, :],
        }
        for side, face in candidates.items():
            faces.append({"zone": zone, "side": side, "nodes": face})

    used: set[int] = set()
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(faces):
        if left_index in used:
            continue
        left_wall = left["nodes"][0]
        best: tuple[float, int, bool] | None = None
        for right_index in range(left_index + 1, len(faces)):
            if right_index in used:
                continue
            right = faces[right_index]
            if left["zone"] == right["zone"]:
                continue
            right_wall = right["nodes"][0]
            if left_wall.shape != right_wall.shape:
                continue
            direct = float(np.max(np.abs(left_wall - right_wall)))
            reverse = float(np.max(np.abs(left_wall - right_wall[::-1])))
            candidate = (direct, right_index, False)
            if reverse < direct:
                candidate = (reverse, right_index, True)
            if best is None or candidate[0] < best[0]:
                best = candidate
        if best is None or best[0] > wall_pair_tolerance_m:
            continue
        _wall_error, right_index, reverse = best
        right = faces[right_index]
        right_nodes = right["nodes"][:, ::-1, :] if reverse else right["nodes"]
        mismatch = float(np.max(np.abs(left["nodes"] - right_nodes)))
        used.update((left_index, right_index))
        pairs.append(
            {
                "left": f"{left['zone']}:{left['side']}",
                "right": f"{right['zone']}:{right['side']}",
                "max_mismatch_m": mismatch,
            }
        )

    unmatched = [
        f"{face['zone']}:{face['side']}" for index, face in enumerate(faces) if index not in used
    ]
    return {
        "paired_face_count": len(pairs),
        "max_mismatch_m": max((pair["max_mismatch_m"] for pair in pairs), default=float("inf")),
        "pairs": pairs,
        "unmatched_side_faces": unmatched,
    }


def deform_volume_blocks(
    template_volume: dict[str, Array],
    template_surface: dict[str, Array],
    target_surface: dict[str, Array],
) -> tuple[dict[str, Array], dict[str, Any]]:
    """Map a template volume to an exact target wall with zero farfield residual.

    A global chord/span affine map handles the large design change. The remaining
    wall displacement is propagated down each existing marching column with a
    C1 weight whose derivative is zero at the wall. This protects the first-cell
    spacing and preserves the fixed multiblock graph.
    """
    validate_template_correspondence(template_volume, template_surface)
    if list(template_surface) != list(target_surface):
        raise ValueError("target surface block names/order differ from the template")
    for name in template_surface:
        if template_surface[name].shape != target_surface[name].shape:
            raise ValueError(
                f"target block {name} has shape {target_surface[name].shape}, "
                f"expected {template_surface[name].shape}"
            )

    template_anchor, target_anchor, scales = _root_le_and_scales(template_surface, target_surface)
    eta = _common_layer_fraction(template_volume)
    deformed: dict[str, Array] = {}
    wall_errors: dict[str, float] = {}
    displacement_max = 0.0

    for zone, surface_name in _ordered_pairs(template_volume, template_surface):
        source = np.asarray(template_volume[zone], dtype=float)
        affine = target_anchor + (source - template_anchor) * scales
        target_wall = target_surface[surface_name].transpose(1, 0, 2)
        residual = target_wall - affine[0]
        weight = (1.0 - eta * eta) ** 2
        mapped = affine + weight[..., None] * residual[None, ...]
        deformed[zone] = mapped
        error = float(np.max(np.abs(mapped[0] - target_wall)))
        wall_errors[zone] = error
        displacement_max = max(
            displacement_max,
            float(np.max(np.linalg.norm(mapped - affine, axis=-1))),
        )

    maximum_wall_error = max(wall_errors.values(), default=float("inf"))
    template_interfaces = volume_interface_report(template_volume)
    deformed_interfaces = volume_interface_report(deformed)
    template_characteristic_length = _characteristic_length(template_surface)
    target_characteristic_length = _characteristic_length(target_surface)
    metadata = {
        "template_anchor_m": template_anchor.tolist(),
        "target_anchor_m": target_anchor.tolist(),
        "affine_scale_xyz": scales.tolist(),
        "residual_weight": "(1-common_normalized_physical_layer_distance^2)^2",
        "max_residual_displacement_m": displacement_max,
        "max_wall_error_m": maximum_wall_error,
        "per_zone_max_wall_error_m": wall_errors,
        "template_interfaces": template_interfaces,
        "deformed_interfaces": deformed_interfaces,
        "first_layer_spacing": {
            "status": "diagnostic_pending_production_yplus_validation",
            "template": first_layer_spacing_report(
                template_volume,
                characteristic_length_m=template_characteristic_length,
            ),
            "deformed": first_layer_spacing_report(
                deformed,
                characteristic_length_m=target_characteristic_length,
            ),
        },
    }
    return deformed, metadata


def written_deformation_metadata(
    written_blocks: dict[str, Array],
    target_surface: dict[str, Array],
    deformation: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild wall, interface, and spacing evidence from a re-opened CGNS."""
    correspondence = validate_template_correspondence(written_blocks, target_surface)
    target_characteristic_length = _characteristic_length(target_surface)
    spacing = dict(deformation.get("first_layer_spacing", {}))
    spacing["deformed"] = first_layer_spacing_report(
        written_blocks,
        characteristic_length_m=target_characteristic_length,
    )
    return {
        **deformation,
        **correspondence,
        "deformed_interfaces": volume_interface_report(written_blocks),
        "first_layer_spacing": spacing,
    }


def write_volume_blocks(
    template_cgns: Path,
    output_cgns: Path,
    blocks: dict[str, Array],
) -> Path:
    """Copy a structured CGNS template and replace only its coordinate arrays."""
    import h5py

    template_cgns = Path(template_cgns)
    output_cgns = Path(output_cgns)
    output_cgns.parent.mkdir(parents=True, exist_ok=True)
    if template_cgns.resolve() == output_cgns.resolve():
        raise ValueError("output CGNS must differ from the immutable template")
    shutil.copy2(template_cgns, output_cgns)
    with h5py.File(str(output_cgns), "r+") as handle:
        zones = list(_iter_zone_coordinate_arrays(handle))
        if [name for name, _ in zones] != list(blocks):
            raise ValueError("CGNS zone order/names differ from the deformed blocks")
        for (zone, arrays), (block_name, xyz) in zip(zones, blocks.items(), strict=True):
            if zone != block_name:
                raise ValueError(f"zone mismatch: {zone} != {block_name}")
            for axis, dataset in enumerate(arrays):
                if dataset.shape != xyz[..., axis].shape:
                    raise ValueError(
                        f"{zone} coordinate shape {dataset.shape} "
                        f"does not match {xyz[..., axis].shape}"
                    )
                dataset[...] = xyz[..., axis]
    return output_cgns


def acceptance_report(
    blocks: dict[str, Array],
    deformation: dict[str, Any],
    *,
    production_floor: float = PRODUCTION_MIN_SCALED_QUALITY,
) -> dict[str, Any]:
    quality = volume_report(blocks)
    hard_reasons: list[str] = []
    if deformation["max_wall_error_m"] > WALL_TOLERANCE_M:
        hard_reasons.append("wall_fidelity")
    template_interfaces = deformation["template_interfaces"]
    interfaces = deformation["deformed_interfaces"]
    template_pairs = {
        tuple(sorted((pair["left"], pair["right"]))) for pair in template_interfaces["pairs"]
    }
    deformed_pairs = {tuple(sorted((pair["left"], pair["right"]))) for pair in interfaces["pairs"]}
    if (
        interfaces["paired_face_count"] != template_interfaces["paired_face_count"]
        or deformed_pairs != template_pairs
        or (interfaces["paired_face_count"] > 0 and interfaces["max_mismatch_m"] > WALL_TOLERANCE_M)
    ):
        hard_reasons.append("nonconformal_block_interfaces")
    if not quality.get("generation_completed", False):
        hard_reasons.append("generation")
    if quality.get("inverted_cells", 1) != 0:
        hard_reasons.append("inverted_cells")
    if not float(quality.get("min_volume", -1.0)) > 0.0:
        hard_reasons.append("positive_volume")
    if not float(quality.get("min_scaled_quality", -1.0)) > 0.0:
        hard_reasons.append("positive_scaled_quality")
    spacing = deformation.get("first_layer_spacing", {}).get("deformed", {})
    if spacing and (
        int(spacing.get("nonfinite_count", 1)) != 0 or int(spacing.get("nonpositive_count", 1)) != 0
    ):
        hard_reasons.append("invalid_first_layer_spacing")
    min_quality = float(quality.get("min_scaled_quality", -1.0))
    return {
        "hard_gate_passed": not hard_reasons,
        "hard_gate_failure_reasons": hard_reasons,
        "production_floor": production_floor,
        "production_floor_passed": not hard_reasons and min_quality >= production_floor,
        "quality": quality,
    }


def deform_cgns(
    *,
    template_cgns: Path,
    template_surface_npz: Path,
    target_surface_npz: Path,
    output_cgns: Path,
    report_path: Path | None = None,
    production_floor: float = PRODUCTION_MIN_SCALED_QUALITY,
) -> dict[str, Any]:
    """Run, write, and independently score one atlas deformation."""
    template_surface = load_surface_blocks(template_surface_npz)
    target_surface = load_surface_blocks(target_surface_npz)
    template_volume = read_volume_blocks(Path(template_cgns))
    blocks, deformation = deform_volume_blocks(template_volume, template_surface, target_surface)
    in_memory_acceptance = acceptance_report(blocks, deformation, production_floor=production_floor)
    write_volume_blocks(template_cgns, output_cgns, blocks)
    written = read_volume_blocks(Path(output_cgns))
    written_metadata = written_deformation_metadata(written, target_surface, deformation)
    acceptance = acceptance_report(written, written_metadata, production_floor=production_floor)
    report = {
        "schema": DEFORMATION_SCHEMA,
        "template_cgns": str(template_cgns),
        "template_cgns_sha256": sha256(template_cgns),
        "template_surface_npz": str(template_surface_npz),
        "template_surface_sha256": sha256(template_surface_npz),
        "target_surface_npz": str(target_surface_npz),
        "target_surface_sha256": sha256(target_surface_npz),
        "output_cgns": str(output_cgns),
        "output_cgns_sha256": sha256(output_cgns),
        "deformation": written_metadata,
        "in_memory_acceptance": in_memory_acceptance,
        "acceptance": acceptance,
    }
    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return report


===== FILE: ./S6_bounded_mesh_atlas/development_atlas.py =====

#!/usr/bin/env python3
"""Validate nearest-template S6 deformation on the 100-case development set."""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (HERE, REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from atlas import ATLAS_SCHEMA, normalize_matrix, rms_distance  # noqa: E402
from deform import (  # noqa: E402
    acceptance_report,
    deform_volume_blocks,
    load_surface_blocks,
    sha256,
    write_volume_blocks,
    written_deformation_metadata,
)
from resolution import epsilon_tag  # noqa: E402
from shared.gates import EPSE_LADDER  # noqa: E402
from shared.geometry_sets import design_matrix, geometry_id  # noqa: E402
from shared.qc import write_surface_artifacts  # noqa: E402
from strategy_s6 import build_pygeo_case, build_surface  # noqa: E402

from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS  # noqa: E402
from aeris.cfd.meshing.volume_audit import read_volume_blocks  # noqa: E402

S1_ROOT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies" / "S1_tip_first/L2_smoke/smoke"


def _default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_default) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


CHECKPOINT_SCHEMA = "aeris.mesh.s6_atlas_checkpoint.v2"
REPORT_SCHEMA = "aeris.mesh.s6_atlas_development_validation.v2"


def _template_paths(index: int, template_root: Path, eps_e: float = 2.0) -> tuple[Path, Path]:
    directory = Path(template_root) / f"lhs100_seed42_{index:03d}" / epsilon_tag(eps_e)
    return directory / "wing_vol.cgns", directory / "surface_blocks.npz"


def _template_configuration(
    template_indices: list[int], template_root: Path, eps_e: float
) -> dict[str, Any]:
    fingerprints = []
    normal_points: set[int] = set()
    first_cell_fractions: list[float] = []
    for index in template_indices:
        cgns, surface = _template_paths(index, template_root, eps_e)
        options = cgns.parent / "pyhyp_options.json"
        prepare = cgns.parent.parent / "prepare_manifest.json"
        if not all(path.is_file() for path in (cgns, surface, options, prepare)):
            raise FileNotFoundError(f"template {index} is incomplete")
        native_options = json.loads(options.read_text(encoding="utf-8"))
        prepare_manifest = json.loads(prepare.read_text(encoding="utf-8"))
        normal_points.add(int(native_options["N"]))
        characteristic_length = float(prepare_manifest["characteristic_length"])
        first_cell_fractions.append(float(native_options["s0"]) / characteristic_length)
        fingerprints.append(
            {
                "geometry_index": index,
                "cgns_sha256": sha256(cgns),
                "surface_npz_sha256": sha256(surface),
                "pyhyp_options_sha256": sha256(options),
            }
        )
    if len(normal_points) != 1:
        raise ValueError("development atlas mixes normal resolutions")
    if not np.allclose(
        first_cell_fractions,
        first_cell_fractions[0],
        rtol=1.0e-12,
        atol=0.0,
    ):
        raise ValueError("development atlas mixes first-cell-height laws")
    points = next(iter(normal_points))
    matches = [
        level for level in ("smoke", "fine", "production") if int(GRID_LEVELS[level]["N"]) == points
    ]
    if len(matches) != 1:
        raise ValueError(f"unsupported S6 normal resolution N={points}")
    return {
        "volume_level": matches[0],
        "normal_points": points,
        "first_cell_fraction_characteristic": first_cell_fractions[0],
        "eps_e": eps_e,
        "template_fingerprints": fingerprints,
    }


def validate(
    *,
    output: Path,
    template_indices: list[int],
    candidate_count: int = 0,
    geometry_indices: list[int] | None = None,
    template_root: Path = S1_ROOT,
    resume: bool = True,
    preferred_quality: float = 0.15,
    eps_e: float = 2.0,
    retain_written_meshes: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    if not template_indices or len(template_indices) != len(set(template_indices)):
        raise ValueError("template indices must be non-empty and unique")
    matrix, names = design_matrix("lhs100_seed42")
    normalized = normalize_matrix(matrix, names)
    template_configuration = _template_configuration(template_indices, Path(template_root), eps_e)
    if candidate_count < 0:
        raise ValueError("candidate count cannot be negative")
    candidate_count = (
        len(template_indices)
        if candidate_count == 0
        else min(candidate_count, len(template_indices))
    )
    if preferred_quality < 0.10:
        raise ValueError("preferred quality must be at least the production floor")
    distances = np.stack(
        [rms_distance(normalized, normalized[index]) for index in template_indices],
        axis=1,
    )
    if geometry_indices is None:
        geometry_indices = list(range(len(normalized)))
    if any(index < 0 or index >= len(normalized) for index in geometry_indices):
        raise ValueError("geometry indices must address the development set")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "atlas_validation_checkpoint.json"
    configuration = {
        "template_root": str(Path(template_root).resolve()),
        "template_indices": template_indices,
        "candidate_count": candidate_count,
        "preferred_quality": preferred_quality,
        "eps_e": eps_e,
        "retain_written_meshes": retain_written_meshes,
        "geometry_indices": geometry_indices,
        "template_configuration": template_configuration,
    }
    rows: list[dict[str, Any]] = []
    if resume and checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("configuration") != configuration:
            raise ValueError("existing checkpoint does not match this validation configuration")
        rows = list(checkpoint.get("rows", []))
    completed_indices = {int(row["geometry_index"]) for row in rows}

    for sequence, index in enumerate(geometry_indices, start=1):
        gid = geometry_id("lhs100_seed42", index)
        if index in completed_indices:
            print(
                f"{sequence:03d}/{len(geometry_indices):03d} {gid} RESUMED",
                flush=True,
            )
            continue
        ordered_slots = np.argsort(distances[index])[:candidate_count]
        attempts: list[dict[str, Any]] = []
        accepted_row: dict[str, Any] | None = None
        try:
            geometry_case = build_pygeo_case(
                "lhs100_seed42",
                index,
                output / "_geometry" / gid,
            )
            if geometry_case.pygeo_result is None:
                raise RuntimeError("canonical geometry did not produce pyGeo")
        except Exception as error:
            row = {
                "geometry_index": index,
                "geometry_id": gid,
                "state": "NEEDS_FALLBACK",
                "attempts": [
                    {
                        "state": "GEOMETRY_BUILD_ERROR",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                ],
                "accepted_template_index": None,
                "accepted_min_scaled_quality": None,
                "accepted_cgns": None,
                "accepted_cgns_sha256": None,
                "accepted_cgns_retained": False,
                "is_atlas_template_target": index in template_indices,
                "selected_identity_deformation": False,
            }
            rows.append(row)
            _write_json(
                checkpoint_path,
                {
                    "schema": CHECKPOINT_SCHEMA,
                    "configuration": configuration,
                    "rows": rows,
                },
            )
            print(
                f"{sequence:03d}/{len(geometry_indices):03d} {gid} NEEDS_FALLBACK template=None",
                flush=True,
            )
            continue
        for slot in ordered_slots:
            attempt_started = time.monotonic()
            template_index = template_indices[int(slot)]
            template_cgns, template_surface_path = _template_paths(
                template_index, template_root, eps_e
            )
            if not template_cgns.is_file() or not template_surface_path.is_file():
                attempts.append(
                    {
                        "template_index": template_index,
                        "state": "MISSING_TEMPLATE",
                        "elapsed_s": time.monotonic() - attempt_started,
                    }
                )
                continue

            template_surface = load_surface_blocks(template_surface_path)
            span_cells = int(next(iter(template_surface.values())).shape[1] - 1)
            try:
                blocks, surface_info = build_surface(
                    geometry_case.pygeo_result,
                    level="smoke",
                    span_cells=span_cells,
                )
            except Exception as error:
                attempts.append(
                    {
                        "template_index": template_index,
                        "distance_rms": float(distances[index, int(slot)]),
                        "state": "SURFACE_BUILD_ERROR",
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "elapsed_s": time.monotonic() - attempt_started,
                    }
                )
                continue
            surface_qc = surface_info["surface_qc"]
            fidelity = surface_info["fidelity"]
            if not surface_qc["accepted_pre_pyhyp"] or not fidelity["passed"]:
                attempts.append(
                    {
                        "template_index": template_index,
                        "distance_rms": float(distances[index, int(slot)]),
                        "state": "FAIL_SURFACE_GATE",
                        "surface_failure_reasons": surface_qc["failure_reasons"],
                        "surface_fidelity": fidelity,
                        "elapsed_s": time.monotonic() - attempt_started,
                    }
                )
                continue
            target_dir = output / "targets" / gid / f"from_{template_index:03d}"
            artifacts = write_surface_artifacts(blocks, target_dir)
            target_surface = load_surface_blocks(Path(artifacts["surface_npz"]["path"]))
            try:
                volume = read_volume_blocks(template_cgns)
                deformed, metadata = deform_volume_blocks(volume, template_surface, target_surface)
                acceptance = acceptance_report(deformed, metadata)
            except Exception as error:
                attempts.append(
                    {
                        "template_index": template_index,
                        "distance_rms": float(distances[index, int(slot)]),
                        "state": "DEFORMATION_ERROR",
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "elapsed_s": time.monotonic() - attempt_started,
                    }
                )
                volume = deformed = metadata = acceptance = None
                gc.collect()
                continue
            quality = acceptance["quality"]
            attempt = {
                "template_index": template_index,
                "distance_rms": float(distances[index, int(slot)]),
                "state": "FAIL",
                "surface_min_scaled_jacobian": surface_info["surface_qc"]["global"][
                    "min_scaled_jacobian"
                ],
                "surface_fidelity": fidelity,
                "wall_error_m": metadata["max_wall_error_m"],
                "inverted_cells": quality["inverted_cells"],
                "min_volume": quality["min_volume"],
                "min_scaled_quality": quality["min_scaled_quality"],
                "interface_pair_count": metadata["deformed_interfaces"]["paired_face_count"],
                "interface_max_mismatch_m": metadata["deformed_interfaces"]["max_mismatch_m"],
                "in_memory_acceptance": acceptance,
            }
            if not acceptance["production_floor_passed"]:
                attempt["elapsed_s"] = time.monotonic() - attempt_started
                attempts.append(attempt)
                volume = template_surface = target_surface = deformed = None
                gc.collect()
                continue

            candidate = target_dir / "wing_vol.cgns"
            try:
                write_volume_blocks(template_cgns, candidate, deformed)
                written = read_volume_blocks(candidate)
                written_metadata = written_deformation_metadata(written, target_surface, metadata)
                independent = acceptance_report(written, written_metadata)
            except Exception as error:
                candidate.unlink(missing_ok=True)
                attempt.update(
                    {
                        "state": "FAIL_WRITTEN_AUDIT",
                        "written_audit_error_type": type(error).__name__,
                        "written_audit_error": str(error),
                        "elapsed_s": time.monotonic() - attempt_started,
                    }
                )
                attempts.append(attempt)
                volume = template_surface = target_surface = deformed = None
                gc.collect()
                continue

            written_quality = independent["quality"]
            attempt.update(
                {
                    "state": (
                        "PASS" if independent["production_floor_passed"] else "FAIL_WRITTEN_AUDIT"
                    ),
                    "wall_error_m": written_metadata["max_wall_error_m"],
                    "inverted_cells": written_quality["inverted_cells"],
                    "min_volume": written_quality["min_volume"],
                    "min_scaled_quality": written_quality["min_scaled_quality"],
                    "interface_pair_count": written_metadata["deformed_interfaces"][
                        "paired_face_count"
                    ],
                    "interface_max_mismatch_m": written_metadata["deformed_interfaces"][
                        "max_mismatch_m"
                    ],
                    "first_layer_spacing": written_metadata["first_layer_spacing"],
                    "independent_written_acceptance": independent,
                    "candidate_cgns": str(candidate.resolve()),
                    "candidate_cgns_sha256": sha256(candidate),
                    "elapsed_s": time.monotonic() - attempt_started,
                }
            )
            attempts.append(attempt)
            if attempt["state"] != "PASS":
                candidate.unlink(missing_ok=True)
            elif (
                accepted_row is None
                or attempt["min_scaled_quality"] > accepted_row["min_scaled_quality"]
            ):
                if accepted_row is not None:
                    Path(accepted_row["candidate_cgns"]).unlink(missing_ok=True)
                accepted_row = attempt
            else:
                candidate.unlink(missing_ok=True)
            volume = template_surface = target_surface = deformed = written = None
            gc.collect()
            if accepted_row is not None and accepted_row["min_scaled_quality"] >= preferred_quality:
                break

        for attempt in attempts:
            attempt["selected"] = attempt is accepted_row

        row = {
            "geometry_index": index,
            "geometry_id": gid,
            "state": "PASS" if accepted_row is not None else "NEEDS_FALLBACK",
            "attempts": attempts,
            "accepted_template_index": (accepted_row["template_index"] if accepted_row else None),
            "accepted_min_scaled_quality": (
                accepted_row["min_scaled_quality"] if accepted_row else None
            ),
            "accepted_cgns": (accepted_row["candidate_cgns"] if accepted_row else None),
            "accepted_cgns_sha256": (
                accepted_row["candidate_cgns_sha256"] if accepted_row else None
            ),
            "accepted_cgns_retained": bool(accepted_row and retain_written_meshes),
            "is_atlas_template_target": index in template_indices,
            "selected_identity_deformation": bool(
                accepted_row and accepted_row["template_index"] == index
            ),
        }
        rows.append(row)
        _write_json(
            checkpoint_path,
            {
                "schema": CHECKPOINT_SCHEMA,
                "configuration": configuration,
                "rows": rows,
            },
        )
        if accepted_row is not None and not retain_written_meshes:
            Path(accepted_row["candidate_cgns"]).unlink(missing_ok=True)
        print(
            f"{sequence:03d}/{len(geometry_indices):03d} {gid} {row['state']} "
            f"template={row['accepted_template_index']}",
            flush=True,
        )

    passed = sum(row["state"] == "PASS" for row in rows)
    qualities = [row["accepted_min_scaled_quality"] for row in rows if row["state"] == "PASS"]
    identity_rows = [row for row in rows if row["is_atlas_template_target"]]
    nonidentity_rows = [row for row in rows if not row["is_atlas_template_target"]]

    def subset_summary(subset: list[dict[str, Any]]) -> dict[str, Any]:
        subset_passed = sum(row["state"] == "PASS" for row in subset)
        return {
            "attempted": len(subset),
            "passed": subset_passed,
            "pass_fraction": subset_passed / len(subset) if subset else None,
        }

    report = {
        "schema": REPORT_SCHEMA,
        "set_name": "lhs100_seed42",
        "geometry_indices": geometry_indices,
        "template_indices": template_indices,
        "candidate_count": candidate_count,
        "preferred_quality": preferred_quality,
        "template_root": str(Path(template_root).resolve()),
        "eps_e": eps_e,
        "campaign_equivalent_written_cgns_audit": True,
        "accepted_meshes_retained": retain_written_meshes,
        **template_configuration,
        "attempted": len(rows),
        "passed": passed,
        "pass_fraction": passed / len(rows),
        "worst_min_scaled_quality": min(qualities) if qualities else None,
        "identity_target_summary": subset_summary(identity_rows),
        "nonidentity_target_summary": subset_summary(nonidentity_rows),
        "elapsed_s": time.monotonic() - started,
        "rows": rows,
    }
    _write_json(output / "atlas_validation_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--template-indices", type=int, nargs="+")
    selection.add_argument("--atlas-manifest", type=Path)
    parser.add_argument(
        "--candidate-count",
        type=int,
        default=0,
        help="maximum templates per target; zero tries the complete atlas",
    )
    parser.add_argument("--preferred-quality", type=float, default=0.15)
    parser.add_argument("--indices", type=int, nargs="+")
    parser.add_argument("--template-root", type=Path, default=S1_ROOT)
    parser.add_argument("--eps-e", type=float, choices=EPSE_LADDER, default=2.0)
    parser.add_argument("--retain-written-meshes", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()
    if args.atlas_manifest is not None:
        atlas_manifest = json.loads(args.atlas_manifest.read_text(encoding="utf-8"))
        if atlas_manifest.get("schema") != ATLAS_SCHEMA:
            raise ValueError("not a current S6 atlas manifest")
        if atlas_manifest.get("set_name") != "lhs100_seed42":
            raise ValueError("atlas manifest uses the wrong development set")
        template_indices = [int(index) for index in atlas_manifest["template_indices"]]
    else:
        template_indices = args.template_indices
    report = validate(
        output=args.output,
        template_indices=template_indices,
        candidate_count=args.candidate_count,
        geometry_indices=args.indices,
        template_root=args.template_root,
        resume=not args.no_resume,
        preferred_quality=args.preferred_quality,
        eps_e=args.eps_e,
        retain_written_meshes=args.retain_written_meshes,
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "attempted",
                    "passed",
                    "pass_fraction",
                    "worst_min_scaled_quality",
                    "elapsed_s",
                )
            },
            indent=2,
        )
    )
    return 0 if report["passed"] == report["attempted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./S6_bounded_mesh_atlas/FUTURE_EXTENSIONS.md =====

# Future AI and FFD extensions

These are deliberately outside the validated S6 core.

The implementation order and release gates are fixed in [ROADMAP.md](ROADMAP.md).

## FFD

pyGeo currently constructs each geometry directly from the BWB design variables.
A future free-form deformation layer can be useful for local shape optimization or
new variables that preserve topology.

The mesh route would remain unchanged:

1. FFD changes the exact pyGeo wall.
2. IDWarp, RBF, or S6 bounded deformation moves a validated volume mesh.
3. The same surface, interface, volume, and CFD gates decide acceptance.

FFD does not remove the need for mesh validation.

## AI

AI should first be used for decisions, not coordinate authority:

- rank atlas templates;
- predict deformation failure risk;
- predict CFD convergence risk;
- choose high-value CFD samples;
- build aerodynamic surrogates.

A graph neural network or neural operator could later predict mesh displacement.
It must still write a normal CGNS and pass every deterministic S6 gate. An AI-only
mesh is not accepted.

## Adoption rule

Add an AI or FFD backend only after the deterministic S6 pipeline is frozen and has
enough labeled cases. Compare it on the same locked development and holdout sets.
Adopt it only if it reduces time or failures without weakening any gate.

For this campaign, AI is likely to save more compute through adaptive CFD sampling
and aerodynamic surrogates than by replacing a deformation step that already takes
seconds.


===== FILE: ./S6_bounded_mesh_atlas/pilot.py =====

#!/usr/bin/env python3
"""Development-set pilot for deforming proven S1 volumes to exact S6 walls."""

from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (HERE, REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from deform import (  # noqa: E402
    acceptance_report,
    deform_volume_blocks,
    load_surface_blocks,
)
from shared.qc import write_surface_artifacts  # noqa: E402
from strategy_s6 import build_locked_surface  # noqa: E402

from aeris.cfd.meshing.volume_audit import read_volume_blocks  # noqa: E402

S1_ROOT = (
    REPO_ROOT
    / "AERIS_MESH_STUDY/artifacts/strategy_studies"
    / "S1_tip_first/L2_smoke/smoke"
)


def _default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def run_pilot(output: Path, indices: list[int]) -> dict[str, Any]:
    output = output.resolve()
    rows: list[dict[str, Any]] = []
    for index in indices:
        geometry_id = f"lhs100_seed42_{index:03d}"
        template_dir = S1_ROOT / geometry_id / "eps20"
        template_cgns = template_dir / "wing_vol.cgns"
        template_surface_path = template_dir / "surface_blocks.npz"
        if not template_cgns.is_file() or not template_surface_path.is_file():
            rows.append({"geometry_id": geometry_id, "state": "MISSING_S1_TEMPLATE"})
            continue

        template_surface = load_surface_blocks(template_surface_path)
        first_template_block = next(iter(template_surface.values()))
        span_cells = int(first_template_block.shape[1] - 1)
        blocks, surface_info, _case = build_locked_surface(
            "lhs100_seed42",
            index,
            output / "_geometry",
            level="smoke",
            span_cells=span_cells,
        )
        target_dir = output / "targets" / geometry_id
        artifacts = write_surface_artifacts(blocks, target_dir)
        (target_dir / "surface_report.json").write_text(
            json.dumps(surface_info, indent=2, sort_keys=True, default=_default) + "\n",
            encoding="utf-8",
        )

        volume = read_volume_blocks(template_cgns)
        target_surface = load_surface_blocks(Path(artifacts["surface_npz"]["path"]))
        deformed, metadata = deform_volume_blocks(
            volume, template_surface, target_surface
        )
        acceptance = acceptance_report(deformed, metadata)
        quality = acceptance["quality"]
        rows.append(
            {
                "geometry_id": geometry_id,
                "state": (
                    "PASS" if acceptance["production_floor_passed"] else "FAIL"
                ),
                "wall_error_m": metadata["max_wall_error_m"],
                "max_residual_displacement_m": metadata[
                    "max_residual_displacement_m"
                ],
                "inverted_cells": quality["inverted_cells"],
                "min_volume": quality["min_volume"],
                "min_scaled_quality": quality["min_scaled_quality"],
                "mean_scaled_quality": quality["mean_scaled_quality"],
                "production_floor": acceptance["production_floor"],
            }
        )
        del volume, template_surface, target_surface, deformed
        gc.collect()

    passes = sum(row["state"] == "PASS" for row in rows)
    qualities = [
        row["min_scaled_quality"] for row in rows if row["state"] == "PASS"
    ]
    report = {
        "schema": "aeris.mesh.s6_development_pilot.v1",
        "purpose": "S1 marched volume to exact S6 wall, same locked geometry",
        "indices": indices,
        "passed": passes,
        "attempted": len(indices),
        "pass_fraction": passes / len(indices) if indices else 0.0,
        "worst_min_scaled_quality": min(qualities) if qualities else None,
        "rows": rows,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "pilot_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=_default) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--indices", type=int, nargs="+", default=list(range(10)))
    args = parser.parse_args()
    report = run_pilot(args.output, args.indices)
    print(json.dumps(report, indent=2, default=_default))
    return 0 if report["passed"] == report["attempted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./S6_bounded_mesh_atlas/qualification.py =====

#!/usr/bin/env python3
"""Governed S6 grid/TE qualification and laptop-safe CFD smoke pilots."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (HERE, REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import campaign  # noqa: E402
import strategy_s6  # noqa: E402
from deform import (  # noqa: E402
    WALL_TOLERANCE_M,
    deform_cgns,
    load_surface_blocks,
    sha256,
    validate_template_correspondence,
    volume_interface_report,
)
from shared.pyhyp_runner import read_result  # noqa: E402
from shared.qc import write_surface_artifacts  # noqa: E402
from shared.volume_qc import volume_report  # noqa: E402

from aeris.cfd.case.spec import FlowConditions, SolveSpec  # noqa: E402
from aeris.cfd.meshing.pyhyp_extrude import (  # noqa: E402
    mach_aero_python,
    write_pyhyp_run_inputs,
)
from aeris.cfd.meshing.pyhyp_options import build_pyhyp_options  # noqa: E402
from aeris.cfd.meshing.volume_audit import read_volume_blocks  # noqa: E402
from aeris.cfd.solvers.base import get_solver_adapter  # noqa: E402

PLAN_SCHEMA = "aeris.mesh.s6_qualification_plan.v3"
LAPTOP_MESH_SCHEMA = "aeris.mesh.s6_laptop_mesh.v2"
LAPTOP_TEMPLATE_SCHEMA = "aeris.mesh.s6_laptop_template.v2"
LAPTOP_CFD_SCHEMA = "aeris.mesh.s6_laptop_cfd.v2"
LAPTOP_SUMMARY_SCHEMA = "aeris.mesh.s6_laptop_summary.v2"
LEGACY_AUDIT_SCHEMA = "aeris.mesh.s6_legacy_pilot_audit.v2"

DEVELOPMENT_SET = "lhs100_seed42"
GRID_GEOMETRIES = (42, 7, 95, 89, 96)
TE_GEOMETRIES = (42, 7, 95)
LAPTOP_GEOMETRIES = (42, 95, 7)
LAPTOP_TEMPLATE_ROUTES = {42: 42, 95: 95, 7: 95}
FLOW = {
    "alpha": 2.0,
    "mach": 0.2,
    "reynolds": 1.0e6,
    "temperature": 288.15,
}
DEFAULT_REGISTRY = (
    REPO_ROOT
    / "artifacts/s6_bounded_mesh_atlas"
    / "template_registry_qualified21_production_portable_v9.json"
)
PRODUCTION_FLOOR = 0.10
LAPTOP_SOLVER_PRESET = "rans_ank_nk_v1"
LAPTOP_RESIDUAL_ORDERS_MIN = 6.0
LAPTOP_FORCE_TAIL_RELATIVE_RANGE_MAX = 0.001
PLANNED_LAPTOP_MPI_PROCESSES = 4


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _reported_file_matches(report: dict[str, Any], path_field: str, hash_field: str) -> bool:
    path_value = report.get(path_field)
    expected = report.get(hash_field)
    if not isinstance(path_value, str) or not isinstance(expected, str):
        return False
    path = Path(path_value)
    return path.is_file() and sha256(path) == expected


def _laptop_raw_options() -> dict[str, Any]:
    return {
        "writeVolumeSolution": False,
        "writeSurfaceSolution": True,
        "monitorVariables": ["resrho", "resturb", "cl", "cd"],
        "NKSubspaceSize": campaign.NK_SUBSPACE_SIZE,
    }


def _laptop_solver_protocol() -> dict[str, Any]:
    return {
        "campaign_solver_implementation_sha256": (campaign._solver_implementation_sha256()),
        "qualification_sha256": sha256(Path(__file__)),
        "flow": FLOW,
        "preset": LAPTOP_SOLVER_PRESET,
        "raw_options": _laptop_raw_options(),
        "residual_orders_min": LAPTOP_RESIDUAL_ORDERS_MIN,
        "force_tail_relative_range_max": LAPTOP_FORCE_TAIL_RELATIVE_RANGE_MAX,
    }


def _laptop_solver_implementation_sha256() -> str:
    encoded = json.dumps(_laptop_solver_protocol(), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _laptop_mesh_implementation_sha256() -> str:
    inputs = {
        "campaign_mesh_implementation_sha256": campaign._mesh_implementation_sha256(),
        "qualification_sha256": sha256(Path(__file__)),
        "pyhyp_extrude_sha256": sha256(REPO_ROOT / "src/aeris/cfd/meshing/pyhyp_extrude.py"),
        "pyhyp_options_sha256": sha256(REPO_ROOT / "src/aeris/cfd/meshing/pyhyp_options.py"),
        "volume_audit_sha256": sha256(REPO_ROOT / "src/aeris/cfd/meshing/volume_audit.py"),
    }
    encoded = json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _primary_span_cells(surface_blocks: dict[str, np.ndarray]) -> int:
    counts = {int(nodes.shape[1] - 1) for nodes in surface_blocks.values()}
    if not counts or min(counts) < 1:
        raise ValueError("surface blocks do not contain a valid j-cell count")
    return max(counts)


def _grid_family() -> list[dict[str, Any]]:
    definitions = (
        ("G1_coarse", "smoke", 129, 7.2e-6),
        ("G2_medium", "medium", 193, 5.1e-6),
        ("G3_fine", "fine", 257, 3.6e-6),
    )
    rows = []
    for name, surface_level, normal_points, first_cell_fraction in definitions:
        spec = strategy_s6.LEVELS[surface_level]
        rows.append(
            {
                "name": name,
                "surface_level": surface_level,
                "chord_points": spec.chord_points,
                "end_points": spec.end_points,
                "collar_points": spec.collar_points,
                "span_cells": spec.span_cells,
                "normal_points": normal_points,
                "first_cell_fraction_characteristic": first_cell_fraction,
            }
        )
    return rows


def _te_variants() -> list[dict[str, Any]]:
    return [
        {
            "name": "TE_small",
            "te_abs_m": 0.0005,
            "te_floor_frac_local_chord": 0.0025,
        },
        {
            "name": "TE_baseline",
            "te_abs_m": 0.0010,
            "te_floor_frac_local_chord": 0.0050,
        },
        {
            "name": "TE_large",
            "te_abs_m": 0.0015,
            "te_floor_frac_local_chord": 0.0075,
        },
    ]


def build_qualification_plan() -> dict[str, Any]:
    """Return the governed development-only qualification experiment."""
    grid = _grid_family()
    for left, right in zip(grid[:-1], grid[1:], strict=True):
        for field in (
            "chord_points",
            "end_points",
            "collar_points",
            "span_cells",
            "normal_points",
        ):
            if int(right[field]) <= int(left[field]):
                raise RuntimeError(f"grid family does not refine {field}")
        if float(right["first_cell_fraction_characteristic"]) >= float(
            left["first_cell_fraction_characteristic"]
        ):
            raise RuntimeError("grid family does not refine first-cell spacing")

    te_variants = _te_variants()
    registry_hash = sha256(DEFAULT_REGISTRY)
    registry = _read_json(DEFAULT_REGISTRY)
    p0_span_cells = {
        str(int(template["geometry_index"])): int(template["span_cells"])
        for template in registry["templates"]
    }
    coefficient_floors = {"cl": 0.10, "cd": 0.01, "cmy": 0.05}
    maximum_relative_change = {"cl": 0.01, "cd": 0.03, "cmy": 0.02}
    grid_force_metric = {
        "formula": "abs(fine-medium)/max(abs(fine), coefficient_floor)",
        "coefficient_floors": coefficient_floors.copy(),
        "maximum_relative_change": maximum_relative_change.copy(),
    }
    te_force_metric = {
        "formula": "abs(variant-baseline)/max(abs(baseline), coefficient_floor)",
        "reference_variant": "TE_baseline",
        "coefficient_floors": coefficient_floors.copy(),
        "maximum_relative_change": maximum_relative_change.copy(),
    }
    return {
        "schema": PLAN_SCHEMA,
        "strategy": strategy_s6.STRATEGY_ID,
        "purpose": "freeze wall, trailing-edge, and true grid policy before hold-out",
        "development_set": DEVELOPMENT_SET,
        "holdout_accessed": False,
        "implementation_provenance": {
            "qualification_sha256": sha256(Path(__file__)),
            "strategy_s6_sha256": sha256(HERE / "strategy_s6.py"),
            "campaign_mesh_implementation_sha256": (campaign._mesh_implementation_sha256()),
            "campaign_solver_implementation_sha256": (campaign._solver_implementation_sha256()),
        },
        "preregistration_evidence": False,
        "history_note": (
            "the preserved v1 plan file was written after the laptop pilot; it records "
            "the earlier policy content but does not prove advance registration"
        ),
        "fixed_flow": FLOW,
        "execution_order": [
            "current_P0_candidate_yplus_on_development_cases",
            "calibrate_P0_wall_spacing_only_if_production_yplus_fails",
            "TE_sensitivity_on_G2",
            "three_grid_GCI_with_selected_TE",
            "confirm_selected_grid_TE_and_yplus",
            "freeze_policy_then_open_holdout_once",
        ],
        "current_candidate_wall_test": {
            "name": "P0_existing_atlas_candidate",
            "surface_level": "smoke",
            "chord_points": strategy_s6.LEVELS["smoke"].chord_points,
            "span_cells": {
                "mode": "geometry_dependent_from_selected_registry_template",
                "minimum": min(p0_span_cells.values()),
                "maximum": max(p0_span_cells.values()),
                "by_template_geometry": p0_span_cells,
            },
            "normal_points": 257,
            "first_cell_fraction_characteristic": 3.6e-6,
            "registry": DEFAULT_REGISTRY.relative_to(REPO_ROOT).as_posix(),
            "registry_sha256": registry_hash,
            "purpose": (
                "test the current 21-template candidate wall law and solver path; "
                "this is not a grid-convergence level"
            ),
            "limitations": [
                "P0 refines wall-normal points but retains smoke tangential resolution",
                "a P0 yplus pass does not establish force or drag grid convergence",
                "repeat yplus on the selected final tangential grid before policy freeze",
            ],
            "production_resolution_scope": (
                "wall_normal_candidate_only_at_smoke_tangential_resolution"
            ),
        },
        "grid_study": {
            "geometry_indices": list(GRID_GEOMETRIES),
            "levels": grid,
            "same_between_levels": [
                "master_geometry",
                "farfield_extent",
                "flow",
                "solver_and_turbulence_model",
                "convergence_and_acceptance_gates",
                "selected_TE_law",
            ],
            "outputs": ["cl", "cd", "cmy"],
            "method": "Richardson_extrapolation_and_GCI_using_effective_cell_size",
            "medium_to_fine_gate": grid_force_metric,
            "minimum_complete_geometries_for_100_case_campaign": 5,
        },
        "trailing_edge_study": {
            "geometry_indices": list(TE_GEOMETRIES),
            "screening_grid": "G2_medium",
            "confirmation_grid": "G3_fine",
            "variants": te_variants,
            "decision_rule": (
                "choose the smallest opening that passes every mesh and CFD hard gate; "
                "report force sensitivity, especially drag, and confirm it on G3"
            ),
            "material_change_metric": te_force_metric,
        },
        "laptop_smoke": {
            "geometry_indices": list(LAPTOP_GEOMETRIES),
            "template_routes": {
                str(index): template for index, template in LAPTOP_TEMPLATE_ROUTES.items()
            },
            "surface_level": "smoke",
            "normal_points": 65,
            "planned_mpi_processes": PLANNED_LAPTOP_MPI_PROCESSES,
            "purpose": "solver_path_and_rejection_logic_only",
            "production_claim_allowed": False,
            "production_wall_law_conclusion": "NOT_TESTED_AT_PRODUCTION_RESOLUTION",
            "limitations": [
                "N65 is coarser than G1 in the wall-normal direction",
                "the production first-cell height and march distance are reused on a coarse grid",
                "smoke tangential spacing can change the resolved wall shear",
                "yplus here is a rejection-logic screen, not wall-law calibration evidence",
            ],
        },
        "gci_validity_rule": (
            "use actual cell counts and unequal refinement ratios; report GCI only "
            "for finite, monotonic, asymptotic-looking sequences, otherwise report "
            "the raw grid envelope and mark the case non-asymptotic"
        ),
        "revision_note": (
            "v3 adds complete tip-grid refinement and machine-readable P0 limits; "
            "the preserved v1/v2 files were written after the pilot and are not "
            "preregistration evidence"
        ),
        "freeze_rule": (
            "do not access the locked holdout until wall yplus, TE, grid, solver, "
            "fallback, and acceptance policies are fixed"
        ),
    }


def write_plan(output: Path) -> dict[str, Any]:
    plan = build_qualification_plan()
    plan["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    _write_json(output, plan)
    return plan


def _case_id(index: int) -> str:
    if index < 0 or index >= 100:
        raise ValueError("laptop pilots must use development indices in [0, 100)")
    return f"{DEVELOPMENT_SET}_{index:03d}"


def _accepted_existing_template(
    path: Path,
    *,
    expected_registry_sha256: str,
    expected_implementation_sha256: str,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    report = _read_json(path)
    if (
        report.get("schema") == LAPTOP_TEMPLATE_SCHEMA
        and report.get("state") == "PASS"
        and report.get("source_registry_sha256") == expected_registry_sha256
        and report.get("mesh_implementation_sha256") == expected_implementation_sha256
        and _reported_file_matches(report, "cgns", "cgns_sha256")
        and _reported_file_matches(report, "source_cgns", "source_cgns_sha256")
        and _reported_file_matches(report, "surface_npz", "surface_npz_sha256")
        and _reported_file_matches(report, "source_pyhyp_options", "source_pyhyp_options_sha256")
        and _reported_file_matches(report, "source_surface_fmt", "source_surface_fmt_sha256")
    ):
        return report
    return None


def prepare_laptop_template(
    *,
    geometry_index: int,
    registry_path: Path,
    output: Path,
    timeout_s: float,
) -> dict[str, Any]:
    """Remarch one frozen production template at N=65 without changing s0."""
    template_dir = Path(output).resolve() / "_templates" / _case_id(geometry_index)
    report_path = template_dir / "template_report.json"
    registry_path = Path(registry_path).resolve()
    if not registry_path.is_file():
        raise FileNotFoundError(registry_path)
    registry_hash = sha256(registry_path)
    implementation_hash = _laptop_mesh_implementation_sha256()
    if existing := _accepted_existing_template(
        report_path,
        expected_registry_sha256=registry_hash,
        expected_implementation_sha256=implementation_hash,
    ):
        return existing

    registry = campaign._materialize_registry_assets(
        _read_json(registry_path),
        registry_path,
    )
    template = next(
        (row for row in registry["templates"] if int(row["geometry_index"]) == geometry_index),
        None,
    )
    if template is None:
        raise ValueError(f"production registry has no template {geometry_index}")
    campaign._verify_template_assets(template)
    native = _read_json(Path(template["pyhyp_options"]))
    surface_fmt = Path(template["surface_npz"]).with_name("surface.fmt")
    if not surface_fmt.is_file():
        raise FileNotFoundError(surface_fmt)
    characteristic_length = float(template["first_cell_height_m"]) / float(
        template["first_cell_fraction_characteristic"]
    )
    cgns = template_dir / "wing_vol_n65.cgns"
    template_dir.mkdir(parents=True, exist_ok=True)
    effective = build_pyhyp_options(
        surface_fmt.resolve(),
        level="production",
        characteristic_length=characteristic_length,
        output_file=cgns.resolve(),
        s0=float(native["s0"]),
        march_dist_factor=float(native["marchDist"]) / characteristic_length,
        n_grid=65,
        n_coarsen=int(native["coarsen"]),
        c_max=float(native["cMax"]),
        theta=float(native["theta"]),
        vol_coef=float(native["volCoef"]),
        eps_e_far=float(native["epsE"]),
        eps_i_far=float(native["epsI"]),
        vol_smooth_iter=int(native["volSmoothIter"]),
        vol_blend=float(native["volBlend"]),
        n_constant_start=int(native["nConstantStart"]),
        ksp_rel_tol=float(native["kspRelTol"]),
        ksp_max_its=int(native["kspMaxIts"]),
    )
    runner = write_pyhyp_run_inputs(template_dir, effective)
    returncode = campaign._run_with_timeout(
        [str(mach_aero_python()), str(runner)],
        template_dir,
        template_dir / "run_stdout.log",
        timeout_s,
    )
    march = read_result(template_dir) or {}
    if not cgns.is_file():
        raise RuntimeError(f"N=65 template {geometry_index} did not write CGNS")
    volume = read_volume_blocks(cgns)
    surface = load_surface_blocks(Path(template["surface_npz"]))
    correspondence = validate_template_correspondence(volume, surface)
    quality = volume_report(volume)
    interfaces = volume_interface_report(volume)
    passed = bool(
        returncode == 0
        and march.get("march_completed")
        and quality["inverted_cells"] == 0
        and float(quality["min_volume"]) > 0.0
        and float(quality["min_scaled_quality"]) >= PRODUCTION_FLOOR
        and correspondence["max_wall_error_m"] <= WALL_TOLERANCE_M
        and interfaces["paired_face_count"] == 20
        and interfaces["max_mismatch_m"] <= WALL_TOLERANCE_M
    )
    report = {
        "schema": LAPTOP_TEMPLATE_SCHEMA,
        "state": "PASS" if passed else "FAIL",
        "purpose": "N65_solver_smoke_template_with_production_wall_spacing",
        "production_claim_allowed": False,
        "source_registry": str(registry_path),
        "source_registry_sha256": registry_hash,
        "mesh_implementation_sha256": implementation_hash,
        "source_template_id": template["template_id"],
        "source_geometry_index": geometry_index,
        "source_cgns": template["cgns"],
        "source_cgns_sha256": template["cgns_sha256"],
        "surface_npz": template["surface_npz"],
        "surface_npz_sha256": template["surface_npz_sha256"],
        "source_pyhyp_options": template["pyhyp_options"],
        "source_pyhyp_options_sha256": template["pyhyp_options_sha256"],
        "source_surface_fmt": str(surface_fmt.resolve()),
        "source_surface_fmt_sha256": sha256(surface_fmt),
        "normal_points": 65,
        "first_cell_height_m": float(native["s0"]),
        "first_cell_fraction_characteristic": float(template["first_cell_fraction_characteristic"]),
        "eps_e": float(native["epsE"]),
        "return_code": returncode,
        "march": march,
        "correspondence": correspondence,
        "interfaces": interfaces,
        "quality": quality,
        "cgns": str(cgns.resolve()),
        "cgns_sha256": sha256(cgns),
    }
    _write_json(report_path, report)
    if not passed:
        raise RuntimeError(f"N=65 production-wall template {geometry_index} failed its gates")
    return report


def prepare_laptop_templates(
    *,
    indices: list[int],
    registry_path: Path,
    output: Path,
    timeout_s: float,
) -> dict[int, dict[str, Any]]:
    reports = {}
    for index in sorted(set(indices)):
        report = prepare_laptop_template(
            geometry_index=index,
            registry_path=registry_path,
            output=output,
            timeout_s=timeout_s,
        )
        reports[index] = report
        print(
            f"template {_case_id(index)} {report['state']} "
            f"qmin={report['quality']['min_scaled_quality']:.6f}",
            flush=True,
        )
    return reports


def _accepted_existing_mesh(
    path: Path,
    *,
    expected_template_sha256: str | None = None,
    expected_template_surface_sha256: str | None = None,
    expected_implementation_sha256: str | None = None,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    report = _read_json(path)
    mesh_path = Path(report.get("mesh_cgns", ""))
    if (
        report.get("schema") == LAPTOP_MESH_SCHEMA
        and report.get("state") == "MESH_ACCEPTED"
        and mesh_path.is_file()
        and report.get("mesh_cgns_sha256") == sha256(mesh_path)
        and (
            expected_template_sha256 is None
            or report.get("template_cgns_sha256") == expected_template_sha256
        )
        and (
            expected_template_surface_sha256 is None
            or report.get("template_surface_sha256") == expected_template_surface_sha256
        )
        and (
            expected_implementation_sha256 is None
            or report.get("mesh_implementation_sha256") == expected_implementation_sha256
        )
    ):
        return report
    return None


def prepare_laptop_case(
    *,
    index: int,
    output: Path,
    template_cgns: Path,
    template_surface: Path,
) -> dict[str, Any]:
    """Create and independently audit one exact-wall N=65 smoke mesh."""
    geometry_id = _case_id(index)
    case_dir = Path(output).resolve() / geometry_id
    report_path = case_dir / "mesh_report.json"
    template_cgns = Path(template_cgns).resolve()
    template_surface = Path(template_surface).resolve()
    if not template_cgns.is_file() or not template_surface.is_file():
        raise FileNotFoundError("the governed N=65 template assets are missing")
    template_hash = sha256(template_cgns)
    template_surface_hash = sha256(template_surface)
    implementation_hash = _laptop_mesh_implementation_sha256()
    if existing := _accepted_existing_mesh(
        report_path,
        expected_template_sha256=template_hash,
        expected_template_surface_sha256=template_surface_hash,
        expected_implementation_sha256=implementation_hash,
    ):
        return existing
    template_blocks = read_volume_blocks(template_cgns)
    normal_counts = {int(nodes.shape[0]) for nodes in template_blocks.values()}
    if normal_counts != {65}:
        raise ValueError(f"laptop template must have N=65, found {sorted(normal_counts)}")
    template_quality = volume_report(template_blocks)
    if (
        template_quality["inverted_cells"] != 0
        or float(template_quality["min_scaled_quality"]) < PRODUCTION_FLOOR
    ):
        raise ValueError("the N=65 template fails the fixed volume screen")
    surface_template_blocks = load_surface_blocks(template_surface)
    span_cells = _primary_span_cells(surface_template_blocks)

    geometry_case = strategy_s6.build_pygeo_case(
        DEVELOPMENT_SET,
        index,
        case_dir / "geometry_source",
    )
    if geometry_case.pygeo_result is None:
        raise RuntimeError("pyGeo did not produce the master geometry")
    surface_blocks, surface_info = strategy_s6.build_surface(
        geometry_case.pygeo_result,
        level="smoke",
        span_cells=span_cells,
    )
    if (
        not surface_info["surface_qc"]["accepted_pre_pyhyp"]
        or not surface_info["fidelity"]["passed"]
    ):
        raise RuntimeError(f"{geometry_id} failed the exact surface gates")
    surface_dir = case_dir / "surface"
    surface_artifacts = write_surface_artifacts(surface_blocks, surface_dir)
    _write_json(surface_dir / "surface_report.json", surface_info)

    mesh_path = case_dir / "mesh" / "wing_vol_n65.cgns"
    deformation_path = case_dir / "mesh" / "deformation_report.json"
    deformation = deform_cgns(
        template_cgns=template_cgns,
        template_surface_npz=template_surface,
        target_surface_npz=Path(surface_artifacts["surface_npz"]["path"]),
        output_cgns=mesh_path,
        report_path=deformation_path,
        production_floor=PRODUCTION_FLOOR,
    )
    accepted = bool(deformation["acceptance"]["production_floor_passed"])
    report = {
        "schema": LAPTOP_MESH_SCHEMA,
        "state": "MESH_ACCEPTED" if accepted else "MESH_REJECTED",
        "purpose": "laptop_solver_smoke_not_production_grid_validation",
        "production_claim_allowed": False,
        "development_set": DEVELOPMENT_SET,
        "holdout_accessed": False,
        "geometry_index": index,
        "geometry_id": geometry_id,
        "normal_points": 65,
        "span_cells": span_cells,
        "surface_level": "smoke",
        "te_law": surface_info["cfd_safe_te"],
        "template_cgns": str(template_cgns),
        "template_cgns_sha256": template_hash,
        "template_surface": str(template_surface),
        "template_surface_sha256": template_surface_hash,
        "mesh_implementation_sha256": implementation_hash,
        "mesh_cgns": str(mesh_path.resolve()),
        "mesh_cgns_sha256": sha256(mesh_path),
        "surface_artifacts": surface_artifacts,
        "surface_fidelity": surface_info["fidelity"],
        "acceptance": deformation["acceptance"],
        "deformation_report": str(deformation_path.resolve()),
        "reference_values": geometry_case.pygeo_result.reference_values,
    }
    _write_json(report_path, report)
    return report


def prepare_laptop_cases(
    *,
    indices: list[int],
    output: Path,
    registry_path: Path,
    timeout_s: float,
) -> list[dict[str, Any]]:
    missing_routes = [index for index in indices if index not in LAPTOP_TEMPLATE_ROUTES]
    if missing_routes:
        raise ValueError(f"no governed laptop template routes for {missing_routes}")
    routes = {index: LAPTOP_TEMPLATE_ROUTES[index] for index in indices}
    templates = prepare_laptop_templates(
        indices=list(routes.values()),
        registry_path=registry_path,
        output=output,
        timeout_s=timeout_s,
    )
    reports = []
    for index in indices:
        template_index = routes[index]
        template = templates[template_index]
        reports.append(
            prepare_laptop_case(
                index=index,
                output=output,
                template_cgns=Path(template["cgns"]),
                template_surface=Path(template["surface_npz"]),
            )
        )
        print(
            f"{_case_id(index)} via {_case_id(template_index)} "
            f"{reports[-1]['state']} "
            f"qmin={reports[-1]['acceptance']['quality']['min_scaled_quality']:.6f}",
            flush=True,
        )
    return reports


def _local_solver_path_passed(
    *,
    returncode: int,
    solver_status: str,
    residual_orders: float | None,
    force_plausibility: dict[str, Any],
    force_tail: dict[str, Any],
) -> bool:
    return bool(
        returncode == 0
        and solver_status == "converged"
        and residual_orders is not None
        and math.isfinite(float(residual_orders))
        and float(residual_orders) >= LAPTOP_RESIDUAL_ORDERS_MIN
        and force_plausibility["passed"]
        and force_tail["passed"]
    )


def _reported_yplus_surface_matches(report: dict[str, Any]) -> bool:
    gate = report.get("wall_yplus_gate")
    if not isinstance(gate, dict):
        return False
    surface = gate.get("surface_cgns")
    expected = gate.get("surface_cgns_sha256")
    if not isinstance(surface, str) or not isinstance(expected, str):
        return False
    path = Path(surface)
    return path.is_file() and sha256(path) == expected


def _existing_laptop_cfd_result(
    path: Path,
    *,
    mesh_sha256: str,
    implementation_sha256: str,
    mpi_np: int,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    report = _read_json(path)
    return (
        report
        if report.get("schema") == LAPTOP_CFD_SCHEMA
        and report.get("state") in {"LOCAL_SOLVER_PATH_PASSED", "LOCAL_SOLVER_PATH_FAILED"}
        and report.get("mesh_cgns_sha256") == mesh_sha256
        and report.get("solver_implementation_sha256") == implementation_sha256
        and report.get("mpi_processes") == mpi_np
        and _reported_file_matches(report, "solve_report", "solve_report_sha256")
        and _reported_file_matches(report, "solver_log", "solver_log_sha256")
        and _reported_yplus_surface_matches(report)
        else None
    )


def solve_laptop_case(
    *,
    index: int,
    output: Path,
    mpi_np: int,
    force: bool,
) -> dict[str, Any]:
    """Run one N=65 ADflow case and apply both smoke and production gates."""
    if mpi_np < 1:
        raise ValueError("mpi process count must be positive")
    geometry_id = _case_id(index)
    case_dir = Path(output).resolve() / geometry_id
    mesh_report = _accepted_existing_mesh(
        case_dir / "mesh_report.json",
        expected_implementation_sha256=_laptop_mesh_implementation_sha256(),
    )
    if mesh_report is None:
        raise RuntimeError(f"{geometry_id} has no accepted laptop mesh")
    cfd_dir = case_dir / "cfd"
    acceptance_path = cfd_dir / "laptop_cfd_report.json"
    solver_implementation_hash = _laptop_solver_implementation_sha256()
    if not force and (
        existing := _existing_laptop_cfd_result(
            acceptance_path,
            mesh_sha256=mesh_report["mesh_cgns_sha256"],
            implementation_sha256=solver_implementation_hash,
            mpi_np=mpi_np,
        )
    ):
        return existing

    campaign._archive_previous_solver_outputs(cfd_dir)
    acceptance_path.unlink(missing_ok=True)
    refs = mesh_report["reference_values"]
    solve = SolveSpec(
        solver="adflow",
        preset=LAPTOP_SOLVER_PRESET,
        flow=FlowConditions(**FLOW),
        area_ref=0.5 * float(refs["area_m2"]),
        chord_ref=float(refs["mean_aerodynamic_chord_m"]),
        mpi_np=mpi_np,
        raw_options=_laptop_raw_options(),
    )
    adapter = get_solver_adapter("adflow")
    prepared = adapter.prepare(solve, Path(mesh_report["mesh_cgns"]), cfd_dir)
    started = time.monotonic()
    returncode = adapter.run(prepared)
    solver_report = adapter.parse(prepared.workdir)
    orders_value = solver_report.convergence.get("orders_dropped")
    orders = float(orders_value) if orders_value is not None else None
    force_plausibility = campaign._force_plausibility_gate(solver_report.forces)
    force_tail = campaign._force_tail_gate(
        prepared.workdir / prepared.log_name,
        relative_range_max=LAPTOP_FORCE_TAIL_RELATIVE_RANGE_MAX,
    )
    yplus, _surface_solution = campaign._wall_yplus_gate(prepared.workdir)
    _write_json(prepared.workdir / "wall_yplus_summary.json", yplus)
    solver_path_passed = _local_solver_path_passed(
        returncode=returncode,
        solver_status=solver_report.status,
        residual_orders=orders,
        force_plausibility=force_plausibility,
        force_tail=force_tail,
    )
    production_gates_passed = bool(solver_path_passed and yplus["passed"])
    solve_report_path = prepared.workdir / "solve_report.json"
    solver_log_path = prepared.workdir / prepared.log_name
    report = {
        "schema": LAPTOP_CFD_SCHEMA,
        "state": ("LOCAL_SOLVER_PATH_PASSED" if solver_path_passed else "LOCAL_SOLVER_PATH_FAILED"),
        "purpose": "laptop_solver_smoke_not_production_grid_validation",
        "production_claim_allowed": False,
        "production_gates_passed_on_coarse_mesh": production_gates_passed,
        "production_wall_law_conclusion": "NOT_TESTED_AT_PRODUCTION_RESOLUTION",
        "n65_limitations": [
            "coarser than G1 in the wall-normal direction",
            "production first-cell height and march distance reused on N65",
            "smoke tangential resolution can alter resolved wall shear",
        ],
        "development_set": DEVELOPMENT_SET,
        "holdout_accessed": False,
        "geometry_index": index,
        "geometry_id": geometry_id,
        "mesh_cgns": mesh_report["mesh_cgns"],
        "mesh_cgns_sha256": mesh_report["mesh_cgns_sha256"],
        "normal_points": 65,
        "span_cells": mesh_report.get("span_cells"),
        "mpi_processes": mpi_np,
        "flow": FLOW,
        "solver_preset": LAPTOP_SOLVER_PRESET,
        "solver_protocol": _laptop_solver_protocol(),
        "solver_implementation_sha256": solver_implementation_hash,
        "solver_return_code": returncode,
        "solver_status": solver_report.status,
        "residual_orders_dropped": orders,
        "force_plausibility_gate": force_plausibility,
        "force_tail_gate": force_tail,
        "wall_yplus_gate": yplus,
        "forces": solver_report.forces,
        "solve_report": str(solve_report_path),
        "solve_report_sha256": sha256(solve_report_path),
        "solver_log": str(solver_log_path),
        "solver_log_sha256": sha256(solver_log_path),
        "elapsed_s": time.monotonic() - started,
    }
    _write_json(acceptance_path, report)
    return report


def _validate_current_laptop_cfd_report(
    path: Path, *, expected_index: int
) -> tuple[dict[str, Any] | None, list[str]]:
    if not path.is_file():
        return None, ["report_missing"]
    try:
        report = _read_json(path)
    except (OSError, ValueError, TypeError) as error:
        return None, [f"report_unreadable:{type(error).__name__}"]

    reasons: list[str] = []
    if report.get("schema") != LAPTOP_CFD_SCHEMA:
        reasons.append("schema_mismatch")
    if report.get("state") not in {
        "LOCAL_SOLVER_PATH_PASSED",
        "LOCAL_SOLVER_PATH_FAILED",
    }:
        reasons.append("invalid_state")
    if report.get("geometry_index") != expected_index:
        reasons.append("geometry_index_mismatch")
    if report.get("holdout_accessed") is not False:
        reasons.append("holdout_flag_not_false")

    mpi_np = report.get("mpi_processes")
    if not isinstance(mpi_np, int) or mpi_np < 1:
        reasons.append("invalid_mpi_processes")
    expected_solver_hash = _laptop_solver_implementation_sha256()
    if report.get("solver_implementation_sha256") != expected_solver_hash:
        reasons.append("solver_implementation_mismatch")
    if report.get("flow") != FLOW:
        reasons.append("flow_mismatch")

    case_dir = path.parents[1]
    mesh_report = _accepted_existing_mesh(
        case_dir / "mesh_report.json",
        expected_implementation_sha256=_laptop_mesh_implementation_sha256(),
    )
    if mesh_report is None:
        reasons.append("mesh_report_stale_or_invalid")
    elif report.get("mesh_cgns_sha256") != mesh_report.get("mesh_cgns_sha256"):
        reasons.append("mesh_hash_mismatch")

    if not _reported_file_matches(report, "solve_report", "solve_report_sha256"):
        reasons.append("solve_report_stale_or_missing")
    if not _reported_file_matches(report, "solver_log", "solver_log_sha256"):
        reasons.append("solver_log_stale_or_missing")
    if not _reported_yplus_surface_matches(report):
        reasons.append("surface_solution_stale_or_missing")
    return report, reasons


def _mpi_deviation_reason(actual: Any, planned: int) -> str:
    if not isinstance(actual, int):
        return "actual_rank_count_missing_or_invalid"
    if actual < planned:
        return "actual_below_plan_reason_not_recorded_in_case_report"
    if actual > planned:
        return "actual_above_plan_reason_not_recorded_in_case_report"
    return "no_deviation"


def collect_laptop(*, indices: list[int], output: Path) -> dict[str, Any]:
    rows = []
    root = Path(output).resolve()
    for index in indices:
        path = root / _case_id(index) / "cfd/laptop_cfd_report.json"
        report, reasons = _validate_current_laptop_cfd_report(path, expected_index=index)
        if report is None and reasons == ["report_missing"]:
            rows.append({"geometry_index": index, "state": "NOT_RUN"})
            continue
        if reasons:
            rows.append(
                {
                    "geometry_index": index,
                    "state": "STALE_OR_INVALID_PROVENANCE",
                    "failure_reasons": reasons,
                    "report": str(path),
                    "report_sha256": sha256(path) if path.is_file() else None,
                    "mpi_processes": report.get("mpi_processes") if report else None,
                }
            )
            continue
        assert report is not None
        rows.append(
            {
                "geometry_index": index,
                "state": report["state"],
                "solver_status": report["solver_status"],
                "residual_orders_dropped": report["residual_orders_dropped"],
                "forces": report["forces"],
                "wall_yplus_passed": report["wall_yplus_gate"]["passed"],
                "wall_yplus_statistics": report["wall_yplus_gate"].get("statistics"),
                "mpi_processes": report["mpi_processes"],
                "normal_points": report["normal_points"],
                "span_cells": report["span_cells"],
                "mesh_cgns_sha256": report["mesh_cgns_sha256"],
                "solver_implementation_sha256": report["solver_implementation_sha256"],
                "report": str(path),
                "report_sha256": sha256(path),
                "elapsed_s": report["elapsed_s"],
            }
        )

    valid_states = {"LOCAL_SOLVER_PATH_PASSED", "LOCAL_SOLVER_PATH_FAILED"}
    completed = [row for row in rows if row["state"] in valid_states]
    stale = [row for row in rows if row["state"] == "STALE_OR_INVALID_PROVENANCE"]
    planned_mpi = PLANNED_LAPTOP_MPI_PROCESSES
    protocol_deviations = [
        {
            "geometry_index": row["geometry_index"],
            "row_state": row["state"],
            "field": "mpi_processes",
            "planned": planned_mpi,
            "actual": row.get("mpi_processes"),
            "reason": _mpi_deviation_reason(row.get("mpi_processes"), planned_mpi),
        }
        for row in rows
        if isinstance(row.get("mpi_processes"), int) and row.get("mpi_processes") != planned_mpi
    ]
    summary = {
        "schema": LAPTOP_SUMMARY_SCHEMA,
        "purpose": "laptop_solver_smoke_not_production_grid_validation",
        "production_claim_allowed": False,
        "campaign_ready": False,
        "development_set": DEVELOPMENT_SET,
        "holdout_accessed": False,
        "requested": len(indices),
        "completed": len(completed),
        "stale_or_invalid": len(stale),
        "solver_path_passed": (
            sum(row["state"] == "LOCAL_SOLVER_PATH_PASSED" for row in completed)
            if completed
            else None
        ),
        "wall_yplus_passed": (
            sum(bool(row["wall_yplus_passed"]) for row in completed) if completed else None
        ),
        "mesh_implementation_sha256": _laptop_mesh_implementation_sha256(),
        "solver_implementation_sha256": _laptop_solver_implementation_sha256(),
        "production_wall_law_status": "NOT_TESTED_AT_PRODUCTION_RESOLUTION",
        "scientific_interpretation": {
            "can_conclude": [
                "the mesh-to-ADflow path and rejection logic run locally",
                "the residual and force-stability gates pass on these N65 cases",
            ],
            "cannot_conclude": [
                "production-grid yplus adequacy",
                "production-grid force accuracy",
                "trailing-edge sensitivity",
                "grid convergence",
            ],
            "n65_yplus_result": (
                "coarse rejection-screen evidence only; do not calibrate or reject "
                "the production wall law from these values"
            ),
        },
        "protocol_deviations": protocol_deviations,
        "rows": rows,
    }
    summary_path = root / "laptop_summary_current.json"
    summary["summary_path"] = str(summary_path)
    summary["historical_summary_preserved"] = str(root / "laptop_summary.json")
    _write_json(summary_path, summary)
    return summary


def _legacy_asset(path_value: Any) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value:
        return {"path": path_value, "exists": False, "sha256": None}
    path = Path(path_value)
    return {
        "path": str(path.resolve()),
        "exists": path.is_file(),
        "sha256": sha256(path) if path.is_file() else None,
    }


def audit_legacy_laptop(*, indices: list[int], output: Path, audit_output: Path) -> dict[str, Any]:
    root = Path(output).resolve()
    rows = []
    for index in indices:
        geometry_id = _case_id(index)
        case_dir = root / geometry_id
        mesh_report_path = case_dir / "mesh_report.json"
        cfd_report_path = case_dir / "cfd/laptop_cfd_report.json"
        mesh_report = _read_json(mesh_report_path)
        cfd_report = _read_json(cfd_report_path)

        surface_artifacts = mesh_report.get("surface_artifacts", {})
        surface_npz_record = surface_artifacts.get("surface_npz", {})
        surface_fmt_record = surface_artifacts.get("surface_fmt", {})
        yplus_gate = cfd_report.get("wall_yplus_gate", {})
        asset_values = {
            "mesh_report": str(mesh_report_path),
            "mesh_cgns": mesh_report.get("mesh_cgns"),
            "deformation_report": mesh_report.get("deformation_report"),
            "surface_npz": surface_npz_record.get("path"),
            "surface_fmt": surface_fmt_record.get("path"),
            "cfd_report": str(cfd_report_path),
            "solve_report": cfd_report.get("solve_report"),
            "solver_log": str(case_dir / "cfd/adflow_run.log"),
            "solver_script": str(case_dir / "cfd/run_adflow.py"),
            "wall_yplus_summary": str(case_dir / "cfd/wall_yplus_summary.json"),
            "surface_solution": yplus_gate.get("surface_cgns"),
        }
        assets = {name: _legacy_asset(path_value) for name, path_value in asset_values.items()}

        surface_path = Path(surface_npz_record["path"])
        surface_blocks = load_surface_blocks(surface_path)
        span_counts = sorted({int(nodes.shape[1] - 1) for nodes in surface_blocks.values()})
        declared_checks = {
            "mesh_cgns": (assets["mesh_cgns"]["sha256"] == mesh_report.get("mesh_cgns_sha256")),
            "surface_npz": (assets["surface_npz"]["sha256"] == surface_npz_record.get("sha256")),
            "surface_fmt": (assets["surface_fmt"]["sha256"] == surface_fmt_record.get("sha256")),
            "cfd_mesh_reference": (
                cfd_report.get("mesh_cgns_sha256") == mesh_report.get("mesh_cgns_sha256")
            ),
            "surface_solution": (
                assets["surface_solution"]["sha256"] == yplus_gate.get("surface_cgns_sha256")
            ),
        }
        _current_report, current_reasons = _validate_current_laptop_cfd_report(
            cfd_report_path, expected_index=index
        )
        rows.append(
            {
                "geometry_index": index,
                "geometry_id": geometry_id,
                "template_geometry_index": LAPTOP_TEMPLATE_ROUTES[index],
                "legacy_cfd_state": cfd_report.get("state"),
                "surface_block_j_cell_counts": span_counts,
                "realized_primary_span_cells": _primary_span_cells(surface_blocks),
                "all_assets_present": all(asset["exists"] for asset in assets.values()),
                "declared_hash_checks": declared_checks,
                "declared_hashes_match": all(declared_checks.values()),
                "current_cache_compatible": not current_reasons,
                "current_cache_rejection_reasons": current_reasons,
                "assets": assets,
            }
        )

    operator_notes = {}
    if 7 in indices:
        operator_notes["7"] = (
            "case 007 was launched with two MPI ranks after case 095 exhausted "
            "laptop swap; this note is not generated by the case report"
        )

    source_summary = root / "laptop_summary.json"
    report = {
        "schema": LEGACY_AUDIT_SCHEMA,
        "state": (
            "LEGACY_EVIDENCE_INTEGRITY_PASSED"
            if all(row["all_assets_present"] and row["declared_hashes_match"] for row in rows)
            else "LEGACY_EVIDENCE_INTEGRITY_FAILED"
        ),
        "purpose": "bind_pre_fingerprint_N65_pilot_bytes_without_rewriting_history",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pilot_generated_by_current_code": False,
        "audit_generated_by_current_code": True,
        "current_cache_compatible": all(row["current_cache_compatible"] for row in rows),
        "rerun_required_for_current_provenance": True,
        "production_claim_allowed": False,
        "campaign_ready": False,
        "development_set": DEVELOPMENT_SET,
        "holdout_accessed": False,
        "claim_scope": [
            "historical local mesh-to-ADflow execution evidence",
            "historical residual, force-stability, and rejection-path evidence",
        ],
        "excluded_claims": [
            "current-code reproducibility",
            "production-grid yplus adequacy",
            "production-grid force accuracy",
            "trailing-edge sensitivity",
            "grid convergence",
        ],
        "operator_notes": operator_notes,
        "source_summary": _legacy_asset(str(source_summary)),
        "audit_implementation_sha256": sha256(Path(__file__)),
        "audit_provenance": {
            "qualification_sha256": sha256(Path(__file__)),
            "mesh_implementation_sha256": _laptop_mesh_implementation_sha256(),
            "solver_implementation_sha256": _laptop_solver_implementation_sha256(),
        },
        "rows": rows,
    }
    _write_json(audit_output, report)
    return report


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser("write-plan")
    plan.add_argument("--output", type=Path, required=True)

    prepare = commands.add_parser("prepare-laptop")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--indices", type=int, nargs="+", default=list(LAPTOP_GEOMETRIES))
    prepare.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    prepare.add_argument("--template-timeout-s", type=float, default=3600.0)

    solve = commands.add_parser("solve-laptop")
    solve.add_argument("--output", type=Path, required=True)
    solve.add_argument("--index", type=int, required=True)
    solve.add_argument("--np", type=int, default=4)
    solve.add_argument("--force", action="store_true")

    collect = commands.add_parser("collect-laptop")
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--indices", type=int, nargs="+", default=list(LAPTOP_GEOMETRIES))

    legacy = commands.add_parser("audit-legacy-laptop")
    legacy.add_argument("--output", type=Path, required=True)
    legacy.add_argument("--audit-output", type=Path, required=True)
    legacy.add_argument("--indices", type=int, nargs="+", default=list(LAPTOP_GEOMETRIES))
    return parser


def main() -> int:
    args = make_parser().parse_args()
    if args.command == "write-plan":
        result = write_plan(args.output)
    elif args.command == "prepare-laptop":
        rows = prepare_laptop_cases(
            indices=args.indices,
            output=args.output,
            registry_path=args.registry,
            timeout_s=args.template_timeout_s,
        )
        result = {
            "prepared": len(rows),
            "accepted": sum(row["state"] == "MESH_ACCEPTED" for row in rows),
        }
    elif args.command == "solve-laptop":
        result = solve_laptop_case(
            index=args.index,
            output=args.output,
            mpi_np=args.np,
            force=args.force,
        )
    elif args.command == "collect-laptop":
        result = collect_laptop(indices=args.indices, output=args.output)
    elif args.command == "audit-legacy-laptop":
        result = audit_legacy_laptop(
            indices=args.indices,
            output=args.output,
            audit_output=args.audit_output,
        )
    else:
        raise RuntimeError("unhandled command: " + str(args.command))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./S6_bounded_mesh_atlas/README.md =====

# S6 Bounded Mesh Atlas

S6 is the recommended candidate route. It is not production-frozen yet.

It combines:

1. exact pyGeo wall coordinates,
2. proven S1/Openblademesh topology and pyHyp volume seeds,
3. a small parameter-space atlas,
4. bounded volume deformation,
5. independent mesh rejection,
6. ADflow RANS/SA with a frozen solve policy.

The key rule is simple: a case reaches CFD only after the written CGNS passes all
mesh gates. Parameter distance chooses a candidate template; it never certifies it.

## Current evidence

- Exact S6 surfaces: 10/10 development geometries pass surface QC.
- Same-geometry S1-to-S6 deformation: 10/10 pass.
- Worst deformation minimum scaled Jacobian: +0.146.
- Inverted cells: 0 in all ten cases.
- Cross-design deformation 000 to 083: 1,621,504 cells, minimum +0.197, 0 inverted.
- All accepted meshes have 20 conformal internal interfaces below 1.0e-10 m.
- A provisional first-ten-seed preflight passed 100/100 development geometries;
  worst accepted quality was +0.110. It was diagnostic, not the final atlas.
- The geometry-active maximin selection produced 16/16 valid smoke seeds; their
  minimum qualities span +0.151 to +0.215.
- The maximin smoke atlas passed 100/100 geometries in 131 attempts; 80 passed
  first try, no route needed more than five attempts, and worst quality was +0.15184.
- One fixed provisional production policy passed 16/16 maximin seeds at `N=257`:
  `epsE=1.5`, first-cell fraction `3.6e-6`, worst quality +0.10535.
- The campaign-equivalent written-CGNS production canary passed 2/2 targets.
- The qualified 21-template written-CGNS audit passed 100/100 development targets.
- Three governed N65 laptop pilots passed 3/3 solver paths and 0/3 strict coarse
  y+ screens; they do not validate or reject the production wall law.
- A deterministic 10,000-design manifest was generated and checked in about 2 s.
- Production CFD/y+, TE/grid sensitivity, and the locked holdout remain.

## Commands

```bash
# Select candidate atlas points.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/run_s6.py \
  atlas --template-count 16 --trust-radius 0.40 \
  --output artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json

# Build and audit the selected development templates.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/build_seeds.py \
  --level smoke \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json \
  --output AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v2/smoke

# Validate all 100 development geometries, trying the full atlas when needed.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/development_atlas.py \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json \
  --template-root AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v2/smoke \
  --preferred-quality 0.15 \
  --output artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_smoke

# Add deterministic seeds for weak, slow, or failed development routes.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/run_s6.py \
  enrich-atlas \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json \
  --development-report artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_smoke/atlas_validation_report.json \
  --output artifacts/s6_bounded_mesh_atlas/atlas_manifest_smoke_enriched_v3.json

# If seeds were added, build them and repeat validation/enrichment. Then build
# production-normal-resolution seeds; smoke evidence cannot set freeze_ready.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/build_seeds.py \
  --level production \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_smoke_enriched_v3.json \
  --eps-e 1.5 --first-cell-fraction 3.6e-6 \
  --output AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v3/calibration_s0_3p6_production

# Repeat the 100-case validation at production resolution, then make the final
# enrichment decision. Only this report may set freeze_ready.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/development_atlas.py \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_qualified16_eps15_s0p3p6_v5.json \
  --template-root AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v3/calibration_s0_3p6_production \
  --eps-e 1.5 \
  --preferred-quality 0.15 \
  --output artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_production_written_v2
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/run_s6.py \
  enrich-atlas \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_qualified16_eps15_s0p3p6_v5.json \
  --development-report artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_production_written_v2/atlas_validation_report.json \
  --output artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_enriched_v6.json

# Build one exact target surface.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/run_s6.py \
  surface --index 83 --level smoke \
  --output artifacts/s6_bounded_mesh_atlas/surfaces

# Deform one proven volume and audit every cell.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/run_s6.py \
  deform --template-cgns TEMPLATE.cgns \
  --template-surface TEMPLATE_surface_blocks.npz \
  --target-surface TARGET_surface_blocks.npz \
  --output-cgns TARGET.cgns --report TARGET_report.json

# Reproduce the ten-case development pilot.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/pilot.py \
  --output artifacts/s6_bounded_mesh_atlas/development_pilot

# Create a deterministic 10,000-design LHS and one-flow manifest.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py \
  sample-designs --count 10000 --seed 2026 --output designs_10000.csv
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py \
  make-manifest --designs designs_10000.csv \
  --flows AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/examples/flows_single.csv \
  --output campaign_10000.json

# Audit immutable seed files and bind the registry to the atlas hash.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py \
  build-registry \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_enriched_v6.json \
  --source-root AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v3/calibration_s0_3p6_production \
  --eps-e 1.5 \
  --output template_registry.json

# Run one design, all its flow points, and prune its accepted transient mesh.
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/campaign.py \
  run-design --manifest campaign_10000.json --registry template_registry.json \
  --campaign-root campaign_output --design-index 0 --np 4 --prune-accepted-mesh

# Start with limited Slurm concurrency; raise it only after the HPC rehearsal.
export S6_MANIFEST="$PWD/campaign_10000.json"
export S6_REGISTRY="$PWD/template_registry.json"
export S6_CAMPAIGN_ROOT="$PWD/campaign_output"
sbatch --array=0-9999%50 \
  AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/slurm_run_design_array.sh

# Safe to repeat after jobs finish; accepted cases are hash-cached.
AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/slurm_collect.sh

# Focused tests.
.venv/bin/python -m pytest -q \
  AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/test_s6.py
```

## Production order

For each geometry:

1. Build and validate pyGeo.
2. Build the exact S6 target surface.
3. Try frozen atlas seeds nearest first until quality reaches +0.15; retain the
   best mesh above the +0.10 hard floor.
4. If no atlas mesh reaches +0.15, try target-specific S1 at the epsE and wall law
   recorded in the frozen registry.
5. Deform the fallback to the exact wall and audit it again.
6. Reject and log the case if the fallback fails. Never repair it by hand.
7. Run ADflow only on an accepted written CGNS.
8. Accept CFD only after residual, force-stability, finite-value, and y+ gates pass.
9. Prune accepted transient meshes only after all flow points for that design pass.

Do not freeze the atlas until the 100-case development run passes. Run the locked
holdout only once after that freeze. Production readiness and future Gmsh/SU2 and
AI work are tracked in `ROADMAP.md`.


===== FILE: ./S6_bounded_mesh_atlas/RESEARCH.md =====

# Research basis and decision

## Decision

Use a structured, geometry-family-specific mesh atlas with exact-wall deformation
and full post-write rejection. Use pyGeo for geometry, S1 plus pyHyp for seed
volumes, and ADflow for RANS/SA.

This is tailored to this project. The geometries vary strongly, but all come from
one four-station BWB generator. Reusing a validated block graph is therefore more
valuable than asking a general unstructured mesher to rediscover topology 10,000
times.

## Why this route

- Structured multiblock RANS gives predictable near-wall resolution and low cell
  count for repeated aerodynamic solves.
- The local S1 study already proves that its topology marches on all ten
  development geometries.
- The old direct exact-surface march diagnostic failed before the surface-interface
  basis correction, so it is not evidence against a corrected direct march. The atlas
  remains preferable because it reuses audited volumes and bounds production risk.
- Smooth volume deformation is established practice in aerodynamic optimization.
  Secco et al. report a robust structured mesh generation and deformation
  workflow built around pyHyp and IDWarp.
- A mesh atlas limits deformation magnitude without making parameter distance a
  substitute for geometric quality.
- Independent post-write gates prevent silent bad meshes from entering CFD.

## Open-source stack

- Geometry: [pyGeo](https://github.com/mdolab/pygeo)
- Seed volume mesher: [pyHyp](https://mdolab-pyhyp.readthedocs-hosted.com/en/latest/)
- CFD: [ADflow](https://mdolab-adflow.readthedocs-hosted.com/en/latest/introduction.html)
- Inspection: ParaView
- Optional future deformation backend:
  [IDWarp](https://mdolab-idwarp.readthedocs-hosted.com/en/latest/tutorial.html)

The implemented bounded column deformation is deterministic and preserves the
wall-normal columns of the proven seed. IDWarp should be benchmarked against it,
not adopted without the same 100-case and holdout gates.

## Evidence from similar work

MDO Lab's published workflow uses pyGeo, pyHyp, IDWarp, and ADflow for aerodynamic
shape optimization. The mesh method is described in
[Secco et al. 2021](https://mdolab.engin.umich.edu/bibliography/Secco2021a).
A pyGeo/IDWarp/ADflow RANS application is also documented in
[Wu et al. 2022](https://public.websites.umich.edu/~mdolaboratory/pdf/Wu2022b.pdf).
An automated, knowledge-based geometry and meshing workflow for large design
variation is described by
[DLR](https://link.springer.com/article/10.1007/s13272-017-0264-1).

ADflow supports structured multiblock RANS. Its solver guide recommends ANK for
robust startup and NK for final convergence:
[ADflow solver strategy](https://mdolab-adflow.readthedocs-hosted.com/en/latest/solvers.html).

The planned independent route is Gmsh prism/tet meshing with SU2 RANS-SA. It is a
valid backup for broader geometry changes, but AERIS's current Gmsh volume path lacks
the validated wall-normal prism stack required for wall-resolved RANS. It will be
implemented and judged with the same geometry, y+, convergence, and force gates after
S6 is validated.

## What is new here

The atlas is not copied from one paper. It combines established mesh deformation
with this project's locked design-space geometry and measured failure modes:

- direct pyGeo evaluation closes S1's spanwise fidelity gap;
- each seed retains the dimensions that already marched successfully;
- maximin sampling spreads 16 initial seeds through the normalized 16-variable
  neutral-OML design space; fixed and neutral elevon-placement variables are omitted;
- every frozen compatible seed is available, nearest first, and distance only orders
  attempts;
- weak-quality, slow, and failed development routes deterministically enrich the
  atlas before it is frozen;
- the fallback uses the proven S1 march, then corrects to the exact S6 wall;
- every output mesh is rescored from its coordinates.

## Limits

The mesh pilots and one coarse CFD solve are development evidence, not proof over
10,000 cases. Production y+, the final enriched 100-case development run, frozen
holdout, 100-case CFD pilot, grid convergence, 10,000-mesh preflight, and HPC
rehearsal remain mandatory. See `ROADMAP.md` for the release gates and later AI work.


===== FILE: ./S6_bounded_mesh_atlas/resolution.py =====

"""Frozen S6 mesh-resolution candidates and their validation status."""

from __future__ import annotations

from shared.gates import EPSE_LADDER

S6_FIRST_CELL_FRACTION = {
    "smoke": 8.8e-6,
    "fine": 6.0e-6,
    # The fixed N257/epsE=1.5 development calibration passed all 16 seeds at
    # 3.6e-6. This remains provisional until production CFD verifies y+.
    "production": 3.6e-6,
}

REFERENCE_REYNOLDS = 1.0e6
PRODUCTION_WALL_SPACING_STATUS = "candidate_pending_cfd_yplus_validation"


def first_cell_fraction(level: str) -> float:
    try:
        return S6_FIRST_CELL_FRACTION[level]
    except KeyError as error:
        raise ValueError(f"S6 has no wall-spacing policy for level {level!r}") from error


def epsilon_tag(eps_e: float) -> str:
    """Return the on-disk tag for one value in the governed epsE ladder."""
    if eps_e not in EPSE_LADDER:
        raise ValueError(f"epsE must be in the frozen ladder {EPSE_LADDER}")
    return f"eps{int(round(10.0 * eps_e)):02d}"


===== FILE: ./S6_bounded_mesh_atlas/ROADMAP.md =====

# AERIS automated CFD roadmap

This file is the persistent work order for the automated CFD campaign. Passing a
mesh unit test does not make a pipeline campaign-ready.

## Current order

1. Finish and validate `s6_atlas + ADflow`.
2. Add `Gmsh prism/tet + SU2` as an independent unstructured pipeline.
3. Add `auto` (S6, then Gmsh fallback) and `compare` modes with one acceptance schema.
4. Use the recorded S6 experience for AI-assisted meshing research.

## Current evidence

- The 16-seed maximin smoke atlas passed all 100 development geometries.
- It required 131 attempts, passed 80 cases first try, never exceeded five attempts,
  and had worst accepted scaled quality +0.15184.
- Smoke enrichment added no seeds, but cannot unlock the holdout.
- A fixed provisional production policy (`N=257`, `epsE=1.5`, first-cell fraction
  `3.6e-6`) passed 16/16 maximin seeds. Independent quality spans `0.10535` to
  `0.23471`; zero cells are below `0.10` and three are below `0.15`.
- A campaign-equivalent written-CGNS canary passed 2/2. The full 100-target
  production audit is running and checkpointed.
- The wall law is not frozen until production CFD proves y+.
- The locked holdout remains untouched.

## S6 release gate for 10,000 CFD cases

S6 can be frozen for the 10,000-case campaign only after all of these pass:

- production-resolution CFD passes the frozen wall-y+ limits;
- the locked unseen hold-out passes without tuning;
- at least 99 of 100 CFD pilot cases finish automatically with accepted meshes and CFD;
- about 20 representative cases show stable lift and drag under grid refinement;
- all 10,000 planned geometries pass mesh preflight or an automatic fallback;
- a 500-1,000-case HPC rehearsal proves restart, failure recovery, storage, and collection.

The immediate blocker is production-resolution y+ validation.

## Reduced gate for a 100 CFD campaign

- preflight all 100 meshes and accept 100/100;
- run 10-20 CFD pilots, including geometric extremes;
- pass production-resolution y+;
- perform grid convergence on five representative cases;
- keep about ten geometries as an untouched hold-out;
- prove unattended restart and failure recovery.

## Unstructured pipeline

The Gmsh + SU2 route is not equivalent to S6 until it has wall-normal prism layers.
Benchmark it on the same ten extreme geometries. Require 10/10 automatic meshes,
zero invalid cells, accepted y+, converged RANS-SA solutions, and stable lift and drag
under refinement.

## AI research record

Save these fields for every attempted mesh and CFD case:

- geometry design variables and normalized coordinates;
- ranked templates, selected template, and rejected alternatives;
- deformation field and deformation cost;
- cell-level and summary mesh quality;
- failed attempts and exact gate reasons;
- mesh generation time and resource use;
- wall y+, residual history, force history, convergence state, and final forces.

The first paper targets AI-assisted meshing: AI ranks templates and predicts failure or
quality, while deterministic deformation and hard gates retain authority. A working
title is "Quality-Constrained AI-Assisted Mesh Atlas Deformation for Automated CFD
Design Campaigns."

## Joint validation programme

The shared S6/S7 sequence this study feeds - staging, the paired comparison and
the decisions that must be taken before any CFD is recorded - is in
`../VALIDATION_PROGRAMME.md`.


===== FILE: ./S6_bounded_mesh_atlas/run_s6.py =====

#!/usr/bin/env python3
"""CLI for constructing, marching, deforming, and auditing S6 meshes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (HERE, REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from atlas import (  # noqa: E402
    build_atlas_manifest,
    enrich_atlas_manifest,
    qualify_atlas_seeds,
    write_manifest,
)
from deform import deform_cgns, sha256  # noqa: E402
from resolution import first_cell_fraction  # noqa: E402
from shared.pyhyp_runner import prepare, read_result  # noqa: E402
from shared.qc import write_surface_artifacts  # noqa: E402
from shared.volume_qc import equivalence_against_pyhyp  # noqa: E402
from strategy_s6 import STRATEGY_ID, build_locked_surface  # noqa: E402

from aeris.cfd.meshing.pyhyp_extrude import mach_aero_python  # noqa: E402


def _default(value: Any) -> Any:
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_default) + "\n",
        encoding="utf-8",
    )
    return path


def surface_command(args: argparse.Namespace) -> dict[str, Any]:
    root = args.output.resolve()
    blocks, info, _case = build_locked_surface(
        args.set_name, args.index, root / "_geometry", level=args.level
    )
    target = root / info["locked_set_id"]
    artifacts = write_surface_artifacts(blocks, target)
    report = _write_json(target / "surface_report.json", info)
    return {
        "geometry_id": info["locked_set_id"],
        "surface_report": str(report),
        "artifacts": artifacts,
        "accepted": bool(info["surface_qc"]["accepted_pre_pyhyp"])
        and bool(info["fidelity"]["passed"]),
    }


def atlas_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = build_atlas_manifest(
        set_name=args.set_name,
        template_count=args.template_count,
        trust_radius_rms=args.trust_radius,
    )
    path = write_manifest(args.output.resolve(), manifest)
    return {"manifest": str(path), **manifest["coverage"]}


def enrich_atlas_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.atlas_manifest.read_text(encoding="utf-8"))
    development = json.loads(args.development_report.read_text(encoding="utf-8"))
    enriched = enrich_atlas_manifest(
        manifest,
        development,
        warning_quality=args.warning_quality,
        maximum_attempts=args.maximum_attempts,
        maximum_templates=args.maximum_templates,
    )
    enriched["quality_enrichment"]["source_atlas"] = {
        "path": str(args.atlas_manifest.resolve()),
        "sha256": sha256(args.atlas_manifest),
    }
    enriched["quality_enrichment"]["development_report"] = {
        "path": str(args.development_report.resolve()),
        "sha256": sha256(args.development_report),
    }
    path = write_manifest(args.output.resolve(), enriched)
    quality_enrichment = enriched["quality_enrichment"]
    return {
        "manifest": str(path),
        "template_count": enriched["template_count"],
        "added_indices": quality_enrichment["added_indices"],
        "candidate_count": quality_enrichment["candidate_count"],
        "requires_revalidation": quality_enrichment["requires_revalidation"],
        "requires_production_validation": quality_enrichment[
            "requires_production_validation"
        ],
        "freeze_ready": quality_enrichment["freeze_ready"],
    }


def qualify_atlas_seeds_command(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.atlas_manifest.read_text(encoding="utf-8"))
    seed_report = json.loads(args.seed_report.read_text(encoding="utf-8"))
    qualified = qualify_atlas_seeds(
        manifest,
        seed_report,
        production_floor=args.production_floor,
        minimum_templates=args.minimum_templates,
    )
    qualification = qualified["seed_qualification"]
    qualification["source_atlas"] = {
        "path": str(args.atlas_manifest.resolve()),
        "sha256": sha256(args.atlas_manifest),
    }
    qualification["seed_report"] = {
        "path": str(args.seed_report.resolve()),
        "sha256": sha256(args.seed_report),
    }
    path = write_manifest(args.output.resolve(), qualified)
    return {
        "manifest": str(path),
        "source_template_count": len(qualification["source_template_indices"]),
        "qualified_template_count": len(qualification["qualified_indices"]),
        "rejected_indices": [
            row["geometry_index"] for row in qualification["rejected"]
        ],
        "freeze_ready": qualification["freeze_ready"],
    }


def march_command(args: argparse.Namespace) -> dict[str, Any]:
    root = args.output.resolve()
    blocks, info, _case = build_locked_surface(
        args.set_name, args.index, root / "_geometry", level=args.surface_level
    )
    manifest = prepare(
        strategy_id=STRATEGY_ID,
        geometry_id=info["locked_set_id"],
        blocks=blocks,
        out_dir=root,
        level=args.volume_level,
        epse_ladder=(args.eps_e,),
        s0_fraction_override=first_cell_fraction(args.volume_level),
    )
    run_dir = Path(manifest["runs"][0]["dir"]).resolve()
    runner = Path(manifest["runs"][0]["runner"]).resolve()
    with (run_dir / "run_stdout.log").open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            [str(mach_aero_python()), str(runner)],
            cwd=run_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    cgns = run_dir / "wing_vol.cgns"
    result = read_result(run_dir) or {}
    quality = equivalence_against_pyhyp(cgns) if cgns.is_file() else None
    accepted = bool(
        completed.returncode == 0
        and result.get("march_completed")
        and quality
        and quality.get("inverted_cells") == 0
        and float(quality.get("min_scaled_quality", -1.0)) > 0.0
    )
    report = {
        "strategy_id": STRATEGY_ID,
        "geometry_id": info["locked_set_id"],
        "return_code": completed.returncode,
        "accepted": accepted,
        "cgns": str(cgns),
        "surface_npz": str(run_dir / "surface_blocks.npz"),
        "march_result": result,
        "direct_quality": quality,
    }
    _write_json(run_dir / "s6_template_report.json", report)
    return report


def deform_command(args: argparse.Namespace) -> dict[str, Any]:
    return deform_cgns(
        template_cgns=args.template_cgns.resolve(),
        template_surface_npz=args.template_surface.resolve(),
        target_surface_npz=args.target_surface.resolve(),
        output_cgns=args.output_cgns.resolve(),
        report_path=args.report.resolve(),
        production_floor=args.production_floor,
    )


def make_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="S6 bounded mesh-atlas workflow")
    commands = root.add_subparsers(dest="command", required=True)

    surface = commands.add_parser("surface")
    surface.add_argument("--set-name", default="lhs100_seed42")
    surface.add_argument("--index", type=int, required=True)
    surface.add_argument("--level", default="smoke")
    surface.add_argument("--output", type=Path, required=True)
    surface.set_defaults(function=surface_command)

    atlas = commands.add_parser("atlas")
    atlas.add_argument("--set-name", default="lhs100_seed42")
    atlas.add_argument("--template-count", type=int, default=16)
    atlas.add_argument("--trust-radius", type=float, default=0.40)
    atlas.add_argument("--output", type=Path, required=True)
    atlas.set_defaults(function=atlas_command)

    enrich = commands.add_parser("enrich-atlas")
    enrich.add_argument("--atlas-manifest", type=Path, required=True)
    enrich.add_argument("--development-report", type=Path, required=True)
    enrich.add_argument("--warning-quality", type=float, default=0.15)
    enrich.add_argument("--maximum-attempts", type=int, default=5)
    enrich.add_argument("--maximum-templates", type=int, default=32)
    enrich.add_argument("--output", type=Path, required=True)
    enrich.set_defaults(function=enrich_atlas_command)

    qualify = commands.add_parser("qualify-atlas-seeds")
    qualify.add_argument("--atlas-manifest", type=Path, required=True)
    qualify.add_argument("--seed-report", type=Path, required=True)
    qualify.add_argument("--production-floor", type=float, default=0.10)
    qualify.add_argument("--minimum-templates", type=int, required=True)
    qualify.add_argument("--output", type=Path, required=True)
    qualify.set_defaults(function=qualify_atlas_seeds_command)

    march = commands.add_parser("march-template")
    march.add_argument("--set-name", default="lhs100_seed42")
    march.add_argument("--index", type=int, required=True)
    march.add_argument("--surface-level", default="smoke")
    march.add_argument("--volume-level", default="smoke")
    march.add_argument("--eps-e", type=float, default=2.0)
    march.add_argument("--output", type=Path, required=True)
    march.set_defaults(function=march_command)

    deform = commands.add_parser("deform")
    deform.add_argument("--template-cgns", type=Path, required=True)
    deform.add_argument("--template-surface", type=Path, required=True)
    deform.add_argument("--target-surface", type=Path, required=True)
    deform.add_argument("--output-cgns", type=Path, required=True)
    deform.add_argument("--report", type=Path, required=True)
    deform.add_argument("--production-floor", type=float, default=0.10)
    deform.set_defaults(function=deform_command)
    return root


def main() -> int:
    args = make_parser().parse_args()
    try:
        result = args.function(args)
    except Exception as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, indent=2))
        return 1
    print(json.dumps({"status": "OK", **result}, indent=2, default=_default))
    if args.command == "march-template":
        return 0 if result["accepted"] else 2
    if args.command == "deform":
        return 0 if result["acceptance"]["production_floor_passed"] else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./S6_bounded_mesh_atlas/strategy_s6.py =====

"""S6: exact-pyGeo, fixed-topology surface meshes for a bounded mesh atlas.

The production idea is deliberately narrow: all campaign geometries come from the
same four-station BWB generator, so they should also share one mesh graph and one
set of block dimensions.  Node coordinates may adapt, but connectivity may not.

S6 keeps the S1/Openblademesh tip closure that has already marched successfully,
while replacing S1's straight interpolation between span stations with direct
evaluation of the pyGeo B-spline loft.  This closes the known fidelity gap without
giving up the topology that made S1 work.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from S1_tip_first.strategy_s1 import (  # noqa: E402
    ARC_ORDER,
    NOSE_END_FRAC,
    section_geometry,
    tip_domains_2d,
)
from shared.geometry_sets import _config, geometry_id, sample  # noqa: E402
from shared.ingestion import SurfaceBlock  # noqa: E402
from shared.qc import orient_blocks_consistently, qc_blocks  # noqa: E402

Array = np.ndarray

STRATEGY_ID = "S6_BOUNDED_MESH_ATLAS"


@dataclass(frozen=True)
class LevelSpec:
    chord_points: int
    end_points: int
    collar_points: int
    span_cells: int
    dense_curve_points: int
    span_max_cell_m: float


LEVELS: dict[str, LevelSpec] = {
    "coarse": LevelSpec(25, 3, 5, 63, 801, 0.020),
    "smoke": LevelSpec(33, 3, 7, 89, 1001, 0.015),
    "medium": LevelSpec(49, 4, 9, 127, 1201, 0.010),
    "fine": LevelSpec(65, 5, 13, 179, 1601, 0.008),
}


@dataclass(frozen=True)
class SectionFrame:
    le: Array
    te: Array
    chord_axis: Array
    thickness_axis: Array
    chord: float
    target_te: float
    half_te_opening_m: float


def build_pygeo_case(set_name: str, index: int, output_dir: Path):
    """Build one locked geometry with pyGeo as the master realization."""
    from aeris.geometry.registry import get_geometry_generator

    smp = sample(set_name, index)
    return get_geometry_generator("bwb_segmented").run_full_case(
        sample=smp,
        config=_config(),
        output_dir=Path(output_dir),
        save_plot=False,
        build_aerosandbox=False,
    )


def _unit(vector: Array, label: str) -> Array:
    magnitude = float(np.linalg.norm(vector))
    if not np.isfinite(magnitude) or magnitude <= 1.0e-14:
        raise ValueError(f"degenerate {label}: {vector}")
    return np.asarray(vector, dtype=float) / magnitude


def _surface_points(surface: Any, u: Array, v: float) -> Array:
    vv = np.full_like(u, float(v), dtype=float)
    points = np.asarray(surface(u, vv), dtype=float)
    if points.shape != (len(u), 3):
        points = points.reshape(len(u), 3)
    return points


def _frame_and_opened_curves(
    pygeo: Any,
    v: float,
    *,
    dense_points: int,
    te_abs_m: float,
    te_floor_frac: float,
) -> tuple[Array, Array, Array, SectionFrame]:
    """Sample one exact pyGeo section and apply the declared CFD-safe TE law."""
    u = np.linspace(0.0, 1.0, dense_points)
    upper = _surface_points(pygeo.surfs[0], u, v)
    lower = _surface_points(pygeo.surfs[1], u, v)

    te = 0.5 * (upper[0] + lower[0])
    le = 0.5 * (upper[-1] + lower[-1])
    chord_axis = _unit(te - le, "section chord axis")
    chord = float(np.linalg.norm(te - le))

    separation = upper - lower
    thick_index = int(np.argmax(np.linalg.norm(separation, axis=1)))
    thickness_direction = separation[thick_index]
    thickness_direction = thickness_direction - (thickness_direction @ chord_axis) * chord_axis
    thickness_axis = _unit(thickness_direction, "section thickness axis")
    target_te = max(float(te_abs_m), float(te_floor_frac) * chord)
    current_te = float(np.linalg.norm(upper[0] - lower[0]))
    half_added = 0.5 * max(0.0, target_te - current_te)

    xhat = np.clip((upper - le) @ chord_axis / max(chord, 1.0e-14), 0.0, 1.0)
    upper = upper + half_added * xhat[:, None] * thickness_axis
    xhat_lower = np.clip((lower - le) @ chord_axis / max(chord, 1.0e-14), 0.0, 1.0)
    lower = lower - half_added * xhat_lower[:, None] * thickness_axis
    frame = SectionFrame(
        le,
        te,
        chord_axis,
        thickness_axis,
        chord,
        target_te,
        half_added,
    )
    return u, upper, lower, frame


def _opened_points_at_u(
    pygeo: Any,
    u: Array,
    v: float,
    *,
    frame: SectionFrame,
    upper: bool,
) -> Array:
    """Independently evaluate the declared CFD surface at exact parameters."""
    points = _surface_points(pygeo.surfs[0 if upper else 1], u, v)
    xhat = np.clip(
        (points - frame.le) @ frame.chord_axis / max(frame.chord, 1.0e-14),
        0.0,
        1.0,
    )
    sign = 1.0 if upper else -1.0
    return points + sign * frame.half_te_opening_m * xhat[:, None] * frame.thickness_axis


def _u_at_xfrac(points: Array, u: Array, frame: SectionFrame, xfrac: float) -> float:
    xhat = (points - frame.le) @ frame.chord_axis / frame.chord
    order = np.argsort(xhat)
    return float(np.interp(float(xfrac), xhat[order], u[order]))


def _point_at_u(points: Array, u: Array, value: float) -> Array:
    return np.array([np.interp(value, u, points[:, axis]) for axis in range(3)])


def _resample_polyline_with_parameter(
    points: Array, parameter: Array, count: int
) -> tuple[Array, Array, Array]:
    points = np.asarray(points, dtype=float)
    parameter = np.asarray(parameter, dtype=float)
    if count < 2 or len(points) < 2:
        raise ValueError("a curve needs at least two source and target points")
    if parameter.shape != (len(points),):
        raise ValueError("curve parameter must have one value per source point")
    distance = np.linalg.norm(np.diff(points, axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(distance)])
    if cumulative[-1] <= 1.0e-14:
        raise ValueError("cannot resample a zero-length curve")
    target = np.linspace(0.0, cumulative[-1], count)
    sampled = np.column_stack([np.interp(target, cumulative, points[:, axis]) for axis in range(3)])
    sampled_parameter = np.interp(target, cumulative, parameter)
    return sampled, sampled_parameter, target


def surface_interface_report(
    blocks: list[SurfaceBlock], *, tolerance_m: float = 1.0e-8
) -> dict[str, Any]:
    """Verify the fixed S6 block graph before any volume work."""
    edges: list[dict[str, Any]] = []
    for block in blocks:
        xyz = np.asarray(block.xyz, dtype=float)
        for side, nodes in (
            ("i0", xyz[0]),
            ("i1", xyz[-1]),
            ("j0", xyz[:, 0]),
            ("j1", xyz[:, -1]),
        ):
            edges.append({"block": block.name, "side": side, "nodes": nodes})

    used: set[int] = set()
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(edges):
        if left_index in used:
            continue
        best: tuple[float, int, bool] | None = None
        for right_index in range(left_index + 1, len(edges)):
            if right_index in used or edges[right_index]["block"] == left["block"]:
                continue
            right_nodes = edges[right_index]["nodes"]
            if left["nodes"].shape != right_nodes.shape:
                continue
            direct = float(np.max(np.abs(left["nodes"] - right_nodes)))
            reverse = float(np.max(np.abs(left["nodes"] - right_nodes[::-1])))
            candidate = (direct, right_index, False)
            if reverse < direct:
                candidate = (reverse, right_index, True)
            if best is None or candidate[0] < best[0]:
                best = candidate
        if best is None or best[0] > tolerance_m:
            continue
        mismatch, right_index, reverse = best
        right = edges[right_index]
        used.update((left_index, right_index))
        pairs.append(
            {
                "left": f"{left['block']}:{left['side']}",
                "right": f"{right['block']}:{right['side']}",
                "reversed": reverse,
                "max_mismatch_m": mismatch,
            }
        )
    return {
        "paired_edge_count": len(pairs),
        "max_mismatch_m": max((pair["max_mismatch_m"] for pair in pairs), default=float("inf")),
        "pairs": pairs,
    }


def _segment_with_parameter(
    points: Array, u: Array, u0: float, u1: float, count: int
) -> tuple[Array, Array, Array]:
    lo, hi = min(u0, u1), max(u0, u1)
    mask = (u > lo) & (u < hi)
    interior = points[mask]
    interior_u = u[mask]
    if u1 < u0:
        interior = interior[::-1]
        interior_u = interior_u[::-1]
    curve = np.vstack([_point_at_u(points, u, u0), interior, _point_at_u(points, u, u1)])
    curve_u = np.concatenate([[u0], interior_u, [u1]])
    return _resample_polyline_with_parameter(curve, curve_u, count)


def _section_arcs(
    pygeo: Any,
    v: float,
    *,
    spec: LevelSpec,
    te_abs_m: float,
    te_floor_frac: float,
    end_scale: float,
) -> tuple[dict[str, Array], dict[str, Any]]:
    """Return the six S1-compatible OML arcs directly on the pyGeo loft."""
    u, upper, lower, frame = _frame_and_opened_curves(
        pygeo,
        v,
        dense_points=spec.dense_curve_points,
        te_abs_m=te_abs_m,
        te_floor_frac=te_floor_frac,
    )
    outer_nose_xfrac = 0.5 * float(end_scale) * NOSE_END_FRAC
    u_mid_upper = _u_at_xfrac(upper, u, frame, 0.5)
    u_mid_lower = _u_at_xfrac(lower, u, frame, 0.5)
    u_nose_upper = _u_at_xfrac(upper, u, frame, outer_nose_xfrac)
    u_nose_lower = _u_at_xfrac(lower, u, frame, outer_nose_xfrac)

    nose_source_count = max(41, spec.dense_curve_points // 8)
    upper_nose, upper_nose_u, upper_nose_distance = _segment_with_parameter(
        upper, u, u_nose_upper, 1.0, nose_source_count
    )
    lower_nose, lower_nose_u, _lower_nose_distance = _segment_with_parameter(
        lower, u, 1.0, u_nose_lower, nose_source_count
    )
    nose_source = np.vstack([upper_nose, lower_nose[1:]])
    nose_source_u = np.concatenate([upper_nose_u, lower_nose_u[1:]])
    nose, nose_u, nose_distance = _resample_polyline_with_parameter(
        nose_source, nose_source_u, spec.end_points
    )

    upper_aft, upper_aft_u, _ = _segment_with_parameter(
        upper, u, 0.0, u_mid_upper, spec.chord_points
    )
    upper_fore, upper_fore_u, _ = _segment_with_parameter(
        upper, u, u_mid_upper, u_nose_upper, spec.chord_points
    )
    lower_fore, lower_fore_u, _ = _segment_with_parameter(
        lower, u, u_nose_lower, u_mid_lower, spec.chord_points
    )
    lower_aft, lower_aft_u, _ = _segment_with_parameter(
        lower, u, u_mid_lower, 0.0, spec.chord_points
    )

    outer = {
        "upper_aft": upper_aft,
        "upper_fore": upper_fore,
        "nose": nose,
        "lower_fore": lower_fore,
        "lower_aft": lower_aft,
        "base": np.linspace(lower[0], upper[0], spec.end_points),
    }

    independent_reference = {
        "upper_aft": _opened_points_at_u(pygeo, upper_aft_u, v, frame=frame, upper=True),
        "upper_fore": _opened_points_at_u(pygeo, upper_fore_u, v, frame=frame, upper=True),
        "lower_fore": _opened_points_at_u(pygeo, lower_fore_u, v, frame=frame, upper=False),
        "lower_aft": _opened_points_at_u(pygeo, lower_aft_u, v, frame=frame, upper=False),
        "base": outer["base"].copy(),
    }
    nose_reference = np.empty_like(nose)
    nose_on_upper = nose_distance <= upper_nose_distance[-1] + 1.0e-14
    nose_reference[nose_on_upper] = _opened_points_at_u(
        pygeo,
        nose_u[nose_on_upper],
        v,
        frame=frame,
        upper=True,
    )
    nose_reference[~nose_on_upper] = _opened_points_at_u(
        pygeo,
        nose_u[~nose_on_upper],
        v,
        frame=frame,
        upper=False,
    )
    independent_reference["nose"] = nose_reference
    fidelity_by_arc_m = {
        key: float(np.max(np.linalg.norm(outer[key] - independent_reference[key], axis=1)))
        for key in ARC_ORDER
    }
    fidelity_max_m = max(fidelity_by_arc_m.values())
    return outer, {
        "frame": frame,
        "u": u,
        "upper": upper,
        "lower": lower,
        "outer_nose_xfrac": outer_nose_xfrac,
        "construction_fidelity_by_arc_m": fidelity_by_arc_m,
        "construction_fidelity_max_m": fidelity_max_m,
        "construction_fidelity_max_frac": fidelity_max_m / frame.chord,
    }


def _tip_clustered_parameters(
    pygeo: Any,
    *,
    n_cells: int,
    first_cell_m: float,
    max_cell_m: float,
) -> tuple[Array, float, float, float]:
    """Fixed-count span parameters with both tip matching and a size cap."""
    dense_v = np.linspace(0.0, 1.0, 4001)
    quarter = np.asarray(pygeo.surfs[0](np.full_like(dense_v, 0.5), dense_v), dtype=float).reshape(
        -1, 3
    )
    cumulative = np.concatenate(
        [[0.0], np.cumsum(np.linalg.norm(np.diff(quarter, axis=0), axis=1))]
    )
    span_length = float(cumulative[-1])
    if n_cells < 2 or max_cell_m <= 0.0:
        raise ValueError("span spacing needs at least two cells and a positive cap")
    if n_cells * max_cell_m < span_length:
        raise ValueError(
            f"{n_cells} span cells capped at {max_cell_m:g} m cannot cover "
            f"the {span_length:g} m quarter-chord line"
        )
    first_cell_m = float(np.clip(first_cell_m, 1.0e-6, span_length / n_cells))
    maximum_coverage = first_cell_m + (n_cells - 1) * max_cell_m
    if maximum_coverage <= span_length * (1.0 + 1.0e-12):
        raise ValueError(
            f"{n_cells} span cells with first={first_cell_m:g} m and "
            f"cap={max_cell_m:g} m cover at most {maximum_coverage:g} m, "
            f"below the {span_length:g} m quarter-chord line"
        )

    max_exponent = max(0.0, float(np.log(max_cell_m / first_cell_m)))

    def widths(log_ratio: float) -> Array:
        exponent = np.minimum(np.arange(n_cells) * log_ratio, max_exponent)
        return first_cell_m * np.exp(exponent)

    lo, hi = 0.0, max_exponent
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if float(widths(mid).sum()) < span_length:
            lo = mid
        else:
            hi = mid
    log_ratio = 0.5 * (lo + hi)
    ratio = float(np.exp(log_ratio))
    widths_tip_to_root = widths(log_ratio)
    widths_tip_to_root *= span_length / float(widths_tip_to_root.sum())
    arc_edges = np.concatenate([[0.0], np.cumsum(widths_tip_to_root[::-1])])
    arc_edges /= arc_edges[-1]
    v_edges = np.interp(arc_edges, cumulative / span_length, dense_v)
    v_edges[-1] = 1.0
    return v_edges, ratio, span_length, float(widths_tip_to_root.max())


def _tip_coordinates_2d(meta: dict[str, Any]) -> tuple[Array, int]:
    frame: SectionFrame = meta["frame"]

    def project(points: Array) -> Array:
        delta = points - frame.le
        return np.column_stack([delta @ frame.chord_axis, delta @ frame.thickness_axis])

    upper = project(meta["upper"])
    lower = project(meta["lower"])
    coords = np.vstack([upper, lower[-2::-1]])
    return coords, len(upper) - 1


def _map_tip_patch(patch: Array, frame: SectionFrame) -> Array:
    return (
        frame.le
        + patch[..., 0, None] * frame.chord_axis
        + patch[..., 1, None] * frame.thickness_axis
    )


def _attach_outer_edge(patch: Array, outer: Array) -> Array:
    """Replace whichever collar edge corresponds to the exact OML tip arc."""
    result = patch.copy()
    candidates = []
    for edge_index in (0, -1):
        edge = result[:, edge_index, :]
        candidates.append((float(np.max(np.linalg.norm(edge - outer, axis=1))), edge_index, False))
        candidates.append(
            (float(np.max(np.linalg.norm(edge - outer[::-1], axis=1))), edge_index, True)
        )
    _error, edge_index, reverse = min(candidates, key=lambda item: item[0])
    result[:, edge_index, :] = outer[::-1] if reverse else outer
    return result


def _tip_blocks(
    tip_meta: dict[str, Any],
    oml_arrays: dict[str, Array],
    *,
    spec: LevelSpec,
    end_scale: float,
) -> tuple[list[SurfaceBlock], dict[str, Any]]:
    coords, le_index = _tip_coordinates_2d(tip_meta)
    geom = section_geometry(
        coords,
        le_index,
        chord_points=spec.chord_points,
        end_points=spec.end_points,
        ratio=1.0,
        end_scale=end_scale,
    )
    frame: SectionFrame = tip_meta["frame"]
    for key in ARC_ORDER:
        exact = oml_arrays[key][:, -1, :]
        delta = exact - frame.le
        geom["outer"][key] = np.column_stack(
            [delta @ frame.chord_axis, delta @ frame.thickness_axis]
        )
    patches_2d, cap_info = tip_domains_2d(geom, collar_points=spec.collar_points)
    patches = [_map_tip_patch(patch, frame) for patch in patches_2d]
    blocks = [
        SurfaceBlock(name=name, xyz=patch, family="wall")
        for name, patch in zip(cap_info["block_names"], patches, strict=True)
    ]
    return blocks, cap_info


def build_surface(
    pygeo_result: Any,
    *,
    level: str = "smoke",
    te_abs_m: float = 0.001,
    te_floor_frac: float = 0.005,
    end_scale: float = 5.0,
    tip_first_cell_frac_of_tip_chord: float = 0.0045,
    span_cells: int | None = None,
) -> tuple[list[SurfaceBlock], dict[str, Any]]:
    """Build the exact-pyGeo S6 surface with fixed dimensions at each level."""
    if level not in LEVELS:
        raise KeyError(f"unknown level {level!r}; known: {sorted(LEVELS)}")
    spec = LEVELS[level]
    if span_cells is not None:
        if span_cells < 2:
            raise ValueError("span_cells must be at least 2")
        spec = replace(spec, span_cells=int(span_cells))
    pygeo = pygeo_result.pygeo.geometry

    _tip_arcs, tip_probe = _section_arcs(
        pygeo,
        1.0,
        spec=spec,
        te_abs_m=te_abs_m,
        te_floor_frac=te_floor_frac,
        end_scale=end_scale,
    )
    tip_frame: SectionFrame = tip_probe["frame"]
    first_cell_m = tip_first_cell_frac_of_tip_chord * tip_frame.chord
    span_fractions, span_ratio, span_length, realized_max_span_cell = _tip_clustered_parameters(
        pygeo,
        n_cells=spec.span_cells,
        first_cell_m=first_cell_m,
        max_cell_m=spec.span_max_cell_m,
    )

    columns: dict[str, list[Array]] = {key: [] for key in ARC_ORDER}
    tip_meta = None
    target_te_min = np.inf
    target_te_max = 0.0
    fidelity_max_m = 0.0
    fidelity_max_frac = 0.0
    fidelity_by_arc_m = {key: 0.0 for key in ARC_ORDER}
    for v in span_fractions:
        arcs, meta = _section_arcs(
            pygeo,
            float(v),
            spec=spec,
            te_abs_m=te_abs_m,
            te_floor_frac=te_floor_frac,
            end_scale=end_scale,
        )
        for key in ARC_ORDER:
            columns[key].append(arcs[key])
        target_te = float(meta["frame"].target_te)
        target_te_min = min(target_te_min, target_te)
        target_te_max = max(target_te_max, target_te)
        fidelity_max_m = max(fidelity_max_m, meta["construction_fidelity_max_m"])
        fidelity_max_frac = max(fidelity_max_frac, meta["construction_fidelity_max_frac"])
        for key, error_m in meta["construction_fidelity_by_arc_m"].items():
            fidelity_by_arc_m[key] = max(fidelity_by_arc_m[key], error_m)
        if v == span_fractions[-1]:
            tip_meta = meta

    oml_arrays = {key: np.stack(value, axis=1) for key, value in columns.items()}
    blocks = [
        SurfaceBlock(name=f"oml_{key}", xyz=oml_arrays[key], family="wall") for key in ARC_ORDER
    ]
    if tip_meta is None:
        raise RuntimeError("tip section was not built")
    tip_blocks, cap_info = _tip_blocks(tip_meta, oml_arrays, spec=spec, end_scale=end_scale)
    tip_normal = _unit(
        np.cross(tip_frame.chord_axis, tip_frame.thickness_axis),
        "tip-cap normal",
    )
    tip_planarity_max_m = max(
        float(np.max(np.abs((block.xyz - tip_frame.le) @ tip_normal))) for block in tip_blocks
    )
    fidelity_max_m = max(fidelity_max_m, tip_planarity_max_m)
    fidelity_max_frac = max(fidelity_max_frac, tip_planarity_max_m / tip_frame.chord)
    blocks.extend(tip_blocks)
    blocks, orientation = orient_blocks_consistently(blocks)
    qc = qc_blocks(blocks)
    interfaces = surface_interface_report(blocks)
    surface_failures: list[str] = []
    if interfaces["paired_edge_count"] != 20 or interfaces["max_mismatch_m"] > 1.0e-10:
        surface_failures.append("surface_block_interface_graph")
    if fidelity_max_frac > 1.0e-4:
        surface_failures.append("surface_fidelity")
    if surface_failures:
        qc["accepted_pre_pyhyp"] = False
        qc["failure_reasons"] = [
            *qc["failure_reasons"],
            *surface_failures,
        ]
    qc["surface_interfaces"] = interfaces

    info = {
        "strategy_id": STRATEGY_ID,
        "geometry_id": pygeo_result.geometry_id,
        "master_geometry": "direct pyGeo B-spline evaluation",
        "level": level,
        "level_spec": asdict(spec),
        "block_count": len(blocks),
        "dimension_signature": [(b.name, list(b.xyz.shape)) for b in blocks],
        "spanwise": {
            "cells": spec.span_cells,
            "first_cell_target_m": first_cell_m,
            "geometric_ratio_tip_to_root": span_ratio,
            "quarter_chord_length_m": span_length,
            "max_cell_target_m": spec.span_max_cell_m,
            "max_cell_realized_m": realized_max_span_cell,
            "fractions": span_fractions.tolist(),
        },
        "cfd_safe_te": {
            "law": "max(te_abs_m, te_floor_frac * local_chord)",
            "te_abs_m": te_abs_m,
            "te_floor_frac": te_floor_frac,
            "realized_min_m": target_te_min,
            "realized_max_m": target_te_max,
            "status": "declared numerical geometry; aerodynamic sensitivity required",
        },
        "tip": cap_info,
        "fidelity": {
            "reference": "CFD-safe pyGeo loft after the declared TE opening",
            "instrument": (
                "each OML node is independently re-evaluated on the pyGeo curve "
                "at its tracked parametric coordinate; the declared tip cap is "
                "checked against its exact plane"
            ),
            "span_columns_checked": len(span_fractions),
            "max_node_to_parametric_curve_m": fidelity_max_m,
            "max_fraction_of_local_chord": fidelity_max_frac,
            "oml_max_by_arc_m": fidelity_by_arc_m,
            "tip_planarity_max_m": tip_planarity_max_m,
            "limit_fraction_of_local_chord": 1.0e-4,
            "passed": fidelity_max_frac <= 1.0e-4,
        },
        "orientation": orientation,
        "surface_qc": qc,
    }
    return blocks, info


def build_locked_surface(
    set_name: str,
    index: int,
    output_dir: Path,
    *,
    level: str = "smoke",
    **kwargs: Any,
) -> tuple[list[SurfaceBlock], dict[str, Any], Any]:
    gid = geometry_id(set_name, index)
    case = build_pygeo_case(set_name, index, Path(output_dir) / gid / "geometry")
    if case.pygeo_result is None:
        raise RuntimeError("the canonical geometry config did not produce a pyGeo result")
    blocks, info = build_surface(case.pygeo_result, level=level, **kwargs)
    info["locked_set_id"] = gid
    info["design_sample"] = case.sample.to_dict()
    return blocks, info, case


===== FILE: ./S6_bounded_mesh_atlas/STUDY.md =====

# S6 study record

## Hypothesis

A proven S1 volume can be moved to an exact pyGeo wall while preserving its
structured topology and acceptable cell quality. A small set of such volumes can
serve a large campaign more reliably than remarching every exact surface.

## Implemented

- Direct evaluation of both pyGeo B-spline patches.
- S1/Openblademesh six-arc OML and seven-block tip closure.
- Exact pyGeo sampling at every span column.
- Template-specific span dimensions.
- Deterministic maximin atlas selection in the 16 neutral-OML-active dimensions.
- Deterministic quality-aware atlas enrichment before holdout freeze.
- Global chord/span affine map plus bounded column residual deformation.
- CGNS coordinate writer with source hashes.
- Independent cell volume and eight-corner scaled Jacobian audit.
- CLI, pilot harness, policy, and focused tests.

## Measurements

Surface development check, indices 0 through 9:

- 10/10 passed.
- One 13-block connectivity graph.
- Minimum surface scaled Jacobian range: +0.238 to +0.255.
- The original construction-polyline fidelity value was self-referential and is
  withdrawn. The corrected instrument tracks each node's parametric coordinate,
  independently re-evaluates pyGeo, and checks the planar tip cap. Geometry 000
  passes at `1.4081e-5` local chord versus the `1.0e-4` gate.

Same-geometry S1 volume to exact S6 wall, indices 0 through 9:

- 10/10 passed the +0.10 production floor.
- Zero inverted cells in every case.
- Worst minimum volume scaled Jacobian: +0.146067.
- Wall error: at most 1.74e-18 m.

Cross-design test, S1 template 000 to exact target 083:

- 1,621,504 cells.
- Zero inverted cells.
- Minimum volume: 8.72e-12 m3.
- Minimum scaled Jacobian: +0.196745.
- Wall error: 1.74e-18 m.
- Written CGNS independently classified clean.

Preliminary development-atlas preflight, using the provisional first ten S1 seeds:

- 100/100 geometries passed without manual repair.
- 184 template attempts: 100 passed, 81 failed quality, and three incompatible span
  laws were skipped automatically.
- Worst accepted minimum scaled Jacobian: +0.110341.
- This exposed and fixed a non-finite tip-spacing solver bug.
- This result is diagnostic only; those seeds were not selected by the final metric.

Geometry-active maximin smoke atlas:

- All 16 selected seeds marched and passed full volume/interface audit.
- Seed minimum scaled quality range: +0.15081 to +0.21498.
- 100/100 development geometries passed with no manual repair.
- 131 total attempts: 80 first-try routes and no route longer than five attempts.
- Worst accepted quality +0.15184; p05 +0.16950; median +0.20111.
- All 16 templates were selected by at least two targets.
- No quality-aware enrichment seed was needed at smoke resolution.
- This is not a holdout-unlock: production-resolution 100/100 is still required.

Production maximin seed atlas, fixed provisional policy:

- `N=257`, `epsE=1.5`, first-cell fraction `3.6e-6`.
- 16/16 templates passed; zero inverted cells and zero cells below `0.10`.
- Minimum/p05/median/maximum independent quality: `0.10535`, `0.11869`,
  `0.20978`, `0.23471`.
- Only three cells are below `0.15`; they are first-layer tip/trailing-edge cells
  in seeds 002 and 068.
- The campaign-equivalent written-CGNS canary passed targets 000 and 083.
- The complete 100-target production audit is running. No freeze claim yet.

Coarse CFD plumbing pilot, geometry 083:

- ADflow RANS-SA converged by 7.59 residual orders in 159 monitor rows.
- Final coefficients were CL -0.01947, CD +0.03366, and CMy +0.03006.
- It was correctly rejected by the wall gate: y+ p95 2.41 and maximum 7.23.
- This proves the solve and rejection path, not production wall resolution.

Old direct-march diagnostic:

- Direct pyHyp march of exact S6 target 083 failed at layer 2 and the runner
  exited with signal 11.
- It ran before the surface-interface basis correction and is therefore inconclusive.
- The atlas is selected for audited reuse and bounded recovery, not because this stale
  diagnostic proves a corrected direct march impossible.
- The target-specific fallback is S1 march followed by S6 exact-wall deformation.

## Artifacts

- `artifacts/s6_bounded_mesh_atlas/atlas_manifest_v2.json`
- `artifacts/s6_bounded_mesh_atlas/development_pilot/pilot_report.json`
- `artifacts/s6_bounded_mesh_atlas/pilot_000_to_083/deformation_report.json`
- `artifacts/s6_bounded_mesh_atlas/pilot_000_to_083/wing_vol.cgns`
- `artifacts/s6_bounded_mesh_atlas/development_atlas_smoke_all100/`
- `artifacts/s6_bounded_mesh_atlas/development_atlas_maximin16_smoke/`
- `artifacts/s6_bounded_mesh_atlas/atlas_manifest_smoke_enriched_v3.json`
- `artifacts/s6_bounded_mesh_atlas/cfd_pilot_083_n65_lowmem/`
- `artifacts/s6_bounded_mesh_atlas/campaign_preflight_10000/`
- `artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_qualified16_eps15_s0p3p6_v5.json`
- `artifacts/s6_bounded_mesh_atlas/development_atlas_production_written_canary_v2/`
- `AERIS_MESH_STUDY/artifacts/strategy_studies/S6_bounded_mesh_atlas/maximin_v3/calibration_s0_3p6_production/`

## Not yet frozen

- The final atlas is still being validated at production normal resolution.
- The locked holdout has not been opened.
- Production-resolution CFD has not run; the local 16 GB machine is insufficient.
- The TE numerical-geometry aerodynamic sensitivity is still required.
- Grid convergence and turbulence-model uncertainty are not established.
- The 100-case CFD pilot and 500-1,000-case HPC rehearsal have not run.
- Production readiness cannot be claimed until the gates in `ROADMAP.md` pass.


===== FILE: ./S6_bounded_mesh_atlas/test_s6.py =====

"""Focused unit tests for the S6 bounded mesh atlas."""

from __future__ import annotations

import csv
import json
import socket
import sys
import time
from pathlib import Path

import atlas
import audit_validation
import campaign
import cfd_qc
import deform
import h5py
import numpy as np
import pytest
import qualification
import resolution
import strategy_s6
import yaml
from shared import volume_qc


def test_qualification_plan_refines_all_directions_and_protects_holdout() -> None:
    plan = qualification.build_qualification_plan()
    assert plan["holdout_accessed"] is False
    assert plan["laptop_smoke"]["production_claim_allowed"] is False
    assert plan["laptop_smoke"]["template_routes"] == {"42": 42, "95": 95, "7": 95}
    assert (
        plan["laptop_smoke"]["production_wall_law_conclusion"]
        == "NOT_TESTED_AT_PRODUCTION_RESOLUTION"
    )
    assert plan["current_candidate_wall_test"]["surface_level"] == "smoke"
    assert plan["current_candidate_wall_test"]["normal_points"] == 257
    p0_span = plan["current_candidate_wall_test"]["span_cells"]
    assert p0_span["mode"] == "geometry_dependent_from_selected_registry_template"
    assert p0_span["minimum"] == 60
    assert p0_span["maximum"] == 98
    assert p0_span["by_template_geometry"]["42"] == 75
    assert p0_span["by_template_geometry"]["95"] == 85
    assert plan["preregistration_evidence"] is False
    assert set(plan["implementation_provenance"]) == {
        "qualification_sha256",
        "strategy_s6_sha256",
        "campaign_mesh_implementation_sha256",
        "campaign_solver_implementation_sha256",
    }
    p0 = plan["current_candidate_wall_test"]
    assert "smoke tangential" in " ".join(p0["limitations"])
    assert p0["production_resolution_scope"].startswith("wall_normal_candidate")

    levels = plan["grid_study"]["levels"]
    for left, right in zip(levels[:-1], levels[1:], strict=True):
        for field in (
            "chord_points",
            "end_points",
            "collar_points",
            "span_cells",
            "normal_points",
        ):
            assert right[field] > left[field]
        assert (
            right["first_cell_fraction_characteristic"] < left["first_cell_fraction_characteristic"]
        )

    variants = plan["trailing_edge_study"]["variants"]
    assert [variant["name"] for variant in variants] == [
        "TE_small",
        "TE_baseline",
        "TE_large",
    ]
    te_metric = plan["trailing_edge_study"]["material_change_metric"]
    assert te_metric["reference_variant"] == "TE_baseline"
    assert "variant-baseline" in te_metric["formula"]
    assert te_metric is not plan["grid_study"]["medium_to_fine_gate"]
    assert [variant["te_abs_m"] for variant in variants] == sorted(
        variant["te_abs_m"] for variant in variants
    )


def test_local_solver_path_classification_excludes_yplus_by_design() -> None:
    assert qualification._local_solver_path_passed(
        returncode=0,
        solver_status="converged",
        residual_orders=6.1,
        force_plausibility={"passed": True},
        force_tail={"passed": True},
    )
    assert not qualification._local_solver_path_passed(
        returncode=0,
        solver_status="converged",
        residual_orders=5.9,
        force_plausibility={"passed": True},
        force_tail={"passed": True},
    )


def test_qualification_caches_require_matching_provenance(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text("registry", encoding="utf-8")
    output_cgns = tmp_path / "template.cgns"
    source_cgns = tmp_path / "source.cgns"
    surface_npz = tmp_path / "surface.npz"
    pyhyp_options = tmp_path / "pyhyp_options.json"
    surface_fmt = tmp_path / "surface.fmt"
    for path, content in (
        (output_cgns, b"output"),
        (source_cgns, b"source"),
        (surface_npz, b"surface"),
        (pyhyp_options, b"options"),
        (surface_fmt, b"fmt"),
    ):
        path.write_bytes(content)

    template_report_path = tmp_path / "template_report.json"
    template_report = {
        "schema": qualification.LAPTOP_TEMPLATE_SCHEMA,
        "state": "PASS",
        "source_registry_sha256": deform.sha256(registry),
        "mesh_implementation_sha256": "implementation-a",
        "cgns": str(output_cgns),
        "cgns_sha256": deform.sha256(output_cgns),
        "source_cgns": str(source_cgns),
        "source_cgns_sha256": deform.sha256(source_cgns),
        "surface_npz": str(surface_npz),
        "surface_npz_sha256": deform.sha256(surface_npz),
        "source_pyhyp_options": str(pyhyp_options),
        "source_pyhyp_options_sha256": deform.sha256(pyhyp_options),
        "source_surface_fmt": str(surface_fmt),
        "source_surface_fmt_sha256": deform.sha256(surface_fmt),
    }
    template_report_path.write_text(json.dumps(template_report), encoding="utf-8")
    assert qualification._accepted_existing_template(
        template_report_path,
        expected_registry_sha256=deform.sha256(registry),
        expected_implementation_sha256="implementation-a",
    )
    assert not qualification._accepted_existing_template(
        template_report_path,
        expected_registry_sha256="changed-registry",
        expected_implementation_sha256="implementation-a",
    )
    assert not qualification._accepted_existing_template(
        template_report_path,
        expected_registry_sha256=deform.sha256(registry),
        expected_implementation_sha256="implementation-b",
    )
    surface_fmt.write_bytes(b"changed")
    assert not qualification._accepted_existing_template(
        template_report_path,
        expected_registry_sha256=deform.sha256(registry),
        expected_implementation_sha256="implementation-a",
    )

    mesh = tmp_path / "mesh.cgns"
    mesh.write_bytes(b"mesh")
    mesh_report_path = tmp_path / "mesh_report.json"
    mesh_report_path.write_text(
        json.dumps(
            {
                "schema": qualification.LAPTOP_MESH_SCHEMA,
                "state": "MESH_ACCEPTED",
                "mesh_cgns": str(mesh),
                "mesh_cgns_sha256": deform.sha256(mesh),
                "template_cgns_sha256": "template-a",
                "template_surface_sha256": "surface-a",
                "mesh_implementation_sha256": "implementation-a",
            }
        ),
        encoding="utf-8",
    )
    assert qualification._accepted_existing_mesh(
        mesh_report_path,
        expected_template_sha256="template-a",
        expected_template_surface_sha256="surface-a",
        expected_implementation_sha256="implementation-a",
    )
    assert not qualification._accepted_existing_mesh(
        mesh_report_path,
        expected_template_sha256="template-b",
        expected_template_surface_sha256="surface-a",
        expected_implementation_sha256="implementation-a",
    )
    assert not qualification._accepted_existing_mesh(
        mesh_report_path,
        expected_template_sha256="template-a",
        expected_template_surface_sha256="surface-b",
        expected_implementation_sha256="implementation-a",
    )
    assert not qualification._accepted_existing_mesh(
        mesh_report_path,
        expected_template_sha256="template-a",
        expected_template_surface_sha256="surface-a",
        expected_implementation_sha256="implementation-b",
    )


def test_laptop_cfd_cache_binds_mesh_solver_and_mpi(tmp_path: Path) -> None:
    solve_report = tmp_path / "solve_report.json"
    solver_log = tmp_path / "adflow_run.log"
    surface_solution = tmp_path / "surface.cgns"
    solve_report.write_text("{}", encoding="utf-8")
    solver_log.write_text("solver output", encoding="utf-8")
    surface_solution.write_bytes(b"surface solution")
    report_path = tmp_path / "laptop_cfd_report.json"
    report_path.write_text(
        json.dumps(
            {
                "schema": qualification.LAPTOP_CFD_SCHEMA,
                "state": "LOCAL_SOLVER_PATH_PASSED",
                "mesh_cgns_sha256": "mesh-a",
                "solver_implementation_sha256": "solver-a",
                "mpi_processes": 4,
                "solve_report": str(solve_report),
                "solve_report_sha256": deform.sha256(solve_report),
                "solver_log": str(solver_log),
                "solver_log_sha256": deform.sha256(solver_log),
                "wall_yplus_gate": {
                    "surface_cgns": str(surface_solution),
                    "surface_cgns_sha256": deform.sha256(surface_solution),
                },
            }
        ),
        encoding="utf-8",
    )
    assert qualification._existing_laptop_cfd_result(
        report_path,
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    assert not qualification._existing_laptop_cfd_result(
        report_path,
        mesh_sha256="mesh-b",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    assert not qualification._existing_laptop_cfd_result(
        report_path,
        mesh_sha256="mesh-a",
        implementation_sha256="solver-b",
        mpi_np=4,
    )
    assert not qualification._existing_laptop_cfd_result(
        report_path,
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=2,
    )
    surface_solution.write_bytes(b"changed surface solution")
    assert not qualification._existing_laptop_cfd_result(
        report_path,
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    assert qualification._mpi_deviation_reason(None, 4) == ("actual_rank_count_missing_or_invalid")
    assert qualification._mpi_deviation_reason(2, 4) == (
        "actual_below_plan_reason_not_recorded_in_case_report"
    )
    assert qualification._mpi_deviation_reason(8, 4) == (
        "actual_above_plan_reason_not_recorded_in_case_report"
    )
    assert qualification._mpi_deviation_reason(4, 4) == "no_deviation"


def test_main_routes_legacy_laptop_audit(monkeypatch, tmp_path, capsys) -> None:
    audit_output = tmp_path / "audit.json"
    called = {}

    def fake_audit(*, indices, output, audit_output):
        called.update(
            indices=indices,
            output=output,
            audit_output=audit_output,
        )
        return {"state": "AUDITED"}

    monkeypatch.setattr(qualification, "audit_legacy_laptop", fake_audit)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qualification.py",
            "audit-legacy-laptop",
            "--output",
            str(tmp_path),
            "--audit-output",
            str(audit_output),
            "--indices",
            "42",
        ],
    )
    assert qualification.main() == 0
    assert called == {
        "indices": [42],
        "output": tmp_path,
        "audit_output": audit_output,
    }
    assert json.loads(capsys.readouterr().out) == {"state": "AUDITED"}


def test_primary_span_count_is_independent_of_block_order() -> None:
    tip = np.zeros((5, 3, 3))
    oml = np.zeros((5, 76, 3))
    assert qualification._primary_span_cells({"tip": tip, "oml": oml}) == 75
    assert qualification._primary_span_cells({"oml": oml, "tip": tip}) == 75


def test_collect_laptop_preserves_historical_summary(tmp_path, monkeypatch) -> None:
    historical = tmp_path / "laptop_summary.json"
    historical.write_bytes(b"historical evidence\n")
    monkeypatch.setattr(qualification, "DEFAULT_REGISTRY", tmp_path / "missing_registry.json")
    report_path = tmp_path / "lhs100_seed42_042" / "cfd" / "laptop_cfd_report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "schema": qualification.LAPTOP_CFD_SCHEMA,
                "state": "LOCAL_SOLVER_PATH_PASSED",
                "geometry_index": 42,
                "holdout_accessed": False,
                "mpi_processes": 2,
                "solver_implementation_sha256": "stale",
                "flow": qualification.FLOW,
            }
        ),
        encoding="utf-8",
    )

    summary = qualification.collect_laptop(indices=[42], output=tmp_path)

    assert historical.read_bytes() == b"historical evidence\n"
    assert Path(summary["summary_path"]).name == "laptop_summary_current.json"
    assert Path(summary["summary_path"]).is_file()
    assert summary["completed"] == 0
    assert summary["stale_or_invalid"] == 1
    assert summary["solver_path_passed"] is None
    assert summary["wall_yplus_passed"] is None
    assert summary["protocol_deviations"] == [
        {
            "geometry_index": 42,
            "row_state": "STALE_OR_INVALID_PROVENANCE",
            "field": "mpi_processes",
            "planned": 4,
            "actual": 2,
            "reason": "actual_below_plan_reason_not_recorded_in_case_report",
        }
    ]


def test_development_report_auditor_checks_written_selection(tmp_path) -> None:
    missing_mesh = tmp_path / "pruned.cgns"
    selected = {
        "template_index": 42,
        "state": "PASS",
        "selected": True,
        "min_scaled_quality": 0.18,
        "wall_error_m": 0.0,
        "interface_max_mismatch_m": 0.0,
        "surface_fidelity": {
            "passed": True,
            "max_fraction_of_local_chord": 1.0e-5,
        },
        "first_layer_spacing": {
            "deformed": {
                "nonfinite_count": 0,
                "nonpositive_count": 0,
                "min_fraction_characteristic": 3.5e-6,
                "p95_fraction_characteristic": 3.7e-6,
            }
        },
        "independent_written_acceptance": {
            "hard_gate_passed": True,
            "production_floor_passed": True,
            "quality": {
                "min_scaled_quality": 0.18,
                "min_volume": 1.0e-9,
                "inverted_cells": 0,
                "total_cells": 100,
                "cells_below_0_10": 0,
                "cells_below_0_15": 0,
            },
        },
        "interface_pair_count": 1,
        "candidate_cgns_sha256": "abc",
    }
    report = {
        "schema": audit_validation.REPORT_SCHEMA,
        "campaign_equivalent_written_cgns_audit": True,
        "geometry_indices": [0],
        "template_indices": [42],
        "candidate_count": 1,
        "preferred_quality": 0.15,
        "attempted": 1,
        "passed": 1,
        "pass_fraction": 1.0,
        "worst_min_scaled_quality": 0.18,
        "rows": [
            {
                "geometry_index": 0,
                "state": "PASS",
                "attempts": [selected],
                "accepted_template_index": 42,
                "accepted_min_scaled_quality": 0.18,
                "accepted_cgns": str(missing_mesh),
                "accepted_cgns_sha256": "abc",
                "accepted_cgns_retained": False,
                "is_atlas_template_target": False,
                "selected_identity_deformation": False,
            }
        ],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    audit = audit_validation.audit_report(path, expected_count=1)
    assert audit["passed"]
    assert audit["report_integrity_passed"]
    assert audit["all_targets_passed"]
    assert audit["summary"]["first_try_passes"] == 1
    assert audit["summary"]["quality"]["minimum"] == pytest.approx(0.18)

    report["rows"][0]["accepted_min_scaled_quality"] = 0.17
    path.write_text(json.dumps(report), encoding="utf-8")
    audit = audit_validation.audit_report(path, expected_count=1)
    assert not audit["passed"]
    assert any("row quality differs" in error for error in audit["errors"])

    report["rows"][0]["accepted_min_scaled_quality"] = 0.18
    report["rows"][0]["state"] = "NEEDS_FALLBACK"
    report["rows"][0]["attempts"][0]["selected"] = False
    report["rows"][0]["accepted_template_index"] = None
    report["passed"] = 0
    report["pass_fraction"] = 0.0
    report["worst_min_scaled_quality"] = None
    path.write_text(json.dumps(report), encoding="utf-8")
    audit = audit_validation.audit_report(path, expected_count=1)
    assert audit["report_integrity_passed"]
    assert not audit["all_targets_passed"]
    assert not audit["passed"]


def test_production_wall_policy_matches_tested_calibration_and_is_numeric() -> None:
    policy = yaml.safe_load((Path(__file__).with_name("POLICY.yaml")).read_text())
    wall = policy["wall_spacing"]
    assert resolution.first_cell_fraction("production") == pytest.approx(3.6e-6)
    assert wall["production_development_fraction"] == pytest.approx(3.6e-6)
    assert wall["production_development_epsE"] == pytest.approx(1.5)
    assert isinstance(wall["reference_reynolds"], (int, float))
    assert wall["reference_reynolds"] == pytest.approx(resolution.REFERENCE_REYNOLDS)


def _cube() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    i = np.linspace(0.0, 1.0, 5)
    j = np.linspace(0.0, 1.0, 4)
    k = np.linspace(0.0, 3.0, 8)
    kk, jj, ii = np.meshgrid(k, j, i, indexing="ij")
    volume = {"zone": np.stack((ii, jj, kk), axis=-1)}
    surface = {"wall": volume["zone"][0].transpose(1, 0, 2)}
    return volume, surface


def test_volume_report_records_worst_cell_diagnostic() -> None:
    volume, _surface = _cube()
    report = volume_qc.volume_report(volume)
    worst = report["worst_cell"]
    assert worst["block"] == "zone"
    assert worst["cell_index_kji"] == [0, 0, 0]
    assert worst["wall_layer_index"] == 0
    assert worst["wall_distance_m"] == pytest.approx(0.0)
    assert worst["min_scaled_quality"] == pytest.approx(1.0)
    assert report["cells_below_0_10"] == 0
    assert report["cells_below_0_15"] == 0


def test_eps_e_paths_follow_the_governed_ladder(tmp_path) -> None:
    assert resolution.epsilon_tag(1.5) == "eps15"
    cgns, surface = campaign._template_paths(7, tmp_path, 1.5)
    assert cgns == tmp_path / "lhs100_seed42_007/eps15/wing_vol.cgns"
    assert surface == tmp_path / "lhs100_seed42_007/eps15/surface_blocks.npz"
    with pytest.raises(ValueError, match="frozen ladder"):
        resolution.epsilon_tag(1.7)


def test_deformation_reports_realized_first_layer_spacing() -> None:
    volume, surface = _cube()
    deformed, metadata = deform.deform_volume_blocks(volume, surface, surface)
    expected = 3.0 / 7.0
    spacing = metadata["first_layer_spacing"]["deformed"]
    assert spacing["nonfinite_count"] == 0
    assert spacing["nonpositive_count"] == 0
    assert spacing["min_m"] == pytest.approx(expected)
    assert spacing["max_m"] == pytest.approx(expected)

    written = deform.written_deformation_metadata(deformed, surface, metadata)
    assert written["max_wall_error_m"] == pytest.approx(0.0)
    assert written["first_layer_spacing"]["deformed"]["median_m"] == pytest.approx(expected)


def test_atlas_selection_is_deterministic_and_unique() -> None:
    rng = np.random.default_rng(4)
    points = rng.random((30, 6))
    first = atlas.farthest_point_indices(points, 8)
    second = atlas.farthest_point_indices(points, 8)
    assert first == second
    assert len(set(first)) == 8


def test_production_seed_qualification_prunes_and_never_freezes() -> None:
    manifest = atlas.build_atlas_manifest(template_count=3)
    templates = manifest["template_indices"]

    def row(index: int, quality: float, state: str = "PASS") -> dict:
        reasons = [] if state == "PASS" else ["quality_below_production_floor"]
        return {
            "geometry_index": index,
            "geometry_id": f"lhs100_seed42_{index:03d}",
            "state": state,
            "audit": {
                "state": state,
                "failure_reasons": reasons,
                "quality": {
                    "min_scaled_quality": quality,
                    "min_volume": 1.0,
                    "inverted_cells": 0,
                },
                "march_result": {"march_metrics": {"min_quality": quality + 0.2}},
            },
        }

    report = {
        "schema": "aeris.mesh.s6_seed_build.v1",
        "level": "production",
        "indices": templates,
        "attempted": 3,
        "rows": [
            row(templates[0], 0.16),
            row(templates[1], 0.03, "FAIL"),
            row(templates[2], 0.12),
        ],
    }
    qualified = atlas.qualify_atlas_seeds(manifest, report, minimum_templates=2)
    assert qualified["template_indices"] == [templates[0], templates[2]]
    evidence = qualified["seed_qualification"]
    assert [item["geometry_index"] for item in evidence["rejected"]] == [templates[1]]
    assert evidence["requires_complete_development_revalidation"]
    assert not evidence["freeze_ready"]


def test_seed_qualification_requires_complete_production_report() -> None:
    manifest = atlas.build_atlas_manifest(template_count=2)
    report = {
        "schema": "aeris.mesh.s6_seed_build.v1",
        "level": "smoke",
        "indices": manifest["template_indices"],
        "attempted": 0,
        "rows": [],
    }
    with pytest.raises(ValueError, match="production seed report"):
        atlas.qualify_atlas_seeds(manifest, report, minimum_templates=1)


def test_quality_enrichment_adds_weak_case_then_can_freeze() -> None:
    manifest = atlas.build_atlas_manifest(template_count=2)
    manifest["seed_qualification"] = {"evidence": "production-seeds"}
    manifest["prior_quality_enrichment"] = {"evidence": "smoke-history"}
    templates = manifest["template_indices"]
    weak_index = next(index for index in range(100) if index not in set(templates))

    def report_for(current: dict, weak: int | None) -> dict:
        rows = []
        for index in range(100):
            attempts = (
                [{"template_index": item} for item in current["template_indices"]]
                if index == weak
                else [{}]
            )
            rows.append(
                {
                    "geometry_index": index,
                    "state": "PASS",
                    "attempts": attempts,
                    "accepted_min_scaled_quality": (0.12 if index == weak else 0.20),
                }
            )
        return {
            "set_name": "lhs100_seed42",
            "volume_level": "production",
            "template_indices": current["template_indices"],
            "candidate_count": current["template_count"],
            "preferred_quality": 0.15,
            "rows": rows,
        }

    enriched = atlas.enrich_atlas_manifest(
        manifest,
        report_for(manifest, weak_index),
        maximum_templates=3,
    )
    assert enriched["template_indices"] == [*templates, weak_index]
    assert enriched["quality_enrichment"]["requires_revalidation"]
    assert not enriched["quality_enrichment"]["freeze_ready"]
    assert enriched["seed_qualification"] == manifest["seed_qualification"]
    assert enriched["prior_quality_enrichment"] == manifest["prior_quality_enrichment"]

    frozen = atlas.enrich_atlas_manifest(
        enriched,
        report_for(enriched, None),
        maximum_templates=3,
    )
    assert frozen["template_indices"] == enriched["template_indices"]
    assert not frozen["quality_enrichment"]["requires_revalidation"]
    assert frozen["quality_enrichment"]["freeze_ready"]

    existing_warning = atlas.enrich_atlas_manifest(
        manifest,
        report_for(manifest, templates[0]),
        maximum_templates=3,
    )
    warning = existing_warning["quality_enrichment"]
    assert warning["added_indices"] == []
    assert warning["unresolved_existing_template_cases"] == []
    assert [row["geometry_index"] for row in warning["accepted_existing_template_warnings"]] == [
        templates[0]
    ]
    assert warning["freeze_ready"]

    failed_existing_report = report_for(manifest, templates[0])
    failed_row = failed_existing_report["rows"][templates[0]]
    failed_row["state"] = "NEEDS_FALLBACK"
    failed_row["accepted_min_scaled_quality"] = None
    failed_existing = atlas.enrich_atlas_manifest(
        manifest,
        failed_existing_report,
        maximum_templates=3,
    )
    assert not failed_existing["quality_enrichment"]["freeze_ready"]
    assert len(failed_existing["quality_enrichment"]["unresolved_existing_template_cases"]) == 1

    known_unbuildable_manifest = json.loads(json.dumps(manifest))
    known_unbuildable_manifest["seed_qualification"] = {
        "rejected": [
            {
                "geometry_index": weak_index,
                "failure_reasons": ["quality_below_production_floor"],
            }
        ]
    }
    known_warning = atlas.enrich_atlas_manifest(
        known_unbuildable_manifest,
        report_for(known_unbuildable_manifest, weak_index),
        maximum_templates=3,
    )["quality_enrichment"]
    assert known_warning["added_indices"] == []
    assert known_warning["known_unbuildable_seed_indices"] == [weak_index]
    assert [
        row["geometry_index"] for row in known_warning["accepted_known_unbuildable_warnings"]
    ] == [weak_index]
    assert known_warning["freeze_ready"]

    known_failed_report = report_for(known_unbuildable_manifest, weak_index)
    known_failed_row = known_failed_report["rows"][weak_index]
    known_failed_row["state"] = "NEEDS_FALLBACK"
    known_failed_row["accepted_min_scaled_quality"] = None
    known_failed = atlas.enrich_atlas_manifest(
        known_unbuildable_manifest,
        known_failed_report,
        maximum_templates=3,
    )["quality_enrichment"]
    assert not known_failed["freeze_ready"]
    assert len(known_failed["unresolved_known_unbuildable_cases"]) == 1

    smoke_report = report_for(manifest, None)
    smoke_report["volume_level"] = "smoke"
    smoke_ready = atlas.enrich_atlas_manifest(
        manifest,
        smoke_report,
        maximum_templates=2,
    )
    assert smoke_ready["quality_enrichment"]["quality_enrichment_complete"]
    assert smoke_ready["quality_enrichment"]["requires_production_validation"]
    assert not smoke_ready["quality_enrichment"]["freeze_ready"]

    with pytest.raises(ValueError, match="permanently pinned"):
        atlas.enrich_atlas_manifest(
            manifest,
            smoke_report,
            maximum_templates=2,
            required_freeze_level="smoke",
        )


def test_registry_indices_are_read_from_current_atlas_schema(tmp_path) -> None:
    path = tmp_path / "atlas.json"
    path.write_text(
        json.dumps(
            {
                "schema": atlas.ATLAS_SCHEMA,
                "set_name": "lhs100_seed42",
                "template_indices": [42, 70, 16],
            }
        ),
        encoding="utf-8",
    )
    assert campaign.indices_from_atlas_manifest(path) == [42, 70, 16]


def test_portable_registry_assets_resolve_and_verify(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(campaign, "REPO_ROOT", tmp_path)
    assets = tmp_path / "templates" / "seed_042"
    assets.mkdir(parents=True)
    cgns = assets / "wing_vol.cgns"
    surface = assets / "surface_blocks.npz"
    options = assets / "pyhyp_options.json"
    cgns.write_bytes(b"cgns")
    surface.write_bytes(b"surface")
    options.write_text("{}\n", encoding="utf-8")

    template = {
        "template_id": "seed_042",
        "geometry_index": 42,
        "cgns": "templates/seed_042/wing_vol.cgns",
        "cgns_sha256": deform.sha256(cgns),
        "surface_npz": "templates/seed_042/surface_blocks.npz",
        "surface_npz_sha256": deform.sha256(surface),
        "pyhyp_options": "templates/seed_042/pyhyp_options.json",
        "pyhyp_options_sha256": deform.sha256(options),
    }
    registry = {
        "schema": campaign.REGISTRY_SCHEMA,
        "asset_path_base": "repository_root",
        "templates": [template],
    }
    path = tmp_path / "artifacts" / "registry.json"
    path.parent.mkdir()
    path.write_text(json.dumps(registry), encoding="utf-8")

    audit = campaign.verify_registry(path)
    assert audit["passed"]
    assert audit["template_count"] == 1
    materialized = campaign._materialize_registry_assets(
        json.loads(path.read_text(encoding="utf-8")), path
    )
    assert Path(materialized["templates"][0]["cgns"]) == cgns

    cgns.write_bytes(b"changed")
    with pytest.raises(campaign.RegistryIntegrityError, match="hash mismatch"):
        campaign.verify_registry(path)


def test_hpc_pilot_package_uses_only_governed_development_cases(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(campaign, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        campaign,
        "verify_registry",
        lambda _path: {"passed": True, "template_count": 21},
    )
    matrix, names = campaign.design_matrix("lhs100_seed42")
    report = {
        "schema": campaign.DEVELOPMENT_REPORT_SCHEMA,
        "set_name": "lhs100_seed42",
        "volume_level": "production",
        "attempted": 100,
        "passed": 100,
        "preferred_quality": 0.15,
        "rows": [],
    }
    for index in range(100):
        quality = 0.16 + 0.0005 * index
        attempts = 1
        if index == 7:
            attempts = 6
        elif index == 95:
            quality = 0.146
            attempts = 21
        report["rows"].append(
            {
                "geometry_index": index,
                "geometry_id": f"lhs100_seed42_{index:03d}",
                "state": "PASS",
                "accepted_min_scaled_quality": quality,
                "attempts": [{} for _ in range(attempts)],
                "accepted_template_index": index,
                "selected_identity_deformation": True,
            }
        )
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    atlas_manifest = {
        "schema": atlas.ATLAS_SCHEMA,
        "set_name": "lhs100_seed42",
        "quality_enrichment": {
            "freeze_ready": True,
            "requires_revalidation": False,
            "development_report": {"sha256": deform.sha256(report_path)},
        },
        "assignments": [
            {"geometry_index": index, "distance_rms": 0.001 * index} for index in range(100)
        ],
    }
    atlas_path = tmp_path / "atlas.json"
    atlas_path.write_text(json.dumps(atlas_manifest), encoding="utf-8")
    registry = {
        "schema": campaign.REGISTRY_SCHEMA,
        "asset_path_base": "repository_root",
        "atlas_manifest": {"sha256": deform.sha256(atlas_path)},
        "templates": [],
    }
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    flows_path = tmp_path / "flows.csv"
    flows_path.write_text(
        "flow_id,alpha,mach,reynolds,temperature\ncruise,2,0.2,1000000,288.15\n",
        encoding="utf-8",
    )

    package = campaign.prepare_hpc_pilot(
        development_report_path=report_path,
        atlas_manifest_path=atlas_path,
        registry_path=registry_path,
        flows_path=flows_path,
        output=tmp_path / "pilot",
    )
    indices = [row["geometry_index"] for row in package["selected"]]
    assert len(indices) == len(set(indices)) == 10
    assert {7, 89, 95}.issubset(indices)
    assert not package["holdout_accessed"]
    assert package["source_set"] == "lhs100_seed42"
    assert package["counts"] == {"designs": 10, "flows": 1, "cases": 10}
    assert (tmp_path / "pilot" / "verify_and_submit.sh").stat().st_mode & 0o100
    assert names == list(package_manifest_names(tmp_path / "pilot" / "manifest.json"))
    assert matrix.shape[0] == 100


def package_manifest_names(path: Path) -> tuple[str, ...]:
    return tuple(json.loads(path.read_text(encoding="utf-8"))["design_variables"])


def test_normalization_omits_fixed_design_variables() -> None:
    names, low, high = atlas.design_bounds()
    midpoint = 0.5 * (low + high)
    normalized = atlas.normalize_matrix(midpoint[None, :], names)
    expected = sum(
        hi > lo and name not in atlas.MESH_DISTANCE_EXCLUDED
        for name, lo, hi in zip(names, low, high, strict=True)
    )
    assert normalized.shape[1] == expected
    np.testing.assert_allclose(normalized, 0.5)


def test_mesh_distance_ignores_neutral_oml_inactive_elevon_variables() -> None:
    names, low, high = atlas.design_bounds()
    first = 0.5 * (low + high)
    second = first.copy()
    for name in atlas.MESH_DISTANCE_EXCLUDED:
        index = names.index(name)
        second[index] = high[index]
    normalized = atlas.normalize_matrix(np.stack((first, second)), names)
    np.testing.assert_allclose(normalized[0], normalized[1])


def test_normalization_rejects_nonfinite_and_changed_fixed_variables() -> None:
    names, low, high = atlas.design_bounds()
    midpoint = 0.5 * (low + high)
    nonfinite = midpoint.copy()
    nonfinite[0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        atlas.normalize_matrix(nonfinite[None, :], names)

    fixed = np.flatnonzero(high == low)
    assert fixed.size > 0
    changed = midpoint.copy()
    changed[fixed[0]] += 1.0
    with pytest.raises(ValueError, match="fixed canonical"):
        atlas.normalize_matrix(changed[None, :], names)


def test_span_law_rejects_infeasible_cap_without_nan() -> None:
    class PlaneSurface:
        def __call__(self, u, v):
            u = np.asarray(u, dtype=float)
            v = np.asarray(v, dtype=float)
            return np.column_stack((u, 1.2 * v, np.zeros_like(u)))

    pygeo = type("PyGeo", (), {"surfs": [PlaneSurface()]})()
    with pytest.raises(ValueError, match="cover at most"):
        strategy_s6._tip_clustered_parameters(
            pygeo,
            n_cells=80,
            first_cell_m=5.0e-4,
            max_cell_m=0.015,
        )

    edges, ratio, span, maximum = strategy_s6._tip_clustered_parameters(
        pygeo,
        n_cells=90,
        first_cell_m=5.0e-4,
        max_cell_m=0.015,
    )
    assert np.all(np.isfinite(edges))
    assert np.all(np.diff(edges) > 0.0)
    assert ratio > 1.0
    assert span == pytest.approx(1.2)
    assert maximum <= 0.015 + 1.0e-12


def test_deformation_matches_wall_and_keeps_farfield_residual_zero() -> None:
    volume, template = _cube()
    target = {"wall": template["wall"].copy()}
    target["wall"][..., 0] *= 1.1
    target["wall"][..., 1] *= 0.9
    target["wall"][..., 2] = 0.02 * np.sin(np.pi * target["wall"][..., 0] / 1.1)

    mapped, metadata = deform.deform_volume_blocks(volume, template, target)
    np.testing.assert_allclose(
        mapped["zone"][0],
        target["wall"].transpose(1, 0, 2),
        atol=1.0e-14,
    )
    source_farfield = volume["zone"][-1]
    expected_farfield = np.asarray(metadata["target_anchor_m"]) + (
        source_farfield - np.asarray(metadata["template_anchor_m"])
    ) * np.asarray(metadata["affine_scale_xyz"])
    np.testing.assert_allclose(mapped["zone"][-1], expected_farfield, atol=1.0e-14)
    report = deform.acceptance_report(mapped, metadata)
    assert report["hard_gate_passed"]
    assert report["quality"]["inverted_cells"] == 0


def test_correspondence_rejects_shape_mismatch() -> None:
    volume, surface = _cube()
    surface["wall"] = surface["wall"][:-1]
    with pytest.raises(ValueError, match="wall shape"):
        deform.validate_template_correspondence(volume, surface)


@pytest.mark.parametrize(
    ("normal_points", "expected"),
    [(129, "smoke"), (193, "fine"), (257, "production")],
)
def test_registry_maps_normal_resolution_to_fallback_level(
    normal_points: int, expected: str
) -> None:
    assert campaign._volume_level_from_normal_points(normal_points) == expected


def test_case_lock_recovers_after_dead_local_worker(tmp_path, monkeypatch) -> None:
    lock = tmp_path / ".case.lock"
    lock.write_text(
        f"pid=123456 host={socket.gethostname()} started={time.time()}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(campaign, "_process_is_alive", lambda _pid: False)

    with campaign._case_lock(lock, wait_s=0.1):
        assert lock.is_file()

    assert not lock.exists()


def test_mesh_fingerprint_covers_governing_modules() -> None:
    paths = {str(path.resolve()) for path in campaign._mesh_implementation_paths()}
    for name in (
        "gates.py",
        "geometry_sets.py",
        "ingestion.py",
        "qc.py",
        "volume_qc.py",
    ):
        expected = campaign.STUDIES / "shared" / name
        assert str(expected.resolve()) in paths
    for name in ("pyhyp_extrude.py", "pyhyp_options.py", "volume_audit.py"):
        expected = campaign.REPO_ROOT / "src/aeris/cfd/meshing" / name
        assert str(expected.resolve()) in paths
    lhs = campaign.REPO_ROOT / "src/aeris/dataset/sampling/samplers/lhs_v1.py"
    assert str(lhs.resolve()) in paths
    surface = campaign.REPO_ROOT / "src/aeris/mesh/surface.py"
    assert str(surface.resolve()) in paths


def test_accepted_result_caches_require_matching_input_hashes(tmp_path) -> None:
    mesh = tmp_path / "mesh.cgns"
    mesh.write_bytes(b"mesh")
    mesh_report = tmp_path / "mesh_report.json"
    mesh_report.write_text(
        json.dumps(
            {
                "schema": campaign.MESH_REPORT_SCHEMA,
                "state": "MESH_ACCEPTED",
                "manifest_sha256": "manifest-a",
                "registry_sha256": "registry-a",
                "mesh_implementation_sha256": "implementation-a",
                "accepted_mesh": {
                    "cgns": str(mesh),
                    "cgns_sha256": deform.sha256(mesh),
                },
            }
        ),
        encoding="utf-8",
    )
    assert campaign._existing_accepted_mesh(
        mesh_report,
        manifest_sha256="manifest-a",
        registry_sha256="registry-a",
        implementation_sha256="implementation-a",
    )
    assert not campaign._existing_accepted_mesh(
        mesh_report,
        manifest_sha256="manifest-b",
        registry_sha256="registry-a",
        implementation_sha256="implementation-a",
    )

    solve_report = tmp_path / "solve_report.json"
    solver_log = tmp_path / "adflow_run.log"
    wall_summary = tmp_path / "wall_yplus_summary.json"
    surface = tmp_path / "aeris_cfd_000_surf.cgns"
    solve_report.write_text("{}", encoding="utf-8")
    solver_log.write_text("solver", encoding="utf-8")
    wall_summary.write_text("{}", encoding="utf-8")
    surface.write_bytes(b"surface")
    cfd_report = tmp_path / "cfd_acceptance.json"
    report = {
        "schema": campaign.CFD_REPORT_SCHEMA,
        "state": "CFD_ACCEPTED",
        "manifest_sha256": "manifest-a",
        "mesh_sha256": "mesh-a",
        "solver_implementation_sha256": "solver-a",
        "mpi_processes": 4,
        "solve_report": str(solve_report),
        "solve_report_sha256": deform.sha256(solve_report),
        "solver_log": str(solver_log),
        "solver_log_sha256": deform.sha256(solver_log),
        "wall_yplus_summary": str(wall_summary),
        "wall_yplus_summary_sha256": deform.sha256(wall_summary),
        "wall_yplus_gate": {
            "passed": True,
            "surface_cgns": str(surface),
            "surface_cgns_sha256": deform.sha256(surface),
        },
        "surface_solution_retained": True,
    }
    cfd_report.write_text(json.dumps(report), encoding="utf-8")
    assert campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    assert not campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-b",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    assert not campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=2,
    )
    report["surface_solution_retained"] = False
    cfd_report.write_text(json.dumps(report), encoding="utf-8")
    surface.unlink()
    assert campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    surface.write_bytes(b"surface")
    report["surface_solution_retained"] = True
    cfd_report.write_text(json.dumps(report), encoding="utf-8")

    solver_log.write_text("changed", encoding="utf-8")
    assert not campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    solver_log.write_text("solver", encoding="utf-8")
    surface.write_bytes(b"changed")
    assert not campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )
    surface.write_bytes(b"surface")

    report["state"] = "CFD_REJECTED"
    cfd_report.write_text(json.dumps(report), encoding="utf-8")
    assert (
        campaign._existing_cfd_result(
            cfd_report,
            manifest_sha256="manifest-a",
            mesh_sha256="mesh-a",
            implementation_sha256="solver-a",
            mpi_np=4,
        )["state"]
        == "CFD_REJECTED"
    )
    assert not campaign._existing_accepted_cfd(
        cfd_report,
        manifest_sha256="manifest-a",
        mesh_sha256="mesh-a",
        implementation_sha256="solver-a",
        mpi_np=4,
    )


def test_campaign_finalizes_best_valid_candidate(tmp_path) -> None:
    candidates = []
    attempts = []
    for name, quality in (("near", 0.12), ("better", 0.19)):
        path = tmp_path / name / "wing_vol.cgns"
        path.parent.mkdir()
        path.write_bytes(name.encode())
        digest = campaign.sha256(path)
        candidates.append(
            {
                "template_id": name,
                "distance_rms": 0.1 if name == "near" else 0.2,
                "cgns": str(path),
                "cgns_sha256": digest,
                "acceptance": {"quality": {"min_scaled_quality": quality}},
            }
        )
        attempts.append(
            {
                "template_id": name,
                "candidate_cgns_sha256": digest,
                "independent_written_acceptance": {"production_floor_passed": True},
            }
        )

    selected = campaign._finalize_best_candidate(
        candidates,
        design_dir=tmp_path,
        attempts=attempts,
    )
    assert selected is not None
    assert selected["template_id"] == "better"
    assert (tmp_path / "wing_vol.cgns").read_bytes() == b"better"
    assert not (tmp_path / "near" / "wing_vol.cgns").exists()
    assert [attempt["selected"] for attempt in attempts] == [False, True]


def test_completed_design_cache_does_not_require_pruned_mesh(tmp_path) -> None:
    design_dir = tmp_path / "geometries" / "design_0"
    design_dir.mkdir(parents=True)
    case_ids = ["design_0__flow_0", "design_0__flow_1"]
    design_report = {
        "schema": campaign.DESIGN_REPORT_SCHEMA,
        "state": "DESIGN_ACCEPTED",
        "manifest_sha256": "manifest-a",
        "registry_sha256": "registry-a",
        "mesh_implementation_sha256": "mesh-code-a",
        "solver_implementation_sha256": "solver-code-a",
        "mpi_processes": 4,
        "mesh_sha256": "mesh-a",
        "case_ids": case_ids,
    }
    (design_dir / "design_run_report.json").write_text(json.dumps(design_report), encoding="utf-8")
    for case_id in case_ids:
        case_dir = tmp_path / "cases" / case_id
        case_dir.mkdir(parents=True)
        solve_report = case_dir / "solve_report.json"
        solver_log = case_dir / "adflow_run.log"
        wall_summary = case_dir / "wall_yplus_summary.json"
        surface = case_dir / "aeris_cfd_000_surf.cgns"
        solve_report.write_text("{}", encoding="utf-8")
        solver_log.write_text("solver", encoding="utf-8")
        wall_summary.write_text("{}", encoding="utf-8")
        surface.write_bytes(b"surface")
        (case_dir / "cfd_acceptance.json").write_text(
            json.dumps(
                {
                    "schema": campaign.CFD_REPORT_SCHEMA,
                    "state": "CFD_ACCEPTED",
                    "manifest_sha256": "manifest-a",
                    "mesh_sha256": "mesh-a",
                    "solver_implementation_sha256": "solver-code-a",
                    "mpi_processes": 4,
                    "solve_report": str(solve_report),
                    "solve_report_sha256": deform.sha256(solve_report),
                    "solver_log": str(solver_log),
                    "solver_log_sha256": deform.sha256(solver_log),
                    "wall_yplus_summary": str(wall_summary),
                    "wall_yplus_summary_sha256": deform.sha256(wall_summary),
                    "wall_yplus_gate": {
                        "passed": True,
                        "surface_cgns": str(surface),
                        "surface_cgns_sha256": deform.sha256(surface),
                    },
                    "surface_solution_retained": True,
                }
            ),
            encoding="utf-8",
        )

    cached = campaign._existing_accepted_design(
        campaign_root=tmp_path,
        design_id="design_0",
        case_ids=case_ids,
        manifest_sha256="manifest-a",
        registry_sha256="registry-a",
        mesh_implementation_sha256="mesh-code-a",
        solver_implementation_sha256="solver-code-a",
        mpi_np=4,
    )
    assert cached is not None
    assert cached["state"] == "DESIGN_ACCEPTED"
    assert (
        campaign._existing_accepted_design(
            campaign_root=tmp_path,
            design_id="design_0",
            case_ids=case_ids,
            manifest_sha256="manifest-a",
            registry_sha256="registry-a",
            mesh_implementation_sha256="mesh-code-a",
            solver_implementation_sha256="solver-code-a",
            mpi_np=2,
        )
        is None
    )


def test_collect_handles_mixed_finished_and_missing_cases(tmp_path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "schema": campaign.MANIFEST_SCHEMA,
        "cases": [
            {
                "case_index": 0,
                "case_id": "case_0",
                "design_id": "design_0",
                "flow_id": "flow_0",
            },
            {
                "case_index": 1,
                "case_id": "case_1",
                "design_id": "design_1",
                "flow_id": "flow_0",
            },
        ],
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_hash = deform.sha256(manifest_path)
    accepted_dir = tmp_path / "campaign" / "cases" / "case_0"
    accepted_dir.mkdir(parents=True)
    (accepted_dir / "cfd_acceptance.json").write_text(
        json.dumps(
            {
                "state": "CFD_ACCEPTED",
                "manifest_sha256": manifest_hash,
                "forces": {"cl": 0.4, "cd": 0.03, "cmy": -0.01},
                "residual_orders_dropped": 7.0,
                "wall_yplus_gate": {"statistics": {"p95": 0.8, "maximum": 1.2}},
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "summary.json"
    report = campaign.collect(tmp_path / "campaign", manifest_path, output)
    assert report["counts"] == {"CFD_ACCEPTED": 1, "NOT_RUN": 1}
    with output.with_suffix(".csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    assert rows[0]["cl"] == "0.4"
    assert rows[1]["cl"] == ""


def test_deformation_preserves_a_shared_block_face() -> None:
    i = np.linspace(0.0, 1.0, 5)
    k = np.linspace(0.0, 3.0, 8)

    def block(y0: float, y1: float) -> np.ndarray:
        j = np.linspace(y0, y1, 3)
        kk, jj, ii = np.meshgrid(k, j, i, indexing="ij")
        return np.stack((ii, jj, kk), axis=-1)

    volume = {"left": block(0.0, 0.5), "right": block(0.5, 1.0)}
    template = {
        "left_wall": volume["left"][0].transpose(1, 0, 2),
        "right_wall": volume["right"][0].transpose(1, 0, 2),
    }
    target = {name: wall.copy() for name, wall in template.items()}
    for wall in target.values():
        wall[..., 2] = 0.03 * np.sin(np.pi * wall[..., 0])

    mapped, metadata = deform.deform_volume_blocks(volume, template, target)
    interfaces = deform.volume_interface_report(mapped)
    assert interfaces["paired_face_count"] == 1
    assert interfaces["max_mismatch_m"] < 1.0e-14
    assert deform.acceptance_report(mapped, metadata)["hard_gate_passed"]


def test_manifest_expands_unique_design_flow_pairs(tmp_path) -> None:
    names, low, high = atlas.design_bounds()
    midpoint = 0.5 * (low + high)
    design_csv = tmp_path / "designs.csv"
    design_csv.write_text(
        ",".join(["design_id", *names])
        + "\n"
        + ",".join(["d0", *(str(value) for value in midpoint)])
        + "\n",
        encoding="utf-8",
    )
    flow_csv = tmp_path / "flows.csv"
    flow_csv.write_text(
        "flow_id,alpha,mach,reynolds,temperature\n"
        "cruise,2.0,0.2,1000000,288.15\n"
        "high_alpha,6.0,0.2,1000000,288.15\n",
        encoding="utf-8",
    )

    manifest = campaign.make_manifest(design_csv, flow_csv, tmp_path / "campaign.json")
    assert manifest["counts"] == {"designs": 1, "flows": 2, "cases": 2}
    assert [row["case_id"] for row in manifest["cases"]] == [
        "d0__cruise",
        "d0__high_alpha",
    ]


def test_force_tail_gate_rejects_unstable_forces(tmp_path) -> None:
    stable = tmp_path / "stable.log"
    stable.write_text(
        "\n".join(
            f"1 {index} {index} ANK 100 1 0.1 {1e-2 / index} 1e-6 "
            f"{0.4 + 1e-6 * index} {0.03 + 1e-7 * index} 1"
            for index in range(1, 31)
        ),
        encoding="utf-8",
    )
    assert campaign._force_tail_gate(stable, relative_range_max=0.001)["passed"]

    unstable = tmp_path / "unstable.log"
    unstable.write_text(
        stable.read_text(encoding="utf-8").replace("0.40003", "0.5"),
        encoding="utf-8",
    )
    assert not campaign._force_tail_gate(unstable, relative_range_max=0.001)["passed"]


def test_force_tail_gate_handles_near_zero_lift(tmp_path) -> None:
    log = tmp_path / "near_zero.log"
    log.write_text(
        "\n".join(
            f"1 {index} {index} ANK 100 1 0.1 {1e-2 / index} 1e-6 "
            f"{-0.02 + 1e-6 * index} {0.03 + 1e-7 * index} 1"
            for index in range(1, 31)
        ),
        encoding="utf-8",
    )
    report = campaign._force_tail_gate(log, relative_range_max=0.001)
    assert report["passed"]
    assert report["coefficient_floors"] == {"cl": 0.10, "cd": 0.01}


def test_force_plausibility_requires_complete_finite_positive_drag() -> None:
    assert campaign._force_plausibility_gate({"cl": 0.4, "cd": 0.03, "cmy": -0.02})["passed"]
    assert not campaign._force_plausibility_gate({"cl": 0.4, "cd": -0.001, "cmy": -0.02})["passed"]
    assert not campaign._force_plausibility_gate({"cl": 0.4, "cd": 0.03})["passed"]


def test_wall_yplus_gate_reads_only_no_slip_wall_zones(tmp_path) -> None:
    path = tmp_path / "surface.cgns"
    with h5py.File(path, "w") as handle:
        wall = handle.create_group("BaseSurfaceSol/NSWallAdiabaticBCZone1/Flow solution/YPlus")
        wall.create_dataset(" data", data=np.linspace(0.1, 0.9, 100))
        farfield = handle.create_group("BaseSurfaceSol/FarFieldBCZone2/Flow solution/YPlus")
        farfield.create_dataset(" data", data=np.full(100, 100.0))

    report = cfd_qc.wall_yplus_summary(path)
    assert report["passed"]
    assert report["wall_zone_count"] == 1
    assert report["sample_count"] == 100
    assert report["statistics"]["maximum"] == pytest.approx(0.9)


def test_wall_yplus_gate_rejects_large_wall_values(tmp_path) -> None:
    path = tmp_path / "surface.cgns"
    with h5py.File(path, "w") as handle:
        wall = handle.create_group("BaseSurfaceSol/NSWallAdiabaticBCZone1/Flow solution/YPlus")
        wall.create_dataset(" data", data=np.linspace(0.1, 7.0, 100))

    report = cfd_qc.wall_yplus_summary(path)
    assert not report["passed"]
    assert "maximum_above_limit" in report["failure_reasons"]


===== FILE: ./shared/exact_sections.py =====

"""EXPERIMENT — sections at arbitrary spanwise stations, exactly.

**This is a copy-based experiment.** Nothing under `src/aeris` is modified. If it
holds up it becomes a generator change and an ADR, because it alters
`configs/geometry/bwb.yaml`'s meaning and therefore the sha256 that identifies all
three locked geometry sets.

--------------------------------------------------------------------------------
WHY
--------------------------------------------------------------------------------

Every strategy so far invents spanwise mesh columns by blending linearly between
the generator's realised sections, and the fidelity gate (0.01% of local chord)
cannot be verified for those columns. Measured on `lhs100_seed42_000`: the wing
deviates from a straight line between stations by a median of 0.447% of chord and
up to 7.25% at the inboard/outboard spline junction — 45x to 700x the gate.

Refining the station count does not fix it. Measured 17 -> 35 -> 71 -> 143
stations: 7.25% -> 3.08% -> 1.42% -> 0.68%, a ratio of about 2 per doubling. That
is FIRST-order convergence, which is what linear interpolation gives across a
slope discontinuity, not the second-order O(h^2) a smooth surface would give.
Reaching 0.01% that way needs of order 12,000 stations.

**The requirement is zero deviation on every geometry the mesher will ever see, so
interpolation has to go, not shrink.** The planform is closed-form — a CubicSpline
inboard blended toward a straight line, purely linear outboard — so a section at
ANY spanwise station is exactly computable. If the mesher asks the generator for
sections at exactly the stations it wants, every mesh column is a real section and
the deviation is identically zero by construction, on every geometry.

--------------------------------------------------------------------------------
THE ONE SUBTLETY: z
--------------------------------------------------------------------------------

`sections._cumulative_z` integrates `tan(dihedral)` by the TRAPEZOID rule along
whatever station array it is handed. Dihedral is piecewise linear in y, so
`tan(dihedral)` is not, and the trapezoid result therefore depends on the
discretisation: change the stations and `z(y)` moves. That alone would stop the
"exact section at arbitrary y" claim being true.

Over a segment where dihedral runs linearly from d0 to d1 across [y0, y1]:

    m = (d1 - d0) / (y1 - y0)                       [rad per metre]
    m == 0 :  integral = tan(d0) * (y1 - y0)
    m != 0 :  integral = (ln|cos d0| - ln|cos d1|) / m

which is exact and station-independent. That is what :func:`exact_z_at` uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


def exact_z_at(y_query, boundary_y, boundary_dihedral_deg):
    """LE z at arbitrary y, by exact integration of a piecewise-linear dihedral.

    Replaces the trapezoid rule in `sections._cumulative_z`, whose answer depends
    on the station array it happens to be given.
    """
    y_query = np.atleast_1d(np.asarray(y_query, dtype=float))
    by = np.asarray(boundary_y, dtype=float)
    bd = np.radians(np.asarray(boundary_dihedral_deg, dtype=float))

    def _segment_integral(y0: float, y1: float, d0: float, d1: float) -> float:
        if y1 <= y0:
            return 0.0
        m = (d1 - d0) / (y1 - y0)
        if abs(m) < 1e-14:
            return float(np.tan(d0) * (y1 - y0))
        return float((np.log(abs(np.cos(d0))) - np.log(abs(np.cos(d1)))) / m)

    # Cumulative integral at each boundary, then the partial segment to y.
    cum = np.zeros(len(by))
    for k in range(1, len(by)):
        cum[k] = cum[k - 1] + _segment_integral(by[k - 1], by[k], bd[k - 1], bd[k])

    out = np.empty_like(y_query)
    for i, y in enumerate(y_query):
        k = int(np.clip(np.searchsorted(by, y, side="right") - 1, 0, len(by) - 2))
        d_at_y = float(np.interp(y, by, bd))
        out[i] = cum[k] + _segment_integral(by[k], float(y), bd[k], d_at_y)
    return out


def planform_curves(planform, config):
    """Closed-form LE and TE x(y), reconstructed from the planform control points.

    Mirrors `planform.generate_spline_linear` exactly: a clamped CubicSpline over
    the control points inboard, blended toward the straight-line baseline by
    ``curvature_strength``, and purely linear outboard of the split.
    """
    y_ctrl = np.asarray(planform.y_le, dtype=float)
    x_le_ctrl = np.asarray(planform.x_le, dtype=float)
    x_te_ctrl = np.asarray(planform.x_te, dtype=float)
    split_idx = int(planform.split_idx)
    strength = float(config.controls.curvature_strength)

    def _curve(x_ctrl):
        spline = CubicSpline(y_ctrl, x_ctrl, bc_type="clamped")
        y_split = float(y_ctrl[split_idx])
        y_tip = float(y_ctrl[-1])

        def f(y):
            y = np.atleast_1d(np.asarray(y, dtype=float))
            out = np.empty_like(y)
            inb = y <= y_split
            if inb.any():
                base = np.interp(
                    y[inb], [float(y_ctrl[0]), y_split], [float(x_ctrl[0]), float(x_ctrl[split_idx])]
                )
                out[inb] = base + strength * (spline(y[inb]) - base)
            if (~inb).any():
                out[~inb] = np.interp(
                    y[~inb], [y_split, y_tip], [float(x_ctrl[split_idx]), float(x_ctrl[-1])]
                )
            return out

        return f

    return _curve(x_le_ctrl), _curve(x_te_ctrl)


===== FILE: ./shared/export_paraview.py =====

"""ParaView export — SHARED CONTROL.

ADR-0011 section 4: one exporter, so that inspecting two strategies' meshes means
looking at the same arrays computed the same way. Migrated unchanged from
`04_strategy_prototypes/export_for_paraview.py`.

Writes one legacy-VTK unstructured grid per call, with every block merged and
per-CELL quality arrays attached, so bad cells are found by thresholding rather
than by hunting visually:

    scaled_jacobian   minimum corner scaled Jacobian, signed. NEGATIVE = folded.
    shape_metric      minimum corner shape metric. Near zero = degenerate.
    skewness          equiangle skewness, 0 good, 1 degenerate.
    block_id          integer index of the source block.
    is_tip            1 for tip-cap blocks, 0 for OML blocks.

To inspect: open the .vtk, colour by `scaled_jacobian`, Threshold -1 to 0 to
isolate folds. `is_tip` separates cap from OML. Mike inspects meshes in ParaView,
so this is the intended output of any surface diagnosis.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def cell_metrics(xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-cell scaled Jacobian, shape metric and equiangle skewness.

    **Instrument bug 9**, found on 2026-08-14 while exporting S0 for ParaView and
    fixed here. This function used to compute the scaled Jacobian against a
    BLOCK-AVERAGED reference normal::

        ref = normal.reshape(-1, 3).sum(axis=0); ref /= norm(ref)

    That is meaningless for a block that curves through a large angle. cap4's
    `oml_nose_wrap` wraps around the leading edge, so cells on opposite sides have
    opposing normals, their average is near zero, and the sign flips arbitrarily.
    The exporter reported **7 folded cells and a minimum of -0.132** on a surface
    that `qc_blocks` scores at **+0.191 with no negative cell anywhere** — and it
    reported them in the file a human opens to go looking for folds.

    The authoritative metric signs each corner against the cell's OWN first-corner
    normal (`aeris.cfd.meshing.quality.scaled_jacobian`). It is now called
    directly, along with the authoritative skewness, so the picture and the QC
    table cannot disagree again. That is what ADR-0011 section 4 means by sharing
    QC metric *definitions*: one definition, used everywhere, including in the
    pictures.
    """
    from aeris.cfd.meshing.quality import equiangle_skewness, scaled_jacobian

    from .ingestion import _corner_shape_metric

    return scaled_jacobian(xyz), _corner_shape_metric(xyz), equiangle_skewness(xyz)


def write_vtk(path: Path, blocks) -> dict:
    points: list[np.ndarray] = []
    quads: list[tuple[int, int, int, int]] = []
    sj_all, shape_all, skew_all, bid_all, tip_all = [], [], [], [], []
    offset = 0
    for bid, b in enumerate(blocks):
        xyz = b.xyz
        ni, nj, _ = xyz.shape
        points.append(xyz.reshape(-1, 3))
        for i in range(ni - 1):
            for j in range(nj - 1):
                quads.append(
                    (
                        offset + i * nj + j,
                        offset + (i + 1) * nj + j,
                        offset + (i + 1) * nj + j + 1,
                        offset + i * nj + j + 1,
                    )
                )
        sj, shape, skew = cell_metrics(xyz)
        n_cells = sj.size
        sj_all.append(sj.ravel())
        shape_all.append(shape.ravel())
        skew_all.append(skew.ravel())
        bid_all.append(np.full(n_cells, bid))
        tip_all.append(np.full(n_cells, 1 if b.name.startswith("tip") else 0))
        offset += ni * nj

    pts = np.concatenate(points, axis=0)
    sj = np.concatenate(sj_all)
    lines = [
        "# vtk DataFile Version 3.0",
        f"AERIS strategy study surface - {path.stem}",
        "ASCII",
        "DATASET UNSTRUCTURED_GRID",
        f"POINTS {len(pts)} float",
    ]
    lines += [f"{p[0]:.9g} {p[1]:.9g} {p[2]:.9g}" for p in pts]
    lines.append(f"CELLS {len(quads)} {5 * len(quads)}")
    lines += [f"4 {a} {b} {c} {d}" for a, b, c, d in quads]
    lines.append(f"CELL_TYPES {len(quads)}")
    lines += ["9"] * len(quads)
    lines.append(f"CELL_DATA {len(quads)}")
    for name, data, fmt in (
        ("scaled_jacobian", sj, "float"),
        ("shape_metric", np.concatenate(shape_all), "float"),
        ("skewness", np.concatenate(skew_all), "float"),
        ("block_id", np.concatenate(bid_all), "int"),
        ("is_tip", np.concatenate(tip_all), "int"),
    ):
        lines.append(f"SCALARS {name} {fmt} 1")
        lines.append("LOOKUP_TABLE default")
        lines += [f"{v:.9g}" if fmt == "float" else f"{int(v)}" for v in data]
    path.write_text("\n".join(lines) + "\n")
    return {
        "cells": len(quads),
        "folded_cells": int((sj < 0).sum()),
        "min_scaled_jacobian": float(sj.min()),
    }


===== FILE: ./shared/gates.py =====

"""Gate thresholds and pass/fail checklists — SHARED CONTROL.

ADR-0011 section 6 freezes these **before any strategy is implemented or
optimised**. Nothing here may be chosen, reweighted or relaxed after seeing
results. Thresholds are migrated unchanged from Stage 00 / ADR-0005 / ADR-0008 so
every number already recorded in `status` stays directly comparable.

Two distinctions this module exists to hold:

1. **`0.30` is a RANKING TARGET, never a gate.** The frozen hard gate on volume
   min scaled quality is strictly `> 0`. Stage 02 audited every use of 0.30 across
   `gate_registry.yaml`, `verify_strategies.py` and the narrative and found no
   misuse; keeping the two in one file with the distinction stated is how it stays
   that way.
2. **A surface can pass every shape gate and be unmarchable.** ADR-0010. The two
   marchability metrics — staged cell-size range and min-cell/`s0` — are therefore
   *reported* by `marchability_metrics` and included in Round A per ADR-0011
   section 3.2. They are deliberately **not** hard gates: no threshold on them has
   been established, and inventing one after the fact is exactly what ADR-0011
   section 6 forbids.
"""

from __future__ import annotations

# --- hard gates, ADR-0011 section 6.1 --------------------------------------

#: Geometry fidelity, as a fraction of local chord. Stage 00; 0.01% = 1.0e-4.
#: Measured point-to-SEGMENT against a CLOSED reference contour — both were
#: instrument bugs in Stage 02 (COMMON_BRIEF section 5, items 1 and 2).
FIDELITY_FRAC_OF_LOCAL_CHORD = 1.0e-4

#: Surface min scaled Jacobian must be strictly greater than this. ADR-0005.
SURFACE_MIN_SCALED_JACOBIAN_FLOOR = 0.0

#: Volume min scaled quality must be strictly greater than this. ADR-0008.
VOLUME_MIN_SCALED_QUALITY_FLOOR = 0.0

#: Node rounding for coincidence tests. 1e-7 m = 0.1 micron; finer compares float
#: noise rather than nodes.
NODE_DECIMALS = 7

# --- ranking targets, NOT gates --------------------------------------------

#: RUNBOOK section 7 Round B quality target. Used only for ranking commentary.
#: It is never a pass threshold. See the module docstring.
VOLUME_QUALITY_RANKING_TARGET = 0.30

# --- epsE protocol, ADR-0008 as amended by ADR-0011 section 5 --------------

#: The declared ladder. NOT extended after a failure without a further ADR
#: stating the physical reason (ADR-0008 section 6).
EPSE_LADDER = (1.5, 2.0, 3.0)

#: epsI is tied to epsE at this ratio throughout the study.
EPSI_OVER_EPSE = 2.0

#: Calibration and confirmation levels. Only the coarsen=1 family
#: (smoke -> fine -> production) is a refinement ladder at full surface
#: resolution. The `L*` family uses coarsen=4, so `L4` (N=37) is COARSER than
#: `smoke` (N=129) and would confirm nothing — that error is recorded in
#: ADR-0008 and repeated in ADR-0011 section 5.4 so it cannot recur.
CALIBRATION_LEVEL = "smoke"  # N=129, coarsen=1
CONFIRMATION_LEVEL = "fine"  # N=193, coarsen=1
REFINEMENT_LADDER = ("smoke", "fine", "production")

#: Stage 01 cap4 control on lhs7_00 at the calibration level, for like-for-like
#: comparison. Reproduced through a new code path in Stage 02 at 54/128, which is
#: the study's regression anchor.
CAP4_REFERENCE = {
    "bad_layers": 53,
    "layer_count": 128,
    "min_quality": -0.90808,
    "reproduced_via_new_code_path": {"bad_layers": 54, "min_volume": 2.11e-11},
}


def surface_gate_checklist(
    qc: dict,
    fidelity: dict,
    orientation: dict,
    watertight: bool,
    deterministic_connectivity: bool,
) -> tuple[bool, list[str]]:
    """ADR-0011 section 6.1, surface half. Returns (passed, failure reasons).

    ``qc`` is :func:`shared.qc.qc_blocks` output, ``fidelity`` is
    :func:`shared.verify.oml_fidelity` output, ``orientation`` is the info dict
    from :func:`shared.qc.orient_blocks_consistently`.
    """
    fails: list[str] = []

    frac = fidelity.get("worst_frac_of_local_chord")
    if frac is None or float(frac) > FIDELITY_FRAC_OF_LOCAL_CHORD:
        fails.append(
            f"geometry fidelity {frac} of local chord, gate is "
            f"<= {FIDELITY_FRAC_OF_LOCAL_CHORD}"
        )
    if fidelity.get("fidelity_unverified_for_refined_blocks"):
        # COMMON_BRIEF section 5: silently skipping spanwise-refined blocks would
        # report a refined mesh as fidelity-perfect while its interpolated columns
        # sit off the loft entirely. Unverified is not the same as passing.
        fails.append(
            "fidelity unverified for spanwise-refined blocks: "
            f"{fidelity.get('skipped_spanwise_refined_blocks')}"
        )
    if not watertight:
        fails.append("surface is not watertight at the tip")
    if not orientation.get("all_blocks_connected", False):
        fails.append(
            "orientation edge-walk did not reach every block "
            f"({orientation.get('blocks_reached_by_edge_walk')} of "
            f"{orientation.get('block_count')}) — surface is disconnected"
        )
    if float(orientation.get("signed_volume_before_global_flip", 0.0)) == 0.0:
        fails.append("enclosed signed volume is zero; normals cannot be verified outward")
    jac = (qc.get("global") or {}).get("min_scaled_jacobian")
    if jac is None or float(jac) <= SURFACE_MIN_SCALED_JACOBIAN_FLOOR:
        fails.append(f"surface min scaled Jacobian {jac}, gate is strictly > 0")
    area = (qc.get("global") or {}).get("min_area")
    if area is None or float(area) <= 0.0:
        fails.append(f"minimum surface cell area {area}, gate is strictly > 0")
    if not deterministic_connectivity:
        fails.append("connectivity signature is not deterministic across geometries")

    return (not fails), fails


def volume_gate_checklist(vol: dict) -> tuple[bool, list[str]]:
    """ADR-0008 section 3, verbatim; ADR-0011 section 6.1 volume half.

    The hard gate is `> 0`, never 0.30. Migrated unchanged from
    `03_cap4_epse/s1_volume_canary.py::_checklist`.
    """
    m = vol.get("march_metrics") or {}
    a = vol.get("volume_audit") or {}
    fails = []
    # **Instrument bug 10**, found 2026-08-14 while collecting a 30-march campaign.
    # The checklist scored an INCOMPLETE march as PASS: `lhs100_seed42_009` at
    # epsE 3.0 was still running, had reached 95 of 128 layers with no bad layer
    # yet, and satisfied every other condition. A march that has not finished has
    # not passed anything.
    if vol.get("march_completed") is False:
        fails.append("march did not complete (no 'pyHyp done' in the log)")
    if vol.get("status") != "valid":
        fails.append(f"pyHyp status {vol.get('status')!r}, expected 'valid'")
    if (a.get("inverted_cells") or 0) != 0:
        fails.append(f"inverted cells = {a.get('inverted_cells')}, must be 0")
    minvol = a.get("min_volume")
    if minvol is not None and float(minvol) <= 0:
        fails.append(f"min volume = {minvol}, must be > 0")
    mq = m.get("min_quality")
    if mq is None or float(mq) <= VOLUME_MIN_SCALED_QUALITY_FLOOR:
        fails.append(
            f"min scaled quality = {mq}, must be strictly > 0 (0.30 is a target, not a gate)"
        )
    if (m.get("low_quality_layers") or 0) != 0:
        fails.append(f"low/negative-quality layers = {m.get('low_quality_layers')}, must be 0")
    return (not fails), fails


def volume_gate_checklist_direct(vol: dict) -> tuple[bool, list[str]]:
    """ADR-0014 section 3.1 — the SAME gate for a volume that was not marched.

    Thresholds are the ADR-0008 thresholds, unchanged; only the source of each
    number moves, from pyHyp's report to `shared/volume_qc.volume_report`. This
    lives beside `volume_gate_checklist` rather than replacing it so that neither
    route can quietly become the other (ADR-0014 section 5).

    V5 has no marching layers to count, so the equivalent "no failing region" test
    is per block.
    """
    fails: list[str] = []
    if not vol.get("generation_completed"):
        fails.append(
            "volume generation did not complete "
            f"({vol.get('reason') or vol.get('non_finite_by_block') or vol.get('degenerate_block_shapes')})"
        )
        return False, fails
    if (vol.get("inverted_cells") or 0) != 0:
        fails.append(f"inverted cells = {vol.get('inverted_cells')}, must be 0")
    minvol = vol.get("min_volume")
    if minvol is None or float(minvol) <= 0.0:
        fails.append(f"min volume = {minvol}, must be > 0")
    mq = vol.get("min_scaled_quality")
    if mq is None or float(mq) <= VOLUME_MIN_SCALED_QUALITY_FLOOR:
        fails.append(
            f"min scaled quality = {mq}, must be strictly > 0 (0.30 is a target, not a gate)"
        )
    bad = vol.get("low_quality_blocks") or []
    if bad:
        fails.append(f"blocks with min scaled quality <= 0: {bad}")
    return (not fails), fails


def marchability_metrics(qc: dict, s0: float) -> dict:
    """The two ADR-0010 metrics. REPORTED, not gated — see the module docstring.

    ``cell_size_range`` is max/min surface cell edge over the staged surface, and
    ``min_cell_over_s0`` compares the smallest surface cell against pyHyp's first
    marching layer. Reference points measured in Stage 02 on lhs7_00:

    | surface                | range  | min/s0 | march                       |
    |------------------------|-------:|-------:|-----------------------------|
    | cap4 control           |   153x |   48.7 | completes, 54/128 bad       |
    | S1 as first built      |  3462x |    0.9 | explodes at layer 2         |
    | S1 after redistribution|    99x |   15.4 | 0/128 bad, min quality +0.224 |

    ``cell_size_range`` requires ``qc_blocks`` to have been given the *staged*
    surface — the one actually written for pyHyp — because staging is where the
    distribution is decided.
    """
    min_edge = qc.get("min_cell_edge_m")
    max_edge = qc.get("max_cell_edge_m")
    out: dict = {
        "min_cell_edge_m": min_edge,
        "min_cell_edge_block": qc.get("min_cell_edge_block"),
        "max_cell_edge_m": max_edge,
        "s0": s0,
    }
    if min_edge and max_edge:
        out["cell_size_range"] = float(max_edge) / float(min_edge)
    if min_edge and s0:
        out["min_cell_over_s0"] = float(min_edge) / float(s0)
    out["note"] = (
        "ADR-0010: reported, not gated. Cell-size range predicts catastrophic "
        "explosion; it does NOT predict marginal single-layer failure "
        "(COMMON_BRIEF section 3)."
    )
    return out


===== FILE: ./shared/geometry_sets.py =====

"""The locked geometry sets — SHARED CONTROL.

ADR-0011 section 4: the geometry sets are shared, so every strategy is developed
and judged on the same aircraft. ADR-0011 section 7.4 fixes their roles:

============================  ==========================================
set                           role
============================  ==========================================
``lhs100_seed42``             development and refinement
``round_c_lhs10_seed42``      **HOLD-OUT. No tuning, ever.**
``epse_calibration_lhs10_seed7``  Stage 01/02 evidence basis; permitted for
                              like-for-like comparison against a recorded
                              number, declared in the strategy's STUDY.md
============================  ==========================================

**Set identity is the quadruple (sampler id, seed, n, geometry-config sha256)**
(ADR-0001). A seed alone is NOT an identifier: Latin hypercube stratification
depends on n, so seed 42 at n=100 and seed 42 at n=10 share **zero** rows.
Authority is ``00_governance/lhs_authority.yaml``; regenerate and verify with
``00_governance/make_lhs_sets.py --check``.

The hold-out guard below is deliberate friction. It is not a permission system —
anyone can pass ``i_have_finished_developing_this_strategy=True`` — it is a
tripwire that makes reaching for the hold-out a visible, deliberate act rather
than an absent-minded one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
GOVERNANCE = REPO_ROOT / "AERIS_MESH_STUDY/00_governance"
GEOMETRY_CONFIG = REPO_ROOT / "configs/geometry/bwb.yaml"

#: name -> (seed, n, role)
SETS = {
    "lhs100_seed42": (42, 100, "development_and_refinement"),
    "round_c_lhs10_seed42": (42, 10, "HOLD_OUT_no_tuning"),
    "epse_calibration_lhs10_seed7": (7, 10, "stage01_02_evidence_basis"),
}

HOLD_OUT = "round_c_lhs10_seed42"


def _config():
    from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config

    return build_bwb_generator_config(yaml.safe_load(GEOMETRY_CONFIG.read_text()))


def design_matrix(set_name: str) -> tuple[np.ndarray, list[str]]:
    """Regenerate a locked set's design matrix in memory, with its column names.

    Regenerating rather than reading the CSV keeps the sampler as the single
    source of truth. ``make_lhs_sets.py --check`` is what asserts the CSVs on
    disk still agree with it.
    """
    from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix

    if set_name not in SETS:
        raise KeyError(f"unknown geometry set {set_name!r}; known: {sorted(SETS)}")
    seed, n, _role = SETS[set_name]
    cfg = _config()
    matrix = build_lhs_design_matrix(cfg, n, np.random.default_rng(seed))
    return matrix, cfg.active_design_variable_names()


def sample(set_name: str, index: int, *, i_have_finished_developing_this_strategy: bool = False):
    """One ``BWBDesignSample`` from a locked set.

    Accessing :data:`HOLD_OUT` requires the caller to state, in the call itself,
    that the strategy is frozen. ADR-0011 section 7.1 step 8: the hold-out is run
    **once**, after the user's freeze signal, with no tuning.
    """
    from aeris.generators.bwb_segmented_v1.params import BWBDesignSample

    if set_name == HOLD_OUT and not i_have_finished_developing_this_strategy:
        raise PermissionError(
            f"{HOLD_OUT} is the ADR-0011 hold-out. No strategy sees it during "
            "development, and no tuning of any kind is permitted on it. It is run "
            "once, after the user's freeze signal. If this really is the frozen "
            "hold-out run, pass i_have_finished_developing_this_strategy=True and "
            "record the freeze in the strategy's STUDY.md and in `status`."
        )
    matrix, names = design_matrix(set_name)
    row = matrix[index]
    return BWBDesignSample(**{n: float(v) for n, v in zip(names, row, strict=True)})


def geometry_id(set_name: str, index: int) -> str:
    """Stable identifier for one geometry, e.g. ``lhs100_seed42_017``."""
    return f"{set_name}_{index:03d}"


def wing(
    set_name: str,
    index: int,
    *,
    output_dir: Path | None = None,
    i_have_finished_developing_this_strategy: bool = False,
):
    """Build one geometry and return its AeroSandbox wing.

    Shared for the reason ADR-0011 section 4 gives: geometry is generated the same
    way for every strategy; how each turns it into blocks is the experiment.
    """
    from aeris.geometry.registry import get_geometry_generator

    smp = sample(
        set_name,
        index,
        i_have_finished_developing_this_strategy=i_have_finished_developing_this_strategy,
    )
    out = output_dir or (
        REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies/geom" / geometry_id(set_name, index)
    )
    case = get_geometry_generator("bwb_segmented").run_full_case(
        sample=smp,
        config=_config(),
        output_dir=out,
        save_plot=False,
        build_aerosandbox=True,
    )
    return case.wing


def authority() -> dict:
    """The frozen set authority, for embedding in a results manifest."""
    return yaml.safe_load((GOVERNANCE / "lhs_authority.yaml").read_text())


===== FILE: ./shared/ingestion.py =====

"""Section ingestion — SHARED CONTROL (ADR-0011 section 4).

Every strategy reads the generator's sections through this module, so the
comparison measures meshing methods rather than section readers.

**Ingestion is exactly two things** (ADR-0011 section 4): reading a section from
the generator, and mapping 2D curves to 3D through the wing. That is
:func:`section_loop_2d` and ``_map_sides_to_wing``. Everything else re-exported
here is a *neutral primitive* — a resampler, a TFI patch, a file writer — in the
same category as ``winslow_smooth_2d``: using one is a per-strategy decision, and
none of them decides anything on a strategy's behalf.

**Do not add a blocking, distribution or tip-closure decision here.**

Correction, 2026-08-14, found while building S0. `feature_split_sides` was
migrated into this module and is now **out of it**. It splits a section into
sides — which is to say it decides *where the block corners go* — and that is
blocking, not ingestion. It puts corners on the leading edge and the two blunt-TE
base corners, which is **S1's** answer; cap4 splits its section at ``+/- wrap_x``
into four sides instead, and would have been unable to use it. Keeping it shared
would have handed every strategy S1's corner policy under the name "ingestion",
which is the precise failure ADR-0011 exists to prevent, wearing a different
label. It now lives in `S1_tip_first/s1_stage02_prior_art.py`.
"""

from __future__ import annotations

import numpy as np

from aeris.mesh.surface import (  # noqa: F401 - re-exported for strategies
    MeshBuildError,
    SurfaceBlock,
    _block_qc,
    _corner_shape_metric,
    _insert_point_at_x,
    _map_sides_to_wing,
    _open_trailing_edge,
    _resample_piecewise,
    _resample_polyline,
    _smooth_patch_interior,
    _split_counts,
    _tfi_patch,
    _write_npz,
    _write_plot3d_formatted,
)

Array = np.ndarray


#: DECISION-0004: the as-built aircraft trailing edge is a **constant absolute
#: thickness along the span**. The decision offers two sanctioned values and says
#: "0.5 vs 1.0 mm: both give wing delta-CD ~ 0." **1.0 mm is used here**, on
#: measurement: at 0.5 mm the smallest surface cell is half the size and S1's
#: min-cell/s0 falls to 7.6-17.6, where the march mostly fails; at 1.0 mm it is
#: 13.1-20.0, entirely inside the band where marches have succeeded, and the
#: cell-size range improves from 116-218 to 93-133. The decision's own aerodynamic
#: analysis makes the two interchangeable, so this costs nothing.
#: The original value was 0.5 mm, chosen for manufacturability — "a single
#: constant TE thickness is the easiest to produce — one uniform mould land /
#: foam-cut offset / print wall / finishing gauge. A spanwise-VARYING TE (a
#: fractional or hybrid law) needs a spanwise-varying tool/process and is
#: materially harder to build to tolerance." The same decision says plainly:
#: "Mesh: model the AS-BUILT 0.5 mm TE."
TE_THICKNESS_ABS_M = 0.001

#: DECISION-0004 "Where it applies", the MESH-ONLY escape hatch, now validated:
#:
#:   "If a real pyHyp march cannot advance the thin inboard TE (0.5 mm ~ 0.05%c at
#:    root), apply a mesh-only local inboard floor (~0.25%c) - a NUMERICAL artifact
#:    of the solver, not a change to the aircraft, and quantified here as ~0 drag.
#:    ... Pending pyHyp validation (see Open items)."
#:
#: **The validation exists now, and it also corrects the assumed value.**
#: DECISION-0004 records the meshability floor as "assumed ~0.25%c (UNVALIDATED)"
#: and lists "Validate the 0.25%c fractional term against a real pyHyp march and
#: tighten to the true marchability floor" as an Open item. Measured on ten
#: `lhs100_seed42` geometries with S1, epsE 1.5 / 2.0 / 3.0:
#:
#:     TE law                       pass counts
#:     0.5%c fraction (no floor)     5 / 6 / 7      <- the study's accidental value
#:     constant 0.5 mm               0 / 1 / 4
#:     max(0.25%c, 0.5 mm)           0 / 1 / 4      <- the assumed floor: NO HELP
#:     max(0.50%c, 0.5 mm)           this value
#:
#: **0.25%c is not the marchability floor.** Flooring at it changed nothing, which
#: also falsifies the hypothesis that the thin inboard edge was the problem - the
#: root went 0.5 mm -> 2.1 mm for no gain. What the 5/6/7 row shows is that ~0.5%c
#: IS enough, so the true floor lies between 0.25%c and 0.5%c and the assumed value
#: was roughly a factor of two optimistic.
#:
#: The mesh therefore uses  max(TE_MESH_FLOOR_FRAC * chord, TE_THICKNESS_ABS_M),
#: which is 0.5 mm wherever the chord is small enough to need it and 0.25%c inboard.
#: The AIRCRAFT is unchanged: constant 0.5 mm remains what goes to the shop.
TE_MESH_FLOOR_FRAC = 0.005


def section_loop_2d(
    xsec: object,
    *,
    te_thickness: float | None = None,
    te_thickness_abs_m: float | None = TE_THICKNESS_ABS_M,
    mesh_floor_frac: float | None = TE_MESH_FLOOR_FRAC,
) -> tuple[Array, int]:
    """Return the open 2D section contour and its leading-edge index.

    Ordering follows the AeroSandbox convention: upper trailing edge -> leading
    edge -> lower trailing edge. A blunt trailing edge is opened to
    ``te_thickness`` so the TE base is a real two-corner feature rather than a
    cusp.

    **The trailing edge is ABSOLUTE, not a chord fraction** (DECISION-0004).
    ``te_thickness_abs_m`` is metres and is converted per section using that
    section's own chord, so the physical base is the same size at every station
    and on every geometry. ``te_thickness`` remains available as a raw chord
    fraction for reproducing older results; passing both is an error.

    This was wrong for most of the study and it mattered. Running 0.005 as a
    fraction meshed a trailing edge of **4.3-5.0 mm at the root** — about nine
    times the 0.5 mm that goes to the shop — tapering to 0.46-0.89 mm at the tip,
    i.e. exactly the spanwise-varying edge DECISION-0004 rejected as harder to
    manufacture. It is also the root cause of the marching failures chased in both
    S0 and S1: because the fraction shrinks with chord, the smallest surface cell
    lives at the tip trailing edge and scales with TIP CHORD, so min-cell/`s0`
    varied 6.9 to 17.6 across ten geometries and no single epsE could serve that
    spread. A constant absolute edge makes that cell the same size everywhere.
    """
    if te_thickness is not None and te_thickness_abs_m is not None:
        raise MeshBuildError(
            "pass te_thickness (chord fraction) or te_thickness_abs_m (metres), not both"
        )
    if te_thickness is None:
        chord = float(getattr(xsec, "chord", 0.0))
        if chord <= 0.0:
            raise MeshBuildError("WingXSec has no positive chord; cannot apply an absolute TE.")
        te_thickness = float(te_thickness_abs_m) / chord
        if mesh_floor_frac:
            # The mesh-only inboard floor. Clamped at 5%c, the same envelope the
            # raw fraction is validated against.
            te_thickness = min(max(te_thickness, float(mesh_floor_frac)), 0.05)
    airfoil = getattr(xsec, "airfoil", None)
    if airfoil is None:
        raise MeshBuildError("WingXSec has no airfoil.")
    coords = np.asarray(airfoil.coordinates, dtype=float)
    if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 9:
        raise MeshBuildError("Airfoil coordinates must have shape (N, 2), N >= 9.")
    if te_thickness > 0.0:
        coords = _open_trailing_edge(coords, te_thickness)
    le_index = int(np.argmin(coords[:, 0]))
    if le_index in (0, len(coords) - 1):
        raise MeshBuildError("Unexpected airfoil ordering: LE must lie between the TE points.")
    return coords, le_index


===== FILE: ./shared/__init__.py =====

"""The shared experimental control for the six independent strategy studies.

ADR-0011 section 4 draws the independence line. **Shared** — one implementation,
used by all six:

- ``ingestion``    CAD/section ingestion and 2D->3D mapping through the wing
- ``qc``           QC metric *definitions*, orientation, artifact writing
- ``gates``        gate thresholds and the pass/fail checklists
- ``geometry_sets``the locked geometry sets and their identity rule
- ``pyhyp_runner`` the pyHyp invocation and its argument construction
- ``verify``       the verifier

**Per-strategy**, and therefore absent from this package: all blocking and
block-graph construction, tip closure, spanwise distribution and station
placement, chordwise laws and point counts, any smoothing/projection/deformation
the method calls for, and the strategy's own pyHyp-facing surface staging.

Geometry is generated the same way for every strategy; how each turns it into
blocks is the experiment. If each study wrote its own section reader and its own
quality metric, the comparison would measure readers and metrics rather than
meshing methods.

**This line is not re-litigated mid-study.** If a strategy genuinely cannot work
within it, that is a finding to record and raise — not a reason to copy shared
code into a strategy folder, or strategy code into this package.

Usage from a strategy module::

    import sys
    from pathlib import Path
    STUDIES = Path(__file__).resolve().parents[1]
    REPO_ROOT = STUDIES.parents[1]
    sys.path.insert(0, str(REPO_ROOT / "src"))
    sys.path.insert(0, str(STUDIES))

    from shared.ingestion import section_loop_2d, feature_split_sides
    from shared.qc import qc_blocks, orient_blocks_consistently
"""

__all__ = ["ingestion", "qc", "gates", "geometry_sets", "pyhyp_runner", "verify"]


===== FILE: ./shared/pyhyp_runner.py =====

"""The pyHyp invocation and its argument construction — SHARED CONTROL.

ADR-0011 section 4: one invocation, used by all six strategies, so that a
difference in march outcome is a difference in surface and not a difference in how
pyHyp was called. Migrated in substance from
`03_cap4_epse/s1_volume_canary.py`, generalised to take any strategy's staged
blocks.

**Heavy compute is never launched from here.** `prepare` writes the staged
surfaces and the pyHyp run inputs and returns the commands; the user launches
them; `collect` reads the results back and applies the frozen checklist. That is a
standing invariant of this study (ADR-0011 section 11 / RUNBOOK working notes), not
a property of this module.

Three traps this module exists to hold, all paid for in Stage 02:

1. **`characteristic_length` is the bounding-box DIAGONAL**, `norm(ptp(pts))` —
   `aeris.mesh.surface` computes it that way and pyHyp derives *both* `s0` and
   `marchDist` from it. Using the x-extent instead (0.94 against the correct
   1.5171) makes every march inconsistent with every cap4 number this study
   compares against.
2. **The runner executes from its own directory**, so `inputFile` must be
   absolute. A relative path raises "Input file not found".
3. **Confirmation must be at a genuinely finer level.** `shared.gates` holds the
   ladder; `prepare` refuses a "confirmation" that is not finer than its
   calibration.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from aeris.cfd.meshing.pyhyp_extrude import (  # noqa: E402
    mach_aero_python,
    parse_pyhyp_march_metrics,
    write_pyhyp_run_inputs,
)
from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS as LEVELS  # noqa: E402
from aeris.cfd.meshing.pyhyp_options import build_pyhyp_options  # noqa: E402

from . import gates  # noqa: E402
from .qc import qc_blocks, write_surface_artifacts  # noqa: E402


def characteristic_length(blocks) -> float:
    """Bounding-box DIAGONAL of the staged surface. See trap 1 in the module doc."""
    pts = np.concatenate([b.xyz.reshape(-1, 3) for b in blocks], axis=0)
    return float(np.linalg.norm(np.ptp(pts, axis=0)))


def level_is_finer(candidate: str, than: str) -> bool:
    """True if ``candidate`` is a genuine refinement of ``than``.

    A level is finer only if it is at least as un-coarsened AND has at least as
    many normal-direction points, with at least one strictly better. The `L*`
    family uses coarsen=4, so `L4` (N=37) is COARSER than `smoke` (N=129) even
    though its name sorts later — the ADR-0008 error recorded in ADR-0011
    section 5.4.
    """
    a, b = LEVELS[candidate], LEVELS[than]
    no_worse = a["coarsen"] <= b["coarsen"] and a["N"] >= b["N"]
    strictly_better = a["coarsen"] < b["coarsen"] or a["N"] > b["N"]
    return no_worse and strictly_better


def prepare(
    *,
    strategy_id: str,
    geometry_id: str,
    blocks,
    out_dir: Path,
    level: str,
    epse_ladder=gates.EPSE_LADDER,
    confirming_level: str | None = None,
    s0_fraction_override: float | None = None,
) -> dict:
    """Stage one geometry's surface and write pyHyp run inputs for each epsE.

    Returns a manifest containing the shell commands for the user to launch.
    Raises before writing anything if the surface would not be accepted, so a
    known-bad surface never consumes march time.
    """
    if confirming_level is not None and not level_is_finer(level, confirming_level):
        raise ValueError(
            f"level {level!r} is not finer than {confirming_level!r} "
            f"({LEVELS[level]} vs {LEVELS[confirming_level]}); a confirmation at a "
            "coarser level confirms nothing (ADR-0011 section 5.4)"
        )
    if s0_fraction_override is not None and s0_fraction_override <= 0.0:
        raise ValueError("s0_fraction_override must be positive")

    qc = qc_blocks(blocks)
    if not qc["accepted_pre_pyhyp"]:
        raise ValueError(
            f"{geometry_id}: surface rejected before marching: {qc['failure_reasons']}"
        )

    char_len = characteristic_length(blocks)
    mach_py = str(mach_aero_python())
    manifest: dict = {
        "schema": "aeris.mesh_study.strategy_march_prepare.v1",
        "prepared_utc": datetime.now(timezone.utc).isoformat(),
        "adr": "ADR-0011-independent-strategy-studies.md",
        "strategy_id": strategy_id,
        "geometry_id": geometry_id,
        "level": level,
        "level_settings": dict(LEVELS[level]),
        "confirming_level": confirming_level,
        "epse_ladder": list(epse_ladder),
        "characteristic_length": char_len,
        "s0_fraction_override": s0_fraction_override,
        "surface": {
            "block_count": qc["block_count"],
            "total_cells": qc["total_cells"],
            "global": qc["global"],
        },
        "cap4_reference": gates.CAP4_REFERENCE,
        "runs": [],
        "commands": [],
    }

    for eps in epse_ladder:
        sdir = Path(out_dir) / geometry_id / f"eps{str(eps).replace('.', '')}"
        sdir.mkdir(parents=True, exist_ok=True)
        arts = write_surface_artifacts(blocks, sdir)
        effective = build_pyhyp_options(
            Path(arts["surface_fmt"]["path"]).resolve(),  # trap 2: absolute
            level=level,
            characteristic_length=char_len,
            output_file=(sdir / "wing_vol.cgns").resolve(),
            eps_e_far=eps,
            eps_i_far=gates.EPSI_OVER_EPSE * eps,
            s0=(
                s0_fraction_override * char_len
                if s0_fraction_override is not None
                else None
            ),
        )
        runner = write_pyhyp_run_inputs(sdir, effective)
        s0 = float(effective.values.get("s0", LEVELS[level]["s0_frac"] * char_len))
        march = gates.marchability_metrics(qc, s0)
        (sdir / "surface_report.json").write_text(
            json.dumps(
                {
                    "strategy_id": strategy_id,
                    "geometry_id": geometry_id,
                    "characteristic_length": char_len,
                    "accepted_pre_pyhyp": True,
                    "block_count": qc["block_count"],
                    "total_cells": qc["total_cells"],
                    "global": qc["global"],
                    "marchability": march,
                },
                indent=2,
            )
            + "\n"
        )
        # Redirect to `run_stdout.log`. `collect` falls back to parsing that log
        # when `volume_report.json` is absent, which it always is when the static
        # runner is launched directly — so a command without the redirect produces
        # a CGNS that cannot be scored. Found by running a 30-march campaign whose
        # results were unreadable afterwards.
        cmd = f"(cd {sdir} && {mach_py} {runner.name} > run_stdout.log 2>&1)"
        manifest["commands"].append(cmd)
        manifest["runs"].append(
            {
                "epsE": eps,
                "epsI": gates.EPSI_OVER_EPSE * eps,
                "dir": str(sdir),
                "runner": str(runner),
                "surface_fmt_sha256": arts["surface_fmt"]["sha256"],
                "s0": s0,
                "marchability": march,
            }
        )

    root = Path(out_dir) / geometry_id
    (root / "prepare_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _wall_clock_s(run_dir: Path) -> float | None:
    """March wall-clock, estimated from file mtimes.

    ADR-0011 section 6.2 requires wall-clock per march, and neither
    `volume_report.json` nor pyHyp's march log records it. This estimates it as
    (march log mtime - runner script mtime), which brackets the run because the
    runner is written by `prepare` and the log is closed at exit. It is an
    ESTIMATE and is labelled as one wherever it is reported; a run prepared long
    before it is launched will overstate it.
    """
    log = Path(run_dir) / "run_stdout.log"
    runner = Path(run_dir) / "run_pyhyp.py"
    if not (log.is_file() and runner.is_file()):
        return None
    return round(log.stat().st_mtime - runner.stat().st_mtime, 1)


def read_result(run_dir: Path) -> dict | None:
    """Read one march's result, or None if it has not been run.

    The static runner writes only the CGNS; `volume_report.json` comes from the
    `run_pyhyp_subprocess` wrapper, which is bypassed when the runner is launched
    directly. Falling back to the march log is what stops a completed run being
    reported as NOT_RUN.
    """
    run_dir = Path(run_dir)
    vr = run_dir / "volume_report.json"
    log = run_dir / "run_stdout.log"
    if vr.is_file():
        return json.loads(vr.read_text())
    if log.is_file():
        text = log.read_text()
        mm = parse_pyhyp_march_metrics(text)
        return {
            # A march still in progress, or killed, must never be scored. Without
            # this the checklist happily PASSED a truncated 95-layer run that had
            # simply not reached its bad layers yet.
            "march_completed": "pyHyp done" in text,
            "status": "valid" if mm.get("passed") else "invalid",
            "march_metrics": mm,
            "volume_audit": {
                "inverted_cells": 0 if mm.get("passed") else None,
                "min_volume": mm.get("min_volume"),
            },
            "source": "parsed from run_stdout.log",
        }
    return None


def collect(
    *,
    strategy_id: str,
    out_dir: Path,
    geometry_ids: list[str],
    level: str,
    epse_ladder=gates.EPSE_LADDER,
) -> dict:
    """Apply the frozen volume checklist and select this strategy's epsE.

    Selection rule, fixed by ADR-0008 and carried into ADR-0011 section 5.1: the
    **highest** ladder value passing every geometry. The ladder is not extended
    after a failure. Selection is not final until confirmed at a genuinely finer
    level.
    """
    rows = []
    for gid in geometry_ids:
        for eps in epse_ladder:
            sdir = Path(out_dir) / gid / f"eps{str(eps).replace('.', '')}"
            vol = read_result(sdir)
            if vol is None:
                rows.append({"geometry": gid, "epsE": eps, "state": "NOT_RUN"})
                continue
            ok, fails = gates.volume_gate_checklist(vol)
            m = vol.get("march_metrics") or {}
            rows.append(
                {
                    "geometry": gid,
                    "epsE": eps,
                    "state": "PASS" if ok else "FAIL",
                    "failures": fails,
                    "inverted_cells": (vol.get("volume_audit") or {}).get("inverted_cells"),
                    "low_quality_layers": m.get("low_quality_layers"),
                    "layer_count": m.get("layer_count"),
                    "min_quality": m.get("min_quality"),
                    "min_volume": m.get("min_volume"),
                    "wall_clock_s_estimated_from_mtimes": _wall_clock_s(sdir),
                }
            )

    passing_all = []
    for eps in epse_ladder:
        got = [r for r in rows if r["epsE"] == eps]
        if got and all(r["state"] == "PASS" for r in got):
            passing_all.append(eps)
    selected = max(passing_all) if passing_all else None

    quals = [
        row["min_quality"]
        for row in rows
        if row["state"] == "PASS" and row["min_quality"] is not None
    ]
    report = {
        "schema": "aeris.mesh_study.strategy_march_collect.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "adr": "ADR-0011-independent-strategy-studies.md",
        "strategy_id": strategy_id,
        "level": level,
        "geometries": geometry_ids,
        "epse_ladder": list(epse_ladder),
        "rows": rows,
        "epse_passing_all_geometries": passing_all,
        "epse_selected": selected,
        "selection_rule": (
            "highest ladder value passing the frozen volume checklist on every "
            "geometry; ladder never extended after a failure (ADR-0008 section 6)"
        ),
        "worst_case_min_quality": min(quals) if quals else None,
        "median_min_quality": float(np.median(quals)) if quals else None,
        "cap4_reference": gates.CAP4_REFERENCE,
        "not_final_until": (
            f"confirmed at a genuinely finer level than {level!r} "
            f"(ADR-0011 section 5.4)"
        ),
    }
    (Path(out_dir) / f"collect_{level}.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


===== FILE: ./shared/qc.py =====

"""QC metric definitions, orientation and artifact writing — SHARED CONTROL.

ADR-0011 section 4: QC metric *definitions*, gate thresholds, and the verifier are
shared so that a comparison between strategies is a comparison between meshing
methods and not between quality metrics. **Migrated unchanged** from
`04_strategy_prototypes/stage02_common.py`, so every number recorded in `status`
remains directly comparable.

`winslow_smooth_2d` is a generic operator and is shared under ADR-0011 section 4.1;
using it is a per-strategy decision. COMMON_BRIEF section 1 records that it made
S1's Stage 02 tip cap **worse** (-0.0363 -> -0.0499), which is a measurement about
that cap, not about the operator.
"""

from __future__ import annotations

import numpy as np

from .ingestion import Array, SurfaceBlock, _block_qc, _write_npz, _write_plot3d_formatted


def winslow_smooth_2d(
    patch: Array,
    iterations: int = 200,
    relaxation: float = 1.0,
    fixed_edges: tuple[bool, bool, bool, bool] = (True, True, True, True),
) -> Array:
    """Elliptic (Winslow) smoothing of a structured 2D patch.

    Laplacian smoothing averages a node toward its neighbours in PHYSICAL space,
    which shrinks the grid and slides nodes along the boundary direction. Winslow
    instead solves for the mapping whose computational coordinates are harmonic
    functions of the physical ones,

        alpha * x_xi_xi - 2 * beta * x_xi_eta + gamma * x_eta_eta = 0

    with alpha = x_eta . x_eta, beta = x_xi . x_eta, gamma = x_xi . x_xi. For a
    convex domain the resulting map obeys a maximum principle and cannot fold,
    and in practice it strongly un-folds non-convex ones too. That is the
    property being tested here; Laplacian smoothing has no such guarantee, which
    is why every earlier attempt in this stage failed.

    ``fixed_edges`` holds (i=0, i=last, j=0, j=last). Edges left free are updated
    by one-sided extrapolation so a block interface can relax instead of pinning
    the fold in place.
    """
    p = patch.astype(float).copy()
    ni, nj, _ = p.shape
    if ni < 3 or nj < 3:
        return p
    for _ in range(max(0, int(iterations))):
        x_xi = 0.5 * (p[2:, 1:-1, :] - p[:-2, 1:-1, :])
        x_eta = 0.5 * (p[1:-1, 2:, :] - p[1:-1, :-2, :])
        alpha = np.sum(x_eta * x_eta, axis=2)[..., None]
        beta = np.sum(x_xi * x_eta, axis=2)[..., None]
        gamma = np.sum(x_xi * x_xi, axis=2)[..., None]
        cross = p[2:, 2:, :] - p[:-2, 2:, :] - p[2:, :-2, :] + p[:-2, :-2, :]
        num = (
            alpha * (p[2:, 1:-1, :] + p[:-2, 1:-1, :])
            + gamma * (p[1:-1, 2:, :] + p[1:-1, :-2, :])
            - 0.5 * beta * cross
        )
        den = 2.0 * (alpha + gamma)
        den = np.where(np.abs(den) < 1e-30, 1e-30, den)
        target = num / den
        p[1:-1, 1:-1, :] += relaxation * (target - p[1:-1, 1:-1, :])
        if not fixed_edges[0]:
            p[0, 1:-1, :] = 2.0 * p[1, 1:-1, :] - p[2, 1:-1, :]
        if not fixed_edges[1]:
            p[-1, 1:-1, :] = 2.0 * p[-2, 1:-1, :] - p[-3, 1:-1, :]
        if not fixed_edges[2]:
            p[1:-1, 0, :] = 2.0 * p[1:-1, 1, :] - p[1:-1, 2, :]
        if not fixed_edges[3]:
            p[1:-1, -1, :] = 2.0 * p[1:-1, -2, :] - p[1:-1, -3, :]
    return p


def orient_patches_2d(patches: list[Array]) -> tuple[list[Array], list[bool]]:
    """Give every 2D patch the same signed orientation.

    Assembling domains from independently ordered control edges leaves some
    patches wound the opposite way, which shows up as a uniformly negative
    scaled Jacobian even though the geometry is sound. Consistent normals are a
    hard requirement of the Stage 00 surface_validity gate, so this normalizes
    winding by flipping the j index of any patch that disagrees with positive
    orientation. Flipping an index reverses winding without moving a node.
    """
    out, flipped = [], []
    for patch in patches:
        a = patch[:-1, :-1]
        b = patch[1:, :-1]
        c = patch[1:, 1:]
        d = patch[:-1, 1:]

        def _cross(p, q):
            return p[..., 0] * q[..., 1] - p[..., 1] * q[..., 0]

        area = float((0.5 * (_cross(b - a, d - a) + _cross(d - c, b - c))).sum())
        if area < 0.0:
            out.append(patch[:, ::-1, :])
            flipped.append(True)
        else:
            out.append(patch)
            flipped.append(False)
    return out, flipped


def _boundary_edges(xyz: Array, decimals: int = 7):
    """Directed boundary edges of a structured patch, walked counter-clockwise.

    The walk direction is what carries orientation: two correctly oriented
    neighbours traverse their shared edge in OPPOSITE directions.
    """
    key = lambda p: tuple(np.round(p, decimals))  # noqa: E731
    loop = (
        [xyz[i, 0] for i in range(xyz.shape[0])]
        + [xyz[-1, j] for j in range(1, xyz.shape[1])]
        + [xyz[i, -1] for i in range(xyz.shape[0] - 2, -1, -1)]
        + [xyz[0, j] for j in range(xyz.shape[1] - 2, 0, -1)]
    )
    keys = [key(p) for p in loop]
    return [(keys[i], keys[(i + 1) % len(keys)]) for i in range(len(keys))]


def spanwise_interpolation_error(blocks: list[Array]) -> dict:
    """Measure the error introduced by interpolating between stations.

    Drops every other station, rebuilds those columns by linear interpolation
    from their neighbours, and compares against the true station. That is a
    direct measurement of what the loft curvature costs, on this geometry, in
    metres and as a fraction of local chord.
    """
    worst_abs = 0.0
    worst_frac = 0.0
    for blk in blocks:
        n = blk.shape[1]
        chord = float(np.ptp(blk[:, :, 0])) or 1.0
        for j in range(1, n - 1, 2):
            approx = 0.5 * (blk[:, j - 1, :] + blk[:, j + 1, :])
            d = float(np.linalg.norm(blk[:, j, :] - approx, axis=1).max())
            worst_abs = max(worst_abs, d)
            worst_frac = max(worst_frac, d / chord)
    return {"worst_abs_m": worst_abs, "worst_frac_of_chord": worst_frac}


def orient_blocks_consistently(blocks: list[SurfaceBlock]) -> tuple[list[SurfaceBlock], dict]:
    """Give every block a consistent outward normal across the whole surface.

    pyHyp rejects a surface whose block normals disagree - "ERROR: Normal
    directions may be wrong" - and refuses to march at all. The Stage 00
    surface_validity gate calls for "consistent normals", but per-block winding
    checks cannot see it: each block can be individually well-formed while its
    neighbour faces the other way.

    Orientation is propagated across shared edges instead. Two correctly
    oriented neighbours traverse their shared edge in opposite directions, so a
    breadth-first walk from a seed block fixes every relative orientation. The
    whole surface is then flipped if its enclosed signed volume is negative, so
    the normals end up pointing outward rather than merely agreeing.
    """
    n = len(blocks)
    edges = [_boundary_edges(b.xyz) for b in blocks]
    owner: dict = {}
    for bi, elist in enumerate(edges):
        for e in elist:
            owner.setdefault(frozenset(e), []).append((bi, e))

    flip = [False] * n
    seen = {0}
    queue = [0]
    while queue:
        bi = queue.pop(0)
        for e in edges[bi]:
            for bj, ej in owner.get(frozenset(e), []):
                if bj == bi or bj in seen:
                    continue
                same_direction = (e == ej)
                # After accounting for bi's own flip, a shared edge walked the
                # SAME way means bj is mirrored relative to bi.
                flip[bj] = (same_direction != flip[bi])
                seen.add(bj)
                queue.append(bj)

    oriented = [
        SurfaceBlock(name=b.name, xyz=(b.xyz[:, ::-1, :] if f else b.xyz), family=b.family)
        for b, f in zip(blocks, flip, strict=True)
    ]

    # Divergence theorem: 6V = sum over cells of (centroid . area-normal).
    total = 0.0
    for b in oriented:
        x = b.xyz
        p00, p10, p11, p01 = x[:-1, :-1], x[1:, :-1], x[1:, 1:], x[:-1, 1:]
        area_n = 0.5 * (np.cross(p11 - p00, p01 - p10))
        ctr = 0.25 * (p00 + p10 + p11 + p01)
        total += float(np.sum(ctr * area_n))
    if total < 0.0:
        oriented = [
            SurfaceBlock(name=b.name, xyz=b.xyz[:, ::-1, :], family=b.family) for b in oriented
        ]
        flip = [not f for f in flip]

    info = {
        "blocks_reached_by_edge_walk": len(seen),
        "block_count": n,
        "all_blocks_connected": len(seen) == n,
        "flipped": [b.name for b, f in zip(blocks, flip, strict=True) if f],
        "signed_volume_before_global_flip": total,
    }
    return oriented, info


def qc_blocks(blocks: list[SurfaceBlock]) -> dict:
    """Run the shared per-block QC and return normalized global metrics."""
    per_block = [_block_qc(b) for b in blocks]
    total_cells = sum(int(b["cells"]) for b in per_block)
    result = {
        "block_count": len(blocks),
        "total_cells": total_cells,
        "blocks": per_block,
        "global": {
            "min_shape_metric": min(float(b["min_shape_metric"]) for b in per_block),
            "min_scaled_jacobian": min(float(b["min_scaled_jacobian"]) for b in per_block),
            "max_equiangle_skewness": max(float(b["max_equiangle_skewness"]) for b in per_block),
            "max_aspect_ratio": max(float(b["max_aspect_ratio"]) for b in per_block),
            "min_area": min(float(b["min_area"]) for b in per_block),
            "max_adjacent_normal_angle_deg": max(
                float(b["max_adjacent_normal_angle_deg"]) for b in per_block
            ),
        },
    }
    # Smallest surface cell, which governs whether the first marching layer can
    # even fit. Nothing checked this before, and a cell smaller than s0 inverts
    # the march at layer 2 while every quality metric still looks healthy.
    #
    # ADDED at the ADR-0011 migration, 2026-08-14: `max_cell_edge_m`. It is a new
    # REPORTED metric, not a changed definition and not a new gate — ADR-0011
    # section 6.2 requires the staged cell-size range for every strategy, and
    # Stage 02 computed max/min ad hoc outside qc_blocks. No existing metric
    # changed, so every number recorded in `status` remains comparable.
    min_edge = float("inf")
    min_edge_block = None
    max_edge = 0.0
    max_edge_block = None
    for b in blocks:
        x = b.xyz
        di = np.linalg.norm(np.diff(x, axis=0), axis=2)
        dj = np.linalg.norm(np.diff(x, axis=1), axis=2)
        e = float(min(di.min(), dj.min()))
        if e < min_edge:
            min_edge, min_edge_block = e, b.name
        e_max = float(max(di.max(), dj.max()))
        if e_max > max_edge:
            max_edge, max_edge_block = e_max, b.name
    result["min_cell_edge_m"] = min_edge
    result["min_cell_edge_block"] = min_edge_block
    result["max_cell_edge_m"] = max_edge
    result["max_cell_edge_block"] = max_edge_block
    result["cell_size_range"] = max_edge / min_edge if min_edge > 0 else float("inf")

    g = result["global"]
    reasons = []
    if not g["min_scaled_jacobian"] > 0.0:
        reasons.append("positive_scaled_jacobian")
    if not g["min_area"] > 0.0:
        reasons.append("minimum_surface_cell_area")
    result["failure_reasons"] = reasons
    result["accepted_pre_pyhyp"] = not reasons
    return result


def worst_corner_angle_deg(patch: Array) -> float:
    """Largest interior corner angle in a structured patch, in degrees."""
    worst = 0.0
    ni, nj, _ = patch.shape
    for i in range(ni - 1):
        for j in range(nj - 1):
            quad = [patch[i, j], patch[i + 1, j], patch[i + 1, j + 1], patch[i, j + 1]]
            for k in range(4):
                a = quad[(k - 1) % 4] - quad[k]
                b = quad[(k + 1) % 4] - quad[k]
                na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
                if na < 1e-14 or nb < 1e-14:
                    continue
                ang = float(np.degrees(np.arccos(np.clip(float(a @ b) / (na * nb), -1.0, 1.0))))
                worst = max(worst, ang)
    return worst


def write_surface_artifacts(blocks: list[SurfaceBlock], out_dir) -> dict:
    """Write the shared surface artifact set and return their hashes."""
    import hashlib
    from pathlib import Path

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = out_dir / "surface.fmt"
    npz = out_dir / "surface_blocks.npz"
    _write_plot3d_formatted(fmt, blocks)
    _write_npz(npz, blocks)

    def _sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    return {
        "surface_fmt": {"path": str(fmt), "sha256": _sha(fmt)},
        "surface_npz": {"path": str(npz), "sha256": _sha(npz)},
    }


===== FILE: ./shared/selftest.py =====

"""Self-test for the shared control module.

The shared module is the experimental control: if it drifts, every strategy's
numbers drift with it and the comparison silently stops meaning anything. This
reproduces the frozen Stage 02 S1 configuration through the migrated shared code
and asserts the recorded numbers, so a regression in `shared/` is caught here
rather than in a strategy's results.

It uses `S1_tip_first/s1_stage02_prior_art.py` — the archived Stage 02
implementation — purely as a fixture with a known answer. That file is prior art,
not S1's entry under ADR-0011.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/shared/selftest.py

Reference, `status` section 5F.3 — S1 frozen configuration on
`epse_calibration_lhs10_seed7` index 0 (`lhs7_00`), chord_points 49, uniform
chordwise, te_base_points 3, collar_points 3, realise_law True at 0.010 m:

    blocks                    8
    min scaled Jacobian    +0.045
    cell-size range           99x
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

STUDIES = Path(__file__).resolve().parents[1]
REPO_ROOT = STUDIES.parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(STUDIES))
sys.path.insert(0, str(STUDIES / "S1_tip_first"))

from shared import gates, geometry_sets, verify  # noqa: E402
from shared.ingestion import (  # noqa: E402
    SurfaceBlock,
    _map_sides_to_wing,
    section_loop_2d,
)
from shared.qc import orient_blocks_consistently, qc_blocks  # noqa: E402

import s1_stage02_prior_art as prior  # noqa: E402

# `feature_split_sides` is S1's BLOCKING decision, not shared ingestion — it puts
# corners on the LE and the two blunt-TE base corners, which is S1's answer and
# not cap4's. It moved into S1's folder on 2026-08-14 while S0 was being built.
feature_split_sides = prior.feature_split_sides

# The frozen Stage 02 S1 configuration, `status` section 5F.3.
CFG = dict(
    chord_points=49,
    distribution="uniform",
    te_base_points=3,
    collar_points=3,
    te_thickness=0.005,
    target_spanwise_cell=0.010,
)
EXPECTED = {"blocks": 8, "min_scaled_jacobian": 0.045, "cell_size_range": 99.0}
TOLERANCE = 0.10  # 10% — this guards against drift, not against float noise


def build_prior_art_s1(wing):
    """Stage 02's S1 surface, rebuilt through the migrated shared modules."""
    xsecs = list(wing.xsecs)
    sides_by_xsec = []
    for xsec in xsecs:
        coords, le_index = section_loop_2d(
            xsec, te_thickness=CFG["te_thickness"], te_thickness_abs_m=None
        )
        sides_by_xsec.append(
            feature_split_sides(
                coords,
                le_index,
                chord_points=CFG["chord_points"],
                te_base_points=CFG["te_base_points"],
                distribution=CFG["distribution"],
            )
        )
    oml = _map_sides_to_wing(wing, sides_by_xsec)

    le_line = np.asarray(
        wing.mesh_line(x_nondim=[0.0] * len(xsecs), z_nondim=[0.0] * len(xsecs), add_camber=False)
    )
    lengths = [float(np.linalg.norm(le_line[i + 1] - le_line[i])) for i in range(len(xsecs) - 1)]
    law = prior.geometric_progression_counts(lengths, target_cell=CFG["target_spanwise_cell"])
    oml = prior.realise_spanwise_law(oml, [p - 1 for p in law])

    blocks = [
        SurfaceBlock(name=n, xyz=b, family="wall")
        for n, b in zip(["oml_upper", "oml_lower", "te_base"], oml, strict=True)
    ]
    ring, ring_info = prior.oml_tip_ring_2d(sides_by_xsec[-1])
    cap, cap_info = prior.butterfly_from_ring(
        ring, ring_info["corner_indices"], collar_points=CFG["collar_points"]
    )
    blocks += [
        SurfaceBlock(name=n, xyz=prior.map_2d_patch_to_tip(wing, p), family="wall")
        for n, p in zip(cap_info["block_names"], cap, strict=True)
    ]
    return orient_blocks_consistently(blocks)


def main() -> int:
    wing = geometry_sets.wing("epse_calibration_lhs10_seed7", 0)
    blocks, orientation = build_prior_art_s1(wing)
    qc = qc_blocks(blocks)
    # Stage 02 used the chord FRACTION; the reference must match the mesh.
    fid = verify.oml_fidelity(wing, blocks, te_thickness_frac=CFG["te_thickness"])
    water = verify.watertight_tip(blocks)

    got = {
        "blocks": qc["block_count"],
        "min_scaled_jacobian": qc["global"]["min_scaled_jacobian"],
        "cell_size_range": qc["cell_size_range"],
    }
    print(f"{'metric':24s} {'expected':>12s} {'got':>12s}")
    failures = []
    for key, want in EXPECTED.items():
        have = got[key]
        ok = abs(have - want) <= TOLERANCE * abs(want)
        print(f"{key:24s} {want:12.4g} {have:12.4g}  {'OK' if ok else 'DRIFT'}")
        if not ok:
            failures.append(f"{key}: expected ~{want}, got {have}")

    print(f"\nwatertight tip          {water['watertight_tip']}")
    print(f"blocks reached by walk  {orientation['blocks_reached_by_edge_walk']}"
          f"/{orientation['block_count']}")
    print(f"enclosed signed volume  {orientation['signed_volume_before_global_flip']:+.4e}")
    print(f"fidelity worst frac     {fid['worst_frac_of_local_chord']:.3e} of local chord")
    print(f"fidelity unverified     {fid['fidelity_unverified_for_refined_blocks']} "
          f"{fid['skipped_spanwise_refined_blocks']}")

    # The spanwise law is realised, so fidelity is legitimately UNVERIFIED for the
    # refined blocks — COMMON_BRIEF section 9.5. `gates.surface_gate_checklist`
    # must treat that as a failure rather than a pass, and this asserts it does.
    passed, reasons = gates.surface_gate_checklist(
        qc, fid, orientation, water["watertight_tip"], deterministic_connectivity=True
    )
    print(f"\nsurface gate            {'PASS' if passed else 'FAIL'}")
    for r in reasons:
        print(f"  - {r}")
    if passed:
        failures.append(
            "surface gate PASSED on a spanwise-refined surface whose fidelity is "
            "unverified; the instrument-bug-6 guard is not working"
        )

    if failures:
        print("\nSELFTEST FAILED")
        for f in failures:
            print(f"  {f}")
        return 1
    print("\nSELFTEST OK — shared control reproduces the recorded Stage 02 numbers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./shared/verify.py =====

"""The verifier — SHARED CONTROL.

ADR-0011 section 4. Cell quality is not correctness. Before comparing strategies it
must be shown that each one produces the prescribed geometry and a closed,
consistently oriented surface. Migrated in substance from
`04_strategy_prototypes/verify_strategies.py`, generalised to verify any strategy's
blocks rather than a hard-coded list of four.

**Verify the verifier.** Five instrument bugs were found in Stage 02, each
reporting a false failure on a sound mesh, and a sixth reporting a false pass. Each
fix is preserved here with the failure it prevents, because the fixes look like
pedantry until you know what they cost:

1. Distance measured to sampled *points* rather than polyline *segments* floors the
   error at half the reference spacing — 0.0507% reported on an exact mesh.
   :func:`_point_to_polyline`.
2. An **open** reference contour excludes the blunt base, reporting the TE base
   block as 0.2516% off-surface, exactly half `te_thickness`. :func:`oml_fidelity`
   closes the loop.
3. Watertightness tested in the wrong direction — requiring every *cap* boundary
   node to lie on the OML edge — reports a cap's legitimate internal interfaces as
   holes. The correct condition is the other direction: every OML tip-edge node
   must be present in the cap. :func:`tip_cap_nodes`.
4. Tip-edge nodes taken from *every* OML block's outboard edge report a 0.58 m gap
   on a sound segmented mesh, where each interval has its own outboard edge.
   :func:`tip_edge_nodes` selects by spanwise position instead.
5. Determinism hashing block *dimensions* fails a compliant method: RUNBOOK section
   2.1 freezes the **connectivity** signature and explicitly permits "node
   positions, spacing and permitted counts [to] adapt to geometry".
   :func:`connectivity_signature`.
6. The fidelity check silently **skipped** spanwise-refined blocks — exactly the
   blocks whose interpolated columns sit off the loft — reporting a refined mesh as
   fidelity-perfect. It now records them as unverified, and
   `shared.gates.surface_gate_checklist` treats unverified as a failure.
7. **Found during the ADR-0011 migration, 2026-08-14.** The tip edge was taken from
   each OML block's *last j column*, which assumes that column is the outboard one.
   `orient_blocks_consistently` reverses the j index of any block it flips — seven
   of eight on `lhs7_00` — after which no block matched the tip station and the
   check raised `ValueError` rather than returning a result. Selection is now by
   spanwise **position**, which is instrument bug 4's own principle applied
   properly. :func:`tip_edge_nodes`.
"""

from __future__ import annotations

import numpy as np

from . import gates
from .ingestion import TE_THICKNESS_ABS_M, _map_sides_to_wing, section_loop_2d

NODE_DECIMALS = gates.NODE_DECIMALS


def tip_edge_nodes(blocks) -> np.ndarray:
    """OML nodes that actually lie on the tip station. See instrument bugs 4 and 7.

    **Instrument bug 7**, found by `shared/selftest.py` during the ADR-0011
    migration on 2026-08-14 and fixed here:

    The Stage 02 version took each OML block's `xyz[:, -1, :]` edge and kept it if
    its maximum y matched the tip station. That silently assumes the **last j
    column is the outboard one** — and `orient_blocks_consistently` reverses the j
    index of any block it flips. On `lhs7_00` it flips seven of eight blocks,
    including all three OML blocks, after which `xyz[:, -1, :]` is the ROOT edge,
    no block matches the tip station, and the check raised
    `ValueError: need at least one array to concatenate` instead of reporting a
    result. Any strategy whose blocks happen to be flipped would have been
    unverifiable rather than failed — which is worse, because it looks like a
    crash in the harness rather than a finding.

    The fix applies instrument bug 4's own principle properly: **select by
    spanwise position, not by index.** Every OML node at the tip station is
    collected, whatever the block's index orientation or blocking.
    """
    oml = [b for b in blocks if not b.name.startswith("tip")]
    if not oml:
        raise ValueError("no non-tip blocks; cannot locate the tip station")
    tip_y = max(float(b.xyz[:, :, 1].max()) for b in oml)
    tol = 10.0 ** (-NODE_DECIMALS)
    pts = [b.xyz.reshape(-1, 3)[b.xyz.reshape(-1, 3)[:, 1] >= tip_y - tol] for b in oml]
    pts = [p for p in pts if len(p)]
    if not pts:
        raise ValueError(
            f"no OML node lies within {tol} m of the tip station y={tip_y}; "
            "the tip station could not be located"
        )
    return np.unique(np.round(np.concatenate(pts, axis=0), NODE_DECIMALS), axis=0)


def tip_cap_nodes(blocks) -> set:
    """All nodes belonging to tip-cap blocks. See instrument bug 3."""
    out: set = set()
    for b in blocks:
        if not b.name.startswith("tip"):
            continue
        out |= {tuple(np.round(p, NODE_DECIMALS)) for p in b.xyz.reshape(-1, 3)}
    return out


def _point_to_polyline(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Distance from each point to the nearest SEGMENT of a polyline. Bug 1."""
    a = poly[:-1]
    b = poly[1:]
    ab = b - a
    l2 = np.einsum("ij,ij->i", ab, ab)
    l2[l2 == 0] = 1e-30
    out = np.empty(len(pts))
    for i, p in enumerate(pts):
        t = np.clip(np.einsum("ij,ij->i", p - a, ab) / l2, 0.0, 1.0)
        out[i] = float(np.min(np.linalg.norm(a + t[:, None] * ab - p, axis=1)))
    return out


def oml_fidelity(
    wing, blocks, te_thickness_abs_m: float | None = None, *,
    te_thickness_frac: float | None = None,
) -> dict:
    """Distance from OML nodes to the prescribed section contour. Bugs 2, 6 and 8.

    **Instrument bug 8**, found on 2026-08-14 while measuring S0 without spanwise
    refinement, and fixed here:

    The previous version decided whether a block was spanwise-refined by
    comparing its column COUNT to the station count, then assumed column ``j``
    was station ``j``. Both halves are wrong. A block can carry exactly as many
    columns as there are stations without any of them lying ON a station — S0's
    proportional spanwise allocation does this at ``spanwise_panels=1``, since it
    spends one budget across intervals of unequal length. The check then compared
    each column against an unrelated station and reported **835% of local chord**
    on a mesh whose station columns are in fact exact.

    Columns are now matched to stations by spanwise POSITION. Matched columns are
    measured; unmatched ones are reported as unverified rather than being
    silently skipped (bug 6) or silently mismeasured (bug 8).
    """
    # The reference contour must be opened EXACTLY as the mesh was, or the
    # measurement is against a different aircraft. `te_thickness_frac` exists only
    # so the Stage 02 prior art, which used a chord fraction, can still be checked
    # against its own reference.
    if te_thickness_frac is None and te_thickness_abs_m is None:
        te_thickness_abs_m = TE_THICKNESS_ABS_M
    xsecs = list(wing.xsecs)
    refs = []
    for idx, xsec in enumerate(xsecs):
        coords, _le = section_loop_2d(
            xsec, te_thickness=te_thickness_frac,
            te_thickness_abs_m=None if te_thickness_frac is not None else te_thickness_abs_m,
        )
        closed = np.vstack([coords, coords[0]])  # bug 2: the reference must be CLOSED
        refs.append(_map_sides_to_wing(wing, [[closed] for _ in xsecs])[0][:, idx, :])
    station_y = np.array([float(r[:, 1].mean()) for r in refs])

    # A column counts as ON the prescribed geometry when it actually lies on a
    # station contour, measured — not when its index or its column count says it
    # should. Two earlier rules both failed:
    #
    #   * column COUNT equals station count  -> assumes column j is station j.
    #     S0's proportional spanwise allocation breaks that and the check
    #     reported 835% of local chord on a mesh whose station columns are exact.
    #   * nearest station by mean y within half a station gap -> matches
    #     interpolated columns to whichever station they sit nearest and then
    #     measures them against it (10-18% of chord, all artefact). Tightening
    #     the tolerance to node precision then matched only 16 of 68 real station
    #     columns, because a BLOCK is a sub-arc of the section and its mean y is
    #     not the whole contour's mean y.
    #
    # So the test is the measurement itself: a column is verified when its
    # distance to a station contour is within the fidelity gate. The two nearest
    # stations by mean y are the only candidates worth evaluating.
    worst_abs = 0.0
    worst_frac = 0.0
    worst_block = None
    unverified: dict[str, int] = {}
    measured_columns = 0
    for b in blocks:
        if b.name.startswith("tip"):
            continue
        cols_y = b.xyz[:, :, 1].mean(axis=0)
        for j, y in enumerate(cols_y):
            order = np.argsort(np.abs(station_y - y))[:2]
            best_frac = None
            best_abs = 0.0
            for k in order:
                ref = refs[int(k)]
                chord = float(np.ptp(ref[:, 0]))
                d = float(_point_to_polyline(b.xyz[:, j, :], ref).max())
                frac = d / max(chord, 1e-12)
                if best_frac is None or frac < best_frac:
                    best_frac, best_abs = frac, d
            if best_frac is None or best_frac > gates.FIDELITY_FRAC_OF_LOCAL_CHORD:
                unverified[b.name] = unverified.get(b.name, 0) + 1
                continue
            measured_columns += 1
            if best_frac > worst_frac:
                worst_frac, worst_abs, worst_block = best_frac, best_abs, b.name

    return {
        "worst_abs_m": worst_abs,
        "worst_frac_of_local_chord": worst_frac,
        "worst_block": worst_block,
        "measured_station_columns": measured_columns,
        "unverified_columns_by_block": unverified,
        "skipped_spanwise_refined_blocks": sorted(unverified),
        "fidelity_unverified_for_refined_blocks": bool(unverified),
    }


def connectivity_signature(blocks) -> tuple:
    """The frozen signature: block names and families. NOT dimensions. Bug 5."""
    return tuple(sorted((b.name, b.family) for b in blocks))


def dimension_signature(blocks) -> tuple:
    """Block dimensions — REPORTED, never gated. RUNBOOK section 2.1."""
    return tuple(sorted((b.name, tuple(b.xyz.shape)) for b in blocks))


def watertight_tip(blocks) -> dict:
    """Every OML tip-edge node must be present in the tip cap. Bug 3."""
    cap = tip_cap_nodes(blocks)
    edge = tip_edge_nodes(blocks)
    edge_set = {tuple(np.round(p, NODE_DECIMALS)) for p in edge}
    missing = edge_set - cap
    ref_len = float(np.ptp(edge[:, 0]))
    if missing:
        cap_arr = np.array(sorted(cap))
        gap = max(
            float(np.min(np.linalg.norm(cap_arr - np.array(p), axis=1)))
            for p in list(missing)[:400]
        )
    else:
        gap = 0.0
    return {
        "watertight_tip": not missing,
        "oml_tip_edge_nodes": len(edge_set),
        "missing_from_cap": len(missing),
        "max_gap_to_oml_tip_edge_m": gap,
        "max_gap_as_frac_of_tip_chord": gap / max(ref_len, 1e-12),
    }


def verify_geometry(wing, blocks, *, te_thickness_abs_m: float | None = None) -> dict:
    """Every per-geometry surface check, in one dict. Determinism needs the set."""
    result = watertight_tip(blocks)
    result["oml_fidelity"] = oml_fidelity(wing, blocks, te_thickness_abs_m)
    result["all_finite"] = bool(all(np.isfinite(b.xyz).all() for b in blocks))
    result["block_count"] = len(blocks)
    result["connectivity_signature"] = connectivity_signature(blocks)
    result["dimension_signature"] = dimension_signature(blocks)
    result["families"] = sorted({b.family for b in blocks})
    return result


def verify_set(per_geometry: dict) -> dict:
    """Cross-geometry checks: determinism of connectivity, dimension variation.

    ``per_geometry`` maps geometry_id -> :func:`verify_geometry` output.
    """
    sigs = {tuple(v["connectivity_signature"]) for v in per_geometry.values()}
    dims = {tuple(v["dimension_signature"]) for v in per_geometry.values()}
    return {
        "deterministic_connectivity": len(sigs) == 1,
        "distinct_connectivity_signatures": len(sigs),
        "distinct_block_dimension_sets": len(dims),
        "dimensions_adapt_to_geometry": len(dims) > 1,
        "note": (
            "RUNBOOK section 2.1 freezes CONNECTIVITY; dimension variation is "
            "reported, not gated (instrument bug 5)."
        ),
    }


===== FILE: ./shared/verify_volume_qc.py =====

"""ADR-0014 section 3.4 — verify the in-house volume metric against pyHyp.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/shared/verify_volume_qc.py

S4's volume cannot be scored until `shared/volume_qc.py` agrees with pyHyp on
volumes pyHyp has already reported on. The comparison is run against **S1's**,
which passed 10/10.

What "agree" means here, and what it deliberately does not mean:

* **Validity must agree exactly.** If pyHyp says zero inverted cells and a positive
  minimum volume, the in-house route must say the same. A disagreement here means
  one of the two instruments is wrong and S4 waits.
* **Minimum quality is compared but not required to be equal.** pyHyp's `Quality`
  column and a corner scaled Jacobian are different definitions of the same idea;
  requiring them to match to three decimals would be requiring pyHyp's formula, not
  verifying ours. What is required is that they agree on the SIGN and stay within a
  factor that is recorded here rather than assumed — the sign is what the gate turns
  on, and a factor recorded once is a factor the final report can state.

The first run of this check found a real defect: the corner triple product was
ordered so that "positive" meant the opposite of what `signed_cell_volumes` means by
it, and every valid pyHyp volume scored -1.0. A unit-cube test had passed.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STUDIES = Path(__file__).resolve().parents[1]
REPO_ROOT = STUDIES.parents[1]
for _p in (str(REPO_ROOT / "src"), str(STUDIES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared import gates, volume_qc  # noqa: E402

S1_ROOT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies/S1_tip_first"
OUT = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/strategy_studies/S4_analytic_multiblock"

#: pyHyp's per-layer table. Columns: Lvl Time Its Its Bad Ratio Max Min Quality ...
#: `Min Quality` is column index 7 (0-based) on a data row.
_NUM = r"([\d.eE+-]+)"
_ROW = re.compile(
    r"^\s*\d+\s+[\d.]+\s+\d+\s+\d+\s+(\d+)\s+" + r"\s+".join([_NUM] * 4)
)


def pyhyp_min_quality(log: Path) -> tuple[float | None, bool]:
    """(worst `Min Quality` over completed layers, march_completed)."""
    text = log.read_text(errors="replace")
    worst = None
    for line in text.splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        q = float(m.group(5))
        worst = q if worst is None else min(worst, q)
    return worst, ("pyHyp done" in text)


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    # Each volume is ~60 MB and 2.3M cells. A sample spread over geometries and epsE
    # settles the question; reading all 125 does not settle it any harder.
    ap.add_argument("--sample", type=int, default=6)
    args = ap.parse_args()

    runs = sorted(S1_ROOT.rglob("wing_vol.cgns"))
    if not runs:
        print(f"no S1 volumes found under {S1_ROOT}")
        return 1
    if args.sample and len(runs) > args.sample:
        step = len(runs) / args.sample
        runs = [runs[int(i * step)] for i in range(args.sample)]

    rows = []
    print(f"{'run':46s} {'pyHypQ':>9s} {'inhouseQ':>10s} {'ratio':>7s} "
          f"{'inv':>4s} {'minVol':>11s} {'gate':>5s}")
    for cgns in runs:
        log = cgns.parent / "run_stdout.log"
        pq, done = (pyhyp_min_quality(log) if log.exists() else (None, False))
        if not done:
            continue  # only completed marches are comparable (instrument bug 10)
        rep = volume_qc.equivalence_against_pyhyp(cgns)
        ok, why = gates.volume_gate_checklist_direct(rep)
        iq = rep["min_scaled_quality"]
        ratio = (iq / pq) if (pq not in (None, 0.0)) else float("nan")
        label = "/".join(cgns.parts[-4:-1])
        rows.append(
            {
                "run": label, "pyhyp_min_quality": pq, "inhouse_min_scaled_quality": iq,
                "ratio": ratio, "inverted_cells": rep["inverted_cells"],
                "min_volume": rep["min_volume"], "total_cells": rep["total_cells"],
                "direct_gate": "PASS" if ok else "FAIL", "direct_gate_reasons": why,
            }
        )
        print(f"{label:46s} {pq:9.5f} {iq:10.5f} {ratio:7.3f} "
              f"{rep['inverted_cells']:4d} {rep['min_volume']:11.4e} "
              f"{('PASS' if ok else 'FAIL'):>5s}")

    if not rows:
        print("no COMPLETED S1 marches found to compare against")
        return 1

    agree_sign = all((r["pyhyp_min_quality"] > 0) == (r["inhouse_min_scaled_quality"] > 0)
                     for r in rows)
    agree_valid = all(r["inverted_cells"] == 0 and r["min_volume"] > 0 for r in rows)
    ratios = [r["ratio"] for r in rows]
    verdict = agree_sign and agree_valid

    print(f"\ncompared            : {len(rows)} completed S1 marches")
    print(f"sign agreement      : {agree_sign}")
    print(f"validity agreement  : {agree_valid} (pyHyp passed all of these)")
    print(f"quality ratio       : {min(ratios):.3f} to {max(ratios):.3f} "
          f"(in-house / pyHyp; different definitions, not required to be 1.0)")
    print(f"\nADR-0014 section 3.4: {'VERIFIED' if verdict else 'FAILED — S4 is blocked'}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "volume_qc_equivalence.json").write_text(
        json.dumps(
            {
                "adr": "ADR-0014-non-pyhyp-volume-gate.md",
                "schema": volume_qc.VOLUME_QC_SCHEMA,
                "verified": verdict,
                "sign_agreement": agree_sign,
                "validity_agreement": agree_valid,
                "quality_ratio_range": [min(ratios), max(ratios)],
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())


===== FILE: ./shared/volume_qc.py =====

"""In-house volume QC for a strategy that does not march — SHARED CONTROL.

ADR-0014. `shared/gates.py`'s volume checklist is phrased in terms of pyHyp's
report, and RUNBOOK section 6 S4 exempts S4 from pyHyp. This module supplies the
same five facts (ADR-0014 section 3.1, V1-V5) from the mesh itself.

**Two things this module deliberately does not do.**

1. It does **not** reimplement cell volume. `aeris.cfd.meshing.volume_audit.
   signed_cell_volumes` is the repository's authority for hexahedral volume and it
   is imported, not copied. Instrument bug 9 was exactly this mistake — a quality
   number recomputed a second way for one caller's convenience reported 7 folded
   cells and a minimum of -0.132 on a mesh that was fine.
2. It does **not** invent a threshold. Every number it is compared against comes
   from ADR-0008 via `gates.py`.

What it *does* add is the hexahedral scaled Jacobian, which the repository did not
have — `aeris.cfd.meshing.quality.scaled_jacobian` is for quads. It is defined here
in the same *kind* as the quad version so the two are read the same way:

    At each of a cell's 8 corners take the three incident edge vectors, each
    oriented along the positive element direction, and form
    ``sign * det(e_i, e_j, e_k) / (|e_i| |e_j| |e_k|)`` where ``sign`` is
    ``(-1)**(a+b+c)`` for the corner at local coordinates (a, b, c). The cell's
    value is the minimum over its 8 corners; a perfect cube scores +1.0 at every
    corner, and a folded cell goes negative.

Handedness is resolved **once per mesh**, from the sign of the total signed volume,
not per block — the same rule `qc.orient_blocks_consistently` applies to surfaces.
A mesh built left-handed throughout is a labelling convention, not a folded mesh;
a mesh with both signs present has real inverted cells and is reported as such.

Verified against pyHyp before use — see :func:`equivalence_against_pyhyp` and
ADR-0014 section 3.4.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from aeris.cfd.meshing.volume_audit import signed_cell_volumes  # noqa: E402

Array = np.ndarray

VOLUME_QC_SCHEMA = "aeris.mesh_study.direct_volume_qc.v1"


def hex_scaled_jacobian(nodes: Array, *, orientation: float = 1.0) -> Array:
    """Per-cell minimum scaled corner Jacobian for a ``(nk, nj, ni, 3)`` block.

    Returns shape ``(nk-1, nj-1, ni-1)``. ``orientation`` is +1 or -1 and is the
    mesh-wide handedness resolved by :func:`volume_report`; it is not a per-block
    free choice, because letting each block pick its own sign would report a folded
    block as perfect.
    """
    nodes = np.asarray(nodes, dtype=float)
    if nodes.ndim != 4 or nodes.shape[-1] != 3:
        raise ValueError(f"expected a (nk, nj, ni, 3) block, got {nodes.shape}")
    if min(nodes.shape[:3]) < 2:
        raise ValueError(f"block has no cells: {nodes.shape}")

    def corner(a: int, b: int, c: int) -> Array:
        sk = slice(1, None) if a else slice(None, -1)
        sj = slice(1, None) if b else slice(None, -1)
        si = slice(1, None) if c else slice(None, -1)
        return nodes[sk, sj, si]

    minimum: Array | None = None
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                origin = corner(a, b, c)
                e_k = corner(1 - a, b, c) - origin  # along axis 0
                e_j = corner(a, 1 - b, c) - origin  # along axis 1
                e_i = corner(a, b, 1 - c) - origin  # along axis 2
                # The triple product is ordered (axis 2, axis 1, axis 0) so that
                # "positive" here means the same thing as "positive" in
                # `signed_cell_volumes`. The opposite order passes a unit-cube test
                # just as convincingly and then scores every valid pyHyp volume at
                # -1.0; that is how this ordering was fixed (ADR-0014 section 3.4).
                det = np.einsum("...i,...i->...", e_i, np.cross(e_j, e_k))
                lengths = (
                    np.linalg.norm(e_k, axis=-1)
                    * np.linalg.norm(e_j, axis=-1)
                    * np.linalg.norm(e_i, axis=-1)
                )
                denom = np.where(lengths > 0.0, lengths, np.inf)
                value = ((-1.0) ** (a + b + c)) * orientation * det / denom
                minimum = value if minimum is None else np.minimum(minimum, value)
    if minimum is None:  # pragma: no cover - loops above are fixed and non-empty
        raise RuntimeError("no hexahedral corners were evaluated")
    return minimum


def _worst_cell_diagnostic(nodes: Array, index: tuple[int, int, int]) -> dict:
    """Return local geometry for one cell without retaining full quality arrays."""
    k, j, i = index
    edges = []
    for b in (0, 1):
        for c in (0, 1):
            edges.append(nodes[k + 1, j + b, i + c] - nodes[k, j + b, i + c])
    for a in (0, 1):
        for c in (0, 1):
            edges.append(nodes[k + a, j + 1, i + c] - nodes[k + a, j, i + c])
    for a in (0, 1):
        for b in (0, 1):
            edges.append(nodes[k + a, j + b, i + 1] - nodes[k + a, j + b, i])
    lengths = np.linalg.norm(np.asarray(edges), axis=1)
    lower_face = np.mean(nodes[k, j : j + 2, i : i + 2], axis=(0, 1))
    wall_face = np.mean(nodes[0, j : j + 2, i : i + 2], axis=(0, 1))
    return {
        "cell_index_kji": [k, j, i],
        "wall_layer_index": k,
        "wall_distance_m": float(np.linalg.norm(lower_face - wall_face)),
        "min_edge_length_m": float(lengths.min()),
        "max_edge_length_m": float(lengths.max()),
        "edge_length_ratio": float(lengths.max() / lengths.min()),
        "cell_center_xyz_m": np.mean(
            nodes[k : k + 2, j : j + 2, i : i + 2], axis=(0, 1, 2)
        ).tolist(),
    }


def volume_report(blocks: dict[str, Array]) -> dict:
    """ADR-0014 section 3.1 V1-V5 for a set of ``{name: (nk, nj, ni, 3)}`` blocks.

    ``blocks`` is whatever the strategy built; the same dict shape
    `aeris.cfd.meshing.volume_audit.read_volume_blocks` returns for a pyHyp CGNS, so
    the two routes can be pointed at the same data (ADR-0014 section 3.4).
    """
    if not blocks:
        return {
            "schema": VOLUME_QC_SCHEMA,
            "route": "direct",
            "generation_completed": False,
            "reason": "no blocks were produced",
        }

    # V1 — every block finite and dimensioned. Checked before anything is measured,
    # because a NaN silently makes every comparison below False rather than True.
    non_finite = {
        name: int(np.count_nonzero(~np.isfinite(np.asarray(b, dtype=float))))
        for name, b in blocks.items()
    }
    total_non_finite = sum(non_finite.values())
    degenerate_shapes = {
        name: tuple(np.asarray(b).shape)
        for name, b in blocks.items()
        if np.asarray(b).ndim != 4 or np.asarray(b).shape[-1] != 3
        or min(np.asarray(b).shape[:3]) < 2
    }

    if total_non_finite or degenerate_shapes:
        return {
            "schema": VOLUME_QC_SCHEMA,
            "route": "direct",
            "generation_completed": False,
            "block_count": len(blocks),
            "non_finite_nodes": total_non_finite,
            "non_finite_by_block": {k: v for k, v in non_finite.items() if v},
            "degenerate_block_shapes": degenerate_shapes,
        }

    volumes = {name: signed_cell_volumes(np.asarray(b, dtype=float)) for name, b in blocks.items()}
    total_signed = float(sum(float(v.sum()) for v in volumes.values()))
    orientation = -1.0 if total_signed < 0.0 else 1.0

    per_block = {}
    jac_min = np.inf
    jac_sum = 0.0
    jac_n = 0
    jac_ge_030 = 0
    jac_lt_010 = 0
    jac_lt_015 = 0
    worst_cell: dict | None = None
    for name, b in blocks.items():
        nodes = np.asarray(b, dtype=float)
        vol = orientation * volumes[name]
        jac = hex_scaled_jacobian(nodes, orientation=orientation)
        minimum_index = tuple(int(value) for value in np.unravel_index(np.argmin(jac), jac.shape))
        diagnostic = _worst_cell_diagnostic(nodes, minimum_index)
        diagnostic["block"] = name
        diagnostic["min_scaled_quality"] = float(jac[minimum_index])
        if (
            worst_cell is None
            or diagnostic["min_scaled_quality"] < worst_cell["min_scaled_quality"]
        ):
            worst_cell = diagnostic
        jac_min = min(jac_min, float(jac.min()))
        jac_sum += float(jac.sum())
        jac_n += int(jac.size)
        jac_ge_030 += int(np.count_nonzero(jac >= 0.30))
        jac_lt_010 += int(np.count_nonzero(jac < 0.10))
        jac_lt_015 += int(np.count_nonzero(jac < 0.15))
        per_block[name] = {
            "shape": tuple(int(s) for s in np.asarray(b).shape[:3]),
            "cells": int(vol.size),
            "min_volume": float(vol.min()),
            "min_scaled_quality": float(jac.min()),
            "mean_scaled_quality": float(jac.mean()),
            "inverted_cells": int(np.count_nonzero(vol <= 0.0)),
            "low_quality_cells": int(np.count_nonzero(jac <= 0.0)),
            "cells_below_0_10": int(np.count_nonzero(jac < 0.10)),
            "cells_below_0_15": int(np.count_nonzero(jac < 0.15)),
            "worst_cell": diagnostic,
        }

    cells = sum(v["cells"] for v in per_block.values())
    return {
        "schema": VOLUME_QC_SCHEMA,
        "route": "direct",
        "generation_completed": True,
        "orientation": orientation,
        "block_count": len(blocks),
        "total_cells": cells,
        "min_volume": min(v["min_volume"] for v in per_block.values()),
        "inverted_cells": sum(v["inverted_cells"] for v in per_block.values()),
        "min_scaled_quality": jac_min,
        "mean_scaled_quality": jac_sum / jac_n,
        # ADR-0014 V5: the direct route has no marching layers, so the equivalent
        # "no failing region" test is per BLOCK.
        "low_quality_blocks": [
            n for n, v in per_block.items() if v["min_scaled_quality"] <= 0.0
        ],
        "fraction_at_or_above_0_30": jac_ge_030 / jac_n,
        "cells_below_0_10": jac_lt_010,
        "cells_below_0_15": jac_lt_015,
        "worst_cell": worst_cell,
        "per_block": per_block,
    }


def equivalence_against_pyhyp(cgns_path: Path) -> dict:
    """ADR-0014 section 3.4 — run the in-house metric on a volume pyHyp scored.

    S4's volume cannot be scored until this agrees with pyHyp on a mesh pyHyp
    already passed. An unverified instrument is how Stage 02 produced four numbers
    that had to be withdrawn.
    """
    from aeris.cfd.meshing.volume_audit import read_volume_blocks

    blocks = read_volume_blocks(Path(cgns_path))
    report = volume_report(blocks)
    report["source_cgns"] = str(cgns_path)
    return report


===== FILE: ./VALIDATION_PROGRAMME.md =====

# Joint validation programme for S6 and S7

One programme covering both meshing strategies, run as a paired comparison: the
same geometries, the same operating condition, the same acceptance gates, so any
difference in the results is a difference between the pipelines and not between
the experiments.

It supersedes nothing.  S6's `ROADMAP.md` already carries a reduced gate for a
100-case campaign and S7's carries its own ordering; this states the shared
sequence they both feed, and where the two differ in how far they still are from
it.

## Decisions to take before Stage 0, not during

These are cheap now and expensive to retrofit, because changing any of them
invalidates every result recorded before the change.

- **Operating condition.**  One condition, fixed for Stages 0 to 3.  Record
  altitude, velocity, angle of attack, reference temperature and the resulting
  Reynolds and Mach numbers in the policy, not in a script.
- **Moment reference point.**  Cm is meaningless without it and cannot be
  compared across designs unless the convention is fixed.  Declare the point and
  whether it moves with the geometry (for example, quarter-MAC) or is absolute.
- **Reference area and length.**  Both pipelines must use the same definitions or
  their coefficients are not comparable.  S7's surface report already records
  `area_m2`, `area_yz_m2`, `mean_aerodynamic_chord_m` and both span conventions;
  pick which of them is the reference and say so once.
- **The resolution ladder.**  Name the coarse, medium and fine levels explicitly.
  Stage 1 must run at the *same* coarse level that Stage 2 will use as its coarse
  leg, or the runs cannot be reused and Stage 2 costs 30 runs instead of 20.

## Stage 0 - one accepted CFD case per pipeline

The gate is the same for both: a production-resolution mesh, a converged solve,
and wall y+ inside the frozen limits, with nothing repaired by hand.

The two pipelines are **not** equally close to it.

- **S7** has five production-resolution meshes and a verified solver chain, and
  y+ passes at coarse (p95 0.5573, max 0.8744).  What is missing is convergence:
  the residual limit-cycles at 1.658 orders against a six-order gate while the
  forces settle.  Multigrid reached 3.250 orders and tightened the CD spread by a
  factor of 770; confirming it is the whole of S7's Stage 0.
- **S6** has 100/100 at *development* resolution and **zero production-resolution
  meshes**.  Its Stage 0 therefore starts one step earlier: produce production
  meshes, then run ADflow.  This is the larger of the two gaps and should start
  first because it is longer, not because it is harder.

Do not begin Stage 1 on a pipeline until its Stage 0 case is accepted.  Twenty
runs against an unresolved defect produce twenty instances of the same defect.

**Budget the programme only after Stage 0.**  Cost per CFD is currently unknown
for both pipelines, so any total run count quoted now is a guess.  One converged
case gives the wall time, the memory ceiling and the retry rate that make the rest
of the estimate real.

## Stage 1 - twenty-case geometric generalisation, per pipeline

Fixed condition, varying geometry.  The question is narrow and worth keeping
narrow: *does the automation handle very different BWB geometries without
intervention?*

Twenty geometries, chosen rather than drawn at random:

- five geometric extremes, taken from the corners of the sampled ranges;
- ten maximin-spread designs covering the interior;
- five drawn at random and never inspected beforehand.

The same twenty for both pipelines.  Record per case: geometry id, planform
(twist, dihedral, sweep - now in S7's surface report), mesh outcome and quality,
attempts and failures, convergence history, y+, CL, CD, Cm, wall time and peak
memory.

Target: 20/20 meshes accepted, at least 19/20 converged unattended, y+ passing,
zero invalid cells, no manual repair.

**Wording, for the eventual paper.**  Twenty cases are development evidence of
robustness.  They do not prove generalisation over the design space, and the text
should not say they do.

### What Stage 1 cannot cover

Root dihedral is pinned to zero by the `enforce_flat_root_panel` invariant, so no
case at any stage exercises a non-flat root panel.  State this as a scope limit
rather than discovering it in review.

## Stage 2 - mesh independence on five geometries

Five of the twenty, chosen for difficulty and spread rather than convenience: the
nominal design, two opposing geometric extremes, the hardest case to mesh in Stage
1, and one representative high-loading design.

Each at coarse, medium and fine.  If the level pinning above held, the coarse legs
already exist and this costs ten new runs per pipeline rather than fifteen.

Report Richardson extrapolation and GCI on CL, CD and Cm, with the observed order
of convergence stated - not assumed to be the formal order.  Where the observed
order is far from formal, say so; that is a finding about the discretisation, not
an inconvenience to be smoothed over.

## Stage 3 - fix the production configuration

This is the stage the preregistration exists to protect, because it is where
settings are chosen *after* seeing results.

Permitted: efficiency and robustness changes - resolution where Stage 2 shows it
is unnecessary, solver settings, retry logic, wall spacing chosen to hit the
existing y+ limit.

Not permitted: moving an acceptance threshold so that a case which failed now
passes.  If a gate is genuinely wrong, it is re-derived in a superseding ADR that
carries the measurement showing the old value was mis-derived, and the ADR is
written before the re-run, not after.  `POLICY.yaml` carries
`no_gate_weakening: true` for exactly this.

Then about five dress-rehearsal runs per pipeline under the final settings.

## Stage 4 - freeze

Freeze together, and record the hashes: geometry definitions, mesh settings, wall
spacing, refinement, solver, turbulence model, convergence criteria, retry logic,
quality gates and the output schema.

Only then the hold-out.  `round_c_lhs10_seed42` has never been constructed,
meshed, solved or inspected, and must stay that way until the freeze is recorded.
A hold-out looked at early is not a hold-out.

## Stage 5 - the paired production campaign

At least 100 CFD per pipeline, the same geometries and condition for both, giving
a paired table where each row is one geometry under both strategies.

The comparison is the point, and it is more interesting than the aerodynamics
alone: where structured and unstructured disagree and by how much, cost per case,
unattended success rate, convergence robustness, mesh quality, and which regions
of the design space are hard for which pipeline and why.

Operating conditions may expand here.  Not before - varying angle of attack during
Stage 1 turns a twenty-case test into a hundred-case one and answers a question
nobody asked yet.

# Desktop execution - step by step

This section is written to be handed to a fresh Claude Code session on the
desktop.  It assumes nothing from any earlier conversation.

## Step 1 - get the code

    cd /path/to/v.0.1_Project
    git checkout main
    git pull

Everything is on `main`.  There are no other branches to worry about.

## Step 2 - open Claude Code and paste this as the first message

    Read AERIS_MESH_STUDY/04_strategy_studies/VALIDATION_PROGRAMME.md and
    AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/HANDOFF.md,
    follow the HANDOFF reload order, then execute the S7 Stage 0 work in
    RUNBOOK.md. I am on the desktop, heavy runs are allowed here.
    Report progress with run_report.py and push it.

## Step 3 - check the machine before running anything

    free -g
    df -h .
    nproc

S7 needs roughly **3 GB per MPI rank**, because every rank reads the whole mesh
before partitioning.  The rule is `workers x ranks x 3 GB` must fit in RAM with
headroom.  Eight ranks were OOM-killed on a 16 GiB machine; two were stable.  On
32 GiB use no more than six ranks total.  If `free -g` shows less than 8 GiB
available, the campaign will refuse to start - that is the floor working, not a
bug, and it must not be lowered.

## Step 4 - S7 Stage 0, the multigrid confirmation

This is the single blocker on every S7 accuracy claim.  Full detail is in
`S7_unstructured_gmsh_su2/RUNBOOK.md` under "Confirm multigrid".

    export PATH="$PWD/AERIS_MESH_STUDY/tools/su2_8.5.0/bin:$PATH"
    export SU2_RUN="$PWD/AERIS_MESH_STUDY/tools/su2_8.5.0/bin"
    .venv/bin/python \
      AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/convergence_matrix.py \
      /path/to/coarse_mesh.su2  6000  2  3  round-two

Arguments in order: mesh, iterations, ranks per variant, concurrent variants, and
any fifth argument to select the three multigrid variants instead of all six.

If `AERIS_MESH_STUDY/tools/su2_8.5.0` is missing on the desktop, SU2 8.5.0 is a
gitignored download rather than lost work; re-fetch the pinned release before
running.

Two outcomes, both decisive.  If a variant reaches six orders, adopt it in a
superseding ADR carrying the measurements.  If none does while CD stays flat, the
residual gate was mis-derived and is re-derived - in an ADR, before the re-run.
Neither outcome is "lower the gate until it passes".

## Step 5 - report progress and push it back

Run this at any time, including while a campaign is still going.  It reports
whatever has landed so far.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/run_report.py \
      <artifacts_root> --name s7_stage0_multigrid --push

It writes a small Markdown and JSON pair into
`AERIS_MESH_STUDY/04_strategy_studies/RUN_LOG/` and, with `--push`, commits and
pushes **only those two files**.  It never touches the artifacts and never
commits mesh data.

This exists because the artifact trees are large and get wiped between campaigns.
A run recorded only there is a run nobody can evaluate later.

Then, back on the laptop:

    git pull

and the reports are there to read.

## Step 6 - what to run after Stage 0 passes

In order, and not before Stage 0 is accepted:

1. the remaining 95 coarse meshes - about 16 hours sequential, four hours split
   four ways, see `RUNBOOK.md`;
2. a converged coarse CFD case, which is what actually earns
   `production_y_plus_passed`;
3. S6 production-resolution meshes, which is S6's Stage 0 and the longer of the
   two gaps;
4. Stage 1, the twenty-case generalisation test, once **both** pipelines have one
   accepted case.

## Rules that hold regardless of what the session decides

- The hold-out `round_c_lhs10_seed42` is forbidden: never constructed, meshed,
  solved, inspected, or worked around.  It stays untouched until the Stage 4
  freeze is recorded.
- No acceptance threshold moves to rescue a failing case.  `POLICY.yaml` carries
  `no_gate_weakening: true`.  A gate that is genuinely wrong is re-derived in a
  superseding ADR that states the measurement showing the old value was wrong,
  written before the re-run.
- Everything lives under the project tree.  Nothing in `/tmp`, nothing in a
  scratchpad.
- Findings go in tracked files, because `data/` and the artifact trees are wiped.
- Relocate3D must never be used as a Gmsh optimiser; it corrupts the boundary
  layer.  `HANDOFF.md` carries the rest of these invariants.


## Sequence

    Stage 0   one accepted CFD each      S6 needs production meshes first
    Stage 1   20 + 20, fixed condition   geometric generalisation
    Stage 2   5 geometries x 3 levels    mesh independence
    Stage 3   settings fixed + ~5 each   superseding ADR for any gate change
    Stage 4   freeze, then hold-out      hashes recorded
    Stage 5   100 + 100, paired          comparison campaign

Run counts beyond Stage 1 are provisional until Stage 0 supplies a measured cost
per case.
