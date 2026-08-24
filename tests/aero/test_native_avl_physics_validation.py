"""Independent PHYSICS validation of the native AVL writer — closed-form answers.

These are the checks a code-to-code comparison against the AeroSandbox path
STRUCTURALLY CANNOT make (DECISION-0008):

  * both paths share `inject_polar_cdcl` and `_compute_strip_profile_drag`, so a
    shared bug is invisible to their agreement;
  * both read `twist_deg`, `x_le_m`, `z_le_m` from the SAME section objects, so a
    sign or reference-axis error would be identically wrong in both and they
    would agree to 1e-7.

So the wings here are built analytically by a local stub (no pyGeo at all — which
also proves the writer is backend-independent) and checked against closed-form
aerodynamics and against sign conventions.

Full study: studies/native_avl_physics_validation.md
"""

from __future__ import annotations

import math
import shutil
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from aeris.aero.models import FlightCondition
from aeris.aero.solvers.native_avl import run_native_avl_case

pytestmark = pytest.mark.skipif(
    shutil.which("avl") is None, reason="avl binary not available"
)

ASPECT_RATIO = 6.0
N_SECTIONS = 25
NCHORDWISE = 10
SPANWISE_PER_SECTION = 3

# Closed-form references for AR = 6
HELMBOLD = 2 * math.pi * ASPECT_RATIO / (2 + math.sqrt(ASPECT_RATIO**2 + 4))
LIFTING_LINE_E1 = (2 * math.pi) / (1 + (2 * math.pi) / (math.pi * ASPECT_RATIO))


def _naca_symmetric(thickness: float = 0.12, n: int = 80) -> np.ndarray:
    """NACA 00xx closed loop, TE -> upper -> LE -> lower -> TE (closed form)."""
    x = 0.5 * (1.0 - np.cos(np.linspace(0.0, math.pi, n)))
    yt = (thickness / 0.2) * (
        0.2969 * np.sqrt(np.clip(x, 0.0, None))
        - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1015 * x**4
    )
    return np.vstack([np.column_stack([x, yt])[::-1], np.column_stack([x, -yt])[1:]])


class _CST:
    def __init__(self, coords):
        self._c = coords

    def coordinates(self, n_per_surface: int = 80):
        return self._c


@dataclass
class SyntheticSection:
    """Minimal stand-in for pyGeo's ExtractedSection: only what the writer reads."""

    y_m: float
    chord_m: float
    x_le_m: float = 0.0
    z_le_m: float = 0.0
    twist_deg: float = 0.0
    span_fraction: float = 0.0

    def __post_init__(self):
        self.cst = _CST(_naca_symmetric())
        self.direct_coordinates = self.cst.coordinates()

    @property
    def le_xyz_m(self):
        return np.array([self.x_le_m, self.y_m, self.z_le_m], dtype=float)


def build_wing(*, planform="rectangular", tip_twist_deg=0.0, dihedral_deg=0.0,
               sweep_deg=0.0, n=N_SECTIONS):
    semi = 1.0
    if planform == "rectangular":
        c_root = 2.0 * semi / ASPECT_RATIO
        eta = np.linspace(0.0, 1.0, n)
        chords = c_root * np.ones_like(eta)
    elif planform == "elliptic":
        c0 = 8.0 * semi / (math.pi * ASPECT_RATIO)
        eta = np.linspace(0.0, 0.999, n)   # keep the tip chord finite for AVL
        chords = c0 * np.sqrt(np.clip(1.0 - eta**2, 0.0, None))
    else:
        raise ValueError(planform)

    tan_d = math.tan(math.radians(dihedral_deg))
    tan_s = math.tan(math.radians(sweep_deg))
    return [
        SyntheticSection(y_m=float(e * semi), chord_m=float(c),
                         x_le_m=float(e * semi * tan_s),
                         z_le_m=float(e * semi * tan_d),
                         twist_deg=float(tip_twist_deg * e), span_fraction=float(e))
        for e, c in zip(eta, chords)
    ]


