"""Independent post-solve quality checks for S6 CFD cases."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import h5py
import numpy as np

YPLUS_SCHEMA = "aeris.mesh.s6_wall_yplus.v1"
YPLUS_TARGET = 1.0
YPLUS_P95_MAX = 1.0
YPLUS_P99_MAX = 2.0
YPLUS_ABSOLUTE_MAX = 5.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wall_yplus_summary(
    surface_cgns: Path,
    *,
    target: float = YPLUS_TARGET,
    p95_max: float = YPLUS_P95_MAX,
    p99_max: float = YPLUS_P99_MAX,
    absolute_max: float = YPLUS_ABSOLUTE_MAX,
) -> dict[str, Any]:
    """Read YPlus only from ADflow no-slip wall zones and apply frozen limits."""
    surface_cgns = Path(surface_cgns).resolve()
    arrays: list[np.ndarray] = []
    zones: set[str] = set()

    with h5py.File(surface_cgns, "r") as handle:

        def collect(name: str, obj: Any) -> None:
            if not isinstance(obj, h5py.Dataset):
                return
            parts = name.split("/")
            zone = next(
                (part for part in parts if part.casefold().startswith("nswall")),
                None,
            )
            if zone is None or "yplus" not in {part.casefold() for part in parts}:
                return
            values = np.asarray(obj[()]).reshape(-1)
            if values.size:
                arrays.append(values.astype(float, copy=False))
                zones.add(zone)

        handle.visititems(collect)

    thresholds = {
        "target": float(target),
        "p95_max": float(p95_max),
        "p99_max": float(p99_max),
        "absolute_max": float(absolute_max),
    }
    if not arrays:
        return {
            "schema": YPLUS_SCHEMA,
            "passed": False,
            "failure_reasons": ["no_wall_yplus_fields"],
            "surface_cgns": str(surface_cgns),
            "surface_cgns_sha256": _sha256(surface_cgns),
            "thresholds": thresholds,
            "wall_zone_count": 0,
            "sample_count": 0,
        }

    values = np.concatenate(arrays)
    finite_mask = np.isfinite(values)
    finite = values[finite_mask]
    nonfinite_count = int(values.size - finite.size)
    negative_count = int(np.count_nonzero(finite < 0.0))
    if finite.size:
        statistics = {
            "minimum": float(np.min(finite)),
            "mean": float(np.mean(finite)),
            "p50": float(np.percentile(finite, 50.0)),
            "p95": float(np.percentile(finite, 95.0)),
            "p99": float(np.percentile(finite, 99.0)),
            "maximum": float(np.max(finite)),
            "fraction_at_or_below_target": float(np.mean(finite <= target)),
        }
    else:
        statistics = {
            key: None
            for key in (
                "minimum",
                "mean",
                "p50",
                "p95",
                "p99",
                "maximum",
                "fraction_at_or_below_target",
            )
        }

    failures: list[str] = []
    if nonfinite_count:
        failures.append("nonfinite_yplus")
    if negative_count:
        failures.append("negative_yplus")
    if not finite.size:
        failures.append("no_finite_yplus")
    else:
        if statistics["p95"] > p95_max:
            failures.append("p95_above_limit")
        if statistics["p99"] > p99_max:
            failures.append("p99_above_limit")
        if statistics["maximum"] > absolute_max:
            failures.append("maximum_above_limit")

    return {
        "schema": YPLUS_SCHEMA,
        "passed": not failures,
        "failure_reasons": failures,
        "surface_cgns": str(surface_cgns),
        "surface_cgns_sha256": _sha256(surface_cgns),
        "thresholds": thresholds,
        "wall_zone_count": len(zones),
        "dataset_count": len(arrays),
        "sample_count": int(values.size),
        "nonfinite_count": nonfinite_count,
        "negative_count": negative_count,
        "statistics": statistics,
    }
