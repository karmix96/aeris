"""Step-2 HEAVY pyGeo DoE driver — full production generate incl. physical CAD.

The light gate sweep (`validate_config_frame.py --doe`) confirms the neutral loft
is robust. This driver exercises the part that harness skips: the full production
`aeris geometry generate` path — physical CAD (split elevon), STEP export, Gmsh
STEP-import audit, STL/OBJ/VTK — across a set of sampled designs.

It is HEAVY (per-case CAD tessellation + Gmsh audit + tens of MB of STL/STEP), so
it is meant to run on the desktop, NOT in an assistant session. It writes one
production run folder per seed and summarizes each case's QC + STEP-audit outcome.

Usage (desktop):
    PYTHONPATH=src .venv/bin/python -m standalone.pygeo_validation.run_cad_doe \
        --config configs/geometry/paper1_bwb_pygeo_smoke_doe.yaml \
        --seeds 3000,3005,3011,3017,3023 \
        --out-dir data/runs/pygeo_cad_doe

Pick seeds the light sweep already validated (default below = a 5-point spread of
the 3000..3023 smoke set) so a CAD failure is unambiguously a CAD-path issue, not a
bad loft. Rescue the summary JSON into configs/ before wiping data/runs (memory
policy: findings live in configs/).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from aeris.pipeline.geometry_run import run_geometry_generation


def _stamp_config(base_config: Path, seed: int, work_dir: Path) -> Path:
    raw = yaml.safe_load(base_config.read_text(encoding="utf-8"))
    raw.setdefault("geometry", {}).setdefault("generator", {})["seed"] = int(seed)
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / f"{base_config.stem}_seed{seed}.yaml"
    out.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return out


def _dir_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / 1_048_576.0


def _summarize_run(run_root: Path) -> dict:
    """Pull QC + STEP-audit state from a completed run's manifest."""
    out: dict = {"run_root": str(run_root)}
    manifest = run_root / "manifest.json"
    if not manifest.exists():
        out["error"] = "no manifest.json"
        return out
    m = json.loads(manifest.read_text(encoding="utf-8"))
    geo = m.get("geometry") or {}
    pygeo = (geo.get("summary") or {}).get("pygeo") or geo.get("pygeo") or {}
    # Be tolerant of manifest shape; record whatever QC / CAD keys are present.
    out["quality_status"] = pygeo.get("quality_status") or geo.get("quality_status")
    cad = pygeo.get("physical_cad") or geo.get("physical_cad") or {}
    out["cad_status"] = cad.get("status") if isinstance(cad, dict) else None
    out["step_import_ok"] = cad.get("step_import_ok") if isinstance(cad, dict) else None
    out["artifacts_mb"] = round(_dir_size_mb(run_root), 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--seeds", type=str, default="3000,3005,3011,3017,3023",
                    help="Comma-separated generator seeds to sweep.")
    ap.add_argument("--out-dir", type=Path, default=Path("data/runs/pygeo_cad_doe"))
    ap.add_argument("--summary-json", type=Path, default=None,
                    help="Where to write the DoE summary (default: <out-dir>/cad_doe_summary.json).")
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir = args.out_dir / "stamped_configs"

    results = []
    for seed in seeds:
        cfg = _stamp_config(args.config, seed, cfg_dir)
        print(f"[cad-doe] seed {seed}: generating (physical CAD + STEP audit)...")
        exit_code, run_root = run_geometry_generation(cfg)
        entry = {"seed": seed, "exit_code": exit_code}
        if run_root is not None:
            entry.update(_summarize_run(Path(run_root)))
        entry["ok"] = exit_code == 0
        results.append(entry)
        print(f"[cad-doe] seed {seed}: exit={exit_code} "
              f"qc={entry.get('quality_status')} step_ok={entry.get('step_import_ok')} "
              f"size={entry.get('artifacts_mb')}MB")

    summary = {
        "config": str(args.config),
        "generated_utc": datetime.now(UTC).isoformat(),
        "seeds": seeds,
        "n_ok": sum(1 for r in results if r["ok"]),
        "n_total": len(results),
        "results": results,
        "pass": all(r["ok"] for r in results),
    }
    out_json = args.summary_json or (args.out_dir / "cad_doe_summary.json")
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n[cad-doe] {summary['n_ok']}/{summary['n_total']} OK — summary: {out_json}")
    print("[cad-doe] rescue this summary into configs/ before wiping data/runs.")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
