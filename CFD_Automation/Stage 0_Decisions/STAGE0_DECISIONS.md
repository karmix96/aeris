# Stage 0 decisions

These are the starting values the whole project is judged against. For each one: **the value**,
**what it means in practice**, **why we chose it**, and **the source**. The same values, in a form a
program can read, are in `stage0_values.yaml`.

## A few words first

- **CD, CL, CM**: drag, lift and pitching-moment coefficients. They are the wing's forces divided by
  its size and the flow speed, so wings of different sizes can be compared.
- **Drag count**: 0.0001 of CD. A typical wing has CD around 0.0100–0.0300, i.e. 100–300 counts.
- **Mesh**: the grid of small cells around the wing that the solver computes on. A finer mesh is
  more accurate and slower.
- **Error**: how far our computed number is from the true one.
- **Residual**: how far the solver still is from a finished answer on one mesh. It falls as the
  solver iterates.

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
| 1a | Mesh: along the chord | points around the airfoil | 35 % | 22.75 % | 0.68 counts | edge cells ≈ 0.1 % of local chord (DPW) | carried about 88 % of the drag error |
| 1b | Mesh: along the span | sections from root to tip | 15 % | 9.75 % | 0.29 counts | root and tip spacing ≈ 0.1 % of semi-span (DPW) | — |
| 1c | Mesh: away from the wall | thin layers through the boundary layer | 20 % | 13 % | 0.39 counts | first cell y+ ≈ 1; each layer ≤ 1.25 × the previous (DPW) | — |
| 1d | Mesh: edges and blunt trailing edge | cells at nose, trailing edge and across the base | 15 % | 9.75 % | 0.29 counts | 0.1 % of chord at edges (DPW); 8 cells across the base (our choice) | base was the slowest part to settle |
| 1e | Mesh: wake | cells behind the wing and around the tip vortex | 15 % | 9.75 % | 0.29 counts | set in the mesh stage (our choice) | refining the near wake moved drag 23 counts |
| **1** | **Mesh, all directions** | cells too big | **100 %** | **65 %** | **1.95 counts** | error bar from 3 meshes (Celik 2008) | — |
| 2 | Iterations | solver stopped too early | — | 10 % | 0.30 counts | stopping rule in D3 (Celik 2008: < 1/10 of mesh error = 0.195) | measured 0.12 counts at 10⁻⁶: OK |
| 3 | Outer boundary | domain edge too close to the wing | — | 10 % | 0.30 counts | ≈ 100 reference chords (DPW) | 40 → 60 chords moved drag 0.6–0.7 counts: 40 is too close |
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
  local chord long.
- **Why it gets the largest part:** it is the most expensive direction to refine, and in earlier
  AERIS tests it carried most of the drag error (about 88 %).
- **Source:** Drag Prediction Workshop gridding guidelines (Levy et al. 2013).

**1b. Along the span: 0.29 counts.**
- **What it is:** the number of sections from the root to the tip.
- **What goes wrong if there are too few:** the lift is spread wrongly along the span, mostly near
  the tip, which changes the induced drag.
- **Starting mesh from the source:** spacing at the root and at the tip about 0.1 % of the semi-span.
- **Source:** DPW gridding guidelines (Levy et al. 2013).

**1c. Away from the wall: 0.39 counts.**
- **What it is:** the layers of thin cells from the wing surface out through the boundary layer
  (the thin slow layer of air on the surface).
- **What goes wrong if they are too coarse:** the friction drag is wrong.
- **Starting mesh from the source:**
  - first cell at y+ ≈ 1 (small enough to sit inside the very thin layer next to the wall);
  - each layer at most 1.25 times thicker than the one before.
- **Source:** DPW gridding guidelines (Levy et al. 2013).

**1d. Edges and blunt trailing edge: 0.29 counts.**
- **What it is:** the cells at the nose, at the trailing edge, and across the flat back face of the
  thick trailing edge (the "base").
- **What goes wrong:** air leaves the base with low pressure, which pulls the wing back (extra drag).
  Too few cells across the base get that pressure wrong.
- **Starting mesh:** 0.1 % of chord at the edges (DPW); 8 cells across the base.
- **Why a separate part:** in earlier AERIS tests the base was the slowest part to settle with
  refinement.
- **Source:** DPW guidelines for the edges. The base cell count is from earlier AERIS tests (our choice).

**1e. Wake: 0.29 counts.**
- **What it is:** the cells behind the wing and around the tip vortex (the swirl that leaves the
  wing tip).
- **What goes wrong if they are too coarse:** the wake and the vortex smear out, which changes the
  pressure at the trailing edge and the induced drag.
- **Why it matters:** in earlier AERIS tests, refining only the near wake moved drag by 23 counts.
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
- **How we measure it:** move the outer edge further out (for example 40, 80, 160 chords), keeping
  the mesh near the wing the same, and see how much the drag changes.
- **Starting value from the source:** about 100 reference chords.
- **Check:** in earlier AERIS tests, going from 40 to 60 chords moved drag by 0.6–0.7 counts. That is
  more than 0.30, so 40 chords is too close; expect about 80–100.
- **Source:** DPW gridding guidelines (Levy et al. 2013).

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

The wing generator is new, so the wings are defined by **rules**, not by name.

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

### Training set: 100 wings per type
- **In practice:** 100 wings spread evenly over all variables. The mesher must build all of them;
  they show where it works.
- **Why Latin hypercube:** each variable's range is cut into 100 slices and each slice is used once,
  so no part of any range is left empty.
- **Source:** McKay, Beckman & Conover 1979.

