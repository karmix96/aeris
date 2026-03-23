"""
Module: logging_utils

Purpose:
    Provides standardized logger setup for AERIS runs.

Responsibilities:
    - Create logger with console + file output
    - Ensure log file directory exists
    - Apply consistent formatting

Guarantees:
    - Log file is always created
    - Logs are persisted per run

Caveats:
    - Logger handlers are reset each call
    - Logging level is fixed (INFO)

Future Improvements:
    - Configurable log levels
    - Structured logging (JSON)
"""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logger(log_file: Path, logger_name: str = "aeris") -> logging.Logger:
    """Create a logger that writes to both console and file."""

    log_file.parent.mkdir(parents=True, exist_ok=True)  # ✅ FIX

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger
