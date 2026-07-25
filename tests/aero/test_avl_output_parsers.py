"""Unit tests for the shared AVL output parsers (`aeris.aero.solvers.avl_output`).

Fixtures are verbatim excerpts of real AVL dumps from a native pyGeo->AVL run of
`configs/geometry/bwb.yaml`, so the parsers are tested against the exact text
formats AVL emits (including the ``d01``/``d02`` control-derivative columns and
the ``Clb Cnr / Clr Cnb`` composite line that must not clobber ``Cnb``).
"""

from __future__ import annotations

import pytest

from aeris.aero.solvers.avl_output import (
    compute_derived_metrics,
    extract_body_axis_derivatives,
    extract_control_derivatives,
    extract_stability_axis_derivatives,
    parse_hinge_moments,
    parse_stability_file,
    parse_strip_shear_moment,
    parse_surface_forces,
    parse_totals_text,
    read_avl_strips,
    to_float_or_none,
)

TOTALS_TEXT = """\
 ---------------------------------------------------------------
 Vortex Lattice Output -- Total Forces

 Configuration: pygeo_native
     # Surfaces =   2
     # Strips   = 192
     # Vortices =1536

  Sref = 0.64438       Cref = 0.54448       Bref =  1.6319
  Xref =  0.0000       Yref =  0.0000       Zref =  0.0000

  Alpha =   3.00000     pb/2V =  -0.00000     p'b/2V =  -0.00000
  Beta  =   0.00000     qc/2V =   0.00000
  Mach  =     0.000     rb/2V =  -0.00000     r'b/2V =  -0.00000

  CXtot =  -0.00462     Cltot =  -0.00243     Cl'tot =  -0.00243
  CYtot =  -0.00025     Cmtot =  -0.00633
  CZtot =  -0.03847     Cntot =  -0.00003     Cn'tot =   0.00010

  CLtot =   0.03818
  CDtot =   0.00663
  CDvis =   0.00637     CDind = 0.0002635
  CLff  =   0.03818     CDff  = 0.0002514    | Trefftz
  CYff  =  -0.00012         e =    0.4591    | Plane

   elevon_sym      =   2.00000
   elevon_diff     =   1.00000

 ---------------------------------------------------------------
"""

STABILITY_TEXT = """\
 Stability-axis derivatives...

                             alpha                beta
                  ----------------    ----------------
 z' force CL |    CLa =   2.736347    CLb =  -0.004995
 y  force CY |    CYa =  -0.001836    CYb =  -0.009182
 x' mom.  Cl'|    Cla =   0.000189    Clb =  -0.019845
 y  mom.  Cm |    Cma =  -1.206302    Cmb =   0.004039
 z' mom.  Cn'|    Cna =   0.002435    Cnb =   0.002269

                     roll rate  p'      pitch rate  q'        yaw rate  r'
                  ----------------    ----------------    ----------------
 z' force CL |    CLp =   0.000015    CLq =   4.883207    CLr =  -0.008250
 y  force CY |    CYp =  -0.033741    CYq =  -0.003933    CYr =   0.004584
 x' mom.  Cl'|    Clp =  -0.315857    Clq =  -0.000121    Clr =   0.022997
 y  mom.  Cm |    Cmp =  -0.000011    Cmq =  -2.632068    Cmr =   0.004038
 z' mom.  Cn'|    Cnp =   0.008483    Cnq =   0.000982    Cnr =  -0.002952

                  elevon_sym   d01     elevon_diff  d02
                  ----------------    ----------------
 z' force CL |   CLd01 =   0.007971   CLd02 =  -0.000001
 y  force CY |   CYd01 =   0.000006   CYd02 =  -0.000261
 x' mom.  Cl'|   Cld01 =  -0.000000   Cld02 =  -0.002430
 y  mom.  Cm |   Cmd01 =  -0.004539   Cmd02 =  -0.000000
 z' mom.  Cn'|   Cnd01 =   0.000007   Cnd02 =  -0.000082
 Trefftz drag| CDffd01 =   0.000091 CDffd02 =   0.000039
 span eff.   |    ed01 =   0.024703    ed02 =  -0.072056

 Clb Cnr / Clr Cnb  =   1.234567

 Neutral point  Xnp =   0.232353
"""

