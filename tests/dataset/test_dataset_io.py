from __future__ import annotations

import csv
from pathlib import Path

import pytest

from aeris.dataset.io import append_csv_row, ensure_csv_with_header, ensure_dataset_paths


def test_ensure_csv_with_header_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "metadata.csv"
    fieldnames = ["a", "b"]

    ensure_csv_with_header(path, fieldnames)
    ensure_csv_with_header(path, fieldnames)

    rows = path.read_text(encoding="utf-8").splitlines()
    assert rows == ["a,b"]


def test_append_csv_row_writes_header_once(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    fieldnames = ["a", "b"]

    append_csv_row(path, {"a": 1, "b": 2}, fieldnames)
    append_csv_row(path, {"a": 3, "b": 4}, fieldnames)

    rows = path.read_text(encoding="utf-8").splitlines()
    assert rows == ["a,b", "1,2", "3,4"]


def test_append_csv_row_rejects_extra_keys(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    fieldnames = ["a", "b"]

    with pytest.raises(ValueError, match="extra keys"):
        append_csv_row(path, {"a": 1, "b": 2, "c": 3}, fieldnames)


def test_append_csv_row_rejects_missing_keys(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    fieldnames = ["a", "b"]

    with pytest.raises(ValueError, match="missing keys"):
        append_csv_row(path, {"a": 1}, fieldnames)


def test_ensure_dataset_paths_creates_expected_structure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aeris.dataset.io.DATASETS_DIR", tmp_path)

    paths = ensure_dataset_paths("my_dataset")

    assert paths.root == tmp_path / "my_dataset"
    assert paths.geometry_dir.exists()
    assert paths.configs_dir.exists()
    assert paths.logs_dir.exists()
    assert paths.manifest_path == paths.root / "dataset_manifest.json"
    assert paths.metadata_csv_path == paths.root / "metadata.csv"
    assert paths.failures_csv_path == paths.root / "failures.csv"


def test_ensure_dataset_paths_rejects_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("aeris.dataset.io.DATASETS_DIR", tmp_path)

    ensure_dataset_paths("duplicate_me")

    with pytest.raises(FileExistsError, match="already exists"):
        ensure_dataset_paths("duplicate_me")