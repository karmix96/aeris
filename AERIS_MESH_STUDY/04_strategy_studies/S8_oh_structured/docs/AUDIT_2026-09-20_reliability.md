# S8 reliability and validation audit — 2026-09-20

An adversarial read of S8 against its own artifacts. Every number below was extracted from
`reports/`, `runs/` or `data/` in this audit, not copied from the prose. Where the prose and the
JSON disagreed, the JSON won; where the JSON and the raw solver output disagreed, the raw output
won, and both cases are recorded as findings.

Method note: the brief for this audit supplied several figures. Four of them turned out to be
wrong, and they are corrected in [§7](#7-corrections-to-the-brief) rather than repeated. Nothing
here rests on a number the brief provided.

---

## 1. Verdict

**S8 can answer questions about lift, pitching moment and neutral point, and it can rank wings
whose drag differs by more than about ten counts. It cannot resolve the 5–9 count effect it was
built to measure, and the reason is no longer an absence of evidence — it is a measurement.**

The central claim is the trailing-edge credit: −5.27 to −8.98 counts across ten wings, mean −7.26
(`docs/S8_REPORT_2026-09-15.md:1520-1531`). Every one of those numbers is measured at `gci_C`. On
geometry 83 — the only wing carrying both the χ-3 baseline and the treatment at both grid levels —
the same measurement repeated at `gci_M` gives **−2.05 to −3.03 counts** against `gci_C`'s **−8.11
to −9.15**. The credit loses **67–74 % of its magnitude** on the one grid refinement the campaign
possesses, in the same direction at all four incidences (`reports/s8_te_credit_grid.json`,
produced by `te_credit_grid.py`, whose `gci_C` column reproduces the published table exactly).

That is the finding that decides this audit. The campaign has relied on discretisation error
cancelling in a difference between two configurations on the same grid. **It does not cancel.** The
non-cancelling part is 5.5–6.2 counts, which is the size of the entire effect. And with two levels
there is no way to say whether the credit continues toward zero, stabilises near −2.5, or changes
sign.

What is genuinely sound: iterative error is negligible and now proven on every production run
(≤0.017 % on C_D, §4.2); lift and moment are grid-converged; mass conservation is excellent; the
credit is a real profile-drag effect and not a lift change in disguise (ΔC_L ≤ 0.0005, worth
≤0.23 counts of induced drag). The instruments — `gci.py`, `convergence_gate.py`,
`gci_four_level.py` — are honest and refuse what they should, and this audit confirmed that by
feeding them the study's own divergent data.

What is not sound is the drag error model, and the brief's framing understates the problem in one
important way: the missing third level is not the first obstacle. **The wall-normal direction
diverges** (§3.3), and a third *global* level refines that direction too.

Resolvable today: drag differences ≳ 10 counts; orderings; lift; moment; neutral point.
Not resolvable: absolute drag (still moving 22–25 counts per refinement); any difference below
~10 counts; the 1-count materiality gate, which the report itself already retracted
(`docs/S8_REPORT_2026-09-15.md:1645`) but which is still live in the queues
(`docs/S8_REPORT_2026-09-15.md:636,750`).

---

## 2. Every validation study

Relevance is judged against AERIS's actual operating point, read off a run rather than from the
prose: **Ma 0.0837, Re 1.53e6 on a 0.9 m reference chord, aspect ratio 4.84, 3-D half model**
(`runs/s8_v2/g83/gci_C_a0/result.json`).

| # | Case | What it tests | What the artifact shows | Pass? | Relevant? |
|---|---|---|---|---|---|
| 1 | **TMR flat plate**, SU2, 13,056 and 208,896 cells, compressible + incompressible | solver vs CFL3D/FUN3D *on the same grid* | c_f error +0.77 %, +0.65 %, −0.04 %; C_D error +0.21 %, +0.32 %, +0.55 % (`reports/s8_su2_validation.json`) | **Yes** | Verification only, not validation — no measurement involved. 2-D zero-pressure-gradient; says nothing about pressure drag |
| 2 | **NACA 0012**, ADflow, TMR Ma 0.15 Re 6e6 α 10°, 3 grids | solver vs CFL3D/FUN3D SA, **with a reference drag split** | Total C_D +2.67 %. The split: **CDp +6.06 %**, CDv −0.65 %. Observed order per quantity: C_L **0.83**, C_D 2.75, CDp 3.23, CDv **non-monotone**. CM: GCI 49.5 %, extrapolate **+38.96 %** vs reference (`reports/s8_naca0012_tmr.json`) | **Partly** — total passes, split does not, moment fails | Re 4× high, but the only case anywhere with a reference CDp. **The most important row in this table** |
| 3 | **NACA 4412**, ADflow, Ma 0.09 Re 1.52e6 α 13.87°, 3 grids | solver vs CFL3D/FUN3D SA *and* vs experiment | C_D inside the SA band (+1.35 % vs mid); CDv +0.035 %; separation x/c 0.796 vs CFL3D 0.789. C_L **outside** the band (+1.34 %), Richardson non-monotone. c_p minimum: CFD −7.55, CFL3D −7.45, **experiment −6.21** (+21.6 %) (`reports/s8_naca4412_tmr.json`) | **Yes vs code, no vs experiment** | **Re 1.52e6 vs AERIS 1.53e6, Ma 0.09 vs 0.0837 — the closest match in the whole evidence base.** 2-D |
| 4a | **ONERA M6 on NASA's grid** (295k) | solver vs AGARD AR-138 pressures | suction peak 1.06 %, shock 0.014 x/c, RMS Δc_p 0.149 (`…_comparison_nonk.json`). The NK variant gives RMS Δc_p **0.324** — only the non-NK number is quoted | **Yes** | Transonic Ma 0.84, Re 11.7e6. **Wrong regime** |
| 4b | **ONERA M6 through our mesher** (955k) | **our mesh** vs measurement | suction peak **2.61 %** (criterion 2 %), shock **0.0214 x/c** (criterion 0.02), RMS Δc_p 0.0744 (`reports/s8_onera_m6_our_mesh.json`) | **No — misses both pre-set criteria**, as the report states | Transonic. **This is the only test of the mesher against measurement, and it fails** |
| 4c | **M6 sectional loads** | integrated measured normal force | span-integrated **+5.26 %**; worst station **η 0.2, +16.0 %**; η 0.99, −14.6 % (`reports/s8_onera_m6_loads_run_L0_nonk.json`). At full CFD resolution the span-integrated difference is **+12.0 %** | **Marginal** | Transonic — but the worst station is **inboard**, which on a BWB is most of the area |
| 5 | **Eppler 387**, SU2, Re 200k, vs McGhee TM-4062 | transition + laminar separation bubble | SA-LM: C_D −3.17 counts (−2.7 %), C_L +1.9 % — but `within_measurement_uncertainty` is **false** for both, the bubble is **0.470→0.584** against measured **0.43→0.67** (half the length), and momentum residuals **rose 6.5 orders**. SST-LM: C_D **+57.2 counts (+48.5 %)**. Gate: **NOT_ACCEPTED**, 84.70 counts of wander (`reports/s8_su2_validation.json`; gate re-run in this audit) | **No** | Re 200k is **7.7× below** AERIS, not near it (see §7). The two transition models disagree by **60 counts on a 118-count total** |
| 6 | **Transitional flat plate `fp_bc`** | transition onset vs turbulence intensity | onset Re_x 2.59e6 at c_f 4.19e-4 — correct laminar Blasius value. Gate: ACCEPTED. But `"reference": "experiment to be added before this is judged"` | **Unverifiable** | The ✓ in `SU2_REPORT_2026-09-18.md:208` is against an *expectation*, not data |
| 7 | **ERCOFTAC T3A / T3A−** | bypass transition | Not completed; reference server offline. Both **NOT_ACCEPTED**: forces identically **0.0**, residuals **rose** 8–9 orders. T3A− finds no transition and its c_f sits flat near 2.0e-3 (`SU2_REPORT_2026-09-18.md:213`) | **No** | Flagged not graded, correctly |
| 8 | **Grid refinement**, `gci_C`→`gci_M` | discretisation error | Two levels. C_D moves **22.3–24.8 counts** (3 wings, family B) / 28.1–29.8 (family A). No observed order, no GCI. §3 | **Trend only** | Directly relevant |
| 9a | **Chordwise family**, 3 levels | directional order | **The only observed order in the study**: p = **3.20** for C_D and CDp, GCI_fine 5.46 % (9.6 counts); C_L oscillatory, p = 2.45 (`reports/s8_chord_gci_a0.json`) | **Yes, with caveats** | Directly relevant. Holds span/normal at `gci_C` |
| 9b | **Wall-normal family**, 3 levels | directional order | **DIVERGENT.** C_D 208.24 → 209.13 → 213.33; step grows 4.7×. `gci.py` returns p = −5.97 and `certified_uncertainty_percent: null`. §3.3 | **No — no limit demonstrated** | Directly relevant. **The most damaging technical fact in S8** |
| 9c | Spanwise / edge single steps | error decomposition | span recovers 11 %, edges 7 %, chord 88 %, normal −15 % of the CDp gap (`reports/s8_directional_refinement.json`) | n/a | Relevant |
| 10 | **Iterative convergence** | is 1e-6 enough? | Worst force movement beyond 1e-6 is **0.023 % on C_D** over 3 geometries (`reports/s8_l2_revalidation.json`). All **52** production runs pass the gate, C_D settled to ≤0.017 % (this audit, `reports/s8_v2_gate.json`) | **Yes** | Relevant. **Genuinely closed** |
| 11a | **Mass balance** | conservation | relative imbalance ~1e-7, wall leakage ~2e-9, symmetry leakage ~2e-6 (`reports/s8_mass_balance.json`) | **Yes** | Relevant. 8 runs only, family A |
| 11b | **c_p bound** | is the surface resolved? | c_p exceeds its isentropic bound 1.0018 on **12–123 cells of every one of the 52 runs**, peak excess 0.93 → c_p ≈ 1.93, clustered at the **root leading edge**. The tip-cap zone reaches **c_p = −9.48** (`runs/s8_cfd/gci_C_a0/cp_excess_locations.json`) | **No — open on every run** | Relevant, and in the region that sets BWB pressure drag |
| 11c | **Reference area** | defect 23 | Fixed; neutral point unaffected (max change 5.6e-17 m) | **Yes** | Relevant |
| 11d | **Geometry** | mesh vs design vector | 1 of 10 outside tolerance: g12 twist worst error 0.246° against a 0.2° limit; RMS ≤0.075° (`reports/s8_geometry_audit.json`) | **Marginal** | Relevant |
| 11e | **Archive audit** | is the dataset usable? | Was `sound 0 / 52`, all five gate fields missing — because the dataset had lost its pointer to verdicts that existed and were correct (§4.2). After this audit's fix: `sound` is still 0/52, but the **only** remaining finding is y+ | **Bookkeeping fixed here; y+ open** | Relevant |
| 12 | **AVL cross-comparison** | independent lift check | Median \|relative error\| **16.2 / 27.6 / 6.0 / 0.85 %** at α −2/0/4/8; **8 of 40** pairs within ±2 %, all at α 8; max 250.7 % (computed from `reports/s8_reference_area_audit.json` rows and `data/dataset_v2/rows.json`) | **No, as a ±2 % claim** | Relevant. `verify_against_avl.py:23` sets the honest bar: "within about ten per cent is a good result" |
| 13 | **Transition sensitivity** (NeuralFoil) | is fully-turbulent an upper bound? | ratio median 1.568, **min 0.457**, max 1.967, n = 88 (`reports/s8_transition_sensitivity.json`). Values <1 are the low-Re tip sections (Re 171k) | **Reasoning correct; not a bound** | Relevant. But NeuralFoil's own `confidence_mean` is **0.30** on the fully-turbulent branch vs 0.96 free — the numerator is the untrustworthy half, and no document mentions this |
| 14 | **SU2 cross-solver** | second opinion | **4 of 10 accepted** (`SU2_REPORT_2026-09-18.md:270-280`; independently reproduced in this audit by re-running `su2_gate()`). **No converged SU2 solution on any AERIS wing** — confirmed | **Partly** | The accepted four are flat plates. Nothing in AERIS's geometry class |

**Relevance summary.** Of fourteen studies, one is at AERIS's Reynolds and Mach number (NACA 4412,
2-D), one is 3-D against measurement (ONERA M6, transonic, and it *fails* on our mesh), and none
is a low-speed 3-D wing. That gap cannot be closed with the artifacts in this repository — no such
dataset exists publicly — so the honest position is that the 3-D low-speed mesher is **unvalidated
against measurement**, and the M6-on-our-mesh failure is the nearest available evidence about it.