BODY_DERIVS_TEXT = """\
 Geometry-axis derivatives...

                    axial   vel. u     sideslip vel. v      normal  vel. w
                  ----------------    ----------------    ----------------
 x force CX  |    CXu =  -0.017458    CXv =  -0.000069    CXw =   0.157475
 y force CY  |    CYu =  -0.000409    CYv =  -0.009182    CYw =  -0.001860
 z force CZ  |    CZu =   0.066812    CZv =   0.004999    CZw =  -2.738709
 x mom.  Cl  |    Clu =  -0.004858    Clv =  -0.019937    Clw =  -0.000165
 y mom.  Cm  |    Cmu =   0.050652    Cmv =   0.004039    Cmw =  -1.205303
 z mom.  Cn  |    Cnu =  -0.000050    Cnv =   0.001227    Cnw =   0.000009
"""

HINGE_TEXT = """\
 ---------------------------------------------------------------
 Control Hinge Moments
 (referred to    Sref =  0.6105       Cref =    0.5271)

 Control          Chinge
 ---------------- -----------
 elevon_sym       -0.1118E-03
 elevon_diff      -0.3626E-04
 ---------------------------------------------------------------
"""

SURFACE_TEXT = """\
 ---------------------------------------------------------------
 Surface Forces (referred to Sref,Cref,Bref about Xref,Yref,Zref)

     Sref =  0.6105       Cref =    0.5271   Bref =    1.5666

 n      Area      CL      CD      Cm      CY      Cn      Cl     CDi     CDv
 1     0.305  0.0226  0.0034 -0.0052 -0.0013  0.0008 -0.0063  0.0002  0.0032   pygeo_native
 2     0.305  0.0156  0.0033 -0.0011  0.0011 -0.0008  0.0039  0.0001  0.0032   pygeo_native (YDUP)

 Surface Forces (referred to Ssurf, Cave about root LE on hinge axis)

   n     Ssurf      Cave       cl       cd      cdv
   1     0.305     0.390   0.0451   0.0067   0.0064  pygeo_native
   2     0.305     0.390   0.0312   0.0065   0.0064  pygeo_native (YDUP)
 ---------------------------------------------------------------
"""

STRIP_TEXT = """\
  Surface # 1     pygeo_native

 Strip Forces referred to Strip Area, Chord
    j     Xle      Yle      Zle      Chord    Area     c_cl     ai     cl_norm    cl       cd       cdv    cm_c/4     cm_LE   C.P.x/c
     1   0.0024   0.0042   0.0030   0.9448   0.0080   0.0333   0.0083   0.0355   0.0351   0.0105   0.0055   0.0256   0.0148   -0.480
     2   0.0068   0.0127   0.0030   0.9307   0.0079   0.0336   0.0107   0.0364   0.0360   0.0073   0.0055   0.0259   0.0149   -0.469

  Surface # 2     pygeo_native (YDUP)

 Strip Forces referred to Strip Area, Chord
    j     Xle      Yle      Zle      Chord    Area     c_cl     ai     cl_norm    cl       cd       cdv    cm_c/4     cm_LE   C.P.x/c
     1   0.0024  -0.0042   0.0030   0.9448   0.0080   0.0333   0.0083   0.0355   0.0351   0.0105   0.0055   0.0256   0.0148   -0.480
     2   0.0068  -0.0127   0.0030   0.9307   0.0079   0.0336   0.0107   0.0364   0.0360   0.0073   0.0055   0.0259   0.0149   -0.469
"""

