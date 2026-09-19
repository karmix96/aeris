"""Does the geometry the SOLVER saw match the design vector that asked for it?

Every audit so far started at the mesh. The mesh is verified against the loft --
its wall sits 2.2e-16 m from it -- but the loft itself was taken on trust:
"built from the design vector, assumed correct upstream". This closes that link,
and it measures the mesh rather than any export, because the mesh is what the
solver integrated forces on.

The generator interpolates twist and dihedral piecewise-linearly between the four
design values (`sections.py`). Chord, span and sweep are unambiguous and are
checked hard. Twist is checked at every one of the generator's own section
stations inboard of 95 % semispan, against the generator's own distribution.

How twist is measured matters more than it looks, and an earlier version of this
file reported 0.19-0.76 deg of missing washout that the geometry does not have:
  * the chord line runs from the trailing edge to the point of the section
    FARTHEST from it;
  * the trailing edge is the MIDDLE of the opened trailing-edge base. The CFD
    surface opens the loft's sharp trailing edge symmetrically about the camber
    line, to 0.5 % of chord (1 mm at least), so either corner alone sits a quarter
    per cent of chord off it and reads about 0.15 deg of false washout;
  * it is read on a full section, not on the last span row, which is the tip
    closure.
Separately, and not a defect of the wing: pyGeo's own u = 1 point is not that
leading edge for two of the three airfoils, so the `twist_deg` of EXTRACTED
sections -- which AVL is written with -- reads 0.18 deg high inboard and 0.5 deg
high at the tip. That is a label, not a shape: AVL's sections lie within 0.13 %
of chord of the loft. Anything that reads `twist_deg` off extracted sections as a
design quantity inherits the offset.

    PYTHONPATH=src python geometry_audit.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
PILOT = HERE / "runs/s8_pilot"
SET_NAME = "lhs100_seed42"
#: how close is close enough, and why
TOLERANCE = {"root_chord_m": 0.01,          # 1 %: the mesh resolves the root exactly
             "semi_span_m": 0.01,           # 1 %: the tip cap rounds the last millimetre
             "tip_over_root": 0.05,         # 5 %: the tip chord is rounded by the cap
             "outer_sweep_deg": 1.0,        # degrees
             # degrees: a blended section has no unique leading edge; the loft
             # itself sits up to 0.13 deg from the generator's distribution there
             "twist_max_error_deg": 0.2}
TWIST_INBOARD_OF = 0.95


def design_matrix():
    sys.path.insert(0, str(STUDY / "04_strategy_studies"))
    from shared.geometry_sets import design_matrix as dm
    X, names = dm(SET_NAME)
    return np.asarray(X), list(names)


def design_twist(index: int) -> tuple[np.ndarray, np.ndarray]:
    """The generator's own section stations and twist, before any loft."""
    sys.path.insert(0, str(STUDY / "04_strategy_studies/S6_bounded_mesh_atlas"))
    import strategy_s6
    from aeris.generators.bwb_segmented_v1.planform import generate_bwb_planform_from_sample
    from aeris.generators.bwb_segmented_v1.sections import build_section_geometry_from_sample
    sample, config = strategy_s6.sample(SET_NAME, index), strategy_s6._config()
    geometry = build_section_geometry_from_sample(
        generate_bwb_planform_from_sample(sample, config), sample, config)
    return (np.array([s.y_m for s in geometry.sections]),
            np.array([s.twist_deg for s in geometry.sections]))


def wall_of(index: int, level: str = "gci_C") -> np.ndarray | None:
    """The wing surface as (around, span, 3), straight out of the built mesh."""
    blocks = PILOT / f"g{index}" / f"{level}_blocks.npz"
    if not blocks.exists():
        return None
    return np.load(blocks)["o_wing"][:, 0, :, :]


def section_at(wall: np.ndarray, y: float) -> np.ndarray:
    """The wall interpolated column by column to one span station."""
    ring = np.empty((wall.shape[0], 3))
    for j in range(wall.shape[0]):
        yy = wall[j, :, 1]
        o = np.argsort(yy)
        ring[j] = [np.interp(y, yy[o], wall[j, o, axis]) for axis in range(3)]
    return ring


def twist_of(ring: np.ndarray) -> float:
    """Nose-up positive chord-line angle; see the module docstring for why this way."""
    chord = float(np.ptp(ring[:, 0]))
    base = ring[ring[:, 0] > ring[:, 0].max() - 0.002 * chord]
    te = 0.5 * (base[int(np.argmax(base[:, 2]))] + base[int(np.argmin(base[:, 2]))])
    le = ring[int(np.argmax(np.linalg.norm(ring - te, axis=1)))]
    return float(np.degrees(np.arctan2(-(te[2] - le[2]), te[0] - le[0])))


