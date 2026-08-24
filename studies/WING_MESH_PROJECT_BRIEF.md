# AERIS Wing Surface Mesh — State of Play and Project Plan

**Context brief for external discussion. Self-contained — no repo access needed.**

Date: 2026-08-11
Project: PhD on BWB (blended wing body) UAVs — automated mesh generation for
design-space exploration (DSE).

---

## 0. TL;DR

The goal is a mesh policy that takes any wing produced by a 20-variable BWB
config and generates a valid CFD mesh unattended, across hundreds of designs,
with failures detected mechanically rather than by eye.

**This is roughly 70% built already.** The surface mesher, quality metrics,
5-level refinement family, failure-audit tooling and a 50-geometry robustness
result all exist. Sixteen empirical "laws" have been established and written
down. What has *not* happened is the volume-march validation of the current
recipe, the 8 option sweeps that would generalize the laws across the design
space, and the grid-convergence study.

The single most important open item: **the shipped volume-march smoothing
default (`epsE=6.0`) is known to *cause* the main failure mode**, and the fix
(`epsE=3.0`) has been demonstrated but never rolled into the family presets.
Everything downstream is blocked on that.

---

## 1. How a wing is defined

One canonical config file drives everything. The wing is **not** a free-form
surface — it is a 4-station lofted half-wing, mirrored.

| Station | b0 (root) | b1 | b2 | b3 (tip) |
|---|---|---|---|---|
| airfoil | mh91 | mh91 | e374 | nlf1015 |

**Build chain:**

1. **2D planform** (x–y only) — the leading edge is built by marching span
   segments with per-segment sweep (`dx = b / tan(sweep)`), then fitting a
   B-spline through the LE control points, split inboard/outboard at a
   `split_ratio`. Chords are set at each of the 4 stations.
2. **3D sections** — twist and dihedral applied per station.
3. **Loft** — pyGeo (the master representation, a smooth MACH-Aero loft)
   and/or AeroSandbox. Both backends read the same config.

### The 20 design variables

- **Planform (10):** root chord `c1_m`; chord ratios at b1/b2/b3
  (`c2/c3/c4_ratio`); semi-span `b_total_m`; outer-panel fraction `b3_ratio`;
  spline split `split_ratio`; three LE sweeps `sw1/sw2/sw3_deg`
- **Sections (7):** four twists `twist_b0..b3`; three dihedrals
  `dihedral_b1..b3` (b1 pinned to 0 — flat-root-panel invariant)
- **Elevon (3):** `elevon_start_frac`, `elevon_end_frac`, `elevon_hinge_frac`

Every variable is declared as a `{min, max}` range, so **the config file is the
DoE design space**. Sampling it with a fixed seed gives one deterministic
baseline geometry.

Design space scale: small BWB ISR UAV, AR ~4–7, full span 1.5–2.5 m,
root chord 0.70–1.10 m, Re ~1e6 at root down to ~1.2e5 at tip.

---

## 2. The mesh pipeline

```
bwb.yaml (20 DVs)
      ↓
   pyGeo loft  ──────────────► master geometry (smooth, CST-fitted sections)
      ↓
   surface mesher  ─────────► structured multiblock surface (cap4 topology)
      ↓ [surface QC gates]
   pyHyp  ───────────────────► hyperbolic march → 3D volume mesh (CGNS)
      ↓ [volume audit]
   ADflow (RANS/SA)  ───────► forces, convergence
```

**Important clarification:** pyGeo is *geometry parameterization* (FFD,
DVGeometry, DVConstraints) — it is **not** the volume mesher. The volume mesh
comes from **pyHyp**, which extrudes a structured surface mesh outward
hyperbolically. This determines what the surface mesh must satisfy: watertight,
consistent outward normals, matched block connectivity, planar symmetry plane,
and smooth spacing gradients along the marching front.

A second, parallel unstructured family exists (gmsh → SU2), cell-count-matched
to the structured levels so "structured L2 vs unstructured L2" is a fair
comparison.

---

