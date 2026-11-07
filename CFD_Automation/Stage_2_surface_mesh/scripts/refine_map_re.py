"""The refine map by Re level (similarity, decision 70) on the 20 reference wings.

    python scripts/refine_map_re.py              # data/studies/refine_map_re.json and docs/page/refine_re_*.png (about 30 s)
    python scripts/refine_map_re.py --figures    # only redraw the figures from the JSON

Every reference wing (4 types × 5) at the four Re levels on the mean chord (10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶) ×
root angle −5…12° (1° steps): sea level, unit mean chord, 3 strips per panel (as the first approach), the 2-D
section tables read at Mach 0.1 (decision 70), rebuilt on the fixed nose (decision 64, 7 Nov 2026). The speed
follows from Re: V = Re / (ρ/μ) / mean chord. For each wing, Re level, strip and side:

  - where transition sits from −5° to 8°, and from −5° to 12° (earliest and latest over the angles with an answer);
  - the envelope band, as in the first approach: from min(bubble start, transition − 10 % c) to
    max(bubble end, transition + 10 % c, separation start);
  - whether the decided generic band (upper 0–85 % c, lower 0–100 % c; decision 74 option A) covers that band,
    and by how much it falls short when it does not;
  - the strips with no XFOIL answer, split by cause: local Re below the tables' lowest (1.5 × 10⁴) or not
    (beyond the section's 2-D stall, or a failed point).

The first-approach refine map (data/studies/refine_map_reference.json, scripts/refine_map_data.py: real size,
Mach 0.03–0.20, the old tables, the old reference wings) stays the record; its upper-side numbers are read here
for the comparison.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto.flowmap import tables  # noqa: E402
from cfdauto.mesh.refine_map import (ALPHAS, DECIDED_BAND, GENERIC_BAND, MACH_SIMILARITY, RE_LEVELS,  # noqa: E402
                                     envelope_band, strip_map)
from cfdauto.paths import STAGE2  # noqa: E402

OUT = STAGE2 / "data" / "studies" / "refine_map_re.json"
FIRST = STAGE2 / "data" / "studies" / "refine_map_reference.json"
FIG = STAGE2 / "docs" / "page"
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
TYPE_NAME = {"bwb": "BWB", "flying_wing": "flying wing", "cranked": "cranked", "tapered": "tapered"}
WINDOWS = {"8": (-5.0, 8.0), "12": (-5.0, 12.0)}
MARGIN = 0.10
N_PER_PANEL = 3
RE_LOW, RE_HIGH = float(tables.RE[0]), float(tables.RE[-1])     # the tables' Re range
SIDES = (("upper", "xtr_u", "bub_u_s", "bub_u_e", "sep_u_x"), ("lower", "xtr_l", "bub_l_s", "bub_l_e", "sep_l_x"))
TOL = 1e-9


def _f(sm: dict, name: str) -> np.ndarray:
    n, m = sm["shape"]
    v = sm["fields"][name]
    if isinstance(v[0], bool):
        return np.array(v, bool).reshape(n, m)
    return np.array([np.nan if x is None else x for x in v], float).reshape(n, m)


def re_label(r: float) -> str:
    return {1e5: "10⁵", 3e5: "3 × 10⁵", 1.5e6: "1.5 × 10⁶", 3e6: "3 × 10⁶"}.get(r, f"{r:.3g}")


# --- per wing -----------------------------------------------------------------------------------------
def wing_numbers(sm: dict) -> dict:
    """Per Re level: transition range, envelope band, coverage by the decided band, no-answer split, per strip."""
    g = sm["grid"]
    n, m = sm["shape"]
    A = np.tile(np.asarray(g["alpha_deg"], float), len(g["re"]))
    R = np.repeat(np.asarray(g["re"], float), len(g["alpha_deg"]))
    ans, clamp, re_s, al_loc = _f(sm, "answered"), _f(sm, "re_clamped"), _f(sm, "re"), _f(sm, "alpha_local")
    out = {}
    for re_ in g["re"]:
        col = np.isclose(R, re_, rtol=1e-9)
        d = {"re_strip": [float(np.nanmin(re_s[:, col])), float(np.nanmax(re_s[:, col]))],
             "strips_below_tables": int(np.sum(re_s[:, col][:, 0] < RE_LOW)),
             "strips_above_tables": int(np.sum(re_s[:, col][:, 0] > RE_HIGH))}
        # no answer, per angle: share of strips, split by cause
        na = {"alpha_deg": [float(a) for a in g["alpha_deg"]], "below_tables": [], "stall_or_failed": [], "clamped_answered": []}
        loc = []
        for a in g["alpha_deg"]:
            k = np.where(col & np.isclose(A, a))[0][0]
            low = re_s[:, k] < RE_LOW
            na["below_tables"].append(int(np.sum(~ans[:, k] & low)))
            na["stall_or_failed"].append(int(np.sum(~ans[:, k] & ~low)))
            na["clamped_answered"].append(int(np.sum(ans[:, k] & clamp[:, k])))
            loc += [(float(a), float(v)) for v in al_loc[~ans[:, k] & ~low, k]]
        na["local_angle_of_stall_or_failed"] = loc        # (root angle, local angle) of each such strip
        d["no_answer"] = na
        for wname, win in WINDOWS.items():
            band = envelope_band(sm, res=(re_, re_), alphas=win, margin=MARGIN)
            keep = col & (A >= win[0] - TOL) & (A <= win[1] + TOL)
            w = {"fallback": band["fallback"]}
            for side, xk, bs, be, sp in SIDES:
                x, b0, b1, s0 = (_f(sm, k) for k in (xk, bs, be, sp))
                ok = ans & keep[None, :]
                xm = np.where(ok, x, np.nan)
                with np.errstate(all="ignore"):
                    lo_x = np.nanmin(xm, axis=1)
                    hi_x = np.nanmax(xm, axis=1)
                    hi_b = np.nanmax(np.where(ok, b1, np.nan), axis=1)
                    hi_s = np.nanmax(np.where(ok, s0, np.nan), axis=1)
                    lo_b = np.nanmin(np.where(ok, b0, np.nan), axis=1)
                gb = DECIDED_BAND[side]
                env = np.array(band[side], float)
                has = ~np.array(band["fallback"])
                short = np.maximum(env[:, 1] - gb[1], 0.0) + np.maximum(gb[0] - env[:, 0], 0.0)
                # what sets the band's aft end: transition + margin, bubble end or separation start
                terms = np.vstack([np.minimum(hi_x + MARGIN, 1.0), hi_b, hi_s])
                which = np.where(np.isfinite(terms).any(0), np.nanargmax(np.where(np.isfinite(terms), terms, -1), 0), -1)
                laminar_te = np.array([bool(np.any(np.where(ok[i], x[i], 0.0) >= 0.999)) for i in range(n)])
                w[side] = {"xtr_min": _nl(lo_x), "xtr_max": _nl(hi_x), "bubble_start_min": _nl(lo_b),
                           "bubble_end_max": _nl(hi_b), "sep_start_max": _nl(hi_s),
                           "band": [list(map(float, v)) for v in env],
                           "covered": [bool(c) for c in (short <= TOL) | ~has],
                           "short_c": [float(v) if h else None for v, h in zip(short, has)],
                           "aft_end_set_by": [("transition + margin", "bubble end", "separation start")[k] if k >= 0 else None
                                              for k in which],
                           "laminar_to_te": [bool(v) for v in laminar_te],
                           "transition_inside_band": [None if not h else bool(hx <= gb[1] + TOL and lx >= gb[0] - TOL)
                                                      for h, lx, hx in zip(has, lo_x, hi_x)]}
            d[f"to_{wname}"] = w
        out[f"{re_:.3g}"] = d
    return out


def _nl(a) -> list:
    return [None if not np.isfinite(v) else round(float(v), 4) for v in np.asarray(a, float)]


# --- summary --------------------------------------------------------------------------------------------
def summary(wings: list[dict], nums: list[dict]) -> dict:
    out = {}
    for t in TYPES:
        idx = [k for k, w in enumerate(wings) if w["wing"]["type"] == t]
        out[t] = {}
        for re_ in RE_LEVELS:
            key = f"{re_:.3g}"
            s = {}
            for wname in WINDOWS:
                ws = {}
                for side in ("upper", "lower"):
                    cov, short, has, xmax, xmin, inside, lam, setby = [], [], [], [], [], [], [], []
                    for k in idx:
                        w = nums[k][key][f"to_{wname}"]
                        h = [not f for f in w["fallback"]]
                        has += h
                        cov += [c for c, hh in zip(w[side]["covered"], h) if hh]
                        short += [v for v, hh in zip(w[side]["short_c"], h) if hh]
                        xmax += [v for v, hh in zip(w[side]["xtr_max"], h) if hh and v is not None]
                        xmin += [v for v, hh in zip(w[side]["xtr_min"], h) if hh and v is not None]
                        inside += [v for v, hh in zip(w[side]["transition_inside_band"], h) if hh]
                        lam += [v for v, hh in zip(w[side]["laminar_to_te"], h) if hh]
                        setby += [v for v, hh, c in zip(w[side]["aft_end_set_by"], h, w[side]["covered"]) if hh and not c]
                    short = np.array(short, float)
                    ws[side] = {"strips": len(has), "strips_with_answer": int(sum(has)),
                                "covered_share": float(np.mean(cov)) if cov else None,
                                "not_covered": int(len(cov) - sum(cov)),
                                "short_c_max": float(short.max()) if len(short) else None,
                                "short_c_median_of_not_covered": float(np.median(short[short > TOL])) if np.any(short > TOL) else None,
                                "wings_not_covered": int(sum(any(not c for c, f in zip(nums[k][key][f"to_{wname}"][side]["covered"],
                                                                                       nums[k][key][f"to_{wname}"]["fallback"]) if not f)
                                                             for k in idx)),
                                "transition_inside_share": float(np.mean(inside)) if inside else None,
                                "xtr_max": float(np.max(xmax)) if xmax else None,
                                "xtr_min": float(np.min(xmin)) if xmin else None,
                                "xtr_max_median": float(np.median(xmax)) if xmax else None,
                                "xtr_min_median": float(np.median(xmin)) if xmin else None,
                                "laminar_to_te_strips": int(sum(lam)),
                                "aft_end_set_by_of_not_covered": {v: setby.count(v) for v in set(setby)}}
                s[f"to_{wname}"] = ws
            # no answer, per angle, summed over the type's wings
            na = {c: np.sum([nums[k][key]["no_answer"][c] for k in idx], 0).tolist()
                  for c in ("below_tables", "stall_or_failed", "clamped_answered")}
            n_strips = sum(wings[k]["shape"][0] for k in idx)
            na["strips"] = n_strips
            na["share_below_tables"] = [v / n_strips for v in na["below_tables"]]
            na["share_stall_or_failed"] = [v / n_strips for v in na["stall_or_failed"]]
            s["no_answer"] = na
            s["re_strip"] = [min(nums[k][key]["re_strip"][0] for k in idx), max(nums[k][key]["re_strip"][1] for k in idx)]
            s["strips_below_tables"] = int(sum(nums[k][key]["strips_below_tables"] for k in idx))
            s["strips_above_tables"] = int(sum(nums[k][key]["strips_above_tables"] for k in idx))
            out[t][key] = s
    return out


def first_approach() -> dict | None:
    """The record (real size, Mach 0.03-0.13 for both families as in Study 8, -5 to 8 deg, margin 10 % c, old
    tables): the share of strips whose upper band lies inside 0-85 % c, per type; and its Re range."""
    if not FIRST.exists():
        return None
    doc = json.loads(FIRST.read_text())
    out = {"what": "first-approach record: old reference wings at real size, Mach 0.03-0.13 at sea level, -5 to 8 deg, "
                   "margin 10 % c, tables before the nose fix; upper band 0-85 % c (the same as now)"}
    for t in TYPES:
        cov, short, has_n, re_lo, re_hi = [], [], 0, [], []
        for w in (w for w in doc["wings"] if w["wing"]["type"] == t):
            b = envelope_band(w, machs=(0.03, 0.13), alphas=(-5.0, 8.0), margin=MARGIN)
            env = np.array(b["upper"], float)
            h = ~np.array(b["fallback"])
            sh = np.maximum(env[:, 1] - GENERIC_BAND["upper"][1], 0.0)
            cov += list(sh[h] <= TOL); short += list(sh[h]); has_n += int(h.sum())
            g = w["grid"]
            M = np.repeat(np.asarray(g["mach"]), len(g["alpha_deg"]) * len(g["alt_m"]))
            re_m = np.array(w["per_condition"]["re_mean"], float)[(M >= 0.03 - TOL) & (M <= 0.13 + TOL)]
            re_lo.append(float(re_m.min())); re_hi.append(float(re_m.max()))
        out[t] = {"upper_covered_share": float(np.mean(cov)), "strips_with_answer": has_n,
                  "short_c_max": float(np.max(short)), "re_mean_range": [min(re_lo), max(re_hi)]}
    return out


# --- main ------------------------------------------------------------------------------------------------
def build() -> dict:
    t0 = time.time()
    wings, nums = [], []
    for t in TYPES:
        for i in range(5):
            sm = strip_map(t, "reference", i, alphas=ALPHAS, n_per_panel=N_PER_PANEL, res=RE_LEVELS)
            sm["fields"].pop("cl", None)
            wings.append(sm)
            nums.append(wing_numbers(sm))
            print(t, i, "strips", sm["shape"][0], "answered", sum(sm["fields"]["answered"]), "of", len(sm["fields"]["answered"]))
    doc = {"what": "refine map by Re level (similarity, decision 70): the 20 reference wings, Re on the mean chord "
                   "10^5, 3 x 10^5, 1.5 x 10^6, 3 x 10^6 x root angle -5 to 12 deg, sea level, unit mean chord, the 2-D "
                   "tables at Mach 0.1, rebuilt on the fixed nose (decision 64)",
           "wings": wings, "numbers": nums, "summary": summary(wings, nums), "first_approach": first_approach(),
           "rules": {"decided_band": {k: list(v) for k, v in DECIDED_BAND.items()}, "margin": MARGIN,
                     "windows_deg": {k: list(v) for k, v in WINDOWS.items()}, "n_per_panel": N_PER_PANEL,
                     "mach_in_tables": MACH_SIMILARITY, "tables_re_range": [RE_LOW, RE_HIGH]},
           "source": "Stage 1 section tables (2-D XFOIL, free transition, N_crit 9; rebuilt 7 Nov 2026 on the fixed nose) "
                     "through cfdauto.flowmap.engine (strips, uniform elliptic induced angle) in the Re mode of "
                     "cfdauto.mesh.refine_map; sea level.",
           "seconds": round(time.time() - t0, 1)}
    return doc


def _aft_cells(m, lo: float, hi: float) -> dict:
    """Largest ring cell / the station's band cell, over the stations, with the cell centre at lo-hi x/c, per side."""
    n = m.info["n_side"]
    out = {}
    for side, sl in (("upper", slice(0, n)), ("lower", slice(n - 1, 2 * n - 1))):
        worst = []
        for j, st in enumerate(m.stations):
            p, u = m.wing[sl, j], m.u[sl, j]
            if side == "upper":
                p, u = p[::-1], u[::-1]
            d = np.linalg.norm(np.diff(p, axis=0), axis=1) / st["chord_m"]
            uc = 0.5 * (u[1:] + u[:-1])
            k = (uc >= lo) & (uc <= hi)
            worst.append(float(np.max(d[k]) / st["h_band_c"]))
        out[side] = {"max": float(np.max(worst)), "median": float(np.median(worst))}
    return out


