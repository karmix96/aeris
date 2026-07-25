# Study — Chordwise panel spacing and the elevon hinge

Date: 2026-07-25
Feeds: `decision/0009-lowfi-discretisation.md`
Script: `standalone/lowfi_avl_study/probe_hinge_panel_alignment.py`
Evidence: `configs/aero/lowfi_discretisation_evidence/hinge_alignment.*`

## 1. Question

The panel-convergence study (Task 4b) found the largest discretisation error in
the whole low-fidelity chain sitting in a production default: at
`nchordwise = 8`, the elevon control derivative CL_δe carries a **6–8 % error**,
while CL carries ~1 % and the stability derivatives ~0.1 %.

The suspected mechanism is geometric coincidence rather than under-resolution.
With AVL's cosine chordwise spacing and 8 panels the edges fall at

    x/c = 0, 0.038, 0.146, 0.309, 0.500, 0.691, 0.854, 0.962, 1.000

The elevon hinge at x/c = 0.75 lies **0.059 c from the nearest edge**. AVL must
then represent a flap whose hinge is mid-panel.

If that is the mechanism, then **uniform** spacing (Cspace = 0) with 8 panels —
whose edges are multiples of 0.125, so 0.750 is *exactly* an edge — should be much
more accurate at **identical cost**. That is a cheap and testable hypothesis, and
if true it would be a free fix worth having.

## 2. Method

25 sections, 2 spanwise panels per interval (held fixed, so its own error cancels),
3 DoE seeds, α = 6°, δe = 4°, viscous on. Ten configurations spanning both spacing
laws and 8→40 chordwise panels. Reference: **cosine-40** (3840 vortices — chosen
because AVL's ~6000-vortex array limit makes anything finer unaffordable at this
strip count).

The hinge-to-nearest-edge distance is computed and reported for every
configuration, so the alignment claim is *checked* rather than assumed.

A **uniform-40 cross-check** is included to confirm the two spacing laws converge
to the same physical answer — otherwise the reference itself would be suspect.

## 3. Results

| config | hinge→edge distance | vortices | CL_δe err | CL err | Xnp err | Cmq err |
|---|---|---|---|---|---|---|
| cosine-8 (production) | 0.0587 | 768 | **7.71 %** | 1.37 % | 3.6e-4 | 3.2e-4 |
| uniform-8 | **0.0000** | 768 | **3.82 %** | 2.29 % | 5.1e-3 | 4.7e-3 |
| cosine-12 | 0.0000 | 1152 | 3.83 % | 0.62 % | 8.2e-5 | 1.5e-4 |
| uniform-12 | 0.0000 | 1152 | 2.04 % | 0.99 % | 3.4e-3 | 3.7e-3 |
| cosine-16 | 0.0278 | 1536 | 2.61 % | 0.39 % | 3.1e-5 | 9.3e-5 |
| uniform-16 | 0.0000 | 1536 | 1.13 % | 0.40 % | 2.6e-3 | 2.9e-3 |
| cosine-20 | 0.0230 | 1920 | 1.80 % | 0.32 % | 1.2e-5 | 5.4e-5 |
| cosine-24 | 0.0000 | 2304 | **1.06 %** | 0.19 % | 6.0e-6 | 2.9e-5 |
| uniform-40 (cross-check) | 0.0000 | 3840 | 0.52 % | 0.007 % | 1.1e-3 | 1.4e-3 |

### 3.1 The hypothesis is confirmed — but it is not the whole mechanism

At identical cost, **uniform-8 halves the elevon error versus cosine-8
(3.82 % vs 7.71 %, 2.0× better)**. Alignment matters, and it is measurable.

But alignment alone does not explain the pattern. `cosine-12` also lands an edge
*exactly* on the hinge (0.75 is edge i = 8 of 12 cosine panels) yet still shows
3.83 % — worse than `uniform-12`'s 2.04 %. So uniform spacing helps for a second
reason beyond edge alignment: it distributes panels more evenly over the flap's
chordwise extent instead of clustering them at the leading and trailing edges.

The honest statement is therefore **empirical**: uniform spacing roughly halves the
elevon-derivative error at fixed cost, and exact hinge alignment is part but not
all of why.

### 3.2 …and uniform spacing must nevertheless be rejected

The cost of giving up leading-edge clustering is not in the lift, which barely
moves — it is in the **pitch-stability quantities**:

| quantity | cosine-8 | uniform-8 | uniform penalty |
|---|---|---|---|
| Xnp | 3.6e-4 | 5.1e-3 | **14× worse** |
| Cmq | 3.2e-4 | 4.7e-3 | **15× worse** |
| CL | 1.37 % | 2.29 % | 1.7× worse |
| CLα | 1.3e-4 | 2.1e-4 | 1.6× worse |

And the penalty **does not go away with refinement**: uniform-40 still shows
Xnp 1.1e-3 and Cmq 1.4e-3, two orders of magnitude worse than cosine-20's
1.2e-5 / 5.4e-5. The leading-edge suction peak sets the pitching moment, and
cosine clustering is what resolves it.

Trading a 14× degradation in neutral-point accuracy for a 2× gain in elevon
authority is the wrong trade for a *stability-and-control* study. **Uniform
spacing is rejected.**

### 3.3 The reference is trustworthy

uniform-40 and cosine-40 agree to **0.52 % on CL_δe, 0.007 % on CL and 0.007 % on
CLα**. Two different spacing laws converging to the same answer confirms both are
converging to the same physics, and that cosine-40 is a sound reference.

### 3.4 The production error is worse than first measured

Against this finer cosine-40 reference, cosine-8's CL_δe error is **7.71 %**, not
the 6.01 % measured against the coarser cosine-20 reference in Task 4b. The Task-4b
figure understated it because its own reference was not converged. Quote 7.7 %.

## 4. Recommendation

Keep **cosine** spacing and increase resolution. The choice is then a cost curve:

| nchordwise (cosine) | CL_δe err | CL err | Xnp err | vortices @ 25/4 |
|---|---|---|---|---|
| 8 (current) | 7.7 % | 1.4 % | 3.6e-4 | 1536 |
| 16 | 2.6 % | 0.39 % | 3.1e-5 | 3072 |
| **24** | **1.1 %** | 0.19 % | 6.0e-6 | 4608 |

**24 chordwise panels** brings elevon authority to ~1 %, which is the level at
which the +2–5.8 % ASB elevon bias (DECISION-0007) and the ±1.5 % section-alignment
floor (Task 4a) become the dominant control-authority errors rather than the
chordwise grid. It fits inside AVL's ~6000-vortex limit at 25 sections / 4
spanwise (4608 vortices).

16 remains a reasonable economy setting for force/stability work where the elevon
derivative is not the object of study.

## 5. Assumptions and limits

- **Hinge at x/c = 0.75 throughout.** The DoE varies `elevon_hinge_frac` over
  0.652–0.814, so the hinge-to-edge distance — and hence the error — varies across
  the design space. This study fixes it at the nominal 0.75; the error at other
  hinge positions is not mapped, and could be worse where the hinge falls further
  from an edge.
- **One operating point** (α = 6°, δe = 4°).
- **Reference is cosine-40, not truth.** Errors are convergence increments. The
  uniform-40 cross-check bounds the reference's own error at ~0.5 % on CL_δe.
- **2 spanwise panels per interval**, chosen to afford the fine reference. Absolute
  vortex counts therefore differ from the Task-4b tables; the chordwise *trends*
  are what transfers.
- **Only two spacing laws** were tested (AVL Cspace = 1 and 0). AVL also supports
  sine and −1 spacing; these were not explored.
- **A surface split at the hinge line** — the standard AVL technique for an exactly
  resolved flap — was not attempted. It is the principled fix and remains open.

## 6. Conclusions

1. The elevon's large discretisation error is caused by the hinge falling
   mid-panel, confirmed: uniform-8, which aligns an edge exactly with the hinge,
   halves the error at identical cost.
2. Edge alignment is **part but not all** of the mechanism — an aligned cosine grid
   still underperforms an aligned uniform grid at the same count.
3. **Uniform spacing is nevertheless rejected**: it degrades Xnp and Cmq by 14–15×,
   and the penalty persists under refinement, because leading-edge clustering is
   what resolves the pitching moment.
4. **Recommendation: cosine spacing, nchordwise = 24** (CL_δe 1.1 %), or 16 as an
   economy setting for non-control work. Not 8.
5. The production error was **understated** by Task 4b (6.0 %) because that study's
   reference was itself unconverged; against a finer reference it is 7.7 %.
6. A surface split at the hinge line is the principled fix and is left open.