## 3. What already exists (code)

| Module | Lines | Purpose |
|---|---|---|
| `mesh/surface.py` | 2,366 | Structured surface mesher — topologies, TFI/Coons patches, tip caps, QC, writers (PLOT3D/CGNS/VTK/NPZ) |
| `mesh/pyhyp_runner.py` | 386 | pyHyp volume march driver (in-process + subprocess) |
| `mesh/fidelity.py` | 365 | 5-level ladder shared by both families; GCI, Richardson, observed order |
| `mesh/topologies.py` | 128 | Registry: `mid4`, `split8`, `cap4`, `cap4_cgrid_face` |
| `mesh/presets.py` | 112 | Named family presets + scaling laws |
| `cfd/meshing/quality.py` | — | Structured metrics: shape, equiangle skewness, aspect ratio, growth |
| `cfd/meshing/quality_unstructured.py` | — | Tet/poly metrics: scaled Jacobian, min dihedral, volume, gates |
| `cfd/meshing/volume_audit.py` | — | Recomputes signed cell volumes from written CGNS; localizes and classifies inversion |

Plus CLI commands: `aeris cfd campaign mesh-robustness`, `campaign remarch`,
`campaign surface-strategy`, `cfd prune`, `cfd run`, `mesh pyhyp`.

**Environment note:** `pygeo`, `pyspline`, `cgnsutilities` and `gmsh` are
importable in the main venv. `pyhyp`, `idwarp` and `adflow` require the
separate mach-aero conda environment.

---

## 4. Quality metrics and acceptance limits

These were audited against their published sources in July 2026 and **four
errors were found and corrected**. This matters — the earlier numbers were
comparatively valid but mislabelled.

### Corrected targets (surface)

| Metric | Target | Source |
|---|---|---|
| `min_shape_metric` | **> 0.20** | Verdict quad *Shape*, `2\|e1×e2\|/(\|e1\|²+\|e2\|²)` |
| `max_equiangle_skewness` | **< 0.75** | Fluent bands: ≤0.25 excellent, ≤0.5 good, ≤0.75 fair, ≤0.9 poor, >0.9 degenerate |
| `max_aspect_ratio` | **< 100** | — |
| `max_growth_ratio` | **< 1.50** | surface-*tangential* bound |
| `max_adjacent_normal_angle_deg` | reported only, **not a target** | — |

### The four metric corrections

1. **The QC gate was misnamed.** What the code called "scaled corner Jacobian"
   is actually Verdict's quad **Shape** metric. Shape ≤ scaled Jacobian always
   (by AM–GM), so Shape penalises aspect ratio *as well as* angle. The ">0.2"
   guidance is published for the scaled Jacobian — applied to Shape it is a
   **stricter** bar. So the meshes were held to a higher standard than
   advertised, not a lower one.

2. **Two "independent" targets were one measurement.** For a quad,
   `scaled_jacobian == cos(90 × equiangle_skewness)` — verified to max absolute
   error **1.6e-15 over 30,608 cells**. Scoring both counted one quantity
   twice and made it arithmetically impossible for one to pass while the other
   failed. Scores are now out of 4, not 5.

3. **One threshold was invented.** `max_adjacent_normal_angle_deg < 40` had no
   source. It measures curvature *resolution*, not cell quality, and a blunt
   trailing edge must turn ~180° across its base whatever the mesh does. Now a
   diagnostic, never a target.

4. **Growth ratio 1.2 was a wall-normal bound applied to a tangential grid.**
   The whole OML runs 1.26–1.41 — a floor across all four chord blocks, which
   is the signature of a *distribution property*, not a defect. 1.2 is a
   boundary-layer smoothness bound belonging to the pyHyp march. The
   surface-tangential target is 1.50. With this correction every family level
   scores **4/4 on the OML**.

### Volume / campaign criteria (C1–C8)

Benchmarked to ASME V&V 20, the AIAA Drag Prediction Workshop gridding
guidelines, and NATO AVT-366:

| # | Criterion | Target | Status |
|---|---|---|---|
| C1 | Unattended robustness | ≥98% success over ≥100 geometries, zero intervention, every failure machine-classified | ✗ |
| C2 | Topology consistency | One topology for the whole campaign and family | ◐ |
| C3 | True refinement family | ≥3 levels, all three index directions, r ≈ 1.4–1.5 | ✓ (surface) |
| C4 | Quantified numerical uncertainty | Observed order ≈ formal (~2) on CL/CD/Cm; GCI on finest pair | ✗ |
| C5 | Solver-verified quality gates | y+ ≤ 1 verified *post-solve*; near-wall growth ≤ 1.25; all-positive volumes | ◐ |
| C6 | Solver acceptance | ADflow converges ≥5–6 orders on every level, no per-case tuning | ◐ |
| C7 | Provenance | Config hash, code version, seed, parameter echo, QC report per mesh | ✓ |
| C8 | Mesh noise below design signal | Level-to-level scatter < the design deltas the surrogate must learn | ✗ |

C8 is the DSE-specific criterion that single-case V&V ignores, and it is the
one that actually decides whether the surrogate learns physics or mesh noise.

---

## 5. The 16 established laws

All measured, all traceable to raw reports. This is the accumulated knowledge
that a new mesh attempt should draw on.

**On scoring:**
- **L1** — Score the OML and the tip cap **separately**. Whole-mesh extrema are
  meaningless: the tip collar's near-degenerate skewness (0.91–0.98) swamps
  every aggregate, so a strategy that genuinely improves the wing surface
  scores identically to one that does nothing.
- **L2** — The wing surface and tip cap are **independent**. Every tip
  parameter left the OML numbers identical to four decimals. They can be tuned
  separately without interaction.

**On resolution:**
- **L3** — Spanwise resolution is the dominant OML lever and it is monotone.
  Panels 8→32: shape 0.076→0.296, AR 25.0→6.4.
- **L4** — `tip_radial_points` is the dominant tip lever, also monotone.
  5→17: tip shape 0.016→0.060, tip AR 75.2→26.8.
- **L11** — **Spanwise panels must be allocated by segment LENGTH, not per
  section.** The growth ratio sat frozen at 1.508 across ~90 strategies. Cause:
  equal panels per section on unequally-spaced sections gave 4.44 mm cells
  inboard and 6.67 mm outboard — and 6.67/4.44 = **1.50**, exactly the frozen
  number. Proportional allocation drops the spanwise size ratio to 1.016 and
  frees resolution: 16 proportional panels beat 24 uniform (shape 0.426 vs
  0.259, 31% fewer cells).
- **L16** — **A mesh family must scale its cap resolution too.**
  `cap_wrap_points` fixed at 17 while `points_per_side` scaled 25→97 made OML
  aspect ratio degrade 3.5→8.1. Rule:
  `cap_wrap_points ≈ points_per_side × cap_wrap_x / (0.5 − cap_wrap_x)`.
  Same for `tip_radial_points` (fixed at 9 → tip AR ran 9.9→32.1). This
  overturns the older "the cap does not coarsen with the family" policy: that
  policy is right for the cap's *geometry* and wrong for its *resolution*.

**On blocking:**
- **L6** — The trailing edge is a genuine trade-off, not a tuning bug. Two
  levers act in opposite directions: `split_x_fore` 0.30–0.35 gives the best
  cell shape but pushes the TE normal rotation to 136–141°; `cluster_center`
  softens the turn to 88–103° but costs shape and aspect ratio.
- **L7** — **Tip quality cannot be fixed at the tip; it is set by the OML
  blocking.** The cap4 cap is only good when the OML hands it *unequal* side
  counts (49 chord × 17 wrap), giving an anisotropic rectangle matching a
  slender airfoil. Equal counts degenerate it to a square patch.
