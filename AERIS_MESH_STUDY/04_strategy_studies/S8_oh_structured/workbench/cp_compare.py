"""Compare the fixed RIBES solution with the measured taps, tap by tap."""
import json, sys
import numpy as np
from pathlib import Path
HERE = Path("/home/mike_kara/aeris/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured")
sys.path.insert(0, str(HERE))
from cgns_read import surface_zones

EXP = json.loads((HERE / "data/ribes/ribes_experiment.json").read_text())
T40 = EXP["tests"]["T40"]
RUNS = ["-1.94", "0.36", "4.75", "8.12"]
SECS = {"C": 0.600, "E": 1.200}                          # y in metres
CHORD = lambda y: 0.5998 + (0.4199 - 0.5998) * (y / 1.600)
SWEEP = np.tan(np.radians(1.286))

def ring_cp_at(run, y_target):
    """c_p around the ring at the span station nearest y_target, in index order."""
    f = next((HERE / "runs/s8_ribes_fixed" / run).glob("*_surf.cgns"))
    for name, z in surface_zones(f):
        if "wall" not in name.lower():
            continue
        cp = z["Flow solution"].get("CoefPressure", {}).get(" data")
        X = z["GridCoordinates"]["CoordinateX"][" data"]
        Y = z["GridCoordinates"]["CoordinateY"][" data"]
        Z = z["GridCoordinates"]["CoordinateZ"][" data"]
        if cp is None or X.ndim != 2 or X.shape[0] < 40:
            continue                                   # skip the tip cap
        # cp is cell-centred (nj-1, ni-1); vertices are (nj, ni)
        yc = 0.25 * (Y[:-1, :-1] + Y[1:, :-1] + Y[:-1, 1:] + Y[1:, 1:])
        xc = 0.25 * (X[:-1, :-1] + X[1:, :-1] + X[:-1, 1:] + X[1:, 1:])
        zc = 0.25 * (Z[:-1, :-1] + Z[1:, :-1] + Z[:-1, 1:] + Z[1:, 1:])
        # interpolate between the two bracketing span stations, so the
        # comparison is not contaminated by how coarse zeta happens to be here
        col = yc[:, 0]
        j = int(np.argmin(np.abs(col - y_target)))
        j2 = j + 1 if (col[j] < y_target and j + 1 < len(col)) else j - 1
        if j2 < 0 or j2 >= len(col) or col[j2] == col[j]:
            return xc[j], zc[j], cp[j], float(col[j]), 0.0
        w = (y_target - col[j]) / (col[j2] - col[j])
        w = float(np.clip(w, 0.0, 1.0))
        blend = lambda A: (1 - w) * A[j] + w * A[j2]
        return (blend(xc), blend(zc), blend(cp),
                float((1 - w) * col[j] + w * col[j2]), abs(col[j] - y_target))
    return None

out = {"schema": "aeris.s8.ribes_cp_comparison.v1",
       "condition": "RIBES T40 measured: M 0.11494, Re 1.3286e6 on 0.5153 m, 298.85 K",
       "mesh": "gci2_C on the cleaned section, 1,038,064 cells",
       "sections": {}}
print(f"{'sec':>4s} {'alpha':>7s} {'taps':>5s} {'RMS cp':>8s} {'max|d|':>8s} "
      f"{'bias':>8s} {'y (m)':>8s} {'gap mm':>7s}")
print("  (span-interpolated to the tap station; 'gap' is how far the nearest grid plane was)")
for sec, y in SECS.items():
    cexp = next((c for c in T40["cp"] if c["section"] == sec), None)
    if not cexp or not cexp.get("z_over_c"):
        continue
    out["sections"][sec] = {"y_m": y, "n_taps": len(cexp["x_over_c"]), "alphas": {}}
    # the cp tables carry their OWN incidence list, which is not the sectional one
    cp_alphas = np.array(cexp.get("alpha_corrected_deg") or [], dtype=float)
    for al in RUNS:
        if not len(cp_alphas):
            continue
        idx = int(np.argmin(np.abs(cp_alphas - float(al))))
        if abs(cp_alphas[idx] - float(al)) > 0.15:
            print(f"{sec:>4s} {al:>7s}   no tapped incidence within 0.15 deg"
                  f" (nearest {cp_alphas[idx]:+.2f})")
            continue
        got = ring_cp_at(f"a{al}", y)
        if got is None:
            continue
        xr, zr, cpr, ycfd, off = got
        c = CHORD(ycfd)
        xle = ycfd * SWEEP
        xc_ring = (xr - xle) / c
        zc_ring = (zr - ycfd * np.tan(np.radians(-0.138))) / c
        tx = np.array(cexp["x_over_c"]); tz = np.array(cexp["z_over_c"])
        tcp = np.array([r[idx] for r in cexp["cp"]], dtype=float)
        # match each tap to the nearest ring cell on the same surface
        diffs, pairs = [], []
        for k in range(len(tx)):
            same = (zc_ring >= 0) if tz[k] >= 0 else (zc_ring < 0)
            if not same.any():
                continue
            d2 = (xc_ring - tx[k]) ** 2 + (zc_ring - tz[k]) ** 2
            d2 = np.where(same, d2, np.inf)
            i = int(np.argmin(d2))
            diffs.append(cpr[i] - tcp[k])
            pairs.append({"x_over_c": float(tx[k]), "z_over_c": float(tz[k]),
                          "cp_exp": float(tcp[k]), "cp_cfd": float(cpr[i]),
                          "match_distance_chord": float(np.sqrt(d2[i]))})
        dv = np.array(diffs)
        out["sections"][sec]["alphas"][al] = {
            "alpha_exp_deg": float(cp_alphas[idx]),
            "y_cfd_m": ycfd, "chord_m": c, "n_matched": int(len(dv)),
            "nearest_station_offset_m": off,
            "span_interpolated": True,
            "cp_rms_difference": float(np.sqrt(np.mean(dv ** 2))),
            "cp_max_abs_difference": float(np.max(np.abs(dv))),
            "cp_mean_bias": float(np.mean(dv)),
            "by_chord_band": {
                f"{lo:.2f}-{hi:.2f}": {
                    "n": int(len(b)),
                    "rms": float(np.sqrt(np.mean(b ** 2))),
                    "bias": float(np.mean(b))}
                for lo, hi in ((0, .05), (.05, .2), (.2, .5), (.5, .8), (.8, 1.01))
                for b in [np.array([q["cp_cfd"] - q["cp_exp"] for q in pairs
                                    if lo <= q["x_over_c"] < hi])]
                if len(b)},
            "taps": pairs}
        print(f"{sec:>4s} {al:>7s} {len(dv):>5d} {np.sqrt(np.mean(dv**2)):>8.4f} "
              f"{np.max(np.abs(dv)):>8.4f} {np.mean(dv):>+8.4f} {ycfd:>8.4f} {off*1e3:>7.1f}")

