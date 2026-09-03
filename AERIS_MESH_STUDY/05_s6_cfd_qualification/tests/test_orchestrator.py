import ctypes
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest
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


def test_canary_dry_run_reflects_one_shot_state_and_launches_nothing():
    out = invoke_preserving_report("run-canary", "--dry-run")
    payload = json.loads(out.stdout.split("\nrecord:", 1)[0])
    policy = yaml.safe_load((ROOT / "policies/m2_a_c03_canary_v4.yaml").read_text())
    consumed = ROOT.parents[1] / policy["attempt"]["consumed_record"]
    attempt = ROOT.parents[1] / policy["attempt"]["directory"]

    checks = payload["details"]["preflight"]["one_shot_checks"]
    assert checks["authorization_not_consumed"] is (not consumed.exists())
    assert checks["attempt_directory_absent"] is (not attempt.exists())
    assert payload["details"]["process_launched"] is False
    assert payload["details"]["scope"] == "exactly one measurement-only A/C03 canary"
    assert out.returncode in {0, 3}


def test_canary_policy_retains_complete_logs_and_full_residual_history():
    policy = yaml.safe_load((ROOT / "policies/m2_a_c03_canary_v4.yaml").read_text())
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
    assert policy["solver"]["ank_subspace_size"] == 10
    assert policy["solver"]["nk_subspace_size"] == 20
    assert policy["solver"]["ank_pc_ilu_fill"] == 1
    assert policy["solver"]["nk_pc_ilu_fill"] == 1
    assert policy["resource"]["forecast_peak_gib"] == 9.45
    assert policy["resource"]["maximum_preexisting_swap_gib"] == 0.25
    assert policy["watchdog"]["maximum_swap_growth_gib"] == 0.25


def test_governed_source_cleanliness_includes_active_v4_policy():
    source = (ROOT / "canary.py").read_text()
    assert 'policies/m2_a_c03_canary_v4.yaml"' in source


def test_desktop_recovery_plan_matches_candidate_solver_and_implementation():
    plan_path = ROOT / "reports/m2_a_c03_desktop_recovery_plan_20260902.json"
    plan = json.loads(plan_path.read_text())
    preset_path = ROOT.parents[1] / plan["implementation"]["solver_preset_path"]
    preset = yaml.safe_load(preset_path.read_text())["solver"]
    bound = plan["bound_solver_change"]
    assert preset["use_nk_solver"] is bound["useNKSolver"]
    assert preset["nk_switch_tol"] == bound["NKSwitchTol"]
    assert preset["n_cycles"] == bound["nCycles"]
    assert preset["l2_convergence"] == bound["L2Convergence"] == 1e-11
    assert bound["timeLimit"] == 27000.0

    # The plan is immutable evidence of what the first independent review saw.
    # Later corrections are legitimate, but each one must be declared with its
    # exact current hash and a reason; silent drift stays a failure.
    drift = json.loads(
        (ROOT / "reports/m2_a_c03_implementation_drift_20260903.json").read_text()
    )
    assert drift["requires_fresh_independent_review_before_cfd"] is True
    assert drift["cfd_authorized"] is False
    for path_key, hash_key in (
        ("mesh_redistribution_path", "mesh_redistribution_sha256"),
        ("canary_orchestrator_path", "canary_orchestrator_sha256"),
        ("cgns_restart_validator_path", "cgns_restart_validator_sha256"),
        ("solver_preset_path", "solver_preset_sha256"),
    ):
        path = ROOT.parents[1] / plan["implementation"][path_key]
        current = hashlib.sha256(path.read_bytes()).hexdigest()
        if current == plan["implementation"][hash_key]:
            continue
        declared = drift["declared_drift"].get(hash_key)
        assert declared is not None, f"undeclared implementation drift in {path_key}"
        assert declared["reviewed_sha256"] == plan["implementation"][hash_key]
        assert declared["current_sha256"] == current
        assert declared["reason"] != "undeclared"

    checkpoint = plan["bound_checkpoint_policy"]
    assert checkpoint["validate_cgns_restart"] is True
    assert checkpoint["expected_zone_count"] == 13
    assert checkpoint["minimum_coordinate_arrays_per_zone"] == 3
    assert checkpoint["maximum_validation_field_values"] == 2_000_000
    assert checkpoint["required_restart_fields"] == [
        "Density",
        "VelocityX",
        "VelocityY",
        "VelocityZ",
        "Pressure",
        "TurbulentSANuTilde",
    ]


def test_watchdog_counts_the_full_launcher_process_session():
    sys.path.insert(0, str(ROOT))
    from canary import _process_session_rss_bytes

    assert _process_session_rss_bytes(os.getsid(0)) > 0