- **L8** — `cap_wrap_x` is a mid-chord **seam** control, not a crown band.
  Widening it improves tip and OML together, monotonically, until it doesn't.
  **0.15 is the optimum** (OML shape peaks 0.218 at 0.10–0.15, tip shape jumps
  to 0.115 at 0.15). The old 0.01–0.15 validation ceiling assumed the wrong
  meaning and was raised to 0.45.
- **L5** — Two tip options are dead ends: `tip_conformal_ring=true` is
  degenerate (skew 1.000, fails QC); `tip_dome_scale` moves skew by 0.006.
- **L13** — **The collar is the mitigation, not the villain.** Closing the tip
  with one transfinite patch (no radial family) was tested: aspect ratio
  improved to 7.2 — the best measured — but skewness went fully degenerate at
  0.999 and shape collapsed 100×. The collar earns its place by *spreading* the
  loop-to-rectangle mismatch around a ring rather than dumping it on four
  corners. This rules out "simplify the tip topology" with evidence.

**On the trailing edge:**
- **L9** — TE thickness **0.5% chord**, on three independent grounds: (a) real
  transport wings carry 0.2–0.5%c and DPW geometries are blunt at this order;
  (b) at this aircraft's Re, the TE boundary layer is 2.3–3.6% of chord, so a
  0.5% base sits at h/δ = 0.14–0.21 — buried inside the BL, where base drag is
  cheap. *The low Reynolds number of a small BWB UAV is what makes this
  affordable*; a transport wing at Re 4e7 has δ ~0.6%c and the same base would
  be genuinely costly. (c) 0.5%c is 8.0 mm at root and 1.0 mm at tip — about
  the thinnest edge that can be built. 2% chord was tested and rejected: it
  gave the best TE-angle metric, which is exactly why it is the wrong objective
  — it optimises the mesh, not the aircraft.
- **L10** — A resolved TE base needs an absolute floor, not a fixed count. A
  constant point count across a base whose physical size varies 8× produces
  0.24 mm slivers outboard. `te_base_points` was implemented, measured, and
  **rejected** — it degrades two *scored* metrics (growth 1.41→2.96, shape
  0.49→0.06) to fix a *diagnostic*. But the absolute floor *alone* is a genuine
  tip-skew lever: an 8 mm floor drops tip skew 0.902→0.841 and eases the TE
  turn 140°→129°, with the OML untouched.

**On the design space:**
- **L12** — **Tip skewness is set by the outer loop, and smoothing cannot reach
  it.** The centre patch is excellent (skew 0.085); the damage is entirely in
  the ring/collar blocks — corner angles 7.7°, 171.9°, 8.8°, 171.6° with all
  four edges a similar 3.2–4.1 mm. Similar edge lengths with 8° corners means
  these are **rhombi, not stretched rectangles**: the radial direction is
  nearly *tangent* to the ring. That is a node-correspondence failure between
  outer and inner loops, which is why neither resolution nor any cap parameter
  ever moved it. Smoothing helps monotonically inward but the worst cell stays
  at j=0 and improves only 0.914→0.900 — the outer loop is pinned to the OML
  tip edge and cannot move without breaking connectivity.
  **The proposed fix, not yet implemented:** build the inner loop as an inward
  *offset* of the outer loop along its local inward normal, sampled at the same
  parameter values, instead of a camber-aligned rectangle. Then the radial
  direction is perpendicular to the loop by construction and the first ring row
  cannot be rhombic.
- **L14** — **The tip cap is design-space INVARIANT.** Across 50 sampled
  geometries every tip metric is identical to four decimals (shape 0.149, skew
  0.898, AR 11.205). Not a bug: every geometry uses the same airfoil, so the
  tip section is a uniformly scaled and rigidly rotated copy of one normalized
  shape — and skewness and scaled Jacobian are *angle-based*, hence invariant
  under scaling and rotation. Two consequences pointing opposite ways: the tip
  defect will never be "fine on most geometries" (permanent quality ceiling),
  but it is also **not a robustness risk** — it never degrades, never causes a
  failure, contributes zero variance to the DoE.
