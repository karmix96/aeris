from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from aeris.quality.models import QCReport


def write_qc_report(report: QCReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")