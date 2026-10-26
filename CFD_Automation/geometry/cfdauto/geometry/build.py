"""One function: design vector -> wing folder.

    python -m cfdauto.geometry.build --type bwb --set training --index 7
    python -m cfdauto.geometry.build --type conventional --vector my_wing.json --out somewhere/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from .. import __version__
from . import gates
from .labels import label
from .measure import measure, table_from_loft
from .params import AIRFOIL_DIR, GEOMETRY_ROOT, Config, canonical, load_config, resolve
from .sections import build_wing_sections

SETS_DIR = GEOMETRY_ROOT / "data" / "sets"
WINGS_DIR = GEOMETRY_ROOT / "data" / "wings"


def input_hash(cfg: Config, wing_type: str, vec: dict[str, float]) -> str:
    """sha256 of the content that defines the wing: vector, the type's YAML block,
    the trailing-edge rule, the airfoil files and the code version."""
    spec = cfg.types[wing_type]
    payload = {
        "vector": canonical(resolve(spec, vec)),
        "type": wing_type,
        "type_block": spec.block(),
        "te_rule": {"floor_m": cfg.te.floor_m, "chord_fraction": cfg.te.chord_fraction,
                    "open_from_xc": cfg.te.open_from_xc},
        "airfoils": [hashlib.sha256((AIRFOIL_DIR / f"{a}.dat").read_bytes()).hexdigest() for a in spec.airfoils],
        "code_version": __version__,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _make(cfg: Config, wing_type: str, vec: dict[str, float]):
    from .loft import build_loft
    pf, stations = build_wing_sections(cfg.types[wing_type], vec, cfg.te)
    return pf, stations, build_loft(stations, k_span=2)


def build(vec: dict[str, float], wing_type: str, cfg: Config | None = None,
          out_dir: str | Path | None = None, iges: bool = True) -> dict:
    """Build, measure, label and check one wing. Returns a summary.

    With out_dir: a passed wing writes its full folder; a refused wing writes
    only refusal.json (the gate and the reason).
    """
    cfg = cfg or load_config()
    vec = resolve(cfg.types[wing_type], vec)
    h = input_hash(cfg, wing_type, vec)
    summary = {"wing_type": wing_type, "input_hash": h, "vector": vec}

    try:
        pf, stations, loft = _make(cfg, wing_type, vec)
    except ValueError as exc:      # impossible vector (negative chord, zero span, ...)
        return _refuse(summary, gates.GateResult("validity", False, str(exc)), out_dir)

    measured = measure(table_from_loft(loft), stations)
    checks = [
        gates.vector_to_loft(measured, pf, stations),
        gates.trailing_edge(measured, stations, cfg.te),
        gates.validity(loft, stations),
        gates.repeatability(loft.surface_hash(), _make(cfg, wing_type, vec)[2].surface_hash()),
    ]
    for g in checks:
        if not g.passed:
            return _refuse(summary, g, out_dir)

    labels, label_values = label(measured)
    summary |= {
        "passed": True, "gate": None, "reason": "",
        "surface_hash": loft.surface_hash(), "labels": labels,
        "area_m2": measured["area_m2"], "mac_m": measured["mac_m"],
        "aspect_ratio": measured["aspect_ratio"], "span_m": measured["span_m"],
    }
    if out_dir is not None:
        _write(Path(out_dir), summary, vec, stations, loft, measured, labels, label_values, checks, iges)
    return summary


def _refuse(summary: dict, g: gates.GateResult, out_dir) -> dict:
    summary |= {"passed": False, "gate": g.gate, "reason": g.reason}
    if out_dir is not None:
        out = Path(out_dir)
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        (out / "refusal.json").write_text(json.dumps(summary, indent=2))
    return summary


def _write(out: Path, summary, vec, stations, loft, measured, labels, label_values, checks, iges) -> None:
    if out.exists():
        shutil.rmtree(out)
    (out / "sections").mkdir(parents=True)
    (out / "vector.json").write_text(json.dumps(vec, indent=2))
    (out / "stations.json").write_text(json.dumps([
        {"name": s.name, "y_m": s.y, "x_le_m": s.x_le, "z_le_m": s.z_le, "chord_m": s.chord,
         "twist_deg": s.twist_deg, "airfoil": s.airfoil.name, "v": float(v)}
        for s, v in zip(stations, loft.station_v)], indent=2))
    for i, s in enumerate(stations):
        np.savetxt(out / "sections" / f"{i:02d}_{s.name}.dat", s.airfoil.selig(), fmt="%.12f",
                   header=f"{s.airfoil.name}  unit chord, trailing edge opened", comments="")
    (out / "measured.json").write_text(json.dumps(measured, indent=1))
    (out / "labels.json").write_text(json.dumps({"labels": labels, "values": label_values}, indent=2))
    (out / "gates.json").write_text(json.dumps([g.__dict__ for g in checks], indent=2))
    np.savetxt(out / "span_table.csv", loft.span_table(401), delimiter=",", header="v,y_m", comments="", fmt="%.12f")
    if iges:
        loft.write_iges(out / "wing.igs")
    (out / "summary.json").write_text(json.dumps(summary, indent=2))


def load_set(wing_type: str, set_name: str) -> dict:
    return json.loads((SETS_DIR / wing_type / f"{set_name}.json").read_text())


def wing_dir(wing_type: str, set_name: str, index: int) -> Path:
    return WINGS_DIR / wing_type / set_name / f"{index:03d}"


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Build one wing from a design vector.")
    p.add_argument("--type", required=True, choices=["bwb", "conventional"])
    p.add_argument("--set", help="set name in data/sets/<type>/ (training, corner1, corner2, reference)")
    p.add_argument("--index", type=int)
    p.add_argument("--vector", help="JSON file with one design vector (instead of --set/--index)")
    p.add_argument("--out", help="output folder (default data/wings/<type>/<set>/<index>)")
    p.add_argument("--config", default=None)
    a = p.parse_args(argv)
    cfg = load_config(a.config) if a.config else load_config()
    if a.vector:
        vec = json.loads(Path(a.vector).read_text())
        out = Path(a.out) if a.out else WINGS_DIR / a.type / "single" / Path(a.vector).stem
    else:
        if a.set is None or a.index is None:
            p.error("give --set and --index, or --vector")
        if a.set == "holdout":
            p.error("the hold-out set is sealed: its wings are never built in Stage 1")
        vec = load_set(a.type, a.set)["vectors"][a.index]
        out = Path(a.out) if a.out else wing_dir(a.type, a.set, a.index)
    s = build(vec, a.type, cfg, out)
    if s["passed"]:
        print(f"built {out}  labels: {', '.join(s['labels'])}")
    else:
        print(f"refused by {s['gate']}: {s['reason']}  ({out / 'refusal.json'})")


if __name__ == "__main__":
    main()
