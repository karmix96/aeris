from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .common import PipelineError, sha256_object, utc_now, write_csv, write_json
from .evidence import ACCEPTED_VERDICTS, parse_adflow_history, surface_payload_sha256

SCHEMA_VERSION = "aeris.campaign_monitor.v1"
STATUS_VALUES = ("RUNNING", "FAILED", "INCOMPLETE", "FINAL_ACCEPTED")
RUN_MARKERS = ("result.json", "run.log", "memory_watch.json")
SURFACE_PATTERNS = ("*_surf.cgns", "*_surf.cgns.gz", "*surf*.cgns", "*surf*.cgns.gz")
SKIP_PARTS = frozenset({"_superseded", "avl"})
NUMBER_FIELDS = (
    ("CL", "cl"),
    ("CD", "cd"),
    ("CDp", "cdp"),
    ("CDv", "cdv"),
    ("CMy", "cmy"),
)


class UnstableInput(PipelineError):
    """An input changed while the monitor was reading it."""


@dataclass(frozen=True)
class StableFile:
    path: Path
    sha256: str
    device: int
    inode: int
    size: int
    mtime_ns: int

    def public(self, repo: Path) -> dict[str, Any]:
        return {
            "path": _display_path(self.path, repo),
            "sha256": self.sha256,
            "device": self.device,
            "inode": self.inode,
            "bytes": self.size,
            "mtime_ns": self.mtime_ns,
        }


@dataclass
class IndexedValue:
    value: dict[str, Any]
    source: StableFile
    priority: int


@dataclass
class CampaignRun:
    run_id: str
    source_key: str
    directory: Path
    root: Path
    status: str
    reasons: list[str]
    warnings: list[str]
    row: dict[str, Any] | None
    result: dict[str, Any] | None
    gate: dict[str, Any] | None
    memory: dict[str, Any] | None
    surface: Path | None
    log: Path | None
    inputs: dict[str, StableFile] = field(default_factory=dict)
    surface_payload_sha256: str | None = None

    @property
    def geometry_key(self) -> str | None:
        if not self.row:
            return None
        geometry_hash = self.row.get("geometry_hash")
        if geometry_hash:
            return str(geometry_hash)
        geometry_set = self.row.get("geometry_set")
        geometry_index = self.row.get("geometry_index")
        if geometry_set is None or geometry_index is None:
            return None
        return f"{geometry_set}:{geometry_index}"

    def public(self, repo: Path) -> dict[str, Any]:
        row = self.row or {}
        result = self.result or {}
        mission = result.get("mission") or {}
        memory = self.memory or {}
        samples = memory.get("samples") or []
        wall_seconds = max(
            (float(sample.get("t", 0.0)) for sample in samples if isinstance(sample, dict)),
            default=None,
        )
        return {
            "run_id": self.run_id,
            "source_key": self.source_key,
            "source_directory": _display_path(self.directory, repo),
            "status": self.status,
            "reasons": self.reasons,
            "warnings": self.warnings,
            "geometry_set": row.get("geometry_set"),
            "geometry_index": row.get("geometry_index"),
            "geometry_hash": row.get("geometry_hash"),
            "grid_level": row.get("grid_level"),
            "alpha_deg": row.get("alpha_deg", result.get("alpha_deg")),
            "mach": row.get("mach", mission.get("mach")),
            "reynolds": row.get("reynolds", mission.get("reynolds")),
            "gate_verdict": (self.gate or {}).get("verdict"),
            "surface_payload_sha256": self.surface_payload_sha256,
            "peak_rank_rss_sum_gib": memory.get("peak_rank_rss_sum_gib"),
            "peak_swap_used_gib": memory.get("peak_swap_used_gib"),
            "observed_wall_seconds": wall_seconds,
            "inputs": {
                name: evidence.public(repo) for name, evidence in sorted(self.inputs.items())
            },
        }


