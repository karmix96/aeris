# ADR-0015 — the generator produces exact sections at arbitrary spanwise stations

Date: 2026-08-16
Status: Proposed — awaiting the geometry-set re-identification in §6

Supersedes the "mesh-only" reading of the fidelity gate in ADR-0011 §6.1.
First change this study makes to `src/aeris`.

---

## 1. The problem

ADR-0011 §6.1 gates geometry fidelity at **0.01% of local chord**. Every strategy
fails it, on every geometry, for the same reason and only that reason:

> `fidelity unverified for spanwise-refined blocks`

Every strategy invents its spanwise mesh columns by blending linearly between the
generator's realised sections. Those columns are not on the aircraft.

Measured on `lhs100_seed42_000`: the wing departs from a straight line between
stations by a **median 0.447% of chord, and up to 7.25% at the inboard/outboard
spline junction — 45x to 700x the gate.**

**A measurement-only fix is not available**, and this was checked before proposing a
code change. A measurement fix would require the columns to be on the loft and merely
unproven. They are off it by three orders of magnitude more than the gate allows. A
measurement that passed them would be an instrument bug of exactly the kind
COMMON_BRIEF §5 exists to prevent.

**Refining the station count does not rescue it.** Measured 17 → 35 → 71 → 143
stations: 7.25% → 3.08% → 1.42% → 0.68%, a ratio of ~2 per doubling. That is
**first-order** convergence — linear interpolation across a slope discontinuity — not
the O(h²) a smooth surface would give. Reaching 0.01% that way needs of order
**12,000 stations**.

So interpolation has to go, not shrink.

## 2. A second defect, found on the way, which is not about meshing at all

`sections.py::_cumulative_z` integrates `tan(dihedral)` by the **trapezoid rule** along
whatever station array it is handed:

    z[i] = z[i-1] + 0.5 * (tan(d[i-1]) + tan(d[i])) * (y[i] - y[i-1])

Dihedral is piecewise linear in `y`, so `tan(dihedral)` is not, and the trapezoid
result therefore **depends on the discretisation**. Change the station count and
`z(y)` moves.

This matters beyond the mesh study. It means the generator does not currently define
a single aircraft: two runs of the same configuration asking for different station
counts get **different geometries**, and the difference is not a resolution artefact
converging to a truth — it is the answer changing. Any station-count change anywhere
in AERIS silently moves the loft.

It also makes the phrase "the exact section at arbitrary `y`" ill-defined, so it has
to be fixed before §1 can be fixed.

## 3. Decision

### 3.1 Replace the integration rule with its closed form

Over a segment where dihedral runs linearly from `d0` to `d1` across `[y0, y1]`:

    m = (d1 - d0) / (y1 - y0)                     [rad/m]
    m == 0 :  integral = tan(d0) * (y1 - y0)
    m != 0 :  integral = (ln|cos d0| - ln|cos d1|) / m

Exact, and **station-independent**. Implemented and verified as
`shared/exact_sections.py::exact_z_at`.

### 3.2 Add a section-at-arbitrary-`y` entry point

`planform_curves()` reconstructs `planform.generate_spline_linear` in closed form —
clamped `CubicSpline` over the control points blended toward the straight-line
baseline by `curvature_strength` inboard, purely linear outboard — and **reproduces
the generator to 0.000e+00**. With §3.1 supplying `z(y)`, a section at any `y` is
computable.

The generator gains `sections_at(y)`. The existing call path is unchanged except for
the integration rule, so this is **additive**.

### 3.3 The mesher asks for the stations it wants

`shared/ingestion.py` requests sections at exactly the spanwise stations each strategy
realises. Every mesh column then **is** a real section and the deviation is
**identically zero by construction, on every geometry** — not small, not converging,
zero. That is what the user's requirement asked for: *"there should be zero deviation
for all geom the mesher will encounter, not only this."*

## 4. What this does NOT do

- It does **not** relax the 0.01% gate. It makes the gate satisfiable.
- It does **not** change any strategy's blocking, tip closure or spanwise law. What
  changes is where the section data comes from, not what the mesher does with it.
- It does **not** change the ranking criteria. ADR-0011 §6 stays frozen.

## 5. Consequences, stated plainly because they are expensive

- **It changes what `configs/geometry/bwb.yaml` means**, and therefore the sha256 that
  identifies `epse_calibration_lhs10_seed7`, `lhs100_seed42` and
  `round_c_lhs10_seed42`.
- **Every surface and volume result in this study is measured on the old sets** and
  must be re-run. That includes S1's 10/10 marches, S4's complete result, and S0's
  pending re-run.
- **The hold-out must be re-identified before it is used.** Running it on the old sets
  spends the one-shot budget on geometry the final report will not be using — so the
  hold-out waits for this, not the other way round.
- It modifies `src/aeris`, which this study has not done before. The 182 tests in
  `tests/mesh` and `tests/cfd` must still pass, and any test that pins a `z` value
  computed by the trapezoid rule will legitimately change; each such change is to be
  justified individually, not blanket-updated.

## 6. Verification required before this ADR moves to Accepted

1. `planform_curves()` reproduces the shipped planform to 0.000e+00 — **done**.
2. `exact_z_at()` agrees with the trapezoid result **in the limit** of many stations,
   confirming it is the same integral and not a different one.
3. Fidelity measures identically zero on all realised columns for at least one
   strategy on all ten development geometries.
4. `tests/mesh` + `tests/cfd` pass, with any changed expectation justified.
5. The three geometry sets are re-identified and their new sha256 recorded in `status`.

## 7. Evidence

- `04_strategy_studies/shared/exact_sections.py` — both closed forms, with the
  convergence measurements in its docstring
- `AERIS_MESH_STUDY/status` §5J — the determination that this cannot be fixed by
  measurement
- `src/aeris/generators/bwb_segmented_v1/sections.py:124` and its single call site
  at `:246`
- ADR-0011 §6.1 (the gate); COMMON_BRIEF §5 (verify the verifier)
