"""Independent post-solve quality checks for S6 CFD cases."""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np

YPLUS_SCHEMA = "aeris.mesh.s6_wall_yplus.v1"
YPLUS_TARGET = 1.0
YPLUS_P95_MAX = 1.0
YPLUS_P99_MAX = 2.0
YPLUS_ABSOLUTE_MAX = 5.0
YPLUS_WALL_DISTANCE_CONVENTION = (
    "ADflow YPlus sampled at the first off-wall cell centroid; values are not "
    "rescaled to the full first-cell height"
)

_CGNS_MODE_READ = 0
_CGNS_REAL_DOUBLE = 4
_CGNS_NAME_BYTES = 33
_CGNS_SIZE = ctypes.c_int32


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cgns_error(library: ctypes.CDLL) -> str:
    library.cg_get_error.restype = ctypes.c_char_p
    message = library.cg_get_error()
    return message.decode("utf-8", errors="replace") if message else "unknown CGNS error"


def _check_cgns(code: int, action: str, library: ctypes.CDLL) -> None:
    if code != 0:
        raise RuntimeError(f"{action}: {_cgns_error(library)}")


def _load_cgns_library() -> tuple[ctypes.CDLL, str]:
    """Load the CGNS library used for ADF surface output on this solver host."""
    configured = os.environ.get("AERIS_CGNS_LIBRARY")
    discovered = ctypes.util.find_library("cgns")
    candidates: list[str] = []
    if configured:
        candidates.append(configured)
    if discovered:
        for directory in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep):
            if directory:
                candidates.append(str(Path(directory) / discovered))
        candidates.append(discovered)
    candidates.extend(
        str(path) for path in sorted(Path.home().glob("packages/CGNS-*/opt-*/lib/libcgns.so*"))
    )

    failures: list[str] = []
    library: ctypes.CDLL | None = None
    loaded_from = ""
    for candidate in dict.fromkeys(candidates):
        try:
            library = ctypes.CDLL(candidate)
            loaded_from = str(Path(candidate).resolve()) if Path(candidate).is_file() else candidate
            break
        except OSError as error:
            failures.append(f"{candidate}: {error}")
    if library is None:
        detail = "; ".join(failures) if failures else "no candidate library found"
        raise RuntimeError(f"unable to load libcgns: {detail}")

    int_pointer = ctypes.POINTER(ctypes.c_int)
    size_pointer = ctypes.POINTER(_CGNS_SIZE)
    library.cg_open.argtypes = [ctypes.c_char_p, ctypes.c_int, int_pointer]
    library.cg_open.restype = ctypes.c_int
    library.cg_close.argtypes = [ctypes.c_int]
    library.cg_close.restype = ctypes.c_int
    library.cg_nbases.argtypes = [ctypes.c_int, int_pointer]
    library.cg_nbases.restype = ctypes.c_int
    library.cg_base_read.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        int_pointer,
        int_pointer,
    ]
    library.cg_base_read.restype = ctypes.c_int
    library.cg_nzones.argtypes = [ctypes.c_int, ctypes.c_int, int_pointer]
    library.cg_nzones.restype = ctypes.c_int
    library.cg_zone_read.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        size_pointer,
    ]
    library.cg_zone_read.restype = ctypes.c_int
    library.cg_ngrids.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, int_pointer]
    library.cg_ngrids.restype = ctypes.c_int
    library.cg_ncoords.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, int_pointer]
    library.cg_ncoords.restype = ctypes.c_int
    library.cg_index_dim.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        int_pointer,
    ]
    library.cg_index_dim.restype = ctypes.c_int
    library.cg_nsols.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, int_pointer]
    library.cg_nsols.restype = ctypes.c_int
    library.cg_sol_info.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        int_pointer,
    ]
    library.cg_sol_info.restype = ctypes.c_int
    library.cg_sol_size.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        int_pointer,
        size_pointer,
    ]
    library.cg_sol_size.restype = ctypes.c_int
    library.cg_nfields.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        int_pointer,
    ]
    library.cg_nfields.restype = ctypes.c_int
    library.cg_field_info.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        int_pointer,
        ctypes.c_char_p,
    ]
    library.cg_field_info.restype = ctypes.c_int
    library.cg_field_read.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        size_pointer,
        size_pointer,
        ctypes.c_void_p,
    ]
    library.cg_field_read.restype = ctypes.c_int
    return library, loaded_from


