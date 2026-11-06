# Stage 0 decisions

These are the starting values the whole project is judged against. For each one: **the value**,
**what it means in practice**, **why we chose it**, and **the source**. The same values, in a form a
program can read, are in `values.yaml`. Updated 7 Nov 2026 (first updated 2 Nov 2026 with the
Stage 1 findings). The page "CFD Automation Stage 0" mirrors this file.

## A few words first

- **CD, CL, CM**: drag, lift and pitching-moment coefficients. They are the wing's forces divided by
  its size and the flow speed, so wings of different sizes can be compared.
- **Drag count**: 0.0001 of CD. A typical wing has CD around 0.0100–0.0300, i.e. 100–300 counts.
- **Mesh**: the grid of small cells around the wing that the solver computes on. A finer mesh is
  more accurate and slower.
- **Error**: how far our computed number is from the true one.
- **Residual**: how far the solver still is from a finished answer on one mesh. It falls as the
  solver iterates.
- **Proposal, pending**: a proposal that is not decided yet. Everything else here is decided.

## What changed since 2 Nov 2026 (updated 7 Nov)

The sections below are updated to match.

**Decided**
- **New names (2 Nov).** Folder `Stage_0_decisions/` (was "Stage 0_Decisions"). Files `decisions.md`,
  `decisions.html`, `values.yaml` (were `STAGE0_DECISIONS.*` and `stage0_values.yaml`). One
  `CFD_Automation/OPEN_DECISIONS.md` for every stage. Wing sets `training_focus` and `holdout_focus`
  (`training_full`, `holdout_full`, `corner1`, `corner2`, `reference` unchanged). One shared code package,
  `CFD_Automation/cfdauto/`.
- **Stage 1 closed (2 Nov).** Four wing types in two families: tailless (BWB, flying wing) and
  conventional (cranked, tapered). 730 of 730 sampled wings build. Real Class I–II wings with a published
  area fly at Re 1.2 × 10⁵ – 3.1 × 10⁶ on the mean chord (the top is now the NTNU Aludra MK1 row,
  3.1 × 10⁶; it was 2.7 × 10⁶, RUAG Ranger). 2-D strip flow dataset: SA overpredicts profile drag by a
  median +62 % (+69 % in level flight).
- **Stage 2 surface mesh works.** 790 of 790 builds pass 13 checks (numpy loft). A mesh station sits on
  every loft station, so on every break. Tip squeeze: the last spanwise gap = the tip's first wall cell.
  The transition band is built; the upper band starts at the leading edge on every wing. Base cells
  8 / 10 / 14 / 18 at levels C / M / F / FF. Station gap 0.2 × local chord, at least 12 per panel, growth
  1.2. Mesh name `mesh_<level>_<wing_hash8>_re<Re>`: one surface per wing and Re level (Stage 2 decision 59).
- **Transition must be captured, with ADflow and SU2 (owner, 4 Nov).** This replaces "SA for now; final
  choice later". Our ADflow build has SA only (SST aborted) and no transition model, so transition comes
  from SU2 (SST + LM γ-Reθ).
- **Mach (owner, 4 Nov).** No supersonic flow, not even small pockets. The scope extends toward Mach 0.5;
  the cap is still open. The Stage 1 data stop at Mach 0.2 (tables at Mach 0, 0.1 and 0.2).
- **Angles of attack (owner, 6 Nov).** −5° to post-stall (was 0°, 4°, 8°, plus 12° for the nose and wake
  studies), plus a separate post-stall study (URANS or DDES on a few wings). Steady RANS is used up to
  stall onset. The Stage 1 dataset covers root angles 0–10° only.
- **Mesh levels VC, C, M, F (owner, 6 Nov).** VC on the desktop; C, M and F on the university HPC (C,
  about 2.3 M cells, is above the desktop limit of about 1.2 M). Hard minimums at VC: y+ ≤ 1, growth
  ≤ 1.25, base ≥ 8 cells, no kinks, tip gap. Accuracy targets at M, as DPW defines its medium grid: nose
  10°, trailing edge 0.1 % c, station gap, largest cell 2 % c. Transition targets at F: about 20 cells per
  bubble (Ansys CFX guidance). Every spacing ÷ 1.3 per level, so about 2.2× cells per level; wall layers
  about 1.30× per level.
- **Lighter rules (owner, 6 Nov).** Band cell 0.5 % c at F where local Re ≥ 4 × 10⁵ (the bubble-length
  table stops at 0.10 c from local Re 4 × 10⁵ up). Tip gap 2 × s0. Station gap 0.25 × local chord at M.
  Cost (estimates, Stage 2: surface × wall layers, 20 reference wings × 4 Re): fine level about 10–11 M
  cells median on the wing blocks (10.9 M with the band change; 15.2 M with the planned rules). Desktop
  limit about 1.2 M cells.
- **Wall-normal growth (owner, 6 Nov), settled by the mesh levels.** Growth 1.25 at VC is 1.107 at F
  (about 1.30× more wall layers per level), just above the 1.1 a transition model asks for (1.23 at VC would give exactly 1.1) (Stage 2
  decision 57).
- **Volume mesh (owner, 6 Nov).** One matched C-H multiblock mesh for ADflow and SU2, instead of the
  overset wake box and vortex tube. SU2 has no overset and refuses structured CGNS; converted to
  unstructured hexes, it runs. Far field stays at the starting value of 80 chords (ladder 40 / 80 / 160).
  The C-H wake lines may add about +45 % (30–60 %, rough) cells on the wing blocks.
- **Similarity (owner, 6 Nov; D3 section).** Every wing at unit mean chord; the Re on the mean chord is
  the input; Mach fixed at 0.1 (Prandtl–Glauert on CL and CM); trailing edge 0.2 % c. The root chord
  leaves the design vector (18 → 17 numbers). About 8,000 solves instead of 42,000. Built in the Stage 1
  code on 7 Nov; every hash changed and the sets were rebuilt (722 of 722).