VM_TEXT = """\
 Shear/q and Bending Moment/q vs Y
  Configuration: pygeo_native
  Mach  =    0.000
  alpha =    3.000    CLtot =    0.038

 Surface:   1
pygeo_native
     2Ymin/Bref =    2.0831287672718891E-002
   2Y/Bref      Vz/(q*Sref)      Mx/(q*Bref*Sref)
    0.0208  0.225075E-01     0.603437E-02
    0.0260  0.224763E-01     0.597580E-02
    0.0365  0.223992E-01     0.585894E-02
"""


def test_parse_totals_captures_every_scalar_including_e_and_controls():
    t = parse_totals_text(TOTALS_TEXT)
    assert t["CLtot"] == pytest.approx(0.03818)
    assert t["CDind"] == pytest.approx(0.0002635)
    assert t["CDvis"] == pytest.approx(0.00637)
    assert t["CDff"] == pytest.approx(0.0002514)
    assert t["Cmtot"] == pytest.approx(-0.00633)
    assert t["CXtot"] == pytest.approx(-0.00462)
    assert t["CZtot"] == pytest.approx(-0.03847)
    # span efficiency: the single-letter key must survive the scrape
    assert t["e"] == pytest.approx(0.4591)
    # reference values and control deflections
    assert t["Sref"] == pytest.approx(0.64438)
    assert t["Cref"] == pytest.approx(0.54448)
    assert t["Bref"] == pytest.approx(1.6319)
    assert t["elevon_sym"] == pytest.approx(2.0)
    assert t["elevon_diff"] == pytest.approx(1.0)
    # reduced rates
    assert "pb/2V" in t


def test_parse_totals_first_occurrence_wins():
    """Alpha appears once; Sref appears in several AVL blocks. The reference block
    at the top must not be overwritten by a later, lower-precision echo."""
    text = TOTALS_TEXT + "\n  Sref = 9.99999\n"
    assert parse_totals_text(text)["Sref"] == pytest.approx(0.64438)


def test_stability_file_parses_all_derivatives_and_xnp(tmp_path):
    p = tmp_path / "stability.txt"
    p.write_text(STABILITY_TEXT)
    parsed = parse_stability_file(p)

    stab = extract_stability_axis_derivatives(parsed)
    assert stab["CLa"] == pytest.approx(2.736347)
    assert stab["Cma"] == pytest.approx(-1.206302)
    assert stab["Clb"] == pytest.approx(-0.019845)
    assert stab["Clp"] == pytest.approx(-0.315857)
    assert stab["Cmq"] == pytest.approx(-2.632068)
    assert stab["Cnr"] == pytest.approx(-0.002952)
    assert stab["Xnp"] == pytest.approx(0.232353)
    # every canonical key must be present (None allowed only if AVL omitted it)
    assert all(v is not None for v in stab.values())


def test_composite_metric_line_does_not_clobber_cnb(tmp_path):
    p = tmp_path / "stability.txt"
    p.write_text(STABILITY_TEXT)
    parsed = parse_stability_file(p)
    assert parsed["Cnb"] == pytest.approx(0.002269)
    assert parsed["Clb Cnr / Clr Cnb"] == pytest.approx(1.234567)


def test_control_derivatives_map_onto_control_names(tmp_path):
    p = tmp_path / "stability.txt"
    p.write_text(STABILITY_TEXT)
    parsed = parse_stability_file(p)
    ctrl = extract_control_derivatives(STABILITY_TEXT, parsed)

    assert set(ctrl) == {"elevon_sym", "elevon_diff"}
    # symmetric elevon drives pitch, not roll
    assert ctrl["elevon_sym"]["Cm"] == pytest.approx(-0.004539)
    assert ctrl["elevon_sym"]["CL"] == pytest.approx(0.007971)
    assert abs(ctrl["elevon_sym"]["Cl"]) < 1e-6
    # differential elevon drives roll, not pitch
    assert ctrl["elevon_diff"]["Cl"] == pytest.approx(-0.002430)
    assert abs(ctrl["elevon_diff"]["Cm"]) < 1e-6
    assert ctrl["elevon_sym"]["avl_slot"] == "d01"
    assert ctrl["elevon_diff"]["avl_slot"] == "d02"


