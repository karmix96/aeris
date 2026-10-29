"""Published wings, rebuilt with the same generator: ONERA M6, RIBES, NASA CRM, BlendedNet.

    python -m cfdauto.geometry.published_wings --list
    python -m cfdauto.geometry.published_wings --build onera_m6        # needs pyGeo
    python -m cfdauto.geometry.published_wings --build all

Any BlendedNet or BlendedNet++ design can be made from its own parameters:

    from cfdauto.geometry.published_wings import blendednet
    spec, vec, te, meta = blendednet(C2=0.7, C3=0.23, C4=0.075, B1=0.15, B2=0.125, B3=0.45,
                                     S1=50, S2=50, S3=32)

The definitions, sources and how close each copy is live in
configs/published_wings.yaml.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import yaml

from .params import GEOMETRY_ROOT, VARIABLES, TERule, TypeSpec, load_config, read_airfoil_choices, resolve

PUBLISHED_FILE = GEOMETRY_ROOT / "configs" / "published_wings.yaml"
OUT_DIR = GEOMETRY_ROOT / "data" / "wings" / "published_wings"


def _raw() -> dict:
    return yaml.safe_load(PUBLISHED_FILE.read_text())


def names() -> list[str]:
    raw = _raw()
    return list(raw["wings"]) + list(raw["blendednet"]["cases"])


def _te(mode: str) -> TERule:
    base = load_config().te
    return TERule(base.floor_m, base.chord_fraction, base.open_from_xc, mode)


def _spec(name: str, chord_law: str, span_mode: str, airfoils, vec: dict) -> TypeSpec:
    """A type block whose every range is the single value of this wing."""
    choices = read_airfoil_choices(name, airfoils)
    full = {v: float(vec.get(v, 1.0)) for v in VARIABLES}
    spec = TypeSpec(name, chord_law, span_mode, tuple(c[0] for c in choices),
                    {v: (full[v], full[v]) for v in VARIABLES})
    resolved = resolve(spec, full)
    return TypeSpec(name, chord_law, span_mode, spec.airfoils, {v: (resolved[v], resolved[v]) for v in VARIABLES})


def blendednet(C2: float, C3: float, C4: float, B1: float, B2: float, B3: float,
               S1: float, S3: float, S2: float | None = None, X3: float | None = None,
               c1_m: float | None = None, airfoils=None, name: str = "blendednet") -> tuple:
    """A BlendedNet (S2 given) or BlendedNet++ (X3 given) design in our variables.

    Lengths are fractions of the centreline chord C1. BlendedNet++ gives the
    leading edge of station 3, X3, instead of the middle sweep:
        S2 = atan((X3 - B1 tan S1) / B2).
    """
    bn = _raw()["blendednet"]
    if (S2 is None) == (X3 is None):
        raise ValueError("give exactly one of S2 (BlendedNet) or X3 (BlendedNet++)")
    if S2 is None:
        S2 = math.degrees(math.atan((X3 - B1 * math.tan(math.radians(S1))) / B2))
    total = B1 + B2 + B3
    vec = {
        "root_chord_m": float(c1_m if c1_m is not None else bn["c1_m"]),
        "c2_ratio": C2, "c3_ratio": C3, "c4_ratio": C4,
        "semi_span_m": total,                 # in root chords (span_mode root_chord_fractions)
        "b3_ratio": B3 / total,
        "split_ratio": B1 / (B1 + B2),
        "sweep1_deg": S1, "sweep2_deg": S2, "sweep3_deg": S3,
        **{f"twist{i}_deg": 0.0 for i in range(4)},
        **{f"dihedral_p{i}_deg": 0.0 for i in (1, 2, 3)},
    }
    af = airfoils or bn["airfoils"]
    spec = _spec(name, "stations", "root_chord_fractions", af, vec)
    meta = {"name": name, "title": f"BlendedNet design {name}", "kind": "bwb",
            "sources": bn["sources"], "trailing_edge": bn["trailing_edge"],
            "blendednet_parameters": {"C2": C2, "C3": C3, "C4": C4, "B1": B1, "B2": B2, "B3": B3,
                                      "S1": S1, "S2": S2, "S3": S3, **({"X3": X3} if X3 is not None else {})},
            "fidelity": ("Planform exact in the BlendedNet parameters (straight panels, as OpenVSP builds them). "
                         "Airfoils as BlendedNet++ Table 4; NACA 25118 made from the NACA formula. "
                         "Twist and dihedral zero (not stated in the papers).")}
    return spec, resolve(spec, vec), _te(bn["trailing_edge"]), meta


def get(name: str) -> tuple[TypeSpec, dict, TERule, dict]:
    """(type block, design vector, trailing-edge rule, metadata) for a named published wing."""
    raw = _raw()
    if name in raw["wings"]:
        w = raw["wings"][name]
        spec = _spec(name, w["chord_law"], w["span_mode"], w["airfoils"], w["vector"])
        vec = resolve(spec, {v: float(w["vector"].get(v, spec.ranges[v][0])) for v in VARIABLES})
        meta = {k: w[k] for k in ("title", "kind", "use", "sources", "fidelity", "trailing_edge")} | {"name": name}
        return spec, vec, _te(w["trailing_edge"]), meta
    cases = raw["blendednet"]["cases"]
    if name in cases:
        return blendednet(**cases[name], name=name)
    raise KeyError(f"unknown published wing {name!r}; known: {names()}")


def build_published(name: str, out_dir: str | Path | None = None, iges: bool = True) -> dict:
    """Loft, measure, label and check one published wing (needs pyGeo)."""
    from .build import build_spec

    spec, vec, te, meta = get(name)
    out = Path(out_dir) if out_dir else OUT_DIR / name
    return build_spec(spec, vec, te, f"published:{name}", out, iges, extra={"published": meta})


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Rebuild published wings with the generator.")
    p.add_argument("--list", action="store_true")
    p.add_argument("--build", help="a name from --list, or 'all'")
    p.add_argument("--out")
    a = p.parse_args(argv)
    if a.list or not a.build:
        for n in names():
            _, vec, _, meta = get(n)
            print(f"{n:18s} {meta['kind']:13s} {meta['title']}")
        return
    for n in (names() if a.build == "all" else [a.build]):
        s = build_published(n, Path(a.out) / n if a.out and a.build == "all" else a.out)
        state = f"built, labels: {', '.join(s['labels'])}" if s["passed"] else f"refused by {s['gate']}: {s['reason']}"
        print(f"{n:18s} {state}")


if __name__ == "__main__":
    main()
