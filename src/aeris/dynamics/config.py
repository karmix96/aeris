"""
AERIS Dynamics — Mass Properties Configuration
================================================
Loads and validates mass properties from YAML or JSON config files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import yaml

# Physical validation bounds (engineering judgment, UAV context)
MASS_MIN_KG: float = 0.1
MASS_MAX_KG: float = 500.0
CG_X_MIN_M: float = -0.5
CG_X_MAX_M: float = 5.0


@dataclass(frozen=True)
class MassPropertiesConfig:
    """
    Validated mass properties loaded from a config file.
    All fields in SI units.
    """
    mass_kg: float                   # total mass [kg]
    x_cg_m: float                   # longitudinal CG from nose ref [m]
    y_cg_m: float = 0.0             # lateral CG [m] (0 for symmetric)
    z_cg_m: float = 0.0             # vertical CG [m]
    ixx_kg_m2: float | None = None  # roll inertia [kg·m²]
    iyy_kg_m2: float | None = None  # pitch inertia [kg·m²]
    izz_kg_m2: float | None = None  # yaw inertia [kg·m²]

    def __post_init__(self) -> None:
        if self.mass_kg <= 0:
            raise ValueError(f"mass_kg must be positive, got {self.mass_kg}")
        if not (MASS_MIN_KG <= self.mass_kg <= MASS_MAX_KG):
            raise ValueError(
                f"mass_kg={self.mass_kg} kg is outside plausible UAV range "
                f"[{MASS_MIN_KG}, {MASS_MAX_KG}] kg. "
                "Override bounds if this is intentional."
            )
        if not (CG_X_MIN_M <= self.x_cg_m <= CG_X_MAX_M):
            raise ValueError(
                f"x_cg_m={self.x_cg_m} m is outside plausible range "
                f"[{CG_X_MIN_M}, {CG_X_MAX_M}] m."
            )
        for name, val in [
            ("ixx_kg_m2", self.ixx_kg_m2),
            ("iyy_kg_m2", self.iyy_kg_m2),
            ("izz_kg_m2", self.izz_kg_m2),
        ]:
            if val is not None and val <= 0:
                raise ValueError(f"{name} must be positive if provided, got {val}")

    @classmethod
    def from_dict(cls, data: dict) -> "MassPropertiesConfig":
        return cls(
            mass_kg=float(data["mass_kg"]),
            x_cg_m=float(data["x_cg_m"]),
            y_cg_m=float(data.get("y_cg_m", 0.0)),
            z_cg_m=float(data.get("z_cg_m", 0.0)),
            ixx_kg_m2=None if data.get("ixx_kg_m2") is None else float(data["ixx_kg_m2"]),
            iyy_kg_m2=None if data.get("iyy_kg_m2") is None else float(data["iyy_kg_m2"]),
            izz_kg_m2=None if data.get("izz_kg_m2") is None else float(data["izz_kg_m2"]),
        )


def load_mass_properties_config(path: str | Path) -> MassPropertiesConfig:
    """
    Load and validate a mass-properties config from YAML or JSON.

    Expected YAML structure (either flat or nested under 'mass_properties'):

        mass_properties:
          mass_kg: 12.5
          x_cg_m: 0.40
          y_cg_m: 0.0
          z_cg_m: 0.0
          ixx_kg_m2: 0.15
          iyy_kg_m2: 0.80
          izz_kg_m2: 0.90
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Mass config not found: {path}")

    if path.suffix.lower() in {".yaml", ".yml"}:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(
            f"Unsupported mass config format: {path.suffix}. "
            "Use .yaml, .yml, or .json."
        )

    if not isinstance(raw, dict):
        raise ValueError(
            f"Mass config {path.name} must be a YAML/JSON mapping, "
            f"got {type(raw).__name__}."
        )

    data = raw.get("mass_properties", raw)
    if not isinstance(data, dict):
        raise ValueError(
            f"'mass_properties' in {path.name} must be a mapping, "
            f"got {type(data).__name__}."
        )

    required = {"mass_kg", "x_cg_m"}
    missing  = required - set(data.keys())
    if missing:
        raise ValueError(
            f"Mass config {path.name} is missing required fields: "
            + ", ".join(sorted(missing))
        )

    return MassPropertiesConfig.from_dict(data)