def _symmetric_rind_widths(
    stored_shape: tuple[int, ...],
    physical_shape: tuple[int, ...],
) -> tuple[int, ...]:
    if len(stored_shape) != len(physical_shape):
        raise RuntimeError(
            f"stored shape {stored_shape!r} and physical shape {physical_shape!r} differ in rank"
        )
    differences = tuple(
        stored - physical for stored, physical in zip(stored_shape, physical_shape, strict=True)
    )
    if any(difference < 0 or difference % 2 for difference in differences):
        raise RuntimeError(
            f"cannot infer symmetric CGNS rind: stored={stored_shape!r}, "
            f"physical={physical_shape!r}"
        )
    return tuple(difference // 2 for difference in differences)


def _trim_symmetric_rind(
    values: np.ndarray,
    stored_shape: tuple[int, ...],
    physical_shape: tuple[int, ...],
) -> tuple[np.ndarray, tuple[int, ...]]:
    """Remove symmetric CGNS rind planes from a Fortran-ordered field."""
    trim = _symmetric_rind_widths(stored_shape, physical_shape)
    if not any(trim):
        return values, trim
    field = values.reshape(stored_shape, order="F")
    physical = field[
        tuple(
            slice(amount, stored - amount)
            for amount, stored in zip(trim, stored_shape, strict=True)
        )
    ]
    if physical.shape != physical_shape:
        raise RuntimeError(
            f"CGNS rind trim produced {physical.shape!r}, expected {physical_shape!r}"
        )
    return physical.reshape(-1, order="F").copy(), trim


def _read_adf_surface_fields(
    surface_cgns: Path, field_names: set[str]
) -> tuple[dict[str, dict[str, list[np.ndarray]]], dict[str, Any]]:
    library, loaded_from = _load_cgns_library()
    file_number = ctypes.c_int()
    _check_cgns(
        library.cg_open(os.fsencode(surface_cgns), _CGNS_MODE_READ, ctypes.byref(file_number)),
        "open ADF CGNS surface file",
        library,
    )
    arrays: dict[str, dict[str, list[np.ndarray]]] = {}
    solution_layouts: dict[str, list[dict[str, Any]]] = {}
    try:
        number_of_bases = ctypes.c_int()
        _check_cgns(
            library.cg_nbases(file_number.value, ctypes.byref(number_of_bases)),
            "read CGNS base count",
            library,
        )
        for base_index in range(1, number_of_bases.value + 1):
            base_name = ctypes.create_string_buffer(_CGNS_NAME_BYTES)
            cell_dimension = ctypes.c_int()
            physical_dimension = ctypes.c_int()
            _check_cgns(
                library.cg_base_read(
                    file_number.value,
                    base_index,
                    base_name,
                    ctypes.byref(cell_dimension),
                    ctypes.byref(physical_dimension),
                ),
                f"read CGNS base {base_index}",
                library,
            )
            number_of_zones = ctypes.c_int()
            _check_cgns(
                library.cg_nzones(file_number.value, base_index, ctypes.byref(number_of_zones)),
                f"read zone count for base {base_index}",
                library,
            )
            for zone_index in range(1, number_of_zones.value + 1):
                zone_name_buffer = ctypes.create_string_buffer(_CGNS_NAME_BYTES)
                zone_size = (_CGNS_SIZE * 9)()
                _check_cgns(
                    library.cg_zone_read(
                        file_number.value,
                        base_index,
                        zone_index,
                        zone_name_buffer,
                        zone_size,
                    ),
                    f"read zone {zone_index}",
                    library,
                )
                zone_name = zone_name_buffer.value.decode("utf-8", errors="replace")
                index_dimension = ctypes.c_int()
                _check_cgns(
                    library.cg_index_dim(
                        file_number.value,
                        base_index,
                        zone_index,
                        ctypes.byref(index_dimension),
                    ),
                    f"read index dimension for zone {zone_name}",
                    library,
                )
                vertex_shape = tuple(int(zone_size[i]) for i in range(index_dimension.value))
                cell_shape = tuple(
                    int(zone_size[index_dimension.value + i]) for i in range(index_dimension.value)
                )
                number_of_solutions = ctypes.c_int()
                _check_cgns(
                    library.cg_nsols(
                        file_number.value,
                        base_index,
                        zone_index,
                        ctypes.byref(number_of_solutions),
                    ),
                    f"read solution count for zone {zone_name}",
                    library,
                )
                for solution_index in range(1, number_of_solutions.value + 1):
                    solution_name = ctypes.create_string_buffer(_CGNS_NAME_BYTES)
                    location = ctypes.c_int()
                    _check_cgns(
                        library.cg_sol_info(
                            file_number.value,
                            base_index,
                            zone_index,
                            solution_index,
                            solution_name,
                            ctypes.byref(location),
                        ),
                        f"read solution metadata for zone {zone_name}",
                        library,
                    )
                    data_dimension = ctypes.c_int()
                    dimensions = (_CGNS_SIZE * 9)()
                    _check_cgns(
                        library.cg_sol_size(
                            file_number.value,
                            base_index,
                            zone_index,
                            solution_index,
                            ctypes.byref(data_dimension),
                            dimensions,
                        ),
                        f"read solution size for zone {zone_name}",
                        library,
                    )
                    shape = tuple(int(dimensions[i]) for i in range(data_dimension.value))
                    if not shape or any(value <= 0 for value in shape):
                        raise RuntimeError(f"invalid solution shape {shape!r} for zone {zone_name}")
                    physical_shape = (
                        cell_shape
                        if location.value == 3
                        else vertex_shape
                        if location.value == 2
                        else shape
                    )
                    rind_trim = _symmetric_rind_widths(shape, physical_shape)
                    read_min = (_CGNS_SIZE * data_dimension.value)(*([1] * data_dimension.value))
                    read_max = (_CGNS_SIZE * data_dimension.value)(*shape)
                    number_of_fields = ctypes.c_int()
                    _check_cgns(
                        library.cg_nfields(
                            file_number.value,
                            base_index,
                            zone_index,
                            solution_index,
                            ctypes.byref(number_of_fields),
                        ),
                        f"read field count for zone {zone_name}",
                        library,
                    )
                    for field_index in range(1, number_of_fields.value + 1):
                        source_type = ctypes.c_int()
                        field_name_buffer = ctypes.create_string_buffer(_CGNS_NAME_BYTES)
                        _check_cgns(
                            library.cg_field_info(
                                file_number.value,
                                base_index,
                                zone_index,
                                solution_index,
                                field_index,
                                ctypes.byref(source_type),
                                field_name_buffer,
                            ),
                            f"read field metadata for zone {zone_name}",
                            library,
                        )
                        field_name = field_name_buffer.value.decode("utf-8", errors="replace")
                        if field_names and field_name.casefold() not in field_names:
                            continue
                        values = np.empty(int(np.prod(shape)), dtype=np.float64)
                        _check_cgns(
                            library.cg_field_read(
                                file_number.value,
                                base_index,
                                zone_index,
                                solution_index,
                                field_name_buffer.value,
                                _CGNS_REAL_DOUBLE,
                                read_min,
                                read_max,
                                values.ctypes.data_as(ctypes.c_void_p),
                            ),
                            f"read field {field_name} for zone {zone_name}",
                            library,
                        )
                        values, _ = _trim_symmetric_rind(values, shape, physical_shape)
                        arrays.setdefault(zone_name, {}).setdefault(field_name, []).append(values)
                    solution_layouts.setdefault(zone_name, []).append(
                        {
                            "solution": solution_name.value.decode("utf-8", errors="replace"),
                            "grid_location": location.value,
                            "stored_shape": list(shape),
                            "physical_shape": list(physical_shape),
                            "symmetric_rind_trim_per_side": list(rind_trim),
                        }
                    )
    finally:
        _check_cgns(library.cg_close(file_number.value), "close ADF CGNS surface file", library)
    return arrays, {
        "file_backend": "ADF",
        "reader": "CGNS_MLL_via_ctypes",
        "cgns_library": loaded_from,
        "solution_layouts": solution_layouts,
    }


def _read_hdf5_surface_fields(
    surface_cgns: Path, field_names: set[str]
) -> tuple[dict[str, dict[str, list[np.ndarray]]], dict[str, Any]]:
    import h5py

    arrays: dict[str, dict[str, list[np.ndarray]]] = {}
    with h5py.File(surface_cgns, "r") as handle:

        def collect(name: str, obj: Any) -> None:
            if not isinstance(obj, h5py.Dataset):
                return
            parts = name.split("/")
            field_index = next(
                (
                    index
                    for index, part in enumerate(parts)
                    if not field_names or part.casefold() in field_names
                ),
                None,
            )
            if field_index is None:
                return
            field_name = parts[field_index]
            zone_name = parts[field_index - 2] if field_index >= 2 else "unknown_zone"
            values = np.asarray(obj[()]).reshape(-1).astype(float, copy=False)
            if values.size:
                arrays.setdefault(zone_name, {}).setdefault(field_name, []).append(values)

        handle.visititems(collect)
    return arrays, {"file_backend": "HDF5", "reader": "h5py"}


def read_surface_field_arrays(
    surface_cgns: Path, field_names: Iterable[str]
) -> tuple[dict[str, dict[str, list[np.ndarray]]], dict[str, Any]]:
    """Read selected ADflow surface fields from either HDF5 or ADF CGNS."""
    surface_cgns = Path(surface_cgns).resolve()
    requested = {name.casefold() for name in field_names}
    with surface_cgns.open("rb") as stream:
        signature = stream.read(8)
    if signature == b"\x89HDF\r\n\x1a\n":
        return _read_hdf5_surface_fields(surface_cgns, requested)
    return _read_adf_surface_fields(surface_cgns, requested)


def cgns_volume_restart_inventory(
    path: Path,
    *,
    expected_zones: int | None = None,
    required_fields: Iterable[str] = (),
    minimum_coordinate_arrays: int = 3,
    maximum_field_values: int = 2_000_000,
) -> dict[str, Any]:
    """Verify that an ADF-CGNS checkpoint has restart fields in every zone.

    This bounded-memory validation is intended to run beside ADflow. It opens
    the ADF tree, checks grid and solution metadata, then reads and checks one
    required state field at a time. It never loads coordinates or a complete
    multi-field state into Python.
    """
    path = Path(path).resolve()
    with path.open("rb") as stream:
        if stream.read(8) == b"\x89HDF\r\n\x1a\n":
            raise ValueError("checkpoint inventory currently requires ADF-CGNS")
    library, loaded_from = _load_cgns_library()
    file_number = ctypes.c_int()
    _check_cgns(
        library.cg_open(os.fsencode(path), _CGNS_MODE_READ, ctypes.byref(file_number)),
        "open ADF CGNS checkpoint",
        library,
    )
    required = frozenset(required_fields)
    zones: list[dict[str, Any]] = []
    try:
        number_of_bases = ctypes.c_int()
        _check_cgns(
            library.cg_nbases(file_number.value, ctypes.byref(number_of_bases)),
            "read checkpoint base count",
            library,
        )
        for base_index in range(1, number_of_bases.value + 1):
            number_of_zones = ctypes.c_int()
            _check_cgns(
                library.cg_nzones(file_number.value, base_index, ctypes.byref(number_of_zones)),
                f"read checkpoint zone count for base {base_index}",
                library,
            )
            for zone_index in range(1, number_of_zones.value + 1):
                zone_name = ctypes.create_string_buffer(_CGNS_NAME_BYTES)
                zone_size = (_CGNS_SIZE * 9)()
                _check_cgns(
                    library.cg_zone_read(
                        file_number.value,
                        base_index,
                        zone_index,
                        zone_name,
                        zone_size,
                    ),
                    f"read checkpoint zone {zone_index}",
                    library,
                )
                number_of_grids = ctypes.c_int()
                number_of_coordinates = ctypes.c_int()
                _check_cgns(
                    library.cg_ngrids(
                        file_number.value,
                        base_index,
                        zone_index,
                        ctypes.byref(number_of_grids),
                    ),
                    f"read checkpoint grid count for zone {zone_index}",
                    library,
                )
                _check_cgns(
                    library.cg_ncoords(
                        file_number.value,
                        base_index,
                        zone_index,
                        ctypes.byref(number_of_coordinates),
                    ),
                    f"read checkpoint coordinate count for zone {zone_index}",
                    library,
                )
                number_of_solutions = ctypes.c_int()
                _check_cgns(
                    library.cg_nsols(
                        file_number.value,
                        base_index,
                        zone_index,
                        ctypes.byref(number_of_solutions),
                    ),
                    f"read checkpoint solution count for zone {zone_index}",
                    library,
                )
                solution_fields: list[list[str]] = []
                solutions: list[dict[str, Any]] = []
                for solution_index in range(1, number_of_solutions.value + 1):
                    solution_name = ctypes.create_string_buffer(_CGNS_NAME_BYTES)
                    grid_location = ctypes.c_int()
                    _check_cgns(
                        library.cg_sol_info(
                            file_number.value,
                            base_index,
                            zone_index,
                            solution_index,
                            solution_name,
                            ctypes.byref(grid_location),
                        ),
                        f"read checkpoint solution {solution_index} metadata",
                        library,
                    )
                    data_dimension = ctypes.c_int()
                    dimensions = (_CGNS_SIZE * 9)()
                    _check_cgns(
                        library.cg_sol_size(
                            file_number.value,
                            base_index,
                            zone_index,
                            solution_index,
                            ctypes.byref(data_dimension),
                            dimensions,
                        ),
                        f"read checkpoint solution {solution_index} dimensions",
                        library,
                    )
                    shape = tuple(int(dimensions[i]) for i in range(data_dimension.value))
                    value_count = int(np.prod(shape, dtype=np.int64)) if shape else 0
                    number_of_fields = ctypes.c_int()
                    _check_cgns(
                        library.cg_nfields(
                            file_number.value,
                            base_index,
                            zone_index,
                            solution_index,
                            ctypes.byref(number_of_fields),
                        ),
                        f"read checkpoint fields for zone {zone_index} solution {solution_index}",
                        library,
                    )
                    fields: list[str] = []
                    for field_index in range(1, number_of_fields.value + 1):
                        data_type = ctypes.c_int()
                        field_name = ctypes.create_string_buffer(_CGNS_NAME_BYTES)
                        _check_cgns(
                            library.cg_field_info(
                                file_number.value,
                                base_index,
                                zone_index,
                                solution_index,
                                field_index,
                                ctypes.byref(data_type),
                                field_name,
                            ),
                            (
                                f"read checkpoint field {field_index} for zone "
                                f"{zone_index} solution {solution_index}"
                            ),
                            library,
                        )
                        fields.append(field_name.value.decode("utf-8", errors="replace"))
                    solution_fields.append(fields)
                    has_required_fields = required.issubset(fields)
                    required_fields_fully_read_and_finite = not required
                    field_checks: dict[str, dict[str, Any]] = {}
                    if required and has_required_fields and 0 < value_count <= maximum_field_values:
                        read_min = (_CGNS_SIZE * data_dimension.value)(
                            *([1] * data_dimension.value)
                        )
                        read_max = (_CGNS_SIZE * data_dimension.value)(*shape)
                        required_fields_fully_read_and_finite = True
                        for required_field in sorted(required):
                            values = np.empty(value_count, dtype=np.float64)
                            _check_cgns(
                                library.cg_field_read(
                                    file_number.value,
                                    base_index,
                                    zone_index,
                                    solution_index,
                                    os.fsencode(required_field),
                                    _CGNS_REAL_DOUBLE,
                                    read_min,
                                    read_max,
                                    values.ctypes.data_as(ctypes.c_void_p),
                                ),
                                (
                                    f"read required checkpoint field {required_field} "
                                    f"for zone {zone_index} solution {solution_index}"
                                ),
                                library,
                            )
                            finite = bool(np.isfinite(values).all())
                            field_checks[required_field] = {
                                "value_count": value_count,
                                "all_finite": finite,
                            }
                            required_fields_fully_read_and_finite &= finite
                    solutions.append(
                        {
                            "name": solution_name.value.decode("utf-8", errors="replace"),
                            "grid_location": grid_location.value,
                            "shape": list(shape),
                            "value_count_per_field": value_count,
                            "within_validation_value_limit": (
                                0 < value_count <= maximum_field_values
                            ),
                            "fields": fields,
                            "has_required_restart_field_set": has_required_fields,
                            "required_field_checks": field_checks,
                            "required_fields_fully_read_and_finite": (
                                required_fields_fully_read_and_finite
                            ),
                        }
                    )
                zones.append(
                    {
                        "name": zone_name.value.decode("utf-8", errors="replace"),
                        "grid_count": number_of_grids.value,
                        "coordinate_array_count": number_of_coordinates.value,
                        "solution_count": number_of_solutions.value,
                        "solutions": solutions,
                        "solution_fields": solution_fields,
                        "solution_field_counts": [len(fields) for fields in solution_fields],
                        "has_required_restart_field_set": any(
                            required.issubset(fields) for fields in map(set, solution_fields)
                        ),
                        "has_readable_finite_required_restart_state": any(
                            solution["required_fields_fully_read_and_finite"]
                            for solution in solutions
                        ),
                    }
                )
    finally:
        _check_cgns(library.cg_close(file_number.value), "close ADF CGNS checkpoint", library)

    failure_reasons: list[str] = []
    if expected_zones is not None and len(zones) != expected_zones:
        failure_reasons.append("zone_count_mismatch")
    if not zones:
        failure_reasons.append("no_zones")
    if any(zone["grid_count"] <= 0 for zone in zones):
        failure_reasons.append("zone_without_grid")
    if any(zone["coordinate_array_count"] < minimum_coordinate_arrays for zone in zones):
        failure_reasons.append("zone_without_complete_coordinates")
    if any(not zone["solution_field_counts"] for zone in zones):
        failure_reasons.append("zone_without_solution")
    if any(
        field_count <= 0
        for zone in zones
        for field_count in zone["solution_field_counts"]
    ):
        failure_reasons.append("solution_without_fields")
    if required and any(not zone["has_required_restart_field_set"] for zone in zones):
        failure_reasons.append("zone_without_required_restart_field_set")
    if required and any(
        zone["has_required_restart_field_set"]
        and not zone["has_readable_finite_required_restart_state"]
        for zone in zones
    ):
        failure_reasons.append("zone_without_readable_finite_restart_state")
    return {
        "passed": not failure_reasons,
        "failure_reasons": failure_reasons,
        "path": str(path),
        "file_backend": "ADF",
        "reader": "CGNS_MLL_metadata_plus_bounded_full_required_field_reads",
        "cgns_library": loaded_from,
        "base_count": number_of_bases.value,
        "zone_count": len(zones),
        "expected_zone_count": expected_zones,
        "minimum_coordinate_arrays": minimum_coordinate_arrays,
        "required_fields": sorted(required),
        "maximum_field_values": maximum_field_values,
        "zones": zones,
    }


def _is_no_slip_wall_zone(zone_name: str) -> bool:
    normalized = "".join(character for character in zone_name.casefold() if character.isalnum())
    return normalized.startswith(("wall", "nswall"))


def wall_yplus_summary(
    surface_cgns: Path,
    *,
    target: float = YPLUS_TARGET,
    p95_max: float = YPLUS_P95_MAX,
    p99_max: float = YPLUS_P99_MAX,
    absolute_max: float = YPLUS_ABSOLUTE_MAX,
    wall_distance_convention: str = YPLUS_WALL_DISTANCE_CONVENTION,
    enforce_each_region: bool = True,
) -> dict[str, Any]:
    """Read ADflow no-slip-wall YPlus and apply global and regional limits."""
    surface_cgns = Path(surface_cgns).resolve()
    zone_arrays: dict[str, list[np.ndarray]] = {}
    fields, reader = read_surface_field_arrays(surface_cgns, ["YPlus"])
    for zone, zone_fields in fields.items():
        if not _is_no_slip_wall_zone(zone):
            continue
        for field_name, arrays in zone_fields.items():
            if field_name.casefold() == "yplus":
                zone_arrays.setdefault(zone, []).extend(arrays)

    thresholds = {
        "target": float(target),
        "p95_max": float(p95_max),
        "p99_max": float(p99_max),
        "absolute_max": float(absolute_max),
    }
    if not zone_arrays:
        return {
            "schema": YPLUS_SCHEMA,
            "passed": False,
            "failure_reasons": ["no_wall_yplus_fields"],
            "surface_cgns": str(surface_cgns),
            "surface_cgns_sha256": _sha256(surface_cgns),
            "thresholds": thresholds,
            "wall_distance_convention": wall_distance_convention,
            "threshold_scope": "global_and_each_no_slip_wall_zone",
            "surface_reader": reader,
            "wall_zone_count": 0,
            "sample_count": 0,
        }

    def summarize(values: np.ndarray) -> dict[str, Any]:
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
            "passed": not failures,
            "failure_reasons": failures,
            "sample_count": int(values.size),
            "nonfinite_count": nonfinite_count,
            "negative_count": negative_count,
            "statistics": statistics,
        }

    regions = {
        zone: summarize(np.concatenate(arrays)) for zone, arrays in sorted(zone_arrays.items())
    }
    values = np.concatenate([array for arrays in zone_arrays.values() for array in arrays])
    overall = summarize(values)
    failed_regions = [zone for zone, report in regions.items() if not report["passed"]]
    failures = list(overall["failure_reasons"])
    if enforce_each_region and failed_regions:
        failures.append("one_or_more_wall_regions_above_limit")

    return {
        "schema": YPLUS_SCHEMA,
        "passed": not failures,
        "failure_reasons": failures,
        "surface_cgns": str(surface_cgns),
        "surface_cgns_sha256": _sha256(surface_cgns),
        "thresholds": thresholds,
        "wall_distance_convention": wall_distance_convention,
        "threshold_scope": "global_and_each_no_slip_wall_zone",
        "surface_reader": reader,
        "enforce_each_region": bool(enforce_each_region),
        "wall_zone_count": len(zone_arrays),
        "dataset_count": sum(len(arrays) for arrays in zone_arrays.values()),
        "sample_count": overall["sample_count"],
        "nonfinite_count": overall["nonfinite_count"],
        "negative_count": overall["negative_count"],
        "statistics": overall["statistics"],
        "failed_regions": failed_regions,
        "regions": regions,
    }