@dataclass
class CampaignScan:
    repo: Path
    qualification_root: Path
    run_roots: tuple[Path, ...]
    records: list[CampaignRun]
    lock: dict[str, Any]
    indexed_inputs: dict[Path, StableFile]

    def report(self) -> dict[str, Any]:
        counts = Counter(record.status for record in self.records)
        accepted = [record for record in self.records if record.status == "FINAL_ACCEPTED"]
        geometries = sorted(
            {key for record in accepted if (key := record.geometry_key) is not None}
        )
        alerts: list[dict[str, Any]] = []
        if len(geometries) >= 3:
            alerts.append(
                {
                    "level": "INFO",
                    "code": "GEOMETRY_DISJOINT_TRAINING_READY",
                    "message": (
                        f"{len(geometries)} accepted geometries are available; geometry-disjoint "
                        "training and evaluation can be enabled."
                    ),
                }
            )
        else:
            alerts.append(
                {
                    "level": "INFO",
                    "code": "WAITING_FOR_GEOMETRIES",
                    "message": (
                        f"{len(geometries)} accepted geometries are available; at least 3 are "
                        "required for geometry-disjoint train/validation/test evaluation."
                    ),
                }
            )
        failed = counts.get("FAILED", 0)
        if failed:
            alerts.append(
                {
                    "level": "WARNING",
                    "code": "FAILED_RUNS_REQUIRE_REVIEW",
                    "message": f"{failed} run(s) failed scientific or evidence checks.",
                }
            )
        if self.lock.get("status") == "STALE":
            alerts.append(
                {
                    "level": "WARNING",
                    "code": "STALE_CAMPAIGN_LOCK",
                    "message": self.lock["message"],
                }
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "created_utc": utc_now(),
            "mode": "READ_ONLY",
            "qualification_root": _display_path(self.qualification_root, self.repo),
            "run_roots": [_display_path(root, self.repo) for root in self.run_roots],
            "status_values": list(STATUS_VALUES),
            "counts": {status: counts.get(status, 0) for status in STATUS_VALUES},
            "accepted_distinct_geometries": len(geometries),
            "accepted_geometry_keys": geometries,
            "training_ready": len(geometries) >= 3,
            "campaign_lock": self.lock,
            "alerts": alerts,
            "runs": [record.public(self.repo) for record in self.records],
            "source_inputs": [
                item.public(self.repo)
                for _, item in sorted(self.indexed_inputs.items(), key=lambda pair: str(pair[0]))
            ],
        }


def _signature(path: Path) -> tuple[int, int, int, int]:
    status = Path(path).stat()
    return (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns)


def stable_bytes(path: Path) -> tuple[bytes, StableFile]:
    source = Path(path).resolve()
    before = _signature(source)
    content = source.read_bytes()
    after = _signature(source)
    if before != after or len(content) != before[2]:
        raise UnstableInput(f"input changed while being read: {source}")
    return content, StableFile(
        source,
        hashlib.sha256(content).hexdigest(),
        before[0],
        before[1],
        before[2],
        before[3],
    )


def stable_json(path: Path) -> tuple[Any, StableFile]:
    content, evidence = stable_bytes(path)
    try:
        return json.loads(content), evidence
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"invalid JSON in {path}: {exc}") from exc


def stable_hash(path: Path) -> StableFile:
    source = Path(path).resolve()
    before = _signature(source)
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = _signature(source)
    if before != after:
        raise UnstableInput(f"input changed while being hashed: {source}")
    return StableFile(source, digest.hexdigest(), *before)


def verify_stable_file(evidence: StableFile) -> None:
    current = stable_hash(evidence.path)
    if current.sha256 != evidence.sha256:
        raise UnstableInput(f"input changed after campaign scan: {evidence.path}")


def _display_path(path: Path, repo: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(repo).resolve()))
    except ValueError:
        return str(Path(path).resolve())


def _resolve_record_path(value: Any, repo: Path) -> Path | None:
    if not value:
        return None
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (repo / path).resolve()


def _same_number(
    first: Any, second: Any, *, rel: float = 1.0e-9, absolute: float = 1.0e-11
) -> bool:
    try:
        return math.isclose(float(first), float(second), rel_tol=rel, abs_tol=absolute)
    except (TypeError, ValueError):
        return False


def _result_function(result: dict[str, Any], suffix: str) -> Any:
    matches = [
        value
        for name, value in (result.get("functions") or {}).items()
        if name.casefold().endswith("_" + suffix.casefold())
    ]
    return matches[0] if len(matches) == 1 else None


def _alpha_directory(alpha: Any) -> str | None:
    try:
        return f"a{float(alpha):g}"
    except (TypeError, ValueError):
        return None


def _excluded(path: Path) -> bool:
    return any(part in SKIP_PARTS or part.startswith(".") for part in path.parts)