def _run(sections, out_dir, alpha, beta=2.0):
    res = run_native_avl_case(
        sections,
        flight_condition=FlightCondition(alpha_deg=alpha, beta_deg=beta,
                                         velocity_mps=28.0, altitude_m=0.0),
        output_dir=out_dir, nchordwise=NCHORDWISE,
        spanwise_panels_per_section=SPANWISE_PER_SECTION, name="validate",
    )
    assert res.status == "SUCCESS", res.warnings
    return res


@pytest.fixture(scope="module")
def rect_alpha5(tmp_path_factory):
    return _run(build_wing(), tmp_path_factory.mktemp("rect5"), alpha=5.0)


def test_reference_geometry_is_encoded_correctly(tmp_path):
    """Sref/Bref must reproduce the analytic aspect ratio."""
    res = _run(build_wing(planform="elliptic"), tmp_path, alpha=5.0)
    ar = res.b_ref**2 / res.s_ref
    assert ar == pytest.approx(ASPECT_RATIO, rel=0.03)


def test_elliptic_wing_span_efficiency_is_one(tmp_path):
    """The single most demanding check on the geometry encoding.

    Elliptic loading is the minimum-induced-drag distribution, so e = 1 exactly.
    Getting it requires span, chord distribution, area AND AVL's Trefftz-plane
    integration all to be right — a wrong chord law or a mis-scaled span shows up
    here immediately.
    """
    res = _run(build_wing(planform="elliptic"), tmp_path, alpha=5.0, beta=0.0)
    assert res.span_efficiency == pytest.approx(1.0, abs=0.06)


def test_symmetric_untwisted_wing_has_zero_lift_at_zero_alpha(tmp_path):
    res = _run(build_wing(), tmp_path, alpha=0.0, beta=0.0)
    assert res.cl == pytest.approx(0.0, abs=5e-3)
    assert res.cm == pytest.approx(0.0, abs=5e-3)


def test_lift_curve_slope_matches_helmbold(rect_alpha5):
    """AVL must land near Helmbold and below the lifting-line (e=1) value.

    A rectangular wing's loading is less efficient than elliptic, so its 3-D
    slope must sit below the e=1 lifting-line result.
    """
    cla = rect_alpha5.stability_axis_derivatives["CLa"]
    assert cla == pytest.approx(HELMBOLD, rel=0.10)
    assert cla < LIFTING_LINE_E1


def test_unswept_neutral_point_near_quarter_chord(rect_alpha5):
    """Straight unswept wing: aerodynamic centre at ~c/4 aft of the LE."""
    assert rect_alpha5.x_np_over_c_ref == pytest.approx(0.25, abs=0.06)


def test_twist_sign_convention(tmp_path, rect_alpha5):
    """Washout must REDUCE lift, wash-in must increase it.

    Invisible to a code-to-code check: both writers read the same twist field.
    """
    wash_out = _run(build_wing(tip_twist_deg=-5.0), tmp_path / "wo", alpha=5.0)
    wash_in = _run(build_wing(tip_twist_deg=+5.0), tmp_path / "wi", alpha=5.0)
    assert wash_out.cl < rect_alpha5.cl < wash_in.cl


