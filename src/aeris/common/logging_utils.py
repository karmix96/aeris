"""
Module: logging_utils

Purpose:
    Standardized logger setup for AERIS runs.

Responsibilities:
    - Create logger with rotating file output
    - Optionally mirror logs to console
    - Ensure log file directory exists
    - Apply consistent formatting
    - Reset existing handlers safely

Production logic:
    - Repeated setup calls close stale file handlers.
    - Default logger names are unique per log file path.
    - Long runs use rotating log files by default.
    - Parallel workers should use separate log files.

Caveats:
    - This is process-local logging.
    - Multiple OS processes should not intentionally write to the same log file.
    - Queue-based multi-process logging can be added later for heavy parallelism.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class JsonLineFormatter(logging.Formatter):
    """Minimal dependency-free JSON-lines log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp_utc": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def _logger_name_from_path(log_file: Path) -> str:
    """Create a stable logger name from an absolute log path."""
    resolved = str(Path(log_file).expanduser().resolve())
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:12]
    return f"aeris.run.{digest}"


def _close_existing_handlers(logger: logging.Logger) -> None:
    """Flush, close, and remove all handlers currently attached to logger."""
    for handler in list(logger.handlers):
        try:
            handler.flush()
        finally:
            handler.close()
            logger.removeHandler(handler)


def _build_formatter(format_style: str) -> logging.Formatter:
    """Build either text or JSON-lines formatter."""
    normalized = format_style.strip().lower()

    if normalized == "text":
        return logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    if normalized == "json":
        return JsonLineFormatter()

    raise ValueError("format_style must be either 'text' or 'json'.")


def setup_logger(
    log_file: str | Path,
    logger_name: str | None = None,
    level: int = logging.INFO,
    *,
    console: bool = True,
    max_bytes: int = 50 * 1024 * 1024,
    backup_count: int = 5,
    format_style: str = "text",
) -> logging.Logger:
    """Create a logger that writes to a rotating file and optionally console.

    Args:
        log_file:
            Path to the log file.
        logger_name:
            Optional explicit logger name. If omitted, a stable unique name is
            generated from the log file path.
        level:
            Logging level, e.g. logging.INFO, logging.DEBUG, logging.WARNING.
        console:
            Whether to also write logs to stderr/console.
        max_bytes:
            Maximum size of each log file before rotation.
        backup_count:
            Number of rotated log backups to keep.
        format_style:
            "text" for human-readable logs, "json" for JSON-lines logs.

    Returns:
        Configured logging.Logger.
    """
    log_file = Path(log_file).expanduser().resolve()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    if logger_name is None:
        logger_name = _logger_name_from_path(log_file)

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    _close_existing_handlers(logger)

    formatter = _build_formatter(format_style)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    logger.propagate = False

    return logger


def make_process_log_file(log_file: str | Path) -> Path:
    """Return a per-process log file path.

    Useful for local multiprocessing workers. For example:
        app.log -> app.pid12345.log
    """
    path = Path(log_file).expanduser().resolve()
    return path.with_name(f"{path.stem}.pid{os.getpid()}{path.suffix}")


def log_and_echo(
    logger: logging.Logger,
    message: str,
    *,
    level: int = logging.INFO,
    echo: bool = False,
) -> None:
    """Log a message and optionally print it for CLI users.

    This helper is optional. It establishes the convention:
        - logger = machine/audit record
        - echo = human terminal output
    """
    logger.log(level, message)

    if echo:
        print(message)