def discover_run_directories(run_roots: Iterable[Path]) -> list[tuple[Path, Path]]:
    discovered: dict[Path, Path] = {}
    for configured in run_roots:
        root = Path(configured).expanduser().resolve()
        if not root.is_dir():
            continue
        candidates: set[Path] = set()
        for marker in RUN_MARKERS:
            candidates.update(path.parent.resolve() for path in root.rglob(marker))
        for pattern in SURFACE_PATTERNS:
            candidates.update(path.parent.resolve() for path in root.rglob(pattern))
        for directory in candidates:
            try:
                relative = directory.relative_to(root)
            except ValueError:
                continue
            if relative == Path(".") or _excluded(relative):
                continue
            discovered[directory] = root
    return sorted(discovered.items(), key=lambda item: (str(item[1]), str(item[0])))


def _put_index(
    index: dict[Path, list[IndexedValue]],
    directory: Path | None,
    value: dict[str, Any],
    source: StableFile,
    priority: int,
) -> None:
    if directory is not None:
        index.setdefault(directory.resolve(), []).append(IndexedValue(value, source, priority))


def _row_directories(row: dict[str, Any], source_path: Path, repo: Path) -> set[Path]:
    output: set[Path] = set()
    for field_name in ("source_directory", "surface_field_path"):
        resolved = _resolve_record_path(row.get(field_name), repo)
        if resolved:
            output.add(resolved.parent if field_name == "surface_field_path" else resolved)
    alpha_directory = _alpha_directory(row.get("alpha_deg"))
    if source_path.name == "dataset_rows.json" and alpha_directory:
        output.add((source_path.parent / alpha_directory).resolve())
    return output


def _load_row_index(
    qualification_root: Path, run_roots: tuple[Path, ...], repo: Path
) -> tuple[dict[Path, list[IndexedValue]], dict[Path, StableFile]]:
    index: dict[Path, list[IndexedValue]] = {}
    inputs: dict[Path, StableFile] = {}
    sources: list[tuple[Path, int]] = []
    published = qualification_root / "dataset/rows.json"
    if published.is_file():
        sources.append((published, 0))
    for root in run_roots:
        sources.extend((path, 1) for path in root.rglob("dataset_rows.json") if not _excluded(path))
    for source_path, priority in sorted(set(sources), key=lambda value: str(value[0])):
        payload, source = stable_json(source_path)
        inputs[source.path] = source
        rows = payload if isinstance(payload, list) else payload.get("rows", [])
        if not isinstance(rows, list):
            raise PipelineError(f"row sidecar has no row list: {source_path}")
        for row in rows:
            if not isinstance(row, dict):
                continue
            for directory in _row_directories(row, source_path, repo):
                _put_index(index, directory, row, source, priority)
    return index, inputs


def _gate_records(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("results"), list):
        return [record for record in payload["results"] if isinstance(record, dict)]
    return [payload] if "verdict" in payload or "passes" in payload else []


def _load_gate_index(
    qualification_root: Path, run_roots: tuple[Path, ...], repo: Path
) -> tuple[dict[Path, list[IndexedValue]], dict[Path, StableFile]]:
    index: dict[Path, list[IndexedValue]] = {}
    inputs: dict[Path, StableFile] = {}
    sources: list[tuple[Path, int]] = []
    reports = qualification_root / "reports"
    if reports.is_dir():
        sources.extend((path, 2) for path in reports.glob("*gate*.json"))
    published_runs = qualification_root / "dataset/runs"
    if published_runs.is_dir():
        sources.extend((path, 0) for path in published_runs.glob("*/gate.json"))
    for root in run_roots:
        sources.extend((path, 1) for path in root.rglob("gate.json") if not _excluded(path))
    for source_path, priority in sorted(set(sources), key=lambda value: str(value[0])):
        try:
            payload, source = stable_json(source_path)
        except PipelineError:
            continue
        records = _gate_records(payload)
        if not records:
            continue
        inputs[source.path] = source
        for gate in records:
            directory = _resolve_record_path(gate.get("directory"), repo)
            if directory is None and source_path.parent.parent.name == "runs":
                directory = source_path.parent.resolve()
            _put_index(index, directory, gate, source, priority)
    return index, inputs


def _choose_indexed(
    values: list[IndexedValue] | None, *, kind: str
) -> tuple[IndexedValue | None, list[str]]:
    if not values:
        return None, []
    ordered = sorted(values, key=lambda value: (value.priority, str(value.source.path)))
    chosen = ordered[0]
    core_hashes = {sha256_object(value.value) for value in ordered}
    warnings = []
    if len(core_hashes) > 1:
        warnings.append(f"multiple_nonidentical_{kind}_records")
    return chosen, warnings


