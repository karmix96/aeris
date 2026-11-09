from cfdauto.volume import topology as tp


def test_every_face_owned_once():
    shapes = {n: (3, 3, 3) for n in tp.block_names()}
    for cap_upper in ("jMin", "jMax"):
        assert tp.check_complete(shapes, cap_upper) == []


def test_counts():
    assert len(tp.block_names()) == 13
    assert len(tp.interfaces()) == 2 * 6 + 6 + 4
    n_bc = sum(len(f) for f in tp.boundary_conditions().values())
    assert n_bc + 2 * len(tp.interfaces()) == 13 * 6
