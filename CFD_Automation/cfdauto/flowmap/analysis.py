"""Analysis of the flow dataset: trends, statistics, sensitivities, checks of the method, conclusions.

    python -m cfdauto.flowmap.analysis      # reads data/flowdata/dataset.csv.gz; writes docs/flow_*.png,
                                            # docs/flow_analysis.json (numbers) and docs/flow_summary.json (tool context)

Sensitivity of each wing metric to each input, per family:
  - first-order index eta^2 = Var(E[y | x]) / Var(y) (x binned in deciles, or its levels): the share of
    the metric's variance one input explains alone (inputs are independent by design: Latin-hypercube
    wings crossed with a full grid of conditions and section sets);
  - permutation importance of a gradient-boosted model (captures interactions);
  - Spearman rank correlation (direction).
Checks of the method (assumption sensitivities): N_crit 5 / 9 / 11, compressibility at fixed Re,
strips per panel 1 / 2 / 5, the induced angle left out (the old baseline), the section tables against direct
XFOIL runs, and the blend rule against direct 50/50 blends.

Baseline (2 Nov 2026): induced angle included. Statistics use realistic speeds and section sets that can trim
the wing (realistic_set); sections enter the sensitivity by airfoil set (the same airfoils on BWB and flying
wing are one level), and the gradient-boosting test split keeps every wing on one side (no leakage).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..geometry.params import FAMILIES, FAMILY_OF, GEOMETRY_ROOT, WING_TYPES
from . import engine, tables
from .dataset import OUT, build, load_flow_config

DOCS = GEOMETRY_ROOT / "docs"
NAME = {"bwb": "BWB", "flying_wing": "Flying wing", "cranked": "Cranked", "tapered": "Tapered"}
COL = {"bwb": "#2E8B57", "flying_wing": "#B07000", "cranked": "#0C5EA8", "tapered": "#5B8FD0"}
SET_COL = {"A": "#1F2A33", "B": "#C0392B", "C": "#2E86AB", "D": "#9A9A9A"}
INK, MUTED = "#1F2A33", "#6B7785"
INPUTS = {  # column -> label (sensitivity inputs)
    "mean_chord_m": "mean chord (size)", "aspect_ratio": "aspect ratio", "taper": "taper",
    "max_sweep_deg": "LE sweep (max)", "washout_deg": "washout", "twist0_deg": "root twist",
    "dihedral_p1_deg": "dihedral", "b3_ratio": "outer-panel share", "split_ratio": "inner/middle split",
    "set": "section set", "mach": "Mach", "alpha_deg": "angle of attack", "altitude_m": "altitude"}
OUTPUTS = {"sa_bias": "SA drag error", "lam_upper": "laminar run, upper (x_tr / c)",
           "bubble_span": "span with a bubble", "te_sep_span": "span with TE separation",
           "span_re_lt_1e5": "span below Re 10⁵", "conv_span": "span with a 2-D answer"}
CATEGORICAL = {"set", "mach", "alpha_deg", "altitude_m"}


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    logging.getLogger("matplotlib").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#B8C0C8", "axes.labelcolor": INK, "xtick.color": MUTED,
                         "ytick.color": MUTED, "axes.titlesize": 10})
    return plt


def short_label(label: str) -> str:
    """'MH 60 / MH 45 (suggested)' -> 'MH 60 / MH 45*'; '(not reflexed)' -> a dagger (cannot trim a tailless wing);
    other notes in brackets dropped."""
    star = "*" if "(suggested)" in label else ("†" if "not reflexed" in label else "")
    return label.split(" (")[0] + star


def airfoil_set(label: str) -> str:
    """The airfoil set behind a set label, the same on every type: 'MH 104 / MH 61 (suggested)' -> 'MH 104 / MH 61'."""
    return label.split(" (")[0]


def realistic(df: pd.DataFrame) -> pd.DataFrame:
    """Rows the statistics use: realistic speeds and a section set that can trim the wing."""
    keep = df["realistic_speed"]
    if "realistic_set" in df:
        keep = keep & df["realistic_set"]
    return df[keep]


def _clean(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(alpha=0.25)


# ============================================================================================ statistics
def eta2(x: pd.Series, y: pd.Series, categorical: bool, bins: int = 10) -> float:
    ok = x.notna() & y.notna()
    x, y = x[ok], y[ok]
    if len(y) < 50 or y.var() == 0:
        return np.nan
    g = x if categorical else pd.qcut(x.rank(method="first"), bins, labels=False)
    m = y.groupby(g).agg(["mean", "count"])
    return float((m["count"] * (m["mean"] - y.mean()) ** 2).sum() / len(y) / y.var(ddof=0))


def spearman(x: pd.Series, y: pd.Series) -> float:
    ok = x.notna() & y.notna()
    if ok.sum() < 50:
        return np.nan
    return float(x[ok].rank().corr(y[ok].rank()))


GROUPS = {"wing shape": [i for i in INPUTS if i not in ("set", "mach", "alpha_deg", "altitude_m")],
          "sections": ["set"], "flight condition": ["mach", "alpha_deg", "altitude_m"]}


def _xy(d: pd.DataFrame, o: str, n_max: int = 40000, seed: int = 7):
    """Inputs, output and a train mask that keeps every wing on one side (75 % of the wings train)."""
    X = d[list(INPUTS)].copy()
    names = sorted(d["set"].unique())
    X["set"] = d["set"].map({k: i for i, k in enumerate(names)})
    y = d[o]
    wing = (d["type"].astype(str) + ":" + d["wing"].astype(str)).values
    ok = y.notna().values
    X, y, wing = X[ok], y[ok], wing[ok]
    rng = np.random.default_rng(seed)
    n = min(len(y), n_max)
    idx = rng.choice(len(y), n, replace=False)
    X, y, wing = X.iloc[idx], y.iloc[idx], wing[idx]
    ids = np.unique(wing)
    train_ids = set(rng.choice(ids, int(round(0.75 * len(ids))), replace=False))
    train = np.array([w in train_ids for w in wing])
    return X, y, train


def _fit(X: pd.DataFrame, y: pd.Series, cols: list[str], train: np.ndarray):
    from sklearn.ensemble import HistGradientBoostingRegressor
    cat = [k for k, c in enumerate(cols) if c == "set"]
    model = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.08, categorical_features=cat or None, random_state=0)
    model.fit(X[cols][train], y[train])
    return model, float(model.score(X[cols][~train], y[~train]))


def sensitivity(df: pd.DataFrame) -> dict:
    """Per family and output: eta^2 and Spearman per input; permutation importance and test R^2 of a
    gradient-boosted model on all inputs; and the share of variance each input group explains alone
    (R^2 of a model on that group only) and in total (R^2 lost when the group is left out). The
    dataset crosses wings x section sets x conditions in full, so the three groups are independent."""
    from sklearn.inspection import permutation_importance
    out = {}
    for fam in FAMILIES:
        d = realistic(df[df["family"] == fam]).copy()
        d["set"] = d["set_label"].map(airfoil_set)          # the airfoil set, not the type's letter
        res = {}
        for o in OUTPUTS:
            y = d[o]
            e = {i: eta2(d[i], y, i in CATEGORICAL) for i in INPUTS}
            s = {i: (spearman(d[i], y) if i != "set" else np.nan) for i in INPUTS}
            X, ys, train = _xy(d, o)
            model, r2 = _fit(X, ys, list(INPUTS), train)
            pi = permutation_importance(model, X[~train], ys[~train], n_repeats=4, random_state=0, n_jobs=1)
            imp = {i: float(max(v, 0.0)) for i, v in zip(INPUTS, pi.importances_mean)}
            tot = sum(imp.values()) or 1.0
            first, total = {}, {}
            for g, cols in GROUPS.items():
                first[g] = max(_fit(X, ys, cols, train)[1], 0.0)
                rest = [c for c in INPUTS if c not in cols]
                total[g] = max(r2 - _fit(X, ys, rest, train)[1], 0.0)
            res[o] = {"eta2": e, "spearman": s, "perm": {k: v / tot for k, v in imp.items()}, "r2": r2,
                      "eta2_sum": float(np.nansum(list(e.values()))), "group_first": first, "group_total": total}
            print(f"  sensitivity {fam} {o}: R2 {r2:.3f}", flush=True)
        out[fam] = res
    return out


# ============================================================================================ checks
def check_variants(n_wings: int = 20) -> dict:
    """Paired comparisons on a subset: each variant against its matched baseline."""
    fc = load_flow_config()
    key = ["type", "wing", "set", "mach", "altitude_m", "alpha_deg"]
    cols = ["sa_bias", "lam_upper", "bubble_span", "te_sep_span", "conv_span", "cl2d"]

    def pair(base, var, label):
        m = base[key + cols].merge(var[key + cols], on=key, suffixes=("", "_v"))
        out = {"label": label, "n": int(len(m))}
        for c in cols:
            dlt = (m[f"{c}_v"] - m[c]).dropna()
            out[c] = {"median": float(dlt.median()), "q05": float(dlt.quantile(0.05)), "q95": float(dlt.quantile(0.95)),
                      "mean_abs": float(dlt.abs().mean())} if len(dlt) else None
        out["delta_bias"] = (m["sa_bias_v"] - m["sa_bias"]).dropna().tolist()[::7]
        return out

    res = {}
    b01 = build(n_wings=n_wings, mach_in_tables=0.1, fc=fc)
    for nc in tables.NCRIT_VARIANTS:
        res[f"ncrit_{nc:g}"] = pair(b01, build(n_wings=n_wings, mach_in_tables=0.1, ncrit=nc, fc=fc),
                                    f"N_crit {nc:g} instead of 9 (turbulence level {_tu(nc):.2f} % instead of 0.07 %)")
    base = build(n_wings=n_wings, fc=fc)
    res["mach0"] = pair(base, build(n_wings=n_wings, mach_in_tables=0.0, fc=fc), "no compressibility (Mach 0 in 2-D, same Re)")
    res["strips1"] = pair(base, build(n_wings=n_wings, n_per_panel=1, fc=fc), "7 strips instead of 10")
    res["strips5"] = pair(base, build(n_wings=n_wings, n_per_panel=5, fc=fc), "19 strips instead of 10")
    res["no_induced"] = pair(base, build(n_wings=n_wings, induced=False, fc=fc),
                             "induced angle left out (the old baseline): local angle = root angle + twist")
    res["total_drag"] = total_drag(base)
    return res


def total_drag(d: pd.DataFrame) -> dict:
    """The SA error as a share of the whole drag: profile drag plus an elliptic induced drag
    CL^2 / (pi AR), with CL from the strips with the induced angle (the baseline)."""
    d = realistic(d).copy()
    cdi = d["cl2d"] ** 2 / (np.pi * d["aspect_ratio"])
    d["total_bias"] = (d["cd_trip"] - d["cd_free"]) / (d["cd_free"] + cdi)
    d["induced_share"] = cdi / (d["cd_free"] + cdi)
    out = {}
    for t in WING_TYPES:
        x = d[(d["type"] == t)]
        out[t] = {"total_bias_median": float(x["total_bias"].median()), "total_bias_q10": float(x["total_bias"].quantile(0.1)),
                  "total_bias_q90": float(x["total_bias"].quantile(0.9)),
                  "profile_bias_median": float(x["sa_bias"].median()),
                  "induced_share_median": float(x["induced_share"].median())}
    out["by_alpha"] = {f"{a:g}": float(v) for a, v in d.groupby("alpha_deg")["total_bias"].median().items()}
    out["profile_by_alpha"] = {f"{a:g}": float(v) for a, v in d.groupby("alpha_deg")["sa_bias"].median().items()}
    return out


def _tu(ncrit: float) -> float:
    """Mack's relation N_crit = -8.43 - 2.4 ln(Tu) (Tu as a fraction), returned in %."""
    return 100 * float(np.exp(-(ncrit + 8.43) / 2.4))