def _surface_files(directory: Path) -> list[Path]:
    candidates: set[Path] = set()
    for pattern in SURFACE_PATTERNS:
        candidates.update(path.resolve() for path in directory.glob(pattern))
    return sorted(candidates)


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def inspect_lock(lock_path: Path | None, repo: Path) -> dict[str, Any]:
    if lock_path is None or not Path(lock_path).is_file():
        return {"status": "ABSENT", "path": None, "pid": None, "description": None}
    path = Path(lock_path).resolve()
    try:
        content, source = stable_bytes(path)
    except PipelineError as exc:
        return {"status": "UNSTABLE", "path": _display_path(path, repo), "message": str(exc)}
    text = content.decode(errors="replace").strip()
    match = re.search(r"\bpid\s+(\d+)\s+(.*)", text)
    pid = int(match.group(1)) if match else None
    description = match.group(2).strip() if match else text
    alive = bool(pid and _process_alive(pid))
    if alive:
        status = "ACTIVE"
        message = f"campaign lock belongs to live pid {pid}: {description}"
    else:
        status = "STALE"
        message = f"campaign lock has no live owner: {text or 'empty lock file'}"
    return {
        "status": status,
        "path": _display_path(path, repo),
        "pid": pid,
        "description": description,
        "sha256": source.sha256,
        "message": message,
    }


def _lock_matches(directory: Path, lock: dict[str, Any]) -> bool:
    if lock.get("status") != "ACTIVE":
        return False
    description = str(lock.get("description") or "")
    tokens = set(re.findall(r"[A-Za-z0-9_.+-]+", description))
    if directory.name in tokens:
        return True
    parent = directory.parent.name
    alpha = directory.name.removeprefix("a")
    return parent in tokens and alpha in tokens


def _recent(directory: Path, stale_after_seconds: float, now: float) -> bool:
    mtimes = [
        path.stat().st_mtime
        for path in directory.iterdir()
        if path.is_file() and not path.name.startswith(".")
    ]
    return bool(mtimes) and now - max(mtimes) <= stale_after_seconds


def _add_identity_reasons(
    reasons: list[str],
    warnings: list[str],
    row: dict[str, Any],
    result: dict[str, Any],
    gate: dict[str, Any],
) -> None:
    if not _same_number(result.get("alpha_deg"), row.get("alpha_deg")):
        reasons.append("result_alpha_disagrees_with_row")
    mission = result.get("mission") or {}
    for result_name, row_name in (("mach", "mach"), ("reynolds", "reynolds")):
        if not _same_number(mission.get(result_name), row.get(row_name)):
            reasons.append(f"result_{result_name}_disagrees_with_row")
    for row_name, suffix in NUMBER_FIELDS:
        if not _same_number(_result_function(result, suffix), row.get(row_name)):
            reasons.append(f"result_{suffix}_disagrees_with_row")

    if not _same_number(gate.get("alpha_deg"), row.get("alpha_deg")):
        reasons.append("gate_alpha_disagrees_with_row")
    forces = gate.get("forces") or {}
    for row_name, suffix in NUMBER_FIELDS:
        if not _same_number(forces.get(suffix), row.get(row_name)):
            reasons.append(f"gate_{suffix}_disagrees_with_row")
    embedded_verdict = row.get("gate_verdict")
    if embedded_verdict is None:
        warnings.append("row_gate_verdict_missing_using_authoritative_gate")
    elif embedded_verdict != gate.get("verdict"):
        reasons.append("row_gate_verdict_disagrees_with_gate")


