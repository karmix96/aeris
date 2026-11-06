"""Per-wing refine maps of the reference wings, for the interactive page (docs/REFINE_MAP.html).

    python scripts/refine_map_data.py        # writes data/studies/refine_map_reference.json (about 10 s)

Every reference wing (4 types × 5) on the grid Mach 0.03–0.20 (7 values) × root angle −5…12° (1° steps; from
−5° since 6 Nov 2026, was −2°) at sea level, 3 strips per panel. The numbers are the Stage 1 section tables through the flow-map engine; nothing
new is computed, only read out per wing and per condition.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cfdauto.mesh.laws import rules  # noqa: E402
from cfdauto.mesh.refine_map import ALPHAS, GENERIC_BAND, MACHS, strip_map  # noqa: E402
from cfdauto.paths import STAGE2  # noqa: E402

OUT = STAGE2 / "data" / "studies" / "refine_map_reference.json"
TYPES = ("bwb", "flying_wing", "cranked", "tapered")


def main() -> None:
    rc = rules("C")
    ch = rc.raw["chord"]
    wings = []
    for t in TYPES:
        for i in range(5):
            sm = strip_map(t, "reference", i, machs=MACHS, alphas=ALPHAS, alts=(0.0,), n_per_panel=3)
            sm["fields"].pop("cl", None)
            wings.append(sm)
            print(t, i, "strips", sm["shape"][0], "answered", sum(sm["fields"]["answered"]), "of", len(sm["fields"]["answered"]))
    doc = {"wings": wings,
           "rules": {"generic_band": GENERIC_BAND, "nodes_per_bubble": float(ch["nodes_per_bubble"]),
                     "max_spacing_c": float(ch["max_spacing_c"]),
                     "bubble_table": {"re": [float(v) for v in ch["bubble_length"]["re"]], "l_c": [float(v) for v in ch["bubble_length"]["l_c"]]}},
           "focus_mach": {"tailless": [0.03, 0.13], "conventional": [0.03, 0.20]},
           "source": "Stage 1 section tables (2-D XFOIL, free transition, N_crit 9) through cfdauto.flowmap.engine; "
                     "strips with a uniform (elliptic) induced angle; sea level."}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, separators=(",", ":")))
    print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
