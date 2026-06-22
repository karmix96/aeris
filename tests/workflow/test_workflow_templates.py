from __future__ import annotations

import json

from aeris.workflow.templates import (
    get_workflow_template,
    init_workflow_from_template,
    list_workflow_templates,
)


def test_list_workflow_templates_contains_expected_names() -> None:
    names = {item["name"] for item in list_workflow_templates()}
    assert {"canary", "paper_1", "production", "multifidelity", "active_learning"} <= names


def test_get_workflow_template_aliases() -> None:
    assert get_workflow_template("active-learning")["name"] == "active_learning"
    assert get_workflow_template("multi-fidelity")["name"] == "multifidelity"


def test_init_workflow_from_canary_template_writes_template_artifacts(tmp_path) -> None:
    result = init_workflow_from_template(
        template_name="canary",
        name="demo_canary",
        output_dir=tmp_path / "wf",
    )

    assert result.paths.manifest_path.exists()
    assert result.paths.status_path.exists()
    assert (result.paths.root / "workflow_template.json").exists()
    assert result.manifest["template"]["name"] == "canary"
    assert result.status["template"]["name"] == "canary"
    assert result.status["next_required_stage"]["name"] == "geometry_dataset"

    template_payload = json.loads((result.paths.root / "workflow_template.json").read_text())
    assert template_payload["name"] == "canary"


def test_paper_1_template_includes_static_airworthiness_stages() -> None:
    template = get_workflow_template("paper1")

    assert template["name"] == "paper_1"
    stages = template["required_stages"]

    assert "dynamics_batch_labels" in stages
    assert "flyability_ml_dataset" in stages
    assert stages.index("promotion") < stages.index("dynamics_batch_labels")
    assert stages.index("flyability_ml_dataset") < stages.index("ml_eda")