def check_tables(n: int = 160, seed: int = 11) -> dict:
    """Section tables against direct XFOIL runs at random (section, Re, Mach, angle)."""
    from concurrent.futures import ThreadPoolExecutor

    from ..geometry.sections import load_airfoil
    from . import xfoil
    rng = np.random.default_rng(seed)
    pts_ = [(tables.SECTIONS[k % len(tables.SECTIONS)], float(10 ** rng.uniform(np.log10(2e4), np.log10(5e6))),
             float(rng.uniform(0.0, 0.2)), float(np.round(rng.uniform(-4, 10), 2))) for k in range(n)]
    jobs = [(p, mode) for p in pts_ for mode in ("free", "trip")]

    def one(job):
        (sec, re_, M, al), mode = job
        return xfoil.run(load_airfoil(sec).selig(), re_, al, mode == "trip", M)

    with ThreadPoolExecutor(max_workers=2) as ex:
        direct = list(ex.map(one, jobs))
    rows = []
    for ((sec, re_, M, al), mode), d in zip(jobs, direct):
        t = tables.interp(tables.load(sec, mode), np.array([re_]), np.array([M]), np.array([al]))
        rows.append({"section": sec, "re": re_, "mach": M, "alpha": al, "mode": mode,
                     "direct_cd": d["cd"] if d else np.nan, "table_cd": float(t["cd"][0]),
                     "direct_cl": d["cl"] if d else np.nan, "table_cl": float(t["cl"][0]),
                     "direct_xtr": d["xtr_top"] if d else np.nan, "table_xtr": float(t["xtr_top"][0]),
                     "direct_bub": (d.get("bub_u") if d else np.nan), "table_bub": float(t["bub_u"][0])})
    df = pd.DataFrame(rows)
    out = {"n": int(len(df))}
    for mode in ("free", "trip"):
        d = df[(df["mode"] == mode)].dropna(subset=["direct_cd", "table_cd"])
        rel = (d["table_cd"] / d["direct_cd"] - 1).abs()
        dx = (d["table_xtr"] - d["direct_xtr"]).abs()
        dcl = (d["table_cl"] - d["direct_cl"]).abs()
        out[mode] = {"n_both": int(len(d)), "cd_rel_median": float(rel.median()), "cd_rel_q90": float(rel.quantile(0.9)),
                     "xtr_abs_median": float(dx.median()), "xtr_abs_q90": float(dx.quantile(0.9)),
                     "cl_abs_median": float(dcl.median()), "cl_abs_q90": float(dcl.quantile(0.9)),
                     "direct_failed": int(df[(df["mode"] == mode)]["direct_cd"].isna().sum()),
                     "table_missing": int(df[(df["mode"] == mode)]["table_cd"].isna().sum())}
        if mode == "free":
            bb = d.dropna(subset=["direct_bub", "table_bub"])
            out[mode]["bubble_agree"] = float(((bb["table_bub"] >= 0.5) == (bb["direct_bub"] >= 0.5)).mean())
    out["rows"] = df.to_dict(orient="list")
    return out


