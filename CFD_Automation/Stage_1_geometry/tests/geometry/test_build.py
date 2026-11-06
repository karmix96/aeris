import json

import pytest

from cfdauto.geometry import params
from cfdauto.geometry.build import build, input_hash
from cfdauto.geometry.sections import load_airfoil

CFG = params.load_config()


def test_hash_is_content_not_order():
    spec = CFG.types["bwb"]
    vec = params.mid_vector(spec)
    rev = dict(reversed(list(vec.items())))
    assert input_hash(CFG, "bwb", vec) == input_hash(CFG, "bwb", rev)


def test_hash_changes_with_vector_and_type():
    vec = params.mid_vector(CFG.types["bwb"])
    h = input_hash(CFG, "bwb", vec)
    assert h != input_hash(CFG, "bwb", vec | {"twist3_deg": vec["twist3_deg"] + 1e-6})
    assert h != input_hash(CFG, "cranked", vec)


def test_impossible_vector_refused_with_reason(tmp_path):
    vec = params.mid_vector(CFG.types["bwb"]) | {"c4_ratio": -0.1}
    s = build(vec, "bwb", CFG, tmp_path / "w")
    assert not s["passed"] and s["gate"] == "validity" and "chord" in s["reason"]
    assert [p.name for p in (tmp_path / "w").iterdir()] == ["refusal.json"]


def test_nose_hook_refused_with_reason(tmp_path):
    """Decision 64: a section whose loft nose folds back (rc0864c, a flat-faced nose) is refused,
    and so is any wing that uses it."""
    with pytest.raises(ValueError, match="nose folds back"):
        load_airfoil("rc0864c")
    vec = params.mid_vector(CFG.types["bwb"]) | {"airfoils": ["rc0864c", "mh104", "mh61", "mh61"]}
    s = build(vec, "bwb", CFG, tmp_path / "w")
    assert not s["passed"] and s["gate"] == "validity" and "rc0864c: refused, the nose folds back" in s["reason"]
    assert [p.name for p in (tmp_path / "w").iterdir()] == ["refusal.json"]


@pytest.mark.pygeo
@pytest.mark.parametrize("wing_type", ["bwb", "cranked"])
def test_build_writes_wing_folder(tmp_path, wing_type):
    pytest.importorskip("pygeo")
    vec = params.mid_vector(CFG.types[wing_type])
    out = tmp_path / wing_type
    s = build(vec, wing_type, CFG, out)
    assert s["passed"], s["reason"]
    for f in ("vector.json", "stations.json", "measured.json", "labels.json", "gates.json",
              "span_table.csv", "wing.igs", "summary.json"):
        assert (out / f).is_file(), f
    assert wing_type in json.loads((out / "labels.json").read_text())["labels"]
    # a second build gives the same surface
    assert build(vec, wing_type, CFG)["surface_hash"] == s["surface_hash"]