def as_built(level: str = "VC") -> dict:
    """The decided rules as built (configs/surface.yaml, level VC): on reference wing 0 of each type at the four Re
    levels, the largest ring cell over 85-99.5 % c against the station's band cell, per side (decision 60: both sides
    share one node distribution, the stricter side wins, so the lower band 0-100 % c also sets the upper side).
    And the same surfaces with the upper band written as 0-100 % c: are the nodes the same?"""
    import tempfile

    import yaml

    from cfdauto.mesh.surface import build_surface, wing_from_set
    cfg = STAGE2 / "configs" / "surface.yaml"
    raw = yaml.safe_load(cfg.read_text())
    raw["chord"]["band_upper"] = [0.0, 1.0]
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        alt = Path(tmp) / "surface_upper_0_100.yaml"
        alt.write_text(yaml.safe_dump(raw, sort_keys=False))
        for t in TYPES:
            w = wing_from_set(t, "reference", 0)
            for re_ in RE_LEVELS:
                t0 = time.time()
                m = build_surface(w.loft, re_, level)
                m2 = build_surface(w.loft, re_, level, config=alt)
                rows.append({"type": t, "index": 0, "re": re_, "level": level, "passed": bool(m.passed),
                             "n_side": int(m.info["n_side"]), "stations": len(m.stations),
                             "aft_85_995": _aft_cells(m, 0.85, 0.995), "mid_30_70": _aft_cells(m, 0.30, 0.70),
                             "upper_0_100_same_nodes": m.node_hash() == m2.node_hash(),
                             "upper_0_100_n_side": int(m2.info["n_side"]),
                             "upper_0_100_max_du": (float(np.nanmax(np.abs(m.u - m2.u))) if m.u.shape == m2.u.shape else None),
                             "seconds": round(time.time() - t0, 1)})
                r = rows[-1]
                print(f"  built {t} 0 Re {re_:.3g}: upper cell at 85-99.5 % c / band cell max {r['aft_85_995']['upper']['max']:.3f}, "
                      f"lower {r['aft_85_995']['lower']['max']:.3f}; upper band 0-100 % c same nodes: "
                      f"{r['upper_0_100_same_nodes']}, n_side {r['n_side']} -> {r['upper_0_100_n_side']}, "
                      f"largest node move {r['upper_0_100_max_du']} c ({r['seconds']} s)", flush=True)
    up = [r["aft_85_995"]["upper"]["max"] for r in rows]
    return {"what": "decided rules as built (level VC): the largest ring cell over 85-99.5 % c / the station's band cell, "
                    "max over the stations, per side; reference wing 0 of each type at the four Re levels. And whether "
                    "writing the upper band as 0-100 % c changes the nodes.",
            "builds": rows, "upper_ratio_max": float(max(up)), "upper_ratio_min": float(min(up)),
            "all_same_nodes_with_upper_0_100": bool(all(r["upper_0_100_same_nodes"] for r in rows)),
            "same_ring_count_with_upper_0_100": int(sum(r["n_side"] == r["upper_0_100_n_side"] for r in rows)),
            "largest_node_move_with_upper_0_100_c": max((r["upper_0_100_max_du"] or 0.0) for r in rows)}


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="The refine map by Re level on the 20 reference wings.")
    p.add_argument("--figures", action="store_true", help="only redraw the figures from the JSON")
    p.add_argument("--built", action="store_true", help="also build the 16 surfaces of the as-built check (about 5 min); "
                                                       "without it the check already in the JSON is kept")
    a = p.parse_args(argv)
    if a.figures:
        doc = json.loads(OUT.read_text())
    else:
        old = json.loads(OUT.read_text()).get("as_built") if OUT.exists() else None
        doc = build()
        doc["as_built"] = as_built() if a.built else old
        doc["figures"] = CAPTIONS
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(doc, separators=(",", ":")))
        print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.2f} MB, {doc['seconds']} s for the maps")
    figures(doc)


