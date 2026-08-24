"""Reproducible, bounded Claude Code peer-review runner for S7."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

try:  # package import and direct ``python claude_peer.py`` are both supported
    from .common import (
        POLICY_PATH,
        REPO_ROOT,
        atomic_write_text,
        digest_manifest,
        sha256_file,
        source_digest,
        tool_versions,
        verify_digest_manifest,
        write_json,
    )
except ImportError:  # pragma: no cover - direct CLI convenience
    from common import (
        POLICY_PATH,
        REPO_ROOT,
        atomic_write_text,
        digest_manifest,
        sha256_file,
        source_digest,
        tool_versions,
        verify_digest_manifest,
        write_json,
    )


def run_review(
    *,
    prompt_path: Path,
    output_dir: Path,
    model: str = "opus",
    effort: str = "max",
    permission_mode: str = "plan",
    timeout_s: float = 3600.0,
) -> dict:
    prompt_path = Path(prompt_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    prompt_copy = output_dir / "prompt.md"
    prompt_copy.write_bytes(prompt_path.read_bytes())
    stdout_path = output_dir / "claude_stdout.json"
    stderr_path = output_dir / "claude_stderr.log"
    command = [
        "/home/mike/.local/bin/claude",
        "--print",
        "--model",
        model,
        "--effort",
        effort,
        "--permission-mode",
        permission_mode,
        "--output-format",
        "json",
        "--no-session-persistence",
        prompt_copy.read_text(encoding="utf-8"),
    ]
    started = time.time()
    timed_out = False
    with (
        stdout_path.open("w", encoding="utf-8") as stdout,
        stderr_path.open("w", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
        )
        try:
            return_code = process.wait(timeout=float(timeout_s))
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                return_code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return_code = process.wait(timeout=30)
    parsed: dict | None = None
    parse_error: str | None = None
    try:
        value = json.loads(stdout_path.read_text(encoding="utf-8"))
        parsed = value if isinstance(value, dict) else {"value": value}
    except Exception as exc:
        parse_error = repr(exc)
    result_text = (
        parsed.get("result")
        if isinstance(parsed, dict) and isinstance(parsed.get("result"), str)
        else ""
    )
    review_text_path = output_dir / "review.md"
    atomic_write_text(review_text_path, result_text)
    model_usage = parsed.get("modelUsage", {}) if isinstance(parsed, dict) else {}
    model_verified = isinstance(model_usage, dict) and any(
        "opus" in str(name).lower() for name in model_usage
    )
    claude_error = bool(parsed.get("is_error")) if isinstance(parsed, dict) else True
    completed = bool(
        return_code == 0
        and not timed_out
        and parse_error is None
        and not claude_error
        and model_verified
        and result_text.strip()
    )
    report = {
        "schema": "aeris.s7.claude_peer_review.v1",
        "status": "completed" if completed else "failed",
        "model_requested": model,
        "effort_requested": effort,
        "permission_mode": permission_mode,
        "command_without_prompt": command[:-1] + ["<prompt-from-prompt.md>"],
        "return_code": int(return_code),
        "timed_out": timed_out,
        "wall_time_s": time.time() - started,
        "prompt": str(prompt_copy),
        "prompt_sha256": sha256_file(prompt_copy),
        "stdout": str(stdout_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr": str(stderr_path),
        "stderr_sha256": sha256_file(stderr_path),
        "parse_error": parse_error,
        "model_verified_from_usage": model_verified,
        "claude_reported_error": claude_error,
        "review_text": str(review_text_path),
        "review_text_sha256": sha256_file(review_text_path),
        "claude_result_metadata": (
            None
            if parsed is None
            else {
                key: parsed.get(key)
                for key in (
                    "type",
                    "subtype",
                    "is_error",
                    "duration_ms",
                    "duration_api_ms",
                    "num_turns",
                    "session_id",
                    "total_cost_usd",
                    "usage",
                    "modelUsage",
                )
                if key in parsed
            }
        ),
        "tool_versions": tool_versions(),
    }
    report_path = output_dir / "review_run.json"
    write_json(report_path, report)
    manifest = digest_manifest(
        {
            "policy": POLICY_PATH,
            "prompt": prompt_copy,
            "stdout": stdout_path,
            "stderr": stderr_path,
            "review": review_text_path,
            "run_report": report_path,
        },
        required={"policy", "prompt", "stdout", "stderr", "review", "run_report"},
    )
    verification = verify_digest_manifest(manifest)
    write_json(
        output_dir / "review_terminal.json",
        {
            "schema": "aeris.s7.claude_peer_review_terminal.v1",
            "status": report["status"],
            "source_digest": source_digest(),
            "policy_sha256": sha256_file(POLICY_PATH),
            "artifact_manifest": manifest,
            "artifact_verification": verification,
        },
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="opus")
    parser.add_argument("--effort", default="max")
    parser.add_argument("--permission-mode", default="plan")
    parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args()
    report = run_review(
        prompt_path=args.prompt,
        output_dir=args.output,
        model=args.model,
        effort=args.effort,
        permission_mode=args.permission_mode,
        timeout_s=args.timeout,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
