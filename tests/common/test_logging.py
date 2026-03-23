"""
Tests: common.logging_utils

Purpose:
    Verify that logging system correctly writes to file and handles paths.

What is tested:
    - Log file is created
    - Log messages are written to file
    - Parent directories are created automatically

Why it matters:
    Logging is the only trace of execution in production runs.
    Missing logs = impossible debugging.

Notes:
    Uses temporary paths to isolate filesystem effects.
"""

from pathlib import Path
from aeris.common.logging_utils import setup_logger

def test_logger_writes_file(tmp_path):
    log_file = tmp_path / "test.log"

    logger = setup_logger(log_file)

    logger.info("hello world")

    assert log_file.exists()

    content = log_file.read_text()
    assert "hello world" in content

def test_logger_creates_parent_dir(tmp_path):
    log_file = tmp_path / "logs" / "test.log"

    logger = setup_logger(log_file)
    logger.info("test")

    assert log_file.exists()