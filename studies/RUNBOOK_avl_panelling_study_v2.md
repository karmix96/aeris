# RUNBOOK — AVL panelling study (v2)

**Audience: Codex.** This is an execution specification, not a discussion document.
Follow it exactly. Where it says STOP, stop and wait for Mike.

**Supersedes** `studies/RUNBOOK_avl_panelling_for_codex.md` (v1, 2026-07-28).
Do not execute v1. Where the two differ, this document wins. Companion document
`studies/PLAN_avl_panelling_study.md` explains *why*; this one says *what to run*.

Date issued: 2026-07-28 · Total: **1,165 AVL runs** · ~8.2 h serial, ~1.4 h at
8-way parallel. Cache overlap between stages means the number of genuinely new
solves is lower; report actual solves versus cache hits at every stage end.

---

## 0. Non-negotiable rules

1. **STOP after every stage.** Write the results, produce the plots, print the
   summary, and stop. Mike reviews the plots and discusses them before you continue.
   Do not chain stages.
2. **Never change a setting after seeing a result.** Everything that could bias the
   outcome is fixed in Stage 0 and committed before the first solver run. This
   includes every aggregation rule, every gate threshold and every normalisation
   constant in this document.
3. **Never invent a substitute when something fails.** If a run fails, record it and
   continue; if a *stage gate* fails, stop and report. Do not "work around" it.
4. **Every AVL result must be checked for `status == "SUCCESS"` before any
   arithmetic touches it.** AVL does not report exceeding its internal array limits
   as an error — it returns a result with every coefficient `None`, which looks
   exactly like a physics failure. This has already destroyed one study in this
   project.
5. **Do not modify anything under `src/aeris/`.** This study observes production
   code, it does not change it. If you believe production code is wrong, write it in
   the stage report and stop.
6. **Nothing goes in `/tmp` or a scratch directory.** All scripts and outputs live
   under the paths given in §2.
7. **Plots must be simple.** See §8. One message per plot. No multi-panel dashboards.
8. **Do not delete or overwrite raw results.** Runs are cached (§4); re-running a
   stage must reuse completed cells, not redo them. The one exception is Stage 7,
   which bypasses the cache deliberately and writes to a separate tree.
9. **Never call any computed value "true", "exact" or "converged"** in code, output,
   plot or summary. The vocabulary this study is allowed to use is defined in §4.4.

---

## 1. What this study decides

Which AVL panelling setting the design sweep uses. The answer is:

> The cheapest chordwise / spanwise / spacing combination that keeps numerical
> uncertainty acceptable, preserves the ranking of the best designs, **and
> preserves the trim and stability classification of every design.**

Not "the most accurate". Not "the one with the smallest error". The cheapest that
passes the gates in §7.

The third clause is new in v2 and is the clause that matters most. A mesh that
preserves an aerodynamic coefficient but moves a design across the trimmable /
untrimmable boundary has changed the study's conclusions, not merely its numbers.

---

## 2. Paths

```
standalone/panelling_study/            all scripts you write
  common.py                            shared runner (§4) — write this first
  stage0_lock.py
  stage1_lattice.py
  stage2_chordwise.py
  stage3_spanwise.py
  stage4_spacing.py
  stage5_shortlist.py
  stage6_ranking.py
  stage6b_zero_deflection.py
  stage7_timing.py
  plots.py                             all plotting

data/panelling_study/                  raw AVL output (gitignored, large)
  cache/<hash>/                        one directory per unique run
  cache/timing/<setting>/<repeat>/     Stage 7 only, never reused

configs/aero/panelling_study/          TRACKED — results that must survive
  stage0_locked_config.json
  stage<N>_results.csv
  stage<N>_summary.txt
  stage5_shortlist.json
  raw_comparator.tar.gz                written after Stage 6
  plots/stage<N>_*.png
```

`configs/` is tracked and survives `data/` being wiped. Every number Mike needs to
see goes there. `data/` is scratch.

---

## 3. Fixed conditions (identical in every stage unless a stage says otherwise)

```
geometry config           configs/geometry/bwb.yaml
n_sections                25
span_margin               0.0
section_placement         as the config ships — DO NOT VARY IT
snap_sections_to_control  true
velocity                  28.0 m/s
altitude                  0.0 m
beta                      0.0 deg
elevon symmetric          +4.0 deg      ← see §3.1, must be confirmed in Stage 0
elevon differential       +4.0 deg      ← see §3.1, must be confirmed in Stage 0
viscous                   True
avl timeout               900 s, with one retry, then record failure and continue
```

**Section placement is frozen for this entire study.** It is a separate question and
varying it here would confound everything. Whatever `configs/geometry/bwb.yaml`
currently contains is what every run uses.

### 3.1 The control state — resolve this in Stage 0 before anything runs

Every run above is at a **differentially deflected** state. That is deliberate but
it must be justified, not inherited.

**Do, in Stage 0:** read `src/aeris/commands/workflow.py` and record in the locked
config the exact control state at which the production dataset is evaluated.

