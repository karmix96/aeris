"""
Module: logging_utils

Purpose:
    Standardized logger setup for AERIS runs.

Responsibilities:
    - Create logger with rotating file output
    - Optionally mirror logs to console
    - Ensure log file directory exists
    - Apply consistent formatting
    - Reset existing handlers safely (flush + close + remove independently)

Production logic:
    - Repeated setup calls close stale file handlers without leaking descriptors.
    - Default logger names are unique per log file path.
    - Long runs use rotating log files by default.
    - Parallel workers should use separate log files
      (see make_process_log_file).

Caveats:
    - This is process-local logging.
    - Multiple OS processes should not intentionally write to the same log file.
      Use make_process_log_file() in worker processes.
    - Queue-based multi-process logging can be added later for heavy parallelism.
    - In containerized cloud workers, prefer console=False so stderr is not
      duplicated through the container's log capture.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

__all__ = [
    "setup_logger",
    "make_process_log_file",
    "log_and_echo",
    "JsonLineFormatter",
]


class JsonLineFormatter(logging.Formatter):
    """Minimal dependency-free JSON-lines log formatter.

    Emits one JSON object per log record, suitable for cloud log aggregators
    (CloudWatch, Datadog, Loki, etc.).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp_utc": datetime.fromtimestamp(
                record.created,
                tz=UTC,
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
    """Flush, close, and remove all handlers currently attached to logger.

    Each step (flush, close, removeHandler) is executed independently so that a
    failure in one does not leave a closed-but-still-attached handler on the
    logger.
    """
    for handler in list(logger.handlers):
        try:
            handler.flush()
        except Exception:
            pass
        try:
            handler.close()
        except Exception:
            pass
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
            Path to the log file. Use make_process_log_file() if calling from a
            multiprocessing worker, to avoid concurrent writes to the same file.
        logger_name:
            Optional explicit logger name. If omitted, a stable unique name is
            generated from the log file path. Distinct log files always produce
            distinct logger names.
        level:
            Logging level, e.g. logging.INFO, logging.DEBUG, logging.WARNING.
        console:
            Whether to also write logs to stderr/console. Set to False inside
            cloud workers where stderr is already captured by the runtime.
        max_bytes:
            Maximum size of each log file before rotation. Default 50 MiB.
        backup_count:
            Number of rotated log backups to keep. Default 5.
        format_style:
            "text" for human-readable logs, "json" for JSON-lines logs (use
            "json" when logs feed a cloud aggregator).

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

    Pass the returned path to setup_logger() inside the worker process.
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

    Establishes the convention:
        - logger = machine/audit record (persisted in the log file)
        - echo   = human terminal output

    Note: uses print() rather than typer.echo() to keep this module framework-
    neutral. CLI code that needs Typer-specific behavior (colors, --no-color,
    etc.) should not use this helper and instead call typer.echo() directly.
    """
    logger.log(level, message)

    if echo:
        print(message)