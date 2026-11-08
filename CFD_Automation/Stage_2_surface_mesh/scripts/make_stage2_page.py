"""One HTML page to understand and judge the surface mesher: docs/SURFACE_MESH.html.

    python scripts/change_figures.py      # docs/page/levels_first_new.png etc. (the new rules, from laws.py)
    python scripts/built_figures.py       # docs/page/nose_fixed.png, similarity_check.png (7 Nov)
    python scripts/screen_study.py        # the new screen: data/studies/screen_*.json, docs/page/screen_new_*.png
    python scripts/make_stage2_page.py    # then this page (+ docs/SURFACE_MESH.body.html for publishing)

The first-approach pictures (docs/page/*.png of Studies 1-7, docs/*.png) were drawn on 2-7 Nov on the geometry of
before similarity and the nose fix; scripts/page_figures.py and make_figures.py redraw them with --code <a checkout of
commit 7bcb7067>. Every number comes from configs/surface.yaml, configs/surface_first.yaml and data/studies/*.json
(and Stage_1_geometry/data/studies/nose_curvature.json). The words are written below; edit them when a decision
changes. Same style as Stage 1's GEOMETRY_GENERATOR.html.
"""

from __future__ import annotations

import base64
import html
import json
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from cfdauto import __version__  # noqa: E402
from cfdauto.mesh.laws import first_cell_c, rules  # noqa: E402

FIRST = ROOT / "configs" / "surface_first.yaml"    # the first approach (2-3 Nov): every first-approach value
LEVELS = ("VC", "C", "M", "F")                     # the new levels (built 7 Nov)
N_TESTS = 43                                       # pytest Stage_2_surface_mesh/tests, 8 Nov 2026 (2 for the family nose)
STAGE1 = ROOT.parent / "Stage_1_geometry"
DOCS = ROOT / "docs"
PAGE = DOCS / "page"
STUDIES = ROOT / "data" / "studies"
TYPES = ("bwb", "flying_wing", "cranked", "tapered")
RE_NAME = {1e5: "10⁵", 3e5: "3 × 10⁵", 1e6: "10⁶", 1.5e6: "1.5 × 10⁶", 3e6: "3 × 10⁶", 4e6: "4 × 10⁶"}
TYPE_NAME = {"bwb": "BWB", "flying_wing": "flying wing", "cranked": "cranked", "tapered": "tapered"}


def img(path: Path, alt: str) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{html.escape(alt)}" loading="lazy">'


def fig(name: str, caption: str, folder: Path = PAGE) -> str:
    return f'<figure class="card">{img(folder / name, caption)}<figcaption class="cap">{caption}</figcaption></figure>'


def figc(name: str, shows: str, concl: str, folder: Path = PAGE) -> str:
    """A figure with what it shows (caption) and its conclusion (box), as on the Stage 1 page."""
    return (f'<figure class="card">{img(folder / name, shows)}<figcaption class="cap"><em>What it shows.</em> {shows}</figcaption></figure>'
            f'<div class="cbox"><span class="ctag">Conclusion</span>{concl}</div>')


def cbox(text: str, tag: str = "Conclusion") -> str:
    return f'<div class="cbox"><span class="ctag">{tag}</span>{text}</div>'


def chg(text: str, tag: str = "What changes (decided 6 Nov, built 7 Nov 2026)", cls: str = "chg") -> str:
    """An amber box: what the new approach changes in this section (decided 6 Nov 2026; the surface rules built
    7 Nov; the volume mesh is Stage 3)."""
    return f'<div class="cbox {cls}"><span class="ctag">{tag}</span>{text}</div>'


R_FAM = 1.3


def bubble_new(re: float) -> float:
    """New approach (decision 72, built 7 Nov): the bubble-length table of configs/surface.yaml (floor 0.10 c from
    local Re 4e5 up)."""
    return rules("VC").bubble_length_c(re)


def _per(f, fmt="{:.3g}") -> str:
    """One value at VC, C, M, F from the code (laws.py, configs/surface.yaml), as 'a / b / c / d'."""
    return " / ".join(fmt.format(f(rules(lev))) for lev in LEVELS)


def new_rule_text() -> dict:
    """The rules table's "New approach" column: the built values per level, read from laws.py."""
    return {
        "Nose turning": f"10° met at <strong>M</strong> (an accuracy target): {_per(lambda r: r.nose_turning_deg)}° at VC / C / M / F, each level checked against its own angle + 0.2°. The nose is solved at every level, each for its own angle, and the strictest spacing wins (decided 7 Nov), so every level meets its own angle and the family rule stays exact",
        "Nose, along the semi-span": "unchanged (1.15 between stations)",
        "Trailing edge": f"0.1 % c met at <strong>M</strong>: {_per(lambda r: 100 * r.te_spacing_c)} % c",
        "Blunt base": f"{_per(lambda r: r.base_cells, '{:d}')} cells (≥ 8 at VC is a hard minimum; even counts)",
        "Transition band": f"cell = bubble length / 20 met at <strong>F</strong>: / {_per(lambda r: r.cells_per_bubble)}; the bubble length stops at 0.10 c from local Re 4 × 10⁵ up (decision 72), so the cell there is {_per(lambda r: 100 * r.band_spacing_c(1e6))} % c. Upper band 0–100 % c since 8 Nov (owner; written 0–85 % c before, while the built mesh already had band-size cells to the trailing edge: one node list, decision 60, and the lower band; Study 11). Lower band 0–100 % c (decision 74, option A, decided 7 Nov)",
        "Largest cell": f"2 % c met at M: {_per(lambda r: 100 * r.max_spacing_c)} % c",
        "Growth along the ring": f"built {_per(lambda r: r.chord_growth)}; checked {_per(lambda r: r.chord_growth_limit)} (within 1 %): 1.25 at VC is a hard minimum and the limit follows the family rule (a builder choice, stricter)",
        "Stations": f"gap / local chord {_per(lambda r: r.span_spacing_c)} (0.25 at <strong>M</strong>); at least {_per(lambda r: r.min_cells_per_panel, '{:d}')} gaps per panel; growth built {_per(lambda r: r.span_growth)}, checked {_per(lambda r: r.span_growth_limit)}",
        "Tip": f"last gap = <strong>2 × s0</strong> at every level; s0 from y⁺ = {_per(lambda r: r.yplus, '{:.2f}')} (1 at VC is a hard minimum)",
        "Levels": "<strong>VC, C, M, F</strong> (built 7 Nov): VC on the desktop, C, M and F on the university HPC; hard minimums at VC, accuracy targets at M, transition targets at F (decision 71)",
    }


def _uc_text(uc: dict) -> str:
    """The upper band written 0-100 % c against 0-85 % c, in words (data/studies/upper_band_check.json)."""
    vc, f = uc["levels"]["VC"], uc["levels"]["F"]
    return (f"on 7 Nov, at the Re levels of that day: at VC the same mesh to round-off ({vc['same_counts']} of {vc['builds']} reference builds with the same counts, "
            f"no node moved by more than {_sci(vc['largest_node_move_c'])} c); at F 2 more ring nodes on "
            f"{f['ring_nodes_added'].get('2', 0)} of {f['builds']} ({100 * (f['cells_ratio']['median'] - 1):.2f} % more cells, median), "
            f"so the screen was re-run: Study 12)")