- If production evaluates at `(sym +4, diff +4)`: keep the table above. Validating
  panelling at the production state is the correct choice. Record the following
  justification verbatim in the Stage 0 summary:

  > Antisymmetric loading has a higher spanwise wavenumber than symmetric loading
  > and therefore requires more spanwise resolution to converge. Establishing
  > panelling adequacy at a differentially deflected state is conservative with
  > respect to spanwise panel count, not permissive. Stage 6b demonstrates this
  > rather than asserting it.

- If production evaluates at any other state: change the table above to match
  production, record the change, and STOP for Mike before Stage 1.

**Known consequence, to be stated in the Stage 6 summary.** `l_over_d` at a
differentially deflected state includes the induced-drag penalty of the
antisymmetric loading, which depends on elevon band geometry. The `narrow_elevon`
and `wide_elevon` extreme cases are therefore affected structurally, not only
numerically. This is one reason the extreme geometries are reported separately and
never pooled into the normal statistics.

### 3.2 Angles

| use | angles |
|---|---|
| convergence stages (2, 3) | −2, 0, +2, +4, +8 |
| lattice, ranking, deflection stages (1, 6, 6b) | −2, 0, +4 |
| spacing stage (4) | +4 only |

−2, 0, +4 are the production workflow's own default sweep
(`src/aeris/commands/workflow.py:582`). We validate at the conditions the tool is
actually used at. The two extra angles in the convergence stages exist to confirm
that mesh sensitivity really is weakly angle-dependent, as theory predicts (AVL's
influence matrix does not depend on angle of attack; only the right-hand side does).

**Stage 0 must resolve the +8° inconsistency.** +8° appears in Stages 2 and 3 and
not in Stage 6. Confirm from `workflow.py` whether production sweeps +8°. If it
does, add +8° to Stage 6 (+180 runs, ~1.4 h) and record the revised total. If it
does not, remove +8° from Stages 2 and 3 for consistency. Decide in Stage 0, not
after seeing Stage 2.

### 3.3 AVL's hard limits

```
strips   = 48 × spanwise_panels_per_section      must be ≤ 500
vortices = strips × nchordwise                   must be ≤ 6000
```

Consequences worth knowing before you plan anything:

| spanwise | strips | max legal chordwise |
|---|---|---|
| 1 | 48 | 125 |
| 2 | 96 | 62 |
| 4 | 192 | 31 |
| 6 | 288 | 20 |
| 8 | 384 | 15 |
| 10 | 480 | 12 |

Every combination in this runbook has been checked legal. **Assert both limits
before every run anyway**, and abort that run with a clear message rather than
letting AVL fail silently.

---

## 4. `common.py` — write this before anything else

Every stage calls this. Identical code everywhere means the stages are comparable.

### 4.1 Required functions

```python
def load_base_config() -> tuple[str, Any]:
    """resolve_generator_and_config(load_yaml_config('configs/geometry/bwb.yaml'))"""

def make_sample(kind: str, seed: int) -> Any:
    """kind='normal' -> the production sampler, per §5 step 1.
       kind='extreme' -> base sample with the documented override applied (§5)."""

def run_case(sample, *, nchordwise, spanwise, cspace, alpha_deg,
             control_input_deg, diff_input_deg,
             tag: str, bypass_cache: bool = False) -> dict:
    """One AVL solve. Returns a flat dict of scalars (§4.3).

    MUST:
      - compute strips/vortices and assert both limits BEFORE writing the .avl
      - cache on the full provenance hash of §4.2 and return the cached result
        if native_avl_result.json already exists, UNLESS bypass_cache is True
      - on a cache hit, re-read provenance.json and assert every field matches
        the current request before returning
      - assert result.status == 'SUCCESS'; on failure retry once, then return
        a dict with ok=False and the reason, never raise
      - record wall-clock seconds for the AVL call only, and separately the
        wall-clock seconds for section build + AVL call
      - assert the mesh AVL REPORTS (n_strips, n_vortices) equals what was asked
    """
```

Build the sections once per sample and reuse across panelling settings —
`build_pygeo_sections_from_config` costs ~1.4 s and does not depend on panelling.

```python
from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
    build_pygeo_sections_from_config, run_pygeo_native_avl_case)
from aeris.aero.models import FlightCondition

ex, semi, meta = build_pygeo_sections_from_config(
    "configs/geometry/bwb.yaml", sample=sample)

res = run_pygeo_native_avl_case(
    flight_condition=FlightCondition(alpha_deg=a, beta_deg=0.0,
                                     velocity_mps=28.0, altitude_m=0.0),
    output_dir=cache_dir, extracted_sections=ex, semispan_m=semi,
    control=meta["control"], control_input_deg=ctl, diff_input_deg=dif,
    viscous=True, nchordwise=nc, spanwise_panels_per_section=ns, cspace=cs,
    timeout_sec=900)
```

### 4.2 The cache hash — full provenance, no exceptions

Stage 6b runs at zero deflection. If the hash omits the control inputs, those runs
collide with cached +4° runs and silently return wrong numbers. This is a
correctness requirement, not hygiene.

Hash over, and write the full pre-image to `cache/<hash>/provenance.json`:

```
sample_id, nchordwise, spanwise, cspace, alpha_deg, beta_deg,
control_input_deg, diff_input_deg, viscous, velocity_mps, altitude_m,
sha256(configs/geometry/bwb.yaml), git SHA of src/aeris/, AVL binary version string
```

