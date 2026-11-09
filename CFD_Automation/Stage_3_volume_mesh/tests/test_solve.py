import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "solve"))
import case as case_mod            # noqa: E402
import read_results as rr          # noqa: E402


@pytest.fixture(scope="module")
def mesh_folder(volume_vc, bwb, tmp_path_factory):
    from cfdauto.volume.volume import write
    return write(volume_vc, bwb, tmp_path_factory.mktemp("mesh") / "m", formats=("npz",))


def test_case_files(mesh_folder, tmp_path):
    c = case_mod.make_case(mesh_folder, 4.0, 0.1, 3e5, tmp_path / "case")
    r = c["references"]
    # unit mean chord (similarity): the half area is the semi-span, to the stations' trapezoid error
    assert r["area_ref_half"] == pytest.approx(r["semi_span"], rel=0.02)
    assert r["mac"] > 0.9 and r["chord_ref"] == 1.0
    opts = json.loads((tmp_path / "case" / "adflow_options.json").read_text())
    assert opts["liftIndex"] == 3 and opts["turbulenceModel"] == "SA" and opts["gridFile"].endswith("volume.cgns")
    for model in ("sa", "sst_lm"):
        t = (tmp_path / "case" / f"su2_{model}.cfg").read_text()
        assert "MARKER_HEATFLUX= ( wall, 0.0 )" in t and "MARKER_SYM= ( symmetry )" in t and "MARKER_FAR= ( farfield )" in t
        assert "AOA= 4.0" in t and "MACH_NUMBER= 0.1" in t and "REYNOLDS_NUMBER= 300000.0" in t
        assert f"REF_AREA= {r['area_ref_half']}" in t
    assert "KIND_TRANS_MODEL= LM" in (tmp_path / "case" / "su2_sst_lm.cfg").read_text()
    assert "KIND_TRANS_MODEL" not in (tmp_path / "case" / "su2_sa.cfg").read_text()


def test_settled_rule():
    n = 2000
    cd = 0.02 + 1e-3 * np.exp(-np.arange(n) / 100)
    cl = 0.3 + 1e-2 * np.exp(-np.arange(n) / 100)
    assert rr.settled(cl, cd)["settled"]
    cd2 = cd + 2e-4 * np.sin(np.arange(n) / 30)            # 4 counts of oscillation: not settled
    assert not rr.settled(cl, cd2)["settled"]
    assert not rr.settled(cl[:100], cd[:100])["settled"]   # too short to judge


def test_read_su2_history(tmp_path):
    n = 1500
    rho = np.linspace(-2, -9, n)
    cl, cd = np.full(n, 0.31), np.full(n, 0.021)
    lines = ['"Inner_Iter","rms[Rho]","CL","CD","CMy"'] + [f"{i},{rho[i]},{cl[i]},{cd[i]},-0.01" for i in range(n)]
    (tmp_path / "history.csv").write_text("\n".join(lines) + "\n")
    r = rr.judge(rr.read_su2(tmp_path))
    assert r["verdict"] == "accepted" and r["orders_dropped"] == pytest.approx(7.0)


def test_peak_memory_sums_the_ranks():
    """Decision 113: the run records its peak memory (every rank) against S8's two laws."""
    import run_adflow              # the solve folder is on the path (top of this file); ADflow is imported in main only

    class Comm:
        def gather(self, x, root=0):
            return [x, x, x]

    m = run_adflow.peak_memory(Comm(), 2_000_000)
    assert m["ranks"] == 3 and m["peak_rss_gib_sum"] == pytest.approx(3 * m["peak_rss_gib_largest_rank"])
    assert m["gib_per_million_cells"] == pytest.approx(m["peak_rss_gib_sum"] / 2.0)
    assert m["law_ank_only_gib"] == pytest.approx(2.69 + 7.23 * 2) and m["law_ank_then_nk_gib"] == pytest.approx(1.51 + 9.46 * 2)
