#!/usr/bin/env python
"""Collect every TRUSTED CFD result into one reproducible archive.

    .venv/bin/python .../collect_dataset.py --out <dir>

Why this is not just a folder of result.json files
---------------------------------------------------
`artifacts/` is globally gitignored and gets wiped. Every number this project
has produced lives there, and a result whose mesh, geometry, solver
configuration and acceptance verdict are gone is not a result -- it is a number
somebody once saw. So the archive goes under 05_s6_cfd_qualification, and it
carries what is needed to BELIEVE each row as well as to reproduce it:

  identity     which geometry, from which set, at which design vector, hashed
  mesh         cell count, folded cells, wall-layer error, quality metrics,
               and the hash of the blocks the CGNS was written from
  solver       git commit, ADflow version, the resolved option dict and its
               hash, and any override (--no-nk, --l2) recorded EXPLICITLY so a
               governed run says so positively rather than by omission
  verdict      the convergence gate's judgement, its window, and the force-tail
               spreads it judged on -- not just "it finished"
  fields       the surface solution itself, gzipped, because cp and y+ per cell
               are the AI-field-prediction payload and cannot be recovered from
               scalars. Volume solutions are 32 MB each and are referenced by
               path and hash rather than copied.

What is deliberately EXCLUDED
------------------------------
Runs the gate did not accept. They are listed in the manifest with their verdict
and their directory, so nothing is hidden, but they do not become rows. A
dataset that quietly contains a solver-frozen run teaches a surrogate that the
frozen answer was right -- and two of the four original gci_C runs were frozen
while looking, by every metric then being checked, exactly like the good ones.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

ARTIFACTS = REPO / "AERIS_MESH_STUDY/artifacts"
QUAL = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification"
ACCEPTABLE = ("ACCEPTED",)


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(REPO), *args],
                             capture_output=True, text=True, timeout=60)
        return out.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def environment() -> dict:
    import env_s8
    try:
        env = env_s8.resolve()
    except SystemExit:
        env = {}
    version = None
    if env.get("mach_python"):
        try:
            version = subprocess.run(
                [env["mach_python"], "-c",
                 "import adflow;print(getattr(adflow,'__version__','unknown'))"],
                capture_output=True, text=True, timeout=180).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            version = None
    return {
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(git("status", "--porcelain")),
        "git_describe": git("describe", "--tags", "--always", "--dirty"),
        "adflow_version": version,
        "mach_python": env.get("mach_python"),
        "mpirun": env.get("mpirun"),
        "host": subprocess.run(["uname", "-a"], capture_output=True,
                               text=True).stdout.strip(),
    }


def avl_for(index: int, args) -> dict | None:
    """The AVL cross-check for one geometry, if it has been run.

    Looked up per geometry rather than passed in, because the pilot runs one AVL
    sweep per design and a row without its low-fidelity counterpart cannot be
    used to fit the multifidelity correction the campaign exists to build.
    """
    for candidate in (ARTIFACTS / "s8_cfd" / f"avl_{index}",
                      ARTIFACTS / "s8_pilot" / f"g{index}" / "avl"):
        sweep = candidate / "avl_sweep.json"
        if sweep.exists():
            rows = json.loads(sweep.read_text())
            return {"points": [{"alpha_deg": r["alpha_deg"], **r.get("raw", {})}
                               for r in rows], "status": "ok",
                    "source": str(candidate)}
    return None


def find_runs(roots: list[Path]) -> list[Path]:
    runs = []
    for root in roots:
        if not root.exists():
            continue
        for candidate in sorted(root.rglob("result.json")):
            if "_superseded" in candidate.parts:
                continue
            runs.append(candidate.parent)
    return runs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roots", type=Path, nargs="+",
                    default=[ARTIFACTS / "s8_cfd", ARTIFACTS / "s8_pilot"])
    ap.add_argument("--gate", type=Path,
                    default=QUAL / "reports/s8_gci_gate.json")
    ap.add_argument("--out", type=Path, default=QUAL / "dataset")
    ap.add_argument("--set-name", default="lhs100_seed42")
    ap.add_argument("--include-rejected", action="store_true",
                    help="write rows for runs the gate did not accept. Off by "
                         "default: a dataset containing a frozen run teaches a "
                         "surrogate that the frozen answer was right.")
    ap.add_argument("--no-fields", action="store_true",
                    help="skip copying surface solutions")
    args = ap.parse_args()

    import dataset_row

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "runs").mkdir(exist_ok=True)
    (args.out / "meshes").mkdir(exist_ok=True)
    if not args.no_fields:
        (args.out / "fields").mkdir(exist_ok=True)

    gate = json.loads(args.gate.read_text()) if args.gate.exists() else None
    verdicts = {}
    if gate:
        for record in gate["results"]:
            verdicts[Path(record["directory"]).name] = record

    runs = find_runs(args.roots)
    print(f"found {len(runs)} runs under {', '.join(str(r) for r in args.roots)}\n")

    cache: dict = {}
    rows, excluded, meshes = [], [], {}
    env = environment()
    for run in runs:
        result = json.loads((run / "result.json").read_text())
        name = run.name
        record = verdicts.get(name)
        verdict = record["verdict"] if record else None
        # level and index: from the directory layout the campaign writes
        level = None
        for candidate in ("gci_CC", "gci_C", "gci_M", "gci_MF", "gci_F", "oh_L3"):
            if name.startswith(candidate) or candidate in str(run):
                level = candidate
                break
        index = 83
        for part in run.parts:
            if part.startswith("g") and part[1:].isdigit():
                index = int(part[1:])
        mesh_dir = run.parent if (run.parent / f"{level}_summary.json").exists() \
            else ARTIFACTS / "s8_gci83"

        if verdict is not None and verdict not in ACCEPTABLE and not args.include_rejected:
            excluded.append({"run": name, "directory": str(run), "verdict": verdict,
                             "reason": "gate verdict is not ACCEPTED"})
            print(f"  EXCLUDED {name:<24} {verdict}")
            continue

        row = dataset_row.build_row(
            run=run, level=level or "unknown", index=index,
            set_name=args.set_name, mesh_dir=mesh_dir, gate=gate,
            avl=avl_for(index, args),
            mach_python=env.get("mach_python"), cache=cache)
        row["run_name"] = name
        row["source_directory"] = str(run)
        row["solver_overrides"] = result.get("solver_overrides", {})
        row["solver_is_governed_configuration"] = result.get(
            "solver_is_governed_configuration")
        row["l2_target"] = result.get("l2_target")
        row["environment"] = {k: env[k] for k in ("git_commit", "adflow_version")}

        # copy the small, essential per-run artefacts
        dest = args.out / "runs" / name
        dest.mkdir(exist_ok=True)
        for fname in ("result.json", "memory_watch.json", "cp_excess_locations.json"):
            src = run / fname
            if src.exists():
                shutil.copy2(src, dest / fname)
        if record:
            (dest / "gate.json").write_text(json.dumps(record, indent=2) + "\n")

        # surface solution: the per-cell cp and y+ payload, gzipped
        surfaces = sorted(run.glob("*surf*.cgns"))
        if surfaces and not args.no_fields:
            target = args.out / "fields" / f"{name}_surf.cgns.gz"
            if not target.exists():
                with open(surfaces[0], "rb") as fin, gzip.open(target, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
            row["surface_field_archive"] = str(target.relative_to(args.out))
            row["surface_field_sha256"] = sha256(surfaces[0])
        volumes = sorted(run.glob("*vol*.cgns"))
        if volumes:
            row["volume_field_source"] = str(volumes[0])
            row["volume_field_sha256"] = sha256(volumes[0])
            row["volume_field_note"] = ("NOT copied: 32 MB per run. It lives under "
                                        "artifacts/, which is gitignored and WIPED. "
                                        "The hash is here so a regenerated file can "
                                        "be checked against the one that produced "
                                        "this row.")

        # mesh summary, once per (level, index)
        key = f"{level}_{index}"
        summary = mesh_dir / f"{level}_summary.json"
        if key not in meshes and summary.exists():
            shutil.copy2(summary, args.out / "meshes" / f"{key}_summary.json")
            s = json.loads(summary.read_text())
            meshes[key] = {"level": level, "index": index, "cells": s["cells"],
                           "folded": s["negative_cells_all_blocks"],
                           "wall_layer_error_m": s["volume"]["wall_layer_error_m"],
                           "frame_mode": s["volume"]["frame_mode"],
                           "blocks_sha256": sha256(mesh_dir / f"{level}_blocks.npz")}
        rows.append(row)
        print(f"  kept     {name:<24} {verdict or 'no gate'}  "
              f"{len(row['missing_fields'])} field(s) absent")

    manifest = {
        "schema_version": "aeris.s8.dataset.v1",
        "purpose": ("Trusted S8 CFD results with the provenance needed to "
                    "reproduce and to believe them. Surrogate-training dataset, "
                    "NOT certification."),
        "environment": env,
        "policy": "AERIS_MESH_STUDY/05_s6_cfd_qualification/policies/s8_campaign_v1.yaml",
        "acceptance": {
            "authority": "convergence_gate.py",
            "criteria": ("at least five orders of residual drop, CL/CD/CMy settled "
                         "over an adaptive tail, residual neither diverging nor "
                         "growing in envelope, and the linear solve not dead"),
            "accepted_verdicts": list(ACCEPTABLE),
            "stopping_rule": "L2Convergence 1e-6; see reports/s8_l2_sensitivity.json",
        },
        "counts": {"runs_found": len(runs), "rows": len(rows),
                   "excluded": len(excluded)},
        "meshes": meshes,
        "excluded_runs": excluded,
        "row_schema": dataset_row.SCHEMA,
        "field_files": {
            "surface": "copied, gzipped, under fields/",
            "volume": "referenced by path and sha256 only; artifacts/ is wiped",
        },
    }
    (args.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (args.out / "rows.json").write_text(json.dumps(rows, indent=2) + "\n")

    print(f"\n  {len(rows)} rows, {len(excluded)} excluded, {len(meshes)} meshes")
    gaps: dict = {}
    for row in rows:
        gaps.update(row["missing_fields"])
    if gaps:
        print("\n  schema fields not filled, and why:")
        for field, why in sorted(gaps.items()):
            print(f"    {field:<32} {why}")
    print(f"\n  wrote {args.out / 'MANIFEST.json'}")
    print(f"  wrote {args.out / 'rows.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