On every cache hit, re-read `provenance.json` and assert field-by-field equality
with the current request. A mismatch is a STOP condition under §9.

### 4.3 The quantity list — FROZEN, do not add or remove

Extract exactly these into every result row:

| group | fields |
|---|---|
| drag | `cd_ind`, `cd_total`, `span_efficiency`, `l_over_d` |
| forces | `cl`, `cm` |
| stability | `x_np`, and from `stability_axis_derivatives`: `CLa`, `Cma`, `Clp`, `Cmq`, `Cnb` |
| control | from `control_derivatives`: `elevon_sym.CL`, `elevon_sym.Cm`, `elevon_diff.Cl`, `elevon_diff.Cn`, `elevon_diff.CY` |
| hinge | `hinge_moments.elevon_sym`, `hinge_moments.elevon_diff` |
| mesh | `n_strips`, `n_vortices`, `n_sections` |
| meta | `status`, `seconds_avl`, `seconds_total`, `alpha_deg`, `nchordwise`, `spanwise`, `cspace`, `control_input_deg`, `diff_input_deg`, `sample_id` |

Hinge moments are in the list because they size the servos and, being hinge-line
quantities, they are the most panel-sensitive things the model produces. They were
omitted from the previous study.

**Derived quantities**, computed in Stage 6 from the above — no additional runs:

```
delta_trim     = -cm / elevon_sym.Cm            per design, per angle
static_margin  = (x_np - x_ref) / mac           x_ref and mac frozen in Stage 0
roll_power     = elevon_diff.Cl                 sign and magnitude
```

**Stage 0 must record the units of AVL's control derivatives** (per radian or per
degree, depending on the gain written into the `.avl` file). `delta_trim` inherits
those units. Getting this wrong silently scales every trim number by 57.3. Assert
the unit convention once in `common.py` and record it in the locked config.

If `x_ref` and `mac` are not directly available from the sample, record the moment
reference point AVL was given and use it consistently. Freeze both in Stage 0.

### 4.4 Vocabulary — the only labels this study may use

| label | meaning |
|---|---|
| `directional_estimate` | a Richardson-extrapolated value in one refinement direction with the other direction held fixed, e.g. `Q(chord→∞, span=2)`. Not the converged AVL solution. |
| `finest_grid_discrepancy` | the difference from the finest mesh actually computed. For non-monotonic convergence this bounds nothing. It replaces v1's `lower_bound`, which was an unearned claim. |
| `comparator` | the expensive setting a cheap setting is measured against within a stage. Always name which one. |

"True", "exact" and "converged" are forbidden everywhere.

### 4.5 The print-noise floor and near-zero quantities

AVL prints six decimal places, so its resolution is 1e−6.

> **Never compute a relative error against a comparator whose absolute value is
> below 1e−4.** Mark that cell's *relative* error `NaN`.

At a reference of 2.3e−5, one unit in the last printed digit is a 4.35% "error" from
rounding alone. Omitting this rule is what invalidated the previous 100-run study,
in which seven of nine options scored *identically* on meshes that differed sixfold.

**But do not discard the quantity.** v1 dropped these cells entirely, which would
have removed the lateral derivatives (`Cnb`, `elevon_diff.Cn`, `elevon_diff.CY`)
from the assessment altogether. For every quantity, in every stage, record three
numbers:

```
absolute error
relative error          NaN if |comparator| < 1e-4
normalised error        absolute error / scale[quantity]
```

`scale[quantity]` is frozen in Stage 0 as the median `|q|` across the 36 geometries
at +4° under the finest Stage 2 mesh. A quantity that fails the relative test is
still assessed on the normalised error.

### 4.6 Aggregation — frozen here, not chosen later

Wherever a stage reduces errors across geometries and angles to a single number for
a quantity, the rule is **worst case** — the maximum over (geometry × angle).
Report the median alongside it for context. The sample sizes here (4 or 8
geometries) are too small for a percentile to mean anything.

Where a stage reduces across quantities to a single number, the rule is again the
maximum over the quantities named by that stage's gate.

---

## 5. Stage 0 — Lock the inputs *(0 runs)*

**Purpose.** Fix everything that could be bent later to favour a preferred answer.

**Do:**

1. **Sampling.** Confirm what distribution the production sweep draws its designs
   from. If production uses a space-filling design, draw the **30 normal
   geometries** as a maximin-LHS subset of that same design. If production uses
   independent draws, use `make_sample('normal', seed)` for `seed = 2001 … 2030`.
   The requirement is distributional match with production, not space-filling for
   its own sake. Record which was used and why.
2. Build **6 extreme geometries** by overriding a base sample. Record the exact
   override for each in the locked config:
   - `narrow_elevon` — elevon band 0.70–0.85
   - `wide_elevon` — elevon band 0.50–0.98
   - `high_ar` — maximum aspect ratio in the design space
   - `strong_taper` — maximum taper gradient
   - `min_chord` — minimum tip chord
   - `max_sweep` — maximum sweep
3. For every one of the 36, confirm the loft builds and record semispan, reference
   area, aspect ratio and the elevon band.
4. **Coverage table.** Report min / median / max of **every** design variable across
   the 30 normal geometries, against the design-space bounds. Not only aspect ratio
   and reference area. Any variable covering less than half its range is reported as
   a limitation in the summary.