def check_blends() -> dict:
    """The blend rule (average of the parents' results) against 50/50 blends run directly (Mach 0.1)."""
    out = {}
    re_, al = np.meshgrid(tables.RE, tables.ALPHA, indexing="ij")
    for a, b in tables.BLENDS:
        for mode in ("free", "trip"):
            direct = tables.interp(tables.load(tables.blend_name(a, b), mode), re_, np.full(re_.shape, 0.1), al)
            rule = tables.lookup(a, b, 0.5, re_, np.full(re_.shape, 0.1), al, mode)
            ok = np.isfinite(direct["cd"]) & np.isfinite(rule["cd"]) & (al >= -4) & (al <= 10)
            rel = np.abs(rule["cd"][ok] / direct["cd"][ok] - 1)
            dx = np.abs(rule["xtr_top"][ok] - direct["xtr_top"][ok])
            out[f"{a}+{b}|{mode}"] = {"n": int(ok.sum()), "cd_rel_median": float(np.median(rel)),
                                      "cd_rel_q90": float(np.quantile(rel, 0.9)),
                                      "xtr_abs_median": float(np.median(dx)), "xtr_abs_q90": float(np.quantile(dx, 0.9))}
    return out


# ============================================================================================ figures
def fig_section_maps() -> None:
    """Per section, at Mach 0.1: where the free flow turns turbulent, where bubbles sit, how much fully
    turbulent flow changes the drag, and where XFOIL gives no answer (2-D stall)."""
    plt = _plt()
    from matplotlib.colors import TwoSlopeNorm
    secs = tables.SECTIONS
    lr = np.log10(tables.RE)
    for key, title, cmap, norm, lab in (
            ("xtr", "Where the free flow turns turbulent on the upper surface (x_tr / c), Mach 0.1", "viridis", None, "x_tr / c"),
            ("bub", "Laminar separation bubble on the upper surface (1 = yes), Mach 0.1", "Reds", None, "bubble"),
            ("bias", "Profile drag, fully turbulent / free transition − 1, Mach 0.1 (red: SA too high; blue: free flow draggier, "
                     "a long bubble)", "RdBu_r", TwoSlopeNorm(vmin=-0.6, vcenter=0.0, vmax=1.5), "SA drag error")):
        fig, axes = plt.subplots(2, 5, figsize=(15, 6.2), dpi=105, sharex=True, sharey=True)
        for ax, s in zip(axes.flat, secs):
            f, t = tables.load(s, "free"), tables.load(s, "trip")
            j = int(np.argmin(np.abs(f.mach - 0.1)))
            if key == "xtr":
                z = f.data["xtr_top"][:, j, :]
            elif key == "bub":
                z = f.data["bub_u"][:, j, :]
            else:
                z = t.data["cd"][:, j, :] / f.data["cd"][:, j, :] - 1
            kw = {"norm": norm} if norm is not None else {"vmin": 0, "vmax": 1}
            im = ax.pcolormesh(f.alpha, lr, z, cmap=cmap, shading="nearest", **kw)
            nan = ~np.isfinite(z)
            ax.contourf(f.alpha, lr, nan.astype(float), levels=[0.5, 1.5], colors=["#D5D8DC"], alpha=0.9)
            ax.set_title(s.upper(), fontsize=9.5)
            for lv in (np.log10(1e5), np.log10(3e5), np.log10(1.5e6), np.log10(3e6)):
                ax.axhline(lv, color="#1F2A33", lw=0.6, ls=(0, (4, 3)), alpha=0.55)
            ax.set_xlim(-6, 14)
        for ax in axes[1]:
            ax.set_xlabel("local angle [°]")
        for ax in axes[:, 0]:
            ax.set_ylabel("log₁₀ Re (chord)")
        cb = fig.colorbar(im, ax=axes, shrink=0.8, pad=0.01); cb.set_label(lab)
        fig.suptitle(title + ". Grey: no XFOIL answer (near stall, or a failed point). Dashed: the four study Re levels.", x=0.01, ha="left",
                     fontsize=10.5)
        fig.savefig(DOCS / f"flow_sections_{key}.png", bbox_inches="tight")
        plt.close(fig)


