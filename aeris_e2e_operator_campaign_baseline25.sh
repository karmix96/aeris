#!/usr/bin/env bash
set -uo pipefail

# AERIS staged E2E operator campaign — baseline_bwb_25, non-fail-fast.
# This is intentionally NOT a strict CI script.
# It runs checkpoints, records pass/fail, keeps going where possible, and prints a final summary.
#
# Recommended:
#   cd ~/Desktop/Start_Up/Code/v.0.1_Project
#   chmod +x aeris_e2e_operator_campaign_baseline25.sh
#   N_GEOMS=4 timeout 3600 bash ./aeris_e2e_operator_campaign_baseline25.sh
#
# Stronger:
#   N_GEOMS=6 timeout 3600 bash ./aeris_e2e_operator_campaign_baseline25.sh

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/Desktop/Start_Up/Code/v.0.1_Project}"
GEOM_CONFIG="${GEOM_CONFIG:-configs/geometry/baseline_bwb_25.yaml}"

N_GEOMS="${N_GEOMS:-4}"
SEED="${SEED:-260601}"
CASE_TIMEOUT="${CASE_TIMEOUT:-90}"
PANEL_SPAN="${PANEL_SPAN:-4}"
PANEL_CHORD="${PANEL_CHORD:-8}"

ALPHA_VALUES="${ALPHA_VALUES:-0,4}"
CONTROL_VALUES="${CONTROL_VALUES:--5,0,5}"
VELOCITY_VALUES="${VELOCITY_VALUES:-28}"
ALTITUDE_VALUES="${ALTITUDE_VALUES:-1500}"
BETA_VALUES="${BETA_VALUES:-0}"

RUN_TAG="${RUN_TAG:-e2e_operator_bwb25_$(date +%Y%m%d_%H%M%S)}"
AVL_COMMAND="${AVL_COMMAND:-$(command -v avl || true)}"
if [[ -z "${AVL_COMMAND}" ]]; then AVL_COMMAND="avl"; fi

cd "$PROJECT_ROOT" || {
  echo "[FATAL] Project root not found: $PROJECT_ROOT"
  exit 2
}

mkdir -p data/e2e_operator_logs configs/ml/tuning data/processed/ml_runs data/processed/ml_tuning data/processed/ml_predictions data/processed/multifidelity
LOG="data/e2e_operator_logs/${RUN_TAG}.log"
SUMMARY="data/e2e_operator_logs/${RUN_TAG}_summary.tsv"
: > "$SUMMARY"

exec > >(tee -a "$LOG") 2>&1

FEATURES="c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg"
TARGETS="cl,cd,cm"

GEOM_DS="${RUN_TAG}_geom_n${N_GEOMS}"
GEOM_ROOT="data/datasets/${GEOM_DS}"

AERO_DS_NAME="${RUN_TAG}_aero_n${N_GEOMS}"
AERO_DS="data/datasets/${AERO_DS_NAME}"

ML_ROOT="data/processed/ml_runs/${RUN_TAG}"
TUNE_ROOT="data/processed/ml_tuning/${RUN_TAG}"
PRED_ROOT="data/processed/ml_predictions/${RUN_TAG}"
MF_ROOT="data/processed/multifidelity/${RUN_TAG}"
CANDIDATE_CSV="data/processed/${RUN_TAG}_candidate_pool.csv"

FORCED_DATASET=0
ALLOW_FORCED_FLAG=""
MODEL_PROMOTE_FORCED_FLAG=""

pass_count=0
fail_count=0
warn_count=0
skip_count=0

record() {
  local status="$1"
  local label="$2"
  local note="${3:-}"
  printf "%s\t%s\t%s\n" "$status" "$label" "$note" >> "$SUMMARY"
  case "$status" in
    PASS) pass_count=$((pass_count+1));;
    FAIL) fail_count=$((fail_count+1));;
    WARN) warn_count=$((warn_count+1));;
    SKIP) skip_count=$((skip_count+1));;
  esac
}

