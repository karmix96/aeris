"""Project-local AVL runner for the standalone pyGeo study.

Every case uses a new, initially empty directory.  This prevents the upstream
runner's stale-output cleanup from deleting or replacing prior study results.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aeris.aero.solvers.aerosandbox_avl import (
    AVLStrips,
    _compute_strip_profile_drag,
    avl_paneling_context,
    read_avl_strips,
)
from aeris.aero.solvers.avl_polar_injection import inject_polar_cdcl

class StudyAVLStrips(AVLStrips):
    """Keep AVL's default profile-drag switch enabled."""

    def _default_keystroke_file_contents(
        self,
        control_input_deg: float | None = None,
        diff_input_deg: float | None = None,
    ) -> list[str]:
        lines = super()._default_keystroke_file_contents(
            control_input_deg=control_input_deg,
            diff_input_deg=diff_input_deg,
        )
        for i in range(len(lines) - 4):
            if lines[i : i + 5] == ["o", "r", "d", "v", ""]:
                return lines[: i + 3] + lines[i + 4 :]
        raise RuntimeError(
            "Unexpected AVL keystroke layout; could not preserve viscous mode"
        )



@dataclass
class AVLCaseResult:
    case_name: str
    alpha_deg: float
    velocity_mps: float
    altitude_m: float
    mach: float
    cl: float
    cd_avl: float
    cd_induced: float
    cm: float
    span_efficiency: float
    cd_profile_integrated: float | None
    cd_corrected: float | None
    l_over_d_avl: float | None
    l_over_d_corrected: float | None
    n_cdcl_injected: int
    n_surface_zero_cdcl_removed: int
    n_profile_extrapolated_strips: int
    runtime_sec: float
    workdir: Path
    strips: pd.DataFrame
    raw: dict[str, Any]

    def as_row(self) -> dict[str, float | int | str | None]:
        return {
            "case_name": self.case_name,
            "alpha_deg": self.alpha_deg,
            "velocity_mps": self.velocity_mps,
            "altitude_m": self.altitude_m,
            "mach": self.mach,
            "CL": self.cl,
            "CD_avl": self.cd_avl,
            "CD_induced": self.cd_induced,
            "Cm": self.cm,
            "span_efficiency": self.span_efficiency,
            "CD_profile_integrated": self.cd_profile_integrated,
            "CD_corrected": self.cd_corrected,
            "L_over_D_avl": self.l_over_d_avl,
            "L_over_D_corrected": self.l_over_d_corrected,
            "n_cdcl_injected": self.n_cdcl_injected,
            "n_surface_zero_cdcl_removed": self.n_surface_zero_cdcl_removed,
            "n_profile_extrapolated_strips": self.n_profile_extrapolated_strips,
            "runtime_sec": self.runtime_sec,
            "workdir": str(self.workdir),
        }


