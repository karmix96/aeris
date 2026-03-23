from dataclasses import dataclass, field

from aeris.dynamics.analysis import build_dynamics_foundation_result, compute_static_margin
from aeris.dynamics.models import MassProperties


@dataclass
class FakeAeroResult:
    Xnp: float = 0.80
    mac_m: float = 0.40
    Cma: float = -0.50
    spiral_metric: float = 0.11
    solver_id: str = "aerosandbox_avl"
    flight_condition: dict = field(default_factory=lambda: {"alpha_deg": 4.0, "velocity_mps": 28.0})


def test_compute_static_margin():
    sm, sm_pct = compute_static_margin(x_np_m=0.80, x_cg_m=0.72, mac_m=0.40)
    assert sm is not None
    assert sm_pct is not None
    assert abs(sm - 0.2) < 1e-12
    assert abs(sm_pct - 20.0) < 1e-12


def test_build_dynamics_foundation_result():
    result = build_dynamics_foundation_result(
        aero_result=FakeAeroResult(),
        mass_properties=MassProperties(mass_kg=12.5, x_cg_m=0.72),
        source_run_dir="data/runs/example",
    )
    assert result.stability_metrics.static_margin is not None
    assert abs(result.stability_metrics.static_margin - 0.2) < 1e-12
    assert result.stability_metrics.cma_consistent_with_static_margin is True
    assert result.state_space_preparation.ready_for_eigenanalysis is False