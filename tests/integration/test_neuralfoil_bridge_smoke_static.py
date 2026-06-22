from pathlib import Path


def test_neuralfoil_bridge_wiring_is_not_silent() -> None:
    workflow = Path("src/aeris/pipeline/aero_workflows.py").read_text(encoding="utf-8")
    solver = Path("src/aeris/aero/solvers/aerosandbox_avl.py").read_text(encoding="utf-8")
    dataset = Path("src/aeris/dataset/aero_dataset_run.py").read_text(encoding="utf-8")
    commands = Path("src/aeris/commands/dataset.py").read_text(encoding="utf-8")

    assert "viscous_polar_source" in commands
    assert "viscous_polar_re_grid" in commands
    assert "viscous_polar_source=viscous_polar_source_key" in commands
    assert "viscous_polar_re_grid=parsed_viscous_polar_re_grid" in commands

    assert "viscous_polar_source: str" in dataset
    assert "viscous_polar_re_grid: list[float] | None" in dataset
    assert "viscous_polar_source=viscous_polar_source" in dataset
    assert "viscous_polar_re_grid=viscous_polar_re_grid" in dataset

    assert "build_neuralfoil_polar_store_for_segments" in workflow
    assert "Polar bridge active: backend=neuralfoil" in workflow
    assert '"backend": "neuralfoil"' in workflow
    assert '"mach": _bridge_mach' in workflow

    assert "cd_avl_cdtot" in solver
    assert "cd_primary_source" in solver
    assert "polar_bridge_strip_integration" in solver
    assert "result.cd = result.cd_total" in solver
    assert "result.l_over_d = result.cl / result.cd" in solver
