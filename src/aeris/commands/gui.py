from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

import aeris.gui


gui_app = typer.Typer(help="Launch the internal AERIS Streamlit GUI.")


@gui_app.callback()
def gui_callback() -> None:
    """GUI command group."""
    pass


@gui_app.command("run")
def gui_run(
    host: str = typer.Option("localhost", "--host", help="Streamlit server host."),
    port: int = typer.Option(8501, "--port", help="Streamlit server port."),
    headless: bool = typer.Option(True, "--headless/--browser", help="Run Streamlit without opening a browser automatically."),
) -> None:
    """
    Launch the AERIS internal operator GUI.

    Install GUI dependencies first:
        pip install -r requirements-gui.txt
    """
    gui_pkg_dir = Path(aeris.gui.__file__).resolve().parent
    app_path = gui_pkg_dir / "app.py"

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.address",
        host,
        "--server.port",
        str(port),
        "--server.headless",
        "true" if headless else "false",
    ]
    try:
        raise typer.Exit(code=subprocess.call(command))
    except FileNotFoundError:
        typer.secho(
            "[AERIS] Streamlit is not installed. Run: pip install -r requirements-gui.txt",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