- **L15** — **The tuning baseline was the best geometry in the space.** Seed
  100's OML shape of 0.426 sits at the **100th percentile** of the 50-sample
  spread. The design-space median is **0.231, not 0.426**.

  | OML metric | min | p10 | median | p90 | max |
  |---|---|---|---|---|---|
  | min_shape | 0.114 | 0.157 | **0.231** | 0.312 | 0.388 |
  | max_skewness | 0.520 | 0.577 | 0.648 | 0.744 | 0.851 |
  | max_aspect_ratio | 4.264 | 5.730 | 8.056 | 12.422 | 17.425 |
  | max_growth_ratio | 1.239 | 1.300 | 1.398 | 1.545 | 1.896 |

  **Quote the median, not the baseline.** A single hand-picked geometry
  systematically flatters the recipe.

---

## 6. The volume-march failure mode — diagnosed and explained

This is the most useful result in the project and it is worth stating in full,
because it is the template for how every future failure should be handled.

**Initial observation:** 3 of 10 geometries "failed" the pyHyp march, cause
unknown.

**What the audit found** (recomputing signed cell volumes from the written
CGNS — *no new compute*, purely from retained artifacts):

1. **pyHyp did not fail on any of the 10.** All ten ran to completion, exit 0,
   all 129 layers, positive final min volume. The "70% success rate" was
   AERIS's own verdict, not pyHyp's.
2. 7 of 10 written meshes are geometrically clean (zero negative-volume cells
   out of 1,703,936). 3 contain inverted cells.
3. **Every inverted cell in all 3 failures is in the same place:**

   | seed | inverted | fraction | block | i (chordwise) | j (spanwise) | layers |
   |---|---|---|---|---|---|---|
   | 1 | 53 | 0.0031% | domain.00003 | 7–8 | 0 (root) | 25–51 |
   | 3 | 100 | 0.0059% | domain.00003 | 6–9 | 0 (root) | 15–57 |
   | 4 | 14 | 0.0008% | domain.00003 | 7–8 | 94–95 (tip) | 1–6 |

   `domain.00003` is the aft block wrapping the trailing edge; i=7–8 is exactly
   the blunt-TE crown. **The defect is always the blunt-TE crown cells at a
   spanwise extremity** — the root symmetry plane or the tip-cap junction,
   i.e. where the marching front has no spanwise relief on one side. Never
   mid-span.

**What it rules out:**
- *Not* a global geometry-space limit — the march is sound everywhere except
  one topological corner.
- *Not* predicted by the surface QC gate. `min_shape_metric` was **0.01674 for
  9 of the 10 geometries** — identical to five significant figures, because it
  is measured at a topology-fixed cap corner whose shape barely depends on the
  planform. **It cannot discriminate and must not be used as a pre-march
  predictor.**
- *Not* explained by normal angle (failures 72.9–80.9° sit *inside* the passing
  range 71.8–92.8°; the geometry with the worst angle passed).
- *Not* TE thickness (failures inside the passing range).

**The cause — a controlled single-variable re-march (15 marches, surfaces held
byte-identical):**

| variant | clean | total inverted cells |
|---|---|---|
| `baseline` (`epsE=6.0`, shipped default) | 0/3 | 167 |
| `theta=5.0` | 0/3 | 184 |
| `nConstantStart=10` | 0/3 | 164 |
| `cMax=0.25` | 0/3 | 161 |
| **`epsE=3.0, epsI=6.0`** | **2/3** | **2** |

Confirmed monotone (seed 4, inverted cells vs `epsE`): 3.0 → 2 cells;
6.0 → 14 cells; 12.0 → 79 cells, spreading from layers 1–6 to layers 1–41.

**Law: explicit smoothing `epsE` must be LOWERED, not raised, to eliminate
trailing-edge cell inversion. The default `epsE=6.0` *causes* the defect.**
`theta`, `nConstantStart` and `cMax` have no useful effect. Physical reading:
the smoothing operator drags the TE crown nodes laterally where the marching
front has no spanwise relief, folding cells that would otherwise march cleanly.

