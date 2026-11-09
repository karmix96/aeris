"""build_volume(surface, level, re) -> the C-H volume mesh of one wing at one level and one Re.

    python -m cfdauto.volume --type bwb --set reference --index 0 --level VC --re 3e5

Steps (Grand Roadmap recipes R-V, R-X; decisions/volume_rules.md):
1. the stations of the Stage 2 surface, each with its s0 (law 13), its boundary-layer thickness and the growth
   inside it that gives the level's cells across it (law 14);
2. the far field (one for all stations, at least 80 c from the wing) and the wake lines of every station; the
   streamwise nodes of the wake (s0 off the base, the wake band, the far growth) with one count for all stations;
3. in every station plane the line shapes from one smoothed front (march.front), closed straight to far-field
   nodes common to all stations, and one wall-normal distribution per station placed along them (decision 84);
   the base block between the wake lines; one count of layers for all stations;
4. the six plane blocks stacked from the root to the tip; past the tip, the tip plane swept outboard (first gap =
   the wing's tip gap, growth law 12) and the cap swept with it: 13 blocks;
5. the checks (checks.py). Nothing is written unless every refusing check passes (write(): refusal.json).
The smoothing ladder: if a cell folds, every station is rebuilt with the next front smoothing (kappa).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import march as mr
from . import plane as pl
from . import topology as tp
from .laws import VolumeRules, rules as get_rules

Array = np.ndarray
ENDS = (np.array([0.0, 1.0]), np.array([0.0, -1.0]))
KAPPA_LADDER = (1.0, 1.5, 2.0, 3.0)
FRONT_GROWTH = 1.1          # growth of the front distances that trace the line shapes (not the node distribution)
SWITCH_LOCAL_C = 2.0        # the front is marched through the fine zone (2 local chords), then straight to the far field


@dataclass
class VolumeMesh:
    level: str
    re_mean: float
    blocks: dict                       # name -> (ni, nj, nk, 3)
    info: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    review: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def outcome(self) -> str:
        if not self.passed:
            return "refused"
        return "needs review" if self.review else "passed"

    def failed(self) -> list:
        return [c for c in self.checks if not c.passed]

    @property
    def cells(self) -> int:
        return int(sum(np.prod(np.array(b.shape[:3]) - 1) for b in self.blocks.values()))

    @property
    def nodes(self) -> int:
        return int(sum(np.prod(b.shape[:3]) for b in self.blocks.values()))

    def node_hash(self) -> str:
        h = hashlib.sha256()
        for n in sorted(self.blocks):
            h.update(n.encode())
            h.update(np.round(self.blocks[n], 12).tobytes())
        return h.hexdigest()


# --- 1-2: stations, far field, wake -------------------------------------------------------------------------

def stations_of(surface, rl: VolumeRules) -> list[pl.Station]:
    wing = surface.wing
    n_side = surface.info["n_side"]
    out = []
    for k, r in enumerate(surface.stations):
        ring = wing[:, k][:, [0, 2]]
        s0 = rl.first_cell(r["re_local"], r["chord_m"])
        delta = rl.delta(r["re_local"], r["chord_m"])
        g_bl = float(mr.bl_growth(np.array([s0]), np.array([delta]), rl.bl_cells, rl.wall_growth)[0])
        st = pl.Station(k, float(r["y_m"]), ring, float(r["chord_m"]), float(r["re_local"]), s0, delta, g_bl)
        st.wake = pl.wake_of(ring, n_side, st.chord, rl)
        st.te_cell = float(min(np.linalg.norm(ring[1] - ring[0]), np.linalg.norm(ring[2 * n_side - 3] - ring[2 * n_side - 2])))
        out.append(st)
    return out


def smoothstep(t: Array) -> Array:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def wake_first_cells(sts: list[pl.Station], rl: VolumeRules) -> Array:
    """The first cell behind the base, per station. wake.first_cell: s0 (default; decision 90: the base is a wall at
    y+ <= 1) or te_cell (the wing's last chordwise cell: no spacing jump across the trailing-edge line, the base not
    wall-resolved; an option counted for decision 105, which check 5 refuses until decision 90 changes)."""
    how = str(rl.raw["wake"].get("first_cell", "s0"))
    if how not in ("s0", "te_cell"):
        raise ValueError(f"wake.first_cell must be s0 or te_cell, not {how!r}")
    return np.array([s.s0 if how == "s0" else max(s.te_cell, s.s0) for s in sts])


def wake_nodes(sts: list[pl.Station], dom: pl.Domain, rl: VolumeRules) -> tuple[Array, Array]:
    """Arc lengths of the wake nodes (n_w, n_stations), one count for all stations, and the minimal counts.
    Far behind the band the nodes of every station move to the same x (the station mean), so the wake columns of
    neighbouring stations line up along the semi-span (decision 84): weight 0 up to the longest band, smoothstep to
    1 at the outflow."""
    A, L = [], []
    for st in sts:
        args, length = pl.wake_lengths(st, dom, rl)
        st.s_end = length
        A.append(args)
        L.append(length)
    arr = {k: np.array([a[k] for a in A]) for k in A[0]}
    s0 = wake_first_cells(sts, rl)
    L = np.array(L)
    f = mr.min_cells(s0, L, **arr)
    n_cells = int(np.ceil(f.max() - 1e-9)) + 1                 # one spare cell: every station meets its limits
    dq, _ = mr.fill(s0, L, n_cells, **arr)
    x = np.stack([st.wake.centre(dq[:, k])[0][:, 0] for k, st in enumerate(sts)], 1)
    xm = x.mean(axis=1, keepdims=True)
    s_a = max(float(rl.band["length_local_c"]) * st.chord for st in sts) + max(float(rl.wake["turn_local_c"]) * st.chord
                                                                               for st in sts) * 4.0
    dist = x - np.array([st.wake.M[0] for st in sts])[None, :]
    w = smoothstep((dist - s_a) / (dom.x_out - dom.x_b - s_a))
    x_new = (1.0 - w) * x + w * xm
    dq = dq + (x_new - x)                                       # past the turn the centre line runs along +x
    dq[-1] = L
    return dq, f


def blend_outer(Gs: list[Array], d: Array, sts, rl) -> list[Array]:
    """Move the outer layers of every station toward the station mean, so the far field is one grid extruded along
    the semi-span (decision 84). From the first layer at which every station is past its fine zone and its band
    (weight 0) to the far field (weight 1), smoothstep in the layer index."""
    nj = d.shape[0] - 1
    starts = []
    for k, st in enumerate(sts):
        b = rl.band
        H = float(b["margin_c"]) + float(b["length_local_c"]) * st.chord * np.tan(np.radians(b["alpha_hi_deg"]))
        reach = max(rl.fine_zone_local_c * st.chord, H)
        starts.append(int(np.searchsorted(d[:, k], reach)))
    j0 = min(max(starts), nj - 2)
    mean = np.mean(Gs, axis=0)
    w = smoothstep((np.arange(nj + 1) - j0) / max(nj - j0, 1))[None, :, None]
    return [(1.0 - w) * G + w * mean for G in Gs], j0


# --- 3: the station planes ------------------------------------------------------------------------------------

def plane_set(sts, dom, lay, dq, rl, kappa):
    """Line shapes and distributions of every station. Returns (paths, arc lengths, distributions d (nj+1, n_st),
    the minimal counts per station, nj, far-field nodes Q)."""
    Fs, Xs, wks, hits = [], [], [], []
    for k, st in enumerate(sts):
        X, wk = pl.c_line(st, lay, dq[:, k])
        Dsw = SWITCH_LOCAL_C * st.chord
        n = int(np.ceil(np.log1p((FRONT_GROWTH - 1.0) * Dsw / st.s0) / np.log(FRONT_GROWTH)))
        df = np.concatenate([[0.0], np.cumsum(st.s0 * FRONT_GROWTH ** np.arange(n))])
        df *= Dsw / df[-1]
        F, nl = mr.front(X, df, kappa, ENDS)
        h, _ = mr.outer_hit(F[-1], nl, dom)
        Fs.append(F)
        Xs.append(X)
        wks.append(wk)
        hits.append(h)
    Q = mr.on_boundary(np.mean(hits, axis=0), dom)
    Q[0] = [dom.x_out, dom.z_m + dom.R]
    Q[-1] = [dom.x_out, dom.z_m - dom.R]
    Ps, Ss, specs = [], [], []
    for k, st in enumerate(sts):
        P = mr.paths(Fs[k], Q)
        S = mr.path_length(P)
        Ps.append(P)
        Ss.append(S)
        specs.append(pl.station_spec(st, float(S[-1].max()), rl))
    keys = list(specs[0])
    A = {key: np.array([s[key] for s in specs]) for key in keys}
    f = mr.min_cells(**A)
    nj = int(np.ceil(f.max() - 1e-9)) + 1                      # one spare layer
    d, lam = mr.fill(A["s0"], A["L"], nj, A["g_bl"], A["delta"], A["g_fine"], A["fine"], A["g_far"],
                     A["cap_a"], A["cap_b"], A["cap_h"], A["cap_m"])
    return dict(paths=Ps, S=Ss, d=d, lam=lam, need=f, nj=nj, Q=Q, X=Xs, wake=wks, specs=specs)


def station_grid(lay, P, S, d_ref) -> Array:
    """The combined C grid of one station (n_c, nj+1, 2): the station distribution placed along its paths."""
    d = pl.shrink(d_ref, S[-1])
    return np.transpose(mr.place(P, S, d), (1, 0, 2))


def split(G: Array, st, lay, wake) -> dict[str, Array]:
    """The six 2-D blocks of one station, (ni, nj, 2) in (x, z)."""
    out = {n: G[a: b + 1] for n, (a, b) in lay.blocks().items()}
    out["B"] = pl.base_block(st, lay, wake, lay.n_side)
    return out


def quad_quality(G: Array) -> Array:
    """Smallest corner scaled Jacobian of every quad of a (ni, nj, 2) plane block, right-handed with +y."""
    a, b, c, e = G[:-1, :-1], G[1:, :-1], G[1:, 1:], G[:-1, 1:]
    out = None
    for p, q, r in ((a, b, e), (b, c, a), (c, e, b), (e, a, c)):
        e1, e2 = q - p, r - p
        cr = -(e1[..., 0] * e2[..., 1] - e1[..., 1] * e2[..., 0])
        j = cr / (np.linalg.norm(e1, axis=-1) * np.linalg.norm(e2, axis=-1))
        out = j if out is None else np.minimum(out, j)
    return out


# --- 4: outboard ----------------------------------------------------------------------------------------------

def outboard_y(y: Array, rl: VolumeRules) -> tuple[Array, float]:
    """Station positions past the tip (the tip first): first gap = the wing's last gap, growth law 12 inside the
    outboard fine zone, far growth beyond, to far.distance_c past the tip."""
    gap = float(y[-1] - y[-2])
    L = rl.far_distance
    one = lambda v: np.array([float(v)])
    f = mr.min_cells(one(gap), one(L), one(rl.outboard_growth), one(0.0), one(rl.outboard_growth),
                     one(rl.outboard_fine_zone), one(rl.far_growth))
    n = int(np.ceil(f[0] - 1e-9)) + 1
    d, _ = mr.fill(one(gap), one(L), n, one(rl.outboard_growth), one(0.0), one(rl.outboard_growth),
                   one(rl.outboard_fine_zone), one(rl.far_growth))
    return float(y[-1]) + d[:, 0], float(f[0])


def stack(planes: list[dict], y: Array, wall: dict | None = None) -> dict[str, Array]:
    """3-D blocks (ni, nj, nk, 3) from 2-D station blocks and their y; wall: exact Stage 2 nodes to put on j = 0."""
    out = {}
    for name in planes[0]:
        ni, nj = planes[0][name].shape[:2]
        arr = np.empty((ni, nj, len(planes), 3))
        for k, p in enumerate(planes):
            arr[:, :, k, 0] = p[name][..., 0]
            arr[:, :, k, 1] = y[k]
            arr[:, :, k, 2] = p[name][..., 1]
        out[name] = arr
    return out


# --- the build ------------------------------------------------------------------------------------------------

def build_volume(surface, level: str | None = None, re_mean: float | None = None, config=None,
                 kappa_ladder=KAPPA_LADDER, run_checks: bool = True) -> VolumeMesh:
    """The C-H volume mesh on a Stage 2 SurfaceMesh (cfdauto.mesh.surface.build_surface / build_family)."""
    t0 = time.time()
    level = level or surface.level
    rl = get_rules(level, config)
    re_mean = float(re_mean if re_mean is not None else surface.re_mean)
    n_side, n_base = surface.info["n_side"], surface.info["n_base"]
    sts = stations_of(surface, rl)
    dom = pl.domain([s.ring for s in sts], n_side, rl)
    dq, wake_need = wake_nodes(sts, dom, rl)
    lay = pl.PlaneLayout(n_side, n_base, dq.shape[0])
    y = np.array([s.y for s in sts])

    rung, planes, ps, worst = None, None, None, None
    for r, kappa in enumerate(kappa_ladder):
        ps = plane_set(sts, dom, lay, dq, rl, kappa)
        Gs = [station_grid(lay, ps["paths"][k], ps["S"][k], ps["d"][:, k]) for k in range(len(sts))]
        Gs, j_blend = blend_outer(Gs, ps["d"], sts, rl)
        ps["j_blend"] = j_blend
        planes = [split(G, st, lay, ps["wake"][k]) for k, (G, st) in enumerate(zip(Gs, sts))]
        worst = min(float(quad_quality(b).min()) for p in planes for b in p.values())
        rung = r
        if worst > 0.0:
            break
    y_out, out_need = outboard_y(y, rl)
    inner = stack(planes, y)
    outer = stack([planes[-1]] * len(y_out), y_out)
    blocks = {f"{n}_in": a for n, a in inner.items()} | {f"{n}_out": a for n, a in outer.items()}
    # the exact Stage 2 wall: ring nodes on j = 0 of the C blocks, base nodes on j = 0 of B, the cap
    for name, (a, b) in lay.blocks().items():
        if name in ("CU", "CN", "CL"):
            ra, rb = a - lay.i_te_up, b - lay.i_te_up
            blocks[f"{name}_in"][:, 0, :, :] = surface.wing[ra: rb + 1, :, :]
            blocks[f"{name}_out"][:, 0, 0, :] = surface.wing[ra: rb + 1, -1, :]
    base = np.concatenate([surface.wing[2 * n_side - 2: 2 * n_side - 1], surface.wing[2 * n_side - 1:],
                           surface.wing[:1]], axis=0)
    blocks["B_in"][:, 0, :, :] = base
    blocks["B_out"][:, 0, 0, :] = base[:, -1, :]
    cap = surface.cap
    capb = np.repeat(cap[:, :, None, :], len(y_out), axis=2).copy()
    capb[:, :, :, 1] = y_out[None, None, :]
    capb[:, :, 0, :] = cap
    blocks["CAP"] = capb
    # the cap's side faces are the outboard C blocks' j = 0 faces (the tip ring swept outboard): one set of nodes
    cap_upper = "jMin" if surface.info["cap"]["eta_reversed"] else "jMax"
    info = {
        "level": rl.level, "re_mean": re_mean, "rules": rl.values(), "n_side": n_side, "n_base": n_base,
        "n_wake": lay.n_w, "n_layers": ps["nj"], "n_c": lay.n_c, "n_span": len(y), "n_out": len(y_out),
        "cap_shape": list(cap.shape[:2]), "cap_upper_face": cap_upper,
        "kappa": kappa_ladder[rung], "rung": rung, "plane_min_sj": worst, "j_blend": ps["j_blend"],
        "domain": {"x_b": dom.x_b, "z_m": dom.z_m, "R": dom.R, "x_out": dom.x_out, "y_far": float(y_out[-1])},
        "need": {"layers_max": float(ps["need"].max()), "layers_station": int(np.argmax(ps["need"])),
                 "wake_max": float(wake_need.max()), "outboard": out_need},
        "stations": [{"k": s.k, "y": s.y, "chord": s.chord, "re_local": s.re_local, "s0": s.s0, "delta": s.delta,
                      "g_bl": s.g_bl, "t_te": s.wake.t_te, "phi0_deg": float(np.degrees(s.wake.phi0))} for s in sts],
        "y_out": y_out.tolist(), "seconds_build": round(time.time() - t0, 2),
    }
    vm = VolumeMesh(rl.level, re_mean, blocks, info)
    vm.info["cells"] = vm.cells
    vm.info["nodes"] = vm.nodes
    vm.info["ram_gib_adflow"] = rl.ram_gib(vm.cells)
    vm._plane = dict(sts=sts, lay=lay, dq=dq, dom=dom, ps=ps, surface=surface, rules=rl)
    if run_checks:
        from .checks import run_checks as _rc
        vm.checks, vm.review = _rc(vm)
        vm.info["seconds_total"] = round(time.time() - t0, 2)
    return vm


def count_volume(surface, level: str | None = None, re_mean: float | None = None, config=None) -> dict:
    """Cells and RAM of the volume mesh without building it (for levels that do not fit here): the counts from the
    same laws, with the node counts of the surface."""
    level = level or surface.level
    rl = get_rules(level, config)
    n_side, n_base = surface.info["n_side"], surface.info["n_base"]
    sts = stations_of(surface, rl)
    dom = pl.domain([s.ring for s in sts], n_side, rl)
    dq, wake_need = wake_nodes(sts, dom, rl)
    lay = pl.PlaneLayout(n_side, n_base, dq.shape[0])
    # the layer count from straight lines to the far field (the march adds a few per cent of length; +1 spare)
    specs = []
    for st in sts:
        specs.append(pl.station_spec(st, dom.R * 1.05, rl))
    A = {key: np.array([s[key] for s in specs]) for key in specs[0]}
    nj = int(np.ceil(mr.min_cells(**A).max() - 1e-9)) + 1
    y = np.array([s.y for s in sts])
    y_out, _ = outboard_y(y, rl)
    n_st, n_out = len(y), len(y_out)
    nc, nw, nb = lay.n_c, lay.n_w, n_base
    plane_cells = (nc - 1) * nj + (nb - 1) * (nw - 1)
    cap = surface.cap.shape
    cells = plane_cells * (n_st - 1) + plane_cells * (n_out - 1) + (cap[0] - 1) * (cap[1] - 1) * (n_out - 1)
    return {"level": rl.level, "n_layers": nj, "n_wake": nw, "n_c": nc, "n_span": n_st, "n_out": n_out,
            "cells": int(cells), "ram_gib_adflow": rl.ram_gib(cells), "counted_not_built": True}


# --- writing --------------------------------------------------------------------------------------------------

def mesh_name(vm: VolumeMesh, wing) -> str:
    from ..mesh.surface import fmt_re
    return f"volume_{vm.level}_{wing.input_hash[:8]}_{fmt_re(vm.re_mean)}"


def volume_code_hash() -> str:
    h = hashlib.sha256()
    for f in sorted(Path(__file__).resolve().parent.glob("*.py")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def export(vm: VolumeMesh, out: Path, formats=("cgns", "su2")) -> dict:
    """Write the solver files and check 15 on them: the CGNS file read back by this package's reader and, where a CGNS
    library exists, by the library (what ADflow sees); the .su2 file read back (counts, welds, no inside-out cell,
    boundary quads facing out). Appends check 15 to vm.checks."""
    from .checks import Check
    bcs, itf = tp.boundary_conditions(), tp.interfaces(vm.info["cap_upper_face"])
    res, ok, worst, t0 = {}, True, 0.0, time.time()
    if "cgns" in formats:
        from . import cgns
        p = cgns.write_cgns(vm, Path(out) / "volume.cgns")
        own, lib = cgns.roundtrip(vm, p), cgns.libcgns_check(vm.blocks, bcs, itf, p)
        res["cgns"] = {"file": p.name, "bytes": p.stat().st_size, "own_reader": own, "libcgns": lib}
        ok &= own["passed"] and (lib is None or lib["passed"])
        worst = max(worst, own["coords_max_error"], 0.0 if lib is None else lib["coords_max_error"])
    if "su2" in formats:
        from . import su2
        p = Path(out) / "volume.su2"
        su2.write_su2(vm, p)
        r = su2.check_su2(vm.blocks, bcs, itf, p)
        res["su2"] = {"file": p.name} | r
        ok &= r["passed"]
    res["seconds"] = round(time.time() - t0, 1)
    note = "; ".join(f"{k}: {', '.join(v.get('problems', [])) or 'ok'}" for k, v in res.items() if isinstance(v, dict)
                     and "problems" in v)
    vm.checks = [c for c in vm.checks if c.n != 15] + [Check(
        15, "export_round_trip", bool(ok), worst, "CGNS read back exactly (own reader and libcgns); .su2: counts equal, "
        "every face welded, no inside-out cell, boundary quads face out", note)]
    return res


def write(vm: VolumeMesh, wing, out: Path, formats=("npz",)) -> Path:
    """The mesh folder: blocks.npz, quality.json, manifest.json and the solver files asked for (cgns, su2: check 15 is
    run on them); a refused mesh writes only refusal.json (which check, its value, its limit)."""
    import shutil
    from ..mesh.surface import _jsonable, mesh_code_hash
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    cfg = Path(vm.info["rules"]["config"])
    head = {"name": mesh_name(vm, wing), "wing_type": wing.wing_type, "set": wing.set_name, "index": wing.index,
            "wing_input_hash": wing.input_hash, "level": vm.level, "re_mean": vm.re_mean,
            "rules_config": cfg.name, "rules_hash": hashlib.sha256(cfg.read_bytes()).hexdigest(),
            "volume_code_hash": volume_code_hash(), "surface_code_hash": mesh_code_hash(),
            "cells": vm.cells, "nodes": vm.nodes, "ram_gib_adflow": vm.info["ram_gib_adflow"]}
    exports = {}
    if vm.passed:
        solver = tuple(f for f in formats if f in ("cgns", "su2"))
        if solver:
            exports = export(vm, out, solver)
    head["outcome"] = vm.outcome
    checks = [c.as_dict() for c in vm.checks]
    if not vm.passed:
        for f in ("volume.cgns", "volume.su2"):
            (out / f).unlink(missing_ok=True)
        (out / "refusal.json").write_text(json.dumps(_jsonable(head | {
            "failed": [c.as_dict() for c in vm.failed()], "checks": checks, "exports": exports}), indent=1))
        return out
    np.savez(out / "blocks.npz", **vm.blocks)
    (out / "quality.json").write_text(json.dumps(_jsonable({"checks": checks, "review": vm.review,
                                                            "info": vm.info, "exports": exports}), indent=1))
    shapes = {n: list(b.shape[:3]) for n, b in vm.blocks.items()}
    (out / "manifest.json").write_text(json.dumps(_jsonable(head | {
        "mesh_node_hash": vm.node_hash(), "blocks": shapes,
        "boundary_conditions": tp.boundary_conditions(),
        "interfaces": tp.interfaces(vm.info["cap_upper_face"]),
        "files": sorted(p.name for p in out.iterdir()) + ["manifest.json"]}), indent=1))
    return out
