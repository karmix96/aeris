"""
Typed configuration and sampled design-variable models for bwb_segmented_v1.

Defines:
    - immutable generator configuration dataclasses
    - immutable sampled design vectors
    - conversion from raw config dictionaries into typed configuration objects

Schema compatibility:
    Two YAML schemas are accepted for selecting the generator:

        (a) Preferred:
            geometry:
              generator:
                id: bwb_segmented_v1

        (b) Legacy (a deprecation warning is logged at the resolver level):
            geometry:
              generator:
                family: bwb_segmented
                version: v1

    Internally, BWB always stores both `family` and `version` for use in
    manifests. When only `id` is provided, family and version are derived
    by splitting on the last '_v' delimiter.

Identity guarantee:
    At the end of build_bwb_generator_config, family + version are checked
    against the expected generator id ('bwb_segmented_v1'). A mismatch raises
    ValueError immediately rather than producing a misleading manifest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


# Must match BwbSegmentedV1Generator.GENERATOR_ID exactly. Kept in sync
# manually because importing from generator.py would create a circular import.
# If you change one, change the other.
_EXPECTED_GENERATOR_ID = "bwb_segmented_v1"


# ---------------------------------------------------------------------------
# Strict cast helpers
#
# These give clear error messages for YAML typos and reject silent coercions
# (e.g. bool getting coerced to int, "yes" getting coerced to True).
# ---------------------------------------------------------------------------


def _as_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise TypeError(f"{field_name} must be a bool, got {type(value).__name__}.")


def _as_int(value: Any, *, field_name: str) -> int:  # AERIS_PATCH_SUPP2_APPLIED
    if isinstance(value, bool):
        # bool is a subclass of int in Python; reject explicitly to catch
        # YAML mistakes like 'n_points: true'.
        raise TypeError(f"{field_name} must be int, got bool.")
    if isinstance(value, float) and not value.is_integer():
        raise TypeError(
            f"{field_name} must be an integer, got float {value!r}. "
            "YAML values like 10.7 are silently truncated by int() — "
            "use a plain integer (e.g. n_points: 10)."
        )
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be int, got {value!r}.") from exc


def _as_float(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric, got bool.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be numeric, got {value!r}.") from exc


def _as_str(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string, got {type(value).__name__}.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty.")
    return text


def _as_optional_int(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    return _as_int(value, field_name=field_name)


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlotOutputsConfig:
    save_plot: bool = True
    build_aerosandbox: bool = True


@dataclass(frozen=True)
class GeneratorConfig:
    family: str
    version: str
    seed: int | None


@dataclass(frozen=True)
class ControlsConfig:
    n_points: int
    n_spline_inboard: int
    n_spline_outboard: int
    curvature_strength: float
    spline_split_ratio: float
    segment_length_variation: float
    sweep_variation: float


@dataclass(frozen=True)
class RangeConfig:
    min: float
    max: float


@dataclass(frozen=True)
class PlanformBoundsConfig:
    c1_m: RangeConfig
    c2_ratio: RangeConfig
    c3_ratio: RangeConfig
    c4_ratio: RangeConfig
    b_total_m: RangeConfig
    b3_ratio: RangeConfig
    split_ratio: RangeConfig
    sw1_deg: RangeConfig
    sw2_deg: RangeConfig
    sw3_deg: RangeConfig


@dataclass(frozen=True)
class SegmentAirfoilConfig:
    """One spanwise segment → one 2D-library airfoil for the polar bridge.

    y_frac_end is normalised by semispan (0 < y_frac_end ≤ 1.0).
    The last entry should have y_frac_end=1.0; it is clamped automatically.
    """
    airfoil_id: str
    y_frac_end: float


@dataclass(frozen=True)
class StationAirfoilsConfig:
    """Prescribed airfoil at each BWB span station (Paper 1).

    b0 (root): reflex profile, positive Cm0 for pitch stability.
    b1 (kink): transitional, moderate camber.
    b2 (mid):  lighter camber, efficient cruise.
    b3 (tip):  symmetric/low-camber for roll authority.

    Step-function: sections in [b0->b1) get b0, [b1->b2) get b1, etc.
    """
    b0: str
    b1: str
    b2: str
    b3: str

    def to_dict(self) -> dict:
        return {"b0": self.b0, "b1": self.b1, "b2": self.b2, "b3": self.b3}


@dataclass(frozen=True)
class SectionBoundsConfig:
    airfoil_name: str
    dihedral_root_deg: float

    twist_b0_deg: RangeConfig
    twist_b1_deg: RangeConfig
    twist_b2_deg: RangeConfig
    twist_b3_deg: RangeConfig

    dihedral_b1_deg: RangeConfig
    dihedral_b2_deg: RangeConfig
    dihedral_b3_deg: RangeConfig

    # AVL polar bridge — optional; None means no CDCL injection
    airfoil_library_id: str | None = None       # single airfoil from library (approach 1a)
    segment_airfoils: tuple[SegmentAirfoilConfig, ...] = ()  # multi-segment (approach 1b / 2)
    station_airfoils: StationAirfoilsConfig | None = None    # Paper 1 prescribed geometry airfoils


@dataclass(frozen=True)
class ControlSurfaceBoundsConfig:
    """Sampling bounds for the shared elevon geometry DVs (v3+)."""
    elevon_start_frac: RangeConfig
    elevon_end_frac: RangeConfig
    elevon_hinge_frac: RangeConfig


@dataclass(frozen=True)
class ControlSurfaceSpanwiseConfig:
    start_frac: float
    end_frac: float


@dataclass(frozen=True)
class ControlSurfaceConfig:
    name: str
    family: str
    hinge_point: float
    symmetric: bool
    spanwise: ControlSurfaceSpanwiseConfig
    deflection_sign: str = "standard"
    side: str | None = None
    required: bool = False


@dataclass(frozen=True)
class ControlSurfacesConfig:
    enabled: bool
    surfaces: tuple[ControlSurfaceConfig, ...]


@dataclass(frozen=True)
class BWBDesignSample:
    """One concrete BWB design sample (17 independent design variables).

    All fields are immutable; pass the dataclass around freely.

    Sign conventions:
        sw1_deg, sw2_deg, sw3_deg
            Negative values indicate AFT sweep (current BWB convention).
            YAML configs declare positive *magnitudes*; the sampler negates
            them when building this dataclass. Downstream geometry math
            assumes negative-aft.

        twist_*_deg, dihedral_*_deg
            Stored as authored in YAML. No sign flipping.

    See sweep_magnitudes_deg if you need the absolute values back (e.g.
    for human-readable reports or YAML round-trip).
    """

    # Independent planform variables
    c1_m: float
    c2_ratio: float
    c3_ratio: float
    c4_ratio: float
    b_total_m: float
    b3_ratio: float
    split_ratio: float
    sw1_deg: float
    sw2_deg: float
    sw3_deg: float

    # Independent section variables
    twist_b0_deg: float
    twist_b1_deg: float
    twist_b2_deg: float
    twist_b3_deg: float
    dihedral_b1_deg: float
    dihedral_b2_deg: float
    dihedral_b3_deg: float

    # Elevon geometry DVs — defaults match v1/v2 fixed values
    elevon_start_frac: float = 0.60
    elevon_end_frac: float   = 0.95
    elevon_hinge_frac: float = 0.75

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sweep_magnitudes_deg(self) -> tuple[float, float, float]:
        """Return the absolute sweep magnitudes for sw1/sw2/sw3 (positive)."""
        return (abs(self.sw1_deg), abs(self.sw2_deg), abs(self.sw3_deg))


@dataclass(frozen=True)
class BWBGeneratorConfig:
    name: str
    generator: GeneratorConfig
    controls: ControlsConfig
    planform_bounds: PlanformBoundsConfig
    section_bounds: SectionBoundsConfig
    outputs: PlotOutputsConfig
    control_surfaces: ControlSurfacesConfig
    elevon_bounds: ControlSurfaceBoundsConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sample_field_names(self) -> list[str]:
        """Return all fields stored in :class:`BWBDesignSample`.

        This includes fixed/default fields such as elevon geometry when
        ``elevon_bounds`` is absent. Use ``active_design_variable_names()`` for
        the independent variables sampled by the current config.
        """
        return [f.name for f in fields(BWBDesignSample)]

    def active_design_variable_names(self) -> list[str]:
        """Return independent design variables sampled by this config.

        v1/v2 configs store elevon_start/end/hinge in the sample for schema
        stability, but those values are fixed defaults unless ``elevon_bounds``
        is present. v3 configs with ``elevon_bounds`` expose all 20 active DVs.
        """
        elevon_fields = {
            "elevon_start_frac",
            "elevon_end_frac",
            "elevon_hinge_frac",
        }
        names = self.sample_field_names()
        if self.elevon_bounds is None:
            names = [name for name in names if name not in elevon_fields]
        return names

    def design_variable_names(self) -> list[str]:
        """Backward-compatible alias for active design-variable names."""
        return self.active_design_variable_names()

    def fixed_parameters(self) -> dict[str, Any]:
        return {
            "airfoil_name": self.section_bounds.airfoil_name,
            "dihedral_root_deg": self.section_bounds.dihedral_root_deg,
            "generator_family": self.generator.family,
            "generator_version": self.generator.version,
        }


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_optional_str(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, field_name=field_name)


def _parse_segment_airfoils(raw: Any) -> tuple[SegmentAirfoilConfig, ...]:
    """Parse optional section_bounds.segment_airfoils list from YAML."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise TypeError(
            f"section_bounds.segment_airfoils must be a list, got {type(raw).__name__}."
        )
    result: list[SegmentAirfoilConfig] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise TypeError(
                f"section_bounds.segment_airfoils[{i}] must be a mapping."
            )
        result.append(
            SegmentAirfoilConfig(
                airfoil_id=_as_str(
                    item.get("airfoil_id", item.get("id", "")),
                    field_name=f"segment_airfoils[{i}].airfoil_id",
                ),
                y_frac_end=_as_float(
                    item.get("y_frac_end", item.get("y_end_frac", 1.0)),
                    field_name=f"segment_airfoils[{i}].y_frac_end",
                ),
            )
        )
    return tuple(result)


