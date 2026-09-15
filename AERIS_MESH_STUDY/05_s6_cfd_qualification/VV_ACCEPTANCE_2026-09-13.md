# Acceptance criteria for the S8 campaign, against published practice

> **Read with [`S8_REPORT_2026-09-15.md`](../04_strategy_studies/S8_oh_structured/S8_REPORT_2026-09-15.md)**, the full account of S8 to 15 September.
> Its §8.2 lists the statements in this document that later work superseded.

**Written 2026-09-13, before the cloud batch is bought.** The question this answers is not
"is the mesh what we asked for" — `audit_runs.py` and `mesh_guidelines.py` answer that — but
"is what we asked for what the field asks for". Every criterion below is somebody else's
number, with its source named, because a criterion we invented is one we can talk ourselves
out of at 2 a.m.

## Where the numbers come from

| Source | What it gives |
|---|---|
| AIAA CFD Drag Prediction Workshop, gridding guidelines (Workshops 3–7), `aiaa-dpw.larc.nasa.gov` | y+ < 1 on the **coarsest** grid and finer above (2/3, 4/9, 8/27 across levels); growth rate in the viscous layer **< 1.25**; **two constant-spacing layers** at the wall; chordwise spacing **~0.1 % of local chord** at leading and trailing edge; spanwise spacing **~0.1 % of semispan** at root and tip; outer boundary **~100 reference chords**; the same family, stretching and topology at every level |
| NASA Turbulence Modeling Resource, `tmbwg.github.io/turbmodels` | Wall-resolved RANS integrates to the wall: y+ ≤ 1, no wall functions. SA freestream **χ = 3 to 5**. Verification cases with answers agreed by three codes to 0.02 % |
| Celik et al., *J. Fluids Eng.* **130** (2008) 078001 | Three grids, refinement factor **r ≥ 1.3**, GCI on the finest pair, observed order reported |
| ASME V&V 20-2009 | Comparison error **E = S − D**; validation uncertainty **u_val** from numerical, input and experimental parts; the model error lies in **E ± u_val** |
| Common practice, wall-resolved RANS | **30–40 cells inside the boundary layer** |
| Workshop convention | One **drag count** = 1×10⁻⁴ in CD. Scatter across codes at the workshops is **4–5 counts**. Our CD is about **208 counts**, so one count is 0.5 % |

## Where this campaign stands against them

Measured on index 83 by `mesh_guidelines.py`, which now runs on any built mesh:

| Criterion | Limit | Coarse 567k | Medium 1.11M | Verdict |
|---|---|---|---|---|
| y+ on every wall cell | ≤ 1 | 0.86 wing / **0.85 cap after the fix** | 0.73 / 0.85 | **met** (was 4.2 on the cap) |
| Growth in the viscous layer | < 1.25 | **1.253** | 1.190 | coarse marginally over |
| Constant-spacing layers at the wall | ≥ 2 | **0** | **0** | **not met** |
| Cells inside the boundary layer | ≥ 30 | **20** | **26** | met only at fine (33) and extra-fine (43) |
| Leading-edge spacing, worst span row | ~0.1 % chord (≤ 0.15 accepted) | **0.166 %** at the tip; 0.05–0.07 % inboard | 0.140 % | **coarse not met** in the outer 8 % of span; medium met |
| Trailing-edge spacing | ~0.1 % chord | **0.40 %** | **0.31 %** | **not met**, 4× coarse |
| Spanwise at the tip | ~0.1 % semispan | 0.005 % | 0.004 % | met |
| Spanwise at the root | ~0.1 % semispan | **2.04 %** | **1.59 %** | deviation, justified below |
| Far field | ~100 chords | **40** | **40** | deviation, measured below |
| Folded cells | 0 | 0 | 0 | met |
| Same family, stretching, topology | required | yes | yes | met |
| Refinement factor | ≥ 1.3 | 1.3 exactly | — | met, at the minimum |

