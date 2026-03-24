from pathlib import Path

import pytest

from aeris.aero.views import (
    _extract_native_airplane,
    build_asb_airplane_from_paths,
)


class DummyAirplane:
    def __init__(self):
        self.wings = [type("Wing", (), {"xsecs": [type("X", (), {"chord": 1.0, "xyz_le": [0, 0, 0]})(),
                                                 type("X", (), {"chord": 1.0, "xyz_le": [0, 1, 0]})()]})()]
        self.s_ref = 10.0
        self.b_ref = 5.0
        self.c_ref = 2.0


def _write_sections_csv(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "idx,y_span_m,le_x_m,chord_m,twist_deg_segment,dihedral_deg_segment\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )


def _write_airfoil(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "foil\n0.0 0.0\n0.5 0.1\n1.0 0.0\n",
        encoding="utf-8",
    )


def test_extract_native_airplane_from_attribute():
    airplane = DummyAirplane()
    case = type("Case", (), {"airplane": airplane})()
    assert _extract_native_airplane(case) is airplane


def test_build_asb_airplane_from_paths_raises_on_missing_airfoil(tmp_path: Path):
    csv_path = tmp_path / "airfoils" / "openvsp_sections.csv"
    airfoil_dir = tmp_path / "airfoils" / "xfoil"

    _write_sections_csv(
        csv_path,
        [
            "0,0.0,0.0,1.0,0.0,0.0",
            "1,1.0,0.1,0.8,0.0,0.0",
        ],
    )
    airfoil_dir.mkdir(parents=True, exist_ok=True)
    _write_airfoil(airfoil_dir / "airfoil_000_y0.0000m.dat")

    with pytest.raises(FileNotFoundError):
        build_asb_airplane_from_paths(csv_path, airfoil_dir)


def test_build_asb_airplane_from_paths_raises_on_duplicate_span_station(tmp_path: Path):
    csv_path = tmp_path / "airfoils" / "openvsp_sections.csv"
    airfoil_dir = tmp_path / "airfoils" / "xfoil"

    _write_sections_csv(
        csv_path,
        [
            "0,0.0,0.0,1.0,0.0,0.0",
            "1,0.0,0.1,0.8,0.0,0.0",
        ],
    )
    _write_airfoil(airfoil_dir / "airfoil_000_y0.0000m.dat")
    _write_airfoil(airfoil_dir / "airfoil_001_y0.0000m.dat")

    with pytest.raises(RuntimeError, match="Duplicate span stations"):
        build_asb_airplane_from_paths(csv_path, airfoil_dir)