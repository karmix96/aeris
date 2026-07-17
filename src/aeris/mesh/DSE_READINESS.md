# DSE Mesh Automation — Defensibility Criteria and Gap Analysis

**Scope:** the `aeris mesh pyhyp` pipeline (YAML geometry → structured multiblock
surface → pyHyp hyperbolic volume march → CGNS) as the mesh generator for
design-space exploration (DSE) of BWB configurations, feeding RANS solutions
into surrogate/ML training.

**Question this document answers:** what must this process demonstrate before a
reviewer (thesis committee, journal referee, certification-minded customer)
accepts DSE results built on it — and how far the current implementation is
from that bar.

---

## 1. The defense posture

In a DSE campaign the mesh is not one artifact; it is a *policy* applied to
hundreds or thousands of geometries nobody inspects individually. The claims a
researcher must defend are therefore different from single-case CFD:

1. Every mesh in the campaign was produced by the same deterministic,
   documented policy (no per-case hand tuning).
2. The numerical error introduced by that policy is quantified and is small
   relative to the design signal the DSE is trying to resolve.
3. Failures are detected mechanically, not by eyeball.

Reference practice: ASME V&V 20 (grid convergence / numerical uncertainty),
the AIAA Drag Prediction Workshop gridding guidelines (family construction,
y+, growth ratios), and NATO AVT-366 (CFD-in-design robustness expectations).

## 2. Acceptance criteria

| # | Criterion | Target | Rationale |
|---|-----------|--------|-----------|
| C1 | **Unattended robustness** | ≥ 98% mesh success over a representative DOE (≥ 100 geometries spanning the sampled bounds), zero human intervention; every failure machine-classified (geometry QC vs surface QC vs march) | A DSE mesh generator that needs babysitting is not an automation result; biased failures (e.g. always high-sweep tips) silently bias the surrogate |
| C2 | **Topology consistency** | One topology for the whole campaign and the whole refinement family | Mixing topologies across the family or the design space confounds mesh effects with design effects |
| C3 | **True refinement family** | ≥ 3 levels with systematic refinement in *all three* index directions at (near-)constant ratio r (target r ≈ 1.4–1.5), same s0 scaling law | Richardson extrapolation / GCI is only defensible on a proper family; refining only wall-normal N does not constitute a grid-convergence study |
| C4 | **Quantified numerical uncertainty** | Observed order of convergence ≈ formal order (~2) on CL, CD, Cm; GCI on the finest pair reported; target discretization band ≤ a few drag counts on the baseline | This is the number a committee will ask for; without it "fine mesh" is an adjective, not evidence |
| C5 | **Solver-verified quality gates** | y+ ≤ 1 (wall-resolved) verified *post-solve*, not just targeted; near-wall growth ratio ≤ ~1.25; all-positive volumes (hard gate, already policy); skewness reported per level | Surface-mesh Jacobians are advisory; the solver is the arbiter |
| C6 | **Solver acceptance** | ADflow (or chosen solver) converges ≥ 5–6 orders on every family level of the baseline, and on the DOE sample without per-case tuning | A mesh that marches but does not converge is a failed mesh for DSE purposes |
| C7 | **Provenance** | Config hash, code version, seed, full parameter echo and QC report stored per mesh (largely in place via manifests/reports) | Reproducibility is table stakes |
| C8 | **Mesh noise below design signal** | Level-to-level scatter of the DSE outputs (e.g. ΔCD between L2 and L1 across several geometries) smaller than the response differences the surrogate must learn | If mesh-induced scatter ≥ design deltas, the ML model learns mesh noise; this is the DSE-specific criterion single-case V&V ignores |

## 3. Current state (evidence as of 2026-07-16)

* **Pipeline:** deterministic e2e chain with hard QC gates, per-run
  `surface_report.json` / `volume_report.json` / `smoke_manifest.json`
  (hashes, parameters, march metrics). Commits `1690ae8`, `bfaeaf1`.
* **Topologies:** `mid4` (requires coarsen=4 → in-plane resolution capped),
  `split8` (never marched; dead end), `cap4` (camber-aligned tip cap; marches
  at full in-plane resolution, coarsen=1).
* **Validated:** cap4+c1 at L1 (N257, y+~0.2 target, all 256 layers positive
  volume) and L4; L2/L3 validation in progress. mid4+c4 validated L1–L4.
* **Levels today refine wall-normal only:** L1–L4 change N and s0 at fixed
  in-plane resolution (97 points/side). Historically forced by the mid4
  coarsen=4 constraint; no longer forced now that cap4 marches at c1.
* **Not yet done:** any solver run; any grid-convergence study; any
  multi-geometry robustness campaign; post-solve y+ verification; farfield
  BC/family-tag definition for the solver.

## 4. Gap analysis

| # | Status | Gap |
|---|--------|-----|
| C1 | ✗ | All evidence is baseline BWB seed 100. No DOE sweep, no failure taxonomy across geometries. |
| C2 | ◐ | cap4 gives a single-topology answer; decision to standardize on it (and retire split8) not yet formalized. |
| C3 | ✗ | Current L1–L4 is a *wall-normal* ladder, not a grid family. cap4+c1 removes the blocker; family redefinition not yet implemented. |
| C4 | ✗ | Blocked by C3 + C6 (needs solver outputs on a true family). |
| C5 | ◐ | Positive-volume hard gate and per-block metrics exist; y+ and growth-ratio are targeted, not verified; no post-solve check. |
| C6 | ◐ | WP1 smoke PASSED (2026-07-16): ADflow 2.13.1 RANS/SA on cap4 L4 (α=2°, M=0.2, Re=1e6, 4 ranks) converged ~11 orders (ANK→NK, 92 iters, ~17 min); CL=0.3801, CD=0.02360, no solver complaints about the tip cap. Remaining: L1 solve, post-solve y+ audit, DOE-wide acceptance. NOTE: 15 GB RAM caps local runs at 4 ranks on ~1M cells (8-rank run OOM-killed); L1 (~6.7M cells) likely needs bigger hardware. |
| C7 | ✓ | Manifests, hashes, parameter echoes, deterministic seeds in place. |
| C8 | ✗ | Requires C4 machinery across ≥ several geometries. |

