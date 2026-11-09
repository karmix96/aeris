"""Which rule set the study scripts build, and where their files go.

    STAGE3_RULESET=2 (the default since decision 107): configs/volume.yaml; data and figures prefixed r2_
    STAGE3_RULESET=1: configs/volume_rules1.yaml (V0-V6); data and figures without a prefix (the record; it was built
                      with the construction before decisions 106 and 108-110, commit 3ddc29c)
"""

from __future__ import annotations

import os
from pathlib import Path

RULESET = os.environ.get("STAGE3_RULESET", "2")
if RULESET not in ("1", "2"):
    raise SystemExit(f"STAGE3_RULESET must be 1 or 2, not {RULESET!r}")
CONFIG = None if RULESET == "2" else str(Path(__file__).resolve().parents[1] / "configs" / "volume_rules1.yaml")
PREFIX = "" if RULESET == "1" else f"r{RULESET}_"
