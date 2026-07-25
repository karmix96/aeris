"""AVL's two per-section corrections must stay active, correct and section-resolved.

AVL offers exactly two per-section corrections to the bare VLM and AERIS uses
both (DECISION-0006):

  CDCL  — viscous profile drag, a 3-point (cl, cd) polar injected per SECTION,
          computed by NeuralFoil from that section's own CST coordinates at that
          section's local Reynolds number.
  CLAF  — thickness lift-slope, 1 + 0.77*(t/c) per section.

Both have silently regressed before (the OPER "v" toggle once switched viscous
forces off, making the injected CDCL inert), so these are regression guards, not
one-off checks. Each is asserted three ways: PRESENT in the .avl, CORRECT against
an independent recomputation, and — where AVL is available — ACTIVE, i.e. AVL's
answer moves when the block is neutralised.

Full write-up: studies/avl_section_corrections.md
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

from aeris.aero.models import FlightCondition
from aeris.aero.solvers.native_avl import _max_thickness_over_chord, write_native_avl
from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
    build_pygeo_sections_from_config,
    run_pygeo_native_avl_case,
)

CONFIG = Path("configs/geometry/bwb.yaml")
CST_POINTS = 80  # what the native writer feeds AVL


@pytest.fixture(scope="module")
def sections():
    ex, semispan, meta = build_pygeo_sections_from_config(CONFIG, n_sections=13)
    return sorted(ex, key=lambda s: float(s.y_m)), semispan, meta


def _parse_avl_sections(avl_path: Path) -> list[dict]:
    lines = avl_path.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == "SECTION":
            sec: dict = {"claf": None, "cdcl": None}
            j = i + 3
            while j < len(lines) and lines[j].strip() != "SECTION":
                if lines[j].strip() == "CLAF":
                    sec["claf"] = float(lines[j + 1].strip())
                elif lines[j].strip() == "CDCL":
                    vals = lines[j + 2].split()
                    if len(vals) == 6:
                        sec["cdcl"] = [float(v) for v in vals]
                j += 1
            out.append(sec)
            i = j
        else:
            i += 1
    return out


def _thickness_over_chord_independent(coords: np.ndarray) -> float:
    """Independent t/c: interpolate both surfaces onto a shared dense abscissa.

    Deliberately a different algorithm from the solver's own routine (which
    matches on rounded x values), so this is a cross-check, not a copy.
    """
    c = np.asarray(coords, dtype=float)
    i_le = int(np.argmin(c[:, 0]))
    upper, lower = c[: i_le + 1][::-1], c[i_le:]
    xs = np.linspace(0.0, 1.0, 2001)
    return float(np.max(np.interp(xs, upper[:, 0], upper[:, 1])
                        - np.interp(xs, lower[:, 0], lower[:, 1])))


# ---------------------------------------------------------------- CLAF ----
def test_claf_written_for_every_section_and_matches_the_rule(sections, tmp_path):
    ordered, _, _ = sections
    avl = tmp_path / "airplane.avl"
    write_native_avl(ordered, avl)
    parsed = _parse_avl_sections(avl)

    assert len(parsed) == len(ordered)
    for sec, written in zip(ordered, parsed):
        assert written["claf"] is not None
        tc = _thickness_over_chord_independent(
            sec.cst.coordinates(n_per_surface=CST_POINTS)
        )
        assert written["claf"] == pytest.approx(1.0 + 0.77 * tc, abs=1e-5)
        # a plausible subsonic airfoil, not a degenerate slab or a sliver
        assert 0.05 < tc < 0.30


def test_claf_is_section_resolved_and_tracks_the_airfoil_transition(sections, tmp_path):
    """mh91 (~15% t/c) -> e374 (~11%) -> nlf1015 (~15%): CLAF must follow the
    blend, carrying more information than the 4 authored station airfoils."""
    ordered, _, _ = sections
    avl = tmp_path / "airplane.avl"
    write_native_avl(ordered, avl)
    claf = [s["claf"] for s in _parse_avl_sections(avl)]

    tc = [(c - 1.0) / 0.77 for c in claf]
    assert max(tc) - min(tc) > 0.02, "t/c must vary along span, not be constant"
    # the thin e374 region sits inboard of the tip, so the minimum is interior
    assert 0 < int(np.argmin(tc)) < len(tc) - 1
    # more distinct values than authored stations => resolved from the loft
    assert len({round(c, 6) for c in claf}) > 4


def test_max_thickness_over_chord_agrees_with_independent_measurement(sections):
    ordered, _, _ = sections
    for sec in (ordered[0], ordered[len(ordered) // 2], ordered[-1]):
        coords = sec.cst.coordinates(n_per_surface=CST_POINTS)
        assert _max_thickness_over_chord(coords) == pytest.approx(
            _thickness_over_chord_independent(coords), abs=2e-3
        )


# ---------------------------------------------------------------- CDCL ----
def test_cdcl_placeholders_are_zero_without_a_polar_store(sections, tmp_path):
    ordered, _, _ = sections
    avl = tmp_path / "airplane.avl"
    write_native_avl(ordered, avl)
    for sec in _parse_avl_sections(avl):
        assert sec["cdcl"] == [0.0] * 6


@pytest.mark.skipif(shutil.which("avl") is None, reason="avl binary not available")
def test_cdcl_injected_for_every_section_and_section_resolved(sections, tmp_path):
    ordered, semispan, meta = sections
    fc = FlightCondition(alpha_deg=6.0, velocity_mps=28.0, altitude_m=0.0)
    res = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=tmp_path, extracted_sections=ordered,
        semispan_m=semispan, control=meta["control"], viscous=True, name="cdcl",
    )
    assert res.status == "SUCCESS"
    assert res.n_cdcl_injected == len(ordered)

    parsed = _parse_avl_sections(tmp_path / "airplane.avl")
    cd_min = [s["cdcl"][3] for s in parsed]           # CD2 = min-drag cd
    assert all(v > 0 for v in cd_min)
    # every section gets its OWN polar, not one shared fit
    assert len({round(v, 8) for v in cd_min}) == len(ordered)
    # low-Re tip sections must be draggier than the high-Re root
    assert cd_min[-1] > cd_min[0]


@pytest.mark.skipif(shutil.which("avl") is None, reason="avl binary not available")
def test_viscous_toggle_actually_reaches_avl(sections, tmp_path):
    """CDvis must be zero with viscous off and positive with it on — the guard
    against the OPER 'v'-toggle class of regression, where the CDCL blocks are
    written but AVL never counts them."""
    ordered, semispan, meta = sections
    fc = FlightCondition(alpha_deg=6.0, velocity_mps=28.0, altitude_m=0.0)

    off = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=tmp_path / "off", extracted_sections=ordered,
        semispan_m=semispan, control=meta["control"], viscous=False, name="off",
    )
    on = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=tmp_path / "on", extracted_sections=ordered,
        semispan_m=semispan, control=meta["control"], viscous=True, name="on",
    )

    assert off.cd_vis == pytest.approx(0.0, abs=1e-9)
    assert on.cd_vis is not None and on.cd_vis > 1e-4
    assert off.cd_profile is None
    assert on.cd_profile is not None and on.cd_profile > 1e-4
    # AVL's own injected-CDCL drag and the independent strip integration are two
    # routes to the same quantity; they must agree to within the QC tolerance.
    assert abs(on.cd_vis - on.cd_profile) / on.cd_profile < 0.10
    # induced drag must be untouched by the viscous switch
    assert on.cd_ind == pytest.approx(off.cd_ind, rel=1e-6)


@pytest.mark.skipif(shutil.which("avl") is None, reason="avl binary not available")
def test_claf_is_active_in_avl(sections, tmp_path):
    """Ablation: force every CLAF to 1.0 and CLa must drop.

    The wing-level ratio must land strictly between 1.0 (CLAF ignored entirely)
    and the mean CLAF (no 3-D downwash dilution) — CLAF is a SECTION property.
    """
    from aeris.aero.solvers.avl_output import (
        extract_stability_axis_derivatives,
        parse_stability_file,
    )

    ordered, semispan, meta = sections
    fc = FlightCondition(alpha_deg=6.0, velocity_mps=28.0, altitude_m=0.0)
    base_dir = tmp_path / "base"
    res = run_pygeo_native_avl_case(
        flight_condition=fc, output_dir=base_dir, extracted_sections=ordered,
        semispan_m=semispan, control=meta["control"], viscous=False, name="claf",
    )
    assert res.status == "SUCCESS"
    cla_base = res.stability_axis_derivatives["CLa"]
    claf_written = [s["claf"] for s in _parse_avl_sections(base_dir / "airplane.avl")]
    mean_claf = float(np.mean(claf_written))
    assert mean_claf > 1.02  # otherwise the ablation proves nothing

    # neutralise CLAF in place and re-run AVL on the same geometry
    abl_dir = tmp_path / "ablate"
    abl_dir.mkdir()
    for f in base_dir.glob("airplane.avl.af*"):
        (abl_dir / f.name).write_text(f.read_text())
    lines = (base_dir / "airplane.avl").read_text().splitlines()
    for k, line in enumerate(lines):
        if line.strip() == "CLAF":
            lines[k + 1] = "1.0"
    (abl_dir / "airplane.avl").write_text("\n".join(lines) + "\n")

    import subprocess

    keys = ["plop", "g", "", "oper", "o", "r", "d", "",
            "a a 6.0", "b b 0", "x", "st", "stability.txt", "", "quit"]
    with open(abl_dir / "stdout.txt", "w") as log:
        p = subprocess.Popen(["avl", "airplane.avl"], cwd=abl_dir,
                             stdin=subprocess.PIPE, stdout=log, stderr=log, text=True)
        p.communicate(input="\n".join(keys), timeout=300)

    cla_abl = extract_stability_axis_derivatives(
        parse_stability_file(abl_dir / "stability.txt")
    )["CLa"]

    assert cla_abl is not None and cla_abl > 0
    ratio = cla_base / cla_abl
    assert ratio > 1.01, "CLAF is written but AVL is not applying it"
    assert ratio < mean_claf, "CLAF applied without 3-D downwash dilution"
