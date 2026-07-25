# Study — Native pyGeo→AVL: output completeness, geometry fidelity, and equivalence with the AeroSandbox path

Date: 2026-07-25
Decision produced: `decision/0005-native-avl-output-and-geometry-fidelity.md`
Scripts: `standalone/lowfi_avl_study/{probe_span_margin,verify_native_vs_asb}.py`
Evidence: `configs/aero/native_avl_verification_evidence/`

## 1. Question

Task 1 of the low-fidelity hardening pass asked three things:

1. Does the pyGeo→AVL chain run clean on `configs/geometry/bwb.yaml`?
2. Does the native runner capture **everything** AVL can export — span efficiency
   e, neutral point Xnp, all stability derivatives, per-strip data?
3. Do those fields agree with the AeroSandbox reference solver?

Confirming (1) is what exposed the two geometry-fidelity defects that dominate
this write-up.

## 2. Method

All runs use the one unified geometry config `configs/geometry/bwb.yaml` at its
default seed (small BWB ISR UAV: full span 1.63 m, Sref 0.644 m², AR ≈ 4.1,
mh91/mh91/e374/nlf1015, washout −0.31° root → −5.4° tip, elevon band 0.60–0.95 of
semi-span). Freestream 28 m/s, sea level, Mach 0.082.

Both solvers are driven from the **same** pyGeo realized `ExtractedSection`
objects, so any difference between them is solver plumbing, not geometry:

- **native** — `run_pygeo_native_avl_case` → `native_avl.py`, which authors the
  `.avl` directly and never constructs an `asb.Airplane`;
- **ASB reference** — `run_pygeo_avl_case` → `AeroSandboxAVLSolver`, which uses
  AeroSandbox purely as the AVL serializer.

Paneling matched at 8 chordwise × 4 spanwise panels per section interval
(192 strips, 1536 vortices in both). Viscous correction on in both:
CDCL injection from per-section CST NeuralFoil polars + independent strip
profile-drag integration, `cd_total = cd_ind_AVL + cd_profile_NeuralFoil`.

Three operating points decompose the comparison:

| case | α | β | δe | δa | isolates |
|---|---|---|---|---|---|
| A | 3° | 0° | 0° | 0° | pure geometry + viscous chain |
| B | 3° | 0° | 4° | 0° | symmetric (pitch) control |
| C | 3° | 2° | 0° | 2° | sideslip + differential (roll) control |

## 3. Assumptions and their justification

- **AVL's Trefftz-plane e and the strip integration are taken as-is.** No
  attempt is made to correct AVL's inviscid core; the viscous model is the
  documented CDCL + strip-polar bridge.
- **The moment reference is the geometry origin (0,0,0), not a CG.** No mass
  model exists yet, so a static margin cannot be formed. The study reports
  `Xnp/Cref` and explicitly refuses to call it a static margin.
- **Sections are extracted at uniform span fractions.** Whether 25 is enough is
  deliberately *not* claimed here — that is the separate section-convergence
  study (Task 4a). Every number below is at fixed 25 sections, so the comparisons
  are like-for-like.
- **e at low CL is ill-conditioned.** This wing's zero-lift angle is ≈2.2°, so at
  α=3° CL ≈ 0.05 and e = CL²/(π·AR·CDff) divides two small numbers. e is used
  here only for *relative* comparison at identical CL, never as an absolute
  quality metric.

## 4. Result 1 — the chain runs, and the capture is now complete

Field-by-field comparison of the native result against the ASB result
(`verify_native_vs_asb.py`): fields present in the ASB result but **missing from
the native result: NONE**.

The native runner now dumps and parses `ft`, `fn`, `fs`, `vm`, `fb`, `hm`, `st`,
`sb` (and optionally `fe`), yielding: all totals + **e**, **Xnp**, 25
stability-axis derivatives, 18 body-axis derivatives, per-control authority
derivatives (CL_δ, CY_δ, Cl_δ, Cm_δ, Cn_δ, CDff_δ, e_δ), hinge moments,
per-surface force breakdown, the full strip table, and the spanwise
shear/bending distribution. Everything lands in `native_avl_result.json`.

Parsing was consolidated into one AeroSandbox-free module
(`aeris/aero/solvers/avl_output.py`) used by **both** solvers, unit-tested against
verbatim AVL dumps (`tests/aero/test_avl_output_parsers.py`, 12 tests).

## 5. Result 2 — the extraction span margin was corrupting every number

**Finding.** The section extractor defaulted to a 2 % inset at both span ends.
Under `YDUPLICATE` the innermost section at y > 0 is mirrored about y = 0, so the
AVL model was two half-wings separated by a **32.6 mm centreline gap**, shedding a
spurious inboard tip-vortex pair, with the tip simultaneously truncated.

| margin | gap (m) | CL | CLα /rad | e | L/D visc | Bref (m) |
|---|---|---|---|---|---|---|
| 0.02 | 0.0326 | 0.02230 | 2.741 | 0.316 | 3.39 | 1.5666 |
| 0.01 | 0.0163 | 0.02657 | 2.863 | 0.334 | 4.01 | 1.5992 |
| 0.005 | 0.0082 | 0.03021 | 2.982 | 0.358 | 4.52 | 1.6156 |
| 0.001 | 0.0016 | 0.03842 | 3.288 | 0.437 | 5.70 | 1.6286 |
| 1e-4 | 0.0002 | 0.04729 | 3.632 | 0.537 | 6.94 | 1.6315 |
| **0.0** | 0.0000 | **0.04945** | **3.715** | **0.562** | **7.25** | **1.6319** |

