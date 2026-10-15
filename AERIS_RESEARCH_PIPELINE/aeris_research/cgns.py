from __future__ import annotations

import contextlib
import ctypes
import ctypes.util
import gzip
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from .common import PipelineError, canonical_json

CG_MODE_READ = 0
REAL_SINGLE = 3
REAL_DOUBLE = 4
LOCATION = {
    0: "Null",
    1: "UserDefined",
    2: "Vertex",
    3: "CellCenter",
    4: "FaceCenter",
    5: "IFaceCenter",
    6: "JFaceCenter",
    7: "KFaceCenter",
    8: "EdgeCenter",
}
NUMPY_OF = {REAL_SINGLE: np.float32, REAL_DOUBLE: np.float64}
CTYPE_OF = {REAL_SINGLE: ctypes.c_float, REAL_DOUBLE: ctypes.c_double}
FIELD_NAMES = ("CoefPressure", "SkinFrictionMagnitude", "YPlus")


@dataclass(frozen=True)
class SurfaceZone:
    name: str
    coordinates: np.ndarray
    fields: dict[str, np.ndarray]


@dataclass(frozen=True)
class CanonicalSurface:
    coordinates: np.ndarray
    connectivity: np.ndarray
    normals: np.ndarray
    areas: np.ndarray
    fields: dict[str, np.ndarray]
    node_zone: np.ndarray
    node_i: np.ndarray
    node_j: np.ndarray
    cell_zone: np.ndarray
    cell_i: np.ndarray
    cell_j: np.ndarray
    zone_names: tuple[str, ...]
    zone_shapes: tuple[tuple[int, int], ...]
    topology_hash: str
    backend: str


class CGNSError(PipelineError):
    pass


def _library_candidates() -> list[str]:
    values: list[str] = []
    configured = os.environ.get("AERIS_LIBCGNS")
    if configured:
        values.append(configured)
    found = ctypes.util.find_library("cgns")
    if found:
        values.append(found)
    values.extend(
        [
            "/home/mike_kara/packages/CGNS-4.5.2/opt-gfortran/lib/libcgns.so.4.5",
            "libcgns.so.4.5",
            "libcgns.so.4",
            "libcgns.so",
        ]
    )
    return list(dict.fromkeys(values))


def _load_library() -> tuple[ctypes.CDLL, str]:
    errors = []
    for candidate in _library_candidates():
        try:
            return ctypes.CDLL(candidate), candidate
        except OSError as exc:
            errors.append(f"{candidate}: {exc}")
    raise CGNSError("cannot load libcgns; tried " + "; ".join(errors))


