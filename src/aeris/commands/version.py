from importlib.metadata import PackageNotFoundError, version as get_version

import typer


def register(app: typer.Typer) -> None:
    @app.command("version")
    def show_version() -> None:
        """Show the installed Aeris version."""
        try:
            pkg_version = get_version("aeris")
        except PackageNotFoundError:
            pkg_version = "unknown"

        typer.echo(f"aeris {pkg_version}")
