"""The surface mesh of one wing at one level and one Re: rings at stations + the tip cap.

    python -m cfdauto.mesh --type bwb --set reference --index 0 --level VC --re 3e5

Steps (Grand Roadmap recipe R-S):
1. stations along the span (on every loft station, chord-scaled, squeezed to the tip);
2. at each station: the nose spacing solved by bisection for the turning target (law 1) at each
   solve level, on that level's own ring (every level, VC, C, M, F, each for its own angle: 16.9,
   13, 10, 7.7 deg, the 10 deg met at M moved by laws.py; the first approach: C only); the smallest,
   moved to VC, wins, so every level meets its own angle and the family rule stays exact;
3. this level's values from laws.py (each value moved from its anchor level by the family rule);
   the nose spacing is the VC one divided by r^k, so the family rule stays exact;
4. one node distribution in arc fraction for the whole wing: at every place the strictest
   station wins, so node i sits at the same arc fraction on every station (no sheared quads
   where the stations are squeezed at the tip) and no cell is ever coarser than asked; the
   spanwise envelope (law 2) holds by construction;
5. the rings, every node asked from the loft; the tip cap from the tip ring;
6. the checks, each against this level's own value; nothing is written unless all pass.

The nose repair (owner, 8 Nov 2026). The solve uses each station's own ring; the mesh uses the shared node list, which
can turn a nose a little more. A repair multiplies the nose spacing of every station by 0.9. It is needed only where
a ring turns past this level's check limit (its angle + 0.2 deg, the limit that refuses a mesh; before 8 Nov a
turning 0.003-0.006 deg past the solve's own tolerance of 0.02 deg triggered it, on 4 of 782 F builds). A repair is a
property of the family, one wing at one Re: build_family applies the same factor at every level, so every spacing
still refines by exactly 1.3 between levels, and every mesh records it (info["nose_family"], info["nose_repair"]).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .cap import tip_cap
from .checks import Check, scaled_jacobian
from .laws import Rules, rules as get_rules
from .ring import RingSpec, Section, build_ring_at, kink_mask, nose_turning, solve_nose, turning, union_distribution
from .stations import SpanTable, place_stations

Array = np.ndarray

REPAIR_FACTOR = 0.9       # one repair round: the nose spacing of every station x 0.9
REPAIR_TOL_STEPS = 10     # a round is needed above the level's angle + 10 x its turning tolerance = the check limit


@dataclass
class SurfaceMesh:
    level: str
    re_mean: float
    wing: Array                 # (n_ring, n_span, 3), ring index first, root to tip
    cap: Array                  # (n_chord, n_base, 3)
    u: Array                    # (n_ring, n_span) chord fraction of each ring node (nan on the base)
    stations: list[dict]
    checks: list[Check]
    info: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def node_hash(self) -> str:
        h = hashlib.sha256()
        for a in (self.wing, self.cap):
            h.update(np.round(a, 12).tobytes())
        return h.hexdigest()


def fmt_re(re: float) -> str:
    m, e = f"{re:.6e}".split("e")
    return f"re{float(m):g}e{int(e)}"


def mesh_code_hash() -> str:
    h = hashlib.sha256()
    for f in sorted(Path(__file__).resolve().parent.glob("*.py")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def build_surface(loft, re_mean: float, level: str | None = None, config=None, nose_factor: float = 1.0) -> SurfaceMesh:
    """level: a level of the config's ladder (VC, C, M, F; default the coarsest). config: a rules file
    (default configs/surface.yaml; the first approach: configs/surface_first.yaml). nose_factor: the family's nose
    repair (1.0 = none; build_family sets it, the same at every level). A round still needed here is applied and
    recorded (info["turning_repairs"] > 0): then this level is off the family ratio until the family is rebuilt with
    build_family."""
    rc: Rules = get_rules(None, config)            # the coarsest level
    rl: Rules = get_rules(level or rc.level, config)
    solvers = [get_rules(lev, config) for lev in rc.nose_solve_levels]   # VC, C, M, F (the first approach: C)
    tab = SpanTable.of(loft, rl.dense_span)

    # 1. stations; the tip gap is the tip first cell at this Re (laws 9, 10, 13)
    c_tip = float(tab.chord[-1])
    re_tip = re_mean * c_tip / tab.mean_chord
    s0_tip = rl.first_cell_c(re_tip) * c_tip
    tip_gap = rl.tip_gap_in_s0 * s0_tip
    tab = tab.refined_at_tip(loft, tip_gap)
    st = place_stations(tab, rl, tip_gap, loft.station_v)

    # 2. sections and the nose solve at each solve level, for that level's own angle, on its own ring, the finest
    # first. Each answer is moved to the coarsest level (x r^k) and the smallest wins: a coarser level starts from
    # the finer answer (h_cap) and is solved only if its turning there misses its own angle. A solve that cannot
    # meet its angle at any spacing is left out unless none can (then the turning check refuses the build).
    secs = [Section.at(loft, v, rl.dense_per_side) for v in st["v"]]
    rows = []
    for sec in secs:
        re_loc = re_mean * sec.chord / tab.mean_chord
        c = sec.chord
        best = None                                         # (h / c moved to the coarsest level, level, the solve)
        for rs in sorted(solvers, key=lambda r: -r.k):
            cap = best[0] * c / rs.scale if best and best[2]["solved"] else None
            nose = solve_nose(sec, rs.band_spacing_c(re_loc) * c, rs.max_spacing_c * c, rs.te_spacing_c * c, rs, cap)
            if nose["at_cap"]:
                continue                                    # the finer answer already meets this level's angle
            h = nose["h_le"] / c * rs.scale
            # a coarser level wins only with a truly smaller spacing: an equal one (the band cell, which every level
            # moves by the same 1.3) leaves the finer level's answer and its name in place
            if best is None or not best[2]["solved"] or (nose["solved"] and h < best[0] * (1.0 - 1e-9)):
                best = (h, rs.level, nose)
        h, at, nose = best
        rows.append({"y_m": sec.y, "v": sec.v, "chord_m": c, "re_local": re_loc,
                     "h_le_c_solved": h, "nose_solved_at": at, "turning_solved_deg": nose["turning_deg"],
                     "nose_capped_at_band": nose["capped_at_band"], "nose_solved": nose["solved"],
                     "geometry_kink_deg": nose["kinks"]["max_deg"], "_kinks": nose["kinks"]})

    # 3-5. This level's spacings per station, then ONE node distribution in arc fraction for the
    # whole wing (the strictest station wins at every place), the rings, and the turning measured
    # again on the rings as built. The family's nose factor first; a station above this level's check limit
    # then tightens the nose spacing of the whole wing by 10 % (the union keeps every station's own band and
    # trailing-edge cells); build_family moves such a round to every level.
    target = rl.nose_turning_deg + REPAIR_TOL_STEPS * rl.nose_turning_tol_deg
    h_le_c = np.array([r["h_le_c_solved"] for r in rows]) * float(nose_factor)

    def make_specs(h_le_c):
        return [RingSpec(h_le=h * sec.chord / rl.scale, h_band=rl.band_spacing_c(r["re_local"]) * sec.chord,
                         h_max=rl.max_spacing_c * sec.chord, h_te=rl.te_spacing_c * sec.chord)
                for r, sec, h in zip(rows, secs, h_le_c)]

    repairs = 0
    for repairs in range(40):
        specs = make_specs(h_le_c)
        frac, _, need = union_distribution(secs, specs, rl)
        n_side = len(frac)
        outs = [build_ring_at(sec, frac, rl) for sec in secs]
        turn = np.array([nose_turning(o["ring"], n_side, kink_mask(o["u_upper"], o["u_lower"], r["_kinks"], n_side))
                         for o, r in zip(outs, rows)])
        bad = (turn > target) & np.array([r["nose_solved"] for r in rows])
        if not bad.any():
            break
        h_le_c = h_le_c * REPAIR_FACTOR
    rings = [o["ring"] for o in outs]
    us = [np.concatenate([o["u_upper"][::-1], o["u_lower"][1:], np.full(rl.n_base - 2, np.nan)]) for o in outs]
    repair = repairs
    for r, sec, sp, h, nd in zip(rows, secs, specs, h_le_c, need):
        c = sec.chord
        r |= {"h_le_c_asked": sp.h_le / c, "h_band_c": sp.h_band / c, "h_te_c": sp.h_te / c,
              "nose_tightened": bool(h < r["h_le_c_solved"] * (1 - 1e-12)),
              "cells_needed": float(nd), "spare_points": int(n_side - 1 - np.ceil(nd - 1e-9))}
    wing = np.stack(rings, axis=1)
    u = np.stack(us, axis=1)
    cap, cap_info = tip_cap(wing[:, -1], n_side, rl.n_base, rl.cap_smoothing)

    mesh = SurfaceMesh(rl.level, float(re_mean), wing, cap, u, rows, [], {
        "n_side": n_side, "n_base": rl.n_base, "n_ring": int(wing.shape[0]), "n_span": int(wing.shape[1]),
        "wing_quads": int((wing.shape[0]) * (wing.shape[1] - 1)),
        "cap_quads": int((cap.shape[0] - 1) * (cap.shape[1] - 1)),
        "semi_span_m": tab.semi_span, "mean_chord_m": tab.mean_chord, "tip_chord_m": c_tip,
        "re_tip": re_tip, "s0_tip_m": s0_tip, "tip_gap_asked_m": tip_gap, "cells_per_panel": st["cells_per_panel"],
        "loft_station_y_m": tab.loft_y.tolist(), "cap": cap_info, "rules": rl.values(),
        "turning_repairs": repair,
        "nose_factor": float(nose_factor),
        "nose_repair": {"family_factor": float(nose_factor), "rounds_here": int(repair),
                        "factor_here": float(nose_factor) * REPAIR_FACTOR ** repair,
                        "label": ("none" if repair == 0 and nose_factor == 1.0 else
                                  "family repair (the same factor at every level)" if repair == 0 else
                                  "repaired at this level only: off the family ratio; rebuild with build_family"),
                        "trigger_deg": float(target)},
    })
    mesh.checks = run_checks(mesh, secs, specs, st, tab, rl)
    return mesh


def build_family(loft, re_mean: float, levels=None, config=None) -> dict[str, SurfaceMesh]:
    """Every level of one wing at one Re with ONE nose factor, so that every spacing refines by exactly 1.3 between
    levels, also when a nose repair is needed (owner, 8 Nov 2026). First every level with factor 1; if a level needs
    repair rounds, the factor 0.9^n (n the most rounds any level needed) goes on every level and all are rebuilt,
    until no level needs a round. Each mesh then carries info["nose_family"]: the factor, the rounds, the levels
    that needed them, and a label (none, or family repair)."""
    import time
    levels = list(levels or get_rules(None, config).names)
    factor, found, t_all = 1.0, [], 0.0
    for _ in range(12):
        meshes, secs = {}, {}
        for lev in levels:
            t0 = time.time()
            meshes[lev] = build_surface(loft, re_mean, lev, config, nose_factor=factor)
            secs[lev] = time.time() - t0
        t_all += sum(secs.values())
        need = {lev: m.info["turning_repairs"] for lev, m in meshes.items() if m.info["turning_repairs"]}
        if not need:
            break
        found.append({"factor": factor, "rounds_needed": need})
        factor *= REPAIR_FACTOR ** max(need.values())
    else:
        raise RuntimeError("the family nose factor did not settle in 12 rebuilds")
    rounds = int(round(np.log(factor) / np.log(REPAIR_FACTOR))) if factor < 1.0 else 0
    fam = {"levels": levels, "factor": factor, "rounds": rounds, "found": found,
           "label": "none" if rounds == 0 else f"family repair: nose x {REPAIR_FACTOR}^{rounds} at every level",
           "seconds_total": round(t_all, 2)}
    for lev, m in meshes.items():
        m.info["nose_family"] = fam
        m.info["seconds"] = round(secs[lev], 2)
    return meshes


# --- checks ---------------------------------------------------------------------------

def _side_metrics(ring: Array, n_side: int, u: Array, band_up, band_lo) -> dict:
    up = ring[:n_side][::-1]                      # LE -> TE
    lo = ring[n_side - 1: 2 * n_side - 1]         # LE -> TE
    out = {}
    for name, pts, uu, band in (("upper", up, u[:n_side][::-1], band_up), ("lower", lo, u[n_side - 1:2 * n_side - 1], band_lo)):
        d = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        r = d[1:] / d[:-1]
        mid = 0.5 * (uu[1:] + uu[:-1])
        inb = (mid >= band[0]) & (mid <= band[1])
        out[name] = {"le": float(d[0]), "te": float(d[-1]), "growth": float(max(r.max(), (1 / r).max())),
                     "band_max": float(d[inb].max()) if inb.any() else 0.0, "max": float(d.max())}
    return out


def run_checks(m: SurfaceMesh, secs, specs, st, tab, rl: Rules) -> list[Check]:
    """The 13 checks, each against this level's own value (rl): the turning check at VC is VC's nose target
    (16.9 deg), at F it is F's (7.7 deg); the trailing-edge, band and tip-gap checks compare with what this level
    asked; the growth checks with this level's limits."""
    n_side, ch = m.info["n_side"], rl.checks
    worst = {k: 0.0 for k in ("turn", "growth", "band", "te", "plane")}
    h_le_del = []
    for j, (sec, sp, row) in enumerate(zip(secs, specs, m.stations)):
        ring = m.wing[:, j]
        sm = _side_metrics(ring, n_side, m.u[:, j], rl.band_upper, rl.band_lower)
        u_j = m.u[:, j]
        t = nose_turning(ring, n_side, kink_mask(u_j[:n_side][::-1], u_j[n_side - 1:2 * n_side - 1], row["_kinks"], n_side))
        row |= {"turning_deg": t, "h_le_c": 0.5 * (sm["upper"]["le"] + sm["lower"]["le"]) / sec.chord,
                "h_te_c_delivered": max(sm["upper"]["te"], sm["lower"]["te"]) / sec.chord,
                "growth_max": max(sm["upper"]["growth"], sm["lower"]["growth"]),
                "band_max_c": max(sm["upper"]["band_max"], sm["lower"]["band_max"]) / sec.chord,
                "max_spacing_c": max(sm["upper"]["max"], sm["lower"]["max"]) / sec.chord,
                "te_corner_ratio": float(sm["upper"]["te"] / np.linalg.norm(ring[-1] - ring[0]))}
        h_le_del.append(row["h_le_c"])
        worst["turn"] = max(worst["turn"], t)
        worst["growth"] = max(worst["growth"], row["growth_max"])
        worst["band"] = max(worst["band"], row["band_max_c"] / row["h_band_c"])
        worst["te"] = max(worst["te"], row["h_te_c_delivered"] / row["h_te_c"])
        worst["plane"] = max(worst["plane"], float(np.abs(ring[:, 1] - sec.y).max()))

    kink = max(r["geometry_kink_deg"] for r in m.stations)
    for r in m.stations:
        r.pop("_kinks", None)
    h = np.array(h_le_del)
    env = float(np.max(np.maximum(h[1:] / h[:-1], h[:-1] / h[1:]))) if len(h) > 1 else 1.0
    gaps = np.diff(st["y"])
    span_growth = float(np.max(np.maximum(gaps[1:] / gaps[:-1], gaps[:-1] / gaps[1:])))
    hit = float(max(np.abs(st["y"] - yl).min() for yl in tab.loft_y))
    tip_ratio = st["tip_gap"] / st["tip_gap_asked"]
    jw = float(scaled_jacobian(m.wing, wrap_i=True).min())
    jcap = scaled_jacobian(m.cap)
    # The two cells where the nose arc meets the upper and lower sides have three corners on
    # the ring, which is smooth there: their corner angle is 180 deg minus the ring's turning
    # (a few degrees), whatever the smoothing does. Reported on their own; folded = refused.
    corners = jcap[0, [0, -1]]
    jc_corner = float(corners.min())
    jcap[0, [0, -1]] = np.inf
    jc = float(jcap.min())
    n_expected = 2 * n_side + m.info["n_base"] - 3
    target = rl.nose_turning_deg + 10 * rl.nose_turning_tol_deg
    lo, hi = ch["tip_gap_band"]
    lev = rl.level
    return [
        Check("nose_turning", worst["turn"] <= target, worst["turn"],
              f"<= {target:.2f} deg ({lev}: {rl.nose_turning_deg:.4g} + {10 * rl.nose_turning_tol_deg:g}) at every ring "
              "node but the trailing-edge corners and geometry kinks (law 1)"),
        Check("geometry_kinks", kink <= target, kink,
              f"<= {target:.2f} deg ({lev}'s turning limit): a kink of the section itself (trailing-edge opening on "
              "very small chords) that no cell size can reduce"),
        Check("nose_envelope", env <= rl.nose_envelope * 1.01, env, f"<= {rl.nose_envelope} between stations (law 2)"),
        Check("chord_growth", worst["growth"] <= rl.chord_growth_limit * 1.01, worst["growth"],
              f"<= {rl.chord_growth_limit:.4g} ({lev}) within 1 % (the lower side follows the upper side's arc fraction; "
              "where the two noses differ, open decision 64, its first cells grow a little faster)"),
        Check("band_spacing", worst["band"] <= 1.01, worst["band"],
              f"<= 1 x the band cell asked at {lev} (bubble length / {rl.cells_per_bubble:.3g}), within 1 %"),
        Check("te_spacing", worst["te"] <= 1.01, worst["te"],
              f"<= 1 x the trailing-edge cell asked at {lev} ({100 * rl.te_spacing_c:.3g} % c; law 3), within 1 %"),
        Check("span_growth", span_growth <= rl.span_growth_limit, span_growth, f"<= {rl.span_growth_limit:.4g} ({lev})"),
        Check("loft_stations_hit", hit <= 1e-12, hit, "a station exactly on every loft station [m]"),
        Check("tip_gap", lo <= tip_ratio <= hi + 1e-9, tip_ratio,
              f"in [{lo}, {hi}] x the tip gap asked at {lev} ({rl.tip_gap_in_s0:g} x s0 at y+ {rl.yplus:.3g}; law 10)"),
        Check("planar_stations", worst["plane"] <= ch["on_loft_m"], worst["plane"], "every ring in its station plane [m]"),
        Check("wing_quads", jw >= ch["min_scaled_jacobian"], jw, f">= {ch['min_scaled_jacobian']} (scaled Jacobian)"),
        Check("cap_quads", jc >= ch["min_scaled_jacobian"], jc,
              f">= {ch['min_scaled_jacobian']} (scaled Jacobian, all but the two nose-corner cells)"),
        Check("cap_nose_corners", jc_corner > 0.0, jc_corner,
              "> 0, not folded (the H cap puts two corners on the smooth nose: angle 180 deg - turning)"),
        Check("ring_count", m.wing.shape[0] == n_expected, float(m.wing.shape[0]), f"== 2 n_side + n_base - 3 = {n_expected}"),
    ]