def test_twist_is_applied_per_section_not_globally(tmp_path, rect_alpha5):
    """Linear washout must unload the TIP more than the root.

    A globally applied incidence would scale the whole distribution down
    uniformly; only a per-section twist shifts the loading inboard.
    """
    wash_out = _run(build_wing(tip_twist_deg=-5.0), tmp_path / "wo", alpha=5.0)

    def root_tip(res):
        df = pd.read_csv(res.artifact_paths["strips_parsed"])
        df = df[df["y_le"] >= 0].sort_values("y_le")
        k = max(1, len(df) // 10)
        return (float(df["cl_local"].iloc[:k].mean()),
                float(df["cl_local"].iloc[-k:].mean()))

    r_base, t_base = root_tip(rect_alpha5)
    r_wo, t_wo = root_tip(wash_out)
    assert t_wo < t_base
    assert (t_wo - t_base) < (r_wo - r_base)


def test_dihedral_sign_convention(tmp_path, rect_alpha5):
    """Positive dihedral must make Clb more negative — the dihedral effect.

    Checks the z_le sign convention independently of any other code.
    """
    dih = _run(build_wing(dihedral_deg=10.0), tmp_path, alpha=5.0)
    assert dih.stability_axis_derivatives["Clb"] < rect_alpha5.stability_axis_derivatives["Clb"]


def test_sweep_sign_convention(tmp_path, rect_alpha5):
    """Aft sweep must move the neutral point AFT and reduce CLa.

    Checks the x_le sign convention.
    """
    swept = _run(build_wing(sweep_deg=30.0), tmp_path, alpha=5.0)
    assert swept.x_np > rect_alpha5.x_np
    assert swept.stability_axis_derivatives["CLa"] < rect_alpha5.stability_axis_derivatives["CLa"]


def test_writer_needs_no_pygeo():
    """The whole module drives the writer from a local stub, so this documents
    that `write_native_avl` depends on a duck-typed section, not on pyGeo."""
    sec = build_wing()[0]
    for attr in ("y_m", "chord_m", "twist_deg", "le_xyz_m", "span_fraction", "cst"):
        assert hasattr(sec, attr)
    assert "pygeo" not in type(sec).__module__.lower()


# ── AVL array limits must fail loudly, not silently ───────────────────────────

def test_writer_refuses_over_limit_vortex_count(tmp_path):
    """An over-limit mesh must raise, not produce a .avl that AVL rejects.

    AVL's response to exceeding its compiled arrays is a run that returns with
    every coefficient None and status=FAILED -- indistinguishable from a physics
    failure. A 49-section x 4-panel x 24-chordwise mesh is 9216 vortices against a
    ~6000 limit; that combination silently NaN'd an entire study before this guard
    existed.
    """
    import numpy as np
    import pytest
    from aeris.aero.solvers.native_avl import write_native_avl

    class _S:
        def __init__(self, y, c):
            self.y_m = float(y)
            self.chord_m = float(c)
            self.x_le_m = 0.0
            self.z_le_m = 0.0
            self.twist_deg = 0.0
            self.span_fraction = float(y)
            n = 41
            th = np.linspace(0.0, 2.0 * np.pi, n)
            self.direct_coordinates = np.column_stack(
                [0.5 * (1 + np.cos(th)), 0.06 * np.sin(th)])

    secs = [_S(y, 0.5) for y in np.linspace(0.0, 1.0, 49)]
    with pytest.raises(ValueError, match="vortices"):
        write_native_avl(secs, tmp_path / "over.avl", representation="direct",
                         nchordwise=24, spanwise_panels_per_section=4)

    # The panel-matched alternative used by the placement study is legal: 49
    # sections x 2 panels is the SAME vortex count as 25 x 4, so a section-
    # refinement reference can be built without crossing the limit.
    assert 2 * (49 - 1) * 2 * 24 == 2 * (25 - 1) * 4 * 24 == 4608


def test_writer_refuses_over_limit_strip_count(tmp_path):
    """NSMAX=500 strips is the other compiled limit."""
    import numpy as np
    import pytest
    from aeris.aero.solvers.native_avl import write_native_avl

    class _S:
        def __init__(self, y):
            self.y_m = float(y)
            self.chord_m = 0.5
            self.x_le_m = 0.0
            self.z_le_m = 0.0
            self.twist_deg = 0.0
            self.span_fraction = float(y)
            n = 41
            th = np.linspace(0.0, 2.0 * np.pi, n)
            self.direct_coordinates = np.column_stack(
                [0.5 * (1 + np.cos(th)), 0.06 * np.sin(th)])

    secs = [_S(y) for y in np.linspace(0.0, 1.0, 60)]
    with pytest.raises(ValueError, match="strips"):
        write_native_avl(secs, tmp_path / "over.avl", representation="direct",
                         nchordwise=4, spanwise_panels_per_section=8)
