"""Structured CGNS for ADflow: a writer and a reader in pure Python (no libcgns), and a check with libcgns.

The file is CGNS in its ADF container (the format every CGNS library reads; the CGNS 4.5.2 that ADflow links on
Mike's machine is built without HDF5 and reads only ADF, so HDF5 would not do). The ADF layout follows the CGNS
source, src/adf/ADF_internals.c (version A02011: every integer and disk pointer in the headers as ASCII hex):

    file header (186 bytes) | free-chunk table (80) | root node header (246) | node headers, sub-node tables and
    data chunks, one after another; a disk pointer is 8 hex digits of 4096-byte block + 4 hex digits of offset.

The CGNS tree (SIDS): CGNSLibraryVersion; one CGNSBase_t "Base" (3, 3); per block a structured Zone_t with
GridCoordinates (CoordinateX/Y/Z, R8, i fastest), ZoneBC (one BC_t per face: BCWallViscous, BCFarfield or
BCSymmetryPlane, with a PointRange and a FamilyName), ZoneGridConnectivity (one GridConnectivity1to1_t per matched
face, both sides: PointRange, PointRangeDonor, Transform); Family_t nodes wall, farfield, symmetry with FamilyBC.

    write_cgns(vm, path)      the mesh of a VolumeMesh
    read_cgns(path)           zones (coordinates, BCs, connectivity) and families, for the round trip (check 15)
    libcgns_read(path)        the same through libcgns (ctypes), where the library exists: an independent check
"""

from __future__ import annotations

import ctypes
import os
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import topology as tp

BLOCK = 4096
WHAT = b"\xc0\xa8\xa3\xa9ADF Database Version A02011>"            # 32 bytes, the old (ASCII-hex) version
BLANK_PTR = (0, BLOCK)
BC_TYPE = {tp.WALL: "BCWallViscous", tp.FAR: "BCFarfield", tp.SYM: "BCSymmetryPlane"}
CGNS_VERSION = 3.4


def _hex(n: int, width: int) -> bytes:
    if n < 0 or n >= 16 ** width:
        raise ValueError(f"{n} does not fit {width} hex digits")
    return f"{n:0{width}X}".encode()