- **Lower transition band from the leading edge (owner, 7 Nov; Stage 2 decision 74, option A).** Counted
  first: it costs no cells, because both sides of a ring share one node list; transition runs then reach −5°.
- **Nose shape fixed (owner, 7 Nov; decision 64).** One curvature method along the surface found a real
  defect: the leading edge sat at the farthest raw point, not at the curve's tip, which made a curvature
  spike on one side and a flat spot on the other (NACA 4415: a 0.18 % c nose cell turned 9.47° built
  against 4.31° true). New rule in Stage 1: one cubic spline, the leading edge at its apex, 201 points per
  side; a gate refuses airfoils whose nose folds back (14 of 2,183 database files). The 5 % turning test
  now passes on 95.6 % of the database (21.0 % before). The 6 Nov note that the finding was overstated was wrong.
- **Re levels:** 1 × 10⁵ stays (owner, 7 Nov), 18 % below the slowest real UAV (1.22 × 10⁵ on the mean
  chord), as a margin.
- **First SU2 smoke test (4 Nov), not a result.** It shows the mesh path works; no wing has been run
  (note at the end of D3).

**Proposals, pending**
- **Solver split.** ADflow SA for all mesh studies and the fully turbulent data; SU2 SST + LM on about
  20 % of the wings first.
- **Mach.** Core data at Mach ≤ 0.2 now; Mach 0.3–0.5 later, with a fast-UAV family.
- **Angles.** Mesh studies at −5°, 4° and the highest steady angle. Dataset from −5° to stall in about
  2.5° steps.
- **Re levels.** Check C4 adds a level near 7 × 10⁵ – 10⁶ only if needed.

**Open**
- **Still open from Stage 0:** grid share 65 %, pitching moment 0.002, the iteration share, a D5.
- **pyGeo tests and one `build --all`** on the owner's machine: the rename made every stored hash stale.

---

## D1 — How accurate must the answers be?

### Increment target: ΔCD ≤ 2 counts, ΔCL ≤ 0.005
- **In practice:** when we compare two wings, the error on the *difference* between them must be at
  most 2 drag counts. Example: wing A has CD = 0.0210 and wing B has 0.0205. They are 5 counts apart.
  With a 2-count error we can say "B has less drag". If two wings are less than 2 counts apart, we
  call them a tie.
- **Why:** the workflow is mostly used to pick the better wing, and design changes often move drag
  by only a few counts. The difference is easier to get right than each value alone, because two
  wings meshed the same way carry much of the same error, and it cancels when you subtract.
- **Source:** Morrison, Kleb & Vassberg (DPW observations): "Industry's goal is ±1 drag count."
  We start at 2.
- **Update 2 Nov 2026 (Stage 1 flow study, 2-D strips):** with fully turbulent SA alone, 2 counts is
  a **numerical target only** (mesh and iterations). SA's own error on the drag difference between
  similar wings is 4 counts median and above 2 counts in 71 % of pairs; the ranking flips in 6 %.
  A dataset meant to rank wings or airfoils by drag needs transition-model results, at least on a
  calibration subset (open decision 52 d).

### Absolute drag: max(3 % of CD, 3 counts)
- **In practice:** the drag of one wing may be off from the truth by at most 3 % or 3 counts,
  whichever is larger. CD = 0.0200 → up to 6 counts. CD = 0.0080 → 3 % is only 2.4, so the 3-count
  floor applies. We use this when we compare with a wind tunnel.
- **Why:** expert teams running different codes on the same wing disagree by about 5 counts. One
  checked workflow must do better than that, or its error bar is too wide to be useful.
- **Source:** Levy et al. 2013, Drag Prediction Workshop summary: spread between participants
  σ = 0.00053 (about 5 counts).

### Absolute lift: max(1 % of CL, 0.005)
- **In practice:** CL = 0.8 → up to 0.008. CL = 0.3 → 1 % is 0.003, so the floor 0.005 applies.
- **Why:** set to about the same relative size as the drag budget.
- **Source:** our choice.

### Pitching moment: 0.002
- **In practice:** CM may be off by up to 0.002. CM decides whether the wing is stable in pitch,
  so this matters when we study stability.
- **Why:** a starting value, to be checked when stability is studied.
- **Source:** our choice.

### How the 3 counts of drag error are shared out

The drag of one wing may be wrong by 3 counts (see "Absolute drag" above). That error does not come
from one place. It comes from **four sources**. We give each source a **share** of the 3 counts,
like splitting a budget. A study of one source **stops when that source's error is smaller than its
share**: not before (the answer is not good enough yet) and not long after (we are wasting computer time).

**Summary.** The mesh share is split again into five directions. So there are two "%" columns:
"% of mesh" says how the mesh share is divided; "% of total" is each part's share of the whole
3 counts. Each column adds up to 100 %.

