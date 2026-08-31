# AERIS — Memories

Single consolidated project memory (Mike's convention: all memories live here).
Decisions live in `decision/` (ADR-style); study write-ups in `studies/`.

---

## User & working style

- **Mike** — founder + lead researcher of AERIS, a BWB-UAV aircraft-design codebase.
  Building toward a defensible PhD multifidelity workflow. Works collaboratively and
  fast; wants decisions made deliberately and documented, and honest/calibrated
  reporting (no overclaiming — say what's verified vs not).
- **Full authority:** act as lead research engineer without asking approval, EXCEPT
  (a) important physics/modelling decisions → surface and confirm; (b) never delete
  the codebase, important files, memory, or evidence; (c) never force-push / rewrite
  history. Emit a clear progress message per change.

## Working conventions (feedback)

- **Decisions → `decision/`** (ADR files, numbered, e.g. `0001-...md`).
- **Studies → `studies/`** (each study: short description, assumptions, results,
  conclusions).
- **Memories → `memories/memories.md`** (this single file).
- **Heavy compute → desktop:** don't launch long/heavy runs in-session (big DoEs,
  full CFD, CAD/Gmsh/pyHyp campaigns, 50-case visual batches). Prepare runnable
  runbook commands for Mike; a single case / modest sweep in-session is fine.
- **Findings live in `configs/`:** rescue REPORT/evidence out of `data/`+`artifacts/`
  (gitignored, regenerable) into tracked `configs/` before anything is wiped.
- **Save data in the project tree** (never /tmp or scratch for deliverables).
- **Nothing saved by default:** geometry/CAD/mesh/plot outputs off unless requested
  at run time (CLI flag / GUI toggle).
- **Mesh inspection:** Mike inspects meshes in ParaView, not custom plots.

## Key decisions (see decision/ for full ADRs)

- **Master geometry = the smooth MACH-Aero pyGeo B-spline loft.** Do NOT force it to
  interpolate the piecewise Aeris authored stations. The pyGeo loft's metrics are
  authoritative; sub-% smooth-vs-piecewise shifts live in the design space, not
  errors. (Validation gate = frame reconstruction + reference metrics + control
  invariance; all pass.)
- **ASB-free AVL target:** AERIS must not construct an `asb.Airplane` for the
  AVL+viscous path. aerosandbox may be IMPORTED (NeuralFoil hard-depends on it).
  Native AVL writer + coordinate-NeuralFoil satisfy this; the geometry path is truly
  aerosandbox-free (guard test).
- **One geometry config:** `configs/geometry/bwb.yaml` for BOTH backends. All other
  geometry configs deleted (suite RED by design until tests are rebuilt).
- **Fixed airfoils at b0/b1/b2/b3:** mh91 / mh91 / e374 / nlf1015 (Panagiotou &
  Yakinthos BWB UAV baseline). NOT AH 94-145. Swap the four `station_airfoils` names
  for any `data/airfoil_database` entry.
- **TE thickness (DECISION-0004):** airfoils are sharp; blunt TE =
  **FIXED constant 0.5 mm absolute along span** (1.0 mm if sturdier edge needed). Study (`studies/trailing_edge_thickness.md`, NeuralFoil
  sweep on our airfoils at Re tip 1.85e5 / MAC 7.7e5 / root 1.8e6): ΔCd ~linear in TE
  thickness (Hoerner); ≤0.5%c costs ≤~7 section drag counts, RAISES CL_max (van Dam),
  small Cm; >1%c material; blunting nlf1015 at low-Re tip REDUCES drag. **WING-LEVEL
  (the driver): ΔCD ≈ −0.5 drag counts (<0.5% of total), slightly favorable** —
  area-weighted integral (wing.py), largest %c TE at low-area tip. Applies to
  the MESH TE floor. OPEN: validate 0.25%c pyHyp marchability floor; 3-D ADflow base
  drag check. pyGeo master surface stays sharp; blunt TE is a downstream mesh/mfg
  transform.

- **Native AVL fidelity + capture (DECISION-0005, 2026-07-25):** three things.
  (1) The native runner now captures the COMPLETE AVL output family (e, Xnp, 25
  stability + 18 body derivatives, per-control authority derivs, hinge moments,
  surface forces, strips, shear/bending) into `native_avl_result.json`; parsers
  live in the shared asb-free `aero/solvers/avl_output.py` used by BOTH solvers.
  (2) **`span_margin` default 0.02 → 0.0 (FULL span).** The 2% inset left a
  32.6 mm centreline GAP under YDUPLICATE → spurious inboard tip vortices:
  CL was −54.9%, CLα −26.2% (2.741 vs 3.715 /rad), L/D halved. **All low-fi aero
  numbers from before 2026-07-25 are invalid.** (3) Elevon now spans exactly its
  geometric band (edge sections snapped + both boundaries tagged): CL_δe +16.7%.
  Verified vs ASB: NO field missing, clean symmetric case agrees ≤0.6% (CLα 8e-7,
  Xnp 1e-5). Study: `studies/native_avl_output_and_fidelity.md`.

- **Low-fi viscous+thickness model (DECISION-0006, 2026-07-25) — VERIFIED, not
  assumed.** `CD = cd_ind_AVL + cd_profile_NeuralFoil`; AVL's two per-section
  hooks are both used and both proven PRESENT/CORRECT/ACTIVE by ablation:
  **CDCL** (25/25 sections, per-section CST NeuralFoil at the section's own Re;
  independent refit agrees 4.3e-7; CDvis 0→0.00663 on toggle; tip 3.8× draggier
  than root from Re alone) and **CLAF** = 1+0.77·t/c (16 distinct values from 4
  authored airfoils; t/c 15.00%→10.93%→15.07% recovers mh91→e374→nlf1015;
  ablation CLα 3.484→3.685, ratio 1.0576 vs lifting-line 1.0641 — 0.6% apart,
  proving it acts as a SECTION property diluted by 3-D downwash).
  **Verification standard adopted: presence in the .avl is NOT evidence** — an
  ablation must move AVL's answer by the *predicted magnitude*. (The OPER `v`
  toggle once silently disabled viscous forces with CDCL still in the file.)
  Strip integration is PRIMARY, AVL CDtot is the audit — they differ 4.28%,
  which is the 3-point CDCL fit's own error. Study: `studies/avl_section_corrections.md`.

