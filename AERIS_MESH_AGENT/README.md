# AERIS_MESH_AGENT

Paper code for **learned routing and stopping in automated structured-mesh
generation** over the AERIS parametric BWB family.

The question: an automated CFD dataset campaign has to mesh every geometry
before it can solve any of them, and finding a recipe that works for each new
shape is what actually throttles the campaign. The S6 bounded atlas already
records every attempt it makes. This treats that ledger as data.

## What is here

```
src/mesh_agent/      ledger extraction, features, outcome models, policies
experiments/         exp01..exp05, each writing to results/ tables/ figures/
paper/PAPER.md       the draft; build_paper.py injects generated results
runbook/             the desktop campaign that makes the evaluation exact
tables/ figures/ results/    generated, reproducible from the commands below
```

## Reproduce

```bash
export OMP_NUM_THREADS=1          # tiny data; threading is pure overhead here
python experiments/exp01_ledger_audit.py
python experiments/exp02_outcome_model.py
python experiments/exp03_policy_evaluation.py
python experiments/exp04_robustness.py
python experiments/exp05_figures.py
python paper/build_paper.py
```

Runs in about twelve minutes on twelve CPU cores. No GPU, no solver, no CFD.

## Findings so far

- The atlas ledger is **deterministic**: cells measured by two independent
  campaigns disagree in 0 of the overlapping cases.
- The single recorded `FAIL` state hides **three** events with different costs
  and different remedies — a folded march, a valid-but-under-quality mesh, and a
  surface-build error that costs no time at all.
- **35 of 162 attempts** in the production campaign were made *after* a passing
  mesh already existed. The incumbent has no stopping rule.
- Geometry `lhs100_seed42_095` spent 21 attempts and accepted the result of its
  first, which was the best of all 21.
- A gradient-boosted model on **design variables alone**, validated with each
  geometry held out, cuts the campaign from 162 attempts to 114 while holding
  accepted quality within 0.3 %.
- Adding *only* a stopping rule — no model — already reaches 127, so the missing
  stopping rule is the larger defect. Saying otherwise would credit machine
  learning with someone else's saving.
- In wall-clock the gain is smaller than the attempt count suggests: 48 → 38
  min, because the saved attempts are disproportionately the cheap failures.

## What this cannot claim yet

The development set meshes 100/100 eventually, so there is **no infeasible
geometry in the data**. Nothing here supports a claim about predicting
meshability; the claim is about predicting routing cost. See
`runbook/RUNBOOK_matrix_completion.md`, campaign B.

Only 11.8 % of the (geometry × template) matrix has ever been measured, so
policies are evaluated by *restricted* replay and every saving is a lower bound.
Campaign A (≈ 8 h, mesh-only) removes that restriction.

## Hold-out

`round_c_lhs10_seed42` is the ADR-0011 hold-out. No code in this package
references it, and no model or threshold here may be tuned against it.