run_step() {
  local label="$1"
  shift
  echo ""
  echo "================================================================"
  echo "[STEP] $label"
  echo "[CMD]  $*"
  echo "================================================================"
  "$@"
  local rc=$?
  if [[ "$rc" -eq 0 ]]; then
    echo "[PASS] $label"
    record PASS "$label" ""
  else
    echo "[FAIL] $label rc=$rc"
    record FAIL "$label" "rc=$rc"
  fi
  return 0
}

run_shell() {
  local label="$1"
  shift
  echo ""
  echo "================================================================"
  echo "[STEP] $label"
  echo "[CMD]  bash -lc $*"
  echo "================================================================"
  bash -lc "$*"
  local rc=$?
  if [[ "$rc" -eq 0 ]]; then
    echo "[PASS] $label"
    record PASS "$label" ""
  else
    echo "[FAIL] $label rc=$rc"
    record FAIL "$label" "rc=$rc"
  fi
  return 0
}

skip_step() {
  local label="$1"
  local note="${2:-}"
  echo "[SKIP] $label $note"
  record SKIP "$label" "$note"
}

require_file() {
  local path="$1"
  local label="$2"
  if [[ -f "$path" ]]; then
    record PASS "$label" "$path"
    return 0
  fi
  echo "[MISSING] $label: $path"
  record FAIL "$label" "missing $path"
  return 1
}

require_dir() {
  local path="$1"
  local label="$2"
  if [[ -d "$path" ]]; then
    record PASS "$label" "$path"
    return 0
  fi
  echo "[MISSING] $label: $path"
  record FAIL "$label" "missing $path"
  return 1
}

has_ml_cmd() {
  aeris ml --help 2>/dev/null | grep -q "$1"
}

has_model() {
  python - "$1" <<'PY'
import sys
from aeris.ml.model_registry import list_model_types
raise SystemExit(0 if sys.argv[1] in set(list_model_types()) else 1)
PY
}

echo "================================================================"
echo "AERIS E2E OPERATOR CAMPAIGN — NON-FAIL-FAST"
echo "================================================================"
echo "Project root:        $PROJECT_ROOT"
echo "Geometry config:     $GEOM_CONFIG"
echo "Run tag:             $RUN_TAG"
echo "N_GEOMS:             $N_GEOMS"
echo "AVL command:         $AVL_COMMAND"
echo "Log:                 $LOG"
echo "Summary:             $SUMMARY"
echo "================================================================"

if [[ ! -f "$GEOM_CONFIG" ]]; then
  echo "[FATAL] Geometry config not found: $GEOM_CONFIG"
  record FAIL "geometry config exists" "missing $GEOM_CONFIG"
  exit 2
fi

# -----------------------------------------------------------------------------
# Phase 0 — tiny local repair for the known stale baseline test expectation.
# This does NOT hide failures; it fixes the obvious stale assertion after moving to baseline_bwb_25.
# -----------------------------------------------------------------------------
run_shell "repair stale baseline config paths in tests" "python - <<'PY'
from pathlib import Path

replacements = {
    'configs/geometry/wing_bwb.yaml': 'configs/geometry/baseline_bwb_25.yaml',
    'configs/geometry/baseline_bwb.yaml': 'configs/geometry/baseline_bwb_25.yaml',
    'baseline_bwb.yaml': 'baseline_bwb_25.yaml',
}

changed = []
for p in Path('tests').rglob('*.py'):
    text = p.read_text(encoding='utf-8')
    new = text
    for old, repl in replacements.items():
        new = new.replace(old, repl)
    if new != text:
        p.write_text(new, encoding='utf-8')
        changed.append(str(p))

print('changed:', changed)
PY"

run_shell "show remaining stale config refs in real tests" "grep -R --include='*.py' --line-number -E 'configs/geometry/(wing_bwb|baseline_bwb)\\.yaml|baseline_bwb\\.yaml' tests || true"