def _require(mapping: dict[str, Any], key: str) -> Any:
    if key not in mapping:
        raise KeyError(f"Missing required config key: {key}")
    return mapping[key]


def _range_cfg(mapping: dict[str, Any], key: str) -> RangeConfig:
    block = _require(mapping, key)
    if not isinstance(block, dict):
        raise TypeError(
            f"Config field {key!r} must be a mapping with 'min' and 'max', "
            f"got {type(block).__name__}."
        )
    return RangeConfig(
        min=_as_float(_require(block, "min"), field_name=f"{key}.min"),
        max=_as_float(_require(block, "max"), field_name=f"{key}.max"),
    )


def _resolve_family_version(generator_cfg: dict[str, Any]) -> tuple[str, str]:
    """Resolve (family, version) from the YAML generator block.

    Accepts either:
        - explicit 'id' field: 'bwb_segmented_v1' → ('bwb_segmented', 'v1')
        - explicit 'family' + 'version' fields (legacy)

    The split for the 'id' form uses the last '_v' delimiter so that
    'bwb_segmented_v1' produces family='bwb_segmented', version='v1'.

    Raises:
        ValueError: if neither schema is satisfied, or 'id' cannot be split.
        TypeError: if a value has the wrong type.
    """
    explicit_id = generator_cfg.get("id")
    if explicit_id is not None:
        id_str = _as_str(explicit_id, field_name="geometry.generator.id")
        if "_v" not in id_str:
            raise ValueError(
                f"Cannot derive family+version from generator id={id_str!r}. "
                "Expected format: <family>_v<version> (e.g. 'bwb_segmented_v1')."
            )
        family_part, version_suffix = id_str.rsplit("_v", 1)
        if not family_part or not version_suffix:
            raise ValueError(
                f"Generator id={id_str!r} produces empty family or version "
                "after splitting on '_v'."
            )
        return family_part, f"v{version_suffix}"

    family = generator_cfg.get("family")
    version = generator_cfg.get("version")
    if family is None or version is None:
        raise KeyError(
            "geometry.generator must provide either 'id' (preferred) or "
            "both 'family' and 'version'."
        )
    return (
        _as_str(family, field_name="geometry.generator.family"),
        _as_str(version, field_name="geometry.generator.version"),
    )


