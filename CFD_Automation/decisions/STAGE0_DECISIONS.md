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

### How the total error is shared out
The total allowed error is cut into pieces, one per source of error. Each study then knows when to
stop: **a study stops when its own piece is used up, not before and not long after.**

| piece | share | with a 3-count drag budget | what it means in practice |
|---|---|---|---|
| Mesh (all directions) | 65 % of the total | 1.95 counts | error from cells that are too big |
| · along the chord | 35 % of the mesh piece | 0.68 counts | points around the airfoil |
| · along the span | 15 % | 0.29 counts | sections from root to tip |
| · away from the wall | 20 % | 0.39 counts | layers in the boundary layer |
| · edges and blunt trailing edge | 15 % | 0.29 counts | cells at the nose, the trailing edge and its base |
| · wake | 15 % | 0.29 counts | cells behind the wing and around the tip vortex |
| Iterations | 10 % of the total | 0.30 counts | stopping the solver too early (see the stopping rule in D3) |
| Outer boundary | 10 % | 0.30 counts | the domain edge being too close to the wing |
| Numerical settings | 15 % | 0.45 counts | solver settings such as artificial dissipation |
| **Total** | 100 % | **3.00 counts** | |

- **Why this split:** it is a plan, not a measurement. The chord gets the largest piece because
  it is the most expensive direction to refine. The split is revised once the first error map shows
  where the error really sits.
- **Sources:** the split is our choice. For iterations, Celik et al. 2008 (Appendix A) ask for an
  iterative error at least 10 times smaller than the mesh error; Eça & Hoekstra 2006 ask for 100 to
  1,000 times smaller.

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

### Reynolds numbers: 3 × 10⁵, 1.5 × 10⁶, 5 × 10⁶ (on the mean chord)
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