# -----------------------------------------------------------------------------
# Phase 1 — CLI and syntax. These are important but not allowed to block runtime tests.
# -----------------------------------------------------------------------------
run_step "aeris version" aeris version
run_step "aeris geometry help" aeris geometry --help
run_step "aeris dataset help" aeris dataset --help
run_step "aeris aero help" aeris aero --help
run_step "aeris ml help" aeris ml --help

PY_COMPILE_FILES=(
  src/aeris/cli.py
  src/aeris/commands/geometry.py
  src/aeris/commands/dataset.py
  src/aeris/commands/aero.py
  src/aeris/commands/ml.py
)
[[ -f src/aeris/ml/active_learning/suggest.py ]] && PY_COMPILE_FILES+=(src/aeris/ml/active_learning/suggest.py)
[[ -f src/aeris/ml/quality/audit.py ]] && PY_COMPILE_FILES+=(src/aeris/ml/quality/audit.py)
[[ -f src/aeris/ml/quality/confidence.py ]] && PY_COMPILE_FILES+=(src/aeris/ml/quality/confidence.py)
[[ -f src/aeris/ml/neural/sklearn_mlp.py ]] && PY_COMPILE_FILES+=(src/aeris/ml/neural/sklearn_mlp.py)

run_step "py_compile core surfaces" python -m py_compile "${PY_COMPILE_FILES[@]}"

# Run pytest, but do not block the operational E2E path.
TESTS=(tests/commands tests/ml)
[[ -d tests/dataset ]] && TESTS+=(tests/dataset)
[[ -d tests/aero ]] && TESTS+=(tests/aero)
run_step "pytest focused suite non-blocking" pytest -q "${TESTS[@]}"

# -----------------------------------------------------------------------------
# Phase 2 — geometry and geometry dataset.
# -----------------------------------------------------------------------------
run_step "pipeline smoke baseline25" aeris pipeline smoke -c "$GEOM_CONFIG"
run_step "single geometry generate baseline25" aeris geometry generate -c "$GEOM_CONFIG"

run_step "geometry dataset generate n=${N_GEOMS}" \
  aeris dataset generate \
  -c "$GEOM_CONFIG" \
  --n "$N_GEOMS" \
  --sampler lhs_v1 \
  --sampler-seed "$SEED" \
  --name "$GEOM_DS" \
  --no-save-plot \
  --build-aerosandbox \
  --run-qc \
  --qc-preset debug

if require_dir "$GEOM_ROOT" "geometry dataset root exists"; then
  run_step "geometry dataset inspect" aeris dataset inspect --dataset "$GEOM_ROOT"
  run_step "geometry dataset QC basic non-blocking" aeris dataset qc --dataset "$GEOM_ROOT" --profile basic
else
  skip_step "geometry dataset inspect/QC" "geometry dataset missing"
fi

# -----------------------------------------------------------------------------
# Phase 3 — single aero + control sweep.
# -----------------------------------------------------------------------------
run_step "single aero run with +5 deg control" \
  aeris aero run \
  --config "$GEOM_CONFIG" \
  --geometry-source native \
  --alpha 4 \
  --beta 0 \
  --velocity 28 \
  --altitude 1500 \
  --control-input-deg 5 \
  --solver aerosandbox_avl \
  --avl-command "$AVL_COMMAND" \
  --timeout-sec "$CASE_TIMEOUT" \
  --spanwise-resolution "$PANEL_SPAN" \
  --chordwise-resolution "$PANEL_CHORD" \
  --output-name "${RUN_TAG}_single_aero_ctrl5"

SINGLE_AERO_RUN="$(ls -td data/runs/*${RUN_TAG}_single_aero_ctrl5* 2>/dev/null | head -n 1 || true)"
if [[ -n "$SINGLE_AERO_RUN" && -d "$SINGLE_AERO_RUN" ]]; then
  run_step "single aero inspect" aeris aero inspect --run-dir "$SINGLE_AERO_RUN"
