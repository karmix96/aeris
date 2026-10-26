"""Read and check the wing YAML; the design vector."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

GEOMETRY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = GEOMETRY_ROOT / "configs" / "wing.yaml"
AIRFOIL_DIR = GEOMETRY_ROOT / "airfoils"

VARIABLES = (
    "root_chord_m", "c2_ratio", "c3_ratio", "c4_ratio",
    "semi_span_m", "b3_ratio", "split_ratio",
    "sweep1_deg", "sweep2_deg", "sweep3_deg",
    "twist0_deg", "twist1_deg", "twist2_deg", "twist3_deg",
    "dihedral0_deg", "dihedral1_deg", "dihedral2_deg", "dihedral3_deg",
)
WING_TYPES = ("bwb", "conventional")
CHORD_LAWS = ("stations", "linear_taper")
SPAN_MODES = ("semi_span", "root_chord_fractions")
# Variables that linear_taper computes instead of sampling.
TAPER_DERIVED = ("c2_ratio", "c3_ratio")


@dataclass(frozen=True)
class TypeSpec:
    name: str
    chord_law: str
    span_mode: str
    airfoils: tuple[str, str, str, str]
    ranges: dict[str, tuple[float, float]]
    pinned: dict[str, float] = field(default_factory=dict)

    @property
    def free_variables(self) -> tuple[str, ...]:
        """Variables the sampler varies: not pinned, not derived."""
        derived = TAPER_DERIVED if self.chord_law == "linear_taper" else ()
        return tuple(v for v in VARIABLES if v not in self.pinned and v not in derived)

    def block(self) -> dict:
        """The type's YAML block as plain data (for hashing)."""
        return {
            "chord_law": self.chord_law,
            "span_mode": self.span_mode,
            "airfoils": list(self.airfoils),
            "pinned": dict(sorted(self.pinned.items())),
            "ranges": {k: list(self.ranges[k]) for k in VARIABLES},
        }


@dataclass(frozen=True)
class TERule:
    floor_m: float
    chord_fraction: float
    open_from_xc: float

    def thickness_m(self, chord_m: float) -> float:
        return max(self.floor_m, self.chord_fraction * chord_m)

    def switch_chord_m(self) -> float:
        """Chord at which the rule changes from the floor to the fraction."""
        return self.floor_m / self.chord_fraction


@dataclass(frozen=True)
class Config:
    wing_type: str
    shares: dict[str, float]
    wing_class: str
    te: TERule
    types: dict[str, TypeSpec]
    sets: dict
    raw: dict


def load_config(path: str | Path = DEFAULT_CONFIG) -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    wing_type = raw["wing_type"]
    if wing_type not in (*WING_TYPES, "mixed"):
        raise ValueError(f"wing_type must be bwb, conventional or mixed, got {wing_type!r}")
    shares = {k: float(v) for k, v in raw.get("shares", {}).items()}
    if wing_type == "mixed":
        if set(shares) != set(WING_TYPES) or not math.isclose(sum(shares.values()), 1.0):
            raise ValueError("mixed needs shares for bwb and conventional that sum to 1")

    wing_class = str(raw["wing_class"])
    te_raw = raw["trailing_edge"]
    if wing_class not in te_raw["floor_m"]:
        raise ValueError(f"no trailing-edge floor for wing_class {wing_class!r}")
    te = TERule(
        floor_m=float(te_raw["floor_m"][wing_class]),
        chord_fraction=float(te_raw["chord_fraction"]),
        open_from_xc=float(te_raw["open_from_xc"]),
    )
    if not 0.0 < te.open_from_xc < 1.0:
        raise ValueError("open_from_xc must be between 0 and 1")

    types = {name: _read_type(name, raw["types"][name]) for name in WING_TYPES}
    return Config(wing_type, shares, wing_class, te, types, raw.get("sets", {}), raw)


