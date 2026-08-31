# Runbook — completing the atlas outcome matrix

**Purpose.** Turn the 11.8 % of the (geometry × template) outcome matrix that the
atlas happened to measure into the whole thing, so that any routing or stopping
policy can be evaluated exactly instead of by restricted replay.

**Run this on the desktop.** It is mesh-only: no solver, no CFD, no GPU.

---

## Why this campaign is the one that matters

The counterfactual replay in `results/exp03_policy_evaluation.md` is restricted
to the templates the atlas actually attempted, because those are the only cells
whose outcome is recorded. That makes every learned-policy number a **lower
bound** — the policy is not allowed to reach into the 88 % of the matrix nobody
measured.

With the full matrix, the evaluation becomes exact for *any* policy, the paper's
central claim stops depending on a restriction, and the same table also gives:

- the per-geometry **quality ceiling** (the best any template can do), which is
  what the stopping rule has to predict;
- the true **template coverage** structure — which templates are redundant;
- a clean measurement of how far design-space distance really is from optimal
  routing.

## Cost, from the ledger rather than a guess

| | |
|---|---|
| Cells already measured | 247 |
| Cells remaining (100 × 21) | **1,853** |
| Mean attempt | 15.5 s (median 17.4 s, p90 24.1 s) |
| Cost by outcome | PASS 20.0 s · folded 11.2 s · low quality 9.4 s · **surface build error ≈ 0 s** |
| **Estimated wall-clock** | **≈ 8 hours**, resumable |

Surface-build errors cost essentially nothing, which is why the paper reports
wall-clock alongside attempt counts: failing fast is not the same as failing.

## Campaign A — complete the matrix (do this first)

The driver already supports this without modification. `development_atlas.py`
stops a geometry early when an attempt reaches `--preferred-quality`; setting
that above any achievable value makes it evaluate **every** template for every
geometry, which is exactly a full sweep.

```bash
cd ~/Desktop/Start_Up/Code/v.0.1_Project

python AERIS_MESH_STUDY/04_strategy_studies/S6_bounded_mesh_atlas/development_atlas.py \
  --output artifacts/s6_bounded_mesh_atlas/matrix_completion_v1 \
  --atlas-manifest artifacts/s6_bounded_mesh_atlas/atlas_manifest_production_qualified21_eps15_s0p3p6_v7.json \
  --eps-e 1.5 \
  --preferred-quality 1.01 \
  2>&1 | tee artifacts/s6_bounded_mesh_atlas/matrix_completion_v1/run.log
```

Notes before running it:

- **`--preferred-quality 1.01` is the whole trick.** Scaled quality cannot reach
  1.01, so nothing is ever accepted early and every template is attempted.
- **Resume is the default** (`--no-resume` opts out). The checkpoint is written
  after every geometry, so an interrupted run continues where it stopped, and a
  configuration mismatch raises rather than silently mixing runs.
- **Do not pass `--retain-written-meshes`.** The existing campaigns did not
  retain volumes; keeping 2,100 of them would be gigabytes for no benefit, since
  every quality metric is recorded in the checkpoint.
- Confirm `--eps-e 1.5` matches the pooled production configuration
  (`1.5 | 3.6e-06 | 257 | production`), or the results are not comparable with
  what is already measured.
- The 21-template manifest is the one whose indices are
  `{2,8,16,24,29,41,42,43,47,56,65,68,70,81,85,88,89,90,92,94,95}`.

Then re-run the analysis; it picks the new campaign up automatically:

```bash
python AERIS_MESH_AGENT/experiments/exp01_ledger_audit.py
python AERIS_MESH_AGENT/experiments/exp02_outcome_model.py
python AERIS_MESH_AGENT/experiments/exp03_policy_evaluation.py
python AERIS_MESH_AGENT/experiments/exp04_robustness.py
python AERIS_MESH_AGENT/experiments/exp05_figures.py
```

## Campaign B — a real feasibility boundary

The development set passes 100/100 eventually, so it contains **no infeasible
geometry**. Any claim about predicting meshability, as opposed to predicting
routing cost, is unsupported until the design space is widened until things
genuinely break.

Sample designs beyond the current planform bounds — larger sweeps, sharper
taper, more aggressive twist and tip geometry — and run the same sweep. Aim for
roughly 20–40 % of geometries with no acceptable template at all. Until that
exists, the paper should say "routing cost", never "meshability".

## Campaign C — the knob, not just the template

`eps_e` is currently frozen at 1.5 for the entire design space, and
`development_atlas.py` exposes `--eps-e` over the `EPSE_LADDER`. Repeating a
subset of the matrix at two or three ladder values turns the action from "which
template" into "which template **and** which smoothing", which is the second
half of the agent's action space.

Start small: the 26 geometries that needed more than one attempt, at two extra
`eps_e` values, is 26 × 21 × 2 ≈ 1,100 attempts ≈ 5 h.

## What must not be touched

`round_c_lhs10_seed42` is the ADR-0011 hold-out. It is run once, after the
freeze signal, and no policy, model or threshold in this paper may be tuned
against it. `shared/geometry_sets.py` guards it deliberately; nothing in
`AERIS_MESH_AGENT/` references it.