def fig_distributions(df: pd.DataFrame) -> None:
    plt = _plt()
    d = df[df["realistic_speed"]]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.2), dpi=105, sharey=True)
    axes = axes.ravel()
    for ax, t in zip(axes, WING_TYPES):
        dd = d[d["type"] == t]
        sets = sorted(dd["set"].unique())
        data = [100 * dd[dd["set"] == s]["sa_bias"].dropna().values for s in sets]
        vp = ax.violinplot(data, showextrema=False, widths=0.85)
        for b, s in zip(vp["bodies"], sets):
            b.set_facecolor(SET_COL[s]); b.set_alpha(0.45)
        for k, (v, s) in enumerate(zip(data, sets)):
            q = np.percentile(v, [10, 50, 90])
            ax.plot([k + 1, k + 1], [q[0], q[2]], color=INK, lw=1.2)
            ax.plot(k + 1, q[1], "o", color=INK, ms=4)
            ax.text(k + 1.08, q[1], f"{q[1]:.0f}", fontsize=7.5, va="center")
            lf = dd[(dd["set"] == s) & dd["level_flight"]]["sa_bias"].dropna()
            if len(lf) > 20:
                ax.plot(k + 1, 100 * lf.median(), "D", mfc="white", mec=INK, ms=5)
        ax.axhspan(-100 * engine.SA_OK, 100 * engine.SA_OK, color="#2E8B57", alpha=0.10)
        labels = [short_label(dd[dd["set"] == s]["set_label"].iloc[0]) for s in sets]
        ax.set_xticks(range(1, len(sets) + 1)); ax.set_xticklabels(labels, fontsize=8)
        ax.set_title(NAME[t], color=COL[t], fontweight="bold"); _clean(ax)
    for ax in axes[::2]:
        ax.set_ylabel("SA drag error [%]")
    fig.suptitle("How far fully turbulent SA is from the free-transition drag (all focus wings, realistic speeds, angles, altitudes)\n"
                 "dot and bar: median and 10–90 %; diamond: median in level flight; green band: ±10 %; * suggested sections; "
                 "† not reflexed: cannot trim a tailless wing (reference only)",
                 x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(DOCS / "flow_bias_violins.png")
    plt.close(fig)


def fig_trends(df: pd.DataFrame) -> None:
    plt = _plt()
    for xcol, xlab, name in (("mach", "flight Mach", "mach"), ("alpha_deg", "root angle [°]", "alpha")):
        fig = plt.figure(figsize=(15, 10.0), dpi=105)
        gs = fig.add_gridspec(4, 4, height_ratios=[1, 1, 1, 0.22], hspace=0.28, wspace=0.22)
        axes = np.array([[fig.add_subplot(gs[r, c]) for c in range(4)] for r in range(3)])
        for c, t in enumerate(WING_TYPES):
            dd = df[(df["type"] == t)]
            handles = []
            for r, (ycol, ylab, scale) in enumerate((("sa_bias", "SA drag error [%]", 100), ("lam_upper", "laminar run, upper [% chord]", 100),
                                                     ("bubble_span", "span with a bubble, mean [%]", 100))):
                ax = axes[r, c]
                for s in sorted(dd["set"].unique()):
                    g = dd[dd["set"] == s].groupby(xcol)[ycol]
                    lab = dd[dd["set"] == s]["set_label"].iloc[0]
                    if "realistic_set" in dd and not bool(dd[dd["set"] == s]["realistic_set"].iloc[0]):
                        lab += ", cannot trim"
                    if ycol == "bubble_span":          # mostly all or nothing per row: show the mean, no band
                        mean = g.mean()
                        h, = ax.plot(mean.index, scale * mean, color=SET_COL[s], lw=1.8, marker="o", ms=3, label=lab)
                    else:
                        q = g.quantile([0.25, 0.5, 0.75]).unstack()
                        h, = ax.plot(q.index, scale * q[0.5], color=SET_COL[s], lw=1.8, marker="o", ms=3, label=lab)
                        ax.fill_between(q.index, scale * q[0.25], scale * q[0.75], color=SET_COL[s], alpha=0.12)
                    if r == 0:
                        handles.append(h)
                if r == 0:
                    ax.set_title(NAME[t], color=COL[t], fontweight="bold")
                    ax.axhspan(-100 * engine.SA_OK, 100 * engine.SA_OK, color="#2E8B57", alpha=0.08)
                if c == 0:
                    ax.set_ylabel(ylab)
                if r == 2:
                    ax.set_xlabel(xlab)
                else:
                    ax.tick_params(labelbottom=False)
                _clean(ax)
            if xcol == "mach":
                fam = FAMILY_OF[t]
                hi = load_flow_config()["dataset"]["realistic_mach"][fam][1]
                for r in range(3):
                    axes[r, c].axvspan(hi, df["mach"].max() + 0.01, color="#D5D8DC", alpha=0.5, lw=0)
            lg = fig.add_subplot(gs[3, c]); lg.axis("off")
            lg.legend(handles=handles, loc="upper left", fontsize=7.5, frameon=False, ncol=1)
        for r in range(3):
            lo = min(axes[r, c].get_ylim()[0] for c in range(4)); hi = max(axes[r, c].get_ylim()[1] for c in range(4))
            for c in range(4):
                axes[r, c].set_ylim(lo, hi)
        what = "flight Mach (grey: faster than any real wing of the family)" if xcol == "mach" else "root angle"
        fig.suptitle(f"Trends with {what}: median (line) and middle half (band) over wings, the other conditions and altitudes; "
                     "bubble span: mean",
                     x=0.01, ha="left", fontsize=10.5, y=0.995)
        fig.savefig(DOCS / f"flow_trends_{name}.png", bbox_inches="tight")
        plt.close(fig)


def fig_re_bands(df: pd.DataFrame) -> None:
    plt = _plt()
    fig, axes = plt.subplots(1, 4, figsize=(15, 3.6), dpi=105, sharey=True)
    cols = [("span_re_lt_1e5", engine.BANDS[0]), ("span_re_1e5_5e5", engine.BANDS[1]),
            ("span_re_5e5_3e6", engine.BANDS[2]), ("span_re_gt_3e6", engine.BANDS[3])]
    for ax, t in zip(axes, WING_TYPES):
        g = df[(df["type"] == t) & (df["alpha_deg"] == 0)].groupby("mach")[[c for c, _ in cols]].mean()
        ax.stackplot(g.index, *[100 * g[c] for c, _ in cols], colors=[b[3] for _, b in cols], alpha=0.9,
                     labels=[f"Re {b[2]}" for _, b in cols])
        ax.set_title(NAME[t], color=COL[t], fontweight="bold"); ax.set_xlabel("flight Mach"); ax.set_ylim(0, 100)
        _clean(ax)
    axes[0].set_ylabel("share of the semi-span [%]")
    axes[-1].legend(fontsize=7.5, frameon=False, loc="lower right")
    fig.suptitle("Which Re band the wing sits in, by flight Mach (mean over focus wings, all section sets and altitudes)",
                 x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(DOCS / "flow_re_bands.png")
    plt.close(fig)


def fig_categories(df: pd.DataFrame) -> None:
    """Most common model answer per (Mach, angle) cell, the median SA bias in it, and where the wings
    are in level flight at a real wing loading (outlined)."""
    plt = _plt()
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch, Rectangle
    cols = ["#2E8B57", "#E0A030", "#C0392B", "#9AA5B1"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.4), dpi=105, sharey=True)
    axes = axes.ravel()
    for ax, t in zip(axes, WING_TYPES):
        d = df[(df["type"] == t) & (df["set"] == "A")]
        g = d.groupby(["alpha_deg", "mach"])
        piv = g["category"].agg(lambda s: np.bincount(s.astype(int), minlength=4).argmax()).unstack()
        med = g["sa_bias"].median().unstack()
        lvl = g["level_flight"].mean().unstack()
        ax.pcolormesh(piv.columns, piv.index, piv.values, cmap=ListedColormap(cols), vmin=-0.5, vmax=3.5, shading="nearest")
        dm, da = np.diff(piv.columns).min(), np.diff(piv.index).min()
        for i, a in enumerate(piv.index):
            for j, M in enumerate(piv.columns):
                v = med.values[i, j]
                ax.text(M, a, "–" if not np.isfinite(v) else f"{100 * v:+.0f}".replace("-", "−"), ha="center", va="center",
                        fontsize=8.5, color="white")
                if lvl.values[i, j] >= 0.5:
                    ax.add_patch(Rectangle((M - dm / 2, a - da / 2), dm, da, fill=False, ec="#111111", lw=1.8))
        ax.set_title(f"{NAME[t]} (suggested sections)", color=COL[t], fontweight="bold", fontsize=10)
        ax.set_xlabel("flight Mach")
    for ax in axes[::2]:
        ax.set_ylabel("root angle [°]")
    h = [Patch(color=c, label=l) for c, l in zip(cols, engine.CATEGORIES)]
    h.append(Patch(fc="none", ec="#111111", lw=1.8, label="half or more of the wings in level flight here"))
    fig.legend(handles=h, loc="lower center", ncol=3, fontsize=8.5, frameon=False)
    fig.suptitle("Proposed model, most common answer per condition; numbers: median SA drag error [%]",
                 x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.95))
    fig.savefig(DOCS / "flow_categories.png")
    plt.close(fig)