else
  skip_step "single aero inspect" "single aero run not found"
fi

run_step "aero sweep control -5/0/+5" \
  aeris aero sweep \
  --config "$GEOM_CONFIG" \
  --geometry-source native \
  --alpha-values "$ALPHA_VALUES" \
  --beta-values "$BETA_VALUES" \
  --velocity-values "$VELOCITY_VALUES" \
  --altitude-values "$ALTITUDE_VALUES" \
  --control-input-values="$CONTROL_VALUES" \
  --p-values 0 \
  --q-values 0 \
  --r-values 0 \
  --solver aerosandbox_avl \
  --avl-command "$AVL_COMMAND" \
  --timeout-sec "$CASE_TIMEOUT" \
  --spanwise-resolution "$PANEL_SPAN" \
  --chordwise-resolution "$PANEL_CHORD" \
  --output-name "${RUN_TAG}_control_sweep"

SWEEP_RUN="$(ls -td data/runs/*${RUN_TAG}_control_sweep* 2>/dev/null | head -n 1 || true)"
if [[ -n "$SWEEP_RUN" && -d "$SWEEP_RUN" ]]; then
  run_step "aero sweep inspect" aeris aero sweep-inspect --run-dir "$SWEEP_RUN"
  run_step "aero sweep case 0 inspect" aeris aero sweep-case-inspect --run-dir "$SWEEP_RUN" --case-index 0
else
  skip_step "sweep inspect" "sweep run not found"
fi

# -----------------------------------------------------------------------------
# Phase 4 — unified aero dataset, QC, curation, promotion.
# -----------------------------------------------------------------------------
run_step "unified aero dataset generate n=${N_GEOMS}" \
  aeris dataset aero-generate \
  -c "$GEOM_CONFIG" \
  --n "$N_GEOMS" \
  --sampler lhs_v1 \
  --sampler-seed "$SEED" \
  --name "$AERO_DS_NAME" \
  --no-save-plot \
  --build-aerosandbox \
  --alpha-values "$ALPHA_VALUES" \
  --beta-values "$BETA_VALUES" \
  --velocity-values "$VELOCITY_VALUES" \
  --altitude-values "$ALTITUDE_VALUES" \
  --control-input-values="$CONTROL_VALUES" \
  --p-values 0 \
  --q-values 0 \
  --r-values 0 \
  --solver aerosandbox_avl \
  --avl-command "$AVL_COMMAND" \
  --timeout-sec "$CASE_TIMEOUT" \
  --spanwise-resolution "$PANEL_SPAN" \
  --chordwise-resolution "$PANEL_CHORD" \
  --retain-aero-runs failures_only \
  --qc-preset debug

if require_dir "$AERO_DS" "aero dataset root exists"; then
  run_step "aero dataset inspect" aeris dataset inspect --dataset "$AERO_DS"
  run_step "aero dataset QC basic non-blocking" aeris dataset aero-qc --dataset "$AERO_DS" --profile basic
  run_step "aero dataset curate" aeris dataset curate-aero --dataset "$AERO_DS"

  if aeris dataset promote-aero --dataset "$AERO_DS"; then
    echo "[PASS] strict dataset promotion"
    record PASS "strict dataset promotion" ""
  else
    echo "[WARN] strict dataset promotion failed; forcing only to exercise ML gates."
    record WARN "strict dataset promotion" "failed; forcing for smoke"
    run_step "forced dataset promotion smoke-only" aeris dataset promote-aero --dataset "$AERO_DS" --force
    FORCED_DATASET=1
  fi

  if [[ "$FORCED_DATASET" == "1" ]]; then
    ALLOW_FORCED_FLAG="--allow-forced"
    MODEL_PROMOTE_FORCED_FLAG="--allow-forced-dataset"
  fi

  run_step "require promoted aero dataset" aeris dataset require-promoted-aero --dataset "$AERO_DS" $ALLOW_FORCED_FLAG
  run_step "training-data promoted dataset" aeris dataset training-data --dataset "$AERO_DS" --features "$FEATURES" --targets "$TARGETS" $ALLOW_FORCED_FLAG
  run_step "split training data grouped" aeris dataset split-training-data --dataset "$AERO_DS" --features "$FEATURES" --targets "$TARGETS" --method grouped --train-fraction 0.5 --val-fraction 0.25 --test-fraction 0.25 --random-seed 123 $ALLOW_FORCED_FLAG
