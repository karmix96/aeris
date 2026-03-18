from pathlib import Path
import json
import pandas as pd

RUNS_DIR = Path("data/runs")

rows = []

for run in sorted(RUNS_DIR.iterdir()):
    summary = run / "artifacts/geometry/geometry_summary.json"

    if not summary.exists():
        continue

    with open(summary) as f:
        data = json.load(f)

    row = {}

    row["run"] = run.name
    row["seed"] = data["generator"]["seed"]

    # planform parameters
    for k, v in data["sampled_planform"].items():
        row[k] = v

    # section parameters
    for k, v in data["sampled_sections"].items():
        if isinstance(v, (int, float)):
            row[k] = v

    # metrics
    row["AR"] = data["metrics"]["aspect_ratio_aerosandbox"]
    row["span"] = data["metrics"]["full_span_m"]
    row["area"] = data["metrics"]["approx_area_m2"]

    rows.append(row)

df = pd.DataFrame(rows)

print("\n=== Geometry Samples ===\n")
print(df.round(4))

print("\n=== Variation Check ===\n")
print(df.describe().round(4))

print("\n=== Unique Seeds ===")
print(df["seed"].unique())

import matplotlib.pyplot as plt

df["AR"].hist(bins=10)
plt.title("Aspect Ratio Distribution")
plt.show()

from pathlib import Path
import json
import math

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = PROJECT_ROOT / "data" / "runs"

rows = []
plot_entries = []

for run in sorted(RUNS_DIR.iterdir()):
    if not run.is_dir():
        continue

    summary_path = run / "artifacts" / "geometry" / "geometry_summary.json"
    plot_path = run / "artifacts" / "geometry" / "plots" / "planform.png"

    if not summary_path.exists():
        continue

    with summary_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    row: dict[str, float | int | str] = {}
    row["run"] = run.name
    row["seed"] = data["generator"]["seed"]

    for k, v in data["sampled_planform"].items():
        row[k] = v

    for k, v in data["sampled_sections"].items():
        if isinstance(v, (int, float)):
            row[k] = v

    row["AR"] = data["metrics"]["aspect_ratio_aerosandbox"]
    row["span"] = data["metrics"]["full_span_m"]
    row["area"] = data["metrics"]["approx_area_m2"]

    rows.append(row)

    if plot_path.exists():
        plot_entries.append(
            {
                "run": run.name,
                "seed": data["generator"]["seed"],
                "plot_path": plot_path,
                "AR": data["metrics"]["aspect_ratio_aerosandbox"],
                "span": data["metrics"]["full_span_m"],
                "area": data["metrics"]["approx_area_m2"],
            }
        )

df = pd.DataFrame(rows)

print("\n=== Geometry Samples ===\n")
if df.empty:
    print("No geometry summaries found.")
else:
    print(df.round(4))

    print("\n=== Variation Check ===\n")
    print(df.describe().round(4))

    print("\n=== Unique Seeds ===")
    print(df["seed"].unique())

    # Save a CSV summary for later inspection
    output_csv = PROJECT_ROOT / "data" / "debug" / "seed_variation_summary.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"\nSaved summary CSV to: {output_csv}")

# ---- Plot gallery of planforms ----
if plot_entries:
    n = len(plot_entries)
    ncols = min(3, n)
    nrows = math.ceil(n / ncols)

    fig, axes = plt.subplots(nrows=nrows, ncols=ncols, figsize=(6 * ncols, 4.5 * nrows))
    fig.suptitle("Generated Planforms by Seed", fontsize=16)

    # Make axes always iterable
    if isinstance(axes, plt.Axes):
        axes = [axes]
    else:
        axes = axes.flatten()

    for ax, entry in zip(axes, plot_entries):
        img = mpimg.imread(entry["plot_path"])
        ax.imshow(img)
        ax.axis("off")
        ax.set_title(
            f"seed={entry['seed']} | AR={entry['AR']:.3f}\n"
            f"span={entry['span']:.3f} m | area={entry['area']:.3f} m²",
            fontsize=10,
        )

    # Hide unused axes
    for ax in axes[len(plot_entries):]:
        ax.axis("off")

    plt.tight_layout()
    plt.show()
else:
    print("\nNo planform plots found to display.")

import imageio.v2 as imageio

# ---- Create GIF animation of planforms ----
if plot_entries:
    gif_path = PROJECT_ROOT / "data" / "debug" / "planform_variation.gif"

    images = []

    # sort by seed so the animation is logical
    plot_entries_sorted = sorted(plot_entries, key=lambda x: x["seed"])

    for entry in plot_entries_sorted:
        img = imageio.imread(entry["plot_path"])
        images.append(img)

    gif_path.parent.mkdir(parents=True, exist_ok=True)

    imageio.mimsave(
        gif_path,
        images,
        duration=2  # seconds per frame
    )

    print(f"\nGIF saved to: {gif_path}")