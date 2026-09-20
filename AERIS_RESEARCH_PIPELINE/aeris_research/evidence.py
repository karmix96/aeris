from __future__ import annotations

import gzip
import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import InputLedger, PipelineError

ACCEPTED_VERDICTS = frozenset({"ACCEPTED"})
ITERATION_LINE = re.compile(
    r"^\s*(?P<grid>\d+)\s+(?P<iteration>\d+)\s+(?P<inner>\d+)\s+"
    r"(?P<solver>\*?[A-Za-z]+)\s+"
)


def _same_number(first: Any, second: Any) -> bool:
    try:
        return math.isclose(float(first), float(second), rel_tol=1.0e-9, abs_tol=1.0e-11)
    except (TypeError, ValueError):
        return False


def _result_function(result: dict[str, Any], suffix: str) -> Any:
    matches = [
        value
        for name, value in (result.get("functions") or {}).items()
        if name.casefold().endswith("_" + suffix.casefold())
    ]
    return matches[0] if len(matches) == 1 else None


def surface_payload_sha256(path: Path) -> str:
    """Hash the CGNS payload; archive metadata records this, not gzip bytes."""

    digest = hashlib.sha256()
    try:
        stream_context = (
            gzip.open(path, "rb") if Path(path).suffix == ".gz" else Path(path).open("rb")
        )
        with stream_context as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except (gzip.BadGzipFile, EOFError) as exc:
        raise PipelineError(f"invalid surface archive {path}: {exc}") from exc
    return digest.hexdigest()


@dataclass(frozen=True)
class RunEvidence:
    row: dict[str, Any]
    result: dict[str, Any] | None
    gate: dict[str, Any] | None
    memory: dict[str, Any] | None
    archive: Path | None
    log: Path | None
    status: str
    reasons: tuple[str, ...]


