"""Retention rules for CFD run artifacts (configs/cfd/RETENTION.md)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from aeris.commands.cfd import _prunable_files, cfd_app


def _make_case(root: Path) -> Path:
    surface = root / "sample_00000" / "surface"
    surface.mkdir(parents=True)
    for name in (
        # rule 1 + 2: evidence and reproducibility inputs
        "surface.fmt",
        "surface_report.json",
        "volume_report.json",
        "pyhyp_options.json",
        "pyhyp_effective_options.json",
        "pyhyp_stdout.log",
        "pyhyp_stderr.log",
        "run_pyhyp.py",
        # rule 3: regenerable bulk
        "wing_vol_smoke.cgns",
        "surface.vtk",
        "surface_blocks.npz",
    ):
        (surface / name).write_text(name)
    return surface


def test_inputs_and_evidence_are_never_pruned(tmp_path):
    surface = _make_case(tmp_path)
    victims = {p.name for p in _prunable_files(tmp_path)}
    assert victims == {"wing_vol_smoke.cgns", "surface.vtk", "surface_blocks.npz"}
    # The whole point of rule 2: what remains must still regenerate the mesh.
    for required in ("surface.fmt", "pyhyp_options.json", "run_pyhyp.py"):
        assert required not in victims
        assert (surface / required).is_file()


def test_reports_and_logs_survive(tmp_path):
    _make_case(tmp_path)
    victims = {p.suffix for p in _prunable_files(tmp_path)}
    assert ".json" not in victims
    assert ".log" not in victims


def test_prune_is_dry_run_by_default(tmp_path):
    surface = _make_case(tmp_path)
    result = CliRunner().invoke(cfd_app, ["prune", str(tmp_path)])
    assert result.exit_code == 0
    assert "would delete" in result.stdout
    assert (surface / "wing_vol_smoke.cgns").is_file()


def test_prune_apply_deletes_only_bulk(tmp_path):
    surface = _make_case(tmp_path)
    result = CliRunner().invoke(cfd_app, ["prune", str(tmp_path), "--apply"])
    assert result.exit_code == 0
    assert not (surface / "wing_vol_smoke.cgns").exists()
    assert not (surface / "surface.vtk").exists()
    assert (surface / "surface.fmt").is_file()
    assert (surface / "volume_report.json").is_file()


def test_prune_keeps_one_failure_exemplar(tmp_path):
    surface = _make_case(tmp_path)
    (surface / "wing_vol_smoke.invalid.cgns").write_text("quarantined")
    other = tmp_path / "sample_00001" / "surface"
    other.mkdir(parents=True)
    (other / "wing_vol_smoke.invalid.cgns").write_text("quarantined")

    CliRunner().invoke(cfd_app, ["prune", str(tmp_path), "--apply"])
    survivors = list(tmp_path.rglob("*.invalid.cgns"))
    assert len(survivors) == 1


def test_prune_can_drop_exemplars_too(tmp_path):
    surface = _make_case(tmp_path)
    (surface / "wing_vol_smoke.invalid.cgns").write_text("quarantined")
    CliRunner().invoke(cfd_app, ["prune", str(tmp_path), "--apply", "--no-keep-exemplar"])
    assert not list(tmp_path.rglob("*.invalid.cgns"))
    assert (surface / "surface.fmt").is_file()