def test_checkpoint_signal_target_requires_one_exact_python_rank(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT))
    import canary

    python = tmp_path / "python"
    runner = tmp_path / "run_adflow.py"
    records = [
        {"pid": 10, "executable": str(python), "argv": [str(python), str(runner)]},
        {"pid": 11, "executable": "/usr/bin/mpirun", "argv": ["mpirun", str(runner)]},
    ]
    monkeypatch.setattr(canary, "_session_process_records", lambda _session: records)

    selected = canary._checkpoint_signal_target(99, executable_realpath=python, runner_path=runner)
    assert selected["selected_pid"] == 10
    assert selected["match_count"] == 1

    records.append({"pid": 12, "executable": str(python), "argv": [str(python), str(runner)]})
    ambiguous = canary._checkpoint_signal_target(99, executable_realpath=python, runner_path=runner)
    assert ambiguous["selected_pid"] is None
    assert ambiguous["match_count"] == 2


def test_durable_checkpoint_copy_refuses_overwrite(tmp_path):
    sys.path.insert(0, str(ROOT))
    from canary import _durable_copy

    source = tmp_path / "forced.cgns"
    destination = tmp_path / "checkpoints/checkpoint_0001.cgns"
    source.write_bytes(b"restart-state")
    _durable_copy(source, destination)
    assert destination.read_bytes() == b"restart-state"
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _durable_copy(source, destination)


def test_solution_selection_prefers_normal_output_and_retains_forced(tmp_path):
    sys.path.insert(0, str(ROOT))
    from canary import _solution_selection

    final = tmp_path / "aeris_cfd_000_surf.cgns"
    forced = tmp_path / "aeris_cfd_forced_surf.cgns"
    final.write_bytes(b"final")
    forced.write_bytes(b"forced")
    selected = _solution_selection(tmp_path, "surf")
    assert selected["selected"] == final
    assert selected["forced_candidates"] == [forced]


def test_watchdog_captures_versioned_sigusr1_checkpoint(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT))
    import canary

    inspected: list[Path] = []

    def valid_inventory(path, **_requirements):
        inspected.append(Path(path))
        return {"passed": True, "path": str(path), "test_inventory": True}

    monkeypatch.setattr(canary, "cgns_volume_restart_inventory", valid_inventory)

    runner = tmp_path / "run_adflow.py"
    runner.write_text(
        "import pathlib, signal, time\n"
        "target = pathlib.Path(__file__).parent / 'aeris_cfd_forced_vol.cgns'\n"
        "def checkpoint(_signal, _frame):\n"
        "    target.write_bytes(str(time.time_ns()).encode())\n"
        "signal.signal(signal.SIGUSR1, checkpoint)\n"
        "time.sleep(0.8)\n",
        encoding="utf-8",
    )
    runtime = canary._run_with_watchdog(
        [sys.executable, str(runner)],
        workdir=tmp_path,
        log_path=tmp_path / "solver.log",
        samples_path=tmp_path / "resources.jsonl",
        watchdog_policy={
            "poll_interval_seconds": 0.02,
            "heartbeat_interval_seconds": 10.0,
            "minimum_mem_available_gib": 0.0,
            "maximum_swap_growth_gib": 100.0,
            "minimum_runtime_free_disk_gib": 0.0,
            "terminate_grace_seconds": 1.0,
        },
        checkpoint_policy={
            "enabled": True,
            "validate_cgns_restart": True,
            "expected_zone_count": 13,
            "required_restart_fields": ["Density", "TurbulentSANuTilde"],
            "events_filename": "checkpoint_events.jsonl",
            "directory": "checkpoints",
            "forced_volume_filename": "aeris_cfd_forced_vol.cgns",
            "interval_seconds": 0.1,
            "stable_seconds": 0.04,
            "maximum_write_wait_seconds": 0.4,
            "solver_executable_realpath": str(Path(sys.executable).resolve()),
            "runner_filename": runner.name,
        },
    )
    checkpointing = runtime["checkpointing"]
    assert runtime["returncode"] == 0
    assert runtime["watchdog_stopped"] is False
    assert checkpointing["request_count"] >= 1
    assert checkpointing["captured_count"] >= 1
    assert checkpointing["restart_validation_enabled"] is True
    assert checkpointing["expected_zone_count"] == 13
    assert len(inspected) >= 2
    assert checkpointing["failure_count"] <= (
        checkpointing["request_count"] - checkpointing["captured_count"]
    )
    for checkpoint in checkpointing["checkpoints"]:
        path = Path(checkpoint["path"])
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == checkpoint["sha256"]
        assert checkpoint["source_sha256"] == checkpoint["sha256"]
        assert checkpoint["source_inventory"]["passed"] is True
        assert checkpoint["copied_inventory"]["passed"] is True
        assert not path.with_name(f"{path.stem}.pending.cgns").exists()


