"""Generic CAD-export orchestration for AERIS geometry generators.

The key architecture rule is: this module owns CLI/workflow-level orchestration,
not BWB geometry math.  Generator-specific CAD reconstruction currently lives in
``aeris.generators.bwb_segmented_v1.vsp_export``.
"""

from __future__ import annotations

import json
import platform
import shutil
import sys
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from aeris.common.config import load_yaml_config
from aeris.common.paths import create_run_folder
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator

SUPPORTED_FORMATS = {"vspscript", "step"}
SUPPORTED_STEP_BACKENDS = {"auto", "cadquery", "openvsp"}


@dataclass(frozen=True)
class CADExportResult:
    """Summary of one CAD export run."""

    status: str
    run_root: Path
    cad_dir: Path
    manifest_path: Path
    formats_requested: tuple[str, ...]
    formats_produced: tuple[str, ...]
    vspscript_path: Path | None
    step_path: Path | None
    stdout_path: Path | None
    stderr_path: Path | None
    warnings: tuple[str, ...]

    @property
    def succeeded(self) -> bool:
        return self.status in {"success", "partial_success"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "run_root": str(self.run_root),
            "cad_dir": str(self.cad_dir),
            "manifest_path": str(self.manifest_path),
            "formats_requested": list(self.formats_requested),
            "formats_produced": list(self.formats_produced),
            "vspscript_path": None if self.vspscript_path is None else str(self.vspscript_path),
            "step_path": None if self.step_path is None else str(self.step_path),
            "stdout_path": None if self.stdout_path is None else str(self.stdout_path),
            "stderr_path": None if self.stderr_path is None else str(self.stderr_path),
            "warnings": list(self.warnings),
        }


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def parse_cad_formats(formats: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Parse CLI format input into normalized CAD format names."""

    if isinstance(formats, str):
        raw = [item.strip().lower() for item in formats.split(",")]
    else:
        raw = [str(item).strip().lower() for item in formats]

    aliases = {
        "vsp": "vspscript",
        "openvsp": "vspscript",
        "vspscript": "vspscript",
        ".vspscript": "vspscript",
        "step": "step",
        "stp": "step",
        ".step": "step",
        ".stp": "step",
    }

    normalized: list[str] = []
    for item in raw:
        if not item:
            continue
        if item not in aliases:
            raise ValueError(
                f"Unsupported CAD export format {item!r}. "
                f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}."
            )
        value = aliases[item]
        if value not in normalized:
            normalized.append(value)

    if not normalized:
        raise ValueError("At least one CAD export format is required.")

    # STEP currently depends on a vspscript reconstruction, so always keep it.
    if "step" in normalized and "vspscript" not in normalized:
        normalized.insert(0, "vspscript")

    return tuple(normalized)


def parse_step_backend(step_backend: str) -> str:
    """Normalize STEP backend selection."""

    value = str(step_backend or "auto").strip().lower()
    aliases = {
        "auto": "auto",
        "cadquery": "cadquery",
        "cq": "cadquery",
        "asb": "cadquery",
        "aerosandbox": "cadquery",
        "openvsp": "openvsp",
        "vsp": "openvsp",
    }
    if value not in aliases:
        raise ValueError(
            f"Unsupported STEP backend {step_backend!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_STEP_BACKENDS))}."
        )
    return aliases[value]


def _make_output_root(config_path: Path, output_dir: Path | None) -> Path:
    if output_dir is not None:
        root = Path(output_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root
    return create_run_folder(prefix=f"cad_export_{config_path.stem}").root


def openvsp_doctor(openvsp_command: str | Path = "vsp") -> dict[str, Any]:
    """Check whether an OpenVSP executable/path is available.

    This intentionally avoids launching OpenVSP.  Some GUI builds open windows or
    block on startup, so the doctor is a cheap PATH/existence check.
    """

    command_text = str(openvsp_command).strip() or "vsp"
    candidate = Path(command_text).expanduser()
    if candidate.exists():
        resolved = str(candidate.resolve())
        found = True
        source = "path"
    else:
        resolved = shutil.which(command_text)
        found = resolved is not None
        source = "PATH" if found else None

    return {
        "openvsp_command": command_text,
        "found": found,
        "resolved_path": resolved,
        "source": source,
        "platform": platform.system().lower(),
        "note": (
            "STEP export requires OpenVSP batch execution. "
            "VSP script export works without OpenVSP installed."
        ),
    }


def export_cad_from_config(
    *,
    config_path: str | Path,
    formats: str | list[str] | tuple[str, ...] = "vspscript",
    output_dir: str | Path | None = None,
    openvsp_command: str | Path = "vsp",
    timeout_sec: int = 180,
    step_backend: str = "auto",
) -> CADExportResult:
    """Export CAD artifacts for a config-defined geometry."""

    resolved_config_path = Path(config_path).expanduser().resolve()
    requested = parse_cad_formats(formats)
    resolved_step_backend = parse_step_backend(step_backend)
    run_root = _make_output_root(
        resolved_config_path,
        None if output_dir is None else Path(output_dir),
    )
    cad_dir = run_root / "cad_exports"
    cad_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cad_dir / "geometry_export_manifest.json"

    vspscript_path = cad_dir / "geometry.vspscript"
    step_path = cad_dir / "geometry.step" if "step" in requested else None
    vsp3_path = cad_dir / "geometry.vsp3" if "step" in requested else None
    stdout_path = cad_dir / "stdout.txt"
    stderr_path = cad_dir / "stderr.txt"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")

    warnings: list[str] = []
    produced: list[str] = []
    status = "running"
    error: dict[str, Any] | None = None
    execution_payload: dict[str, Any] | None = None
    cadquery_payload: dict[str, Any] | None = None
    source_artifacts: dict[str, str] = {}

    manifest: dict[str, Any] = {
        "status": status,
        "phase": "geometry_export_cad",
        "created_at_utc": _utc_now_iso(),
        "completed_at_utc": None,
        "config_path": str(resolved_config_path),
        "run_root": str(run_root),
        "cad_dir": str(cad_dir),
        "formats_requested": list(requested),
        "formats_produced": [],
        "platform": platform.system().lower(),
        "python_version": sys.version.split()[0],
        "openvsp": None,
        "step_export": {
            "backend_requested": resolved_step_backend,
            "cadquery": None,
            "openvsp": None,
        },
        "generator": None,
        "artifacts": {},
        "warnings": [],
        "error": None,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    try:
        raw_config = load_yaml_config(resolved_config_path)
        generator_id, generator_config = resolve_generator_and_config(raw_config)
        generator = get_geometry_generator(generator_id)
        seed = getattr(getattr(generator_config, "generator", None), "seed", None)
        sample = generator.sample_one(generator_config, seed=seed)

        if generator_id != "bwb_segmented_v1":
            raise NotImplementedError(
                f"CAD export currently supports only bwb_segmented_v1, got {generator_id!r}."
            )

        from aeris.generators.bwb_segmented_v1.vsp_export import (
            build_bwb_cad_source,
            export_cadquery_step_from_section_geometry,
            export_openvsp_vspscript_from_section_geometry,
            run_openvsp_batch_script,
        )

        source = build_bwb_cad_source(
            config=generator_config,
            sample=sample,
            output_dir=cad_dir,
        )
        source_artifacts = source.artifact_paths

        export_openvsp_vspscript_from_section_geometry(
            section_geometry=source.section_geometry,
            config=generator_config,
            sample=sample,
            output_path=vspscript_path,
            include_step_footer=("step" in requested),
            step_path=step_path,
            vsp3_path=vsp3_path,
        )
        if vspscript_path.exists():
            produced.append("vspscript")

        if "step" in requested:
            # STEP backend policy:
            #   cadquery  -> direct AeroSandbox/CadQuery STEP only
            #   openvsp   -> OpenVSP batch script only
            #   auto      -> try CadQuery first, then OpenVSP if CadQuery fails
            if resolved_step_backend in {"auto", "cadquery"}:
                cadquery_stdout = cad_dir / "cadquery_stdout.txt"
                cadquery_stderr = cad_dir / "cadquery_stderr.txt"
                cadquery_result = export_cadquery_step_from_section_geometry(
                    section_geometry=source.section_geometry,
                    config=generator_config,
                    step_path=step_path or (cad_dir / "geometry.step"),
                    stdout_path=cadquery_stdout,
                    stderr_path=cadquery_stderr,
                    symmetric=True,
                )
                cadquery_payload = cadquery_result.to_dict()
                if cadquery_result.succeeded:
                    produced.append("step")
                    stdout_path.write_text(cadquery_stdout.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                    stderr_path.write_text(cadquery_stderr.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                else:
                    warnings.append(
                        cadquery_result.skipped_reason
                        or "AeroSandbox/CadQuery STEP export did not produce geometry.step."
                    )

            if "step" not in produced and resolved_step_backend in {"auto", "openvsp"}:
                execution = run_openvsp_batch_script(
                    vspscript_path=vspscript_path,
                    openvsp_executable=openvsp_command,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    step_path=step_path,
                    timeout_sec=timeout_sec,
                )
                execution_payload = execution.to_dict()
                if execution.succeeded:
                    produced.append("step")
                else:
                    warnings.append(
                        execution.skipped_reason
                        or "OpenVSP STEP export did not produce geometry.step. See stdout.txt/stderr.txt."
                    )

        status = "success" if set(produced) >= set(requested) else "partial_success"
        if not produced:
            status = "failed"

        manifest.update(
            {
                "status": status,
                "completed_at_utc": _utc_now_iso(),
                "formats_produced": list(produced),
                "generator": {
                    "id": generator_id,
                    "seed": seed,
                    "design_sample": _jsonable(sample),
                },
                "openvsp": {
                    "command_requested": str(openvsp_command),
                    "doctor": openvsp_doctor(openvsp_command),
                    "execution": execution_payload,
                },
                "step_export": {
                    "backend_requested": resolved_step_backend,
                    "cadquery": cadquery_payload,
                    "openvsp": execution_payload,
                },
                "artifacts": {
                    "vspscript": str(vspscript_path) if vspscript_path.exists() else None,
                    "step": str(step_path) if step_path and step_path.exists() else None,
                    "vsp3": str(vsp3_path) if vsp3_path and vsp3_path.exists() else None,
                    "stdout": str(stdout_path),
                    "stderr": str(stderr_path),
                    "cadquery_stdout": str(cad_dir / "cadquery_stdout.txt") if (cad_dir / "cadquery_stdout.txt").exists() else None,
                    "cadquery_stderr": str(cad_dir / "cadquery_stderr.txt") if (cad_dir / "cadquery_stderr.txt").exists() else None,
                    **source_artifacts,
                },
                "warnings": warnings,
                "error": None,
            }
        )
    except Exception as exc:
        status = "failed"
        error = {"type": type(exc).__name__, "message": str(exc)}
        warnings.append(str(exc))
        stderr_path.write_text(str(exc) + "\n", encoding="utf-8")
        manifest.update(
            {
                "status": status,
                "completed_at_utc": _utc_now_iso(),
                "formats_produced": list(produced),
                "artifacts": {
                    "vspscript": str(vspscript_path) if vspscript_path.exists() else None,
                    "step": str(step_path) if step_path and step_path.exists() else None,
                    "stdout": str(stdout_path),
                    "stderr": str(stderr_path),
                    **source_artifacts,
                },
                "warnings": warnings,
                "error": error,
            }
        )
    finally:
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return CADExportResult(
        status=status,
        run_root=run_root,
        cad_dir=cad_dir,
        manifest_path=manifest_path,
        formats_requested=requested,
        formats_produced=tuple(produced),
        vspscript_path=vspscript_path if vspscript_path.exists() else None,
        step_path=step_path if step_path is not None and step_path.exists() else None,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        warnings=tuple(warnings),
    )