5. Resolve **§3.1** (control state) and **§3.2** (+8°). Record both decisions.
6. Record the **control-derivative unit convention** and the frozen `x_ref`, `mac`
   and `scale[quantity]` values (§4.3, §4.5).
7. Write the three **standing justifications** below into the summary, before any
   solver run.
8. Write `configs/aero/panelling_study/stage0_locked_config.json` containing: the
   36 sample definitions, the frozen quantity list, the derived-quantity
   definitions, the angles, the control state, the aggregation rules, the
   normalisation scales, the gates from §7, the git SHA, and the hash of
   `configs/geometry/bwb.yaml`.

### The three standing justifications — written now, before any result exists

**Altitude.** AVL's influence matrix is independent of altitude. Altitude enters
only through Reynolds number in the viscous correction and through dynamic
pressure, neither of which alters the discretisation error of the vortex lattice.
Panelling adequacy established at sea level therefore transfers to the altitude
variation present in the production dataset. No runs are spent on this.

**Spanwise = 1.** With `snap_sections_to_control = true`, spanwise 1 resolves the
elevon band with only as many strips as the section placement provides. Hinge
moments are expected to be unusable there. That is the intended "clearly below the
knee" point in Stage 3, and it is predicted here rather than discovered later.

**Determinism.** AVL solves a direct linear system. Repeated solves with identical
inputs are bit-identical. Every "scatter" reported anywhere in this study is
design-to-design variation, never run-to-run noise. Say this in any summary that
reports a spread.

**Plot:** one only.
`stage0_geometry_sample.png` — scatter, aspect ratio on x, reference area on y, 30
normal points in grey, 6 extreme points in red with labels. Title: *"the 36 shapes
this study uses"*.

**STOP.** Report: any geometry that failed to build, the coverage table, the two
resolved decisions, and the spread of the sample.

---

## 6. The stages

### Stage 1 — 2D lattice: are the two directions separable? *(108 runs, ~0.7 h)*

**Purpose.** Stages 2 and 3 each refine one direction while holding the other fixed.
That is only meaningful if the two errors are independent. This stage decides
whether the rest of the plan is valid, and it is deliberately the cheapest thing
that can invalidate it.

**Run:**

```
chordwise ∈ {8, 12, 20}   ×   spanwise ∈ {2, 4, 6}      (9 cells, all legal)
geometries: seeds 2001, 2002, 2003, 2004                (4 normal)
angles: −2, 0, +4
cspace: 1.0
```

**Compute.** For each quantity `q`, geometry `g` and angle `a`, form the 3 × 3 table
`Q[i][j]` over chordwise i ∈ {8, 12, 20} and spanwise j ∈ {2, 4, 6}. Apply the
standard two-way decomposition with no replication:

```
mu     = mean(Q)
A[i]   = mean_j(Q[i][:]) - mu          # chordwise main effect
B[j]   = mean_i(Q[:][j]) - mu          # spanwise main effect
AB[ij] = Q[i][j] - mu - A[i] - B[j]    # interaction residual

I = rms(AB) / (rms(A) + rms(B))
```

The solver is deterministic (§5), so `AB` carries no random error and the
decomposition is exact. Skip any cell failing the §4.5 floor on the relative test,
but assess it on the normalised error.

**GATE — both must hold:**

1. The **maximum** of `I` over all (quantity, geometry, angle) is **< 0.20**.
2. The ordering of the 4 geometries by `l_over_d` at +4° is identical at
   spanwise 2, 4 and 6.

Report `I` as a table: rows = quantities, columns = max and median. The aggregation
is worst case and was fixed in Stage 0.

**If the gate fails:** STOP and report. Do not run Stages 2 and 3 — they would not
be interpretable. The plan becomes a full 2D study and Mike and Claude will redesign
it.

**Record this limitation in the summary regardless of the outcome.** Separability is
demonstrated only on chordwise ∈ [8, 20] × spanwise ∈ [2, 6]. Stages 2 and 3
evaluate points outside that box (chordwise 6 and 48; spanwise 1 and 8). Behaviour
outside the box is an extrapolation. The Stage 5 shortlist must lie inside the box
unless Mike approves otherwise in writing.

**Plots:** two.

- `stage1_interaction_CL.png` — x = chordwise (8, 12, 20), y = `cl`, one line per
  spanwise value, three lines total, each labelled directly at its right-hand end.
  **If the three lines are parallel, the directions are separable.** Put that
  sentence in the title.
- `stage1_interaction_CD.png` — identical, for `cd_ind`.

**STOP.**

---

### Stage 2 — Chordwise convergence *(160 runs, ~0.85 h)*

**Purpose.** Establish how fast the answer settles as chordwise panels increase, and
how far from settled the candidate settings are.

**Run:**

```
chordwise ∈ {6, 12, 24, 48}      spanwise = 2 (fixed)     cspace = 1.0
geometries: seeds 2001 … 2008    (8 normal)
angles: −2, 0, +2, +4, +8
```

**Why spanwise 2:** 48 chordwise needs ≤ 125 strips. Spanwise 2 gives 96. Stage 1's
gate is what licenses carrying the conclusion to other spanwise counts.