---

## 3. The grid work

### 3.1 Two mesh families share the same level names

The single biggest provenance hazard in S8, and it is not recorded anywhere. `gci_C` and `gci_M`
each name **two different meshes**:

| | `gci_C` cells | `gci_M` cells | `o_out` layers | tip-cap first cell |
|---|---|---|---|---|
| **Family A** — `runs/s8_gci83`, `runs/s8_pilot`, `runs/s8_cfd`, `runs/s8_aniso`, `runs/s8_checklist` | 567,256 | 1,111,152 | 48 / 49 | **10.20 × s0** |
| **Family B** — `runs/s8_v2` (the 52-run production campaign) | 603,592 | 1,172,856 | 54 / 55 | **2.04 × s0** |

Family A carries the tip cap that was declared defective on 13 September (y+ 2.9–4.5, against a
mandatory y+ ≤ 1); family B carries the rebuilt one. The difference is worth **5.4–7.2 counts of
C_D at `gci_C`** and 0.4–1.4 at `gci_M`, i.e. the size of the effect being measured.

**Consequence, and it is first-class: the entire grid-uncertainty evidence base is on family A.**
The two-level trend, the directional decomposition, the chordwise three-level GCI, the divergent
wall-normal family, the L2 sensitivity study and the mass balance were all measured on meshes with
the defective cap, and **none has been re-run on the corrected meshes**. The production campaign,
which is what the engineering conclusions are drawn from, is family B. So the error bar and the
number it is attached to come from different meshes. This is the direct answer to the brief's
question about defect timing: *the dataset was re-run after the cap fix; the verification was not.*