**Five gaps and two deviations.** None of them was known before this audit, and none would have
been caught by any check the campaign had. (Four until 15 Sept: leading-edge spacing had been
read on one ring picked by index, 93 % of semispan, and passed. Measured on every span row it
meets 0.1 % inboard, 0.05–0.07 %, but not in the outer 8 % of span, 0.17 % at the tip.)

## What is being done about each

| Gap | Action | Where |
|---|---|---|
| Tip cap in the buffer layer (y+ 4.2) | Fixed: cap cell 10 → 2 × s0; build refuses above 3; audit judges the worst wall cell, not the 99th percentile | done |
| Far field 40 vs ~100 chords | Measured as a single change at α 0 and α 8, in drag counts | `queue16`, `gci_C_ff100` |
| Trailing-edge spacing 0.40 % vs 0.1 % | Measured as a single change at α 0 and α 4 | `queue16`, `gci_C_te` |
| Growth 1.253, no constant wall layers, 20 BL cells at coarse | The coarse level is the extrapolation anchor, not an answer. Criteria apply at the level the answer is taken from: fine (33 cells) and extra-fine (43) meet them. If the two tests above move drag by more than a count, the whole family is rebuilt to comply | decision after `queue16` |
| Spanwise at the root 2 % vs 0.1 % | Deviation accepted with evidence: the DPW clusters at the root for a **wing-body junction**, and this wing meets a **symmetry plane**. Spanwise refinement recovered only 11 % of the grid gap, against 88 % for chordwise | recorded |

## Do these numbers apply to OUR flow?

They were written for transonic transports at Re 5–20 million, so the question is fair. Two
checks say yes.

**The low-speed workshop gives the same numbers.** The AIAA High-Lift Prediction Workshop runs
at **M 0.2, Re 4.3 million** — subsonic, high lift, separated flow — and its gridding
guidelines are identical: y+ ~1.0 on the coarse grid then 2/3, 4/9, 8/27; at least two
constant-spacing layers at the wall; viscous-layer growth under 1.25; far field ~100 chords;
0.1 % of local chord at both edges. Only one number differs, and it is stricter than ours: it
asks for grid size to grow **3× per level** (r = 1.44), where we use 2.2× (r = 1.3).

That is the substantive answer: these are boundary-layer and far-field-induction criteria, not
shock-capturing criteria. They do not depend on the Mach number.

**But the validation CASES did depend on it, and ours were badly chosen.**

| Case | Regime | Ours? |
|---|---|---|
| ONERA M6 | M 0.84, Re 11.7e6, **shocked** | Tests the mesher against measured pressure. **Wrong regime** — we have no shocks |
| NACA 0012 (TMR) | M 0.15, Re 6e6, attached | Close. Verification against three codes' agreed answer |
| **NACA 4412 (TMR)** | **M ~0.09, Re 1.52e6 on a 0.9012 m chord**, trailing-edge separation | **Our regime almost exactly** — our mission is Re 1.53e6 on 0.9 m |

The NACA 4412 case is a better match to AERIS than anything we have run: the same Reynolds
number, the same chord, low speed, and it carries Coles & Wadcock's measured velocity profiles
plus CFL3D's own SA solution for cp and skin friction. Its data and a grid are now in
`external/naca4412/`. It is at α 13.87° with trailing-edge separation, which is past our
campaign's range — that is its value: it says where our setup stops being trustworthy.

## Acceptance criteria for the campaign

A result is fit to train a surrogate, or to be quoted, when **all** of these hold.

**A. Geometry.** The built mesh reproduces the design vector: root chord, span and tip ratio
within 1 %, outer sweep within 1°, twist within 0.2° at every generator station inboard of 95 %
semispan. *Measured by* `geometry_audit.py`.
*Status (15 Sept):* 49/50. Twist was never short — the old check measured it wrongly (last span
row, extreme-x points). rms error 0.02–0.08° per design. The one outside is g12, +0.25° where its
twist has a sharp V at a span break: the loft's spline rounds it by 0.15° and the mesh's span rows
by 0.09°, within about 2 cm. CFD and AVL fly the same rounded wing (AVL's sections lie within
0.13 % of chord of the loft).