**Second defect found in the same data:** one geometry was scored `ok` while
carrying **30 consecutive layers of negative scaled quality** (min −0.373). It
has zero inverted cells so the mesh is not folded, but it is severely skewed
and the campaign recorded it identically to a pristine mesh. The
`quality_warning` boolean never reached the campaign summary. Now fixed.

**Not yet closed:** one seed still had 2 inverted cells at `epsE=3.0`. The next
step is `epsE=1.5` and `2.0` to find the floor — `epsE` exists to keep the
front smooth, so it cannot go to zero for free.

---

## 7. The current recipe and family

### Selected surface recipe

```
oml_topology          cap4
points_per_side       49        (L3_medium)
spanwise_panels       16        (proportional allocation)
spanwise_allocation   proportional
cap_wrap_x            0.15
cap_wrap_points       21
tip_radial_points     9
tip_smooth_iters      20
te_thickness          0.005     (0.5% chord)
(volume)              epsE 3.0, epsI 6.0, cMax 0.5,
                      volSmoothIter 1200, nConstantStart 3
```

### The 5-level family (v2)

| level | pts/side | span panels | cap_wrap_pts | tip_radial | surface cells |
|---|---|---|---|---|---|
| L1_coarse | 25 | 8 | 11 | 5 | 7,516 |
| L2_smoke | 33 | 12 | 15 | 7 | 15,352 |
| L3_medium | 49 | 16 | 21 | 9 | 30,608 |
| L4_fine | 65 | 24 | 29 | 13 | 61,592 |
| L5_production | 97 | 32 | 43 | 17 | 122,712 |

Cell count ratio 2.04 / 1.99 / 2.01 / 1.99 → **linear r ≈ 1.42**, essentially
constant, on the 1.4 target for GCI (Celik et al. 2008).

**The family is geometrically self-similar** — the property GCI actually
requires:

| level | OML shape | skew | AR | growth | TE angle | tip shape | tip skew | tip AR |
|---|---|---|---|---|---|---|---|---|
| L1 | 0.496 | 0.625 | 3.2 | 1.407 | 154.0 | 0.133 | 0.901 | 11.7 |
| L2 | 0.466 | 0.630 | 3.3 | 1.369 | 148.8 | 0.139 | 0.900 | 12.4 |
| L3 | 0.491 | 0.633 | 3.5 | 1.407 | 140.2 | 0.126 | 0.902 | 14.6 |
| L4 | 0.474 | 0.636 | 3.5 | 1.407 | 127.3 | 0.129 | 0.904 | 14.5 |
| L5 | 0.483 | 0.637 | 3.8 | 1.407 | 104.0 | 0.111 | 0.908 | 17.0 |

Shape, AR, growth and tip skew are flat across a **16× cell-count range**. Only
the TE turn improves with refinement (154°→104°), which is correct behaviour.

**What scales vs what is held constant** — the distinction that makes this a
valid family:
- **Scales** (anything setting *cell size*): `points_per_side`,
  `spanwise_panels`, `cap_wrap_points`, `tip_radial_points`
- **Constant** (anything setting *geometry*): `cap_wrap_x` (a seam location),
  `te_thickness` (a property of the aircraft — must be identical at every level
  or the levels are not the same aircraft, which would invalidate GCI),
  `spanwise_allocation` (a rule, not a count), `tip_smooth_iters`

### Known, bounded, permanent limits

- **Tip skewness ~0.90** — sits exactly on the "degenerate" band boundary.
  Not fixable by any blocking arrangement (L12/L13); needs a rounded tip
  geometry or an overset tip cap. Constant across all 50 geometries (L14), so a
  quality ceiling rather than a robustness risk.
- **TE normal rotation 104–154°** — geometry, not mesh quality. A diagnostic,
  not a target.
- **OML skewness pinned at ~0.63** — structural: on a swept, tapered planform
  the chordwise and spanwise grid families cannot be orthogonal, and refinement
  cannot change an angle. 0.63 is "fair" and acceptable for RANS.

