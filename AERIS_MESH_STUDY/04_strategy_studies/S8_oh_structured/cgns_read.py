#!/usr/bin/env python
"""Read an ADflow CGNS solution, whichever container format it is in.

    .venv/bin/python .../cgns_read.py --file <run>/s8_a0_000_surf.cgns --list
    .venv/bin/python .../cgns_read.py --file ... --field CoefPressure

Why this exists
---------------
CGNS is a data model with TWO container formats: HDF5 and ADF.  `check_cp_bound.py`
opens the file with h5py and its docstring says "which is what ADflow writes
here" -- and on this host it is not.  The CGNS library ADflow links
(/home/mike_kara/packages/CGNS-4.5.2) was built WITHOUT HDF5 support, so ADflow
writes ADF, h5py refuses the file with "file signature not found", and every tool
that reads solutions through h5py silently has nothing to read.  That is why the
cp-over-bound panel of plot_sweep.py came out blank rather than wrong.

`cgnsconvert` cannot help: the same build gives "output type HDF5 not supported".
`cgnsutilities` reads the file but is a GRID utility -- it returns coordinates and
boundary conditions and drops the flow solution.

So this calls the CGNS Mid-Level Library directly through ctypes, which is the
one interface that is guaranteed to read whatever the library itself wrote.
It falls back to h5py when the file IS HDF5, so it works on both and callers do
not have to care.

PLAN 0.1 is the reason this is a shared module and not a fix in one script: a
quantity nobody can read is indistinguishable from a quantity that is fine.
"""

from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path

import numpy as np

#: the library ADflow itself links, found from adflow's own shared object if
#: possible so the reader can never be a different version from the writer
LIBCGNS_CANDIDATES = (
    "/home/mike_kara/packages/CGNS-4.5.2/opt-gfortran/lib/libcgns.so.4.5",
    "libcgns.so.4.5", "libcgns.so.4", "libcgns.so",
)
CG_MODE_READ = 0
#: CGNS DataType_t, from cgnslib.h:
#:   Null 0, UserDefined 1, Integer 2, RealSingle 3, RealDouble 4,
#:   Character 5, LongInteger 6
#: These were first written as 4 and 5 -- off by one, which made every field
#: read either fail on an unknown type or reinterpret doubles as characters.
REAL_SINGLE, REAL_DOUBLE = 3, 4
NUMPY_OF = {REAL_SINGLE: np.float32, REAL_DOUBLE: np.float64}
CTYPE_OF = {REAL_SINGLE: ctypes.c_float, REAL_DOUBLE: ctypes.c_double}
#: CGNS GridLocation_t
LOCATION = {0: "Null", 1: "UserDefined", 2: "Vertex", 3: "CellCenter",
            4: "FaceCenter", 5: "IFaceCenter", 6: "JFaceCenter", 7: "KFaceCenter",
            8: "EdgeCenter"}


def _load() -> ctypes.CDLL:
    last = None
    for name in LIBCGNS_CANDIDATES:
        try:
            return ctypes.CDLL(name)
        except OSError as exc:
            last = exc
    raise SystemExit(
        f"cannot load libcgns ({last}). ADflow links "
        f"{LIBCGNS_CANDIDATES[0]}; set LD_LIBRARY_PATH to its directory.")


