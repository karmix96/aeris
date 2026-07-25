# Study — Two separate convergence studies: geometry sections, then AVL panels

Date: 2026-07-25
Decision produced: `decision/0009-lowfi-discretisation.md`
Script: `standalone/lowfi_avl_study/convergence_study.py`
Evidence: `configs/aero/lowfi_discretisation_evidence/`

## 1. Question — and why the prior study could not answer it

`scripts/section_study.py` varied the number of extraction sections and read off
"convergence". That measurement is **confounded by construction**, because in the
native writer

    total spanwise panels per side = (n_sections − 1) × spanwise_panels_per_section

so adding sections silently refines the vortex-lattice grid at the same time. Any
curve from that design superposes two independent effects:

- **(a) geometry-section independence** — how many spanwise slices of the pyGeo
  loft are needed before the *shape handed to AVL* stops changing;
- **(b) AVL-panel independence** — how fine the *vortex lattice on that shape*
  must be before the VLM solution stops changing.

These have different causes, different costs, and different fixes. Conflating them
means you cannot tell whether a coarse answer is a geometry problem or a
paneling problem — and therefore cannot know what to spend budget on.

## 2. Method — separation by construction

**(a) Geometry mode.** Vary `n_sections` while holding the **total spanwise panel
count fixed at 96 per side**. Section counts are chosen so that (n−1) divides 96
exactly — n ∈ {5, 7, 9, 13, 17, 25, 33, 49} with 24, 16, 12, 8, 6, 4, 3, 2
panels per interval respectively. Every level therefore has **exactly 192 strips
and the same chordwise resolution**; only geometric fidelity changes.

**(b) Panel mode.** Hold `n_sections` fixed at 25 and sweep spanwise panels per
interval (1…10) and chordwise panels (4…20) **one at a time**. Only the lattice
changes.

Run (a) then (b), since (b) needs (a)'s answer as its fixed section count.

Both modes run over **5 DoE seeds** (3 for the chordwise-16 replication) and
report the **worst seed** as well as the median — a discretisation is only
converged if it is converged *everywhere* in the design space, not on average.

Reference for each mode is its own finest level. Purely geometric quantities
(Sref, Bref, Cref, AR) are tracked alongside the aerodynamics to separate "the
shape has converged" from "the aerodynamics of the shape has converged".

### Guarding against a self-inflicted confound

Mode (a) was first run at the production chordwise resolution of 8. Mode (b) then
revealed that chordwise 8 is itself far from converged (§4). That would make (a)'s
conclusions suspect — a section-convergence curve measured on an unconverged
chordwise grid could be an artefact of it.

So **(a) was re-run at chordwise 16** over 3 seeds. The conclusions are unchanged
(worst-seed at n = 25: CL 0.148 % at chord 16 vs 0.144 % at chord 8; CL_δe 1.37 %
vs 1.46 %; the same non-monotonic CL_δe pattern). Mode (a) is therefore *not* an
artefact of the coarse chordwise grid.

## 3. Result (a) — geometry sections: 25 is enough for forces, not for the elevon

Worst-seed relative error against n = 49, panel count fixed:

| n_sections | worst force/stability field | worst error | CL_δe error |
|---|---|---|---|
| 5 | CDind | 15.5 % | 52.4 % |
| 7 | Cnb | 7.01 % | 24.1 % |
| 9 | Cnb | 4.94 % | 14.8 % |
| 13 | CDind | 1.94 % | **0.33 %** |
| 17 | CDind | 0.72 % | 1.55 % |
| **25** | e | **0.56 %** | 1.46 % |
| 33 | cd_profile | 0.51 % | 0.36 % |

Pure geometry converges much faster than the aerodynamics: Sref is within 0.05 %
by n = 9 and 0.026 % by n = 25; Cref within 0.31 % by n = 13. Bref is exact at
every level because both span ends are always included. **So "the shape has
converged" is reached long before "the aerodynamics has converged"** — geometric
metric convergence is not a safe proxy, and a study that only checked area/MAC
would have declared victory at n = 9.

### The elevon derivative is non-monotonic — and that is the real finding

CL_δe error against n: 52.4 %, 24.1 %, 14.8 %, **0.33 %**, 1.55 %, 1.46 %, 0.36 %.

It is **not monotonic**: n = 13 beats n = 17 and n = 25. This is not noise — the
same pattern appears in both the chord-8 (5 seeds) and chord-16 (3 seeds) runs.

The mechanism is band-edge alignment. Sections are snapped exactly onto
`elevon_start_frac` / `elevon_end_frac` (DECISION-0005), but AVL still ramps the
control gain linearly over the interval *just outside* each edge, and that
interval's width depends on where the neighbouring section happens to fall. The
result is an oscillatory ~±1.5 % floor on control authority that does **not**
decrease smoothly with n.

The absolute value does converge — seed 7000: CL_δe = 0.009575 (n=13), 0.009739,
0.009398, 0.009495, 0.009506, 0.009531 (n=49), with the n=33→49 increment only
+0.3 % — but the approach oscillates rather than decays.

**Consequence:** you cannot buy control-derivative accuracy reliably by adding
uniform sections. That is the central motivation for adaptive section placement
(Task 6).

## 4. Result (b) — the chordwise grid is the dominant error, and it was mis-set

### (i) Spanwise panels — the production setting is fine

25 sections fixed, chordwise 8, worst-seed error vs 10 panels/interval:

| panels/interval | total per side | worst field | worst error |
|---|---|---|---|
| 1 | 24 | Clp | 2.85 % |
| 2 | 48 | Clp | 1.29 % |
| 3 | 72 | Clp | 0.75 % |
| **4** | **96** | Cnb | **0.54 %** |
| 6 | 144 | Cnb | 0.30 % |
| 8 | 192 | cd_profile | 0.36 % |