### Corner sets: 42 extreme wings (for 17 variables)
- **In practice:**
  - Part 1, 34 wings: each variable pushed to its lowest and then its highest value, the others
    in the middle. This shows which single variable breaks the mesher.
  - Part 2, 8 wings: every pair of variables appears at all four combinations (low-low, low-high,
    high-low, high-high). This shows when two extremes together break it.
  - A corner wing that fails stays in the list. It marks the edge of what the workflow can do.
- **Arithmetic for part 2:** the smallest N with C(N−1, ⌈N/2⌉) ≥ 17. N = 7 → C(6, 4) = 15, too few.
  N = 8 → C(7, 4) = 35, enough. So 8 wings, the proven minimum.
- **Source:** Katona 1973; Kleitman & Spencer 1973.

### Hold-out set: 10 wings per type, opened once at the end
- **In practice:** 10 wings drawn now and locked away. Nobody builds or looks at them until every
  rule is final. Then they are run once, and the result is the honest test of "it works on wings it
  has never seen".
- **Why:** if we look at the test wings while tuning, we tune to them without meaning to, and the
  test stops being a test.
- **Source:** Dwork et al. 2015 (Science), 2017 (CACM).

### Robustness: 0 failures in at least 150 wings
- **In practice:** if the workflow succeeds on all 150 wings (training + corner + hold-out), we may
  claim that at least about 98 % of all wings in the design space will work, with 95 % confidence.
- **Arithmetic:** the most the failure rate can be is 1 − 0.05^(1/150) = 1 − 0.98022 = 1.98 %.
  Quick rule: 3 ÷ 150 = 2.0 %.
- **Source:** Hanley & Lippman-Hand 1983 ("rule of three").

---

## D3 — Flow conditions and how we measure

### Speed: Mach ≤ 0.3
- **In practice:** up to about 100 m/s (360 km/h) at sea level. Air behaves as nearly
  incompressible. Faster, transonic flight is a later stage.
- **Why:** Class I and II UAVs fly well below this.
- **Source:** our choice.

### Reynolds numbers: 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶ (on the mean chord; top was 5 × 10⁶ until 29 Oct 2026)
- **In practice:** the Reynolds number says how "big and fast" a wing is for the air:
  Re = air density × speed × chord ÷ air viscosity. A small, slow wing has low Re; a large, fast
  wing has high Re. Example: a 0.2 m chord at 25 m/s and 1,500 m gives about 3 × 10⁵.
  Every mesh study is run at these three levels, because the cells next to the wall must be smaller
  at higher Re.
- **Why these three:** low, middle and high end of small Class I and Class II wings (check below).
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
(Raven, 1.4 m span) sit below 3 × 10⁵. 5 × 10⁶ is a safe upper end.

**Update 29 Oct 2026: top level lowered to 2 × 10⁶.** The check above used chords guessed per
aircraft. A sourced table of real Class I–II wings with a published wing area
(`geometry/configs/real_uavs.yaml`) gives Re 1.2 × 10⁵ to 2.1 × 10⁶ (mean chord = area / span;
cruise at 3,048 m to top speed at sea level). The highest is the AAI Pioneer (Class II, 5.15 m span,
mean chord 0.549 m, 56.7 m/s). No wing of our families reaches 5 × 10⁶, so the levels are now
**3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶**. Class II wings with a published area (Götten et al. 2021; Essari
2015 thesis with Jane's-style data for Hermes 450, Ranger, Seeker, Shadow 600) have mean chords of
0.55–0.66 m and reach Re 2.1–2.7 × 10⁶ at top speed and sea level; the highest is the RUAG Ranger
(2.74 × 10⁶), rounded up to 3 × 10⁶.

### Angles of attack: 0°, 4°, 8°; plus 12° for the nose and the wake
- **In practice:** every study runs at 0°, 4° and 8°. Studies of the leading edge and the wake
  also run at 12°.
- **Why:** cruise, climb and high lift. At high angle the flow turns sharply round the nose, which
  needs finer cells there, so the nose rules are tested at 12°.
- **Source:** our choice.

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
- **Source:** Celik et al. 2008.

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

### Turbulence model: Spalart–Allmaras, no transition model
- **In practice:** the solver treats the boundary layer as turbulent from the leading edge. Real
  wings at low Re keep a laminar stretch first, which lowers friction drag. So at low Re our drag is
  reported with a model error band next to the mesh error.
- **Why:** at low Re, where the flow turns turbulent decides much of the drag, and this model does
  not predict it.
- **Source:** Crivellini et al. 2014.

---

## D4 — Working rules

| rule | in practice | why | source |
|---|---|---|---|
| Mesh name `<family>_<level>_<wing_hash8>` | every mesh name says which family, which size and which exact wing (first 8 characters of the wing's fingerprint) | one name must mean one mesh; in AERIS one name once meant two different meshes | — |
| Every run ends as accepted, rejected or needs review | no "almost converged" or "probably fine" | results can be counted | — |
| Failures stay in every count | a wing that failed is never removed from the list | otherwise success rates look better than they are | — |
| Pass/fail limits are written before the results | we write "a study passes if …" first, then run it | stops us adjusting the test to fit the answer | Nosek et al. 2018 |
| Hold-out opened once, at the end | see D2 | see D2 | Dwork et al. 2015 |
| Trial results kept apart from final results | numbers from early trial meshes guide the work but never go in the paper | only the frozen setup is evidence | — |
| Every figure and table is made by a script from stored data | no hand-made plots | anyone can rebuild them | — |