def _classify_candidate(
    directory: Path,
    root: Path,
    repo: Path,
    row_values: list[IndexedValue] | None,
    gate_values: list[IndexedValue] | None,
    lock: dict[str, Any],
    stale_after_seconds: float,
    now: float,
) -> CampaignRun:
    relative = directory.relative_to(root)
    source_key = f"{root.name}/{relative.as_posix()}"
    run_id = re.sub(r"[^A-Za-z0-9_.-]+", "__", source_key).strip("._-")
    reasons: list[str] = []
    warnings: list[str] = []
    inputs: dict[str, StableFile] = {}
    active = _lock_matches(directory, lock) or any(
        (directory / marker).exists() for marker in (".running", "RUNNING", "running.json")
    )
    recent = _recent(directory, stale_after_seconds, now)

    row_indexed, row_warnings = _choose_indexed(row_values, kind="row")
    gate_indexed, gate_warnings = _choose_indexed(gate_values, kind="gate")
    warnings.extend(row_warnings)
    warnings.extend(gate_warnings)
    row = dict(row_indexed.value) if row_indexed else None
    gate = dict(gate_indexed.value) if gate_indexed else None
    if row_indexed:
        inputs["row_sidecar"] = row_indexed.source
    if gate_indexed:
        inputs["gate_sidecar"] = gate_indexed.source

    def read_mapping(name: str) -> dict[str, Any] | None:
        path = directory / name
        if not path.is_file():
            return None
        try:
            value, source = stable_json(path)
        except UnstableInput:
            warnings.append(f"unstable_{name}")
            return None
        except PipelineError:
            reasons.append(f"invalid_{name}")
            return None
        inputs[name] = source
        if not isinstance(value, dict):
            reasons.append(f"invalid_{name}_type")
            return None
        return value

    result = read_mapping("result.json")
    memory = read_mapping("memory_watch.json")
    log = directory / "run.log" if (directory / "run.log").is_file() else None
    history: list[dict[str, Any]] = []
    if log:
        try:
            log_bytes, log_source = stable_bytes(log)
            inputs["run.log"] = log_source
            history = parse_adflow_history(log_bytes.decode(errors="replace"))
            if not history:
                reasons.append("run_log_has_no_adflow_history")
        except UnstableInput:
            warnings.append("unstable_run.log")
            log = None
    else:
        reasons.append("missing_run_log")

    surfaces = _surface_files(directory)
    surface = surfaces[0] if len(surfaces) == 1 else None
    payload_hash = None
    if not surfaces:
        reasons.append("missing_surface_field")
    elif len(surfaces) > 1:
        reasons.append("ambiguous_surface_fields")
    else:
        try:
            surface_source = stable_hash(surface)
            inputs["surface_field"] = surface_source
            payload_hash = surface_payload_sha256(surface)
            if _signature(surface) != (
                surface_source.device,
                surface_source.inode,
                surface_source.size,
                surface_source.mtime_ns,
            ):
                raise UnstableInput(f"surface changed while payload was hashed: {surface}")
        except UnstableInput:
            warnings.append("unstable_surface_field")
            surface = None
            payload_hash = None

    explicit_failure = False
    if result is None:
        reasons.append("missing_result")
    else:
        if result.get("routine_failed") is not False:
            reasons.append("solver_routine_failed_or_unknown")
            explicit_failure = True
        if result.get("converged") is not True:
            reasons.append("solver_not_converged")
            explicit_failure = True
    if gate is None:
        reasons.append("missing_gate")
    else:
        if gate.get("passes") is not True or gate.get("verdict") not in ACCEPTED_VERDICTS:
            reasons.append(f"gate_{str(gate.get('verdict') or 'failed').lower()}")
            explicit_failure = True
    if row is None:
        reasons.append("missing_dataset_row")
    if memory is None:
        reasons.append("missing_memory_watch")
    else:
        if memory.get("aborted_reason"):
            reasons.append("memory_watch_aborted_run")
            explicit_failure = True
        if not isinstance(memory.get("samples"), list) or not memory.get("samples"):
            reasons.append("memory_watch_has_no_samples")

    if row is not None and result is not None and gate is not None:
        _add_identity_reasons(reasons, warnings, row, result, gate)
        expected_path = _resolve_record_path(row.get("surface_field_path"), repo)
        if expected_path and surface and expected_path != surface:
            reasons.append("row_surface_path_disagrees_with_run")
        expected_hash = row.get("surface_field_sha256")
        if expected_hash and payload_hash and expected_hash != payload_hash:
            reasons.append("surface_payload_hash_mismatch")
            explicit_failure = True
        elif not expected_hash and payload_hash:
            warnings.append("surface_hash_computed_during_monitoring")

    identity_failure = any("disagrees" in reason or "mismatch" in reason for reason in reasons)
    explicit_failure = (
        explicit_failure
        or identity_failure
        or any(
            reason.startswith("invalid_") or reason == "ambiguous_surface_fields"
            for reason in reasons
        )
    )
    transient = active or recent
    if explicit_failure:
        status = "FAILED"
    elif reasons:
        status = "RUNNING" if transient else "INCOMPLETE"
    else:
        status = "FINAL_ACCEPTED"
    return CampaignRun(
        run_id=run_id,
        source_key=source_key,
        directory=directory,
        root=root,
        status=status,
        reasons=sorted(set(reasons)),
        warnings=sorted(set(warnings)),
        row=row,
        result=result,
        gate=gate,
        memory=memory,
        surface=surface,
        log=log,
        inputs=inputs,
        surface_payload_sha256=payload_hash,
    )


