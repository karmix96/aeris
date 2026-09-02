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
