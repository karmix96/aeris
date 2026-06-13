"""
XFOIL subprocess adapter for AERIS 2D.

Communicates with the XFOIL executable via stdin/stdout/polar file.
Works on Ubuntu (xfoil) and Windows (xfoil.exe) — no compilation needed.

Install:
  Ubuntu/Debian: sudo apt-get install xfoil
  Windows:       download xfoil.exe from https://web.mit.edu/drela/Public/web/xfoil/
  Custom path:   export AERIS_XFOIL_BIN=/path/to/xfoil

XFOIL session issued per airfoil × (Re, Mach) condition:
  LOAD <tmp.dat>      load airfoil coordinates
  PANE                repanel (optional, controlled by config)
  OPER                enter operating-point menu
  VISC <Re>           set viscous Re
  MACH <Mach>         set Mach number
  ITER <max_iter>     set Newton iteration limit
  PACC                start polar accumulation
  <tmp_polar.txt>     output file
                      (blank line = no dump file)
  ASEQ a_start a_end a_step   alpha sweep
  PACC                stop polar accumulation
  QUIT
"""
from __future__ import annotations

import math
import os
import platform
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from aeris.aero_2d.models import Aero2DResult

# ── Binary resolution ─────────────────────────────────────────────────────────

def _find_xfoil_binary() -> str:
    """Return the XFOIL executable path, respecting AERIS_XFOIL_BIN env var."""
    env = os.environ.get("AERIS_XFOIL_BIN")
    if env:
        return env
    return "xfoil.exe" if platform.system() == "Windows" else "xfoil"


def _check_xfoil_available() -> None:
    """Raise a clear error if XFOIL binary is not found."""
    import shutil
    binary = _find_xfoil_binary()
    if shutil.which(binary) is None and not Path(binary).is_file():
        system = platform.system()
        if system == "Linux":
            install_hint = "  sudo apt-get install xfoil"
        elif system == "Darwin":
            install_hint = "  brew install xfoil"
        else:
            install_hint = "  Download xfoil.exe from https://web.mit.edu/drela/Public/web/xfoil/"
        raise FileNotFoundError(
            f"[AERIS] XFOIL executable '{binary}' not found.\n"
            f"Install:\n{install_hint}\n"
            f"Or set: export AERIS_XFOIL_BIN=/path/to/xfoil"
        )


# ── Polar file parser ─────────────────────────────────────────────────────────

def _parse_polar_file(polar_path: Path) -> list[dict[str, float]]:
    """Parse XFOIL polar accumulation output file.

    XFOIL polar file format (after two header lines):
      alpha      CL      CD     CDp      CM   Top_Xtr  Bot_Xtr
      ------  ------  ------  ------  ------  -------  -------
       -4.00  -0.4523  0.00751 ...
       ...
    """
    if not polar_path.exists() or polar_path.stat().st_size == 0:
        return []

    rows = []
    header_passed = False
    with polar_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            # The dashes line signals that data rows follow
            if stripped.startswith("------"):
                header_passed = True
                continue
            if not header_passed:
                continue
            # Data line: split and parse
            parts = stripped.split()
            if len(parts) < 5:
                continue
            try:
                rows.append({
                    "alpha": float(parts[0]),
                    "cl":    float(parts[1]),
                    "cd":    float(parts[2]),
                    "cm":    float(parts[4]),   # parts[3]=CDp, parts[4]=CM
                })
            except (ValueError, IndexError):
                continue
    return rows


# ── Core sweep function ───────────────────────────────────────────────────────