---

## 8. Validation status — what is proven vs assumed

| Item | Status |
|---|---|
| Surface build, all 5 levels, baseline | ✅ builds, passes all QC gates |
| Surface robustness, 50 design-space geometries | ✅ **50/50 (100%)**, no failures, no QC rejections |
| 2D NACA0012 TMR validation anchor | ✅ was CL=1.0918 vs TMR 1.0909 — **artifacts deleted, needs regeneration** |
| ADflow solve on an old cap4 mesh | ✅ RANS/SA converged ~11 orders, 92 iters, ~17 min, 4 ranks; tip cap caused no solver trouble |
| Volume march of the **current** recipe | ❌ **never marched** |
| `epsE=3.0` rolled into family presets | ❌ demonstrated but not shipped |
| 8 surface-option sweeps across 20 geometries | ❌ spec'd, not run |
| 3-grid GCI on the wing | ❌ not run |
| 100-geometry robustness campaign | ❌ not run |
| Post-solve y+ verification | ❌ not run |

**Deleted 2026-07-22:** `data/cfd_cases/` and `data/meshes/` (1.25 GB), to
restart against a corrected recipe. Findings were rescued into tracked config
folders first; every mesh regenerates deterministically from config + preset.

**Hardware constraint:** 15–16 GB RAM caps local runs at 4 ranks on ~1M cells
(an 8-rank run was OOM-killed). L5_production at pyHyp's own ~6.7M-cell
estimate likely needs bigger hardware.

---

## 9. The plan

### Original 6-stage framing

1. Understand what a structured mesh is and how to produce it
2. Build the surface mesh to suit the volume mesher
3. Find the metrics and limits every mesh must pass
4. Bear in mind this is for a PhD on BWB UAVs
5. Create guidelines from many attempts — one variable at a time, then
   combinations
6. On a new design: mesh, evaluate against metrics, retry using the guidelines

### Assessment

Stages 1–3 are **substantially complete** (sections 2–5 above). Stage 5 is
partly done — 16 laws exist, but derived from **one baseline geometry**, and
L15 proves that baseline was the *best* geometry in the space. Stage 6 is
unbuilt and carries a methodological risk (below).

### Two corrections to the plan

**(a) Stage 5's independent variable should be geometry, not mesh knobs.**

OFAT over mesh parameters on a fixed baseline is what produced the current 16
laws, and L15 shows exactly how that misleads: the tuning geometry scored at
the 100th percentile of the design space. The DSE ships *one* policy — what
matters is which **geometries** break it, not which knob settings break the
baseline.

Also, the failures found so far are not diffuse parameter interactions. They
are single, localizable, geometric causes: one column of cells at the blunt-TE
crown; a 143° corner fold from too few wrap points; 1.5e-7 sliver cells from
too narrow a cap. A failure taxonomy is the right instrument, not a response
surface.

The existing 8-sweep plan already does the right thing by running each option
across a **fixed 20-geometry Latin-hypercube sample** rather than one baseline.
That design should be kept and the results grouped by failure *mechanism*, not
by coarse pass/fail status.

**(b) Stage 6 must be a tiered policy, not a retry loop.**

Criterion C1 says: *every mesh in the campaign was produced by the same
deterministic, documented policy — no per-case hand tuning*. An adaptive search
over mesh parameters violates this. A referee will ask whether the CD trends
are design physics or mesh policy co-varying with design, and there will be no
answer.

It is defensible if and only if it is:
- a **finite, pre-declared decision tree** — recipe A, then B, then C,
  published before the campaign and never edited mid-campaign
- **deterministic** — the same geometry always yields the same recipe; no
  search, no randomness
- **recorded** — every mesh stores which recipe produced it, and the
  distribution is reported ("94% recipe A, 5% B, 1% failed")
- **audited** — the L4/L5 scatter must be shown comparable across recipes, so
  recipe-B meshes are not systematically biased against recipe-A meshes

Same mechanism, completely different defensibility. Frame it as a *tiered
policy*.