def test_watchdog_never_publishes_checkpoint_that_fails_restart_inventory(
    tmp_path, monkeypatch
):
    sys.path.insert(0, str(ROOT))
    import canary

    monkeypatch.setattr(
        canary,
        "cgns_volume_restart_inventory",
        lambda _path, **_requirements: {
            "passed": False,
            "failure_reasons": ["zone_without_required_restart_field_set"],
        },
    )
    runner = tmp_path / "run_adflow.py"
    runner.write_text(
        "import pathlib, signal, time\n"
        "target = pathlib.Path(__file__).parent / 'aeris_cfd_forced_vol.cgns'\n"
        "def checkpoint(_signal, _frame):\n"
        "    target.write_bytes(b'incomplete-restart')\n"
        "signal.signal(signal.SIGUSR1, checkpoint)\n"
        "time.sleep(0.7)\n",
        encoding="utf-8",
    )
    runtime = canary._run_with_watchdog(
        [sys.executable, str(runner)],
        workdir=tmp_path,
        log_path=tmp_path / "solver.log",
        samples_path=tmp_path / "resources.jsonl",
        watchdog_policy={
            "poll_interval_seconds": 0.02,
            "heartbeat_interval_seconds": 10.0,
            "minimum_mem_available_gib": 0.0,
            "maximum_swap_growth_gib": 100.0,
            "minimum_runtime_free_disk_gib": 0.0,
            "terminate_grace_seconds": 1.0,
        },
        checkpoint_policy={
            "enabled": True,
            "validate_cgns_restart": True,
            "expected_zone_count": 13,
            "required_restart_fields": ["Density", "TurbulentSANuTilde"],
            "events_filename": "checkpoint_events.jsonl",
            "directory": "checkpoints",
            "forced_volume_filename": "aeris_cfd_forced_vol.cgns",
            "interval_seconds": 0.05,
            "stable_seconds": 0.02,
            "maximum_write_wait_seconds": 0.5,
            "solver_executable_realpath": str(Path(sys.executable).resolve()),
            "runner_filename": runner.name,
        },
    )
    checkpointing = runtime["checkpointing"]
    events = [
        json.loads(line)
        for line in (tmp_path / "checkpoint_events.jsonl").read_text().splitlines()
    ]
    assert runtime["returncode"] == 0
    assert checkpointing["captured_count"] == 0
    assert checkpointing["failure_count"] >= 1
    assert any(row["event"] == "checkpoint_validation_wait" for row in events)
    assert not list((tmp_path / "checkpoints").glob("checkpoint_[0-9][0-9][0-9][0-9].cgns"))


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
    ranks = str(policy["solver"]["mpi_processes"])
    assert prepared.command[:3] == (environment["mpirun"], "-np", ranks)
    assert prepared.command[3] == environment["python"]
    assert options["equationType"] == "RANS"
    assert options["turbulenceModel"] == "SA"
    assert options["monitorVariables"] == policy["solver"]["monitor_variables"]
    assert options["surfaceVariables"] == policy["solver"]["surface_variables"]
    assert options["storeConvHist"] is True
    assert options["writeVolumeSolution"] is policy["solver"]["write_volume_solution"]
    assert options["writeSurfaceSolution"] is True
    assert options["ANKSubspaceSize"] == 10
    assert options["NKSubspaceSize"] == 20
    assert options["ANKPCILUFill"] == 1
    assert options["NKPCILUFill"] == 1
    assert case["reynolds_length_ref"] == 0.9
    assert case["moment_reference"] == [0.4, 0.0, 0.0]
    compile((tmp_path / "run_adflow.py").read_text(), "run_adflow.py", "exec")