def read_surface_zone_coordinates(surface_cgns: Path) -> dict[str, np.ndarray]:
    """Vertex coordinates of every structured surface zone, shaped (ni, nj, 3).

    The CGNS mid-level library reads both ADF and HDF5 backed files, so this
    single path serves whichever backend ADflow wrote.
    """
    surface_cgns = Path(surface_cgns).resolve()
    library, _ = _load_cgns_library()
    size_pointer = ctypes.POINTER(_CGNS_SIZE)
    library.cg_coord_read.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        size_pointer,
        size_pointer,
        ctypes.c_void_p,
    ]
    library.cg_coord_read.restype = ctypes.c_int

    file_number = ctypes.c_int()
    _check_cgns(
        library.cg_open(os.fsencode(surface_cgns), _CGNS_MODE_READ, ctypes.byref(file_number)),
        "open CGNS surface file for coordinates",
        library,
    )
    zones: dict[str, np.ndarray] = {}
    try:
        number_of_bases = ctypes.c_int()
        _check_cgns(
            library.cg_nbases(file_number.value, ctypes.byref(number_of_bases)),
            "read CGNS base count",
            library,
        )
        for base_index in range(1, number_of_bases.value + 1):
            number_of_zones = ctypes.c_int()
            _check_cgns(
                library.cg_nzones(file_number.value, base_index, ctypes.byref(number_of_zones)),
                f"read zone count for base {base_index}",
                library,
            )
            for zone_index in range(1, number_of_zones.value + 1):
                zone_name_buffer = ctypes.create_string_buffer(_CGNS_NAME_BYTES)
                zone_size = (_CGNS_SIZE * 9)()
                _check_cgns(
                    library.cg_zone_read(
                        file_number.value, base_index, zone_index, zone_name_buffer, zone_size
                    ),
                    f"read zone {zone_index}",
                    library,
                )
                zone_name = zone_name_buffer.value.decode("utf-8", errors="replace")
                index_dimension = ctypes.c_int()
                _check_cgns(
                    library.cg_index_dim(
                        file_number.value, base_index, zone_index, ctypes.byref(index_dimension)
                    ),
                    f"read index dimension for zone {zone_name}",
                    library,
                )
                if index_dimension.value != 2:
                    continue
                vertex_shape = (int(zone_size[0]), int(zone_size[1]))
                rmin = (_CGNS_SIZE * 2)(1, 1)
                rmax = (_CGNS_SIZE * 2)(vertex_shape[0], vertex_shape[1])
                count = vertex_shape[0] * vertex_shape[1]
                stacked = np.empty((*vertex_shape, 3), dtype=float)
                for axis, name in enumerate(("CoordinateX", "CoordinateY", "CoordinateZ")):
                    buffer = np.empty(count, dtype=np.float64)
                    _check_cgns(
                        library.cg_coord_read(
                            file_number.value,
                            base_index,
                            zone_index,
                            name.encode("ascii"),
                            _CGNS_REAL_DOUBLE,
                            rmin,
                            rmax,
                            buffer.ctypes.data_as(ctypes.c_void_p),
                        ),
                        f"read {name} for zone {zone_name}",
                        library,
                    )
                    stacked[..., axis] = buffer.reshape(vertex_shape, order="F")
                zones[zone_name] = stacked
    finally:
        _check_cgns(
            library.cg_close(file_number.value), "close CGNS surface file", library
        )
    return zones


