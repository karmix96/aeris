"""Read and check the wing YAML; the design vector."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import airfoils as _airfoils

GEOMETRY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = GEOMETRY_ROOT / "configs" / "wing.yaml"
AIRFOIL_DIR = _airfoils.LOCAL_DIR   # project sections; the AERIS database is searched too
STATIONS = ("b0", "b1", "b2", "b3")
TE_MODES = ("rule", "as_is")

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
    airfoils: tuple[str, str, str, str]          # default section per station (first choice)
    ranges: dict[str, tuple[float, float]]
    pinned: dict[str, float] = field(default_factory=dict)
    #: candidate sections per station; a station with more than one is drawn by the sampler
    airfoil_choices: tuple[tuple[str, ...], ...] = ()

    @property
    def free_variables(self) -> tuple[str, ...]:
        """Variables the sampler varies: not pinned, not derived."""
        derived = TAPER_DERIVED if self.chord_law == "linear_taper" else ()
        return tuple(v for v in VARIABLES if v not in self.pinned and v not in derived)

    @property
    def choices(self) -> tuple[tuple[str, ...], ...]:
        return self.airfoil_choices or tuple((a,) for a in self.airfoils)

    @property
    def choice_variables(self) -> tuple[str, ...]:
        """One sampling variable per station that has more than one candidate section."""
        return tuple(f"airfoil_{STATIONS[i]}" for i, c in enumerate(self.choices) if len(c) > 1)

    def block(self) -> dict:
        """The type's YAML block as plain data (for hashing)."""
        return {
            "chord_law": self.chord_law,
            "span_mode": self.span_mode,
            "airfoils": [list(c) for c in self.choices],
            "pinned": dict(sorted(self.pinned.items())),
            "ranges": {k: list(self.ranges[k]) for k in VARIABLES},
        }


@dataclass(frozen=True)
class TERule:
    floor_m: float
    chord_fraction: float
    open_from_xc: float
    #: "rule": thickness = max(floor, fraction x chord). "as_is": keep each section's own
    #: blunt trailing edge (for published wings whose real edge must not change).
    mode: str = "rule"

    def thickness_m(self, chord_m: float) -> float:
        return max(self.floor_m, self.chord_fraction * chord_m)

    def target_m(self, chord_m: float, own_te_over_c: float) -> float:
        """Built trailing-edge thickness for a section of this chord."""
        if self.mode == "as_is":
            return own_te_over_c * chord_m
        return self.thickness_m(chord_m)

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
        mode=str(te_raw.get("mode", "rule")),
    )
    if not 0.0 < te.open_from_xc < 1.0:
        raise ValueError("open_from_xc must be between 0 and 1")
    if te.mode not in TE_MODES:
        raise ValueError(f"trailing_edge.mode must be one of {TE_MODES}")

    types = {name: _read_type(name, raw["types"][name]) for name in WING_TYPES}
    return Config(wing_type, shares, wing_class, te, types, raw.get("sets", {}), raw)


def _read_type(name: str, block: dict) -> TypeSpec:
    if block["chord_law"] not in CHORD_LAWS:
        raise ValueError(f"{name}: chord_law must be one of {CHORD_LAWS}")
    if block["span_mode"] not in SPAN_MODES:
        raise ValueError(f"{name}: span_mode must be one of {SPAN_MODES}")
    choices = read_airfoil_choices(name, block["airfoils"])
    airfoils = tuple(c[0] for c in choices)
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
    multi = any(len(c) > 1 for c in choices)
    return TypeSpec(name, block["chord_law"], block["span_mode"], airfoils, ranges, pinned,
                    choices if multi else ())


def read_airfoil_choices(where: str, raw) -> tuple[tuple[str, ...], ...]:
    """Four entries (b0..b3). Each is one section name or a list of candidates.

    Names come from geometry/airfoils, the AERIS airfoil database, or a NACA
    4/5-digit formula (see airfoils.py).
    """
    if isinstance(raw, dict):
        raw = [raw.get(s) for s in STATIONS]
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise ValueError(f"{where}: need four airfoil entries (b0..b3)")
    out = []
    for s, entry in zip(STATIONS, raw):
        names = (entry,) if isinstance(entry, str) else tuple(entry or ())
        if not names or not all(isinstance(n, str) and n for n in names):
            raise ValueError(f"{where}: station {s} needs a section name or a list of names")
        for n in names:
            if not _airfoils.exists(n):
                raise ValueError(f"{where}: airfoil {n!r} not found (local, AERIS database, or NACA formula)")
        out.append(names)
    return tuple(out)


def station_airfoils(spec: TypeSpec, vec: dict) -> tuple[str, str, str, str]:
    """The section at each station: the vector's own list if it has one, else the type default."""
    names = vec.get("airfoils")
    return tuple(names) if names else spec.airfoils


def from_unit(spec: TypeSpec, unit: dict[str, float]) -> dict[str, float]:
    """Map values in [0, 1] (one per free variable) to a full design vector."""
    vec = {}
    for v in VARIABLES:
        lo, hi = spec.ranges[v]
        vec[v] = lo + float(unit.get(v, 0.5)) * (hi - lo)
    if spec.airfoil_choices:
        # A station with candidates takes the one its unit value falls on (default: the first).
        picks = []
        for s, cands in zip(STATIONS, spec.choices):
            u = unit.get(f"airfoil_{s}")
            k = 0 if u is None else min(int(float(u) * len(cands)), len(cands) - 1)
            picks.append(cands[k])
        vec["airfoils"] = picks
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
    if vec.get("airfoils"):
        names = list(vec["airfoils"])
        if len(names) != 4:
            raise ValueError("vector 'airfoils' needs four names (b0..b3)")
        for n in names:
            if not _airfoils.exists(n):
                raise ValueError(f"airfoil {n!r} not found (local, AERIS database, or NACA formula)")
        out["airfoils"] = names
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
    """One string per vector: fixed key order, values rounded to 12 digits (plus the
    vector's own airfoil list when it has one)."""
    out = {v: round(float(vec[v]), 12) for v in VARIABLES}
    if vec.get("airfoils"):
        out["airfoils"] = list(vec["airfoils"])
    return json.dumps(out, separators=(",", ":"))