A reader cannot tell the families apart, because "`gci_C` = 208.2 counts" (family A,
`reports/s8_gci_a0.json`) and "`gci_C` = 201.7 counts" (family B,
`reports/s8_gci_four_level_g83.json`) are both true and both unlabelled. The raw runs resolve it:
`runs/s8_cfd/gci_C_a0/result.json` gives 208.237, `runs/s8_v2/g83/gci_C_a0/result.json` gives
201.737. Defect ledger entry "16 Sept — the wall-resolved tip cap silently added 6.3 % cells"
records the cause but not that it split the evidence base in two.

### 3.2 The refinement ratio: r = 1.3 is not defensible, and the study already knew

Three documents in this folder hold the correct position:

> `docs/AUDIT_2026-09-05.md:392` — "Using the global r_h is the conservative choice: a smaller r
> widens the GCI band, so the reported uncertainty errs high. **Claiming r = 1.300 while the domain
> refines at 1.25 would err the other way**, and an earlier draft of this document did exactly that
> by quoting only the local spacing ratios below."

> `docs/PLAN_desktop_campaign.md:181` — "`gci.py` takes the ratios from the cell counts; **do not
> pass 1.300**."

> `docs/STATUS_AND_NEXT_STEPS.md:167` — "**Use the GLOBAL refinement ratio, not 1.300.**"

The 17 September addendum reverses all three:

> `docs/S8_REPORT_2026-09-15.md:1672` — "So the family meets the r >= 1.3 that Celik and the ASME
> procedure ask for" … "an earlier draft of this addendum got that wrong."

**The addendum is wrong and the 5 September audit was right.** ASME V&V 20 and Celik define r on
the *representative* cell size h = (Σ ΔV_i / N)^(1/3), which is a whole-domain quantity — so the
cell-count cube root is the ratio the procedure asks for. The addendum's observation that the
near-wall node arrays refine at 1.300 is true and beside the point; the outboard extrusions do not,
and they are 49 % of the cells at `gci_C`. The global ratio is **1.2479** (family B) or **1.2512**
(family A). **Celik's r ≥ 1.3 is not met.**

