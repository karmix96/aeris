"""
Tests: common.config

Purpose:
    Validate YAML configuration loading and basic input validation.

What is tested:
    - Valid YAML loads correctly
    - Invalid file extension is rejected
    - Missing file raises error

Why it matters:
    Config is the entry point of all pipelines.
    Invalid configs must fail early and clearly.

Limitations:
    Does not validate schema or parameter correctness (handled elsewhere).
"""

from aeris.common.config import load_yaml_config
import pytest

def test_load_valid_yaml(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("a: 1\nb: 2")

    data = load_yaml_config(f)

    assert data["a"] == 1


def test_invalid_extension(tmp_path):
    f = tmp_path / "config.txt"
    f.write_text("a: 1")

    with pytest.raises(ValueError):
        load_yaml_config(f)


def test_missing_file():
    import pytest
    with pytest.raises(FileNotFoundError):
        load_yaml_config("nonexistent.yaml")