- **Low-fi DISCRETISATION (DECISION-0009, 2026-07-25).** The two convergence
  questions were CONFLATED before (adding a section also refined the lattice,
  since total spanwise panels = (n−1)×panels_per_interval). Separated: geometry
  mode varies n_sections with the panel count PINNED at 96/side; panel mode pins
  n_sections and sweeps each direction alone.
  **PRODUCTION = 25 sections / 4 spanwise / `nchordwise` 24 / cosine.**
  **`nchordwise` 8 → 24** — at 8 the elevon CL_δe carried **7.7 %** error, the
  biggest in the whole chain, because the hinge at x/c=0.75 sits 0.059c from the
  nearest cosine panel edge. Joint check 25/4/8 → 25/4/24: CL 1.07→0.15 %,
  CDind 3.20→0.51 %, CL_δe 7.06→0.38 %.
  Three gotchas worth remembering:
  (a) **geometric metrics converge ~3× earlier than aerodynamics** (Sref 0.05 % by
  n=9 vs aero 1.9 % at n=13) — NEVER use area/MAC convergence as a proxy;
  (b) **CL_δe is NON-MONOTONIC in n_sections** (n=13 beats 17 and 25,
  reproducibly): a ±1.5 % oscillatory floor from section alignment vs the elevon
  band edges, which uniform refinement cannot fix → motivates adaptive placement;
  (c) **uniform chordwise spacing halves the elevon error but wrecks Xnp/Cmq
  (14–15× worse, and it does NOT improve with refinement)** — rejected; LE
  clustering is what resolves the pitching moment.
  **Hard AVL limits: (n−1)×spanwise ≤ 250 strips; strips×nchordwise ≤ ~6000
  vortices.** 49/4/16 and 65/4/* both FAIL. Studies:
  `studies/section_and_panel_convergence.md`, `studies/hinge_panel_alignment.md`.

- **CONTROL RESOLUTION is the binding low-fi error (DECISION-0010, 2026-07-25).**
  Not wing resolution. AVL smears a control at its EDGES — chordwise at the hinge,
  spanwise at the band ends — and the error is set by how much of the control the
  smearing occupies. One criterion replaces two tuned numbers:
  **N_flap ≥ 6** (chordwise panels aft of the hinge; error ~ N_flap^-1.47, R²0.966)
  and **ramp fraction ≲ 15%** (gain-ramp width outside the band edges / band width;
  r = +0.978, re-confirmed +0.964 on an independent set). PREDICTIVE — estimable
  from geometry before running AVL. `ramp_fraction()` is in
  `aeris.geometry.geometric_information`.
  **I published a WRONG mechanism first** (hinge/panel-edge "coincidence") and a
  hinge sweep killed it: within-chordwise-level corr(edge distance, error) =
  +0.611/+0.077/-0.040/-0.163, inconsistent. At nchordwise=24 the hinge with EXACT
  edge alignment is not the most accurate. Lesson: pooled correlations across a
  refinement level are confounded by the level.
- **Robustness (Task 5):** 25/4/24 holds ≤0.5% on 9 CONSTRUCTED extremes —
  AR 2.25–7.85, max sweep/twist/dihedral, both hinge bounds. Geometry extremes are
  a NON-ISSUE. Both failures are elevon-BAND: narrow band (0.70–0.85) = 4.34%.
  Random sampling CANNOT reach a 19-D corner (0.2^19 ≈ 5e-14) — extremes must be
  BUILT. `build_pygeo_sections_from_config(sample=...)` accepts a constructed design.
  Honest number: nchordwise=24 gives CL_δe **≤1.8%** across the hinge range (not the
  1.1% quoted at hinge 0.75 alone). 32 chordwise would give 0.76% but is 6144
  vortices — over AVL's limit. So 1.8% is the ceiling at this grid.
- **Adaptive section placement (DECISION-0011) — I got this WRONG first, then
  fixed it.** Reported as a negative result (10× worse than uniform); the cause was
  a **design flaw in my own metric**, not the idea. Each channel was normalised to
  UNIT INTEGRAL before blending, so a sweep break of range 1.05 and a wiggle of
  range 0.0002 both contributed exactly 1.000 — the metric recorded WHERE each
  property varied and destroyed HOW MUCH it mattered, i.e. the one judgement it
  exists to make. **Fix: fixed physical reference scales** (lengths/root chord,
  twist/10°, thickness+camber/0.1), NO per-channel re-normalisation; verified
  against de Boor (density ∝ √amplitude). Verdict reversed:
  max_gradient 4.21×, elevon_wide 2.25×, elevon_narrow 1.72×, easy cases 0.27–0.49×,
  and **worst case over the set 1.23% → 0.84%** — so ADOPTED for DoE work
  (uniform still fine for a one-off ordinary wing).
  Two things survive the correction: `concentration()` still predicts difficulty
  BACKWARDS (−0.813 → −0.820) so it is genuinely useless, and |g''|^(1/2) cannot
  resolve features sharper than its smoothing window, so true kinks (control-band
  edges) still need HARD node constraints, not density.
  **`floor=0.50` was tuned against the BROKEN metric — re-tune it.**
  Lesson: Mike's scepticism ("something doesn't make sense") found this. When a
  result contradicts a strong prior, suspect the instrument before the finding.
- **BUG CLASS TO WATCH: two pipelines, one override.** The 3 elevon DVs were
  sampled but never reached AVL — `services.generate_geometry_case` applied the
  sampled-elevon override, `build_pygeo_sections_from_config` (which reimplements
  the pipeline for the AERO path) did not. Every aero run before 2026-07-25 flew
  elevon 0.60–0.95 at hinge 0.75. Invisible to every check: geometry built fine,
  both solvers saw the same elevon so they still agreed. Guarded by
  `tests/aero/test_elevon_dvs_reach_avl.py`. **Whenever a second pipeline
  reimplements a first, diff the override steps.**

- **WIRING (2026-07-25).** The panelling decisions are now reachable, not just
  documented: `geometry.aero_discretisation` block in `bwb.yaml` (n_sections,
  span_margin, spanwise_panels_per_section, nchordwise, cspace,
  snap_sections_to_control, section_placement, ramp_fraction_limit), validated
  against AVL's array limits AT CONFIG LOAD. Resolution order **CLI flag → config
  → code default**. CLI gained `--cspace` and `--section-placement`; the GUI
  pyGeo-native tab exposes all four and warns before exceeding the limits.
  Adaptive placement is now actually CALLED from
  `build_pygeo_sections_from_config` (it was orphaned research code — DECISION-0011
  was unimplementable). Guard: `tests/aero/test_discretisation_wiring.py`.
- **Band-edge snapping now INSERTS, not moves (corrects DECISION-0005).** Moving
  the nearest section onto the edge leaves its neighbour a full spacing out, which
  WIDENS the gain ramp: 11.8% → 23.0% of band width — the opposite of what
  DECISION-0010 wants, and it made the whole `auto` gate fire on every wing. It
  also meant the ramp numbers in the studies (computed by inserting) described a
  section set production never built. Inserting costs 2 sections and gets both.
  **Two of my own decisions were in tension and nothing caught it until the gate
  misfired.**

- **RE-RUN after the snapping fix (2026-07-25).** Only Task 5 extremes could
  change a decision, and it did: **elevon_narrow 4.34% → 0.74%**. The "narrow
  elevon fails" headline was largely an artefact of moving-snap. All nine extremes
  now ≤1.3%. Head-to-head at matched conditions validates the auto gate BOTH ways:
  narrow → adaptive 0.68% vs uniform 1.18% (1.7×); normal → uniform 0.33% vs
  adaptive 0.78% (2.4×). DECISION-0011 now rests on that instead of on a failure.
  Unaffected and NOT re-run: Tasks 1(vs-ASB)/2/3 (both sides saw identical
  sections, so comparisons cancel), Task 4 physics validation (synthetic wings,
  never touches that code path), Task 6 (its uniform baseline already inserted).

## Project state (2026-07-24)

- **pyGeo backend committed** and decoupled from AeroSandbox (geometry import graph
  is asb-free; regression-guarded).
- **Native pyGeo→AVL+viscous chain** (no asb.Airplane): `native_avl.py` +
  `pygeo_avl_adapter.run_pygeo_native_avl_case` + `NeuralFoilCoordinateSource`.
  CLI `aeris aero pygeo-native`; GUI Aero page tab "④ pyGeo native". Matches the
  asb-serialized numbers to 0.1–0.4%.
- **Elevon does pitch + roll:** native AVL emits `<name>_sym` (d1, δe pitch) +
  `<name>_diff` (d2, δa roll); result reports Cm/Cl_roll/Cn/CY. `--control-input-deg`
  (δe) + `--diff-input-deg` (δa). Verified δe→pitch, δa→roll.
- **DoE design space** = `bwb.yaml` ranges (small BWB ISR UAV, full span 1.5–2.5 m,
  AR 2.6–6.2). **20 design variables** = 10 planform + 7 section + 3 elevon geometry
  (start/end/hinge via `elevon_bounds`, so the DoE varies the elevon for the later
  controllability optimization). Root dihedral enforced 0.
- **pyGeo vs ASB comparison** done (`studies/pygeo_vs_aerosandbox_geometry.md`):
  50/50 build both backends; metrics agree <1.3%. Interactive side-by-side 3D viewer
  exists.
- Generator id renamed `bwb_segmented_v1` → **`bwb_segmented`** (config-facing;
  package path unchanged).
- **Geometry creation is opt-in + backend-selectable.** `aeris geometry generate`
  flags: `--backend aerosandbox|pygeo|both`, `--exports iges,tecplot,sections,npz,
  step,stl,obj,vtk` (default NONE; CAD-family auto-enables physical CAD),
  `--physical-cad`, `--save-metrics` (→ `geometry_metrics.json` with span/area/AR/
  MAC/volume/wetted + taper/root/tip, attributed to the backend(s) that built),
  `--seed`. Nothing (CAD/VTK/STEP/plots) written unless requested. GUI geometry page
  "① Create geometry" has two backend tabs (AeroSandbox | pyGeo), pyGeo tab exposes
  the export checkboxes + physical-CAD + save-metrics.

## Technical gotchas (hard-won)

- **`planform_bounds.b_total_m` is the SEMI-span** (full span = 2×). Config comments
  it now.
- **Integrated-metric comparisons MUST extract pyGeo over the FULL span** (margin
  1e-4). A [0.02, 0.98] margin understates span ~4% and biases every integral.
- **NeuralFoil hard-depends on aerosandbox** (imports it at load) — zero-aerosandbox
  viscous is impossible while using NeuralFoil; the target is only "no asb.Airplane".
- **AVL `.avl` airfoil files must be ≤ IBX (~360 pts)** — native writer downsamples
  (cst_points=80 → 159-pt loop); AeroSandbox uses ~99. This 80-vs-181-point camber
  difference is the whole residual ~0.5% CL gap between the native and ASB paths.
- **The ASB reference path CANNOT do roll.** AeroSandbox's AVL exporter collapses
  every control surface into ONE variable `all_deflections` (SgnDup +1); AVL
  reports "1 Control variables", so the `d2` keystroke hits nothing and δa is
  silently ignored (measured Cl_roll = the sideslip term alone). Its elevon also
  over-extends to the tip. Only the NATIVE path models differential elevon —
  which is what the 3 elevon DVs exist to optimise. Don't trust ASB-path lateral
  numbers.
- **AVL interpolates control gain linearly between sections** — a control band
  edge exists only where a SECTION declares the control. Tag both boundary
  sections, and snap sections onto the band edges, or the elevon extent quantises
  to the section grid (staircase response vs the elevon DVs).
- **No CG exists yet** → AVL Xref=(0,0,0) is the geometry origin, not the CG, so
  `static_margin` is deliberately NOT reported (only `x_np_over_c_ref`). Pass
  `moment_reference_m=` + `moment_reference_is_cg=True` once a mass model exists.
- **`section_bounds.airfoil_name`** is the fallback airfoil (overridden per station
  by `station_airfoils`); kept = root airfoil to avoid confusion.
- **Generator-id rename gotcha:** renaming GENERATOR_ID to `bwb_segmented` broke
  code that hardcoded `generator_id != "bwb_segmented_v1"` (neutral + deflected CAD
  export). Fixed to accept `("bwb_segmented","bwb_segmented_v1")`. If more id-gated
  code surfaces, apply the same. Package import path stays `bwb_segmented_v1`.
- **Split-elevon physical CAD is DEFERRED (broken at small scale).** Both the
  neutral `--physical-cad` and the deflected `export-deflected-cad` produce INVALID
  OCC solids for the rescaled small BWB — `validity_ok = all bodies shape.isValid()`
  is False systematically (all seeds), and the deflected loft fails 2-3/8 bodies
  (`StdFail_NotDone`). NOT the airfoils (clean), NOT flaky, NOT the split-epsilon.
  Root cause: thin split-elevon bodies at small scale degenerate for OCC; the
  standalone "worked" at the OLD larger scale. Real fix = denser elevon sections +
  shape healing (each CAD build is >2 min — slow to iterate). Secondary path;
  control authority is covered by native AVL. GUI: CAD removed from the Create-
  geometry tab, lives only in "⑤ CAD export".
- **Geometry runs are LEAN by default:** write-only inspection CSVs (control_points/
  planform_sections/section_3d + pyGeo authored/extracted/cst) are gated behind
  `geometry.outputs.save_detail_csv` / `--save-detail` (off). Empty `sections/` dir
  only created when section DATs are written. GUI Visualize tab embeds the pyGeo
  interactive 3-D HTML in-page (streamlit.components.v1.html).

## Key references

- Config: `configs/geometry/bwb.yaml` (the one config).
- Backend: `src/aeris/generators/bwb_segmented_v1/` (pygeo_*.py, PYGEO_BACKEND.md).
- Native AVL: `src/aeris/aero/solvers/native_avl.py`; adapter
  `pygeo_avl_adapter.py`; polar `src/aeris/airfoil/neuralfoil_coordinate_source.py`.
- Comparison tooling: `standalone/pygeo_asb_comparison/`.
- Evidence: `configs/geometry/{pygeo_avl_evidence,pygeo_validation_evidence,pygeo_asb_comparison_evidence}/`.
- **Codex's work is NOT off-limits (Mike, 2026-07-26).** The earlier "Codex owns
  `standalone/pygeo_surface_mesh_study/` — leave it alone" rule is SUPERSEDED:
  Mike said "you can edit codex work, actually do it. i don't like its work". So
  `src/aeris/mesh/surface.py`, `standalone/pygeo_surface_mesh_study/` and the
  mesh study configs are all editable. Still: never delete evidence, never
  force-push. (NB: commit 66976b4 accidentally swept in Codex's uncommitted
  surface.py via `git add -A src/` — content intact, attribution wrong.)

## DSE vs verification panelling (DECISION-0013, 2026-07-26)

**AVL cost is ~cubic in vortex count, and we were running at 77% of its ceiling.**
A single low-fi point cost 58 s: pyGeo loft 1.36 s + NeuralFoil viscous 0.60 s +
**AVL 56.93 s**. 192 strips x 24 chordwise = 4608 vortices vs AVL's compiled ~6000
limit. DECISION-0009 picked 24 chordwise on accuracy alone and never priced it —
that made a 2000-design x 5-alpha sweep 6.7 days, i.e. not a DSE tool at all.

Two tiers now:
- **DSE (shipped default): nchordwise 12** — 2304 vortices, 14.6 s/point.
- **Verification: nchordwise 24** — 57.3 s/point; use for promoted designs,
  control-authority sizing, anything feeding CFD. `--nchordwise 24` / GUI field.

Why it is safe: at every panel count the worst error is a CONTROL derivative.
`Xnp` is 0.3350 from 6 panels up; at 12, CL 0.51% / Cm 0.67% / Xnp 0.00% /
CL_de 3.76%. And the control error is a **consistent bias, not scatter** —
cheap/rich ratio 0.9684 (nominal) vs 0.9687 (narrow elevon), spread ~1% of the
bias — so it cancels when designs are RANKED, which is what a DSE does.

**Guard added:** AVL's answer to exceeding its arrays is `status=FAILED` with every
coefficient `None` — indistinguishable from a physics failure, and it silently
produced an all-NaN study. `avl_limits_ok()` ran only at config-parse time.
`write_native_avl` now RAISES on the NSMAX=500 strip limit and the ~6000 vortex
limit. Never trust an AVL run's silence; check `status`.

**Sliver merge (same date):** pins were unioned onto the base grid with
`np.unique`, which only removes exact duplicates. Measured across 10 geometries the
tightest interval was 2.4%-9.1% of uniform spacing (~0.001 of span) on EVERY
geometry — one of 25 sections wasted on a near-duplicate station. Now a base
station within `SLIVER_MERGE_FRACTION = 0.25` of a uniform interval from a pin is
dropped in the pin's favour, and the largest-gap top-up respends the freed section.
Remaining tight pairs are pin-vs-pin (real geometry features), which is legitimate.

**Open, unexplained:** narrow-elevon-with-pins hangs AVL reproducibly (>8 min vs
58 s norm) at 24 chordwise, with well-formed geometry and all `.af` files valid.
Not the sliver (nominal has a tighter one and solves fine). Study runs now record
TIMEOUT and continue instead of aborting.

## Section placement (DECISION-0014, 2026-07-26, revised after audit)

**`section_placement: auto` — gated adaptive placement is RETAINED.** An interim
verdict of `never` was WITHDRAWN the same day; see why below, it is the useful part.

Ranked on quantities the reference can resolve (control derivatives, forces,
stability — NOT drag), matched 25-section budget, 10 geometries:

| approach | mean | MAX |
|---|---|---|
| A uniform, no pins | 15.17% | 34.54% |
| B uniform + hard pins | **0.82%** | 1.98% |
| C adaptive, gated (auto) | 0.86% | **1.68%** |
| D adaptive, forced | 0.91% | 1.68% |

1. **Hard feature pins do nearly all the work** — without them, 34.54% worst case.
2. **B and C tie on the mean** (0.04 pp, inside the reference's ~0.5% noise).
3. **C has the better tail**, winning where the ramp is severe: narrow elevon
   (66.7% ramp) 1.52% -> 1.12%, random_1020 (36.3%) 1.98% -> 1.42%. On benign
   geometries the gate does not fire and C is identical to B. A budget sweep
   confirms it: on the narrow elevon adaptive wins at 11/15/19/25 sections alike.

### THE RULE THAT CAME OUT OF THE WITHDRAWN VERDICT

**Never rank spanwise discretisation with drag.** `CDind`, `cd_total`, `e` cannot
adjudicate placement in AVL. A reference disagrees with ITSELF by 1.2-2.9% on drag
depending on how its OWN sections are placed, and it does NOT converge away:
49/73/97 sections give 2.90%/1.37%/1.17%. AVL's Trefftz-plane drag is acutely
sensitive to how stations sample the spanwise load. The withdrawn verdict came from
ranking on an aggregate dominated by drag, against a reference that was itself
uniform+pinned -- so it both used an unresolvable quantity AND flattered the
candidate sharing its construction. Report drag; never decide with it.

**Also: don't judge a method only on the quantities it targets** -- that is
question-begging. Rank on everything the reference can actually resolve.

**Config wiring bug fixed:** `run_pygeo_native_avl_case` had a hardcoded
`nchordwise=24`, so `geometry.aero_discretisation` reached AVL only via CLI/GUI --
every library caller (i.e. every study script) silently ran at 24 regardless of
config. `build_pygeo_sections_from_config` now returns nchordwise/cspace/
spanwise_panels in its meta; callers must pass them. The GUI now reads all four
knobs from config via `_config_discretisation()`.

**Sliver merge:** pins were unioned with `np.unique` (exact duplicates only), so all
10 geometries wasted a station on a near-duplicate ~0.001 of span from its
neighbour. Pins now absorb base stations within `SLIVER_MERGE_FRACTION = 0.25` of a
uniform interval; the largest-gap top-up respends the freed section.

**Settings of record: `studies/SETTINGS_OF_RECORD.md`.**

## Automated CFD campaign strategy (S6, 2026-08-16)

- **Order of work:** finish and validate structured `S6 atlas + ADflow`; then add
  wall-resolved `Gmsh prism/tet + SU2`; then add common `auto` and `compare`
  modes; only then train AI helpers from the captured S6 experience.
- **S6 is a strong candidate, not production-ready.** The coarse ADflow pilot
  converged by 7.59 residual orders, but its deliberately coarsened wall grid
  failed y+ (p95 2.41, max 7.23). Fine templates are valid 10/10. The locked
  hold-out remains untouched.
- **10,000-case freeze gate:** production y+; locked hold-out without tuning;
  at least 99/100 accepted CFD pilot cases; grid convergence on about 20 cases;
  10,000/10,000 mesh preflight with automatic recovery; and a 500-1,000-case HPC
  rehearsal proving restart, storage, and collection.
- **100-case reduced gate:** preflight 100/100 meshes, run 10-20 extreme CFD
  pilots, pass production y+, perform five grid-convergence cases, reserve about
  ten unseen cases, and prove unattended recovery.
- **AI/FFD rule:** pyGeo or FFD controls geometry; deterministic S6, IDWarp, or RBF
  controls the accepted volume. AI may rank templates and predict quality,
  failures, or useful CFD samples, but an AI-only mesh is never trusted. Every
  result must pass the same wall, interface, volume, Jacobian, y+, and CFD gates.
- Persist geometry DVs, rankings, attempted templates, deformation provenance,
  mesh quality, failures, timing, y+, residual/force histories, and final forces
  for the planned AI-assisted mesh-atlas paper. The persistent detailed work order
  is `AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/ROADMAP.md`.
- **Latest S6 mesh evidence (2026-08-16):** the geometry-active maximin smoke atlas
  passed 100/100 development geometries in 131 attempts, with 80 first-try passes,
  maximum five attempts, and worst accepted quality +0.15184. It needed no smoke
  enrichment seeds. This does not unlock the holdout: production-resolution 100/100
  validation and production y+ are still required.
- **Production seed result (2026-08-16):** the governed development calibration is
  now `N=257`, `epsE=1.5`, and first-cell fraction `3.6e-6`. All 16 deterministic
  maximin templates pass the independent +0.10 scaled-quality floor. The minimum
  is +0.10535253, and only three cells across the atlas are below +0.15; these are
  first-layer tip/trailing-edge cells in seeds 002 and 068. The manifest remains
  unfrozen pending complete development validation and production CFD/y+ evidence.
  The current production label still refines wall-normal N while retaining the
  L2_smoke tangential surface, so a true three-direction grid family remains open.
- **First production development audit (2026-08-20):** the 16-template written-CGNS
  run finished 99/100 in 220 attempts. Geometry 089 failed because its best quality
  was +0.092659, below the +0.10 floor. The independent report auditor confirmed
  report integrity but correctly rejected campaign acceptance. No gate was lowered.
- **Production enrichment (2026-08-20):** six local seeds were attempted. Seeds
  089, 095, 085, 008, and 094 passed; seed 007 failed one cell at +0.086926 and is
  recorded as known-unbuildable under the fixed policy. The qualified atlas has 21
  templates. In the running revalidation, geometry 007 already passes at +0.153736
  through template 095, so the failed local seed is not required for acceptance.
- **Production revalidation completed (2026-08-20):** the 21-template,
  100-target production-resolution written-CGNS audit passed 100/100, and its
  independent audit passed integrity and campaign acceptance. This freezes atlas
  membership only. Do not open the locked hold-out or freeze the full CFD policy.
- **Reload handoff:** start at `AERIS_MESH_STUDY/PROJECT_HANDOFF/README.md`. It
  includes status, decisions, evidence, risks, exact commands, a future-agent
  prompt, and a constrained Claude continuation prompt/logging contract. Never use
  `artifacts/s6_bounded_mesh_atlas/atlas_manifest_frozen_candidate_v3.json`; its
  smoke-level freeze flag is obsolete.

## S6 grid/TE and laptop qualification (2026-08-21)

- Three governed N65 development meshes passed hard mesh gates and all three
  ADflow runs converged with 7.51-7.74 residual orders and stable forces.
- The strict N65 y+ screen passed 0/3 (p95 1.10-1.37, p99 2.85-3.25, maximum
  4.57-6.31). This proves the solver/rejection path only. N65 is too coarse to
  validate, tune, or reject the production wall law.
- The current P0 atlas (smoke tangential, N257, s0 fraction 3.6e-6) is separate
  from the true G1/G2/G3 family. TE variants remain 0.5/1.0/1.5 mm with
  0.25/0.50/0.75% local-chord floors.
- Claude Opus/max found three high-severity cache/provenance risks. The runner now
  binds source/registry and mesh hashes, MPI count, and solver artifacts. Mesh
  fingerprints include governing quality, geometry-set, QC, and meshing modules;
  41 focused tests and Ruff pass.
- The three pilot reports predate those final fingerprints. Do not rewrite them.
  Their separate `legacy_evidence_audit.json` passes asset/hash integrity but
  records `current_cache_compatible=false`; rerun only for exact current-code
  provenance. P0 span count is template-dependent (60-98), not fixed at 89.
- The collector writes `laptop_summary_current.json` and cannot overwrite the
  historical summary. The v1 plan file was written after the pilots, so it is a
  policy snapshot, not preregistration proof. The final v3 G1/G2/G3 family now
  refines endpoint and collar counts as well as chord/span/normal counts.
- The next heavy action is one P0 development canary on >=64 GB, then two more
- Pilot design index 0 is geometry 007, the hardest known route (six attempts).
  It is good for peak-memory testing, but its y+ is not representative of the
  median design.
  only after memory and y+ are measured. Hold-out remains untouched.
- Canonical detail: `AERIS_MESH_STUDY/PROJECT_HANDOFF/QUALIFICATION_UPDATE_2026-08-21.md`.

## AI paper direction (2026-08-30)

- **Mike's framing (mine was rejected):** Paper 1 = use AI to make BWB meshing
  robust; Paper 2 = use the resulting corpus of new meshes for a more AI-native
  contribution. Plan: `studies/PAPER_PLAN_AI_MESHING.md`.
- **Atlas ledger numbers that justify Paper 1** (qualified21 v3 checkpoint, 100
  LHS geometries): 162 attempts, PASS 116 / FAIL 32 / SURFACE_BUILD_ERROR 14;
  74/100 first-pass; retry tail 2,3,4,5,6 and one geometry needing **21**;
  failures co-occur as inverted_cells + positive_volume + positive_scaled_quality
  (folding); 20 of 21 templates used, template 42 takes 21/100; ~25 s per attempt.
  **The problem is routing COST, not infeasibility** — the atlas reaches 100/100.
  A feasibility boundary requires deliberately widening the design space.
- **Hardware ceiling, measured:** 12 cores, 15 GiB RAM, **NO GPU** (`nvidia-smi`
  absent; torch 2.12.0+cu130, `cuda.is_available()==False`). DoMINO/GeoTransolver/
  SMART-scale training is not runnable locally. Re-check if cluster GPU appears.
- **HF labels do not exist yet:** `cfd_pilot_083` and `cfd_pilot_083_n65`
  `solve_report.json` both read `status: failed`, `forces: {}`. Anything needing
  RANS is gated on the S6 desktop campaign; the meshing paper is not.
- **Paper 2 decided (Mike, 2026-08-30): the AI BUILDS the mesh.** Not the flow
  surrogate. Replace the fixed analytic distribution family in
  `src/aeris/mesh/surface.py:170` (`uniform/cosine/cluster_*/tanh`) with a learned
  free-form monotone parametric-coordinate field. Three guarantees by
  construction: predict in PARAMETER space so exact-wall fidelity is inherited
  (nodes re-evaluated on the pyGeo curve at tracked parametric coords); monotone
  via positive increments + cumsum so no surface tangling; volume still audited by
  `volume_audit`/`quality`. AI-native part = differentiable mesh-quality loss
  (scaled Jacobian/skewness/AR/growth are differentiable), so self-supervised
  refinement needs NO reference mesh and can use the full 10,000-design pool.
  Flow surrogate + mesh-fingerprint-leakage study deferred until CFD converges.
- **Agent framing (2026-08-30):** P1+P2 are two halves of one meshing agent.
  **Corrected attempt accounting:** of 162 attempts, 127 are up to first PASS and
  **35 are spent AFTER a PASS** searching for higher quality — the loop has two
  thresholds (`preferred_quality` 0.15, production floor 0.1) and no stopping
  rule. Failures are THREE classes, not one: SURFACE_BUILD_ERROR 14 (pre-extrusion),
  FAIL_folded 19 (inverted>0), FAIL_low_quality 13 (valid, 0 inverted, below floor).
  **Decisive case `lhs100_seed42_095`:** 21 attempts, first attempt (0.147) was the
  BEST of all 21, accepted 0.1468 after scanning the whole atlas — it fell 0.003
  short of the 0.15 preference and nothing told it 0.147 was the ceiling. A
  stopping-rule failure, not a meshing failure.
  Agent's new content beyond P1/P2 = failure-conditioned next action (the
  `volume_audit._cluster_report` diagnostic — block, layer range, j/i range,
  `on_spanwise_edge`, `wall_adjacent`, wall bbox — is recorded but NEVER used to
  pick the next attempt) + a learned stopping rule.
  **Key link:** the atlas has a per-geometry quality CEILING no routing policy can
  exceed; P1 finds it faster, P2 raises it.
  Scope honestly: contextual bandit / imitation, NOT deep RL (162 attempts; even
  5,000 is not deep-RL territory). NOT an LLM agent — 20-dim numeric decision
  space, and it would forfeit S6's reproducibility covenant.

## AERIS_MESH_AGENT — paper built end to end (2026-08-30)

- **Folder `AERIS_MESH_AGENT/`** (new top-level): `src/mesh_agent/` (ledger,
  features, outcome, policy, paths), `experiments/exp01..exp05`, `tests/`,
  `paper/PAPER.md` + `build_paper.py`, `runbook/`, generated `tables/ figures/
  results/`. Reproduces in ~12 min, CPU only. **Set `OMP_NUM_THREADS=1`** —
  HistGradientBoosting on 247 rows oversubscribes 12 cores and runs 60x slower
  (25 CPU-min vs 24 s).
- **Dataset:** pooled production config `eps_e 1.5 | 3.6e-06 | 257 | production`
  = 384 attempts, 100 geometries, 21 templates, **247 of 2100 cells (11.8%)**,
  **0 conflicts** across overlapping campaigns (determinism verified).
- **KEY DISCOVERY:** the atlas baseline is NOT a blind scan —
  `development_atlas.py` does `ordered_slots = np.argsort(distances[index])`,
  i.e. nearest-template-first in normalised design space. Any learned routing
  must be compared against that heuristic, not a strawman.
- **Templates ARE geometry indices** from the same lhs100_seed42 pool
  {2,8,16,24,29,41,42,43,47,56,65,68,70,81,85,88,89,90,92,94,95}, so campaigns
  with different candidate_counts pool cleanly.
- **Results:** atlas 162 attempts -> **114** (-29.6%) with learned ranking +
  ceiling stopping on **design variables alone**, quality -0.30%, first-attempt
  74%->90%, worst case 21->4. Oracle = 100. Ablation: stopping rule ALONE with no
  model = 127 (-21.6%) but costs -2.79% quality. Wall-clock only 48->38 min
  (-21%) because saved attempts are the cheap failures; 36 of 48 min is
  irreducible (one successful extrusion per geometry).
- **exp02:** design-only PASS AUC 0.891, quality Spearman 0.756; +surface
  features raise Spearman to 0.843 but NOT AUC (0.894) — feasibility is
  predictable from the design vector alone; the surface build buys only ranking
  precision, and did not win on policy cost.
- **Honest limits stated in the paper:** restricted replay (policies may only
  reorder templates the atlas actually tried -> lower bound); selection bias in
  which cells exist; **no infeasible geometry in the data** (100/100 pass
  eventually) so the claim is routing COST, never meshability.
- **Runbook `runbook/RUNBOOK_matrix_completion.md`:** Campaign A completes the
  100x21 matrix in **~8 h mesh-only** via the trick `--preferred-quality 1.01`
  (unreachable, so nothing accepts early and every template is attempted);
  resume is default; do NOT pass `--retain-written-meshes`. Campaign B widens the
  design space for a real feasibility boundary. Campaign C varies `eps_e`.
- Hold-out `round_c_lhs10_seed42` untouched; a test tokenises src/experiments to
  prove the name never appears as live code.
- **Robustness (exp04, 20 grouped partitions):** learned ranking + ceiling
  stopping = 112.8 +/- 3.4 attempts (range 107-119) vs atlas 162 — spread an
  order of magnitude below the saving. accept-first-valid is cheaper (106.0 +/-
  1.7) but gives up 1.2% quality, so it is reported, not headlined. Both exp03
  and exp04 select their headline under a **0.5% accepted-quality constraint**;
  selecting on attempts alone silently rewards buying speed with quality.
- 9 invariant tests in `tests/test_mesh_agent.py` guard the claims (determinism,
  no template invention under restricted replay, nothing beats the oracle, no
  acceptance below the floor, stopping never costs attempts, out-of-fold really
  holds out its own geometry, hold-out name never appears as live code).
- Not committed to git — build is complete and reproducible; commit when Mike asks.

## S7 unstructured: coarse confirmation made executable (2026-08-31)

- **The job:** ROADMAP step 1, confirm **Newton-Krylov** at `coarse` (1.55 M
  cells). Not multigrid — that is refuted and is *bypassed entirely* under
  `NEWTON_KRYLOV` (byte-identical histories). Shortlist, cheapest first:
  `G_nk_cfl`, `I_combined`, `F_nk_linear`. `J_nk_no_mg` is a duplicate of
  `I_combined` and must not be run.
- **`solver_tuning.py` can now do it.** It was 10 variants, 4 in parallel, serial
  SU2, unconditional `rmtree` — none of which survives 1.55 M cells. Added:
  `--shortlist` / `--variants`, `--ranks` (mpirun), `--from-case-dir`, a memory
  plan that **refuses** rather than OOMs, sequential default above 250 k cells,
  and an immutable resumable run root (`request.json` identity + per-variant
  `result.json`; a part-way directory is reported, never deleted).
- **Memory law, measured:** `1.20 GiB per rank per million cells` — each rank
  reads the whole mesh before partitioning. At coarse that is 1.86 GiB/rank, so
  **4 ranks = 7.44 GiB is the desktop recommendation** and 8 ranks reproduces the
  recorded OOM. Concurrency multiplies both ways (workers x ranks).
- **Cost, measured** by differencing 5- and 25-iteration probes (65 s, 174 s):
  **5.45 s/iteration on 2 ranks**, 37.8 s startup → 6 000 iters = 9.1 h/variant
  at 2 ranks. The 4-rank speedup is **assumed 1.8x, not measured** (guide M1A).
- **DEFECT 11 — defect 10 recurring one resolution up.** Smoke histories start at
  -2.576..-2.687; **coarse starts at -3.6643**, so it must reach **-9.6643** to
  drop six orders. The stop of -9.0 (derived from `assumed_worst_initial: -3.0`,
  calibrated on smoke) truncates it at 5.336 orders and it is then rejected as
  `insufficient_residual_drop` — indistinguishable from a failed solve. Fixed:
  assumption -3.0→**-4.0**, stop -9.0→**-10.0**, and structurally,
  `su2_pipeline.residual_gate` now derives the required final **from each run's
  own initial residual** and reports `solver_stop_truncates_drop_gate`. The reason
  provably cannot fire on a run that would pass; verified on the real coarse
  history (fires under the old stop, clears under the new).
  **Neither acceptance threshold has ever changed** (drop 6.0, final -8.0).
- **Cost consequence, not to be wished away:** smoke needed 5 872 iterations to
  reach -9.5 and coarse asks -9.6643 with 36x the cells, so **6 000 iterations may
  land short**. Extend the budget; do not lower the gate.
- **New doc:** `AERIS_MESH_STUDY/AERIS_S7_UNSTRUCTURED_CFD_MASTER_EXECUTION_GUIDE.md`,
  written in the shape of the S6 master guide Mike pointed to. Milestones M0–M6
  with stop/go gates, per-run preflight, failure handling, permitted claims. Key
  stop/go: a variant *still descending* at the iteration budget has NOT failed —
  that misreading is exactly what the multigrid episode was.
- Per S6 guide §16, S7 stays outside the Paper 1 critical path and earns a matched
  comparison only by independently passing mesh, y+, convergence and grid gates.
- 51 tests pass, ruff clean. Not committed; awaiting Mike.
