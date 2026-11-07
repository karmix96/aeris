"""The flow dataset: every focus wing x section set x Mach x angle x altitude, same assumptions.

First approach (the record): made at real size and real speed before 7 Nov 2026, with the section tables built
before the nose fix (decision 64). Not rebuilt: since decision 70 every wing is built at unit mean chord, so a rerun
as it is would put every wing at a 1 m mean chord at the real speeds (the wrong Re).

    python -m cfdauto.flowmap.dataset            # writes data/flowdata/dataset.csv.gz (about 200,000 rows)

Each row is one wing at one flight condition with one section set: the inputs (geometry, sections,
Mach, altitude, root angle) and the wing metrics from the engine (Re along the span, transition,
bubbles, trailing-edge separation, the profile-drag bias of fully turbulent SA, the model category).
Baseline (2 Nov 2026): the induced angle is included (engine.evaluate, induced=True). A section set marked
`trims: false` in configs/flowmap.yaml (a non-reflexed set on a tailless wing) cannot trim: its rows are
kept, flagged realistic_set = False, and never count as level flight.
"""

from __future__ import annotations

import argparse
import itertools
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from ..geometry.build import load_set
from ..geometry.params import FAMILY_OF, GEOMETRY_ROOT, TAILLESS_TYPES, VARIABLES, WING_TYPES, load_config, resolve
from ..geometry.planform import build_planform
from . import engine

CONFIG = GEOMETRY_ROOT / "configs" / "flowmap.yaml"
OUT = GEOMETRY_ROOT / "data" / "flowdata"


def load_flow_config() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def wing_inputs(spec, vec) -> dict:
    v = resolve(spec, vec)
    pf = build_planform(spec, v)
    span, area = 2 * pf.semi_span, pf.area()
    d = {k: float(v[k]) for k in VARIABLES}
    d |= {"full_span_m": span, "mean_chord_m": area / span, "taper": float(pf.chord[-1] / pf.chord[0]),
          "washout_deg": float(v["twist0_deg"] - v["twist3_deg"]), "max_sweep_deg": float(np.max(pf.sweep_le_deg))}
    return d


def wing_loading_band(full_span_m, family, fc: dict) -> tuple[np.ndarray, np.ndarray]:
    """Real-wing wing-loading band [N/m^2] for this full span and family (configs/flowmap.yaml)."""
    lf = fc["level_flight"]
    off = np.vectorize(lambda f: lf["offset"][f])(np.asarray(family)) if np.ndim(family) else lf["offset"][family]
    c = 10 ** (lf["a"] + off + lf["k"] * np.log10(np.asarray(full_span_m, float)))
    return c / lf["factor"], c * lf["factor"]


def conditions(fc: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    g = list(itertools.product(fc["dataset"]["mach"], fc["dataset"]["altitude_m"], fc["dataset"]["alpha_deg"]))
    a = np.array(g, float)
    return a[:, 0], a[:, 1], a[:, 2]


def build(types=WING_TYPES, n_wings: int | None = None, set_name: str = "training_focus", ncrit: float = 9.0,
          induced: bool = True, n_per_panel: int | None = None, mach_in_tables=None, fc: dict | None = None) -> pd.DataFrame:
    cfg, fc = load_config(), fc or load_flow_config()
    mach, alt, alpha = conditions(fc)
    npp = n_per_panel or fc["dataset"]["strips_per_panel"]
    rows = []
    for t in types:
        spec = cfg.types[t]
        vecs = load_set(t, set_name)["vectors"]
        if n_wings:
            vecs = vecs[:n_wings]
        for wi, vec in enumerate(vecs):
            base = wing_inputs(spec, vec)
            for st in fc["section_sets"][t]:
                ws = engine.wing_strips(spec, vec, st["sections"], npp)
                r = engine.evaluate(ws, mach, alt, alpha, ncrit=ncrit, induced=induced,
                                    mach_in_tables=(None if mach_in_tables is None else np.full(mach.shape, mach_in_tables)))
                m = engine.metrics(ws, r)
                df = pd.DataFrame({k: v for k, v in m.items()})
                df["mach"], df["altitude_m"], df["alpha_deg"], df["speed_m_s"] = mach, alt, alpha, r["speed"]
                df["type"], df["family"], df["wing"], df["set"], df["set_label"] = t, FAMILY_OF[t], wi, st["id"], st["label"]
                df["realistic_set"] = bool(st.get("trims", True))
                for k, v in base.items():
                    df[k] = v
                rows.append(df)
    out = pd.concat(rows, ignore_index=True)
    out["category_name"] = [engine.CATEGORIES[i] for i in out["category"]]
    lo = {f: fc["dataset"]["realistic_mach"][f] for f in ("tailless", "conventional")}
    out["realistic_speed"] = [lo[f][0] - 1e-9 <= M <= lo[f][1] + 1e-9 for f, M in zip(out["family"], out["mach"])]
    wl, wh = wing_loading_band(out["full_span_m"].values, out["family"].values, fc)
    out["ws_band_lo"], out["ws_band_hi"] = wl, wh
    out["level_flight"] = ((out["wing_loading"] >= wl) & (out["wing_loading"] <= wh) & (out["conv_span"] >= 0.5)
                           & out["realistic_set"])
    return out


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Build the flow dataset from the section tables. First approach: the "
                                            "record, made at real size and speed before 7 Nov 2026 (not rebuilt; since "
                                            "decision 70 every wing has unit mean chord, so a rerun as it is gives the "
                                            "wrong Re).")
    p.add_argument("--n-wings", type=int)
    p.add_argument("--out", default=str(OUT / "dataset.csv.gz"))
    a = p.parse_args(argv)
    t0 = time.time()
    df = build(n_wings=a.n_wings)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False, float_format="%.6g")
    print(f"{len(df):,} rows, {df.shape[1]} columns, {time.time() - t0:.0f} s -> {a.out}")


if __name__ == "__main__":
    main()
