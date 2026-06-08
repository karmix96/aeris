"""
2D airfoil dataset generator.

Mirrors the 3D aero dataset pipeline:
  aeris airfoil dataset generate
    → airfoil_library/  (ingested)
    → configs/airfoil/xfoil_sweep_v1.yaml
    → data/datasets/<name>/airfoil_dataset.csv
    → data/datasets/<name>/airfoil_failures.csv
    → data/datasets/<name>/airfoil_dataset_manifest.json

One row = one airfoil × one (alpha, Re, Mach, Ncrit) condition.
Group key for ML: airfoil_id.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from aeris.airfoil.library import AirfoilLibrary
from aeris.aero_2d.xfoil_adapter import run_alpha_sweep
from aeris.aero_2d.models import Aero2DResult

_DATASET_CSV = "airfoil_dataset.csv"
_FAILURES_CSV = "airfoil_failures.csv"
_MANIFEST_JSON = "airfoil_dataset_manifest.json"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _load_sweep_config(config_path: Path) -> dict[str, Any]:
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _validate_config(cfg: dict[str, Any]) -> None:
    sweep = cfg.get("sweep", {})
    required = ["alpha_start", "alpha_end", "alpha_step", "reynolds"]
    missing = [k for k in required if k not in sweep]
    if missing:
        raise ValueError(f"xfoil sweep config missing keys: {missing}")
    if not isinstance(sweep["reynolds"], list) or len(sweep["reynolds"]) == 0:
        raise ValueError("sweep.reynolds must be a non-empty list")


def generate_airfoil_dataset(
    *,
    library_dir: Path,
    config_path: Path,
    dataset_root: Path,
    name: str,
    airfoil_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Generate the raw 2D XFOIL dataset.

    Parameters
    ----------
    library_dir: path to the ingested airfoil library
    config_path: path to xfoil_sweep_v1.yaml
    dataset_root: output directory (data/datasets/<name>/)
    name: dataset name string
    airfoil_ids: optional list of airfoil IDs to include (None = all)

    Returns the manifest dict (also written to dataset_root/airfoil_dataset_manifest.json).
    """
    library_dir = library_dir.expanduser().resolve()
    config_path = config_path.expanduser().resolve()
    dataset_root = dataset_root.expanduser().resolve()
    dataset_root.mkdir(parents=True, exist_ok=True)

    cfg = _load_sweep_config(config_path)
    _validate_config(cfg)
    sweep = cfg["sweep"]
    solver_cfg = cfg.get("solver", {})

    alpha_start = float(sweep["alpha_start"])
    alpha_end   = float(sweep["alpha_end"])
    alpha_step  = float(sweep["alpha_step"])
    re_list     = [float(r) for r in sweep["reynolds"]]
    mach_list   = [float(m) for m in sweep.get("mach", [0.0])]
    ncrit       = float(sweep.get("ncrit", 9.0))
    max_iter    = int(solver_cfg.get("max_iter", 100))
    repanel     = bool(solver_cfg.get("repanel", True))

    library = AirfoilLibrary(library_dir)
    all_ids = airfoil_ids if airfoil_ids else library.all_ids()

    success_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    n_conditions = len(re_list) * len(mach_list)
    n_total = len(all_ids)

    print(f"[AERIS 2D] Dataset: {name}")
    print(f"[AERIS 2D] Airfoils: {n_total}  Conditions: {n_conditions} (Re × Mach)")
    print(f"[AERIS 2D] Alpha: {alpha_start} → {alpha_end} step {alpha_step}")

    for i, aid in enumerate(all_ids, 1):
        try:
            rec = library.get_by_id(aid)
        except KeyError as exc:
            failure_rows.append({"airfoil_id": aid, "reason": str(exc)})
            continue

        for re in re_list:
            for mach in mach_list:
                try:
                    results = run_alpha_sweep(
                        airfoil_id=rec.airfoil_id,
                        airfoil_name=rec.name,
                        source_file=rec.source_file,
                        x=rec.x,
                        y=rec.y,
                        alpha_start=alpha_start,
                        alpha_end=alpha_end,
                        alpha_step=alpha_step,
                        reynolds=re,
                        mach=mach,
                        ncrit=ncrit,
                        max_iter=max_iter,
                        repanel=repanel,
                    )
                    for r in results:
                        row = r.to_row()
                        # Append geometry stats as ML features
                        row["alpha_sq"]     = float(r.alpha_deg) ** 2
                        row["t_c"]          = rec.stats.t_c
                        row["camber_max"]   = rec.stats.camber_max
                        row["le_radius"]    = rec.stats.le_radius
                        row["te_angle_deg"] = rec.stats.te_angle_deg
                        success_rows.append(row)

                except Exception as exc:
                    failure_rows.append({
                        "airfoil_id": aid,
                        "airfoil_name": rec.name,
                        "re": re,
                        "mach": mach,
                        "reason": str(exc),
                    })

        if i % 50 == 0 or i == n_total:
            conv = sum(1 for r in success_rows if r.get("converged"))
            print(f"[AERIS 2D]  {i}/{n_total} airfoils done  "
                  f"rows={len(success_rows)}  converged={conv}  failures={len(failure_rows)}")

    # Write CSVs
    success_df = pd.DataFrame(success_rows)
    failure_df  = pd.DataFrame(failure_rows)
    dataset_csv  = dataset_root / _DATASET_CSV
    failures_csv = dataset_root / _FAILURES_CSV
    success_df.to_csv(dataset_csv,  index=False)
    failure_df.to_csv(failures_csv, index=False)

    n_conv = int(success_df["converged"].sum()) if not success_df.empty else 0
    convergence_rate = n_conv / len(success_df) if len(success_df) > 0 else 0.0

    manifest: dict[str, Any] = {
        "schema_version": "airfoil_dataset_v1",
        "dataset_name": name,
        "generated_at_utc": _utc_now(),
        "library_dir": str(library_dir),
        "config_path": str(config_path),
        "solver_id": "xfoil_python",
        "sweep_params": {
            "alpha_start": alpha_start,
            "alpha_end": alpha_end,
            "alpha_step": alpha_step,
            "reynolds": re_list,
            "mach": mach_list,
            "ncrit": ncrit,
            "max_iter": max_iter,
            "repanel": repanel,
        },
        "n_airfoils": len(all_ids),
        "n_airfoils_attempted": len(all_ids),
        "n_airfoils_with_failures": len(set(r.get("airfoil_id","") for r in failure_rows)),
        "total_rows": len(success_rows),
        "converged_rows": n_conv,
        "unconverged_rows": len(success_rows) - n_conv,
        "solver_failure_rows": len(failure_rows),
        "convergence_rate": round(convergence_rate, 4),
        "airfoil_dataset_csv": str(dataset_csv),
        "airfoil_failures_csv": str(failures_csv),
    }
    manifest_path = dataset_root / _MANIFEST_JSON
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[AERIS 2D] Done: {len(success_rows)} rows, {n_conv} converged "
          f"({convergence_rate:.1%}), {len(failure_rows)} failures")
    return manifest
