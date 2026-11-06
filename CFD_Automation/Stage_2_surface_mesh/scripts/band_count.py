"""Study 8 · the band count for negative angles (decision 74): option A against option B on the 20 reference wings.

    python scripts/band_count.py            # about 10 min: 160 builds at VC (+ 4 at F), the refine-map numbers, the figure
    python scripts/band_count.py --figure   # only redraw docs/page/band_count.png from data/studies/band_count.json

Option B: keep the lower band at 60–100 % c, and run transition (SU2 LM) only at angles ≥ 0°.
Option A: the lower band from the leading edge, 0–100 % c.
Option A': a per-wing lower band from the refine map (−5° to 8°, Mach 0.03–0.13, 10 % c margin). One node list
serves the whole wing (decision 60), so the band of a wing is the union over its strips.

The rules are the planned rules of the new approach at the coarsest level VC (configs/surface_plan_VC.yaml: the
lighter band, tip gap 2 × s0, station gap 0.25 c at M). Only band_lower changes between the options. A finer level
has every VC spacing ÷ 1.3^k, so the ratio A / B at F equals the ratio at VC up to whole-number rounding.
Wing-block cells = ring cells × station gaps × wall layers; only the ring depends on the band.
Reads data/studies/refine_map_reference.json (scripts/refine_map_data.py) for the lower side at negative angles,
the Study 7 numbers over the new envelope, and A'.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import matplotlib
import numpy as np
import yaml

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto.mesh.laws import rules  # noqa: E402
from cfdauto.mesh.refine_map import GENERIC_BAND, envelope_band  # noqa: E402
from cfdauto.mesh.ring import RingSpec, Section  # noqa: E402
from cfdauto.mesh.surface import build_surface, wing_from_set  # noqa: E402
from cfdauto.paths import STAGE2  # noqa: E402

PLAN = STAGE2 / "configs" / "surface_plan_VC.yaml"
MAP = STAGE2 / "data" / "studies" / "refine_map_reference.json"
OUT = STAGE2 / "data" / "studies" / "band_count.json"
FIG = STAGE2 / "docs" / "page" / "band_count.png"
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
TYPE_NAME = {"bwb": "BWB", "flying_wing": "flying wing", "cranked": "cranked", "tapered": "tapered"}
RE_LEVELS = (1.0e5, 3.0e5, 1.5e6, 3.0e6)   # the four Re levels (Stage 0 values.yaml)
LOWER = {"B": [0.60, 1.00], "A": [0.00, 1.00]}
F_MEDIAN_B = 10.9e6               # fine-level estimate with the lighter band and the option-B band (6 Nov 2026)
ENVELOPE = {"machs": (0.03, 0.13), "alphas": (-5.0, 8.0), "margin": 0.10}
ANGLES = (-5.0, -2.0, 0.0, 4.0, 8.0)
INK, MUTED, LINE = "#142230", "#566573", "#D6DEE6"
ACC, AMBER, WARN = "#0C5EA8", "#9A6200", "#B02A20"


# --- the refine-map numbers ------------------------------------------------------------------

def _f(w: dict, name: str) -> np.ndarray:
    n, m = w["shape"]
    return np.array([np.nan if v is None else v for v in w["fields"][name]], float).reshape(n, m)


def _stats(x: np.ndarray) -> dict | None:
    x = x[np.isfinite(x)]
    if not len(x):
        return None
    return {"median": float(np.median(x)), "min": float(x.min()), "max": float(x.max()),
            "q25": float(np.percentile(x, 25)), "q75": float(np.percentile(x, 75)), "n": int(len(x))}


def lower_side(doc: dict) -> dict:
    """Per type and root angle: where the lower side turns turbulent and where its bubbles sit, over every strip of
    the 5 wings and Mach 0.03–0.13 (sea level); and how far in front of the generic lower band (60 % c) that is."""
    g = doc["wings"][0]["grid"]
    M, A = np.meshgrid(np.asarray(g["mach"]), np.asarray(g["alpha_deg"]), indexing="ij")
    out = {}
    for t in TYPES:
        ws = [w for w in doc["wings"] if w["wing"]["type"] == t]
        out[t] = {}
        for a in ANGLES:
            k = (M.ravel() <= ENVELOPE["machs"][1] + 1e-9) & (np.abs(A.ravel() - a) < 1e-9)
            xt, bs, be, n_all = [], [], [], 0
            for w in ws:
                ans = np.array(w["fields"]["answered"]).reshape(w["shape"])[:, k]
                n_all += ans.size
                xt.append(_f(w, "xtr_l")[:, k][ans]); bs.append(_f(w, "bub_l_s")[:, k][ans]); be.append(_f(w, "bub_l_e")[:, k][ans])
            xt, bs, be = np.concatenate(xt), np.concatenate(bs), np.concatenate(be)
            first = np.fmin(xt, bs)                        # where the band must start: the bubble start, else transition
            miss = np.maximum(0.0, GENERIC_BAND["lower"][0] - first)
            out[t][f"{a:g}"] = {"strip_conditions": n_all, "answered": int(len(xt)),
                                "transition": _stats(xt), "bubble_start": _stats(bs), "bubble_end": _stats(be),
                                "bubble_share": float(np.mean(np.isfinite(bs))) if len(bs) else None,
                                "forward_of_band_share": float(np.mean(first < GENERIC_BAND["lower"][0])) if len(first) else None,
                                "missed_c": {"median": float(np.median(miss)), "max": float(miss.max())} if len(miss) else None}
    return out


def study7(doc: dict, alphas: tuple[float, float]) -> dict:
    """The Study 7 numbers (as the refine page computes them) over one angle envelope: band cells per side summed
    over the strips at the Re of Mach 0.08 (first-approach band cell, the page's rule), per wing against generic;
    the widest stretch outside the generic band; the shortest root bubble against the table at the root's Re."""
    R = doc["rules"]
    tab = R["bubble_table"]
    bub = lambda re: float(np.exp(np.interp(np.log(re), np.log(tab["re"]), np.log(tab["l_c"]))))
    cell = lambda re: min(bub(re) / R["nodes_per_bubble"], R["max_spacing_c"])
    G = GENERIC_BAND
    rows = []
    for w in doc["wings"]:
        g = w["grid"]
        E = envelope_band(w, machs=ENVELOPE["machs"], alphas=alphas, margin=ENVELOPE["margin"])
        k = g["mach"].index(0.08) * len(g["alpha_deg"]) + g["alpha_deg"].index(4.0)
        re = _f(w, "re")[:, k]
        h = np.array([cell(r) for r in re])
        gen = sum((G[s][1] - G[s][0]) / h for s in ("upper", "lower")).sum()
        own = sum((np.array(E[s])[:, 1] - np.array(E[s])[:, 0]) / h for s in ("upper", "lower")).sum()
        mu = ml = 0.0
        for i in range(len(h)):
            if E["fallback"][i]:
                continue
            u, lo = E["upper"][i], E["lower"][i]
            mu = max(mu, max(0, u[1] - G["upper"][1]) + max(0, G["upper"][0] - u[0]))
            ml = max(ml, max(0, lo[1] - G["lower"][1]) + max(0, G["lower"][0] - lo[0]))
        rows.append({"type": w["wing"]["type"], "index": w["wing"]["index"], "cost": float(own / gen - 1),
                     "missed_upper_c": mu, "missed_lower_c": ml, "shortest_root_bubble_c": E["shortest_bubble_c"]["upper"][0],
                     "table_at_root_c": bub(re[0]), "fallback_strips": int(sum(E["fallback"]))})
    c = np.array([r["cost"] for r in rows])
    sr = np.array([np.nan if r["shortest_root_bubble_c"] is None else r["shortest_root_bubble_c"] for r in rows])
    tb = np.array([r["table_at_root_c"] for r in rows])
    rng = lambda key: [float(min(r[key] for r in rows)), float(max(r[key] for r in rows))]
    return {"alphas": list(alphas), "machs": list(ENVELOPE["machs"]), "margin": ENVELOPE["margin"], "wings": rows,
            "cost": {"min": float(c.min()), "median": float(np.median(c)), "max": float(c.max())},
            "missed_upper_c": rng("missed_upper_c"), "missed_lower_c": rng("missed_lower_c"),
            "shortest_root_bubble_c": [float(np.nanmin(sr)), float(np.nanmax(sr))], "table_at_root_c": [float(tb.min()), float(tb.max())],
            "root_shorter_than_table": int(np.sum(sr < tb))}


def answered_share(doc: dict) -> dict:
    """Share of strip-conditions with an XFOIL answer, per type and root angle (Mach 0.03–0.13)."""
    g = doc["wings"][0]["grid"]
    M, A = np.meshgrid(np.asarray(g["mach"]), np.asarray(g["alpha_deg"]), indexing="ij")
    out = {}
    for t in TYPES:
        ws = [w for w in doc["wings"] if w["wing"]["type"] == t]
        out[t] = {}
        for a in g["alpha_deg"]:
            k = (M.ravel() <= ENVELOPE["machs"][1] + 1e-9) & (np.abs(A.ravel() - a) < 1e-9)
            an = np.concatenate([np.array(w["fields"]["answered"]).reshape(w["shape"])[:, k].ravel() for w in ws])
            out[t][f"{a:g}"] = float(an.mean())
    return out


def a_prime(doc: dict) -> list[dict]:
    """Option A': the lower band of each wing from its refine-map envelope, as one band for the wing (the union
    over its strips, because one node list serves every station)."""
    out = []
    for w in doc["wings"]:
        E = envelope_band(w, **ENVELOPE)
        lo = np.array(E["lower"])
        out.append({"type": w["wing"]["type"], "index": w["wing"]["index"],
                    "band_lower": [float(lo[:, 0].min()), float(lo[:, 1].max())],
                    "strips_from_le": int(np.sum(lo[:, 0] <= 1e-9)), "strips": int(len(lo))})
    return out


# --- the count -------------------------------------------------------------------------------

def variant_configs(folder: Path, bands: dict) -> dict:
    raw = yaml.safe_load(PLAN.read_text())
    paths = {}
    for name, lo in bands.items():
        r = json.loads(json.dumps(raw))
        r["chord"]["band_lower"] = list(lo)
        p = folder / f"surface_plan_VC_{name}.yaml"
        p.write_text(yaml.safe_dump(r, sort_keys=False))
        paths[name] = p
    return paths


def count(paths: dict) -> list[dict]:
    rows = []
    for t in TYPES:
        for i in range(5):
            w = wing_from_set(t, "reference", i)
            for re in RE_LEVELS:
                row = {"type": t, "index": i, "re_mean": re}
                for name, p in paths.items():
                    t0 = time.time()
                    m = build_surface(w.loft, re, "C", p)          # "C" in the plan file = the coarsest level, VC
                    row[name] = {"n_side": m.info["n_side"], "n_ring": m.info["n_ring"], "n_span": m.info["n_span"],
                                 "passed": m.passed, "failed": [c.name for c in m.failed()],
                                 "seconds": round(time.time() - t0, 2), "node_hash": m.node_hash()}
                row["ratio"] = row["A"]["n_ring"] / row["B"]["n_ring"]
                row["same_mesh"] = row["A"]["node_hash"] == row["B"]["node_hash"]
                rows.append(row)
                print(f"{t:12s} {i} Re {re:.0e}  ring B {row['B']['n_ring']}  A {row['A']['n_ring']}  ratio {row['ratio']:.4f}  "
                      f"same mesh {row['same_mesh']}  stations {row['B']['n_span']}  passed {row['B']['passed']}/{row['A']['passed']}", flush=True)
    return rows


def f_check(paths: dict) -> list[dict]:
    """Two wings at the fine level F (named FF in the plan file), A against B: the ratio holds there too."""
    rows = []
    for t, i, re in (("bwb", 0, 3.0e6), ("flying_wing", 0, 1.0e5)):
        w = wing_from_set(t, "reference", i)
        row = {"type": t, "index": i, "re_mean": re, "level": "F (FF in the plan file)"}
        for name, p in paths.items():
            m = build_surface(w.loft, re, "FF", p)
            row[name] = {"n_ring": m.info["n_ring"], "n_span": m.info["n_span"], "passed": m.passed, "node_hash": m.node_hash()}
        row["ratio"] = row["A"]["n_ring"] / row["B"]["n_ring"]
        row["same_mesh"] = row["A"]["node_hash"] == row["B"]["node_hash"]
        rows.append(row)
        print(f"F check {t} {i} Re {re:.0e}: ring B {row['B']['n_ring']} A {row['A']['n_ring']} same mesh {row['same_mesh']}", flush=True)
    return rows


def summary(rows: list[dict]) -> dict:
    per = {}
    for t in TYPES:
        per[t] = {}
        for re in RE_LEVELS:
            rr = [r for r in rows if r["type"] == t and r["re_mean"] == re]
            ra = np.array([r["ratio"] for r in rr])
            per[t][f"{re:.0e}"] = {"ring_B_median": float(np.median([r["B"]["n_ring"] for r in rr])),
                                   "ring_A_median": float(np.median([r["A"]["n_ring"] for r in rr])),
                                   "ring_B_range": [min(r["B"]["n_ring"] for r in rr), max(r["B"]["n_ring"] for r in rr)],
                                   "ratio_median": float(np.median(ra)), "ratio_max": float(ra.max())}
    ra = np.array([r["ratio"] for r in rows])
    return {"per_type_re": per, "ratio": {"min": float(ra.min()), "median": float(np.median(ra)), "max": float(ra.max())},
            "same_mesh": int(sum(r["same_mesh"] for r in rows)), "builds": 2 * len(rows),
            "passed": int(sum(r["A"]["passed"] + r["B"]["passed"] for r in rows)),
            "failed_checks": sorted({c for r in rows for k in ("A", "B") for c in r[k]["failed"]}),
            "seconds_median": float(np.median([r[k]["seconds"] for r in rows for k in ("A", "B")])),
            "F_median_B": F_MEDIAN_B, "F_median_A": F_MEDIAN_B * float(np.median(ra))}


# --- the figure ------------------------------------------------------------------------------

def why_rings(paths: dict) -> dict:
    """The BWB reference wing 0 at VC, Re 3e5: the delivered lower-side cells with B and with A, and the lower
    side's own wish list with B (what the lower side would get if it did not share the upper side's node list)."""
    w = wing_from_set("bwb", "reference", 0)
    rl = rules("C", paths["B"])
    out = {}
    for name in ("B", "A"):
        m = build_surface(w.loft, 3.0e5, "C", paths[name])
        n = m.info["n_side"]
        p, u = m.wing[n - 1: 2 * n - 1, 0], m.u[n - 1: 2 * n - 1, 0]        # root ring, lower side, nose -> TE
        d = np.linalg.norm(np.diff(p, axis=0), axis=1) / m.stations[0]["chord_m"]
        out[name] = {"x": 0.5 * (u[1:] + u[:-1]), "h": d}
        if name == "B":
            r0 = m.stations[0]
            sec = Section.at(w.loft, r0["v"], rl.dense_per_side)
            c = sec.chord
            sp = RingSpec(r0["h_le_c_asked"] * c, r0["h_band_c"] * c, rl.max_spacing_c * c, r0["h_te_c"] * c)
            own = sec.size_field(False, sp.h_le, sp.h_band, sp.h_max, sp.h_te, tuple(LOWER["B"]), rl.chord_growth, rl.nose_turning_deg)
            out["own_B"] = {"x": sec.u, "h": own / c}
            out["band_cell"] = r0["h_band_c"]
    return out


def figure(doc: dict, paths: dict) -> None:
    plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": LINE, "axes.labelcolor": INK, "xtick.color": MUTED,
                         "ytick.color": MUTED, "axes.titlesize": 10, "axes.titlecolor": INK, "legend.fontsize": 8.5,
                         "figure.dpi": 130, "savefig.dpi": 130, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(1, 3, figsize=(14.5, 4.9), gridspec_kw={"width_ratios": [1.15, 1.0, 0.85]})
    # 1. where the lower side turns turbulent, per type and root angle, against the generic lower band
    a = ax[0]
    ls = doc["refine_map"]["lower_side"]
    labels, y = [], 0
    for t in TYPES:
        for ang in ("-5", "-2", "0", "4"):
            s = ls[t][ang]["transition"]
            if s:
                a.plot([s["min"] * 100, s["max"] * 100], [y, y], color=MUTED, lw=1.0)
                a.plot([s["q25"] * 100, s["q75"] * 100], [y, y], color=ACC, lw=4, solid_capstyle="butt")
                a.plot([s["median"] * 100], [y], "o", color=INK, ms=4.5)
                share = ls[t][ang]["forward_of_band_share"]
                a.text(103, y, f"{share * 100:.0f} %", va="center", fontsize=7.8, color=INK)
            labels.append((f"{TYPE_NAME[t]}  {int(ang):+d}°" if ang != "0" else f"{TYPE_NAME[t]}  0°").replace("-", "−"))
            y += 1
        y += 0.6
    yt = [i + 0.6 * (i // 4) for i in range(len(labels))]
    a.set_yticks(yt, labels, fontsize=8)
    a.set_ylim(yt[-1] + 0.8, -2.4)
    a.axvspan(60, 100, color=AMBER, alpha=0.13, lw=0)
    a.text(80, -0.8, "generic lower band\n60–100 % c (option B)", ha="center", va="bottom", fontsize=7.8, color=AMBER)
    a.text(103, -0.8, "in front\nof 60 % c", ha="left", va="bottom", fontsize=7.5, color=MUTED)
    a.set_xlim(0, 114); a.set_xticks([0, 20, 40, 60, 80, 100])
    a.set_xlabel("lower-surface transition, x/c [%]")
    a.set_title("Where the lower side turns turbulent (2-D strips, Mach 0.03–0.13)\ndot: median · bar: middle half · line: range", fontsize=9)
    a.grid(axis="x", color=LINE, lw=0.5)
    # 2. why A costs nothing: the lower side takes the upper side's node list
    a = ax[1]
    wr = doc["_why"]
    a.axvspan(60, 100, color=AMBER, alpha=0.13, lw=0)
    a.plot(wr["own_B"]["x"] * 100, wr["own_B"]["h"] * 100, color=MUTED, lw=1.2, ls="--")
    a.plot(wr["B"]["x"] * 100, wr["B"]["h"] * 100, color=ACC, lw=2.2)
    a.plot(wr["A"]["x"] * 100, wr["A"]["h"] * 100, "o", color=AMBER, ms=2.6, mfc="none", mew=0.9)
    a.axhline(wr["band_cell"] * 100, color=INK, lw=0.8, ls=":")
    a.text(62, wr["band_cell"] * 100 * 1.08, f"band cell {wr['band_cell'] * 100:.1f} % c", fontsize=7.8, color=INK, va="bottom")
    a.text(12, 4.2, "the lower side's own wish list with B: coarse in front of 60 % c", fontsize=7.8, color=MUTED, va="bottom")
    a.text(30, wr["band_cell"] * 100 * 0.55, "delivered with B (line) and A (circles):\nthe same cells, node for node", fontsize=7.8, color=INK, va="top")
    a.set_yscale("log"); a.set_ylim(0.02, 9); a.set_xlim(0, 100)
    a.set_xlabel("lower surface, x/c [%]"); a.set_ylabel("cell size [% c]")
    a.set_title("Why A adds nothing: BWB reference wing 0, root ring,\nVC, Re 3 × 10⁵. Both sides share one node list (decision 60)", fontsize=9)
    a.grid(axis="y", color=LINE, lw=0.5)
    # 3. the count: ring nodes A against B, 20 wings × 4 Re
    a = ax[2]
    rows = doc["builds"]
    b = np.array([r["B"]["n_ring"] for r in rows]); aa = np.array([r["A"]["n_ring"] for r in rows])
    lo, hi = 0.9 * b.min(), 1.08 * b.max()
    a.plot([lo, hi], [lo, hi], color=LINE, lw=1.0)
    a.plot(b, aa, "o", color=ACC, ms=5, mfc="none", mew=1.1)
    s = doc["summary"]
    a.text(lo + 0.03 * (hi - lo), hi - 0.04 * (hi - lo), f"{s['builds']} builds: A / B = {s['ratio']['median']:.3f} (median), "
           f"{s['ratio']['max']:.3f} (max)\nthe same mesh on {s['same_mesh']} of {len(rows)} pairs", fontsize=7.8, color=INK, va="top")
    a.text(hi - 0.02 * (hi - lo), lo + 0.03 * (hi - lo), "one circle per wing and Re level; many overlap:\nthe rings are the same at Re 10⁶ and 3 × 10⁶\n(the bubble table's 0.10 c floor)",
           fontsize=7.5, color=MUTED, ha="right", va="bottom")
    a.set_xlim(lo, hi); a.set_ylim(lo, hi); a.set_aspect("equal")
    a.set_xlabel("ring nodes, option B (lower band 60–100 % c)"); a.set_ylabel("ring nodes, option A (0–100 % c)")
    a.set_title("The count at VC (planned rules):\n20 reference wings × 4 Re on the mean chord", fontsize=9)
    a.grid(color=LINE, lw=0.5)
    fig.tight_layout()
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG)
    plt.close(fig)
    print("wrote", FIG)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="band_count_"))
    paths = variant_configs(tmp, LOWER)
    rmap = json.loads(MAP.read_text())
    if "--figure" in sys.argv:
        doc = json.loads(OUT.read_text())
    else:
        doc = {"what": "Study 8: ring nodes of the 20 reference wings x 4 Re at VC for the lower band of option B "
                       "(60-100 % c) and option A (0-100 % c), decision 74; and the refine-map numbers behind it",
               "config": "configs/surface_plan_VC.yaml (planned rules at VC; only chord.band_lower changes)",
               "level": "VC (named C in the plan file)", "re_levels": list(RE_LEVELS), "lower_bands": LOWER,
               "scaling": "a finer level has every VC spacing / 1.3^k, so A/B at F = A/B at VC up to whole-number "
                          "rounding; wing-block cells scale with ring nodes (stations and wall layers do not depend on the band)"}
        doc["refine_map"] = {"envelope": {k: list(v) if isinstance(v, tuple) else v for k, v in ENVELOPE.items()},
                             "answered_share": answered_share(rmap), "lower_side": lower_side(rmap),
                             "study7_new": study7(rmap, ENVELOPE["alphas"]), "study7_first_envelope": study7(rmap, (0.0, 8.0)),
                             "a_prime": a_prime(rmap)}
        doc["builds"] = count(paths)
        doc["f_check"] = f_check(paths)
        doc["summary"] = summary(doc["builds"])
        ap = doc["refine_map"]["a_prime"]
        doc["summary"]["a_prime_equals_A"] = all(abs(r["band_lower"][0]) < 1e-9 and r["band_lower"][1] > 1 - 1e-9 for r in ap)
        OUT.write_text(json.dumps(doc, indent=1))
        print("wrote", OUT)
    doc["_why"] = why_rings(paths)
    figure(doc, paths)


if __name__ == "__main__":
    main()