def _read_type(name: str, block: dict) -> TypeSpec:
    if block["chord_law"] not in CHORD_LAWS:
        raise ValueError(f"{name}: chord_law must be one of {CHORD_LAWS}")
    if block["span_mode"] not in SPAN_MODES:
        raise ValueError(f"{name}: span_mode must be one of {SPAN_MODES}")
    airfoils = tuple(block["airfoils"])
    if len(airfoils) != 4:
        raise ValueError(f"{name}: need four airfoils (b0..b3)")
    for a in airfoils:
        if not (AIRFOIL_DIR / f"{a}.dat").is_file():
            raise ValueError(f"{name}: airfoil {a!r} not found in {AIRFOIL_DIR}")
    ranges = {}
    for v in VARIABLES:
        if v not in block["ranges"]:
            raise ValueError(f"{name}: missing range for {v}")
        lo, hi = (float(x) for x in block["ranges"][v])
        if lo > hi:
            raise ValueError(f"{name}: range for {v} has min > max")
        ranges[v] = (lo, hi)
    extra = set(block["ranges"]) - set(VARIABLES)
    if extra:
        raise ValueError(f"{name}: unknown variables {sorted(extra)}")
    pinned = {k: float(v) for k, v in (block.get("pinned") or {}).items()}
    unknown = set(pinned) - set(VARIABLES)
    if unknown:
        raise ValueError(f"{name}: cannot pin unknown variables {sorted(unknown)}")
    return TypeSpec(name, block["chord_law"], block["span_mode"], airfoils, ranges, pinned)


def from_unit(spec: TypeSpec, unit: dict[str, float]) -> dict[str, float]:
    """Map values in [0, 1] (one per free variable) to a full design vector."""
    vec = {}
    for v in VARIABLES:
        lo, hi = spec.ranges[v]
        vec[v] = lo + float(unit.get(v, 0.5)) * (hi - lo)
    return resolve(spec, vec)


def to_unit(spec: TypeSpec, vec: dict[str, float]) -> list[float]:
    """Free variables scaled to [0, 1] (0.5 where a range has zero width)."""
    out = []
    for v in spec.free_variables:
        lo, hi = spec.ranges[v]
        out.append(0.5 if hi == lo else (vec[v] - lo) / (hi - lo))
    return out


def mid_vector(spec: TypeSpec) -> dict[str, float]:
    return from_unit(spec, {})


def resolve(spec: TypeSpec, vec: dict[str, float]) -> dict[str, float]:
    """Apply pinned values and the chord law. Returns a new full vector."""
    check_vector(vec)
    out = {v: float(vec[v]) for v in VARIABLES}
    out.update(spec.pinned)
    if spec.chord_law == "linear_taper":
        # Chord linear from root to tip: c(y) = c_root * (1 + (c4 - 1) * y / S).
        p3 = out["b3_ratio"]
        y1 = (1.0 - p3) * out["split_ratio"]
        y2 = 1.0 - p3
        out["c2_ratio"] = 1.0 + (out["c4_ratio"] - 1.0) * y1
        out["c3_ratio"] = 1.0 + (out["c4_ratio"] - 1.0) * y2
    return out


def check_vector(vec: dict[str, float]) -> None:
    missing = [v for v in VARIABLES if v not in vec]
    if missing:
        raise ValueError(f"design vector is missing {missing}")
    bad = [v for v in VARIABLES if not math.isfinite(float(vec[v]))]
    if bad:
        raise ValueError(f"design vector has non-finite values for {bad}")


def in_ranges(spec: TypeSpec, vec: dict[str, float], tol: float = 1e-12) -> bool:
    for v in spec.free_variables:
        lo, hi = spec.ranges[v]
        if not lo - tol <= vec[v] <= hi + tol:
            return False
    return True


def canonical(vec: dict[str, float]) -> str:
    """One string per vector: fixed key order, values rounded to 12 digits."""
    return json.dumps({v: round(float(vec[v]), 12) for v in VARIABLES}, separators=(",", ":"))