else
  skip_step "dataset QC/curate/promote/ML" "aero dataset missing"
fi

# -----------------------------------------------------------------------------
# Phase 5 — ML only if curated/promoted file exists.
# -----------------------------------------------------------------------------
if [[ -f "$AERO_DS/curated_aero_dataset.csv" && -f "$AERO_DS/promotion_manifest.json" ]]; then
  run_step "ML feature presets" aeris ml feature-presets
  run_step "ML validate schema" aeris ml validate-schema --dataset "$AERO_DS" --feature-preset bwb_control --targets "$TARGETS" $ALLOW_FORCED_FLAG

  cat > "configs/ml/tuning/${RUN_TAG}_compare_params.json" <<'JSON'
{
  "linear_regression": {},
  "ridge": {"alpha": 1.0},
  "elastic_net": {"alpha": 0.001, "l1_ratio": 0.5, "max_iter": 5000},
  "random_forest": {"n_estimators": 20, "max_depth": 5, "n_jobs": -1},
  "extra_trees": {"n_estimators": 20, "max_depth": 5, "n_jobs": -1},
  "gradient_boosting": {"n_estimators": 30, "learning_rate": 0.05, "max_depth": 2},
  "hist_gradient_boosting": {"max_iter": 30, "learning_rate": 0.05, "max_depth": 3},
  "neural_mlp": {"hidden_layer_sizes": [16, 16], "activation": "relu", "solver": "adam", "alpha": 0.0001, "learning_rate_init": 0.001, "max_iter": 150, "early_stopping": false},
  "neural_mlp_ensemble": {"n_members": 3, "hidden_layer_sizes": [16], "activation": "relu", "solver": "adam", "alpha": 0.0001, "learning_rate_init": 0.001, "max_iter": 120, "early_stopping": false}
}
JSON

  MODEL_TYPES="$(python - <<'PY'
from aeris.ml.model_registry import list_model_types
print(','.join(list_model_types()))
PY
)"
  echo "[INFO] Registered model types: $MODEL_TYPES"
  IFS=',' read -r -a MODEL_ARRAY <<< "$MODEL_TYPES"

  for MODEL in "${MODEL_ARRAY[@]}"; do
    PARAM_FILE="configs/ml/tuning/${RUN_TAG}_${MODEL}_params.json"
    python - "$MODEL" "configs/ml/tuning/${RUN_TAG}_compare_params.json" "$PARAM_FILE" <<'PY'
import json, sys
model, source, out = sys.argv[1], sys.argv[2], sys.argv[3]
all_params = json.load(open(source))
params = all_params.get(model, {})
with open(out, "w") as f:
    json.dump(params, f, indent=2)