The old default understated CL by 54.9 % and the lift-curve slope by 26.2 %, and
halved L/D. The error is monotonic in the gap and reaches zero only at margin
exactly 0. Note that even the 1e-4 margin used for geometric metric extraction
costs 2.2 % of CLα — the VLM is far more sensitive to a centreline slot than any
integrated geometric metric is, so "small enough for metrics" is not small enough
for aerodynamics.

**Physical cross-check.** CLα = 3.72 /rad for a swept AR ≈ 4.1 wing sits where
lifting-line with a sweep correction puts it (≈4.2 /rad unswept at AR 4.1,
reduced by the ~30° inboard sweep). 2.74 /rad does not correspond to any
plausible wing of this planform. The full-span value is the physical one.

**Fix.** `span_margin` defaults to 0.0, and the runner emits a warning whenever
the innermost section sits above 0.1 % of semi-span so the defect cannot return
silently (regression-tested).

## 6. Result 3 — the elevon did not span its own geometric extent

**Finding.** AVL interpolates a control's gain linearly between sections, so a
band edge exists only where a section declares the control. The writer tagged only
the inboard section of each interval, so the gain tapered 1→0 across the
outboard-most interval and part of the elevon was silently lost. Worse, the extent
was quantised to whatever the uniform section grid happened to bracket — meaning
the DoE's three elevon design variables would have driven a **staircase** control
response rather than a smooth one, which is hostile to gradient-based
controllability optimisation.

**Fix.** Two sections are snapped exactly onto `elevon_start_frac` /
`elevon_end_frac`, and every section inside the band including both boundaries is
tagged.

| quantity | before | after | change |
|---|---|---|---|
| CL_δe (/deg) | 0.00810 | 0.00945 | **+16.7 %** |
| Cm_δe (/deg) | −0.004399 | −0.005138 | +16.8 % |
| tagged span (fraction of semi-span) | 0.600–0.917 | **0.600–0.950** | matches geometry |

**Residual, stated honestly.** A perfectly sharp cutoff needs duplicated break
sections at the band edges. Without them the gain still tapers across the
half-interval just outside each edge — about 6 % of elevon span at 25 sections,
shrinking as sections increase. This couples directly to the section-count study
(Task 4a) and is quantified there rather than asserted away here.

## 7. Result 4 — native vs AeroSandbox equivalence

**Case A (clean symmetric) — the two paths are equivalent.** Every shared field
agrees to ≤ 0.6 %, and the physics-carrying quantities agree far better:

| field | native | ASB | rel. diff |
|---|---|---|---|
| CLα | 3.71522 | 3.71522 | 8e-7 |
| Xnp | 0.232674 | 0.232672 | 1e-5 |
| CZw | −3.71588 | −3.71591 | 8e-6 |
| Clp | −0.293196 | −0.293211 | 5e-5 |
| CD (viscous total) | 0.0068231 | 0.0068266 | 5e-4 |
| cd_profile | 0.0065092 | 0.0065097 | 8e-5 |
| e | 0.5615 | 0.5626 | 2e-3 |
| Cmq | −3.50932 | −3.51820 | 2.5e-3 |
| CL | 0.04945 | 0.04971 | 5.2e-3 |

The residual ~0.5 % in CL comes from airfoil discretisation: the native writer
emits 80-point-per-surface CST loops (AVL's IBX limit forces downsampling) while
AeroSandbox emits ~181, giving a ≈0.05° difference in effective camber line. Both
paths write identical CDCL blocks and near-identical CLAF values (1.1154674 vs
1.1154678), confirming the viscous and thickness corrections are the same model
in both.

**Cases B and C — the ASB reference path has two structural control-modelling
limits.** These are findings about the reference, not native defects:

- **It cannot deflect an elevon differentially.** AeroSandbox's AVL exporter
  collapses all control surfaces into one variable, `all_deflections`, with
  SgnDup +1; AVL reports `1 Control variables`. The `d2` keystroke addresses a
  variable that does not exist and is silently ignored. Measured at δa = 2°,
  β = 2°: native Cl_roll = −0.00583, ASB Cl_roll = −0.00093 — exactly the
  sideslip-only contribution (β·Clb = −0.00091), i.e. **zero roll authority**.
  The native decomposition checks out: 2°·Cl_δa (−0.002449) + β·Clb = −0.00581
  vs −0.00583 measured.
- **Its elevon over-extends to the wing tip** (tagged span 0.600–1.000 vs the
  geometry's 0.600–0.950), leaving ~6 % more pitch authority than the geometry
  supports.

## 8. Conclusions

1. The native pyGeo→AVL chain runs clean and now captures the complete AVL output
   family; nothing the ASB path reports is missing from it.
2. For the clean symmetric case the two paths are numerically equivalent
   (≤0.6 %, key derivatives to 1e-5), so the native path is a validated
   replacement, not an approximation of the reference.
3. The native path is strictly more capable: it is the only one of the two that
   can model differential (roll) elevon deflection, which is precisely what the
   DoE's elevon design variables exist to optimise. The ASB path is retained as a
   symmetric-case cross-check only.
4. Two geometry-fidelity defects were found and fixed. Together they moved CLα by
   +36 %, L/D by +114 %, and elevon pitch authority by +17 %. **Low-fidelity aero
   results generated before 2026-07-25 must be regenerated.**

## 9. What this study does NOT establish

- That 25 sections are enough (Task 4a) or that 8×4 panels are enough (Task 4b).
  Every number here is at that fixed discretisation.
- That the baseline seed is representative of the design space (Task 5); all
  results are one geometry.
- Any absolute validation against experiment or CFD. This is a code-to-code
  equivalence and internal-consistency study only.
- That e ≈ 0.56 is a meaningful efficiency for this wing — at α = 3° it is
  evaluated near zero lift where it is ill-conditioned.