# --- figures ---------------------------------------------------------------------------------------------
INK, MUTED, LINE, SHADE = "#142230", "#566573", "#D6DEE6", "#EEF1F4"
RAMP = ("#86b6ef", "#3987e5", "#1c5cab", "#0d366b")   # Re 10^5 -> 3 x 10^6: one hue, light -> dark (ordinal, validated)
CAPTIONS = {
    "refine_re_transition.png": {
        "what": "Median transition position over the 65 strips of each type (5 wings × 13 strips) against the root angle, "
                "at the four Re levels on the mean chord, upper and lower side, with the decided bands: upper 0–85 % c "
                "(shaded: beyond it), lower 0–100 % c.",
        "conclusion": "The upper transition moves aft as the angle and the Re fall: at 10⁵ its median sits at 88–100 % c at "
                      "−5° on every type, past the upper band's end; the lower transition comes to the leading edge at "
                      "negative angles (median 0–29 % c at −5°), which the lower band 0–100 % c holds."},
    "refine_re_coverage.png": {
        "what": "Per type and Re level, −5° to 8°: the share of strips whose band (transition ± 10 % c, bubbles, separation "
                "start) fits inside the written upper band 0–85 % c, the share whose transition itself fits (tick), and how "
                "far the band's aft end goes past 85 % c.",
        "conclusion": "As written, the upper band misses the upper transition on most strips at 10⁵ and 3 × 10⁵ (0–49 % fit, "
                      "short by up to 15 % c, to the trailing edge) and on 3–68 % at 1.5 × 10⁶ and 3 × 10⁶; as built this is "
                      "no gap, because the shared node distribution (decision 60) and the lower band 0–100 % c already give "
                      "the upper side band cells to the trailing edge."},
    "refine_re_no_answer.png": {
        "what": "Share of strips with no XFOIL answer against the root angle, per type and Re level; no strip is below the "
                "tables' lowest Re, so each one is beyond the section's 2-D stall or a failed point.",
        "conclusion": "Only the tailless wings lose answers in numbers, at negative root angles (up to 46 % of the BWB and "
                      "43 % of the flying-wing strips at −5°), where their outboard sections (MH 61, MH 60 / MH 45) are "
                      "below the lowest angle XFOIL converges at; the band there rests on the other angles."},
}