def test_recovery_solver_contract_disables_nk_and_enables_restart_output(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT))
    from canary import _build_solve_spec, _load_policy, _repo_path

    from aeris.cfd.solvers.base import get_solver_adapter

    policy = json.loads(json.dumps(_load_policy()))
    solver = policy["solver"]
    solver.update(
        {
            "preset": "rans_ank_memory_safe_v1",
            "use_nk_solver": False,
            "nk_switch_tol": 1.0e-10,
            "n_cycles": 20000,
            "l2_convergence": 1.0e-8,
            "write_volume_solution": True,
            "solution_precision": "double",
            "time_limit_seconds": 27000.0,
            "surface_variables": [
                "cp",
                "cf",
                "cfx",
                "cfy",
                "cfz",
                "yplus",
                "rho",
                "vx",
                "vy",
                "vz",
            ],
        }
    )
    monkeypatch.setenv("MACH_AERO_CONDA_PREFIX", solver["environment"]["prefix"])
    workdir = tmp_path / "recovery"
    get_solver_adapter("adflow").prepare(
        _build_solve_spec(policy), _repo_path(policy["mesh"]["path"]), workdir
    )
    options = json.loads((workdir / "adflow_options.json").read_text())
    assert options["useNKSolver"] is False
    assert options["NKSwitchTol"] == 1.0e-10
    assert options["nCycles"] == 20000
    assert options["L2Convergence"] == 1.0e-8
    assert options["writeVolumeSolution"] is True
    assert options["solutionPrecision"] == "double"
    assert options["timeLimit"] == 27000.0
    assert "rho" in options["surfaceVariables"]
    compile((workdir / "run_adflow.py").read_text(), "run_adflow.py", "exec")


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
    assert '"governed_boundary_flux_definition_required": true' in out.stdout
    assert '"governed_boundary_flux_measurement_available": true' in out.stdout
    assert '"acceptance_contract_complete": true' in out.stdout


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
    # Fields parse, but a stub file carries no zone geometry, so the interface
    # check cannot run and must fail closed rather than pass by default.
    assert result["passed"] is False
    assert result["failure_reasons"] == [
        "conformal_interface_discontinuity",
        "interface_discontinuity_not_evaluated",
    ]
    assert result["interface_discontinuity_check"]["error"]


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
        cgns_volume_restart_inventory,
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
    library.cg_coord_write.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_void_p,
        int_pointer,
    ]
    library.cg_coord_write.restype = ctypes.c_int
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
            for coordinate_name, coordinate_values in (
                (b"CoordinateX", [0.0, 1.0, 2.0, 0.0, 1.0, 2.0]),
                (b"CoordinateY", [0.0, 0.0, 0.0, 1.0, 1.0, 1.0]),
                (b"CoordinateZ", [0.0] * 6),
            ):
                coordinate = ctypes.c_int()
                values = (ctypes.c_double * 6)(*coordinate_values)
                _check_cgns(
                    library.cg_coord_write(
                        file_number.value,
                        base.value,
                        zone.value,
                        4,
                        coordinate_name,
                        values,
                        ctypes.byref(coordinate),
                    ),
                    "write fixture coordinate",
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

    inventory = cgns_volume_restart_inventory(
        surface,
        expected_zones=2,
        required_fields=["CoefPressure", "SkinFrictionMagnitude", "YPlus"],
    )
    assert inventory["passed"] is True
    assert inventory["zone_count"] == 2
    assert all(zone["coordinate_array_count"] == 3 for zone in inventory["zones"])
    missing = cgns_volume_restart_inventory(
        surface,
        expected_zones=2,
        required_fields=["TurbulentSANuTilde"],
    )
    assert missing["passed"] is False
    assert missing["failure_reasons"] == ["zone_without_required_restart_field_set"]


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


def _load_canary():
    import importlib.util

    spec = importlib.util.spec_from_file_location("aeris_canary", ROOT / "canary.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLASSIFICATION = {
    "mass_imbalance_normalized": {
        "max": 1.0e-4,
        "required_definition": "signed_net_boundary_mass_flux_over_gross_boundary_mass_flux",
    }
}


def _raw_run(**overrides):
    run = {
        "mass_imbalance_definition": (
            "signed_net_boundary_mass_flux_over_gross_boundary_mass_flux"
        ),
        "mass_imbalance_normalized": 1.0e-6,
        "boundary_mass_flux": {
            "complete": True,
            "error": None,
            "signed_net": 1.0e-6,
            "gross": 1.0,
            "family_count": 4,
            "per_family": {},
            "granularity_note": "note",
        },
        "residual_cancellation_ratio_diagnostic": 0.14,
    }
    run.update(overrides)
    return run


def test_conservation_passes_on_governed_boundary_flux():
    canary = _load_canary()
    result = canary._conservation(_raw_run(), CLASSIFICATION)
    assert result["passed"] is True
    assert result["boundary_flux_complete"] is True
    assert result["measured_definition"] == CLASSIFICATION["mass_imbalance_normalized"][
        "required_definition"
    ]


def test_conservation_rejects_interior_residual_cancellation_ratio():
    canary = _load_canary()
    legacy = _raw_run(
        mass_imbalance_definition=(
            "abs(sum continuity residual)/sum(abs continuity residual)"
        ),
        mass_imbalance_normalized=1.0e-9,
    )
    result = canary._conservation(legacy, CLASSIFICATION)
    assert result["passed"] is False


def test_conservation_fails_closed_on_incomplete_integration():
    canary = _load_canary()
    run = _raw_run()
    run["boundary_mass_flux"] = dict(run["boundary_mass_flux"], complete=False)
    assert canary._conservation(run, CLASSIFICATION)["passed"] is False


def test_conservation_fails_closed_when_integration_errored():
    canary = _load_canary()
    run = _raw_run()
    run["boundary_mass_flux"] = dict(run["boundary_mass_flux"], error="mdot blew up")
    assert canary._conservation(run, CLASSIFICATION)["passed"] is False


def test_conservation_fails_closed_when_boundary_flux_absent():
    canary = _load_canary()
    run = _raw_run()
    del run["boundary_mass_flux"]
    result = canary._conservation(run, CLASSIFICATION)
    assert result["passed"] is False
    assert result["boundary_flux_complete"] is False


def test_conservation_enforces_the_threshold():
    canary = _load_canary()
    assert canary._conservation(
        _raw_run(mass_imbalance_normalized=1.0e-3), CLASSIFICATION
    )["passed"] is False
    assert canary._conservation(
        _raw_run(mass_imbalance_normalized=1.0e-4), CLASSIFICATION
    )["passed"] is True


ATTEMPT04_SURFACE = (
    ROOT
    / "studies/canary/m2_a_c03_measurement_20260902_004/aeris_cfd_000_surf.cgns"
)


def _cfd_qc():
    sys.path.insert(0, str(ROOT.parents[0] / "04_strategy_studies/S6_bounded_mesh_atlas"))
    import cfd_qc

    return cfd_qc


def test_edge_cell_rows_and_centres_agree_on_orientation():
    cfd_qc = _cfd_qc()
    cells = np.arange(12, dtype=float).reshape(3, 4)
    face, inner = cfd_qc._edge_cell_rows(cells, "i0")
    assert list(face) == [0.0, 1.0, 2.0, 3.0]
    assert list(inner) == [4.0, 5.0, 6.0, 7.0]
    face, inner = cfd_qc._edge_cell_rows(cells, "j1")
    assert list(face) == [3.0, 7.0, 11.0]
    assert list(inner) == [2.0, 6.0, 10.0]

    # A unit-spaced patch puts the i0 face row half a cell in from the edge and
    # the inner row one full cell further.
    ii, jj = np.meshgrid(np.arange(4.0), np.arange(5.0), indexing="ij")
    vertices = np.stack([ii, jj, np.zeros_like(ii)], axis=-1)
    face_c, inner_c = cfd_qc._edge_cell_centres(vertices, "i0")
    assert face_c.shape == (4, 3)
    assert face_c[0][0] == pytest.approx(0.5)
    assert inner_c[0][0] == pytest.approx(1.5)


def test_safe_gradient_never_divides_by_zero():
    cfd_qc = _cfd_qc()
    out = cfd_qc._safe_gradient(np.array([1.0, 2.0]), np.array([0.0, 2.0]))
    assert np.isnan(out[0])
    assert out[1] == pytest.approx(1.0)


def test_attempt04_surface_interfaces_are_fully_matched():
    cfd_qc = _cfd_qc()
    result = cfd_qc.conformal_interface_discontinuity(ATTEMPT04_SURFACE)
    # The governed mesh family declares 20 conformal paired interfaces, and the
    # geometric match must find exactly that many with no wall zone left out.
    assert result["matched_interface_count"] == 20
    assert result["wall_zones_without_matched_interface"] == []
    assert len(result["wall_zones_examined"]) == 13
    assert result["reshape_failures"] == []
    for interface in result["interfaces"]:
        assert set(interface["fields"]) == {"cp", "cf", "yplus"}


def test_attempt04_surface_records_the_known_tip_collar_defect():
    cfd_qc = _cfd_qc()
    result = cfd_qc.conformal_interface_discontinuity(ATTEMPT04_SURFACE)
    assert result["passed"] is False
    reasons = {(d["interface"], d["field"], d["reason"]) for d in result["defects"]}
    assert (
        "NSWallAdiabaticBCZone23.j1<->NSWallAdiabaticBCZone7.j0",
        "cp",
        "jump_exceeds_global_field_range",
    ) in reasons
    # Shear-based fields stay continuous, so this is a pressure-field defect at
    # one tip-collar seam rather than a global topology failure.
    assert result["gradient_ratio_summary"]["cf"]["median"] < 1.5
    assert result["gradient_ratio_summary"]["yplus"]["median"] < 1.5


def test_interface_threshold_is_declared_uncalibrated():
    cfd_qc = _cfd_qc()
    result = cfd_qc.conformal_interface_discontinuity(ATTEMPT04_SURFACE)
    assert result["gradient_ratio_threshold_calibrated"] is False
    assert "C01/C02/C03" in result["gradient_ratio_calibration_requirement"]


def test_surface_field_check_no_longer_reports_the_gap_as_unevaluated():
    sys.path.insert(0, str(ROOT))
    from canary import _surface_field_presence

    result = _surface_field_presence(ATTEMPT04_SURFACE)
    assert result["field_presence_passed"] is True
    assert "interface_discontinuity_not_evaluated" not in result["failure_reasons"]
    assert "conformal_interface_discontinuity" in result["failure_reasons"]
    assert result["interface_discontinuity_check"]["matched_interface_count"] == 20


ATTEMPT03_SURFACE = (
    ROOT
    / "studies/canary/m2_a_c03_measurement_20260901_003/aeris_cfd_000_surf.cgns"
)


def _wall_cp(surface):
    cfd_qc = _cfd_qc()
    coords = cfd_qc.read_surface_zone_coordinates(surface)
    raw, reader = cfd_qc.read_surface_field_arrays(surface, ["coefpressure"])
    layouts = reader["solution_layouts"]
    out = {}
    for zone, per_field in raw.items():
        if not cfd_qc._is_no_slip_wall_zone(zone) or zone not in coords:
            continue
        shape = tuple(layouts[zone][0]["physical_shape"])
        for name, arrays in per_field.items():
            if name.casefold() == "coefpressure":
                out[zone] = np.asarray(arrays[0]).reshape(shape, order="F")
    return out


# The physical stagnation bound for this Mach 0.0837 case; cp cannot exceed it.
MAX_ADMISSIBLE_CP = 1.0018


def test_leading_edge_collar_carries_impossible_pressure_on_both_meshes():
    for surface, expected_max in (
        (ATTEMPT03_SURFACE, 5.3),
        (ATTEMPT04_SURFACE, 4.1),
    ):
        cp = _wall_cp(surface)
        collar = cp["NSWallAdiabaticBCZone7"]
        assert int((collar > MAX_ADMISSIBLE_CP).sum()) == 137
        assert collar.max() > expected_max
    # Identical face counts on two different meshes: a collar-block property,
    # not a consequence of the wall-normal correction.


def test_trailing_edge_collar_is_clean():
    cp = _wall_cp(ATTEMPT04_SURFACE)
    assert cp["NSWallAdiabaticBCZone16"].max() <= MAX_ADMISSIBLE_CP


def test_leading_edge_collar_defect_report_matches_the_retained_surfaces():
    report = json.loads(
        (ROOT / "reports/m2_a_c03_leading_edge_collar_defect_20260903.json").read_text()
    )
    for key, surface in (
        ("attempt03_pre_correction_mesh", ATTEMPT03_SURFACE),
        ("attempt04_corrected_mesh", ATTEMPT04_SURFACE),
    ):
        recorded = report[key]
        assert (
            hashlib.sha256(surface.read_bytes()).hexdigest()
            == recorded["surface_solution_sha256"]
        )
        cp = _wall_cp(surface)
        over = sum(int((values > 1.0).sum()) for values in cp.values())
        assert over == recorded["wall_faces_with_cp_above_unity"]
    assert report["authorizes_cfd"] is False


def _wrap_turning_deg(vertices):
    """Total surface turning absorbed across a collar wrap, per span station."""
    out = []
    for j in range(vertices.shape[1]):
        segments = np.diff(vertices[:, j, :], axis=0)
        lengths = np.linalg.norm(segments, axis=1)
        unit = segments / lengths[:, None]
        cosines = np.clip((unit[:-1] * unit[1:]).sum(axis=1), -1.0, 1.0)
        out.append(float(np.degrees(np.arccos(cosines)).sum()))
    return np.array(out)


def test_leading_edge_wrap_is_starved_of_chordwise_cells():
    cfd_qc = _cfd_qc()
    coords = cfd_qc.read_surface_zone_coordinates(ATTEMPT04_SURFACE)
    nose = coords["NSWallAdiabaticBCZone7"]
    assert nose.shape[:2] == (5, 75)  # end_points = 5 at C03
    turning = _wrap_turning_deg(nose)
    # Four cells absorb about a right angle and a half of surface turning.
    assert np.median(turning) > 90.0
    assert np.median(turning) / 3.0 > 25.0


def test_trailing_edge_wrap_has_the_same_width_but_no_turning():
    cfd_qc = _cfd_qc()
    coords = cfd_qc.read_surface_zone_coordinates(ATTEMPT04_SURFACE)
    base = coords["NSWallAdiabaticBCZone16"]
    # Identical end_points and identical block width as the leading edge.
    assert base.shape[:2] == (5, 75)
    assert np.median(_wrap_turning_deg(base)) < 1.0
    # And, unlike the leading edge, no physically impossible pressure.
    assert _wall_cp(ATTEMPT04_SURFACE)["NSWallAdiabaticBCZone16"].max() <= MAX_ADMISSIBLE_CP


def test_end_points_starve_the_wrap_at_every_family_level():
    sys.path.insert(0, str(ROOT.parents[0] / "04_strategy_studies/S6_bounded_mesh_atlas"))
    import strategy_s6

    levels = strategy_s6.LEVELS
    # The wrap carries end_points-1 cells, so C01/C02/C03 give 2, 3 and 4 cells
    # around a leading edge that turns through roughly 100 degrees.
    assert levels["candidate_c01"].end_points == 3
    assert levels["candidate_c02"].end_points == 4
    assert levels["candidate_c03"].end_points == 5
    # Before the D family, no level anywhere used more than 5.
    legacy = {name: spec for name, spec in levels.items() if not name.startswith("candidate_d")}
    assert max(spec.end_points for spec in legacy.values()) == 5


C03_POLICY_SURFACE_SHA256 = "dd35106445ddbab88dbd79fe64c09c53d4a63622a7d0cd8deaca7cd28b0f3a19"


def _strategy_s6():
    sys.path.insert(0, str(ROOT.parents[0] / "04_strategy_studies"))
    sys.path.insert(0, str(ROOT.parents[0] / "04_strategy_studies/S6_bounded_mesh_atlas"))
    import strategy_s6

    return strategy_s6


def test_new_level_knobs_default_to_the_c_family_behaviour():
    strategy_s6 = _strategy_s6()
    for name in ("candidate_c01", "candidate_c02", "candidate_c03"):
        spec = strategy_s6.LEVELS[name]
        assert spec.end_scale == 5.0, name
        assert spec.le_cluster == 0.0, name


def test_uniform_spacing_path_is_bit_identical_to_linspace():
    strategy_s6 = _strategy_s6()
    # The C family must keep byte-for-byte identical meshes, and
    # total * linspace(0, 1, n) is not the same in floating point as
    # linspace(0, total, n).
    for total, count in ((1.0, 29), (0.4946, 75), (2.27, 97)):
        got = strategy_s6._stretched_arc_targets(total, count, 0.0, True)
        assert np.array_equal(got, np.linspace(0.0, total, count))


def test_clustering_refines_toward_the_requested_end():
    strategy_s6 = _strategy_s6()
    at_end = strategy_s6._stretched_arc_targets(1.0, 21, 2.2, True)
    spacing = np.diff(at_end)
    assert spacing[-1] < spacing[0]
    assert at_end[0] == pytest.approx(0.0)
    assert at_end[-1] == pytest.approx(1.0)
    at_start = strategy_s6._stretched_arc_targets(1.0, 21, 2.2, False)
    spacing = np.diff(at_start)
    assert spacing[0] < spacing[-1]
    assert at_start[0] == pytest.approx(0.0)
    assert at_start[-1] == pytest.approx(1.0)


def test_candidate_d_family_resolves_the_wrap_better_than_every_c_level():
    strategy_s6 = _strategy_s6()
    report = json.loads(
        (ROOT / "reports/m2_leading_edge_wrap_redesign_20260903.json").read_text()
    )
    turning = report["candidate_d_family"]["comparison_with_c_family"]["turning_per_cell_deg"]
    assert max(turning[d] for d in ("d01", "d02", "d03")) < min(
        turning[c] for c in ("c01", "c02", "c03")
    )
    for name in ("candidate_d01", "candidate_d02", "candidate_d03"):
        spec = strategy_s6.LEVELS[name]
        assert spec.end_scale == 1.0
        assert spec.le_cluster == 2.2


def test_candidate_d_family_is_not_presented_as_qualified():
    report = json.loads(
        (ROOT / "reports/m2_leading_edge_wrap_redesign_20260903.json").read_text()
    )
    assert report["candidate_d_family"]["status"] == (
        "SURFACE_QUALIFIED_VOLUME_MARCH_UNRESOLVED"
    )
    assert report["authorizes_cfd"] is False
    open_findings = [
        f for f in report["volume_march_sweep"]["findings"] if f.get("severity") == "OPEN"
    ]
    assert open_findings, "the unresolved d03 march must stay recorded as open"


def test_no_probe_levels_leak_into_the_governed_tables():
    strategy_s6 = _strategy_s6()
    from aeris.cfd.meshing.pyhyp_options import GRID_LEVELS
    from resolution import S6_FIRST_CELL_FRACTION

    for table in (strategy_s6.LEVELS, GRID_LEVELS, S6_FIRST_CELL_FRACTION):
        assert not [name for name in table if name.startswith("probe_")]


def _census():
    return json.loads(
        (ROOT / "reports/m2_leading_edge_wrap_census_20260903.json").read_text()
    )


def test_census_covers_every_surface_mesh_in_the_study():
    census = _census()
    # The census stores repo-relative paths; ROOT here is absolute.
    repo = ROOT.parents[1]
    on_disk = sorted(
        str(p.relative_to(repo)) for p in ROOT.parents[0].rglob("surface_blocks.npz")
    )
    recorded = sorted(m["path"] for m in census["meshes"])
    assert recorded == on_disk, "the census must cover every mesh, with none added or dropped"
    assert census["census"]["meshes_screened"] == len(on_disk)


def test_no_existing_mesh_resolves_the_leading_edge():
    cfd_qc = _cfd_qc()
    census = _census()
    assert census["census"]["meshes_meeting_target"] == 0
    # Re-measure a sample rather than trusting the stored numbers alone.
    repo = ROOT.parents[1]
    for record in census["meshes"][:5]:
        measured = cfd_qc.leading_edge_wrap_resolution(repo / record["path"])
        assert measured["wrap_cells"] == record["wrap_cells"]
        assert measured["turning_per_cell_deg"]["median"] == pytest.approx(
            record["median_turning_per_cell_deg"]
        )
        assert measured["turning_per_cell_deg"]["median"] > census["method"][
            "target_deg_per_cell"
        ]


def test_the_defect_predates_s6():
    census = _census()
    studies = census["census"]["by_study"]
    # S1_tip_first is the earliest strategy study; if it is clean the defect
    # would be S6's doing, and it is not.
    s1 = next(k for k in studies if k.startswith("S1"))
    assert studies[s1]["min_deg_per_cell"] > census["method"]["target_deg_per_cell"]
    assert studies[s1]["meshes"] > 0


def test_census_does_not_overclaim_the_consequence():
    census = _census()
    status = census["evidence_status"]
    # Impossible pressure was shown on the two CFD runs only; the rest is cause,
    # not demonstrated effect.
    assert status["consequence_demonstrated_count"] == 2
    assert status["cause_measured_on_all"] == census["census"]["meshes_screened"]
    assert "not claimed" in status["honest_limitation"]
    assert census["authorizes_cfd"] is False


def test_corner_cut_measures_the_geometric_error_at_the_nose():
    sys.path.insert(0, str(ROOT / "viz"))
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "aeris_viz", ROOT / "viz/build_inspector.py"
    )
    viz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(viz)

    # A quarter circle of unit radius sampled with n points: the straight
    # segments fall inside the arc by a sagitta with a known closed form.
    for points in (5, 9, 17):
        theta = np.linspace(0.0, np.pi / 2.0, points)
        arc = np.stack(
            [np.cos(theta), np.zeros_like(theta), np.sin(theta)], axis=-1
        )
        half_angle = (np.pi / 2.0) / (points - 1) / 2.0
        expected = 1.0 - np.cos(half_angle)
        assert viz.corner_cut(arc) == pytest.approx(expected, rel=1e-6)


