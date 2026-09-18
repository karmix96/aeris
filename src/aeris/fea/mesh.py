"""Deterministic closed-shell wingbox meshing and quality audit.

The mesh is written in both Gmsh 2.2 (open interchange/visualization) and
CalculiX/Abaqus INP (solver input) formats.  Generation is deliberately pure
Python/numpy so a campaign can prepare and audit meshes even when Gmsh's GUI or
shared library is unavailable; the resulting ``.msh`` is directly readable by
Gmsh and other open-source preprocessors.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from aeris.fea.case.spec import MeshSpec, SectionSpec, WingboxSpec


@dataclass(frozen=True)
class ShellElement:
    id: int
    nodes: tuple[int, int, int, int]
    region: str
    span_fraction: float
    chord_fraction: float
    area_m2: float


@dataclass(frozen=True)
class StructuralMesh:
    nodes: dict[int, tuple[float, float, float]]
    elements: tuple[ShellElement, ...]
    root_nodes: tuple[int, ...]
    semispan_m: float
    quality: dict[str, float]
    mass_kg: float


def region_thickness(region: str, section: SectionSpec) -> float:
    if region == "RIB":
        return section.rib_thickness_m or section.spar_thickness_m
    if region.endswith("ROOT_DOUBLER"):
        return section.root_doubler_thickness_m or max(
            section.skin_thickness_m, section.spar_thickness_m
        )
    if region == "SPAR_REAR_HINGE":
        return section.hinge_reinforcement_thickness_m or section.spar_thickness_m
    if region.endswith("CUTOUT_REINFORCEMENT"):
        return section.cutout_reinforcement_thickness_m or section.skin_thickness_m
    if region.startswith("SKIN"):
        return section.skin_thickness_m
    return section.spar_thickness_m


def _resample_stations(
    stations: list[dict[str, object]], target_size: float
) -> list[dict[str, float]]:
    result: list[dict[str, float]] = []
    keys = ("x_le_m", "y_m", "z_le_m", "chord_m", "twist_deg", "dihedral_deg")
    for index in range(len(stations) - 1):
        a, b = stations[index], stations[index + 1]
        ay, by = float(a["y_m"]), float(b["y_m"])
        az, bz = float(a["z_le_m"]), float(b["z_le_m"])
        span_distance = math.hypot(by - ay, bz - az)
        divisions = max(1, int(math.ceil(span_distance / target_size)))
        for local in range(divisions):
            t = local / divisions
            result.append(
                {
                    key: (1.0 - t) * float(a.get(key, 0.0)) + t * float(b.get(key, 0.0))
                    for key in keys
                }
            )
    result.append({key: float(stations[-1].get(key, 0.0)) for key in keys})
    return result


def _point(station: dict[str, float], xi: float, eta: float, wingbox: WingboxSpec) -> np.ndarray:
    """Wingbox point: xi along chord, eta=-1..1 through box depth."""
    theta = math.radians(station["twist_deg"])
    chord_axis = np.array([math.cos(theta), 0.0, -math.sin(theta)])
    thickness_axis = np.array([math.sin(theta), 0.0, math.cos(theta)])
    leading_edge = np.array([station["x_le_m"], station["y_m"], station["z_le_m"]])
    depth = max(wingbox.minimum_depth_m, wingbox.depth_ratio * station["chord_m"])
    return leading_edge + xi * station["chord_m"] * chord_axis + eta * 0.5 * depth * thickness_axis


def _quad_area(points: list[np.ndarray]) -> float:
    return 0.5 * float(
        np.linalg.norm(np.cross(points[1] - points[0], points[2] - points[0]))
    ) + 0.5 * float(np.linalg.norm(np.cross(points[2] - points[0], points[3] - points[0])))


def _quad_quality(points: list[np.ndarray]) -> tuple[float, float]:
    lengths = [float(np.linalg.norm(points[(i + 1) % 4] - points[i])) for i in range(4)]
    aspect = max(lengths) / max(min(lengths), 1e-15)
    angles: list[float] = []
    for i in range(4):
        a = points[(i - 1) % 4] - points[i]
        b = points[(i + 1) % 4] - points[i]
        cosine = float(np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-30))
        angles.append(math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0)))))
    return aspect, min(angles)


def build_wingbox_mesh(
    stations_payload: dict[str, object],
    wingbox: WingboxSpec,
    mesh_spec: MeshSpec,
    section: SectionSpec,
    density_kg_m3: float,
) -> StructuralMesh:
    stations_raw = stations_payload["stations"]
    assert isinstance(stations_raw, list)
    stations = _resample_stations(stations_raw, mesh_spec.target_size_m)  # type: ignore[arg-type]
    semispan = stations[-1]["y_m"]
    if semispan <= 0.0:
        raise ValueError("wing semispan must be positive")
    hinge_start = wingbox.hinge_span_start_fraction
    hinge_end = wingbox.hinge_span_end_fraction
    if wingbox.hinge_from_design_vector:
        vector = stations_payload.get("design_vector")
        if not isinstance(vector, dict):
            raise ValueError("hinge_from_design_vector requires station design_vector metadata")
        hinge_start = float(vector["elevon_start_frac"])
        hinge_end = float(vector["elevon_end_frac"])

    nodes: dict[int, tuple[float, float, float]] = {}
    node_by_key: dict[tuple[float, float, float], int] = {}

    def node_id(point: np.ndarray) -> int:
        key = tuple(round(float(value), 12) for value in point)
        existing = node_by_key.get(key)
        if existing is not None:
            return existing
        identifier = len(nodes) + 1
        node_by_key[key] = identifier
        nodes[identifier] = tuple(float(value) for value in point)
        return identifier

    elements: list[ShellElement] = []
    regions: list[tuple[str, list[float], list[float], bool]] = [
        (
            "SKIN_TOP",
            np.linspace(
                wingbox.front_spar_fraction,
                wingbox.rear_spar_fraction,
                mesh_spec.chordwise_elements + 1,
            ).tolist(),
            [1.0],
            True,
        ),
        (
            "SKIN_BOTTOM",
            np.linspace(
                wingbox.front_spar_fraction,
                wingbox.rear_spar_fraction,
                mesh_spec.chordwise_elements + 1,
            ).tolist(),
            [-1.0],
            True,
        ),
        (
            "SPAR_FRONT",
            [wingbox.front_spar_fraction],
            np.linspace(-1.0, 1.0, mesh_spec.depth_elements + 1).tolist(),
            False,
        ),
        (
            "SPAR_REAR",
            [wingbox.rear_spar_fraction],
            np.linspace(-1.0, 1.0, mesh_spec.depth_elements + 1).tolist(),
            False,
        ),
    ]

    for region, xis, etas, chordwise in regions:
        grid: list[list[int]] = []
        for station in stations:
            varying = xis if chordwise else etas
            row = [
                node_id(
                    _point(
                        station,
                        coordinate if chordwise else xis[0],
                        etas[0] if chordwise else coordinate,
                        wingbox,
                    )
                )
                for coordinate in varying
            ]
            grid.append(row)
        for i in range(len(stations) - 1):
            span_fraction = 0.5 * (stations[i]["y_m"] + stations[i + 1]["y_m"]) / semispan
            for j in range(len(grid[i]) - 1):
                chord_fraction = (
                    0.5 * (float(xis[j]) + float(xis[j + 1]))
                    if chordwise
                    else float(xis[0])
                )
                effective_region = region
                if chordwise:
                    surface = "top" if region == "SKIN_TOP" else "bottom"
                    inside_cutout = False
                    near_cutout = False
                    span_padding = mesh_spec.target_size_m / semispan
                    chord_padding = (
                        wingbox.rear_spar_fraction - wingbox.front_spar_fraction
                    ) / mesh_spec.chordwise_elements
                    for cutout in wingbox.cutouts:
                        if cutout.surface != surface:
                            continue
                        inside = (
                            cutout.span_start_fraction <= span_fraction
                            <= cutout.span_end_fraction
                            and cutout.chord_start_fraction <= chord_fraction
                            <= cutout.chord_end_fraction
                        )
                        nearby = (
                            cutout.span_start_fraction - span_padding
                            <= span_fraction
                            <= cutout.span_end_fraction + span_padding
                            and cutout.chord_start_fraction - chord_padding
                            <= chord_fraction
                            <= cutout.chord_end_fraction + chord_padding
                        )
                        inside_cutout = inside_cutout or inside
                        near_cutout = near_cutout or nearby
                    if inside_cutout:
                        continue
                    if near_cutout:
                        effective_region = f"{region}_CUTOUT_REINFORCEMENT"
                if span_fraction <= wingbox.root_doubler_span_fraction:
                    effective_region = f"{region}_ROOT_DOUBLER"
                if region == "SPAR_REAR" and (
                    hinge_start <= span_fraction <= hinge_end
                ):
                    effective_region = "SPAR_REAR_HINGE"
                connectivity = (grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j])
                # Bottom skin is reversed so outward shell normals are consistent.
                if region == "SKIN_BOTTOM":
                    connectivity = tuple(reversed(connectivity))  # type: ignore[assignment]
                points = [np.asarray(nodes[n], dtype=float) for n in connectivity]
                area = _quad_area(points)
                if area <= 1e-14:
                    raise ValueError(
                        f"collapsed {region} element near span fraction {span_fraction:.6f}"
                    )
                elements.append(
                    ShellElement(
                        id=len(elements) + 1,
                        nodes=connectivity,
                        region=effective_region,
                        span_fraction=span_fraction,
                        chord_fraction=chord_fraction,
                        area_m2=area,
                    )
                )

    # Internal ribs fill selected wingbox cross-sections and share all perimeter
    # nodes with the skins/spars. Fractions are snapped deterministically to the
    # nearest resampled station and duplicates are rejected by station index.
    rib_indices = sorted(
        {
            min(
                range(1, len(stations) - 1),
                key=lambda index: abs(stations[index]["y_m"] / semispan - fraction),
            )
            for fraction in wingbox.rib_span_fractions
        }
    )
    rib_xis = np.linspace(
        wingbox.front_spar_fraction,
        wingbox.rear_spar_fraction,
        mesh_spec.chordwise_elements + 1,
    )
    rib_etas = np.linspace(-1.0, 1.0, mesh_spec.depth_elements + 1)
    for station_index in rib_indices:
        station = stations[station_index]
        grid = [
            [node_id(_point(station, float(xi), float(eta), wingbox)) for xi in rib_xis]
            for eta in rib_etas
        ]
        for j in range(mesh_spec.depth_elements):
            for k in range(mesh_spec.chordwise_elements):
                connectivity = (
                    grid[j][k],
                    grid[j][k + 1],
                    grid[j + 1][k + 1],
                    grid[j + 1][k],
                )
                points = [np.asarray(nodes[node], dtype=float) for node in connectivity]
                area = _quad_area(points)
                elements.append(
                    ShellElement(
                        id=len(elements) + 1,
                        nodes=connectivity,
                        region="RIB",
                        span_fraction=station["y_m"] / semispan,
                        chord_fraction=0.5 * (float(rib_xis[k]) + float(rib_xis[k + 1])),
                        area_m2=area,
                    )
                )

    aspects: list[float] = []
    angles: list[float] = []
    for element in elements:
        quality = _quad_quality([np.asarray(nodes[n]) for n in element.nodes])
        aspects.append(quality[0])
        angles.append(quality[1])
    quality = {
        "max_aspect_ratio": max(aspects),
        "min_corner_angle_deg": min(angles),
        "element_count": float(len(elements)),
        "node_count": float(len(nodes)),
    }
    if quality["max_aspect_ratio"] > mesh_spec.max_aspect_ratio:
        raise ValueError(
            f"structural mesh max aspect ratio {quality['max_aspect_ratio']:.3f} exceeds "
            f"gate {mesh_spec.max_aspect_ratio:.3f}"
        )
    if quality["min_corner_angle_deg"] < mesh_spec.min_corner_angle_deg:
        raise ValueError(
            f"structural mesh min corner angle {quality['min_corner_angle_deg']:.3f} deg is below "
            f"gate {mesh_spec.min_corner_angle_deg:.3f} deg"
        )

    half_mass = sum(
        element.area_m2
        * region_thickness(element.region, section)
        * density_kg_m3
        for element in elements
    )
    root_nodes = tuple(
        identifier for identifier, xyz in nodes.items() if abs(xyz[1] - stations[0]["y_m"]) < 1e-10
    )
    return StructuralMesh(
        nodes=nodes,
        elements=tuple(elements),
        root_nodes=root_nodes,
        semispan_m=semispan,
        quality=quality,
        mass_kg=2.0 * half_mass if bool(stations_payload.get("symmetric", True)) else half_mass,
    )


def write_mesh_artifacts(mesh: StructuralMesh, output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    gmsh_path = output_dir / "wingbox.msh"
    with gmsh_path.open("w", encoding="utf-8") as handle:
        handle.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")
        handle.write(f"$Nodes\n{len(mesh.nodes)}\n")
        for identifier, xyz in mesh.nodes.items():
            handle.write(f"{identifier} {xyz[0]:.16g} {xyz[1]:.16g} {xyz[2]:.16g}\n")
        handle.write("$EndNodes\n")
        handle.write(f"$Elements\n{len(mesh.elements)}\n")
        regions = sorted({element.region for element in mesh.elements})
        region_ids = {region: index + 1 for index, region in enumerate(regions)}
        for element in mesh.elements:
            nodes = " ".join(str(node) for node in element.nodes)
            region_id = region_ids[element.region]
            handle.write(f"{element.id} 3 2 {region_id} {region_id} {nodes}\n")
        handle.write("$EndElements\n")

    include_path = output_dir / "wingbox_mesh.inp"
    with include_path.open("w", encoding="utf-8") as handle:
        handle.write("*NODE, NSET=NALL\n")
        for identifier, xyz in mesh.nodes.items():
            # Fixed decimal fields avoid a CalculiX 2.21 free-field parser
            # failure on long scientific-notation coordinates.
            handle.write(f"{identifier}, {xyz[0]:.12f}, {xyz[1]:.12f}, {xyz[2]:.12f}\n")
        regions = sorted({element.region for element in mesh.elements})
        for region in regions:
            handle.write(f"*ELEMENT, TYPE=S4, ELSET={region}\n")
            for element in mesh.elements:
                if element.region == region:
                    handle.write(
                        f"{element.id}, " + ", ".join(str(n) for n in element.nodes) + "\n"
                    )
        handle.write("*NSET, NSET=ROOT\n")
        for start in range(0, len(mesh.root_nodes), 16):
            handle.write(", ".join(str(n) for n in mesh.root_nodes[start : start + 16]) + "\n")
        handle.write("*ELSET, ELSET=EALL\n")
        for start in range(0, len(mesh.elements), 16):
            handle.write(", ".join(str(e.id) for e in mesh.elements[start : start + 16]) + "\n")

    report_path = output_dir / "mesh_report.json"
    report = {
        "schema": "aeris.fea.mesh_report.v1",
        "node_count": len(mesh.nodes),
        "element_count": len(mesh.elements),
        "root_node_count": len(mesh.root_nodes),
        "semispan_m": mesh.semispan_m,
        "full_structural_mass_kg": mesh.mass_kg,
        "quality": mesh.quality,
        "regions": {
            region: sum(e.region == region for e in mesh.elements)
            for region in sorted({element.region for element in mesh.elements})
        },
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "gmsh_mesh": str(gmsh_path),
        "calculix_mesh": str(include_path),
        "mesh_report": str(report_path),
    }
