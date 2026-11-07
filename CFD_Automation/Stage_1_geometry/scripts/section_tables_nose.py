"""The section tables before and after the nose fix (decision 64): what the rebuild changed.

The section tables (cfdauto/flowmap/tables.py) were first built on the sections as made before decision 64.
Since 7 Nov 2026 every section comes from one cubic spline through the raw points, with the leading edge at
the spline's apex and 201 points per side. The tables were rebuilt on these sections on 7 Nov 2026
(`python -m cfdauto.flowmap.tables --build`, 2,408 XFOIL sweeps). This compares old and new on every shared
grid point (section, mode, N_crit, Re, Mach, angle):

  - answers gained and lost (a point has an XFOIL answer when its cd is finite);
  - transition, free-transition tables only (tripped ones sit at the 1 % c trip): |Δ xtr_top|, |Δ xtr_bot| [% c];
  - lift and drag: |Δ cl| / |cl| [%] where |cl| ≥ 0.1, |Δ cl| (absolute), |Δ cd| / cd [%];
  - the 2-D error of a fully turbulent model, cd_trip / cd_free − 1, before and after [points];
  - bubbles: yes / no agreement, and |Δ start|, |Δ end| [% c] where both have one;
over all points, per Re and per section. Statistics of absolute changes: median, 95th percentile, max.
And the tables through the flow-map engine (wing level): the 20 reference wings at the four Re levels, root angle
0–10°, the tables at Mach 0.1: the SA profile-drag error, the upper laminar run, bubbles, the model category.

    cd CFD_Automation && python Stage_1_geometry/scripts/section_tables_nose.py              # seconds
    cd CFD_Automation && python Stage_1_geometry/scripts/section_tables_nose.py --old DIR    # old tables from a folder

The old tables are read from git (rev OLD_REV, the last commit before the rebuild) unless --old is given.
Writes Stage_1_geometry/data/studies/section_tables_nose.json and Stage_1_geometry/docs/section_tables_nose.png.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto.flowmap import tables  # noqa: E402
from cfdauto.paths import REPO, STAGE1  # noqa: E402

OLD_REV = "11b0df15"            # the last commit with the tables built before the nose fix
OUT_JSON = STAGE1 / "data" / "studies" / "section_tables_nose.json"
OUT_PNG = STAGE1 / "docs" / "section_tables_nose.png"
CL_MIN = 0.1                    # relative lift change only where |cl| >= this
ALPHA_BANDS = ((-10, -4), (-4, 0), (0, 4), (4, 8), (8, 11), (11, 14))   # deg; lo included, hi excluded (14 included)
FIGURE = {"file": "docs/section_tables_nose.png",
          "what": "New minus old against the Re on the section chord, over the 10 sections, all angles and Mach 0, 0.1, 0.2: "
                  "the transition change (free transition, upper and lower side), the drag change (free and tripped), and "
                  "the share of grid points that gained or lost an XFOIL answer.",
          "conclusion": "The nose fix moves transition by a median 0.2 % c and the drag by a median 0.8 %; the larger "
                        "changes come at high Re and near the 2-D stall, not at low Re."}
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e4e2dc", "#fcfcfb"
C_UP, C_LO = "#2a78d6", "#eb6834"   # reference palette slots 1 and 2 (validated, light)


# --- reading ------------------------------------------------------------------------------------------
def _load_npz(raw: bytes) -> dict:
    z = np.load(io.BytesIO(raw))
    return {k: z[k] for k in z.files}


def old_bytes(tid: str, folder: Path | None) -> bytes | None:
    if folder is not None:
        f = folder / f"{tid}.npz"
        return f.read_bytes() if f.exists() else None
    rel = (tables.TABLE_DIR / f"{tid}.npz").relative_to(REPO).as_posix()
    p = subprocess.run(["git", "-C", str(REPO), "show", f"{OLD_REV}:{rel}"], capture_output=True)
    return p.stdout if p.returncode == 0 else None


def old_table(tid: str, folder: Path | None) -> dict | None:
    raw = old_bytes(tid, folder)
    return None if raw is None else _load_npz(raw)


def new_table(tid: str) -> dict:
    return _load_npz((tables.TABLE_DIR / f"{tid}.npz").read_bytes())


# --- statistics ---------------------------------------------------------------------------------------
def stats(x: np.ndarray, signed: np.ndarray | None = None) -> dict | None:
    """Median, 95th percentile and max of |x|; with signed, also the median and mean of the signed change."""
    x = np.abs(np.asarray(x, float))
    x = x[np.isfinite(x)]
    if not len(x):
        return None
    out = {"n": int(len(x)), "median": float(np.median(x)), "p95": float(np.percentile(x, 95)), "max": float(x.max())}
    if signed is not None:
        s = np.asarray(signed, float)
        s = s[np.isfinite(s)]
        out["median_signed"] = float(np.median(s))
        out["mean_signed"] = float(np.mean(s))
    return out


def collect(folder: Path | None) -> list[dict]:
    """One record per table: variant, the grid and both sets of fields (aligned)."""
    recs = []
    for s, mode, nc, machs in tables.variants():
        tid = tables.table_id(s, mode, nc)
        o, n = old_table(tid, folder), new_table(tid)
        if o is None:
            print(f"  {tid}: no old table, skipped")
            continue
        for k in ("re", "mach", "alpha"):
            if not np.allclose(o[k], n[k]):
                raise ValueError(f"{tid}: the {k} grid differs between old and new")
        recs.append({"id": tid, "section": s, "mode": mode, "ncrit": nc, "re": n["re"], "mach": n["mach"],
                     "alpha": n["alpha"], "old": o, "new": n})
    return recs


def flat(recs: list[dict], field: str, which: str, pick=lambda r: True) -> np.ndarray:
    return np.concatenate([r[which][field].ravel() for r in recs if pick(r)]) if any(pick(r) for r in recs) else np.array([])


def re_index(recs: list[dict], pick=lambda r: True) -> np.ndarray:
    """The Re of every flattened point (same order as flat)."""
    out = []
    for r in recs:
        if pick(r):
            out.append(np.broadcast_to(r["re"][:, None, None], r["new"]["cd"].shape).ravel())
    return np.concatenate(out)


def alpha_index(recs: list[dict]) -> np.ndarray:
    """The angle of every flattened point (same order as flat)."""
    return np.concatenate([np.broadcast_to(r["alpha"][None, None, :], r["new"]["cd"].shape).ravel() for r in recs])


def compare(recs: list[dict], pick=lambda r: True, re_mask: float | None = None, alpha_band=None) -> dict:
    """Every comparison over the tables chosen by pick (and one Re when re_mask is given; angles inside
    alpha_band = (lo, hi), lo included, when given)."""
    sel = [r for r in recs if pick(r)]
    if not sel:
        return {}
    R = re_index(sel)
    keep = np.ones(R.shape, bool) if re_mask is None else np.isclose(R, re_mask)
    if alpha_band is not None:
        A = alpha_index(sel)
        keep &= (A >= alpha_band[0] - 1e-9) & (A < alpha_band[1] - 1e-9) if alpha_band[1] < 14 else (A >= alpha_band[0] - 1e-9)
    g = lambda f, w: flat(sel, f, w)[keep]                   # noqa: E731
    cd_o, cd_n = g("cd", "old"), g("cd", "new")
    ao, an = np.isfinite(cd_o), np.isfinite(cd_n)
    both = ao & an
    out = {"points": int(keep.sum()), "answered_old": int(ao.sum()), "answered_new": int(an.sum()),
           "gained": int((~ao & an).sum()), "lost": int((ao & ~an).sum()), "both": int(both.sum())}
    cl_o, cl_n = g("cl", "old"), g("cl", "new")
    big = both & (np.abs(cl_o) >= CL_MIN)
    out["cl_pct"] = stats(100 * (cl_n - cl_o)[big] / np.abs(cl_o[big]), 100 * (cl_n - cl_o)[big] / np.abs(cl_o[big]))
    out["cl_abs"] = stats((cl_n - cl_o)[both], (cl_n - cl_o)[both])
    out["cd_pct"] = stats(100 * (cd_n - cd_o)[both] / cd_o[both], 100 * (cd_n - cd_o)[both] / cd_o[both])
    free = np.concatenate([np.full(r["new"]["cd"].size, r["mode"] == "free") for r in sel])[keep]
    for side, f in (("upper", "xtr_top"), ("lower", "xtr_bot")):
        d = 100 * (g(f, "new") - g(f, "old"))
        m = both & free
        out[f"xtr_{side}_pct_c"] = stats(d[m], d[m])
    for side, b in (("upper", "bub_u"), ("lower", "bub_l")):
        fo, fn = g(b, "old"), g(b, "new")
        m = both & free & np.isfinite(fo) & np.isfinite(fn)
        yo, yn = fo[m] >= 0.5, fn[m] >= 0.5
        out[f"bubble_{side}"] = {"agree_share": float(np.mean(yo == yn)) if m.any() else None,
                                 "old_only": int((yo & ~yn).sum()), "new_only": int((~yo & yn).sum()),
                                 "both": int((yo & yn).sum())}
        mb = np.zeros(m.shape, bool)
        mb[m] = yo & yn
        for end in ("s", "e"):
            d = 100 * (g(f"{b}_{end}", "new") - g(f"{b}_{end}", "old"))
            out[f"bubble_{side}"]["start_pct_c" if end == "s" else "end_pct_c"] = stats(d[mb], d[mb])
    return out


def sa_error(recs: list[dict], folder_note: str) -> dict:
    """The 2-D error of a fully turbulent model, cd_trip / cd_free - 1 (N_crit 9, the ten sections), before and
    after, per Re [points]; where both free and tripped have an answer in both builds."""
    out = {"what": "cd_trip / cd_free - 1 at the same section, Re, Mach, angle (N_crit 9); change in points", "per_re": {},
           "per_section": {}}
    alld, allo, alln = [], [], []
    by = {(r["section"], r["mode"]): r for r in recs if r["ncrit"] == 9.0 and "+" not in r["section"]}
    for (s, mode), rf in by.items():
        if mode != "free" or (s, "trip") not in by:
            continue
        rt = by[(s, "trip")]
        nm = min(rf["new"]["cd"].shape[1], rt["new"]["cd"].shape[1])
        e_o = rt["old"]["cd"][:, :nm] / rf["old"]["cd"][:, :nm] - 1
        e_n = rt["new"]["cd"][:, :nm] / rf["new"]["cd"][:, :nm] - 1
        ok = np.isfinite(e_o) & np.isfinite(e_n)
        # per section over Re >= 1e5 and 0-8 deg (the band the flow dataset's statements are about)
        re_ok = (rf["re"] >= 1e5)[:, None, None]
        a_ok = ((rf["alpha"] >= 0) & (rf["alpha"] <= 8))[None, None, :]
        m = ok & re_ok & a_ok
        out["per_section"][s] = {"median_old_pct": float(np.median(100 * e_o[m])), "median_new_pct": float(np.median(100 * e_n[m])),
                                 "n": int(m.sum()), "where": "Re >= 1e5, 0-8 deg, Mach 0-0.2"}
        for i, re_ in enumerate(rf["re"]):
            out["per_re"].setdefault(f"{re_:.3g}", {"d": [], "o": [], "n": []})
            out["per_re"][f"{re_:.3g}"]["d"] += list(100 * (e_n[i] - e_o[i])[ok[i]].ravel())
            out["per_re"][f"{re_:.3g}"]["o"] += list(100 * e_o[i][ok[i]].ravel())
            out["per_re"][f"{re_:.3g}"]["n"] += list(100 * e_n[i][ok[i]].ravel())
        alld += list(100 * (e_n - e_o)[ok]); allo += list(100 * e_o[ok]); alln += list(100 * e_n[ok])
    for k, v in out["per_re"].items():
        out["per_re"][k] = {"change_points": stats(np.array(v["d"]), np.array(v["d"])),
                            "median_old_pct": float(np.median(v["o"])) if v["o"] else None,
                            "median_new_pct": float(np.median(v["n"])) if v["n"] else None}
    out["all"] = {"change_points": stats(np.array(alld), np.array(alld)), "median_old_pct": float(np.median(allo)),
                  "median_new_pct": float(np.median(alln))}
    out["old_source"] = folder_note
    return out


def wing_check(folder: Path | None) -> dict:
    """The tables through the flow-map engine, old against new: the 20 reference wings (2 strips per panel) at the
    four Re levels on the mean chord, root angle 0-10 deg (the flow dataset's angles, 2 deg steps), sea level, the
    tables at Mach 0.1. Wing-level numbers of the flow dataset: the SA profile-drag error, the upper laminar run,
    the share of the half wing with an upper bubble, the model category."""
    import tempfile

    from cfdauto.flowmap import engine
    from cfdauto.geometry.build import load_set
    from cfdauto.geometry.params import load_config, resolve

    cfg = load_config()
    R, A = (v.ravel() for v in np.meshgrid((1e5, 3e5, 1.5e6, 3e6), np.arange(0.0, 10.01, 2.0), indexing="ij"))
    keys = ("sa_bias", "lam_upper", "bubble_span", "category")

    def run() -> dict:
        out = {k: [] for k in keys} | {"re": [], "type": []}
        for t in ("bwb", "flying_wing", "cranked", "tapered"):
            spec = cfg.types[t]
            for vec in load_set(t, "reference")["vectors"]:
                ws = engine.wing_strips(spec, resolve(spec, vec), None, 2)
                c_mean = ws.pf.area() / (2 * ws.pf.semi_span)
                mach = R / (engine.rho_over_mu(0.0) * c_mean) / engine.sound_speed(0.0)
                m = engine.metrics(ws, engine.evaluate(ws, mach, np.zeros(R.shape), A, mach_in_tables=np.full(R.shape, 0.1)))
                for k in keys:
                    out[k] += [float(v) for v in np.asarray(m[k], float)]
                out["re"] += list(R); out["type"] += [t] * len(R)
        return {k: np.array(v) for k, v in out.items()}

    new = run()
    saved = tables.TABLE_DIR
    with tempfile.TemporaryDirectory() as tmp:
        for s, mode, nc, _ in tables.variants():
            tid = tables.table_id(s, mode, nc)
            raw = old_bytes(tid, folder)
            if raw is not None:
                (Path(tmp) / f"{tid}.npz").write_bytes(raw)
        tables.TABLE_DIR, tables._LOADED = Path(tmp), {}
        try:
            old = run()
        finally:
            tables.TABLE_DIR, tables._LOADED = saved, {}

    def block(mask) -> dict:
        b_o, b_n = 100 * old["sa_bias"][mask], 100 * new["sa_bias"][mask]
        ok = np.isfinite(b_o) & np.isfinite(b_n)
        lam = np.isfinite(old["lam_upper"][mask]) & np.isfinite(new["lam_upper"][mask])
        return {"conditions": int(mask.sum()),
                "sa_error_median_old_pct": float(np.median(b_o[ok])), "sa_error_median_new_pct": float(np.median(b_n[ok])),
                "sa_error_change_points": stats(b_n[ok] - b_o[ok], b_n[ok] - b_o[ok]),
                "within_10pct_share_old": float(np.mean(np.abs(b_o[ok]) < 10)), "within_10pct_share_new": float(np.mean(np.abs(b_n[ok]) < 10)),
                "lam_upper_change_pct_c": stats(100 * (new["lam_upper"][mask] - old["lam_upper"][mask])[lam],
                                                100 * (new["lam_upper"][mask] - old["lam_upper"][mask])[lam]),
                "bubble_span_change_points": stats(100 * (new["bubble_span"][mask] - old["bubble_span"][mask]),
                                                   100 * (new["bubble_span"][mask] - old["bubble_span"][mask])),
                "category_same_share": float(np.mean(old["category"][mask] == new["category"][mask]))}

    every = np.ones(R.size * 20, bool)
    out = {"what": "the 20 reference wings x Re 1e5, 3e5, 1.5e6, 3e6 x root angle 0-10 deg (2 deg), sea level, tables at "
                   "Mach 0.1, 2 strips per panel: wing-level numbers with the old and the new tables",
           "all": block(every)}
    out["per_re"] = {f"{r:.3g}": block(np.isclose(new["re"], r)) for r in (1e5, 3e5, 1.5e6, 3e6)}
    out["per_type"] = {t: block(new["type"] == t) for t in ("bwb", "flying_wing", "cranked", "tapered")}
    return out


# --- figure ---------------------------------------------------------------------------------------------
def figure(res: dict) -> None:
    plt.rcParams.update({"font.size": 10.5, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
                         "ytick.color": INK2, "axes.titlesize": 11, "axes.titlecolor": INK, "legend.fontsize": 9.5,
                         "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF,
                         "axes.facecolor": SURF, "savefig.facecolor": SURF, "axes.titlelocation": "left"})
    pr = res["free_n9"]["per_re"]
    re_ = np.array([float(k) for k in pr])
    fig, ax = plt.subplots(3, 1, figsize=(6.6, 9.6), sharex=True, dpi=130)

    a = ax[0]
    for side, col in (("upper", C_UP), ("lower", C_LO)):
        p95 = [pr[k][f"xtr_{side}_pct_c"]["p95"] for k in pr]
        med = [pr[k][f"xtr_{side}_pct_c"]["median"] for k in pr]
        a.plot(re_, p95, "-o", color=col, lw=2, ms=4.5, label=f"{side} side, 95th percentile")
        a.plot(re_, med, ":", color=col, lw=1.6, label=f"{side} side, median")
    a.set_ylabel("|change| in transition [% c]")
    a.set_title("Transition position (free transition, N_crit 9)")
    a.set_ylim(0, 1.45 * a.get_ylim()[1])
    a.legend(frameon=False, loc="upper left", ncol=2, fontsize=8.5)

    a = ax[1]
    for key, col, name in (("free_n9", C_UP, "free transition"), ("trip", C_LO, "tripped at 1 % c")):
        p = res[key]["per_re"]
        a.plot(re_, [p[k]["cd_pct"]["p95"] for k in p], "-o", color=col, lw=2, ms=4.5, label=f"{name}, 95th percentile")
        a.plot(re_, [p[k]["cd_pct"]["median"] for k in p], ":", color=col, lw=1.6, label=f"{name}, median")
    a.set_ylabel("|change| in drag cd [%]")
    a.set_title("Drag")
    a.set_ylim(0, 1.45 * a.get_ylim()[1])
    a.legend(frameon=False, loc="upper left", ncol=2, fontsize=8.5)

    a = ax[2]
    for key, col, name in (("free_n9", C_UP, "free transition"), ("trip", C_LO, "tripped at 1 % c")):
        p = res[key]["per_re"]
        a.plot(re_, [100 * p[k]["gained"] / p[k]["points"] for k in p], "-o", color=col, lw=2, ms=4.5,
               label=f"{name}, gained")
        a.plot(re_, [-100 * p[k]["lost"] / p[k]["points"] for k in p], "--s", color=col, lw=1.6, ms=4,
               label=f"{name}, lost (below 0)")
    a.axhline(0, color=MUTED, lw=0.8)
    a.set_ylabel("answers gained (+) / lost (−)\n[% of grid points]")
    a.set_title("XFOIL answers")
    lo, hi = a.get_ylim()
    a.set_ylim(lo - 0.75 * (hi - lo), hi)
    a.legend(frameon=False, loc="lower left", ncol=2, fontsize=8.5)
    a.set_xscale("log")
    a.set_xlabel("Reynolds number on the section chord")
    for a in ax:
        a.grid(True, color=GRID, lw=0.6)
        a.set_axisbelow(True)
    fig.suptitle("Section tables: rebuilt on the fixed nose (decision 64), new − old\n"
                 "10 sections, all angles −10° to 14°, Mach 0, 0.1, 0.2", x=0.02, ha="left", fontsize=11.5, color=INK)
    fig.tight_layout()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT_PNG)


# --- main -----------------------------------------------------------------------------------------------
def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Section tables before and after the nose fix.")
    p.add_argument("--old", type=Path, help="folder with the old tables (default: git rev %s)" % OLD_REV)
    p.add_argument("--figure-only", action="store_true", help="redraw the figure from the JSON")
    a = p.parse_args(argv)
    if a.figure_only:
        figure(json.loads(OUT_JSON.read_text()))
        return
    recs = collect(a.old)
    note = f"old tables from {a.old}" if a.old else f"old tables from git rev {OLD_REV}"
    groups = {
        "free_n9": lambda r: r["mode"] == "free" and r["ncrit"] == 9.0 and "+" not in r["section"],
        "trip": lambda r: r["mode"] == "trip" and "+" not in r["section"],
        "free_ncrit_5_11": lambda r: r["mode"] == "free" and r["ncrit"] != 9.0,
        "blends": lambda r: "+" in r["section"],
        "all": lambda r: True,
    }
    res = {"what": "section tables rebuilt on the fixed nose (decision 64), 7 Nov 2026: new minus old on every shared grid "
                   "point (section, mode, N_crit, Re, Mach, angle)",
           "old_source": note, "cl_min_for_relative": CL_MIN,
           "tables": len(recs), "grid": {"re": [float(v) for v in tables.RE], "mach": [float(v) for v in tables.MACH],
                                          "alpha_deg": [float(tables.ALPHA[0]), float(tables.ALPHA[-1]), 0.5]},
           "units": {"xtr": "% c, |new - old|", "cl_pct": "% of |cl old| (|cl| >= 0.1)", "cl_abs": "absolute",
                     "cd_pct": "% of cd old", "bubble": "% c, |new - old| where both have a bubble on that side"}}
    for name, pick in groups.items():
        g = compare(recs, pick)
        g["per_re"] = {f"{r:.3g}": compare(recs, pick, r) for r in tables.RE}
        res[name] = g
    res["per_section_free_n9"] = {s: compare(recs, lambda r, s=s: r["section"] == s and r["mode"] == "free" and r["ncrit"] == 9.0)
                                  for s in tables.SECTIONS}
    res["per_angle_free_n9"] = {f"{lo:g} to {hi:g}": compare(recs, groups["free_n9"], alpha_band=(lo, hi))
                                for lo, hi in ALPHA_BANDS}
    res["per_angle_trip"] = {f"{lo:g} to {hi:g}": compare(recs, groups["trip"], alpha_band=(lo, hi)) for lo, hi in ALPHA_BANDS}
    res["per_section_trip"] = {s: compare(recs, lambda r, s=s: r["section"] == s and r["mode"] == "trip")
                               for s in tables.SECTIONS}
    res["sa_error_2d"] = sa_error(recs, note)
    res["wing_level"] = wing_check(a.old)
    res["figure"] = FIGURE
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, indent=1))
    print("wrote", OUT_JSON)
    f = res["free_n9"]
    print(f"free N_crit 9: {f['points']} points, gained {f['gained']}, lost {f['lost']}; "
          f"xtr upper {f['xtr_upper_pct_c']}, lower {f['xtr_lower_pct_c']}; cd {f['cd_pct']}")
    figure(res)


if __name__ == "__main__":
    main()