def build_bwb_generator_config(config: dict[str, Any]) -> BWBGeneratorConfig:
    """Build a typed BWBGeneratorConfig from a raw YAML config dict.

    Accepts both the 'id' schema and the legacy 'family + version' schema.
    After construction, verifies that the resolved family_version matches
    BWB's expected GENERATOR_ID.

    Raises:
        KeyError: missing required config key.
        TypeError: config value has the wrong type.
        ValueError: a config value is structurally invalid (e.g. id cannot
            be split, family+version does not match BWB's GENERATOR_ID).
    """
    geometry_cfg = config.get("geometry", {})
    if not isinstance(geometry_cfg, dict):
        raise TypeError(
            f"Top-level 'geometry' must be a mapping, "
            f"got {type(geometry_cfg).__name__}."
        )

    generator_cfg = geometry_cfg.get("generator", {})
    if not isinstance(generator_cfg, dict):
        raise TypeError(
            f"'geometry.generator' must be a mapping, "
            f"got {type(generator_cfg).__name__}."
        )

    controls_cfg = geometry_cfg.get("controls", {})
    planform_cfg = geometry_cfg.get("planform_bounds", {})
    sections_cfg = geometry_cfg.get("section_bounds", {})
    outputs_cfg = geometry_cfg.get("outputs", {})
    control_surfaces_cfg = geometry_cfg.get("control_surfaces", {})

    family, version = _resolve_family_version(generator_cfg)

    bwb_config = BWBGeneratorConfig(
        name=_as_str(config.get("name", "wing_bwb"), field_name="name"),
        generator=GeneratorConfig(
            family=family,
            version=version,
            seed=_as_optional_int(
                generator_cfg.get("seed"),
                field_name="geometry.generator.seed",
            ),
        ),
        controls=ControlsConfig(
            n_points=_as_int(
                _require(controls_cfg, "n_points"),
                field_name="controls.n_points",
            ),
            n_spline_inboard=_as_int(
                _require(controls_cfg, "n_spline_inboard"),
                field_name="controls.n_spline_inboard",
            ),
            n_spline_outboard=_as_int(
                _require(controls_cfg, "n_spline_outboard"),
                field_name="controls.n_spline_outboard",
            ),
            curvature_strength=_as_float(
                _require(controls_cfg, "desired_curvature_strength"),
                field_name="controls.desired_curvature_strength",
            ),
            spline_split_ratio=_as_float(
                controls_cfg.get("spline_split_ratio", 0.55),
                field_name="controls.spline_split_ratio",
            ),
            segment_length_variation=_as_float(
                controls_cfg.get("segment_length_variation", 0.25),
                field_name="controls.segment_length_variation",
            ),
            sweep_variation=_as_float(
                controls_cfg.get("sweep_variation", 0.10),
                field_name="controls.sweep_variation",
            ),
        ),
        planform_bounds=PlanformBoundsConfig(
            c1_m=_range_cfg(planform_cfg, "c1_m"),
            c2_ratio=_range_cfg(planform_cfg, "c2_ratio"),
            c3_ratio=_range_cfg(planform_cfg, "c3_ratio"),
            c4_ratio=_range_cfg(planform_cfg, "c4_ratio"),
            b_total_m=_range_cfg(planform_cfg, "b_total_m"),
            b3_ratio=_range_cfg(planform_cfg, "b3_ratio"),
            split_ratio=_range_cfg(planform_cfg, "split_ratio"),
            sw1_deg=_range_cfg(planform_cfg, "sw1_deg"),
            sw2_deg=_range_cfg(planform_cfg, "sw2_deg"),
            sw3_deg=_range_cfg(planform_cfg, "sw3_deg"),
        ),
        section_bounds=SectionBoundsConfig(
            airfoil_name=_as_str(
                sections_cfg.get("airfoil_name", "naca4412"),
                field_name="section_bounds.airfoil_name",
            ),
            dihedral_root_deg=_as_float(
                sections_cfg.get("dihedral_root_deg", 0.0),
                field_name="section_bounds.dihedral_root_deg",
            ),
            twist_b0_deg=_range_cfg(sections_cfg, "twist_b0_deg"),
            twist_b1_deg=_range_cfg(sections_cfg, "twist_b1_deg"),
            twist_b2_deg=_range_cfg(sections_cfg, "twist_b2_deg"),
            twist_b3_deg=_range_cfg(sections_cfg, "twist_b3_deg"),
            dihedral_b1_deg=_range_cfg(sections_cfg, "dihedral_b1_deg"),
            dihedral_b2_deg=_range_cfg(sections_cfg, "dihedral_b2_deg"),
            dihedral_b3_deg=_range_cfg(sections_cfg, "dihedral_b3_deg"),
            airfoil_library_id=_parse_optional_str(
                sections_cfg.get("airfoil_library_id"),
                field_name="section_bounds.airfoil_library_id",
            ),
            segment_airfoils=_parse_segment_airfoils(
                sections_cfg.get("segment_airfoils"),
            ),
            station_airfoils=_parse_station_airfoils(
                sections_cfg.get("station_airfoils"),
            ),
        ),
        outputs=PlotOutputsConfig(
            save_plot=_as_bool(
                outputs_cfg.get("save_plot", True),
                field_name="outputs.save_plot",
            ),
            build_aerosandbox=_as_bool(
                outputs_cfg.get("build_aerosandbox", True),
                field_name="outputs.build_aerosandbox",
            ),
        ),
        control_surfaces=_build_control_surfaces_config(control_surfaces_cfg),
        elevon_bounds=_build_elevon_bounds_config(geometry_cfg.get("elevon_bounds")),
    )

    # Identity consistency: catch family/version mismatches against BWB.
    resolved_id = f"{bwb_config.generator.family}_{bwb_config.generator.version}"
    if resolved_id != _EXPECTED_GENERATOR_ID:
        raise ValueError(
            f"BWB generator received family_version={resolved_id!r}, "
            f"but this code path expects {_EXPECTED_GENERATOR_ID!r}. "
            "Check 'geometry.generator.id' (or 'family' + 'version') in your YAML."
        )

    return bwb_config