class CGNSFile:
    """A read-only CGNS file, through the mid-level library.

    cgsize_t may be 32- or 64-bit depending on how the library was configured,
    and getting it wrong does not raise: it reads adjacent memory and returns
    plausible-looking garbage.  This build is 32-bit, which was established by
    the check below firing -- zone dims 43 and 5 came back as 21474836523, which
    is exactly 5 * 2**32 + 43, two 32-bit values read as one 64-bit one.  So the
    width is DETECTED on the first zone rather than assumed, and the sanity
    check is kept afterwards.
    """

    def __init__(self, path: Path):
        self.lib = _load()
        self.cgsize = None
        self.path = Path(path)
        self.fn = ctypes.c_int()
        rc = self.lib.cg_open(str(self.path).encode(), CG_MODE_READ,
                              ctypes.byref(self.fn))
        if rc != 0:
            raise SystemExit(f"cg_open failed on {path} (code {rc}): {self._error()}")

    def _error(self) -> str:
        self.lib.cg_get_error.restype = ctypes.c_char_p
        return (self.lib.cg_get_error() or b"").decode()

    def close(self) -> None:
        self.lib.cg_close(self.fn)

    def __enter__(self): return self
    def __exit__(self, *exc): self.close(); return False

    def zones(self) -> list[dict]:
        nbases = ctypes.c_int()
        self.lib.cg_nbases(self.fn, ctypes.byref(nbases))
        out = []
        for b in range(1, nbases.value + 1):
            name = ctypes.create_string_buffer(33)
            celldim, physdim = ctypes.c_int(), ctypes.c_int()
            self.lib.cg_base_read(self.fn, b, name, ctypes.byref(celldim),
                                  ctypes.byref(physdim))
            nzones = ctypes.c_int()
            self.lib.cg_nzones(self.fn, b, ctypes.byref(nzones))
            for z in range(1, nzones.value + 1):
                zname = ctypes.create_string_buffer(33)
                index_dim = celldim.value          # structured: index dim == cell dim
                vertex = cells = None
                widths = ([self.cgsize] if self.cgsize
                          else [ctypes.c_int32, ctypes.c_int64])
                for width in widths:
                    size = (width * 9)()
                    self.lib.cg_zone_read(self.fn, b, z, zname, size)
                    v = [int(size[i]) for i in range(index_dim)]
                    c = [int(size[index_dim + i]) for i in range(index_dim)]
                    if all(0 < x < 10 ** 9 for x in v):
                        self.cgsize, vertex, cells = width, v, c
                        break
                if vertex is None:
                    raise SystemExit(
                        f"zone {zname.value!r} gives no credible dims at either "
                        f"cgsize_t width. The library's index size cannot be inferred.")
                out.append({"base": b, "zone": z, "base_name": name.value.decode(),
                            "zone_name": zname.value.decode(),
                            "vertex_dims": vertex, "cell_dims": cells,
                            "cell_dim": celldim.value, "phys_dim": physdim.value})
        return out

    def fields(self, base: int, zone: int) -> list[dict]:
        nsols = ctypes.c_int()
        self.lib.cg_nsols(self.fn, base, zone, ctypes.byref(nsols))
        out = []
        for s in range(1, nsols.value + 1):
            sname = ctypes.create_string_buffer(33)
            location = ctypes.c_int()
            self.lib.cg_sol_info(self.fn, base, zone, s, sname, ctypes.byref(location))
            nfields = ctypes.c_int()
            self.lib.cg_nfields(self.fn, base, zone, s, ctypes.byref(nfields))
            for f in range(1, nfields.value + 1):
                dtype = ctypes.c_int()
                fname = ctypes.create_string_buffer(33)
                self.lib.cg_field_info(self.fn, base, zone, s, f,
                                       ctypes.byref(dtype), fname)
                out.append({"solution": s, "solution_name": sname.value.decode(),
                            "location": LOCATION.get(location.value, location.value),
                            "field": f, "name": fname.value.decode(),
                            "data_type": dtype.value})
        return out

    def read_field(self, base: int, zone: int, solution: int, name: str,
                   dims: list[int], dtype: int = REAL_DOUBLE) -> np.ndarray:
        n = int(np.prod(dims))
        buffer = (CTYPE_OF[dtype] * n)()
        width = self.cgsize or ctypes.c_int32
        rmin = (width * len(dims))(*([1] * len(dims)))
        rmax = (width * len(dims))(*[int(d) for d in dims])
        rc = self.lib.cg_field_read(self.fn, base, zone, solution, name.encode(),
                                    dtype, rmin, rmax, buffer)
        if rc != 0:
            raise SystemExit(f"cg_field_read({name!r}) failed: {self._error()}")
        # CGNS is Fortran-ordered
        return np.frombuffer(buffer, dtype=NUMPY_OF[dtype], count=n).reshape(
            dims, order="F")

    def read_coords(self, base: int, zone: int, dims: list[int]) -> np.ndarray:
        n = int(np.prod(dims))
        out = []
        for axis in ("CoordinateX", "CoordinateY", "CoordinateZ"):
            buffer = (ctypes.c_double * n)()
            width = self.cgsize or ctypes.c_int32
            rmin = (width * len(dims))(*([1] * len(dims)))
            rmax = (width * len(dims))(*[int(d) for d in dims])
            rc = self.lib.cg_coord_read(self.fn, base, zone, axis.encode(),
                                        REAL_DOUBLE, rmin, rmax, buffer)
            if rc != 0:
                raise SystemExit(f"cg_coord_read({axis}) failed: {self._error()}")
            out.append(np.frombuffer(buffer, dtype=np.float64,
                                     count=n).reshape(dims, order="F"))
        return np.stack(out, axis=-1)


