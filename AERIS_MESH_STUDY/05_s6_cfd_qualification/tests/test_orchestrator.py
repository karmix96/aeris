import ctypes
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
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


def invoke_preserving_report(command, *extra):
    report = ROOT / "reports" / f"{command.replace('-', '_')}.json"
    existed = report.exists()
    prior_report = report.read_bytes() if existed else None
    try:
        return invoke(command, *extra)
    finally:
        # CLI smoke tests must not obscure immutable terminal run evidence.
        if existed:
            report.write_bytes(prior_report)
        elif report.exists():
            report.unlink()


def test_contract_dry_run():
    assert invoke("audit-contract", "--dry-run").returncode == 0


def test_heavy_work_is_blocked():
    assert invoke_preserving_report("run-canary").returncode != 0
    assert invoke_preserving_report("run-tmr").returncode != 0


def test_consumed_canary_dry_run_is_permanently_blocked_and_launches_nothing():
    out = invoke_preserving_report("run-canary", "--dry-run")

    assert out.returncode == 3
    assert '"status": "BLOCKED"' in out.stdout
    assert '"process_launched": false' in out.stdout
    assert '"attempt_directory_absent": false' in out.stdout
    assert '"authorization_not_consumed": false' in out.stdout
    assert "exactly one measurement-only A/C03 canary" in out.stdout


def test_canary_policy_retains_complete_logs_and_full_residual_history():
    policy = yaml.safe_load((ROOT / "policies/m2_a_c03_canary_v2.yaml").read_text())
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
    assert policy["solver"]["environment"]["prefix"] == (
        "/home/mike_kara/miniconda3/envs/mach-aero"
    )
    assert policy["solver"]["environment"]["prelaunch_non_cfd_mpi_probe_required"] is True
    assert policy["resource"]["maximum_preexisting_swap_gib"] == 0.25
    assert policy["watchdog"]["maximum_swap_growth_gib"] == 0.25


def test_governed_canary_prepares_exact_solver_contract(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT))
    from canary import _build_solve_spec, _load_policy, _repo_path

    from aeris.cfd.solvers.base import get_solver_adapter

    policy = _load_policy()
    environment = policy["solver"]["environment"]
    monkeypatch.setenv("MACH_AERO_CONDA_PREFIX", environment["prefix"])
    prepared = get_solver_adapter("adflow").prepare(
        _build_solve_spec(policy), _repo_path(policy["mesh"]["path"]), tmp_path
    )
    options = json.loads((tmp_path / "adflow_options.json").read_text())
    case = json.loads((tmp_path / "adflow_case.json").read_text())
    assert prepared.command[:3] == (environment["mpirun"], "-np", "1")
    assert prepared.command[3] == environment["python"]
    assert options["equationType"] == "RANS"
    assert options["turbulenceModel"] == "SA"
    assert options["monitorVariables"] == policy["solver"]["monitor_variables"]
    assert options["surfaceVariables"] == policy["solver"]["surface_variables"]
    assert options["storeConvHist"] is True
    assert options["writeVolumeSolution"] is False
    assert options["writeSurfaceSolution"] is True
    assert options["NKSubspaceSize"] == 20
    assert case["reynolds_length_ref"] == 0.9
    assert case["moment_reference"] == [0.4, 0.0, 0.0]
    compile((tmp_path / "run_adflow.py").read_text(), "run_adflow.py", "exec")


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


def test_residual_measurement_ignores_policy_metadata_rows():
    sys.path.insert(0, str(ROOT))
    from canary import _residual_measurement

    policy = yaml.safe_load((ROOT / "policies/convergence_v2.yaml").read_text())
    raw = {
        "residual_components_final": {
            "density": 1.0e-6,
            "momentum": 2.0e-6,
            "energy": 3.0e-6,
            "sa": 4.0e-6,
        },
        "residual_components_definition": "ADflow native RMS monitors",
    }
    result = _residual_measurement(raw, policy)
    assert result["passed"] is True
    assert set(result["checks"]) == {"density", "momentum", "energy", "sa"}


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


