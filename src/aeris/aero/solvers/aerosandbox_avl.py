"""
AVL-based aerodynamic solver adapter using AeroSandbox.

This module wraps AVL execution, handles input preparation, solver execution,
output parsing, and conversion into structured AeroResult objects.

It also enforces validation and parser consistency checks to ensure reliability
of aerodynamic outputs for downstream pipelines.
"""

from __future__ import annotations

import copy
import json
import math
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import aerosandbox as asb
import aerosandbox.numpy as asbnp
import pandas as pd
from aerosandbox.aerodynamics.aero_3D.avl import AVL as AVLBase
from aerosandbox.geometry import Wing, WingXSec

from aeris.aero.base import AeroSolver
from aeris.aero.models import AeroFailure, AeroInput, AeroResult, AeroStatus
from aeris.aero.solvers.avl_polar_injection import inject_polar_cdcl
from aeris.aero.registry import register_solver
from aeris.aero.validation import (
    validate_aero_input,
    validate_aero_result,
)
from aeris.aero.solvers.avl_validation import validate_avl_parser_consistency
from aeris.aero.io import AERO_RESULT_SCHEMA_VERSION, _json_safe, _write_aero_result_json


class AVLStrips(AVLBase):
    """
    AVL wrapper that preserves raw files and parses totals + stability, while also
    exposing output file locations.
    """

    def _default_keystroke_file_contents(
        self,
        control_input_deg: float | None = None,
        diff_input_deg: float | None = None,
    ) -> list[str]:
        run_file_contents: list[str] = []

        # Disable graphics
        run_file_contents += [
            "plop",
            "g",
            "",
        ]

        # Enter OPER menu
        run_file_contents += [
            "oper",
        ]

        # Options:
        # - r : use body-axis rotation-rate convention
        # - d : enable derivative output
        # - v : toggle viscous forces option
        run_file_contents += [
            "o",
            "r",
            "d",
            "v",
            "",
        ]

        # Flow / atmosphere parameters
        run_file_contents += [
            "m",
            f"mn {float(self.op_point.mach())}",
            f"v {float(self.op_point.velocity)}",
            f"d {float(self.op_point.atmosphere.density())}",
            "g 9.81",
            "",
        ]

        # Reduced body rates expected by AVL
        p_bar = self.op_point.p * self.airplane.b_ref / (2 * self.op_point.velocity)
        q_bar = self.op_point.q * self.airplane.c_ref / (2 * self.op_point.velocity)
        r_bar = self.op_point.r * self.airplane.b_ref / (2 * self.op_point.velocity)

        run_file_contents += [
            f"a a {float(self.op_point.alpha)}",
            f"b b {float(self.op_point.beta)}",
            f"r r {float(p_bar)}",
            f"p p {float(q_bar)}",
            f"y y {float(r_bar)}",
        ]

        # IMPORTANT:
        # Explicit AVL control command.
        # If controls exist, command the actual value through OPER.
        if _airplane_has_any_control_surface(self.airplane):
            sym_value  = 0.0 if control_input_deg is None else float(control_input_deg)
            diff_value = 0.0 if diff_input_deg    is None else float(diff_input_deg)

            # d1 d1 {sym}  — symmetric (pitch) deflection of first control surface
            run_file_contents += ["d1", "d1", f"{sym_value}"]

            # d2 d2 {diff} — second control surface (antisymmetric elevon for roll).
            # With ControlSurface(symmetric=False) on Wing(symmetric=True), ASB
            # writes gain=+1 for the right half and gain=-1 for the mirrored left half,
            # creating a separate d2 variable. d2 d2 {val} → right down, left up = roll.
            # Only send when diff is requested AND the plane has a second surface.
            if diff_input_deg is not None and diff_value != 0.0:
                run_file_contents += ["d2", "d2", f"{diff_value}"]

        return run_file_contents

    def run(
        self,
        run_command: str | None = None,
        control_input_deg: float | None = None,
        diff_input_deg: float | None = None,
        totals_filename: str = "output.txt",
        strip_filename: str = "strips.txt",
        surface_filename: str = "surfaces.txt",
        element_filename: str = "elements.txt",
        stability_filename: str = "stability.txt",
        save_surface_forces: bool = False,
        save_element_forces: bool = False,
    ) -> dict[str, Any]:
        directory = Path(self.working_directory)
        directory.mkdir(parents=True, exist_ok=True)

        def _rm(path: Path) -> None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass

        airplane_file = "airplane.avl"
        body_filename = "body.txt"
        hinge_filename = "hinge.txt"
        body_derivs_filename = "body_derivs.txt"
        vm_filename = "strip_shear_moment.txt"

        airplane_avl_path = directory / airplane_file
        self.write_avl(airplane_avl_path)

        # Polar bridge: replace zero CDCL placeholders with library polar data
        if hasattr(self, "_cdcl_injector") and callable(self._cdcl_injector):
            try:
                self._cdcl_injector(airplane_avl_path)
            except Exception as _exc:
                import logging as _logging
                _logging.getLogger(__name__).warning(
                    "AVL polar injection failed (continuing with zero CDCL): %s", _exc
                )

        _rm(directory / totals_filename)
        _rm(directory / strip_filename)
        _rm(directory / stability_filename)
        _rm(directory / body_filename)
        _rm(directory / hinge_filename)
        _rm(directory / body_derivs_filename)
        _rm(directory / vm_filename)

        if save_surface_forces:
            _rm(directory / surface_filename)
        if save_element_forces:
            _rm(directory / element_filename)

        keystroke_lines = self._default_keystroke_file_contents(
            control_input_deg=control_input_deg,
            diff_input_deg=diff_input_deg,
        )
        if run_command is not None:
            keystroke_lines.append(run_command)

        keystroke_lines += [
            "x",
            "ft", totals_filename,
        ]

        if save_surface_forces:
            keystroke_lines += ["fn", surface_filename]
        if save_element_forces:
            keystroke_lines += ["fe", element_filename]

        keystroke_lines += [
            "fs", strip_filename,
            "vm", vm_filename,
            "fb", body_filename,
            "hm", hinge_filename,
            "st", stability_filename,
            "sb", body_derivs_filename,
            "cpom",
            "",
            "quit",
        ]

        keystrokes_path = directory / "keystrokes.txt"
        keystrokes_path.write_text("\n".join(keystroke_lines))

        stdout_path = directory / "avl_stdout.txt"
        proc = None

        try:
            with open(stdout_path, "w") as avl_log:
                proc = subprocess.Popen(
                    [self.avl_command, airplane_file],
                    cwd=directory,
                    stdin=subprocess.PIPE,
                    stdout=avl_log,
                    stderr=avl_log,
                    text=True,
                )
                proc.communicate(input="\n".join(keystroke_lines), timeout=self.timeout)
        except subprocess.TimeoutExpired as exc:
            if proc is not None:
                proc.kill()
                proc.communicate()
            raise TimeoutError(
                f"AVL timed out after {self.timeout} s. See log: {stdout_path}"
            ) from exc

        log_text = stdout_path.read_text() if stdout_path.exists() else ""
        avl_text = airplane_avl_path.read_text() if airplane_avl_path.exists() else ""

        if "Strip array overflow" in log_text or "SDUPL: Strip array overflow" in log_text:
            raise RuntimeError(
                "AVL strip array overflow (NSMAX=500). "
                "Reduce mesh/panel resolution or number of sections."
            )

        if "MAKESURF: Array overflow" in log_text:
            raise RuntimeError(
                "AVL surface array overflow. The geometry/view sent to AVL is too dense."
            )

        totals_path = directory / totals_filename
        if not totals_path.exists():
            raise FileNotFoundError(
                f"AVL did not write totals file '{totals_filename}'. "
                f"See {stdout_path} and {keystrokes_path}."
            )

        output_data = totals_path.read_text()
        res = self.parse_unformatted_data_output(
            output_data,
            data_identifier=" =",
            overwrite=False,
        )

        stab_path = directory / stability_filename
        body_derivs_path = directory / body_derivs_filename

        if stab_path.exists():
            res["_stability_file_parsed"] = _parse_stability_file(stab_path)

        if body_derivs_path.exists():
            res["_body_file_parsed"] = _parse_stability_file(body_derivs_path)

        for key_to_lowerize in ["Alpha", "Beta", "Mach"]:
            if key_to_lowerize in res:
                res[key_to_lowerize.lower()] = res.pop(key_to_lowerize)

        for key in list(res.keys()):
            if "tot" in key:
                res[key.replace("tot", "")] = res.pop(key)

        q = self.op_point.dynamic_pressure()
        S = self.airplane.s_ref
        b = self.airplane.b_ref
        c = self.airplane.c_ref

        res["p"] = res.get("pb/2V", 0.0) * (2 * self.op_point.velocity / b)
        res["q"] = res.get("qc/2V", 0.0) * (2 * self.op_point.velocity / c)
        res["r"] = res.get("rb/2V", 0.0) * (2 * self.op_point.velocity / b)

        res["L"] = q * S * res.get("CL", 0.0)
        res["Y"] = q * S * res.get("CY", 0.0)
        res["D"] = q * S * res.get("CD", 0.0)

        res["l_b"] = q * S * b * res.get("Cl", 0.0)
        res["m_b"] = q * S * c * res.get("Cm", 0.0)
        res["n_b"] = q * S * b * res.get("Cn", 0.0)

        # Do not compute derived metrics here from the merged raw dict.
        # Derivative-family-specific metrics are computed later from the
        # explicitly separated parsed derivative families.
        res["Clb Cnr / Clr Cnb"] = asbnp.nan

        res["F_w"] = [-res["D"], res["Y"], -res["L"]]
        res["F_b"] = self.op_point.convert_axes(*res["F_w"], from_axes="wind", to_axes="body")
        res["F_g"] = self.op_point.convert_axes(*res["F_b"], from_axes="body", to_axes="geometry")

        res["M_b"] = [res["l_b"], res["m_b"], res["n_b"]]
        res["M_g"] = self.op_point.convert_axes(*res["M_b"], from_axes="body", to_axes="geometry")
        res["M_w"] = self.op_point.convert_axes(*res["M_b"], from_axes="body", to_axes="wind")

        control_diagnostics = {
            "airplane_has_control_surfaces": _airplane_has_any_control_surface(self.airplane),
            "airplane_avl_has_control_blocks": _avl_text_has_control_blocks(avl_text),
            "keystrokes_has_d1_command": _keystrokes_contain_d1(keystroke_lines),
            "stdout_control_variables": _extract_stdout_control_variable_count(log_text),
        }

        res["_control_diagnostics"] = control_diagnostics
        res["_files"] = {
            "working_dir": str(directory),
            "airplane_avl": str(airplane_avl_path),
            "keystrokes": str(keystrokes_path),
            "stdout": str(stdout_path),
            "totals": str(totals_path),
            "strips": str(directory / strip_filename),
            "stability": str(stab_path),
            "body_derivs": str(body_derivs_path),
            "body_forces": str(directory / body_filename),
            "hinge_moments": str(directory / hinge_filename),
            "strip_shear_moment": str(directory / vm_filename),
            "surfaces": str(directory / surface_filename) if save_surface_forces else None,
            "elements": str(directory / element_filename) if save_element_forces else None,
        }

        return res