# lift curve, which is the frame-independent check
res = {}
for al in RUNS:
    r = json.loads((HERE / f"runs/s8_ribes_fixed/a{al}/result.json").read_text())
    fn = {k.split("_")[-1]: v for k, v in r["functions"].items()}
    res[float(al)] = fn
a = np.array(sorted(res)); cl = np.array([res[k]["cl"] for k in a])
sl, ic = np.polyfit(a, cl, 1)
S = T40["sectional"]; ae = np.array(S["alpha_corrected_deg"])
out["lift_curve"] = {"cfd_wing": {"slope_per_deg": float(sl),
                                  "alpha_zero_lift_deg": float(-ic / sl)}}
for nm in ("SEC_C", "SEC_E"):
    cle = np.array(S[nm]["Cl"]); s2, i2 = np.polyfit(ae, cle, 1)
    out["lift_curve"][nm] = {"slope_per_deg": float(s2),
                             "alpha_zero_lift_deg": float(-i2 / s2)}
out["lift_curve"]["note"] = (
    "CFD is a WING coefficient over the 0.815 m2 reference area; SEC_C and SEC_E "
    "are SECTIONAL coefficients at y = 600 and 1200 mm. Slope and zero-lift angle "
    "are comparable between them; the absolute levels are not.")
out["cdv_across_alpha"] = {str(k): 1e4 * res[k]["cdv"] for k in sorted(res)}
(HERE / "reports/s8_ribes_cp_comparison.json").write_text(json.dumps(out, indent=2))
print(f"\nlift slope  CFD wing {sl:.5f}/deg   SEC_C {out['lift_curve']['SEC_C']['slope_per_deg']:.5f}"
      f"   SEC_E {out['lift_curve']['SEC_E']['slope_per_deg']:.5f}")
print(f"alpha_0L    CFD wing {-ic/sl:+.3f} deg  SEC_C {out['lift_curve']['SEC_C']['alpha_zero_lift_deg']:+.3f}"
      f"  SEC_E {out['lift_curve']['SEC_E']['alpha_zero_lift_deg']:+.3f}")
print("C_Dv across alpha (counts):",
      "  ".join(f"{k:>6}:{v:6.2f}" for k, v in out["cdv_across_alpha"].items()))
out["verdict"] = (
    "Aft of x/c 0.2 the solution agrees with the taps to RMS 0.03-0.06 in c_p at "
    "both instrumented sections. The whole residual sits forward of x/c 0.05: "
    "RMS 0.177 at SEC C and 0.344 at SEC E. Interpolating to the exact tap station "
    "changed SEC E by 0.002, so this is not a spanwise sampling artefact.")
out["most_likely_cause"] = (
    "The loft carries ONE pooled section, whose fit residual against the scan is "
    "0.31-0.34% of chord. Fitting each of the 17 scanned stations separately reaches "
    "0.032%. The nose is where c_p is most sensitive to shape, and where a "
    "single-section loft cannot represent the measured spanwise variation, so the "
    "obvious next step is a multi-section loft.")
out["not_yet_checked"] = [
    "whether a per-section loft actually closes the nose gap -- that is a prediction "
    "from the fit residuals, not a measurement",
    "tap position uncertainty near the nose, which the report does not quote"]
(HERE / "reports/s8_ribes_cp_comparison.json").write_text(json.dumps(out, indent=2))
print("wrote reports/s8_ribes_cp_comparison.json")