def _parse_station_airfoils(cfg: dict | None) -> "StationAirfoilsConfig | None":
    if cfg is None:
        return None
    if not isinstance(cfg, dict):
        raise TypeError(f"section_bounds.station_airfoils must be a mapping; got {type(cfg).__name__}")
    for key in ("b0", "b1", "b2", "b3"):
        if key not in cfg:
            raise ValueError(f"section_bounds.station_airfoils missing key '{key}'")
        if not isinstance(cfg[key], str) or not cfg[key].strip():
            raise ValueError(f"section_bounds.station_airfoils.{key} must be a non-empty string")
    return StationAirfoilsConfig(
        b0=str(cfg["b0"]).strip(), b1=str(cfg["b1"]).strip(),
        b2=str(cfg["b2"]).strip(), b3=str(cfg["b3"]).strip(),
    )


def _build_elevon_bounds_config(cfg: dict | None) -> "ControlSurfaceBoundsConfig | None":
    """Parse optional elevon_bounds YAML section. None when absent (v1/v2)."""
    # AERIS_PATCH_BATCH2_ELEVON_BOUNDS_FAIL_LOUD
    # Missing block means fixed v1/v2 elevon defaults. A present-but-empty or
    # wrong-typed block is a YAML/operator error and must not silently disable v3.
    if cfg is None:
        return None
    if not isinstance(cfg, dict):
        raise TypeError(
            f"geometry.elevon_bounds must be a mapping with elevon_start_frac, "
            f"elevon_end_frac, and elevon_hinge_frac blocks; got {type(cfg).__name__}."
        )
    if not cfg:
        raise ValueError(
            "geometry.elevon_bounds is present but empty. Remove the block for "
            "fixed v1/v2 defaults, or provide elevon_start_frac/elevon_end_frac/"
            "elevon_hinge_frac bounds for v3 sampling."
        )
    def _rc(key: str) -> RangeConfig:
        block = cfg.get(key)
        if not isinstance(block, dict):
            raise TypeError(f"elevon_bounds.{key} must have 'min' and 'max'.")
        return RangeConfig(
            min=_as_float(_require(block, "min"), field_name=f"elevon_bounds.{key}.min"),
            max=_as_float(_require(block, "max"), field_name=f"elevon_bounds.{key}.max"),
        )
    return ControlSurfaceBoundsConfig(
        elevon_start_frac=_rc("elevon_start_frac"),
        elevon_end_frac=_rc("elevon_end_frac"),
        elevon_hinge_frac=_rc("elevon_hinge_frac"),
    )