def test_surface_field_reader_reads_adflow_adf_and_filters_wall_yplus(tmp_path):
    sys.path.insert(0, str(ROOT))
    sys.path.insert(
        0,
        str(ROOT.parents[0] / "04_strategy_studies/S6_bounded_mesh_atlas"),
    )
    from canary import _surface_field_presence
    from cfd_qc import (
        _CGNS_SIZE,
        _check_cgns,
        _load_cgns_library,
        wall_yplus_summary,
    )

    library, _ = _load_cgns_library()
    int_pointer = ctypes.POINTER(ctypes.c_int)
    size_pointer = ctypes.POINTER(_CGNS_SIZE)
    library.cg_base_write.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_int,
        int_pointer,
    ]
    library.cg_base_write.restype = ctypes.c_int
    library.cg_zone_write.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        size_pointer,
        ctypes.c_int,
        int_pointer,
    ]
    library.cg_zone_write.restype = ctypes.c_int
    library.cg_sol_write.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        int_pointer,
    ]
    library.cg_sol_write.restype = ctypes.c_int
    library.cg_field_write.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_void_p,
        int_pointer,
    ]
    library.cg_field_write.restype = ctypes.c_int

    surface = tmp_path / "surface_adf.cgns"
    file_number = ctypes.c_int()
    _check_cgns(
        library.cg_open(str(surface).encode(), 1, ctypes.byref(file_number)),
        "create ADF fixture",
        library,
    )
    try:
        base = ctypes.c_int()
        _check_cgns(
            library.cg_base_write(file_number.value, b"BaseSurfaceSol", 2, 3, ctypes.byref(base)),
            "write fixture base",
            library,
        )
        zone_size = (_CGNS_SIZE * 6)(3, 2, 2, 1, 0, 0)
        for zone_name, yplus_values in (
            (b"wall1", [0.5, 0.6]),
            (b"Far1", [100.0, 100.0]),
        ):
            zone = ctypes.c_int()
            solution = ctypes.c_int()
            _check_cgns(
                library.cg_zone_write(
                    file_number.value,
                    base.value,
                    zone_name,
                    zone_size,
                    2,
                    ctypes.byref(zone),
                ),
                "write fixture zone",
                library,
            )
            _check_cgns(
                library.cg_sol_write(
                    file_number.value,
                    base.value,
                    zone.value,
                    b"Flow solution",
                    3,
                    ctypes.byref(solution),
                ),
                "write fixture solution",
                library,
            )
            for field_name, field_values in (
                (b"CoefPressure", [0.1, 0.2]),
                (b"SkinFrictionMagnitude", [0.01, 0.02]),
                (b"YPlus", yplus_values),
            ):
                values = (ctypes.c_double * 2)(*field_values)
                field = ctypes.c_int()
                _check_cgns(
                    library.cg_field_write(
                        file_number.value,
                        base.value,
                        zone.value,
                        solution.value,
                        4,
                        field_name,
                        values,
                        ctypes.byref(field),
                    ),
                    "write fixture field",
                    library,
                )
    finally:
        _check_cgns(library.cg_close(file_number.value), "close ADF fixture", library)

    presence = _surface_field_presence(surface)
    assert presence["field_presence_passed"] is True
    assert presence["surface_reader"]["file_backend"] == "ADF"
    yplus = wall_yplus_summary(surface)
    assert yplus["passed"] is True
    assert yplus["wall_zone_count"] == 1
    assert yplus["sample_count"] == 2
    assert yplus["statistics"]["maximum"] == 0.6


def test_adflow_adf_reader_removes_symmetric_rind_planes():
    sys.path.insert(
        0,
        str(ROOT.parents[0] / "04_strategy_studies/S6_bounded_mesh_atlas"),
    )
    from cfd_qc import _trim_symmetric_rind

    stored = np.arange(12.0)
    physical, widths = _trim_symmetric_rind(stored, (4, 3), (2, 1))
    assert widths == (1, 1)
    assert physical.tolist() == [5.0, 6.0]


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
