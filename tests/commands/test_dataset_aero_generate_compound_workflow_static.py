from __future__ import annotations

from pathlib import Path


def test_aero_generate_records_compound_workflow_stages_in_order() -> None:
    text = Path("src/aeris/commands/dataset.py").read_text(encoding="utf-8")

    geometry_idx = text.find('stage="geometry_dataset"')
    sweep_idx = text.find('stage="aero_sweep"')
    dataset_idx = text.find('stage="aero_dataset"')

    assert geometry_idx != -1
    assert sweep_idx != -1
    assert dataset_idx != -1
    assert geometry_idx < sweep_idx < dataset_idx
    assert 'stage="aero_dataset_sweep"' not in text

    assert '"compound_command": True' in text
    assert '"compound_stage": "geometry_dataset"' in text
    assert '"compound_stage": "aero_sweep"' in text
    assert '"compound_stage": "aero_dataset"' in text
