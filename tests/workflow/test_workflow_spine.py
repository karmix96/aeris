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
    assert updated.status["next_required_stage"]["name"] == "aero_sweep"
    stage_status = updated.paths.stages_dir / "geometry_dataset" / "stage_status.json"
    assert stage_status.exists()

    payload = inspect_workflow(updated.paths.root, stage="geometry_dataset")
    assert payload["stage"]["status"] == "complete"
    assert "data/datasets/demo_geometry" in payload["stage"]["artifacts"]
    assert get_next_required_stage(updated.paths.root)["name"] == "aero_sweep"


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


def _complete_required_stages_until(workflow_dir: Path, until_stage: str, artifact_root: Path | None = None) -> None:
    from aeris.workflow import DEFAULT_STAGE_DEFINITIONS

    for stage_def in DEFAULT_STAGE_DEFINITIONS:
        name = stage_def["name"]
        if name == until_stage:
            return
        if not stage_def.get("required", True):
            continue
        artifacts: list[str] | None = None
        if artifact_root is not None:
            artifact = artifact_root / f"{name}.txt"
            if name == "promotion":
                artifact = artifact_root / "promotion_manifest.json"
                artifact.write_text(
                    json.dumps({
                        "promotion_ready_at_time_of_promotion": True,
                        "promotion_forced": False,
                        "promotion_blockers": [],
                    }),
                    encoding="utf-8",
                )
            else:
                artifact.write_text(name, encoding="utf-8")
            artifacts = [str(artifact)]
        record_stage(workflow_dir=workflow_dir, stage=name, status="complete", artifacts=artifacts)


def test_validate_workflow_reports_missing_complete_stage_artifact(tmp_path: Path) -> None:
    from aeris.workflow import validate_workflow

    result = init_workflow(name="demo", output_dir=tmp_path / "wf")
    missing = tmp_path / "does_not_exist" / "artifact.json"
    record_stage(
        workflow_dir=result.paths.root,
        stage="geometry_dataset",
        status="complete",
        artifacts=[str(missing)],
    )

    validation = validate_workflow(result.paths.root)

    assert validation.report_path is not None
    assert validation.report_path.exists()
    assert validation.report["health"] == "inconsistent"
    assert validation.report["counts"]["missing_artifacts"] == 1
    assert "geometry_dataset" in validation.report["blockers"][0]


def test_validate_workflow_checks_model_promotion_manifest(tmp_path: Path) -> None:
    from aeris.workflow import validate_workflow

    result = init_workflow(name="demo", output_dir=tmp_path / "wf")
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    _complete_required_stages_until(result.paths.root, "model_promotion", artifact_root=artifact_root)

    model_dir = artifact_root / "model"
    model_dir.mkdir()
    manifest = model_dir / "model_promotion_manifest.json"
    manifest.write_text(
        json.dumps({"status": "approved", "promotion_ready_at_time_of_promotion": True, "blockers": []}),
        encoding="utf-8",
    )
    record_stage(
        workflow_dir=result.paths.root,
        stage="model_promotion",
        status="complete",
        artifacts=[str(manifest)],
    )

    validation = validate_workflow(result.paths.root)

    assert validation.report["health"] == "incomplete"
    assert validation.report["counts"]["blockers"] == 0
    trust_checks = validation.report["trust_checks"]
    assert any(item["stage"] == "model_promotion" and item["passed"] is True for item in trust_checks)
    assert validation.report["next_required_stage"]["name"] == "inference_guard"


def test_validate_workflow_detects_stage_order_gap(tmp_path: Path) -> None:
    from aeris.workflow import validate_workflow

    result = init_workflow(name="demo", output_dir=tmp_path / "wf")
    record_stage(workflow_dir=result.paths.root, stage="ml_training", status="complete")

    validation = validate_workflow(result.paths.root, write_report=False)

    assert validation.report["health"] == "incomplete"
    assert validation.report["stage_order_issues"]
    assert validation.report["stage_order_issues"][0]["first_incomplete_required_stage"] == "geometry_dataset"