def test_inspector_is_self_contained_and_carries_real_geometry():
    import re

    page = (ROOT / "viz/leading_edge_inspector.html").read_text()
    # Self-contained: no network fetches, nothing left to resolve at open time.
    assert "/*__MESH_DATA__*/null" not in page, "mesh data was never substituted"
    assert "src=\"http" not in page and "href=\"http" not in page
    data = json.loads(re.search(r"const MESH = (\{.*?\});", page, re.S).group(1))

    assert len(data["stations"]) >= 5
    assert set(data["levels"]) >= {"C01", "C02", "C03", "D03"}
    for name, level in data["levels"].items():
        assert len(level["sections"]) == len(data["stations"]), name
        assert len(level["metrics"]) == len(data["stations"]), name
        for section in level["sections"]:
            assert "oml_nose" in section, name
            assert len(section["oml_nose"]) == level["wrap_cells"] + 1, name

    # Coarser wrap means a bigger corner cut, monotonically, at every station.
    order = ["C01", "C02", "C03", "D03"]
    for index in range(len(data["stations"])):
        cuts = [data["levels"][n]["metrics"][index]["cut"] for n in order]
        assert cuts == sorted(cuts, reverse=True), data["stations"][index]
    assert data["levels"]["C03"]["wrap_cells"] == 4
    assert data["levels"]["D03"]["wrap_cells"] == 6