def _style() -> None:
    plt.rcParams.update({"font.size": 10.5, "axes.edgecolor": LINE, "axes.labelcolor": INK, "xtick.color": MUTED,
                         "ytick.color": MUTED, "axes.titlesize": 11, "axes.titlecolor": INK, "legend.fontsize": 9.5,
                         "figure.dpi": 130, "savefig.dpi": 130, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titlelocation": "left"})


def _save(fig, name: str) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / name, bbox_inches="tight")
    plt.close(fig)
    print("wrote", FIG / name)


def _median_xtr(doc: dict, t: str, field: str) -> np.ndarray:
    """Median over the type's strips with an answer, per Re level and angle: (n_re, n_alpha)."""
    ws = [w for w in doc["wings"] if w["wing"]["type"] == t]
    g = ws[0]["grid"]
    na = len(g["alpha_deg"])
    X = np.vstack([np.where(_f(w, "answered"), _f(w, field), np.nan) for w in ws])
    with np.errstate(all="ignore"):
        return np.array([np.nanmedian(X[:, k * na:(k + 1) * na], 0) for k in range(len(g["re"]))])


def fig_transition(doc: dict) -> None:
    g = doc["wings"][0]["grid"]
    al = np.asarray(g["alpha_deg"])
    fig, ax = plt.subplots(len(TYPES), 2, figsize=(7.4, 11.2), sharex=True, sharey=True)
    for r, t in enumerate(TYPES):
        for c, (side, field) in enumerate((("upper", "xtr_u"), ("lower", "xtr_l"))):
            a = ax[r, c]
            gb = DECIDED_BAND[side]
            if gb[1] < 1.0:
                a.axhspan(gb[1], 1.02, color=SHADE, lw=0)
                a.axhline(gb[1], color=INK, lw=1.2)
                a.axhline(gb[1] - MARGIN, color=INK, lw=0.9, ls=(0, (4, 3)))
            med = _median_xtr(doc, t, field)
            for k, re_ in enumerate(g["re"]):
                a.plot(al, med[k], "-o", color=RAMP[k], lw=1.9, ms=3.6, label=f"Re {re_label(re_)}")
            a.set_ylim(-0.02, 1.02)
            a.set_xlim(al[0] - 0.5, al[-1] + 0.5)
            a.axvline(WINDOWS["8"][1], color=MUTED, lw=0.9, ls=":")
            a.grid(True, color=LINE, lw=0.5)
            a.set_axisbelow(True)
            a.set_title(f"{TYPE_NAME[t]}, {side} side", fontsize=10.5)
            if c == 0:
                a.set_ylabel("transition, x/c")
            if r == len(TYPES) - 1:
                a.set_xlabel("root angle [°]")
            if r == 0 and c == 0:
                a.text(al[-1] + 0.3, gb[1] + 0.015, "upper band ends: 85 % c", fontsize=8.5, color=INK, va="bottom", ha="right",
                       bbox=dict(fc=SHADE, ec="none", pad=0.5), zorder=5)
                a.text(al[-1] + 0.3, gb[1] - MARGIN + 0.015, "85 % c − 10 % c margin", fontsize=8.5, color=INK, va="bottom",
                       ha="right", bbox=dict(fc="#ffffff", ec="none", pad=0.5), zorder=5)
            if r == 0 and c == 1:
                a.text(al[-1] + 0.3, 0.03, "lower band: the whole chord", fontsize=8.5, color=INK, ha="right")
    h, lab = ax[0, 0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.995), fontsize=9.5,
               title="Re on the mean chord (median over the 65 strips of each type; dotted: 8°)", title_fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    _save(fig, "refine_re_transition.png")


def fig_coverage(doc: dict) -> None:
    S = doc["summary"]
    fig, ax = plt.subplots(2, 1, figsize=(7.4, 7.4), sharex=True)
    x = np.arange(len(TYPES))
    wbar = 0.2
    for k, re_ in enumerate(RE_LEVELS):
        key = f"{re_:.3g}"
        u = [S[t][key]["to_8"]["upper"] for t in TYPES]
        cov = [100 * v["covered_share"] for v in u]
        bare = [100 * v["transition_inside_share"] for v in u]
        med = [100 * (v["short_c_median_of_not_covered"] or 0.0) for v in u]
        top = [100 * (v["short_c_max"] or 0.0) for v in u]
        xs = x + (k - 1.5) * wbar
        ax[0].bar(xs, cov, width=wbar - 0.03, color=RAMP[k], label=f"Re {re_label(re_)}")
        ax[0].plot(xs, bare, "_", color=INK, ms=13, mew=2.2)
        ax[1].bar(xs, med, width=wbar - 0.03, color=RAMP[k])
        ax[1].plot(xs, top, "_", color=INK, ms=13, mew=2.2)
        for xi, v in zip(xs, cov):
            ax[0].text(xi, 2, f"{v:.0f}", ha="center", va="bottom", fontsize=7.5,
                       color="#ffffff" if v >= 8 and k >= 1 else INK)
    ax[0].set_ylim(0, 105)
    ax[0].set_ylabel("strips inside 0–85 % c [%]")
    ax[0].set_title("Upper side, −5° to 8°: strips whose band fits inside the written band 0–85 % c\n"
                    "(bar: transition ± 10 % c; tick: the transition itself, no margin)")
    ax[0].set_yticks([0, 25, 50, 75, 100])
    ax[1].set_ylim(0, 17)
    ax[1].set_ylabel("past 85 % c [% c]")
    ax[1].set_title("Strips that do not fit: how far the band's aft end goes past 85 % c\n"
                    "(bar: median; tick: largest; 15 % c = to the trailing edge)")
    ax[1].set_xticks(x, [TYPE_NAME[t] for t in TYPES])
    for a in ax:
        a.grid(True, axis="y", color=LINE, lw=0.5)
        a.set_axisbelow(True)
    h = [plt.Rectangle((0, 0), 1, 1, color=c) for c in RAMP]
    fig.legend(h, [f"Re {re_label(r)}" for r in RE_LEVELS], loc="upper center", ncol=4, frameon=False,
               bbox_to_anchor=(0.5, 1.0), fontsize=9.5, title="Re on the mean chord", title_fontsize=9.5)
    fig.text(0.01, 0.0, "As written, per side. As built, both sides share one node list (decision 60) and the lower band is "
                        "0–100 % c,\nso the upper side also has band cells to the trailing edge (16 built surfaces, see the note).",
             fontsize=8.5, color=MUTED, ha="left", va="top")
    fig.tight_layout(rect=(0, 0.02, 1, 0.93))
    _save(fig, "refine_re_coverage.png")


def fig_no_answer(doc: dict) -> None:
    S = doc["summary"]
    al = np.asarray(doc["wings"][0]["grid"]["alpha_deg"])
    fig, ax = plt.subplots(2, 2, figsize=(7.4, 6.4), sharex=True, sharey=True)
    top = 0.0
    for a, t in zip(ax.ravel(), TYPES):
        for k, re_ in enumerate(RE_LEVELS):
            na = S[t][f"{re_:.3g}"]["no_answer"]
            stall = 100 * np.asarray(na["share_stall_or_failed"])
            low = 100 * np.asarray(na["share_below_tables"])
            top = max(top, float(stall.max()), float(low.max()))
            a.plot(al, stall, "-o", color=RAMP[k], lw=1.9, ms=3.6, label=f"Re {re_label(re_)}")
            if low.max() > 0:
                a.plot(al, low, "--s", color=RAMP[k], lw=1.4, ms=3.4)
        a.set_title(TYPE_NAME[t], fontsize=10.5)
        a.grid(True, color=LINE, lw=0.5)
        a.set_axisbelow(True)
    for a in ax[:, 0]:
        a.set_ylabel("strips with no answer [%]")
    for a in ax[1]:
        a.set_xlabel("root angle [°]")
    ax[0, 0].set_ylim(-1, max(5.0, top * 1.12))
    h, lab = ax[0, 0].get_legend_handles_labels()
    below = sum(sum(S[t][f"{r:.3g}"]["no_answer"]["below_tables"]) for t in TYPES for r in RE_LEVELS)
    fig.legend(h, lab, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.0), fontsize=9.5,
               title=("No XFOIL answer, Re on the mean chord: beyond the section's 2-D stall or a failed point"
                      + (" (solid); local Re below the tables' 1.5 × 10⁴ (dashed)" if below
                         else ";\nno strip has a local Re below the tables' lowest (1.5 × 10⁴)")), title_fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    _save(fig, "refine_re_no_answer.png")


def figures(doc: dict) -> None:
    _style()
    fig_transition(doc)
    fig_coverage(doc)
    fig_no_answer(doc)


if __name__ == "__main__":
    main()