def _build_control_surfaces_config(
    control_surfaces_cfg: dict[str, Any],
) -> ControlSurfacesConfig:
    # AERIS_PATCH_BATCH2_CONTROL_SURFACES_FAIL_LOUD
    # Missing/empty mapping disables controls. Present wrong types such as []
    # must fail loudly instead of silently disabling controls.
    if control_surfaces_cfg is None:
        return ControlSurfacesConfig(enabled=False, surfaces=())

    if not isinstance(control_surfaces_cfg, dict):
        raise TypeError(
            f"geometry.control_surfaces must be a mapping, "
            f"got {type(control_surfaces_cfg).__name__}."
        )

    if not control_surfaces_cfg:
        return ControlSurfacesConfig(enabled=False, surfaces=())

    enabled = _as_bool(
        control_surfaces_cfg.get("enabled", False),
        field_name="control_surfaces.enabled",
    )
    raw_surfaces = control_surfaces_cfg.get("surfaces", [])

    if not isinstance(raw_surfaces, list):
        raise TypeError("geometry.control_surfaces.surfaces must be a list.")

    surfaces: list[ControlSurfaceConfig] = []
    seen_names: set[str] = set()

    for i, raw in enumerate(raw_surfaces):
        if not isinstance(raw, dict):
            raise TypeError(
                f"geometry.control_surfaces.surfaces[{i}] must be a dict."
            )

        prefix = f"control_surfaces.surfaces[{i}]"

        name = _as_str(_require(raw, "name"), field_name=f"{prefix}.name")
        family = _as_str(_require(raw, "family"), field_name=f"{prefix}.family")
        hinge_point = _as_float(
            _require(raw, "hinge_point"), field_name=f"{prefix}.hinge_point"
        )
        symmetric = _as_bool(
            raw.get("symmetric", True), field_name=f"{prefix}.symmetric"
        )
        deflection_sign = _as_str(
            raw.get("deflection_sign", "standard"),
            field_name=f"{prefix}.deflection_sign",
        )
        required = _as_bool(
            raw.get("required", False), field_name=f"{prefix}.required"
        )

        raw_side = raw.get("side", None)
        side = (
            _as_str(raw_side, field_name=f"{prefix}.side")
            if raw_side is not None
            else None
        )

        spanwise_cfg = raw.get("spanwise", {})
        if not isinstance(spanwise_cfg, dict):
            raise TypeError(f"{prefix}.spanwise must be a dict.")

        start_frac = _as_float(
            _require(spanwise_cfg, "start_frac"),
            field_name=f"{prefix}.spanwise.start_frac",
        )
        end_frac = _as_float(
            _require(spanwise_cfg, "end_frac"),
            field_name=f"{prefix}.spanwise.end_frac",
        )

        if name in seen_names:
            raise ValueError(f"Duplicate control surface name: {name!r}")
        seen_names.add(name)

        if family not in {"trailing_edge"}:
            raise ValueError(
                f"Unsupported control surface family {family!r}. "
                "Currently supported: 'trailing_edge'."
            )

        if not (0.0 < hinge_point < 1.0):
            raise ValueError(
                f"Control surface {name!r} has invalid hinge_point={hinge_point}. "
                "Expected 0.0 < hinge_point < 1.0."
            )

        if not (0.0 <= start_frac < end_frac <= 1.0):
            raise ValueError(
                f"Control surface {name!r} has invalid spanwise range "
                f"[{start_frac}, {end_frac}]. "
                "Expected 0.0 <= start_frac < end_frac <= 1.0."
            )

        if symmetric and side is not None:
            raise ValueError(
                f"Control surface {name!r} is symmetric=True, "
                "so side must be omitted."
            )

        if not symmetric and side not in {"left", "right"}:
            raise ValueError(
                f"Control surface {name!r} is symmetric=False, "
                "so side must be 'left' or 'right'."
            )

        if deflection_sign not in {"standard"}:
            raise ValueError(
                f"Unsupported deflection_sign {deflection_sign!r} "
                f"for control surface {name!r}."
            )

        surfaces.append(
            ControlSurfaceConfig(
                name=name,
                family=family,
                hinge_point=hinge_point,
                symmetric=symmetric,
                spanwise=ControlSurfaceSpanwiseConfig(
                    start_frac=start_frac,
                    end_frac=end_frac,
                ),
                deflection_sign=deflection_sign,
                side=side,
                required=required,
            )
        )

    if not enabled and surfaces:
        raise ValueError(
            "geometry.control_surfaces.enabled is false, but surfaces are defined."
        )

    return ControlSurfacesConfig(enabled=enabled, surfaces=tuple(surfaces))