def test_body_axis_derivatives(tmp_path):
    p = tmp_path / "body_derivs.txt"
    p.write_text(BODY_DERIVS_TEXT)
    body = extract_body_axis_derivatives(parse_stability_file(p))
    assert body["CZw"] == pytest.approx(-2.738709)
    assert body["Cmw"] == pytest.approx(-1.205303)
    assert body["CXu"] == pytest.approx(-0.017458)
    assert all(v is not None for v in body.values())


def test_derived_metrics_spiral():
    stab = {"Clb": -0.02, "Cnr": -0.003, "Clr": 0.02, "Cnb": 0.0025}
    m = compute_derived_metrics(stab)
    assert m["spiral_metric"] == pytest.approx((-0.02 * -0.003) / (0.02 * 0.0025))

    assert compute_derived_metrics({"Clb": None, "Cnr": 1, "Clr": 1, "Cnb": 1})[
        "spiral_metric"
    ] is None
    assert compute_derived_metrics({"Clb": 1, "Cnr": 1, "Clr": 0.0, "Cnb": 1})[
        "spiral_metric"
    ] is None


def test_hinge_moments(tmp_path):
    p = tmp_path / "hinge.txt"
    p.write_text(HINGE_TEXT)
    hm = parse_hinge_moments(p)
    assert hm == pytest.approx({"elevon_sym": -0.1118e-3, "elevon_diff": -0.3626e-4})


def test_surface_forces_both_tables(tmp_path):
    p = tmp_path / "fn.txt"
    p.write_text(SURFACE_TEXT)
    sf = parse_surface_forces(p)
    assert len(sf["referred_to_sref"]) == 2
    assert len(sf["referred_to_ssurf"]) == 2
    assert sf["referred_to_sref"][0]["cl"] == pytest.approx(0.0226)
    assert sf["referred_to_sref"][0]["cdv"] == pytest.approx(0.0032)
    assert sf["referred_to_sref"][1]["name"] == "pygeo_native (YDUP)"
    assert sf["referred_to_ssurf"][0]["cave"] == pytest.approx(0.390)


def test_read_strips_both_semi_wings(tmp_path):
    p = tmp_path / "strips.txt"
    p.write_text(STRIP_TEXT)
    df = read_avl_strips(p, alpha_deg=3.0)
    assert len(df) == 4
    assert set(df["surface"]) == {1, 2}
    # both halves present -> profile-drag integration must halve+double
    assert (df["y_le"] < 0).any() and (df["y_le"] > 0).any()
    assert df["alpha_deg"].unique().tolist() == [3.0]
    for col in ("chord", "area", "cl_local"):
        assert col in df.columns


def test_strip_shear_moment(tmp_path):
    p = tmp_path / "vm.txt"
    p.write_text(VM_TEXT)
    df = parse_strip_shear_moment(p)
    assert len(df) == 3
    assert df["surface"].unique().tolist() == [1]
    assert df["vz_over_q_sref"].iloc[0] == pytest.approx(0.225075e-01)
    assert df["mx_over_q_bref_sref"].iloc[-1] == pytest.approx(0.585894e-02)
    # the 2Ymin/Bref header line must not be mistaken for a data row
    assert df["two_y_over_bref"].max() < 1.0


def test_to_float_or_none_rejects_nonfinite():
    assert to_float_or_none("1.5") == 1.5
    assert to_float_or_none("nan") is None
    assert to_float_or_none("inf") is None
    assert to_float_or_none("abc") is None
    assert to_float_or_none(None) is None