**Why these four values:** they contain two ratio-2 chains — `6 → 12 → 24` and
`12 → 24 → 48`. The two chains overlap in two of three points, so they are a
**consistency check** on the observed order `p`, not independent estimates.
Disagreement falsifies asymptotic behaviour; agreement is necessary but not
sufficient. Do not claim more than that anywhere.

**Compute, per quantity, per geometry, per angle:**

1. `delta` — relative change from the previous mesh.
2. Observed order from each chain: `p = log2(|Q₁₂−Q₆| / |Q₂₄−Q₁₂|)` and likewise for
   the finer chain.
3. **Admissibility gates — all six must pass before extrapolating:**
   - monotonic across the chain,
   - differences shrinking,
   - `0.5 ≤ p ≤ 3`,
   - the two chains' `p` agree within 30%,
   - comparator above the 1e−4 noise floor,
   - **asymptotic-range ratio** `R = GCI_coarse / (2^p · GCI_fine)` satisfies
     `0.8 ≤ R ≤ 1.25`. Report `R` for every quantity whether or not it passes.
4. **If all pass:** Richardson-extrapolate and compute the GCI. Label the result
   `directional_estimate` — it is `Q(chord→∞, span=2)`, not the converged AVL
   solution.
5. **If any fails:** do not extrapolate. Use chordwise 48 as comparator, and label
   every error computed against it **`finest_grid_discrepancy`**. Say so in the
   summary, and name which of the six gates failed.

**Plots:** two.

- `stage2_convergence.png` — x = chordwise on a log-2 axis, y = `elevon_sym.CL`
  (elevon power, the most panel-hungry quantity), one line, points marked. If
  extrapolation was admissible, add a single horizontal dashed line for the
  estimate, labelled *"estimated limit"*. Nothing else on the plot.
- `stage2_error_vs_time.png` — x = median seconds, y = error in percent, four
  points, each labelled with its chordwise count, connected by one line.
  **This is the knee plot.** Title: *"where does more time stop buying accuracy?"*

**STOP.** Report: observed orders, `R` for every quantity, whether the two chains
agreed, which quantities were refused extrapolation and why, and where the knee
appears to be.

---

### Stage 3 — Spanwise convergence *(160 runs, ~0.85 h)*

**Run:**

```
spanwise ∈ {1, 2, 4, 8}      chordwise = 12 (fixed)      cspace = 1.0
geometries: seeds 2001 … 2008
angles: −2, 0, +2, +4, +8
```

Chains: `1 → 2 → 4` and `2 → 4 → 8`. Same computation, same six admissibility gates,
same labelling as Stage 2.

**Expect spanwise 1 to fail** on hinge moments and possibly on `elevon_diff.*`, for
the reason recorded in Stage 0. Report it as a confirmed prediction, not a surprise.

**Watch for this and report it explicitly.** The viscous correction is applied per
strip, so refining spanwise refines the discretisation of the profile-drag integral
as well as the vortex lattice. `cd_total` may therefore converge differently from
`cd_ind`, and `l_over_d` may be governed by the viscous term rather than the induced
term. If that is what the data shows, say so — it materially affects how much
spanwise resolution the shortlist should carry.

**Plots:** two, identical in form to Stage 2 — `stage3_convergence.png` and
`stage3_error_vs_time.png`, with spanwise on the x axis.

**STOP.**

---

### Stage 4 — Panel spacing *(52 runs, ~0.4 h)*

**Purpose.** Chordwise panels need not be evenly spaced. Cosine spacing bunches them
at the leading and trailing edges where pressure changes fastest. We have never
checked whether that is right at a *reduced* panel count, where it matters most.

**Run at spanwise 2**, so that the Stage 2 comparator applies without mixing
spanwise error into the spacing comparison. At spanwise 4 the intended comparator
is not even legal (192 strips × 32 = 6,144 vortices, over the limit).

```
cspace   ∈ {0.0 uniform, 0.5 half-cosine, 1.0 full cosine}
chordwise ∈ {8, 12, 16, 24}      spanwise = 2      geometries: seeds 2001–2004
angle: +4 only                                                        (48 runs)
comparator: chordwise 48, spanwise 2, cspace 1.0     — cached from Stage 2, free
```

**Reference-neutrality check (4 runs).** Run chordwise 48, spanwise 2,
`cspace = 0.0` on the same four geometries at +4°.

- If the uniform and cosine solutions at 48 panels agree to within the §4.5 floor,
  the comparator is spacing-independent and the comparison is not rigged in favour
  of cosine. Record the agreement figure.
- If they do not agree, **STOP**. The spacing question is then not separable from
  the convergence question and the stage design needs revisiting.

Several cells of the main grid are Stage 2 cache hits. Report how many.

State in the summary that the spacing conclusion is established at spanwise 2 and
carried to other spanwise counts under the Stage 1 separability result.

**Plot:** one.
`stage4_spacing.png` — grouped bar chart. x = chordwise count (4 groups), 3 bars per
group (one per spacing), y = error in percent against the Stage 2 comparator. Legend
with three entries. Nothing else.

**STOP.**

---

### Stage 5 — Shortlist *(0 runs)*

**Purpose.** Stage 6 costs half the remaining budget and runs once. The five
settings chosen here are the five the study will be able to say anything about.