def scan_campaign(
    qualification_root: Path,
    run_roots: Iterable[Path],
    *,
    lock_path: Path | None = None,
    stale_after_seconds: float = 1800.0,
    now: float | None = None,
) -> CampaignScan:
    qualification_root = Path(qualification_root).expanduser().resolve()
    if not (qualification_root / "dataset").is_dir():
        raise PipelineError(f"not a qualification evidence root: {qualification_root}")
    repo = next(
        (
            candidate
            for candidate in (qualification_root, *qualification_root.parents)
            if (candidate / ".git").exists()
        ),
        None,
    )
    if repo is None:
        raise PipelineError(f"cannot find repository above {qualification_root}")
    roots = tuple(Path(root).expanduser().resolve() for root in run_roots)
    if not roots:
        raise PipelineError("at least one campaign run root is required")
    row_index, row_inputs = _load_row_index(qualification_root, roots, repo)
    gate_index, gate_inputs = _load_gate_index(qualification_root, roots, repo)
    lock = inspect_lock(lock_path, repo)
    indexed_inputs = {**row_inputs, **gate_inputs}
    records = [
        _classify_candidate(
            directory,
            root,
            repo,
            row_index.get(directory),
            gate_index.get(directory),
            lock,
            float(stale_after_seconds),
            time.time() if now is None else float(now),
        )
        for directory, root in discover_run_directories(roots)
    ]
    identifiers = [record.run_id for record in records]
    duplicates = [name for name, count in Counter(identifiers).items() if count > 1]
    if duplicates:
        raise PipelineError(f"campaign roots produce duplicate run identifiers: {duplicates}")
    for record in records:
        indexed_inputs.update((item.path, item) for item in record.inputs.values())
    return CampaignScan(repo, qualification_root, roots, records, lock, indexed_inputs)


def restart_recommendations(scan: CampaignScan) -> list[dict[str, Any]]:
    output = []
    for run in scan.records:
        if run.status == "FINAL_ACCEPTED":
            action = "NONE"
        elif run.status == "RUNNING":
            action = "WAIT_AND_RESCAN"
        elif run.status == "FAILED":
            action = "REVIEW_THEN_RERUN_IN_NEW_DIRECTORY"
        elif "missing_gate" in run.reasons:
            action = "RUN_GATE_THEN_REPUBLISH_SIDECAR"
        elif "missing_dataset_row" in run.reasons:
            action = "PUBLISH_DATASET_SIDECAR"
        else:
            action = "REVIEW_INCOMPLETE_EVIDENCE"
        output.append(
            {
                "run_id": run.run_id,
                "status": run.status,
                "recommended_action": action,
                "automatic_action_taken": False,
                "overwrite_existing_directory": False,
                "reasons": run.reasons,
            }
        )
    return output


def write_monitor_outputs(scan: CampaignScan, output: Path) -> dict[str, Any]:
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = scan.report()
    write_json(output / "status.json", report)
    rows = report["runs"]
    columns = (
        "run_id",
        "source_key",
        "status",
        "geometry_set",
        "geometry_index",
        "geometry_hash",
        "grid_level",
        "alpha_deg",
        "mach",
        "reynolds",
        "gate_verdict",
        "peak_rank_rss_sum_gib",
        "peak_swap_used_gib",
        "observed_wall_seconds",
        "surface_payload_sha256",
        "reasons",
        "warnings",
    )
    write_csv(output / "status.csv", rows, columns)
    write_json(output / "alerts.json", {"alerts": report["alerts"]})
    recommendations = restart_recommendations(scan)
    write_json(
        output / "restart_recommendations.json",
        {
            "schema_version": "aeris.restart_recommendations.v1",
            "created_utc": utc_now(),
            "mode": "ADVISORY_ONLY",
            "recommendations": recommendations,
        },
    )
    return report
