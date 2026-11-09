"""One VC mesh (BWB reference wing 0, Re 3e5): every check, the wall, the counter (about 20 s)."""
import numpy as np
import pytest


def test_passes_every_check(volume_vc):
    assert volume_vc.outcome == "passed", [(c.name, c.value, c.limit) for c in volume_vc.failed()]
    assert {c.n for c in volume_vc.checks} == {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14}


def test_wall_is_the_stage2_surface(volume_vc, surface_vc):
    B = volume_vc.blocks
    ring = np.concatenate([B["CU_in"][:, 0], B["CN_in"][1:, 0], B["CL_in"][1:, 0]], 0)
    n_air = 2 * surface_vc.info["n_side"] - 1
    assert np.array_equal(ring, surface_vc.wing[:n_air])
    assert np.array_equal(B["CAP"][:, :, 0], surface_vc.cap)


def test_tip_plane_is_shared(volume_vc):
    B = volume_vc.blocks
    for n in ("WU", "CU", "CN", "CL", "WL", "B"):
        assert np.array_equal(B[f"{n}_in"][:, :, -1], B[f"{n}_out"][:, :, 0])


def test_counter_matches_the_build(volume_vc, surface_vc):
    from cfdauto.volume.volume import count_volume
    c = count_volume(surface_vc)
    assert c["cells"] == pytest.approx(volume_vc.cells, rel=0.02)


def test_refusal_writes_only_refusal(volume_vc, bwb, tmp_path):
    import copy
    from cfdauto.volume.checks import Check
    from cfdauto.volume.volume import write
    vm = copy.copy(volume_vc)
    vm.checks = list(volume_vc.checks) + [Check(99, "forced", False, 1.0, "test")]
    out = write(vm, bwb, tmp_path / "m")
    assert sorted(p.name for p in out.iterdir()) == ["refusal.json"]


def test_wake_first_cell_option(surface_vc, tmp_path):
    """Decision 105's counted option: the first cell behind the base = the wing's last chordwise cell (default s0)."""
    import numpy as np
    import yaml
    from pathlib import Path
    from cfdauto.volume.laws import CONFIG, rules
    from cfdauto.volume.volume import count_volume, stations_of, wake_first_cells
    raw = yaml.safe_load(Path(CONFIG).read_text())
    raw["wake"]["first_cell"] = "te_cell"
    p = tmp_path / "te.yaml"
    p.write_text(yaml.safe_dump(raw))
    rl0, rl1 = rules("VC"), rules("VC", p)
    sts = stations_of(surface_vc, rl0)
    a, b = wake_first_cells(sts, rl0), wake_first_cells(sts, rl1)
    assert np.allclose(a, [s.s0 for s in sts])
    assert np.all(b >= a) and np.all(np.array([s.te_cell for s in sts]) < 0.01 * np.array([s.chord for s in sts]))
    assert count_volume(surface_vc, "VC", 3e5, p)["n_wake"] < count_volume(surface_vc)["n_wake"]
    raw["wake"]["first_cell"] = "nonsense"
    q = tmp_path / "bad.yaml"                          # a new file: the rules loader caches by path
    q.write_text(yaml.safe_dump(raw))
    import pytest
    with pytest.raises(ValueError):
        wake_first_cells(sts, rules("VC", q))