_INTERFACE_EDGES = ("i0", "i1", "j0", "j1")


def _edge_vertices(coordinates: np.ndarray, edge: str) -> np.ndarray:
    if edge == "i0":
        return coordinates[0, :, :]
    if edge == "i1":
        return coordinates[-1, :, :]
    if edge == "j0":
        return coordinates[:, 0, :]
    if edge == "j1":
        return coordinates[:, -1, :]
    raise ValueError(f"unknown edge {edge!r}")


def _edge_cell_rows(cells: np.ndarray, edge: str) -> tuple[np.ndarray, np.ndarray]:
    """The cell row touching an edge and the next row in from it."""
    if edge == "i0":
        return cells[0, :], cells[1, :]
    if edge == "i1":
        return cells[-1, :], cells[-2, :]
    if edge == "j0":
        return cells[:, 0], cells[:, 1]
    if edge == "j1":
        return cells[:, -1], cells[:, -2]
    raise ValueError(f"unknown edge {edge!r}")


def _edge_cell_centres(
    vertices: np.ndarray, edge: str
) -> tuple[np.ndarray, np.ndarray]:
    """Centroids of the cell row touching an edge and of the next row in.

    Raw field jumps punish an interface merely for sitting where cells are
    large, so the gradient form needs the distance the jump is taken over.
    """
    if edge in ("i0", "i1"):
        first, second, third = (0, 1, 2) if edge == "i0" else (-1, -2, -3)
        face = 0.25 * (
            vertices[first, :-1]
            + vertices[second, :-1]
            + vertices[first, 1:]
            + vertices[second, 1:]
        )
        inner = 0.25 * (
            vertices[second, :-1]
            + vertices[third, :-1]
            + vertices[second, 1:]
            + vertices[third, 1:]
        )
        return face, inner
    if edge in ("j0", "j1"):
        first, second, third = (0, 1, 2) if edge == "j0" else (-1, -2, -3)
        face = 0.25 * (
            vertices[:-1, first]
            + vertices[:-1, second]
            + vertices[1:, first]
            + vertices[1:, second]
        )
        inner = 0.25 * (
            vertices[:-1, second]
            + vertices[:-1, third]
            + vertices[1:, second]
            + vertices[1:, third]
        )
        return face, inner
    raise ValueError(f"unknown edge {edge!r}")


