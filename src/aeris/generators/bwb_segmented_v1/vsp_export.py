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
        # OpenVSP (3.36.x) can return a non-zero exit code even when the
        # script executed and wrote the STEP file. Trust the produced
        # artifact: if the STEP exists, the export succeeded.
        if self.attempted and self.step_exists:
            return True
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
WriteVSPFile(\"{_vsp_string(vsp3_path)}\", SET_ALL);
ExportFile(\"{_vsp_string(step_path)}\", SET_ALL, EXPORT_STEP);
"""
    stripped = text.rstrip()
    last_brace = stripped.rfind("}")
    if last_brace != -1:
        new_text = stripped[:last_brace] + footer + "\n}\n"
    else:
        new_text = stripped + footer + "\n"
    vspscript_path.write_text(new_text, encoding="utf-8")


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


@dataclass(frozen=True)
class SolidSTEPExportResult:
    """Result of watertight-solid STEP export via CadQuery loft."""

    attempted: bool
    backend: str
    stdout_path: Path
    stderr_path: Path
    step_path: Path
    step_exists: bool
    is_solid: bool
    solid_count: int = 0
    shell_count: int = 0
    face_count: int = 0
    volume_m3: float | None = None
    bbox_x_m: float | None = None
    bbox_y_m: float | None = None
    bbox_z_m: float | None = None
    skipped_reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return bool(self.attempted and self.step_exists and self.is_solid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "backend": self.backend,
            "stdout_path": str(self.stdout_path),
            "stderr_path": str(self.stderr_path),
            "step_path": str(self.step_path),
            "step_exists": self.step_exists,
            "is_solid": self.is_solid,
            "solid_count": self.solid_count,
            "shell_count": self.shell_count,
            "face_count": self.face_count,
            "volume_m3": self.volume_m3,
            "bbox_x_m": self.bbox_x_m,
            "bbox_y_m": self.bbox_y_m,
            "bbox_z_m": self.bbox_z_m,
            "succeeded": self.succeeded,
            "skipped_reason": self.skipped_reason,
        }


def _section_closed_wire(airfoil_name, le_x, y, z, chord, twist_deg, fallback_name="naca0012"):
    """Build a closed CadQuery wire for one section profile.

    Uses the SAME airfoil coordinates AeroSandbox uses (asb.Airfoil(name).coordinates),
    scaled by chord and twisted about the leading edge, then placed in 3D with the
    section's LE position (x aft, y span, z up). z already contains cumulative
    dihedral from the section geometry, so the loft matches the ASB airplane.
    """
    import aerosandbox as asb
    import numpy as np
    import cadquery as cq

    try:
        af = asb.Airfoil(airfoil_name)
        coords = af.coordinates
        if coords is None:
            raise ValueError("no coordinates")
    except Exception:
        af = asb.Airfoil(fallback_name)
        coords = af.coordinates

    coords = np.asarray(coords, dtype=float)
    t = np.radians(float(twist_deg))
    cos_t = np.cos(t)
    sin_t = np.sin(t)

    pts = []
    seen = set()
    for xc, zc in coords:
        xs = float(xc) * float(chord)
        zs = float(zc) * float(chord)
        # Twist about LE (rotation in the x-z plane, nose-up positive)
        xr = xs * cos_t + zs * sin_t
        zr = -xs * sin_t + zs * cos_t
        px = float(le_x) + xr
        py = float(y)
        pz = float(z) + zr
        key = (round(px, 9), round(py, 9), round(pz, 9))
        if key in seen:
            continue
        seen.add(key)
        # Scale from metres (AERIS internal) to mm (OCC/CadQuery internal unit).
        # OCC/CadQuery works in mm; exportStep writes mm to STEP.
        pts.append(cq.Vector(px * 1000.0, py * 1000.0, pz * 1000.0))

    if len(pts) < 3:
        raise ValueError("Section produced fewer than 3 unique points; cannot form a wire.")

    return cq.Wire.makePolygon(pts, close=True)


def _ensure_airplane_has_cadquery_geometry_mike(airplane, log_lines: list[str]) -> str:
    """Ensure the Airplane has Mike's volumetric CadQuery exporter.

    Prefer the installed/original method when present. Only inject the fallback
    when the local AeroSandbox installation does not provide it. This keeps the
    production path honest: solid STEP means Mike-style volumetric CadQuery,
    not the older surface-shell exporter.
    """
    for method_name in (
        "export_cadquery_geometry_mike",
        "export_cadquery_mike",
        "export_cadquer_mike",  # tolerate the old typo if it exists locally
    ):
        exporter = getattr(airplane, method_name, None)
        if callable(exporter):
            if method_name != "export_cadquery_geometry_mike":
                airplane.export_cadquery_geometry_mike = exporter
            log_lines.append(f"Using installed Airplane.{method_name}().")
            return f"installed_{method_name}"

    import types

    def _gen_cq_mike(self, minimum_airfoil_TE_thickness=0.001, fuselage_tol=1e-4):
        import cadquery as cq

        solids = []
        for wing in self.wings:
            xsec_wps = []
            for i, xsec in enumerate(wing.xsecs):
                csys = wing._compute_frame_of_WingXSec(i)
                af = xsec.airfoil
                if af.TE_thickness() < minimum_airfoil_TE_thickness:
                    af = af.set_TE_thickness(minimum_airfoil_TE_thickness)
                LE = af.LE_index()
                wp = (
                    cq.Workplane(
                        inPlane=cq.Plane(
                            origin=tuple(float(v) for v in xsec.xyz_le),
                            xDir=tuple(float(v) for v in csys[0]),
                            normal=tuple(float(v) for v in -csys[1]),
                        )
                    )
                    .spline([tuple(pt * xsec.chord) for pt in af.coordinates[:LE, :]])
                    .spline(
                        listOfXYTuple=[tuple(pt * xsec.chord) for pt in af.coordinates[LE:, :]],
                        includeCurrent=True,
                    )
                    .close()
                )
                xsec_wps.append(wp)
            wires = [wp.val() for wp in xsec_wps]
            wing_solid = cq.Solid.makeLoft(wires, ruled=True)
            solids.append(wing_solid)
            if wing.symmetric:
                solids.append(wing_solid.mirror("XZ"))
        final_wp = cq.Workplane("XY").newObject(solids)
        return final_wp.combine(clean=True)

    def _exp_cq_mike(self, filename, minimum_airfoil_TE_thickness=0.001):
        from cadquery import exporters

        solid = self.generate_cadquery_geometry_mike(minimum_airfoil_TE_thickness)
        solid.objects = [o.scale(1000) for o in solid.objects]
        exporters.export(solid, fname=str(filename))

    airplane.generate_cadquery_geometry_mike = types.MethodType(_gen_cq_mike, airplane)
    airplane.export_cadquery_geometry_mike = types.MethodType(_exp_cq_mike, airplane)
    log_lines.append("Injected fallback export_cadquery_geometry_mike at runtime.")
    return "injected_export_cadquery_geometry_mike"


def _copy_xsec_for_full_span_mirror(xsec):
    """Mirror one AeroSandbox WingXSec across the XZ plane for full-span lofting."""
    import aerosandbox as asb

    xyz = [float(v) for v in xsec.xyz_le]
    return asb.WingXSec(
        xyz_le=[xyz[0], -xyz[1], xyz[2]],
        chord=float(xsec.chord),
        twist=float(xsec.twist),
        airfoil=xsec.airfoil,
        control_surfaces=[],
    )


def _copy_xsec_without_controls(xsec):
    """Copy one AeroSandbox WingXSec while stripping controls for neutral CAD."""
    import aerosandbox as asb

    return asb.WingXSec(
        xyz_le=[float(v) for v in xsec.xyz_le],
        chord=float(xsec.chord),
        twist=float(xsec.twist),
        airfoil=xsec.airfoil,
        control_surfaces=[],
    )


def _build_mike_solid_export_airplane(
    *,
    section_geometry: SectionGeometryResult,
    config: BWBGeneratorConfig,
    symmetric: bool = True,
):
    """Build the exact AeroSandbox airplane used by the solid Mike exporter.

    For symmetric BWB geometry, do not loft a half-wing and then boolean-fuse its
    mirror. That can leave two touching solids or a thin root artifact for some
    DoE geometries. Instead build a non-symmetric full-span AeroSandbox wing and
    let Mike's exporter loft one continuous solid from left tip to right tip.
    """
    import aerosandbox as asb

    from aeris.generators.bwb_segmented_v1.aerosandbox_adapter import (
        build_aerosandbox_geometry,
    )

    asb_result = build_aerosandbox_geometry(section_geometry, config)
    airplane = asb_result.airplane

    if not symmetric:
        return airplane, "canonical_asb_airplane"

    if not airplane.wings:
        raise ValueError("AeroSandbox airplane has no wings for solid STEP export.")

    wing = airplane.wings[0]
    positive_xsecs = list(wing.xsecs)
    if len(positive_xsecs) < 2:
        raise ValueError("Need at least 2 BWB sections for solid STEP export.")

    # y order: negative tip -> negative near-root -> root -> positive tip.
    # Exclude the mirrored root to avoid duplicate coincident root wires.
    mirrored_left = [
        _copy_xsec_for_full_span_mirror(xsec)
        for xsec in reversed(positive_xsecs[1:])
    ]
    right = [_copy_xsec_without_controls(xsec) for xsec in positive_xsecs]
    full_xsecs = mirrored_left + right

    full_wing = asb.Wing(
        name=f"{wing.name}_full_span_solid",
        symmetric=False,
        xsecs=full_xsecs,
    )

    full_airplane = asb.Airplane(
        name=airplane.name,
        xyz_ref=[0.0, 0.0, 0.0],
        wings=[full_wing],
        s_ref=float(full_wing.area()),
        c_ref=float(full_wing.mean_aerodynamic_chord()),
        b_ref=float(full_wing.span()),
    )
    return full_airplane, "canonical_asb_full_span_no_mirror_boolean"


def export_solid_step_from_section_geometry(
    *,
    section_geometry,
    config,
    step_path,
    stdout_path,
    stderr_path,
    symmetric: bool = True,
) -> "SolidSTEPExportResult":
    """Export a watertight solid STEP by lofting AERIS section profiles.

    Produces a single closed BREP solid (verified is_solid), mirrored across
    the XZ plane and fused when symmetric=True. Consistent with the AeroSandbox
    airplane geometry but suitable for CFD meshing, boolean operations, and
    solver analysis.
    """
    import cadquery as cq

    step_path = Path(step_path)
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    step_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    log_lines: list[str] = []
    err_lines: list[str] = []

    # Remove stale STEP so success cannot be inherited from a previous run.
    if step_path.exists():
        step_path.unlink()

    try:
        # Build the same canonical AeroSandbox airplane AERIS uses elsewhere,
        # then export it through Mike's volumetric CadQuery path. For symmetric
        # wings, use a full-span non-symmetric loft to avoid root boolean artifacts.
        airplane, airplane_source = _build_mike_solid_export_airplane(
            section_geometry=section_geometry,
            config=config,
            symmetric=symmetric,
        )
        log_lines.append(
            f"Built {airplane_source} for Mike solid export "
            f"({len(airplane.wings[0].xsecs)} export sections)."
        )

        mike_source = _ensure_airplane_has_cadquery_geometry_mike(airplane, log_lines)
        airplane.export_cadquery_geometry_mike(str(step_path))
        log_lines.append(
            f"Solid STEP written via {mike_source}: {step_path}"
        )

        step_exists = step_path.exists()
        is_valid = bool(step_exists)
        solid_count = 0
        shell_count = 0
        face_count = 0
        volume_m3 = None
        bbox_x_m = None
        bbox_y_m = None
        bbox_z_m = None

        if step_exists:
            try:
                imported = cq.importers.importStep(str(step_path))
                solids = imported.solids().vals()
                shells = imported.shells().vals()
                faces = imported.faces().vals()
                bb = imported.val().BoundingBox()

                solid_count = len(solids)
                shell_count = len(shells)
                face_count = len(faces)
                volume_m3 = float(sum(solid.Volume() for solid in solids) / 1e9)

                bbox_x_m = float(abs(bb.xmax - bb.xmin) / 1000.0)
                bbox_y_m = float(abs(bb.ymax - bb.ymin) / 1000.0)
                bbox_z_m = float(abs(bb.zmax - bb.zmin) / 1000.0)

                expected_solid_count = 1 if symmetric else None
                is_valid = (
                    solid_count == expected_solid_count and volume_m3 > 0.0
                    if expected_solid_count is not None
                    else solid_count >= 1 and volume_m3 > 0.0
                )
                log_lines.append(
                    "STEP validation: "
                    f"solids={solid_count} shells={shell_count} faces={face_count} "
                    f"volume_m3={volume_m3:.9g} "
                    f"bbox_m=({bbox_x_m:.6g}, {bbox_y_m:.6g}, {bbox_z_m:.6g})"
                )
                if expected_solid_count is not None and solid_count != expected_solid_count:
                    err_lines.append(
                        f"Expected exactly {expected_solid_count} fused solid for symmetric "
                        f"BWB export, got {solid_count}."
                    )
            except Exception as verify_exc:
                is_valid = False
                err_lines.append(
                    f"STEP validation failed: {type(verify_exc).__name__}: {verify_exc}"
                )

        stdout_path.write_text(
            "\n".join(log_lines) + ("\n" if log_lines else ""),
            encoding="utf-8",
        )
        stderr_path.write_text(
            "\n".join(err_lines) + ("\n" if err_lines else ""),
            encoding="utf-8",
        )

        return SolidSTEPExportResult(
            attempted=True,
            backend="solid",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            step_path=step_path,
            step_exists=step_exists,
            is_solid=is_valid,
            solid_count=solid_count,
            shell_count=shell_count,
            face_count=face_count,
            volume_m3=volume_m3,
            bbox_x_m=bbox_x_m,
            bbox_y_m=bbox_y_m,
            bbox_z_m=bbox_z_m,
            skipped_reason=None if is_valid else "Solid STEP validation failed.",
        )


    except Exception as exc:
        msg = f"Solid STEP loft export failed: {type(exc).__name__}: {exc}"
        err_lines.append(msg)
        stdout_path.write_text("\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8")
        stderr_path.write_text("\n".join(err_lines) + "\n", encoding="utf-8")
        return SolidSTEPExportResult(
            attempted=True,
            backend="solid",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            step_path=step_path,
            step_exists=step_path.exists(),
            is_solid=False,
            skipped_reason=msg,
        )