def fig_sensitivity(sens: dict) -> None:
    plt = _plt()
    ins, outs = list(INPUTS), list(OUTPUTS)
    for kind, title in (("eta2", "First-order index η² (share of variance one input explains alone; for wing inputs, values up to "
                                 "about 0.05 are noise: 200 wings per family, see dihedral)"),
                        ("perm", "Permutation importance of a gradient-boosted model (includes interactions; sums to 1)")):
        fig, axes = plt.subplots(1, 2, figsize=(14, 5.6), dpi=105, gridspec_kw={"wspace": 0.04})
        for ax, fam in zip(axes, FAMILIES):
            m = np.array([[sens[fam][o][kind][i] for o in outs] for i in ins])
            im = ax.imshow(m, cmap="Blues", vmin=0, vmax=max(0.5, np.nanmax(m)), aspect="auto")
            for a in range(len(ins)):
                for b in range(len(outs)):
                    v = m[a, b]
                    if np.isfinite(v) and v >= 0.02:
                        sgn = sens[fam][outs[b]]["spearman"][ins[a]]
                        tag = "" if not np.isfinite(sgn) or abs(sgn) < 0.05 else ("+" if sgn > 0 else "−")
                        ax.text(b, a, f"{v:.2f}{tag}", ha="center", va="center", fontsize=7.5,
                                color="white" if v > 0.35 else INK)
            ax.set_xticks(range(len(outs))); ax.set_xticklabels([OUTPUTS[o] for o in outs], rotation=25, ha="right", fontsize=8)
            ax.set_yticks(range(len(ins))); ax.set_yticklabels([INPUTS[i] for i in ins] if fam == "tailless" else [], fontsize=8)
            r2 = ", ".join(f"{sens[fam][o]['r2']:.2f}" for o in outs)
            ax.set_title(f"{fam} (model R² per output: {r2})" if kind == "perm" else fam, fontsize=9.5)
        fig.colorbar(im, ax=axes, shrink=0.8, pad=0.01)
        fig.suptitle(title + ". Sign: Spearman direction (+ grows with the input).", x=0.01, ha="left", fontsize=10.5)
        fig.savefig(DOCS / f"flow_sensitivity_{kind}.png", bbox_inches="tight")
        plt.close(fig)


def fig_partial(df: pd.DataFrame) -> None:
    """Binned medians of the SA bias against the strongest continuous inputs."""
    plt = _plt()
    xs = [("mean_chord_m", "mean chord [m]"), ("aspect_ratio", "aspect ratio"), ("washout_deg", "washout [°]"),
          ("max_sweep_deg", "max LE sweep [°]"), ("taper", "taper"), ("dihedral_p1_deg", "dihedral [°] (no effect expected)")]
    fig, axes = plt.subplots(2, 3, figsize=(15, 7.4), dpi=105, sharey=True)
    d = df[df["realistic_speed"] & (df["set"] == "A")]
    for ax, (c, lab) in zip(axes.flat, xs):
        for t in WING_TYPES:
            dd = d[d["type"] == t]
            q = pd.qcut(dd[c].rank(method="first"), 8, labels=False)
            g = dd.groupby(q).agg(x=(c, "median"), y=("sa_bias", "median"), lo=("sa_bias", lambda s: s.quantile(0.25)),
                                  hi=("sa_bias", lambda s: s.quantile(0.75)))
            ax.plot(g["x"], 100 * g["y"], marker="o", ms=3, color=COL[t], label=NAME[t])
            ax.fill_between(g["x"], 100 * g["lo"], 100 * g["hi"], color=COL[t], alpha=0.1)
        ax.set_xlabel(lab); _clean(ax)
    for ax in axes[:, 0]:
        ax.set_ylabel("SA drag error [%]")
    axes[0, 0].legend(fontsize=8, frameon=False)
    fig.suptitle("SA drag error against single wing inputs (suggested sections, realistic speeds; median and middle half over "
                 "all other inputs)", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(DOCS / "flow_partial.png")
    plt.close(fig)


def fig_checks(chk: dict, tab: dict, bl: dict) -> None:
    plt = _plt()
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), dpi=105)
    ax = axes[0]
    keys = ["ncrit_5", "ncrit_11", "mach0", "strips1", "strips5", "no_induced"]
    short = {"ncrit_5": "N_crit 5 (Tu 0.37 %)", "ncrit_11": "N_crit 11 (Tu 0.03 %)", "mach0": "no compressibility",
             "strips1": "7 strips", "strips5": "19 strips", "no_induced": "no induced angle"}
    data = [100 * np.array(chk[k]["delta_bias"]) for k in keys]
    ax.boxplot(data, orientation="horizontal", showfliers=False, widths=0.6)
    ax.set_yticks(range(1, len(keys) + 1)); ax.set_yticklabels([short[k] for k in keys], fontsize=8)
    ax.axvline(0, color=MUTED, lw=0.8); ax.set_xlabel("change of the SA drag error [percentage points]")
    ax.set_title("Same wings and conditions, one assumption changed", fontsize=9.5); _clean(ax)
    d = pd.DataFrame(tab["rows"])
    for ax, (col, lab) in zip(axes[1:], (("cd", "profile drag CD"), ("xtr", "upper transition x_tr / c"))):
        for mode, c in (("free", "#0C5EA8"), ("trip", "#C0392B")):
            dd = d[d["mode"] == mode]
            if col == "xtr" and mode == "trip":
                continue
            ax.scatter(dd[f"direct_{col}"], dd[f"table_{col}"], s=10, color=c, alpha=0.6, label=mode)
        lim = [np.nanmin(d[[f"direct_{col}", f"table_{col}"]].values), np.nanmax(d[[f"direct_{col}", f"table_{col}"]].values)]
        ax.plot(lim, lim, color=MUTED, lw=0.8)
        if col == "cd":
            ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel(f"direct XFOIL {lab}"); ax.set_ylabel(f"section table {lab}")
        ax.legend(fontsize=8, frameon=False); _clean(ax)
    axes[1].set_title(f"Tables vs direct XFOIL ({tab['n']} runs): CD median error "
                      f"{100 * tab['free']['cd_rel_median']:.1f} % (free), {100 * tab['trip']['cd_rel_median']:.1f} % (tripped)", fontsize=9)
    axes[2].set_title(f"x_tr median error {tab['free']['xtr_abs_median']:.3f} c; bubble yes/no agrees "
                      f"{100 * tab['free'].get('bubble_agree', np.nan):.0f} %", fontsize=9)
    fig.tight_layout()
    fig.savefig(DOCS / "flow_checks.png")
    plt.close(fig)


