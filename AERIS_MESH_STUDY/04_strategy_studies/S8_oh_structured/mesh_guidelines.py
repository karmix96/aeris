"""Judge a built mesh against the published gridding guidelines, not our own.

Our own checks answer "is the mesh what we asked for". This one answers the
different question the cloud spend depends on: "is what we asked for what the
field asks for". Every criterion below is somebody else's number, with the
source named, because a criterion we invented is a criterion we can talk
ourselves out of.

Sources
  AIAA CFD Drag Prediction Workshop gridding guidelines (Workshops 3-7,
  aiaa-dpw.larc.nasa.gov): y+ < 1 on the COARSEST grid and finer above it;
  growth rate of cell sizes in the viscous layer < 1.25; two constant-spacing
  layers at the wall; chordwise spacing ~0.1 % of local chord at leading and
  trailing edge; spanwise spacing ~0.1 % of semispan at root and tip; outer
  boundary ~100 reference chords; the same family, stretching and topology at
  every refinement level.
  NASA Turbulence Modeling Resource (tmbwg.github.io/turbmodels): wall-resolved
  RANS integrates to the wall, so y+ <= 1 with no wall functions; freestream
  turbulence for SA is chi = 3 to 5.
  Celik et al., J. Fluids Eng. 130 (2008): three grids, refinement factor >= 1.3,
  GCI on the finest pair.
  Common practice for wall-resolved RANS: 30-40 cells inside the boundary layer.
  One drag count is 1e-4 in CD; workshop scatter across codes is 4-5 counts,
  which is the yardstick for "does this difference matter".

    python mesh_guidelines.py --blocks .../gci_C_blocks.npz --summary .../gci_C_summary.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
STUDY = HERE.parents[1]
#: mission_authority_v1.yaml
RE_PER_METRE = 1530708.188575197 / 0.9


def check(name: str, value: float, limit: str, ok: bool, source: str, note: str = "") -> dict:
    return {"criterion": name, "value": value, "limit": limit, "pass": bool(ok),
            "source": source, "note": note}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--blocks", type=Path, required=True)
    ap.add_argument("--summary", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    data = np.load(args.blocks)
    w = data["o_wing"]                       # (around, normal, span, 3)
    wall = w[:, 0, :, :]
    summary = json.loads(args.summary.read_text()) if args.summary and args.summary.exists() else {}

    k = wall.shape[1] // 2
    ring = wall[:, k, :]
    chord = float(ring[:, 0].max() - ring[:, 0].min())
    around = np.linalg.norm(np.diff(ring, axis=0), axis=1)
    le = int(np.argmin(ring[:, 0]))
    span = wall[0, :, 1]
    semispan = float(span.max())
    dspan = np.diff(span)
    line = w[wall.shape[0] // 4, :, k, :]
    layer = np.linalg.norm(np.diff(line, axis=0), axis=1)
    growth = layer[1:] / layer[:-1]
    distance = np.concatenate([[0.0], np.cumsum(layer)])
    x = float(abs(line[0, 0] - ring[:, 0].min())) or 0.05
    delta = 0.37 * x / (RE_PER_METRE * x) ** 0.2      # turbulent boundary-layer estimate
    s0 = float(layer[0])
    # y+ from the first cell, via a flat-plate skin-friction estimate
    cf = 0.026 / (RE_PER_METRE * x) ** (1 / 7)
    yplus = s0 * RE_PER_METRE * (cf / 2) ** 0.5

    dpw = "AIAA Drag Prediction Workshop gridding guidelines"
    checks = [
        check("first cell, y+ (estimated)", yplus, "<= 1", yplus <= 1.0,
              "TMR / DPW", "measured y+ from the solution is the authority; this is the mesh's own estimate"),
        check("growth ratio in the viscous layer", float(growth[:20].max()), "< 1.25",
              growth[:20].max() < 1.25, dpw),
        check("constant-spacing layers at the wall", int(np.sum(np.abs(growth[:5] - 1) < 0.01)),
              ">= 2", np.sum(np.abs(growth[:5] - 1) < 0.01) >= 2, dpw),
        check("cells inside the boundary layer", int(np.sum(distance < delta)), ">= 30",
              np.sum(distance < delta) >= 30, "common practice for wall-resolved RANS"),
        check("leading-edge spacing, % of local chord", 100 * float(around[max(le - 1, 0)]) / chord,
              "~0.1 %", around[max(le - 1, 0)] / chord <= 0.0015, dpw),
        check("trailing-edge spacing, % of local chord", 100 * float(around[0]) / chord,
              "~0.1 %", around[0] / chord <= 0.0015, dpw),
        check("spanwise spacing at the root, % of semispan", 100 * float(dspan[0]) / semispan,
              "~0.1 %", dspan[0] / semispan <= 0.0015, dpw,
              "DPW clusters at the root for a wing-body junction; this wing meets a symmetry plane"),
        check("spanwise spacing at the tip, % of semispan", 100 * float(dspan[-1]) / semispan,
              "~0.1 %", dspan[-1] / semispan <= 0.0015, dpw),
    ]
    far = summary.get("volume", {}).get("farfield_root_chords")
    if far:
        checks.append(check("far field, root chords", float(far), "~100", far >= 100, dpw,
                            "measured sensitivity 40 -> 60 chords: 0.33 % of CD at alpha 0, "
                            "0.23 % at alpha 8, which is 0.7 and 0.5 drag counts"))
    folded = summary.get("negative_cells_all_blocks")
    if folded is not None:
        checks.append(check("folded cells", int(folded), "0", folded == 0, "any"))

    failed = [c for c in checks if not c["pass"]]
    print(f"{'criterion':<46}{'value':>12}  {'limit':<10} verdict")
    for c in checks:
        v = c["value"]
        print(f"  {c['criterion']:<44}{v:>12.4g}  {c['limit']:<10} "
              f"{'pass' if c['pass'] else 'FAIL'}")
    print(f"\n  {len(checks) - len(failed)}/{len(checks)} criteria met")
    for c in failed:
        print(f"    FAIL  {c['criterion']}: {c['value']:.4g} against {c['limit']}  [{c['source']}]")
        if c["note"]:
            print(f"          {c['note']}")

    report = {"schema": "aeris.s8.mesh_guidelines.v1", "blocks": str(args.blocks),
              "checks": checks, "failed": len(failed)}
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
