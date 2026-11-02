"""Prove, with numbers, that each built wing is the intended wing.

    python scripts/verify_geometry.py                 # all published wings
    python scripts/verify_geometry.py --wings onera_m6 crm_approx
    python scripts/verify_geometry.py --backend numpy # force the scipy loft

Writes docs/verification.json and docs/verification.md. Exit code 1 if any check fails.

Checks (see cfdauto/geometry/verify.py):
  sections   loft cut at each station vs the ORIGINAL airfoil points   <= 0.01 % chord
  edges      leading/trailing edge vs exact straight lines             <= 1e-6 % chord
  ruled      panels are straight blends of their two sections          <= 1e-6 % chord
  cad (M6)   loft vs the CATIA model AileM6_with_sharp_TE.igs          <= 0.05 % chord
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfdauto.geometry import published_wings as pw, verify  # noqa: E402
from cfdauto.geometry.loft import build_loft  # noqa: E402
from cfdauto.geometry.sections import build_wing_sections  # noqa: E402

LIMITS = {"sections": 0.01, "edges": 1e-6, "ruled": 1e-6, "cad": 0.05}


def check(name: str, backend: str | None) -> dict:
    spec, vec, te, meta = pw.get(name)
    _, stations = build_wing_sections(spec, vec, te)
    loft = build_loft(stations, backend=backend)
    aft = None if te.mode == "as_is" else te.open_from_xc   # rule mode opens the TE on purpose
    sec = verify.section_fidelity(loft, stations, exclude_aft_of=aft)
    edges = verify.planform_edges(loft, stations)
    ruled = verify.ruled_panels(loft, stations)
    r = {"wing": name, "backend": loft.backend, "te_mode": te.mode,
         "sections_max_pct": max(s["max_pct_chord"] for s in sec), "sections": sec,
         "edges_max_pct": max(edges["le_max_pct"], edges["te_max_pct"]),
         "ruled_max_pct": ruled}
    if name == "onera_m6" and verify.M6_CAD.is_file():
        try:
            r["cad"] = verify.onera_m6_vs_cad(loft)
        except ImportError:
            r["cad"] = None          # gmsh not installed
    r["pass"] = (r["sections_max_pct"] <= LIMITS["sections"] and r["edges_max_pct"] <= LIMITS["edges"]
                 and r["ruled_max_pct"] <= LIMITS["ruled"]
                 and (not r.get("cad") or r["cad"]["max_pct_chord"] <= LIMITS["cad"]))
    return r


def to_md(rows: list[dict]) -> str:
    out = ["# Geometry verification", "",
           "Numbers, not pictures. All errors in % of local chord. Limits: "
           f"sections {LIMITS['sections']}, edges {LIMITS['edges']}, ruled {LIMITS['ruled']}, "
           f"CAD {LIMITS['cad']}.", "",
           "| wing | loft | sections max | edges max | ruled max | outside data | pass |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        cad = r.get("cad")
        cad_s = (f"CATIA IGES: max {cad['max_pct_chord']:.4f}, rms {cad['rms_pct_chord']:.4f}"
                 if cad else "none in repo")
        out.append(f"| {r['wing']} | {r['backend']} | {r['sections_max_pct']:.5f} | "
                   f"{r['edges_max_pct']:.1e} | {r['ruled_max_pct']:.1e} | {cad_s} | "
                   f"{'yes' if r['pass'] else 'NO'} |")
    sus = sorted({(s["airfoil"], x, side) for r in rows for s in r["sections"] for x, side in s["suspect_points"]})
    if sus:
        out += ["", "Points in the airfoil files that look like typos (one point off a smooth line; "
                "left out of the error, the loft smooths over them):", ""]
        out += [f"- {a}: {side} surface at x/c {x}" for a, x, side in sus]
    out += ["", "What this proves and what it does not:", "",
            "- sections/edges/ruled: the surface is exactly the wing the parameters describe "
            "(right airfoils, chords, sweeps, twists, straight panels).",
            "- outside data: only the ONERA M6 has an independent CAD model here. BlendedNet, CRM "
            "and RIBES need their own surface files (see OPEN_DECISIONS.md) to prove the "
            "parameters themselves are right.", ""]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wings", nargs="*", default=None)
    ap.add_argument("--backend", choices=["pygeo", "numpy"], default=None)
    ap.add_argument("--out", default=str(ROOT / "docs"))
    a = ap.parse_args()
    rows = [check(n, a.backend) for n in (a.wings or pw.names())]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "verification.json").write_text(json.dumps(rows, indent=1))
    (out / "verification.md").write_text(to_md(rows))
    print(to_md(rows))
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
