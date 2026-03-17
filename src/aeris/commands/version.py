from importlib.metadata import PackageNotFoundError, version as get_version # (The Version Finder)

import typer


def register(app: typer.Typer) -> None:             # This allows this file to modify your main app from the outside.
    @app.command("version")                         # This tells Typer to create a specific action. Because the name is "version", 
                                                    # the user can now type aeris version in their terminal.
                                                    
    def show_version() -> None:
        """Show the installed Aeris version."""
        try:
            pkg_version = get_version("aeris")      # It looks into the folder where your Python packages are installed (like site-packages) 
                                                    # to see what version of "aeris" is recorded there.
        except PackageNotFoundError:
            pkg_version = "unknown"

        typer.echo(f"aeris {pkg_version}")          # While print() works, typer.echo() is better for CLI tools because 
                                                    # it handles different terminal types and colors more reliably.
