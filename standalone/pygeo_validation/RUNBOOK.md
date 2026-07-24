# pyGeo validation runbook (roadmap steps 1–2)

Two tools, two weights.

## 1. Config-frame validation (step 1) — LIGHT, run anywhere

Builds only the neutral loft + slices; no CAD/exports. Safe in an assistant session.

```bash
PYTHONPATH=src .venv/bin/python -m standalone.pygeo_validation.validate_config_frame \
  --config configs/geometry/paper1_bwb_pygeo.yaml \
  --check-controls-invariance \
  --report-dir configs/geometry/pygeo_validation_evidence
```

Gate = frame reconstruction + reference area/span/AR + control-surface invariance.
Result on the production config: **GATE 4/4 PASS**; smoothing characterized
(chord 1.18%, twist 0.40°, LE 8.4 mm). See `pygeo_validation_evidence/`.

## 2. Wide-bound smoke DoE — LIGHT, run anywhere

Sweeps N sampled designs through the neutral-loft gate over the WIDE bounds of
`paper1_bwb_pygeo_smoke_doe.yaml`.

```bash
PYTHONPATH=src .venv/bin/python -m standalone.pygeo_validation.validate_config_frame \
  --config configs/geometry/paper1_bwb_pygeo_smoke_doe.yaml --doe 24 \
  --report-dir configs/geometry/pygeo_validation_evidence
```

Result: **24/24 built + gate-pass** (seeds 3000..3023, ~22 s). Reference-metric
reproduction: area rel err max 4.0e-4. Smoothing envelope over the design space:
chord p95 1.68% / max 1.88%, twist p95 0.49° / max 0.55°, LE max ~12 mm.
See `pygeo_validation_evidence/paper1_bwb_pygeo_smoke_doe_doe.md`.

## 3. Heavy-CAD DoE — DESKTOP ONLY

Exercises the full production `aeris geometry generate` path (physical CAD split
elevon, STEP export, Gmsh STEP-import audit, STL/OBJ/VTK) that the light sweep
skips. Heavy: per-case CAD tessellation + Gmsh + tens of MB of STL/STEP. Run on the
desktop, not in a session.

```bash
PYTHONPATH=src .venv/bin/python -m standalone.pygeo_validation.run_cad_doe \
  --config configs/geometry/paper1_bwb_pygeo_smoke_doe.yaml \
  --seeds 3000,3005,3011,3017,3023 \
  --out-dir data/runs/pygeo_cad_doe
```

Seeds default to a 5-point spread of the already-loft-validated 3000..3023 set, so
a CAD failure is unambiguously a CAD-path issue. Writes one production run folder
per seed + `cad_doe_summary.json` (QC status, STEP-import-audit outcome, artifact
size per case). **Rescue `cad_doe_summary.json` into `configs/` before wiping
`data/runs/`** (memory policy: findings live in configs/, data/ gets wiped).

To widen: pass more seeds. Each adds one full CAD generate (~tens of MB).
