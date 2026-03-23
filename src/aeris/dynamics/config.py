from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

import yaml


@dataclass(frozen=True)
class MassPropertiesConfig:
    mass_kg: float
    x_cg_m: float
    y_cg_m: float = 0.0
    z_cg_m: float = 0.0
    ixx_kg_m2: float | None = None
    iyy_kg_m2: float | None = None
    izz_kg_m2: float | None = None

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
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Mass config not found: {path}")

    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError(f"Unsupported mass config format: {path.suffix}")

    if not isinstance(data, dict):
        raise ValueError("Mass config must contain a top-level mapping/object.")

    if "mass_properties" in data:
        data = data["mass_properties"]

    if not isinstance(data, dict):
        raise ValueError("'mass_properties' must be a mapping/object.")

    return MassPropertiesConfig.from_dict(data)