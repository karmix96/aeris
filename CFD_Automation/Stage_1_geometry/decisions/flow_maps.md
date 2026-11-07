# Flow maps and the flow dataset (31 Oct 2026; baseline corrected 2 Nov 2026)

> **Section tables rebuilt on the fixed nose (7 Nov 2026).** All 46 section tables were rebuilt on the sections with
> the fixed nose (decision 64): 2,408 XFOIL sweeps, 40 min on 2 workers (2 cores, shared with another run). New
> against old on every shared grid point: `scripts/section_tables_nose.py`, `data/studies/section_tables_nose.json`,
> `docs/section_tables_nose.png`. The old tables stay in git (commit 11b0df15).
>
> - **XFOIL answers** (free transition, N_crit 9; 20,580 grid points): 574 gained, 317 lost (2.8 % and 1.5 %).
>   Tripped: 762 gained, 548 lost. All 46 tables: 1,750 gained, 1,152 lost of 58,996 points. Most of them at −10° to
>   −4.5° and 11–14°, near the 2-D stall.
> - **Transition** (free, N_crit 9): upper side, median change 0.19 % c, 95 % of points within 1.5 % c, largest
>   21 % c; lower side, median 0, 95 % within 2.1 % c, largest 85 % c (1.3 % of points move more than 10 % c: a
>   lower transition that jumps between the nose and the trailing edge).
> - **Lift and drag** (free): cl median 0.8 %, 95 % within 7.5 % (where |cl| ≥ 0.1); cd median 0.8 %, 95 % within
>   9.9 %. Tripped: cl median 0.6 %, 95 % within 6.1 %; cd median 0.4 %, 95 % within 8.4 %.
> - **Bubbles** (free): yes / no the same on 97.6 % (upper) and 97.7 % (lower) of the points; where both have one,
>   start and end move by a median 0.3 % c (upper; 95 % within 1.4–1.7 % c).
> - **By Re.** The changes grow with Re; low Re is not where they are largest. Upper transition, 95th percentile:
>   0.6–1.1 % c up to Re 4 × 10⁵, 1.5–2.9 % c from 6 × 10⁵ to 6 × 10⁶. Drag (free), 95th percentile: 2–8 % up to
>   4 × 10⁵, 11–20 % from 6 × 10⁵ up; the median stays 0.4–1.4 % at every Re.
> - **By angle.** The large drag changes sit near the 2-D stall: 95th percentile 22 % at −10° to −4.5°, 14 % at
>   11–14°; 2.7 % at 0–3.5° and 4.6 % at 4–7.5° (free).
> - **Through the engine** (the 20 reference wings at the four Re levels, root angle 0–10°, 480 conditions): the SA
>   profile-drag error, median +58.1 % before and +59.0 % after (change: median +0.3 points, 95 % within 5.3, largest
>   25); within ±10 % on 7.9 % and 7.3 % of the conditions; the model category the same on 480 of 480; the upper
>   laminar run moves by a median 0.1 % c (95 % within 0.9 % c). The share of the half wing with an upper bubble:
>   median change 0, mean +0.3 points, but 5 % of the conditions move by 17.5 points or more (largest 37): a bubble
>   flag flips on a few strips at once.
> - **2-D SA error by section** (cd tripped / cd free − 1, Re ≥ 10⁵, 0–8°, median, before → after): LA2573A 37 → 37 %,
>   E387 49 → 52 %, SD7032 59 → 61 %, NACA 4415 66 → 66 %; the other six move by 0.5–1.5 points. Below Re 10⁵ the
>   medians stay negative (−5 to −31 %).
> - The first-approach flow dataset, its figures and the numbers below were made with the old tables. They stay the
>   record and are not rebuilt.
> - **No Stage 1 conclusion changes.** The SA error (+62 % median), the model rule, the laminar run, the airfoil
>   ranking (LA2573A lowest, then E387, NACA 4415 and SD7032 highest) and the sign flip below Re 10⁵ all hold with the
>   new tables; the changes are a few points against effects of tens of points. The weakest number is the bubble share
>   of the half wing on single conditions (it can move by up to 37 points); its mean moves by 0.3 points (−0.8 to
>   +1.1 by Re level).
> - Figure conclusion: the nose fix moves transition by a median 0.2 % c and the drag by a median 0.8 %; the larger
>   changes come at high Re and near the 2-D stall, not at low Re.