print(out)
PY
    run_step "ML train ${MODEL}" \
      aeris ml train \
      --dataset "$AERO_DS" \
      --feature-preset bwb_control \
      --targets "$TARGETS" \
      --model-type "$MODEL" \
      --split-method grouped \
      --train-fraction 0.5 \
      --val-fraction 0.25 \
      --test-fraction 0.25 \
      --random-seed 123 \
      --model-params-json "$PARAM_FILE" \
      --output-dir "$ML_ROOT/${MODEL}" \
      $ALLOW_FORCED_FLAG
    if [[ -d "$ML_ROOT/${MODEL}" ]]; then
      run_step "ML inspect ${MODEL}" aeris ml inspect-model --model-run-dir "$ML_ROOT/${MODEL}"
    fi
  done

  run_step "ML compare all registered models" \
    aeris ml compare \
    --dataset "$AERO_DS" \
    --feature-preset bwb_control \
    --targets "$TARGETS" \
    --models "$MODEL_TYPES" \
    --split-method grouped \
    --train-fraction 0.5 \
    --val-fraction 0.25 \
    --test-fraction 0.25 \
    --random-seed 123 \
    --model-params-json "configs/ml/tuning/${RUN_TAG}_compare_params.json" \
    --output-dir "$ML_ROOT/compare_all_models" \
    $ALLOW_FORCED_FLAG

  cat > "configs/ml/tuning/${RUN_TAG}_ridge_space.json" <<'JSON'
{
  "search": {"backend": "aeris", "strategy": "grid", "max_trials": 2},
  "params": {"alpha": [0.1, 1.0], "fit_intercept": [true]}
}
JSON
  run_step "ML tune ridge grid smoke" \
    aeris ml tune \
    --backend aeris \
    --dataset "$AERO_DS" \
    --feature-preset bwb_control \
    --targets "$TARGETS" \
    --model-type ridge \
    --param-space-json "configs/ml/tuning/${RUN_TAG}_ridge_space.json" \
    --max-trials 2 \
    --split-method grouped \
    --train-fraction 0.5 \
    --val-fraction 0.25 \
    --test-fraction 0.25 \
    --output-dir "$TUNE_ROOT/ridge_aeris" \
    $ALLOW_FORCED_FLAG

  if has_model neural_mlp; then
    cat > "configs/ml/tuning/${RUN_TAG}_neural_mlp_optuna_space.json" <<'JSON'
{
  "search": {"backend": "optuna", "sampler": "random", "n_trials": 2},
  "params": {
    "hidden_layer_sizes": [[16], [16, 16]],
    "activation": ["relu"],
    "solver": ["adam"],
    "alpha": {"type": "float", "low": 1e-5, "high": 1e-3, "log": true},
    "learning_rate_init": {"type": "float", "low": 1e-4, "high": 1e-2, "log": true},
    "max_iter": [120],
    "early_stopping": [false]
  }
}
JSON
    run_step "ML tune neural_mlp optuna smoke" \
      aeris ml tune \
      --backend optuna \
      --dataset "$AERO_DS" \
      --feature-preset bwb_control \
      --targets "$TARGETS" \
      --model-type neural_mlp \
      --param-space-json "configs/ml/tuning/${RUN_TAG}_neural_mlp_optuna_space.json" \
      --n-trials 2 \
      --optuna-sampler random \
      --split-method grouped \
      --train-fraction 0.5 \
      --val-fraction 0.25 \
      --test-fraction 0.25 \
      --output-dir "$TUNE_ROOT/neural_mlp_optuna" \
      $ALLOW_FORCED_FLAG

    if [[ -d "$TUNE_ROOT/ridge_aeris" && -d "$TUNE_ROOT/neural_mlp_optuna" ]]; then
      run_step "ML compare tuning runs" aeris ml compare-tuning-runs --runs "$TUNE_ROOT/ridge_aeris,$TUNE_ROOT/neural_mlp_optuna" --output-dir "$TUNE_ROOT/compare_tuning_runs"
    fi
  fi

  run_step "ML compare seeds smoke" \
    aeris ml compare-seeds \
    --dataset "$AERO_DS" \
    --feature-preset bwb_control \
    --targets "$TARGETS" \
    --models random_forest,extra_trees \
    --seeds 101,202 \
    --split-method grouped \
    --train-fraction 0.5 \
    --val-fraction 0.25 \
    --test-fraction 0.25 \
    --model-params-json "configs/ml/tuning/${RUN_TAG}_compare_params.json" \
    --output-dir "$ML_ROOT/compare_seeds" \
    $ALLOW_FORCED_FLAG

  CHOSEN_MODEL="extra_trees"
  if [[ -d "$ML_ROOT/neural_mlp_ensemble" ]]; then CHOSEN_MODEL="neural_mlp_ensemble"; fi
  CHOSEN_RUN="$ML_ROOT/${CHOSEN_MODEL}"
  cp "$AERO_DS/curated_aero_dataset.csv" "$CANDIDATE_CSV"

  if [[ -d "$CHOSEN_RUN" ]]; then
    run_step "ML promote chosen model ${CHOSEN_MODEL}" \
      aeris ml promote-model \
      --model-run-dir "$CHOSEN_RUN" \
      --max-test-rmse-mean 999 \
      --min-test-r2-mean -999 \
      --no-require-diagnostics \
      $MODEL_PROMOTE_FORCED_FLAG \
      --notes "E2E operator smoke only: ${RUN_TAG}. Thresholds intentionally loose."

    run_step "ML require promoted model" aeris ml require-promoted-model --model-run-dir "$CHOSEN_RUN"

    run_step "ML check inference inputs" \
      aeris ml check-inference-inputs \
      --model-run-dir "$CHOSEN_RUN" \
      --input-csv "$CANDIDATE_CSV" \
      --output-dir "$PRED_ROOT/inference_guard" \
      --require-promoted-model

    run_step "ML predict guarded" \
      aeris ml predict \
      --model-run-dir "$CHOSEN_RUN" \
      --input-csv "$CANDIDATE_CSV" \
      --output-dir "$PRED_ROOT/predict" \
      --require-promoted-model \
      --enforce-envelope

    if has_ml_cmd "audit-model"; then
      run_step "ML audit model" aeris ml audit-model --model-run-dir "$CHOSEN_RUN" --output-dir "$PRED_ROOT/audit"
    fi

    if has_ml_cmd "predict-with-confidence"; then
      run_step "ML predict with confidence" \
        aeris ml predict-with-confidence \
        --model-run-dir "$CHOSEN_RUN" \
        --input-csv "$CANDIDATE_CSV" \
        --output-dir "$PRED_ROOT/predict_with_confidence"
    fi

    if has_ml_cmd "suggest-samples"; then
      run_step "ML active-learning suggest samples" \
        aeris ml suggest-samples \
        --model-run-dir "$CHOSEN_RUN" \
        --candidate-csv "$CANDIDATE_CSV" \
        --output-dir "$PRED_ROOT/active_learning" \
        --top-n 5 \
        --objective-column pred__cl \
        --objective-mode maximize
    fi
  else
    skip_step "model promotion / inference" "chosen model run missing"
  fi

