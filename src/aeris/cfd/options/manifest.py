"""
Effective-options manifest: the reproducibility record of a tool invocation.

Every prepare step writes one manifest per tool recording the fully resolved
option set with per-key provenance, any curated-option overrides via raw
pass-through, and sha256 fingerprints of the input files.  This is the audit
trail that makes a mesh or solve defensible: given the manifest, the run is
exactly reconstructable (AIAA CFD verification practice; NASA CFD Vision
2030 traceability goals).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from aeris.cfd.options.layers import EffectiveOptions
from aeris.common.config import file_sha256

EFFECTIVE_OPTIONS_SCHEMA_VERSION = "aeris.cfd.effective_options.v1"


def write_effective_options_manifest(
    path: Path,
    *,
    effective: EffectiveOptions,
    input_files: Mapping[str, Path] | None = None,
    extra: Mapping[str, object] | None = None,
) -> Path:
    """Write the manifest JSON and return its path.

    Missing input files are recorded with a ``null`` fingerprint rather than
    failing the run — the manifest must never be the reason a solve dies.
    """
    fingerprints: dict[str, str | None] = {}
    for label, file_path in (input_files or {}).items():
        p = Path(file_path)
        fingerprints[label] = file_sha256(p) if p.is_file() else None

    payload: dict[str, object] = {
        "schema": EFFECTIVE_OPTIONS_SCHEMA_VERSION,
        "tool": effective.tool,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "options": {
            key: {"value": value, "source": effective.provenance.get(key, "unknown")}
            for key, value in sorted(effective.values.items())
        },
        "warnings": list(effective.warnings),
        "overridden_curated_keys": list(effective.overridden_curated_keys),
        "input_sha256": fingerprints,
    }
    if extra:
        payload["extra"] = dict(extra)

    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return path