def _safe_gradient(values: np.ndarray, distances: np.ndarray) -> np.ndarray:
    return np.divide(
        values,
        distances,
        out=np.full(values.shape, np.nan),
        where=distances > 0.0,
    )


def conformal_interface_discontinuity(
    surface_cgns: Path,
    *,
    fields: Iterable[str] = ("cp", "cf", "yplus"),
    zone_predicate=None,
    match_tolerance_fraction: float = 1.0e-9,
) -> dict[str, Any]:
    """Measure surface-field jumps across point-matched wall-zone interfaces.

    A conformal interface is physically invisible: the jump across it should be
    no larger than the jump between neighbouring cells inside either zone. This
    returns, per interface and per field, the median and maximum interface jump
    together with the local in-zone jump that sets the natural scale, so a
    policy can gate on the ratio without this function choosing the threshold.
    """
    surface_cgns = Path(surface_cgns).resolve()
    if zone_predicate is None:
        zone_predicate = _is_no_slip_wall_zone

    aliases = {
        "cp": {"cp", "coefpressure"},
        "cf": {"cf", "skinfrictionmagnitude"},
        "yplus": {"yplus"},
    }
    wanted = {name: aliases.get(name, {name}) for name in fields}
    requested = sorted({alias for names in wanted.values() for alias in names})

    coordinates = read_surface_zone_coordinates(surface_cgns)
    raw_fields, reader = read_surface_field_arrays(surface_cgns, requested)
    layouts = reader.get("solution_layouts", {})

    zone_cells: dict[str, dict[str, np.ndarray]] = {}
    reshape_failures: list[str] = []
    for zone_name, per_field in raw_fields.items():
        if not zone_predicate(zone_name) or zone_name not in coordinates:
            continue
        layout = layouts.get(zone_name) or []
        if not layout:
            reshape_failures.append(f"{zone_name}:missing_layout")
            continue
        physical_shape = tuple(int(v) for v in layout[0]["physical_shape"])
        if len(physical_shape) != 2:
            reshape_failures.append(f"{zone_name}:non_2d_solution")
            continue
        resolved: dict[str, np.ndarray] = {}
        for canonical, names in wanted.items():
            for field_name, arrays in per_field.items():
                if field_name.casefold() not in names or not arrays:
                    continue
                flat = np.asarray(arrays[0], dtype=float).reshape(-1)
                if flat.size != physical_shape[0] * physical_shape[1]:
                    reshape_failures.append(f"{zone_name}:{canonical}:size_mismatch")
                    break
                resolved[canonical] = flat.reshape(physical_shape, order="F")
                break
        if resolved:
            zone_cells[zone_name] = resolved

    all_points = np.concatenate(
        [coordinates[name].reshape(-1, 3) for name in zone_cells] or [np.zeros((1, 3))]
    )
    diagonal = float(np.linalg.norm(all_points.max(axis=0) - all_points.min(axis=0)))
    tolerance = max(diagonal * match_tolerance_fraction, 1.0e-12)

    edges = []
    for zone_name in sorted(zone_cells):
        for edge in _INTERFACE_EDGES:
            vertices = _edge_vertices(coordinates[zone_name], edge)
            edges.append((zone_name, edge, np.asarray(vertices, dtype=float)))

    interfaces: list[dict[str, Any]] = []
    used: set[tuple[str, str]] = set()
    for a in range(len(edges)):
        zone_a, edge_a, verts_a = edges[a]
        if (zone_a, edge_a) in used:
            continue
        for b in range(a + 1, len(edges)):
            zone_b, edge_b, verts_b = edges[b]
            if zone_a == zone_b or (zone_b, edge_b) in used:
                continue
            if verts_a.shape != verts_b.shape:
                continue
            forward = float(np.abs(verts_a - verts_b).max())
            reversed_ = float(np.abs(verts_a - verts_b[::-1]).max())
            if min(forward, reversed_) > tolerance:
                continue
            flip = reversed_ < forward
            used.add((zone_a, edge_a))
            used.add((zone_b, edge_b))

            centre_face_a, centre_inner_a = _edge_cell_centres(
                coordinates[zone_a], edge_a
            )
            centre_face_b, centre_inner_b = _edge_cell_centres(
                coordinates[zone_b], edge_b
            )
            if flip:
                centre_face_b = centre_face_b[::-1]
                centre_inner_b = centre_inner_b[::-1]
            span_interface = np.linalg.norm(centre_face_a - centre_face_b, axis=1)
            span_a = np.linalg.norm(centre_face_a - centre_inner_a, axis=1)
            span_b = np.linalg.norm(centre_face_b - centre_inner_b, axis=1)

            per_field: dict[str, Any] = {}
            for field in sorted(set(zone_cells[zone_a]) & set(zone_cells[zone_b])):
                face_a, inner_a = _edge_cell_rows(zone_cells[zone_a][field], edge_a)
                face_b, inner_b = _edge_cell_rows(zone_cells[zone_b][field], edge_b)
                if flip:
                    face_b, inner_b = face_b[::-1], inner_b[::-1]
                if face_a.shape != face_b.shape or face_a.shape != span_interface.shape:
                    per_field[field] = {"error": "cell_row_length_mismatch"}
                    continue
                jump = np.abs(face_a - face_b)
                local = np.concatenate(
                    [np.abs(face_a - inner_a), np.abs(face_b - inner_b)]
                )
                local_scale = float(np.median(local))
                median_jump = float(np.median(jump))
                interface_gradient = _safe_gradient(jump, span_interface)
                local_gradient = np.concatenate(
                    [
                        _safe_gradient(np.abs(face_a - inner_a), span_a),
                        _safe_gradient(np.abs(face_b - inner_b), span_b),
                    ]
                )
                median_interface_gradient = float(np.nanmedian(interface_gradient))
                median_local_gradient = float(np.nanmedian(local_gradient))
                per_field[field] = {
                    "cells": int(jump.size),
                    "median_interface_jump": median_jump,
                    "maximum_interface_jump": float(jump.max()),
                    "median_local_in_zone_jump": local_scale,
                    "jump_ratio": (
                        median_jump / local_scale if local_scale > 0.0 else None
                    ),
                    "median_interface_gradient_per_m": median_interface_gradient,
                    "median_local_gradient_per_m": median_local_gradient,
                    "gradient_ratio": (
                        median_interface_gradient / median_local_gradient
                        if median_local_gradient > 0.0
                        else None
                    ),
                    "finite": bool(np.isfinite(jump).all()),
                }
            interfaces.append(
                {
                    "zone_a": zone_a,
                    "edge_a": edge_a,
                    "zone_b": zone_b,
                    "edge_b": edge_b,
                    "orientation": "reversed" if flip else "forward",
                    "vertices": int(verts_a.shape[0]),
                    "fields": per_field,
                }
            )
            break

    participating = {i["zone_a"] for i in interfaces} | {i["zone_b"] for i in interfaces}

    # Field range across every wall zone, used for the defect test below.
    field_ranges: dict[str, float] = {}
    for per_field in zone_cells.values():
        for field, values in per_field.items():
            finite = values[np.isfinite(values)]
            if finite.size:
                span = float(finite.max() - finite.min())
                field_ranges[field] = max(field_ranges.get(field, 0.0), span)

    # A conformal interface cannot legitimately jump by more than the whole
    # field varies over the entire wall, nor carry a non-finite value. Those are
    # topology or solution defects. Everything softer than that is a resolution
    # question that only the grid family can settle, so it is measured and
    # reported rather than judged here.
    defects: list[dict[str, Any]] = []
    ratios: dict[str, list[float]] = {}
    for interface in interfaces:
        for field, stats in interface["fields"].items():
            if "error" in stats:
                defects.append(
                    {"interface": _interface_label(interface), "field": field,
                     "reason": stats["error"]}
                )
                continue
            if not stats["finite"]:
                defects.append(
                    {"interface": _interface_label(interface), "field": field,
                     "reason": "non_finite_interface_jump"}
                )
            span = field_ranges.get(field, 0.0)
            if span > 0.0 and stats["maximum_interface_jump"] > span:
                defects.append(
                    {
                        "interface": _interface_label(interface),
                        "field": field,
                        "reason": "jump_exceeds_global_field_range",
                        "maximum_interface_jump": stats["maximum_interface_jump"],
                        "global_field_range": span,
                    }
                )
            ratio = stats.get("gradient_ratio")
            if ratio is not None and np.isfinite(ratio):
                ratios.setdefault(field, []).append(float(ratio))

    gradient_ratio_summary = {
        field: {
            "interfaces": len(values),
            "median": float(np.median(values)),
            "p95": float(np.percentile(values, 95)),
            "maximum": float(max(values)),
        }
        for field, values in sorted(ratios.items())
    }
    worst = sorted(
        (
            {
                "interface": _interface_label(interface),
                "field": field,
                "gradient_ratio": stats.get("gradient_ratio"),
                "median_interface_jump": stats.get("median_interface_jump"),
            }
            for interface in interfaces
            for field, stats in interface["fields"].items()
            if stats.get("gradient_ratio") is not None
        ),
        key=lambda row: row["gradient_ratio"],
        reverse=True,
    )[:10]

    passed = not defects and not reshape_failures and bool(interfaces)
    return {
        "definition": (
            "Median absolute surface-field jump across point-matched wall-zone "
            "edges, divided by the median absolute jump between neighbouring "
            "cells inside the same zones. A conformal interface should give a "
            "ratio near one."
        ),
        "surface_reader": {k: v for k, v in reader.items() if k != "solution_layouts"},
        "match_tolerance_m": tolerance,
        "wall_zones_examined": sorted(zone_cells),
        "wall_zones_with_matched_interface": sorted(participating),
        "wall_zones_without_matched_interface": sorted(set(zone_cells) - participating),
        "matched_interface_count": len(interfaces),
        "interfaces": interfaces,
        "reshape_failures": reshape_failures,
        "global_field_range": field_ranges,
        "defects": defects,
        "gradient_ratio_summary": gradient_ratio_summary,
        "worst_gradient_ratios": worst,
        "gradient_ratio_threshold_calibrated": False,
        "gradient_ratio_calibration_requirement": (
            "A single grid cannot separate an under-resolved physical gradient "
            "from a topology defect. Calibrate the acceptable ratio across the "
            "C01/C02/C03 family at M5: a ratio that falls with refinement is "
            "discretization error, a ratio that does not is a defect."
        ),
        "passed": passed,
    }


