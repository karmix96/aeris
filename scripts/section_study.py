from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from statistics import mean
from typing import Iterable

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIGS_DIR = PROJECT_ROOT / "configs"
DATASETS_DIR = PROJECT_ROOT / "data" / "datasets"
DEBUG_DIR = PROJECT_ROOT / "data" / "debug" / "section_study"


METRIC_COLUMNS = [
    "full_span_m",
    "approx_area_m2",
    "approx_aspect_ratio_planform",
    "aspect_ratio_aerosandbox",
    "n_xsecs_aerosandbox",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a parametric study over geometry.controls.n_points by generating fresh "
            "AERIS datasets from scratch and summarizing the results."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Base geometry YAML config to clone and modify.",
    )
    parser.add_argument(
        "--sections",
        type=int,
        nargs="+",
        required=True,
        help="List of n_points values to test, e.g. 15 25 40 60 100.",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=1,
        help="Number of geometries per section-count case. Default: 1.",
    )
    parser.add_argument(
        "--sampler",
        type=str,
        default="lhs_v1",
        help="Dataset sampler to use. Default: lhs_v1.",
    )
    parser.add_argument(
        "--sampler-seed",
        type=int,
        default=123,
        help="Sampler seed. Default: 123.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="section_study",
        help="Study name prefix used for outputs and dataset names.",
    )
    parser.add_argument(
        "--build-aerosandbox",
        action="store_true",
        help="Enable AeroSandbox object construction during dataset generation.",
    )
    parser.add_argument(
        "--save-plot",
        action="store_true",
        help="Enable plot generation during dataset generation.",
    )
    parser.add_argument(
        "--force-clean",
        action="store_true",
        help="Delete existing study output folders and dataset folders with matching names before rerunning.",
    )
    parser.add_argument(
        "--aeris-cmd",
        type=str,
        default="aeris",
        help="CLI executable to call. Default: aeris.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False)


def ensure_study_dirs(study_name: str, force_clean: bool) -> tuple[Path, Path]:
    study_root = DEBUG_DIR / study_name
    configs_dir = study_root / "configs"
    if force_clean and study_root.exists():
        shutil.rmtree(study_root)
    configs_dir.mkdir(parents=True, exist_ok=True)
    return study_root, configs_dir


def ensure_project_root_from_config(config_path: Path) -> Path:
    # Infer repo root from the config path to avoid hardcoding the user's local absolute path.
    # Expected placement: <repo>/configs/geometry/*.yaml
    resolved = config_path.expanduser().resolve()
    if "configs" not in resolved.parts:
        raise ValueError(
            f"Config path must live under the repository configs/ tree. Got: {resolved}"
        )
    idx = resolved.parts.index("configs")
    return Path(*resolved.parts[:idx])


def set_n_points(raw_cfg: dict, n_points: int) -> dict:
    data = json.loads(json.dumps(raw_cfg))  # safe deep-copy for plain YAML data
    geometry = data.setdefault("geometry", {})
    controls = geometry.setdefault("controls", {})
    controls["n_points"] = int(n_points)
    return data


def dataset_name(study_name: str, n_points: int) -> str:
    return f"{study_name}_npoints_{n_points}"


def run_dataset_generation(
    aeris_cmd: str,
    config_path: Path,
    dataset_name_value: str,
    n_samples: int,
    sampler: str,
    sampler_seed: int,
    build_aerosandbox: bool,
    save_plot: bool,
    dataset_root: Path,
    force_clean: bool,
) -> None:
    if force_clean and dataset_root.exists():
        shutil.rmtree(dataset_root)

    cmd = [
        aeris_cmd,
        "dataset",
        "generate",
        "-c",
        str(config_path),
        "--n",
        str(n_samples),
        "--sampler",
        sampler,
        "--sampler-seed",
        str(sampler_seed),
        "--name",
        dataset_name_value,
    ]

    cmd.append("--build-aerosandbox" if build_aerosandbox else "--no-build-aerosandbox")
    cmd.append("--save-plot" if save_plot else "--no-save-plot")

    print("\n>>> Running:")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def read_manifest(dataset_root: Path) -> dict:
    path = dataset_root / "dataset_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def read_metadata_rows(dataset_root: Path) -> list[dict[str, str]]:
    metadata_path = dataset_root / "metadata.csv"
    with metadata_path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def maybe_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def summarize_dataset(dataset_root: Path, n_points: int) -> dict[str, object]:
    manifest = read_manifest(dataset_root)
    rows = read_metadata_rows(dataset_root)

    summary: dict[str, object] = {
        "dataset_name": dataset_root.name,
        "n_points": n_points,
        "requested_n": manifest.get("requested_n"),
        "attempted_n": manifest.get("attempted_n"),
        "succeeded_n": manifest.get("succeeded_n"),
        "failed_n": manifest.get("failed_n"),
        "status": manifest.get("status"),
    }

    for col in METRIC_COLUMNS:
        vals = [maybe_float(r.get(col)) for r in rows]
        vals = [v for v in vals if v is not None]
        summary[f"{col}_mean"] = mean(vals) if vals else None
        summary[f"{col}_min"] = min(vals) if vals else None
        summary[f"{col}_max"] = max(vals) if vals else None

    return summary


def write_summary_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    rows = list(rows)
    if not rows:
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    if any(n < 2 for n in args.sections):
        raise ValueError("All --sections values must be >= 2.")
    if args.n < 1:
        raise ValueError("--n must be >= 1.")

    project_root = ensure_project_root_from_config(args.config)
    datasets_dir = project_root / "data" / "datasets"
    debug_dir = project_root / "data" / "debug" / "section_study"

    study_root = debug_dir / args.name
    configs_dir = study_root / "configs"
    if args.force_clean and study_root.exists():
        shutil.rmtree(study_root)
    configs_dir.mkdir(parents=True, exist_ok=True)

    base_cfg = load_yaml(args.config)
    summaries: list[dict[str, object]] = []

    print(f"Study root: {study_root}")
    print(f"Base config: {args.config}")
    print(f"Section counts: {args.sections}")

    for n_points in args.sections:
        patched = set_n_points(base_cfg, n_points)
        cfg_out = configs_dir / f"{args.config.stem}_npoints_{n_points}.yaml"
        save_yaml(cfg_out, patched)

        ds_name = dataset_name(args.name, n_points)
        ds_root = datasets_dir / ds_name

        run_dataset_generation(
            aeris_cmd=args.aeris_cmd,
            config_path=cfg_out,
            dataset_name_value=ds_name,
            n_samples=args.n,
            sampler=args.sampler,
            sampler_seed=args.sampler_seed,
            build_aerosandbox=args.build_aerosandbox,
            save_plot=args.save_plot,
            dataset_root=ds_root,
            force_clean=args.force_clean,
        )

        summaries.append(summarize_dataset(ds_root, n_points))

    summary_csv = study_root / "section_study_summary.csv"
    write_summary_csv(summary_csv, summaries)

    print("\n=== SECTION STUDY COMPLETE ===")
    print(f"Summary CSV: {summary_csv}")
    print("Datasets:")
    for row in summaries:
        print(
            f"- {row['dataset_name']}: n_points={row['n_points']}, "
            f"status={row['status']}, succeeded={row['succeeded_n']}, failed={row['failed_n']}"
        )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"\nDataset generation command failed with exit code {exc.returncode}.", file=sys.stderr)
        raise SystemExit(exc.returncode)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        raise SystemExit(130)
