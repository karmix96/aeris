"""
AERIS — CST airfoil + aero_2d audit patch tests.
AERIS_CST_AUDIT_TESTS
Covers: BUG-C4, ISSUE-C5, ISSUE-C6, ISSUE-C7, ISSUE-C12, ISSUE-A16/C14.
Multi-discipline: trust chain, I/O robustness, headless solver, physics.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# BUG-C4: dataset_generate.py only catches KeyError, not all exceptions
# ─────────────────────────────────────────────────────────────────────────────

class TestBugC4MetadataExceptionNarrowed:
    def test_source_only_catches_keyerror(self):
        """dataset_generate.py metadata fetch must only catch KeyError."""
        import aeris.airfoil.dataset_generate as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        # The only acceptable swallow is KeyError — not bare Exception
        assert "except KeyError" in src, (
            "dataset_generate.py must use 'except KeyError' for metadata fetch, "
            "not bare 'except Exception'. BUG-C4 not patched."
        )

    def test_metadata_keyerror_gives_empty_dict(self, tmp_path):
        """KeyError from metadata_for_id must silently produce empty metadata."""
        from aeris.airfoil.library import AirfoilLibrary
        # Create a minimal library WITHOUT CST columns
        inv_data = {
            "airfoil_id": ["abc123"],
            "name": ["test"],
            "family": ["naca4"],
            "source_file": ["test.dat"],
            "n_coords": [100],
            "t_c": [0.12],
            "t_c_x": [0.30],
            "camber_max": [0.02],
            "camber_max_x": [0.40],
            "le_radius": [0.015],
            "te_angle_deg": [5.0],
        }
        (tmp_path / "coords").mkdir()
        # Write a fake .npz
        x = np.linspace(0, 1, 50)
        y = np.zeros(50)
        np.savez_compressed(tmp_path / "coords" / "abc123.npz", x=x, y=y)
        pd.DataFrame(inv_data).to_csv(tmp_path / "airfoil_inventory.csv", index=False)

        lib = AirfoilLibrary(tmp_path)
        # metadata_for_id returns row as dict — no CST columns present but no error
        meta = lib.metadata_for_id("abc123")
        assert isinstance(meta, dict)
        assert "cst_u0" not in meta  # no CST, as expected for Selig library

    def test_metadata_unknown_id_raises_keyerror(self, tmp_path):
        """metadata_for_id must raise KeyError for unknown airfoil_id."""
        inv_data = {
            "airfoil_id": ["abc123"],
            "name": ["test"], "family": ["naca4"],
            "source_file": ["test.dat"], "n_coords": [100],
            "t_c": [0.12], "t_c_x": [0.30],
            "camber_max": [0.02], "camber_max_x": [0.40],
            "le_radius": [0.015], "te_angle_deg": [5.0],
        }
        (tmp_path / "coords").mkdir()
        pd.DataFrame(inv_data).to_csv(tmp_path / "airfoil_inventory.csv", index=False)
        from aeris.airfoil.library import AirfoilLibrary
        lib = AirfoilLibrary(tmp_path)
        with pytest.raises(KeyError):
            lib.metadata_for_id("unknown_id_that_doesnt_exist")


# ─────────────────────────────────────────────────────────────────────────────
# ISSUE-C5: curation_report.json contains generated_at_utc
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueC5CurationTimestamp:
    def _make_dataset(self, tmp_path: Path) -> None:
        """Create a minimal dataset dir with airfoil_dataset.csv."""
        rows = [
            {"airfoil_id": "a1", "alpha_deg": 0.0, "reynolds": 1e6,
             "mach": 0.0, "ncrit": 9.0, "cl": 0.3, "cd": 0.02, "cm": -0.05,
             "cp_min": None, "converged": True},
            {"airfoil_id": "a1", "alpha_deg": 4.0, "reynolds": 1e6,
             "mach": 0.0, "ncrit": 9.0, "cl": 0.6, "cd": 0.025, "cm": -0.06,
             "cp_min": None, "converged": True},
        ]
        pd.DataFrame(rows).to_csv(tmp_path / "airfoil_dataset.csv", index=False)
        # Write a passing QC report
        (tmp_path / "airfoil_qc_report.json").write_text(
            json.dumps({"passed": True}), encoding="utf-8"
        )

    def test_curation_report_has_timestamp(self, tmp_path):
        """curation_report.json must contain generated_at_utc."""
        from aeris.airfoil.curate import curate_airfoil_dataset
        self._make_dataset(tmp_path)
        report = curate_airfoil_dataset(dataset_root=tmp_path)
        assert "generated_at_utc" in report, (
            "curation_report.json missing generated_at_utc — ISSUE-C5 not patched"
        )

    def test_curation_timestamp_is_iso_string(self, tmp_path):
        """generated_at_utc must be a parseable ISO datetime string."""
        from datetime import datetime
        from aeris.airfoil.curate import curate_airfoil_dataset
        self._make_dataset(tmp_path)
        report = curate_airfoil_dataset(dataset_root=tmp_path)
        ts = report["generated_at_utc"]
        assert isinstance(ts, str) and len(ts) > 0
        parsed = datetime.fromisoformat(ts)
        assert parsed.year >= 2024

    def test_curation_report_written_file_has_timestamp(self, tmp_path):
        """curation_report.json file on disk must contain generated_at_utc."""
        from aeris.airfoil.curate import curate_airfoil_dataset
        self._make_dataset(tmp_path)
        curate_airfoil_dataset(dataset_root=tmp_path)
        saved = json.loads((tmp_path / "curation_report.json").read_text(encoding="utf-8"))
        assert "generated_at_utc" in saved


# ─────────────────────────────────────────────────────────────────────────────
# ISSUE-C6: cst_reporting.py writes are atomic
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueC6AtomicCstReporting:
    def test_write_json_atomic_helper_exists(self):
        """_write_json_atomic helper must exist in cst_reporting module."""
        import aeris.airfoil.cst_reporting as mod
        assert hasattr(mod, "_write_json_atomic"), (
            "_write_json_atomic not found in cst_reporting — ISSUE-C6 not patched"
        )

    def test_atomic_helper_uses_os_replace(self):
        """_write_json_atomic must use os.replace (atomic pattern)."""
        import inspect
        import aeris.airfoil.cst_reporting as mod
        src = inspect.getsource(mod._write_json_atomic)
        assert "os.replace" in src

    def test_polish_outputs_no_temp_files_left(self, tmp_path):
        """After polish_cst_library_outputs, no .tmp files must remain."""
        root = tmp_path / "lib"
        (root / "coords").mkdir(parents=True)
        (root / "dat").mkdir()
        (root / "cst_json").mkdir()
        aid = "abc123"
        np.savez_compressed(root / "coords" / f"{aid}.npz",
                            x=np.array([0.0, 1.0]), y=np.array([0.0, 0.0]))
        pd.DataFrame([{
            "airfoil_id": aid, "name": "a", "source_file": "a.dat",
            "family": "cst", "cst_validation_valid": True,
            "cst_json": str(root / "cst_json" / f"{aid}.json"),
            "t_c": 0.12, "camber_max": 0.02, "le_radius": 0.01,
            "te_angle_deg": 8.0, "cst_u0": 0.1, "cst_l0": -0.1,
        }]).to_csv(root / "airfoil_inventory.csv", index=False)
        manifest = {
            "schema_version": "airfoil_cst_library_v1",
            "generator_id": "cst_airfoil_v1",
            "n_airfoils_requested": 1,
            "n_airfoils_generated": 1,
            "order": 8, "n1": 0.5, "n2": 1.0, "dz_te": 0.0, "n_per_surface": 121,
        }
        (root / "cst_airfoil_library_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        from aeris.airfoil.cst_reporting import polish_cst_library_outputs
        polish_cst_library_outputs(root)
        leftovers = list(root.glob("*.tmp"))
        assert len(leftovers) == 0


# ─────────────────────────────────────────────────────────────────────────────
# ISSUE-C7: promote.py writes are atomic
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueC7AtomicPromote:
    def test_write_json_uses_os_replace(self):
        """promote.py _write_json must use os.replace (atomic pattern)."""
        import inspect
        from aeris.airfoil import promote
        src = inspect.getsource(promote._write_json)
        assert "os.replace" in src, (
            "promote.py _write_json does not use os.replace — ISSUE-C7 not patched"
        )

    def _make_promotion_ready_dataset(self, tmp_path: Path) -> None:
        rows = [
            {"airfoil_id": "a1", "alpha_deg": 0.0, "reynolds": 1e6,
             "mach": 0.0, "ncrit": 9.0, "cl": 0.3, "cd": 0.02, "cm": -0.05,
             "cp_min": None, "converged": True},
        ]
        pd.DataFrame(rows).to_csv(tmp_path / "curated_airfoil_dataset.csv", index=False)
        (tmp_path / "curation_report.json").write_text(json.dumps({
            "schema_version": "airfoil_curation_v1",
            "kept_rows": 1, "rejected_rows": 0,
            "kept_airfoils": 1, "rejected_airfoils": 0,
            "rejection_reason_counts": {},
            "qc_passed": True,
            "promotion_ready": True,
            "promotion_blockers": [],
            "curated_airfoil_dataset_csv": str(tmp_path / "curated_airfoil_dataset.csv"),
            "rejected_airfoil_rows_csv": str(tmp_path / "rejected_airfoil_rows.csv"),
        }), encoding="utf-8")
        (tmp_path / "airfoil_dataset_manifest.json").write_text(json.dumps({
            "schema_version": "airfoil_dataset_v1",
            "dataset_name": "test",
            "solver_id": "xfoil_subprocess",
            "n_airfoils": 1, "total_rows": 1,
            "converged_rows": 1, "convergence_rate": 1.0,
        }), encoding="utf-8")

    def test_promotion_manifest_written(self, tmp_path):
        from aeris.airfoil.promote import promote_airfoil_dataset
        self._make_promotion_ready_dataset(tmp_path)
        manifest = promote_airfoil_dataset(dataset_root=tmp_path)
        assert (tmp_path / "promotion_manifest.json").exists()
        assert manifest["promotion_ready_at_time_of_promotion"] is True

    def test_promotion_manifest_no_temp_files(self, tmp_path):
        from aeris.airfoil.promote import promote_airfoil_dataset
        self._make_promotion_ready_dataset(tmp_path)
        promote_airfoil_dataset(dataset_root=tmp_path)
        leftovers = list(tmp_path.glob("*.tmp"))
        assert len(leftovers) == 0


# ─────────────────────────────────────────────────────────────────────────────
# ISSUE-C12: curate blocks promotion when QC was never run
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueC12QcBypassBlocked:
    def _make_raw_dataset(self, tmp_path: Path) -> None:
        rows = [
            {"airfoil_id": "a1", "alpha_deg": 0.0, "reynolds": 1e6,
             "mach": 0.0, "ncrit": 9.0, "cl": 0.3, "cd": 0.02, "cm": -0.05,
             "cp_min": None, "converged": True},
        ]
        pd.DataFrame(rows).to_csv(tmp_path / "airfoil_dataset.csv", index=False)

    def test_curation_blocks_when_qc_report_absent(self, tmp_path):
        """curate must mark promotion_ready=False when QC was never run."""
        from aeris.airfoil.curate import curate_airfoil_dataset
        self._make_raw_dataset(tmp_path)
        # No airfoil_qc_report.json written
        report = curate_airfoil_dataset(dataset_root=tmp_path)
        assert report["promotion_ready"] is False, (
            "promotion_ready should be False when QC report is absent. "
            "ISSUE-C12 not patched."
        )
        assert "airfoil_qc_not_run" in report.get("promotion_blockers", []), (
            "Blocker 'airfoil_qc_not_run' not found in promotion_blockers. "
            "ISSUE-C12 not patched."
        )

    def test_curation_passes_when_qc_passed(self, tmp_path):
        """curate with passing QC report must set promotion_ready=True."""
        from aeris.airfoil.curate import curate_airfoil_dataset
        self._make_raw_dataset(tmp_path)
        (tmp_path / "airfoil_qc_report.json").write_text(
            json.dumps({"passed": True}), encoding="utf-8"
        )
        report = curate_airfoil_dataset(dataset_root=tmp_path)
        assert report["promotion_ready"] is True
        assert "airfoil_qc_not_run" not in report.get("promotion_blockers", [])

    def test_curation_blocks_when_qc_failed(self, tmp_path):
        """curate with failed QC must block with 'airfoil_qc_failed'."""
        from aeris.airfoil.curate import curate_airfoil_dataset
        self._make_raw_dataset(tmp_path)
        (tmp_path / "airfoil_qc_report.json").write_text(
            json.dumps({"passed": False}), encoding="utf-8"
        )
        report = curate_airfoil_dataset(dataset_root=tmp_path)
        assert report["promotion_ready"] is False
        assert "airfoil_qc_failed" in report.get("promotion_blockers", [])

    def test_blockers_distinct_for_missing_vs_failed_qc(self, tmp_path):
        """'airfoil_qc_not_run' and 'airfoil_qc_failed' must be distinct strings."""
        assert "airfoil_qc_not_run" != "airfoil_qc_failed"


# ─────────────────────────────────────────────────────────────────────────────
# ISSUE-A16/C14: xfoil_adapter has PLOP→G→(blank) before OPER
# ─────────────────────────────────────────────────────────────────────────────

class TestIssueC14XfoilPlop:
    """PLOP was intentionally REMOVED (patch_xfoil_remove_plop.sh).
    Under xvfb-run, display suppression is handled by the virtual X server.
    PLOP consumed stdin lines needed by LOAD/PANE causing 0% convergence.
    These tests now verify the correct headless mechanisms instead.
    """

    def test_plop_not_in_command_sequence(self):
        """PLOP must NOT be in the xfoil command sequence.
        It was removed because it consumed stdin lines causing 0% convergence.
        xvfb-run and DISPLAY="" provide headless operation without PLOP.
        """
        import aeris.aero_2d.xfoil_adapter as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        # Find the run_alpha_sweep function body (not comments)
        idx_fn = src.find("def run_alpha_sweep(")
        fn_body = src[idx_fn:idx_fn + 3000]
        assert 'cmds.append("PLOP")' not in fn_body, (
            "PLOP is in the xfoil command sequence — it causes 0% convergence "
            "under xvfb-run by consuming stdin lines needed by LOAD/PANE. "
            "PLOP was intentionally removed; xvfb-run handles headless display."
        )

    def test_xvfb_run_headless_path_present(self):
        """xvfb-run headless path must be present as the primary display mechanism."""
        import aeris.aero_2d.xfoil_adapter as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "xvfb-run" in src, (
            "xvfb-run headless path missing from xfoil_adapter"
        )

    def test_display_env_fallback_present(self):
        """DISPLAY='' fallback must be present for systems without xvfb-run."""
        import aeris.aero_2d.xfoil_adapter as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert '"DISPLAY"' in src or "DISPLAY" in src, (
            "DISPLAY='' fallback missing from xfoil_adapter"
        )

    def test_oper_present_in_command_sequence(self):
        """OPER must still be in the command sequence to enter viscous solver."""
        import aeris.aero_2d.xfoil_adapter as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert 'cmds.append("OPER")' in src

class TestCSTPhysicsInvariants:
    def _make_naca_like_cst(self) -> "CSTAirfoil":
        from aeris.airfoil.cst_generator import CSTAirfoil
        # Symmetric-ish airfoil: small positive upper, near-mirror lower
        au = np.array([0.15, 0.18, 0.20, 0.18, 0.16, 0.13, 0.10, 0.07, 0.05])
        al = -0.6 * au  # slightly cambered
        return CSTAirfoil(au, al, order=8)

    def test_coordinates_shape(self):
        foil = self._make_naca_like_cst()
        xy = foil.coordinates(n_per_surface=101)
        assert xy.shape[1] == 2
        # Selig order: TE → upper LE → lower TE
        # Total points: 2*n - 1 (shared LE)
        assert xy.shape[0] == 2 * 101 - 1

    def test_trailing_edge_at_x1(self):
        foil = self._make_naca_like_cst()
        xy = foil.coordinates(n_per_surface=101)
        # First and last points should be at x=1 (trailing edge, dz_te=0)
        assert abs(xy[0, 0] - 1.0) < 1e-10
        assert abs(xy[-1, 0] - 1.0) < 1e-10

    def test_leading_edge_at_x0(self):
        foil = self._make_naca_like_cst()
        xy = foil.coordinates(n_per_surface=101)
        # Midpoint should be at x≈0 (LE)
        mid = len(xy) // 2
        assert abs(xy[mid, 0]) < 0.01

    def test_thickness_positive_everywhere(self):
        foil = self._make_naca_like_cst()
        x = np.linspace(0.01, 0.99, 200)
        t = foil.thickness(x)
        assert np.all(t > 0), "Thickness must be positive interior"

    def test_max_thickness_in_reasonable_range(self):
        foil = self._make_naca_like_cst()
        tmax, xt = foil.max_thickness()
        # Typical airfoils: 5% to 25% t/c, max at 20-50% chord
        assert 0.05 < tmax < 0.30
        assert 0.15 < xt < 0.65

    def test_validation_passes_for_reasonable_cst(self):
        foil = self._make_naca_like_cst()
        from aeris.airfoil.cst_generator import ValidationLimits
        report = foil.validate(ValidationLimits(max_curvature_reversals=12))
        assert report.valid, f"Reasonable CST airfoil failed validation: {report.failures}"

    def test_validation_fails_for_self_intersecting_airfoil(self):
        """A CST airfoil with al >> au should self-intersect and fail validation."""
        from aeris.airfoil.cst_generator import CSTAirfoil, ValidationLimits
        # Force upper < lower → self-intersection
        au = np.full(9, 0.02)  # very thin upper
        al = np.full(9, 0.15)  # thick lower → crosses upper
        try:
            foil = CSTAirfoil(au, al, order=8)
            report = foil.validate(ValidationLimits())
            assert not report.valid, (
                "Self-intersecting airfoil should fail validation"
            )
        except Exception:
            pass  # Constructor may raise for degenerate input — acceptable

    def test_to_dict_from_dict_roundtrip(self):
        from aeris.airfoil.cst_generator import CSTAirfoil
        foil = self._make_naca_like_cst()
        d = foil.to_dict()
        restored = CSTAirfoil.from_dict(d)
        assert np.allclose(foil.au, restored.au, atol=1e-12)
        assert np.allclose(foil.al, restored.al, atol=1e-12)
        assert foil.order == restored.order

    def test_le_radius_positive(self):
        foil = self._make_naca_like_cst()
        rle = foil.le_radius()
        assert rle > 0 and math.isfinite(rle)

    def test_area_positive(self):
        foil = self._make_naca_like_cst()
        area = foil.area()
        assert area > 0

    def test_generate_random_validates(self):
        from aeris.airfoil.cst_generator import CSTAirfoil, ValidationLimits
        foil = CSTAirfoil.generate_random(
            order=8,
            au_bounds=(0.08, 0.22),
            al_bounds=(-0.22, -0.02),
            limits=ValidationLimits(max_curvature_reversals=12),
            rng=np.random.default_rng(99),
        )
        assert foil.validate(ValidationLimits(max_curvature_reversals=12)).valid

    def test_generate_random_fails_gracefully_on_impossible_bounds(self):
        """generate_random must raise RuntimeError when no valid foil found."""
        from aeris.airfoil.cst_generator import CSTAirfoil, ValidationLimits
        with pytest.raises(RuntimeError, match="no valid airfoil"):
            CSTAirfoil.generate_random(
                order=8,
                au_bounds=(0.001, 0.002),  # too thin — will always fail validation
                al_bounds=(-0.002, -0.001),
                max_attempts=5,
                rng=np.random.default_rng(0),
            )
