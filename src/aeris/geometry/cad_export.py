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
SUPPORTED_STEP_BACKENDS = {"auto", "solid", "cadquery", "openvsp"}


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
        # AERIS_PATCH_BATCH2_CAD_SUCCESS_STRICT
        # Partial success means at least one artifact exists, but not all requested
        # artifacts. Treat it as not fully succeeded so CLI/GUI/workflows do not
        # confuse VSPScript-only output with successful STEP output.
        return self.status == "success"

    @property
    def partially_succeeded(self) -> bool:
        return self.status == "partial_success"

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


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """AERIS_PATCH_BATCH2_CAD_ATOMIC_MANIFEST: write JSON via temp + replace."""
    import os
    import tempfile

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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
        "solid": "solid",
        "loft": "solid",
        "watertight": "solid",
        "cadquery": "cadquery",
        "cq": "cadquery",
        "asb": "cadquery",
        "aerosandbox": "cadquery",
        "openvsp": "openvsp",
        "vsp": "openvsp",
    }
    if value not in aliases:
        raise ValueError(
            f"Unsupported STEP backend {step_backend!r}. Valid values: solid (watertight loft — CFD/boolean ready), cadquery (surface shells), openvsp (OpenVSP batch), auto (solid→cadquery→openvsp). "
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

    # AERIS_PATCH_BATCH1_CAD_REMOVE_STALE_STEP
    # Explicit output directories reuse fixed artifact names. Delete stale STEP
    # outputs before a new export attempt so result.succeeded cannot be fooled
    # by a file produced by an earlier run.
    for _stale_path in (step_path, vsp3_path):
        if _stale_path is not None and _stale_path.exists():
            _stale_path.unlink()

    warnings: list[str] = []
    produced: list[str] = []
    status = "running"
    error: dict[str, Any] | None = None
    execution_payload: dict[str, Any] | None = None
    solid_payload: dict[str, Any] | None = None
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
            "solid": None,
            "cadquery": None,
            "openvsp": None,
        },
        "generator": None,
        "artifacts": {},
        "warnings": [],
        "error": None,
    }
    _write_json_atomic(manifest_path, manifest)

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
            export_solid_step_from_section_geometry,
            export_solid_step_from_section_geometry,
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
            # solid backend: watertight loft (best for CFD/booleans)
            # auto tries solid first, then cadquery, then openvsp
            solid_payload: dict | None = None
            if resolved_step_backend in {"auto", "solid"}:
                solid_stdout = cad_dir / "solid_stdout.txt"
                solid_stderr = cad_dir / "solid_stderr.txt"
                solid_result = export_solid_step_from_section_geometry(
                    section_geometry=source.section_geometry,
                    config=generator_config,
                    step_path=step_path or (cad_dir / "geometry.step"),
                    stdout_path=solid_stdout,
                    stderr_path=solid_stderr,
                    symmetric=True,
                )
                solid_payload = solid_result.to_dict()
                if solid_result.succeeded:
                    produced.append("step")
                    stdout_path.write_text(
                        solid_stdout.read_text(encoding="utf-8", errors="replace"),
                        encoding="utf-8",
                    )
                    stderr_path.write_text(
                        solid_stderr.read_text(encoding="utf-8", errors="replace"),
                        encoding="utf-8",
                    )
                else:
                    warnings.append(
                        solid_result.skipped_reason
                        or "Solid STEP loft failed."
                    )
            if resolved_step_backend in {"auto", "cadquery"} and "step" not in produced:
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
                    "backend_final": "solid" if solid_payload and solid_payload.get("succeeded") else (
                        "cadquery" if cadquery_payload and cadquery_payload.get("succeeded") else (
                            "openvsp" if execution_payload and execution_payload.get("succeeded") else None
                        )
                    ),
                    "solid": solid_payload,
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
        _write_json_atomic(manifest_path, manifest)

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

# AERIS_PATCH_BATCH2_CAD_ATOMIC_MANIFEST_REPLACED

