from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from aeris.cli import app

runner = CliRunner()


def _write_promotable_cst_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    curated = root / 'curated_airfoil_dataset.csv'
    curated.write_text('airfoil_id,alpha_deg,cl,cd,cm\na,0,0.1,0.01,0.0\n', encoding='utf-8')
    (root / 'curation_report.json').write_text(json.dumps({
        'schema_version': 'airfoil_curation_v1',
        'dataset_root': str(root),
        'kept_rows': 1,
        'rejected_rows': 0,
        'kept_airfoils': 1,
        'rejected_airfoils': 0,
        'rejection_reason_counts': {},
        'qc_passed': True,
        'promotion_ready': True,
        'promotion_blockers': [],
        'curated_airfoil_dataset_csv': str(curated),
        'rejected_airfoil_rows_csv': str(root / 'rejected_airfoil_rows.csv'),
    }), encoding='utf-8')
    (root / 'airfoil_dataset_manifest.json').write_text(json.dumps({
        'schema_version': 'airfoil_dataset_v1',
        'dataset_name': root.name,
        'solver_id': 'xfoil_subprocess',
        'total_rows': 1,
        'converged_rows': 1,
        'convergence_rate': 1.0,
        'n_airfoils': 1,
        'airfoil_source_schema': {
            'has_cst_features': True,
            'generator_ids': ['cst_airfoil_v1'],
            'cst_feature_columns': ['cst_u0', 'cst_l0'],
        },
    }), encoding='utf-8')


def test_airfoil_promote_helper_uses_cst_feature_preset_for_cst_dataset(tmp_path: Path) -> None:
    ds = tmp_path / 'cst_ds'
    _write_promotable_cst_dataset(ds)

    result = runner.invoke(app, ['airfoil', 'dataset', 'promote', '--dataset', str(ds)])

    assert result.exit_code == 0, result.output
    assert '{feature_preset_hint}' not in result.output
    assert '--feature-preset airfoil_cst_xfoil_v1' in result.output
    assert '--feature-set airfoil_xfoil_v1' not in result.output
    assert '--feature-preset airfoil_xfoil_v1 --model-types' not in result.output


def test_airfoil_command_source_has_no_literal_feature_preset_placeholder() -> None:
    text = Path('src/aeris/commands/airfoil.py').read_text(encoding='utf-8')
    assert '--feature-preset {feature_preset_hint}' not in text or 'f"' in text or "f'" in text
    assert '--feature-set airfoil_xfoil_v1' not in text
