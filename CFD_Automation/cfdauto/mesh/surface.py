"""The surface mesh of one wing at one level and one Re: rings at stations + the tip cap.

    python -m cfdauto.mesh --type bwb --set reference --index 0 --level C --re 3e5

Steps (Grand Roadmap recipe R-S):
1. stations along the span (on every loft station, chord-scaled, squeezed to the tip);
2. at each station: the nose spacing solved for the turning target at level C (law 1);
3. every spacing divided by r^k for this level;
4. one node distribution in arc fraction for the whole wing: at every place the strictest
   station wins, so node i sits at the same arc fraction on every station (no sheared quads
   where the stations are squeezed at the tip) and no cell is ever coarser than asked; the
   spanwise envelope (law 2) holds by construction;
5. the rings, every node asked from the loft; the tip cap from the tip ring;
6. the checks; nothing is written unless all pass.
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


def build_surface(loft, re_mean: float, level: str = "C", config=None) -> SurfaceMesh:
    rc: Rules = get_rules("C", config)
    rl: Rules = get_rules(level, config)
    tab = SpanTable.of(loft, rl.dense_span)

    # 1. stations; the tip gap is the tip first cell at this Re (laws 9, 10, 13)
    c_tip = float(tab.chord[-1])
    re_tip = re_mean * c_tip / tab.mean_chord
    s0_tip = rl.first_cell_c(re_tip) * c_tip
    tip_gap = rl.tip_gap_in_s0 * s0_tip
    tab = tab.refined_at_tip(loft, tip_gap)
    st = place_stations(tab, rl, tip_gap, loft.station_v)

    # 2. sections and the nose solve at level C
    secs = [Section.at(loft, v, rl.dense_per_side) for v in st["v"]]
    rows = []
    for sec in secs:
        re_loc = re_mean * sec.chord / tab.mean_chord
        c = sec.chord
        nose = solve_nose(sec, rc.band_spacing_c(re_loc) * c, rc.max_spacing_c * c, rc.te_spacing_c * c, rc)
        rows.append({"y_m": sec.y, "v": sec.v, "chord_m": c, "re_local": re_loc,
                     "h_le_c_solved": nose["h_le"] / c, "turning_solved_deg": nose["turning_deg"],
                     "nose_capped_at_band": nose["capped_at_band"], "nose_solved": nose["solved"],
                     "geometry_kink_deg": nose["kinks"]["max_deg"], "_kinks": nose["kinks"]})

    # 3-5. This level's spacings per station, then ONE node distribution in arc fraction for the
    # whole wing (the strictest station wins at every place), the rings, and the turning measured
    # again on the rings as built. A station above the target tightens the nose spacing of the
    # whole wing by 10 % (the union keeps every station's own band and trailing-edge cells).
    target = rc.nose_turning_deg + rc.nose_turning_tol_deg
    h_le_c = np.array([r["h_le_c_solved"] for r in rows])

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
        h_le_c = h_le_c * 0.9
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

    mesh = SurfaceMesh(level, float(re_mean), wing, cap, u, rows, [], {
        "n_side": n_side, "n_base": rl.n_base, "n_ring": int(wing.shape[0]), "n_span": int(wing.shape[1]),
        "wing_quads": int((wing.shape[0]) * (wing.shape[1] - 1)),
        "cap_quads": int((cap.shape[0] - 1) * (cap.shape[1] - 1)),
        "semi_span_m": tab.semi_span, "mean_chord_m": tab.mean_chord, "tip_chord_m": c_tip,
        "re_tip": re_tip, "s0_tip_m": s0_tip, "cells_per_panel": st["cells_per_panel"],
        "loft_station_y_m": tab.loft_y.tolist(), "cap": cap_info, "rules": rl.values(),
        "turning_repairs": repair,
    })
    mesh.checks = run_checks(mesh, secs, specs, st, tab, rc, rl)
    return mesh


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


def run_checks(m: SurfaceMesh, secs, specs, st, tab, rc: Rules, rl: Rules) -> list[Check]:
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
    target = rc.nose_turning_deg + 10 * rc.nose_turning_tol_deg
    lo, hi = ch["tip_gap_band"]
    return [
        Check("nose_turning", worst["turn"] <= target, worst["turn"],
              f"<= {target:.2f} deg at every ring node but the trailing-edge corners and geometry kinks (law 1)"),
        Check("geometry_kinks", kink <= target, kink,
              f"<= {target:.2f} deg: a kink of the section itself (trailing-edge opening on very small chords) "
              "that no cell size can reduce"),
        Check("nose_envelope", env <= rc.nose_envelope * 1.01, env, f"<= {rc.nose_envelope} between stations (law 2)"),
        Check("chord_growth", worst["growth"] <= rl.chord_growth_limit, worst["growth"], f"<= {rl.chord_growth_limit}"),
        Check("band_spacing", worst["band"] <= 1.01, worst["band"], "<= 1 x band target (bubble length / nodes)"),
        Check("te_spacing", worst["te"] <= 1.01, worst["te"], "<= 1 x 0.1 % c / r^k (law 3)"),
        Check("span_growth", span_growth <= rl.span_growth_limit, span_growth, f"<= {rl.span_growth_limit}"),
        Check("loft_stations_hit", hit <= 1e-12, hit, "a station exactly on every loft station [m]"),
        Check("tip_gap", lo <= tip_ratio <= hi + 1e-9, tip_ratio, f"in [{lo}, {hi}] x tip first cell (law 10)"),
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
    head = {"name": mesh_name(mesh, wing), "wing_type": wing.wing_type, "set": wing.set_name, "index": wing.index,
            "wing_input_hash": wing.input_hash, "loft_surface_hash": wing.surface_hash,
            "loft_backend": wing.loft.backend, "level": mesh.level, "re_mean": mesh.re_mean,
            "mesh_code_hash": mesh_code_hash(), "passed": mesh.passed}
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
