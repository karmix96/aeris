"""Stage 1's 2-D strip prediction against SU2's 3-D transition runs, on the one wing solved so far: where the upper
surface separates laminar and where it turns turbulent. The first 3-D check of the Stage 1 flow maps and of the
refine map (decision 65 waits on one).

    python scripts/strip_vs_su2.py     # -> data/studies/strip_vs_su2.json, docs/page/strip_vs_su2.png

2-D side: `cfdauto.mesh.refine_map.strip_map` in its Re mode (XFOIL e^N tables, N_crit 9, a uniform induced angle),
BWB reference wing 0 at Re 3e5 on the mean chord, alpha 4 deg. 3-D side: the `wall_map.json` of the SU2 runs of
12-13 Nov (data/v7/su2_transition/): per station, where the streamwise wall friction first turns negative
(separation) and where it rises steeply (the turbulent friction rise). Neither side is a measurement.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(HERE.parent))
from style import INK, LINE, MUTED, plt                        # noqa: E402
from cfdauto.mesh.refine_map import strip_map                   # noqa: E402

SU2 = HERE / "data" / "v7" / "su2_transition"
RUNS = (("SA + LM, VVC (R2)", "R2_sa_lm", "#2a78d6", "o"),
        ("SA + LM, light VC (R6)", "R6_sa_lm_lightvc", "#eb6834", "s"),
        ("SA-BCM, VVC (R3)", "R3_sa_bcm", "#1baf7a", "^"),
        ("SST + LM, VVC (R4)", "R4_sst_lm", "#eda100", "D"))
TYPE, SET, INDEX, RE, ALPHA = "bwb", "reference", 0, 3e5, 4.0


def num(v) -> float:
    return float(v) if isinstance(v, (int, float)) else float("nan")


def main() -> None:
    sm = strip_map(TYPE, SET, INDEX, alphas=(ALPHA,), res=(RE,), n_per_panel=6)
    ys = np.array(sm["strips"]["y_over_S"])

    def field(k):
        v = np.array([np.nan if x is None else x for x in np.ravel(np.array(sm["fields"][k], dtype=object))], float)
        return v.reshape(len(ys), -1)[:, 0]                    # one condition: a column per strip

    xf = {k: field(k) for k in ("bub_u_s", "bub_u_e", "xtr_u", "xtr_l", "sep_l_x", "re", "alpha_local")}

    def at(k, y):
        ok = np.isfinite(xf[k])
        return float(np.interp(y, ys[ok], xf[k][ok]))

    rows, summary = [], {}
    for name, folder, _, _ in RUNS:
        w = json.loads((SU2 / folder / "wall_map.json").read_text())
        for st in w["stations"]:
            y, u = st["y_over_s"], st["upper"]
            rows.append({"run": name, "y_over_s": y, "chord": st["chord"],
                         "su2_separation_xc": num(u.get("separation_xc")), "su2_friction_rise_xc": num(u.get("friction_rise_at_xc")),
                         "xfoil_separation_xc": at("bub_u_s", y), "xfoil_transition_xc": at("xtr_u", y),
                         "xfoil_reattachment_xc": at("bub_u_e", y), "xfoil_local_re": at("re", y)})
        mine = [r for r in rows if r["run"] == name]
        ds = np.array([r["su2_separation_xc"] - r["xfoil_separation_xc"] for r in mine])
        dt = np.array([r["su2_friction_rise_xc"] - r["xfoil_transition_xc"] for r in mine])
        summary[name] = {"stations": len(mine),
                         "separation_minus_xfoil_c": {"mean": float(np.nanmean(ds)), "min": float(np.nanmin(ds)), "max": float(np.nanmax(ds))},
                         "friction_rise_minus_xfoil_transition_c": {"mean": float(np.nanmean(dt)), "min": float(np.nanmin(dt)),
                                                                    "max": float(np.nanmax(dt)), "mean_abs": float(np.nanmean(np.abs(dt)))}}
    out = {"case": {"wing": f"{TYPE} {SET} {INDEX}", "re_mean_chord": RE, "alpha_deg": ALPHA,
                    "strips": "XFOIL e^N tables, N_crit 9 (Tu 0.07 %), Mach 0.1, uniform induced angle; cfdauto.mesh.refine_map.strip_map",
                    "su2": "incompressible RANS on the Stage 3 mesh, Tu 0.1 %; data/v7/su2_transition/*/wall_map.json",
                    "strip_cl_wing": sm["per_condition"]["cl_wing"][0], "strip_induced_angle_deg": sm["per_condition"]["alpha_induced_deg"][0]},
           "lower_side": {"xfoil_transition_xc": [float(v) for v in xf["xtr_l"]], "y_over_s": [float(v) for v in ys],
                          "note": "XFOIL: laminar to 0.93-1.00 c; every SU2 transition run: laminar to the trailing edge"},
           "summary": summary, "rows": rows,
           "limits": ("one wing, one Re, one angle; both sides are models (e^N strips against correlation-based RANS), not a "
                      "measurement; neither has crossflow transition; SA + LM and SST + LM were oscillating, not converged; "
                      "VVC and light VC put about 7 to 9 cells in a bubble; the SU2 runs used Tu 0.1 %, the strips N_crit 9 (0.07 %)")}
    (HERE / "data" / "studies" / "strip_vs_su2.json").write_text(json.dumps(out, indent=1))

    fig, ax = plt.subplots(1, 2, figsize=(10.2, 4.5), sharey=True)
    for a, (key_x, key_s, title) in zip(ax, (("xfoil_separation_xc", "su2_separation_xc", "Laminar separation starts"),
                                             ("xfoil_transition_xc", "su2_friction_rise_xc", "The flow turns turbulent"))):
        ok = np.isfinite(xf["bub_u_s"])
        a.fill_between(ys[ok], xf["bub_u_s"][ok], xf["bub_u_e"][ok], color=LINE, alpha=0.55, lw=0, zorder=1,
                       label="2-D strips: the bubble, separation to reattachment")
        k2 = "bub_u_s" if key_x == "xfoil_separation_xc" else "xtr_u"
        a.plot(ys[ok], xf[k2][ok], color=INK, lw=2, zorder=2, label="2-D strips: the line each panel names")
        a.annotate("2-D strips", (0.62, float(np.interp(0.62, ys[ok], xf[k2][ok]))), xytext=(0, 7 if k2 == "bub_u_s" else -13),
                   textcoords="offset points", fontsize=8.3, color=INK, ha="center")
        for j, (name, _, col, mk) in enumerate(RUNS):
            r = [q for q in rows if q["run"] == name]
            a.plot([q["y_over_s"] + (j - 1.5) * 0.013 for q in r], [q[key_s] for q in r], mk, ms=6.5, color=col, mec="white",
                   mew=1.0, zorder=3, label="SU2 " + name)   # side by side: four runs share each station
        a.set_title(title)
        a.set_xlabel("y / semi-span")
        a.grid(color=LINE, lw=0.5)
        a.set_xlim(0, 1)
    ax[0].set_ylabel("x / c on the upper side")
    ax[0].set_ylim(0.2, 1.0)
    h, lab = ax[1].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=3, frameon=False, fontsize=8.2, bbox_to_anchor=(0.5, 0.155))
    fig.suptitle("BWB reference wing 0, Re 3e5, 4 deg: Stage 1's 2-D strips against SU2's 3-D transition runs", x=0.01, ha="left",
                 fontsize=10.5, color=INK)
    fig.text(0.01, 0.905, "upper side; neither is a measurement; SA + LM and SST + LM were oscillating", fontsize=8.3, color=MUTED)
    fig.subplots_adjust(top=0.84, bottom=0.29, left=0.07, right=0.985, wspace=0.06)
    fig.savefig(HERE / "docs" / "page" / "strip_vs_su2.png")     # not style.save: its tight_layout would undo the legend's room
    plt.close(fig)
    print("wrote strip_vs_su2.png")
    for name, s in summary.items():
        t = s["friction_rise_minus_xfoil_transition_c"]
        d = s["separation_minus_xfoil_c"]
        print(f"{name:24s} separation {d['mean']:+.3f} c ({d['min']:+.2f} to {d['max']:+.2f}); "
              f"turbulent rise {t['mean']:+.3f} c ({t['min']:+.2f} to {t['max']:+.2f}; mean abs {t['mean_abs']:.3f})")


if __name__ == "__main__":
    main()
