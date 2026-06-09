from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from aeris.generators.bwb_segmented_v1 import vsp_export


@pytest.mark.skipif(
    shutil.which("vsp") is None and shutil.which("OpenVSP") is None,
    reason="OpenVSP executable not installed/discoverable; STEP smoke skipped.",
)
def test_openvsp_step_execution_smoke_when_available(tmp_path):
    exe = shutil.which("vsp") or shutil.which("OpenVSP")
    script = tmp_path / "minimal.vspscript"
    # This smoke only verifies batch invocation/capture. Full geometry STEP export
    # is covered by operator validation because it depends on local OpenVSP build capabilities.
    script.write_text("Print(\"AERIS OpenVSP smoke\\n\");\n", encoding="utf-8")
    result = vsp_export.run_openvsp_batch_script(
        vspscript_path=script,
        openvsp_executable=exe or "vsp",
        stdout_path=tmp_path / "stdout.txt",
        stderr_path=tmp_path / "stderr.txt",
        step_path=tmp_path / "geometry.step",
        timeout_sec=30,
    )
    assert result.attempted is True
    assert result.stdout_path.exists()
    assert result.stderr_path.exists()
