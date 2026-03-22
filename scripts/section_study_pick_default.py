from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable

DEFAULT_REL_TOL = 0.01  # 1%
DEFAULT_ABS_TOL = 1e-9

DEFAULT_METRICS = [
    "full_span_m_mean",
    "approx_area_m2_mean",
    "approx_aspect_ratio_planform_mean",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read a section_study_summary.csv file and recommend the lowest converged "
            "n_points value based on relative metric changes."
        )
    )
    parser.add_argument(
        "--summary-csv",
        type=Path,
        required=True,
        help="Path to section_study_summary.csv produced by section_study.py",
    )
    parser.add_argument(
        "--metrics",
        nargs="+",
        default=DEFAULT_METRICS,
        help=(
            "Summary CSV columns to use for convergence. "
            f"Default: {' '.join(DEFAULT_METRICS)}"
        ),
    )
    parser.add_argument(
        "--rel-tol",
        type=float,
        default=DEFAULT_REL_TOL,
        help="Relative tolerance for convergence between consecutive section counts. Default: 0.01 (1%%).",
    )
    parser.add_argument(
        "--abs-tol",
        type=float,
        default=DEFAULT_ABS_TOL,
        help="Absolute tolerance floor to avoid division by zero issues. Default: 1e-9.",
    )
    parser.add_argument(
        "--require-success",
        action="store_true",
        help="Ignore rows whose status is not 'success'.",
    )
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"Summary CSV is empty: {path}")
    return rows


def to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def filter_rows(rows: Iterable[dict[str, str]], require_success: bool) -> list[dict[str, str]]:
    out = []
    for row in rows:
        n_points = to_int(row.get("n_points"))
        if n_points is None:
            continue
        if require_success and row.get("status") != "success":
            continue
        out.append(row)
    out.sort(key=lambda r: to_int(r.get("n_points")) or 0)
    if len(out) < 2:
        raise ValueError("Need at least two valid rows to assess convergence.")
    return out


def rel_change(a: float, b: float, abs_tol: float) -> float:
    denom = max(abs(a), abs_tol)
    return abs(b - a) / denom


def build_report(rows: list[dict[str, str]], metrics: list[str], rel_tol: float, abs_tol: float) -> tuple[list[dict[str, object]], int | None]:
    comparisons: list[dict[str, object]] = []
    recommended: int | None = None

    for prev, curr in zip(rows[:-1], rows[1:]):
        prev_n = to_int(prev.get("n_points"))
        curr_n = to_int(curr.get("n_points"))
        assert prev_n is not None and curr_n is not None

        metric_changes: dict[str, float | None] = {}
        all_within = True

        for metric in metrics:
            a = to_float(prev.get(metric))
            b = to_float(curr.get(metric))
            if a is None or b is None:
                metric_changes[metric] = None
                all_within = False
                continue
            rc = rel_change(a, b, abs_tol)
            metric_changes[metric] = rc
            if rc > rel_tol:
                all_within = False

        comparisons.append(
            {
                "from_n_points": prev_n,
                "to_n_points": curr_n,
                "all_within_tol": all_within,
                **metric_changes,
            }
        )

        if all_within and recommended is None:
            recommended = prev_n

    return comparisons, recommended


def print_report(comparisons: list[dict[str, object]], metrics: list[str], rel_tol: float, recommended: int | None) -> None:
    print("\n=== SECTION COUNT CONVERGENCE REPORT ===")
    print(f"Relative tolerance: {rel_tol:.6f}")
    print(f"Metrics: {', '.join(metrics)}")
    print()

    for row in comparisons:
        print(f"{row['from_n_points']} -> {row['to_n_points']} | within_tol={row['all_within_tol']}")
        for metric in metrics:
            val = row.get(metric)
            if val is None:
                print(f"  - {metric}: N/A")
            else:
                print(f"  - {metric}: {val:.6%}")
        print()

    if recommended is None:
        print("No converged n_points recommendation found with the current tolerance.")
        print("Recommendation: either raise the tolerance slightly or test more section counts.")
    else:
        print(f"Recommended lowest converged n_points: {recommended}")


def main() -> None:
    args = parse_args()
    rows = read_rows(args.summary_csv)
    rows = filter_rows(rows, require_success=args.require_success)
    comparisons, recommended = build_report(
        rows=rows,
        metrics=args.metrics,
        rel_tol=args.rel_tol,
        abs_tol=args.abs_tol,
    )
    print_report(
        comparisons=comparisons,
        metrics=args.metrics,
        rel_tol=args.rel_tol,
        recommended=recommended,
    )


if __name__ == "__main__":
    main()