def read_avl_strips(filepath: str | Path, alpha_deg: float | None = None) -> pd.DataFrame:
    lines = Path(filepath).read_text().splitlines()
    rows: list[dict[str, Any]] = []
    surface_id = None
    header_cols = None

    for line in lines:
        m = re.search(r"Surface\s*#\s*(\d+)", line, re.IGNORECASE)
        if m:
            surface_id = int(m.group(1))
            header_cols = None
            continue

        if ("Strip" in line or re.search(r"\bj\b", line)) and "Chord" in line:
            header_cols = re.findall(r"[A-Za-z0-9'_/.-]+", line)
            continue

        if header_cols and re.match(r"\s*\d+\s", line):
            tokens = re.findall(r"[A-Za-z0-9'_/.-]+", line)
            if len(tokens) >= len(header_cols):
                row = dict(zip(header_cols, tokens[:len(header_cols)]))
                row["surface"] = surface_id
                rows.append(row)

    if not rows:
        raise ValueError(f"No strip data found in {filepath}")

    df = pd.DataFrame(rows)
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    rename_map = {
        "Strip": "strip",
        "j": "strip",
        "Xle": "x_le",
        "Yle": "y_le",
        "Zle": "z_le",
        "Chord": "chord",
        "Area": "area",
        "ai": "alpha_induced",
        "cl": "cl_local",
        "cd": "cd_local",
        "cm_c/4": "cm_c4",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "strip" in df.columns:
        df["strip"] = pd.to_numeric(df["strip"], errors="coerce").astype("Int64")

    if alpha_deg is not None:
        df["alpha_deg"] = float(alpha_deg)

    return df


def configure_avl_paneling(airplane: asb.Airplane, panel_cfg: dict[str, Any] | None = None) -> None:
    panel_cfg = panel_cfg or {}

    span_spacing = panel_cfg.get("spanwise_spacing", "equal")
    chord_spacing = panel_cfg.get("chordwise_spacing", "cosine")
    span_res = int(panel_cfg.get("spanwise_resolution", 4))
    chord_res = int(panel_cfg.get("chordwise_resolution", 8))

    if span_res <= 0 or chord_res <= 0:
        raise ValueError("AVL panel resolutions must be positive integers.")

    AVLBase.default_analysis_specific_options[Wing]["wing_level_spanwise_spacing"] = False
    AVLBase.default_analysis_specific_options[WingXSec]["spanwise_spacing"] = span_spacing
    AVLBase.default_analysis_specific_options[WingXSec]["spanwise_resolution"] = span_res
    AVLBase.default_analysis_specific_options[Wing]["chordwise_spacing"] = chord_spacing
    AVLBase.default_analysis_specific_options[Wing]["chordwise_resolution"] = chord_res


@contextmanager
def avl_paneling_context(airplane, panel_cfg: dict[str, Any] | None = None):
    original = AVLBase.default_analysis_specific_options
    snapshot = copy.deepcopy(original)

    try:
        configure_avl_paneling(airplane, panel_cfg=panel_cfg)
        yield
    finally:
        original.clear()
        original.update(snapshot)


def _resolve_avl_command(explicit_command: str | None) -> str:
    if explicit_command:
        return explicit_command
    found = shutil.which("avl")
    if found:
        return found
    raise FileNotFoundError(
        "AVL executable not found. Set settings.avl_command or make 'avl' available on PATH."
    )


def _validate_solver_airplane(airplane: Any) -> list[str]:
    errors: list[str] = []
    if airplane is None:
        return ["geometry.airplane is None"]

    s_ref = _to_float_or_none(getattr(airplane, "s_ref", None))
    b_ref = _to_float_or_none(getattr(airplane, "b_ref", None))
    c_ref = _to_float_or_none(getattr(airplane, "c_ref", None))

    if s_ref is None or s_ref <= 0.0:
        errors.append(f"Invalid airplane.s_ref={getattr(airplane, 's_ref', None)}")
    if b_ref is None or b_ref <= 0.0:
        errors.append(f"Invalid airplane.b_ref={getattr(airplane, 'b_ref', None)}")
    if c_ref is None or c_ref <= 0.0:
        errors.append(f"Invalid airplane.c_ref={getattr(airplane, 'c_ref', None)}")

    wings = getattr(airplane, "wings", None)
    if not wings:
        errors.append("Airplane has no wings")
    return errors


def _airplane_has_any_control_surface(airplane: asb.Airplane) -> bool:
    for wing in getattr(airplane, "wings", []) or []:
        for xsec in getattr(wing, "xsecs", []) or []:
            control_surfaces = getattr(xsec, "control_surfaces", None)
            if control_surfaces and len(control_surfaces) > 0:
                return True
    return False


def _geometry_view_declares_control_surfaces(geometry_view: Any) -> bool:
    value = getattr(geometry_view, "has_control_surfaces", None)
    if value is not None:
        return bool(value)

    metadata = getattr(geometry_view, "metadata", {}) or {}
    return bool(metadata.get("has_control_surfaces", False))


def _geometry_view_control_surface_names(geometry_view: Any) -> tuple[str, ...]:
    names = getattr(geometry_view, "control_surface_names", None)
    if names:
        return tuple(str(name) for name in names)

    metadata = getattr(geometry_view, "metadata", {}) or {}
    names = metadata.get("control_surface_names", []) or []
    return tuple(str(name) for name in names if str(name).strip())


def _resolve_control_input_deg(settings) -> float | None:
    """
    Resolve explicit AVL control input command from solver settings.

    Semantics
    ---------
    - None  -> do not send any d1 command
    - float -> send d1 / d1 / <value>

    We do not rely on AeroSandbox's AVL exporter to serialize the actual
    commanded control deflection magnitude into the CONTROL gain.
    """
    value = settings.solver_options.get("control_input_deg", None)
    if value is None:
        return None
    return float(value)


def _mach_consistency_warning(fc) -> str | None:
    """
    In the current AERIS aero pipeline, Mach is treated as metadata/check information.

    The AVL operating point is driven primarily by:
    - velocity
    - altitude -> atmosphere
    - alpha/beta/rates

    If provided Mach disagrees materially with velocity/altitude-derived Mach,
    emit a warning rather than pretending both are authoritative.
    """
    if fc.mach is None:
        return None

    try:
        atmosphere = asb.Atmosphere(altitude=fc.altitude_m)
        expected = float(fc.velocity_mps) / float(atmosphere.speed_of_sound())
    except Exception:
        return None

    if abs(float(fc.mach) - expected) > 0.02:
        return (
            f"Mach/velocity inconsistency: input mach={fc.mach:.5f}, "
            f"derived mach={expected:.5f} from velocity/altitude. "
            "Current AERIS semantics treat Mach as metadata/QC, while AVL run "
            "is driven by velocity and atmosphere."
        )
    return None


def _extract_stdout_control_variable_count(log_text: str) -> int | None:
    match = re.search(r"^\s*(\d+)\s+Control variables\b", log_text, flags=re.MULTILINE)
    if not match:
        return None
    return int(match.group(1))


def _avl_text_has_control_blocks(avl_text: str) -> bool:
    return bool(re.search(r"^\s*CONTROL\s*$", avl_text, flags=re.MULTILINE))


def _keystrokes_contain_d1(lines: list[str]) -> bool:
    return any(str(line).strip().lower() == "d1" for line in lines)


@register_solver
class AeroSandboxAVLSolver(AeroSolver):
    solver_id = "aerosandbox_avl"

    def run_case(self, aero_input: AeroInput, output_dir: Path) -> AeroResult:
        input_errors = validate_aero_input(aero_input)
        airplane = aero_input.geometry.airplane

        input_errors.extend(_validate_solver_airplane(airplane))
        if input_errors:
            return AeroResult(
                status=AeroStatus.INVALID_INPUT,
                solver_id=self.solver_id,
                failure=AeroFailure(
                    status=AeroStatus.INVALID_INPUT,
                    reason="input_validation_failed",
                    message="; ".join(input_errors),
                ),
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        fc = aero_input.flight_condition
        settings = aero_input.settings

        panel_cfg = settings.solver_options.get("paneling", {})
        save_surface_forces = bool(settings.solver_options.get("save_surface_forces", False))
        save_element_forces = bool(settings.solver_options.get("save_element_forces", False))
        control_input_deg = _resolve_control_input_deg(settings)
        avl_command = _resolve_avl_command(settings.avl_command)

        geometry_declares_controls = _geometry_view_declares_control_surfaces(aero_input.geometry)
        geometry_control_names = _geometry_view_control_surface_names(aero_input.geometry)
        airplane_has_controls = _airplane_has_any_control_surface(airplane)
        requested_control_actuation = control_input_deg is not None

        if requested_control_actuation and not geometry_declares_controls:
            return AeroResult(
                status=AeroStatus.INVALID_INPUT,
                solver_id=self.solver_id,
                failure=AeroFailure(
                    status=AeroStatus.INVALID_INPUT,
                    reason="control_input_requested_but_geometry_has_no_control_surfaces",
                    message=(
                        "control_input_deg was provided, but AeroGeometryView declares no "
                        "control surfaces. Refusing silent no-op actuation."
                    ),
                ),
                solver_metadata={
                    "control_input_deg": control_input_deg,
                    "geometry_declares_controls": geometry_declares_controls,
                    "airplane_has_controls": airplane_has_controls,
                    "geometry_control_surface_names": list(geometry_control_names),
                    "geometry_view_id": aero_input.geometry.view_id,
                    "source_generator": aero_input.geometry.source_generator,
                    "source_geometry_id": aero_input.geometry.source_geometry_id,
                },
            )

        if geometry_declares_controls and not airplane_has_controls:
            return AeroResult(
                status=AeroStatus.INVALID_INPUT,
                solver_id=self.solver_id,
                failure=AeroFailure(
                    status=AeroStatus.INVALID_INPUT,
                    reason="geometry_control_surface_mismatch",
                    message=(
                        "AeroGeometryView declares control surfaces, but the airplane object "
                        "passed to the solver contains none. Refusing inconsistent geometry."
                    ),
                ),
                solver_metadata={
                    "control_input_deg": control_input_deg,
                    "geometry_declares_controls": geometry_declares_controls,
                    "airplane_has_controls": airplane_has_controls,
                    "geometry_control_surface_names": list(geometry_control_names),
                    "geometry_view_id": aero_input.geometry.view_id,
                    "source_generator": aero_input.geometry.source_generator,
                    "source_geometry_id": aero_input.geometry.source_geometry_id,
                },
            )

        op_point = asb.OperatingPoint(
            atmosphere=asb.Atmosphere(altitude=fc.altitude_m),
            velocity=fc.velocity_mps,
            alpha=fc.alpha_deg,
            beta=fc.beta_deg,
            p=fc.p_rad_s,
            q=fc.q_rad_s,
            r=fc.r_rad_s,
        )

        start = time.perf_counter()

        try:
            with avl_paneling_context(airplane, panel_cfg=panel_cfg):
                avl = AVLStrips(
                    airplane=airplane,
                    op_point=op_point,
                    working_directory=str(output_dir),
                    avl_command=avl_command,
                    verbose=settings.verbose,
                    timeout=settings.timeout_sec,
                )

                # Optional polar bridge: wire up CDCL injector when both
                # section_map and polar_store are provided via solver_options.
                _section_map = settings.solver_options.get("section_map")
                _polar_store = settings.solver_options.get("polar_store")
                if _section_map is not None and _polar_store is not None:
                    _V = fc.velocity_mps
                    _mach = fc.mach
                    _alt = fc.altitude_m
                    avl._cdcl_injector = lambda _p: inject_polar_cdcl(
                        _p, _section_map, _polar_store, _V, _mach, _alt
                    )

                raw = avl.run(
                    control_input_deg=control_input_deg,
                    diff_input_deg=settings.solver_options.get("diff_input_deg"),
                    totals_filename="output.txt",
                    strip_filename="strips.txt",
                    surface_filename="surfaces.txt",
                    element_filename="elements.txt",
                    stability_filename="stability.txt",
                    save_surface_forces=save_surface_forces,
                    save_element_forces=save_element_forces,
                )

            runtime_sec = time.perf_counter() - start

            control_diagnostics = raw.get("_control_diagnostics", {}) or {}
            avl_has_control_blocks = bool(control_diagnostics.get("airplane_avl_has_control_blocks", False))
            keystrokes_has_d1 = bool(control_diagnostics.get("keystrokes_has_d1_command", False))
            stdout_control_variables = control_diagnostics.get("stdout_control_variables", None)

            if requested_control_actuation:
                control_failures: list[str] = []

                if not avl_has_control_blocks:
                    control_failures.append("exported AVL file contains no CONTROL blocks")
                if not keystrokes_has_d1:
                    control_failures.append("keystrokes contain no d1 command")
                if stdout_control_variables is None:
                    control_failures.append("AVL stdout did not report control-variable count")
                elif int(stdout_control_variables) <= 0:
                    control_failures.append("AVL reported 0 control variables")

                if control_failures:
                    return AeroResult(
                        status=AeroStatus.INVALID_OUTPUT,
                        solver_id=self.solver_id,
                        runtime_sec=runtime_sec,
                        failure=AeroFailure(
                            status=AeroStatus.INVALID_OUTPUT,
                            reason="control_actuation_unavailable",
                            message="; ".join(control_failures),
                        ),
                        artifact_paths={k: v for k, v in raw.get("_files", {}).items()},
                        solver_metadata={
                            "avl_command": avl_command,
                            "timeout_sec": settings.timeout_sec,
                            "paneling": panel_cfg,
                            "save_surface_forces": save_surface_forces,
                            "save_element_forces": save_element_forces,
                            "control_input_deg": control_input_deg,
                            "geometry_declares_controls": geometry_declares_controls,
                            "airplane_has_controls": airplane_has_controls,
                            "geometry_control_surface_names": list(geometry_control_names),
                            "control_diagnostics": control_diagnostics,
                            "geometry_view_id": aero_input.geometry.view_id,
                            "source_generator": aero_input.geometry.source_generator,
                            "source_geometry_id": aero_input.geometry.source_geometry_id,
                        },
                    )

            cl = _to_float_or_none(raw.get("CL"))
            cd = _to_float_or_none(raw.get("CD"))
            cm = _to_float_or_none(raw.get("Cm"))

            cy = _to_float_or_none(raw.get("CY"))
            cl_roll = _to_float_or_none(raw.get("Cl"))
            cn = _to_float_or_none(raw.get("Cn"))

            cd_ind = _to_float_or_none(raw.get("CDind"))
            cd_ff = _to_float_or_none(raw.get("CDff"))
            span_efficiency = _to_float_or_none(raw.get("e"))

            stability_axis_derivatives = _extract_stability_axis_derivatives(raw)
            body_axis_derivatives = _extract_body_axis_derivatives(raw)
            derived_metrics = _compute_derived_metrics(stability_axis_derivatives)

            x_np = _to_float_or_none(stability_axis_derivatives.get("Xnp"))

            l_over_d = None
            if cd is not None and math.isfinite(cd) and cd != 0 and cl is not None:
                l_over_d = cl / cd

            result = AeroResult(
                status=AeroStatus.SUCCESS,
                solver_id=self.solver_id,
                cl=cl,
                cd=cd,
                cm=cm,
                l_over_d=l_over_d,
                cy=cy,
                cl_roll=cl_roll,
                cn=cn,
                cd_ind=cd_ind,
                cd_ff=cd_ff,
                span_efficiency=span_efficiency,
                x_np=x_np,
                stability_axis_derivatives=stability_axis_derivatives,
                body_axis_derivatives=body_axis_derivatives,
                derived_metrics=derived_metrics,
                runtime_sec=runtime_sec,
                artifact_paths={k: v for k, v in raw.get("_files", {}).items()},
                raw_outputs={k: _json_safe(v) for k, v in raw.items() if k != "_files"},
                solver_metadata={
                    "avl_command": avl_command,
                    "timeout_sec": settings.timeout_sec,
                    "paneling": panel_cfg,
                    "save_surface_forces": save_surface_forces,
                    "save_element_forces": save_element_forces,
                    "control_input_deg": control_input_deg,
                    "geometry_declares_controls": geometry_declares_controls,
                    "airplane_has_controls": airplane_has_controls,
                    "geometry_control_surface_names": list(geometry_control_names),
                    "control_diagnostics": control_diagnostics,
                    "flight_condition": {
                        "alpha_deg": fc.alpha_deg,
                        "beta_deg": fc.beta_deg,
                        "mach": fc.mach,
                        "velocity_mps": fc.velocity_mps,
                        "altitude_m": fc.altitude_m,
                        "p_rad_s": fc.p_rad_s,
                        "q_rad_s": fc.q_rad_s,
                        "r_rad_s": fc.r_rad_s,
                    },
                    "geometry_view_id": aero_input.geometry.view_id,
                    "source_generator": aero_input.geometry.source_generator,
                    "source_geometry_id": aero_input.geometry.source_geometry_id,
                },
            )

            mach_warning = _mach_consistency_warning(fc)
            if mach_warning:
                result.warnings.append(mach_warning)

            result_errors = validate_aero_result(result)
            parser_qc_errors = validate_avl_parser_consistency(result)

            if parser_qc_errors:
                result.warnings.extend([f"PARSER_QC: {msg}" for msg in parser_qc_errors])

            all_errors = list(result_errors)
            all_errors.extend(parser_qc_errors)

            if all_errors:
                result.status = AeroStatus.INVALID_OUTPUT
                result.failure = AeroFailure(
                    status=AeroStatus.INVALID_OUTPUT,
                    reason="output_validation_failed",
                    message="; ".join(all_errors),
                )

            strips_path = result.artifact_paths.get("strips")
            if strips_path and Path(strips_path).exists():
                try:
                    strips_df = read_avl_strips(strips_path, alpha_deg=fc.alpha_deg)
                    strips_df.to_csv(output_dir / "strips_parsed.csv", index=False)
                    result.artifact_paths["strips_parsed"] = str(output_dir / "strips_parsed.csv")

                    # Polar bridge: compute profile drag from strip polars when
                    # both section_map and polar_store are present.
                    __section_map = settings.solver_options.get("section_map")
                    __polar_store = settings.solver_options.get("polar_store")
                    if __section_map is not None and __polar_store is not None:
                        cd_prof, n_extrap = _compute_strip_profile_drag(
                            strips_df=strips_df,
                            section_map=__section_map,
                            polar_store=__polar_store,
                            s_ref=float(airplane.s_ref),
                            velocity_mps=fc.velocity_mps,
                            mach=fc.mach,
                            altitude_m=fc.altitude_m,
                        )
                        if cd_prof is not None:
                            result.cd_profile = cd_prof
                            cd_ind_val = result.cd_ind or 0.0
                            result.cd_total = cd_ind_val + cd_prof
                            if result.cl is not None and result.cd_total > 0:
                                result.l_over_d_viscous = result.cl / result.cd_total
                            # Store extrapolation count for downstream QC
                            result.solver_metadata["profile_drag_n_extrapolated_strips"] = n_extrap
                            if n_extrap > 0:
                                result.warnings.append(
                                    f"POLAR_BRIDGE: {n_extrap} strip(s) had cl outside 2D polar "
                                    "range — profile drag clamped at polar boundary (unreliable)."
                                )
                            # Cross-check: strip-integration vs AVL CDtot (should agree ±15%)
                            # AVL CDtot now includes CDCL profile drag from injection.
                            # Strip integration (cd_total) is the authoritative estimate.
                            # A large divergence indicates a polar fitting or symmetry issue.
                            avl_cdtot = result.cd  # CDtot as reported by AVL
                            if avl_cdtot is not None and avl_cdtot > 0 and result.cd_total > 0:
                                rel_diff = abs(result.cd_total - avl_cdtot) / result.cd_total
                                result.solver_metadata["profile_drag_cd_total_vs_avl_cdtot_rel_diff"] = rel_diff
                                if rel_diff > 0.15:
                                    result.warnings.append(
                                        f"POLAR_BRIDGE: cd_total (strip-integration) = "
                                        f"{result.cd_total:.5f} vs AVL CDtot = {avl_cdtot:.5f} "
                                        f"({rel_diff:.1%} disagreement). "
                                        "Check CDCL fit quality and polar coverage."
                                    )

                except Exception as exc:
                    result.warnings.append(f"Strip parsing failed: {exc}")

            result.artifact_paths["aero_result_json"] = str(output_dir / "aero_result.json")
            _write_aero_result_json(result, output_dir)
            return result

        except Exception as exc:
            runtime_sec = time.perf_counter() - start
            result = AeroResult(
                status=AeroStatus.SOLVER_FAILED,
                solver_id=self.solver_id,
                runtime_sec=runtime_sec,
                failure=AeroFailure(
                    status=AeroStatus.SOLVER_FAILED,
                    reason="solver_exception",
                    message=str(exc),
                    exception_type=type(exc).__name__,
                ),
                solver_metadata={
                    "avl_command": avl_command,
                    "timeout_sec": settings.timeout_sec,
                    "geometry_view_id": aero_input.geometry.view_id,
                },
            )
            try:
                result.artifact_paths["aero_result_json"] = str(output_dir / "aero_result.json")
                _write_aero_result_json(result, output_dir)
            except Exception:
                pass
            return result


def _parse_stability_file(stab_path: Path) -> dict[str, float]:
    text = stab_path.read_text()
    out: dict[str, float] = {}

    # Standard single-token key = value pairs
    pattern = re.compile(r"([A-Za-z][A-Za-z0-9'/_\.-]*)\s*=\s*([-+0-9.Ee]+)")

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Handle composite metric explicitly so it doesn't overwrite Cnb
        if "Clb Cnr / Clr Cnb" in stripped and "=" in stripped:
            lhs, rhs = stripped.split("=", 1)
            metric_key = lhs.strip()
            try:
                metric_val = float(rhs.strip().split()[0])
                out[metric_key] = metric_val
            except Exception:
                pass
            continue

        for match in pattern.finditer(line):
            raw_key = match.group(1).strip()
            raw_val = match.group(2).strip()

            try:
                val = float(raw_val)
            except Exception:
                continue

            # Keep first occurrence; don't overwrite already parsed derivatives
            if raw_key not in out:
                out[raw_key] = val

            normalized = _normalize_stability_key(raw_key)
            if normalized is not None and normalized not in out:
                out[normalized] = val

    return out


def _normalize_stability_key(key: str) -> str | None:
    k = key.strip()

    alias_map = {
        "CL_a": "CLa",
        "Cm_a": "Cma",
        "CY_b": "CYb",
        "Cl_b": "Clb",
        "Cn_b": "Cnb",
        "Cl_p": "Clp",
        "Cm_q": "Cmq",
        "Cn_r": "Cnr",
        "Cl_r": "Clr",
        "Cn_p": "Cnp",
        "CLu": "CLu",
        "Cmu": "Cmu",
        "CYp": "CYp",
        "CYr": "CYr",
    }
    if k in alias_map:
        return alias_map[k]

    compressed = re.sub(r"[^A-Za-z0-9]", "", k)

    canonical_targets = {
        "CLa", "Cma", "CYb", "Clb", "Cnb",
        "Clp", "Cmq", "Cnr", "Clr", "Cnp",
        "CLu", "Cmu", "CYp", "CYr",
    }
    if compressed in canonical_targets:
        return compressed

    return None


def _to_float_or_none(value: Any) -> float | None:
    try:
        val = float(value)
        if not math.isfinite(val):
            return None
        return val
    except Exception:
        return None


def _extract_stability_axis_derivatives(raw: dict[str, Any]) -> dict[str, float | None]:
    parsed = raw.get("_stability_file_parsed", {}) or {}

    derivative_keys = [
        # Stability-axis static derivatives
        "CLa", "CLb",
        "CYa", "CYb",
        "Cla", "Clb",
        "Cma", "Cmb",
        "Cna", "Cnb",

        # Stability-axis rate derivatives
        "CLp", "CLq", "CLr",
        "CYp", "CYq", "CYr",
        "Clp", "Clq", "Clr",
        "Cmp", "Cmq", "Cmr",
        "Cnp", "Cnq", "Cnr",

        # Common scalar printed in stability file
        "Xnp",
    ]

    return {
        key: _to_float_or_none(parsed.get(key))
        for key in derivative_keys
    }


def _extract_body_axis_derivatives(raw: dict[str, Any]) -> dict[str, float | None]:
    parsed = raw.get("_body_file_parsed", {}) or {}

    derivative_keys = [
        "CXu", "CXv", "CXw",
        "CYu", "CYv", "CYw",
        "CZu", "CZv", "CZw",
        "Clu", "Clv", "Clw",
        "Cmu", "Cmv", "Cmw",
        "Cnu", "Cnv", "Cnw",
    ]

    return {
        key: _to_float_or_none(parsed.get(key))
        for key in derivative_keys
    }


def _compute_strip_profile_drag(
    strips_df: pd.DataFrame,
    section_map,
    polar_store,
    s_ref: float,
    velocity_mps: float,
    mach: float,
    altitude_m: float,
) -> tuple[float, int] | tuple[None, int]:
    """Integrate section profile drag over the semi-span from AVL strip data.

    Uses AVL's own strip panel areas (chord × Δy per strip) — exact to the
    same discretisation AVL used for the VLM solution.

    Symmetry: for symmetric wings AVL writes strips for both halves in
    strips.txt (y < 0 and y ≥ 0).  When both sides are present the summation
    covers only y ≥ 0 strips and the result is multiplied by 2.  When only
    one side is present (e.g., a half-wing model) no doubling is applied.

    Returns:
        (cd_profile, n_extrapolated_strips)
        cd_profile = None if required columns are absent or data is empty.
        n_extrapolated_strips counts strips whose local cl fell outside the
        2D polar's covered cl range — those cd values are clamped (np.interp
        boundary) and should be treated as unreliable.
    """
    from aeris.aero.solvers.avl_polar_injection import _kinematic_viscosity

    needed = {"y_le", "chord", "area", "cl_local"}
    if not needed.issubset(strips_df.columns):
        return None, 0
    if len(strips_df) < 2:
        return None, 0

    nu = _kinematic_viscosity(altitude_m)

    # Detect symmetry: check if strips.txt contains both semi-wings.
    y_vals = strips_df["y_le"].dropna().to_numpy(float)
    has_both_sides = bool((y_vals < -1e-6).any() and (y_vals > 1e-6).any())
    symmetry_factor = 2.0 if has_both_sides else 1.0

    # Work on the positive (or only) half.
    df = strips_df[strips_df["y_le"] >= -1e-9].copy()
    if df.empty:
        return None, 0

    df = df.sort_values("y_le").reset_index(drop=True)
    y_arr = df["y_le"].to_numpy(float)
    chord_arr = df["chord"].to_numpy(float)
    area_arr = df["area"].to_numpy(float)
    cl_arr = df["cl_local"].to_numpy(float)

    cd_prof_sum = 0.0
    n_extrapolated = 0
    for idx in range(len(df)):
        y_m = float(y_arr[idx])
        chord = float(chord_arr[idx])
        strip_area = float(area_arr[idx])
        cl = float(cl_arr[idx])
        re = velocity_mps * chord / nu if nu > 0 else 1e6

        airfoil_id = section_map.get_airfoil_id(y_m)
        if airfoil_id is None:
            continue

        # Track cl out-of-envelope before querying (np.interp clamps silently)
        cl_bounds = polar_store.get_cl_bounds(airfoil_id, re=re, mach=mach)
        if cl_bounds is not None:
            cl_min, cl_max = cl_bounds
            if cl < cl_min or cl > cl_max:
                n_extrapolated += 1

        cd_2d = polar_store.query_cd(airfoil_id, cl=cl, re=re, mach=mach)
        if cd_2d is None:
            continue

        # Use AVL's strip area (= chord × Δy) — no reconstruction needed.
        cd_prof_sum += cd_2d * strip_area

    if s_ref <= 0:
        return None, n_extrapolated

    cd_profile = symmetry_factor * cd_prof_sum / s_ref
    return cd_profile, n_extrapolated


def _compute_derived_metrics(
    stability_axis_derivatives: dict[str, float | None],
) -> dict[str, float | None]:
    clb = stability_axis_derivatives.get("Clb")
    cnr = stability_axis_derivatives.get("Cnr")
    clr = stability_axis_derivatives.get("Clr")
    cnb = stability_axis_derivatives.get("Cnb")

    spiral_metric: float | None = None
    try:
        if None not in (clb, cnr, clr, cnb) and clr != 0.0 and cnb != 0.0:
            spiral_metric = float((clb * cnr) / (clr * cnb))
    except Exception:
        spiral_metric = None

    return {
        "spiral_metric": spiral_metric,
    }