def _finite_float(mapping: dict[str, Any], key: str, default: float = float("nan")) -> float:
    try:
        value = float(mapping.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if np.isfinite(value) else default


def remove_surface_zero_cdcl(path: Path) -> int:
    """Remove the serializer's surface placeholder for a precedence audit."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    i = 0
    in_surface = False
    seen_section = False
    removed = 0
    while i < len(lines):
        token = lines[i].strip().upper()
        if token == "SURFACE":
            in_surface = True
            seen_section = False
        elif token == "SECTION":
            seen_section = True
        if token == "CDCL" and in_surface and not seen_section:
            j = i + 1
            while j < len(lines) and (
                not lines[j].strip()
                or lines[j].lstrip().startswith(("#", "!"))
            ):
                j += 1
            fields = lines[j].split() if j < len(lines) else []
            try:
                is_zero = len(fields) == 6 and all(float(v) == 0.0 for v in fields)
            except ValueError:
                is_zero = False
            if is_zero:
                i = j + 1
                removed += 1
                continue
        output.append(lines[i])
        i += 1
    if removed:
        Path(path).write_text("\n".join(output) + "\n", encoding="utf-8")
    return removed


def run_avl_case(
    airplane,
    *,
    case_name: str,
    workdir: Path,
    alpha_deg: float,
    velocity_mps: float,
    altitude_m: float = 0.0,
    beta_deg: float = 0.0,
    paneling: dict[str, Any] | None = None,
    section_map=None,
    polar_source=None,
    inject_cdcl: bool = True,
    remove_surface_placeholder: bool = False,
    preserve_viscous_mode: bool = True,
    control_input_deg: float | None = None,
    timeout_sec: float = 20.0,
    avl_command: str | None = None,
) -> AVLCaseResult:
    """Run one isolated AVL case and retain all raw files."""
    import aerosandbox as asb

    # AeroSandbox writes companion AFILE paths using the path supplied here.
    # An absolute path prevents resolving a relative workdir twice after chdir.
    directory = Path(workdir).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(
            f"Refusing to overwrite non-empty AVL case directory: {directory}"
        )
    directory.mkdir(parents=True, exist_ok=True)

    executable = avl_command or shutil.which("avl")
    if executable is None:
        raise FileNotFoundError("AVL executable was not found on PATH")
    atmosphere = asb.Atmosphere(altitude=float(altitude_m))
    mach = float(velocity_mps) / float(atmosphere.speed_of_sound())
    op_point = asb.OperatingPoint(
        atmosphere=atmosphere,
        velocity=float(velocity_mps),
        alpha=float(alpha_deg),
        beta=float(beta_deg),
    )

    injected_count = 0
    surface_placeholders_removed = 0

    def injector(path: Path) -> None:
        nonlocal injected_count, surface_placeholders_removed
        injected_count = inject_polar_cdcl(
            path,
            section_map,
            polar_source,
            float(velocity_mps),
            mach,
            float(altitude_m),
        )

        if injected_count and remove_surface_placeholder:
            surface_placeholders_removed = remove_surface_zero_cdcl(path)
    start = time.perf_counter()
    with avl_paneling_context(airplane, panel_cfg=paneling or {}):
        analysis_type = StudyAVLStrips if preserve_viscous_mode else AVLStrips
        analysis = analysis_type(
            airplane=airplane,
            op_point=op_point,
            working_directory=str(directory),
            avl_command=str(executable),
            verbose=False,
            timeout=float(timeout_sec),
        )
        if (
            inject_cdcl
            and section_map is not None
            and polar_source is not None
        ):
            analysis._cdcl_injector = injector
        raw = analysis.run(
            control_input_deg=control_input_deg,
            totals_filename="output.txt",
            strip_filename="strips.txt",
            stability_filename="stability.txt",
        )
    runtime = time.perf_counter() - start

    strips_path = directory / "strips.txt"
    strips = (
        read_avl_strips(strips_path, alpha_deg=float(alpha_deg))
        if strips_path.is_file()
        else pd.DataFrame()
    )
    if not strips.empty:
        strips.to_csv(directory / "strips_parsed.csv", index=False)

    cd_profile: float | None = None
    n_extrapolated = 0
    if section_map is not None and polar_source is not None and not strips.empty:
        cd_profile, n_extrapolated = _compute_strip_profile_drag(
            strips_df=strips,
            section_map=section_map,
            polar_store=polar_source,
            s_ref=float(airplane.s_ref),
            velocity_mps=float(velocity_mps),
            mach=mach,
            altitude_m=float(altitude_m),
        )

    cl = _finite_float(raw, "CL")
    cd_avl = _finite_float(raw, "CD")
    cd_induced = _finite_float(raw, "CDind", 0.0)
    cm = _finite_float(raw, "Cm")
    efficiency = _finite_float(raw, "e")
    cd_corrected = (
        cd_induced + float(cd_profile)
        if cd_profile is not None and np.isfinite(cd_induced)
        else None
    )
    l_over_d_avl = cl / cd_avl if cd_avl > 0.0 else None
    l_over_d_corrected = (
        cl / cd_corrected if cd_corrected is not None and cd_corrected > 0.0 else None
    )
    return AVLCaseResult(
        case_name=str(case_name),
        alpha_deg=float(alpha_deg),
        velocity_mps=float(velocity_mps),
        altitude_m=float(altitude_m),
        mach=mach,
        cl=cl,
        cd_avl=cd_avl,
        cd_induced=cd_induced,
        cm=cm,
        span_efficiency=efficiency,
        cd_profile_integrated=cd_profile,
        cd_corrected=cd_corrected,
        l_over_d_avl=l_over_d_avl,
        l_over_d_corrected=l_over_d_corrected,
        n_cdcl_injected=injected_count,
        n_profile_extrapolated_strips=int(n_extrapolated),
        n_surface_zero_cdcl_removed=surface_placeholders_removed,
        runtime_sec=runtime,
        workdir=directory,
        strips=strips,
        raw=raw,
    )
