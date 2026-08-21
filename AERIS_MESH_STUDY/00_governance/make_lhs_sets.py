"""Regenerate the frozen Stage 00 LHS sample tables.

Every locked geometry set in this study is defined by the triple
``(sampler, seed, n)`` plus the geometry-config hash - a seed alone does not
identify a set, because Latin hypercube stratification depends on ``n``.

Run from the repository root with the main virtual environment:

    .venv/bin/python AERIS_MESH_STUDY/00_governance/make_lhs_sets.py --check

``--check`` regenerates in memory and fails if any committed CSV differs.
Without it, the CSVs are rewritten in place.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import yaml

from aeris.dataset.sampling.samplers.lhs_v1 import build_lhs_design_matrix
from aeris.generators.bwb_segmented_v1.params import build_bwb_generator_config

REPO_ROOT = Path(__file__).resolve().parents[2]
GEOMETRY_CONFIG = REPO_ROOT / "configs/geometry/bwb.yaml"
OUT_DIR = Path(__file__).resolve().parent

# (filename, seed, n, purpose)
SETS = [
    ("lhs100_seed42_samples.csv", 42, 100, "full LHS for surface laws and variable deltas"),
    ("round_c_lhs10_seed42_samples.csv", 42, 10, "Round C tournament hold-out"),
    ("epse_calibration_lhs10_seed7_samples.csv", 7, 10, "Stage 01 epsE_common_start calibration"),
]


def _columns(config) -> list[str]:
    return config.active_design_variable_names()


def _matrix(config, seed: int, n: int) -> np.ndarray:
    return build_lhs_design_matrix(config, n, np.random.default_rng(seed))


def _read_csv(path: Path) -> np.ndarray:
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    cols = [name for name in rows[0] if name != "sample_index"]
    return np.array([[float(row[name]) for name in cols] for row in rows])


def _write_csv(path: Path, columns: list[str], matrix: np.ndarray) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["sample_index", *columns])
        for index, row in enumerate(matrix):
            writer.writerow([index, *(repr(float(value)) for value in row)])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify instead of rewriting")
    parser.add_argument("--only", help="restrict writing to one filename")
    args = parser.parse_args()

    config = build_bwb_generator_config(yaml.safe_load(GEOMETRY_CONFIG.read_text()))
    columns = _columns(config)

    matrices: dict[str, np.ndarray] = {}
    failures: list[str] = []

    for filename, seed, n, purpose in SETS:
        matrix = _matrix(config, seed, n)
        matrices[filename] = matrix
        path = OUT_DIR / filename
        if args.check:
            if not path.exists():
                failures.append(f"{filename}: missing")
                continue
            stored = _read_csv(path)
            if stored.shape != matrix.shape or not np.allclose(stored, matrix, rtol=0, atol=1e-12):
                failures.append(f"{filename}: does not match seed={seed} n={n}")
            else:
                print(f"OK   {filename:44s} seed={seed} n={n}  ({purpose})")
        elif args.only in (None, filename):
            _write_csv(path, columns, matrix)
            print(f"wrote {filename:44s} seed={seed} n={n}  ({purpose})")

    # The epsE calibration set must not touch the Round C hold-out: RUNBOOK
    # section 7 forbids epsE tuning on the held-out LHS geometries.
    def rows(name: str) -> set[tuple[float, ...]]:
        return {tuple(np.round(row, 9)) for row in matrices[name]}

    overlap = rows("epse_calibration_lhs10_seed7_samples.csv") & rows("round_c_lhs10_seed42_samples.csv")
    if overlap:
        failures.append(f"epsE calibration set overlaps the Round C hold-out in {len(overlap)} rows")
    else:
        print("OK   epsE calibration set is disjoint from the Round C hold-out")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