def _interface_label(interface: dict[str, Any]) -> str:
    return (
        f"{interface['zone_a']}.{interface['edge_a']}"
        f"<->{interface['zone_b']}.{interface['edge_b']}"
    )


def leading_edge_wrap_resolution(
    surface_blocks: Path | dict, *, block_name: str = "oml_nose"
) -> dict[str, Any]:
    """Measure how much surface turning each leading-edge wrap cell absorbs.

    This is the mesh-only screen for the defect recorded in
    ``m2_a_c03_leading_edge_collar_defect_20260903.json``: when a wrap cell has
    to absorb tens of degrees of turning, the surface normal rotates so far
    inside one cell that the pressure reconstruction stops being meaningful and
    cp climbs above its physical bound.

    Convention: the wrap polyline at one span station has ``n`` points, so
    ``n-1`` cells and ``n-2`` interior joints. Total turning is the sum of the
    joint angles, and turning *per cell* divides that total by ``n-1``. Dividing
    by the joint count instead overstates the figure by ``(n-1)/(n-2)``.
    """
    if isinstance(surface_blocks, dict):
        blocks = surface_blocks
    else:
        loaded = np.load(Path(surface_blocks), allow_pickle=True)
        blocks = {name: loaded[name] for name in loaded.files}
    if block_name not in blocks:
        raise KeyError(f"{block_name!r} not among surface blocks {sorted(blocks)}")

    wrap = np.asarray(blocks[block_name], dtype=float)
    if wrap.ndim != 3 or wrap.shape[-1] != 3 or wrap.shape[0] < 3:
        raise ValueError(f"{block_name!r} is not a usable wrap block: shape {wrap.shape}")

    points = int(wrap.shape[0])
    cells = points - 1
    totals = []
    for station in range(wrap.shape[1]):
        segments = np.diff(wrap[:, station, :], axis=0)
        lengths = np.linalg.norm(segments, axis=1)
        if not np.all(lengths > 0.0):
            raise ValueError(f"degenerate wrap segment in {block_name!r}")
        unit = segments / lengths[:, None]
        cosines = np.clip((unit[:-1] * unit[1:]).sum(axis=1), -1.0, 1.0)
        totals.append(float(np.degrees(np.arccos(cosines)).sum()))
    totals = np.array(totals)

    return {
        "block": block_name,
        "wrap_points": points,
        "wrap_cells": cells,
        "span_stations": int(wrap.shape[1]),
        "total_turning_deg": {
            "minimum": float(totals.min()),
            "median": float(np.median(totals)),
            "maximum": float(totals.max()),
        },
        "turning_per_cell_deg": {
            "minimum": float(totals.min() / cells),
            "median": float(np.median(totals) / cells),
            "maximum": float(totals.max() / cells),
        },
        "convention": (
            "total joint turning divided by the number of wrap cells, not by the "
            "number of joints"
        ),
    }