def measure(wall: np.ndarray) -> dict:
    y = wall[0, :, 1]
    def section(k):
        return wall[:, k, :]
    def chord(sec):
        return float(sec[:, 0].max() - sec[:, 0].min())
    def leading_edge_x(k):
        return float(section(k)[:, 0].min())
    outer = [k for k in range(len(y)) if y[k] >= 0.75 * y.max()]
    dy = y[outer[-1]] - y[outer[0]]
    sweep = np.degrees(np.arctan2(leading_edge_x(outer[-1]) - leading_edge_x(outer[0]), dy))
    return {"root_chord_m": chord(section(0)),
            "semi_span_m": float(y.max()),
            "tip_over_root": chord(section(-1)) / chord(section(0)),
            "outer_sweep_deg": float(sweep)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=STUDY /
                    "reports/s8_geometry_audit.json")
    args = ap.parse_args()

    X, names = design_matrix()
    col = {n: i for i, n in enumerate(names)}
    designs, outside = {}, []
    print(f"{'geom':>5}{'root chord':>22}{'semi-span':>20}{'tip/root':>18}"
          f"{'outer sweep':>20}{'twist worst error':>30}")
    for gdir in sorted(PILOT.glob("g[0-9]*"), key=lambda p: int(p.name[1:])):
        index = int(gdir.name[1:])
        wall = wall_of(index)
        if wall is None:
            continue
        got = measure(wall)
        v = X[index]
        want = {"root_chord_m": float(v[col["c1_m"]]),
                "semi_span_m": float(v[col["b_total_m"]]),
                "tip_over_root": float(v[col["c4_ratio"]]),
                "outer_sweep_deg": float(-v[col["sw3_deg"]])}
        entry, line = {}, f"{index:>5}"
        for key, asked in want.items():
            built = got[key]
            diff = built - asked
            limit = TOLERANCE[key]
            ok = abs(diff) <= (limit if key.endswith("_deg") else limit * abs(asked))
            entry[key] = {"asked_for": asked, "built": built, "difference": diff,
                          "within_tolerance": bool(ok)}
            if not ok:
                outside.append({"geometry": index, "quantity": key, "asked_for": asked,
                                "built": built, "difference": diff})
            line += f"{asked:>9.3f} ->{built:>8.3f}{'' if ok else ' !'}"

        y_design, t_design = design_twist(index)
        stations = y_design[y_design <= TWIST_INBOARD_OF * got["semi_span_m"]]
        rows = [{"y_m": float(y), "design_deg": float(np.interp(y, y_design, t_design)),
                 "mesh_deg": twist_of(section_at(wall, float(y)))} for y in stations]
        errors = np.array([r["mesh_deg"] - r["design_deg"] for r in rows])
        k = int(np.argmax(np.abs(errors)))
        ok = bool(abs(errors[k]) <= TOLERANCE["twist_max_error_deg"])
        entry["twist"] = {"stations": rows, "worst_error_deg": float(errors[k]),
                          "worst_at_y_m": rows[k]["y_m"], "rms_error_deg":
                          float(np.sqrt(np.mean(errors ** 2))), "within_tolerance": ok}
        if not ok:
            outside.append({"geometry": index, "quantity": "twist_max_error_deg",
                            "asked_for": rows[k]["design_deg"], "built": rows[k]["mesh_deg"],
                            "difference": float(errors[k])})
        line += f"   {errors[k]:+.3f} at y {rows[k]['y_m']:.3f} (rms {entry['twist']['rms_error_deg']:.3f}){'' if ok else ' !'}"
        designs[str(index)] = entry
        print(line)

    total = len(designs) * len(TOLERANCE)
    report = {"schema": "aeris.s8.geometry_audit.v2",
              "question": "does the mesh the solver integrated match the design vector?",
              "source": "the built mesh (o_wing wall block), not any export; twist against "
                        "the generator's own section distribution",
              "tolerances": TOLERANCE,
              "twist_method": ("chord line from the middle of the opened trailing-edge base to "
                               "the farthest point of the section, at every generator station "
                               f"inboard of {TWIST_INBOARD_OF:.0%} semispan"),
              "designs": designs, "outside_tolerance": outside}
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\n{total - len(outside)}/{total} measurements within tolerance")
    for o in outside:
        print(f"  g{o['geometry']} {o['quantity']}: asked {o['asked_for']:.3f}, "
              f"built {o['built']:.3f} ({o['difference']:+.3f})")
    print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