**Cost model.**

```
vortices = 48 × spanwise × nchordwise      subject to 48 × spanwise ≤ 500
                                                   and vortices ≤ 6000
```

Use measured median seconds from Stages 2–4 where available; interpolate on vortex
count elsewhere. Replace all interpolated figures with measurements after Stage 7.

**Composed uncertainty.** For a configuration `(nc, ns, cs)`:

```
eps(nc, ns, cs) = eps_chord(nc | ns=2) + eps_span(ns | nc=12) + eps_space(cs)
```

Additive, not root-sum-square. This is conservative and is licensed by the Stage 1
separability result. The rule is fixed here and is not revised after seeing the
Pareto front.

**Do.** Select **exactly 5 complete configurations** on the (cost, `eps`) Pareto
front:

1. one clearly **below** the knee — deliberately too cheap, to show failure,
2. **three spanning** the knee, one of which must be the current production setting,
3. one clearly **above** the knee — the cheapest configuration whose `eps` is under
   **0.5%**. This becomes the comparator for Stage 6.

**The five must not all share one (spanwise, cspace) pair.** v1 fixed spanwise and
spacing uniformly, which meant the study varied only chordwise while claiming to
decide all three. If Stages 3 and 4 genuinely show that a single spanwise count and
a single spacing dominate at every cost level, that is an acceptable outcome — but
it must be stated as a finding with its evidence, not assumed by construction.

All five must lie inside the Stage 1 separability box (chordwise 8–20, spanwise 2–6)
or carry a written note of the extrapolation and Mike's approval.

Write `configs/aero/panelling_study/stage5_shortlist.json` with the five
configurations, their cost, their composed `eps` with the three contributions shown
separately, and a one-line justification each.

**Plot:** one.
`stage5_pareto.png` — x = median seconds, y = composed numerical uncertainty in
percent. All configurations evaluated so far as small grey dots; the five chosen as
large labelled dots. Title: *"the five settings taken forward, and why"*.

**STOP.** Mike approves the shortlist before Stage 6 runs.

---

### Stage 6 — Ranking and decision test *(450 + 90 runs, ~4.3 h)*

**Purpose.** The decisive test. A cheap setting wrong by 3% on *every* design keeps
the ordering and costs nothing. A setting wrong by 1% *randomly* shuffles the
ordering and makes you promote the wrong aircraft. And a setting that keeps the
ordering while shifting every trim deflection by 30% makes you promote an aircraft
that cannot be trimmed.

**Run:**

```
5 shortlisted settings × 30 normal geometries × angles −2, 0, +4     = 450
5 shortlisted settings ×  6 extreme geometries × angles −2, 0, +4    =  90
```

If Stage 0 determined that production sweeps +8°, add it here (+180 runs).

The extreme geometries are computed and reported **separately** and are never pooled
into the normal statistics. They were hand-picked to be hard and would drag the
averages somewhere unrepresentative.

**Compute:**

1. Rank the 30 designs by `l_over_d` at +4° under the comparator, and under each
   cheap setting.
2. **Spearman correlation** between the two orderings, and the **maximum rank
   displacement** of any single design.
3. **Top-10 set retention** and **top-3 set retention**, each as `n/k`.
4. **The `l_over_d` gap** between ranks 3 and 4, and between ranks 10 and 11, under
   the comparator, expressed as a percentage. Compare each against the cheap
   setting's own uncertainty.
5. **Objective regret** — take the design the cheap setting ranks first, look up its
   `l_over_d` under the comparator, and express the shortfall against the
   comparator's best as a percentage.
6. **Bias versus scatter**, per quantity: the ratio cheap/comparator for each of the
   30; report the mean (the bias), the spread (the scatter), and the spread as a
   percentage of the bias. Report the sign of every control derivative.
7. **Decision preservation.** Compute `delta_trim` and `static_margin` (§4.3) for
   every design at every angle under both the comparator and the cheap setting.
   Report: how many designs change trimmable/untrimmable label, how many change
   stable/unstable label, and the maximum `|Δ delta_trim|` in degrees.
8. Percentage of runs that succeeded.

**Plots:** four, all simple.

- `stage6_rank_agreement.png` — one scatter per cheap setting, laid out in a single
  row. x = rank under the comparator (1–30), y = rank under the cheap setting.
  A grey 45° line. Points on the line means perfect agreement. Spearman value in
  each panel title.
- `stage6_top10.png` — bar chart, one bar per setting, height = top-10 retention
  (0–10). A horizontal line at 10 labelled *"required"*.
- `stage6_bias_vs_scatter.png` — one bar per quantity, height = scatter as a
  percentage of bias, for the recommended setting only. A horizontal line at 5%
  labelled *"limit"*. Below the line is safe.
- `stage6_trim_shift.png` — one bar per setting, height = maximum `|Δ delta_trim|`
  in degrees across all 30 designs and 3 angles. A horizontal line at 0.5° labelled
  *"limit"*.

**STOP.**

---

### Stage 6b — Deflection sensitivity *(120 runs, ~0.6 h)*

**Purpose.** Demonstrate that the panelling choice does not depend on the control
state it was validated at. This is what makes §3.1 a justification rather than an
assumption.

**Run:**

