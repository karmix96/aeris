import hashlib
import subprocess
import sys
from pathlib import Path

import h5py
import yaml

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "run.py"


def invoke(command, *extra):
    return subprocess.run(
        [sys.executable, str(RUN), command, *extra],
        cwd=ROOT.parents[1],
        text=True,
        capture_output=True,
    )


def test_contract_dry_run():
    assert invoke("audit-contract", "--dry-run").returncode == 0


def test_heavy_work_is_blocked():
    assert invoke("run-canary").returncode != 0
    assert invoke("run-tmr").returncode != 0


def test_canary_dry_run_is_exactly_scoped_and_launches_nothing():
    out = invoke("run-canary", "--dry-run")
    assert out.returncode == 0
    assert '"process_launched": false' in out.stdout
    assert "exactly one measurement-only A/C03 canary" in out.stdout


def test_canary_policy_retains_complete_logs_and_full_residual_history():
    policy = yaml.safe_load((ROOT / "policies/m2_a_c03_canary_v1.yaml").read_text())
    assert policy["solver"]["monitor_variables"] == [
        "resrho",
        "resmom",
        "resrhoe",
        "resturb",
        "cl",
        "cd",
        "cmy",
        "cdp",
        "cdv",
    ]
    assert policy["artifacts"]["retention"] == "retain_all_cfd_logs_and_measurement_evidence"
    assert policy["solver"]["write_volume_solution"] is False
    assert policy["solver"]["retain_surface_solution"] is True


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


def test_half_domain_contract():
    out = invoke("check-half-domain")
    assert out.returncode == 0
    assert '"state_zero_and_symmetric": true' in out.stdout
    assert '"force_reconstruction_required": true' in out.stdout


def test_29x75_identity_and_cache_invalidation():
    out = invoke("test-identity")
    assert out.returncode == 0
    assert '"stable_format_detected": true' in out.stdout
    assert '"candidate_grid": [' in out.stdout
    assert '"cache_invalidation_proven": true' in out.stdout


def test_versioned_execution_and_verdict_schemas():
    out = invoke("audit-schemas")
    assert out.returncode == 0
    assert '"terminal_states_separate": true' in out.stdout
    assert '"normalized_mass_imbalance_required": true' in out.stdout


def test_versioned_classification_policy():
    out = invoke("audit-policy")
    assert out.returncode == 0
    assert '"thresholds_machine_readable": true' in out.stdout
    assert '"reclassification_retains_original": true' in out.stdout
    assert "convergence_v2.yaml" in out.stdout


