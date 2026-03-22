from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from aeris.dynamics.models import (
    DynamicsFoundationResult,
    MassProperties,
    StabilityMetrics,
    StateSpacePreparation,
    TrimDefinition,
)

from pathlib import Path
import json


def load_geometry_summary(run_dir: str | Path) -> dict | None:
    path = Path(run_dir) / "geometry" / "geometry_summary.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

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
            val = getattr(obj, name)
            if val is not None:
                return val

    return None


def compute_static_margin(
    *,
    x_np_m: float | None,
    x_cg_m: float,
    mac_m: float | None,
    x_positive_aft: bool = True,
) -> tuple[float | None, float | None]:
    if x_np_m is None or mac_m is None:
        return None, None
    if mac_m <= 0.0:
        raise ValueError(f"mac_m must be positive, got {mac_m}")

    raw = (x_np_m - x_cg_m) / mac_m
    sm = raw if x_positive_aft else -raw
    return sm, sm * 100.0


def interpret_longitudinal(static_margin: float | None, cma: float | None) -> tuple[str | None, bool | None]:
    if static_margin is None:
        return None, None

    if static_margin > 0.0:
        interp = "positive_static_margin"
    elif static_margin < 0.0:
        interp = "negative_static_margin"
    else:
        interp = "neutral_static_margin"

    if cma is None:
        return interp, None

    consistent = (
        (static_margin > 0.0 and cma < 0.0)
        or (static_margin < 0.0 and cma > 0.0)
        or (static_margin == 0.0 and abs(cma) < 1e-12)
    )
    return interp, consistent


def build_state_space_preparation(
    *,
    mass_properties: MassProperties,
    x_np_m: float | None,
    mac_m: float | None,
    cma: float | None,
    spiral_metric: float | None,
) -> StateSpacePreparation:
    missing: list[str] = []

    inertia_available = any(
        value is not None
        for value in (
            mass_properties.inertia.ixx_kg_m2,
            mass_properties.inertia.iyy_kg_m2,
            mass_properties.inertia.izz_kg_m2,
        )
    )
    if not inertia_available:
        missing.append("principal inertia estimates")
    if x_np_m is None:
        missing.append("neutral point")
    if mac_m is None:
        missing.append("mean aerodynamic chord")
    if cma is None:
        missing.append("Cma")
    if spiral_metric is None:
        missing.append("spiral metric")

    return StateSpacePreparation(
        mass_available=True,
        cg_available=True,
        inertia_available=inertia_available,
        xnp_available=x_np_m is not None,
        mac_available=mac_m is not None,
        longitudinal_derivatives_available=cma is not None,
        lateral_derivatives_available=spiral_metric is not None,
        ready_for_trim_solver=False,
        ready_for_eigenanalysis=False,
        missing_items=missing,
    )


def build_dynamics_foundation_result(
    *,
    aero_result: Any,
    mass_properties: MassProperties,
    source_run_dir: str,
    trim_definition: TrimDefinition | None = None,
    x_positive_aft: bool = True,
) -> DynamicsFoundationResult:
    trim_definition = trim_definition or TrimDefinition()

    x_np_m = _get(aero_result, "x_np", "Xnp", "x_np_m")
    mac_m = _get(aero_result, "mac_m", "mean_aerodynamic_chord_m", "cbar_m")

    if mac_m is None:
        geometry_summary = load_geometry_summary(source_run_dir)
        if geometry_summary is not None:
            mac_m = (
                geometry_summary
                .get("reference_values", {})
                .get("mean_aerodynamic_chord_m")
            )
            
    cma = _get(aero_result, "Cma", "cma")
    spiral_metric = _get(aero_result, "spiral_metric")
    solver_id = _get(aero_result, "solver_id", "solver")
    operating_point = _get(aero_result, "flight_condition", "operating_point", "flight_condition_snapshot") or {}

    static_margin, static_margin_pct = compute_static_margin(
        x_np_m=x_np_m,
        x_cg_m=mass_properties.x_cg_m,
        mac_m=mac_m,
        x_positive_aft=x_positive_aft,
    )
    interp, consistent = interpret_longitudinal(static_margin, cma)

    return DynamicsFoundationResult(
        schema_version="0.1.0",
        source_run_dir=source_run_dir,
        source_solver_id=solver_id,
        operating_point_snapshot=asdict(operating_point) if is_dataclass(operating_point) else dict(operating_point),
        mass_properties=mass_properties,
        trim_definition=trim_definition,
        stability_metrics=StabilityMetrics(
            x_np_m=x_np_m,
            x_cg_m=mass_properties.x_cg_m,
            mac_m=mac_m,
            static_margin=static_margin,
            static_margin_percent_mac=static_margin_pct,
            cma=cma,
            cma_consistent_with_static_margin=consistent,
            spiral_metric=spiral_metric,
            longitudinal_interpretation=interp,
        ),
        state_space_preparation=build_state_space_preparation(
            mass_properties=mass_properties,
            x_np_m=x_np_m,
            mac_m=mac_m,
            cma=cma,
            spiral_metric=spiral_metric,
        ),
        metadata={"x_axis_positive_aft": x_positive_aft},
    )