```
5 shortlisted settings × geometries 2001–2008 × angles −2, 0, +4
elevon symmetric = 0.0     elevon differential = 0.0
```

Verify before starting that these produce **cache misses** (§4.2). If any run
returns instantly, the hash is wrong — STOP.

**Compute.** Spearman, maximum rank displacement, top-10 set retention (over 8
designs, so report top-3 here instead) and objective regret, exactly as in Stage 6
but on the 8-geometry subset. Recompute the same statistics on the Stage 6 data
restricted to seeds 2001–2008 so the two are directly comparable.

**GATE.** The setting selected by §7 must be unchanged when the study is run at zero
deflection. If it changes, STOP and report — the panelling decision is
deflection-dependent and the study must say so rather than pick one state.

**Plot:** one.
`stage6b_deflection.png` — bar chart, one pair of bars per setting: objective regret
at (+4, +4) and at (0, 0). Title states whether the selection changed.

**STOP.**

---

### Stage 7 — Honest timings *(25 runs, ~0.2 h)*

**Purpose.** A timing taken while other jobs share the machine is not a timing. A
timing taken from cache is not a timing at all.

**Run.** Each of the 5 shortlisted settings, 5 repeats, on geometry seed 2001 at +4°,
**strictly one at a time with nothing else running.** Disable all parallelism for
this stage. Call `run_case(..., bypass_cache=True)` and write to
`data/panelling_study/cache/timing/<setting>/<repeat>/` so nothing is reused and
nothing overwrites the study cache. Report the **median**, not the best.

**Report three numbers per setting:**

1. median AVL-only seconds,
2. median end-to-end seconds including the ~1.4 s section build,
3. projected hours for 2,000 designs × 3 angles, computed from **end-to-end** time.

The section build is a per-design constant that does not scale with panelling, so it
dilutes the relative saving of a cheaper mesh. That dilution is real and the
selection rule must see it.

**Then** revise `stage5_shortlist.json` in place with measured costs replacing
interpolated ones, and note in the summary whether any interpolated cost was wrong
by more than 20%.

**Plot:** one.
`stage7_cost.png` — bar chart, one bar per setting, height = median end-to-end
seconds. Single y-axis. Print the projected hours as a text label above each bar.
**No twin axis** — §8 forbids it and v1 contradicted itself here.

**STOP.**

---

## 7. The acceptance gates — fixed now, do not adjust

A cheap setting is admissible only if **all seven** hold, on the 30 normal
geometries. The 6 extreme geometries are reported against the same gates but
separately, and a failure there is a documented limitation, not a disqualification.

| # | gate |
|---|---|
| 1 | Spearman on `l_over_d` **≥ 0.98**, *and* no single design displaced by more than **4 rank positions** |
| 2 | **Top-10 set retention = 10/10.** Report top-3 but do not gate on it |
| 3 | **Objective regret ≤ 0.5%** |
| 4 | Numerical uncertainty **< 1%** on `cl`, `cm`, `cd_ind`, `cd_total`, `x_np` — GCI where admissible, `finest_grid_discrepancy` where not, aggregated worst case per §4.6 |
| 5 | Control derivatives: **sign preserved** on all five, **\|bias\| ≤ 5%** and **scatter ≤ 5% of bias** on `elevon_sym.Cm` and `elevon_diff.Cl` |
| 6 | **Decision preservation** — zero designs change trimmable/untrimmable label, zero change stable/unstable label, and `\|Δ delta_trim\| ≤ 0.5°` for every design at every angle |
| 7 | **100%** of runs report `status == "SUCCESS"` |

**Why gate 1 carries a displacement clause.** At n = 30, Spearman ≥ 0.98 permits
`Σd² ≤ 89` — approximately one design moving nine rank positions while everything
else stays put. The global correlation alone does not protect against exactly the
failure this study is trying to prevent.

**Why gate 2 replaces v1's top-3.** Exact top-3 retention can be failed by a swap
between two designs that are numerically indistinguishable. If Stage 6 step 4 shows
the rank-10/11 gap is smaller than the setting's own uncertainty, gate 2 is
**uninformative** and must be reported as such — the study then rests on gates 3
and 6, and the summary must say so plainly rather than quietly passing.

**Why gates 5 and 6 replace v1's control gate.** v1 allowed any size of bias
provided the scatter was small. A uniform 30% error in elevon power preserves every
ranking and shifts every trim deflection by 30%, which moves designs across the
feasibility boundary. Gate 6 tests the decision directly and costs nothing extra.

### The selection rule

**Among settings passing all seven gates, choose the cheapest by end-to-end time.**
That is the entire rule. It already implements the knee — the cheapest passing
setting is by construction the point beyond which more spending buys nothing the
gates recognise. The knee plot is evidence shown to the reader, **not an eighth
gate**. Stage 6b then confirms the choice is not an artefact of the control state.

### If nothing passes

Do not lower a gate to produce a winner. Report that the design tier needs a more
expensive discretisation than hoped, and state what it costs.

---

## 8. Plot rules — read before writing any plotting code

Mike reviews these between stages. They must be readable in three seconds.

**Required:**

