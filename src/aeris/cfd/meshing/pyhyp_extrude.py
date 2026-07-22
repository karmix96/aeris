"""
pyHyp extrusion execution: subprocess runner, march-metrics QC, reports.

The subprocess path works by serializing the fully resolved options to
``pyhyp_options.json`` and dropping a short, *static* runner script beside
it.  The runner contains no baked-in values — it just loads the JSON and
calls pyHyp — so there is exactly one place options are computed
(``build_pyhyp_options``) and the generated pair stays standalone
re-runnable for cluster debugging: ``<mach-aero python> run_pyhyp.py``.

March validity policy (see ``parse_pyhyp_march_metrics``): a negative
marched cell *volume* is a hard failure (inverted cell, mesh unusable,
CGNS quarantined); a negative scaled *quality* with positive volume is a
warning (skewed but usable — expected at blunt-TE tip corners, matching
MDO Lab practice for BWB tip meshes).

That policy reads the march *log*, which reports only per-layer extrema
and which pyHyp writes even for runs it goes on to finish with an exit
code of 0.  Every successful extrusion is therefore also audited
geometrically (``aeris.cfd.meshing.volume_audit``) against the CGNS that
was actually written, which is what supplies the extent and location of a
defect — the facts needed to classify a failure rather than merely detect
one.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path

from aeris.cfd.env import mach_aero_python
from aeris.cfd.meshing.volume_audit import (
    VOLUME_AUDIT_SCHEMA_VERSION,
    audit_volume_cgns,
    summarize_audit,
)
from aeris.cfd.options.layers import EffectiveOptions
from aeris.cfd.options.manifest import write_effective_options_manifest

VOLUME_REPORT_SCHEMA_VERSION = "aeris.pyhyp_volume_report.v1"

OPTIONS_JSON_NAME = "pyhyp_options.json"
MANIFEST_NAME = "pyhyp_effective_options.json"
RUNNER_NAME = "run_pyhyp.py"

_RUNNER_TEMPLATE = '''\
#!/usr/bin/env python3
"""Auto-generated static pyHyp runner (aeris.cfd) — options come from
pyhyp_options.json next to this script; this file bakes in nothing."""
import json
from pathlib import Path


def main():
    here = Path(__file__).parent
    options = json.loads((here / "pyhyp_options.json").read_text())
    if options.get("BC"):
        # JSON stringifies the 1-based integer block ids pyHyp requires
        options["BC"] = {int(block): edges for block, edges in options["BC"].items()}

    from pyhyp import pyHyp as PyHyp

    hyp = PyHyp(options=options)
    hyp.run()
    hyp.writeCGNS(options["outputFile"])
    print(f"pyHyp done -> {options['outputFile']}", flush=True)


if __name__ == "__main__":
    main()
'''


def write_pyhyp_run_inputs(surface_dir: Path, effective: EffectiveOptions) -> Path:
    """Write options JSON, provenance manifest, and static runner.

    Returns the runner path. ``outputFile`` must be resolved in the
    effective options before calling.
    """
    if "outputFile" not in effective.values:
        raise ValueError("effective pyHyp options must include outputFile")

    options_path = surface_dir / OPTIONS_JSON_NAME
    options_path.write_text(
        json.dumps(effective.values, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    input_file = effective.values.get("inputFile")
    write_effective_options_manifest(
        surface_dir / MANIFEST_NAME,
        effective=effective,
        input_files={"surface": Path(str(input_file))} if input_file else None,
    )
    runner = surface_dir / RUNNER_NAME
    runner.write_text(_RUNNER_TEMPLATE, encoding="utf-8")
    return runner


def resolve_characteristic_length(
    surface_dir: Path, characteristic_length: float | None = None
) -> float:
    """Return the given length or read it from surface_report.json."""
    if characteristic_length is None:
        report_path = surface_dir / "surface_report.json"
        if report_path.is_file():
            try:
                report = json.loads(report_path.read_text())
                characteristic_length = float(report["characteristic_length"])
            except (KeyError, ValueError, json.JSONDecodeError):
                characteristic_length = None
    if not characteristic_length or not (characteristic_length > 0):
        raise ValueError(
            "characteristic_length must be provided or readable from surface_report.json."
        )
    return float(characteristic_length)


def _parse_float_token(token: str) -> float:
    try:
        value = float(token)
    except ValueError:
        return math.nan
    return value if math.isfinite(value) else math.nan


def parse_pyhyp_march_metrics(text: str) -> dict[str, object]:
    """Parse pyHyp's per-layer marching table into QC metrics."""
    rows: list[dict[str, float | int | bool]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 10 or not parts[0].isdigit():
            continue
        min_quality = _parse_float_token(parts[8])
        min_volume = _parse_float_token(parts[9])
        volume_valid = math.isfinite(min_volume) and min_volume > 0.0
        quality_ok = math.isfinite(min_quality) and min_quality > 0.0
        rows.append(
            {
                "grid_level": int(parts[0]),
                "min_quality": min_quality,
                "min_volume": min_volume,
                "volume_valid": volume_valid,
                "quality_ok": quality_ok,
                # kept for backward compatibility: overall per-row validity
                "valid": volume_valid and quality_ok,
            }
        )

    if not rows:
        return {
            "rows": [],
            "min_quality": None,
            "min_volume": None,
            "passed": None,
            "quality_warning": None,
        }

    min_quality = min(float(row["min_quality"]) for row in rows)
    min_volume = min(float(row["min_volume"]) for row in rows)
    first_invalid_layer = next(
        (int(row["grid_level"]) for row in rows if not bool(row["volume_valid"])),
        None,
    )
    first_low_quality_layer = next(
        (int(row["grid_level"]) for row in rows if not bool(row["quality_ok"])),
        None,
    )
    low_quality_layers = sum(1 for row in rows if not bool(row["quality_ok"]))
    passed = first_invalid_layer is None
    return {
        "rows": rows,
        "min_quality": min_quality,
        "min_volume": min_volume,
        "first_invalid_layer": first_invalid_layer,
        "first_low_quality_layer": first_low_quality_layer,
        "low_quality_layers": low_quality_layers,
        "layer_count": len(rows),
        "quality_warning": first_low_quality_layer is not None,
        "passed": passed,
    }


def write_volume_report(
    surface_dir: Path,
    *,
    status: str,
    output_cgns: Path,
    march_metrics: dict[str, object],
    volume_audit: dict[str, object] | None = None,
    error: str | None = None,
) -> Path:
    report = {
        "schema": VOLUME_REPORT_SCHEMA_VERSION,
        "status": status,
        "output_cgns": str(output_cgns),
        "march_metrics": march_metrics,
    }
    if volume_audit is not None:
        report["volume_audit"] = volume_audit
    if error is not None:
        report["error"] = error
    path = surface_dir / "volume_report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def quarantine_invalid_cgns(output_cgns: Path) -> Path | None:
    """Rename an invalid CGNS to *.invalid.cgns so no solver picks it up."""
    if not output_cgns.exists():
        return None
    invalid_path = output_cgns.with_name(output_cgns.stem + ".invalid" + output_cgns.suffix)
    try:
        invalid_path.unlink()
    except FileNotFoundError:
        pass
    output_cgns.rename(invalid_path)
    return invalid_path


def audit_written_mesh(output_cgns: Path) -> dict[str, object]:
    """Audit the written CGNS, reporting rather than raising on failure.

    A campaign must classify every outcome rather than crash, so an audit
    that cannot run (unreadable file, unexpected CGNS layout) comes back
    classified ``audit_failed`` and the caller falls back to the march-log
    verdict, instead of taking the run down with it.
    """
    try:
        return audit_volume_cgns(output_cgns)
    except Exception as exc:  # noqa: BLE001 - audit is diagnostic, never fatal
        return {
            "schema": VOLUME_AUDIT_SCHEMA_VERSION,
            "classification": "audit_failed",
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_pyhyp_subprocess(
    surface_dir: Path,
    effective: EffectiveOptions,
    *,
    python_executable: str | None = None,
) -> dict[str, object]:
    """Extrude the volume mesh in a mach-aero subprocess and QC the march.

    Writes run inputs, executes the static runner, parses the march table,
    quarantines invalid output, and writes ``volume_report.json``.
    """
    surface_dir = surface_dir.resolve()
    runner = write_pyhyp_run_inputs(surface_dir, effective)
    python = python_executable or str(mach_aero_python())
    output_cgns = Path(str(effective.values["outputFile"]))

    t0 = time.perf_counter()
    result = subprocess.run(
        [python, str(runner)],
        capture_output=True,
        text=True,
        cwd=str(surface_dir),
    )
    elapsed = time.perf_counter() - t0

    stdout_path = surface_dir / "pyhyp_stdout.log"
    stderr_path = surface_dir / "pyhyp_stderr.log"
    stdout_path.write_text(result.stdout, encoding="utf-8")
    stderr_path.write_text(result.stderr, encoding="utf-8")

    if result.returncode != 0:
        tail = result.stderr[-2000:] if result.stderr else "(no stderr)"
        raise RuntimeError(
            f"pyHyp subprocess exited {result.returncode}.\n{tail}\nLog: {stderr_path}"
        )

    march_metrics = parse_pyhyp_march_metrics(result.stdout + "\n" + result.stderr)

    if not output_cgns.is_file() or output_cgns.stat().st_size == 0:
        error = f"pyHyp subprocess succeeded but output missing: {output_cgns}"
        write_volume_report(
            surface_dir,
            status="missing_output",
            output_cgns=output_cgns,
            march_metrics=march_metrics,
            error=error,
        )
        raise RuntimeError(error)
    # pyHyp exiting 0 does not mean the mesh is sound: it reports a negative
    # minimum volume for a layer and then keeps marching, so the written file
    # can contain inverted cells.  Audit the geometry that was actually
    # written rather than trusting the log alone, and use it to say *where*
    # and *how bad* — the march table only gives per-layer extrema.
    volume_audit = audit_written_mesh(output_cgns)

    # "audit_failed" means the check itself could not run — that is not
    # evidence against the mesh, so fall back to the march-log verdict.
    audit_classification = (volume_audit or {}).get("classification")
    audit_rejects = audit_classification not in (None, "clean", "audit_failed")
    if march_metrics.get("passed") is False or audit_rejects:
        invalid_path = quarantine_invalid_cgns(output_cgns)
        detail = (
            summarize_audit(volume_audit)
            if audit_classification not in (None, "audit_failed")
            else "(volume audit unavailable)"
        )
        error = (
            "pyHyp subprocess produced invalid marched volume metrics: "
            f"min_volume={march_metrics.get('min_volume')}, "
            f"min_quality={march_metrics.get('min_quality')}, "
            f"first_invalid_layer={march_metrics.get('first_invalid_layer')}.\n"
            f"{detail}\n"
            f"Invalid CGNS moved to {invalid_path}. Inspect {stdout_path}."
        )
        write_volume_report(
            surface_dir,
            status="invalid",
            output_cgns=invalid_path or output_cgns,
            march_metrics=march_metrics,
            volume_audit=volume_audit,
            error=error,
        )
        raise RuntimeError(error)
    write_volume_report(
        surface_dir,
        status="valid",
        output_cgns=output_cgns,
        march_metrics=march_metrics,
        volume_audit=volume_audit,
    )

    return {
        "coarsen": effective.values["coarsen"],
        "N": effective.values["N"],
        "s0": effective.values["s0"],
        "march_distance": effective.values["marchDist"],
        "effective_options": str(surface_dir / MANIFEST_NAME),
        "quality_warning": march_metrics.get("quality_warning"),
        "low_quality_layers": march_metrics.get("low_quality_layers"),
        "volume_audit": volume_audit,
        "output_cgns": str(output_cgns),
        "output_size_bytes": int(output_cgns.stat().st_size),
        "elapsed_seconds": elapsed,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "march_metrics": march_metrics,
    }
