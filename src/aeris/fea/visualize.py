"""Reproducible, open-source visualizations for governed FEA runs and studies."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def _read_calculix_mesh(
    path: Path,
) -> tuple[dict[int, np.ndarray], dict[int, tuple[int, ...]], dict[int, str]]:
    nodes: dict[int, np.ndarray] = {}
    elements: dict[int, tuple[int, ...]] = {}
    regions: dict[int, str] = {}
    section = ""
    current_region = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        upper = line.upper()
        if upper.startswith("*NODE"):
            section, current_region = "node", ""
            continue
        if upper.startswith("*ELEMENT"):
            section, current_region = "element", ""
            continue
        if upper.startswith("*ELSET"):
            section, current_region = "elset", upper.split("ELSET=", 1)[-1].strip()
            continue
        if line.startswith("*") or not line:
            if line.startswith("*"):
                section = ""
            continue
        try:
            values = [float(item.strip()) for item in line.split(",")]
        except ValueError:
            continue
        if section == "node" and len(values) >= 4:
            nodes[int(values[0])] = np.asarray(values[1:4], dtype=float)
        elif section == "element" and len(values) >= 5:
            elements[int(values[0])] = tuple(int(value) for value in values[1:])
        elif section == "elset":
            for value in values:
                regions[int(value)] = current_region
    return nodes, elements, regions


def plot_mesh(case_dir: Path, output_dir: Path) -> Path:
    """Plot the audited shell mesh, colored by structural region."""
    mesh_path = case_dir / "mesh" / "wingbox_mesh.inp"
    nodes, elements, regions = _read_calculix_mesh(mesh_path)
    fig = plt.figure(figsize=(12, 7))
    ax = fig.add_subplot(111, projection="3d")
    names = sorted(set(regions.values()))
    colors = plt.get_cmap("tab20")(np.linspace(0.05, 0.95, max(len(names), 1)))
    color_map = dict(zip(names, colors, strict=False))
    for element_id, connectivity in elements.items():
        points = np.asarray([nodes[node_id] for node_id in connectivity if node_id in nodes])
        if len(points) < 3:
            continue
        closed = np.vstack([points, points[0]])
        region = regions.get(element_id, "UNASSIGNED")
        ax.plot(
            closed[:, 0], closed[:, 1], closed[:, 2],
            color=color_map.get(region, "0.55"), lw=0.45,
        )
    for name, color in color_map.items():
        ax.plot([], [], [], color=color, lw=3, label=name)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_zlabel("z [m]")
    ax.set_title("AERIS governed shell mesh and structural regions")
    ax.view_init(elev=24, azim=-62)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    fig.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "mesh_topology.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def plot_oas_comparison(case_dir: Path, output_dir: Path) -> Path:
    """Plot OAS/CFD lift and absolute comparison errors from the validation report."""
    report = json.loads((case_dir / "validation" / "openaerostruct_validation.json").read_text())
    rows = report["comparisons"]
    alpha = np.asarray([row["alpha_deg"] for row in rows], dtype=float)
    cfd = np.asarray([row["cfd_cl"] for row in rows], dtype=float)
    oas = np.asarray([row["oas_cl"] for row in rows], dtype=float)
    errors = np.abs(oas - cfd)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    axes[0].plot(alpha, cfd, "o-", label="S8 CFD authority")
    axes[0].plot(alpha, oas, "s--", label="OpenAeroStruct")
    axes[0].set(xlabel="Angle of attack [deg]", ylabel="$C_L$", title="Global lift comparison")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize=8)
    axes[1].bar(alpha, errors, width=0.65, color="#d97706")
    axes[1].axhline(report["tolerances"]["max_abs_cl_error"], color="k", ls="--", lw=1)
    axes[1].set(
        xlabel="Angle of attack [deg]",
        ylabel=r"$|\Delta C_L|$",
        title="Absolute error gate",
    )
    axes[1].grid(axis="y", alpha=0.25)
    fig.suptitle("AERIS S8 geometry: OpenAeroStruct cross-check", fontsize=13)
    fig.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "oas_comparison.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def plot_study(study_dir: Path, output_dir: Path, *, filename: str | None = None) -> Path:
    """Plot mass, displacement, and stress for any completed study report."""
    report = json.loads((study_dir / "study_report.json").read_text())
    rows = [row for row in report.get("variants", []) if row.get("metrics")]
    if not rows:
        raise ValueError(f"study report has no metrics: {study_dir}")
    labels = [str(row["name"]) for row in rows]
    metrics = [row["metrics"] for row in rows]
    x = np.arange(len(labels))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    axes[0].bar(
        x,
        [float(item.get("full_structural_mass_kg", np.nan)) for item in metrics],
        color="#2563eb",
    )
    axes[0].set_ylabel("Mass [kg]")
    axes[1].plot(
        x,
        [float(item.get("max_displacement_m", np.nan)) * 1e3 for item in metrics],
        "o-",
        color="#059669",
    )
    axes[1].set_ylabel("Maximum displacement [mm]")
    axes[2].plot(
        x,
        [float(item.get("max_von_mises_pa", np.nan)) / 1e6 for item in metrics],
        "o-",
        color="#dc2626",
    )
    axes[2].set_ylabel("Peak von Mises [MPa]")
    for axis in axes:
        axis.set_xticks(x, labels, rotation=45, ha="right", fontsize=8)
        axis.grid(axis="y", alpha=0.25)
    axes[0].set_title("Mass")
    axes[1].set_title("Deflection")
    axes[2].set_title("Stress")
    fig.suptitle(f"AERIS structural study: {report.get('study', study_dir.name)}", fontsize=13)
    fig.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (filename or "study_comparison.png")
    fig.savefig(path, dpi=180)
    plt.close(fig)
    return path


def generate_visualizations(
    case_dir: Path, output_dir: Path, study_dirs: tuple[Path, ...] = ()
) -> dict[str, str]:
    """Generate all available case/study plots and return their paths."""
    outputs = {"mesh": str(plot_mesh(case_dir, output_dir))}
    if (case_dir / "validation" / "openaerostruct_validation.json").is_file():
        outputs["openaerostruct"] = str(plot_oas_comparison(case_dir, output_dir))
    for index, study_dir in enumerate(study_dirs):
        report = json.loads((study_dir / "study_report.json").read_text(encoding="utf-8"))
        study_name = str(report.get("study", study_dir.name)).replace("/", "_")
        outputs[f"study_{index}"] = str(
            plot_study(study_dir, output_dir, filename=f"study_{study_name}.png")
        )
    manifest = output_dir / "visualization_manifest.json"
    manifest.write_text(
        json.dumps({"schema": "aeris.fea.visualization.v1", "outputs": outputs}, indent=2)
        + "\n"
    )
    roadmap = output_dir / "FEA_VISUAL_REPORT.md"
    roadmap.write_text(
        "# AERIS FEA visual report\n\n"
        "This report is generated from hashed case/study artifacts; PNGs are diagnostic views, "
        "not additional acceptance gates.\n\n"
        "## Included evidence\n\n"
        "- `mesh_topology.png`: audited shell elements colored by region.\n"
        "- `oas_comparison.png`: S8 CFD authority versus OpenAeroStruct global lift.\n"
        "- `study_comparison.png`: mass, displacement, and stress across each supplied study.\n\n"
        "## Next three steps toward robust FEA design-space exploration\n\n"
        "1. **Release structural authorities:** replace provisional box depth, spar locations, "
        "aircraft mass, and typical aluminum values with versioned released geometry, mass, "
        "material allowables, and manufacturing knockdowns. The governance gate will fail closed "
        "until hashes and provenance are updated.\n"
        "2. **Expand the parameterized structural model:** promote rib pitch, fittings, hinge "
        "loads, "
        "cut-out envelopes, laminate/metal section definitions, and joint stiffness to explicit "
        "study variables; add response surfaces for mass, stress, deflection, and buckling "
        "margin.\n"
        "3. **Close the validation loop:** calibrate modal/buckling/nonlinear settings against a "
        "coupon and representative-wing test, then enable the untouched hold-out for threshold "
        "freeze and automated DSE ranking.\n\n"
        "Current status: conceptual screening and software verification are automated; physical "
        "evidence and released structural authorities remain required for detailed-design use.\n",
        encoding="utf-8",
    )
    outputs["report"] = str(roadmap)
    outputs["manifest"] = str(manifest)
    return outputs
