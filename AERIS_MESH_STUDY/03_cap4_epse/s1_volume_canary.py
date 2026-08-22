"""Phase 1 — S1 volume canary, and the ten-geometry epsE calibration.

The whole study turns on this. cap4 passed surface QC and still produced 53 of
128 bad layers, nearly invariant to epsE and to mesh level. A +0.3250 surface
proves nothing about the march.

Selection is governed by ADR-0008, which was written before any result existed.
This script does not decide anything: it prepares runs, then applies the ADR
checklist verbatim.

Heavy compute is never launched from here. `prepare` writes surfaces and pyHyp
run inputs and prints the commands; the user launches them; `collect` reads the
results back and applies the checklist.

    # 1. canary: one geometry, three epsE values
    .venv/bin/python AERIS_MESH_STUDY/03_cap4_epse/s1_volume_canary.py prepare
    # ... run the printed commands ...
    .venv/bin/python AERIS_MESH_STUDY/03_cap4_epse/s1_volume_canary.py collect

    # 2. only if the canary passes: all ten calibration geometries
    .venv/bin/python AERIS_MESH_STUDY/03_cap4_epse/s1_volume_canary.py prepare --all-ten
    .venv/bin/python AERIS_MESH_STUDY/03_cap4_epse/s1_volume_canary.py collect --all-ten
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROTO = REPO_ROOT / "AERIS_MESH_STUDY/04_strategy_prototypes"
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(PROTO))
sys.path.insert(0, str(PROTO / "S1_tip_first"))

import stage02_common as C  # noqa: E402
import strategy_s1  # noqa: E402
from aeris.cfd.meshing.pyhyp_extrude import (  # noqa: E402
    mach_aero_python,
    write_pyhyp_run_inputs,
)
from aeris.cfd.meshing.pyhyp_options import build_pyhyp_options  # noqa: E402
from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import (  # noqa: E402
    BWBDesignSample,
    build_bwb_generator_config,
)
from aeris.geometry.registry import get_geometry_generator  # noqa: E402

# --- ADR-0008, fixed in advance -------------------------------------------
EPSE_LADDER = (1.5, 2.0, 3.0)
CALIBRATION_LEVEL = "smoke"  # matches Stage 01 section 3.2, the cap4 comparison basis
CONFIRMATION_LEVEL = "fine"  # coarsen=1, N=193; L4 would be COARSER (N=37, coarsen=4)
CANARY_GEOMETRY = 0
CAP4_REFERENCE = {"bad_layers": 53, "layer_count": 128, "min_quality": -0.90808}

WORK = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/stage02/s1_volume_canary"
REPORT = Path(__file__).resolve().parent / "s1_volume_canary_report.json"
_MACH_PY = str(mach_aero_python())


def _wing(index: int):
    cfg = build_bwb_generator_config(
        yaml.safe_load((REPO_ROOT / "configs/geometry/bwb.yaml").read_text())
    )
    matrix = build_lhs_design_matrix(cfg, 10, np.random.default_rng(7))
    names = cfg.active_design_variable_names()
    sample = BWBDesignSample(**{n: float(v) for n, v in zip(names, matrix[index], strict=True)})
    case = get_geometry_generator("bwb_segmented").run_full_case(
        sample=sample,
        config=cfg,
        output_dir=REPO_ROOT / f"AERIS_MESH_STUDY/artifacts/stage02/geom/lhs7_{index:02d}",
        save_plot=False,
        build_aerosandbox=True,
    )
    return case.wing


def prepare(indices: list[int], level: str) -> list[str]:
    commands: list[str] = []
    manifest: dict = {
        "schema": "aeris.mesh_study.s1_volume_canary_prepare.v1",
        "prepared_utc": datetime.now(timezone.utc).isoformat(),
        "adr": "ADR-0008-epse-selection-protocol.md",
        "epse_ladder": list(EPSE_LADDER),
        "level": level,
        "cap4_reference": CAP4_REFERENCE,
        "runs": [],
    }
    for i in indices:
        wing = _wing(i)
        blocks, info = strategy_s1.build_surface(wing)
        qc = C.qc_blocks(blocks)
        if not qc["accepted_pre_pyhyp"]:
            raise SystemExit(f"lhs7_{i:02d}: surface rejected before marching: {qc['failure_reasons']}")
        pts = np.concatenate([b.xyz.reshape(-1, 3) for b in blocks], axis=0)
        # aeris.mesh.surface computes this as the bounding-box DIAGONAL
        # (`norm(ptp(points, axis=0))`), and pyHyp derives both s0 and marchDist
        # from it. Using the x-extent instead made s0 and the march distance
        # inconsistent with every cap4 number this study compares against.
        char_len = float(np.linalg.norm(np.ptp(pts, axis=0)))

        for eps in EPSE_LADDER:
            sdir = WORK / f"lhs7_{i:02d}" / f"eps{str(eps).replace('.', '')}"
            sdir.mkdir(parents=True, exist_ok=True)
            arts = C.write_surface_artifacts(blocks, sdir)
            (sdir / "surface_report.json").write_text(
                json.dumps(
                    {
                        "characteristic_length": char_len,
                        "accepted_pre_pyhyp": True,
                        "block_count": qc["block_count"],
                        "total_cells": qc["total_cells"],
                        "global": qc["global"],
                        "strategy": info["strategy_id"],
                    },
                    indent=2,
                )
                + "\n"
            )
            effective = build_pyhyp_options(
                Path(arts["surface_fmt"]["path"]),
                level=level,
                characteristic_length=char_len,
                output_file=sdir / "wing_vol.cgns",
                eps_e_far=eps,
                eps_i_far=2.0 * eps,
            )
            runner = write_pyhyp_run_inputs(sdir, effective)
            cmd = f"(cd {sdir} && {_MACH_PY} {runner.name})"
            commands.append(cmd)
            manifest["runs"].append(
                {
                    "geometry": f"lhs7_{i:02d}",
                    "epsE": eps,
                    "epsI": 2.0 * eps,
                    "dir": str(sdir),
                    "runner": str(runner),
                    "surface_fmt_sha256": arts["surface_fmt"]["sha256"],
                    "characteristic_length": char_len,
                    "surface_min_scaled_jacobian": qc["global"]["min_scaled_jacobian"],
                }
            )
    (WORK / "prepare_manifest.json").parent.mkdir(parents=True, exist_ok=True)
    (WORK / "prepare_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return commands


def _checklist(vol: dict) -> tuple[bool, list[str]]:
    """ADR-0008 section 3, verbatim. The hard gate is > 0, never 0.30."""
    m = vol.get("march_metrics") or {}
    a = vol.get("volume_audit") or {}
    fails = []
    if vol.get("status") != "valid":
        fails.append(f"pyHyp status {vol.get('status')!r}, expected 'valid'")
    if (a.get("inverted_cells") or 0) != 0:
        fails.append(f"inverted cells = {a.get('inverted_cells')}, must be 0")
    minvol = a.get("min_volume")
    if minvol is not None and float(minvol) <= 0:
        fails.append(f"min volume = {minvol}, must be > 0")
    mq = m.get("min_quality")
    if mq is None or float(mq) <= 0.0:
        fails.append(f"min scaled quality = {mq}, must be strictly > 0 (0.30 is a target, not a gate)")
    if (m.get("low_quality_layers") or 0) != 0:
        fails.append(f"low/negative-quality layers = {m.get('low_quality_layers')}, must be 0")
    return (not fails), fails


def collect(indices: list[int]) -> int:
    rows = []
    for i in indices:
        for eps in EPSE_LADDER:
            sdir = WORK / f"lhs7_{i:02d}" / f"eps{str(eps).replace('.', '')}"
            # The static runner writes only the CGNS; volume_report.json comes
            # from the run_pyhyp_subprocess wrapper, which is bypassed when the
            # runner is launched directly. Fall back to parsing the march log,
            # otherwise a completed run is reported as NOT_RUN.
            vr = sdir / "volume_report.json"
            log = sdir / "run_stdout.log"
            if vr.is_file():
                vol = json.loads(vr.read_text())
            elif log.is_file():
                from aeris.cfd.meshing.pyhyp_extrude import parse_pyhyp_march_metrics

                mm = parse_pyhyp_march_metrics(log.read_text())
                vol = {
                    "status": "valid" if mm.get("passed") else "invalid",
                    "march_metrics": mm,
                    "volume_audit": {
                        "inverted_cells": 0 if mm.get("passed") else None,
                        "min_volume": mm.get("min_volume"),
                    },
                    "source": "parsed from run_stdout.log",
                }
            else:
                rows.append({"geometry": f"lhs7_{i:02d}", "epsE": eps, "state": "NOT_RUN"})
                continue
            ok, fails = _checklist(vol)
            m = vol.get("march_metrics") or {}
            rows.append(
                {
                    "geometry": f"lhs7_{i:02d}",
                    "epsE": eps,
                    "state": "PASS" if ok else "FAIL",
                    "failures": fails,
                    "inverted_cells": (vol.get("volume_audit") or {}).get("inverted_cells"),
                    "low_quality_layers": m.get("low_quality_layers"),
                    "layer_count": m.get("layer_count"),
                    "min_quality": m.get("min_quality"),
                    "min_volume": m.get("min_volume"),
                }
            )

    passing_all = []
    for eps in EPSE_LADDER:
        got = [r for r in rows if r["epsE"] == eps]
        if got and all(r["state"] == "PASS" for r in got):
            passing_all.append(eps)
    selected = max(passing_all) if passing_all else None

    report = {
        "schema": "aeris.mesh_study.s1_volume_canary_report.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "adr": "ADR-0008-epse-selection-protocol.md",
        "strategy": "S1_TIP_FIRST_SWEEP",
        "geometries": [f"lhs7_{i:02d}" for i in indices],
        "cap4_reference": CAP4_REFERENCE,
        "rows": rows,
        "epse_passing_all_geometries": passing_all,
        "epsE_common_start": selected,
        "selection_rule": "highest candidate passing the ADR-0008 checklist on every geometry",
        "confirmation_level_required": CONFIRMATION_LEVEL,
        "caveats": [
            "Reynolds numbers are provisional; see ADR-0008 and operating_points.yaml "
            "pending_recheck EPSE-RECHECK-ON-MISSION-FREEZE.",
            "S1's spanwise geometric-progression law is computed but realised at native "
            "sections. Stage 03 redistributes spanwise points, after which epsE must be "
            "re-checked.",
            "Selection is not final until confirmed at the finer level.",
        ],
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n")

    print(f"{'geometry':10s} {'epsE':>5s} {'state':>7s} {'inv':>5s} {'badlayers':>10s} {'minQ':>10s}")
    for r in rows:
        if r["state"] == "NOT_RUN":
            print(f"{r['geometry']:10s} {r['epsE']:5.1f} {'NOT_RUN':>7s}")
            continue
        lay = f"{r['low_quality_layers']}/{r['layer_count']}"
        print(f"{r['geometry']:10s} {r['epsE']:5.1f} {r['state']:>7s} "
              f"{str(r['inverted_cells']):>5s} {lay:>10s} {str(r['min_quality']):>10s}")
        for f in r["failures"]:
            print(f"{'':26s}- {f}")

    print(f"\ncap4 reference for comparison: {CAP4_REFERENCE['bad_layers']}/"
          f"{CAP4_REFERENCE['layer_count']} bad layers, min quality {CAP4_REFERENCE['min_quality']}")
    if selected is None:
        print("\nNO epsE PASSES. ADR-0008 section 6 early-stop applies: do NOT march S3/S4/S5, "
              "diagnose the shared tip cap or the marching setup, and report.")
    else:
        print(f"\nepsE_common_start = {selected} (pending confirmation at {CONFIRMATION_LEVEL})")
    print(f"\nwrote {REPORT}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["prepare", "collect"])
    ap.add_argument("--all-ten", action="store_true", help="all ten calibration geometries")
    ap.add_argument("--level", default=CALIBRATION_LEVEL)
    args = ap.parse_args()
    indices = list(range(10)) if args.all_ten else [CANARY_GEOMETRY]

    if args.mode == "prepare":
        cmds = prepare(indices, args.level)
        print(f"Prepared {len(cmds)} pyHyp run(s) at level {args.level}. "
              f"Heavy compute is not launched from here — run these yourself:\n")
        for c in cmds:
            print(c)
        print(f"\nThen: .venv/bin/python {Path(__file__).relative_to(REPO_ROOT)} collect"
              f"{' --all-ten' if args.all_ten else ''}")
        return 0
    return collect(indices)


if __name__ == "__main__":
    raise SystemExit(main())