### Work packages, in dependency order

| WP | Work | Where | Cost |
|---|---|---|---|
| **WP0** | Find the `epsE` floor (sweep 1.5 / 2.0 / 3.0 on the 3 known-failing geometries); pick the **highest** value giving 3/3 clean; check `low_quality_layers` too, not just inverted count | laptop | ~15 min |
| **WP1** | Confirm on a fresh 10-geometry sample — success criterion 10/10 clean, `failure_mechanisms` empty. Same seed draw as the old campaign, so a direct before/after against the archived 6/10 | laptop | ~35 min |
| **WP2** | Regenerate the 2D NACA0012 TMR anchor (uses an airfoil O-grid, unaffected by the `epsE` finding — a straight reproduction check). If it does not reproduce, **stop**: that is a suite regression, not a meshing question | laptop | ~10 min |
| **WP3** | Wire the v2 family into presets: 5 `coarsen=1` grid levels with the wall-spacing law `s0_frac = 4.4e-6 × (97/points_per_side)`, plus the `epsE` move — one coherent change, since family members must share one march policy | laptop | hours |
| **WP4** | The 8 surface-option sweeps, 20-geometry LHS, one option at a time → fills in `SURFACE_MESH_LAWS.md` per option: tested range, observed safe range, failure mode outside it, source report | desktop | ~20–25 h |
| **WP5** | Wing-level 3-grid GCI → observed order, Richardson extrapolation, GCI band (**criterion C4** — the number a committee will ask for) | desktop | compute-bound |
| **WP6** | 100-geometry robustness campaign → success rate, failure taxonomy, level-to-level scatter vs design deltas (**C1 + C8**) | desktop | compute-bound |
| **WP7** | Build the tiered policy from WP4/WP6's taxonomy; freeze it; re-run WP6 to verify | — | — |

WP0–WP2 are under an hour combined and unblock everything else.

### The parameters queued for sweeping

| option | tested range | prior single-baseline knowledge |
|---|---|---|
| `topology` | cap4, mid4, split8 | cap4 selected; split8 a dead end |
| `split_x_fore` | 0.10–0.35 | trade-off, L6 |
| `points_per_side` | 25, 33, 49, 65, 97 | family levels |
| `spanwise_panels` | 2, 4, 8, 12, 16 | dominant OML lever, L3 |
| `tip_radial_points` | 3, 9, 17 | dominant tip lever, L4 |
| `cap_width_frac` | 0.15, 0.3, 0.5 | 0.15 fails (1.5e-7 slivers, NaN at layer 5) |
| `cap_wrap_points` | 9, 17, 25 | 9 fails (143° corner fold, inversion layer 15) |
| `cap_wrap_x` | 0.015–0.45 | 0.15 optimum (L8); 0.03 fails at root TE |

Each sweep must produce: tested range, observed safe range, failure mode
outside it, and the source report file — so every law is traceable to raw
data rather than asserted.

---

## 10. Open questions

1. **What is the unstructured family for?** ADflow — the validated solver — is
   structured/overset. SU2 takes unstructured. Either it is a
   **cross-verification arm** (same case, two independent chains; agreement is
   evidence — strong PhD content, roughly doubles the work), or a **robustness
   fallback** for geometries where the hyperbolic march fails (pragmatic, but
   then solvers are mixed within one DSE and C2/C8 get much harder). These
   should not be conflated.

2. **Is the tip worth fixing?** The inward-normal-offset inner loop (L12) is a
   one-time structural improvement. L14 says the tip is a bounded constant
   defect contributing zero DoE variance, so it is *not* a prerequisite for the
   campaign — but it is a permanent ~0.90 skewness ceiling sitting exactly on
   the degenerate boundary, and a referee may ask about it.

3. **Where does the campaign run?** L5_production is flagged as likely
   exceeding 16 GB. The campaign level should be the coarsest family level
   whose GCI-based uncertainty (C4) falls below the C8 threshold — which is not
   known until WP5 and WP6 are done.
