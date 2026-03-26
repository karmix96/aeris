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
from aeris.aero.registry import register_solver
from aeris.aero.validation import (
    validate_aero_input,
    validate_aero_result,
)
from aeris.aero.solvers.avl_validation import validate_avl_parser_consistency

AERO_RESULT_SCHEMA_VERSION = "aero_result_v1"

class AVLStrips(AVLBase):
    """
    AVL wrapper that preserves raw files and parses totals + stability, while also
    exposing output file locations.
    """
    
    def _default_keystroke_file_contents(
        self,
        control_input_deg: float | None = None,
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
            value = 0.0 if control_input_deg is None else float(control_input_deg)
            run_file_contents += ["d1", "d1", f"{value}"]

        return run_file_contents
    
    def run(
        self,
        run_command: str | None = None,
        control_input_deg: float | None = None,
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

        self.write_avl(directory / airplane_file)

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
            control_input_deg=control_input_deg
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

        res["_files"] = {
            "working_dir": str(directory),
            "airplane_avl": str(directory / airplane_file),
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


import copy
from contextlib import contextmanager

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

                raw = avl.run(
                    control_input_deg=control_input_deg,
                    totals_filename="output.txt",
                    strip_filename="strips.txt",
                    surface_filename="surfaces.txt",
                    element_filename="elements.txt",
                    stability_filename="stability.txt",
                    save_surface_forces=save_surface_forces,
                    save_element_forces=save_element_forces,
                )

            runtime_sec = time.perf_counter() - start

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

def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    try:
        return float(value)
    except Exception:
        return str(value)

def _write_aero_result_json(result: AeroResult, output_dir: Path) -> Path:
    payload = {
        "schema_version": AERO_RESULT_SCHEMA_VERSION,
        "status": result.status.value,
        "solver_id": result.solver_id,
        "scalars": {
            "cl": result.cl,
            "cd": result.cd,
            "cm": result.cm,
            "l_over_d": result.l_over_d,
            "cy": result.cy,
            "cl_roll": result.cl_roll,
            "cn": result.cn,
            "cd_ind": result.cd_ind,
            "cd_ff": result.cd_ff,
            "span_efficiency": result.span_efficiency,
            "x_np": result.x_np,
        },
        "stability_axis_derivatives": result.stability_axis_derivatives,
        "body_axis_derivatives": result.body_axis_derivatives,
        "derived_metrics": result.derived_metrics,
        "runtime_sec": result.runtime_sec,
        "warnings": result.warnings,
        "artifact_paths": result.artifact_paths,
        "solver_metadata": result.solver_metadata,
        "failure": (
            {
                "status": result.failure.status.value,
                "reason": result.failure.reason,
                "message": result.failure.message,
                "exception_type": result.failure.exception_type,
            }
            if result.failure is not None
            else None
        ),
    }

    out_path = output_dir / "aero_result.json"
    out_path.write_text(json.dumps(_json_safe(payload), indent=2))
    return out_path