def _sci(v: float) -> str:
    m, e = f"{v:.1e}".split("e")
    return f"{m} × 10" + str(int(e)).translate(str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹"))


def change_table(sn: dict, uc: dict) -> str:
    """What was first (built 2-3 Nov) and what the new approach changes (decided 4-6 Nov; built 7 Nov where it says)."""
    f = sn["reference"]["F"]["cells_est"]
    rows = [
        ("Levels, and where each target sits", "C, M, F, FF. Every rule met at C, the coarsest level: each finer level only went past the targets, at about 2.2 × the cells per level.",
         "VC, C, M, F. Hard minimums at VC (y⁺ ≤ 1, growth ≤ 1.25, base ≥ 8, no kinks, tip gap); accuracy targets at M (nose 10°, trailing edge 0.1 % c, station gap, largest cell), as the DPW guidelines define their medium grid; transition targets at F (20 cells per bubble; wall growth 1.25 at VC is 1.107 at F, just above the 1.1 a transition model asks for). VC on the desktop; C, M, F on the university HPC. Built 7 Nov (<code>configs/surface.yaml</code>, <code>laws.py</code>); screened (Study 9). The nose is solved at every level and the strictest wins (owner, 7 Nov). Two builder choices, both stricter, confirmed by Mike on 8 Nov: the growth limits follow the family rule; the station growth kept at 1.2.", "decided 6 Nov; built 7 Nov", "built"),
        ("Transition band cell", "bubble length / 20 at C; bubble 0.40 / 0.30 / 0.10 / 0.05 c at local Re 6 × 10⁴ / 10⁵ / 4 × 10⁵ / 10⁶.",
         "bubble length / 20 at F; the bubble length stops at 0.10 c from local Re 4 × 10⁵ up, so the cell is 0.5 % c at F there (the shortest high-Re root bubbles, about 1.5 % c, then get about 3 cells: fine for SA, not for LM). Built 7 Nov.", "decided 6 Nov; built 7 Nov", "built"),
        ("Stations and tip", "gap 0.2 × local chord at C, at least 12 per panel; last gap at the tip = s0.",
         "gap 0.25 × local chord at M, at least 12 per panel at M; last gap at the tip = 2 × s0. Built 7 Nov. The station growth stays 1.2 (as decided), so the built rules give 7–14 more stations (about +17 %) than the plan file of Study 8 (growth 1.25, 7 gaps per panel).", "decided 6 Nov; built 7 Nov", "built"),
        ("Lower band", "60–100 % c, set for angles 0–8°.",
         "From the leading edge: 0–100 % c (option A, decided by Mike on 7 Nov; built). Angles now run from −5°, and at −5° the lower side takes the suction peak near the nose. It costs no cells: on the 20 reference wings × 4 Re levels A and B gave the same ring, node for node (Study 8), because both sides share one node list and the upper band (0–85 % c) already makes the front of the lower side fine.", "decided 7 Nov; built 7 Nov", "built"),
        ("Upper band", "0–85 % c, from the leading edge on every wing (decision 58).",
         f"Written 0–100 % c since 8 Nov (owner). At the Re levels the upper transition sits past 85 % c at low Re and low angle (0–49 % of the strips fit 0–85 % c at Re 10⁵ and 3 × 10⁵; Study 11); the built ring already had band-size cells there (one node list, decision 60, and the lower band 0–100 % c), so the rule now says what the mesh does. The cost: {_uc_text(uc)}. Screened in Study 12.", "decided 8 Nov; built 8 Nov", "built"),
        ("Volume mesh (Stage 3)", "O-H body mesh (S8) with an overset wake box and a tip-vortex tube; ADflow only (SU2 has no overset).",
         "One matched C-H multiblock mesh for ADflow and SU2 (SU2 reads it converted to unstructured hexes). Wake lines from the trailing edge to the far field; the tip vortex resolved in the outboard blocks; no overlap gate. The ring and the cap of Stage 2 stay as they are.", "decided 6 Nov", "Stage 3"),
        ("Wing size and Re (similarity)", "Wings at real size; Re 3 × 10⁵ on the mean chord for the screen, 4 Re levels on the reference wings; trailing edge max(0.5 mm Class I / 1.0 mm Class II, 0.2 % c).",
         "Every wing at unit mean chord (area / full span); the Re on the mean chord is an input (4 levels: 10⁵, 3 × 10⁵, 10⁶, 4 × 10⁶ since 8 Nov, were 1.5 × 10⁶ and 3 × 10⁶; 10⁵ is 18 % below the slowest real UAV, kept as a margin, Mike, 7 Nov); Mach 0.1 with a Prandtl–Glauert correction on CL and CM; trailing edge 0.2 % c; the root chord leaves the vector (18 → 17 numbers); no 7 m full-span cap. Built in Stage 1 on 7 Nov: the sets rebuilt (722 of 722), 13 of the 20 reference wings are new picks. Checked in Stage 2 (Study 10).", "decided 6 Nov; built 7 Nov", "built (Stage 1)"),
        ("Re levels (78)", "10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶ on the mean chord (top 3 × 10⁶ from the fastest real Class II wing).",
         "10⁵, 3 × 10⁵, 10⁶, 4 × 10⁶ (Mike, 8 Nov): 4 × 10⁶ takes in every cruise point of the Greek tactical programmes (LOTUS, Archytas, ACTUS; Stage 0); 10⁶ fills the old ×5 gap (check C4 on 2-D data). Still 4 levels and 8,000 solves. Re-screened on 8 Nov (Study 9): the 20 reference wings at the new levels, 320 of 320 builds pass; at F the two moved levels have 0.7 % fewer cells, and the largest F mesh is 10.17 M (was 9.74 M), 1.7 % above 10 M. The refine map redone (Study 11).", "decided 8 Nov", "screened"),
        ("Flow model", "Fully turbulent ADflow SA planned; the turbulence model left to a later stage.",
         "Transition must be captured, with ADflow and SU2 (4 Nov). Split, proposal (pending): ADflow SA for the mesh studies and the fully turbulent data; SU2 SST + LM on about 20 % of the wings.", "decided 4 Nov; split pending", "—"),
        ("Angles of attack", "0–8° (12° for the nose and wake studies).",
         "−5° to post-stall; steady RANS up to stall onset; a separate post-stall study (URANS or DDES on a few wings).", "decided 6 Nov", "—"),
        ("Mach", "0.03–0.13 tailless, 0.03–0.20 conventional.",
         "Toward 0.5, no supersonic flow (4 Nov). Core Mach ≤ 0.2 now; 0.3–0.5 later with a fast-UAV family (pending). Under similarity the dataset runs at Mach 0.1.", "decided 4 Nov; core pending", "—"),
        ("Nose shape (64)", "First reading: the built nose is not round (upper and lower radius 3–13 × apart on cambered noses).",
         "The defect was real, and the 6 Nov note that it was overstated was wrong. One curvature method found it between the raw points: the old rule made a spike on one side and a flat spot on the other (NACA 4415: a 0.18 % c nose cell turned 9.47° built against 4.31° true). Fixed in Stage 1 on 7 Nov (Mike): one cubic spline, the leading edge at its apex, 201 points per side; a gate refuses 14 database files whose nose folds back; 95.6 % of the database passes the 5 % test (21.0 % before). Study 4.", "decided 7 Nov; built 7 Nov", "built (Stage 1)"),
        ("Mesh size, fine level", "No target.",
         f"Counted 7 Nov (Study 9; the count the pages use, because it can be redone): F {f['median'] / 1e6:.1f} M cells median on the wing blocks over the 20 reference wings × 4 Re (largest {f['max'] / 1e6:.1f} M), against the 9–11 M asked. The first estimate (6 Nov) gave 10.9 M, with a wall-layer rule that was not recorded, on the first-approach reference wings. The C-H wake lines add a rough +30–60 %. Stage 3 sets the real wall-layer rule.", "screened 7 Nov", "screened"),
    ]
    flag = {"built": "ok", "built (Stage 1)": "ok", "built (as written)": "ok", "screened": "ok", "Stage 3": "s3", "—": "s3"}
    out = ['<div class="tbl"><table class="wide"><tr><th>What</th><th>First (built and screened 2–3 Nov)</th><th>New approach</th><th>Decided</th><th>Built?</th></tr>']
    for what, first, new, when, st in rows:
        badge = "—" if st == "—" else f"<span class='flag {flag[st]}'>{st}</span>"
        out.append(f"<tr><td class='what'>{what}</td><td class='src'>{first}</td><td class='new'>{new}</td><td class='src'>{when}</td><td>{badge}</td></tr>")
    out.append("</table></div>")
    return "".join(out)


def load() -> dict:
    cfg = yaml.safe_load(FIRST.read_text())                       # the rules table's first column
    screen = json.loads((STUDIES / "screen_C.json").read_text())
    fam = json.loads((STUDIES / "family_ratios.json").read_text())
    nose = json.loads((STUDIES / "nose_radius.json").read_text())
    bc = json.loads((STUDIES / "band_count.json").read_text())
    sn = json.loads((STUDIES / "screen_new_summary.json").read_text())       # Study 9 (scripts/screen_study.py)
    sim = json.loads((STUDIES / "similarity_check.json").read_text())        # Study 10 (scripts/similarity_check.py)
    nc = json.loads((STAGE1 / "data" / "studies" / "nose_curvature.json").read_text())   # Study 4, 7 Nov
    rre = json.loads((STUDIES / "refine_map_re.json").read_text())           # Study 11 (scripts/refine_map_re.py)
    uc = json.loads((STUDIES / "upper_band_check.json").read_text())         # the upper band written 0-100 % c
    return {"cfg": cfg, "screen": screen, "fam": fam, "nose": nose, "bc": bc, "sn": sn, "sim": sim, "nc": nc,
            "rre": rre, "uc": uc}


def _pc(v: float) -> str:
    return f"{v * 100:.0f} %"


def band_count_tables(bc: dict) -> str:
    """Study 8: the lower side at negative angles (refine map) and the ring count A against B (data/studies/band_count.json)."""
    ls = bc["refine_map"]["lower_side"]
    out = ['<div class="tbl"><table class="wide"><tr><th>Type</th><th>Root angle</th><th>Strips × Mach values with an answer</th>'
           '<th>Lower transition x/c: median (range)</th><th>Lower bubble: share of strips; start x/c median (range)</th>'
           '<th>Transition or bubble in front of 60 % c</th><th>Missed by the generic lower band: median / max</th></tr>']
    for t in TYPES:
        for a in ("-5", "-2", "0"):
            d = ls[t][a]
            tr, bs = d["transition"], d["bubble_start"]
            bub = f"{_pc(d['bubble_share'])}; {_pc(bs['median'])} ({_pc(bs['min'])}–{_pc(bs['max'])})" if bs else f"{_pc(d['bubble_share'])}; –"
            ang = f"{int(a):+d}°".replace("-", "−") if a != "0" else "0°"
            out.append(f"<tr><td class='what'>{TYPE_NAME[t]}</td><td class='num'>{ang}</td><td class='num'>{d['answered']} of {d['strip_conditions']}</td>"
                       f"<td class='num'>{_pc(tr['median'])} ({_pc(tr['min'])}–{_pc(tr['max'])})</td><td class='num'>{bub}</td>"
                       f"<td class='num'>{_pc(d['forward_of_band_share'])}</td><td class='num'>{d['missed_c']['median'] * 100:.0f} / {d['missed_c']['max'] * 100:.0f} % c</td></tr>")
    out.append("</table></div>")
    s = bc["summary"]
    res = ["10⁵", "3 × 10⁵", "1.5 × 10⁶", "3 × 10⁶"]
    keys = ["1.0e+05", "3.0e+05", "1.5e+06", "3.0e+06"]
    out.append('<div class="tbl"><table class="mid"><tr><th>Type (5 wings)</th>' + "".join(f"<th>Re {r}: ring nodes B / A (median)</th>" for r in res)
               + "<th>Ratio A / B: median / max</th></tr>")
    for t in TYPES:
        p = s["per_type_re"][t]
        cells = "".join(f"<td class='num'>{p[k]['ring_B_median']:.0f} / {p[k]['ring_A_median']:.0f}</td>" for k in keys)
        ra = [r["ratio"] for r in bc["builds"] if r["type"] == t]
        rmed, rmax = float(np.median(ra)), max(ra)
        out.append(f"<tr><td class='what'>{TYPE_NAME[t]}</td>{cells}<td class='num'>{rmed:.3f} / {rmax:.3f}</td></tr>")
    out.append(f"<tr><td class='what'>All {len(bc['builds'])} pairs</td><td colspan='4'>the same mesh, node for node, on {s['same_mesh']} of {len(bc['builds'])} pairs; "
               f"{s['passed']} of {s['builds']} builds pass every check</td><td class='num'>{s['ratio']['median']:.3f} / {s['ratio']['max']:.3f}</td></tr>")
    out.append(f"<tr><td class='what'>Fine level F (estimate of 6 Nov)</td><td colspan='4'>wing blocks, median: 10.9 M cells with B × the median ratio (the screen of the built rules: Study 9)</td>"
               f"<td class='num'>{s['F_median_A'] / 1e6:.1f} M with A</td></tr></table></div>")
    return "".join(out)


# --------------------------------------------------------------------------------------
# tables from the data
# --------------------------------------------------------------------------------------

def screen_table(screen: dict) -> tuple[str, dict]:
    rows = [r for r in screen["rows"] if r["built"]]
    s = screen["summary"]
    out = ['<div class="tbl"><table class="mid"><tr><th>Type (builds)</th><th>Ring nodes min–median–max</th><th>Stations</th>'
           '<th>Quads</th><th>Build time [s]</th><th>Wing quads J min / median</th><th>Cap quads J min / median</th><th>Passed</th></tr>']
    stats = {}
    for t in TYPES:
        rr = [r for r in rows if r["wing_type"] == t and r["re_mean"] == 3.0e5]
        nr = np.array([r["n_ring"] for r in rr]); ns = np.array([r["n_span"] for r in rr]); q = np.array([r["quads"] for r in rr])
        sec = np.array([r["seconds"] for r in rr]); wq = np.array([r["checks"]["wing_quads"] for r in rr]); cq = np.array([r["checks"]["cap_quads"] for r in rr])
        n_all = sum(1 for r in screen["rows"] if r["wing_type"] == t)
        n_ok = sum(1 for r in screen["rows"] if r["wing_type"] == t and r["passed"])
        stats[t] = {"n": len(rr), "ring": (nr.min(), np.median(nr), nr.max()), "span": (ns.min(), np.median(ns), ns.max()),
                    "wq": (wq.min(), np.median(wq)), "cq": (cq.min(), np.median(cq))}
        out.append(f"<tr><td class='what'>{TYPE_NAME[t]} ({n_all})</td><td class='num'>{nr.min()}–{int(np.median(nr))}–{nr.max()}</td>"
                   f"<td class='num'>{ns.min()}–{int(np.median(ns))}–{ns.max()}</td><td class='num'>{q.min() / 1e3:.0f}k–{np.median(q) / 1e3:.0f}k–{q.max() / 1e3:.0f}k</td>"
                   f"<td class='num'>{sec.min():.1f}–{np.median(sec):.1f}–{sec.max():.1f}</td><td class='num'>{wq.min():.2f} / {np.median(wq):.2f}</td>"
                   f"<td class='num'>{cq.min():.2f} / {np.median(cq):.2f}</td><td class='num'>{n_ok} / {n_all}</td></tr>")
    out.append("</table></div>")
    ref = [r for r in rows if r["set"] == "reference"]
    rl = ['<div class="tbl"><table class="mid"><tr><th>Re on the mean chord</th>' + "".join(f"<th>{TYPE_NAME[t]}: ring × stations (5 wings)</th>" for t in TYPES) + "</tr>"]
    for re in (1e5, 3e5, 1.5e6, 3e6):
        cells = []
        for t in TYPES:
            rr = [r for r in ref if r["wing_type"] == t and r["re_mean"] == re]
            cells.append(f"<td class='num'>{min(r['n_ring'] for r in rr)}–{max(r['n_ring'] for r in rr)} × {min(r['n_span'] for r in rr)}–{max(r['n_span'] for r in rr)}</td>")
        rl.append(f"<tr><td class='what'>{re:.1e}</td>{''.join(cells)}</tr>")
    rl.append("</table></div>")
    tot = {"total": s["total"], "passed": s["passed"], "crashed": sum(1 for r in screen["rows"] if not r["built"]),
           "max_turn": max(r["checks"]["nose_turning"] for r in rows), "max_growth": max(r["checks"]["chord_growth"] for r in rows),
           "repairs": sum(1 for r in rows if r["turning_repairs"] > 0), "min_wq": min(r["checks"]["wing_quads"] for r in rows),
           "min_cq": min(r["checks"]["cap_quads"] for r in rows), "sec_med": s["seconds"]["median"], "sec_max": s["seconds"]["max"],
           "n_wings": len({(r["wing_type"], r["set"], r["index"]) for r in screen["rows"]})}
    return "".join(out) + "".join(rl), tot | {"stats": stats}


def family_table(fam: dict) -> str:
    keys = [("nose_root", "nose cell, root"), ("nose_tip", "nose cell, tip"), ("te_root", "trailing-edge cell"), ("band_root", "band cell, root"),
            ("band_tip", "band cell, tip"), ("root_gap", "first station gap"), ("tip_gap", "last station gap (tip)"), ("base_cell", "base cell")]
    out = ['<div class="tbl"><table class="mid"><tr><th>Spacing</th>' + "".join(f"<th>{TYPE_NAME[t]} C/M</th><th>{TYPE_NAME[t]} M/F</th>" for t in TYPES) + "</tr>"]
    for k, name in keys:
        cells = "".join(f"<td class='num'>{fam['wings'][t]['ratios']['C/M'][k]:.3f}</td><td class='num'>{fam['wings'][t]['ratios']['M/F'][k]:.3f}</td>" for t in TYPES)
        out.append(f"<tr><td class='what'>{name}</td>{cells}</tr>")
    cnt = "".join(f"<td class='num' colspan='2'>{' / '.join(str(fam['wings'][t]['counts'][l]['n_ring']) + ' × ' + str(fam['wings'][t]['counts'][l]['n_span']) for l in ('C', 'M', 'F'))}</td>" for t in TYPES)
    out.append(f"<tr><td class='what'>ring × stations at C / M / F</td>{cnt}</tr></table></div>")
    return "".join(out)


def nose_table(nose: dict) -> str:
    out = ['<div class="tbl"><table class="mid"><tr><th>Section</th><th>Raw file: R/c at the leading-edge point</th><th>Built: upper side</th><th>Built: lower side</th><th>Ratio built / raw</th></tr>']
    for name in ("naca4415", "e387", "sd7032", "mh104", "mh61", "mh45", "mh60", "s5010", "la2573a", "naca25118"):
        d = nose.get(name, {})
        if "raw" not in d:
            continue
        r, m = d["raw"]["R_c_at_le_point"], d["resampled"]
        out.append(f"<tr><td class='what'>{name}</td><td class='num'>{r:.4f}</td><td class='num'>{m['R_c_upper']:.4f}</td><td class='num'>{m['R_c_lower']:.4f}</td>"
                   f"<td class='num'>{m['R_c_upper'] / r:.1f} × / {m['R_c_lower'] / r:.1f} ×</td></tr>")
    out.append("</table></div>")
    return "".join(out)


def rules_table(cfg: dict) -> str:
    """cfg: the first approach's YAML (configs/surface_first.yaml); the New column is read from laws.py."""
    ch, sp = cfg["chord"], cfg["span"]
    rc = rules("C", FIRST)
    new_rule = new_rule_text()
    vc, fl = rules("VC"), rules("F")
    rows = [
        ("Nose turning", "law 1", f"no ring node turns the surface by more than {ch['nose_turning_deg']:g}° (± {ch['nose_turning_tol_deg']}); solved by bisection on the ring as built; away from the nose the same angle caps the cell from the local curvature radius (cell ≤ R × 10°, x/c > 0.5 %)", "10° is the Grand Roadmap's starting value (law 1), not a derived number; the primer plans a ladder 12 / 10 / 8 / 6° in T6 to test it. Meaning: a straight cell that turns the surface by θ misses the curve by about R θ² / 8, 0.4 % of the local radius at 10°, and a half-round nose gets 18 cells. S8: measured on the built ring, because a radius estimate gave 20° for 6° asked"),
        ("Nose, along the semi-span", "law 2", f"nose spacing / chord changes by at most {ch['nose_envelope']} between stations", "S8; holds by construction with one distribution for the wing"),
        ("Trailing edge", "law 3", f"{ch['te_spacing_c'] * 100:g} % of the local chord at the two corners", "DPW gridding guidelines (Levy et al. 2013)"),
        ("Blunt base", "law 6", f"{ch['base_cells']} cells across the base at C (even, so the cap's nose arc is centred): 10, 14, 18 at M, F, FF", "S8 (base cells 4/6/8 ladder); our choice"),
        ("Transition band", "Stage 1", f"upper surface {ch['band_upper'][0] * 100:g}–{ch['band_upper'][1] * 100:g} % c, lower {ch['band_lower'][0] * 100:g}–{ch['band_lower'][1] * 100:g} % c; cell = bubble length / {ch['nodes_per_bubble']:g}; bubble length from the local Re: "
         + ", ".join(f"{float(l):g} c at {float(re):.0e}" for re, l in zip(ch['bubble_length']['re'], ch['bubble_length']['l_c'])) + " (log-log between the points, constant outside)",
         "Stage 1 handover (band, bubble lengths from 2-D XFOIL, N_crit 9); Ansys CFX Modeling Guide, γ-Re_θ transition model: at least 20 nodes across a bubble"),
        ("Largest cell", "own", f"{ch['max_spacing_c'] * 100:g} % c outside the bands", "our choice (starting value)"),
        ("Growth along the ring", "DPW", f"{ch['growth']} per cell used to build the size field; checked ≤ {ch['growth_limit']} (within 1 %)", "Stage 1 handover; DPW"),
        ("Stations", "laws 8, 9", f"one exactly on every loft station; gap = {sp['spacing_c']:g} × local chord, at least {sp['min_cells_per_panel']} gaps per panel; growth {sp['growth']} (checked ≤ {sp['growth_limit']})", "our starting values; the spanwise ladder decides"),
        ("Tip", "laws 9, 10, 13", f"stations squeezed so the last gap = {sp['tip_gap_in_s0']:g} × the tip first cell s0; s0 / c = y⁺ / (Re √(Cf/2)), Cf = 0.026 Re^(−1/7) at y⁺ = {cfg['wall']['yplus']:g}", "Grand Roadmap (cap first cell = tip s0); turbulent flat plate (White 2006)"),
        ("Levels", "law 23", f"C, M, F, FF: every spacing ÷ {cfg['levels']['ratio']}^k, the growth g^(1 / {cfg['levels']['ratio']}^k) so each level is a true scaled copy", "Celik et al. 2008 (r ≥ 1.3)"),
    ]
    out = ['<div class="tbl"><table class="wide"><tr><th>Where</th><th>Law</th><th>First: rule at level C (built 2–3 Nov)</th><th>New approach (built 7 Nov): VC / C / M / F, from <code>laws.py</code></th><th>Source</th></tr>']
    for what, law, rule, src in rows:
        out.append(f"<tr><td class='what'>{what}<span class='id'>{law}</span></td><td class='num'>{law}</td><td>{rule}</td><td class='new'>{new_rule[what]}</td><td class='src'>{src}</td></tr>")
    out.append("</table></div>")
    re_rows = "".join(f"<tr><td class='num'>{re:.0e}</td><td class='num'>{rc.bubble_length_c(re):.3f} c</td><td class='num'>{rc.band_spacing_c(re) * 100:.2f} % c</td>"
                      f"<td class='num'>{bubble_new(re):.3f} c</td><td class='num'>{fl.band_spacing_c(re) * 100:.2f} % c</td><td class='num'>{vc.band_spacing_c(re) * 100:.2f} % c</td>"
                      f"<td class='num'>{first_cell_c(re) * 100:.4f} % c</td></tr>"
                      for re in (6e4, 1e5, 3e5, 1e6, 3e6, 5.5e6))
    re_tab = ('<div class="tbl"><table class="mid"><tr><th>Local Re</th><th>First: bubble length</th><th>First: band cell (C)</th><th>New: bubble length</th>'
              '<th>New: band cell at F</th><th>New: band cell at VC (capped at the largest cell)</th><th>First wall cell s0, y⁺ = 1 (both: at the coarsest level)</th></tr>' + re_rows + "</table></div>")
    return "".join(out) + re_tab


def primer_table() -> str:
    rows = [
        ("R-S.1", "Station positions along the semi-span: count from the semi-span in local chords; nearly even from the root, squeezed toward the tip so the last gap equals the cap's first cell; set in metres, then converted to v.",
         "done", "Gap = 0.2 × local chord (law 8 as a chord rule, not a count), at least 12 per panel, growth 1.2; last gap = s0 at the tip Re; a station exactly on every loft station (added: the ruled loft has a crease there). Check <code>tip_gap</code>, <code>loft_stations_hit</code>, <code>span_growth</code>."),
        ("R-S.2", "Sample the section densely from the loft (1,601 points at C).", "done", "6,001 points per side, cosine in x/c; the dense curve only turns arc length into u; every node is evaluated on the loft."),
        ("R-S.3", "One ring per station: TE upper corner → nose → lower corner → across the base; n_side 75, n_base 9 at C; Vinokur two-sided stretching per side; the base even.",
         "changed", "Same ring order and the same 2·n_side + n_base − 3 nodes. Vinokur stretching is replaced by a size field + equidistribution, because the transition band needs a set cell size in the middle of a side, which a two-sided stretching cannot give. n_side is no longer a constant (75): it follows from the rules (≈180–430 at C)."),
        ("R-S.4", "Trailing-edge spacing 0.1 % of local chord (law 3).", "done", "Check <code>te_spacing</code> (delivered ≤ asked within 1 %)."),
        ("R-S.5", "Solve the nose spacing by bisection until the largest nose-cell turning is 10° ± 0.02° (law 1).", "done, widened", "Bisection on the ring as built; the check covers every ring node, not the nose ± 3 (on cambered noses the sharpest cell sat a few cells onto the lower surface); away from the nose the same angle caps the cell from the curvature; the solve walks down until a window [0.77 h, h] passes (the built noses are not monotone, decision 64)."),
        ("R-S.6", "Spanwise envelope on the nose spacing: at most 1.15 between neighbouring stations, only tightening (law 2).", "by construction", "One distribution for the whole wing makes the nose spacing / chord the same at every station; the check <code>nose_envelope</code> stays (reads ≈ 1.00)."),
        ("R-S.7", "Apply the family's refinement factor to the end spacings: every spacing ÷ r per level, not only the counts.", "done, widened", "Every spacing ÷ 1.3 per level and the growth g^(1/1.3), so the stretched parts refine too; verified on the four reference wings at C, M, F (ratios 1.30 ± 3 %)."),
        ("R-S.8", "Evaluate every node on the loft; never interpolate (wall within 1e-9 m).", "done", "Test <code>test_every_node_is_on_the_loft</code> (max distance 0 to machine precision)."),
        ("R-S.9", "Per-station table and checks: turning met, envelope clamps, nose spacing, scaled Jacobian of every quad, perimeter count; refuse to write otherwise.",
         "done", "<code>stations.csv</code> (asked and delivered per station), <code>quality.json</code> (13 checks with value and limit), refusal writes only <code>refusal.json</code>."),
        ("M1", "Every surface constant into one module with a stated input list (mesh_laws.py): n_side, n_base, n_span, station positions, nose target, TE spacing, envelope; n_base 9; cap first cell = tip s0 (refuse above 3 ×); per-station table with the nose aspect ratio and the mid-chord growth.",
         "done, partly", "<code>cfdauto/mesh/laws.py</code> reads <code>configs/surface.yaml</code>: one function per rule, with the level in. Not done: the nose aspect ratio column (needs the first wall cell, Stage 3); the bit-identical rebuild test of g83 does not apply (no AERIS wings in CFD_Automation); the mesh is rebuilt bit-identically for the same input (test <code>test_same_input_same_mesh</code>)."),
        ("M4 (surface part)", "One function makes any level from the baseline; a test that the ratio of every spacing equals r within 1 %.", "done (3 %)", "<code>rules(level)</code> + <code>scripts/family_check.py</code>; ratios within 3 % (1 % is not reachable with whole numbers of gaps per panel and even base counts)."),
        ("Stage 1 handover", "Fine at the nose, over a wide transition band (upper 10–85 % c, from the leading edge on swept panels; lower 60–100 % c), at the trailing edge (0.1 % c, 8 base cells), on every break, toward the tip (cap first cell = tip first cell), station count scaling with semi-span / mean chord; cells per bubble: no source yet.",
         "done, with two changes", "The upper band starts at the leading edge on every wing (decision 58); the cells-per-bubble rule now has a source (20, decision 56). The wall and wake rows of the handover are Stage 3."),
    ]
    out = ['<div class="tbl"><table class="wide"><tr><th>Item</th><th>What the primer / handover asks</th><th>Status</th><th>What was built, and the evidence</th></tr>']
    cls = {"done": "ok", "changed": "chg", "done, widened": "ok", "by construction": "ok", "done, partly": "part", "done (3 %)": "ok", "done, with two changes": "chg"}
    for i, what, st, ev in rows:
        out.append(f"<tr><td class='what'>{i}</td><td>{what}</td><td><span class='flag {cls[st]}'>{st}</span></td><td>{ev}</td></tr>")
    out.append("</table></div>")
    return "".join(out)


def checks_table() -> str:
    lv = [rules(lev) for lev in LEVELS]
    turn = " / ".join(f"{r.nose_turning_deg + 10 * r.nose_turning_tol_deg:.3g}" for r in lv) + "°"
    new = {"nose_turning": f"≤ {turn}", "geometry_kinks": f"≤ {turn}",
           "chord_growth": "≤ " + " / ".join(f"{r.chord_growth_limit:.3g}" for r in lv) + " (within 1 %)",
           "span_growth": "≤ " + " / ".join(f"{r.span_growth_limit:.3g}" for r in lv),
           "tip_gap": "0.8 … 1.01 × (2 × s0)", "te_spacing": "trailing-edge cell / the level's own (" +
           " / ".join(f"{100 * r.te_spacing_c:.3g}" for r in lv) + " % c) ≤ 1.01",
           "band_spacing": "≤ 1.01 × the level's band cell (bubble / " + " / ".join(f"{r.cells_per_bubble:.3g}" for r in lv) + ")"}
    rows = [
        ("nose_turning", "largest turning at any ring node (not the two TE corners, not geometry kinks)", "≤ 10.2°"),
        ("geometry_kinks", "a kink of the section itself (a dense step turning > 1°), which no cell size can reduce", "≤ 10.2°"),
        ("nose_envelope", "nose spacing / chord between neighbouring stations", "≤ 1.15"),
        ("chord_growth", "neighbouring cells along the ring", "≤ 1.25 (within 1 %)"),
        ("band_spacing", "largest cell inside the band / the band target", "≤ 1.01"),
        ("te_spacing", "trailing-edge cell / 0.1 % c", "≤ 1.01"),
        ("span_growth", "neighbouring station gaps", "≤ 1.3"),
        ("loft_stations_hit", "distance from the nearest station to every loft station", "0 m"),
        ("tip_gap", "last station gap / tip first cell", "0.8 … 1.01"),
        ("planar_stations", "every ring in its station plane (y = const)", "≤ 1e-9 m"),
        ("wing_quads", "smallest scaled Jacobian of the wing quads", "≥ 0.05"),
        ("cap_quads", "smallest scaled Jacobian of the cap quads, the two nose-corner cells apart", "≥ 0.05"),
        ("cap_nose_corners", "the two cap cells with three corners on the smooth nose", "> 0 (not folded)"),
        ("ring_count", "unique ring nodes", "= 2 n_side + n_base − 3"),
    ]
    out = ['<div class="tbl"><table class="mid"><tr><th>Check</th><th>What it measures</th><th>Limit, first (level C)</th><th>Limit, new: VC / C / M / F (built 7 Nov)</th></tr>']
    for n, w, l in rows:
        out.append(f"<tr><td class='what'><code>{n}</code></td><td>{w}</td><td class='num'>{l}</td><td class='num'>{new.get(n, 'the same')}</td></tr>")
    out.append("</table></div>")
    return "".join(out)


def nose_fixed_block(nc: dict, sim: dict) -> str:
    """Study 4, second correction (7 Nov): the nose defect is real and fixed in Stage 1 (decision 64), from
    Stage_1_geometry/data/studies/nose_curvature.json and data/studies/similarity_check.json."""
    a = nc["airfoils"]
    t44 = {r: a["naca4415"]["curves"][r]["T_deg"] for r in ("raw", "old", "new")}
    d44 = a["naca4415"]["curves"]["old"]["T_diff_vs_raw_pct"]
    new_worst = max(((abs(v), v, n) for n in a for v in a[n]["curves"]["new"]["T_diff_vs_raw_pct"]), key=lambda x: x[0])
    t_exact = a["naca4415"]["curves"]["exact"]["T_deg"]
    minus = lambda x: f"{x}".replace("-", "−")
    db = nc["database"]["summary"]
    ln = nc["stage2_nose_line"]
    key = lambda r: (r["wing_type"], r["index"], r["re_mean"])
    before = {key(r): r for r in sim["similarity_only"]["rows"]}
    after = {key(r): r for r in sim["similarity_and_nose"]["rows"]}
    conv = [k for k in before if k[0] in ("cranked", "tapered")]
    mh = [k for k in before if k[0] in ("bwb", "flying_wing")]
    nb = lambda ks, d: (min(100 * d[k]["nose_h_le_c"][0] for k in ks), max(100 * d[k]["nose_h_le_c"][0] for k in ks))
    cb, ca, mb, ma = nb(conv, before), nb(conv, after), nb(mh, before), nb(mh, after)
    dr = sorted({after[k]["n_ring"] - before[k]["n_ring"] for k in before})
    same_span = all(after[k]["n_span"] == before[k]["n_span"] for k in before)
    tilt = [abs(a[n]["tangent_tilt_at_le_deg"]) for n in a]
    move = [a[n]["le_move_pct"] for n in a]
    shows = ("Left: the curvature around the NACA 4415 nose along the arc (minus on the lower side): the true shape (the raw "
             "file), the old built section and the new one. Second: the worst error of the turning per cell on the ten "
             "airfoils, old rule against new rule, against the 5 % test (shaded). Third: the Stage 2 nose solve on a NACA "
             "4415 station of a tapered training wing, old section against new: the largest turning against the nose "
             "spacing, at the first approach's 10°. Right: the nose cell the mesher delivers at level C (first rules) on "
             "the same 20 shapes at unit mean chord, old section against new (Study 10's runs).")
    concl = (f"The defect was real. The old rule put the leading edge at the raw point farthest from the trailing edge, "
             f"not at the curve's own tip (the apex lies {min(move):.3f}–{max(move):.3f} % c of arc away on the ten), and "
             f"forced the tangent square there (it was already turned by {min(tilt):.2f}–{max(tilt):.1f}°). So one side "
             f"got a spike of curvature and the other a flat spot, between the raw points. On NACA 4415 a 0.18 % c cell "
             f"turned {t44['old'][2]:.2f}° built against {t_exact[2]:.2f}° true (the NACA formula; {t44['raw'][2]:.2f}° on the "
             f"raw file: +{d44[2]:.0f} %, and +{d44[0]:.0f} % at 0.04 % c). The new rule (one cubic spline, the leading edge at "
             f"its apex, 201 points per side) passes on all ten (worst {minus(f'{new_worst[1]:.1f}')} %, "
             f"{new_worst[2].upper().replace('MH', 'MH ')}) and on "
             f"{db['pass_new_share_pct']:.1f} % of the {db['measured_both']:,} database files both rules build "
             f"({db['pass_old_share_pct']:.1f} % before); a gate refuses the {len(db['refused_by_nose_gate'])} files whose "
             f"nose folds back (none is used). For the mesh: at the same 10° the NACA 4415 / 4412 reference wings now get a "
             f"nose cell of {ca[0]:.3f}–{ca[1]:.3f} % c instead of {cb[0]:.3f} % c (the spike had forced it down); the MH "
             f"wings {mb[0]:.3f}–{mb[1]:.3f} → {ma[0]:.3f}–{ma[1]:.3f} % c; the rings change by {minus(dr[0])} to {minus(dr[-1])} nodes; "
             f"{'the stations and the caps do not change' if same_span else 'the stations change'}. The flat part of the "
             f"nose solve stays: below about 0.2 % c the worst node sits 1.9–2.4 % c down the lower side, where the growth "
             f"limit sets the cells, and the true airfoil does the same "
             f"({min(ln['new']['turning_deg']):.1f}–{max(t for h, t in zip(ln['h_le_pct'], ln['new']['turning_deg']) if h < 0.2):.1f}° "
             f"with the fix), so the window search stays. The 10° target is met up to a nose spacing of "
             f"{ln['new']['largest_h_le_pct_meeting_10deg']:.3f} % c there, against "
             f"{ln['old']['largest_h_le_pct_meeting_10deg']:.3f} % c before.")
    text = ("Mike decided the fix on 7 Nov (decision 64), and it is built in Stage 1. The 6 Nov correction above "
            "was wrong: it compared built and raw only at the raw points, where they agree by construction, and the "
            "defect sat between them. Stage 1 then measured raw and built with one curvature method that no frame or "
            "formula can fool: each curve a smooth spline, its curvature from its own derivatives along its own arc, and "
            "the largest turning a cell of arc length 0.04–0.50 % c gets near the nose, with a 5 % test written before "
            "the run (<code>Stage_1_geometry/decisions/nose_curvature.md</code>). The 2 Nov reading had the right cause.")
    return (chg(text, "Second correction (7 Nov 2026): the defect is real; fixed in Stage 1", "chg")
            + figc("nose_fixed.png", shows, concl))


CHECK_NAME = {"nose_turning": "nose turning", "geometry_kinks": "geometry kinks", "nose_envelope": "nose envelope",
              "chord_growth": "growth along the ring", "band_spacing": "band cell / asked", "te_spacing": "trailing-edge cell / asked",
              "span_growth": "growth between station gaps", "loft_stations_hit": "station on every loft station",
              "tip_gap": "tip gap / asked", "planar_stations": "rings in their planes", "wing_quads": "wing quads (scaled Jacobian)",
              "cap_quads": "cap quads (scaled Jacobian)", "cap_nose_corners": "cap nose corners", "ring_count": "ring count"}


def _r(d: dict, k: str, f="{:.0f}", scale=1.0) -> str:
    v = d.get(k) or {}
    if not v:
        return "–"
    return "–".join(f.format(v[q] * scale) for q in ("min", "median", "max"))


def new_screen_block(sn: dict) -> str:
    """Study 9: the new screen (data/studies/screen_new_summary.json from scripts/screen_study.py)."""
    full, ref, fam = sn["full"], sn["reference"], sn["family"]
    lv = {"VC": full["VC"], "C": ref["C"], "M": ref["M"], "F": full["F"]}
    what = {"VC": "every set", "C": "reference wings", "M": "reference wings", "F": "every set"}
    out = []
    # A. pass counts
    t = ['<div class="tbl"><table class="mid"><tr><th>Level</th><th>What was built</th><th>Builds</th><th>Passed</th><th>Refused</th><th>Crashed</th><th>Nose repairs</th><th>Build time [s] min–median–max</th></tr>']
    for lev, d in lv.items():
        t.append(f"<tr><td class='what'>{lev}</td><td>{what[lev]} ({d['wings']} wings)</td><td class='num'>{d['builds']}</td><td class='num'>{d['passed']}</td>"
                 f"<td class='num'>{d['refused']}</td><td class='num'>{d['crashed']}</td><td class='num'>{d['repairs']}</td><td class='num'>{_r(d, 'seconds', '{:.1f}')}</td></tr>")
    t.append("</table></div>")
    out.append("".join(t))
    # B. per type, every set at Re 3e5, VC and F
    t = ['<div class="tbl"><table class="wide"><tr><th>Level · type (builds at Re 3 × 10⁵)</th><th>Ring nodes min–median–max</th><th>Stations</th><th>Quads [k]</th>'
         '<th>Cells [M] min–median–max</th><th>Build time [s]</th><th>Wing quads J min / median</th><th>Cap quads J min / median</th><th>Passed</th></tr>']
    for lev in ("VC", "F"):
        for ty in TYPES:
            d = sn["full_re3e5"][lev]["by_type"][ty]
            if not d["builds"]:
                continue
            t.append(f"<tr><td class='what'>{lev} · {TYPE_NAME[ty]} ({d['builds']})</td><td class='num'>{_r(d, 'n_ring')}</td><td class='num'>{_r(d, 'n_span')}</td>"
                     f"<td class='num'>{_r(d, 'quads', '{:.0f}', 1e-3)}</td><td class='num'>{_r(d, 'cells_est', '{:.2f}', 1e-6)}</td><td class='num'>{_r(d, 'seconds', '{:.1f}')}</td>"
                     f"<td class='num'>{d['wing_quads_J']['min']:.2f} / {d['wing_quads_J']['median']:.2f}</td><td class='num'>{d['cap_quads_J']['min']:.3f} / {d['cap_quads_J']['median']:.2f}</td>"
                     f"<td class='num'>{d['passed']} / {d['builds']}</td></tr>")
    t.append("</table></div>")
    out.append("".join(t))
    # C. reference wings per level and Re
    res = [(f"{r:.1e}", RE_NAME.get(r, f"{r:.2g}")) for r in sn.get("re_levels", (1e5, 3e5, 1.5e6, 3e6))]
    t = ['<div class="tbl"><table class="mid"><tr><th>Reference wings (20 per Re)</th>' + "".join(f"<th>Re {n}: ring × stations; cells [M] median</th>" for _, n in res) + "</tr>"]
    for lev in LEVELS:
        cells = []
        for k, _ in res:
            d = ref[lev]["by_re"].get(k)
            if not d:
                cells.append("<td class='num'>–</td>")
                continue
            cells.append(f"<td class='num'>{d['n_ring']['min']:.0f}–{d['n_ring']['max']:.0f} × {d['n_span']['min']:.0f}–{d['n_span']['max']:.0f}; {d['cells_est']['median'] / 1e6:.2f}</td>")
        t.append(f"<tr><td class='what'>{lev}</td>{''.join(cells)}</tr>")
    t.append("</table></div>")
    out.append("".join(t))
    return out


def new_screen_checks_table(sn: dict) -> str:
    """The worst build of every check per level: value, limit, margin, where."""
    full, ref = sn["full"], sn["reference"]
    lv = {"VC": full["VC"], "C": ref["C"], "M": ref["M"], "F": full["F"]}
    t = ['<div class="tbl"><table class="wide"><tr><th>Check</th>' + "".join(f"<th>{lev}: worst value (limit) · margin</th>" for lev in lv) + "</tr>"]
    for name in ("nose_turning", "geometry_kinks", "nose_envelope", "chord_growth", "band_spacing", "te_spacing", "span_growth",
                 "tip_gap", "wing_quads", "cap_quads", "cap_nose_corners"):
        cells = []
        for lev, d in lv.items():
            c = d["checks"][name]
            lim = c["limit"]
            lim_s = f"{lim[0]:g}–{lim[1]:g}" if isinstance(lim, list) else f"{lim:.4g}"
            cells.append(f"<td class='num'>{c['value']:.4g} ({lim_s}) · {c['min_margin']:.3g}</td>")
        t.append(f"<tr><td class='what'>{CHECK_NAME[name]}</td>{''.join(cells)}</tr>")
    t.append("</table></div>")
    return "".join(t)


def new_family_table(sn: dict) -> str:
    fam = sn["family"]
    keys = [("nose_root", "nose cell, root"), ("nose_tip", "nose cell, tip"), ("te_root", "trailing-edge cell"), ("band_root", "band cell, root"),
            ("band_tip", "band cell, tip"), ("root_gap", "first station gap"), ("tip_gap", "last station gap (tip)"), ("base_cell", "base cell")]
    pairs = [p for p in ("VC/C", "C/M", "M/F") if p in fam]
    rep = any(fam[p].get("repaired_pairs") for p in pairs)
    t = ['<div class="tbl"><table class="mid"><tr><th>Spacing (coarser / finer)' + (', pairs without a nose repair' if rep else '') + '</th>' + "".join(
        f"<th>{p} ({fam[p]['pairs'] - fam[p].get('repaired_pairs', 0)} pairs): median (min–max)</th>" for p in pairs) + "</tr>"]
    for k, n in keys:
        t.append(f"<tr><td class='what'>{n}</td>" + "".join(
            f"<td class='num'>{fam[p]['spacings_no_repair'][k]['median']:.3f} ({fam[p]['spacings_no_repair'][k]['min']:.3f}–{fam[p]['spacings_no_repair'][k]['max']:.3f})</td>" for p in pairs) + "</tr>")
    if rep:
        t.append("<tr><td class='what'>nose cell, root: the builds repaired at M</td>" + "".join(
            (f"<td class='num'>{fam[p]['spacings_repaired']['nose_root']['median']:.3f} ({fam[p]['repaired_pairs']} pairs)</td>" if fam[p].get("repaired_pairs") else "<td class='num'>—</td>")
            for p in pairs) + "</tr>")
    first = sn.get("nose_levels_check", {}).get("nose_ratio_first", {})
    if first:
        t.append("<tr><td class='what'>nose cell, root, flying wings: the first build (nose solved at VC and F only)</td>" + "".join(
            (f"<td class='num old'>{first[p]['flying_wing']['median']:.3f} ({first[p]['flying_wing']['min']:.3f}–{first[p]['flying_wing']['max']:.3f})</td>" if first.get(p, {}).get('flying_wing') else "<td class='num'>—</td>")
            for p in pairs) + "</tr>")
    for k, n in (("ring_cells", "ring cells (finer / coarser)"), ("station_gaps", "station gaps"), ("wall_layers", "wall layers"), ("cells_est", "cells")):
        t.append(f"<tr><td class='what'>{n}</td>" + "".join(
            f"<td class='num'>{fam[p]['counts'][k]['median']:.3f} ({fam[p]['counts'][k]['min']:.3f}–{fam[p]['counts'][k]['max']:.3f})</td>" for p in pairs) + "</tr>")
    t.append("</table></div>")
    return "".join(t)


def new_cells_table(sn: dict) -> str:
    full, ref = sn["full_re3e5"], sn["reference"]
    t = ['<div class="tbl"><table class="wide"><tr><th>Level</th><th>Cells [M], 20 reference wings × 4 Re: min–median–max</th><th>RAM [GiB], median / max</th>'
         '<th>Fit the desktop today (16 GB: ≤ 1.2 M)</th><th>Fit with +36 GB (≤ 5.0 M)</th><th>Cells [M], every set at Re 3 × 10⁵: median / max</th><th>Wall layers</th></tr>']
    for lev in LEVELS:
        d = ref[lev]
        f3 = full.get(lev)
        all3 = f"{f3['cells_est']['median'] / 1e6:.2f} / {f3['cells_est']['max'] / 1e6:.2f}" if f3 else "—"
        t.append(f"<tr><td class='what'>{lev}</td><td class='num'>{_r(d, 'cells_est', '{:.2f}', 1e-6)}</td><td class='num'>{d['ram_gib']['median']:.1f} / {d['ram_gib']['max']:.1f}</td>"
                 f"<td class='num'>{d['fits_desktop']} of {d['builds']}</td><td class='num'>{d['fits_desktop_36']} of {d['builds']}</td><td class='num'>{all3}</td><td class='num'>{_r(d, 'wall_layers')}</td></tr>")
    t.append("</table></div>")
    return "".join(t)


def _fit(n_ok: int, n: int) -> str:
    return "all" if n_ok == n else ("none" if n_ok == 0 else f"{n_ok} of {n}")


FIRST_ESTIMATE = {"VC": (1.0, 1.5), "C": (2.3, 3.3), "M": (5.0, 7.2), "F": (10.9, 15.9)}   # 6 Nov: median, largest [M]


def nose_first_vs_now(sn: dict) -> tuple[str, dict]:
    """Owner point (2): the nose solved at VC and F only (first build) against every level (decided 7 Nov)."""
    nl = sn.get("nose_levels_check", {}).get("levels", {})
    if not nl:
        return "", {}
    t = ['<div class="tbl"><table class="mid"><tr><th>Level (20 reference wings × 4 Re)</th><th>Builds changed, by type</th>'
         '<th>Ring nodes changed by</th><th>Nose repairs: first (VC and F) → now (every level)</th><th>Passed now</th></tr>']
    for lev in LEVELS:
        d = nl.get(lev)
        if not d:
            continue
        bt = ", ".join(f"{TYPE_NAME[k]} {v}" for k, v in d["changed_by_type"].items() if v) or "none"
        ra = d["ring_added"]
        sg = lambda v: "0" if round(v) == 0 else f"{v:+.0f}".replace("-", "−")
        if not ra:
            ra_s = "—"
        elif ra["min"] == ra["max"]:
            ra_s = sg(ra["min"])
        else:
            ra_s = f"{sg(ra['min'])} to {sg(ra['max'])} (median {sg(ra['median'])})"
        t.append(f"<tr><td class='what'>{lev}</td><td class='num'>{d['changed']} of {d['builds']}: {bt}</td><td class='num'>{ra_s}</td>"
                 f"<td class='num'>{d['repairs_first']} → {d['repairs_now']}</td><td class='num'>{d['passed_now']} of {d['builds']}</td></tr>")
    t.append("</table></div>")
    agg = {"changed": sum(d["changed"] for d in nl.values()), "builds": sum(d["builds"] for d in nl.values()),
           "types": sorted({k for d in nl.values() for k, v in d["changed_by_type"].items() if v}),
           "repairs_first": sum(d["repairs_first"] for d in nl.values()), "repairs_now": sum(d["repairs_now"] for d in nl.values()),
           "ratio_first": sn["nose_levels_check"].get("nose_ratio_first", {}), "ratio_now": sn["nose_levels_check"].get("nose_ratio_now", {})}
    return "".join(t), agg


def _and(xs: list) -> str:
    return "" if not xs else xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def cells_side_by_side(sn: dict) -> str:
    """The two cell counts: the first estimate (6 Nov, rule not recorded) and this one (Study 9)."""
    ref = sn["reference"]
    now = " / ".join(f"{ref[lev]['cells_est']['median'] / 1e6:.1f} ({ref[lev]['cells_est']['max'] / 1e6:.1f})" for lev in LEVELS)
    first = " / ".join(f"{a:.1f} ({b:.1f})" for a, b in FIRST_ESTIMATE.values())
    rf = ref["F"]["cells_est"]
    rows = [
        ("Wall-layer rule", "not recorded (surface × wall layers, about 1.30 × the layers per level)",
         "n = the largest over the stations of ceil(ln(1 + (g − 1) D / s0) / ln g); D = 2 local chords; g = 1.25, 1.187, 1.141, 1.107 at VC, C, M, F; s0 from y⁺ = 1, 0.77, 0.59, 0.46 at each station's local Re (flat plate); cells = (ring nodes − 1)(stations − 1) n + cap quads × n"),
        ("Surfaces", "the plan file (station growth 1.25, 7 gaps per panel) on the first-approach reference wings at real size (13 of the 20 replaced on 7 Nov)",
         "the built rules on the rebuilt reference wings at unit mean chord (Study 9)"),
        ("Cells [M], VC / C / M / F: median (largest)", first, now),
        ("Fine level F", "10.9 M median (15.2 M with the planned rules)", f"{rf['median'] / 1e6:.1f} M median ({rf['min'] / 1e6:.1f}–{rf['max'] / 1e6:.1f} M)"),
        ("Can it be redone?", "no: the rule is not written down", "yes: <code>scripts/screen.py</code>, <code>scripts/screen_study.py</code>"),
    ]
    t = ['<div class="tbl"><table class="wide"><tr><th>Cells of the wing blocks</th><th>First estimate (6 Nov)</th><th>This count (Study 9, 7 Nov): the one the pages use</th></tr>']
    for a, b, c in rows:
        t.append(f"<tr><td class='what'>{a}</td><td class='src'>{b}</td><td class='new'>{c}</td></tr>")
    t.append("</table></div>")
    return "".join(t)


def new_screen_section(sn: dict) -> str:
    """Study 9, the new screen: what was done, the tables, the figures, the conclusion (from screen_new_summary.json)."""
    lv_txt = ", ".join(RE_NAME.get(r, f"{r:.2g}") for r in sn.get("re_levels", (1e5, 3e5, 1.5e6, 3e6)))
    hc = sn.get("hash_check") or {}
    hc_txt = (f"The reference wings were screened again on 8 Nov at the new Re levels (10⁶ and 4 × 10⁶ in place of 1.5 × 10⁶ and "
              f"3 × 10⁶; decision 78); the mesh code had changed only in a file the surface mesher does not use, and the "
              f"{hc['rebuilt_compared']} meshes rebuilt at 10⁵ and 3 × 10⁵ have the very same nodes as on 7 Nov "
              f"({hc['rebuilt_same_nodes']} of {hc['rebuilt_compared']}), so the 7 Nov set screens stand. ") if hc else ""
    full, ref, fam = sn["full"], sn["reference"], sn["family"]
    vc, f, c, m = full["VC"], full["F"], ref["C"], ref["M"]
    lv = {"VC": vc, "C": c, "M": m, "F": f}
    n = sum(d["builds"] for d in lv.values()); ok = sum(d["passed"] for d in lv.values())
    crashed = sum(d["crashed"] for d in lv.values()); repairs = sum(d["repairs"] for d in lv.values())
    fails = {}
    for d in lv.values():
        for k, v in d["failed_checks"].items():
            fails[k] = fails.get(k, 0) + v
    fail_s = "; ".join(f"{CHECK_NAME.get(k, k)}: {v}" for k, v in sorted(fails.items(), key=lambda x: -x[1])) or "none"
    sb = {lev: d.get("nose_set_by_stations") or d["nose_solved_at_stations"] for lev, d in lv.items()}
    st_all = sum(sum(v.values()) for v in sb.values())
    src = {k: sum(v.get(k, 0) for v in sb.values()) for k in ("F", "M", "C", "VC", "band")}
    src_s = ", ".join(f"{name} {src[k]:,} ({100 * src[k] / st_all:.1f} %)" for k, name in
                      (("F", "F's solve"), ("M", "M's"), ("C", "C's"), ("VC", "VC's"), ("band", "the band cell")) if src[k])
    rf = ref["F"]["cells_est"]
    fmed = rf["median"] / 1e6
    asked = "inside" if 9.0 <= fmed <= 11.0 else ("above" if fmed > 11.0 else "below")
    vs6 = sn["F_reference_vs_6nov"]
    fam_n = {p: fam[p]["counts"] for p in fam}
    sp = {p: fam[p]["spacings_no_repair"] for p in fam}
    keys6 = ("nose_root", "nose_tip", "te_root", "band_root", "band_tip", "tip_gap")
    sp_lo = min(sp[p][k]["min"] for p in sp for k in keys6); sp_hi = max(sp[p][k]["max"] for p in sp for k in keys6)
    nose_lo = min(sp[p][k]["min"] for p in sp for k in ("nose_root", "nose_tip"))
    nose_hi = max(sp[p][k]["max"] for p in sp for k in ("nose_root", "nose_tip"))
    rep_pairs = sum(fam[p].get("repaired_pairs", 0) for p in fam)
    cells_r = [fam_n[p]["cells_est"]["median"] for p in ("VC/C", "C/M", "M/F")]
    capmin = {lev: lv[lev]["cap_quads_J"]["min"] for lev in lv}
    blocks = new_screen_block(sn)
    desk = {lev: (ref[lev]["fits_desktop"], ref[lev]["fits_desktop_36"], ref[lev]["builds"]) for lev in LEVELS}
    nose_tab, na = nose_first_vs_now(sn)
    ref_rep = sum(ref[lev]["repairs"] for lev in LEVELS)
    rep_where = "; ".join(f"{d['repairs']} at {lev} ({', '.join(TYPE_NAME[t] for t, k in d['repaired_by_type'].items() if k)}; "
                          f"{', '.join(sorted({x.split()[1] for x in d.get('repaired', [])}))} wings)" for lev, d in lv.items() if d["repairs"])
    rep_s = ("no nose repair at any level" if repairs == 0 else
             (f"no nose repair on the {4 * c['builds']} reference builds; " if ref_rep == 0 else "")
             + f"one repair round (the whole wing's nose spacing × 0.9) on {repairs} builds: {rep_where}. The solve measures each "
               f"station's own ring, the check the shared node list, so a few builds still need the repair")
    fw_first = {pp: na.get("ratio_first", {}).get(pp, {}).get("flying_wing", {}).get("median") for pp in ("C/M", "M/F")} if na else {}
    nose_par = ""
    if na:
        tn = {"bwb": "BWB", "flying_wing": "flying-wing", "cranked": "cranked", "tapered": "tapered"}
        others = [t for t in TYPES if t not in na["types"]]
        nose_par = (f"<p><strong>The nose at every level, the strictest wins</strong> (the owner's answer to point (2) of the builder choices, 7 Nov). "
                    f"First the nose was solved at VC and at F only. That left M short: all 20 flying-wing reference builds needed one repair "
                    f"at M (nose × 0.9), and the nose cell stepped by {fw_first.get('C/M') or 1.44:.2f} from C to M and {fw_first.get('M/F') or 1.17:.2f} "
                    f"from M to F, not 1.3. Now each level solves its own angle on its own ring, with the turning check's own measure; the "
                    f"smallest spacing wins and every level takes it ÷ 1.3^k. A coarser level is only solved where the finer answer misses its "
                    f"angle. On the 20 reference wings × 4 Re × 4 levels (7 Nov, at the Re levels of that day): {na['changed']} of {na['builds']} builds changed, "
                    + (f"all of them {_and([tn[t] for t in na['types']])} builds; " if na["types"] else "")
                    + (f"the {_and([tn[t] for t in others])} builds are the same node for node. " if others else "")
                    + f"Nose repairs: {na['repairs_first']} before, {na['repairs_now']} now.</p>")
    return f"""
  <h3 id="study9">Study 9 · The new screen: the built rules on every wing (7 Nov 2026; the reference wings again on 8 Nov at the new Re levels)</h3>
  <p><strong>What was done.</strong> The rules built on 7 Nov (<code>configs/surface.yaml</code>, with the nose solved at every level) on the rebuilt sets (unit mean chord, the nose fix; 722 wings, new hashes), with the numpy twin of the loft. Every set at VC and at F: training_focus, training_full, corner1 and corner2 at Re 3 × 10⁵ on the mean chord, and the 20 reference wings at all four Re levels ({lv_txt}): {vc['builds']} builds per level. The 20 reference wings also at C and M, at the four Re levels: {c['builds']} builds each. {hc_txt} The 13 checks refuse at each level's own limits (VC 17.1°, F 7.89° for the turning; the growth limits by the family rule), written before the run; failures stay in every count. Each build records every check's value, limit and margin, the ring nodes, stations, quads, build time, which level's solve set each station's nose, and the reasons for each value (<code>data/studies/screen_VC.json</code>, <code>screen_F.json</code>, <code>screen_reference_new.json</code>; the numbers below: <code>screen_new_summary.json</code>; the first build against now: <code>nose_levels_check.json</code>; code: <code>scripts/screen.py</code>, <code>scripts/screen_study.py</code>). Another job ran XFOIL on the other core during the screen, so the build times are on the high side.</p>
  {nose_par}
  {nose_tab}
  <p><strong>Result.</strong></p>
  <ul>
    <li><strong>Passed:</strong> {n} builds, {ok} passed every check, {n - ok - crashed} refused, {crashed} crashed (refusals by check: {fail_s}).</li>
    <li><strong>The nose:</strong> what set it, over {st_all:,} stations: {src_s}. The delivered turning sits at or below each level's angle (within the solve's 0.02°): {vc['nose_turning']['min']:.1f}–{vc['nose_turning']['max']:.1f}° at VC (angle 16.9°), {c['nose_turning']['min']:.1f}–{c['nose_turning']['max']:.1f}° at C (13°), {m['nose_turning']['min']:.2f}–{m['nose_turning']['max']:.2f}° at M (10°), {f['nose_turning']['min']:.2f}–{f['nose_turning']['max']:.2f}° at F (7.69°); {rep_s}.</li>
    <li><strong>Growth:</strong> along the ring at most {vc['chord_growth']['max']:.3f} at VC (limit 1.25, within 1 %) and {f['chord_growth']['max']:.3f} at F (limit 1.107); between station gaps {vc['span_growth']['max']:.3f} at VC (limit 1.3) and {f['span_growth']['max']:.3f} at F (limit 1.127).</li>
    <li><strong>Quad quality:</strong> the lowest cap quads {capmin['VC']:.3f} at VC, {capmin['C']:.3f} at C, {capmin['M']:.3f} at M, {capmin['F']:.3f} at F (limit 0.05); the lowest wing quads {min(d['wing_quads_J']['min'] for d in lv.values()):.2f}.</li>
    <li><strong>Time:</strong> median {vc['seconds']['median']:.1f} s per build at VC and {f['seconds']['median']:.1f} s at F (max {f['seconds']['max']:.1f} s). Solving the nose at every level costs about 15–30 % more time per build than at VC and F only (the same builds, back to back: BWB reference wing 0 at Re 3 × 10⁵, 3.5–4.4 → 4.6 s at VC and 7.0–7.4 → 9.2–9.5 s at F).</li>
  </ul>
  {blocks[0]}
  <p><strong>Per type</strong>, every set at Re 3 × 10⁵ (the reference wings at that Re included), at VC and F:</p>
  {blocks[1]}
  <p><strong>The 20 reference wings</strong> at each level and Re level:</p>
  {blocks[2]}
  {figc("screen_new_counts.png", "The 20 reference wings × 4 Re levels at VC, C, M and F, per wing type: ring nodes, stations, and the cells of the wing blocks (the estimate below, log scale) against the 9–11 M asked for F (green), the desktop today (red) and with +36 GB (amber). Boxes: the middle half; whiskers: the full range.",
        f"Each level has about 1.3 × the ring nodes and stations of the one below, and about {np.mean(cells_r):.1f} × the cells (wall layers × 1.3 too). The BWB has the most ring nodes (its root has the highest local Re, so the smallest band cell) and the conventional wings the fewest. The ring stops growing from Re 10⁶ up (the same ring at 10⁶ and 4 × 10⁶): the bubble-length floor (0.10 c from local Re 4 × 10⁵) sets the band cell there.")}
  {figc("screen_new_checks.png", "Left: for every check, how much of the room to its limit the worst build used (1 = at the limit). For the turning it is the turning over its limit; for a growth check the room is the limit − 1; for the band, trailing-edge and tip-gap cells (delivered against asked) it is their tolerance (1 % over; the tip gap also 20 % under), so a cell delivered at exactly the asked size uses none; for the quad quality it is 0.05 over the smallest value. VC and F: every set; C and M: the 20 reference wings × 4 Re. Right: which level's solve set the nose of the stations (the band cell where the nose is no finer than the band), and the largest turning per level.",
        f"No check was crossed. Two run close by design: the turning is solved to the level's angle (the limit is the angle + 0.2°), and the band and trailing-edge cells are delivered at the asked size. The one that comes close by itself is the cap quality: {capmin['VC']:.3f} at VC, {capmin['M']:.3f} at M and {capmin['F']:.3f} at F against the refusal limit 0.05. F's solve sets most noses, M's some; VC, C and M therefore get a finer nose than their own angle asks.")}
  {new_screen_checks_table(sn)}
  <p><strong>The family ratios</strong> between neighbouring levels on the 20 reference wings × 4 Re (as Study 2, but for the built rules and all four levels):</p>
  {figc("screen_new_family.png", "Left: every spacing between neighbouring levels, coarser / finer: median (bar) and range over the 80 pairs of each step (dashed: r = 1.3); red ×: the nose cell of the first build (nose solved at VC and F only) on the flying wings. Right: the counts, finer / coarser: ring cells, station gaps, wall layers and cells (dashed: 1.3 and 1.3³ = 2.2).",
        (f"The levels are true scaled copies: the nose, trailing-edge, band and tip-gap cells refine by {sp_lo:.3f}–{sp_hi:.3f} per step (1.3 within {100 * max(abs(sp_lo - 1.3), abs(sp_hi - 1.3)) / 1.3:.1f} %); the nose cells by {nose_lo:.3f}–{nose_hi:.3f}. " if rep_pairs == 0 else
         f"On the pairs without a nose repair the nose, trailing-edge, band and tip-gap cells refine by {sp_lo:.3f}–{sp_hi:.3f} per step; {rep_pairs} pairs still had a repair. ")
        + (f"With the nose at VC and F only, the flying wings' nose cell stepped by {fw_first.get('C/M'):.2f} (C/M) and {fw_first.get('M/F'):.2f} (M/F). " if fw_first.get("C/M") else "")
        + f"The other exceptions are whole numbers, as before: the base cells (8, 10, 14, 18: 1.25, 1.4, 1.29) and the first station gap where the gaps per panel set it (8, 10, 12, 16: 1.25, 1.2, 1.33). The cells grow by {cells_r[0]:.2f}, {cells_r[1]:.2f} and {cells_r[2]:.2f} per step (median), close to 1.3³ = 2.2.")}
  {new_family_table(sn)}
  <p><strong>The cells, against the 9–11 M asked and the desktop.</strong> Two counts exist. The pages use this one, because it can be redone; the first estimate of 6 Nov is shown next to it, but its wall-layer rule was not recorded. Both count the wing blocks only: the C-H wake lines are extra (a rough +30–60 %). Stage 3 sets the real wall-layer rule, and with it the real count.</p>
  {cells_side_by_side(sn)}
  {figc("screen_new_cells.png", "Left: cells per mesh per level (wing blocks, this count), median (bar) and largest (tick): the 20 reference wings × 4 Re (blue) and every set at Re 3 × 10⁵ (amber, VC and F only), with the RAM ADflow needs on the right axis (1.51 GiB + 9.46 GiB per million cells). Right: the fine level F on the 20 reference wings × 4 Re: the first estimate (6 Nov, rule not recorded), this count, and this count with a rough +30–60 % for the C-H wake lines.",
        f"F has {fmed:.1f} M cells median ({rf['min'] / 1e6:.1f}–{rf['max'] / 1e6:.1f} M) on the 20 reference wings × 4 Re: {asked} the 9–11 M asked, and {vs6:.2f} × the first estimate of 10.9 M. The surfaces are not why (the built rules have about 17 % more stations than the plan file of that estimate): the two counts differ in their wall-layer rule and in their wings. With the C-H wake lines F lands at about {fmed * 1.3:.0f}–{fmed * 1.6:.0f} M. The desktop today (16 GB: about 1.2 M cells) takes {_fit(desk['VC'][0], desk['VC'][2])} of the VC meshes and {_fit(desk['C'][0], desk['C'][2])} at C; with +36 GB (about 5.0 M) it takes {_fit(desk['VC'][1], desk['VC'][2])} at VC, {_fit(desk['C'][1], desk['C'][2])} at C and {_fit(desk['M'][1], desk['M'][2])} at M; F needs the HPC.")}
  {new_cells_table(sn)}
  {cbox(f"The built rules mesh every wing: {ok} of {n} builds passed, {crashed} crashed, on all four levels and every set" + (f", so, by the rule of three, the true failure rate per level on this design space is below about {300 / vc['builds']:.1f} % (VC, F) and {300 / c['builds']:.1f} % (C, M) with 95 % confidence, for the surface alone. " if ok == n else ". ") + (f"With the nose solved at every level, every level meets its own angle with no repair" if repairs == 0 else
    f"With the nose solved at every level, the {4 * c['builds']} reference builds meet each level's angle with no repair "
    f"(the first build needed one at M on all 20 flying-wing builds); {f['repairs']} of the {f['builds']} F builds of every set still needed one repair round") + (", and the levels are true scaled copies, as the grid study needs. " if rep_pairs == 0 else f"; {rep_pairs} level pairs still break the family rule for the nose cell. ") + f"The cells (this count): F {fmed:.1f} M median, {asked} the 9–11 M asked; about {fmed * 1.3:.0f}–{fmed * 1.6:.0f} M with the C-H wake lines. Weak points: the cap quads come close to the 0.05 limit ({capmin['VC']:.3f} at VC, {capmin['M']:.3f} at M); the nose is finer than VC, C and M ask, because F or M sets it; the cell count is an estimate whose wall-layer rule Stage 3 will set; it is the numpy loft; no solve has run. What this does not show: whether the march (Stage 3) accepts these surfaces, and whether the coarse levels are good enough for the drag (the ladders after the first solves).")}"""


def family_screen_section(sf: dict) -> str:
    """Study 12 (8 Nov 2026): the family screen, every set at VC, C, M and F with one nose factor per family and the upper
    band 0-100 % c (data/studies/screen_family_summary.json from scripts/screen_study.py --family)."""
    if not sf:
        return ""
    full, nf, ab = sf["full"], sf["nose_family"], sf.get("against_before", {})
    builds = sum(d["builds"] for d in full.values()); ok = sum(d["passed"] for d in full.values())
    refused = sum(d["refused"] for d in full.values()); crashed = sum(d["crashed"] for d in full.values())
    fams = nf["families"]
    n_ref = 20 * len(sf.get("re_levels", [1, 2, 3, 4]))
    n_other = full["VC"]["wings"] - 20
    rep = nf["repaired_families"]
    rep_s = ("none" if rep == 0 else _and(nf["repaired"][:6]) + (" …" if rep > 6 else ""))
    lab_s = ", ".join(f"{k}: {v}" for k, v in nf["labels"].items())
    secs = sf.get("seconds_total") or sum(d["seconds"]["median"] * d["builds"] for d in full.values() if d.get("seconds"))
    fails = {}
    for d in full.values():
        for k, v in d["failed_checks"].items():
            fails[k] = fails.get(k, 0) + v
    fail_s = "; ".join(f"{CHECK_NAME.get(k, k)}: {v}" for k, v in sorted(fails.items(), key=lambda x: -x[1])) or "none"
    # against the screens it replaces
    ab_s = []
    for lev in LEVELS:
        d = ab.get(lev)
        if not d:
            continue
        gain = {int(k): v for k, v in d["ring_nodes_added"].items() if int(k) > 0}
        lose = {int(k): v for k, v in d["ring_nodes_added"].items() if int(k) < 0}
        ab_s.append(f"{lev}: the same ring nodes, stations and cells on {d['same_counts']} of {d['compared']}"
                    + (f"; {sum(gain.values())} gained ring nodes ({', '.join(f'+{k}: {v}' for k, v in sorted(gain.items()))}), "
                       f"the cells by at most +{100 * (d['cells_ratio']['max'] - 1):.2f} %" if gain else "")
                    + (f"; {sum(lose.values())} lost ring nodes ({', '.join(f'−{-k}: {v}' for k, v in sorted(lose.items()))}), "
                       f"the cells by at most −{100 * (1 - d['cells_ratio']['min']):.2f} %" if lose else "")
                    + (f"; nose repairs {d['repairs_before']} before, {d['repairs_now']} now" if d["repairs_before"] or d["repairs_now"] else ""))
    ab_txt = "; ".join(ab_s)
    pos_s = " or ".join(f"+{k}" for k in sorted({int(k) for lev in ab for k in ab[lev]["ring_nodes_added"] if int(k) > 0}))
    plus_s = ", ".join(f"{lev} {sum(v for k, v in ab[lev]['ring_nodes_added'].items() if int(k) > 0)} of {ab[lev]['compared']}"
                       for lev in LEVELS if lev in ab)
    neg = {lev: sum(v for k, v in ab[lev]["ring_nodes_added"].items() if int(k) < 0) for lev in ab}
    band_c = (f"The upper band written 0–100 % c moved nodes but hardly the counts: {pos_s} ring nodes on {plus_s} meshes, "
              f"the cells by at most +{100 * max(ab[lev]['cells_ratio']['max'] - 1 for lev in ab):.1f} %"
              + ("; " + ", ".join(f"{n} {lev} meshes have fewer ring nodes, the builds that had a nose repair before"
                                  for lev, n in neg.items() if n) if any(neg.values()) else "") + "." if ab else "")
    # the cells
    cells_s = ", ".join(f"{lev} {full[lev]['cells_est']['median'] / 1e6:.2f} ({full[lev]['cells_est']['max'] / 1e6:.2f})" for lev in LEVELS)
    turn_s = ", ".join(f"{lev} {full[lev]['nose_turning']['max']:.2f}°" for lev in LEVELS)
    angle = {"VC": 16.9, "C": 13.0, "M": 10.0, "F": 7.69}
    fa = sf.get("family_all", {})
    def _rng(keys):                          # the delivered spacing, coarser / finer, over every family and step
        if not fa:
            return float("nan"), float("nan")
        return (min(fa[p]["spacings"][k]["min"] for p in fa for k in keys),
                max(fa[p]["spacings"][k]["max"] for p in fa for k in keys))
    nt_lo, nt_hi = _rng(("nose_root", "nose_tip", "te_root"))
    bt_lo, bt_hi = _rng(("band_root", "band_tip", "tip_gap"))
    cells_r = [fa[p]["counts"]["cells_est"]["median"] for p in ("VC/C", "C/M", "M/F") if p in fa]
    pairs = fa.get("VC/C", {}).get("pairs", 0)
    desk = {lev: (full[lev]["fits_desktop"], full[lev]["fits_desktop_36"], full[lev]["builds"]) for lev in LEVELS}
    capmin = {lev: full[lev]["cap_quads_J"]["min"] for lev in LEVELS}
    t = ['<div class="tbl"><table class="wide"><tr><th>Level</th><th>Builds (families)</th><th>Passed</th>'
         '<th>Families with a nose repair</th><th>Ring nodes min–median–max</th><th>Stations</th>'
         '<th>Cells [M] min–median–max</th><th>Largest turning (angle)</th><th>Build time [s] median (max)</th></tr>']
    for lev in LEVELS:
        d = full[lev]
        t.append(f"<tr><td class='what'>{lev}</td><td class='num'>{d['builds']}</td><td class='num'>{d['passed']}</td>"
                 f"<td class='num'>{rep}</td><td class='num'>{_r(d, 'n_ring')}</td><td class='num'>{_r(d, 'n_span')}</td>"
                 f"<td class='num'>{_r(d, 'cells_est', '{:.2f}', 1e-6)}</td><td class='num'>{d['nose_turning']['max']:.2f}° ({angle[lev]:g}°)</td>"
                 f"<td class='num'>{d['seconds']['median']:.1f} ({d['seconds']['max']:.1f})</td></tr>")
    t.append("</table></div>")
    t2 = ['<div class="tbl"><table class="mid"><tr><th>Per type, every set at Re 3 × 10⁵: cells [M] median (largest)</th>'
          + "".join(f"<th>{lev}</th>" for lev in LEVELS) + "</tr>"]
    for ty in TYPES:
        cells = []
        for lev in LEVELS:
            d = sf["full_re3e5"][lev]["by_type"][ty]
            cells.append(f"<td class='num'>{d['cells_est']['median'] / 1e6:.2f} ({d['cells_est']['max'] / 1e6:.2f})</td>" if d.get("cells_est") else "<td>–</td>")
        t2.append(f"<tr><td class='what'>{TYPE_NAME[ty]} ({sf['full_re3e5']['VC']['by_type'][ty]['builds']} wings)</td>{''.join(cells)}</tr>")
    t2.append("</table></div>")
    fig1 = figc("family_cells.png",
                "Cells per mesh per level (wing blocks, the estimate of Study 9), median (bar) and largest (tick): the 20 reference wings × 4 Re (blue) and every set at Re 3 × 10⁵ (amber), now at every level, with the RAM ADflow needs (right axis). Right: the fine level F on the reference wings against the first estimate of 6 Nov and with a rough +30–60 % for the C-H wake lines.",
                f"Every level is now counted on every set. The desktop today (about 1.2 M cells) takes {_fit(desk['VC'][0], desk['VC'][2])} of the VC meshes; with +36 GB (about 5.0 M) it takes {_fit(desk['C'][1], desk['C'][2])} at C and {_fit(desk['M'][1], desk['M'][2])} at M; F needs the HPC (median {full['F']['cells_est']['median'] / 1e6:.2f} M, largest {full['F']['cells_est']['max'] / 1e6:.2f} M).")
    fig2 = figc("family_checks.png",
                "Left: for every check, how much of the room to its limit the worst build used (1 = at the limit), every set at every level. Right: which level's solve set the nose of the stations, and the largest turning per level.",
                f"No check was crossed at any level. The cap quads remain the closest by themselves: {capmin['VC']:.3f} at VC, {capmin['C']:.3f} at C, {capmin['M']:.3f} at M, {capmin['F']:.3f} at F, against the refusal limit 0.05.")
    fig3 = figc("family_family.png",
                "Every spacing and count between neighbouring levels, on the 20 reference wings × 4 Re (as Study 9): spacings coarser / finer (left), counts finer / coarser (right).",
                (f"Over every family ({pairs} pairs per step) the delivered nose and trailing-edge cells refine by {nt_lo:.3f}–{nt_hi:.3f} per step "
                 f"(the asked nose spacing by exactly 1.3; the rest is whole node counts), the band and tip-gap cells by {bt_lo:.3f}–{bt_hi:.3f} "
                 f"(whole cells per band and per gap), and the cells grow by "
                 + ", ".join(f"{x:.2f}" for x in cells_r) + " per step (median), close to 1.3³ = 2.2." if fa else "–"))
    return f"""
  <h3 id="study12">Study 12 · The family screen: every set at every level, one nose factor per family (8 Nov 2026)</h3>
  <p><strong>What was done.</strong> Two decisions of the owner (8 Nov), built. (1) <strong>The nose repair belongs to the family</strong>, one wing at one Re: a repair round (every station's nose spacing × 0.9) is needed only where a ring turns past its level's check limit (the angle + 0.2°; before, 0.02° past the angle was enough, and 4 of 782 F builds took a round for 0.003–0.006°). If any level of a family needs a round, the same factor goes on all four levels and all four are rebuilt, so every spacing still refines by exactly 1.3; every mesh carries the label (none, or family repair with its factor and the level that needed it). (2) <strong>The upper band is written 0–100 % c</strong> (was 0–85 % c; the built mesh already had band cells there). Then every set at all four levels for the first time: the {n_other} wings of training_focus, training_full, corner1 and corner2 at Re 3 × 10⁵, and the 20 reference wings at the four Re levels: {fams} families × 4 levels = {builds:,} builds, with the numpy loft, in two processes (about {secs / 3600 / 2:.1f} h each). Code: <code>scripts/screen.py --family</code> (<code>cfdauto.mesh.surface.build_family</code>), <code>scripts/screen_study.py --family</code>; data: <code>data/studies/screen_family_VC.json</code> to <code>screen_family_F.json</code>, <code>screen_family_summary.json</code>.</p>
  <p><strong>Result.</strong></p>
  <ul>
    <li><strong>Passed:</strong> {ok:,} of {builds:,} builds ({refused} refused, {crashed} crashed; refusals by check: {fail_s}).</li>
    <li><strong>The nose repair:</strong> {rep} of {fams} families needed one ({rep_s}). Every family carries one factor at every level ({nf['same_factor_at_every_level']} of {fams}); no level kept a round of its own ({nf['rounds_of_their_own']}). Labels over the {builds:,} meshes: {lab_s}.</li>
    <li><strong>Against the screens it replaces</strong> (the sets of 7 Nov at VC and F; the reference wings of 8 Nov at every level; the same wing, Re and level): {ab_txt}.</li>
    <li><strong>Cells</strong> (wing blocks, estimate), median (largest) over every family, in millions: {cells_s}.</li>
    <li><strong>The nose:</strong> largest turning {turn_s} (angles 16.9°, 13°, 10°, 7.69°; check limits 17.1°, 13.2°, 10.2°, 7.89°): {"every ring inside its check limit, so no round was needed" if all(full[lev]['nose_turning']['max'] <= angle[lev] + 0.2 for lev in LEVELS) else "some rings past their check limit took a family round"}{"; a few rings pass their angle by up to " + f"{max(full[lev]['nose_turning']['max'] - angle[lev] for lev in LEVELS):.2f}° (the solve's tolerance is 0.02°), which a round would have repaired before" if any(full[lev]['nose_turning']['max'] - angle[lev] > 0.02 for lev in LEVELS) else ""}.</li>
  </ul>
  {"".join(t)}
  {"".join(t2)}
  {fig1}
  {fig2}
  {fig3}
  {cbox(f"The rules mesh every wing at every level: {ok:,} of {builds:,} builds passed" + (f", so, by the rule of three, the true failure rate per level on this design space is below about {300 / full['VC']['builds']:.2f} % with 95 % confidence, for the surface alone" if ok == builds else "") + f". The family rule now holds by construction, also for the nose: one nose factor per family at every level; {'no family needed a repair' if rep == 0 else f'{rep} families needed one, and it went on every level'}. {band_c} What this does not show: the volume mesh (Stage 3), the solver, and node-by-node agreement with pyGeo on the full sets (checked on the reference wings).")}"""


def refine_re_section(rre: dict, uc: dict) -> str:
    """Study 11: the refine map at the Re levels (7 Nov; data/studies/refine_map_re.json, scripts/refine_map_re.py)."""
    s, ab = rre["summary"], rre["as_built"]
    keys = tuple((k, RE_NAME.get(float(k), k)) for k in next(iter(s.values())).keys())     # the levels the map ran at
    t = ['<div class="tbl"><table class="mid"><tr><th>Upper side, −5° to 8°: strips whose band fits 0–85 % c (transition itself)</th>'
         + "".join(f"<th>{TYPE_NAME[ty]}</th>" for ty in TYPES) + "</tr>"]
    for k, name in keys:
        t.append(f"<tr><td class='what'>Re {name}</td>" + "".join(
            f"<td class='num'>{100 * s[ty][k]['to_8']['upper']['covered_share']:.0f} % ({100 * s[ty][k]['to_8']['upper']['transition_inside_share']:.0f} %)</td>"
            for ty in TYPES) + "</tr>")
    t.append("</table></div>")
    cov = rre["figures"]["refine_re_coverage.png"]
    return f"""
  <h3 id="study11">Study 11 · The refine map at the Re levels (7 Nov 2026; redone 8 Nov at the new levels)</h3>
  <p><strong>What was done.</strong> The refine map of Study 7 in its new Re mode (similarity): the 20 reference wings (the new picks) at the four Re levels on the mean chord, root angles −5° to 12°, unit mean chord, the section tables rebuilt on the fixed nose and read at Mach 0.1, 13 strips per half wing. Per strip and side: where transition sits from −5° to 8°, the band it needs (transition ± 10 % c, bubbles, separation start), whether the bands hold it, and the strips with no XFOIL answer. Then an as-built check on {len(ab['builds'])} built surfaces (wing 0 of each type × 4 Re, level VC). Details and the other two figures: the refine page (<code>docs/REFINE_MAP.html</code>, first section) and <code>decisions/refine_map_re.md</code>; data <code>data/studies/refine_map_re.json</code>; <code>scripts/refine_map_re.py</code>.</p>
  {"".join(t)}
  {figc("refine_re_coverage.png", cov["what"], cov["conclusion"])}
  {cbox(f"The lower band (0–100 % c) holds every strip at every Re level. The upper band as written (0–85 % c) does not hold the upper transition at low Re and low angle: at 10⁵ and 3 × 10⁵ only 0–49 % of the strips fit, short by up to 15 % c (to the trailing edge), and the cause is always the transition itself, never a bubble or a separation. As built this is no gap: on the {len(ab['builds'])} surfaces the largest upper cell over 85–99.5 % c is {ab['upper_ratio_min']:.3f}–{ab['upper_ratio_max']:.3f} × the band cell, because both sides share one node list (decision 60) and the lower band is 0–100 % c. So no mesh change was needed. The owner wrote the upper band as 0–100 % c on 8 Nov, to match: {_uc_text(uc)} (Study 12). No XFOIL answer: only on the tailless wings at negative root angles, up to 46 % (BWB) and 42 % (flying wing) of the strips at −5°, where the outboard sections are below the lowest angle XFOIL converges at; the band there rests on the other angles. Limits: 2-D strips in calm air with one induced angle; no crossflow, no 3-D relief, no tip effects. The per-wing band (decision 65) stays a candidate until a 3-D transition check.")}"""


def similarity_section(sim: dict) -> str:
    """Study 10: the similarity check (data/studies/similarity_check.json from scripts/similarity_check.py)."""
    key = lambda r: (r["wing_type"], r["index"], r["re_mean"])
    old = {key(r): r for r in sim["old"]["rows"]}
    new = {key(r): r for r in sim["similarity_only"]["rows"]}
    both = {key(r): r for r in sim["similarity_and_nose"]["rows"]}
    ks = [k for k in old if k in new]
    same_ring = sum(old[k]["n_ring"] == new[k]["n_ring"] for k in ks)
    sw = sorted({k[:2] for k in ks if old[k]["n_panels"] > new[k]["n_panels"]})
    drops = [old[k]["n_span"] - new[k]["n_span"] for k in ks if k[:2] in sw]
    other_same = all(old[k]["n_span"] == new[k]["n_span"] for k in ks if k[:2] not in sw)
    fall = [k for k in ks if new[k]["cap_quads_J"] < old[k]["cap_quads_J"] - 0.01]
    big = max(fall, key=lambda k: old[k]["cap_quads_J"] - new[k]["cap_quads_J"])
    low = min(ks, key=lambda k: new[k]["cap_quads_J"])
    picks = sorted({k[:2] for k in ks if new[k]["same_pick"]})
    name = lambda w: f"{TYPE_NAME[w[0]]} {w[1]}"
    dr = sorted({both[k]["n_ring"] - new[k]["n_ring"] for k in ks})
    passed = (sum(new[k]["passed"] for k in ks), sum(both[k]["passed"] for k in ks))
    shows = ("The 20 reference shapes of before similarity, each at the four Re levels (80 meshes, first rules, level C): at real "
             "size (the first screen) against unit mean chord (the code of the similarity merge, with the old nose rule, so only "
             "the size and the trailing edge change). Left: ring nodes. Second: stations; arrows: the wings that lost their "
             "switch section. Third: the smallest scaled Jacobian of the cap quads (dashed red: the refusal limit). Right: the "
             "four Re levels on the mean chord (dashed) against the Re range of the real UAVs that set the Stage 1 ranges, "
             "from cruise to top speed (Stage 1, real_uavs.json).")
    concl = (f"Size changes nothing in the ring: the same ring nodes on {same_ring} of {len(ks)} meshes, as similarity says it "
             f"should (at the same Re the flow, and so every rule, is the same in chords). The stations drop by "
             f"{min(drops)}–{max(drops)} on the {len(sw)} wings that had a switch section ({', '.join(name(w) for w in sw)}): "
             f"that extra loft station came from the old trailing-edge floor (0.5 mm or 1.0 mm, against 0.2 % c), and "
             f"{'nothing else changes' if other_same else 'some others change too'}. The cap quality falls on {len(fall)} of "
             f"{len(ks)} meshes, most on {name(big[:2])} at Re {big[2]:.0e} ({old[big]['cap_quads_J']:.3f} → "
             f"{new[big]['cap_quads_J']:.3f}): the old floor had made the trailing edge of small tips thicker, which gave "
             f"the cap room. The lowest stays {new[low]['cap_quads_J']:.3f} ({name(low[:2])}, Re {low[2]:.0e}), above the "
             f"0.05 limit. The four Re levels cover the real UAVs: 10⁵ is 18 % below the slowest (1.22 × 10⁵), kept as a "
             f"margin (Mike, 7 Nov), and 4 × 10⁶ (since 8 Nov; 3 × 10⁶ before) is above the fastest top speed (3.1 × 10⁶) and "
             f"takes in every cruise point of the Greek tactical UAVs.")
    return f"""
  <h3 id="study10">Study 10 · The similarity check: the same shapes at real size and at unit mean chord (7 Nov 2026, new)</h3>
  <p><strong>What was done.</strong> Similarity (decision 70) was built in Stage 1 on 7 Nov: every wing at unit mean chord (area / full span), the Re on the mean chord an input, the root chord out of the vector (17 numbers), the trailing edge 0.2 % c on every wing, no 7 m full-span cap; the sets were rebuilt (722 of 722 built), and 13 of the 20 reference wings are new picks (the same at the same index: {', '.join(name(w) for w in picks)}). To see what similarity alone does to a mesh, the 20 reference shapes of before (Stage 1 sets at commit 7bcb7067) were built again at unit mean chord and meshed with the first rules at level C at the four Re levels: once with the code of the similarity merge (commit 9472830c: the new size and trailing edge, the old nose rule) and once with today's code (also the nose fix), and compared with their first meshes at real size (the first screen, Study 1). {passed[0]} and {passed[1]} of 80 builds passed. Code: <code>scripts/similarity_check.py</code>; data: <code>data/studies/similarity_check.json</code>.</p>
  {figc("similarity_check.png", shows, concl)}
  {cbox(f"Similarity is safe for the surface mesh: at the same Re it gives the same ring, node for node; it removes the switch sections (fewer stations) and makes some tip caps worse, but none near the limit on these 80. The nose fix on top changes the rings by {str(dr[0]).replace("-", "−")} to {str(dr[-1]).replace("-", "−")} nodes and makes the NACA 4415 / 4412 nose cells about 1.4–1.5 × larger (Study 4). Limits: first rules at level C only (the new rules on the new sets are Study 9); the 80 meshes of the old reference shapes, not the new picks; numpy loft. Studies 1–8 used these old shapes; the new reference wings differ on 13 of 20.")}"""


def fig_pipeline() -> str:
    boxes = [
        ("IN · the Stage 1 loft", ["the exact wing surface:", "upper(x/c, v) and lower(x/c, v),", "with its loft stations b0..b3"], "in"),
        ("1 · Stations", ["slices along the semi-span:", "one on every loft station,", "one every 0.2 chord, ≥ 12 per panel,", "squeezed to s0 at the tip"], "acc"),
        ("2 · Size fields", ["per station and side: how big a cell", "may be at every place (nose, band,", "curvature, trailing edge, 2 % c max),", "growing ≤ 1.2 per cell"], "acc"),
        ("3 · Nose solve", ["the nose cell found by trial on the", "built ring: no node turns the", "surface by more than 10°"], "acc"),
        ("4 · One node list for all stations", ["every station carries the same ring,", "so the wish lists of step 2 are", "merged: at each place, the smallest", "cell any station asks for is used"], "acc"),
        ("5 · Rings and cap", ["every node asked from the loft", "(never interpolated); one H patch", "closes the flat tip"], "acc"),
        ("6 · Thirteen checks", ["turning, growth, spacings, breaks,", "tip gap, quad quality; any failure:", "only refusal.json is written"], "warn"),
        ("OUT · the files", ["surface.npz, surface.xyz (Plot3D),", "stations.csv, quality.json,", "manifest.json (four hashes)"], "out"),
    ]
    w, h, gx, gy, x0, y0 = 232, 118, 20, 34, 10, 10
    cols = 4
    W = x0 * 2 + cols * w + (cols - 1) * gx
    H = y0 * 2 + 2 * h + gy
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="the surface mesh pipeline, in six steps from the loft to the files" style="width:100%;height:auto;max-width:100%">',
             '<style>.pb{fill:var(--surface);stroke:var(--line);stroke-width:1.4}.pb.acc{stroke:var(--accent)}.pb.warn{stroke:var(--amber)}.pb.in,.pb.out{stroke:var(--muted);stroke-dasharray:5 3}'
             '.ph{font:700 14px var(--body);fill:var(--ink)}.ph.acc{fill:var(--accent)}.ph.warn{fill:var(--amber)}.ph.in,.ph.out{fill:var(--muted)}'
             '.pt{font:12.5px var(--body);fill:var(--ink)}.pa{stroke:var(--muted);stroke-width:1.4;fill:none;marker-end:url(#ah2)}</style>',
             '<defs><marker id="ah2" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="var(--muted)"/></marker></defs>']
    for i, (head, lines, cls) in enumerate(boxes):
        r, c = divmod(i, cols)
        x, y = x0 + c * (w + gx), y0 + r * (h + gy)
        parts.append(f'<rect class="pb {cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>')
        parts.append(f'<text class="ph {cls}" x="{x + 12}" y="{y + 24}">{html.escape(head)}</text>')
        for k, line in enumerate(lines):
            parts.append(f'<text class="pt" x="{x + 12}" y="{y + 46 + 17 * k}">{html.escape(line)}</text>')
        if c < cols - 1:
            parts.append(f'<path class="pa" d="M{x + w},{y + h / 2} L{x + w + gx - 2},{y + h / 2}"/>')
        elif r == 0:   # wrap from the end of row 1 to the start of row 2
            xe, ye = x + w / 2, y + h
            xs2, ys2 = x0 + w / 2, y0 + h + gy
            parts.append(f'<path class="pa" d="M{xe},{ye} L{xe},{ye + gy / 2} L{xs2},{ye + gy / 2} L{xs2},{ys2 - 2}"/>')
    parts.append("</svg>")
    return '<div class="card">' + "".join(parts) + "</div>"


