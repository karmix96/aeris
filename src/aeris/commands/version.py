"""
Version command registration for the AERIS CLI.

Responsibilities:
    - Register the version subcommand
    - Report installed package version metadata

Notes:
    - Keeps version reporting independent from domain command groups
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as get_version

import typer

version_app = typer.Typer(help="Version and installation info.")

@version_app.callback(invoke_without_command=True)
def show_version() -> None:
    """Show the installed AERIS version."""
    try:
        pkg_version = get_version("aeris")
    except PackageNotFoundError:
        pkg_version = "unknown"

    typer.echo(f"aeris {pkg_version}")