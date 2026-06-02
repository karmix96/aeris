#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

python - <<'PY'
from __future__ import annotations
from pathlib import Path

path = Path('src/aeris/ml/compare_hardening.py')
if not path.exists():
    raise SystemExit('[error] Missing src/aeris/ml/compare_hardening.py')
text = path.read_text()

if 'def compare_models_across_seeds' not in text:
    raise SystemExit('[error] compare_models_across_seeds not found')

start = text.index('def compare_models_across_seeds')
try:
    end = text.index('\ndef compare_tuning_runs', start)
except ValueError:
    end = len(text)
block = text[start:end]

# Ensure the function accepts feature_set_name.
header_end = block.index(') -> dict[str, Any]:')
header = block[:header_end]
if 'feature_set_name: str | None = None' not in header:
    marker = '    output_dir: Path | None = None,'
    if marker not in block[:header_end]:
        raise SystemExit('[error] Could not find output_dir parameter marker in compare_models_across_seeds')
    block = block.replace(
        marker,
        marker + '\n    feature_set_name: str | None = None,',
        1,
    )

# Ensure seed-level compare_models calls receive the feature-set provenance.
if 'feature_set_name=feature_set_name' not in block:
    marker = '            output_dir=seed_output_dir,\n        )'
    if marker not in block:
        raise SystemExit('[error] Could not find compare_models call marker in compare_models_across_seeds')
    block = block.replace(
        marker,
        '            output_dir=seed_output_dir,\n            feature_set_name=feature_set_name,\n        )',
        1,
    )

# Ensure top-level compare-seeds summary records the selected feature set.
# Keep this inside the compare_models_across_seeds block only.
if '"feature_set_name": feature_set_name' not in block:
    candidates = [
        '        "target_columns": list(target_columns),\n        "model_types": list(models),',
        '        "target_columns": list(target_columns),\n        "models": list(models),',
        '        "feature_columns": list(feature_columns),\n        "target_columns": list(target_columns),',
    ]
    patched = False
    for marker in candidates:
        if marker in block:
            if marker.endswith('"model_types": list(models),') or marker.endswith('"models": list(models),'):
                replacement = marker.replace(
                    '        "model_types": list(models),' if 'model_types' in marker else '        "models": list(models),',
                    '        "feature_set_name": feature_set_name,\n' +
                    ('        "model_types": list(models),' if 'model_types' in marker else '        "models": list(models),')
                )
            else:
                replacement = '        "feature_columns": list(feature_columns),\n        "target_columns": list(target_columns),\n        "feature_set_name": feature_set_name,'
            block = block.replace(marker, replacement, 1)
            patched = True
            break
    if not patched:
        raise SystemExit('[error] Could not find summary dictionary marker for feature_set_name insertion')

text = text[:start] + block + text[end:]
path.write_text(text)
print('[ok] patched compare-seeds feature_set_name provenance in src/aeris/ml/compare_hardening.py')
PY

# Patch command test if the Slice 4 CLI test file exists and does not check compare-seeds provenance.
python - <<'PY'
from __future__ import annotations
from pathlib import Path

path = Path('tests/commands/test_ml_feature_set_training_cli.py')
if not path.exists():
    print('[info] tests/commands/test_ml_feature_set_training_cli.py not found; skipping test patch')
    raise SystemExit(0)
text = path.read_text()

if 'test_ml_compare_seeds_cli_records_feature_set' in text:
    print('[ok] compare-seeds CLI provenance test already exists')
    raise SystemExit(0)

helper_needed = 'import json' not in text.split('\n', 10)[:10]
if helper_needed:
    # Insert import near top after future import if possible.
    text = text.replace('from __future__ import annotations\n\n', 'from __future__ import annotations\n\nimport json\n', 1)

append = r'''


def test_ml_compare_seeds_cli_records_feature_set(tmp_path: Path) -> None:
    dataset = _build_dataset(tmp_path)
    output_dir = tmp_path / "compare_seeds_feature_set_cli"

    result = runner.invoke(
        app,
        [
            "ml",
            "compare-seeds",
            "--dataset",
            str(dataset),
            "--feature-set",
            "bwb_control_raw",
            "--targets",
            "cl,cd,cm",
            "--models",
            "linear_regression,ridge",
            "--seeds",
            "101,202",
            "--split-method",
            "grouped",
            "--group-column",
            "geometry_id",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    summary = json.loads((output_dir / "comparison_seed_stability_summary.json").read_text())
    assert summary["feature_set_name"] == "bwb_control_raw"
    assert summary["feature_columns"] == [
        "c1_m",
        "b_total_m",
        "sw1_deg",
        "alpha_deg",
        "velocity_mps",
        "altitude_m",
        "control_input_deg",
    ]
'''
text = text.rstrip() + append + '\n'
path.write_text(text)
print('[ok] added compare-seeds feature-set provenance CLI test')
PY

python -m py_compile src/aeris/ml/compare_hardening.py

echo
cat <<'TXT'
Run now:
  pytest -q tests/commands/test_ml_feature_set_training_cli.py tests/ml/test_feature_set_training_integration.py
  pytest -q tests/ml tests/commands/test_ml*.py

Then repeat the compare-seeds CLI smoke and inspect comparison_seed_stability_summary.json.
TXT
