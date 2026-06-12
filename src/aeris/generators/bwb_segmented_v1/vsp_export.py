"""OpenVSP / STEP export support for ``bwb_segmented_v1``.

This module is intentionally generator-specific.  It knows how to turn the
AERIS BWB section geometry into an AeroSandbox airplane and then asks
AeroSandbox to emit an OpenVSP script.  Generic orchestration lives in
``aeris.geometry.cad_export``.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from aeris.generators.bwb_segmented_v1.export import (
    export_planform_sections_csv,
    export_section_3d_csv,
)
from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, BWBGeneratorConfig
from aeris.generators.bwb_segmented_v1.planform import (
    PlanformResult,
    generate_bwb_planform_from_sample,
)
from aeris.generators.bwb_segmented_v1.sections import (
    SectionGeometryResult,
    build_section_geometry_from_sample,
)
from aeris.generators.bwb_segmented_v1.validation import (
    validate_planform_result,
    validate_section_geometry,
)


@dataclass(frozen=True)
class BWBCADSource:
    """Deterministic geometry source used by CAD exporters."""

    planform: PlanformResult
    section_geometry: SectionGeometryResult
    artifact_paths: dict[str, str]


@dataclass(frozen=True)
class OpenVSPExecutionResult:
    """Result of an optional OpenVSP batch-script execution."""

    attempted: bool
    command: list[str]
    returncode: int | None
    stdout_path: Path
    stderr_path: Path
    step_path: Path | None
    step_exists: bool
    skipped_reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return bool(self.attempted and self.returncode == 0 and self.step_exists)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "command": self.command,
            "returncode": self.returncode,
            "stdout_path": str(self.stdout_path),
            "stderr_path": str(self.stderr_path),
            "step_path": None if self.step_path is None else str(self.step_path),
            "step_exists": self.step_exists,
            "succeeded": self.succeeded,
            "skipped_reason": self.skipped_reason,
        }


@dataclass(frozen=True)
class CadQuerySTEPExportResult:
    """Result of direct AeroSandbox/CadQuery STEP export."""

    attempted: bool
    backend: str
    stdout_path: Path
    stderr_path: Path
    step_path: Path
    step_exists: bool
    skipped_reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return bool(self.attempted and self.step_exists)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "backend": self.backend,
            "stdout_path": str(self.stdout_path),
            "stderr_path": str(self.stderr_path),
            "step_path": str(self.step_path),
            "step_exists": self.step_exists,
            "succeeded": self.succeeded,
            "skipped_reason": self.skipped_reason,
        }


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_dict"):
        return _jsonable(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict

        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def build_bwb_cad_source(
    *,
    config: BWBGeneratorConfig,
    sample: BWBDesignSample,
    output_dir: Path,
) -> BWBCADSource:
    """Build deterministic BWB section geometry for CAD export.

    This deliberately does not call the high-level geometry service.  CAD export
    only needs validated planform + section geometry, so this path stays small
    and avoids coupling CAD export to plotting, AeroSandbox metadata extraction,
    or normal run-manifest logic.
    """

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    planform = generate_bwb_planform_from_sample(sample, config)
    validate_planform_result(planform)

    section_geometry = build_section_geometry_from_sample(planform, sample, config)
    validate_section_geometry(section_geometry)

    source_dir = output_dir / "source_geometry"
    source_dir.mkdir(parents=True, exist_ok=True)
    planform_sections_path = source_dir / "planform_sections.csv"
    section_3d_path = source_dir / "section_3d.csv"

    export_planform_sections_csv(planform, planform_sections_path)
    export_section_3d_csv(section_geometry, section_3d_path)

    source_summary_path = source_dir / "cad_source_summary.json"
    source_summary = {
        "created_at_utc": _utc_now_iso(),
        "generator_id": "bwb_segmented_v1",
        "geometry_name": config.name,
        "section_count": len(section_geometry.sections),
        "semi_span_m": float(planform.semi_span_m),
        "full_span_m": float(planform.full_span_m),
        "approx_area_m2": float(planform.approx_area_m2),
        "approx_aspect_ratio_planform": float(planform.approx_aspect_ratio),
        "sample": _jsonable(sample),
    }
    source_summary_path.write_text(json.dumps(source_summary, indent=2), encoding="utf-8")

    return BWBCADSource(
        planform=planform,
        section_geometry=section_geometry,
        artifact_paths={
            "source_dir": str(source_dir),
            "planform_sections_csv": str(planform_sections_path),
            "section_3d_csv": str(section_3d_path),
            "cad_source_summary_json": str(source_summary_path),
        },
    )


def _build_aerosandbox_airplane_from_sections(
    *,
    section_geometry: SectionGeometryResult,
    config: BWBGeneratorConfig,
    symmetric: bool = True,
):
    """Build an AeroSandbox airplane from AERIS section records."""

    try:
        import aerosandbox as asb
    except Exception as exc:  # pragma: no cover - depends on operator environment
        raise RuntimeError(
            "AeroSandbox is required to create the OpenVSP vspscript. "
            "Install AERIS dependencies first."
        ) from exc

    wing_xsecs = []
    fallback_airfoil_name = config.section_bounds.airfoil_name or "naca0012"

    for section in section_geometry.sections:
        airfoil_name = section.airfoil_name or fallback_airfoil_name
        try:
            airfoil = asb.Airfoil(airfoil_name)
        except Exception:
            airfoil = asb.Airfoil("naca0012")

        wing_xsecs.append(
            asb.WingXSec(
                xyz_le=[section.x_le_m, section.y_m, section.z_le_m],
                chord=section.chord_m,
                twist=section.twist_deg,
                airfoil=airfoil,
            )
        )

    if len(wing_xsecs) < 2:
        raise ValueError("Need at least 2 BWB sections to export OpenVSP geometry.")

    wing = asb.Wing(name="BWB", symmetric=symmetric, xsecs=wing_xsecs)

    return asb.Airplane(
        name=config.name or "aeris_bwb",
        xyz_ref=[0.0, 0.0, 0.0],
        wings=[wing],
        s_ref=float(wing.area()),
        c_ref=float(wing.mean_aerodynamic_chord()),
        b_ref=float(wing.span()),
    )


def _vsp_string(path: Path) -> str:
    """Return an OpenVSP-script-friendly path literal body."""

    return str(Path(path).expanduser().resolve()).replace("\\", "/").replace('"', '\\"')


def _prepend_traceability_header(
    *,
    vspscript_path: Path,
    config: BWBGeneratorConfig,
    section_geometry: SectionGeometryResult,
    sample: BWBDesignSample,
) -> None:
    text = vspscript_path.read_text(encoding="utf-8", errors="replace")
    marker = "AERIS CAD EXPORT TRACEABILITY"
    if marker in text:
        return

    first = section_geometry.sections[0]
    last = section_geometry.sections[-1]
    header = f"""// {marker}
