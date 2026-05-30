"""
Shared internal helpers for AERIS CLI command modules.

This module exists to eliminate duplication between command files and to
keep each command file focused on parameter parsing and output. Helpers
defined here are not part of the public CLI API (the underscore prefix is
intentional).
"""

from __future__ import annotations

from typing import NoReturn

import typer


def fail_command(command_name: str, exc: Exception) -> NoReturn:
    """Print a uniform error message and exit nonzero.

    Use for runtime/internal failures (e.g. a training job crashed, a dataset
    file is malformed). Do NOT use for parameter-validation errors — raise
    typer.BadParameter for those.

    Always raises typer.Exit; the NoReturn annotation tells static type
    checkers the call does not return.
    """
    typer.secho(
        f"[AERIS] {command_name} failed: {exc}",
        err=True,
        fg=typer.colors.RED,
    )
    raise typer.Exit(code=1)


def parse_csv_list(value: str, option_name: str) -> list[str]:
    """Parse a comma-separated string into a list of non-empty stripped items.

    Raises:
        typer.BadParameter: if the resulting list is empty.
    """
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise typer.BadParameter(
            f"Expected a comma-separated non-empty list for {option_name}."
        )
    return items


def parse_float_list(value: str, option_name: str) -> list[float]:
    """Parse a comma-separated string into a list of floats.

    An empty input returns an empty list (this is intentional — many sweep
    options accept "no values" to mean "use the scalar default"). For
    options that must be non-empty, callers should add an explicit check
    after parsing.

    Raises:
        typer.BadParameter: if any token cannot be parsed as a float.
    """
    text = value.strip()
    if not text:
        return []

    values: list[float] = []
    for raw in text.split(","):
        token = raw.strip()
        if not token:
            continue
        try:
            values.append(float(token))
        except ValueError as exc:
            raise typer.BadParameter(
                f"Invalid float value '{token}' for {option_name}. "
                f"Use comma-separated numeric values, e.g. 0,2,4"
            ) from exc
    return values