def run_alpha_sweep(
    *,
    airfoil_id: str,
    airfoil_name: str,
    source_file: str,
    x: np.ndarray,
    y: np.ndarray,
    alpha_start: float,
    alpha_end: float,
    alpha_step: float,
    reynolds: float,
    mach: float = 0.0,
    ncrit: float = 9.0,
    max_iter: int = 100,
    repanel: bool = True,
    model_size: str = "large",  # unused — kept for API compatibility
    show_plots: bool = False,   # True = Xplot11 visible; False = headless via xvfb-run
) -> list[Aero2DResult]:
    """Run one XFOIL alpha sweep for a single (Re, Mach, Ncrit) condition.

    Writes a temporary .dat file and polar file, runs XFOIL via subprocess,
    parses the polar output, and returns one Aero2DResult per converged alpha.

    Unconverged alpha points are NOT present in the polar file — XFOIL simply
    skips them. We reconstruct the full alpha grid and mark missing points as
    converged=False with cl/cd/cm=None.

    show_plots=False (default): runs XFOIL under xvfb-run (virtual display).
    No Xplot11 windows appear. Requires xvfb-run (sudo apt install xvfb).
    show_plots=True: uses the real DISPLAY — Xplot11 windows will appear.
    """
    _check_xfoil_available()
    binary = _find_xfoil_binary()

    with tempfile.TemporaryDirectory(prefix="aeris_xfoil_") as tmpdir:
        tmp = Path(tmpdir)
        dat_path   = tmp / "airfoil.dat"
        polar_path = tmp / "polar.txt"

        # Write coordinate file (Selig format)
        lines = [airfoil_name]
        for xi, yi in zip(x.tolist(), y.tolist()):
            lines.append(f"{xi:.8f}  {yi:.8f}")
        dat_path.write_text("\n".join(lines), encoding="utf-8")

        # Build XFOIL command sequence
        cmds: list[str] = []
        cmds.append(f"LOAD {dat_path}")
        cmds.append("")                     # accept default name
        if repanel:
            cmds.append("PANE")            # repanel for robustness
        # AERIS_PATCH_C14_APPLIED: PLOP→G→(blank) disables Xplot11 graphics.
        # DISPLAY="" env (set below) is a secondary fallback. Both are needed
        # for reliable headless operation on Linux without explicit xvfb-run.
        cmds.append("PLOP")
        cmds.append("G")
        cmds.append("")   # exit PLOP submenu
        cmds.append("OPER")
        cmds.append(f"VISC {reynolds:.0f}")
        cmds.append(f"MACH {mach:.4f}")
        cmds.append(f"ITER {max_iter}")
        cmds.append(f"VPAR")
        cmds.append(f"N {ncrit:.1f}")
        cmds.append("")                     # exit VPAR
        cmds.append("PACC")
        cmds.append(str(polar_path))        # polar output file
        cmds.append("")                     # no dump file
        cmds.append(f"ASEQ {alpha_start:.2f} {alpha_end:.2f} {alpha_step:.2f}")
        cmds.append("PACC")                 # stop accumulation
        cmds.append("")
        cmds.append("QUIT")

        stdin_text = "\n".join(cmds) + "\n"

        try:
            import shutil as _shutil
            if show_plots:
                cmd = [binary]          # real display — Xplot11 windows appear
                run_env = None
            elif _shutil.which("xvfb-run"):
                cmd = ["xvfb-run", "-a", binary]   # headless virtual display
                run_env = None
            else:
                cmd = [binary]          # xvfb-run absent — best effort
                run_env = {**os.environ, "DISPLAY": ""}
            proc = subprocess.run(
                cmd,
                input=stdin_text.encode("utf-8"),
                capture_output=True,
                timeout=120,
                cwd=str(tmp),
                env=run_env,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"XFOIL binary '{binary}' not found. "
                "Install with: sudo apt-get install xfoil"
            ) from exc
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"XFOIL timed out for '{airfoil_name}' "
                f"(Re={reynolds:.0f}). Increase timeout or check airfoil."
            )

        # Parse polar file
        polar_rows = _parse_polar_file(polar_path)

    # Reconstruct full alpha grid
    n_alpha = max(1, round((alpha_end - alpha_start) / alpha_step) + 1)
    alpha_grid = [round(alpha_start + i * alpha_step, 4) for i in range(n_alpha)]

    # Index converged results by alpha (rounded to 2 dp for matching)
    converged_map: dict[float, dict[str, float]] = {}
    for row in polar_rows:
        key = round(row["alpha"], 2)
        converged_map[key] = row

    results: list[Aero2DResult] = []
    for alpha in alpha_grid:
        key = round(alpha, 2)
        row = converged_map.get(key)
        if row is not None:
            cl = float(row["cl"])
            cd = float(row["cd"])
            cm = float(row["cm"])
            # Secondary validity check
            ok = (
                math.isfinite(cl)
                and math.isfinite(cd)
                and math.isfinite(cm)
                and cd > 0.0
            )
        else:
            cl = cd = cm = None
            ok = False

        results.append(Aero2DResult(
            airfoil_id=airfoil_id,
            airfoil_name=airfoil_name,
            source_file=source_file,
            alpha_deg=alpha,
            reynolds=reynolds,
            mach=mach,
            ncrit=ncrit,
            cl=cl if ok else None,
            cd=cd if ok else None,
            cm=cm if ok else None,
            cp_min=None,    # requires separate XFOIL cp output — not implemented yet
            converged=ok,
            solver_id="xfoil_subprocess",
            solver_version=_xfoil_version(binary),
        ))

    return results


def _xfoil_version(binary: str) -> str:
    """Try to extract XFOIL version string from its startup banner."""
    try:
        proc = subprocess.run(
            [binary],
            input=b"QUIT\n",
            capture_output=True,
            timeout=10,
        )
        for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
            if "version" in line.lower() or "xfoil" in line.lower():
                return line.strip()[:60]
    except Exception:
        pass
    return "unknown"
