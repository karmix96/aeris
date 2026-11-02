"""The built surface is the intended wing: numbers checked on every published wing."""

import numpy as np
import pytest

from cfdauto.geometry import airfoils, published_wings as pw, verify
from cfdauto.geometry.loft import build_loft, pygeo_available
from cfdauto.geometry.params import load_config
from cfdauto.geometry.sections import build_wing_sections


def _loft(name, backend="numpy"):
    spec, vec, te, _ = pw.get(name)
    _, st = build_wing_sections(spec, vec, te)
    return build_loft(st, backend=backend), st


@pytest.mark.parametrize("name", pw.names())
def test_published_wing_is_exact(name):
    loft, st = _loft(name)
    assert max(r["max_pct_chord"] for r in verify.section_fidelity(loft, st)) < 0.01
    e = verify.planform_edges(loft, st)
    assert max(e["le_max_pct"], e["te_max_pct"]) < 1e-6
    assert verify.ruled_panels(loft, st) < 1e-6


def test_typo_point_found_and_skipped():
    up, lo = verify._unit_chord(airfoils.raw_points("sc20412"))
    bad = airfoils.suspect_points(lo)
    assert len(bad) == 1 and abs(lo[bad[0], 0] - 0.73) < 1e-3
    for clean in ("naca0012", "sc20414", "onera_m6", "ribes"):
        up, lo = verify._unit_chord(airfoils.raw_points(clean))
        assert len(airfoils.suspect_points(up)) == 0 and len(airfoils.suspect_points(lo)) == 0


def test_any_airfoil_at_any_station():
    cfg = load_config()
    spec = next(iter(cfg.types.values()))
    vec = {v: 0.5 * (lo + hi) for v, (lo, hi) in spec.ranges.items()}
    vec["airfoils"] = ["naca23015", "e387", "sc20412", "naca0009"]
    _, st = build_wing_sections(spec, vec, cfg.te)
    # (an extra blended section may sit where the trailing-edge rule switches; it has "|" in its name)
    assert [s.airfoil.name for s in st if "|" not in s.airfoil.name] == vec["airfoils"]


def test_onera_m6_matches_catia_model():
    pytest.importorskip("gmsh")
    if not verify.M6_CAD.is_file():
        pytest.skip("M6 CAD file not in this checkout")
    loft, _ = _loft("onera_m6")
    r = verify.onera_m6_vs_cad(loft)
    assert r["max_pct_chord"] < 0.05 and r["rms_pct_chord"] < 0.005


@pytest.mark.pygeo
@pytest.mark.skipif(not pygeo_available(), reason="needs pyGeo")
@pytest.mark.parametrize("name", pw.names())
def test_pygeo_and_numpy_lofts_agree(name):
    """Two independent builds of the same surface must give the same points."""
    a, st = _loft(name, "pygeo")
    b, _ = _loft(name, "numpy")
    u = np.linspace(0, 1, 401)
    c = min(s.chord for s in st)
    for v in np.linspace(0, 1, 41):
        vv = np.full_like(u, v)
        assert np.abs(a.upper(u, vv) - b.upper(u, vv)).max() < 1e-6 * c
        assert np.abs(a.lower(u, vv) - b.lower(u, vv)).max() < 1e-6 * c
