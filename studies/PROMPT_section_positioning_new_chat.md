You are the lead researcher on the AERIS BWB aerodynamics project, and you will
execute a study you must be able to defend at AIAA SciTech. Be sceptical of your own
results, pre-register everything, and never tune a gate to manufacture a winner.

# Task
Design-and-run the **adaptive spanwise section-positioning study** specified in
`studies/RUNBOOK_section_positioning_study_v1.md`. Read that runbook in full first —
it is the contract. It fixes the two flaws that would sink the prior attempt: a
reference biased toward uniform, and gates that were not decision-relevant.

# Context you must load before doing anything
- The runbook: `studies/RUNBOOK_section_positioning_study_v1.md`.
- Prior work you are superseding the *evidence* of (keep the ideas, redo the proof):
  `studies/adaptive_section_placement.md`, `decision/0011-adaptive-section-placement.md`.
- The metric module you will extend: `src/aeris/geometry/geometric_information.py`
  (`spanwise_information_profile`, `adaptive_span_fractions`, `ramp_fraction`).
- The geometry: `configs/geometry/bwb.yaml` (3 sweep segments sw1/2/3, chords
  c1..c4 at breaks b0..b3, four fixed-station airfoils mh91/mh91/e374/nlf1015, one
  elevon pair whose band is a DoE variable, `section_placement: auto`).
- **Reuse the panelling study's infrastructure — do NOT re-implement it:**
  `standalone/panelling_study/common.py` (the AVL runner, provenance-hash cache,
  subprocess-slice parallelism, GCI/§4.5-floor/worst-case machinery), its cache under
  `data/panelling_study/`, and `configs/aero/panelling_study/all_runs.csv`.
  Its full report + audit is `studies/panelling_study_report.html`.
- **A decision already made:** the panel mesh is FROZEN at **c16s2u** (chord 16,
  span-2 multiplier, uniform spacing). This study moves only the section axis.

# The intellectual core (what makes it AIAA-worthy)
1. **Legitimate ground truth without CFD.** The geometry is analytic, so AVL's only
   section error is piecewise-linear spanwise interpolation. The reference is a dense
   section set that is *provably placement-independent* — Gate G1: three dense
   placements (uniform / adaptive / opposite-clustered) must agree < 0.5%, AND a
   Richardson band in 1/N < 0.5%. Prove it per design; STOP and densify if it fails.
   This is the fix for the prior study's fatal bias (it used a uniform reference that
   shared a family with the uniform candidate).
2. **Express complexity as a horse-race, judged on that neutral reference** (§4):
   M0 uniform, M1 ramp-fraction (validated difficulty scalar), M2 magnitude-preserving
   curvature equidistribution (ρ∝|g''|^½ — do NOT reintroduce the per-channel
   unit-integral normalisation that erased magnitude; that was the prior bug),
   **M3 the new hybrid** = curvature × aerodynamic-influence weight w(y) (goal-oriented:
   place nodes where the wing is geometrically busy AND aerodynamically loaded — build
   w(y) cheaply from AVL loading |dΓ/dy| and the control-influence kernel), and M4 =
   M3 + a proper cell-size-ratio gradation limiter + hard nodes + a budget selector.
   Gate G6 forbids using any monitor that can't predict difficulty (ρ≥0.7) — kills
   circularity; the prior `concentration()` score fails this and is the negative control.
3. **Hard points are constraints, not choices.** Fixed-airfoil stations, planform
   breaks, and elevon-band edges are mandatory nodes; Stage 4 ablation proves each earns
   its place. The free budget is distributed among them.
4. **Deliver the budget selector** the prior study punted (how MANY sections), and
   validate it for efficiency AND safety (G7).

# How to work
- Execute the runbook stage by stage (0→9). Each stage has a gate; if a stage gate
  fails, STOP and report — do not work around it.
- **Stage 0 first, and its provenance check is non-negotiable:** the cache hash MUST
  include the full section-fraction vector + placement id, or two placements at the
  same N collide and return wrong numbers. Prove it with a two-placement hash-diff
  before any solving (the panelling study had the analogous control-input hash bug).
- Pre-register gates and monitors before seeing results. Worst-case aggregation
  (max over design × angle × control state). Apply the 1e-4 noise floor.
- Report negative results in full — a conditional "adaptive pays only when uniform
  breaches the ramp criterion" is a legitimate, defensible outcome.
- Present results at each stage with §8-compliant plots (≤4 lines/5 bars, finding-as-
  title, readable in 3s). The money figure is a span-map: where sections land vs the
  loading/curvature, per policy.
- You are authorised to make all engineering and methodological decisions and proceed
  without asking for approval; show results at stage checkpoints for transparency.

# Deliverables
1. Stage-by-stage execution against the runbook, gated.
2. A full analytical HTML report and a plain-language one-pager, in the exact style of
   `studies/panelling_study_report.html` (embed all plots as data URIs; theme-aware).
3. `decision/0012-section-positioning-doe.md`: the recommended placement policy +
   budget rule, the worst-case accuracy it guarantees, the section saving vs uniform at
   equal accuracy, and the explicit boundary (where it helps / is neutral / must
   escalate). Plus the one defensible complexity scalar and the one that must not be used.
4. Git commits on `main` (study files, scripts, summaries, JSON, report) so I can push —
   never commit secrets (`github_token.txt` is gitignored) and never commit the solver
   scratch cache (only the per-run JSON, as the panelling study did).

Start by reading the runbook and the two prior artifacts, then produce the Stage 0
lock and its provenance-hash proof.