**B. Mesh.** Every guideline in the table above met at the level the answer is taken from;
y+ ≤ 1 on every wall cell at every level; zero folded cells; a rebuild reproduces all 37
quality metrics. *Measured by* `mesh_guidelines.py`, `build_volume.py`, `compare_meshes`.

**C. Iterative convergence.** Every equation — continuity, three momentum, energy, turbulence
— drops its own limit (Fluent's defaults: 1e-3 for flow and turbulence, 1e-6 for energy)
against the largest residual in the first five iterations; the combined residual reaches 1e-6;
the forces move less than **one drag count** over the last quarter of the run; no run converges
in fewer than ten iterations; no force outside physical bounds. *Measured by*
`convergence_gate.py`, `equation_convergence.py`, and the solver's own guards.

**D. Grid convergence.** Three levels at r ≥ 1.3, GCI on the finest pair, observed order
reported and inside [1, 3] — outside that range the extrapolation is indicative, not an error
bar. Every quoted coefficient carries its GCI as its numerical uncertainty. *Measured by*
`gci.py`. *Status:* the chordwise family gives observed order 3.25, above the scheme's formal
2, so it is reported as indicative.

**E. Cross-code.** ADflow and SU2, on the same mesh with the same model and conditions, agree
within the workshop's own scatter, **5 drag counts**. Beyond that, one code is investigated
before either number is used. *Measured by* `su2_mesh.py` + `su2_config.py`. *Status:* queued.

**F. Validation against measurement.** ONERA M6 **on our own mesh**: suction peak within 2 %,
shock position within 0.02 x/c, integrated sectional load within 5 % at stations 2–6. NACA 0012
against the TMR's agreed answer: lift within 0.5 %, drag within 2 % after extrapolation.
**NACA 4412 (TMR 2DN44), set before its results exist:** CL within 1 % and CD within 3 % of the
CFL3D–FUN3D SA band after extrapolation (the band itself is 0.23 % wide in lift and 3 % in drag),
upper-surface separation within 0.05 x/c of CFL3D's 0.79; cp and the six velocity profiles are
reported against experiment as trends, because TMR itself calls the case weak as validation.
*Status (15 Sept):* M6 on our mesh converged — suction peak 2.6 % (**not met**), shock position
0.021 x/c (**marginal**), sectional loads not yet integrated on it. NACA 0012 at −0.19 % lift,
+2.7 % drag on the finest converged grid. NACA 4412 grids built (3.6e-8 chord from TMR's wall
points), queued in `queue18.sh`.

**G. Model form.** SA against a second turbulence model, reported as a band, not a number. The
transition assumption carried as an explicit bound (fully turbulent section drag is 1.4–2.0×
free-transition) until it is measured. Freestream turbulence at the TMR's χ = 3, not a default.
*Status:* second model still failing; χ = 3 adopted and re-running.

**H. Data.** Every archived row passes `audit_runs.py`: gate verdict, physical bounds and
finiteness, per-equation convergence, its own reference area, moment reference and chord, no
folded cells, y+, ten-iteration floor, freestream direction — and carries its own Reynolds
numbers and the solver options actually in force.

## The final table: published number, our own measurement, what we adopt

Where our own evidence is stronger than a round number, it wins — and is named.

| # | Criterion | Published | Our own measurement | Adopted | Why |
|---|---|---|---|---|---|
| 1 | y+, every wall cell | ≤ 1 (DPW, HiLiftPW, TMR) | cap was 4.2, in the buffer layer, at every level | **≤ 1 on the worst cell, every level** | No wall functions available; the buffer layer is where no model is defined |
| 2 | Viscous-layer growth | < 1.25 | 1.253 coarse, 1.190 medium | **< 1.25 at the level the answer comes from** | Coarse is the extrapolation anchor, not an answer |
| 3 | Constant layers at the wall | ≥ 2 | 0, unmeasured effect | **Deviation, recorded, low priority** | Effect unmeasured; first cell is already y+ 0.85 |
| 4 | Cells across the boundary layer | 30–40 (practice) | 20 / 26 / 33 / 43 by level | **≥ 30 at the answer level** | Our own directional study says the wall-normal direction is *not* where the drag error is: refining it moves CDp the wrong way (+3.3 %), while chordwise carries 88 % |
| 5 | Leading edge | ~0.1 % chord | 0.096 % | **met, keep** | Delivered by the 10°-per-cell turning target |
| 6 | Trailing edge | ~0.1 % chord | 0.40 %, 4× coarse | **measure, then adopt if ≥ 1 count** | Edge refinement recovered 7 % of the grid gap ≈ 2 counts |
| 7 | Spanwise, tip | ~0.1 % semispan | 0.005 % | **met, keep** | |
| 8 | Spanwise, root | ~0.1 % semispan | 2.04 % | **deviation, justified** | The workshops cluster there for a wing-**body** junction; ours meets a symmetry plane, and spanwise refinement recovers 11 % against chordwise's 88 % |
| 9 | Far field | ~100 chords | 40; 40→60 costs 0.7 counts at α 0, 0.5 at α 8 | **measure at 100; keep 40 only if < 1 count** | Under the workshops' own 4–5 count scatter |
| 10 | Refinement factor | r ≥ 1.3 (Celik); 3× cells per level (HiLiftPW) | r = 1.3, 2.2× cells | **r = 1.3, with the risk stated** | At the minimum: a small r makes the observed order noisy, which may be why the chordwise family reports p = 3.25 |
| 11 | **Iterative convergence** | "converged"; forces to ~1 drag count; residual histories reported | continuing past 1e-6 moves forces **0.073 %** (0.15 counts); two different paths to the same 1e-6 differ by **0.32 % in CDp** (0.6 counts); a stalled run at 3e-6 was **1.8 %** off (3.7 counts) | **Total residual 1e-6, AND every equation past its own limit, AND forces settled inside 1 count over the last quarter, AND no run under 10 iterations, AND stall detection** | Our own numbers say 1e-6 is enough *if* the run is healthy, and that health — not the number — is what distinguishes a converged run from a stopped one |
| 12 | Cross-code agreement | 4–5 counts of scatter at the workshops | not yet measured | **5 counts, else investigate** | |
| 13 | Freestream turbulence | SA χ = 3–5 (TMR) | ADflow's default is χ ≈ 1.3; χ = 3 costs +0.88 % CD, grid-independent | **χ = 3** | A default nobody chose is not a modelling decision |
| 14 | Transition | run fully turbulent, trip if needed | fully turbulent section drag is 1.4–2.0× free-transition | **fully turbulent, with the band quoted** | No transition model in this solver |
| 15 | Validation case regime | match the application | M6 is transonic | **add NACA 4412 at Re 1.52e6** | The only public case at our Reynolds number |

## The validation statement we will be able to make, and the one we will not

Following ASME V&V 20, a validation result is **E = S − D** with an uncertainty **u_val**. For
the M6 on our own mesh we will have S (our computation), D (Schmitt & Charpin 1979) and a
numerical uncertainty from the grid family; the experimental uncertainty for that campaign is
published as ±0.02 in cp at Mach 0.84. That supports a statement of the form *"the modelling
error in surface pressure lies within E ± u_val"*.

What we will **not** be able to say, at any point in this campaign: that S8 predicts the drag
of an AERIS wing to within any stated band, because no AERIS wing has been measured. The
closest available statement is the chain: the solver reproduces a known low-speed drag answer
to 0.4 %, our mesh reproduces measured pressures on a real wing, the grid error is bounded by
the GCI, and the model-form error is bounded by the transition and turbulence-model bands.
That chain is worth stating explicitly wherever a drag number is used.

## What every report must show

1. The convergence history of **every equation**, not just the total.
2. Forces in **drag counts**, with the GCI as an error bar, not a bare number.
3. The grid the number came from, its cell count, and its guideline compliance.
4. Surface pressures at stations against measurement where measurement exists, upper and lower
   surfaces separated.
5. The solver options actually in force, read back from the solver.
6. Every deviation from the guidelines above, with the measurement that justifies it.