else
  skip_step "ML phases" "curated/promoted aero dataset missing"
fi

# -----------------------------------------------------------------------------
# Phase 6 — multifidelity smoke if LF aero dataset exists.
# -----------------------------------------------------------------------------
if [[ -f "$AERO_DS/aero_dataset.csv" ]]; then
  run_shell "create synthetic LF/HF CSVs for multifidelity smoke" "python - '$AERO_DS/aero_dataset.csv' '$MF_ROOT/lf_smoke.csv' '$MF_ROOT/hf_smoke.csv' <<'PY'
import sys
from pathlib import Path
import pandas as pd
src, lf_out, hf_out = map(Path, sys.argv[1:4])
lf = pd.read_csv(src)
lf_out.parent.mkdir(parents=True, exist_ok=True)
hf = lf.copy()
hf['cl'] = lf['cl'].astype(float) + 0.010 + 0.001 * lf.get('alpha_deg', 0).astype(float)
hf['cd'] = lf['cd'].astype(float) * 1.030 + 0.0005
hf['cm'] = lf['cm'].astype(float) - 0.005 + 0.0002 * lf.get('control_input_deg', 0).astype(float)
lf.to_csv(lf_out, index=False)
hf.to_csv(hf_out, index=False)
print(lf_out)
print(hf_out)
PY"

  PAIR_KEYS="$(python - "$MF_ROOT/lf_smoke.csv" <<'PY'
