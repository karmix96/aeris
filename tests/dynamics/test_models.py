from aeris.dynamics.models import (
    DynamicsFoundationResult,
    InertiaPlaceholders,
    MassProperties,
    StabilityMetrics,
    StateSpacePreparation,
    TrimDefinition,
)


def test_models_construct_cleanly():
    mass = MassProperties(
        mass_kg=12.5,
        x_cg_m=0.72,
        inertia=InertiaPlaceholders(ixx_kg_m2=0.8),
    )
    trim = TrimDefinition(
        fixed_variables={"velocity_mps": 28.0, "altitude_m": 1500.0},
        solve_variables=[],
        enabled=False,
    )
    metrics = StabilityMetrics(
        x_np_m=0.80,
        x_cg_m=0.72,
        mac_m=0.40,
        static_margin=0.20,
        static_margin_percent_mac=20.0,
        cma=-0.45,
        cma_consistent_with_static_margin=True,
        spiral_metric=0.12,
        longitudinal_interpretation="positive_static_margin",
    )
    prep = StateSpacePreparation(
        mass_available=True,
        cg_available=True,
        inertia_available=False,
        xnp_available=True,
        mac_available=True,
        longitudinal_derivatives_available=True,
        lateral_derivatives_available=True,
        ready_for_trim_solver=False,
        ready_for_eigenanalysis=False,
        missing_items=["inertia tensor", "trim solve variables"],
    )
    result = DynamicsFoundationResult(
        schema_version="0.1.0",
        source_run_dir="data/runs/example",
        source_solver_id="aerosandbox_avl",
        operating_point_snapshot={"alpha_deg": 4.0, "velocity_mps": 28.0},
        mass_properties=mass,
        trim_definition=trim,
        stability_metrics=metrics,
        state_space_preparation=prep,
    )

    payload = result.to_dict()
    assert payload["mass_properties"]["mass_kg"] == 12.5
    assert payload["stability_metrics"]["static_margin"] == 0.20