"""Does the geometry the SOLVER saw match the design vector that asked for it?

Every audit so far started at the mesh. The mesh is verified against the loft --
its wall sits 2.2e-16 m from it -- but the loft itself was taken on trust:
"built from the design vector, assumed correct upstream". This closes that link,
and it measures the mesh rather than any export, because the mesh is what the
solver integrated forces on.

The generator interpolates twist and dihedral piecewise-linearly between the four
design values (`sections.py`), so the built wing should meet them at the
boundaries. Chord, span and sweep are unambiguous and are checked hard. Twist is
checked softly and reported with its own uncertainty: the angle of a blended
section's leading-edge-to-trailing-edge line is not the same quantity as the
generator's nominal twist axis, and near the rounded tip the two differ by a few
tenths of a degree whatever the generator does.

    python geometry_audit.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
PILOT = STUDY / "artifacts/s8_pilot"
#: how close is close enough, and why
TOLERANCE = {"root_chord_m": 0.01,          # 1 %: the mesh resolves the root exactly
             "semi_span_m": 0.01,           # 1 %: the tip cap rounds the last millimetre
             "tip_over_root": 0.05,         # 5 %: the tip chord is rounded by the cap
             "outer_sweep_deg": 1.0,        # degrees
             "twist_change_deg": 0.6}       # degrees, convention-limited (see above)


def design_matrix():
    sys.path.insert(0, str(STUDY / "04_strategy_studies"))
    from shared.geometry_sets import design_matrix as dm
    X, names = dm("lhs100_seed42")
    return np.asarray(X), list(names)


def wall_of(index: int, level: str = "gci_C") -> np.ndarray | None:
    """The wing surface as (around, span, 3), straight out of the built mesh."""
    blocks = PILOT / f"g{index}" / f"{level}_blocks.npz"
    if not blocks.exists():
        return None
    return np.load(blocks)["o_wing"][:, 0, :, :]


def measure(wall: np.ndarray) -> dict:
    y = wall[0, :, 1]
    def section(k):
        return wall[:, k, :]
    def chord(sec):
        return float(sec[:, 0].max() - sec[:, 0].min())
    def twist(sec):
        x, z = sec[:, 0], sec[:, 2]
        le, te = int(np.argmin(x)), int(np.argmax(x))
        return float(np.degrees(np.arctan2(-(z[te] - z[le]), x[te] - x[le])))
    def leading_edge_x(k):
        return float(section(k)[:, 0].min())
    outer = [k for k in range(len(y)) if y[k] >= 0.75 * y.max()]
    dy = y[outer[-1]] - y[outer[0]]
    sweep = np.degrees(np.arctan2(leading_edge_x(outer[-1]) - leading_edge_x(outer[0]), dy))
    return {"root_chord_m": chord(section(0)),
            "semi_span_m": float(y.max()),
            "tip_over_root": chord(section(-1)) / chord(section(0)),
            "outer_sweep_deg": float(sweep),
            "twist_change_deg": twist(section(-1)) - twist(section(0)),
            "root_twist_deg": twist(section(0)), "tip_twist_deg": twist(section(-1))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=STUDY /
                    "05_s6_cfd_qualification/reports/s8_geometry_audit.json")
    args = ap.parse_args()

    X, names = design_matrix()
    col = {n: i for i, n in enumerate(names)}
    designs, outside = {}, []
    print(f"{'geom':>5}{'root chord':>22}{'semi-span':>20}{'tip/root':>18}"
          f"{'outer sweep':>20}{'twist root->tip':>24}")
    for gdir in sorted(PILOT.glob("g[0-9]*")):
        index = int(gdir.name[1:])
        wall = wall_of(index)
        if wall is None:
            continue
        got = measure(wall)
        v = X[index]
        want = {"root_chord_m": float(v[col["c1_m"]]),
                "semi_span_m": float(v[col["b_total_m"]]),
                "tip_over_root": float(v[col["c4_ratio"]]),
                "outer_sweep_deg": float(-v[col["sw3_deg"]]),
                "twist_change_deg": float(v[col["twist_b3_deg"]] - v[col["twist_b0_deg"]])}
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
        entry["measured_twist_deg"] = {"root": got["root_twist_deg"], "tip": got["tip_twist_deg"]}
        designs[str(index)] = entry
        print(line)

    total = len(designs) * len(TOLERANCE)
    report = {"schema": "aeris.s8.geometry_audit.v1",
              "question": "does the mesh the solver integrated match the design vector?",
              "source": "the built mesh (o_wing wall block), not any export",
              "tolerances": TOLERANCE,
              "twist_note": ("measured as the leading-edge-to-trailing-edge line angle, which "
                             "is not the generator's nominal twist axis; near the rounded tip "
                             "the two differ by a few tenths of a degree by construction"),
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
