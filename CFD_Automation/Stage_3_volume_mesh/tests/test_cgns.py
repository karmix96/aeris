import numpy as np
import pytest

from cfdauto.volume import cgns
from cfdauto.volume import topology as tp


def two_blocks():
    """A small two-block box: A (x 0..1) and B (x 1..2) matched at x = 1 with a transposed, reversed index order.
    A: i +x, j +y, k +z. B: i +z, j +y, k -x (right-handed), so A.iMax = B.kMax with (j, k) of A = (j, i) of B."""
    xa, ya, za = np.linspace(0, 1, 5), np.linspace(0, 1, 4) ** 1.5, np.linspace(0, 1, 3)
    A = np.stack(np.meshgrid(xa, ya, za, indexing="ij"), -1)
    xb = np.linspace(2, 1, 6)                              # k runs -x
    B = np.empty((3, 4, 6, 3))
    for i, z in enumerate(za):
        for j, y in enumerate(ya):
            B[i, j, :, 0], B[i, j, :, 1], B[i, j, :, 2] = xb, y, z
    blocks = {"A": A, "B": B}
    bcs = {"A": {"iMin": tp.FAR, "jMin": tp.WALL, "jMax": tp.FAR, "kMin": tp.SYM, "kMax": tp.FAR},
           "B": {"iMin": tp.FAR, "iMax": tp.FAR, "jMin": tp.WALL, "jMax": tp.FAR, "kMin": tp.FAR}}
    return blocks, bcs, [("A", "iMax", "B", "kMax")]


def test_right_handed_fixture():
    for X in two_blocks()[0].values():
        e = [np.diff(X, axis=a)[(0,) * 3] for a in range(3)]
        assert np.dot(np.cross(e[0], e[1]), e[2]) > 0


def test_one_to_one_transform():
    blocks, _, itf = two_blocks()
    m = cgns.one_to_one(blocks, "A", "iMax", "B", "kMax")
    # A's i (normal, out of A at iMax) goes into B along -k from its kMax face: -3; A's j = B's j; A's k = B's i
    assert m["transform"].tolist() == [-3, 2, 1]
    assert m["range"].tolist() == [[5, 1, 1], [5, 4, 3]]
    assert m["donor_range"].tolist() == [[1, 1, 6], [3, 4, 6]]
    back = cgns.one_to_one(blocks, "B", "kMax", "A", "iMax")
    assert back["transform"].tolist() == [3, 2, -1]


def test_adf_file_layout(tmp_path):
    blocks, bcs, itf = two_blocks()
    p = cgns.write_blocks(blocks, bcs, itf, tmp_path / "two.cgns")
    raw = p.read_bytes()
    assert len(raw) % cgns.BLOCK == 0
    assert raw[4:32] == b"ADF Database Version A02011>"
    assert raw[186:190] == b"fCbt" and raw[262:266] == b"Fcte" and raw[266:270] == b"NoDe"


def test_roundtrip_own_reader(tmp_path):
    blocks, bcs, itf = two_blocks()
    p = cgns.write_blocks(blocks, bcs, itf, tmp_path / "two.cgns")
    r = cgns.roundtrip_blocks(blocks, bcs, itf, p)
    assert r["passed"], r["problems"]
    assert r["coords_max_error"] == 0.0 and r["one2one"] == 2 and r["version"] == pytest.approx(3.4)


def test_roundtrip_bad_transform_is_caught(tmp_path):
    blocks, bcs, itf = two_blocks()
    root = cgns.cgns_tree(blocks, bcs, itf)
    base = [n for n in root.children if n.label == "CGNSBase_t"][0]
    za = [n for n in base.children if n.name == "A"][0]
    zgc = [n for n in za.children if n.label == "ZoneGridConnectivity_t"][0]
    tr = [n for n in zgc.children[0].children if n.name == "Transform"][0]
    tr.data = np.array([-3, 1, 2], dtype="<i4").tobytes()  # j and k swapped: wrong
    p = tmp_path / "bad.cgns"
    cgns.write_adf(root, p)
    assert not cgns.roundtrip_blocks(blocks, bcs, itf, p)["passed"]


@pytest.mark.skipif(cgns.libcgns() is None, reason="no CGNS library here (ADflow's machine has one)")
def test_libcgns_reads_it(tmp_path):
    blocks, bcs, itf = two_blocks()
    p = cgns.write_blocks(blocks, bcs, itf, tmp_path / "two.cgns")
    r = cgns.libcgns_check(blocks, bcs, itf, p)
    assert r["passed"], r["problems"]
    assert r["zones"] == 2 and r["one2one"] == 2


def test_volume_mesh_cgns(volume_vc, tmp_path):
    vm = volume_vc
    p = cgns.write_cgns(vm, tmp_path / "volume.cgns")
    r = cgns.roundtrip(vm, p)
    assert r["passed"], r["problems"]
    assert r["zones"] == 13 and r["one2one"] == 2 * len(tp.interfaces(vm.info["cap_upper_face"]))
    if cgns.libcgns() is not None:
        bcs, itf = tp.boundary_conditions(), tp.interfaces(vm.info["cap_upper_face"])
        c = cgns.libcgns_check(vm.blocks, bcs, itf, p)
        assert c["passed"], c["problems"]