The reversal was not confined to prose. `reports/s8_gci_four_level_g83.json` recorded
`refinement_ratio_from_cells: 1.2479` and then passed **1.3** into the band, which is the one
substitution that makes the reported uncertainty *smaller*:

| quantity, α 0 | band at r = 1.3 (as shipped) | band at r = 1.2479 (correct) |
|---|---|---|
| C_D | 54.83 % | **67.89 %** |
| CDp | 104.72 % | **129.67 %** |

*Fixed in this audit.* `gci_four_level.py` now uses the global ratio, records
`refinement_ratio_used`, and adds an explicit `asme_r_requirement` block reporting `met: false`.
`reports/s8_gci_four_level_g83.json` has been regenerated and verified byte-equivalent to the
tool's output.

Note also that the report quotes a third ratio, **1.274**, for the extrapolations at
`S8_REPORT_2026-09-15.md:1660` — reproducible only by assuming it, and derivable from no artifact.
The p = 2 extrapolate at α 0 is 138.6 counts at r = 1.2479, 142.9 at r = 1.274 and 146.4 at
r = 1.300: **the choice of ratio alone moves the answer by 7.8 counts**, which is the effect size.

### 3.3 The wall-normal direction diverges, and that outranks the missing third level

Confirmed, and the numbers are the report's (`S8_REPORT_2026-09-15.md:573`). At α 0, refining only
the wall-normal direction at fixed first-cell height, on family A meshes:

| level | `o_wing` shape | cells | C_D (ct) | CDp (ct) | CDv (ct) |
|---|---|---|---|---|---|
| `gci_C` | [93, 65, 49] | 567,256 | 208.237 | 118.278 | 89.959 |
| `gci_C_normal_s0` | [93, 84, 49] | 741,120 | 209.134 | 122.208 | 86.926 |
| `gci_C_normal_s0_2` | [93, 109, 49] | 972,024 | **213.330** | **128.516** | 84.813 |

Steps on C_D: **+0.90 then +4.20 counts. The step grows by 4.7×.** Node ratios 1.292 and 1.298, so
the family itself is clean. Fed to the study's own `gci.py`:

```
cd :  p_observed = -5.97   certified_uncertainty_percent = null
      "DIVERGENT: |f1-f2| = 0.0004196 is not smaller than |f2-f3| = 8.97e-05 …
       This family has no demonstrated limit … No GCI."
cdp:  p_observed = -1.74   certified_uncertainty_percent = null    (also DIVERGENT)
cdv:  p_observed =  1.46   GCI 6.73 %  (the one convergent quantity)
```

**What a diverging direction does to the whole claim.** Richardson extrapolation and the GCI both
assume the solution is in an asymptotic range. One direction demonstrably is not. Therefore:

- No GCI is valid for the *global* family, even with a third level, until this is resolved — a
  global refinement refines the wall-normal direction too.
