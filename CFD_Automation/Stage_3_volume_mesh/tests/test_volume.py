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
    """The first cell behind the base: s0 in rule set 1 (decision 90), the wing's last chordwise cell in rule set 2
    (decision 107), which needs fewer wake nodes; an unknown option is refused."""
    import numpy as np
    import yaml
    from pathlib import Path
    from cfdauto.volume.laws import CONFIG, rules
    from cfdauto.volume.volume import count_volume, stations_of, wake_first_cells
    rules1 = Path(CONFIG).with_name("volume_rules1.yaml")
    rl1, rl2 = rules("VC", rules1), rules("VC")
    sts = stations_of(surface_vc, rl2)
    a, b = wake_first_cells(sts, rl1), wake_first_cells(sts, rl2)
    assert np.allclose(a, [s.s0 for s in sts])
    assert np.allclose(b, [max(s.te_cell, s.s0) for s in sts]) and np.all(b > a)
    assert np.all(np.array([s.te_cell for s in sts]) < 0.01 * np.array([s.chord for s in sts]))
    assert count_volume(surface_vc)["n_wake"] < count_volume(surface_vc, "VC", 3e5, rules1)["n_wake"]
    raw = yaml.safe_load(Path(CONFIG).read_text())
    raw["wake"]["first_cell"] = "nonsense"
    q = tmp_path / "bad.yaml"
    q.write_text(yaml.safe_dump(raw))
    import pytest
    with pytest.raises(ValueError):
        wake_first_cells(sts, rules("VC", q))


def test_span_smooth_moves_only_the_far_parts():
    """Decision 110: the far parts of neighbouring stations move toward each other; the near part is never moved,
    the lines keep their ends and the growth limit; an impossible case is left as it is."""
    from cfdauto.volume.volume import span_smooth
    n, N = 60, 9
    y = np.linspace(0.0, 0.4, N)
    D = np.stack([np.concatenate([[0.0], np.cumsum(1e-3 * (1.18 + 0.004 * k) ** np.arange(n))]) for k in range(N)], 1)
    D *= 80.0 / D[-1]
    start = np.full(N, 3.0)
    out, f = span_smooth(D, y, start, 1.27)
    assert f > 0.0
    near = D < start[None, :]
    assert np.array_equal(out[near], D[near]) and np.allclose(out[-1], D[-1])
    h = np.diff(out, axis=0)
    assert np.all(h > 0.0)
    for k in range(N):
        j = int(np.searchsorted(D[:, k], start[k]))
        r = h[j:, k] / h[j - 1:-1, k]
        assert np.maximum(r, 1.0 / r).max() <= 1.27
    far = (D > 30.0).all(axis=1)
    assert np.abs(np.diff(out[far], axis=1)).max() < 0.7 * np.abs(np.diff(D[far], axis=1)).max()
    same, f0 = span_smooth(D, y, start, 1.0001)          # no ramp can keep this limit: nothing is moved
    assert f0 == 0.0 and np.array_equal(same, D)