import sys, pandas as pd
cols = set(pd.read_csv(sys.argv[1], nrows=1).columns)
candidates = ["geometry_id", "alpha_deg", "beta_deg", "velocity_mps", "altitude_m", "p_rad_s", "q_rad_s", "r_rad_s", "control_input_deg"]
print(",".join([c for c in candidates if c in cols]))
PY
)"
  echo "[INFO] Multifidelity pair keys: $PAIR_KEYS"

  run_step "MF build delta dataset" \
    aeris ml build-delta-dataset \
    --lf-csv "$MF_ROOT/lf_smoke.csv" \
    --hf-csv "$MF_ROOT/hf_smoke.csv" \
    --pair-keys "$PAIR_KEYS" \
    --targets "$TARGETS" \
    --output-dir "$MF_ROOT/delta_dataset"

  if [[ -f "$MF_ROOT/delta_dataset/delta_dataset.csv" ]]; then
    EXTRA_PARAMS="configs/ml/tuning/${RUN_TAG}_extra_trees_params.json"
    if [[ ! -f "$EXTRA_PARAMS" ]]; then
      echo '{"n_estimators": 20, "max_depth": 5, "n_jobs": -1}' > "$EXTRA_PARAMS"
    fi

    run_step "MF train delta model" \
      aeris ml train-delta-model \
      --delta-dataset "$MF_ROOT/delta_dataset" \
      --features "c1_m,b_total_m,sw1_deg,alpha_deg,velocity_mps,altitude_m,control_input_deg,lf__cl,lf__cd,lf__cm" \
      --base-targets "$TARGETS" \
      --model-type extra_trees \
      --split-method grouped \
      --train-fraction 0.5 \
      --val-fraction 0.25 \
      --test-fraction 0.25 \
      --model-params-json "$EXTRA_PARAMS" \
      --output-dir "$MF_ROOT/delta_model"

    if [[ -d "$MF_ROOT/delta_model" ]]; then
      run_step "MF predict delta model" \
        aeris ml predict-delta-model \
        --model-run-dir "$MF_ROOT/delta_model" \
        --input-csv "$MF_ROOT/delta_dataset/delta_dataset.csv" \
        --output-dir "$MF_ROOT/delta_predictions"

      run_step "MF evaluate delta model" \
        aeris ml evaluate-delta-model \
        --model-run-dir "$MF_ROOT/delta_model" \
        --output-dir "$MF_ROOT/delta_evaluation"
    fi
  fi
else
  skip_step "multifidelity smoke" "aero_dataset.csv missing"
fi

# -----------------------------------------------------------------------------
# Final summary.
# -----------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "AERIS E2E OPERATOR CAMPAIGN COMPLETE"
echo "================================================================"
echo "Run tag:             $RUN_TAG"
echo "Geometry config:     $GEOM_CONFIG"
echo "Log:                 $LOG"
echo "Summary TSV:         $SUMMARY"
echo "PASS:                $pass_count"
echo "FAIL:                $fail_count"
echo "WARN:                $warn_count"
echo "SKIP:                $skip_count"
echo "Geometry dataset:    $GEOM_ROOT"
echo "Aero dataset:        $AERO_DS"
echo "ML root:             $ML_ROOT"
echo "Prediction root:     $PRED_ROOT"
echo "Multifidelity root:  $MF_ROOT"
echo "Forced dataset:      $FORCED_DATASET"
echo ""
echo "Failures did not stop the campaign. Read the TSV summary first:"
echo "  column -t -s \$'\\t' $SUMMARY"
echo ""
echo "If FORCED_DATASET=1, this was workflow coverage, not a trusted engineering dataset."
echo "================================================================"