def load_sample_from_geometry_run(run_dir):
    """Load a BWBDesignSample + BWBGeneratorConfig from an existing geometry run.

    Essential for DoE workflows: pick N from 10,000 geometry runs and export
    only those specific cases to CAD, without re-sampling from bounds.

    Parameters
    ----------
    run_dir : str or Path
        Geometry run root folder (contains manifest.json and artifacts/).

    Returns
    -------
    (BWBDesignSample, BWBGeneratorConfig, Path)

    Raises
    ------
    FileNotFoundError  If manifest.json or geometry_summary.json are absent.
    KeyError           If stored JSON is missing expected DV fields.
    ValueError         If the run did not succeed.
    """
    import json as _json
    from pathlib import Path as _Path
    from aeris.generators.bwb_segmented_v1.params import BWBDesignSample, build_bwb_generator_config
    from aeris.common.config import load_yaml_config as _load_yaml

    run_dir = _Path(run_dir).expanduser().resolve()

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json at {manifest_path}")
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))

    run_status = manifest.get("status", "unknown")
    if run_status != "success":
        raise ValueError(
            f"Run {run_dir.name} has status={run_status!r}. "
            "Only successful runs can be exported to CAD."
        )

    cfg_path_str = manifest.get("config_path") or (
        manifest.get("geometry") or {}
    ).get("config_path")
    if not cfg_path_str:
        raise KeyError("manifest.json does not contain config_path")
    cfg_path = _Path(cfg_path_str).expanduser().resolve()
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"Original config not found: {cfg_path}. "
            "The YAML config file must still exist to reconstruct generator settings."
        )

    summary_candidates = [
        run_dir / "artifacts" / "geometry" / "geometry_summary.json",
        run_dir / "geometry_summary.json",
    ]
    summary_path = next((p for p in summary_candidates if p.exists()), None)
    if summary_path is None:
        raise FileNotFoundError(f"No geometry_summary.json found under {run_dir}")
    summary = _json.loads(summary_path.read_text(encoding="utf-8"))

    sp = summary.get("sampled_planform") or {}
    ss = summary.get("sampled_sections") or {}
    required = (
        "c1_m", "c2_ratio", "c3_ratio", "c4_ratio",
        "b_total_m", "b3_ratio", "split_ratio",
        "sw1_deg", "sw2_deg", "sw3_deg",
    )
    missing = [k for k in required if k not in sp]
    if missing:
        raise KeyError(f"geometry_summary.json missing planform DV fields: {missing}")

    sample = BWBDesignSample(
        c1_m=float(sp["c1_m"]),
        c2_ratio=float(sp["c2_ratio"]),
        c3_ratio=float(sp["c3_ratio"]),
        c4_ratio=float(sp["c4_ratio"]),
        b_total_m=float(sp["b_total_m"]),
        b3_ratio=float(sp["b3_ratio"]),
        split_ratio=float(sp["split_ratio"]),
        sw1_deg=float(sp["sw1_deg"]),
        sw2_deg=float(sp["sw2_deg"]),
        sw3_deg=float(sp["sw3_deg"]),
        twist_b0_deg=float(ss.get("twist_b0_deg", 0.0)),
        twist_b1_deg=float(ss.get("twist_b1_deg", 0.0)),
        twist_b2_deg=float(ss.get("twist_b2_deg", 0.0)),
        twist_b3_deg=float(ss.get("twist_b3_deg", 0.0)),
        dihedral_b1_deg=float(ss.get("dihedral_b1_deg", 0.0)),
        dihedral_b2_deg=float(ss.get("dihedral_b2_deg", 0.0)),
        dihedral_b3_deg=float(ss.get("dihedral_b3_deg", 0.0)),
        elevon_start_frac=float(sp.get("elevon_start_frac", 0.60)),
        elevon_end_frac=float(sp.get("elevon_end_frac", 0.95)),
        elevon_hinge_frac=float(sp.get("elevon_hinge_frac", 0.75)),
    )

    raw = _load_yaml(str(cfg_path))
    config = build_bwb_generator_config(raw)
    return sample, config, run_dir


