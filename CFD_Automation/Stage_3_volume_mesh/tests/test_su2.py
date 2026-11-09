import numpy as np

from cfdauto.volume import su2
from cfdauto.volume import topology as tp

from test_cgns import two_blocks


def test_weld_shares_the_matched_face():
    blocks, bcs, itf = two_blocks()
    ids, pts, n = su2.weld(blocks, itf)
    assert n == 5 * 4 * 3 + 3 * 4 * 6 - 4 * 3
    # the matched face: A.iMax node (j, k) is B.kMax node (k, j)
    assert np.array_equal(tp.face(ids["A"][..., None], "iMax")[..., 0], tp.face(ids["B"][..., None], "kMax")[..., 0].T)
    assert np.abs(pts[ids["A"]] - blocks["A"]).max() == 0.0


def test_hexes_positive_and_quads_outward():
    blocks, bcs, itf = two_blocks()
    m = su2.mesh(blocks, bcs, itf)
    assert su2._corner_jacobians(m["points"], m["cells"]) > 0
    P, C = m["points"], m["cells"]
    for name, q in m["markers"].items():
        c = su2.bounding_cells(C, q)
        assert np.all(c >= 0)
        X = P[q]
        nrm = np.cross(X[:, 2] - X[:, 0], X[:, 3] - X[:, 1])
        assert np.all(np.einsum("ij,ij->i", nrm, X.mean(1) - P[C[c]].mean(1)) > 0), name
    assert {k: len(v) for k, v in m["markers"].items()} == {"wall": 4 * 2 + 2 * 5, "symmetry": 4 * 3,
                                                            "farfield": 3 * 2 + 4 * 3 + 4 * 2 + 3 * 5 * 2 + 2 * 3 + 2 * 5}


def test_write_read_check(tmp_path):
    blocks, bcs, itf = two_blocks()
    info = su2.write_blocks(blocks, bcs, itf, tmp_path / "two.su2")
    assert info["points"] == 120 and info["cells"] == 54
    r = su2.check_su2(blocks, bcs, itf, tmp_path / "two.su2")
    assert r["passed"], r["problems"]
    text = (tmp_path / "two.su2").read_text()
    assert "NDIME= 3" in text and "MARKER_TAG= wall" in text and "MARKER_TAG= symmetry" in text


def test_check_catches_an_inside_out_cell(tmp_path):
    blocks, bcs, itf = two_blocks()
    p = tmp_path / "two.su2"
    su2.write_blocks(blocks, bcs, itf, p)
    lines = p.read_text().splitlines()
    i = lines.index("NELEM= 54") + 1
    v = lines[i].split()
    v[1:5], v[5:9] = v[5:9], v[1:5]                     # top and bottom swapped: inside out
    lines[i] = " ".join(v)
    p.write_text("\n".join(lines) + "\n")
    r = su2.check_su2(blocks, bcs, itf, p)
    assert not r["passed"]
