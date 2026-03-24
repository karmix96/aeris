from __future__ import annotations

from pathlib import Path

import pytest

from aeris.aero.io import read_aero_result

pytestmark = [pytest.mark.integration]

RUN_DIR = Path("data/runs/2026-03-24_172547_913777_aero_baseline_bwb_25")

if not RUN_DIR.exists():
    pytest.skip(f"Missing saved aero run dir: {RUN_DIR}", allow_module_level=True)


def test_saved_aero_result_can_be_reloaded() -> None:
    result = read_aero_result(RUN_DIR)

    assert result is not None
    assert isinstance(result, dict)

    assert result["status"] == "success"
    assert "scalars" in result

    scalars = result["scalars"]
    assert scalars["cl"] is not None
    assert scalars["cd"] is not None
    assert scalars["cm"] is not None