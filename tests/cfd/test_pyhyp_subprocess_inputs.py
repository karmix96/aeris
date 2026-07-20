"""Subprocess path writes resolved JSON + a static runner (no baked values)."""

from __future__ import annotations

import json
from pathlib import Path

from aeris.cfd.meshing.pyhyp_options import build_pyhyp_options
from aeris.cfd.options.manifest import EFFECTIVE_OPTIONS_SCHEMA_VERSION
from aeris.mesh.pyhyp_runner import _write_subprocess_runner

CHAR_LEN = 2.27


def _make_surface_dir(tmp_path: Path) -> Path:
    (tmp_path / "surface_report.json").write_text(json.dumps({"characteristic_length": CHAR_LEN}))
    (tmp_path / "surface.fmt").write_text("dummy plot3d\n")
    return tmp_path


def test_runner_is_static_and_options_json_matches_builder(tmp_path: Path):
    surface_dir = _make_surface_dir(tmp_path)
    runner = _write_subprocess_runner(surface_dir, level="smoke", c_max=0.5)

    script = runner.read_text()
    # the runner must bake in nothing: no level table, no numeric recipe
    assert "GRID_LEVELS" not in script
    assert "0.5" not in script
    assert "pyhyp_options.json" in script

    options = json.loads((surface_dir / "pyhyp_options.json").read_text())
    expected = build_pyhyp_options(
        surface_dir.resolve() / "surface.fmt",
        level="smoke",
        characteristic_length=CHAR_LEN,
        output_file=surface_dir.resolve() / "wing_vol_smoke.cgns",
        c_max=0.5,
    ).values
    assert options == expected


def test_manifest_records_provenance_and_fingerprint(tmp_path: Path):
    surface_dir = _make_surface_dir(tmp_path)
    _write_subprocess_runner(surface_dir, level="smoke", pyhyp_options={"splay": 0.25, "cMax": 0.9})
    manifest = json.loads((surface_dir / "pyhyp_effective_options.json").read_text())
    assert manifest["schema"] == EFFECTIVE_OPTIONS_SCHEMA_VERSION
    assert manifest["tool"] == "pyhyp"
    assert manifest["options"]["cMax"] == {"value": 0.9, "source": "raw"}
    assert manifest["options"]["splay"] == {"value": 0.25, "source": "raw"}
    assert manifest["options"]["N"]["source"] == "level:smoke"
    assert manifest["options"]["fileType"]["source"] == "aeris-default"
    assert manifest["overridden_curated_keys"] == ["c_max"]
    assert isinstance(manifest["input_sha256"]["surface"], str)


def test_characteristic_length_required(tmp_path: Path):
    (tmp_path / "surface.fmt").write_text("dummy\n")
    try:
        _write_subprocess_runner(tmp_path, level="smoke")
    except ValueError as exc:
        assert "characteristic_length" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError without surface_report.json")