@contextlib.contextmanager
def materialized_cgns(path: Path) -> Iterator[Path]:
    """Yield a seekable CGNS path, expanding gzip archives only into /tmp."""

    source = Path(path).resolve()
    if source.suffix != ".gz":
        yield source
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix="aeris_surface_", suffix=".cgns")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as destination, gzip.open(source, "rb") as compressed:
            shutil.copyfileobj(compressed, destination, length=1024 * 1024)
        yield temporary
    except (gzip.BadGzipFile, EOFError) as exc:
        raise CGNSError(f"invalid gzip surface archive {source}: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def is_hdf5(path: Path) -> bool:
    with Path(path).open("rb") as stream:
        return stream.read(8) == b"\x89HDF\r\n\x1a\n"


class _ADFFile:
    def __init__(self, path: Path):
        self.lib, self.loaded_from = _load_library()
        self.cgsize: type[ctypes._SimpleCData] | None = None
        self.path = Path(path)
        self.number = ctypes.c_int()
        code = self.lib.cg_open(os.fsencode(self.path), CG_MODE_READ, ctypes.byref(self.number))
        if code != 0:
            raise CGNSError(f"cg_open failed for {path}: {self.error()}")

    def error(self) -> str:
        self.lib.cg_get_error.restype = ctypes.c_char_p
        return (self.lib.cg_get_error() or b"").decode(errors="replace")

    def check(self, code: int, action: str) -> None:
        if code != 0:
            raise CGNSError(f"{action}: {self.error()} (CGNS code {code})")

    def close(self) -> None:
        self.check(self.lib.cg_close(self.number.value), "close CGNS file")

    def __enter__(self) -> "_ADFFile":
        return self

    def __exit__(self, *_: object) -> bool:
        self.close()
        return False

    def zones(self) -> list[dict[str, Any]]:
        number_of_bases = ctypes.c_int()
        self.check(
            self.lib.cg_nbases(self.number.value, ctypes.byref(number_of_bases)), "read bases"
        )
        output: list[dict[str, Any]] = []
        for base in range(1, number_of_bases.value + 1):
            base_name = ctypes.create_string_buffer(33)
            cell_dim, physical_dim = ctypes.c_int(), ctypes.c_int()
            self.check(
                self.lib.cg_base_read(
                    self.number.value,
                    base,
                    base_name,
                    ctypes.byref(cell_dim),
                    ctypes.byref(physical_dim),
                ),
                f"read base {base}",
            )
            number_of_zones = ctypes.c_int()
            self.check(
                self.lib.cg_nzones(self.number.value, base, ctypes.byref(number_of_zones)),
                f"read zone count for base {base}",
            )
            for zone in range(1, number_of_zones.value + 1):
                zone_name = ctypes.create_string_buffer(33)
                widths = [self.cgsize] if self.cgsize else [ctypes.c_int32, ctypes.c_int64]
                vertex_dims = cell_dims = None
                for width in widths:
                    assert width is not None
                    dimensions = (width * 9)()
                    code = self.lib.cg_zone_read(
                        self.number.value, base, zone, zone_name, dimensions
                    )
                    if code != 0:
                        continue
                    vertices = [int(dimensions[index]) for index in range(cell_dim.value)]
                    cells = [
                        int(dimensions[cell_dim.value + index]) for index in range(cell_dim.value)
                    ]
                    if all(0 < value < 1_000_000_000 for value in vertices):
                        self.cgsize = width
                        vertex_dims, cell_dims = vertices, cells
                        break
                if vertex_dims is None or cell_dims is None:
                    raise CGNSError(f"cannot infer cgsize_t width for zone {zone}")
                output.append(
                    {
                        "base": base,
                        "zone": zone,
                        "name": zone_name.value.decode(errors="replace"),
                        "vertex_dims": vertex_dims,
                        "cell_dims": cell_dims,
                    }
                )
        return output

    def fields(self, base: int, zone: int) -> list[dict[str, Any]]:
        number_of_solutions = ctypes.c_int()
        self.check(
            self.lib.cg_nsols(self.number.value, base, zone, ctypes.byref(number_of_solutions)),
            f"read solution count for zone {zone}",
        )
        output = []
        for solution in range(1, number_of_solutions.value + 1):
            solution_name = ctypes.create_string_buffer(33)
            location = ctypes.c_int()
            self.check(
                self.lib.cg_sol_info(
                    self.number.value,
                    base,
                    zone,
                    solution,
                    solution_name,
                    ctypes.byref(location),
                ),
                f"read solution {solution}",
            )
            number_of_fields = ctypes.c_int()
            self.check(
                self.lib.cg_nfields(
                    self.number.value, base, zone, solution, ctypes.byref(number_of_fields)
                ),
                f"read field count for solution {solution}",
            )
            for field in range(1, number_of_fields.value + 1):
                data_type = ctypes.c_int()
                field_name = ctypes.create_string_buffer(33)
                self.check(
                    self.lib.cg_field_info(
                        self.number.value,
                        base,
                        zone,
                        solution,
                        field,
                        ctypes.byref(data_type),
                        field_name,
                    ),
                    f"read field {field}",
                )
                output.append(
                    {
                        "solution": solution,
                        "name": field_name.value.decode(errors="replace"),
                        "location": LOCATION.get(location.value, str(location.value)),
                        "data_type": data_type.value,
                    }
                )
        return output

    def read_coordinates(self, zone: dict[str, Any]) -> np.ndarray:
        dimensions = [value for value in zone["vertex_dims"] if value > 0]
        if len(dimensions) != 2:
            raise CGNSError(f"surface zone {zone['name']} is not two-dimensional")
        count = int(np.prod(dimensions))
        width = self.cgsize or ctypes.c_int32
        lower = (width * 2)(1, 1)
        upper = (width * 2)(*dimensions)
        axes = []
        for name in ("CoordinateX", "CoordinateY", "CoordinateZ"):
            buffer = (ctypes.c_double * count)()
            self.check(
                self.lib.cg_coord_read(
                    self.number.value,
                    zone["base"],
                    zone["zone"],
                    name.encode(),
                    REAL_DOUBLE,
                    lower,
                    upper,
                    buffer,
                ),
                f"read {zone['name']}/{name}",
            )
            axes.append(
                np.frombuffer(buffer, dtype=np.float64, count=count).reshape(dimensions, order="F")
            )
        return np.stack(axes, axis=-1)

    def _read_field_at_shape(
        self, zone: dict[str, Any], field: dict[str, Any], dimensions: list[int]
    ) -> np.ndarray:
        data_type = field["data_type"]
        if data_type not in CTYPE_OF:
            raise CGNSError(f"unsupported CGNS type {data_type} for {field['name']}")
        count = int(np.prod(dimensions))
        buffer = (CTYPE_OF[data_type] * count)()
        width = self.cgsize or ctypes.c_int32
        lower = (width * len(dimensions))(*([1] * len(dimensions)))
        upper = (width * len(dimensions))(*dimensions)
        code = self.lib.cg_field_read(
            self.number.value,
            zone["base"],
            zone["zone"],
            field["solution"],
            field["name"].encode(),
            data_type,
            lower,
            upper,
            buffer,
        )
        self.check(code, f"read {zone['name']}/{field['name']} at {dimensions}")
        return np.frombuffer(buffer, dtype=NUMPY_OF[data_type], count=count).reshape(
            dimensions, order="F"
        )

    def read_field(self, zone: dict[str, Any], field: dict[str, Any]) -> np.ndarray:
        cells = [value for value in zone["cell_dims"] if value > 0]
        vertices = [value for value in zone["vertex_dims"] if value > 0]
        candidates = [[value + 2 for value in cells], cells, vertices]
        errors = []
        for dimensions in candidates:
            try:
                return self._read_field_at_shape(zone, field, dimensions)
            except CGNSError as exc:
                errors.append(str(exc))
        raise CGNSError(
            f"cannot read {zone['name']}/{field['name']} at rind, cell, or vertex extent: "
            + "; ".join(errors)
        )


def _strip_rind(values: np.ndarray, cell_shape: tuple[int, int], context: str) -> np.ndarray:
    if values.shape == cell_shape:
        return values
    padded = tuple(value + 2 for value in cell_shape)
    if values.shape == padded:
        return values[1:-1, 1:-1]
    raise CGNSError(
        f"{context} has shape {values.shape}; expected physical {cell_shape} or rind {padded}"
    )


def _read_adf(path: Path) -> tuple[list[SurfaceZone], str]:
    output = []
    with _ADFFile(path) as handle:
        for zone in handle.zones():
            if "wall" not in zone["name"].casefold():
                continue
            coordinates = handle.read_coordinates(zone)
            cell_shape = (coordinates.shape[0] - 1, coordinates.shape[1] - 1)
            fields: dict[str, np.ndarray] = {}
            for field in handle.fields(zone["base"], zone["zone"]):
                if field["name"] not in FIELD_NAMES:
                    continue
                if field["location"] != "CellCenter":
                    raise CGNSError(
                        f"{zone['name']}/{field['name']} is {field['location']}, not CellCenter"
                    )
                values = handle.read_field(zone, field)
                fields[field["name"]] = _strip_rind(
                    values, cell_shape, f"{zone['name']}/{field['name']}"
                ).astype(np.float64, copy=False)
            output.append(SurfaceZone(zone["name"], coordinates, fields))
        backend = f"ADF:CGNS_MLL:{handle.loaded_from}"
    return output, backend


def _hdf_data(group: Any, name: str) -> np.ndarray:
    node = group[name]
    if hasattr(node, "keys") and " data" in node:
        return np.asarray(node[" data"])
    return np.asarray(node)


def _read_hdf5(path: Path) -> tuple[list[SurfaceZone], str]:
    try:
        import h5py
    except ImportError as exc:
        raise CGNSError("h5py is required for HDF5-backed CGNS") from exc

    output: list[SurfaceZone] = []
    with h5py.File(path, "r") as handle:
        zones: list[tuple[str, Any]] = []

        def collect(name: str, node: Any) -> None:
            if not isinstance(node, h5py.Group):
                return
            label = node.attrs.get("label", b"")
            if isinstance(label, bytes):
                label = label.decode(errors="replace")
            if label == "Zone_t" and "wall" in name.casefold():
                zones.append((name.rsplit("/", 1)[-1], node))

        handle.visititems(collect)
        for name, zone in zones:
            coordinates_group = zone["GridCoordinates"]
            coordinates = np.stack(
                [_hdf_data(coordinates_group, f"Coordinate{axis}").T for axis in "XYZ"],
                axis=-1,
            )
            cell_shape = (coordinates.shape[0] - 1, coordinates.shape[1] - 1)
            solution = next(
                (value for key, value in zone.items() if "solution" in key.casefold()), None
            )
            fields = {}
            if solution is not None:
                for field_name in FIELD_NAMES:
                    if field_name in solution:
                        values = _hdf_data(solution, field_name).T
                        fields[field_name] = _strip_rind(
                            values, cell_shape, f"{name}/{field_name}"
                        ).astype(np.float64, copy=False)
            output.append(SurfaceZone(name, coordinates, fields))
    return output, "HDF5:h5py"


def _canonicalise(zones: list[SurfaceZone], backend: str) -> CanonicalSurface:
    if not zones:
        raise CGNSError("surface CGNS contains no wall zones")
    ordered = sorted(zones, key=lambda zone: zone.name)
    zone_names = tuple(zone.name for zone in ordered)
    if len(set(zone_names)) != len(zone_names):
        raise CGNSError("wall zone names are not unique")

    all_coordinates = []
    all_connectivity = []
    all_node_zone = []
    all_node_i = []
    all_node_j = []
    all_cell_zone = []
    all_cell_i = []
    all_cell_j = []
    field_chunks: dict[str, list[np.ndarray]] = {name: [] for name in FIELD_NAMES}
    zone_shapes = []
    node_offset = 0

    for zone_index, zone in enumerate(ordered):
        coordinates = np.asarray(zone.coordinates, dtype=np.float64)
        if coordinates.ndim != 3 or coordinates.shape[-1] != 3:
            raise CGNSError(f"zone {zone.name} coordinates do not have shape (ni,nj,3)")
        ni, nj = coordinates.shape[:2]
        if ni < 2 or nj < 2:
            raise CGNSError(f"zone {zone.name} is too small: {(ni, nj)}")
        zone_shapes.append((ni, nj))
        indices = np.arange(ni * nj, dtype=np.int64).reshape((ni, nj), order="F")
        connectivity = np.stack(
            [
                indices[:-1, :-1],
                indices[1:, :-1],
                indices[1:, 1:],
                indices[:-1, 1:],
            ],
            axis=-1,
        ).reshape((-1, 4), order="F")
        all_connectivity.append(connectivity + node_offset)
        all_coordinates.append(coordinates.reshape((-1, 3), order="F"))

        ii, jj = np.meshgrid(np.arange(ni), np.arange(nj), indexing="ij")
        all_node_zone.append(np.full(ni * nj, zone_index, dtype=np.int32))
        all_node_i.append(ii.reshape(-1, order="F").astype(np.int32))
        all_node_j.append(jj.reshape(-1, order="F").astype(np.int32))
        ci, cj = np.meshgrid(np.arange(ni - 1), np.arange(nj - 1), indexing="ij")
        cell_count = (ni - 1) * (nj - 1)
        all_cell_zone.append(np.full(cell_count, zone_index, dtype=np.int32))
        all_cell_i.append(ci.reshape(-1, order="F").astype(np.int32))
        all_cell_j.append(cj.reshape(-1, order="F").astype(np.int32))
        for field_name in FIELD_NAMES:
            values = zone.fields.get(field_name)
            if values is None:
                field_chunks[field_name].append(np.full(cell_count, np.nan))
            else:
                expected = (ni - 1, nj - 1)
                if values.shape != expected:
                    raise CGNSError(
                        f"zone {zone.name}/{field_name} is {values.shape}, expected {expected}"
                    )
                field_chunks[field_name].append(values.reshape(-1, order="F"))
        node_offset += ni * nj

    coordinates = np.concatenate(all_coordinates)
    connectivity = np.concatenate(all_connectivity).astype(np.int64, copy=False)
    p00 = coordinates[connectivity[:, 0]]
    p10 = coordinates[connectivity[:, 1]]
    p11 = coordinates[connectivity[:, 2]]
    p01 = coordinates[connectivity[:, 3]]
    # ADflow's structured surface export winds wall faces into the fluid. The
    # outward body normal is therefore the negative diagonal cross product.
    # This convention reproduces ADflow pressure CL across the archived sweep;
    # centroid-based per-cell flipping is invalid for an open half-model wall.
    area_vectors = -0.5 * np.cross(p11 - p00, p01 - p10)
    areas = np.linalg.norm(area_vectors, axis=1)
    if np.any(~np.isfinite(areas)) or np.any(areas <= 0.0):
        raise CGNSError("wall surface contains non-finite or zero-area cells")
    normals = area_vectors / areas[:, None]

    node_zone = np.concatenate(all_node_zone)
    node_i = np.concatenate(all_node_i)
    node_j = np.concatenate(all_node_j)
    cell_zone = np.concatenate(all_cell_zone)
    cell_i = np.concatenate(all_cell_i)
    cell_j = np.concatenate(all_cell_j)
    topology_description = {
        "schema": "aeris.canonical_surface_topology.v1",
        "zone_order": list(zone_names),
        "zone_vertex_shapes": [list(shape) for shape in zone_shapes],
        "node_order": "zone-name lexical, then CGNS Fortran order (i fastest)",
        "cell_order": "zone-name lexical, then CGNS Fortran order (i fastest)",
        "cell_type": "QUAD_4",
    }
    digest = hashlib.sha256()
    digest.update(canonical_json(topology_description))
    digest.update(connectivity.astype("<i8", copy=False).tobytes(order="C"))
    digest.update(node_zone.astype("<i4", copy=False).tobytes(order="C"))
    digest.update(node_i.astype("<i4", copy=False).tobytes(order="C"))
    digest.update(node_j.astype("<i4", copy=False).tobytes(order="C"))

    return CanonicalSurface(
        coordinates=coordinates,
        connectivity=connectivity,
        normals=normals,
        areas=areas,
        fields={name: np.concatenate(chunks) for name, chunks in field_chunks.items()},
        node_zone=node_zone,
        node_i=node_i,
        node_j=node_j,
        cell_zone=cell_zone,
        cell_i=cell_i,
        cell_j=cell_j,
        zone_names=zone_names,
        zone_shapes=tuple(zone_shapes),
        topology_hash=digest.hexdigest(),
        backend=backend,
    )


def read_surface(path: Path) -> CanonicalSurface:
    """Read an ADF/HDF5 CGNS surface archive into deterministic wall ordering."""

    with materialized_cgns(path) as materialized:
        zones, backend = (
            _read_hdf5(materialized) if is_hdf5(materialized) else _read_adf(materialized)
        )
    return _canonicalise(zones, backend)


def pressure_coefficients(
    cp: np.ndarray,
    coordinates: np.ndarray,
    connectivity: np.ndarray,
    normals: np.ndarray,
    areas: np.ndarray,
    *,
    alpha_deg: float,
    area_ref: float,
    chord_ref: float,
    moment_ref_xyz: np.ndarray,
    symmetry_factor: float = 1.0,
) -> dict[str, float]:
    """Integrate pressure-only force and moment coefficients on the exported wall."""

    cp = np.asarray(cp, dtype=float)
    force_cells = -cp[:, None] * normals * areas[:, None] * symmetry_factor / area_ref
    force = force_cells.sum(axis=0)
    radians = np.deg2rad(alpha_deg)
    lift_direction = np.array([-np.sin(radians), 0.0, np.cos(radians)])
    centres = coordinates[connectivity].mean(axis=1)
    arms = centres - np.asarray(moment_ref_xyz, dtype=float)
    moments = np.cross(arms, force_cells).sum(axis=0) / chord_ref
    return {
        "cl_pressure": float(np.dot(force, lift_direction)),
        "cmy_pressure": float(moments[1]),
    }
