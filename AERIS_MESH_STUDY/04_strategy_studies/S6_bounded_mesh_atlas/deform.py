"""Bounded, column-preserving deformation of an S6 structured volume mesh."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STUDIES = HERE.parent
REPO_ROOT = STUDIES.parents[1]
for _path in (REPO_ROOT / "src", STUDIES):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from shared.volume_qc import volume_report  # noqa: E402

from aeris.cfd.meshing.volume_audit import (  # noqa: E402
    _iter_zone_coordinate_arrays,
    read_volume_blocks,
)

Array = np.ndarray
DEFORMATION_SCHEMA = "aeris.mesh.s6_bounded_deformation.v1"
WALL_TOLERANCE_M = 1.0e-10
PRODUCTION_MIN_SCALED_QUALITY = 0.10


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_surface_blocks(path: Path) -> dict[str, Array]:
    """Load surface blocks while preserving their Plot3D/NPZ insertion order."""
    with np.load(Path(path)) as archive:
        return {name: np.asarray(archive[name], dtype=float) for name in archive.files}


def _surface_points(blocks: dict[str, Array]) -> Array:
    if not blocks:
        raise ValueError("surface block set is empty")
    return np.concatenate([block.reshape(-1, 3) for block in blocks.values()])


def _characteristic_length(blocks: dict[str, Array]) -> float:
    points = _surface_points(blocks)
    length = float(np.linalg.norm(np.ptp(points, axis=0)))
    if not np.isfinite(length) or length <= 0.0:
        raise ValueError("surface characteristic length must be finite and positive")
    return length


def first_layer_spacing_report(
    blocks: dict[str, Array], *, characteristic_length_m: float
) -> dict[str, Any]:
    """Measure the realized wall-normal first edge without imposing a y+ gate."""
    if not np.isfinite(characteristic_length_m) or characteristic_length_m <= 0.0:
        raise ValueError("characteristic length must be finite and positive")
    per_zone: dict[str, dict[str, float | int]] = {}
    values: list[Array] = []
    for zone, nodes in blocks.items():
        if nodes.shape[0] < 2:
            raise ValueError(f"volume zone {zone} has no first off-wall layer")
        spacing = np.linalg.norm(nodes[1] - nodes[0], axis=-1).reshape(-1)
        values.append(spacing)
        finite = spacing[np.isfinite(spacing)]
        per_zone[zone] = {
            "count": int(spacing.size),
            "nonfinite_count": int(spacing.size - finite.size),
            "nonpositive_count": int(np.count_nonzero(finite <= 0.0)),
            "min_m": float(np.min(finite)) if finite.size else float("nan"),
            "median_m": float(np.median(finite)) if finite.size else float("nan"),
            "max_m": float(np.max(finite)) if finite.size else float("nan"),
        }
    combined = np.concatenate(values) if values else np.empty(0)
    finite = combined[np.isfinite(combined)]
    positive = finite[finite > 0.0]
    stats = {
        "count": int(combined.size),
        "nonfinite_count": int(combined.size - finite.size),
        "nonpositive_count": int(np.count_nonzero(finite <= 0.0)),
        "min_m": float(np.min(positive)) if positive.size else float("nan"),
        "p05_m": float(np.quantile(positive, 0.05)) if positive.size else float("nan"),
        "median_m": float(np.median(positive)) if positive.size else float("nan"),
        "p95_m": float(np.quantile(positive, 0.95)) if positive.size else float("nan"),
        "max_m": float(np.max(positive)) if positive.size else float("nan"),
        "characteristic_length_m": characteristic_length_m,
        "per_zone": per_zone,
    }
    for key in ("min_m", "p05_m", "median_m", "p95_m", "max_m"):
        stats[key.replace("_m", "_fraction_characteristic")] = stats[key] / characteristic_length_m
    return stats


def _root_le_and_scales(
    template_surface: dict[str, Array],
    target_surface: dict[str, Array],
) -> tuple[Array, Array, Array]:
    """Return template anchor, target anchor, and chord/span/chord scales."""

    def measurements(blocks: dict[str, Array]) -> tuple[Array, float, float]:
        points = _surface_points(blocks)
        y_min = float(points[:, 1].min())
        span = float(points[:, 1].max() - y_min)
        tolerance = max(1.0e-10, span * 1.0e-8)
        root = points[np.abs(points[:, 1] - y_min) <= tolerance]
        if len(root) < 2:
            raise ValueError("could not identify the root section")
        chord = float(root[:, 0].max() - root[:, 0].min())
        if chord <= 0.0 or span <= 0.0:
            raise ValueError("template and target must have positive root chord and span")
        anchor = root[int(np.argmin(root[:, 0]))].copy()
        return anchor, chord, span

    template_anchor, template_chord, template_span = measurements(template_surface)
    target_anchor, target_chord, target_span = measurements(target_surface)
    chord_scale = target_chord / template_chord
    scales = np.array([chord_scale, target_span / template_span, chord_scale])
    return template_anchor, target_anchor, scales


def _ordered_pairs(
    volume_blocks: dict[str, Array],
    surface_blocks: dict[str, Array],
) -> list[tuple[str, str]]:
    if len(volume_blocks) != len(surface_blocks):
        raise ValueError(
            f"block-count mismatch: volume={len(volume_blocks)}, surface={len(surface_blocks)}"
        )
    return list(zip(volume_blocks, surface_blocks, strict=True))


def validate_template_correspondence(
    volume_blocks: dict[str, Array],
    template_surface: dict[str, Array],
    *,
    tolerance_m: float = WALL_TOLERANCE_M,
) -> dict[str, Any]:
    """Prove that volume zone order and surface-block order are equivalent."""
    errors: dict[str, float] = {}
    for zone, surface_name in _ordered_pairs(volume_blocks, template_surface):
        volume = np.asarray(volume_blocks[zone], dtype=float)
        surface = np.asarray(template_surface[surface_name], dtype=float)
        expected_shape = (surface.shape[1], surface.shape[0], 3)
        if volume[0].shape != expected_shape:
            raise ValueError(
                f"{zone}/{surface_name} wall shape {volume[0].shape} "
                f"does not match {expected_shape}"
            )
        errors[zone] = float(np.max(np.abs(volume[0] - surface.transpose(1, 0, 2))))
    maximum = max(errors.values(), default=float("inf"))
    if maximum > tolerance_m:
        raise ValueError(f"template CGNS wall does not match template surface: {maximum:.3e} m")
    return {"max_wall_error_m": maximum, "per_zone_max_wall_error_m": errors}


def _common_layer_fraction(blocks: dict[str, Array]) -> Array:
    """One physical-distance weight shared by every block and interface node."""
    layer_spacings = []
    n_layers: int | None = None
    for nodes in blocks.values():
        if n_layers is None:
            n_layers = int(nodes.shape[0])
        elif nodes.shape[0] != n_layers:
            raise ValueError("all connected blocks must have the same layer count")
        segment = np.linalg.norm(np.diff(nodes, axis=0), axis=-1)
        layer_spacings.append(np.median(segment.reshape(segment.shape[0], -1), axis=1))
    if n_layers is None or n_layers < 2:
        raise ValueError("volume needs at least one block with two marching layers")
    spacing = np.median(np.stack(layer_spacings), axis=0)
    cumulative = np.concatenate([[0.0], np.cumsum(spacing)])
    if cumulative[-1] <= 0.0:
        raise ValueError("volume has zero wall-to-farfield distance")
    return (cumulative / cumulative[-1]).reshape(-1, 1, 1)


def volume_interface_report(
    blocks: dict[str, Array],
    *,
    wall_pair_tolerance_m: float = 1.0e-8,
) -> dict[str, Any]:
    """Measure every inter-block side face found from its common wall edge."""
    faces: list[dict[str, Any]] = []
    for zone, nodes in blocks.items():
        candidates = {
            "i0": nodes[:, :, 0, :],
            "i1": nodes[:, :, -1, :],
            "j0": nodes[:, 0, :, :],
            "j1": nodes[:, -1, :, :],
        }
        for side, face in candidates.items():
            faces.append({"zone": zone, "side": side, "nodes": face})

    used: set[int] = set()
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(faces):
        if left_index in used:
            continue
        left_wall = left["nodes"][0]
        best: tuple[float, int, bool] | None = None
        for right_index in range(left_index + 1, len(faces)):
            if right_index in used:
                continue
            right = faces[right_index]
            if left["zone"] == right["zone"]:
                continue
            right_wall = right["nodes"][0]
            if left_wall.shape != right_wall.shape:
                continue
            direct = float(np.max(np.abs(left_wall - right_wall)))
            reverse = float(np.max(np.abs(left_wall - right_wall[::-1])))
            candidate = (direct, right_index, False)
            if reverse < direct:
                candidate = (reverse, right_index, True)
            if best is None or candidate[0] < best[0]:
                best = candidate
        if best is None or best[0] > wall_pair_tolerance_m:
            continue
        _wall_error, right_index, reverse = best
        right = faces[right_index]
        right_nodes = right["nodes"][:, ::-1, :] if reverse else right["nodes"]
        mismatch = float(np.max(np.abs(left["nodes"] - right_nodes)))
        used.update((left_index, right_index))
        pairs.append(
            {
                "left": f"{left['zone']}:{left['side']}",
                "right": f"{right['zone']}:{right['side']}",
                "max_mismatch_m": mismatch,
            }
        )

    unmatched = [
        f"{face['zone']}:{face['side']}" for index, face in enumerate(faces) if index not in used
    ]
    return {
        "paired_face_count": len(pairs),
        "max_mismatch_m": max((pair["max_mismatch_m"] for pair in pairs), default=float("inf")),
        "pairs": pairs,
        "unmatched_side_faces": unmatched,
    }


def deform_volume_blocks(
    template_volume: dict[str, Array],
    template_surface: dict[str, Array],
    target_surface: dict[str, Array],
) -> tuple[dict[str, Array], dict[str, Any]]:
    """Map a template volume to an exact target wall with zero farfield residual.

    A global chord/span affine map handles the large design change. The remaining
    wall displacement is propagated down each existing marching column with a
    C1 weight whose derivative is zero at the wall. This protects the first-cell
    spacing and preserves the fixed multiblock graph.
    """
    validate_template_correspondence(template_volume, template_surface)
    if list(template_surface) != list(target_surface):
        raise ValueError("target surface block names/order differ from the template")
    for name in template_surface:
        if template_surface[name].shape != target_surface[name].shape:
            raise ValueError(
                f"target block {name} has shape {target_surface[name].shape}, "
                f"expected {template_surface[name].shape}"
            )

    template_anchor, target_anchor, scales = _root_le_and_scales(template_surface, target_surface)
    eta = _common_layer_fraction(template_volume)
    deformed: dict[str, Array] = {}
    wall_errors: dict[str, float] = {}
    displacement_max = 0.0

    for zone, surface_name in _ordered_pairs(template_volume, template_surface):
        source = np.asarray(template_volume[zone], dtype=float)
        affine = target_anchor + (source - template_anchor) * scales
        target_wall = target_surface[surface_name].transpose(1, 0, 2)
        residual = target_wall - affine[0]
        weight = (1.0 - eta * eta) ** 2
        mapped = affine + weight[..., None] * residual[None, ...]
        deformed[zone] = mapped
        error = float(np.max(np.abs(mapped[0] - target_wall)))
        wall_errors[zone] = error
        displacement_max = max(
            displacement_max,
            float(np.max(np.linalg.norm(mapped - affine, axis=-1))),
        )

    maximum_wall_error = max(wall_errors.values(), default=float("inf"))
    template_interfaces = volume_interface_report(template_volume)
    deformed_interfaces = volume_interface_report(deformed)
    template_characteristic_length = _characteristic_length(template_surface)
    target_characteristic_length = _characteristic_length(target_surface)
    metadata = {
        "template_anchor_m": template_anchor.tolist(),
        "target_anchor_m": target_anchor.tolist(),
        "affine_scale_xyz": scales.tolist(),
        "residual_weight": "(1-common_normalized_physical_layer_distance^2)^2",
        "max_residual_displacement_m": displacement_max,
        "max_wall_error_m": maximum_wall_error,
        "per_zone_max_wall_error_m": wall_errors,
        "template_interfaces": template_interfaces,
        "deformed_interfaces": deformed_interfaces,
        "first_layer_spacing": {
            "status": "diagnostic_pending_production_yplus_validation",
            "template": first_layer_spacing_report(
                template_volume,
                characteristic_length_m=template_characteristic_length,
            ),
            "deformed": first_layer_spacing_report(
                deformed,
                characteristic_length_m=target_characteristic_length,
            ),
        },
    }
    return deformed, metadata


def written_deformation_metadata(
    written_blocks: dict[str, Array],
    target_surface: dict[str, Array],
    deformation: dict[str, Any],
) -> dict[str, Any]:
    """Rebuild wall, interface, and spacing evidence from a re-opened CGNS."""
    correspondence = validate_template_correspondence(written_blocks, target_surface)
    target_characteristic_length = _characteristic_length(target_surface)
    spacing = dict(deformation.get("first_layer_spacing", {}))
    spacing["deformed"] = first_layer_spacing_report(
        written_blocks,
        characteristic_length_m=target_characteristic_length,
    )
    return {
        **deformation,
        **correspondence,
        "deformed_interfaces": volume_interface_report(written_blocks),
        "first_layer_spacing": spacing,
    }


def write_volume_blocks(
    template_cgns: Path,
    output_cgns: Path,
    blocks: dict[str, Array],
) -> Path:
    """Copy a structured CGNS template and replace only its coordinate arrays."""
    import h5py

    template_cgns = Path(template_cgns)
    output_cgns = Path(output_cgns)
    output_cgns.parent.mkdir(parents=True, exist_ok=True)
    if template_cgns.resolve() == output_cgns.resolve():
        raise ValueError("output CGNS must differ from the immutable template")
    shutil.copy2(template_cgns, output_cgns)
    with h5py.File(str(output_cgns), "r+") as handle:
        zones = list(_iter_zone_coordinate_arrays(handle))
        if [name for name, _ in zones] != list(blocks):
            raise ValueError("CGNS zone order/names differ from the deformed blocks")
        for (zone, arrays), (block_name, xyz) in zip(zones, blocks.items(), strict=True):
            if zone != block_name:
                raise ValueError(f"zone mismatch: {zone} != {block_name}")
            for axis, dataset in enumerate(arrays):
                if dataset.shape != xyz[..., axis].shape:
                    raise ValueError(
                        f"{zone} coordinate shape {dataset.shape} "
                        f"does not match {xyz[..., axis].shape}"
                    )
                dataset[...] = xyz[..., axis]
    return output_cgns


def acceptance_report(
    blocks: dict[str, Array],
    deformation: dict[str, Any],
    *,
    production_floor: float = PRODUCTION_MIN_SCALED_QUALITY,
) -> dict[str, Any]:
    quality = volume_report(blocks)
    hard_reasons: list[str] = []
    if deformation["max_wall_error_m"] > WALL_TOLERANCE_M:
        hard_reasons.append("wall_fidelity")
    template_interfaces = deformation["template_interfaces"]
    interfaces = deformation["deformed_interfaces"]
    template_pairs = {
        tuple(sorted((pair["left"], pair["right"]))) for pair in template_interfaces["pairs"]
    }
    deformed_pairs = {tuple(sorted((pair["left"], pair["right"]))) for pair in interfaces["pairs"]}
    if (
        interfaces["paired_face_count"] != template_interfaces["paired_face_count"]
        or deformed_pairs != template_pairs
        or (interfaces["paired_face_count"] > 0 and interfaces["max_mismatch_m"] > WALL_TOLERANCE_M)
    ):
        hard_reasons.append("nonconformal_block_interfaces")
    if not quality.get("generation_completed", False):
        hard_reasons.append("generation")
    if quality.get("inverted_cells", 1) != 0:
        hard_reasons.append("inverted_cells")
    if not float(quality.get("min_volume", -1.0)) > 0.0:
        hard_reasons.append("positive_volume")
    if not float(quality.get("min_scaled_quality", -1.0)) > 0.0:
        hard_reasons.append("positive_scaled_quality")
    spacing = deformation.get("first_layer_spacing", {}).get("deformed", {})
    if spacing and (
        int(spacing.get("nonfinite_count", 1)) != 0 or int(spacing.get("nonpositive_count", 1)) != 0
    ):
        hard_reasons.append("invalid_first_layer_spacing")
    min_quality = float(quality.get("min_scaled_quality", -1.0))
    return {
        "hard_gate_passed": not hard_reasons,
        "hard_gate_failure_reasons": hard_reasons,
        "production_floor": production_floor,
        "production_floor_passed": not hard_reasons and min_quality >= production_floor,
        "quality": quality,
    }


def deform_cgns(
    *,
    template_cgns: Path,
    template_surface_npz: Path,
    target_surface_npz: Path,
    output_cgns: Path,
    report_path: Path | None = None,
    production_floor: float = PRODUCTION_MIN_SCALED_QUALITY,
) -> dict[str, Any]:
    """Run, write, and independently score one atlas deformation."""
    template_surface = load_surface_blocks(template_surface_npz)
    target_surface = load_surface_blocks(target_surface_npz)
    template_volume = read_volume_blocks(Path(template_cgns))
    blocks, deformation = deform_volume_blocks(template_volume, template_surface, target_surface)
    in_memory_acceptance = acceptance_report(blocks, deformation, production_floor=production_floor)
    write_volume_blocks(template_cgns, output_cgns, blocks)
    written = read_volume_blocks(Path(output_cgns))
    written_metadata = written_deformation_metadata(written, target_surface, deformation)
    acceptance = acceptance_report(written, written_metadata, production_floor=production_floor)
    report = {
        "schema": DEFORMATION_SCHEMA,
        "template_cgns": str(template_cgns),
        "template_cgns_sha256": sha256(template_cgns),
        "template_surface_npz": str(template_surface_npz),
        "template_surface_sha256": sha256(template_surface_npz),
        "target_surface_npz": str(target_surface_npz),
        "target_surface_sha256": sha256(target_surface_npz),
        "output_cgns": str(output_cgns),
        "output_cgns_sha256": sha256(output_cgns),
        "deformation": written_metadata,
        "in_memory_acceptance": in_memory_acceptance,
        "acceptance": acceptance,
    }
    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return report
