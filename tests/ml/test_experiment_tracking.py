from __future__ import annotations

import json
from pathlib import Path

from aeris.ml.experiment_tracking import build_experiment_tracker


def test_experiment_tracker_no_backends_writes_manifest(tmp_path: Path) -> None:
    tracker = build_experiment_tracker(
        output_dir=tmp_path / "run",
        backends=[],
        experiment_name="aeris_test",
        run_name="smoke",
        params={"model_type": "neural_mlp_live", "targets": ["a", "b"]},
    )
    tracker.log_epoch({"epoch": 1, "train_loss": 1.25, "bad": "not numeric"})
    state = tracker.close()

    manifest = tmp_path / "run" / "tracking" / "experiment_tracking_manifest.json"
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["backends_requested"] == []
    assert data["backends_active"] == []
    assert state.tracking_dir is not None


def test_experiment_tracker_missing_optional_backend_does_not_fail(tmp_path: Path) -> None:
    tracker = build_experiment_tracker(
        output_dir=tmp_path / "run",
        backends=["definitely_missing_backend"],
        experiment_name="aeris_test",
        run_name="smoke",
    )
    tracker.log_epoch({"epoch": 1, "train_loss": 1.0})
    tracker.close()

    manifest = tmp_path / "run" / "tracking" / "experiment_tracking_manifest.json"
    assert manifest.exists()
