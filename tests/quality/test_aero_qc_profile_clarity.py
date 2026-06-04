from __future__ import annotations

from aeris.quality.profiles import resolve_aero_profile, resolve_geometry_profile


def test_production_profiles_resolve_explicitly() -> None:
    geometry_profile, geometry_validators = resolve_geometry_profile("production")
    aero_profile, aero_validators = resolve_aero_profile("production")

    assert geometry_profile == "production"
    assert aero_profile == "production"
    assert "geometry_basic_ranges_v1" in geometry_validators
    assert "aero_basic_ranges_v1" in aero_validators
    assert "aero_ld_sanity_v1" not in aero_validators


def test_unknown_profiles_still_fall_back_to_basic() -> None:
    geometry_profile, _ = resolve_geometry_profile("does_not_exist")
    aero_profile, _ = resolve_aero_profile("does_not_exist")

    assert geometry_profile == "basic"
    assert aero_profile == "basic"