> **What changes (7 Nov 2026).** Everything below is the **first approach**: the flow maps and the flow dataset
> were made at real size and real speed (the focus wings of 30 Oct–6 Nov, full span ≤ 7 m) and are **not
> rebuilt**. Since decision 70 every wing is built at unit mean chord, and the tool (`python -m cfdauto.flowmap`)
> reads such a wing as one with a 1 m mean chord: rerunning the dataset as it is would put every wing at a 1 m
> mean chord at the real speeds (the wrong Re). In similarity form a condition is an Re on the mean chord (the
> four levels): give the tool the speed V = Re / (ρ/μ) (ρ/μ = 6.85 × 10⁴ s/m² at sea level). The level-flight
> flag (wing loading against real wings of the same full span) needs a real size. The section tables are
> size-free; first built on the sections before the nose fix, they were rebuilt on the fixed nose on 7 Nov (decision
> 64; note above). The 2-D XFOIL airfoil
> study (`scripts/xfoil_band.py`) was rerun on 7 Nov on the new sections: at 2° the tripped drag is +39 to
> +128 % above the free drag at Re ≥ 3 × 10⁵ (median +81 %), −2 to +21 % at 10⁵.

Mike's plan: full design space → what the parametrization can make → focus (Class I and small Class II,
b ≤ 7 m) → flow maps per family (Re along the semi-span, phenomena, transition, effect of the sections) → a tool
that takes a wing and shows all this with a proposed turbulence model. Then (same day): a large dataset of
wings × section sets × Mach × angle with the same assumptions, sensitivity analyses, trends and
statistics, and conclusions under the assumptions and limits; the tool updated to match. 1–2 Nov 2026: a
logic check and an independent review; their fixes are in the code and the numbers below.

## How it works (`cfdauto/flowmap`)

1. **Section tables** (`tables.py`). Every section used by the section sets, free transition
   (e^N, N_crit 9) and tripped at 1 % chord, on 14 Re (1.5e4–6e6, log) × Mach 0 / 0.1 / 0.2 × 49 angles
   (−10…14°, 0.5°). Extra: N_crit 5 and 11 (free, Mach 0.1) and three 50/50 blends (checks). 2,408
   XFOIL sweeps, robust (`xfoil.py`: a hanging or NaN point is killed and skipped, never blocks).
   Single-angle failures between two converged angles are filled linearly (1.5–4 % of each table;
   with a forced trip XFOIL fails where the stagnation point crosses the trip); a 0/1 flag (bubble,
   separation) is filled only where both neighbours agree. Two or more failures in a row stay NaN =
   "no XFOIL answer". Lookup: trilinear in (log Re, Mach, angle), NaN-aware (half-weight rule).
   A strip between two different station sections takes the blend of the parents' answers.
2. **Engine** (`engine.py`). Strips (root, 2 per panel, breaks, 97 % of S) × conditions → strip answers
   and wing metrics. Baseline since 2 Nov 2026: local angle = root angle + twist − a uniform (elliptic)
   induced angle CL / (π AR), iterated with the relaxation 1 / (1 + 2 / AR) (exact for a 2π lift slope).
   Metrics: Re bands, laminar run, bubbles, TE separation, the SA profile-drag error (chord-weighted
   tripped / free − 1), the wing CL (the strip lift, which already carries the downwash) and the wing
   loading it carries. `induced=False` is the old baseline, kept as a check (then CL = 2-D lift × the
   Helmbold slope ratio with the half-chord sweep). The tool and the dataset use the same engine (test
   `test_tool_equals_dataset`).
3. **Model rule** (`engine.category`): "no XFOIL answer" if under half of the half wing has a 2-D answer (often near
   stall, sometimes a failed point; not a measured stall); SA adequate if |error| < 10 %, the mean upper
   laminar run is under 20 % chord and no strip is below Re 1e5; else a transition model (low-Re caution).