| # | part | what it is | % of mesh | % of total | allowed error | starting value (source) | warning from earlier AERIS tests |
|---|---|---|---|---|---|---|---|
| 1a | Mesh: along the chord | points around the airfoil | 35 % | 22.75 % | 0.68 counts | edge cells ≈ 0.1 % of local chord (DPW); since Stage 2 the transition band also sets cells here (D3) | carried about 88 % of the drag error |
| 1b | Mesh: along the semi-span | sections from root to tip | 15 % | 9.75 % | 0.29 counts | Stage 2: a station on every loft station; gap 0.2 × local chord, ≥ 12 per panel, growth 1.2; last gap at the tip = the tip's first wall cell (our choice; first start was 0.1 % of semi-span at root and tip, DPW). Decided (owner, 6 Nov): tip gap 2 × s0; station gap 0.25 × local chord at M | — |
| 1c | Mesh: away from the wall | thin layers through the boundary layer | 20 % | 13 % | 0.39 counts | first cell y+ ≈ 1; each layer ≤ 1.25 × the previous (DPW). Decided (owner, 6 Nov): 1.25 at VC is 1.107 at F, which meets the 1.1 of a transition model (Ansys CFX) | — |
| 1d | Mesh: edges and blunt trailing edge | cells at nose, trailing edge and across the base | 15 % | 9.75 % | 0.29 counts | 0.1 % of chord at edges (DPW); 8 / 10 / 14 / 18 cells across the base at levels VC / C / M / F (our choice; the first approach named them C / M / F / FF) | base was the slowest part to settle |
| 1e | Mesh: wake | cells behind the wing and around the tip vortex | 15 % | 9.75 % | 0.29 counts | set in the mesh stage (our choice). Decided (owner, 6 Nov): one matched C-H mesh for ADflow and SU2 | refining the near wake moved drag 23 counts |
| **1** | **Mesh, all directions** | cells too big | **100 %** | **65 %** | **1.95 counts** | error bar from 3 meshes (Celik 2008) | — |
| 2 | Iterations | solver stopped too early | — | 10 % | 0.30 counts | stopping rule in D3 (Celik 2008: < 1/10 of mesh error = 0.195) | measured 0.12 counts at 10⁻⁶: OK |
| 3 | Outer boundary | domain edge too close to the wing | — | 10 % | 0.30 counts | ≈ 100 reference chords (DPW); the project's starting value is 80 chords, ladder 40 / 80 / 160 | 40 → 60 chords moved drag 0.6–0.7 counts: 40 is too close |
| 4 | Numerical settings | artificial smoothing in the solver | — | 15 % | 0.45 counts | our choice | halving it moved drag 12–21 counts: biggest risk |
| | **Total** | | | **100 %** | **3.00 counts** | | |

DPW = Drag Prediction Workshop gridding guidelines (Levy et al. 2013).

We simply add the errors. That is the safe way: in practice some of them partly cancel.

The percentages are **our plan**, not measured. Once the first mesh study shows where the error
really sits, the split can change, but only by a written decision and before the next results.

#### 1. Mesh error: 1.95 counts (65 % of 3)
- **What it is:** the error that comes from the cells being too big. On an infinitely fine mesh it
  would be zero.
- **How we measure it:** build the same mesh at three sizes and compute the error bar (GCI, see D3).
- **When it is good enough:** the drag error bar is at most 1.95 counts.
- **Why it gets the biggest share:** in almost every CFD study the mesh is the largest source of error.
- **Source:** the share is our choice. The method is Celik et al. 2008.

The mesh error is then split by direction, because each direction is refined separately and costs
a different amount.

**1a. Along the chord: 0.68 counts.**
- **What it is:** the number of points around the airfoil, from the trailing edge, round the nose
  and back.
- **What goes wrong if there are too few:** the sharp pressure peak at the nose and the pressure
  rise towards the trailing edge are smoothed out, so the pressure drag is wrong.
- **Starting mesh from the source:** cells at the leading and trailing edge about 0.1 % of the
  local chord long. Since Stage 2 the transition band also sets cells along the chord (D3,
  turbulence model).
- **Why it gets the largest part:** it is the most expensive direction to refine, and in earlier
  AERIS tests it carried most of the drag error (about 88 %).
- **Source:** Drag Prediction Workshop gridding guidelines (Levy et al. 2013).

**1b. Along the semi-span: 0.29 counts.**
- **What it is:** the number of sections from the root to the tip.
- **What goes wrong if there are too few:** the lift is spread wrongly along the semi-span, mostly
  near the tip, which changes the induced drag.
- **Starting mesh (Stage 2, 2 Nov 2026):**
  - a mesh station on every loft station, so on every break;
  - station gap 0.2 × local chord, at least 12 gaps per panel, growth 1.2 inside a panel;
  - tip squeeze: the last gap at the tip = the tip's first wall cell (s0).
  - The first start was the DPW value: spacing at the root and at the tip about 0.1 % of the semi-span.
- **Decided (owner, 6 Nov):** tip gap 2 × s0; station gap 0.25 × local chord at level M.
- **Source:** Stage 2 decision 62 (our starting values, to be tested in the spanwise ladder); DPW
  gridding guidelines (Levy et al. 2013) for the first start.

**1c. Away from the wall: 0.39 counts.**
- **What it is:** the layers of thin cells from the wing surface out through the boundary layer
  (the thin slow layer of air on the surface).
- **What goes wrong if they are too coarse:** the friction drag is wrong.
- **Starting mesh from the source:**
  - first cell at y+ ≈ 1 (small enough to sit inside the very thin layer next to the wall);
  - each layer at most 1.25 times thicker than the one before.
- **Decided (owner, 6 Nov), settled by the mesh levels (D3):** growth 1.25 at VC is 1.107 at F, because
  each level has about 1.30× more wall layers. That is just above the 1.1 a transition model asks for (1.23 at VC would give exactly 1.1) (Ansys CFX
  guidance; 1.2 already moves transition a little upstream). Stage 2 decision 57. It changes the layer
  count, not the surface.
- **Source:** DPW gridding guidelines (Levy et al. 2013); Ansys CFX Modeling Guide for 1.1.

**1d. Edges and blunt trailing edge: 0.29 counts.**
- **What it is:** the cells at the nose, at the trailing edge, and across the flat back face of the
  thick trailing edge (the "base").
- **What goes wrong:** air leaves the base with low pressure, which pulls the wing back (extra drag).
  Too few cells across the base get that pressure wrong.
