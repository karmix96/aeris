"""Is the degenerate tip corner a cap4 blocking artefact, or a geometry defect?

Stage 01 blocked on a ~179.7 degree corner quad in the tip cap at the
leading-edge shoulder. Two competing explanations:

  H1 (cap4-specific): the airfoil-face cap takes its corners from the cap4 OML
      block splits at x/c = split_x_fore and split_x_aft. Those splits sit on a
      SMOOTH part of the airfoil contour, so the two edges meeting at the cap
      corner are collinear and the corner angle is ~180 degrees by
      construction. Moving the split should move the bad corner but not cure
      it, and a different OML topology should behave differently.

  H2 (shared upstream): the pyGeo tip-station section itself has a cusp or a
      collapsed segment, in which case every strategy inherits the defect and
      it must be fixed before Stage 02.

This probe decides between them, surface-only. No pyHyp march, no solver.

    .venv/bin/python AERIS_MESH_STUDY/03_cap4_epse/tip_corner_origin_probe.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from aeris.cfd.meshing.registry import get_topology  # noqa: E402
from aeris.cfd.presets.registry import get_preset  # noqa: E402
from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix  # noqa: E402
from aeris.generators.bwb_segmented_v1.params import (  # noqa: E402
    BWBDesignSample,
    build_bwb_generator_config,
)
from aeris.geometry.registry import get_geometry_generator  # noqa: E402

GEOMETRY_CONFIG = REPO_ROOT / "configs/geometry/bwb.yaml"
OUT_DIR = REPO_ROOT / "AERIS_MESH_STUDY/artifacts/stage01/tip_corner_origin_probe"
REPORT_JSON = Path(__file__).resolve().parent / "tip_corner_origin_probe_report.json"
REPORT_MD = Path(__file__).resolve().parent / "tip_corner_origin_probe_report.md"

BASE_PARAMS: dict[str, object] = {
    "points_per_side": 49,
    "spanwise_panels": 16,
    "cap_wrap_points": 9,
    "tip_radial_points": 7,
    "cap_wrap_x": 0.40,
    "tip_smooth_iters": 0,
    "te_thickness": 0.005,
    "te_thickness_abs_floor": 0.0,
    "te_base_points": 0,
    "min_shape_metric": 1.0e-6,
    "max_adjacent_normal_angle": 180.0,
    "chordwise_distribution": "uniform",
    "chordwise_beta": 2.0,
    "spanwise_distribution": "uniform",
    "spanwise_beta": 2.0,
    "spanwise_allocation": "proportional",
}

# H1 predicts: moving split_x_fore moves the bad corner but leaves it ~180 deg,
# and the non-cap4 OML topologies behave differently.
VARIANTS: list[tuple[str, str, dict[str, object]]] = [
    ("cap4_split_0.10", "wing_cap4_v1", {"oml_topology": "cap4", "split_x_fore": 0.10}),
    ("cap4_split_0.20", "wing_cap4_v1", {"oml_topology": "cap4", "split_x_fore": 0.20}),
    ("cap4_split_0.35", "wing_cap4_v1", {"oml_topology": "cap4", "split_x_fore": 0.35}),
    ("mid4", "wing_mid4_v1", {"oml_topology": "mid4"}),
    ("split8", "wing_split8_v1", {"oml_topology": "split8"}),
]


def build_sample_zero():
    config = build_bwb_generator_config(yaml.safe_load(GEOMETRY_CONFIG.read_text()))
    matrix = build_lhs_design_matrix(config, 10, np.random.default_rng(7))
    names = config.active_design_variable_names()
    sample = BWBDesignSample(**{n: float(v) for n, v in zip(names, matrix[0], strict=True)})
    return sample, config


def worst_corner_angle(points: np.ndarray) -> tuple[float, tuple[int, int]]:
    """Largest interior corner angle over all quads of a structured patch."""
    worst = -1.0
    where = (-1, -1)
    ni, nj, _ = points.shape
    for i in range(ni - 1):
        for j in range(nj - 1):
            quad = [points[i, j], points[i + 1, j], points[i + 1, j + 1], points[i, j + 1]]
            for k in range(4):
                a = quad[(k - 1) % 4] - quad[k]
                b = quad[(k + 1) % 4] - quad[k]
                na, nb = np.linalg.norm(a), np.linalg.norm(b)
                if na < 1e-14 or nb < 1e-14:
                    continue
                ang = np.degrees(np.arccos(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0)))
                if ang > worst:
                    worst, where = float(ang), (i, j)
    return worst, where


def tip_station_smoothness(case) -> dict[str, object]:
    """H2 check: does the raw tip-station section itself contain a cusp?

    Measures the turning angle between consecutive segments of the outermost
    geometry section. A smooth airfoil turns gently everywhere except the LE
    and the blunt TE.
    """
    wing = case.wing
    xsec = wing.xsecs[-1]
    coords = np.asarray(xsec.airfoil.coordinates, dtype=float)
    seg = np.diff(coords, axis=0)
    lengths = np.linalg.norm(seg, axis=1)
    unit = seg / np.maximum(lengths[:, None], 1e-16)
    dots = np.clip(np.sum(unit[:-1] * unit[1:], axis=1), -1.0, 1.0)
    turn = np.degrees(np.arccos(dots))
    return {
        "n_points": int(len(coords)),
        "min_segment_length": float(lengths.min()),
        "median_segment_length": float(np.median(lengths)),
        "collapsed_segments_below_1e-9": int((lengths < 1e-9).sum()),
        "max_turning_angle_deg": float(turn.max()),
        "max_turning_at_index": int(turn.argmax()),
        "turning_angle_99th_pct_deg": float(np.percentile(turn, 99)),
    }


def main() -> int:
    sample, config = build_sample_zero()
    generator = get_geometry_generator("bwb_segmented")
    preset_surface = dict(get_preset("smoke").surface)

    results = []
    geometry_check: dict[str, object] = {}

    for name, topology_id, overrides in VARIANTS:
        params = dict(preset_surface)
        params.update(BASE_PARAMS)
        params.update(overrides)
        work = OUT_DIR / name
        work.mkdir(parents=True, exist_ok=True)
        entry: dict[str, object] = {"variant": name, "topology_id": topology_id, "overrides": overrides}
        try:
            case = generator.run_full_case(
                sample=sample, config=config, output_dir=work / "geometry",
                save_plot=False, build_aerosandbox=True,
            )
            if not geometry_check:
                geometry_check = tip_station_smoothness(case)
            get_topology(topology_id).generate(case.wing, work / "surface", params)
            report = json.loads((work / "surface" / "surface_report.json").read_text())
            npz = np.load(work / "surface" / "surface_blocks.npz")
        except Exception as exc:  # noqa: BLE001
            entry["error"] = f"{type(exc).__name__}: {exc}"
            results.append(entry)
            print(f"{name:18s} FAILED: {exc}")
            continue

        g = report["global"]
        tip_names = [b["name"] for b in report["blocks"] if "tip" in b["name"]]
        angles = {}
        for tn in tip_names:
            key = tn if tn in npz else next((k for k in npz.files if k.endswith(tn)), None)
            if key is None:
                continue
            ang, where = worst_corner_angle(np.asarray(npz[key], dtype=float))
            angles[tn] = {"worst_corner_angle_deg": ang, "at_ij": list(where)}
        entry.update({
            "error": None,
            "min_shape_metric": g["min_shape_metric"],
            "max_equiangle_skewness": g["max_equiangle_skewness"],
            "min_scaled_jacobian": g["min_scaled_jacobian"],
            "accepted_pre_pyhyp": report.get("accepted_pre_pyhyp"),
            "tip_blocks": tip_names,
            "tip_corner_angles": angles,
        })
        results.append(entry)
        worst_ang = max((v["worst_corner_angle_deg"] for v in angles.values()), default=float("nan"))
        print(f"{name:18s} shape={g['min_shape_metric']:.4e} skew={g['max_equiangle_skewness']:.4f} "
              f"worst_tip_corner={worst_ang:.3f} deg")

    payload = {
        "schema": "aeris.mesh_study.stage01_tip_corner_origin_probe.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "sample_id": "lhs7_00",
        "hypotheses": {
            "H1_cap4_blocking": "cap corners inherit cap4 OML splits on a smooth contour",
            "H2_shared_geometry": "the tip-station section itself is defective",
        },
        "tip_station_geometry_check": geometry_check,
        "variants": results,
    }
    REPORT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("\ntip-station geometry check:", json.dumps(geometry_check, indent=1))
    print(f"wrote {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