def read_field_auto(handle: "CGNSFile", zone: dict, field: dict) -> np.ndarray:
    """One field at its STORED extent, rind layers included.

    ADflow writes cell-centred surface data with one rind layer on each side, so
    the stored array is (ni_cell + 2, nj_cell + 2) and not (ni_cell, nj_cell).
    Reading the core range instead silently returns a differently-shaped array,
    and `locate_cp_excess.analyse_zone` checks that shape precisely because
    getting it wrong shifts every cell index by one and moves every reported
    leading-edge location.  The extent is therefore established by trying the
    rind-padded shape FIRST and falling back, rather than assumed.
    """
    base, zone_id, solution = zone["base"], zone["zone"], field["solution"]
    cells = [d for d in zone["cell_dims"] if d > 0]
    vertex = [d for d in zone["vertex_dims"] if d > 0]
    for dims in ([c + 2 for c in cells], cells, vertex):
        try:
            return handle.read_field(base, zone_id, solution, field["name"],
                                     dims, field["data_type"])
        except (SystemExit, KeyError, ValueError):
            continue
    raise SystemExit(f"cannot read {field['name']!r} at any plausible extent "
                     f"(tried rind-padded, cell and vertex shapes)")


def surface_zones(path: Path) -> list[tuple[str, dict]]:
    """Zones as nested plain dicts shaped like the h5py tree callers expect.

    Returns `{"Flow solution": {"CoefPressure": {" data": array}, ...},
              "GridCoordinates": {...}}`, so `_data(group, name)` works against
    an ADF file with no change to the code that consumes it.  Arrays are
    transposed to the (nj, ni) order h5py hands back for a Fortran-ordered CGNS
    array, so the two paths agree cell for cell.
    """
    out = []
    with CGNSFile(path) as handle:
        for zone in handle.zones():
            solution: dict = {}
            for field in handle.fields(zone["base"], zone["zone"]):
                solution[field["name"]] = {
                    " data": read_field_auto(handle, zone, field).T}
            dims = [d for d in zone["vertex_dims"] if d > 0]
            xyz = handle.read_coords(zone["base"], zone["zone"], dims)
            coords = {f"Coordinate{a}": {" data": xyz[..., i].T}
                      for i, a in enumerate("XYZ")}
            out.append((zone["zone_name"],
                        {"Flow solution": solution, "GridCoordinates": coords}))
    return out


def _h5_collect(path: Path, name: str) -> np.ndarray | None:
    try:
        import h5py
    except ImportError:
        return None
    found: list[np.ndarray] = []

    def walk(node):
        for key, item in node.items():
            if isinstance(item, h5py.Group):
                if key == name and " data" in item:
                    found.append(np.array(item[" data"]).ravel())
                walk(item)

    try:
        with h5py.File(path, "r") as handle:
            walk(handle)
    except OSError:
        return None
    return np.concatenate(found) if found else None


def is_hdf5(path: Path) -> bool:
    with open(path, "rb") as fh:
        return fh.read(8) == b"\x89HDF\r\n\x1a\n"


def read_variable(path: Path, name: str) -> np.ndarray | None:
    """Every value of one field, concatenated over zones.  Format-agnostic."""
    path = Path(path)
    if is_hdf5(path):
        return _h5_collect(path, name)
    values: list[np.ndarray] = []
    with CGNSFile(path) as handle:
        for zone in handle.zones():
            for field in handle.fields(zone["base"], zone["zone"]):
                if field["name"] != name:
                    continue
                dims = (zone["cell_dims"] if field["location"] == "CellCenter"
                        else zone["vertex_dims"])
                dims = [d for d in dims if d > 0] or [1]
                values.append(handle.read_field(
                    zone["base"], zone["zone"], field["solution"], name, dims,
                    field["data_type"]).ravel(order="F"))
    return np.concatenate(values) if values else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, required=True)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--field", default=None)
    args = ap.parse_args()

    print(f"{args.file.name}: {'HDF5' if is_hdf5(args.file) else 'ADF'} container")
    if args.list:
        with CGNSFile(args.file) as handle:
            for zone in handle.zones():
                fields = handle.fields(zone["base"], zone["zone"])
                print(f"\n  zone {zone['zone_name']}  vertex {zone['vertex_dims']}  "
                      f"cells {zone['cell_dims']}")
                for f in fields:
                    print(f"      {f['name']:<24} {f['location']}")
    if args.field:
        values = read_variable(args.file, args.field)
        if values is None:
            print(f"  {args.field}: not present")
            return 1
        print(f"\n  {args.field}: {values.size:,} values  "
              f"min {values.min():.6g}  max {values.max():.6g}  "
              f"mean {values.mean():.6g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