# --- one wing from the Stage 1 sets ----------------------------------------------------

@dataclass
class Wing:
    wing_type: str
    set_name: str
    index: int
    input_hash: str
    loft: object

    @property
    def surface_hash(self) -> str:
        return self.loft.surface_hash()


def wing_from_set(wing_type: str, set_name: str, index: int, backend: str | None = None) -> Wing:
    from ..geometry.build import SEALED_SETS, input_hash, load_set
    from ..geometry.loft import build_loft
    from ..geometry.params import load_config, resolve
    from ..geometry.sections import build_wing_sections

    if set_name in SEALED_SETS:
        raise PermissionError("the hold-out sets are sealed: their wings are never meshed before gate G3")
    cfg = load_config()
    spec = cfg.types[wing_type]
    vec = resolve(spec, load_set(wing_type, set_name)["vectors"][index])
    _, stations = build_wing_sections(spec, vec, cfg.te)
    return Wing(wing_type, set_name, index, input_hash(cfg, wing_type, vec), build_loft(stations, 2, backend))


def mesh_name(mesh: SurfaceMesh, wing: Wing) -> str:
    return f"mesh_{mesh.level}_{wing.input_hash[:8]}_{fmt_re(mesh.re_mean)}"


def write(mesh: SurfaceMesh, wing: Wing, out: Path) -> Path:
    """Write the mesh folder, or only refusal.json when a check failed."""
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    checks = [c.as_dict() for c in mesh.checks]
    cfg = Path(mesh.info["rules"]["config"])
    head = {"name": mesh_name(mesh, wing), "wing_type": wing.wing_type, "set": wing.set_name, "index": wing.index,
            "wing_input_hash": wing.input_hash, "loft_surface_hash": wing.surface_hash,
            "loft_backend": wing.loft.backend, "level": mesh.level, "re_mean": mesh.re_mean,
            "rules_config": cfg.name, "rules_hash": hashlib.sha256(cfg.read_bytes()).hexdigest(),
            "mesh_code_hash": mesh_code_hash(), "passed": mesh.passed,
            # the nose repair label (owner, 8 Nov 2026): the family factor and whether this level is off the ratio
            "nose_repair": mesh.info.get("nose_repair"), "nose_family": mesh.info.get("nose_family")}
    if not mesh.passed:
        (out / "refusal.json").write_text(json.dumps(head | {"failed": [c.as_dict() for c in mesh.failed()],
                                                             "checks": checks}, indent=1))
        return out
    np.savez_compressed(out / "surface.npz", wing=mesh.wing, cap=mesh.cap, u=mesh.u,
                        y=np.array([r["y_m"] for r in mesh.stations]), v=np.array([r["v"] for r in mesh.stations]))
    write_plot3d(out / "surface.xyz", [mesh.wing, mesh.cap])
    keys = list(mesh.stations[0].keys())
    lines = [",".join(keys)] + [",".join(f"{r[k]:.10g}" if isinstance(r[k], float) else str(r[k]) for k in keys)
                                for r in mesh.stations]
    (out / "stations.csv").write_text("\n".join(lines) + "\n")
    (out / "quality.json").write_text(json.dumps({"checks": checks, "info": _jsonable(mesh.info)}, indent=1))
    (out / "manifest.json").write_text(json.dumps(head | {"mesh_node_hash": mesh.node_hash(),
                                                          "counts": {k: mesh.info[k] for k in
                                                                     ("n_side", "n_base", "n_ring", "n_span",
                                                                      "wing_quads", "cap_quads")}}, indent=1))
    return out


def write_plot3d(path: Path, blocks: list[Array]) -> None:
    """ASCII multi-block Plot3D surface (ni, nj, 1 per block); opens in ParaView and Tecplot."""
    with open(path, "w") as f:
        f.write(f"{len(blocks)}\n")
        for b in blocks:
            f.write(f"{b.shape[0]} {b.shape[1]} 1\n")
        for b in blocks:
            for k in range(3):
                np.savetxt(f, b[:, :, k].T.reshape(-1, 4 if b[:, :, k].size % 4 == 0 else 1), fmt="%.12e")


def _jsonable(x):
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    return x
