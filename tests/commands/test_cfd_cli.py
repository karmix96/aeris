"""aeris cfd CLI: presets list/show and case dry-run."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from aeris.commands.cfd import cfd_app

runner = CliRunner()


def test_presets_list():
    result = runner.invoke(cfd_app, ["presets", "list"])
    assert result.exit_code == 0, result.output
    for name in ("smoke", "fine", "production"):
        assert name in result.output
    assert "mesh_family" in result.output


def test_presets_show_includes_citation():
    result = runner.invoke(cfd_app, ["presets", "show", "smoke"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["name"] == "smoke"
    assert payload["volume"]["c_max"] == 0.5
    assert "DSE_READINESS" in payload["citation"]


def test_presets_show_unknown_fails():
    result = runner.invoke(cfd_app, ["presets", "show", "nope"])
    assert result.exit_code == 2


def test_run_dry_run_standalone(tmp_path: Path):
    ref = tmp_path / "ref_surface"
    ref.mkdir()
    (ref / "surface.fmt").write_text("dummy\n")
    (ref / "surface_report.json").write_text(json.dumps({"characteristic_length": 2.27}))
    case = tmp_path / "case.yaml"
    case.write_text(
        yaml.safe_dump(
            {
                "schema": "aeris.cfd.case.v1",
                "case": {
                    "name": "cli_t1",
                    "geometry": {"surface_dir": str(ref)},
                    "volume_mesh": {"preset": "smoke"},
                },
            }
        )
    )
    workdir = tmp_path / "run"
    result = runner.invoke(
        cfd_app,
        ["run", str(case), "--dry-run", "--workdir", str(workdir)],
    )
    assert result.exit_code == 0, result.output
    assert (workdir / "surface" / "pyhyp_options.json").is_file()
    assert (workdir / "case_manifest.json").is_file()


def test_run_invalid_case_exits_2(tmp_path: Path):
    case = tmp_path / "case.yaml"
    case.write_text(yaml.safe_dump({"schema": "wrong", "case": {"name": "x"}}))
    result = runner.invoke(cfd_app, ["run", str(case)])
    assert result.exit_code == 2