- **Starting mesh:** 0.1 % of chord at the edges (DPW). Across the base: 8 cells at level C, 10 at M,
  14 at F, 18 at FF (Stage 2 decision 61). The counts are even, so the tip cap's nose arc stays
  centred. So the steps are 1.25, 1.4 and 1.29, not exactly 1.3: the one spacing that does not follow
  the family ratio exactly.
- **Why a separate part:** in earlier AERIS tests the base was the slowest part to settle with
  refinement.
- **Source:** DPW guidelines for the edges. The base cell counts are our choice (earlier AERIS tests;
  Stage 2).

**1e. Wake: 0.29 counts.**
- **What it is:** the cells behind the wing and around the tip vortex (the swirl that leaves the
  wing tip).
- **What goes wrong if they are too coarse:** the wake and the vortex smear out, which changes the
  pressure at the trailing edge and the induced drag.
- **Why it matters:** in earlier AERIS tests, refining only the near wake moved drag by 23 counts.
- **Decided (owner, 6 Nov):** one matched C-H multiblock mesh for ADflow and SU2, instead of the overset
  wake box and tip-vortex tube (SU2 has no overset and refuses structured CGNS; converted to unstructured
  hexes, it runs). The C-H wake lines run to the far field and may add about +45 % (30–60 %) cells on the
  wing blocks (rough count).
- **Source:** the share is our choice; the wake-mesh rules are set in the mesh stage.

#### 2. Iterations: 0.30 counts (10 % of 3)
- **What it is:** the error from stopping the solver before it has finished.
- **How we measure it:** let a few runs continue past the stopping point and see how much the forces
  still change.
- **When it is good enough:** the stopping rule in D3.
- **Check:**
  - earlier AERIS runs continued past 10⁻⁶ moved drag by at most 0.12 counts, inside 0.30;
  - Celik's stricter rule asks for less than one tenth of the mesh error, i.e. 1.95 ÷ 10 = 0.195
    counts. Our share of 0.30 is looser than that, but the measured 0.12 meets both.
- **Source:** Celik et al. 2008 (Appendix A); Eça & Hoekstra 2006.

#### 3. Outer boundary: 0.30 counts (10 % of 3)
- **What it is:** the computer domain has to end somewhere. If its outer edge is too close to the
  wing, the edge disturbs the flow around the wing.
- **How we measure it:** move the outer edge further out (40, 80, 160 chords), keeping the mesh near
  the wing the same, and see how much the drag changes.
- **Starting value:** the source suggests about 100 reference chords. The project's starting value is
  80 chords, tested with the ladder 40 / 80 / 160.
- **Check:** in earlier AERIS tests, going from 40 to 60 chords moved drag by 0.6–0.7 counts. That is
  more than 0.30, so 40 chords is too close; expect about 80–100.
- **Source:** DPW gridding guidelines (Levy et al. 2013); 80 chords is our starting value.

#### 4. Numerical settings: 0.45 counts (15 % of 3)
- **What it is:** the solver adds a little artificial smoothing ("dissipation") to stay stable. Too
  much smoothing behaves like extra friction and adds false drag.
- **How we measure it:** halve and double the smoothing setting on two mesh sizes. The effect must
  shrink as the mesh gets finer, and be at most 0.45 counts on the mesh we use.
- **Warning:** in earlier AERIS tests, halving the smoothing moved drag by 20.6 counts on the coarse
  mesh and 12.0 on the medium mesh. That is far above 0.45 counts, so this is a real risk.
- **Source:** our choice.

### Turbulence-model error: its own band, never inside the mesh budget
- **In practice:** every drag number is reported as "value ± mesh error", and separately
  "± model error". A finer mesh cannot remove model error, so the two are never added into one number.
- **Why:** mesh error is about how well we solve the equations. Model error is about whether the
  equations describe the real air. They are different problems with different fixes.
- **Source:** ASME V&V 20-2009, which keeps numerical, input and experimental uncertainty apart.

---

## D2 — Which wings do we test?

The wing generator is new, so the wings are defined by **rules**, not by name. Counts are per wing
type: four types in two families, tailless (BWB, flying wing) and conventional (cranked, tapered).
BWB and cranked have 17 variables; flying wing and tapered have 13.

### Reference wings: 5 per wing type
- **In practice:** five wings we study in depth with every mesh study: one with every variable at
  mid-range; the smallest-area and the largest-area wing of the training set; the most swept wing
  with the smallest tip; the most twisted wing. They are chosen before any mesh is built, and never
  swapped after we see a result.
- **Why:** a mesh rule that works on one wing is true for one wing. Five spread-out wings show how
  the mesh needs change across the design space, and five is still affordable.
- **Source:** our choice.

### Coverage check
- **In practice:** we check that the five are spread out, not bunched together. For each training
  wing we find its nearest reference wing; the largest of those distances must be no worse than for
  a typical set of five picked at random (the median of 1,000 random sets). Distances are measured
  with every variable scaled to 0–1.
- **Source:** Johnson, Moore & Ylvisaker 1990 (minimax distance designs).

### Training set: 100 wings per type in the focus space, plus 40 in the full space
- **In practice:** `training_focus`: 100 wings spread evenly over all variables of the focus space.
  `training_full`: 40 more over the full space. The mesher must build all of them; they show where it
  works.
- **Why Latin hypercube:** each variable's range is cut into 100 slices and each slice is used once,
  so no part of any range is left empty.
- **Source:** McKay, Beckman & Conover 1979.

### Corner sets: 42 extreme wings for 17 variables, 33 for 13
- **In practice:**
  - Part 1 (`corner1`): each variable pushed to its lowest and then its highest value, the others
    in the middle: 34 wings for BWB and cranked, 26 for flying wing and tapered. This shows which
    single variable breaks the mesher.
  - Part 2 (`corner2`): every pair of variables appears at all four combinations (low-low, low-high,
    high-low, high-high): 8 wings for 17 variables, 7 for 13. This shows when two extremes together
    break it.
  - A corner wing that fails stays in the list. It marks the edge of what the workflow can do.