**Summary: the mesh *generation* layer is essentially done (C7, half of C5,
enabling technology for C2/C3). The *evidence* layer — everything a defense
actually rests on — has not started, and all of it gates on putting a solver
in the loop.**

## 5. Recommended topology and refinement policy

* **Topology:** standardize on **cap4 + coarsen=1** for the campaign. It is
  the only topology that marches at full in-plane resolution, so it is the
  only one that can anchor a true refinement family (C3). Keep mid4+c4 as a
  cheap screening/smoke recipe only; retire split8.
* **Family redefinition (proposal):** hold topology and s0-law fixed; scale
  in-plane and wall-normal together at r ≈ 1.4–1.5, e.g.
  * F3 (coarse): points_per_side ≈ 49, spanwise panels 4, N 129
  * F2 (medium): points_per_side ≈ 71, spanwise panels 6, N 193
  * F1 (fine):  points_per_side ≈ 97 (current), spanwise panels 8, N 257
  with s0 scaled per level by the existing characteristic-length law. Cap
  parameters (`tip_radial_points=3`, wrap counts) scale with points_per_side
  or stay fixed — to be settled empirically when the family is built.
* **Campaign level:** run the DOE at the coarsest family level whose GCI-based
  uncertainty (C4) is below the C8 threshold; keep the finer levels for
  uncertainty quotation and spot checks.

## 6. Roadmap (work packages, in dependency order)

1. **WP1 — Solver smoke (C6 start):** ADflow on the existing cap4 L1 mesh;
   convergence history, post-solve y+ map. Decisive go/no-go for cap4.
2. **WP2 — True family (C3):** implement F1–F3 presets per §5; verify all
   three march on the baseline.
3. **WP3 — Grid convergence study (C4):** solve F1–F3 at 2–3 flight
   conditions; observed order, Richardson extrapolate, GCI; report.
4. **WP4 — Robustness campaign (C1, C8):** mesh (and coarse-solve) a 100-case
   DOE; success-rate + failure taxonomy; level-to-level scatter vs design
   deltas.
5. **WP5 — Writeup:** fold WP1–WP4 evidence into the defense document; freeze
   the campaign recipe.

WP1 is days of work; WP2 likewise (mostly presets + validation runs); WP3–WP4
are compute-bound campaigns. Nothing in the list requires new meshing
research unless WP1 or WP2 fails — the known risk points are cap4 collar
behaviour under in-plane coarsening (F2/F3) and solver responses to the
blunt-TE tip-corner skewness.

**Status updates (2026-07-16):**
* WP1 ✅ first pass: ADflow converged ~11 orders on cap4 L4; the tip-corner
  skewness caused no solver trouble. See C6 row and
  `data/meshes/bwb_cap4_L4/adflow/`.
* WP2 risk CONFIRMED: cap4 at points_per_side=49 fails the march (segfault
  with default cap_wrap_points=17; inverts at layer 15 with wrap=9). The
  coarse family levels need genuine collar/cap redesign work, not parameter
  scaling. Failure artifacts: `data/meshes/bwb_cap4_F3_smoke/`.

**Status updates (2026-07-17) — WP2 resolved at the coarse level:**
* Root cause was NOT the collar/cap size contrast: cell-volume scans of the
  invalid volumes localised every inversion to one column — the blunt-TE
  base at the ROOT symmetry plane (`oml_2`, base-centre i, j=0).  With
  `cap_wrap_x=0.03` the wrap points spread over the whole wrap arc and the
  base is crossed by a single cell absorbing both ~90° corner turns.
* Fix (family-wide policy, `aeris.mesh.presets`):
  - `cap_wrap_x` 0.03 → 0.015: doubles base resolution; adjacent-normal
    angle at the TE wrap drops 115° → 78°.
  - Tip cap is held at its validated parameters on every level (width_frac
    0.5, wrap 17, collar 3).  The cap tiles a fixed-size feature and cannot
    coarsen with the OML: wrap=9 → 143° corner fold; width_frac=0.15 →
    1.5e-7 centre cells and NaN at layer 5 (both measured).  Cap is < 2% of
    the surface; family ratio unaffected.
  - s0 family law: s0_frac = 4.4e-6 × (97/points_per_side) — wall spacing
    refines at the same ratio as the in-plane spacing.  The old coarse-level
    s0 (2.2e-5) let the first layers stride past the TE base cells.
  - One damped march policy at all levels: cMax 0.5, epsE 6, epsI 12,
    volSmoothIter 1200, nConstantStart 3.
* Family presets implemented (`--preset smoke|fine|production` = 49/71/97
  pts/side, panels 4/6/8, N 129/193/257, r ≈ 1.4 in all three directions).
* smoke level VALIDATED: marches all 128 layers, min quality +0.128, ZERO
  low-quality layers (the old production recipe had 60), near-wall growth
  ratio ≤ 1.12, ~1M cells, 62 s, 24.5 MB.  Run: `data/meshes/bwb_smoke/`.
* fine/production are updated by the same policy but NOT yet re-marched;
  all changes are in the stabilising direction (the 78° corner should
  remove the production skew warnings).  Pre-2026-07-17 mesh artifacts were
  deleted; every mesh regenerates deterministically from config + preset.
