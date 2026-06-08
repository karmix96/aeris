from __future__ import annotations

from pathlib import Path

APP = Path("src/aeris/gui/app.py")


def test_gui_dynamics_exposes_batch_labels_and_flyability_ml_dataset_tabs() -> None:
    text = APP.read_text(encoding="utf-8")
    assert "⑥ Batch Labels" in text
    assert "⑦ Flyability ML Dataset" in text
    assert '"dynamics", "batch-labels"' in text
    assert '"dynamics", "build-ml-dataset"' in text
    assert "dynamics_batch_labels" in text
    assert "flyability_ml_dataset" in text
    assert "flyability_ml_dataset_report.json" in text
