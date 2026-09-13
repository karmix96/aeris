# Acceptance criteria for the S8 campaign, against published practice

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
| Leading-edge spacing | ~0.1 % chord | 0.096 % | 0.074 % | met |
| Trailing-edge spacing | ~0.1 % chord | **0.40 %** | **0.31 %** | **not met**, 4× coarse |
| Spanwise at the tip | ~0.1 % semispan | 0.005 % | 0.004 % | met |
| Spanwise at the root | ~0.1 % semispan | **2.04 %** | **1.59 %** | deviation, justified below |
| Far field | ~100 chords | **40** | **40** | deviation, measured below |
| Folded cells | 0 | 0 | 0 | met |
| Same family, stretching, topology | required | yes | yes | met |
| Refinement factor | ≥ 1.3 | 1.3 exactly | — | met, at the minimum |

**Four gaps and two deviations.** None of them was known before this audit, and none would have
been caught by any check the campaign had.

## What is being done about each

| Gap | Action | Where |
|---|---|---|
| Tip cap in the buffer layer (y+ 4.2) | Fixed: cap cell 10 → 2 × s0; build refuses above 3; audit judges the worst wall cell, not the 99th percentile | done |
| Far field 40 vs ~100 chords | Measured as a single change at α 0 and α 8, in drag counts | `queue16`, `gci_C_ff100` |
| Trailing-edge spacing 0.40 % vs 0.1 % | Measured as a single change at α 0 and α 4 | `queue16`, `gci_C_te` |
| Growth 1.253, no constant wall layers, 20 BL cells at coarse | The coarse level is the extrapolation anchor, not an answer. Criteria apply at the level the answer is taken from: fine (33 cells) and extra-fine (43) meet them. If the two tests above move drag by more than a count, the whole family is rebuilt to comply | decision after `queue16` |
| Spanwise at the root 2 % vs 0.1 % | Deviation accepted with evidence: the DPW clusters at the root for a **wing-body junction**, and this wing meets a **symmetry plane**. Spanwise refinement recovered only 11 % of the grid gap, against 88 % for chordwise | recorded |

## Acceptance criteria for the campaign

A result is fit to train a surrogate, or to be quoted, when **all** of these hold.

**A. Geometry.** The built mesh reproduces the design vector: root chord, span and tip ratio
within 1 %, outer sweep within 1°, twist within 0.5°. *Measured by* `geometry_audit.py`.
*Status:* 47/50 measurements pass; twist is systematically 0.5° short and unexplained.

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
*Status:* M6 on our mesh running; NACA at −0.19 % lift, +2.7 % drag on the finest converged grid.

**G. Model form.** SA against a second turbulence model, reported as a band, not a number. The
transition assumption carried as an explicit bound (fully turbulent section drag is 1.4–2.0×
free-transition) until it is measured. Freestream turbulence at the TMR's χ = 3, not a default.
*Status:* second model still failing; χ = 3 adopted and re-running.

**H. Data.** Every archived row passes `audit_runs.py`: gate verdict, physical bounds and
finiteness, per-equation convergence, its own reference area, moment reference and chord, no
folded cells, y+, ten-iteration floor, freestream direction — and carries its own Reynolds
numbers and the solver options actually in force.

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
