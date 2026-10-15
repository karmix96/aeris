from pathlib import Path

import pytest

from aeris_research.common import PipelineError, reject_output_inside_inputs


def test_output_guard_rejects_protected_descendant(tmp_path):
    protected = tmp_path / "qualification"
    protected.mkdir()
    with pytest.raises(PipelineError, match="inside protected input tree"):
        reject_output_inside_inputs(protected / "paper", [protected])


def test_output_guard_accepts_isolated_sibling(tmp_path):
    protected = tmp_path / "qualification"
    protected.mkdir()
    output = tmp_path / "research" / "build"
    assert reject_output_inside_inputs(output, [protected]) == Path(output).resolve()