- **One message per plot.** If you need two sentences to explain it, split it.
- Matplotlib defaults. No custom styles, no seaborn themes.
- **Maximum 4 lines or 5 bars** on one axes. `stage6_top10.png`,
  `stage6_trim_shift.png`, `stage7_cost.png` and `stage6b_deflection.png` each have
  5 settings and are within this.
- **Label lines directly at their right-hand end**, not in a legend, whenever there
  are 4 or fewer.
- Axis labels with units. A title that states the finding, not the contents —
  *"error stops falling after 16 panels"*, not *"error vs panels"*.
- `dpi=150`, `bbox_inches='tight'`.
- Percentages as percentages (`3.8%`), never as `0.038`.

**Forbidden:**

- Multi-panel dashboards. The only exception is `stage6_rank_agreement.png`, which
  is one row of small scatters.
- Twin y-axes, log-log plots, colour maps, 3D anything, shaded uncertainty regions.
  Log-2 on a single x-axis (Stages 2 and 3) is permitted.
- More than 5 colours in the whole study. Use grey for reference lines and one
  accent colour for the thing being shown.
- Any plot not listed in this runbook. If you think one is needed, say so in the
  stage report and let Mike decide.

---

## 9. Failure handling

| situation | what to do |
|---|---|
| a single run fails after one retry | record `ok=False` and the reason, continue, report the count at the stage end |
| more than 5% of a stage's runs fail | STOP, report |
| any run returns `status != "SUCCESS"` but non-`None` numbers | STOP immediately — this should be impossible and means something is wrong with the guard |
| AVL reports a different mesh than requested | STOP immediately |
| a cache hit whose `provenance.json` does not match the request | STOP immediately — the hash is wrong and every earlier result is suspect |
| a Stage 6b run returns instantly | STOP immediately — same cause as above |
| the Stage 4 reference-neutrality check fails | STOP, report |
| a stage gate fails | STOP, report, do not proceed |
| a quantity fails the extrapolation gates | this is normal — fall back to `finest_grid_discrepancy` labelling, note which gate failed, continue |

---

## 10. What each stage report must contain

Plain text, at `configs/aero/panelling_study/stage<N>_summary.txt`:

1. What was run: cells, geometries, angles, total runs, **new solves versus cache
   hits**, total wall-clock.
2. Failures: how many, which, why.
3. The numbers the stage exists to produce — as a small table, not prose.
4. Whether the stage gate passed.
5. **One paragraph in plain English** saying what the result means. Write it for
   someone who has not read this runbook.
6. Anything that surprised you, or that you think is wrong.

Point 6 is not optional. If something looks strange, say so. The previous study
failed because inconvenient results were smoothed over rather than reported.

---

## 11. Order of work

```
Stage 0  →  STOP  →  Stage 1  →  STOP  →  Stage 2  →  STOP  →  Stage 3  →  STOP
         →  Stage 4  →  STOP  →  Stage 5  →  STOP  →  Stage 6  →  STOP
         →  Stage 6b →  STOP  →  Stage 7
```

Mike reviews the plots at each STOP and discusses them with Claude before you
continue. Do not anticipate the next stage's work while waiting.

**After Stage 7:** archive the `.avl` input decks and AVL stdout for the
**comparator** runs only into
`configs/aero/panelling_study/raw_comparator.tar.gz`. Tracked CSV summaries are not
enough to reconstruct a disputed number; archiving all 1,165 raw directories is not
proportionate.

---

## 12. Run budget

| stage | runs | approx serial |
|---|---|---|
| 0 | 0 | — |
| 1 | 108 | 0.7 h |
| 2 | 160 | 0.85 h |
| 3 | 160 | 0.85 h |
| 4 | 52 | 0.4 h |
| 5 | 0 | — |
| 6 | 540 | 4.3 h |
| 6b | 120 | 0.6 h |
| 7 | 25 | 0.2 h |
| **total** | **1,165** | **~8.2 h** |

Add 180 runs (~1.4 h) to Stage 6 if Stage 0 determines that production sweeps +8°.

Stages 2, 3 and 4 overlap with Stage 1 at `(chordwise 12, spanwise 2, cspace 1.0)`
for seeds 2001–2004 at −2, 0, +4, and Stage 4's main grid overlaps Stage 2. Actual
new solves will be below the totals above.

---

## 13. Scope — what this study does not do

This establishes **only** that the chosen AVL discretisation is numerically settled,
preserves the design ranking, and preserves the trim and stability classification
**under the AVL model**. It does **not** establish that AVL agrees with CFD or
experiment, that the viscous correction is right, that the elevon model is
realistic, or that AVL captures separation.

Those are separate levels of validation and separate studies. Do not claim any of
them in any stage report.

Two further limitations that must appear in the final summary rather than be left
for a reviewer to find:

1. **Separability is demonstrated on a smaller domain than it is used on.** Stage 1
   covers chordwise 8–20 × spanwise 2–6; Stages 2 and 3 evaluate outside that box.
   Every use of the separability result outside the box is an extrapolation.
2. **`l_over_d` is evaluated at a differentially deflected state** (unless Stage 0
   determined otherwise), so it carries the induced-drag penalty of the
   antisymmetric loading, which depends on elevon band geometry. Stage 6b is what
   tests whether the panelling decision is sensitive to this; it is not a claim that
   the state itself is representative of trimmed flight.