def fig_bias_vs_re(df: pd.DataFrame) -> None:
    """The main trend: SA drag error against the wing's mean Re, one line per root angle (suggested sections)."""
    plt = _plt()
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.8), dpi=105, sharey=True, sharex=True)
    axes = axes.ravel()
    cmap = plt.get_cmap("viridis")
    alphas = sorted(df["alpha_deg"].unique())
    for ax, t in zip(axes, WING_TYPES):
        d = df[(df["type"] == t) & (df["set"] == "A")]
        ax.hexbin(np.log10(d["re_mean"]), 100 * d["sa_bias"], gridsize=40, cmap="Greys", mincnt=1, bins="log", alpha=0.35,
                  extent=(4.3, 6.9, -40, 160))
        edges = np.linspace(4.3, 6.9, 14)
        for k, a in enumerate(alphas):
            dd = d[d["alpha_deg"] == a]
            g = dd.groupby(pd.cut(np.log10(dd["re_mean"]), edges))["sa_bias"]
            med, cnt = g.median(), g.count()
            x = np.array([iv.mid for iv in med.index])
            ok = (cnt.values >= 30) & np.isfinite(med.values)
            ax.plot(x[ok], 100 * med.values[ok], color=cmap(k / max(1, len(alphas) - 1)), lw=1.8, label=f"{a:g}°")
        ax.axhspan(-100 * engine.SA_OK, 100 * engine.SA_OK, color="#2E8B57", alpha=0.12)
        ax.axvline(5, color="#C0392B", lw=0.8, ls=":")
        ax.set_title(f"{NAME[t]}: {d['set_label'].iloc[0].replace(' (suggested)', '')}", color=COL[t], fontweight="bold", fontsize=9.5)
        ax.set_ylim(-40, 160); _clean(ax)
    for ax in axes[2:]:
        ax.set_xlabel("log₁₀ mean Re of the wing")
    for ax in axes[::2]:
        ax.set_ylabel("SA drag error [%]")
    axes[1].legend(title="root angle", fontsize=8, title_fontsize=8, frameon=False, loc="upper right", ncol=2)
    fig.suptitle("Fully turbulent SA against free transition, by the wing's mean Re (suggested sections)\n"
                 "line: median per root angle; grey: all rows; green band: ±10 %; dotted: Re 10⁵", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(DOCS / "flow_bias_vs_re.png")
    plt.close(fig)


def fig_groups(sens: dict) -> None:
    """What sets each output: the wing, the sections or the flight condition (alone and with interactions)."""
    plt = _plt()
    outs = list(OUTPUTS)
    gcol = {"wing shape": "#0C5EA8", "sections": "#B07000", "flight condition": "#2E8B57"}
    fig, axes = plt.subplots(2, 1, figsize=(12, 7.4), dpi=105, sharex=True)
    for ax, fam in zip(axes, FAMILIES):
        y = np.arange(len(outs))
        left = np.zeros(len(outs))
        for g, c in gcol.items():
            v = np.array([sens[fam][o]["group_first"][g] for o in outs])
            ax.barh(y, 100 * v, left=100 * left, color=c, height=0.6, label=f"{g} alone")
            for yi, (l0, vi) in enumerate(zip(left, v)):
                if vi > 0.06:
                    ax.text(100 * (l0 + vi / 2), yi, f"{100 * vi:.0f}", ha="center", va="center", color="white", fontsize=7.5)
            left += v
        r2 = np.array([sens[fam][o]["r2"] for o in outs])
        inter = np.clip(r2 - left, 0, None)
        ax.barh(y, 100 * inter, left=100 * left, color="#B8C0C8", height=0.6, label="together only (interactions)")
        for yi, o in enumerate(outs):
            tt = "  ".join(f"{g.split()[0]} {100 * sens[fam][o]['group_total'][g]:.0f}" for g in gcol)
            ax.text(101, yi, f"total: {tt}", va="center", fontsize=8, color=MUTED)
        ax.set_yticks(y); ax.set_yticklabels([OUTPUTS[o] for o in outs], fontsize=9)
        ax.set_xlim(0, 140); ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_title(fam, fontsize=10.5, loc="left"); _clean(ax); ax.invert_yaxis()
    axes[-1].set_xlabel("share of the variance [%]")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, fontsize=8, frameon=False, loc="lower center", ncol=4)
    fig.suptitle("What sets each output: the wing, the sections or how it flies\n(gradient-boosted model; bars: each group alone, "
                 "grey: only together; 'total' includes interactions)", x=0.01, ha="left", fontsize=10.5)
    fig.tight_layout(rect=(0, 0.06, 1, 0.92))
    fig.savefig(DOCS / "flow_groups.png")
    plt.close(fig)


