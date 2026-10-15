from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


class PipelineError(RuntimeError):
    """A failure that should stop a research product from being published."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_object(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def reject_output_inside_inputs(output: Path, forbidden_roots: Iterable[Path]) -> Path:
    destination = _resolved(output)
    for root in forbidden_roots:
        protected = _resolved(root)
        if destination == protected or protected in destination.parents:
            raise PipelineError(f"output {destination} is inside protected input tree {protected}")
    return destination


@dataclass
class InputLedger:
    """Hash every input on first access and detect changes during a build."""

    records: dict[Path, str] = field(default_factory=dict)

    def track(self, path: Path) -> Path:
        source = _resolved(path)
        if not source.is_file():
            raise PipelineError(f"required input does not exist: {source}")
        digest = sha256_file(source)
        previous = self.records.setdefault(source, digest)
        if previous != digest:
            raise PipelineError(f"input changed between reads: {source}")
        return source

    def read_bytes(self, path: Path) -> bytes:
        return self.track(path).read_bytes()

    def read_text(self, path: Path) -> str:
        return self.track(path).read_text(encoding="utf-8")

    def read_json(self, path: Path) -> Any:
        try:
            return json.loads(self.read_text(path))
        except json.JSONDecodeError as exc:
            raise PipelineError(f"invalid JSON in {path}: {exc}") from exc

    def verify_unchanged(self) -> None:
        changed = [
            str(path) for path, digest in self.records.items() if sha256_file(path) != digest
        ]
        if changed:
            raise PipelineError("input evidence changed during build: " + ", ".join(changed))

    def manifest(self, relative_to: Path | None = None) -> list[dict[str, str]]:
        rows = []
        base = _resolved(relative_to) if relative_to else None
        for path, digest in sorted(self.records.items(), key=lambda item: str(item[0])):
            try:
                display = str(path.relative_to(base)) if base else str(path)
            except ValueError:
                display = str(path)
            rows.append({"path": display, "sha256": digest})
        return rows


def atomic_write_bytes(path: Path, content: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path: Path, content: str) -> None:
    atomic_write_bytes(path, content.encode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _normalise_csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(columns), extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {column: _normalise_csv_value(row.get(column)) for column in columns}
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def latex_escape(value: Any) -> str:
    text = str(_normalise_csv_value(value))
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(character, character) for character in text)


def write_latex_table(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    *,
    caption: str,
    label: str,
) -> None:
    alignment = "l" + "r" * max(0, len(columns) - 1)
    resize = len(columns) > 7
    lines = [
        r"\begin{table}[tb]",
        r"\centering",
        r"\small",
    ]
    if resize:
        lines.append(r"\resizebox{\linewidth}{!}{%")
    lines.extend(
        [
            rf"\begin{{tabular}}{{{alignment}}}",
            r"\toprule",
            " & ".join(latex_escape(column) for column in columns) + " \\\\",
            r"\midrule",
        ]
    )
    for row in rows:
        lines.append(" & ".join(latex_escape(row.get(column)) for column in columns) + " \\\\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    if resize:
        lines.append("}")
    lines.extend(
        [
            rf"\caption{{{latex_escape(caption)}}}",
            rf"\label{{{latex_escape(label)}}}",
            r"\end{table}",
        ]
    )
    atomic_write_text(path, "\n".join(lines) + "\n")


def output_manifest(root: Path, *, exclude: Iterable[str] = ()) -> list[dict[str, Any]]:
    root = _resolved(root)
    excluded = set(exclude)
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = str(path.relative_to(root))
        if relative in excluded:
            continue
        rows.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return rows