- The chordwise three-level GCI (p = 3.20, the study's only observed order) holds the wall-normal
  resolution fixed at `gci_C`'s, which is a value now known to be non-asymptotic. Its 5.46 % band
  is therefore an order in one direction, not an uncertainty on the answer.
- Most sharply: **at essentially the same cell count (~973k), chordwise refinement gives C_D =
  175.42 counts and wall-normal refinement gives 213.33 — a 37.9-count spread**, four to seven
  times the effect. `gci_M`'s 179.8 counts is a partial cancellation of two large errors pulling in
  opposite directions (chord −34.8 counts on CDp, normal +10.2 and growing), neither converged.
  That is why "the curve has not flattened" understates it: it is not obvious the curve has a limit.

`gci.py` refusing this family is the instrument working correctly. The study records the divergence
as "**Open — important**" and that grading is right.

### 3.4 What the two-level band actually is

With the correct global r = 1.2479, p assumed 2.0 and the two-level safety factor Fs = 3, for
geometry 83 (family B, regenerated `reports/s8_gci_four_level_g83.json`):

| α | C_D (ct) | band (%) | band (counts) |
|---|---|---|---|
| −2 | 230.4 | 56.3 | **129.6** |
| 0 | 179.1 | 67.9 | **121.6** |
| 4 | 169.1 | 71.1 | **120.3** |
| 8 | 278.9 | 47.8 | **133.3** |

This is not a GCI and must never be quoted as one — the labels `"study": "TREND_NOT_GCI"` and
`condition: "TREND_ONLY"` are present on every relevant artifact, and **no downstream document
treats the trend as a GCI.** That check passes: `S8_REPORT_2026-09-15.md:566` says "Two levels =
**trend, not GCI**", `:1652` says "Both are indicators rather than a GCI", and
`reports/s8_level_selection.json` says it three times. The brief's concern here is unfounded, and
the discipline is real.

---

## 4. The uncertainty budget

For a **difference between two wings of 5–9 counts**. "In a difference" is the only column that
matters; absolute figures are given for scale.

| Source | Absolute | In a difference | Evidence | Status |
|---|---|---|---|---|
| **Discretisation — the measured one** | 22–25 ct per refinement | **5.5–6.2 ct** | `reports/s8_te_credit_grid.json`: the credit itself moves from −8.1…−9.2 to −2.0…−3.0 | **Measured. Dominant.** |
| Discretisation — common-mode residue | — | 0.85–4.39 ct | `S8_REPORT_2026-09-15.md:1637`, 3 wings | Measured |
| Discretisation — no asymptotic range | unbounded | unbounded | §3.3, wall-normal divergent | **Unbounded** |
| Discretisation — where cells go | 37.9 ct at fixed count | untested | §3.3 | Untested |
| **Artificial dissipation (vis4)** | **−20.6 / +35.1 ct** | **untested** | `AUDIT_2026-09-10.md:469`; `S8_REPORT:610` marks it **pending** | **Largest untested lever** |
| Far field | +4.2 to +5.7 ct (40→100 chords) | untested | `AUDIT_2026-09-10.md:481`. The only JSON, `s8_farfield_sensitivity.json`, records the **smallest** of the three available numbers (40→60 = +0.69 ct) | Under-recorded |
| Freestream turbulence χ | +0.8 to +2.1 ct | **1.3 ct** (fleet spread) | `reports/s8_freestream_turbulence.json`: +0.456 % to +1.186 % | Measured |
| Model form — CDp bias | +3.4 % (SU2) to +6.1 % (ADflow) | ~3.0–7.2 ct if it scales | `s8_naca0012_tmr.json`, `s8_su2_validation.json` | **Both solvers biased the same way** |
| Model form — transition | ratio 0.46–1.97 | untested | `s8_transition_sensitivity.json` | Not a bound |
| Model form — transition model spread | 60 ct on 118 | n/a | E387 SA-LM vs SST-LM | No validated model |
| **Iterative** | ≤0.04 ct | ≤0.04 ct | all 52 runs gated in this audit; ≤0.017 % on C_D | **Closed** |
| Geometry (twist) | ≤0.25° | small | `s8_geometry_audit.json` | Acceptable |
| Reference area | 0 | 0 | defect 23 fixed | Closed |
| c_p above physical bound | unquantified | unquantified | 12–123 cells per run, at the root LE | **Never costed in counts** |
| y+ > 1 on the tip cap | unquantified | unquantified | 1.22–1.85 on all 52 runs | Open |

**Assembly.** Taking only the two components measured *on a difference* — the credit's grid drift
(6.2 counts) and the χ spread (1.3 counts) — gives **≈6.3 counts** in quadrature. Against an effect
of 5–9 counts, **the uncertainty is at least as large as the thing being measured**, before vis4
(untested, ±20–35 counts absolute), the unbounded wall-normal direction, and the cross-solver CDp
bias are counted at all.

**The study cannot currently support its central claim.** The published ten-wing range is a
coarse-grid number, and the only available check says the effect is 3.4× smaller on a finer grid.

Two things this budget does *not* say. The 1-count materiality gate is indefensible by a wide
margin — but the report already says so (`:1645`), so this is a matter of removing it from the
queues, not a new finding. And drag *orderings* survive: `g47 < g13 < g83` at α 0 holds at both
levels, so comparative conclusions with ≳10-count margins stand.

### 4.2 What this audit closed

Two budget lines were open on bookkeeping rather than physics, and both are now closed.

**The shipped dataset asserted an acceptance authority whose verdicts it had lost.** On first pass
this looked worse than it is, and the correction matters: **the gate did run, and it was right.**
All 13 per-geometry `runs/s8_v2/g*/gci_*_gate.json` files existed and were committed, carrying
**52/52 ACCEPTED**. Re-running the gate in this audit reproduced all 52 records identically on
verdict, iteration count and final residual. Nothing about the campaign's convergence was ever in
doubt; what was lost was the *link* between the verdicts and the dataset.

`data/dataset_v2/MANIFEST.json` declared `"authority": "convergence_gate.py"`,
`"accepted_verdicts": ["ACCEPTED"]`, `"excluded": 0` — while all 52 rows carried
`gate_verdict: null` and `missing_fields` saying "convergence_gate.py has not judged this run". The
archive audit reported `sound: 0 / 52` and `test_checkers_reject.py` was **failing on `main`**.

Root cause, traced here and previously unrecorded. The committed verdicts stored
`"directory": "/home/mike_kara/aeris/AERIS_MESH_STUDY/artifacts/s8_v2/g12/gci_C_a-2"` — an absolute
path that was correct when written and **no longer exists**, because the 19 September consolidation
moved `artifacts/` to `runs/`. `dataset_row.build_row` matched with
`Path(directory).resolve() == run.resolve()`, so every match failed. Three gate reports had used
three different conventions (that absolute path, `../../artifacts/s8_cfd/gci_C_a-2`, and
`AERIS_MESH_STUDY/artifacts/s8_cfd/gci_M_a-2`), and none of them survives the tree moving.
**A broken lookup is indistinguishable from an unasked question** in that field, so every row
silently came out "not judged" while the manifest went on asserting acceptance.

This is the consolidation's fourth casualty, after the three the ledger already records
(`fff180a`, "Fix the rest of the paths my consolidation broke"). The difference is that the other
three broke loudly.

And the guard that exists to catch exactly this was switched off. `ACCEPTABLE = ("ACCEPTED",)`, so a
`null` verdict cannot reach the archive unless `--include-rejected` was passed — which means
**defect 25's fix ("missing gate verdict passed the archive filter") was bypassed for the whole
production dataset**, and the MANIFEST had no field in which to record that it had been. The
acceptance block therefore read as though the gate had judged and passed all 52 runs.

Fixed and verified:
- `collect_dataset.py`'s manifest now carries `acceptance_filter_enforced` and
  `rows_without_a_verdict`, so the provenance record can express "collected with the filter off".
  Both now read `true` / `0`.
- `convergence_gate.py` now stores a resolved path plus `run_identity` (`g83/gci_M_a0`).
- `dataset_row.py` matches on the resolved path first and on `<geometry>/<run>` second — never on
  the run name alone, which is `gci_C_a0` for every wing and merges ten geometries (defects 24–26).
- `runs/.gitignore` admitted `!*_gate.json`, which **does not match a file named `gate.json`** — the
  name `convergence_gate.py --out <run>/gate.json` writes, and the name used in the release dataset
  (`build/releases/*/dataset/runs/*/gate.json`). This one is **latent, not the cause**: the
  per-geometry files are named `gci_C_gate.json` and did match. Fixed anyway, because the next person
  to write a per-run verdict into `runs/` would lose it silently.
- The gate was re-run on all 52 production runs and **reproduced the committed verdicts exactly**:
  52 / 52 ACCEPTED via residual target, C_D settled to ≤0.017 %, C_L ≤0.031 %, turbulence equation
  4.07–5.35 orders, none frozen, no dead linear solve. Now also consolidated in
  `reports/s8_v2_gate.json`, and the 13 per-geometry files rewritten with resolvable paths.
- `data/dataset_v2` rebuilt: 52 rows, every one ACCEPTED, **zero missing fields**, physics and
  surface-field hashes bit-identical to before (verified field by field).
- `reports/s8_archive_audit_v2.json` regenerated: all five gate findings gone.
- `test_checkers_reject.py` now **passes, 26/26** (it was 24 of 25 with one hard failure).

**So the iterative-error line of the budget is genuinely closed at ≤0.04 counts**, and it was closed
all along — the verdicts existed and were correct, and only the dataset's pointer to them was
broken. Nothing in the substantive conclusions changes.

What remains serious is not the convergence question but the provenance one. For a day, the shipped
dataset asserted an acceptance criterion that its own rows recorded as unmet, its guard against
exactly that was switched off, and its manifest had no field in which to say so. The gate was
working; the chain of custody was not. That is the failure mode this project's checker apparatus
exists to prevent, and the reason it was not caught is instructive: **every individual artifact was
honest.** The gate reports said ACCEPTED, the rows said "not judged", the archive audit said
`sound: 0`, the test suite went red. Nothing lied. No single file was in a position to notice that
the manifest's claim and the rows' content had come apart.

---

## 5. Where the prose over-claims relative to the JSON

**5.1 The AVL ±2 % claim — refuted by the rows in the same file.**

> `reports/s8_reference_area_audit.json`, field `consequence_retracted`: "Corrected, CFD and AVL CL
> agree to about **+/-2 per cent on every geometry**."

> `docs/S8_REPORT_2026-09-15.md:583`: "| D4 | CFD vs AVL lift | **±2 % on every wing after defect
> 23** | Trusted as corrected |"

The same file's 40 rows, using its own `CL_own_area` and `AVL_CL`:

| α | median \|rel err\| | max | within ±2 % |
|---|---|---|---|
| −2 | 16.16 % | 28.05 % | 0/10 |
| 0 | **33.12 %** | **250.73 %** | 0/10 |
| 4 | 6.12 % | 12.96 % | 0/10 |
| 8 | 0.74 % | 2.29 % | 8/10 |

**8 of 40, all at α 8. Median 12.34 %.** The claim is false, it is asserted inside the JSON as well
as the prose, and `S8_REPORT:583` still grades it "Trusted as corrected". The study's own tool sets
the honest bar: `verify_against_avl.py:23`, "Agreement to within about ten per cent is a good
result; exact agreement would be suspicious." By that bar the α 4 and α 8 results are fine and the
α −2 and α 0 results are not — which is a real finding about near-zero lift, not a failure.

**5.2 "on three grids" — there are two.**

> `docs/SU2_REPORT_2026-09-18.md:138` and `:318`: "SU2 reproduces NASA's flat plate to under 1 % on
> both criteria, **on three grids**, compressible and incompressible."

`reports/s8_su2_validation.json`: `fp_comp_137` = 13,056 cells, `fp_comp_545` = 208,896,
`fp_inc_545` = **208,896**. Two grids, three configurations. `S8_REPORT_2026-09-15.md:1327` gets it
right ("at two grid levels") and `:1394` gets it right ("three configurations"); the SU2 report
does not.

**5.3 The ASME r ≥ 1.3 claim.** §3.2. `S8_REPORT_2026-09-15.md:1672` says the family "meets the
r >= 1.3 that Celik and the ASME procedure ask for"; the global ratio is 1.2479 and the shipped
JSON recorded it as such while passing 1.3 into the band.

**5.4 The far-field budget.** `reports/s8_farfield_sensitivity.json` records only 40→60 chords
(+0.69 counts). `AUDIT_2026-09-10.md:481` records 40→100 chords at **+5.7 / +6.9 counts** (+4.2 /
+4.7 without the cap change). The JSON preserves the smallest of the three numbers and the
uncertainty budget inherits it.

**5.5 The `finished` flag is not a convergence flag.** `reports/s8_su2_validation.json` reports
`"finished": true` for `fp_bc`, whose residuals **rose ~10 orders** in its final leg of 10
iterations, and `"finished": false` with `cf_pass: true, cd_pass: true` for `fp_comp_545`. The
`su2_gate()` verdicts that resolve this — the "four of ten" table at `SU2_REPORT:270` — are
**prose-only**: the string "gate", "ACCEPTED" and "wander" appear **zero** times in the JSON. I
re-ran `su2_gate()` and reproduced the table exactly, so the prose is correct and the *artifact* is
stale. Same direction as 5.1 but inverted: here the JSON is the over-claiming document.
`naca0012_inc_897` carries `"pass": {"CDv": true, "CD": true, "CL": true}` in the JSON while the
gate rejects it on 2.30 counts of wander — and note there is **no `CDp` key in that `pass` dict**,
so the 3.38 % pressure-drag error is not gated at all.

**5.6 `README.md`**: "whether a run was accepted | the same directory's `*_gate.json`" — true for
`runs/s8_pilot`, false for the production campaign until this audit created those files.

**5.7 Internal inconsistency, minor:** `nlf_sst_lm` reports `iterations: 2232` with
`iterations_all_legs: 225`. The total cannot be smaller than the part.

---

## 6. The shortest path to a defensible result

Ranked by cost. **A third grid level is sixth, not first** — and the reason is not cost, it is that
a third global level cannot answer the question that matters while the wall-normal direction has no
demonstrated limit.

**1. Free — no solver time.** Re-measure the credit at `gci_M`. Done in this audit for geometry 83
(`te_credit_grid.py`); it is the finding in §1. Also free: remove the 1-count gate from the queues
(`S8_REPORT:636,750`), correct §5.1–5.6, and label the two mesh families so the error bar and the
number it decorates can be told apart.

**2. ~6–8 h — the decisive test of the central claim.** The χ-3 baseline at `gci_M` for **g13 and
g47**: 8 solves. Both already have the treatment at `gci_M`; only the baseline leg is missing. That
turns the credit's grid sensitivity from one wing into three and says whether the 67–74 % loss is a
property of the change or of geometry 83. **Nothing else in this list is worth doing first.**

**3. ~1.5 h — close the largest untested lever.** vis4 halved and doubled on **two** wings at
`gci_C`, α 0: 4 solves. Absolute drag moves 55.7 counts across that range and the effect on a
*difference* has never been measured. If differences are insensitive, a large budget line closes.
If they are not, **no grid level will rescue the claim**, and knowing that for 1.5 h of compute
before renting hardware is the highest-value hour available.

**4. ~3–4 h — diagnose the divergence.** CDp rising while CDv falls as layers are added at fixed s0
points at the `o_wing`/`o_out` interface or the eddy-viscosity profile across it, not at the
boundary layer. Two runs with the interface moved, at fixed everything else, would localise it. A
third global level bought before this is a third point on a family with no demonstrated limit.

**5. ~8–12 h — re-anchor the directional evidence on family B.** The chordwise three-level family
and the wall-normal one are both on the defective-cap meshes (§3.1). Rebuilding the chord family at
`gci_M`'s span/normal resolution would give an observed order in the direction carrying 88 % of the
error, on the meshes the dataset actually uses. ~1.3–1.5M cells; `gci_M` used 11.43 GiB of a 13 GiB
budget, so this is marginal on this host and should be memory-watched.

**6. Rented compute — `gci_F` at 2.32M cells.** Needs 23 GiB against a 15.86 GiB physical host, so
no `.wslconfig` change reaches it (`reports/s8_level_selection.json`). Two risks make it a poor
*first* purchase: **ANK-only is unproven above 1,183,140 cells** (the largest solved, `g13 gci_M`,
peak RSS 11.43 GiB, swap 0.04 GiB — verified), so the first cloud run may discover a solver
problem rather than produce an order; and it refines the divergent direction along with the others.
Buy it after 2, 3 and 4, when it will answer a question rather than raise one.

**7. Not on the critical path but cheap:** cost the c_p bound violation in counts (integrate the
surface pressure with and without the over-bound cells clipped — the root LE strip is where BWB
pressure drag lives, and this has never been converted into a number); re-run the mass balance and
the L2 sensitivity on family B; record NeuralFoil's 0.30 confidence wherever the transition bound
is quoted.

---

## 7. Corrections to the brief

The audit brief supplied figures that the artifacts do not support. Recorded because inheriting
them would have propagated them.

| Brief says | Artifacts say |
|---|---|
| `gci_C` 603,592 and `gci_M` 1,172,856 cells | Those are family B (`runs/s8_v2`). The grid study those numbers are attached to ran on family A: **567,256 and 1,111,152** (`runs/s8_gci83/*_summary.json`). §3.1 |
| Two-grid fallback gives "about 98 counts on a C_D of 179" | **Reproducible, and that is the finding.** 98.2 counts is exactly the α-0 band as shipped — because it was computed at r = 1.300. With the correct global r = 1.2479 it is **121.6 counts**. The brief inherited the understated figure from the artifact fixed in §3.2 |
| "Assuming p = 1 rather than p = 2 moves the extrapolated answer by 82 counts" | A misreading of `S8_REPORT:1651`, where 82.5 is how much `gci_M` is *high by* if p = 1. The difference between the two extrapolations is **46.2 counts** at r = 1.274, 42.6 at r = 1.3, 50.6 at r = 1.2479. The docstring of `gci_four_level.py` repeats the 82 figure |
| "52 runs over ~83 wings × 4 angles" | 52 runs = **10 pilot geometries** at `gci_C` + **3** at `gci_M`, × 4 angles. "83" is the *index* of one wing in `lhs100_seed42`, not a count. There is no 83-wing campaign |
| E387 "the only validation case anywhere near AERIS's actual Reynolds number" | E387 is Re 200k, **7.7× below** AERIS's 1.53e6. **NACA 4412 is at Re 1.52e6 and Ma 0.09** — a 0.7 % Reynolds match. The study's best-matched case is the one it leans on least |
| Wall-normal "208.2 → 209.1 → 213.3" | Correct, and the underlying runs are `runs/s8_checklist/dir_normal_s0*`: **208.237 → 209.134 → 213.330**. There is no JSON report for this family — the only record is the prose table at `S8_REPORT:573` |

---

## 8. Things not asked about

1. **No trim state, and it is quantifiable.** At α 0 the ten wings span C_L −0.160 to −0.0087. At
   AR 4.84 and e 0.9 that is **18.6 counts of induced drag** difference from the lift mismatch
   alone, against a C_D spread of 35.4 counts. Between-wing drag comparisons at fixed α are
   dominated by an untrimmed lift difference. (The *credit* is a within-wing comparison and is
   unaffected — ΔC_L ≤ 0.0005, ≤0.23 counts.)
2. **`run.log` is not in git**, so the gate's *input* is unreproducible from the repository. The
   verdicts are now committed as artifacts; the evidence they were derived from is not. If `runs/`
   were lost, the convergence status of the campaign could never be re-established.
3. **Every production run is outside the governed configuration.** All 52 rows carry
   `solver_is_governed_configuration: false`, because `eddyVisInfRatio 0.21` and
   `useNKSolver false` are overrides (`solve_s8.py:431`). Both are deliberate and defensible; but
   nothing fails on the flag, and the policy authorising the deviation should be named.
4. **The tip cap is still out of spec.** After the 13 September fix, worst y+ is **1.22–1.85** on
   all 52 runs against a mandatory ≤1 (p99 ≤ 1.16). It is now the *only* archive-audit finding, so
   `sound` remains 0/52 for a real reason rather than a bookkeeping one. The same cap zone carries
   **c_p = −9.48** — local velocity 3.2× freestream on a low-speed wing tip, which is a geometric
   artifact, not physics.
5. **The M6 loads comparison quotes the favourable framing.** +5.26 % is CFD subsampled at the
   measured points; at full CFD resolution the span-integrated difference is **+12.0 %**. The
   subsampled comparison is the methodologically correct one, but the 6.4-point gap between them is
   a discretisation-of-the-integral uncertainty that is not recorded anywhere.
6. **Both solvers over-predict pressure drag, by 3.4 % and 6.1 %**, on the one case with a
   reference split. This is the single most relevant model-form number in the study — the effect
   being measured *is* a pressure-drag effect — and it appears in no uncertainty discussion.
7. **NACA 0012's moment agreement is accidental.** Finest-grid CM is −0.44 % from the reference, but
   the sequence runs −0.000248 → 0.004342 → 0.006755 with GCI 49.5 % and an extrapolate **+38.96 %**
   off. Any moment or neutral-point conclusion leaning on this case is unsupported. (The
   grid-convergence argument for moments rests on `gci_C`→`gci_M`, which is sound; this is about not
   citing NACA 0012 for it.)
8. **The study's own only measurement of observed order spans 0.83 to 3.23** across quantities on a
   proper three-level 2-D family, with one quantity non-monotone (`s8_naca0012_tmr.json`). The
   two-level band assumes p = 2.0 for all quantities. The assumption is not supported by the
   study's own data — including for C_L, where the measured order is 0.83.
9. **`gci_M` is not demonstrably grid-converged and the study says so** — this is listed in the
   brief as a known gap, and it is correctly and repeatedly recorded. Worth stating that the
   documentation discipline here is genuinely good: the defect ledger, the retraction notices and
   the `TREND_NOT_GCI` labelling are better than most published CFD. The problem is not candour.
   It is that the central number has been quoted at one grid level and its grid sensitivity, which
   was cheap to measure, was never measured.

---

## 9. Changes made to the repository by this audit

Code and artifact fixes, all verified:

| File | Change |
|---|---|
| `gci_four_level.py` | band now uses the global cell-derived r, not 1.300; adds `refinement_ratio_used` and `asme_r_requirement` |
| `reports/s8_gci_four_level_g83.json` | regenerated; bands widen (C_D α 0: 54.8 % → 67.9 %) |
| `convergence_gate.py` | records a resolved `directory` plus `run_identity` |
| `dataset_row.py` | matches gate records by resolved path, then by `<geometry>/<run>` |
| `runs/.gitignore` | admits `gate.json`, which `!*_gate.json` never matched (latent) |
| `reports/s8_v2_gate.json` | **new** — the 52 production verdicts in one place: **52/52 ACCEPTED** |
| `runs/s8_v2/g*/gci_*_gate.json` | rewritten with resolvable paths; verdicts unchanged and reproduced identically |
| `collect_dataset.py` | manifest records `acceptance_filter_enforced` and `rows_without_a_verdict` |
| `data/dataset_v2/` | rebuilt with verdicts; 0 missing fields; physics and field hashes unchanged |
| `reports/s8_archive_audit_v2.json` | regenerated; only the y+ finding remains |
| `te_credit_grid.py`, `reports/s8_te_credit_grid.json` | **new** — the credit's grid sensitivity |
| `test_checkers_reject.py` | now passes **26/26** (was 24/25 with one failure on `main`) |

Not changed, deliberately: no force, mesh or solver result has been altered, and no verdict has
been softened. The `s8_gci_a*.json` family-A reports are left exactly as they are — they are
evidence about meshes that were later rebuilt, and rewriting them would destroy the record that
§3.1 depends on.
