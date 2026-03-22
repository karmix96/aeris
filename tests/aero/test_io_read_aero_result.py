import json

from aeris.aero.io import read_aero_result


def test_read_aero_result_from_nested_aero_dir(tmp_path):
    aero_dir = tmp_path / "aero"
    aero_dir.mkdir(parents=True)
    payload = {"Xnp": 0.8, "mac_m": 0.4, "Cma": -0.5}
    (aero_dir / "aero_result.json").write_text(json.dumps(payload), encoding="utf-8")

    loaded = read_aero_result(tmp_path)
    assert loaded["Xnp"] == 0.8