Monotone and well behaved; the roll-damping derivative Clp is the limiting
quantity at coarse resolution, which is expected since it depends on the outboard
spanwise loading gradient. **4 panels per interval is adequate** (≤0.54 %), and 6
buys a further factor ~1.8 for 50 % more cost.

### (ii) Chordwise panels — 6 % error on control authority at the production setting

25 sections fixed, 4 spanwise panels, worst-seed error vs 20 chordwise:

| nchordwise | worst field | CL_δe | CDind | CL |
|---|---|---|---|---|
| 4 | CL_δe | 15.2 % | 4.77 % | 2.95 % |
| 6 | CL_δe | 7.81 % | 4.60 % | 1.58 % |
| **8 (production)** | CL_δe | **6.01 %** | **3.28 %** | 1.08 % |
| 12 | CL_δe | 2.07 % | 1.20 % | 0.31 % |
| 16 | CL_δe | **0.82 %** | 0.39 % | 0.074 % |

**This is the largest discretisation error anywhere in the low-fidelity chain**, and
it sits in the production default. At `nchordwise = 8` the elevon control
derivative carries a **6 % error** — comparable in magnitude to the AeroSandbox
elevon defect that DECISION-0007 judged disqualifying. Induced drag carries 3.3 %.

The mechanism is hinge resolution. With AVL's cosine chordwise spacing and 8
panels the panel edges fall at

    x/c = 0, 0.038, 0.146, 0.309, 0.500, 0.691, 0.854, 0.962, 1.000

and the elevon hinge at x/c = 0.75 lands **between** 0.691 and 0.854 — nowhere
near an edge. AVL must then smear the control gain across that panel. Refining
chordwise moves an edge closer to the hinge, which is why CL_δe improves ~7× from
8 to 16 panels while CL improves only ~15×… i.e. the control derivative is
disproportionately sensitive to this specific geometric coincidence, not to
chordwise resolution per se.

CL_δe is the limiting quantity at *every* chordwise level, which is itself the
diagnostic: if this were generic under-resolution, the worst field would move
around.

## 5. Budget constraints discovered

Two hard AVL array limits bind the joint refinement:

| limit | constraint | binds at |
|---|---|---|
| NSMAX = 500 strips (both halves) | (n_sections − 1) × spanwise_panels ≤ 250 | n = 65 at 4 panels/interval → 512, **fails** |
| NVMAX ≈ 6000 vortices | strips × nchordwise ≤ ~6000 | n = 49, 4 spanwise, 16 chordwise → 6144, **fails** |

So refining sections and chordwise resolution simultaneously is not free:

| configuration | strips | vortices | status |
|---|---|---|---|
| 25 / 4 / 8 (production) | 192 | 1536 | ok |
| 25 / 4 / 16 (recommended) | 192 | 3072 | ok |
| 33 / 4 / 16 | 256 | 4096 | ok |
| 49 / 4 / 16 | 384 | 6144 | **exceeds NVMAX** |

**This is a quantified ceiling on what uniform refinement can buy**, and a direct
argument for spending the section budget adaptively rather than uniformly
(Task 6): adaptive placement raises geometric fidelity *without* spending strips.

## 6. Assumptions and limits

- **One operating point** (α = 6°, δe = 4°, β = 0°). Convergence rates may differ
  near CL_max, where the polar bridge begins clamping strips.
- **Reference is the finest level, not truth.** Errors are convergence increments,
  not accuracy. At n = 33 the increment to n = 49 is ≤0.5 %, so the reference is
  a reasonable proxy — but a Richardson-extrapolated limit was not formed.
- **Cosine chordwise, uniform spanwise spacing throughout** (AVL Cspace = 1,
  Sspace = 0). The interaction between spacing *law* and hinge position is
  examined separately (`studies/hinge_panel_alignment.md`).
- **Sections are uniformly spaced** apart from the two snapped onto the elevon band
  edges. The whole point of Task 6 is that this is not optimal.
- **5 seeds** (3 for the chord-16 replication). Whether that is enough for the
  worst-case statistic to be design-space representative is Task 5.
- The chord-16 replication used 3 seeds, not 5, so it confirms the *shape* of the
  conclusion rather than reproducing every number to the same confidence.

## 7. Conclusions

1. **The two effects are now separated**, and they have different answers:
   geometry sections converge by ~25, while the *chordwise* grid — which the old
   conflated study could not isolate — is the dominant error source and was
   mis-set at 8.
2. **Geometry: n_sections = 25** gives ≤0.56 % worst-seed on all forces and
   stability derivatives. Robust to chordwise resolution (verified by replication
   at chord 16).
3. **Geometric metrics converge far earlier than aerodynamics** (Sref to 0.05 % by
   n = 9), so area/MAC convergence must not be used as a proxy for aerodynamic
   convergence.
4. **The elevon derivative does not converge monotonically** — it has an
   oscillatory ~±1.5 % floor set by section alignment against the control-band
   edges, not by resolution. Uniform refinement cannot reliably fix it.
5. **Spanwise 4 panels/interval is adequate** (≤0.54 %).
6. **Chordwise must increase from 8 to 16.** At 8, CL_δe carries 6.0 % error and
   CDind 3.3 %; at 16 these fall to 0.82 % and 0.39 %. The cause is the elevon
   hinge at 0.75 c falling mid-panel under cosine spacing.
7. **Two AVL array limits quantify a real ceiling** on uniform refinement
   (≤250 strips per side, ≤~6000 vortices), which is why adaptive section
   placement is worth pursuing rather than simply buying more sections.
