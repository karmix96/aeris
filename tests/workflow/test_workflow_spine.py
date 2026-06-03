from __future__ import annotations

import json
from pathlib import Path

from aeris.workflow import get_next_required_stage, init_workflow, inspect_workflow, record_stage


def test_init_workflow_writes_required_files(tmp_path: Path) -> None:
    result = init_workflow(name="demo", output_dir=tmp_path / "wf")

    assert result.paths.manifest_path.exists()
    assert result.paths.status_path.exists()
    assert result.paths.events_path.exists()
    assert result.status["workflow_status"] == "initialized"
    assert result.status["next_required_stage"]["name"] == "geometry_dataset"

    manifest = json.loads(result.paths.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stage_policy"]["workflow_records_state_only"] is True


def test_record_stage_updates_next_required_stage_and_stage_file(tmp_path: Path) -> None:
    result = init_workflow(name="demo", output_dir=tmp_path / "wf")

    updated = record_stage(
        workflow_dir=result.paths.root,
        stage="geometry_dataset",
        status="complete",
        inputs=["configs/geometry/bwb_training_v1.yaml"],
        artifacts=["data/datasets/demo_geometry"],
        notes="geometry canary passed",
    )

    assert updated.status["workflow_status"] == "in_progress"
    assert updated.status["next_required_stage"]["name"] == "aero_dataset"
    stage_status = updated.paths.stages_dir / "geometry_dataset" / "stage_status.json"
    assert stage_status.exists()

    payload = inspect_workflow(updated.paths.root, stage="geometry_dataset")
    assert payload["stage"]["status"] == "complete"
    assert "data/datasets/demo_geometry" in payload["stage"]["artifacts"]
    assert get_next_required_stage(updated.paths.root)["name"] == "aero_dataset"


def test_record_blocked_stage_marks_workflow_blocked(tmp_path: Path) -> None:
    result = init_workflow(name="demo", output_dir=tmp_path / "wf")

    updated = record_stage(
        workflow_dir=result.paths.root,
        stage="aero_dataset",
        status="blocked",
        blockers=["AVL not available on PATH"],
    )

    assert updated.status["workflow_status"] == "blocked"
    assert updated.status["next_required_stage"]["name"] == "geometry_dataset"
