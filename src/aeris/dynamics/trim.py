from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json


@dataclass(frozen=True)
class LongitudinalTrimEstimate:
    alpha_current_deg: float | None
    cm_current: float | None
    cma_per_rad: float | None
    delta_alpha_rad: float | None
    delta_alpha_deg: float | None
    alpha_trim_deg: float | None
    valid: bool
    reason: str | None = None


@dataclass(frozen=True)
class TrimResult:
    schema_version: str
    run_dir: str
    mode: str
    longitudinal: LongitudinalTrimEstimate
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _get(obj, *names):
    def search_dict(d):
        for k, v in d.items():
            if k in names and v is not None:
                return v
            if isinstance(v, dict):
                found = search_dict(v)
                if found is not None:
                    return found
        return None

    if isinstance(obj, dict):
        return search_dict(obj)

    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value

    return None


def estimate_longitudinal_trim(aero_result: dict, run_dir: str | Path) -> TrimResult:
    alpha_current_deg = _get(
        aero_result,
        "alpha_deg",
    )

    if alpha_current_deg is None:
        solver_meta = aero_result.get("solver_metadata", {})
        flight_condition = solver_meta.get("flight_condition", {})
        alpha_current_deg = flight_condition.get("alpha_deg")

    cm_current = _get(aero_result, "cm", "Cm")
    cma_per_rad = _get(aero_result, "Cma", "cma")

    if alpha_current_deg is None:
        longitudinal = LongitudinalTrimEstimate(
            alpha_current_deg=None,
            cm_current=cm_current,
            cma_per_rad=cma_per_rad,
            delta_alpha_rad=None,
            delta_alpha_deg=None,
            alpha_trim_deg=None,
            valid=False,
            reason="Missing current alpha.",
        )
        return TrimResult(
            schema_version="0.1.0",
            run_dir=str(run_dir),
            mode="longitudinal_control_fixed_linearized",
            longitudinal=longitudinal,
        )

    if cm_current is None:
        longitudinal = LongitudinalTrimEstimate(
            alpha_current_deg=alpha_current_deg,
            cm_current=None,
            cma_per_rad=cma_per_rad,
            delta_alpha_rad=None,
            delta_alpha_deg=None,
            alpha_trim_deg=None,
            valid=False,
            reason="Missing Cm.",
        )
        return TrimResult(
            schema_version="0.1.0",
            run_dir=str(run_dir),
            mode="longitudinal_control_fixed_linearized",
            longitudinal=longitudinal,
        )

    if cma_per_rad is None:
        longitudinal = LongitudinalTrimEstimate(
            alpha_current_deg=alpha_current_deg,
            cm_current=cm_current,
            cma_per_rad=None,
            delta_alpha_rad=None,
            delta_alpha_deg=None,
            alpha_trim_deg=None,
            valid=False,
            reason="Missing Cma.",
        )
        return TrimResult(
            schema_version="0.1.0",
            run_dir=str(run_dir),
            mode="longitudinal_control_fixed_linearized",
            longitudinal=longitudinal,
        )

    if abs(cma_per_rad) < 1e-12:
        longitudinal = LongitudinalTrimEstimate(
            alpha_current_deg=alpha_current_deg,
            cm_current=cm_current,
            cma_per_rad=cma_per_rad,
            delta_alpha_rad=None,
            delta_alpha_deg=None,
            alpha_trim_deg=None,
            valid=False,
            reason="Cma too close to zero for linear trim estimate.",
        )
        return TrimResult(
            schema_version="0.1.0",
            run_dir=str(run_dir),
            mode="longitudinal_control_fixed_linearized",
            longitudinal=longitudinal,
        )

    delta_alpha_rad = -cm_current / cma_per_rad
    delta_alpha_deg = delta_alpha_rad * 180.0 / 3.141592653589793
    alpha_trim_deg = alpha_current_deg + delta_alpha_deg

    longitudinal = LongitudinalTrimEstimate(
        alpha_current_deg=float(alpha_current_deg),
        cm_current=float(cm_current),
        cma_per_rad=float(cma_per_rad),
        delta_alpha_rad=float(delta_alpha_rad),
        delta_alpha_deg=float(delta_alpha_deg),
        alpha_trim_deg=float(alpha_trim_deg),
        valid=True,
        reason=None,
    )

    return TrimResult(
        schema_version="0.1.0",
        run_dir=str(run_dir),
        mode="longitudinal_control_fixed_linearized",
        longitudinal=longitudinal,
        metadata={
            "assumption": "Linearized control-fixed trim estimate using current Cm and Cma at the operating point."
        },
    )


def write_trim_result(result: TrimResult, output_dir: str | Path) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "trim_result.json"
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return path