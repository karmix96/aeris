from aeris.dynamics.io import read_dynamics_foundation_result, write_dynamics_foundation_result
from aeris.dynamics.models import (
    DynamicsFoundationResult,
    MassProperties,
    StabilityMetrics,
    StateSpacePreparation,
    TrimDefinition,
)


def test_write_read_roundtrip(tmp_path):
    result = DynamicsFoundationResult(
        schema_version="0.1.0",
        source_run_dir="data/runs/example",
        source_solver_id="aerosandbox_avl",
        operating_point_snapshot={"alpha_deg": 4.0},
        mass_properties=MassProperties(mass_kg=10.0, x_cg_m=0.5),
        trim_definition=TrimDefinition(),
        stability_metrics=StabilityMetrics(
            x_np_m=0.6,
            x_cg_m=0.5,
            mac_m=0.25,
            static_margin=0.4,
            static_margin_percent_mac=40.0,
        ),
        state_space_preparation=StateSpacePreparation(
            mass_available=True,
            cg_available=True,
            inertia_available=False,
            xnp_available=True,
            mac_available=True,
            longitudinal_derivatives_available=False,
            lateral_derivatives_available=False,
            ready_for_trim_solver=False,
            ready_for_eigenanalysis=False,
        ),
    )
    path = write_dynamics_foundation_result(result, tmp_path)
    payload = read_dynamics_foundation_result(path)
    assert payload["stability_metrics"]["static_margin_percent_mac"] == 40.0