def _ptr(pos: int | tuple) -> bytes:
    b, o = (pos // BLOCK, pos % BLOCK) if isinstance(pos, int) else pos
    return _hex(b, 8) + _hex(o, 4)


def _text(s: str, n: int = 32) -> bytes:
    b = s.encode()
    if len(b) > n:
        raise ValueError(f"{s!r} is longer than {n}")
    return b + b" " * (n - len(b))


@dataclass
class Node:
    name: str
    label: str
    dtype: str = "MT"                  # MT, I4, I8, R4, R8, C1
    dims: tuple = ()
    data: bytes = b""
    children: list = field(default_factory=list)
    pos: int = 0                       # where its header goes
    sub_pos: int = 0
    data_pos: int = 0

    def add(self, *nodes: "Node") -> "Node":
        self.children.extend(nodes)
        return self


def c1(name: str, label: str, s: str, children=()) -> Node:
    b = s.encode()
    return Node(name, label, "C1", (len(b),), b, list(children))


def arr(name: str, label: str, a: np.ndarray, dtype: str) -> Node:
    a = np.asarray(a)
    npt = {"I4": "<i4", "I8": "<i8", "R4": "<f4", "R8": "<f8"}[dtype]
    return Node(name, label, dtype, tuple(int(d) for d in a.shape), np.asfortranarray(a).astype(npt).tobytes(order="F"))


# --- ADF ----------------------------------------------------------------------------------------------------------

def _layout(root: Node) -> int:
    """Place every node header, sub-node table and data chunk; returns the end of the file."""
    pos = 186 + 80
    root.pos = pos
    pos += 246
    stack = [root]
    order = []
    while stack:
        n = stack.pop()
        if n is not root:
            n.pos = pos
            pos += 246
        if n.children:
            n.sub_pos = pos
            pos += 4 + 12 + 44 * len(n.children) + 4
        if n.data:
            n.data_pos = pos
            pos += 4 + 12 + len(n.data) + 4
        order.append(n)
        stack.extend(reversed(n.children))
    return pos


def _header(n: Node) -> bytes:
    dims = list(n.dims) + [0] * (12 - len(n.dims))
    h = (b"NoDe" + _text(n.name) + _text(n.label) + _hex(len(n.children), 8) + _hex(len(n.children), 8)
         + (_ptr(n.sub_pos) if n.children else _ptr(BLANK_PTR)) + _text(n.dtype) + _hex(len(n.dims), 2)
         + b"".join(_hex(d, 8) for d in dims) + _hex(1 if n.data else 0, 4)
         + (_ptr(n.data_pos) if n.data else _ptr(BLANK_PTR)) + b"TaiL")
    assert len(h) == 246
    return h


def write_adf(root: Node, path: Path) -> int:
    """Write the tree under root (the root is the ADF MotherNode) to path; returns the file size."""
    end = _layout(root)
    date = time.strftime("%a %b %d %H:%M:%S %Y").encode().ljust(28)
    fh = (WHAT + b"AdF0" + date + b"AdF1" + date + b"AdF2" + b"LB" + b"AdF3"
          + b"".join(_hex(v, 2) for v in (1, 2, 4, 8, 4, 8, 8, 8, 8, 8, 8, 8)) + b"AdF4"
          + _ptr(root.pos) + _ptr(end - 1) + _ptr(186) + _ptr(BLANK_PTR) + b"AdF5")
    assert len(fh) == 186
    fct = b"fCbt" + _ptr(BLANK_PTR) * 6 + b"Fcte"
    with open(path, "wb") as f:
        f.write(fh)
        f.write(fct)
        stack = [root]
        while stack:
            n = stack.pop()
            assert f.tell() == n.pos, (n.name, f.tell(), n.pos)
            f.write(_header(n))
            if n.children:
                tab = b"".join(_text(c.name) + _ptr(c.pos) for c in n.children)
                f.write(b"SNTb" + _ptr(n.sub_pos + 16 + len(tab)) + tab + b"snTE")
            if n.data:
                f.write(b"DaTa" + _ptr(n.data_pos + 16 + len(n.data)))
                f.write(n.data)
                f.write(b"dEnD")
            stack.extend(reversed(n.children))
        assert f.tell() == end
        pad = (-end) % BLOCK
        f.write(b"\0" * pad)
    return end + pad


@dataclass
class RNode:
    name: str
    label: str
    dtype: str
    dims: tuple
    children: list
    data_at: tuple | None              # (offset, nbytes)


def _unhex(b: bytes) -> int:
    return int(b.decode(), 16)


def _unptr(b: bytes) -> int:
    blk, off = _unhex(b[:8]), _unhex(b[8:12])
    return blk * BLOCK + off


def read_adf(path: Path) -> tuple[RNode, bytes]:
    """The whole tree (headers only; data read on demand from the returned bytes)."""
    raw = Path(path).read_bytes()
    if raw[4:24] != b"ADF Database Version":
        raise ValueError("not an ADF file")
    for t, at in ((b"AdF0", 32), (b"AdF1", 64), (b"AdF2", 96), (b"AdF3", 102), (b"AdF4", 130), (b"AdF5", 182)):
        if raw[at: at + 4] != t:
            raise ValueError(f"file header tag {t!r} missing")
    if raw[25:26] == b"B":
        raise ValueError("only the A version (ASCII hex) is read here")

    def node(pos: int) -> RNode:
        h = raw[pos: pos + 246]
        if h[:4] != b"NoDe" or h[242:246] != b"TaiL":
            raise ValueError(f"bad node header at {pos}")
        name = h[4:36].decode().rstrip()
        label = h[36:68].decode().rstrip()
        nsub = _unhex(h[68:76])
        dtype = h[96:128].decode().rstrip()
        nd = _unhex(h[128:130])
        dims = tuple(_unhex(h[130 + 8 * i: 138 + 8 * i]) for i in range(nd))
        nchunks = _unhex(h[226:230])
        kids = []
        if nsub:
            sp = _unptr(h[84:96])
            if raw[sp: sp + 4] != b"SNTb":
                raise ValueError(f"bad sub-node table at {sp}")
            for c in range(nsub):
                e = sp + 16 + 44 * c
                kids.append(node(_unptr(raw[e + 32: e + 44])))
        data_at = None
        if nchunks:
            dp = _unptr(h[230:242])
            if raw[dp: dp + 4] != b"DaTa":
                raise ValueError(f"bad data chunk at {dp}")
            endtag = _unptr(raw[dp + 4: dp + 16])
            if raw[endtag: endtag + 4] != b"dEnD":
                raise ValueError(f"bad data end tag at {endtag}")
            data_at = (dp + 16, endtag - (dp + 16))
        return RNode(name, label, dtype, dims, kids, data_at)

    return node(_unptr(raw[134:146])), raw


def rdata(n: RNode, raw: bytes):
    if n.data_at is None:
        return None
    off, nb = n.data_at
    b = raw[off: off + nb]
    if n.dtype == "C1":
        return b.decode()
    dt = {"I4": "<i4", "I8": "<i8", "R4": "<f4", "R8": "<f8"}[n.dtype]
    a = np.frombuffer(b, dtype=dt)
    return a.reshape(n.dims, order="F") if len(n.dims) > 1 else a


# --- the CGNS tree of a mesh ------------------------------------------------------------------------------------

def _face_range(shape, face: str) -> np.ndarray:
    """1-based PointRange [[i1, j1, k1], [i2, j2, k2]] of a whole face."""
    lo = [1, 1, 1]
    hi = [int(s) for s in shape]
    ax = "ijk".index(face[0])
    if face.endswith("Min"):
        hi[ax] = 1
    else:
        lo[ax] = hi[ax]
    return np.array([lo, hi])


def one_to_one(blocks: dict, a: str, fa: str, b: str, fb: str, tol: float = 1e-10) -> dict:
    """PointRange on a, PointRangeDonor on b and the Transform of the matched faces a.fa = b.fb, from the orientation
    that maps b's face onto a's node for node (topology.orient)."""
    A, Bk = blocks[a], blocks[b]
    (t, s0, s1), err = tp.orient(tp.face(A, fa), tp.face(Bk, fb), tol)
    if t is None:
        raise ValueError(f"{a}.{fa} and {b}.{fb} do not match within {tol:g} (largest distance {err:.3g})")
    sa, sb = A.shape[:3], Bk.shape[:3]
    ax_a, ax_b = "ijk".index(fa[0]), "ijk".index(fb[0])
    ua, va = [d for d in range(3) if d != ax_a]
    ub, vb = [d for d in range(3) if d != ax_b]
    # face a node (p, q) (p along ua, q along va) is face b node: g = (fb.T if t else fb)[::s0, ::s1]; g[p, q] = fa[p, q]
    n0, n1 = sa[ua], sa[va]

    def donor(p: int, q: int) -> np.ndarray:
        pp = p if s0 == 1 else n0 - 1 - p
        qq = q if s1 == 1 else n1 - 1 - q
        idx = [0, 0, 0]
        idx[ax_b] = 0 if fb.endswith("Min") else sb[ax_b] - 1
        if t:
            idx[ub], idx[vb] = qq, pp
        else:
            idx[ub], idx[vb] = pp, qq
        return np.array(idx) + 1

    T = [0, 0, 0]
    T[ax_a] = (1 if fa.endswith("Max") != fb.endswith("Max") else -1) * (ax_b + 1)
    T[ua] = s0 * ((vb if t else ub) + 1)
    T[va] = s1 * ((ub if t else vb) + 1)
    return {"range": _face_range(sa, fa), "donor_range": np.array([donor(0, 0), donor(n0 - 1, n1 - 1)]),
            "transform": np.array(T), "error": err}


def cgns_tree(blocks: dict, bcs: dict, interfaces: list) -> Node:
    root = Node("ADF MotherNode", "Root Node of ADF File")
    root.add(arr("CGNSLibraryVersion", "CGNSLibraryVersion_t", np.array([CGNS_VERSION]), "R4"))
    base = arr("Base", "CGNSBase_t", np.array([3, 3]), "I4")
    root.add(base)
    for fam, t in ((tp.WALL, BC_TYPE[tp.WALL]), (tp.FAR, BC_TYPE[tp.FAR]), (tp.SYM, BC_TYPE[tp.SYM])):
        base.add(Node(fam, "Family_t").add(c1("FamilyBC", "FamilyBC_t", t)))
    conn = {n: [] for n in blocks}
    for a, fa, b, fb in interfaces:
        conn[a].append((fa, b, fb, one_to_one(blocks, a, fa, b, fb)))
        conn[b].append((fb, a, fa, one_to_one(blocks, b, fb, a, fa)))
    for name, X in blocks.items():
        ni, nj, nk = X.shape[:3]
        size = np.array([[ni, ni - 1, 0], [nj, nj - 1, 0], [nk, nk - 1, 0]])
        z = arr(name, "Zone_t", size, "I4")
        z.add(c1("ZoneType", "ZoneType_t", "Structured"))
        gc = Node("GridCoordinates", "GridCoordinates_t")
        for c, ax in zip("XYZ", range(3)):
            gc.add(arr(f"Coordinate{c}", "DataArray_t", X[..., ax], "R8"))
        z.add(gc)
        zbc = Node("ZoneBC", "ZoneBC_t")
        for face, t in bcs.get(name, {}).items():
            zbc.add(c1(f"{name}_{face}", "BC_t", BC_TYPE[t], [
                arr("PointRange", "IndexRange_t", _face_range(X.shape[:3], face).T, "I4"),
                c1("FamilyName", "FamilyName_t", t)]))
        if zbc.children:
            z.add(zbc)
        zgc = Node("ZoneGridConnectivity", "ZoneGridConnectivity_t")
        for face, donor, dface, m in conn[name]:
            zgc.add(c1(f"{name}_{face}"[:32], "GridConnectivity1to1_t", donor, [
                arr("Transform", '"int[IndexDimension]"', m["transform"], "I4"),
                arr("PointRange", "IndexRange_t", m["range"].T, "I4"),
                arr("PointRangeDonor", "IndexRange_t", m["donor_range"].T, "I4")]))
        if zgc.children:
            z.add(zgc)
        base.add(z)
    return root


def write_blocks(blocks: dict, bcs: dict, interfaces: list, path: Path) -> Path:
    """Any structured multiblock mesh (block -> (ni, nj, nk, 3), right-handed) with full-face BCs and matches."""
    path = Path(path)
    write_adf(cgns_tree(blocks, bcs, interfaces), path)
    return path


def write_cgns(vm, path: Path) -> Path:
    """The structured CGNS file of a VolumeMesh."""
    return write_blocks(vm.blocks, tp.boundary_conditions(), tp.interfaces(vm.info["cap_upper_face"]), path)


def read_cgns(path: Path) -> dict:
    """Zones -> {'coords' (ni, nj, nk, 3), 'bcs' {name: (type, family, range)}, 'one2one' {name: (donor, range,
    donor_range, transform)}}; also 'families' and 'version'."""
    root, raw = read_adf(path)
    out = {"zones": {}, "families": {}, "version": None}
    for n in root.children:
        if n.label == "CGNSLibraryVersion_t":
            out["version"] = float(rdata(n, raw)[0])
        if n.label != "CGNSBase_t":
            continue
        for z in n.children:
            if z.label == "Family_t":
                out["families"][z.name] = rdata(z.children[0], raw)
            if z.label != "Zone_t":
                continue
            size = rdata(z, raw)
            zone = {"size": size, "bcs": {}, "one2one": {}}
            for c in z.children:
                if c.label == "ZoneType_t":
                    zone["type"] = rdata(c, raw)
                if c.label == "GridCoordinates_t":
                    xyz = {k.name: rdata(k, raw) for k in c.children}
                    zone["coords"] = np.stack([xyz["CoordinateX"], xyz["CoordinateY"], xyz["CoordinateZ"]], -1)
                if c.label == "ZoneBC_t":
                    for b in c.children:
                        kids = {k.name: k for k in b.children}
                        zone["bcs"][b.name] = (rdata(b, raw), rdata(kids["FamilyName"], raw),
                                               rdata(kids["PointRange"], raw).T)
                if c.label == "ZoneGridConnectivity_t":
                    for g in c.children:
                        kids = {k.name: k for k in g.children}
                        zone["one2one"][g.name] = (rdata(g, raw), rdata(kids["PointRange"], raw).T,
                                                   rdata(kids["PointRangeDonor"], raw).T,
                                                   rdata(kids["Transform"], raw))
            out["zones"][z.name] = zone
    return out


def _map_ok(A: np.ndarray, Bd: np.ndarray, pr, prd, T, tol: float = 1e-10) -> bool:
    """The transform maps every node of the receiver's range onto the donor's node at the same place."""
    idx = np.stack(np.meshgrid(*[np.arange(min(pr[0][d], pr[1][d]), max(pr[0][d], pr[1][d]) + 1) for d in range(3)],
                               indexing="ij"), -1).reshape(-1, 3)
    M = np.zeros((3, 3), int)
    for d in range(3):
        M[abs(int(T[d])) - 1, d] = np.sign(T[d])
    didx = (idx - np.asarray(pr[0])) @ M.T + np.asarray(prd[0])
    if np.any(didx < 1) or np.any(didx > np.array(Bd.shape[:3])):
        return False
    end = (np.asarray(pr[1]) - np.asarray(pr[0])) @ M.T + np.asarray(prd[0])
    if np.any(end != np.asarray(prd[1])):
        return False
    return float(np.abs(A[tuple((idx - 1).T)] - Bd[tuple((didx - 1).T)]).max()) <= tol


def roundtrip_blocks(blocks: dict, bcs: dict, interfaces: list, path: Path) -> dict:
    """Check 15 (CGNS), read back with this module's reader: every coordinate equals the array exactly; every BC face
    is there with its type, family and range; every match is there on both sides and its transform maps the range
    onto the donor range node for node."""
    r = read_cgns(path)
    worst, problems = 0.0, []
    for name, X in blocks.items():
        z = r["zones"].get(name)
        if z is None:
            problems.append(f"zone {name} missing")
            continue
        if z.get("type") != "Structured":
            problems.append(f"{name}: zone type {z.get('type')}")
        worst = max(worst, float(np.abs(z["coords"] - X).max()))
        want = {f"{name}_{f}": (BC_TYPE[t], t, _face_range(X.shape[:3], f)) for f, t in bcs.get(name, {}).items()}
        if set(z["bcs"]) != set(want):
            problems.append(f"{name}: BCs {sorted(z['bcs'])} != {sorted(want)}")
        for k, (typ, fam, rng) in want.items():
            if k in z["bcs"]:
                gt, gf, gr = z["bcs"][k]
                if gt != typ or gf != fam or not np.array_equal(gr, rng):
                    problems.append(f"{name}: BC {k} is {gt}/{gf}/{gr.tolist()}, expected {typ}/{fam}/{rng.tolist()}")
    n_one = sum(len(z["one2one"]) for z in r["zones"].values())
    if n_one != 2 * len(interfaces):
        problems.append(f"{n_one} 1-to-1 records, expected {2 * len(interfaces)}")
    bad = [f"{name}.{g}" for name, z in r["zones"].items() for g, (donor, pr, prd, T) in z["one2one"].items()
           if donor not in r["zones"] or not _map_ok(z["coords"], r["zones"][donor]["coords"], pr, prd, T)]
    if bad:
        problems.append(f"{len(bad)} 1-to-1 records do not map node for node: {bad[:4]}")
    fam_want = {t: BC_TYPE[t] for t in (tp.WALL, tp.FAR, tp.SYM)}
    if r["families"] != fam_want:
        problems.append(f"families {r['families']} != {fam_want}")
    return {"coords_max_error": worst, "problems": problems, "zones": len(r["zones"]), "one2one": n_one,
            "version": r["version"], "passed": worst == 0.0 and not problems}


def roundtrip(vm, path: Path) -> dict:
    return roundtrip_blocks(vm.blocks, tp.boundary_conditions(), tp.interfaces(vm.info["cap_upper_face"]), path)


# --- libcgns (where it exists) ------------------------------------------------------------------------------

def _vtk_cgns() -> str:
    try:
        import vtkmodules
    except ImportError:
        return ""
    p = Path(vtkmodules.__file__).parent / "libvtkcgns.so"
    return str(p) if p.exists() else ""


def libcgns():
    """(library, symbol prefix, where): a CGNS library to cross-check the files with: $CGNS_LIB, the system's libcgns,
    or the copy VTK ships (symbols prefixed vtkcgns_; the same CGNS code, ADF included). None if there is none."""
    for name, prefix in ((os.environ.get("CGNS_LIB", ""), ""), ("libcgns.so", ""), ("libcgns.so.4.5", ""),
                         ("libcgns.so.4", ""), (_vtk_cgns(), "vtkcgns_")):
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
            getattr(lib, prefix + "cg_open")
            return lib, prefix, name
        except (OSError, AttributeError):
            continue
    return None


def libcgns_read(path: Path) -> dict | None:
    """The file as the CGNS library reads it (cg_open, cg_zone_read, cg_coord_read, cg_boco_info / cg_boco_read /
    cg_famname_read, cg_1to1_read, cg_family_read / cg_fambc_read, cg_version); None without a library."""
    found = libcgns()
    if found is None:
        return None
    lib, pre, where = found
    f = lambda n: getattr(lib, pre + n)
    f("cg_get_error").restype = ctypes.c_char_p
    f("cg_BCTypeName").restype = ctypes.c_char_p
    f("cg_PointSetTypeName").restype = ctypes.c_char_p
    ci, cf = ctypes.c_int, ctypes.c_float

    def ok(ret, what):
        if ret != 0:
            raise RuntimeError(f"{pre}{what}: {f('cg_get_error')().decode()}")

    fn = ci()
    ok(f("cg_open")(str(path).encode(), 0, ctypes.byref(fn)), "cg_open")
    out = {"library": where, "zones": {}, "families": {}}
    try:
        ver = cf()
        ok(f("cg_version")(fn, ctypes.byref(ver)), "cg_version")
        out["version"] = round(ver.value, 4)
        nz = ci()
        ok(f("cg_nzones")(fn, 1, ctypes.byref(nz)), "cg_nzones")
        # cgsize_t is 32 or 64 bit depending on the build: read the zone size into 72 bytes and see which it is
        buf = (ctypes.c_int64 * 9)()
        name = ctypes.create_string_buffer(64)
        ok(f("cg_zone_read")(fn, 1, 1, name, buf), "cg_zone_read")
        v64 = [int(buf[i]) for i in range(9)]
        wide = all(0 < v64[d] < 2 ** 31 for d in range(3)) and all(v64[3 + d] == v64[d] - 1 for d in range(3))
        cs = ctypes.c_int64 if wide else ctypes.c_int32
        out["cgsize_t_bits"] = 64 if wide else 32
        for z in range(1, nz.value + 1):
            size = (cs * 9)()
            ok(f("cg_zone_read")(fn, 1, z, name, size), "cg_zone_read")
            v = [int(size[i]) for i in range(3)]
            zt = ci()
            ok(f("cg_zone_type")(fn, 1, z, ctypes.byref(zt)), "cg_zone_type")
            n = int(np.prod(v))
            xyz = []
            for ax in ("CoordinateX", "CoordinateY", "CoordinateZ"):
                data = np.empty(n, dtype=np.float64)
                ok(f("cg_coord_read")(fn, 1, z, ax.encode(), 4, (cs * 3)(1, 1, 1), (cs * 3)(*v),
                                      data.ctypes.data_as(ctypes.c_void_p)), "cg_coord_read")
                xyz.append(data.reshape(v, order="F"))
            zone = {"size": v, "structured": zt.value == 2, "coords": np.stack(xyz, -1), "bcs": {}, "one2one": {}}
            nb = ci()
            ok(f("cg_nbocos")(fn, 1, z, ctypes.byref(nb)), "cg_nbocos")
            for bc in range(1, nb.value + 1):
                bname = ctypes.create_string_buffer(64)
                btype, ptype, nidx, ndset, ndt = ci(), ci(), ci(), ci(), ci()
                npnts, nlist = cs(), cs()
                normal = (ci * 3)()
                ok(f("cg_boco_info")(fn, 1, z, bc, bname, ctypes.byref(btype), ctypes.byref(ptype), ctypes.byref(npnts),
                                     normal, ctypes.byref(nlist), ctypes.byref(ndt), ctypes.byref(ndset)), "cg_boco_info")
                pnts = (cs * (3 * max(npnts.value, 2)))()
                ok(f("cg_boco_read")(fn, 1, z, bc, pnts, None), "cg_boco_read")
                ok(f("cg_goto")(fn, 1, b"Zone_t", z, b"ZoneBC_t", 1, b"BC_t", bc, b"end"), "cg_goto")
                fam = ctypes.create_string_buffer(64)
                fam_s = fam.value.decode() if f("cg_famname_read")(fam) == 0 else ""
                zone["bcs"][bname.value.decode()] = (f("cg_BCTypeName")(btype.value).decode(),
                                                     f("cg_PointSetTypeName")(ptype.value).decode(), fam.value.decode(),
                                                     np.array([int(pnts[i]) for i in range(6)]).reshape(2, 3))
                del fam_s
            n1 = ci()
            ok(f("cg_n1to1")(fn, 1, z, ctypes.byref(n1)), "cg_n1to1")
            for c in range(1, n1.value + 1):
                cname, dname = ctypes.create_string_buffer(64), ctypes.create_string_buffer(64)
                rng, drng, tr = (cs * 6)(), (cs * 6)(), (ci * 3)()
                ok(f("cg_1to1_read")(fn, 1, z, c, cname, dname, rng, drng, tr), "cg_1to1_read")
                zone["one2one"][cname.value.decode()] = (dname.value.decode(),
                                                         np.array([int(rng[i]) for i in range(6)]).reshape(2, 3),
                                                         np.array([int(drng[i]) for i in range(6)]).reshape(2, 3),
                                                         np.array([int(tr[i]) for i in range(3)]))
            out["zones"][name.value.decode()] = zone
        nf = ci()
        ok(f("cg_nfamilies")(fn, 1, ctypes.byref(nf)), "cg_nfamilies")
        for i in range(1, nf.value + 1):
            fname = ctypes.create_string_buffer(64)
            nboco, ngeo = ci(), ci()
            ok(f("cg_family_read")(fn, 1, i, fname, ctypes.byref(nboco), ctypes.byref(ngeo)), "cg_family_read")
            t = ""
            if nboco.value:
                bname, btype = ctypes.create_string_buffer(64), ci()
                ok(f("cg_fambc_read")(fn, 1, i, 1, bname, ctypes.byref(btype)), "cg_fambc_read")
                t = f("cg_BCTypeName")(btype.value).decode()
            out["families"][fname.value.decode()] = t
    finally:
        f("cg_close")(fn)
    return out


def libcgns_check(blocks: dict, bcs: dict, interfaces: list, path: Path) -> dict | None:
    """Check 15 (CGNS) through the CGNS library itself: what ADflow's cg_* calls will see. None without a library."""
    r = libcgns_read(path)
    if r is None:
        return None
    worst, problems = 0.0, []
    for name, X in blocks.items():
        z = r["zones"].get(name)
        if z is None:
            problems.append(f"zone {name} missing")
            continue
        if not z["structured"] or z["size"] != list(X.shape[:3]):
            problems.append(f"{name}: size {z['size']} structured {z['structured']}")
            continue
        worst = max(worst, float(np.abs(z["coords"] - X).max()))
        for f_, t in bcs.get(name, {}).items():
            got = z["bcs"].get(f"{name}_{f_}")
            if got is None or got[0] != BC_TYPE[t] or got[1] != "PointRange" or got[2] != t or \
                    not np.array_equal(got[3], _face_range(X.shape[:3], f_)):
                problems.append(f"{name}: BC {f_} read as {got}")
        if len(z["bcs"]) != len(bcs.get(name, {})):
            problems.append(f"{name}: {len(z['bcs'])} BCs")
    n_one = 0
    for name, z in r["zones"].items():
        for g, (donor, pr, prd, T) in z["one2one"].items():
            n_one += 1
            if donor not in r["zones"] or not _map_ok(z["coords"], r["zones"][donor]["coords"], pr, prd, T):
                problems.append(f"1-to-1 {name}.{g} -> {donor} does not map node for node")
    if n_one != 2 * len(interfaces):
        problems.append(f"{n_one} 1-to-1 records, expected {2 * len(interfaces)}")
    if r["families"] != {t: BC_TYPE[t] for t in (tp.WALL, tp.FAR, tp.SYM)}:
        problems.append(f"families {r['families']}")
    return {"library": r["library"], "version": r["version"], "cgsize_t_bits": r["cgsize_t_bits"],
            "coords_max_error": worst, "zones": len(r["zones"]), "one2one": n_one, "problems": problems,
            "passed": worst == 0.0 and not problems}