- **Arithmetic for part 2:** the smallest N with C(N−1, ⌈N/2⌉) ≥ the number of variables.
  - 17 variables: N = 7 → C(6, 4) = 15, too few. N = 8 → C(7, 4) = 35, enough. So 8 wings, the proven
    minimum.
  - 13 variables: N = 6 → C(5, 3) = 10, too few. N = 7 → C(6, 4) = 15, enough. So 7 wings.
- **Decided (owner, 6 Nov; similarity, D3):** the root chord leaves the design vector, so part 1 becomes
  32 / 24 wings (2 per free variable) instead of 34 / 26. Being built in the Stage 1 code now.
- **Source:** Katona 1973; Kleitman & Spencer 1973.

### Hold-out sets: 10 + 5 wings per type, opened once at the end
- **In practice:** `holdout_focus`: 10 wings in the focus space; `holdout_full`: 5 in the full space.
  Drawn now and locked away. Nobody builds or looks at them until every rule is final. Then they are
  run once, and the result is the honest test of "it works on wings it has never seen".
- **Why:** if we look at the test wings while tuning, we tune to them without meaning to, and the
  test stops being a test.
- **Source:** Dwork et al. 2015 (Science), 2017 (CACM).

### Robustness: 0 failures in at least 150 wings
- **In practice:** if the workflow succeeds on all 150 wings (training + corner + hold-out), we may
  claim that at least about 98 % of all wings in the design space will work, with 95 % confidence.
- **Counts per type:** the built sets give 185 wings (BWB, cranked: 100 + 5 + 40 + 32 + 8) or 176
  (flying wing, tapered: 100 + 5 + 40 + 24 + 7; before similarity 187 and 178, with 34 and 26 corner wings); the hold-outs (10 + 5) run once at the end. The focus
  sets alone give 105 (115 with the focus hold-out), below 150, so the ≥ 98 % claim needs the full-space
  sets too.
- **Arithmetic:** the most the failure rate can be is 1 − 0.05^(1/150) = 1 − 0.98022 = 1.98 %.
  Quick rule: 3 ÷ 150 = 2.0 %.
- **Source:** Hanley & Lippman-Hand 1983 ("rule of three").

---

## D3 — Flow conditions and how we measure

### Speed: no supersonic flow; the scope extends toward Mach 0.5, cap still open (owner, 4 Nov 2026; was Mach ≤ 0.3)
- **In practice:** no supersonic flow anywhere, not even small pockets on the wing. The scope extends
  toward Mach 0.5, about 170 m/s at sea level; the cap is still open.
- **Why:** the owner's scope. The focus wings fly at Mach 0.03–0.2.
- **Limit:** the Stage 1 data stop at Mach 0.2 (section tables at Mach 0, 0.1 and 0.2).
- **Decided (owner, 6 Nov; similarity, below):** the solves run at Mach 0.1, with a Prandtl–Glauert
  correction on CL and CM.
- **Proposal, pending:**
  - core data at Mach ≤ 0.2 now;
  - Mach 0.3–0.5 later, with a fast-UAV family (real fast UAVs, thinner sections, section tables to
    Mach 0.5);
  - at Mach 0.5 the angle is capped near 4° by a supersonic-pocket check. 2-D estimate: pockets from
    5.5–6.5° at Mach 0.5, 8–9.5° at 0.4, only near stall at 0.3.
- **Source:** our choice (owner).

### Reynolds numbers: 1 × 10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶ (on the mean chord; top was 5 × 10⁶ until 29 Oct 2026; 1 × 10⁵ added 30 Oct 2026)
- **In practice:** the Reynolds number says how "big and fast" a wing is for the air:
  Re = air density × speed × chord ÷ air viscosity. A small, slow wing has low Re; a large, fast
  wing has high Re. Example: a 0.2 m chord at 25 m/s and 1,500 m gives about 3 × 10⁵.
  Every mesh study is run at these four levels, because the cells next to the wall must be smaller
  at higher Re.
- **Why these four:** from the slowest mini Class I wings to the fastest Class II wings with a
  published wing area (see the updates below the check).
- **Source:** NATO UAS class table; ISA atmosphere; Sutherland's law.

**Reynolds check.** Re = ρVc/μ, ISA atmosphere, Sutherland viscosity.

| altitude | ρ [kg/m³] | μ [Pa·s] | ρ/μ [s/m²] |
|---|---|---|---|
| 0 m | 1.2250 | 1.789e-5 | 6.85e4 |
| 1,524 m | 1.0555 | 1.741e-5 | 6.06e4 |
| 3,048 m | 0.9046 | 1.692e-5 | 5.35e4 |

| aircraft (class) | speed | Re per m chord | chord for 3e5 |
|---|---|---|---|
| Raven (I mini) | cruise 8.3 m/s, sea level | 5.7e5 | 0.53 m |
| ScanEagle (I small) | cruise 24.7 m/s, 1,524 m | 1.5e6 | 0.20 m |
| Shadow (II) | cruise 36 m/s, 3,048 m | 1.9e6 | 0.16 m |
| Hermes 450 (II) | max 48.9 m/s, sea level | 3.3e6 | 0.09 m |

Example: 6.06e4 × 24.7 = 1.50e6 per metre. Reaching 3 × 10⁵ needs 3e5 / 1.50e6 = 0.20 m chord.

Result: small Class I and Class II sit between 3 × 10⁵ and about 3 × 10⁶. Mini/micro Class I
(Raven, 1.4 m full span) sit below 3 × 10⁵. 5 × 10⁶ is a safe upper end.