// generator_id: bwb_segmented_v1
// geometry_name: {config.name}
// section_count: {len(section_geometry.sections)}
// symmetry: true
// root_section: y={first.y_m:.8f} chord={first.chord_m:.8f} twist={first.twist_deg:.8f}
// tip_section: y={last.y_m:.8f} chord={last.chord_m:.8f} twist={last.twist_deg:.8f}
// sampled_sweep_magnitudes_deg: {sample.sweep_magnitudes_deg}
// generated_at_utc: {_utc_now_iso()}
"""
    vspscript_path.write_text(header + "\n" + text, encoding="utf-8")


def _append_step_export_footer(
    *,
    vspscript_path: Path,
    step_path: Path,
    vsp3_path: Path,
) -> None:
    """Append OpenVSP batch commands that export VSP3 and STEP files.

    The footer is intentionally plain OpenVSP script code.  If the local
    OpenVSP build does not support STEP export, the batch execution will fail
    cleanly and the CLI will preserve stdout/stderr.
    """

    text = vspscript_path.read_text(encoding="utf-8", errors="replace")
    marker = "AERIS OPENVSP STEP EXPORT FOOTER"
    if marker in text:
        return

    footer = f"""

// {marker}
Update();
WriteVSPFile(\"{_vsp_string(vsp3_path)}\");
ExportFile(\"{_vsp_string(step_path)}\", SET_ALL, EXPORT_STEP);
"""
    vspscript_path.write_text(text.rstrip() + footer + "\n", encoding="utf-8")


def export_openvsp_vspscript_from_section_geometry(
    *,
    section_geometry: SectionGeometryResult,
    config: BWBGeneratorConfig,
    sample: BWBDesignSample,
    output_path: Path,
    include_step_footer: bool = False,
    step_path: Path | None = None,
    vsp3_path: Path | None = None,
) -> Path:
    """Write a traceable OpenVSP ``.vspscript`` for a BWB geometry."""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    airplane = _build_aerosandbox_airplane_from_sections(
        section_geometry=section_geometry,
        config=config,
        symmetric=True,
    )

    exporter = getattr(airplane, "export_OpenVSP_vspscript", None)
    if exporter is None:
        raise RuntimeError(
            "The installed AeroSandbox airplane object has no "
            "export_OpenVSP_vspscript(...) method."
        )

    exporter(output_path)
    _prepend_traceability_header(
        vspscript_path=output_path,
        config=config,
        section_geometry=section_geometry,
        sample=sample,
    )

    if include_step_footer:
        if step_path is None:
            step_path = output_path.with_suffix(".step")
        if vsp3_path is None:
            vsp3_path = output_path.with_suffix(".vsp3")
        _append_step_export_footer(
            vspscript_path=output_path,
            step_path=step_path,
            vsp3_path=vsp3_path,
        )

    return output_path



def export_cadquery_step_from_section_geometry(
    *,
    section_geometry: SectionGeometryResult,
    config: BWBGeneratorConfig,
    step_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    symmetric: bool = True,
) -> CadQuerySTEPExportResult:
    """Export STEP directly through AeroSandbox/CadQuery.

    This follows the working operator pattern:

    1. rebuild an AeroSandbox airplane from the AERIS section geometry,
    2. call ``airplane.mesh_body()`` when available,
    3. call ``airplane.export_cadquery_geometry(<step_path>)``.

    It is intentionally separate from OpenVSP batch export. OpenVSP STEP export
    is useful when the local OpenVSP script mode behaves, but CadQuery direct
    export is often the more reliable STEP path once the airplane object exists.
    """

    step_path = Path(step_path)
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    step_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []
    err_lines: list[str] = []

    # AERIS_PATCH_BATCH1_VSP_REMOVE_STALE_CADQUERY_STEP
    # A failed direct STEP export must not inherit success from an old file.
    if step_path.exists():
        step_path.unlink()

    try:
        airplane = _build_aerosandbox_airplane_from_sections(
            section_geometry=section_geometry,
            config=config,
            symmetric=symmetric,
        )
        log_lines.append("Built AeroSandbox airplane from AERIS section geometry.")

        mesh_body = getattr(airplane, "mesh_body", None)
        if callable(mesh_body):
            try:
                mesh_body()
                log_lines.append("airplane.mesh_body() completed.")
            except Exception as exc:  # pragma: no cover - depends on ASB/CadQuery versions
                # Some ASB versions can still export CAD even if mesh preview fails.
                err_lines.append(f"airplane.mesh_body() warning: {type(exc).__name__}: {exc}")

        exporter = getattr(airplane, "export_cadquery_geometry", None)
        if not callable(exporter):
            msg = (
                "The installed AeroSandbox Airplane object has no "
                "export_cadquery_geometry(...) method. Cannot direct-export STEP."
            )
            err_lines.append(msg)
            stdout_path.write_text("\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8")
            stderr_path.write_text("\n".join(err_lines) + "\n", encoding="utf-8")
            return CadQuerySTEPExportResult(
                attempted=False,
                backend="cadquery",
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                step_path=step_path,
                step_exists=False,
                skipped_reason=msg,
            )

        exporter(str(step_path))
        step_exists = step_path.exists()
        if step_exists:
            log_lines.append(f"AeroSandbox/CadQuery STEP export wrote: {step_path}")
            skipped_reason = None
        else:
            skipped_reason = "AeroSandbox/CadQuery export returned but did not create the STEP file."
            err_lines.append(skipped_reason)

        stdout_path.write_text("\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8")
        stderr_path.write_text("\n".join(err_lines) + ("\n" if err_lines else ""), encoding="utf-8")
        return CadQuerySTEPExportResult(
            attempted=True,
            backend="cadquery",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            step_path=step_path,
            step_exists=step_exists,
            skipped_reason=skipped_reason,
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        msg = f"AeroSandbox/CadQuery STEP export failed: {type(exc).__name__}: {exc}"
        err_lines.append(msg)
        stdout_path.write_text("\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8")
        stderr_path.write_text("\n".join(err_lines) + "\n", encoding="utf-8")
        return CadQuerySTEPExportResult(
            attempted=True,
            backend="cadquery",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            step_path=step_path,
            step_exists=step_path.exists(),
            skipped_reason=msg,
        )


def run_openvsp_batch_script(
    *,
    vspscript_path: Path,
    openvsp_executable: str | Path,
    stdout_path: Path,
    stderr_path: Path,
    step_path: Path | None,
    timeout_sec: int = 180,
) -> OpenVSPExecutionResult:
    """Execute OpenVSP in batch-script mode and capture stdout/stderr."""

    import shutil

    vspscript_path = Path(vspscript_path)
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    cmd_text = str(openvsp_executable).strip() or "vsp"
    cmd_path: str | None
    candidate = Path(cmd_text).expanduser()
    if candidate.exists():
        cmd_path = str(candidate.resolve())
    else:
        cmd_path = shutil.which(cmd_text)

    if cmd_path is None:
        msg = f"OpenVSP executable not found: {cmd_text}. STEP export skipped."
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(msg + "\n", encoding="utf-8")
        return OpenVSPExecutionResult(
            attempted=False,
            command=[cmd_text, "-script", str(vspscript_path)],
            returncode=None,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            step_path=step_path,
            step_exists=False if step_path is not None else False,
            skipped_reason=msg,
        )

    command = [cmd_path, "-script", str(vspscript_path)]

    # AERIS_PATCH_BATCH1_VSP_REMOVE_STALE_OPENVSP_STEP
    # OpenVSP execution success must correspond to this run, not a stale STEP.
    if step_path is not None:
        _step = Path(step_path)
        if _step.exists():
            _step.unlink()

    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        stdout_path.write_text(completed.stdout or "", encoding="utf-8")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8")
        return OpenVSPExecutionResult(
            attempted=True,
            command=command,
            returncode=completed.returncode,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            step_path=step_path,
            step_exists=bool(step_path and Path(step_path).exists()),
            skipped_reason=None,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text((exc.stderr or "") + f"\nTimeout after {timeout_sec}s.\n", encoding="utf-8")
        return OpenVSPExecutionResult(
            attempted=True,
            command=command,
            returncode=124,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            step_path=step_path,
            step_exists=bool(step_path and Path(step_path).exists()),
            skipped_reason=f"Timeout after {timeout_sec}s.",
        )