4. **Dataset** (`dataset.py`): 400 focus training wings (100 per type) × 4 section sets per type
   (`configs/flowmap.yaml`) × Mach 0.03–0.20 (7) × root angle 0–10° (6) × altitude 0 / 1,524 / 3,048 m
   = 201,600 rows. Flags: realistic speed (per family); realistic set (`trims: false` for the non-reflexed
   NACA set on tailless wings, which cannot trim); level flight (wing loading within × / ÷ 2 of the fit to
   37 real wings, log10(W/S) = 1.869 − 0.164 [tailless] + 1.127 log10(b); 35 of 37 inside; never for a set
   that cannot trim).
5. **Analysis** (`analysis.py`): statistics on realistic speeds and sets; distributions, trends, Re bands,
   model maps; sensitivity (η² binned, gradient-boosting permutation importance, grouped variance shares:
   wing shape / sections / flight condition, alone and total; sections coded by airfoil set, test split by
   wing); pairs of similar wings (does SA's error cancel?); assumption checks on 20 wings per type; tables vs
   direct XFOIL; blend rule.

## Findings (numbers: `docs/flow_analysis.json`; figures: `docs/flow_*.png`; page section "Flow dataset")

- Fully turbulent SA overestimates the profile drag almost everywhere: median +62 % at realistic speeds and
  sets (10–90 %: +17 to +91 %), within ±10 % in 5 % of rows; in level flight (23 % of rows) +69 % (+62 to
  +78 % by type), within ±10 % in 4 %. Total drag (elliptic induced drag added): +18 to +33 % by type.
- Model rule: SA adequate in 2 % of rows, a transition model in 97 % (low-Re caution in 6 %), no XFOIL
  answer 0.4 %.
- SA's error does not cancel between similar wings: 5,759 pairs (same type, set, Mach, altitude, |ΔCL| < 0.03)
  show 4 counts median error on the profile-drag difference (q90 18), above the 2-count target (Stage 0 D1)
  in 71 % of pairs; SA ranks 6 % of pairs the other way round.
- The error peaks at about 4° root angle (+81 %) and is +40 % at 10°; the laminar run falls from 63 % (0°) to
  26 % (10°) of chord. TE separation stays at 1–2 % of the half wing up to 10°.
- Speed: over the grid +44 % at Mach 0.03 to about +70 % at 0.11–0.14; in level flight +20 % → +81 % (Mach
  0.14) → +63 % (0.20). In level flight the angle follows the speed: read the level-flight trends.
- What sets the error (grouped variance, alone / total; honest split by wing): flight condition 53 / 78 %
  (tailless), 29 / 75 % (conventional); airfoil set 1 / 9 % and 11 / 54 %; wing shape 8 / 28 % and 7 / 18 %.
  Strongest inputs: tailless angle 51 %, Mach 21 %, size 10 %; conventional airfoil set 35 %, angle 33 %,
  Mach 19 %. Sweep does not enter the strips; aspect ratio only through the uniform induced angle.
- Airfoils (conventional): LA2573A +34–36 %, E387 +50 %, NACA 4415 and SD7032 about +67 %: SA mis-ranks airfoils.
- Bubbles on 52–72 % of the half wing by angle (90 % at Mach 0.03, 45 % at 0.2), from about 0.11 c to 0.78 c
  (30 % of bubble rows lie partly outside 0.3–0.7 c); the lower surface stays laminar to about 0.99 c.
- Below Re 1e5 the sign flips: where most of the half wing is below 1e5 the median is −4 % and 58 % are
  negative. Part of the half wing is below 1e5 in 19 % of BWB rows, 2–5 % of the others.
- Crossflow flag (one strip swept > 25° with Re normal to its edge > 1e6; unsourced threshold): 44 % of BWB
  rows, 17 % of flying-wing rows.
- Assumption checks (median change of the error, points): N_crit 5 −11, N_crit 11 +2, induced angle left out
  −4 (5–95 %: −41 to +15: the big changes at high angle), compressibility +0.5, strips 7 / 19 −0.1 / +0.1.
  Tables vs direct XFOIL: drag median 0.7 % (free), 0.3 % (tripped); bubble yes/no agrees 98 %. Blend rule
  vs blended section: drag median 0.0–4.0 % by pair.

## Logic check (1 Nov 2026) and what was done (2 Nov 2026)

- L1. "SA for mesh studies, the model does not matter" was wrong: what a mesh must resolve depends on the
  model. Make the mesh transition-ready and repeat a reduced mesh study with the transition model.
- L2. Sweep does not enter the strips, aspect ratio only through the uniform induced angle: keep both fully
  sampled in every CFD and ML set. Similarity scaling rests on dimensional analysis.
- L3. "Real flow" = smooth wing, calm air (N_crit 9): a design reference and an upper bound. 25–55 % of the
  error comes from the lower surface staying laminar to the trailing edge, which hinge lines would end.
- L4. Planform differences at a fixed airfoil are safer than absolute drag; airfoil differences are not.
- L5. SA is fully turbulent only with the standard inflow eddy viscosity (ν̃/ν about 3, Spalart & Rumsey
  2007); with a low value it shows apparent transition (Crivellini & D'Alessandro 2014). Fix and report it.
- L6. Quote level-flight numbers for physics; read the sensitivity shares as properties of the grid.
- L7. Below Re 1e5 (tiny tips) XFOIL and the strips are weakest: qualitative only.
- L8. Done: the induced angle is the baseline; the old high-angle findings (error +20 % at 10°, TE separation
  on 20 % of the half wing at 10°, SA adequate for flying wings at 10°) were artefacts.
- L9. SA's error does not cancel at the 2-count level: D1 is a numerical target; drag ranking needs
  transition-model results, at least on a calibration subset.
- L10. Mesh transition band: upper 0.10–0.85 c, lower 0.60–1.00 c; on swept panels the upper band starts at the
  leading edge (crossflow transition, not seen by the strips, would start there; added 2 Nov 2026).
- L11. Done: "beyond 2-D stall" is "no XFOIL answer". Optional: retry failed points with finer steps.
- L12. Done: the NACA set on tailless wings is tagged (cannot trim) and left out of the statistics. Start the
  3-D check on the BWB centre body (about 30 % of the semi-span, about half of the area).
- L13. Done: sections coded by airfoil set in the sensitivity; test split by wing (R² now 0.88 tailless,
  0.95 conventional for the SA error); flags never averaged into 0.5; crossflow flag per strip (still an
  unsourced threshold); "Class I and small Class II".
- L14 (2 Nov 2026). "A first cell per station" was overstated: at one flight speed y+ = 1 gives a first cell
  that changes only about 20 % along the span (Re and chord change together: s0 ~ c^(1/14)); it changes with the
  speed (Mach 0.03 -> 0.20: about 6 x smaller). What changes per station is the boundary-layer thickness (up to
  about 10 x from a small BWB's tip to its root), so the wall-layer count must cover the root.

## Limits

2-D strips (no crossflow transition, no spanwise drift, no 3-D bubble relief, no tip vortex); one uniform
induced angle (its spanwise change is not modelled; a vortex-lattice loading would be better); XFOIL e^N
with one N_crit, least reliable below Re 5e4, in long bubbles and near stall; the condition grid is a box,
not a flight envelope (the level-flight flag is a rough filter); statistics describe our ranges and section
sets, not a population of aircraft; the error measure is the 2-D, transition-only part of the SA error.

## Open (page "Open decisions")

Mike, 2 Nov 2026: the model choice is made in a later stage (the mesh is built transition-ready meanwhile);
no flow check is needed before the mesh stage; the 3-D check is the first run of the mesh stage and is needed
before the paper quotes flow numbers; the other checks are optional (OPEN_DECISIONS 54, 55).


Transition model in the pipeline (SU2 γ-Reθ for drag; ADflow SA for the first mesh studies on a
transition-ready mesh, then a reduced mesh study with the transition model; the SA inflow value); D1 as a
numerical target and a transition-model calibration subset; the 10 % SA threshold; the tool's default
N_crit; the level-flight band; a 3-D check of the strips (SU2 γ-Reθ on reference wings, BWB centre body
first) before quoting numbers in the paper.