**Update 29 Oct 2026: top level lowered to 3 × 10⁶.** The check above used chords guessed per
aircraft. A sourced table of real Class I–II wings with a published wing area
(`Stage_1_geometry/configs/real_uavs.yaml`) gives Re 1.2 × 10⁵ to 2.1 × 10⁶ (mean chord = area / full
span; cruise at 3,048 m to top speed at sea level). The highest is the AAI Pioneer (Class II, 5.15 m
full span, mean chord 0.549 m, 56.7 m/s). No wing of our families reaches 5 × 10⁶, so the levels are now
**3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶**. Class II wings with a published area (Götten et al. 2021; Essari
2015 thesis with Jane's-style data for Hermes 450, Ranger, Seeker, Shadow 600) have mean chords of
0.55–0.66 m and reach Re 2.1–2.7 × 10⁶ at top speed and sea level; the highest is the RUAG Ranger
(2.74 × 10⁶), rounded up to 3 × 10⁶.

**Update 30 Oct 2026: level 1 × 10⁵ added (Mike).** Real Class I wings fly at 1.2–3 × 10⁵ (Black Swift
S0, eBee) and the geometry focus space reaches 8 × 10⁴; the lowest level, 3 × 10⁵, missed that whole
decade. Cost: about a third more runs. Wing tips reach 1–2 × 10⁴; no level there, because no RANS model
is reliable at those values (stated as a limit). At 1 × 10⁵ the SA result tests the mesh, not the
flow: the model band is largest there (see the turbulence-model decision).

**Update (31 Oct 2026, decision 49; Stage 1 closed 2 Nov): real wings now reach 3.1 × 10⁶.** With the
NTNU and CNAS database rows, real Class I–II wings with a published area fly at Re 1.2 × 10⁵ – 3.1 × 10⁶
on the mean chord. The top is now the NTNU Aludra MK1 row at its listed top speed (3.1 × 10⁶; its area
comes from the listed full span and aspect ratio). Before, it was the RUAG Ranger (2.7 × 10⁶). The
levels are unchanged. The Aludra row is 3 % above the top level, and its listed chord (0.60 m)
disagrees with full span ÷ aspect ratio (0.74 m): check the row before quoting it.

**Decided (owner, 6 Nov; similarity, below):** Re on the mean chord is the input, so every shape runs
at all four levels. **Proposal, pending:** the Re levels: check C4 adds a level near 7 × 10⁵ – 10⁶ only
if needed.

### Similarity: unit mean chord, Re as the input, Mach 0.1 (owner, 6 Nov 2026)
- **In practice:** every wing is solved at a mean chord of 1, and the Reynolds number on that chord is
  set directly as the input. Mach is fixed at 0.1, with a Prandtl–Glauert correction on CL and CM.
  Fixed once: trailing edge 0.2 % c; Tu 0.07 % (N_crit 9); T 288.15 K; γ 1.4; Pr 0.71; adiabatic wall.
- **Status:** being built in the Stage 1 code now. All hashes change.
- **What it changes:**
  - the root chord leaves the design vector (18 → 17 numbers);
  - meshes per wing 21 → 4;
  - dataset 42,000 → 8,000 solves at 5 angles; about 12,800 with about 8 angles from −5° to stall (the
    angle steps are still pending, see Angles);
  - corner set, part 1: 32 / 24 wings (2 per free variable) instead of 34 / 26 (D2).
- **Checks first:** C1 scale; C2 Mach; C3 trailing edge; C4 Re-level interpolation (add a level near
  7 × 10⁵ – 10⁶ only if needed; still pending).
- **Why:** CL, CD and CM depend on the shape, Re and Mach, not on the size itself. One mesh per wing
  and Re level then serves every real size and speed with that Re.
- **Limit:** Re does not carry surface roughness or air turbulence.
- **Source:** Anderson, Fundamentals of Aerodynamics, 5th ed., 2011 (similarity §1.7–1.8;
  Prandtl–Glauert §11.4–11.6). The fixed values are our choice.

### Angles of attack: −5° to post-stall, plus a post-stall study (owner, 6 Nov 2026)
- **In practice:** steady RANS from −5° up to stall onset. Past stall, a separate study with URANS or
  DDES on a few wings. Before 6 Nov: every study at 0°, 4° and 8°; studies of the leading edge and the
  wake also at 12°.
- **Why:** cruise, climb, high lift, and negative angles. At high angle the flow turns sharply round
  the nose, which needs finer cells there. At negative angles the lower surface becomes the suction side.
- **Limit:** the Stage 1 dataset covers root angles 0–10° only.
- **Proposal, pending:** mesh studies at −5°, 4° and the highest steady angle; the dataset from −5° to
  stall in about 2.5° steps (about 8 angles).
- **Source:** our choice (owner).

### What we watch: CL, CD (pressure and friction parts), CM, neutral point, pressure at chosen sections, y+
- **In practice:** a study passes only if **every one** of these is inside its budget **at every
  angle**. Passing on lift but failing on drag is a fail.
- **Why:** forces can look right while the pressure on the wing is wrong; y+ tells us whether the
  first cell next to the wall is small enough.
- **Source:** our choice.

### Mesh family: at least 3 meshes, each 1.3 times finer in every direction
- **In practice:** to measure mesh error we build the same mesh at three sizes. Each step is
  1.3 times finer in all three directions, so it has about 1.3³ = 2.2 times more cells.
- **Why:** with two meshes you only see that the answer moved. With three you can see how fast it
  settles and estimate where it would end. Steps smaller than 1.3 are too small to measure reliably.
- **Since Stage 2 (2 Nov 2026):** the surface mesher builds levels C, M, F and FF this way: every
  spacing ÷ 1.3 per level (checked within 3 %). Only the base counts step by 1.25, 1.4 and 1.29 (see 1d).
- **Decided (owner, 6 Nov):**
  - four levels VC, C, M, F: VC on the desktop; C, M and F on the university HPC (C, about 2.3 M cells,
    is above the desktop limit of about 1.2 M);
  - hard minimums at VC: y+ ≤ 1, growth ≤ 1.25, base ≥ 8 cells, no kinks, tip gap;
  - accuracy targets at M, as DPW defines its medium grid: nose 10°, trailing edge 0.1 % c, station gap,
    largest cell 2 % c;
  - transition targets at F: about 20 cells per bubble;
  - every spacing ÷ 1.3 per level, so about 2.2× cells per level; wall layers about 1.30× per level;
  - lighter rules: band cell 0.5 % c at F where local Re ≥ 4 × 10⁵ (the bubble-length table stops at
    0.10 c from local Re 4 × 10⁵ up); tip gap 2 × s0; station gap 0.25 × local chord at M.
- **Estimated cost (Stage 2; surface × wall layers; 20 reference wings × 4 Re):** fine level about
  10–11 M cells median on the wing blocks: 10.9 M with the band change; 15.2 M with the planned rules.
  The C-H wake lines may add about +45 % (30–60 %, rough). Desktop limit about 1.2 M cells. See the
  weak points.
- **Source:** Celik et al. 2008; DPW-4 gridding guidelines (the medium grid).

### Error estimate: GCI with a safety factor of 1.25
- **In practice:** from the three meshes we compute the Grid Convergence Index, an error bar on
  each number. It is multiplied by 1.25 to stay on the safe side. If the three results scatter, we
  use the least-squares version, which fits a line through more points.
- **Source:** Celik et al. 2008; Roache 1994; Eça & Hoekstra 2014.

### Results that go up and down with refinement: no error bar; find out why
- **In practice:** if the answer goes up, then down, as the mesh gets finer, the meshes are not yet
  fine enough for the method to hold. We do not quote an error bar; we look for the cause.
- **Source:** Celik et al. 2008.

### Stopping rule: when is one solver run finished?
- **In practice:** a run counts as finished only when **all** of these hold:
  1. the residual has fallen to 10⁻⁶ of its value at the start (in ADflow: `L2Convergence = 1e-6`,
     measured against the free-stream residual);
  2. the forces have stopped moving over the last iterations: CL changes less than 0.05 %, CD less
     than 0.1 %, CM less than 0.0001;
  3. every equation, including the turbulence equation, has fallen at least 1,000 times
     (3 orders of magnitude).
  - If the residual stalls before 10⁻⁶ but has fallen 100,000 times (5 orders) and the forces have
    stopped moving, the run is still accepted.
  - Anything else is marked "needs review".
  - A run is stopped after 30,000 iterations or 6 hours.
  - "The solver finished without an error" is never taken as proof.
- **Why:**
  - A low residual alone does not prove the forces stopped changing.
  - The turbulence equation can stall while the others keep falling.
  - **Note on Fluent:** Fluent's "10⁻⁶" is a *scaled* residual. Its default target is 10⁻³ for
    most equations and 10⁻⁶ only for energy. ADflow's 10⁻⁶ is a fall from the free-stream value,
    which is stricter.
- **It meets the budget:**
  - The iterations may use 10 % × 3 counts = 0.3 counts.
  - Earlier AERIS runs, continued past 10⁻⁶, moved CD by at most 0.12 counts and CL by at most
    0.00005.
  - 0.12 < 0.3, so 10⁻⁶ is enough. We check this once more when the mesh family is frozen.
- **Source:** Celik et al. 2008, Appendix A; ADflow options documentation.

### One change per run
- **In practice:** between two runs we compare, only one setting changes. In a mesh study the wing
  never changes.
- **Why:** if two things change, we cannot say which one moved the result.
- **Source:** our choice.

### Turbulence model: transition must be captured, with ADflow and SU2 (owner, 4 Nov 2026)
- **In practice:** the results must capture the change from laminar to turbulent flow (transition).
  This replaces "SA for now; the final choice in a later stage, at the latest by gate G0"
  (decision 54). Our ADflow build has SA only (SST aborted) and no transition model, so transition
  comes from SU2 (SST + LM γ-Reθ).
- **The mesh stays transition-ready:** first cell y+ ≤ 1 at each case's speed; at least 30 cells
  across the boundary layer at every station; the transition band as built in Stage 2: upper surface
  0–85 % of chord (from the leading edge on every wing, Stage 2 decision 58; Stage 1 asked 10–85 %,
  from the leading edge on swept panels), lower surface 60–100 %; band cell = bubble length ÷ 20 at
  level C (Stage 2 decision 56). Every drag number carries a model band next to the mesh error.
- **Decided (owner, 6 Nov):**
  - about 20 cells per bubble at level F, instead of at level C as built (Ansys CFX transition-model grid
    guidance: 20 nodes per bubble, wall-normal growth about 1.1, y+ about 1, 75–100 nodes from the leading
    to the trailing edge);
  - wall-normal growth 1.25 at VC is 1.107 at F, just above the 1.1 a transition model asks for (1.23 at VC would give exactly 1.1) (Stage 2
    decision 57);
  - band cell 0.5 % c at F where local Re ≥ 4 × 10⁵: the bubble-length table stops at 0.10 c from local
    Re 4 × 10⁵ up (see Mesh family).
- **Proposals, pending:**
  - solver split: ADflow SA for all mesh studies and the fully turbulent data; SU2 SST + LM on about
    20 % of the wings first;
  - (the lower transition band is decided: from the leading edge, Stage 2 decision 74, owner 7 Nov).
- **Why:** Stage 1 (2-D XFOIL strips, smooth wing in calm air) found a long laminar run and laminar
  bubbles on most of these wings; fully turbulent SA overpredicts the profile drag by a median
  +62 % (+69 % in level flight). What a mesh must resolve depends on the model, so a mesh tuned only
  for SA would have to be rebuilt for a transition model.
- **Note on SA:** "SA" means fully turbulent only with the standard inflow eddy viscosity
  (ν̃/ν about 3). With a low inflow value SA shows an uncontrolled "apparent transition"
  (Crivellini & D'Alessandro 2014). The value must be fixed and recorded before the first ADflow solve.
- **Source:** owner decision (4 Nov 2026); Stage 1 flow study (project doc "Stage_1 Executive
  summary"); Ansys CFX Modeling Guide (transition-model grid requirements); Spalart & Rumsey 2007
  (inflow value); Crivellini et al. 2014.

### Note: first SU2 smoke test (4 Nov 2026), not a result
SU2 8.6.0 ran SA and LM on one Stage 2 ring mesh: a section extruded between two symmetry planes,
97,920 cells, Re 3 × 10⁵, Mach 0.15, 4°. After about 370 iterations, not converged: SA CL 0.860,
CD 0.0184; LM CL 0.908, CD 0.0137. It shows the mesh path works. No wing has been run.

---

## D4 — Working rules

| rule | in practice | why | source |
|---|---|---|---|
| Mesh name `mesh_<level>_<wing_hash8>_re<Re>` | every mesh name says which size, which exact wing (first 8 characters of the wing's fingerprint) and which Re (on the mean chord); the surface depends on Re, because the tip gap and the band cells do: one surface per wing and Re level (Stage 2 decision 59); not "family", which already means the wing families (tailless, conventional) | one name must mean one mesh; in AERIS one name once meant two different meshes | — |
| Every run ends as accepted, rejected or needs review | no "almost converged" or "probably fine" | results can be counted | — |
| Failures stay in every count | a wing that failed is never removed from the list | otherwise success rates look better than they are | — |
| Pass/fail limits are written before the results | we write "a study passes if …" first, then run it | stops us adjusting the test to fit the answer | Nosek et al. 2018 |
| Hold-out opened once, at the end | see D2 | see D2 | Dwork et al. 2015 |
| Trial results kept apart from final results | numbers from early trial meshes guide the work but never go in the paper | only the frozen setup is evidence | — |
| Every figure and table is made by a script from stored data | no hand-made plots | anyone can rebuild them | — |

---

## Weak points still open

- **Drag ranking with SA.** The 2-count increment target holds for the mesh, not for the model: SA's
  own error on differences is about 4 counts. Ranking wings or airfoils by drag needs transition-model
  results (SU2 SST + LM), at least on a calibration subset.
- **Transition rests on SU2 alone.** Decided 4 Nov: transition must be captured. Our ADflow build has SA
  only (SST aborted), so only SU2 (SST + LM) can do it. So far SU2 has run one smoke test on one ring
  mesh, not converged. Its cost on a full wing is unmeasured, and ADflow and SU2 SA have not yet been
  compared on the same mesh.
- **Mesh size.** Estimated in Stage 2, the fine level has 15.2 M cells (median) with the planned rules,
  against the proposed 9–11 M. The band change (decided 6 Nov) gives 10.9 M, but then the short high-Re
  root bubbles (about 1.5 % c) get only about 3 nodes: fine for SA, not for LM. The C-H wake lines may
  add about +45 % on the wing blocks, so F may land nearer 15 M than 11 M. The desktop takes about 1.2 M
  cells: with F at 10.9 M, VC is about 1.0 M (median) and C about 2.3 M, so C does not fit on the desktop.
- **SU2 has no overset.** It also refuses structured CGNS (structured meshes converted to unstructured
  hexes do run). So the overset wake box and vortex tube cannot serve both solvers. The C-H mesh
  (decided 6 Nov) has its own costs: the tip vortex must be held by the outboard blocks without a tube,
  the open-line march is new work, and the wake lines add cells.
- **Nose shape (decision 64): fixed on 7 Nov.** A first check (Stage 2) found the upper and lower nose
  radius of cambered sections 3–13× apart. On 6 Nov a second check called this mostly the measuring
  method; that was wrong, because it compared built and raw only at the raw points, where they agree by
  construction. A third check with one curvature method along the surface found the real defect between
  the points (NACA 4415: a 0.18 % c nose cell turned 9.47° built against 4.31° true). Fixed in Stage 1;
  every geometry hash changed and the sets were rebuilt. The pyGeo `build --all` is still owed.
- **The new scope needs data.** −5° to post-stall and Mach toward 0.5 lie outside the Stage 1 data (root
  angles 0–10°, Mach ≤ 0.2). The mesh rules were set from those ranges, so they must be checked again
  for the new ones.
- **Numerical settings.** Earlier tests moved drag 12–21 counts against a 0.45-count share. Expect this
  to drive the solver settings.
- **Iteration share.** 0.30 counts is looser than Celik's 1/10-of-mesh-error rule (0.195). The measured
  0.12 meets both; re-check once the mesh family is frozen.
- **Still open from Stage 0:** grid share 65 %, pitching moment 0.002, the iteration share, a D5 (open
  decisions 1, 3, 4, 6).
- **Split of the mesh share.** A plan, not a measurement. Change it only by a written decision, before
  new results.

Sources added on 6 Nov 2026: AIAA DPW-4 gridding guidelines
(https://aiaa-dpw.larc.nasa.gov/Workshop4/gridding_guidelines_4.html); Ansys CFX Modeling Guide,
transition-model grid requirements
(https://ansyshelp.ansys.com/public/views/secured/corp/v251/en/cfx_mod/i1324236.html); SU2 v8.6.0 source
code (https://github.com/su2code/SU2); Anderson, Fundamentals of Aerodynamics, 5th ed., 2011.
