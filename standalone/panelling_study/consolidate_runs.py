"""Consolidate every cached AVL solve into one flat dataset for offline analysis.

Walks data/panelling_study/cache/<hash>/, reads each native_avl_result.json and
its provenance.json, and writes two analysis-ready files into the study config
dir:

  all_runs.json  — array of one merged record per solve (result + provenance)
  all_runs.csv   — the same, flattened, ready for pandas.read_csv

Deterministic row order (by tag, sample, mesh, angle, control) so the committed
files diff cleanly if the study is ever re-run.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

CACHE = Path("/home/mike_kara/aeris/data/panelling_study/cache")
OUT = Path("/home/mike_kara/aeris/configs/aero/panelling_study")

PROV_ONLY = ("geom_config_sha256", "src_git_sha", "avl_version", "viscous",
             "velocity_mps", "altitude_m", "beta_deg")


def main():
    records = []
    for d in CACHE.iterdir():
        if not d.is_dir():
            continue
        rp = d / "native_avl_result.json"
        if not rp.exists():
            continue
        rec = json.loads(rp.read_text())
        prov_p = d / "provenance.json"
        if prov_p.exists():
            prov = json.loads(prov_p.read_text())
            for k in PROV_ONLY:
                if k in prov and k not in rec:
                    rec[k] = prov[k]
        rec["cache_key"] = d.name
        records.append(rec)

    def sort_key(r):
        return (str(r.get("tag", "")), str(r.get("sample_id", "")),
                r.get("nchordwise", 0), r.get("spanwise", 0),
                float(r.get("cspace", 0) or 0), float(r.get("alpha_deg", 0) or 0),
                float(r.get("control_input_deg", 0) or 0),
                float(r.get("diff_input_deg", 0) or 0))

    records.sort(key=sort_key)

    (OUT / "all_runs.json").write_text(json.dumps(records, indent=1, sort_keys=True))

    # union of all keys, stable column order: identifiers first then the rest
    lead = ["cache_key", "sample_id", "tag", "nchordwise", "spanwise", "cspace",
            "alpha_deg", "control_input_deg", "diff_input_deg", "status", "ok"]
    keys = set()
    for r in records:
        keys.update(r.keys())
    cols = lead + sorted(k for k in keys if k not in lead)

    with (OUT / "all_runs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow(r)

    print(f"consolidated {len(records)} runs")
    print(f"  {OUT/'all_runs.json'}")
    print(f"  {OUT/'all_runs.csv'}  ({len(cols)} columns)")
    # quick provenance sanity: how many distinct settings / samples / tags
    tags = sorted({r.get('tag','') for r in records})
    print("  tags:", ", ".join(t for t in tags if t))
    print("  distinct samples:", len({r.get('sample_id') for r in records}))


if __name__ == "__main__":
    main()