# ============================================================================================ conclusions
def numbers(df: pd.DataFrame, sens: dict, chk: dict, tab: dict, bl: dict) -> dict:
    sp = df[df["realistic_speed"]]                 # every set (per-set tables)
    d = realistic(df)                              # headline statistics: sets that can trim the wing
    out = {"rows": int(len(df)), "rows_realistic": int(len(d)), "rows_realistic_speed": int(len(sp)),
           "wings": int(df.groupby(["type", "wing"]).ngroups),
           "conditions": int(df.groupby(["mach", "altitude_m", "alpha_deg"]).ngroups),
           "baseline": "induced angle included (uniform, elliptic, iterated)"}
    out["bias"] = {}
    for t in WING_TYPES:
        for s in sorted(sp["set"].unique()):
            xx = sp[(sp["type"] == t) & (sp["set"] == s)]
            x = xx["sa_bias"].dropna()
            out["bias"][f"{t}|{s}"] = {"label": xx["set_label"].iloc[0], "trims": bool(xx["realistic_set"].iloc[0]),
                                       "median": float(x.median()), "q10": float(x.quantile(0.1)), "q90": float(x.quantile(0.9)),
                                       "share_sa_ok": float((x.abs() < engine.SA_OK).mean())}
    allb = d["sa_bias"].dropna()
    out["bias_all"] = {"median": float(allb.median()), "q10": float(allb.quantile(0.1)), "q90": float(allb.quantile(0.9)),
                       "share_sa_ok": float((allb.abs() < engine.SA_OK).mean()), "share_negative": float((allb < 0).mean())}
    out["categories"] = {engine.CATEGORIES[k]: float(v) for k, v in d["category"].value_counts(normalize=True).sort_index().items()}
    by_a = d.groupby("alpha_deg")["sa_bias"].median()
    out["bias_by_alpha"] = {f"{k:g}": float(v) for k, v in by_a.items()}
    by_m = d.groupby("mach")["sa_bias"].median()
    out["bias_by_mach"] = {f"{k:g}": float(v) for k, v in by_m.items()}
    out["bubble_span_by_alpha"] = {f"{k:g}": float(v) for k, v in d.groupby("alpha_deg")["bubble_span"].mean().items()}
    out["lam_by_mach"] = {f"{k:g}": float(v) for k, v in d.groupby("mach")["lam_upper"].median().items()}
    out["low_re_share_by_type"] = {t: float((d[d["type"] == t]["span_re_lt_1e5"] > 0).mean()) for t in WING_TYPES}
    out["te_sep_by_alpha"] = {f"{k:g}": float(v) for k, v in d.groupby("alpha_deg")["te_sep_span"].mean().items()}
    out["conv_by_alpha"] = {f"{k:g}": float(v) for k, v in d.groupby("alpha_deg")["conv_span"].mean().items()}
    out["crossflow_share"] = {t: float(d[d["type"] == t]["crossflow_risk"].mean()) for t in WING_TYPES}
    out["top_inputs"] = {fam: {o: sorted(((v, k) for k, v in sens[fam][o]["perm"].items()), reverse=True)[:3]
                               for o in OUTPUTS} for fam in FAMILIES}
    out["eta2"] = {fam: {o: sens[fam][o]["eta2"] for o in OUTPUTS} for fam in FAMILIES}
    out["r2"] = {fam: {o: sens[fam][o]["r2"] for o in OUTPUTS} for fam in FAMILIES}
    out["groups_first"] = {fam: {o: sens[fam][o]["group_first"] for o in OUTPUTS} for fam in FAMILIES}
    out["groups_total"] = {fam: {o: sens[fam][o]["group_total"] for o in OUTPUTS} for fam in FAMILIES}
    out["spearman"] = {fam: {o: sens[fam][o]["spearman"] for o in OUTPUTS} for fam in FAMILIES}
    out["checks"] = {k: {kk: vv for kk, vv in v.items() if kk != "delta_bias"} for k, v in chk.items()}
    out["tables_vs_direct"] = {k: v for k, v in tab.items() if k != "rows"}
    out["blend_rule"] = bl
    out["altitude_effect"] = _paired_altitude(d)
    lf = df[df["level_flight"]]
    out["level_flight"] = {
        "share_rows": float(df["level_flight"].mean()),
        "share_by_type": {t: float(df[df["type"] == t]["level_flight"].mean()) for t in WING_TYPES},
        "bias": {t: {"median": float(lf[lf["type"] == t]["sa_bias"].median()), "q10": float(lf[lf["type"] == t]["sa_bias"].quantile(0.1)),
                     "q90": float(lf[lf["type"] == t]["sa_bias"].quantile(0.9)),
                     "share_sa_ok": float((lf[lf["type"] == t]["sa_bias"].abs() < engine.SA_OK).mean()),
                     "bubble_span_mean": float(lf[lf["type"] == t]["bubble_span"].mean()),
                     "te_sep_span_mean": float(lf[lf["type"] == t]["te_sep_span"].mean()),
                     "low_re_share": float((lf[lf["type"] == t]["span_re_lt_1e5"] > 0).mean()),
                     "lam_upper_median": float(lf[lf["type"] == t]["lam_upper"].median())} for t in WING_TYPES},
        "categories": {engine.CATEGORIES[k]: float(v) for k, v in lf["category"].value_counts(normalize=True).sort_index().items()},
        "bias_all": {"median": float(lf["sa_bias"].median()), "q10": float(lf["sa_bias"].quantile(0.1)),
                     "q90": float(lf["sa_bias"].quantile(0.9)), "share_sa_ok": float((lf["sa_bias"].abs() < engine.SA_OK).mean())},
        "cl3d": {"median": float(lf["cl3d"].median()), "q10": float(lf["cl3d"].quantile(0.1)), "q90": float(lf["cl3d"].quantile(0.9))},
    }
    out["by_set"] = {}
    for t in WING_TYPES:
        for st in sorted(sp["set"].unique()):
            x = sp[(sp["type"] == t) & (sp["set"] == st)]
            out["by_set"][f"{t}|{st}"] = {"label": x["set_label"].iloc[0], "trims": bool(x["realistic_set"].iloc[0]),
                                         "bubble_span_mean": float(x["bubble_span"].mean()),
                                         "te_sep_span_mean": float(x["te_sep_span"].mean()), "conv_span_mean": float(x["conv_span"].mean()),
                                         "lam_upper_median": float(x["lam_upper"].median()),
                                         "cd_free_median": float(x["cd_free"].median()), "cd_trip_median": float(x["cd_trip"].median())}
    lo = d[d["span_re_lt_1e5"] > 0.5]["sa_bias"].dropna()
    out["low_re_rows"] = {"n": int(len(lo)), "bias_median": float(lo.median()) if len(lo) else None,
                          "share_negative": float((lo < 0).mean()) if len(lo) else None}
    w = d[d["set"] == "A"].groupby(["type", "wing"])["sa_bias"].median()
    out["wing_spread"] = {t: {f"q{q}": float(w[t].quantile(q / 100)) for q in (10, 50, 90)} for t in WING_TYPES}
    out["median_ci"] = bootstrap_median_ci(d)
    out["lam_by_alpha"] = {f"{k:g}": float(v) for k, v in d.groupby("alpha_deg")["lam_upper"].median().items()}
    out["bubble_span_by_mach"] = {f"{k:g}": float(v) for k, v in d.groupby("mach")["bubble_span"].mean().items()}
    out["bubble_extent"] = _bubble_extent(d)
    out["level_flight"]["bias_by_mach"] = {f"{k:g}": float(v) for k, v in lf.groupby("mach")["sa_bias"].median().items()}
    out["level_flight"]["bias_by_alpha"] = {f"{k:g}": float(v) for k, v in lf.groupby("alpha_deg")["sa_bias"].median().items()}
    out["no_answer_by_alpha"] = {f"{k:g}": int(v) for k, v in df[df["category"] == 3].groupby("alpha_deg").size().items()}
    out["pairs"] = pair_differences(d)
    return out


