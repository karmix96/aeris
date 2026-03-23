"""
Tests: common.paths

Purpose:
    Validate creation of run directories and filesystem structure.

What is tested:
    - Run folder is created successfully
    - Logs and artifacts subfolders exist
    - Directory structure is correct

Why it matters:
    All pipelines depend on correct run folder creation.
    If this fails, logging and artifact storage break globally.

Notes:
    Uses temporary directory (tmp_path) to avoid polluting project data.
"""

from aeris.common.paths import create_run_folder

def test_create_run_folder(tmp_path, monkeypatch):
    # Redirect RUNS_DIR to temp
    monkeypatch.setattr("aeris.common.paths.RUNS_DIR", tmp_path)

    run = create_run_folder(prefix="test")

    assert run.root.exists()
    assert run.logs.exists()
    assert run.artifacts.exists()

    assert run.logs.is_dir()
    assert run.artifacts.is_dir()

def test_run_id_unique(monkeypatch):
    from aeris.common.paths import make_run_id

    id1 = make_run_id()
    id2 = make_run_id()

    assert id1 != id2  # may fail if same second → reveals weakness