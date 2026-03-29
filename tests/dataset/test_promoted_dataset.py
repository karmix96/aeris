from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aeris.dataset.promoted_dataset import (
    load_promoted_aero_dataset,
    require_promoted_aero_dataset,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_curated_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "geometry_id": "geom_00001",
                "cl": 0.5,
                "cd": 0.03,
                "cm": -0.02,
                "promotion_ready": True,
            }
        ]
    ).to_csv(path, index=False)


def test_require_promoted_aero_dataset_succeeds_for_normal_promotion(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_ready"
    curated_csv = dataset_root / "curated_aero_dataset.csv"
    _write_curated_csv(curated_csv)

    _write_json(
        dataset_root / "promotion_manifest.json",
        {
            "promotion_ready_at_time_of_promotion": True,
            "promotion_forced": False,
            "promotion_blockers": [],
            "artifacts": {
                "curated_aero_dataset_csv": str(curated_csv),
            },
        },
    )

    context = require_promoted_aero_dataset(dataset_root=dataset_root)

    assert context["dataset_root"] == str(dataset_root.resolve())
    assert context["curated_aero_dataset_csv"] == str(curated_csv.resolve())
    assert context["promotion_manifest"]["promotion_forced"] is False


def test_require_promoted_aero_dataset_fails_when_manifest_missing(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_missing"

    with pytest.raises(FileNotFoundError) as exc:
        require_promoted_aero_dataset(dataset_root=dataset_root)

    assert "promotion_manifest.json" in str(exc.value)


def test_require_promoted_aero_dataset_fails_when_curated_csv_missing(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_missing_csv"

    _write_json(
        dataset_root / "promotion_manifest.json",
        {
            "promotion_ready_at_time_of_promotion": True,
            "promotion_forced": False,
            "promotion_blockers": [],
            "artifacts": {
                "curated_aero_dataset_csv": str(dataset_root / "curated_aero_dataset.csv"),
            },
        },
    )

    with pytest.raises(FileNotFoundError) as exc:
        require_promoted_aero_dataset(dataset_root=dataset_root)

    assert "Promoted curated dataset CSV not found" in str(exc.value)


def test_require_promoted_aero_dataset_rejects_forced_promotion_by_default(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_forced"
    curated_csv = dataset_root / "curated_aero_dataset.csv"
    _write_curated_csv(curated_csv)

    _write_json(
        dataset_root / "promotion_manifest.json",
        {
            "promotion_ready_at_time_of_promotion": False,
            "promotion_forced": True,
            "promotion_blockers": ["aero_qc_failed"],
            "artifacts": {
                "curated_aero_dataset_csv": str(curated_csv),
            },
        },
    )

    with pytest.raises(ValueError) as exc:
        require_promoted_aero_dataset(dataset_root=dataset_root)

    assert "force-promoted" in str(exc.value)


def test_require_promoted_aero_dataset_can_allow_forced_promotion(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_forced_allowed"
    curated_csv = dataset_root / "curated_aero_dataset.csv"
    _write_curated_csv(curated_csv)

    _write_json(
        dataset_root / "promotion_manifest.json",
        {
            "promotion_ready_at_time_of_promotion": False,
            "promotion_forced": True,
            "promotion_blockers": ["aero_qc_failed"],
            "artifacts": {
                "curated_aero_dataset_csv": str(curated_csv),
            },
        },
    )

    context = require_promoted_aero_dataset(
        dataset_root=dataset_root,
        allow_forced=True,
    )

    assert context["promotion_manifest"]["promotion_forced"] is True


def test_load_promoted_aero_dataset_loads_dataframe(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset_load"
    curated_csv = dataset_root / "curated_aero_dataset.csv"
    _write_curated_csv(curated_csv)

    _write_json(
        dataset_root / "promotion_manifest.json",
        {
            "promotion_ready_at_time_of_promotion": True,
            "promotion_forced": False,
            "promotion_blockers": [],
            "artifacts": {
                "curated_aero_dataset_csv": str(curated_csv),
            },
        },
    )

    context = load_promoted_aero_dataset(dataset_root=dataset_root)

    assert "dataframe" in context
    assert len(context["dataframe"]) == 1
    assert list(context["dataframe"].columns) == ["geometry_id", "cl", "cd", "cm", "promotion_ready"]