def _bubble_extent(d: pd.DataFrame) -> dict:
    """Where on the chord the upper-surface bubbles sit (rows with a bubble): start and end quantiles."""
    b = d[d["bubble_span"] > 0]
    end = b["bubble_start"] + b["bubble_len"]
    return {"start_q05": float(b["bubble_start"].quantile(0.05)), "start_median": float(b["bubble_start"].median()),
            "end_median": float(end.median()), "end_q95": float(end.quantile(0.95)),
            "share_outside_30_70": float(((b["bubble_start"] < 0.3) | (end > 0.7)).mean()),
            "start_median_by_alpha": {f"{k:g}": float(v) for k, v in b.groupby("alpha_deg")["bubble_start"].median().items()},
            "lam_lower_median": float(d["lam_lower"].median())}


def pair_differences(d: pd.DataFrame, n_per_group: int = 400, seed: int = 1) -> dict:
    """Does SA's error cancel between similar wings? Random pairs of wings with the same type, section set,
    Mach and altitude and nearly the same lift (|delta CL| < 0.03): SA's error on the profile-drag difference
    in drag counts, and how often SA ranks the pair the other way round."""
    rng = np.random.default_rng(seed)
    errs, flips, gaps = [], [], []
    x = d.dropna(subset=["cd_free", "cd_trip", "cl2d"])
    for _, g in x.groupby(["type", "set", "mach", "altitude_m"]):
        cl, cf, ct = g["cl2d"].values, g["cd_free"].values, g["cd_trip"].values
        ia, ib = rng.integers(0, len(g), n_per_group), rng.integers(0, len(g), n_per_group)
        m = (ia != ib) & (np.abs(cl[ia] - cl[ib]) < 0.03)
        ia, ib = ia[m], ib[m]
        df_, dt_ = cf[ia] - cf[ib], ct[ia] - ct[ib]
        errs.append(np.abs(dt_ - df_) * 1e4); flips.append(np.sign(dt_) != np.sign(df_)); gaps.append(np.abs(df_) * 1e4)
    e, f, gp = np.concatenate(errs), np.concatenate(flips), np.concatenate(gaps)
    mid = (gp >= 2) & (gp <= 10)
    return {"n": int(len(e)), "err_counts_median": float(np.median(e)), "err_counts_q90": float(np.quantile(e, 0.9)),
            "share_above_2_counts": float((e > 2).mean()), "share_flipped": float(f.mean()),
            "share_flipped_gap_2_10": float(f[mid].mean()) if mid.any() else None}


def bootstrap_median_ci(d: pd.DataFrame, n_boot: int = 300, seed: int = 3) -> dict:
    """95 % interval of the median SA error per type when the wings are resampled (rows of one wing stay
    together): how precisely 100 wings per type pin the statistics down."""
    rng = np.random.default_rng(seed)
    out = {}
    for t in WING_TYPES:
        g = [x.dropna().values for _, x in d[d["type"] == t].groupby("wing")["sa_bias"]]
        meds = [float(np.median(np.concatenate([g[i] for i in rng.integers(0, len(g), len(g))]))) for _ in range(n_boot)]
        out[t] = {"lo": float(np.quantile(meds, 0.025)), "hi": float(np.quantile(meds, 0.975)), "n_wings": len(g)}
    return out


def _paired_altitude(d: pd.DataFrame) -> dict:
    key = ["type", "wing", "set", "mach", "alpha_deg"]
    a = d[d["altitude_m"] == 0][key + ["sa_bias", "lam_upper"]]
    b = d[d["altitude_m"] == 3048][key + ["sa_bias", "lam_upper"]]
    m = a.merge(b, on=key, suffixes=("_0", "_3048"))
    dl = (m["sa_bias_3048"] - m["sa_bias_0"]).dropna()
    return {"n": int(len(m)), "bias_change_median": float(dl.median()), "bias_change_q05": float(dl.quantile(0.05)),
            "bias_change_q95": float(dl.quantile(0.95)),
            "lam_change_median": float((m["lam_upper_3048"] - m["lam_upper_0"]).median())}


def summary_for_tool(df: pd.DataFrame) -> dict:
    """Per type: quantiles of the main metrics over realistic speeds and sets (the tool shows where a wing sits)."""
    d = realistic(df)
    out = {}
    for t in WING_TYPES:
        out[t] = {}
        for c in ("sa_bias", "lam_upper", "bubble_span", "te_sep_span", "re_mean", "span_re_lt_1e5"):
            x = d[d["type"] == t][c].dropna()
            out[t][c] = {f"q{q}": float(x.quantile(q / 100)) for q in (5, 10, 25, 50, 75, 90, 95)}
    return out


PARTS = ("figures", "sensitivity", "checks", "tables", "blends")


def main(argv=None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Trends, statistics, sensitivity and checks of the flow dataset.")
    ap.add_argument("--only", nargs="+", choices=PARTS, help="run these parts (results of the others are read from the cache)")
    a = ap.parse_args(argv)
    run = set(a.only or PARTS)
    cache = OUT / "analysis_parts.json"
    parts = json.loads(cache.read_text()) if cache.exists() else {}
    t0 = time.time()
    df = pd.read_csv(OUT / "dataset.csv.gz")
    print(f"dataset {len(df):,} rows ({time.time() - t0:.0f} s)", flush=True)

    def save():
        cache.write_text(json.dumps(parts, default=float))

    if "figures" in run:
        fig_section_maps(); fig_distributions(df); fig_trends(df); fig_re_bands(df); fig_categories(df)
        fig_partial(df); fig_bias_vs_re(df)
        print(f"figures done ({time.time() - t0:.0f} s)", flush=True)
    if "sensitivity" in run:
        parts["sens"] = sensitivity(df); save()
        print(f"sensitivity done ({time.time() - t0:.0f} s)", flush=True)
    if "sens" in parts:
        fig_sensitivity(parts["sens"]); fig_groups(parts["sens"])
    if "checks" in run:
        parts["chk"] = check_variants(); save()
        print(f"assumption checks done ({time.time() - t0:.0f} s)", flush=True)
    if "tables" in run:
        parts["tab"] = check_tables(); save()
        print(f"tables vs direct XFOIL done ({time.time() - t0:.0f} s)", flush=True)
    if "blends" in run:
        parts["bl"] = check_blends(); save()
    if all(k in parts for k in ("sens", "chk", "tab", "bl")):
        fig_checks(parts["chk"], parts["tab"], parts["bl"])
        res = numbers(df, parts["sens"], parts["chk"], parts["tab"], parts["bl"])
        (DOCS / "flow_analysis.json").write_text(json.dumps(res, indent=1, default=float))
        (DOCS / "flow_summary.json").write_text(json.dumps(summary_for_tool(df), indent=1))
        print(f"done: docs/flow_analysis.json ({time.time() - t0:.0f} s)")
    else:
        print("parts missing for the summary: " + ", ".join(k for k in ("sens", "chk", "tab", "bl") if k not in parts))


if __name__ == "__main__":
    main()