def export_cad_from_sample(
    *,
    sample,
    config,
    output_dir,
    formats="vspscript,step",
    openvsp_command="vsp",
    timeout_sec=180,
    step_backend="auto",
):
    """Export CAD from a SPECIFIC pre-built BWBDesignSample (DoE run export path).

    Identical logic to export_cad_from_config but uses a provided sample
    instead of re-sampling from the YAML config bounds. Use after a DoE campaign
    to export CAD for specific selected geometries (e.g. 50 out of 10,000).

    Parameters
    ----------
    sample : BWBDesignSample
        The design vector. Use load_sample_from_geometry_run() to build this.
    config : BWBGeneratorConfig
        Generator config loaded from the original YAML.
    output_dir : Path-like
        Directory for CAD artifacts.
    formats, step_backend, openvsp_command, timeout_sec
        Same semantics as export_cad_from_config.
    """
    import platform as _platform
    import sys as _sys
    from pathlib import Path as _Path

    output_dir = _Path(output_dir).expanduser().resolve()
    requested = parse_cad_formats(formats)
    resolved_step_backend = parse_step_backend(step_backend)
    cad_dir = output_dir / "cad_exports"
    cad_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cad_dir / "geometry_export_manifest.json"

    vspscript_path = cad_dir / "geometry.vspscript"
    step_path = cad_dir / "geometry.step" if "step" in requested else None
    vsp3_path = cad_dir / "geometry.vsp3" if "step" in requested else None
    stdout_path = cad_dir / "stdout.txt"
    stderr_path = cad_dir / "stderr.txt"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")

    for _stale in (step_path, vsp3_path):
        if _stale is not None and _stale.exists():
            _stale.unlink()

    warnings_list = []
    produced = []
    status = "running"
    error = None
    execution_payload = None
    cadquery_payload = None
    source_artifacts = {}

    manifest = {
        "status": status,
        "phase": "geometry_export_cad_from_run",
        "created_at_utc": _utc_now_iso(),
        "completed_at_utc": None,
        "run_root": str(output_dir),
        "cad_dir": str(cad_dir),
        "formats_requested": list(requested),
        "formats_produced": [],
        "platform": _platform.system().lower(),
        "python_version": _sys.version.split()[0],
        "generator": None,
        "step_export": {
            "backend_requested": resolved_step_backend,
            "solid": None,
            "cadquery": None,
            "openvsp": None,
        },
        "artifacts": {},
        "warnings": [],
        "error": None,
    }
    _write_json_atomic(manifest_path, manifest)

    try:
        from aeris.generators.bwb_segmented_v1.vsp_export import (
            build_bwb_cad_source,
            export_cadquery_step_from_section_geometry,
            export_openvsp_vspscript_from_section_geometry,
        )

        source = build_bwb_cad_source(
            config=config,
            sample=sample,
            output_dir=cad_dir,
        )
        source_artifacts = source.artifact_paths

        export_openvsp_vspscript_from_section_geometry(
            section_geometry=source.section_geometry,
            config=config,
            sample=sample,
            output_path=vspscript_path,
            include_step_footer=("step" in requested),
            step_path=step_path,
            vsp3_path=vsp3_path,
        )
        if vspscript_path.exists():
            produced.append("vspscript")

        if "step" in requested:
            solid_payload2: dict | None = None
            if resolved_step_backend in {"auto", "solid"}:
                sol_out = cad_dir / "solid_stdout.txt"
                sol_err = cad_dir / "solid_stderr.txt"
                sol_result = export_solid_step_from_section_geometry(
                    section_geometry=source.section_geometry,
                    config=config,
                    step_path=step_path or (cad_dir / "geometry.step"),
                    stdout_path=sol_out,
                    stderr_path=sol_err,
                    symmetric=True,
                )
                solid_payload2 = sol_result.to_dict()
                if sol_result.succeeded:
                    produced.append("step")
                else:
                    warnings_list.append(
                        sol_result.skipped_reason or "Solid STEP loft failed."
                    )
            if resolved_step_backend in {"auto", "cadquery"} and "step" not in produced:
                cq_out = cad_dir / "cadquery_stdout.txt"
                cq_err = cad_dir / "cadquery_stderr.txt"
                cq_result = export_cadquery_step_from_section_geometry(
                    section_geometry=source.section_geometry,
                    config=config,
                    step_path=step_path or (cad_dir / "geometry.step"),
                    stdout_path=cq_out,
                    stderr_path=cq_err,
                    symmetric=True,
                )
                cadquery_payload = cq_result.to_dict()
                if cq_result.succeeded:
                    produced.append("step")
                else:
                    warnings_list.append(
                        cq_result.skipped_reason or "CadQuery STEP export failed"
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
                    warnings_list.append(
                        execution.skipped_reason or "OpenVSP STEP export failed"
                    )

        status = "success" if set(produced) >= set(requested) else "partial_success"
        if not produced:
            status = "failed"

        manifest.update({
            "status": status,
            "completed_at_utc": _utc_now_iso(),
            "formats_produced": list(produced),
            "generator": {
                "id": "bwb_segmented_v1",
                "design_sample": _jsonable(sample),
            },
            "step_export": {
                "backend_requested": resolved_step_backend,
                "cadquery": cadquery_payload,
                "openvsp": execution_payload,
            },
            "artifacts": {
                "vspscript": str(vspscript_path) if vspscript_path.exists() else None,
                "step": str(step_path) if step_path and step_path.exists() else None,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                **source_artifacts,
            },
            "warnings": warnings_list,
            "error": None,
        })

    except Exception as exc:
        status = "failed"
        error = {"type": type(exc).__name__, "message": str(exc)}
        stderr_path.write_text(str(exc), encoding="utf-8")
        manifest.update({
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
            "warnings": warnings_list,
            "error": error,
        })

    finally:
        _write_json_atomic(manifest_path, manifest)

    return CADExportResult(
        status=status,
        run_root=output_dir,
        cad_dir=cad_dir,
        manifest_path=manifest_path,
        formats_requested=requested,
        formats_produced=tuple(produced),
        vspscript_path=vspscript_path if vspscript_path.exists() else None,
        step_path=step_path if step_path is not None and step_path.exists() else None,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        warnings=tuple(warnings_list),
    )

