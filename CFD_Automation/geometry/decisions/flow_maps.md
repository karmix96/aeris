# Flow maps and the flow dataset (31 Oct 2026)

Mike's plan: full design space → what the parametrization can make → focus (Class I–II, b ≤ 7 m)
→ flow maps per family (Re along the span, phenomena, transition, effect of the sections) → a tool that
takes a wing and shows all this with a proposed turbulence model. Then (same day): a large dataset of
wings × section sets × Mach × angle with the same assumptions, sensitivity analyses, trends and
statistics, and conclusions under the assumptions and limits; the tool updated to match.

## How it works (`cfdauto/flowmap`)

1. **Section tables** (`tables.py`). Every section used by the section sets, free transition
   (e^N, N_crit 9) and tripped at 1 % chord, on 14 Re (1.5e4–6e6, log) × Mach 0 / 0.1 / 0.2 × 49 angles
   (−10…14°, 0.5°). Extra: N_crit 5 and 11 (free, Mach 0.1) and three 50/50 blends (checks). 2,408
   XFOIL sweeps, robust (`xfoil.py`: a hanging or NaN point is killed and skipped, never blocks).
   Single-angle failures between two converged angles are filled linearly (1.5–4 % of each table;
   with a forced trip XFOIL fails where the stagnation point crosses the trip); two or more in a row
   stay NaN = "no 2-D answer". Lookup: trilinear in (log Re, Mach, angle), NaN-aware (half-weight rule).
   A strip between two different station sections takes the blend of the parents' answers.
2. **Engine** (`engine.py`). Strips (root, 2 per panel, breaks, 97 % of S) × conditions → strip answers
   and wing metrics: Re bands, laminar run, bubbles, TE separation, the SA profile-drag error
   (chord-weighted tripped / free − 1), a 3-D lift estimate (Helmbold/DATCOM slope ratio) and the wing
   loading it carries. The tool and the dataset use the same engine (test `test_tool_equals_dataset`).
3. **Model rule** (`engine.category`): beyond 2-D stall if under half the span converges; SA adequate
   if |error| < 10 % and no strip below Re 1e5; else a transition model (with a low-Re caution).
4. **Dataset** (`dataset.py`): 400 focus training wings (100 per type) × 4 section sets per type
   (`configs/flowmap.yaml`) × Mach 0.03–0.20 (7) × root angle 0–10° (6) × altitude 0 / 1,524 / 3,048 m
   = 201,600 rows. Flags: realistic speed (per family) and level flight (wing loading within × / ÷ 2 of
   the fit to 37 real wings: log10(W/S) = 1.869 − 0.164 [tailless] + 1.127 log10(b); 35 of 37 inside).
5. **Analysis** (`analysis.py`): distributions, trends, Re bands, model maps; sensitivity (η² binned,
   gradient-boosting permutation importance, grouped variance shares: wing shape / sections / flight
   condition, alone and total); assumption checks on 20 wings per type; tables vs direct XFOIL; blend rule.

## Findings (numbers: `docs/flow_analysis.json`; figures: `docs/flow_*.png`; page section "Flow dataset")

- Fully turbulent SA overestimates the profile drag almost everywhere: median +55 % at realistic
  speeds (10–90 %: +8 % to +90 %), within ±10 % in 10 % of rows; in level flight
  (27 % of rows) +65 %. Resampling the wings moves a type's median by at most ±1.7 points.
- Model rule: SA adequate in 7 % of rows, a transition model in
  93 % (with a low-Re caution in 7 %), beyond 2-D stall 0.3 %.
- What sets the error (grouped variance, alone / total): flight condition 68 / 92 % (tailless),
  30 / 89 % (conventional); sections 1 / 10 % and 5 / 60 % (on conventional
  wings the section interacts with the angle: LA2573A's error grows with angle, the others fall); wing shape
  4 / 24 % and 2 / 16 % (size, through Re, with speed). Dihedral (a placebo here) scores zero.
- The angle is the strongest input: the error peaks at 2–4° root angle and falls at 8–10°; TE separation
  appears at 10°. Faster flight raises the error up to Mach ≈ 0.1, then it is flat.
- Below Re 1e5 the sign flips: where most of the half wing is below 1e5 the median is -2 % and
  53 % of rows are negative (long bubbles: the real flow is draggier than fully turbulent CFD).
  Part of the half wing is below 1e5 in 19 % of BWB rows, 2–5 % of the others.
- Crossflow risk (LE sweep > 25°, Re normal > 1e6): 50 % of BWB rows, 17 % of flying-wing rows.
- Total drag (elliptic induced drag added, induced-angle run): median +18 % to +26 % by type.
- Assumption checks (median change of the error, points): N_crit 5 -9, N_crit 11 +2, induced angle
  +4 (5–95 %: -13 to +35), compressibility +0.5, strips 7 / 19 -0.1 / +0.0.
  Tables vs direct XFOIL: drag median 0.7 % (free), 0.3 % (tripped); bubble yes/no
  agrees 98 %. Blend rule vs blended section: drag median 0.0–4.0 % by pair.
- Model rule refined (31 Oct 2026): SA also needs a mean upper laminar run under 20 % chord; a small drag
  error with a long laminar run (mostly LA2573A at low angles) is a coincidence of two different flows.

## Limits

2-D strips (no crossflow transition, no spanwise drift, no 3-D bubble relief, no tip vortex); no
induced angle in the baseline (checked as a variant); XFOIL e^N with one N_crit, least reliable below
Re 5e4, in long bubbles and near stall; the condition grid is a box, not a flight envelope (the
level-flight flag is a rough filter); statistics describe our ranges and section sets, not a population
of aircraft; the error measure is the 2-D, transition-only part of the SA error.

## Open (page "Open decisions")

Transition model in the pipeline (SU2 γ-Reθ for drag; ADflow SA for mesh studies); the 10 % SA
threshold; the tool's default N_crit; the level-flight band; a 3-D check of the strips (AVL + XFOIL
polars or SU2 γ-Reθ on reference wings) before quoting numbers in the paper.