# --------------------------------------------------------------------------------------
# the page
# --------------------------------------------------------------------------------------

CSS = """
:root {
  --bg: #F3F6F9; --surface: #FFFFFF; --ink: #142230; --muted: #566573; --line: #D6DEE6; --grp: #E8EEF4;
  --accent: #0C5EA8; --bwb: #2E8B57; --warn: #B02A20; --amber: #9A6200; --violet: #6A4BB0;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif;
  --body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --mono: "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #98A7B5; --line: #26333F; --grp: #1C2732;
  --accent: #62AEF2; --bwb: #5FC48F; --warn: #F08A80; --amber: #E7B24F; --violet: #B49BF0; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #0E141A; --surface: #151E27; --ink: #E4ECF3; --muted: #98A7B5; --line: #26333F; --grp: #1C2732;
  --accent: #62AEF2; --bwb: #5FC48F; --warn: #F08A80; --amber: #E7B24F; --violet: #B49BF0; color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 16px; line-height: 1.55; margin: 0;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); padding-block: 28px 56px; }
.wrap { max-width: 1100px; margin: 0 auto; display: flex; flex-direction: column; gap: 36px; }
header { border-bottom: 2px solid var(--ink); padding-bottom: 16px; display: flex; flex-direction: column; gap: 10px; }
.eyebrow { font-family: var(--mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }
h1 { font-family: var(--display); font-size: clamp(32px, 5vw, 46px); line-height: 1.05; margin: 0; text-wrap: balance; }
h2 { font-family: var(--display); font-size: 28px; margin: 0; text-wrap: balance; }
h3 { font-family: var(--display); font-size: 21px; margin: 0; font-weight: 600; }
p { margin: 0; max-width: 78ch; }
ul, ol { margin: 0; padding-left: 22px; max-width: 80ch; } li { margin-bottom: 4px; }
section { display: flex; flex-direction: column; gap: 14px; scroll-margin-top: 12px; }
.lede { color: var(--muted); font-size: 17px; }
nav { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 14px; }
nav a, p a, td a, li a { color: var(--accent); text-decoration: none; border-bottom: 1px solid transparent; }
nav a:hover, nav a:focus-visible, p a:hover { border-bottom-color: currentColor; outline: none; }
.card { background: #FFFFFF; border: 1px solid var(--line); border-radius: 6px; padding: 10px; overflow-x: auto; margin: 0; min-width: 0; }
.card img { display: block; width: 100%; height: auto; max-width: 100%; }
.cap { color: #566573; font-size: 14px; margin-top: 6px; }
.three { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
.box { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 14px 16px; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.box h3 { margin: 0; font-family: var(--mono); font-weight: 500; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.box .big { font-family: var(--display); font-size: 24px; line-height: 1.1; }
.box.verdict { border-color: var(--amber); } .box.verdict .big { color: var(--amber); }
.box.good { border-color: var(--bwb); } .box.good .big { color: var(--bwb); }
.box.bad { border-color: var(--warn); } .box.bad .big { color: var(--warn); }
.box p { font-size: 14px; color: var(--muted); }
code, pre { font-family: var(--mono); font-size: 13px; }
p code, li code, td code, .cbox code, .cap code, .box code { overflow-wrap: anywhere; white-space: normal; }
pre { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; overflow-x: auto; margin: 0; }
.tbl { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
table.wide { min-width: 900px; } table.mid { min-width: 640px; }
th, td { text-align: left; vertical-align: top; padding: 9px 12px; border-bottom: 1px solid var(--line); }
tr:last-child td { border-bottom: 0; }
th { font-family: var(--mono); font-weight: 500; font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
td.what { font-weight: 700; width: 18%; } td.what .id { display: block; font-family: var(--mono); font-weight: 500; font-size: 11px; color: var(--muted); }
td.num { font-family: var(--mono); font-size: 13px; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.num.old { color: var(--muted); }
td.src { font-size: 12.5px; color: var(--muted); width: 30%; min-width: 220px; line-height: 1.45; }
.flag { font-family: var(--mono); font-size: 11px; text-transform: uppercase; padding: 1px 6px; border-radius: 3px; border: 1px solid currentColor; white-space: nowrap; font-weight: 500; }
li .flag { white-space: normal; display: inline-block; max-width: 100%; }
.flag.ok { color: var(--bwb); } .flag.chg { color: var(--amber); } .flag.part { color: var(--violet); } .flag.no { color: var(--warn); } .flag.s3 { color: var(--muted); }
.steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
.step { background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.step .k { font-family: var(--mono); font-size: 11px; color: var(--accent); letter-spacing: .06em; text-transform: uppercase; }
.step h3 { font-size: 18px; }
.step p { font-size: 14px; }
.cbox { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid var(--bwb); border-radius: 6px; padding: 10px 14px; font-size: 15px; line-height: 1.5; max-width: 100%; }
.cbox .ctag { display: block; font-family: var(--mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--bwb); margin-bottom: 2px; }
.cbox.warn { border-left-color: var(--warn); } .cbox.warn .ctag { color: var(--warn); }
.cbox.old { border-left-color: var(--muted); color: var(--muted); } .cbox.old .ctag { color: var(--muted); }
.cbox.chg { border-left-color: var(--amber); background: color-mix(in srgb, var(--amber) 6%, var(--surface)); } .cbox.chg .ctag { color: var(--amber); }
td.new { font-size: 13.5px; background: color-mix(in srgb, var(--amber) 7%, transparent); min-width: 240px; }
.two { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
.two .box ul { padding-left: 18px; font-size: 14px; }
footer { color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); padding-top: 14px; }
@media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto; } }
"""