class QualificationEvidence:
    """Read-only view over one qualification evidence package."""

    def __init__(self, qualification_root: Path, ledger: InputLedger | None = None):
        self.root = Path(qualification_root).resolve()
        self.repo = self._find_repo(self.root)
        self.dataset = self.root / "dataset"
        self.reports = self.root / "reports"
        self.ledger = ledger or InputLedger()
        if not self.dataset.is_dir() or not self.reports.is_dir():
            raise PipelineError(f"not a qualification evidence root: {self.root}")

    @staticmethod
    def _find_repo(path: Path) -> Path:
        for candidate in (path, *path.parents):
            if (candidate / ".git").exists() and (candidate / "AERIS_MESH_STUDY").is_dir():
                return candidate
        raise PipelineError(f"cannot find AERIS repository above {path}")

    def json(self, path: Path, *, optional: bool = False) -> Any:
        if optional and not path.is_file():
            return None
        return self.ledger.read_json(path)

    @property
    def rows(self) -> list[dict[str, Any]]:
        rows = self.json(self.dataset / "rows.json")
        if not isinstance(rows, list):
            raise PipelineError("dataset/rows.json must contain a list")
        return rows

    @property
    def manifest(self) -> dict[str, Any]:
        value = self.json(self.dataset / "MANIFEST.json")
        if not isinstance(value, dict):
            raise PipelineError("dataset/MANIFEST.json must contain an object")
        return value

    def report(self, name: str, *, optional: bool = False) -> Any:
        return self.json(self.reports / name, optional=optional)

    def run_file(self, run_name: str, name: str) -> Path:
        return self.dataset / "runs" / run_name / name

    def field_archive(self, row: dict[str, Any]) -> Path | None:
        relative = row.get("surface_field_archive")
        if not relative:
            return None
        candidate = Path(relative)
        return candidate if candidate.is_absolute() else self.dataset / candidate

    def run_log(self, row: dict[str, Any]) -> Path | None:
        candidates: list[Path] = []
        source = row.get("source_directory")
        if source:
            source_path = Path(source)
            candidates.append(source_path / "run.log")
            if not source_path.is_absolute():
                candidates.append(self.repo / source_path / "run.log")
        run_name = row.get("run_name")
        if run_name:
            candidates.append(
                self.repo / "AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_cfd" / run_name / "run.log"
            )
        return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)

    def classify(self, row: dict[str, Any]) -> RunEvidence:
        run_name = str(row.get("run_name", ""))
        if not run_name:
            raise PipelineError("dataset row has no run_name")
        result = self.json(self.run_file(run_name, "result.json"), optional=True)
        gate = self.json(self.run_file(run_name, "gate.json"), optional=True)
        memory = self.json(self.run_file(run_name, "memory_watch.json"), optional=True)
        archive = self.field_archive(row)
        reasons: list[str] = []

        if not isinstance(result, dict):
            reasons.append("missing_result")
        else:
            if result.get("routine_failed") is not False:
                reasons.append("solver_routine_failed_or_unknown")
            if result.get("converged") is not True:
                reasons.append("solver_not_converged")
            if not _same_number(result.get("alpha_deg"), row.get("alpha_deg")):
                reasons.append("result_alpha_disagrees_with_row")
            mission = result.get("mission") or {}
            for result_name, row_name in (("mach", "mach"), ("reynolds", "reynolds")):
                if not _same_number(mission.get(result_name), row.get(row_name)):
                    reasons.append(f"result_{result_name}_disagrees_with_row")
            for row_name, suffix in (
                ("CL", "cl"),
                ("CD", "cd"),
                ("CDp", "cdp"),
                ("CDv", "cdv"),
                ("CMy", "cmy"),
            ):
                if not _same_number(_result_function(result, suffix), row.get(row_name)):
                    reasons.append(f"result_{suffix}_disagrees_with_row")

        if not isinstance(gate, dict):
            reasons.append("missing_gate")
        else:
            if gate.get("passes") is not True:
                reasons.append("gate_failed")
            if gate.get("verdict") not in ACCEPTED_VERDICTS:
                reasons.append(f"gate_verdict_{gate.get('verdict') or 'missing'}")
            if not _same_number(gate.get("alpha_deg"), row.get("alpha_deg")):
                reasons.append("gate_alpha_disagrees_with_row")
            gate_forces = gate.get("forces") or {}
            for row_name, gate_name in (
                ("CL", "cl"),
                ("CD", "cd"),
                ("CDp", "cdp"),
                ("CDv", "cdv"),
                ("CMy", "cmy"),
            ):
                if not _same_number(gate_forces.get(gate_name), row.get(row_name)):
                    reasons.append(f"gate_{gate_name}_disagrees_with_row")

        if archive is None or not archive.is_file():
            reasons.append("missing_surface_archive")
            archive = None
        else:
            self.ledger.track(archive)
            expected = row.get("surface_field_sha256")
            if not expected:
                reasons.append("missing_surface_hash")
            elif surface_payload_sha256(archive) != expected:
                reasons.append("surface_hash_mismatch")

        row_verdict = row.get("gate_verdict")
        if isinstance(gate, dict) and row_verdict != gate.get("verdict"):
            reasons.append("row_gate_disagrees_with_gate_file")

        if reasons:
            integrity = any(
                reason.endswith("mismatch") or "disagrees" in reason for reason in reasons
            )
            failed = any(
                reason
                in {"solver_routine_failed_or_unknown", "solver_not_converged", "gate_failed"}
                for reason in reasons
            )
            status = "INTEGRITY_ERROR" if integrity else "FAILED" if failed else "INCOMPLETE"
        else:
            status = "FINAL_ACCEPTED"
        log = self.run_log(row)
        return RunEvidence(row, result, gate, memory, archive, log, status, tuple(reasons))

    def runs(self) -> list[RunEvidence]:
        return [self.classify(row) for row in self.rows]


def parse_adflow_history(text: str) -> list[dict[str, Any]]:
    """Parse the stable ADflow iteration table without depending on solver code."""

    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = ITERATION_LINE.match(line)
        if not match:
            continue
        tokens = line.split()
        if len(tokens) < 19:
            continue
        try:
            numeric = [float(value) for value in tokens[4:]]
        except ValueError:
            continue
        if len(numeric) < 15:
            continue
        record = {
            "grid": int(tokens[0]),
            "iteration": int(tokens[1]),
            "inner_iterations": int(tokens[2]),
            "solver": tokens[3].lstrip("*"),
            "preconditioner_updated": tokens[3].startswith("*"),
            "cfl": numeric[0],
            "step": numeric[1],
            "linear_residual": numeric[2],
            "cl": numeric[9],
            "cd": numeric[10],
            "cdp": numeric[11],
            "cdv": numeric[12],
            "cmy": numeric[13],
            "total_residual": numeric[14],
        }
        if all(math.isfinite(float(record[key])) for key in ("cl", "cd", "cmy", "total_residual")):
            records.append(record)
    if records:
        initial = records[0]["total_residual"]
        for record in records:
            record["relative_residual"] = record["total_residual"] / initial if initial else None
    return records
