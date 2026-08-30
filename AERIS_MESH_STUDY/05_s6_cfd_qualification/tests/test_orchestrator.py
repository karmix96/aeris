from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run.py"


def invoke(command, *extra):
    return subprocess.run([sys.executable, str(RUN), command, *extra], cwd=ROOT.parents[1], text=True, capture_output=True)


def test_contract_dry_run():
    assert invoke("audit-contract", "--dry-run").returncode == 0


def test_heavy_work_is_blocked():
    assert invoke("run-canary").returncode != 0


def test_holdout_is_metadata_locked():
    out = invoke("check-holdout-lock")
    assert out.returncode == 0
    assert '"contents_read": false' in out.stdout


def test_no_destructive_cleanup_policy():
    assert "explicit_human_approval_only" in (ROOT / "POLICY.yaml").read_text()


def test_geometry_semantic_diff_is_empty():
    out = invoke("audit-geometry-space")
    assert out.returncode == 0
    assert '"live_variable_count": 20' in out.stdout
    assert '"snapshot_variable_count": 20' in out.stdout
    assert '"bound_differences": []' in out.stdout
