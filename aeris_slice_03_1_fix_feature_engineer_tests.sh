#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

TEST_MAT="tests/ml/test_feature_materialization.py"
TEST_CLI="tests/commands/test_ml_feature_engineer_cli.py"

if [[ ! -f "$TEST_MAT" ]]; then
  echo "[error] missing $TEST_MAT" >&2
  exit 1
fi
if [[ ! -f "$TEST_CLI" ]]; then
  echo "[error] missing $TEST_CLI" >&2
  exit 1
fi

python - <<'PY'
from pathlib import Path

# 1) The implementation returns the more precise validation code
#    missing_feature_set_source_columns. Update the test expectation.
path = Path("tests/ml/test_feature_materialization.py")
text = path.read_text()
old = 'with pytest.raises(FeatureMaterializationError, match="missing_source_columns"):'
new = 'with pytest.raises(FeatureMaterializationError, match="missing_feature_set_source_columns"):'
if old not in text and new not in text:
    raise SystemExit("Could not find expected pytest.raises line in test_feature_materialization.py")
text = text.replace(old, new)
path.write_text(text)
print("[ok] updated materialization failure regex to the precise validation code")

# 2) Typer/Rich command errors may be emitted on stderr, not stdout.
#    Result.output is the stable CliRunner combined stream to assert against.
path = Path("tests/commands/test_ml_feature_engineer_cli.py")
text = path.read_text()
old = 'assert "Unknown feature set" in result.stdout'
new = 'assert "Unknown feature set" in result.output'
if old not in text and new not in text:
    raise SystemExit("Could not find expected stdout assertion in test_ml_feature_engineer_cli.py")
text = text.replace(old, new)
path.write_text(text)
print("[ok] updated CLI error assertion to use result.output")
PY

python -m compileall -q tests/ml/test_feature_materialization.py tests/commands/test_ml_feature_engineer_cli.py

echo
cat <<'EOF'
Run now:
  pytest -q tests/ml/test_feature_materialization.py tests/commands/test_ml_feature_engineer_cli.py tests/ml/test_feature_sets.py tests/commands/test_ml_feature_sets_cli.py tests/commands/test_ml_cli.py
  pytest -q tests/ml tests/commands/test_ml*.py
EOF