def test_execution_validator_rejects_incomplete_record(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version": 1}', encoding="utf-8")
    out = invoke("validate-execution", "--execution", str(path))
    assert out.returncode != 0


def test_execution_validator_accepts_governed_record(tmp_path):
    path = tmp_path / "good.json"
    path.write_text(
        '{"schema_version":1,"execution_id":"x","terminal_state":"blocked",'
        '"inputs":{"geometry_sha256":"g","policy_sha256":"p","mesh_identity":"m"},'
        '"artifacts":{"hashes_only":true}}',
        encoding="utf-8",
    )
    out = invoke("validate-execution", "--execution", str(path))
    assert out.returncode == 0


def test_moment_references_are_explicit():
    out = invoke("audit-moment-reference")
    assert out.returncode == 0
    assert '"quarter_mac_per_geometry": true' in out.stdout
    assert '"implicit_origin_forbidden": true' in out.stdout


def test_cfd_monitor_and_residual_contract():
    out = invoke("audit-cfd-contract")
    assert out.returncode == 0
    assert '"cmy_monitored": true' in out.stdout
    assert '"component_residuals_stored": true' in out.stdout
    assert '"full_native_residual_history_monitored": true' in out.stdout
    assert '"governed_boundary_flux_measurement_available": false' in out.stdout


def test_force_tail_reads_adflow_canonical_monitor_names():
    sys.path.insert(0, str(ROOT))
    from canary import _force_tail

    raw = {
        "convergence_history": {
            "CoefLift": [0.5] * 200,
            "CoefDrag": [0.02] * 200,
            "CoefMomentY": [-0.03] * 200,
        }
    }
    policy = yaml.safe_load((ROOT / "policies/convergence_v2.yaml").read_text())
    assert _force_tail(raw, policy)["passed"] is True


def test_surface_field_reader_recognizes_adflow_cgns_names(tmp_path):
    sys.path.insert(0, str(ROOT))
    from canary import _surface_field_presence

    surface = tmp_path / "surface.cgns"
    with h5py.File(surface, "w") as handle:
        zone = handle.create_group("Base/nswall_test/FlowSolution")
        zone.create_dataset("CoefPressure", data=[0.1, 0.2])
        zone.create_dataset("SkinFrictionMagnitude", data=[0.01, 0.02])
        zone.create_dataset("YPlus", data=[0.5, 0.6])
    result = _surface_field_presence(surface)
    assert result["field_presence_passed"] is True
    assert result["passed"] is False
    assert result["failure_reasons"] == ["interface_discontinuity_not_evaluated"]


def test_reclassification_retains_execution_and_prior_verdict(tmp_path):
    execution = tmp_path / "execution.json"
    execution.write_text(
        '{"execution_id":"e1","status":"converged","convergence":{'
        '"residual_components_l2":{"density":1e-6,"momentum":1e-6,"energy":1e-6,"sa":1e-6},'
        '"mass_imbalance_normalized":1e-5}}',
        encoding="utf-8",
    )
    before = hashlib.sha256(execution.read_bytes()).hexdigest()
    strict = tmp_path / "strict.yaml"
    strict.write_text(
        "policy_id: strict\nresiduals:\n"
        "  density: {max_final: 1e-7}\n"
        "  momentum: {max_final: 1e-7}\n"
        "  energy: {max_final: 1e-7}\n"
        "  sa: {max_final: 1e-7}\n"
        "mass_imbalance_normalized: {max: 1e-6}\n"
    )
    lenient = tmp_path / "lenient.yaml"
    lenient.write_text(
        "policy_id: lenient\nresiduals:\n"
        "  density: {max_final: 1e-5}\n"
        "  momentum: {max_final: 1e-5}\n"
        "  energy: {max_final: 1e-5}\n"
        "  sa: {max_final: 1e-5}\n"
        "mass_imbalance_normalized: {max: 1e-4}\n"
    )
    assert (
        invoke("classify", "--execution", str(execution), "--policy", str(strict)).returncode != 0
    )
    assert (
        invoke("classify", "--execution", str(execution), "--policy", str(lenient)).returncode == 0
    )
    assert len(list((tmp_path / "verdicts").glob("verdict_*.json"))) == 2
    assert hashlib.sha256(execution.read_bytes()).hexdigest() == before


def test_measurement_only_execution_cannot_be_accepted(tmp_path):
    execution = tmp_path / "measurement.json"
    execution.write_text(
        '{"execution_id":"m1","status":"converged","measurement_only":true,'
        '"convergence":{"residual_components_l2":{"density":1e-6,'
        '"momentum":1e-6,"energy":1e-6,"sa":1e-6},'
        '"mass_imbalance_normalized":1e-5}}',
        encoding="utf-8",
    )
    policy = tmp_path / "policy.yaml"
    policy.write_text(
        "policy_id: guarded\nresiduals:\n  density: {max_final: 1e-5}\n"
        "  momentum: {max_final: 1e-5}\n  energy: {max_final: 1e-5}\n"
        "  sa: {max_final: 1e-5}\nmass_imbalance_normalized: {max: 1e-4}\n"
        "classification:\n  measurement_only_execution_may_be_accepted: false\n"
    )
    assert (
        invoke("classify", "--execution", str(execution), "--policy", str(policy)).returncode != 0
    )


def test_three_level_family_math_and_resource_screen():
    out = invoke("screen-grid-family")
    assert out.returncode == 0
    assert '"ratios_in_band": true' in out.stdout
    assert '"forecast_le_75pct_limit": true' in out.stdout
    assert '"written_cgns_A_B_C_E": true' in out.stdout
    assert '"nominal_A_written": true' in out.stdout
    assert '"nominal_finest_zero_inversions": true' in out.stdout
    assert '"status": "CONDITIONAL"' in out.stdout
    assert "exactly one governed measurement-only A/C03 canary" in out.stdout