def build_page(d: dict) -> tuple[str, str]:
    cfg, screen, fam, nose, bc = d["cfg"], d["screen"], d["fam"], d["nose"], d["bc"]
    sn, sim, nc = d["sn"], d["sim"], d["nc"]
    rre, uc = d["rre"], d["uc"]
    scr_tab, tot = screen_table(screen)
    bwb = fam["wings"]["bwb"]["counts"]
    vcf, ff, rv = sn["full"]["VC"], sn["full"]["F"], sn["reference"]
    n_new = vcf["builds"] + ff["builds"] + rv["C"]["builds"] + rv["M"]["builds"]
    ok_new = vcf["passed"] + ff["passed"] + rv["C"]["passed"] + rv["M"]["passed"]
    crash_new = vcf["crashed"] + ff["crashed"] + rv["C"]["crashed"] + rv["M"]["crashed"]
    rep_new = vcf["repairs"] + ff["repairs"] + rv["C"]["repairs"] + rv["M"]["repairs"]
    fcell = rv["F"]["cells_est"]
    sf_path = STUDIES / "screen_family_summary.json"
    sf = json.loads(sf_path.read_text()) if sf_path.exists() else None
    if sf:                                   # Study 12 (8 Nov): every set at every level; the pages use it from here on
        fs = sf["full"]
        n_f = sum(x["builds"] for x in fs.values()); ok_f = sum(x["passed"] for x in fs.values())
        crash_f = sum(x["crashed"] for x in fs.values())
        rep_f, fams_f = sf["nose_family"]["repaired_families"], sf["nose_family"]["families"]
        vcx, fx = fs["VC"], fs["F"]
        fcell = sf["reference"]["F"]["cells_est"]
        cap_s = ", ".join(f"{fs[lev]['cap_quads_J']['min']:.3f} at {lev}" for lev in LEVELS)
        ab = sf.get("against_before", {})
        plus_s = ", ".join(f"{lev} {sum(v for k, v in ab[lev]['ring_nodes_added'].items() if int(k) > 0)} of {ab[lev]['compared']}"
                           for lev in LEVELS if lev in ab)
        lede_f = (f" The family screen (8 Nov) meshed every set at all four levels for the first time, one nose factor per "
                  f"wing and Re: {ok_f:,} of {n_f:,} passed, {rep_f} families needed a nose repair (<a href=\"#study12\">Study 12</a>).")
        verdict_box = (f'<div class="box verdict"><h3>Is the surface mesh finished?</h3><div class="big">Yes, on the numpy loft: '
                       f'ready to close.</div><p>Every set at every level passed ({ok_f:,} of {n_f:,}, Study 12); both builder choices '
                       f'and the upper band were decided on 8 Nov and built. The pyGeo loft on Mike\'s machine gives the same '
                       f'meshes as the numpy loft on the 20 reference wings (VC and F: the same ring nodes and stations on 80 of 80 '
                       f'each). Left: Mike\'s word to close, then Stage 3, the matched C-H volume mesh.</p></div>')
        screen_box = (f'<div class="box good"><h3>The family screen (8 Nov)</h3><div class="big">{ok_f:,} of {n_f:,} builds passed</div>'
                      f'<p>Every set at VC, C, M and F: {fams_f} families ({vcx["wings"] - 20} wings at Re 3 × 10⁵; the 20 reference '
                      f'wings at all four Re levels) × 4 levels. {crash_f} crashes. One nose factor per family at every level: '
                      f'{"no family needed a repair" if rep_f == 0 else f"{rep_f} families needed one, on every level"}. '
                      f'Build time median {vcx["seconds"]["median"]:.1f} s at VC, {fx["seconds"]["median"]:.1f} s at F.</p></div>')
        mesh_box = (f'<div class="box"><h3>The mesh (new rules)</h3><div class="big">one ring per station + a tip cap</div><p>At VC: '
                    f'ring of {vcx["n_ring"]["min"]:.0f}–{vcx["n_ring"]["max"]:.0f} nodes, {vcx["n_span"]["min"]:.0f}–'
                    f'{vcx["n_span"]["max"]:.0f} stations. At F: {fx["n_ring"]["min"]:.0f}–{fx["n_ring"]["max"]:.0f} nodes, '
                    f'{fx["n_span"]["min"]:.0f}–{fx["n_span"]["max"]:.0f} stations. Fine level F: {fcell["median"] / 1e6:.2f} M '
                    f'cells median on the wing blocks (20 reference wings × 4 Re; every set: {fx["cells_est"]["median"] / 1e6:.2f} M, '
                    f'largest {fx["cells_est"]["max"] / 1e6:.2f} M; an estimate, the C-H wake lines add a rough +30–60 %), '
                    f'against 9–11 M asked.</p></div>')
        weak_box = (f'<div class="box bad"><h3>Weak points</h3><div class="big">numpy loft, no solve, cap quads near the limit</div>'
                    f'<p>The cap quads come close to the 0.05 limit (lowest {cap_s}); 17 % more stations than the plan file; the '
                    f'coarse levels do not resolve transition; Studies 1–8 used the old 20 reference shapes; the full sets were '
                    f'meshed on the numpy loft only. All in <a href="#open">Weak points</a>.</p></div>')
        done_f = f" the family screen (8 Nov): every set at every level, {ok_f:,} of {n_f:,} passed, one nose factor per family (Study 12);"
        not_done_box = (f'<div class="box verdict"><h3>Not finished</h3><div class="big">the close</div><p>Nothing is left in '
                        f'Stage 2 but the owner\'s word to close. Every mesh here is on the numpy loft; on Mike\'s machine (8 Nov) '
                        f'the pyGeo loft gave the same meshes on the 20 reference wings (VC and F: the same ring nodes and stations '
                        f'on 80 of 80 each; VC: every check value within 6 × 10⁻¹⁰). Both builder choices were confirmed and the '
                        f'upper band decided (8 Nov); the nose repair now belongs to the family. Then Stage 3 starts.</p></div>')
        pos_s = " or ".join(f"+{k}" for k in sorted({int(k) for lev in ab for k in ab[lev]["ring_nodes_added"] if int(k) > 0}))
        band_s = (f"Fixed on 8 Nov: written 0–100 % c (owner). The built mesh already had band-size cells there (one node list), "
                  f"so the counts hardly moved: {pos_s} ring nodes on {plus_s} meshes, the cells by at most "
                  f"+{100 * max(ab[lev]['cells_ratio']['max'] - 1 for lev in ab):.1f} % (Study 12)." if ab else
                  "Fixed on 8 Nov: written 0–100 % c (owner) (Study 12).")
    else:
        lede_f = done_f = ""
        verdict_box = screen_box = mesh_box = weak_box = not_done_box = band_s = None
    head = f"""
<header>
  <div class="eyebrow">CFD_Automation · Stage 2 · surface mesh · cfdauto {__version__} · 2 Nov 2026 · updated 8 Nov 2026</div>
  <h1>Surface Mesh</h1>
  <p class="lede">What Stage 2 is, what was built and how it works, what was studied, what it assumes, what the primer asked, what is open, and whether it is finished. Stage 2 was first built and screened on 2–3 Nov (the <em>first approach</em>). A new approach was decided on 4–6 Nov and <strong>built on 7 Nov</strong>: the surface rules in Stage 2 (levels VC, C, M, F with each target at the level that needs it, the lighter rules, the lower band from the leading edge), and in Stage 1 the nose fix and similarity (every wing at unit mean chord). The new screen passed {ok_new:,} of {n_new:,} builds (<a href="#study9">Study 9</a>).{lede_f} The section <a href="#change">What was first, and what changes</a> says what changed; an amber <em>What changes</em> box in every section says what changed there. Studies 1–7 are first-approach evidence, drawn on the geometry of before 7 Nov; Studies 8–{12 if sf else 11} are new.</p>
  <nav aria-label="On this page"><a href="#glance">At a glance</a><a href="#change">What changes</a><a href="#why">Why structured</a><a href="#what">What Stage 2 is</a><a href="#primer">What the primer asks</a><a href="#how">The steps, one by one</a><a href="#rules">The rules</a><a href="#studies">Studies and conclusions</a><a href="#study9">Study 9: the new screen</a><a href="#study10">Study 10: similarity</a><a href="#study11">Study 11: refine map by Re</a><a href="#study12">Study 12: the family screen</a><a href="#steps">What was done, step by step</a><a href="#assumptions">Assumptions</a><a href="#findings">Findings and decisions</a><a href="#open">Open, weak points, to do</a><a href="#handover">Handover to Stage 3</a><a href="#files">Files and commands</a></nav>
</header>"""

    glance = f"""
<section id="glance">
  <h2>At a glance</h2>
  <div class="three">
    {verdict_box or f'''<div class="box verdict"><h3>Is the surface mesh finished?</h3><div class="big">Built and screened with the new rules (7 Nov). Not closed yet.</div><p>The pyGeo loft on Mike's machine (8 Nov) gives the same meshes as the numpy loft (VC and F: the same ring nodes and stations on 80 of 80 each; VC: every check value within 6 × 10⁻¹⁰) on the 20 reference wings. Left: the family screen (Study 12), then close Stage 2 and start Stage 3, the matched C-H volume mesh.</p></div>'''}
    {screen_box or f'''<div class="box good"><h3>The new screen (7 Nov; reference wings 8 Nov)</h3><div class="big">{ok_new:,} of {n_new:,} builds passed</div><p>Every set at VC and at F ({vcf['wings']} wings at Re 3 × 10⁵; the 20 reference wings at all four Re levels), and the reference wings at C and M. {crash_new} crashes. The nose solved at every level: {'no nose repair' if rep_new == 0 else f"no nose repair on the reference builds; {ff['repairs']} of {ff['builds']} F builds needed one round"}. Build time median {vcf['seconds']['median']:.1f} s at VC, {ff['seconds']['median']:.1f} s at F.</p></div>'''}
    {mesh_box or f'''<div class="box"><h3>The mesh (new rules)</h3><div class="big">one ring per station + a tip cap</div><p>At VC: ring of {vcf['n_ring']['min']:.0f}–{vcf['n_ring']['max']:.0f} nodes, {vcf['n_span']['min']:.0f}–{vcf['n_span']['max']:.0f} stations. At F: {ff['n_ring']['min']:.0f}–{ff['n_ring']['max']:.0f} nodes, {ff['n_span']['min']:.0f}–{ff['n_span']['max']:.0f} stations. Fine level F: {fcell['median'] / 1e6:.1f} M cells median on the wing blocks (20 reference wings × 4 Re; an estimate, the C-H wake lines add a rough +30–60 %), against 9–11 M asked.</p></div>'''}
    <div class="box"><h3>Rules and checks</h3><div class="big">10 rules · 13 checks · {N_TESTS} tests</div><p>Every rule in one YAML with its anchor level and source (<code>configs/surface.yaml</code>; the first approach in <code>configs/surface_first.yaml</code>); every check with a value, a limit and a margin; a refused mesh writes only <code>refusal.json</code>. Code in <code>CFD_Automation/cfdauto/mesh/</code>, the rest in <code>Stage_2_surface_mesh/</code> (branch stage2-surface-mesh).</p></div>
    {weak_box or f'''<div class="box bad"><h3>Weak points</h3><div class="big">numpy loft, no solve, cap quads near the limit</div><p>The cap quads come close to the 0.05 limit (lowest {vcf['cap_quads_J']['min']:.3f} at VC, {ff['cap_quads_J']['min']:.3f} at F); 17 % more stations than the plan file; the coarse levels do not resolve transition; Studies 1–8 used the old 20 reference shapes. All in <a href="#open">Weak points</a>.</p></div>'''}
    <div class="box"><h3>The first screen (2–3 Nov)</h3><div class="big">{tot['passed']} of {tot['total']} builds passed</div><p>The first rules at level C, on the geometry of before 7 Nov: {tot['n_wings']} wings of 4 types and 5 sets at Re 3 × 10⁵; the 20 reference wings at all four Re levels. {tot['crashed']} crashes. Build time median {tot['sec_med']:.1f} s, max {tot['sec_max']:.1f} s.</p></div>
  </div>
</section>"""


    nt = {lev: (vcf if lev == "VC" else ff if lev == "F" else rv[lev])["nose_turning"] for lev in LEVELS}
    change = f"""
<section id="change">
  <h2>What was first, and what changes with the new approach</h2>
  <p>Stage 2 was built and screened on 2–3 Nov with the first approach. On 4–6 Nov a new approach was decided, and on 7 Nov it was built: the surface rules in Stage 2 (<code>configs/surface.yaml</code>, read by <code>laws.py</code>), the nose fix and similarity in Stage 1. The first approach is kept in <code>configs/surface_first.yaml</code> and still builds the same meshes, node for node. What is measured in Studies 1–7 (790 of 790 builds) is first-approach evidence, on the geometry of before 7 Nov: it shows the mesher works. Study 8 (7 Nov) counted the lower band with a plan file before the build. Study 9 is the new screen of the built rules; Study 10 checks what similarity does to the meshes. The table says what was first and what changed; the figures show the main changes. In every section below, an amber box <em>What changes</em> says what changed there.</p>
  {change_table(sn, uc)}
  {figc("levels_first_new.png", "Five rules on the four levels, first (grey, built 2–3 Nov) against new (blue, built 7 Nov): the values each level gets, read from the code (<code>laws.py</code> with each config). A rule is met at one level and every spacing is ÷ 1.3 per finer level. Green bars (top left): the largest turning each level delivered in the new screen. Level names: first C, M, F, FF; new VC, C, M, F (the same four places on the ladder).",
        f"First, every target was met at the coarsest level, so the finer levels went far past it (44 cells per bubble at FF) while the cost grew about 2.2 × per level. New, each target is met where it is needed: the accuracy targets (nose 10°, trailing edge 0.1 % c, station gap) at M, as the DPW guidelines define their medium grid, and the transition target (20 cells per bubble) at F, where SU2 with LM will run. The coarse levels are coarser than before (16.9° per nose cell and 9.1 cells per bubble at VC): good enough for the SA mesh studies, not for transition. Because the nose is solved at every level and the strictest spacing wins, the delivered turning sits at or below each level's angle: {nt['VC']['min']:.1f}–{nt['VC']['max']:.1f}° at VC, {nt['F']['min']:.2f}–{nt['F']['max']:.2f}° at F. The wall rules do not change: y⁺ ≤ 1 and growth 1.25 at the coarsest level give 1.107 at F, just above the 1.1 a transition model asks for (1.23 at VC would give exactly 1.1).")}
  {figc("cost_first_new.png", "The estimate of 6 Nov, before the build. Left: cells per mesh at the new levels with the lighter band: median and largest over the 20 reference wings × 4 Re levels (surfaces from the plan file × wall layers by formula; the wing blocks only). Right: the fine level F per rule set.",
        f"This is the first estimate (6 Nov): F at 10.9 M cells (median), inside the 9–11 M asked on 3 Nov; the planned rules gave 15.2 M. Its wall-layer rule was not recorded, and it used the first-approach reference wings (13 of the 20 replaced on 7 Nov). The pages now use the count of Study 9, because its rule is written down and it can be redone: F {fcell['median'] / 1e6:.1f} M median. Both count the wing blocks only; the C-H wake lines add a rough +30–60 %. Stage 3 sets the real wall-layer rule, and with it the real count.")}
  {figc("topology_first_new.png", "Left: the first plan: O rings around the section with an overset wake box (ADflow only). Middle: the new plan: one matched C-H mesh; the C rows wrap the nose and leave the trailing edge, the H blocks behind carry the wake to the far field. Right: the new plan from above: the station lines go on behind the wing and past the tip into the outboard blocks, where the tip vortex is resolved. Schematic, not a mesh.",
        "The surface mesh does not change: the ring is still the first row and the cap still closes the tip. What changes is the volume mesh (Stage 3, not built): a march that starts from an open line at the trailing edge, wake lines to the far field (about +45 % cells, rough), the tip vortex clustered in the outboard blocks instead of a tube, and no overlap gate. The nose must stay inside the C block's ring direction, a spacing request and not a block dimension: a separate nose collar with 5 points is what broke S6. The gain: one mesh family and one error bar for both solvers.")}
  {figc("band_negative.png", "The transition band on one section: the first band, and the two options for negative angles. Mike chose option A on 7 Nov; it is built.",
        "The first band (lower side 60–100 % c) was set for 0–8°. At −5° the lower side becomes the suction side near the nose, so its transition and bubbles move forward, out of the band: the refine map, run down to −5° (the section tables reach −10°), puts the lower transition at a median of 1–15 % c per wing type at −5°. Option A covers them with one rule for both sides. On paper its band is about 1.5 × longer (125 → 185 % of the chord), but counted on the 20 reference wings it costs no cells: the ring is the same, node for node, because both sides share one node list and the upper band already makes the front of the lower side fine (Study 8). So A was chosen (decision 74): transition runs can start at −5°.")}
  <h3>What stays the same</h3>
  <ul>
    <li>The pipeline and the code: stations, size fields, the nose solve, one node list, rings and cap, the 13 checks, the files. The new approach changes the values and where each rule is met. One step changed in how it runs: the nose is now solved at every level (VC, C, M, F), each for its own angle, and the strictest spacing wins; a coarser level is solved only where the finer level's answer, made 1.3 × coarser, misses its angle.</li>
    <li>The ring and the tip cap, the family rule (every spacing ÷ 1.3 per level and the growth g^(1/1.3)), the base counts 8, 10, 14, 18.</li>
    <li>One surface per wing and Re level (decision 59); under similarity, one per Re level of the unit-chord wing.</li>
    <li>The first-approach evidence on this page: it shows the mesher works on every wing. The new rules have their own screen now (Study 9).</li>
  </ul>
</section>"""

    why = f"""
<section id="why">
  <h2>Why a structured mesh, and why this one</h2>
  <p>A mesh is the set of small cells the solver computes on. There are two ways to build one. A <strong>structured</strong> mesh is rows and columns: every cell has an address (i, j, k), its neighbours are the next addresses, and the rows follow the surface. An <strong>unstructured</strong> mesh is a list of cells of any shape (triangles, tetrahedra, polyhedra) joined by a table of who touches whom. Both solve the same equations; they differ in what they make easy and what they make hard.</p>
  {figc("structured_vs_unstructured.png",
        "The BWB root section meshed both ways, for the picture only: left, rows of quads that follow the surface (the ring of Stage 2 is the first row; the layers are drawn by a plain offset here, the real march is Stage 3); right, triangles from a Delaunay triangulation of points around the same section.",
        "The structured mesh puts long, thin cells along the surface where the flow changes little along the wall and much across it; the unstructured one needs many more cells for the same resolution near the wall, and its cells have no rows to refine by a fixed ratio.")}
  <div class="two">
    <div class="box good"><h3>What a structured mesh gives us</h3><ul>
      <li><strong>Cells aligned with the flow.</strong> The boundary layer is thin and changes fast across, slowly along; rows of high-aspect-ratio quads resolve it with few cells and low numerical error. The DPW guidelines and most published wing CFD use structured near-wall grids for this reason.</li>
      <li><strong>An exact refinement family.</strong> Celik's grid-convergence method (Stage 0, D3) needs meshes that are true scaled copies with r ≥ 1.3. With rows, every spacing can be divided by r; a triangle mesh can only be "about" 1.3 × finer.</li>
      <li><strong>Addresses.</strong> Every node has (i, j): the nose is a known index, the trailing edge another, the tip a known station. Error maps by region (Grand Roadmap T3), ablations by direction (T6) and the laws (stage 5) all need that.</li>
      <li><strong>The solver.</strong> ADflow is a structured multiblock solver; overset lets us add the wake and tip-vortex boxes without one giant block.</li>
      <li><strong>Rules, not hand work.</strong> With one topology for every wing, the mesh is a set of numbers (spacings, counts, growth) that a law can give. That is the paper's claim.</li>
    </ul></div>
    <div class="box bad"><h3>What it costs</h3><ul>
      <li><strong>One topology per class of shape.</strong> The O ring around the section with an H cap on the tip fits wings with a flat tip and a blunt trailing edge. A winglet, a box wing or a fuselage would need a new block layout, by hand. (That is why box wings are out of scope.)</li>
      <li><strong>Counts are shared.</strong> Every station carries the same ring, so the station that needs most nodes sets the count for all; the tip, which needs about a third, gets the full ring. Cells cannot be added in one place only; refinement where the flow asks for it comes from the overset boxes (Stage 3), not from the near-body mesh.</li>
      <li><strong>Quality follows the geometry.</strong> Where the trailing edge sweeps at 85° over a 4 mm panel (corner set), the quads between stations shear; where two built noses differ (finding 64), the two sides fight. An unstructured mesh would not care.</li>
      <li><strong>The cap has corners.</strong> Closing a ring with one H patch leaves two cells with three corners on the smooth nose; a polyhedral cap would not.</li>
      <li><strong>No wake in the O mesh.</strong> An O ring cannot set the spacing along the wake (a layer is a quarter chord thick one chord behind); the wake box and the tip tube of Stage 3 carry it.</li>
    </ul></div>
  </div>
  {chg("ADflow and SU2 will both run one matched C-H mesh (SU2 reads it converted to unstructured hexes; it has no overset). In the C-H mesh the wake has its own rows, so two of the costs above go: the wake no longer needs an overset box, and the refinement behind the wing comes from the wake lines, not from boxes (Stage 3, not built). The nose finding (64) in the list above was real: the old Stage 1 rule made the two sides of the nose differ, and it was fixed in Stage 1 on 7 Nov (Study 4). The 85°-sweep corner panels came from the old 0.5 mm trailing-edge floor and are gone under similarity (Study 5).")}
  <h3>O, C or H around the section, and why O-H</h3>
  <p>Three ways to wrap rows around a section: <strong>O</strong> (closed rings), <strong>C</strong> (rows that wrap the nose and run off behind the trailing edge, so the wake has rows), <strong>H</strong> (rows above and below, a collapsed line at the nose). The mesh study (S0–S8, in the AERIS_MESH_STUDY folder) tried six strategies and settled on S8, an O ring with an H cap on the tip: the O ring puts the nose and the base inside one closed curve, so leading-edge resolution is a spacing request, not a block dimension (the C-family's nose collar capped it at 5 points, which was the whole source of the pressure-peak defect); the H cap is the one patch that closes the ring without a collapsed edge. The price, no rows in the wake, is paid with overset boxes (Stage 3).</p>
  {figc("topology.png",
        "Left, side view: the ring (Stage 2) and a sketch of the O layers the march will add (Stage 3), with the wake box behind the trailing edge. Right, top view: the half wing with its stations, the tip cap and the outboard blocks, the wake box and the tip-vortex tube of the overset plan.",
        "Stage 2 builds only the first row (the ring at every station) and the patch on the tip. Everything that reaches into the air, the layers, the outboard blocks, the boxes, is Stage 3 and uses this surface as its wall.")}
  {chg("The volume topology is now <strong>C-H, matched, for both solvers</strong>. Why: SU2 has no overset (cutting holes and interpolating between overlapping meshes is solver code, not a file format), and one matched family gives one error bar for both solvers. The O-H argument above still holds for the nose: the nose must stay a spacing request inside the C block's ring direction; a separate 5-point nose collar (S6) is what made the pressure-peak defect. The ring and the cap of this stage are the same in both plans; the change is in Stage 3 (<a href='#change'>figure above</a>).")}
  <h3>What the surface mesh must get right (from Stage 1)</h3>
  <p>The flow study of Stage 1 said where the baseline must be fine before any refinement: the nose (the suction peak; transition reaches it at high angle), a wide transition band (upper 10–85 % c, lower 60–100 % c). The band is not where transition is at one condition: at one angle and Re the flow turns turbulent over a short stretch, the bubble, 0.05–0.4 c long. The band is where that stretch can land over everything one mesh must serve: at a given Re the same mesh is run over the whole angle range, now −5° up to stall onset (it was 0–10° root angle). Over 0–10° Stage 1 found the upper surface turning turbulent anywhere from about 11 % c (high angle) to 78 % c (low angle, low Re), and the lower surface staying laminar to about 99 % c. Below 0° the lower side turns turbulent near the nose instead: at −5° at a median of 1–15 % c over the strips (2-D strips, Study 8). A mesh that is fine only where transition sits at one angle would be wrong at the next. A mesh per angle is possible (solution-adaptive meshing does exactly that) but we chose not to: Stage 0's rule for a mesh study is one change per run, so the results at 0°, 4° and 8° must come from the same mesh family to be compared; a per-angle mesh needs to know where transition will sit before the solve, which only the 2-D strips can say today; and it would multiply the mesh count by the number of angles. If the chordwise ladder (T6) shows the band is the cost that matters, a narrower band per angle is the first thing to revisit (Study 7 shows what a per-wing band looks like today). The other places where the baseline must be fine: the trailing edge and its blunt base, every break of the planform (a kink in the loft), the tip (smallest chord, lowest Re, the vortex), and enough stations along the semi-span. How many is set by how long the half wing is measured in its own chords, not by a fixed number: a slender wing (long semi-span, short chord) is many chords long and needs more slices than a stubby one. The rule here: a station every 0.2 of the local chord (a half wing 10 chords long gets about 50), at least 12 per panel, and extra ones squeezed in toward the tip. The wall and the wake belong to Stage 3. Every one of these became a rule below.</p>
  {chg("The angles now run from −5° to post-stall (steady RANS up to stall onset; a separate post-stall study). At negative angles the lower side becomes the suction side, so the lower band now runs from the leading edge, 0–100 % c (decision 74, option A, decided by Mike on 7 Nov and built). It costs no cells, because the shared node list already makes the front of the lower side fine (<a href='#study8'>Study 8</a>). The station rule is now a gap of 0.25 × the local chord at M (0.4225 c at VC). Under similarity (built 7 Nov) every wing is built at unit mean chord, and the Re on the mean chord is an input.")}
</section>"""

    what = f"""
<section id="what">
  <h2>What Stage 2 is</h2>
  <p>Stage 1 made the wing: one exact loft per design vector, with measured values and a hash. Stage 2 puts a structured surface mesh on that loft: a closed ring of points around the section at every spanwise station, root to tip, the same ring at every station, plus one patch that closes the flat tip. Every node is asked from the loft at (x/c, v); nothing is interpolated between stored sections. The volume mesh (the march off the wall), the wake boxes and the CGNS file are Stage 3. The mesh name carries the level and the Re: <code>mesh_&lt;level&gt;_&lt;wing_hash8&gt;_re&lt;Re&gt;</code>, because the tip gap and the band cells depend on the Re.</p>
  {fig_pipeline()}
  {cbox("Six steps, the same for every wing: stations, size fields, the nose solve, one node list, rings and cap, checks. No step knows the wing type; the rules read the loft, the chord and the local Re. Every box of this figure has its own visual below, under the same number, in the section <a href='#how'>The steps, one by one</a>.")}
  <p>The Grand Roadmap's recipe R-S (one closed ring per station) and its step M1 (every surface constant into one module of laws) are what this stage implements. The volume recipe R-V and steps M2–M5 (first-cell law, march, boxes, overset export, driver) are Stage 3.</p>
  {chg("Under similarity (built in Stage 1 on 7 Nov) every wing is built at unit mean chord, so a mesh is set by its shape, its level and its Re level: four surfaces per wing and level, one per Re level. The mesh name keeps its form with the new level names (<code>mesh_VC_…</code>). In Stage 3 the boxes and the overset export (R-V.6, M3) are replaced by the matched C-H mesh.")}
</section>"""

    primer = f"""
<section id="primer">
  <h2>What the primer and the Stage 1 handover ask from Stage 2</h2>
  <p>The AERIS Mesh Automation Primer (Annex G, the Grand Roadmap) gives the surface mesh as recipe R-S.1–R-S.9 and the code step M1, with the family rule M4. The Stage 1 handover adds where the baseline must be fine per family. Item by item, with what was built and the evidence:</p>
  {primer_table()}
  <p>Two things in the primer are not in this stage on purpose: the constants it names (n_side 75, n_span 49, 1,601 dense points) were S8's values for one wing; here every count follows from a rule, so it changes with the wing and the Re. And the primer's M1 asks for a bit-identical rebuild of g83; CFD_Automation has no AERIS wings, so the equivalent test is a bit-identical rebuild of the same input (it passes).</p>
  {chg("The primer's overset plan (R-V.6 and M3: boxes, overset export, overlap gate) is replaced by the matched C-H mesh (Stage 3). R-S.4 (trailing edge 0.1 % c) and R-S.5 (nose 10°) are now accuracy targets met at M (built 7 Nov), so they hold on M and F and are looser on VC and C. R-S.7 (the family rule) now also moves the growth limits and the counts from their anchor level.")}
</section>"""

    steps = """
<section id="steps">
  <h2>What was done, step by step</h2>
  <p>In the order it happened. Steps 1–14 are the first approach (2–3 Nov): three passes of the screen were needed; the first two are development evidence, the last is the result. Steps 15–18 are the new approach (6–7 Nov).</p>
  <div class="steps">
    <div class="step"><span class="k">1 · inputs</span><h3>Read the handover and the primer</h3><p>Stage 0 values, the Stage 1 handover table (where the mesh must be fine), Annex G recipe R-S and step M1, and the S8 surface code (section_o.py, strategy_s8.py: the ring, the turning solve, the tip cap).</p></div>
    <div class="step"><span class="k">2 · one tool</span><h3>The spacing tool</h3><p>One function set for both directions: a target cell size along a line, a growth limit, and points placed so every cell holds the same share of ∫ds/h. S8's two-sided tanh stretching could only set the two end cells; the band needs a set size in the middle of a side.</p></div>
    <div class="step"><span class="k">3 · rules</span><h3>The laws and the YAML</h3><p><code>configs/surface.yaml</code> holds every value with its source; <code>laws.py</code> turns each into a function of the level. The cells-per-bubble rule got its source (Ansys CFX transition-model guide: 20 nodes per bubble).</p></div>
    <div class="step"><span class="k">4 · ring</span><h3>The ring at one station</h3><p>Size field per side (nose, band, trailing edge, largest cell, growth), the nose solve by bisection on the ring as built, the base across the blunt trailing edge.</p></div>
    <div class="step"><span class="k">5 · spanwise</span><h3>The stations</h3><p>On every loft station; gap 0.2 × chord, at least 12 per panel; squeezed to the tip first cell s0 at the tip Re.</p></div>
    <div class="step"><span class="k">6 · tip</span><h3>The cap, ported from S8</h3><p>One H patch whose edge is the tip ring node for node, Laplacian smoothing with the edge held, oriented outboard.</p></div>
    <div class="step"><span class="k">7 · gates</span><h3>Checks, files, command line</h3><p>13 checks that refuse; <code>surface.npz</code>, Plot3D, <code>stations.csv</code>, <code>quality.json</code>, <code>manifest.json</code> with four hashes; <code>python -m cfdauto.mesh</code>.</p></div>
    <div class="step"><span class="k">8 · tests</span><h3>14 tests</h3><p>Spacing tool, every node on the loft, turning at every station, band and trailing-edge spacing, stations on every loft station and the tip gap, cap edge = tip ring, same input → same mesh, sealed sets refused, writer and refusal, and the family ratio test (C against M).</p></div>
    <div class="step"><span class="k">9 · screen 1</span><h3>First screen: what it found</h3><p>Per-station node distributions. Found: a tip-gap tolerance (integer counts), a crash on the corner set (a ~10° bend at the trailing-edge opening of 12 mm chords), a break 0.9 mm from the root that broke the spanwise grid, and the lowest wing-quad quality of 0.08 in the tip squeeze.</p></div>
    <div class="step"><span class="k">10 · fix</span><h3>One distribution for the wing</h3><p>The strictest station and side at every arc fraction: node i sits at the same arc fraction on every station. Quads 0.08 → 0.58 on the worst wing; the envelope holds by construction; +3 % nodes.</p></div>
    <div class="step"><span class="k">11 · screen 2</span><h3>Second screen: what it found</h3><p>Chord growth 1.25–1.26 on NACA 4415 noses (the lower side follows the upper side's arc fraction; where the two built noses differ, its first cells grow a little faster). Allowed within 1 %, like the other delivered-against-asked checks.</p></div>
    <div class="step"><span class="k">12 · fix</span><h3>The nose held over four cells</h3><p>The helper that holds a size over a length took the length as the size, so the nose cell came out 4 × the asked size and the solve compensated. Fixed; the delivered turning was right all along, the reported asked spacing was not. The largest growth fell from 1.26 to 1.21.</p></div>
    <div class="step"><span class="k">13 · screens 3, 4</span><h3>The last two screens</h3><p>The third pass was clean but the size-field figure of this page exposed the nose held over one cell instead of four (step 12); the fourth, on the committed code, gives the numbers on this page: 790 of 790.</p></div>
    <div class="step"><span class="k">14 · studies</span><h3>Family ratios, nose radius, figures, docs</h3><p>C, M, F on the four reference wings; raw against built nose radius of the ten suggested airfoils; this page; the decisions note; open decisions 56–64; the branch pushed.</p></div>
    <div class="step"><span class="k">15 · 6 Nov</span><h3>The new approach decided</h3><p>Levels VC, C, M, F with each target at the level that needs it; the lighter band, tip gap and station gap; one matched C-H volume mesh for ADflow and SU2; similarity; angles −5° to post-stall; transition with ADflow and SU2. This page, the refine map, the status and the decisions updated (67–76); the code not yet.</p></div>
    <div class="step"><span class="k">16 · 7 Nov</span><h3>The band count</h3><p>The refine map run down to −5°; the lower side read at −5°, −2° and 0°; options A and B built at VC with the planned rules on the 20 reference wings × 4 Re (160 builds): the same ring on every pair (Study 8). Mike chose A.</p></div>
    <div class="step"><span class="k">17 · 7 Nov</span><h3>Stage 1: the nose fix and similarity</h3><p>The nose re-measured with one curvature method: the defect was real, the 6 Nov correction wrong; the new rule (apex, one cubic spline, 201 points per side, a nose gate) built (64). Similarity built (70): unit mean chord, 17 numbers, trailing edge 0.2 % c; the sets rebuilt (722 of 722), every hash new, 13 of 20 reference wings new picks.</p></div>
    <div class="step"><span class="k">18 · 7 Nov</span><h3>Stage 2: the new rules, built and screened</h3><p>Levels VC, C, M, F with anchored values (71), the lighter rules (72), the lower band from the leading edge (74, A) in <code>configs/surface.yaml</code> and <code>laws.py</code>; the first approach kept in <code>configs/surface_first.yaml</code>. The nose first solved at VC and F; M then needed a repair on the flying wings, so the nose is now solved at every level and the strictest wins (owner, 7 Nov). The new screen (Study 9) and the similarity check (Study 10); this page, the summary, the status and the decisions updated.</p></div>
    <div class="step"><span class="k">19 · 7 Nov</span><h3>The refine map at the Re levels; the upper band checked</h3><p>The refine map in its Re mode on the new reference wings and the rebuilt section tables (Study 11). The upper band as written (0–85 % c) misses the upper transition at low Re, while the built mesh has band-size cells there. Written as 0–100 % c it is the same mesh at VC to round-off, but 2 more ring nodes at F on 42 of 80 reference builds; the owner chose 0–100 % c on 8 Nov (Study 12).</p></div>
  </div>
</section>"""

    how = f"""
<section id="how">
  <h2>The steps, one by one, with their visuals</h2>
  <p>One wing, one level, one Re. The numbering is the pipeline figure's: IN, steps 1 to 6, OUT. Every figure is from the BWB reference wing (index 0, level C, Re 3 × 10⁵) unless said otherwise.</p>
  <h3>IN · The loft in, and the dense section the mesher reads from it</h3>
  <p>At a station v the loft gives the upper and lower surface at any x/c. The mesher samples each side at 6,001 points, cosine in x/c (dense at the nose and the trailing edge), and keeps a table of arc length against x/c per side. That table turns a cell size in metres into a position on the loft; the dense points themselves are never nodes. The same dense curve gives the radius of curvature along the section (right panel), used by the curvature cap and the kink check.</p>
  {figc("dense_section.png", "BWB reference wing, root section (MH 104). Left: the dense sample at the nose (the first 120 of 6,001 points per side). Middle: arc length against x/c per side. Right: radius of curvature of the built section along the chord.",
        "Six thousand points per side resolve the nose to 3 × 10⁻⁵ c of arc, finer than any cell asked for. The curvature of the built section is not the same on the two sides at the leading edge (0.024 c against 0.005 c): finding 64, below. It was real, made by the old Stage 1 rule, and it is gone with the nose fix of 7 Nov (Study 4). This picture is first-approach evidence, drawn on the old section.")}
  <h3>Step 1 · Where the stations go</h3>
  <p>A station sits exactly on every loft station (b0–b3 and the trailing-edge switch station some BWBs have), because the ruled loft has a crease there. Between them the target gap is 0.2 × the local chord, at least 12 gaps per panel, and the gaps may change by at most 1.2 from one to the next. Toward the tip the gaps shrink to the tip first cell s0: the height of the first layer of cells the volume mesh (Stage 3) will put on the wall, set by y⁺ = 1 at the tip Re (explained under Step 2), so the cap faces a cell of the size it will get in the volume mesh. Each panel gets a whole number of gaps, placed so each holds the same share of ∫dy/h. Where each number comes from: a station on every loft station is geometry (the ruled loft has a crease there); the last gap = s0 is the Grand Roadmap (laws 9, 10: the cap's first cell must match the tip's); the growth limit 1.3 is the Stage 1 handover, and we build at 1.2 to leave room for whole numbers; the 0.2 × chord gap and the 12 per panel are our starting values, not derived from a study: 0.2 c gives surface cells about 50 × longer along the semi-span than along the chord, usual for wing meshes, and 12 is the smallest whole number for which a break between two panels cannot step the gap by more than 1.2 × (1 + 1/12) ≈ 1.3. Both are open decision 62, for the spanwise ladder to test.</p>
  {figc("stations.png", "BWB reference wing, level C, Re 3 × 10⁵. Left: the station gap along the semi-span: the 0.2 c target, the size field after the 12-per-panel rule, the tip squeeze and the growth limit, and the gaps delivered. Middle: every station as a chord line. Right: the last 12 mm before the tip.",
        "The 0.2 c rule hardly acts: the 12-per-panel floor sets the inner panels and the tip squeeze sets the outer one (43 of its gaps lie in the last few millimetres, from 3 cm down to 36 µm). The station count is therefore mostly a count of panels and of the squeeze, not of the chord; the spanwise ladder must test both.")}
  {chg(f"Built 7 Nov: station gap 0.25 × local chord met at M (0.4225 c at VC), at least 12 gaps per panel at M (8 at VC, 16 at F); the last gap at the tip = 2 × s0, with s0 from y⁺ = 1 at VC. The new screen gives {vcf['n_span']['min']:.0f}–{vcf['n_span']['max']:.0f} stations at VC and {ff['n_span']['min']:.0f}–{ff['n_span']['max']:.0f} at F (Study 9). The station growth stays 1.2, as decided; the plan file of Study 8 used 1.25 and 7 gaps per panel, which is why the built rules have 7–14 more stations (about +17 %) than the plan's count.")}
  <h3 style="font-size:17px">Step 1, the rules one by one, and which one sets each gap</h3>
  <div class="two">
    <div class="box"><h3>The five rules, and where each comes from</h3><ul>
      <li><strong>A station on every loft station</strong> (b0, b1, b2, b3 and the trailing-edge switch station). Geometry: the loft is straight between them and has a crease at each, so a station there follows the kink. <span class="flag ok">source: geometry; Stage 1 handover</span></li>
      <li><strong>At least 12 gaps per panel.</strong> A panel gets a whole number of gaps, so the gap size can jump at a break by up to 1/n; 12 is the smallest n for which 1.2 × (1 + 1/12) stays under the 1.3 limit below. <span class="flag chg">our choice, derived from the 1.3 limit; open decision 62</span></li>
      <li><strong>A gap of 0.2 × the local chord</strong> where the panel is long enough for it (longer than 2.4 chords). On the reference wings it never acts: the 12-per-panel floor and the tip squeeze set every gap. <span class="flag chg">our choice, no source; open decision 62</span></li>
      <li><strong>Neighbouring gaps differ by at most 1.2</strong> (built) and <strong>1.3</strong> (checked). The 1.3 is the Stage 1 handover's limit on spanwise growth (the DPW guidelines give the same kind of limit for growth in general); 1.2 is what we build at, to leave room for the whole-number jumps at the breaks. <span class="flag ok">source: Stage 1 handover; DPW (Levy et al. 2013)</span> <span class="flag chg">1.2: our choice</span></li>
      <li><strong>The last gap at the tip = s0</strong>, the first wall cell the volume mesh will put on the tip cap (y⁺ = 1 at the tip Re). From the last panel's gap down to s0 at 1.2 per step takes about 40 stations. <span class="flag ok">source: Grand Roadmap, laws 9 and 10 (our own primer); s0 from the flat-plate law, White 2006</span></li>
    </ul></div>
    <div class="box"><h3>Two different 1.3s on this page</h3><ul>
      <li><strong>Growth 1.3 between neighbouring station gaps</strong> (and 1.25 between neighbouring cells along the ring): how fast cells may change size next to each other, inside one mesh. Source: the Stage 1 handover and the DPW guidelines.</li>
      <li><strong>The family ratio r = 1.3 between levels C, M, F</strong>: every spacing of the whole mesh divided by 1.3 to make the next finer mesh, for the grid-convergence estimate. Source: Celik et al. 2008 (r ≥ 1.3).</li>
      <li>They are unrelated numbers that happen to be equal. The station rules above come from the first (growth), not from the family ratio; the only numbers derived from a growth limit are the 12 per panel (so the jump at a break stays under 1.3) and the about 40 stations of the tip squeeze.</li>
    </ul></div>
  </div>
  {figc("station_rules.png", "Every station gap of two reference wings as a bar, coloured by the rule that set it: the BWB (semi-span 3 chords) and the most slender tapered reference wing (7 chords). Black lines: the loft stations.",
        "On real wings of our focus space the 0.2 × chord rule never acts: every gap is set either by the 12-per-panel floor (the straight runs) or by the growth limit (the tip squeeze from millimetres down to tens of µm, and the step between two panels whose floors differ). So the station count is mostly 12 × the number of panels plus about 40 for the squeeze; the spanwise ladder should test the floor and the squeeze before the 0.2 c value.")}
  {figc("four_types.png", "The four reference wings (index 0) at level C, Re 3 × 10⁵ on the mean chord: every second station and every 24th ring line of the upper surface.",
        "Same rules, same code, four shapes: the BWB gets the most ring nodes (its root carries the highest local Re, so the smallest band cell as a fraction of the chord) and the most stations (its tip is the smallest). Nothing was set by hand for any type.")}
  <h3>Step 2 · The size field around the section: how big a cell may be at every place</h3>
  <p>Per station and side, the target cell size along the arc is the smallest of every rule that applies there: the largest cell (2 % c), the transition band (bubble length / 20 at the local Re; upper first 0–85 % c, now 0–100 % c; lower first 60–100 % c, now 0–100 % c), the curvature cap (cell ≤ R × 10° away from the nose), the nose cell held over four cells, the trailing-edge cell (0.1 % c), then a growth limit of 1.2 per cell. Points are then placed so each cell holds the same share of ∫ds/h: the same tool as along the semi-span.</p>
  {figc("size_field.png", "The root section of the BWB reference wing, upper side, built one rule at a time: each panel adds one rule to the previous result (grey). 1: no cell larger than 2 % c. 2: the transition band. 3: the curvature cap. 4: the nose and trailing-edge cells. 5: growth ≤ 1.2 turns the jumps into ramps: the station's own wish list. 6: what is delivered after the list is shared with the lower side and the other stations (dots).",
        "On this wing the band sets almost everything: first, with the upper band to 85 % c and the lower band from 60 % c shared through the one distribution, the whole ring is at band spacing except the nose and the trailing edge. The curvature cap never acts here (panel 3 equals panel 2). The delivered nose cell (0.04 % c, panel 6) is smaller than this station's own 0.096 % c (panel 4) because the sharpest nose of the wing, the tip's MH 61, sets it for every station.")}
  <h3 style="font-size:17px">Step 2, continued: the two sizes that depend on the Reynolds number</h3>
  <p>Two sizes: the band cell (bubble length / 20 at the local Re) and the tip first cell s0 (y⁺ = 1). So one wing has one surface per Re level; building one takes seconds.</p>
  <div class="two">
    <div class="box"><h3>What s0 is</h3><ul>
      <li>s0 is the <strong>first wall cell</strong>: the height of the very first layer of cells that the volume mesh (Stage 3) will grow from the wing surface into the air. It is a volume-mesh size, not a surface-mesh size.</li>
      <li>The surface mesh uses it in one place: the last station gap at the tip is set to s0, so the tip cap meets a cell of the same size as the first volume layer there (Grand Roadmap, laws 9 and 10). From the last panel's gap down to s0 takes about 40 stations at 1.2 per step: that is the "tip squeeze".</li>
      <li>It is not a free choice: it follows from y⁺ = 1. y⁺ is the distance from the wall measured in the flow's own wall units; the turbulence model wants the first cell inside the thin layer right at the wall, which means y⁺ about 1 (Stage 0 budget, row 1c, after the DPW gridding guidelines; Grand Roadmap law 13).</li>
    </ul></div>
    <div class="box"><h3>Where its formula comes from</h3><ul>
      <li><strong>s0 / c = y⁺ / (Re √(Cf / 2))</strong>, with Cf = 0.026 Re^(−1/7): the friction law of a turbulent flat plate (White, Viscous Fluid Flow). Why: y⁺ = y u_τ / ν, the friction velocity is u_τ = U √(Cf / 2), so y = y⁺ ν / (U √(Cf / 2)); divide by the chord and ν / (U c) = 1 / Re.</li>
      <li>Only the Re changes it, so it is one number per station, like the band cell: 0.032 % c at Re 6 × 10⁴, 0.0072 % c at 3 × 10⁵, 0.0024 % c at 10⁶ (middle panel of the figure below).</li>
      <li>Example: the BWB reference wing at Re 3 × 10⁵ on the mean chord has a tip chord of 14 cm at a tip Re of 8 × 10⁴, so s0 = 0.025 % × 14 cm = 36 µm: the last station gap at its tip.</li>
      <li>A flat plate is an estimate; the real wall friction differs along the chord. The volume mesh uses the same law per station, and the first solve audits y⁺ (assumption A4).</li>
    </ul></div>
  </div>
  <div class="two">
    <div class="box"><h3>What the band cell is</h3><ul>
      <li>At our Reynolds numbers the flow on the wing starts laminar, lifts off the surface, becomes turbulent in the air just above it, and lands again. The pocket of slow air between lift-off and landing is the <strong>laminar separation bubble</strong>. It changes the drag and where the flow turns turbulent, so the mesh must resolve it.</li>
      <li>The bubble is long at low Re and short at high Re: 0.40 c at Re 6 × 10⁴, 0.05 c at Re 10⁶ and above. These lengths come from the Stage 1 XFOIL table (2-D, calm air, N_crit 9); nothing else in the project says how long a bubble is.</li>
      <li>Where the bubble sits depends on the angle of attack, which changes from run to run. So one cell size is set over the whole stretch where it can sit, the <strong>transition band</strong> (upper side first 0–85 % c, now 0–100 % c; lower side first 60–100 % c, now 0–100 % c): that cell size is the band cell.</li>
    </ul></div>
    <div class="box"><h3>Where the formula comes from</h3><ul>
      <li><strong>band cell = bubble length / 20</strong>, in three steps per station: ① local Re = Re on the mean chord × local chord / mean chord; ② bubble length from the table at that Re; ③ divide by 20.</li>
      <li>The 20 is not ours: the Ansys CFX guide for the γ-Re_θ transition model asks for at least 20 nodes across a bubble, or the model puts transition in the wrong place. The Stage 1 rule had no source; this is the only one found (decision 56). One vendor, one model: the T6 ladder (20 → 13 → 8) must test it.</li>
      <li>Example at Re 3 × 10⁵: bubble 0.126 c → cell 0.63 % c → about 135 cells over the upper band. At Re 10⁵: 0.30 c → 1.5 % c → about 57 cells. A long root chord has a higher local Re, so a shorter bubble and a smaller cell as a fraction of its chord.</li>
    </ul></div>
  </div>
  {figc("band_cell.png", "Left: a laminar separation bubble on the upper side of a section, with the 20 cells the rule puts across it (red ticks) and the band where it may sit (blue). Right: the three steps for one station at Re 3 × 10⁵: the local Re, the bubble length read from the Stage 1 table, and the division by 20.",
        "The band cell is one number per station and side, set by the local Re alone: the rule has no free choice except the 20, which comes from one vendor guide. The bubble lengths are 2-D XFOIL values, so the rule is as good as that table; 3-D effects, sweep and roughness move bubbles and are not in it.")}
  {chg("Built 7 Nov: band cell = bubble length / 20 met at F, so bubble length / 9.1 at VC. The bubble length stops at 0.10 c from local Re 4 × 10⁵ up: the cell is 0.5 % c at F there, twice the first approach's 0.25 % c at high Re (table under <a href='#rules'>The rules</a>). The price: the shortest high-Re root bubbles (about 1.5 % c) get about 3 cells, fine for SA and wrong for LM; the 3-D check on the BWB centre body decides whether a local band is needed. The lower band now runs from the leading edge (decision 74, option A): it costs no cells (Study 8). As built, the upper side also gets band-size cells over 85–100 % c through the one node list (Study 11); writing the upper band as 0–100 % c is for the owner to decide (it adds 2 ring nodes at F on about half of the reference builds).")}
  <div class="two">
    <div class="box"><h3>How XFOIL gives the bubble length</h3><ul>
      <li>XFOIL computes the thin layer of air on the surface (the boundary layer) along the section and writes, at every point of the surface, the wall friction coefficient Cf: how hard the air rubs on the wall, and in which direction.</li>
      <li>Where the flow has lifted off, the air at the wall runs backwards and Cf is negative. So a bubble is read as a stretch of Cf &lt; 0 on one surface: it starts where Cf crosses zero (separation) and ends where Cf comes back above zero (reattachment). Its length is end − start, in chords.</li>
      <li>Two rules keep it honest: a Cf &lt; 0 stretch that reaches past 95 % c is trailing-edge separation, not a bubble; stretches shorter than 0.5 % c are ignored. If a surface has several, the longest counts. Transition itself is XFOIL's e^N method with N_crit 9 (calm air). Code: Stage 1 <code>cfdauto/flowmap/xfoil.py</code>, <code>features()</code>.</li>
    </ul></div>
    <div class="box"><h3>From the runs to the table</h3><ul>
      <li>Stage 1 ran this on the 10 airfoils of the section sets at 14 Re, 3 Mach and 49 angles (2,408 sweeps). The Stage 2 table takes the upper-surface bubbles at Mach 0.1, 0–8°, and reads the typical length per Re: 0.45 c at 6 × 10⁴, 0.31 c at 10⁵, 0.11 c at 4 × 10⁵, 0.055 c at 10⁶ (medians), rounded to 0.40, 0.30, 0.10 and 0.05.</li>
      <li>The length changes with the angle of attack and the airfoil: the middle half of the bubbles sits within about 10–40 % of the median, depending on Re. The table is at or just under the median, so about half the bubbles get 20 cells or more; the shortest quarter gets 14–18.</li>
      <li>Below Re 4 × 10⁴ XFOIL finds no bubble (open separation); above 1.5 × 10⁶ only a few airfoils keep one (MH 104, LA2573A). The table stays at 0.05 c there, which is "under 0.05 c" in the Stage 1 handover.</li>
    </ul></div>
  </div>
  {figc("bubble_xfoil.png", "Left: a sketch of the wall friction Cf along the upper surface of one XFOIL run, and how the bubble is read from it. Right: every upper-surface bubble length in the Stage 1 tables (10 airfoils, free transition N_crit 9, Mach 0.1, 0–8°) per Re as a box (middle half) and whiskers (the rest), with the share of cases that have a bubble, and the Stage 2 table on top.",
        "The table follows the medians of the Stage 1 runs within rounding. It is one length per Re, while the real bubbles at one Re spread by tens of per cent with angle and airfoil, so the 20-cells rule holds for the typical bubble, not the shortest one. Everything here is 2-D XFOIL in calm air; a 3-D check of bubble lengths is still owed (A2).")}
  {figc("re_rules.png", "Left: the bubble-length table from Stage 1. Middle: the band cell and s0 against the local Re at level C. Right: ring nodes of the reference wings against the Re on the mean chord; S8's 150 for comparison.",
        "The ring grows with Re until the bubble-length floor (0.05 c, band cell 0.25 % c) is reached at about Re 10⁶, then stays at about 850 nodes. At 10⁵ it is about 200: the rule follows the physics (long bubbles need few cells per chord), not a fixed count. Every Re level needs its own surface.")}
  <h3>Step 3 · The nose: solved on the ring as built</h3>
  <p>S8 found that a nose-radius estimate gave 20° per cell when 6° was asked, so the nose spacing is solved: build the ring, measure the largest turning at any node, bisect the nose spacing until the turning is 10° ± 0.02°. The check covers every ring node except the two trailing-edge corners, because on cambered noses the sharpest cell sits a few cells onto the lower surface. The built noses are not monotone (right panel; finding 64), so the solve walks down until every spacing in [0.77 h, h] passes, and a station that still lands above the target after the shared distribution tightens the nose spacing of the whole wing by 10 %.</p>
  {figc("nose_solve.png", "Turning per cell against the nose spacing, measured on rings built at 40 spacings. Left: the BWB root (MH 104). Right: a NACA 4415 station of a tapered training wing.",
        "What the search does: it makes the nose cells smaller step by step until no cell bends the surface by more than 10°. Left (MH 104): smaller nose cells give less bending, in one steady line, so one search finds the right size. Right (NACA 4415, first-approach picture on the old section): the line is not steady. Below about 0.2 % c the worst cell is no longer at the nose: it sits 1.9–2.4 % c down the lower side, where the cells (0.37–0.45 % c) are set by the growth limit 1.2, not by the nose spacing, so the line goes flat at about 7°. The old section also had a small bump on its lower side; it was a Stage 1 defect, now fixed (Study 4), but it is not what makes the line flat: the true airfoil does the same (6.0–6.8° with the fix). The small up-and-down comes from counting: each new size changes the number of nodes on the side, every node moves a little, and so the worst one changes. What this means for the code: a plain search can land on a size that passes by luck and fails as soon as the nodes move. So the solve also tries the sizes just below its answer (the window), and the final rings are checked again. The flat part at the far right of the left plot is another rule (the curvature cap) limiting the cells, not the nose rule.")}
  {chg(f"Built 7 Nov: the 10° target is met at M (16.9° at VC, 13° at C, 7.69° at F), and each level is checked against its own angle + 0.2°. The nose is solved at every level, each on its own ring for its own angle, and the strictest spacing, moved to VC, wins; every level takes it ÷ 1.3^k, so every level meets its own angle with no repair and the family rule stays exact (owner, 7 Nov). The first build solved it at VC and F only; M then needed one repair (nose × 0.9) on all 20 flying-wing reference builds (Study 9). In the new screen VC turns {nt['VC']['min']:.1f}–{nt['VC']['max']:.1f}° instead of 16.9°, because a finer level's solve sets the nose. The bump on the NACA 4415 lower side was a Stage 1 defect, fixed on 7 Nov; the flat line stays (growth law), and so does the window search.")}
  <h3>Step 4 · One node list for all stations</h3>
  <div class="two">
    <div class="box"><h3>Why one list</h3><ul>
      <li>A structured mesh needs the same ring at every station: the same number of nodes, at the same relative places, so that node i of one station joins node i of the next in a clean four-sided cell.</li>
      <li>Step 2 gave every station its own wish list of cell sizes along the section, and the lists differ: the root has the highest local Re (small band cells), the tip has the sharpest nose (small nose cells), the lower side has its band at the back.</li>
      <li>With a list per station, node i drifted along the chord from one station to the next; where the stations are tens of µm apart at the tip, that drift sheared the cells (scaled Jacobian 0.08, Study 3).</li>
    </ul></div>
    <div class="box"><h3>How the lists are merged</h3><ul>
      <li>Every side of every station is measured as a fraction of its own length, 0 at the nose and 1 at the trailing edge, so all lists sit on one scale whatever the chord.</li>
      <li>At each fraction the smallest wished cell of any station or side is taken. Example on the BWB reference wing: nose, root wants 0.10 % of the side, tip wants 0.03 %, everyone gets 0.03 %; band, root wants 0.37 %, tip 1.7 %, everyone gets 0.37 %.</li>
      <li>Nodes are placed once on the merged list, and that list is used on every station and both sides. Nobody gets a coarser cell than it wished; the cost is about 3 % more nodes. The sharpest nose and the finest band of the wing are everywhere.</li>
    </ul></div>
  </div>
  {figc("merge.png", "Left: the wish lists of three stations of the BWB reference wing (root, mid-span, tip; solid upper side, dashed lower side) on the common scale, and the merged list in black. Right: the merged list applied to the root ring and the tip ring, both drawn at unit chord, with every 30th node pair joined.",
        "The merged list is the lower envelope of all wish lists: the root's band sets the middle, the tip's nose sets the front, the lower band of every station sets the back. On the rings, node i lands at the same place on the root and the tip, which is what makes the cells between stations clean.")}
  <h3 style="font-size:17px">Step 4, before and after: what the one list fixed</h3>
  <p>The first version gave each station its own list; the screen then showed surface quads with a scaled Jacobian down to 0.08: node i drifted along the chord between neighbouring stations (a different nose spacing, band cell or count), and where the stations are squeezed to tens of µm at the tip, a drift of a fraction of a cell shears the quad. Now the size fields of all stations and both sides are put on one grid of arc fraction, the strictest wins at every place, and that one distribution serves every station.</p>
  {figc("union_distribution.png", "Flying wing, training_full 6, level C: the scaled Jacobian of every wing quad (1 = right angles, 0 = flat), per-station distributions against the one distribution, and the histogram of all quads.",
        "With one distribution node i sits at the same arc fraction on every station: the sheared band at station 65 (0.08) is gone and the worst quad is 0.58, the sweep of the wing. The cost is about 3 % more ring nodes and the sharpest nose and finest band of the wing everywhere; the gain is a clean structured surface for the march, and the spanwise envelope (law 2) holds by construction.")}
  <h3>Step 5 · The rings and the tip cap</h3>
  <p>Upper trailing-edge corner → nose → lower trailing-edge corner → across the blunt base; 2 n_side + n_base − 3 unique nodes, the same at every station; n_base = 9 points (8 cells) at C. The base nodes are straight between the two corners. Every node is evaluated on the loft at its (x/c, v).</p>
  {figc("ring.png", "The root ring of the BWB reference wing: node order (left), the nose with the turning per node (middle), and the trailing edge with its 0.1 % c cells and the 8 base cells (right).",
        "One closed curve holds the nose, both sides and the base, so the leading edge is a spacing request in metres and the base needs no block of its own. The turning at the nose nodes is at or below 10°; the two trailing-edge corners turn by about 90° by design and are left out of the check.")}
  <h3 style="font-size:17px">Step 5, the cap</h3>
  <p>Ported from S8: one H patch whose edge is the tip ring node for node (checked to 1e-12 m), xi along the chord from a short nose arc to the base, eta across the thickness, 400 Laplacian sweeps with the edge held, oriented so that i × j points outboard. With one distribution for both sides its cross lines join upper and lower nodes at the same arc fraction and stay upright; with a different distribution per side they slanted across the thin trailing-edge region and the cells collapsed (scaled Jacobian 0.03 on the BWB reference wings at Re 3 × 10⁶).</p>
  {figc("cap.png", "The tip cap of the BWB reference wing (top) and the scaled Jacobian of its cells (bottom), chordwise cell against cell across the thickness.",
        "The cap is a clean patch of upright quads over the whole chord; the only weak cells are the two where the nose arc meets the sides, whose three corners lie on the smooth ring (corner angle 180° minus the ring's turning). They are reported apart and refused only if folded. The real test of the cap is the march off it (Stage 3), where it is a viscous wall facing along the semi-span.")}
  <h3>Step 6 · The thirteen checks, then OUT · the files</h3>
  <p>A build writes a mesh only if every check passes; otherwise it writes <code>refusal.json</code> with the failed checks and their values. A violation is reported per station, never averaged away (<code>stations.csv</code>). The files: <code>surface.npz</code> (the arrays), <code>surface.xyz</code> (Plot3D, opens in ParaView), <code>stations.csv</code>, <code>quality.json</code>, <code>manifest.json</code> with four hashes (wing input, loft surface, mesh code, mesh nodes).</p>
  {checks_table()}
  {cbox("Thirteen checks, each with a number and a limit, written before the results (Stage 0, D4). They are what makes the screen a result and not a hope: a wing that passes has met every rule, and a wing that fails says which.")}
</section>"""
    rules_sec = f"""
<section id="rules">
  <h2>The rules and their sources</h2>
  <p>The first column: level C of the first approach (<code>configs/surface_first.yaml</code>). The New column: the values at VC / C / M / F of the rules built on 7 Nov (<code>configs/surface.yaml</code>), read from <code>laws.py</code> when this page is built. "Law n" is the row of the laws table in the Grand Roadmap. The second table gives the two Re-dependent sizes at the Re levels of the study (and 6 × 10⁴ and 5.5 × 10⁶, the extremes a station can see).</p>
  {rules_table(cfg)}
  <p>The family (C, M, F, FF) is checked in Study 2 below. What the band rule costs: about 200 ring nodes at Re 10⁵, 400 at 3 × 10⁵, 850 at and above 1.5 × 10⁶, against 150 in S8. The chordwise direction holds 35 % of the mesh budget (Stage 0, D1), so this rule is the first thing the chordwise ladder (Grand Roadmap T6) must test; if 20 nodes per bubble is more than the drag needs, the coarse level can be relaxed. The whole ring is in practice at band spacing (first: upper 0–85 % c and lower 60–100 % c, shared through the one distribution), except the nose and the trailing edge, which are finer.</p>
  {chg("The New column is built (7 Nov): <code>configs/surface.yaml</code> holds every value with its anchor level (for example <code>nose_turning_deg: {value: 10.0, at: M}</code>), and <code>laws.py</code> moves it to each level by the family rule; <code>Rules.reason(name)</code> says in one line where each value comes from, and every mesh writes the values and reasons to <code>quality.json</code>. The four levels keep their places on the ladder and change their names: the first C, M, F, FF sit where the new VC, C, M, F sit. The first values stay in <code>configs/surface_first.yaml</code>, which rebuilds the first meshes node for node. The nose is solved at every level and the strictest wins (owner, 7 Nov). Two builder choices went past the decision, both stricter; Mike confirmed both on 8 Nov: the growth limits (ring 1.25, station gaps 1.3 at VC) follow the family rule; the station growth stays 1.2. The upper band is 0–100 % c since 8 Nov (owner); the nose repair belongs to the family (owner, 8 Nov; Study 12). The lower band is 0–100 % c (decision 74, option A). The band-cost sentences above are the first approach's.")}
</section>"""

    study9 = new_screen_section(sn)
    study10 = similarity_section(sim)
    study11 = refine_re_section(rre, uc)
    sf_path = STUDIES / "screen_family_summary.json"
    study12 = family_screen_section(json.loads(sf_path.read_text())) if sf_path.exists() else ""
    studies = f"""
<section id="studies">
  <h2>The studies, with their conclusions</h2>
  <p>Studies 1–7 were run while building the mesher with the first approach (2–3 Nov): they are <strong>first-approach evidence</strong>, on the geometry of before 7 Nov (real size, the old nose rule, the old 20 reference wings, 13 of which were replaced on 7 Nov). Study 4 has two corrections, the second on 7 Nov. Studies 8–11 are <strong>new</strong> (7 Nov): the band count for decision 74 (Study 8, with a plan file, before the build; also on the old reference wings), the new screen of the built rules (Study 9), the similarity check (Study 10) and the refine map at the Re levels (Study 11). Each study says what was done, what each figure shows, and what we conclude. None of them is a flow result: no solver has run on these surfaces.</p>

  <h3>Study 1 · The robustness screen (first approach)</h3>
  <p><strong>What was done.</strong> Every built wing of every type and set ({tot['n_wings']} wings: reference, training_focus, training_full, corner1, corner2) meshed at level C and Re 3 × 10⁵ on the mean chord, and the 20 reference wings at all four Re levels, with the numpy twin of the loft. Pass/fail limits were written before the run (the 13 checks). Failures stay in every count.</p>
  <p><strong>Result.</strong> {tot['total']} builds, {tot['passed']} passed every check, {tot['total'] - tot['passed']} refused, {tot['crashed']} crashed. Largest delivered turning {tot['max_turn']:.2f}° (target 10 ± 0.02), largest chord growth {tot['max_growth']:.3f} (limit 1.25), a nose repair on {tot['repairs']} builds. Lowest wing-quad quality {tot['min_wq']:.2f}, lowest cap quality {tot['min_cq']:.2f}. Build time median {tot['sec_med']:.1f} s, max {tot['sec_max']:.1f} s.</p>
  {scr_tab}
  {figc("screen_C.png", "Every build of the screen: ring nodes against the mean chord, stations against semi-span / mean chord, and build time, per type.",
        "Ring size is set by the local Re of the largest chord, not by the wing's size: the BWB sits at about 600 nodes, the three other types at about 400, whatever the chord. The station count rises with the aspect ratio (semi-span in chords) as the law intends, from about 70 to 130. Build time is 4–8 s for every wing; the mesher is not the bottleneck of the workflow.", DOCS)}
  {figc("screen_dist.png", "Distributions over the screen at Re 3 × 10⁵: ring nodes and stations per type, and the lowest scaled Jacobian of the wing quads and of the cap quads per wing, per type (dashed: the refusal limit 0.05).",
        "The wing quads are good on all types (median 0.82–0.98); the few wings below 0.3 are corner wings with an 85°-swept first panel. The cap quads are the weaker part (median 0.19–0.43): the H patch is squeezed between a thin section and the many chordwise cells. Both are far from the refusal limit; the march will say whether the cap quality matters.")}
  {cbox("The mesher is robust on the sets we have: 0 refusals in 790 builds at level C, so, by the rule of three (Stage 0, D2), the true failure rate on this design space is below about 0.4 % with 95 % confidence, for the surface alone. What the screen does not show: whether the volume march accepts these surfaces, whether 20 nodes per bubble is the right coarse level, and anything about the flow. It was run on the numpy loft; on 8 Nov the pyGeo loft gave the same meshes on the 20 reference wings (Mike's machine).")}
  {chg(f"Done on 7 Nov: the new screen of the built rules on the rebuilt sets (unit mean chord, the nose fix; new hashes) is <a href='#study9'>Study 9</a>: every set at VC and F, the 20 reference wings at all four levels and Re levels; {ok_new:,} of {n_new:,} builds passed.", tag="Updated 7 Nov 2026")}

  <h3>Study 2 · The family ratios (C, M, F; first approach)</h3>
  <p><strong>What was done.</strong> Levels C, M, F of the four reference wings at Re 3 × 10⁵; the ratio of every spacing between levels measured on the built meshes (nose cells at the root and the tip, the trailing-edge cell, the band cell at the root and the tip, the first and last station gap, a base cell), and the counts.</p>
  {figc("family.png", "Left: the nose of the BWB root ring at C, M, F. Middle: the measured ratio of every spacing between levels on the BWB reference wing (dashed: 1.3). Right: ring nodes and stations per level for all four types.",
        "Every spacing refines by 1.30 within 3 %, and the counts (rings and stations) grow by 1.3 per level: the levels are true scaled copies, as Celik's method needs. The two exceptions are whole numbers: the base cells (8, 10, 14, 18: 1.25, 1.4, 1.29) and the gaps of the first panel (12, 16, 21). A first version with the same growth at every level refined only the end spacings and grew the station count by 1.2, not 1.3; the growth must scale too.")}
  {family_table(fam)}
  {cbox("The family rule (law 23) holds on the surface for all four types. The primer asks for 1 %; 3 % is what whole numbers allow and it is reported, not hidden. The same rule, every spacing ÷ 1.3 and the growth g^(1/1.3), must be carried into the march and the boxes in Stage 3.")}
  {chg("The ratios hold whatever level a target is met at: they come from ÷ 1.3 per level. The ratios of the built rules, on all 20 reference wings × 4 Re and all four levels, are in <a href='#study9'>Study 9</a>: the same picture. In Stage 3 the rule goes into the march and the C-H blocks (there are no boxes).")}

  <h3>Study 3 · One distribution per station, or one for the wing (first approach)</h3>
  <p><strong>What was done.</strong> The first screen (per-station distributions) was read for the lowest wing-quad quality; the worst wing (flying wing, training_full 6, 0.08) was rebuilt both ways and the scaled Jacobian of every quad compared (figure in section 5 above). Then the whole screen was rerun with one distribution.</p>
  {cbox("One distribution for the wing: the sheared quads in the tip squeeze go from 0.08 to 0.58, the BWB reference wing from 0.77 to 0.92, and no wing of the sets falls below 0.09 (the 85°-sweep corner wings, a property of those wings). The price is about 3 % more ring nodes and the sharpest nose of the wing at every station. Decision 60.")}

  <h3 id="study4">Study 4 · The nose of the built sections (a Stage 1 finding; a wrong correction on 6 Nov; fixed in Stage 1 on 7 Nov)</h3>
  <p><strong>What was done.</strong> While solving the nose spacing the turning did not fall steadily as the spacing was reduced (section 4). The raw airfoil files of the ten suggested sections were compared with the Stage 1 resampled sections: nose radius from y ≈ √(2 R x) at the first cosine point (x = 2.5 × 10⁻⁴ c) on each side, and a circle through three raw points at the leading edge; for NACA 4415 also the formula (R = 1.1019 t²).</p>
  {figc("nose_radius.png", "The first 1.2 % of the chord of NACA 4415, E387 and MH 104: the raw file points, the built section, circles fitted to the built upper and lower nose, and (NACA 4415) the formula's circle.",
        "First reading (2 Nov): the built nose is not the airfoil's nose. NACA 4415 has one nose of 0.0248 c by formula; the built section shows 0.008 c on the upper side and 0.074 c on the lower side at the leading-edge point. E387: 0.0102 c raw, 0.0028 / 0.035 c built. The round-nosed LA2573A and NACA 25118 are fine. The error lives in the first about 0.1 % of the chord.")}
  {nose_table(nose)}
  {cbox("The likely cause: Stage 1 takes the leading edge at the raw point farthest from the trailing edge and interpolates each side in √x from there; when that point is not exactly the nose apex, the two branches are not √x-symmetric. The mesh follows the loft as built, so the surface mesh is right for the wing we have; the wing's nose is not the airfoil's. It matters for the suction peak at high angle and for any law that reads a nose radius (law 1 measures the turning instead, so it adapts). Open decision 64: fix in Stage 1 (every geometry hash changes) or carry as a stated deviation. Mike decides. (7 Nov: this cause was right; fixed, see below.)", "First reading and open decision (2 Nov)")}
  {chg("The first reading compared two different measures: a circle through three raw points against a one-sided formula on the built section. Measured the same one-sided way, the raw files show nearly the same split: NACA 4415 raw 0.0081 / 0.0736 c against built 0.0080 / 0.0741 c; SD7032 raw 0.0287 / 0.0023 against built 0.0318 / 0.0023. So the split is mostly how a one-sided formula sees a cambered, tilted nose (the nose circle's centre lies on the camber slope, about 11° on NACA 4415), not a fault of the geometry. What may remain: the leading-edge rule can change the shape only inside the first gap between raw points, under 0.025 % c on NACA 4415, about 7 × smaller than the nose cell the mesher delivers on the NACA 4415 reference wings (0.18 % c at C). Decision 64 stays open: re-measure raw and built with one curvature method that the tilt cannot fool, and fix only if a real error remains. A fix changes every geometry hash, so it goes before the pyGeo build --all.", "Correction (6 Nov 2026), withdrawn on 7 Nov: it was wrong", "old")}
  {nose_fixed_block(nc, sim)}

  <h3>Study 5 · The corner set: where the rules stop (first approach)</h3>
  <p><strong>What was done.</strong> The first screen crashed on the smallest BWB corner wing (12 mm tip chord). Its tip section was examined: the trailing-edge thickness floor of 0.5 mm is 4 % of that chord, and the opening of the trailing edge over the aft part of the section makes a bend of about 10° at its start; the band cell there (2 % c at that tip's Re) could not follow it, so the nose solve could never bring the largest turning under 10°.</p>
  {figc("corner_bend.png", "BWB corner wing 0, tip station (chord 12 mm). Left: the section in its true shape, every ring node. Middle: the trailing edge zoomed. The base of this tiny section must be at least 0.5 mm thick (the Stage 1 floor), which is 4 % of its chord, so the section opens out over its last 10 % c: that is the widening, and it is geometry, not a mesh fault. Where the opening starts (88–92 % c, shaded) each surface turns by 11–13° within 4 % of the chord. Right: the cell sizes on the upper side: this station's own wish list (band cell 2 % c at its tiny Re), the curvature cap R × 10° that cuts the list at the bend, and what the wing's shared list delivers (0.25 % c, set by the root).",
        "A 2 % c cell across that bend turns by about 10° in one cell: that is why the first screen could not bring the largest turning under 10° on this wing. The fix: the turning rule now applies along the whole ring from the local curvature radius, not only at the nose, so the station's own list already shrinks at the bend (to about 1.2 % c, 8° per cell). On the finished wing the shared list makes the cells 0.25 % c there and the bend costs 2° per cell. A true kink (a dense step turning more than 1°) would be reported apart as a geometry fault; none was found in the sets. The corner set did its job: it found the limit of the rule and the rule was widened.")}
  {chg("Built 7 Nov: under similarity the trailing edge is 0.2 % c on every wing, so the 0.5 mm floor that made this 12 mm tip 4 % c thick is gone, and with it this bend (the corner1 sets were rebuilt: 32 BWB and 32 cranked, 24 flying-wing and 24 tapered wings, two fewer each: the root-chord corners went with the root chord). The curvature cap stays, and check C3 still runs thicker real trailing edges (about 0.42 % c). The new screen meshed every rebuilt corner wing (Study 9).")}

  <h3>Study 6 · Three passes of the screen: what each one found (first approach)</h3>
  <div class="tbl"><table class="mid"><tr><th>Pass</th><th>Code state</th><th>Refused or crashed</th><th>What it found, and the fix</th></tr>
  <tr><td class='num'>1</td><td>a distribution per station</td><td class='num'>10 of 790</td><td>Tip gap 0.1 % above the asked value (whole numbers of gaps: tolerance 0.8–1.01); the nose solve crashed on the smallest corner wing (the 10° bend: curvature cap along the ring, kinks reported apart); a break 0.9 mm from the root broke the spanwise grid (dense grid per panel); the lowest wing-quad quality 0.08 in the tip squeeze (Study 3).</td></tr>
  <tr><td class='num'>2</td><td>one distribution</td><td class='num'>17 of 790</td><td>Chord growth 1.25–1.26 at NACA 4415 noses, where the two built sides differ most (the lower side follows the upper side's arc fraction): the growth check allows 1 %, as the other delivered-against-asked checks do.</td></tr>
  <tr><td class='num'>3</td><td>growth tolerance</td><td class='num'>0 of 790</td><td>Clean. While drawing the size-field figure for this page the reported nose spacing did not match the delivered cells: the helper that holds a size over a length took the length as the size, so the nose cell was 4 × the asked size (the solve compensated, so the turning was right). Fixed; the nose is now held over four cells of the asked size.</td></tr>
  <tr><td class='num'>4 (final)</td><td>as committed</td><td class='num'>0 of 790</td><td>The numbers on this page. The largest growth fell to 1.21.</td></tr>
  </table></div>
  {cbox("Four passes, each on the whole set, were needed to get from the first working mesher to the one that passes every wing. The earlier passes are development evidence, not results; the fourth, on the committed code, is the result. The corner and full-space sets are where every failure appeared, as Stage 0 said they would.")}
  <h3>Study 7 · Where to refine, per wing: the refine map (3 Nov 2026, run again from −5° on 7 Nov; first approach's band cell, old reference wings)</h3>
  <p><strong>What was done.</strong> The transition band is generic (first: upper 0–85 % c, lower 60–100 % c, every wing). To see what a per-wing band would be, the Stage 1 flow dataset (2-D XFOIL section tables, read through the flow-map engine as strips along the semi-span with one induced angle) was read out for each of the 20 reference wings on a grid of Mach 0.03–0.20 × root angle −5…12° at sea level, 3 strips per panel (the grid started at −2° until 7 Nov): where the flow turns turbulent, where the bubbles sit and where it separates, on both surfaces. The envelope over the conditions one mesh must serve (Mach 0.03–0.13, −5° to 8° since 7 Nov; 0–8° before), plus a margin of 10 % c around the transition point, is the band that wing would need. Interactive page with every wing, slider for Mach, angle, ranges and margin: <a href="https://claude.ai/artifact/KXra2FWoVEFYLHCoafhgye">Where To Refine</a> (<code>docs/REFINE_MAP.html</code>; code <code>cfdauto/mesh/refine_map.py</code>).</p>
  {figc("refine_map.png", "BWB reference wing 0, half wing from above, root on the left, leading edge up. Left: both surfaces at Mach 0.08 and 4° at the root, one bar per strip: laminar (blue), the bubble (amber), turbulent (grey), the transition point (line). Right: the band this wing needs over Mach 0.03–0.13 and −5° to 8° with a 10 % c margin (tan), against the generic band (dashed).",
        "The per-wing band is not smaller than the generic one; it sits elsewhere, and from −5° it is wider. Over the 20 reference wings and −5° to 8° its band-cell cost is +8 % to +46 % of the generic band's (median +34 %); over 0–8° (first data, 3 Nov) it was −15 % to +20 % (median about +5 %). The generic band is wrong in place on every wing: at low angle the upper surface stays laminar beyond 85 % c on the outboard panels (missed by 10.5–15 % c per wing; up to 15 % c over 0–8° too), and the lower surface transitions near the leading edge, where the generic band starts at 60 % c: over −5° to 8° that stretch is missed by the full 60 % c on all 20 wings (52–60 % c over 0–8°, on washed-out panels). These costs count each side on its own; the built ring shares one node list for both sides, so a lower band from the leading edge costs no cells there (Study 8). The shortest root bubbles the dataset predicts (1.4–10.7 % c) are shorter than the band-cell table assumes at the root's Re (5–14 % c) on all 20 wings, so the 20-cells-per-bubble rule is not met at the root by either band; the negative angles do not change this. All of this is 2-D XFOIL in calm air with one induced angle for the whole wing; no crossflow transition, no 3-D relief, no tip effects. The per-wing band is a candidate (decision 65), not a rule, until a 3-D transition check says the strips are right; what would make the map better (AVL for the local angle, NeuralFoil for the 2-D answer) is decision 66.")}
  {chg("Done on 7 Nov: the map now runs from −5° (the section tables reach −10°) and its envelope is −5° to 8°; the numbers above are the new ones, with the first ones (0–8°) beside them. The generic lower band (60–100 % c) was set for positive angles; the mesh now has its lower band from the leading edge (decision 74, option A, decided and built on 7 Nov), at no cost in cells (Study 8). The map and its generic band still show the first approach (lower band 60–100 % c, band cell = bubble length / 20 at C) on the old 20 reference wings at real size. Done on 7 Nov: under similarity the map is read per Re level on the mean chord at Mach 0.1, on the new reference wings and the rebuilt section tables: <a href='#study11'>Study 11</a>.", tag="Updated 7 Nov 2026")}

  <h3 id="study8">Study 8 · The band count for negative angles (decision 74, 7 Nov 2026)</h3>
  <p><strong>What was done.</strong> New data, not first-approach evidence, run on 7 Nov before the new rules were built: the code of that morning with the planned rules of the new approach at the coarsest level VC, read from a plan file (<code>configs/surface_plan_VC.yaml</code>: the lighter band, tip gap 2 × s0, station gap 0.25 c at M), on the old 20 reference wings at real size. First, the refine map run down to −5° (Study 7) was read for the lower side: per wing type, where it turns turbulent and where its bubbles sit at −5°, −2° and 0°, over every strip of the 5 wings and Mach 0.03–0.13, and how far that lies in front of the generic lower band (60 % c). Then the count: the 20 reference wings × 4 Re levels on the mean chord (10⁵, 3 × 10⁵, 1.5 × 10⁶, 3 × 10⁶: the levels until 8 Nov), built at VC once with the lower band of option B (60–100 % c) and once with option A (0–100 % c): {bc['summary']['builds']} builds, about {bc['summary']['seconds_median']:.0f} s each. Only the band changes, so the stations and the wall layers are the same, and the wing-block cells scale with the ring nodes. A finer level has every VC spacing ÷ 1.3 per level, so the ratio A / B at F equals the ratio at VC up to whole-number rounding; two wings were also built at F to check it ({'the same mesh on both' if all(r['same_mesh'] for r in bc['f_check']) else 'see the data'}). Option A′, a per-wing lower band from the refine map (−5° to 8°, 10 % c margin), needs no build: one node list serves the whole wing, so its band is the union over the strips, and that union starts at 0 % c on {sum(1 for r in bc['refine_map']['a_prime'] if r['band_lower'][0] < 1e-9)} of the 20 wings, so A′ = A. Code: <code>scripts/band_count.py</code>; data: <code>data/studies/band_count.json</code>.</p>
  <p><strong>Result, the lower side (2-D strips).</strong> At −5° the lower side turns turbulent close to the nose on every type, and its transition or bubble sits in front of 60 % c on every strip that has an answer. At −2° that holds on 81–100 % of the strips, and at 0° still on 51–83 %: the generic lower band is in the wrong place already at 0°. The cranked and tapered wings have a lower bubble near the nose on almost every strip at −5°. On the BWBs and flying wings many outboard strips (MH 61, MH 45, at local angles −6° to −11°) have no answer at −5°, so their numbers rest on the other strips.</p>
  {band_count_tables(bc)}
  {figc("band_count.png", "Left: where the lower side turns turbulent, per wing type and root angle (every strip of the 5 reference wings with an answer, Mach 0.03–0.13), against the generic lower band (60–100 % c); at the right of each row, the share of strips whose transition or bubble lies in front of 60 % c. Middle: the cell size along the lower side of the BWB root ring at VC, Re 3 × 10⁵: what option B delivers (line), what option A delivers (circles), and the lower side's own wish list with B (dashed). Right: ring nodes with A against ring nodes with B, all 80 pairs.",
        "The lower band of option B is in the wrong place at negative angles (and on many strips already at 0°), but option A costs nothing: the ring is the same, node for node, on every pair. The lower side never uses its own wish list: both sides share one node list (decision 60, needed by the tip cap), so at every place the finer side wins, and the upper band (0–85 % c) already puts band cells on the front 85 % of the lower side; the lower band covers the back. With A the band check also covers the front of the lower side, and it passes, because the cells are already there.")}
  {cbox(f"Option A costs no cells: ratio A / B = {bc['summary']['ratio']['median']:.3f} (median) and {bc['summary']['ratio']['max']:.3f} (max) over the 80 pairs, the same at F, so the fine level stays at about {bc['summary']['F_median_A'] / 1e6:.1f} M cells (median, wing blocks) with A. The earlier “1.5 × longer band” (125 → 185 % of the chord) counted each side on its own; the built ring takes the finer side at every place. So the cells no longer decide between A and B. A keeps transition runs (SU2 LM) from −5° at no mesh cost. B only saves the LM runs below 0°, and its lower band does not match where the lower side turns turbulent, even at 0°. Limits: 2-D XFOIL strips in calm air with one induced angle; no answer on 42 % (BWB) and 30 % (flying wing) of the strips at −5°; planned rules at VC from a plan file, not the built config; the old reference wings. Mike chose A on 7 Nov (decision 74); it is built (<code>configs/surface.yaml</code>: lower band 0–100 % c). The 10.9 M is the 6 Nov estimate; the screen of the built rules counts {fcell['median'] / 1e6:.1f} M (Study 9).")}
  {study9}
  {study10}
  {study11}
  {study12}
</section>"""
    assumptions = """
<section id="assumptions">
  <h2>Assumptions</h2>
  <div class="tbl"><table class="wide"><tr><th>#</th><th>Assumption</th><th>Why</th><th>What it leaves out / risk</th></tr>
  <tr><td class='num'>A1</td><td>The loft is the geometry; the numpy twin of the pyGeo loft gives the same surface.</td><td>Stage 1 tests compare the two backends: within 10⁻⁶ chord on the 7 published wings (passed on Mike's machine, 8 Nov). There, on the pyGeo loft, the 20 reference wings × 4 Re: at VC (old levels) every count and every check value equals the numpy screen's (within 6 × 10⁻¹⁰); at the new levels, VC and F, the same ring nodes and stations on 80 of 80 each.</td><td>Holds on the reference wings (the nodes differ by round-off, so their hashes differ). The full sets were not meshed on pyGeo.</td></tr>
  <tr><td class='num'>A2</td><td>Bubble lengths from the Stage 1 XFOIL table (2-D, calm air, N_crit 9), constant at 0.05 c above Re 10⁶ (new: 0.10 c from local Re 4 × 10⁵, decision 72).</td><td>The only source we have for where the band must be fine.</td><td>3-D, sweep and roughness move bubbles; "under 0.05 c" is taken as 0.05 c.</td></tr>
  <tr><td class='num'>A3</td><td>20 nodes across a bubble, at level C (new: at F).</td><td>Ansys CFX guide for the γ-Re_θ model.</td><td>One vendor source, one model; may be more than the drag needs; the T6 ladder decides.</td></tr>
  <tr><td class='num'>A4</td><td>The tip first cell s0 from a turbulent flat plate at the tip Re, y⁺ = 1.</td><td>Standard estimate; the volume mesh will use the same law per station.</td><td>Checked only after the first solve (y⁺ audit).</td></tr>
  <tr><td class='num'>A5</td><td>Station gap 0.2 × local chord, at least 12 per panel, growth 1.2; largest ring cell 2 % c (new: gap 0.25 × chord at M; tip gap 2 × s0).</td><td>Starting values.</td><td>No ladder yet; the spanwise ladder (laws 8, 9) will move them.</td></tr>
  <tr><td class='num'>A6</td><td>The turning rule (10° per cell) applies along the whole ring from the local curvature.</td><td>Needed on the corner set; the same number as at the nose.</td><td>The curvature is read from the dense polyline (smoothed over 5 steps).</td></tr>
  <tr><td class='num'>A7</td><td>One distribution for the wing: the sharpest nose and the finest band everywhere.</td><td>Clean quads between stations; simpler.</td><td>About 3 % more nodes; the root gets the tip's nose cell.</td></tr>
  <tr><td class='num'>A8</td><td>Checks with 1 % tolerance on delivered-against-asked spacings; tip gap 0.8–1.01 × s0.</td><td>Whole numbers of cells and gaps.</td><td>A real violation is far larger than 1 % (1.55 and 7.4 were seen and fixed).</td></tr>
  <tr><td class='num'>A9</td><td>The surface is built per Re level; the name carries the Re (new: per Re level of the unit-chord wing).</td><td>The tip gap and the band cell depend on Re.</td><td>More meshes to manage; seconds each.</td></tr>
  <tr><td class='num'>A10</td><td>The flat tip with sharp edges (Stage 1 geometry) and its H cap.</td><td>Hoerner: sharp side edges beat rounded tips for induced drag; the baseline of the roadmap.</td><td>The rounded-tip sensitivity (T8) is still to be run.</td></tr>
  <tr><td class='num'>A11</td><td><strong>New (built 7 Nov):</strong> every wing at unit mean chord; the Re on the mean chord an input; Mach 0.1 with Prandtl–Glauert; trailing edge 0.2 % c (similarity).</td><td>At low Mach, shape, Re and angle fix the flow (dimensional analysis); 5 × fewer solves.</td><td>Re does not carry roughness or air turbulence; small real wings have thicker trailing edges (check C3); if check C2 fails, Mach becomes an input.</td></tr>
  <tr><td class='num'>A12</td><td><strong>New (built 7 Nov):</strong> hard minimums at VC, accuracy targets at M, transition targets at F.</td><td>DPW defines its spacings on the medium grid; the transition model needs its cells where it runs (F).</td><td>VC and C do not resolve bubbles (9.1 and 11.8 cells): their transition results are not to be trusted; the LM error bar needs M, F (and FF on a few wings).</td></tr>
  <tr><td class='num'>A13</td><td><strong>New:</strong> the cells of a mesh are estimated as surface × wall layers: one layer count per block (the largest over the stations), the layers reaching 2 local chords, the wall growth of the level.</td><td>The volume mesh is Stage 3; this is the count the cost decisions need now.</td><td>The C-H wake lines (+30–60 %, rough) and the outboard blocks are not in it; the real reach and growth come with the march.</td></tr>
  </table></div>
</section>"""

    findings = f"""
<section id="findings">
  <h2>What was found and decided</h2>
  <p>All logged in <code>CFD_Automation/OPEN_DECISIONS.md</code> (56–66; the new approach 67–76) and explained in <code>Stage_2_surface_mesh/decisions/surface_rules.md</code>.</p>
  <div class="tbl"><table class="wide"><tr><th>#</th><th>Decision or finding</th><th>Why</th><th>Open part</th></tr>
  <tr><td class='num'>56</td><td>Cells per bubble = 20 at level C.</td><td>The Stage 1 rule had no source; the Ansys CFX transition-model guide asks for at least 20.</td><td>Whether the coarse level needs the full 20 (T6). Costs 400–850 ring nodes against S8's 150. New (71, built 7 Nov): 20 at F, 9.1 at VC.</td></tr>
  <tr><td class='num'>57</td><td>Wall-normal growth 1.1 for a transition model (Stage 3).</td><td>The same guide: 1.2 already moves transition upstream; Stage 0 says 1.25.</td><td>Decide in Stage 3; it changes the layer count, not the surface. New (71): growth 1.25 at VC is 1.107 at F, just above the 1.1 (1.23 at VC would give exactly 1.1).</td></tr>
  <tr><td class='num'>58</td><td>The upper band starts at the leading edge on every wing.</td><td>One rule instead of a sweep threshold; costs about 10 % of the chord.</td><td>—</td></tr>
  <tr><td class='num'>59</td><td>One surface per wing and Re level; the name carries the Re.</td><td>The tip gap and the band cell depend on Re; seconds each.</td><td>—</td></tr>
  <tr><td class='num'>60</td><td>Both sides and all stations share one node distribution.</td><td>The cap cells collapsed (0.03) and the quads between tip stations sheared (0.08) with separate distributions.</td><td>—</td></tr>
  <tr><td class='num'>61</td><td>Base cells 8, 10, 14, 18 per level.</td><td>Even counts keep the cap's nose arc centred.</td><td>Ratios 1.25, 1.4, 1.29 instead of 1.3: the one spacing that does not follow r exactly.</td></tr>
  <tr><td class='num'>62</td><td>Station gap 0.2 × chord, 12 per panel, growth 1.2.</td><td>Starting values.</td><td>The spanwise ladder. New (72, built 7 Nov): 0.25 × chord at M; the growth 1.2 kept.</td></tr>
  <tr><td class='num'>63</td><td>Largest cell 2 % c outside the bands.</td><td>Our choice.</td><td>Hardly applies: the bands cover most of the ring.</td></tr>
  <tr><td class='num'>64</td><td><strong>Stage 1 finding: the built sections' nose is not round.</strong> NACA 4415: 0.0248 c by formula, built 0.008 / 0.074 c.</td><td>Found by the nose solve; measured on the ten suggested airfoils; measured again on 7 Nov with one curvature method: real (a 0.18 % c cell turned 9.47° built against 4.31° true on NACA 4415).</td><td><strong>Decided 7 Nov (Mike): fixed in Stage 1</strong> (apex leading edge, one cubic spline, 201 points per side, a nose gate); built, sets rebuilt (Study 4). The pyGeo build ran on 8 Nov: 722 of 722.</td></tr>
  <tr><td class='num'>65</td><td><strong>Per-wing transition band from the flow dataset</strong> (candidate): the envelope of bubbles, transition ± margin and separation over the conditions one mesh serves, per strip and side.</td><td>Study 7, the refine map (first approach): the generic band is mis-placed on washed-out panels (lower surface near the leading edge, upper surface beyond 85 % c at low angle); the cost is about the same. Study 11 (7 Nov, the Re levels): the lower band 0–100 % c holds every strip; the upper band as written (0–85 % c) holds only 0–49 % of the strips at Re 10⁵ and 3 × 10⁵.</td><td>As built the upper side has band-size cells to the trailing edge; the upper band is written 0–100 % c since 8 Nov (owner; 2 more ring nodes at F on 42 of 80 reference builds). Keep the generic band or switch after a 3-D transition check (γ-Re_θ in SU2 on a few wings). Not a rule yet.</td></tr>
  <tr><td class='num'>66</td><td><strong>Upgrade the flow dataset with AVL and NeuralFoil</strong> (proposal): AVL for the local angle per strip (sweep, taper, twist), NeuralFoil for the 2-D answer per strip (milliseconds, exact blended section, transition, boundary-layer shape factor at 64 points per surface).</td><td>Today one induced angle serves the whole wing, and the tables blend the parents' answers between sections.</td><td>Build the quasi-3D loop as a flow-map method, check it against the tables on a sample and against a few 3-D runs; neither adds 3-D transition physics. Then revisit 65.</td></tr>
  <tr><td class='num'>67</td><td><strong>Transition must be captured, with ADflow and SU2</strong> (owner, 4 Nov).</td><td>Laminar runs and bubbles: SA overpredicts the profile drag by a median +62 % (Stage 1).</td><td>Which solver does what (76).</td></tr>
  <tr><td class='num'>68</td><td><strong>Mach toward 0.5, no supersonic flow</strong> (owner, 4 Nov).</td><td>Faster UAVs.</td><td>Core Mach ≤ 0.2 now; 0.3–0.5 later with a fast-UAV family (pending).</td></tr>
  <tr><td class='num'>69</td><td><strong>Angles −5° to post-stall</strong>, plus a separate post-stall study (owner, 6 Nov).</td><td>The whole polar, both signs.</td><td>The lower band (74); steady RANS up to stall onset.</td></tr>
  <tr><td class='num'>70</td><td><strong>Similarity</strong> (owner, 6 Nov): unit mean chord, Re an input, Mach 0.1 with Prandtl–Glauert, trailing edge 0.2 % c, root chord out (18 → 17).</td><td>About 5 × fewer solves (8,000, not 42,000); every shape at all 4 Re levels.</td><td><strong>Built in Stage 1 on 7 Nov</strong>: sets rebuilt (722 of 722), 13 of 20 reference wings new; checked in Stage 2 (Study 10); Re levels kept (10⁵ is a margin, Mike, 7 Nov). Checks C1–C4 still to run with the solver.</td></tr>
  <tr><td class='num'>71</td><td><strong>Levels VC, C, M, F</strong> (owner, 6 Nov): hard minimums at VC, accuracy targets at M, transition targets at F; VC on the desktop, C, M, F on the HPC.</td><td>Each target met where it is needed.</td><td><strong>Built 7 Nov</strong>, screened (Study 9: F {sn['reference']['F']['cells_est']['median'] / 1e6:.1f} M cells median). The nose solved at every level, the strictest wins (owner, 7 Nov; the first build solved it at VC and F, and M needed a repair on the flying wings). Two builder choices, both stricter, confirmed by Mike on 8 Nov: the growth limits follow the family rule; the station growth kept at 1.2.</td></tr>
  <tr><td class='num'>72</td><td><strong>Lighter rules</strong> (owner, 6 Nov): bubble length floor 0.10 c from local Re 4 × 10⁵ (band cell 0.5 % c at F); tip gap 2 × s0; station gap 0.25 × chord at M.</td><td>F median 10.9 M instead of 15.2 M with the band alone (first estimate, 6 Nov; its wall-layer rule not recorded).</td><td><strong>Built 7 Nov.</strong> The shortest high-Re root bubbles get about 3 cells: fine for SA, not for LM (3-D check).</td></tr>
  <tr><td class='num'>73</td><td><strong>One matched C-H volume mesh for ADflow and SU2</strong> (owner, 6 Nov), instead of the overset wake box and tube.</td><td>SU2 has no overset; one family, one error bar.</td><td>Stage 3: open-line march, wake lines (about +45 % cells, rough), tip vortex in the outboard blocks.</td></tr>
  <tr><td class='num'>74</td><td><strong>Lower band at negative angles: from the leading edge</strong> (option A, decided by Mike on 7 Nov; built).</td><td>At −5° the lower side becomes the suction side: its transition sits at a median of 1–15 % c per type (2-D strips), in front of 60 % c on every strip with an answer.</td><td>No cost: option A gave the same ring as option B on all 20 reference wings × 4 Re (ratio 1.000, Study 8), because both sides share one node list. —</td></tr>
  <tr><td class='num'>75</td><td><strong>Nose (64), "corrected"</strong> (6 Nov): the first reading was called overstated.</td><td>Measured the same one-sided way, the raw files showed nearly the same split.</td><td><strong>Superseded (7 Nov): the correction was wrong.</strong> It compared built and raw only at the raw points, where they agree by construction; the defect sat between them. See 64 and Study 4.</td></tr>
  <tr><td class='num'>76</td><td><strong>Solver split</strong> (proposal, pending): ADflow SA for the mesh studies and the fully turbulent data; SU2 SST + LM on about 20 % of the wings.</td><td>ADflow is fast and robust; SU2 has transition models.</td><td>An ADflow against SU2 SA code-to-code check; SU2 cost per solve at full size.</td></tr>
  </table></div>
</section>"""

    open_sec = f"""
<section id="open">
  <h2>Open, weak points, to do, and is it finished?</h2>
  <div class="three">
    <div class="box good"><h3>Finished</h3><div class="big">both approaches built and screened</div><p>The first approach (2–3 Nov): the mesher, its rules, its checks, the screen, the family rule, 14 tests then. The new approach (7 Nov): levels VC, C, M, F with anchored targets, the lighter rules, the lower band from the leading edge, in the code; the nose fix and similarity in Stage 1; the new screen ({ok_new:,} of {n_new:,} passed);{done_f} {N_TESTS} tests now (6 for the refine map by Re level, 2 for the family nose); this page and the decisions.</p></div>
    {not_done_box or '''<div class="box verdict"><h3>Not finished</h3><div class="big">the family screen, the close</div><p>Every mesh here is on the numpy loft; on Mike's machine (8 Nov) the pyGeo loft gave the same meshes as the numpy loft (VC and F: the same ring nodes and stations on 80 of 80 each; VC: every check value within 6 × 10⁻¹⁰) on the 20 reference wings. Both builder choices were confirmed and the upper band decided (8 Nov); the family screen (Study 12) is to run. Then Stage 2 closes and Stage 3 starts.</p></div>'''}
    <div class="box bad"><h3>Not known</h3><div class="big">anything about the flow</div><p>No solve has been run. Whether the surface gives a good C-H volume mesh and a converged run is Stage 3's first result. The cell counts are estimates (surface × wall layers, no wake lines) until a C-H wing is built and counted.</p></div>
  </div>
  <h3>Weak points, said plainly</h3>
  <ul>
    <li><strong>Numpy loft here; pyGeo checked on the reference wings only.</strong> Every mesh on this page was built on the numpy twin of the loft. On Mike's machine (8 Nov) the 20 reference wings on the pyGeo loft gave the same meshes as the numpy loft (VC and F: the same ring nodes and stations on 80 of 80 each; VC: every check value within 6 × 10⁻¹⁰). The full sets were not meshed on pyGeo.</li>
    <li><strong>No solve yet.</strong> Nothing here shows that the surface gives a good volume mesh or a converged run.</li>
    <li><strong>The cap quads come close to the limit.</strong> {f"Lowest {cap_s}, against the refusal limit 0.05 (every set at every level, Study 12)." if sf else f"Lowest {vcf['cap_quads_J']['min']:.3f} at VC and {ff['cap_quads_J']['min']:.3f} at F, against the refusal limit 0.05 (Study 9)."} Similarity made some caps worse: the old trailing-edge floor had given small tips a thicker base (Study 10). The march will say whether this matters.</li>
    <li><strong>The stations are 17 % more than the plan.</strong> The decided station growth (1.2) and gaps per panel (12 at M) give 7–14 more stations than the plan file's 1.25 and 7 gaps per panel, so about 17 % more cells than the plan's rules would give. If the plan file's values were meant, they need a decision.</li>
    <li><strong>The cell count is an estimate, and it hangs on the wall-layer rule.</strong> Two counts exist: the first estimate (6 Nov: F 10.9 M; its wall-layer rule not recorded; the first-approach reference wings) and this one ({"Study 12" if sf else "Study 9"}: F {fcell['median'] / 1e6:.2f} M median on the reference wings; one layer count per block, 2 chords deep, growth 1.25 at VC by the family rule, s0 from y⁺ per station). The pages use this one because it can be redone. Both leave out the C-H wake lines (+30–60 %, rough) and the outboard blocks. Stage 3 sets the real wall-layer rule.</li>
    <li><strong>The coarse levels get a finer nose than they ask.</strong> The nose is solved at every level and the strictest wins (owner, 7 Nov), so VC, C and M take the nose of a finer level where it is stricter (VC {nt['VC']['min']:.1f}–{nt['VC']['max']:.1f}° against 16.9°), and a build pays up to four solves per station. This keeps the family rule exact; the first build (VC and F only) needed a repair at M on the flying wings, and that is gone (Study 9).</li>
    <li><strong>The coarse levels do not resolve transition.</strong> VC and C have 9.1 and 11.8 cells per bubble: transition results there must not be trusted. The LM error bar needs M and F.</li>
    <li><strong>The band rule rests on one source</strong> (one vendor guide, one model), and the lighter band gives the shortest high-Re root bubbles (about 1.5 % c) only about 3 cells: fine for SA, wrong for LM.</li>
    <li><strong>Two studies read the flow at real size.</strong> The first refine map (Study 7) and the band count (Study 8) read the flow dataset per flight speed at real size; the refine map at the Re levels (Study 11) replaces Study 7 on the new reference wings.</li>
    <li><strong>The upper band written 0–85 % c missed the upper transition at low Re</strong> (Study 11: 0–49 % of the strips fit at Re 10⁵ and 3 × 10⁵). {band_s or "Fixed on 8 Nov: written 0–100 % c (owner); the built mesh already had band-size cells there (one node list), so the counts hardly move (Study 12)."}</li>
    <li><strong>No XFOIL answer on many tailless strips at −5°</strong> (up to 46 % BWB, 43 % flying wing): the band there rests on the other angles.</li>
    <li><strong>Studies 1–8 used the old 20 reference shapes</strong>, 13 of which were replaced on 7 Nov; their numbers are for those shapes (Study 10 shows the size alone changes no ring).</li>
    <li><strong>Starting values without a ladder:</strong> the station gap, the 12 per panel, the tip gap, the 2 % c cap, the 10° nose angle.</li>
  </ul>
  <h3>To do, in order</h3>
  <ol>
    <li><s>Nose re-measure (64, Stage 1)</s> <span class="flag ok">done 7 Nov: real; fixed in Stage 1</span></li>
    <li><s>Similarity in the generator (Stage 1 code)</s> <span class="flag ok">done 7 Nov: sets rebuilt, 722 of 722</span></li>
    <li><s>The lower band (74)</s> <span class="flag ok">done 7 Nov: option A, from the leading edge</span></li>
    <li><s>Stage 2 code, the new rules (71, 72)</s> <span class="flag ok">done 7 Nov</span></li>
    <li><s>New screen</s> <span class="flag ok">done 7 Nov: Study 9</span></li>
    <li><s>The refine map at the Re levels</s> <span class="flag ok">done 7 Nov: Study 11</span></li>
    <li><s>The nose at M (owner point 2)</s> <span class="flag ok">done 7 Nov: solved at every level, the strictest wins</span></li>
    <li><s>Mike: confirm or change the two builder choices left, and the upper band</s> — done 8 Nov: both builder choices confirmed (the growth limits by the family rule; the station growth 1.2 with at least 12 gaps per panel at M); the upper band written 0–100 % c; the nose repair belongs to the family (Study 12).</li>
    <li><strong>pyGeo run (Mike's machine): done on 8 Nov.</strong> pyGeo tests 24 of 24, Stage 1 tests 204 (1 skipped), <code>build --all</code> 722 of 722 (manifests pushed), Stage 2 tests 41; the 20 reference wings on the pyGeo loft gave the same meshes as the numpy loft (VC and F: the same ring nodes and stations on 80 of 80 each; VC: every check value within 6 × 10⁻¹⁰) (record: <code>data/studies/screen_VC_pygeo_oldlevels.json</code>; the new-level runs as printouts). Stage 1 then fixed its label rules (decision 79, 8 Nov): every wing's input hash changed, its surface did not (the same surface hash on all 722), so every mesh and screen here stands; re-meshed spot check: 5 builds, the same node hashes.</li>
    <li><strong>Close Stage 2:</strong> the final page, summary and handover; notify.</li>
    <li><strong>Stage 3:</strong> the matched C-H volume mesh on one wing first (open-line march, wake lines to the far field, outboard blocks and the tip vortex, far field 80 c; CGNS for ADflow, a converter to .su2 for SU2), count its cells, then the first solves.</li>
    <li><strong>Ladders after the first solves:</strong> chordwise (T6: cells per bubble, the band), spanwise (station gap, 12 per panel, tip gap), the nose angle (12 / 10 / 8 / 6°).</li>
    <li><strong>Decide 65 and 66</strong> (the per-wing band, the AVL + NeuralFoil upgrade) after the first 3-D transition runs (SU2 LM on the BWB centre body first), with the flow dataset per Re level at unit mean chord.</li>
    <li>Open from Stage 0 still: the grid share, the pitching-moment budget, the iteration share.</li>
  </ol>
</section>"""

    handover = """
<section id="handover">
  <h2>Handover to Stage 3 (volume mesh, CGNS)</h2>
  <p>What Stage 3 gets from this stage, and what it must build. The first plan (overset) is kept for the record; the new plan (one matched C-H mesh, decided 6 Nov, not built) replaces it.</p>
  <ul>
    <li><strong>Input per mesh:</strong> <code>surface.npz</code> with <code>wing (n_ring, n_span, 3)</code> ring index first, root to tip; <code>cap (n_chord, n_base, 3)</code> with i × j outboard; <code>u</code> (x/c of every node, NaN on the base), <code>y</code>, <code>v</code> per station; <code>stations.csv</code> with the local Re and chord per station; <code>quality.json</code> with <code>s0_tip_m</code>, <code>re_tip</code>, <code>mean_chord_m</code>.</li>
    <li><strong>The march (recipe R-V):</strong> first cell s0 per station from the local Re and y⁺ = 1 (law 13; <code>laws.first_cell_c</code>); growth ≤ 1.25 in the boundary layer; ≥ 30 cells across the boundary layer; reach about 2 chords; cap first cell = tip s0. New (built 7 Nov): y⁺ ≤ 1 and growth 1.25 are hard minimums at VC, so F gets y⁺ about 0.46 and growth 1.107, just above the 1.1 a transition model asks for (1.23 at VC would give exactly 1.1; decision 57); the last station gap at the tip is now 2 × s0, so the cap's first cell must be chosen against that gap. The cell estimate of Study 9 assumes this march (one layer count per block, 2 chords deep).</li>
    <li><strong>The family:</strong> every spacing ÷ 1.3 per level and the growth g^(1/1.3), as on the surface, so the volume levels are true scaled copies; base cells 8 / 10 / 14 / 18 (new names: VC, C, M, F).</li>
    <li><strong>First plan (replaced):</strong> overset boxes (R-V.6): background 0.03 c, wake box 0.0075 c to 2 c then to 10 c, tube 15–20 cells across the core from 2 c behind the tip, far field 80 c (T2 decides); overset export and the overlap gate (M3).</li>
    <li><strong>New plan: one matched C-H mesh for ADflow and SU2.</strong> The C block wraps the ring (the nose stays a spacing request inside it, no collar); wake lines from the trailing-edge corners and the base to the far field (80 c), fine near the trailing edge (the first plan's 0.0075 c wake spacing is the starting value); the stations go on past the tip into outboard H blocks, growing from the tip gap; the tip vortex is resolved there by clustering along its path (no tube); the cap is the wall of the first outboard block. Structured CGNS for ADflow; a converter to unstructured hexes (.su2) for SU2. Rough cost: +30–60 % cells on the wing blocks, to be counted on the first wing.</li>
    <li><strong>Where the march will be tested first:</strong> the tip squeeze (many gaps on the last panel, down to 2 × s0), the caps whose quads come closest to the limit (Study 9), the corner wings, and (new) the open-line march at the trailing edge.</li>
    <li><strong>What the meshes are now:</strong> the rebuilt sets at unit mean chord, one surface per wing, level and Re level, named <code>mesh_&lt;level&gt;_&lt;hash8&gt;_re&lt;Re&gt;</code> with the levels VC, C, M, F; the screen's counts are in <code>data/studies/screen_VC.json</code>, <code>screen_F.json</code>, <code>screen_reference_new.json</code>.</li>
  </ul>
</section>"""

    files = f"""
<section id="files">
  <h2>Files and commands</h2>
  <pre>pip install -e CFD_Automation
cd CFD_Automation/Stage_2_surface_mesh
python -m cfdauto.mesh --type bwb --set reference --index 0 --level VC --re 3e5   # one mesh (levels VC, C, M, F)
python -m cfdauto.mesh --type bwb --set reference --index 0 --level C --re 3e5 \\
       --config configs/surface_first.yaml                 # the same wing, first approach
python -m pytest                       # 35 tests (test_family builds levels of the BWB: slow)
python scripts/screen.py --level VC    # every built wing at VC (also --level F; --sets reference for C, M);
                                       # --resume parts.jsonl goes on after a stop (data/meshes/run_screen.sh)
python scripts/screen_study.py         # Study 9: merge the parts, the study files, docs/page/screen_new_*.png
python scripts/similarity_check.py     # Study 10 (and --code &lt;CFD_Automation at 9472830c&gt; --tag similarity_only)
python scripts/built_figures.py        # docs/page/nose_fixed.png, similarity_check.png
python scripts/change_figures.py; python scripts/make_refine_page.py; python scripts/make_stage2_page.py
python scripts/page_to_markdown.py; python scripts/make_summary_page.py
# the first-approach pictures and data, exactly as drawn (a checkout of commit 7bcb7067 as --code):
python scripts/page_figures.py --code &lt;old&gt;/CFD_Automation; python scripts/make_figures.py --code &lt;old&gt;/CFD_Automation
python scripts/family_check.py --code &lt;old&gt;/CFD_Automation   # data/studies/family_ratios.json
python scripts/refine_map_data.py      # the refine map data (first approach's band rule)
python scripts/band_count.py           # Study 8: the band count (decision 74), about 10 min
python scripts/refine_map_re.py        # Study 11: the refine map at the Re levels (about 10 s; --built about 5 min)</pre>
  <div class="tbl"><table class="mid"><tr><th>Where</th><th>What</th></tr>
  <tr><td class='what'><code>cfdauto/mesh/</code></td><td><code>laws.py</code> (one function per rule), <code>spacing.py</code> (the spacing tool), <code>ring.py</code> (section, size fields, nose solve, one distribution, rings), <code>stations.py</code>, <code>cap.py</code>, <code>checks.py</code>, <code>surface.py</code> (the build, the checks, the files), <code>figures.py</code>, <code>refine_map.py</code> (the per-wing band from the flow dataset), <code>__main__.py</code></td></tr>
  <tr><td class='what'><code>Stage_2_surface_mesh/</code></td><td><code>configs/surface.yaml</code>, <code>decisions/surface_rules.md</code>, <code>decisions/STAGE2_STATUS.md</code>, <code>docs/</code> (this page, the refine map <code>REFINE_MAP.html</code>, the executive summary <code>EXECUTIVE_SUMMARY.md</code> / <code>.html</code>, pictures), <code>tests/mesh/</code>, <code>scripts/</code>, <code>data/studies/</code> (first approach: <code>screen_C.json</code>, <code>family_ratios.json</code>, <code>nose_radius.json</code>, <code>refine_map_reference.json</code>; new: <code>band_count.json</code>, <code>screen_VC.json</code>, <code>screen_F.json</code>, <code>screen_reference_new.json</code>, <code>screen_new_summary.json</code>, <code>nose_levels_check.json</code>, <code>similarity_check.json</code>, <code>refine_map_re.json</code>, <code>upper_band_check.json</code>); <code>configs/surface.yaml</code> (the new rules), <code>configs/surface_first.yaml</code> (the first approach), <code>configs/surface_plan_VC.yaml</code> (the planned rules at VC, read only by <code>band_count.py</code>)</td></tr>
  <tr><td class='what'>one mesh folder</td><td><code>surface.npz</code>, <code>surface.xyz</code> (Plot3D), <code>stations.csv</code>, <code>quality.json</code>, <code>manifest.json</code> (wing input hash, loft surface hash, mesh code hash, mesh node hash); refused: <code>refusal.json</code> only</td></tr>
  </table></div>
</section>"""

    foot = f"""<footer>Stage 2 of CFD_Automation (karmix96/aeris, branch stage2-surface-mesh). Built and screened with the numpy twin of the loft on 2 Nov 2026 (first approach); updated 6 Nov 2026 with the new approach (decided) and 7 Nov 2026: the refine map from −5° and the band count (Study 8), the new rules built, the nose fix and similarity built in Stage 1, the new screen (Study 9), the similarity check (Study 10) and the refine map at the Re levels (Study 11); cfdauto {__version__}; first screen mesh code hash {screen['mesh_code_hash'][:12]}, new screen {sn.get('mesh_code_hash', '')[:12]} (the merge of the refine map by Re level changed only <code>refine_map.py</code> in that folder, not the mesher, so today's hash differs). Sources: Levy et al. 2013 (DPW gridding guidelines); Celik et al. 2008 (GCI, r ≥ 1.3); Ansys CFX Modeling Guide, γ-Re_θ transition model grid requirements; White, Viscous Fluid Flow (flat-plate friction); the AERIS Mesh Automation Primer, Annex G; S8 (section_o.py, strategy_s8.py).</footer>"""

    body = head + glance + change + why + what + primer + how + rules_sec + studies + steps + assumptions + findings + open_sec + handover + files + foot
    inner = (f'<title>Surface Mesh</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
             f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Sans+3:wght@400;600;700&family=JetBrains+Mono:wght@400;500&display=swap">\n'
             f'<style>{CSS}</style>\n<div class="wrap">{body}</div>')
    full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + inner.replace('<div class="wrap">', '</head>\n<body>\n<div class="wrap">', 1) + "\n</body>\n</html>\n")
    return full, inner


def main() -> None:
    d = load()
    full, inner = build_page(d)
    (DOCS / "SURFACE_MESH.html").write_text(full)
    (DOCS / "SURFACE_MESH.body.html").write_text(inner)
    print(f"wrote docs/SURFACE_MESH.html ({len(full) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
