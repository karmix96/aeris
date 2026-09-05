#!/usr/bin/env python
"""Diff two S8 meshes on EVERY metric, not the ones somebody thought to check.

    .venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/compare_meshes.py \
        --a <dir_a> --b <dir_b> --level gci_C --label-a svd --label-b span_normal

Why this exists.  Defect 21 changed the marching plane, and the change was
validated against wall orthogonality, first-cell height, scaled Jacobian and
inverted-cell count -- all unchanged -- while the wing surface moved 1.194e-03 m.
Every metric that was looked at said "fine"; the one that mattered was not
looked at.  Checking a hand-picked subset after a structural change is how that
happens, so this computes the whole set from the block arrays directly rather
than trusting whatever the build summary happens to record.

Metrics, grouped by the question they answer:

  GEOMETRY      is the mesh still on the aircraft?
                wall position against the surface ring, far-field radius,
                root symmetry planarity, block interface matching

  VALIDITY      is it a legal mesh?
                inverted cells, min cell volume, collapsed edges

  QUALITY       is it a good mesh?
                scaled Jacobian distribution (min and percentiles, not just min),
                skewness, aspect ratio, wall orthogonality, cell volume ratio
                between neighbours

  RESOLUTION    does it resolve what it claims to?
                first cell height, leading-edge and trailing-edge spacing,
                spanwise spacing, normal growth ratio

  TOPOLOGY      is it the same mesh structure?
                block shapes and cell counts

Anything that differs by more than a stated tolerance is printed as a CHANGE.
Silence is the pass condition.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def hex_volumes(b: np.ndarray) -> np.ndarray:
    p = [b[:-1, :-1, :-1], b[1:, :-1, :-1], b[1:, 1:, :-1], b[:-1, 1:, :-1],
         b[:-1, :-1, 1:], b[1:, :-1, 1:], b[1:, 1:, 1:], b[:-1, 1:, 1:]]
    c = sum(p) / 8.0
    vol = np.zeros(p[0].shape[:3])
    for f in [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
              (3, 2, 6, 7), (0, 3, 7, 4), (1, 5, 6, 2)]:
        a, bb, cc, dd = [p[k] for k in f]
        m = (a + bb + cc + dd) / 4.0
        for v1, v2 in ((a, bb), (bb, cc), (cc, dd), (dd, a)):
            vol += np.einsum('...i,...i->...', np.cross(v1 - c, v2 - c), (m - c)) / 6.0
    return -vol


def scaled_jacobian(b: np.ndarray) -> np.ndarray:
    """Min over the eight corners of the normalised triple product."""
    corners = [(0, 1, 3, 4), (1, 2, 0, 5), (2, 3, 1, 6), (3, 0, 2, 7),
               (4, 7, 5, 0), (5, 4, 6, 1), (6, 5, 7, 2), (7, 6, 4, 3)]
    p = [b[:-1, :-1, :-1], b[1:, :-1, :-1], b[1:, 1:, :-1], b[:-1, 1:, :-1],
         b[:-1, :-1, 1:], b[1:, :-1, 1:], b[1:, 1:, 1:], b[:-1, 1:, 1:]]
    worst = np.full(p[0].shape[:3], np.inf)
    for o, i, j, k in corners:
        u, v, w = p[i] - p[o], p[j] - p[o], p[k] - p[o]
        n = (np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1)
             * np.linalg.norm(w, axis=-1))
        sj = np.einsum('...i,...i->...', np.cross(u, v), w) / np.maximum(n, 1e-300)
        worst = np.minimum(worst, sj)
    return worst


def metrics(directory: Path, level: str) -> dict:
    blocks = np.load(directory / f"{level}_blocks.npz")
    summary = json.loads((directory / f"{level}_summary.json").read_text())
    out: dict = {}
    wing = blocks["o_wing"]

    # ---- TOPOLOGY -----------------------------------------------------------
    for name in blocks.files:
        out[f"topology/{name}/shape"] = list(blocks[name].shape[:3])
        out[f"topology/{name}/cells"] = int(np.prod([s - 1 for s in blocks[name].shape[:3]]))

    # ---- GEOMETRY -----------------------------------------------------------
    wall = wing[:, 0, :, :]
    out["geometry/wall_layer_error_m"] = _dig(summary, "wall_layer_error_m")
    out["geometry/farfield_radius_m"] = float(
        np.linalg.norm(wing[:, -1, 0, :] - wing[:, -1, 0, :].mean(axis=0), axis=-1).mean())
    out["geometry/root_plane_y_spread_m"] = float(np.ptp(wing[:, :, 0, 1]))
    out["geometry/span_extent_m"] = float(wall[:, :, 1].max() - wall[:, :, 1].min())
    out["geometry/chord_extent_m"] = float(wall[:, :, 0].max() - wall[:, :, 0].min())
    out["geometry/thickness_extent_m"] = float(wall[:, :, 2].max() - wall[:, :, 2].min())
    if "o_out" in blocks.files:
        out["geometry/interface_o_wing_to_o_out_m"] = float(
            np.abs(wing[:, :, -1, :] - blocks["o_out"][:, :, 0, :]).max())

    # ---- VALIDITY -----------------------------------------------------------
    total_neg = 0
    for name in blocks.files:
        v = hex_volumes(blocks[name])
        total_neg += int((v <= 0.0).sum())
        out[f"validity/{name}/min_cell_volume_m3"] = float(v.min())
        out[f"validity/{name}/max_cell_volume_m3"] = float(v.max())
    out["validity/inverted_cells_total"] = total_neg

    # ---- QUALITY ------------------------------------------------------------
    sj = scaled_jacobian(wing)
    for q, lab in ((0.0, "min"), (0.0001, "p001"), (0.001, "p01"),
                   (0.01, "p1"), (0.5, "median")):
        out[f"quality/o_wing/scaled_jacobian_{lab}"] = float(
            sj.min() if lab == "min" else np.quantile(sj, q))
    vol = hex_volumes(wing)
    ratio = np.maximum(vol[:-1] / np.maximum(vol[1:], 1e-300),
                       vol[1:] / np.maximum(vol[:-1], 1e-300))
    out["quality/o_wing/neighbour_volume_ratio_p99"] = float(np.quantile(ratio, 0.99))
    # wall orthogonality: angle between the first marched edge and the surface
    t = np.diff(wall, axis=0)
    t = t / np.maximum(np.linalg.norm(t, axis=-1, keepdims=True), 1e-300)
    e = wing[:-1, 1, :, :] - wing[:-1, 0, :, :]
    e = e / np.maximum(np.linalg.norm(e, axis=-1, keepdims=True), 1e-300)
    ang = np.degrees(np.arcsin(np.clip(np.abs((t * e).sum(-1)), 0, 1)))
    out["quality/wall_nonorthogonality_median_deg"] = float(np.median(ang))
    out["quality/wall_nonorthogonality_p99_deg"] = float(np.quantile(ang, 0.99))
    out["quality/wall_nonorthogonality_max_deg"] = float(ang.max())

    # ---- RESOLUTION ---------------------------------------------------------
    first = np.linalg.norm(wing[:, 1, :, :] - wing[:, 0, :, :], axis=-1)
    out["resolution/first_cell_min_m"] = float(first.min())
    out["resolution/first_cell_max_m"] = float(first.max())
    n_side = (wall.shape[0] - 1 + 2 - _dig(summary, "nose_arc_points", 5)) // 2 + 1
    le = min(n_side - 1, wall.shape[0] - 2)
    mid = wall.shape[1] // 2
    out["resolution/ds_le_midspan_m"] = float(np.linalg.norm(wall[le + 1, mid] - wall[le, mid]))
    out["resolution/ds_te_midspan_m"] = float(np.linalg.norm(wall[1, mid] - wall[0, mid]))
    span = np.linalg.norm(np.diff(wall[0, :, :], axis=0), axis=-1)
    out["resolution/ds_span_min_m"] = float(span.min())
    out["resolution/ds_span_max_m"] = float(span.max())
    layer = np.linalg.norm(np.diff(wing[:, :, mid, :], axis=1), axis=-1)
    growth = layer[:, 1:] / np.maximum(layer[:, :-1], 1e-300)
    out["resolution/normal_growth_max"] = float(growth.max())
    out["resolution/worst_le_turn_deg"] = _dig(summary, "worst_le_turn_per_cell_deg")
    return out


def _dig(o, key, default=None):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                return v
            r = _dig(v, key, None)
            if r is not None:
                return r
    return default


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", type=Path, required=True)
    ap.add_argument("--b", type=Path, required=True)
    ap.add_argument("--level", default="gci_C")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--rtol", type=float, default=1e-6,
                    help="relative change above which a metric is flagged")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    ma = metrics(args.a, args.level)
    mb = metrics(args.b, args.level)
    keys = sorted(set(ma) | set(mb))

    changed, same, missing = [], [], []
    for k in keys:
        va, vb = ma.get(k), mb.get(k)
        if va is None or vb is None:
            missing.append((k, va, vb)); continue
        if isinstance(va, list):
            (same if va == vb else changed).append((k, va, vb, "")); continue
        if va is None or vb is None:
            missing.append((k, va, vb)); continue
        d = abs(vb - va)
        rel = d / max(abs(va), 1e-300)
        (changed if rel > args.rtol else same).append((k, va, vb, f"{rel:.2e}"))

    print(f"\n{args.level}:  A = {args.label_a}   B = {args.label_b}")
    print(f"metrics compared: {len(keys)}   unchanged: {len(same)}   "
          f"CHANGED: {len(changed)}   missing: {len(missing)}\n")
    if changed:
        print(f"{'metric':<48}{args.label_a:>16}{args.label_b:>16}{'rel':>10}")
        for k, va, vb, rel in changed:
            fa = f"{va:.6g}" if not isinstance(va, list) else str(va)
            fb = f"{vb:.6g}" if not isinstance(vb, list) else str(vb)
            print(f"  {k:<46}{fa:>16}{fb:>16}{rel:>10}")
    else:
        print("  no metric changed by more than the tolerance")
    for k, va, vb in missing:
        print(f"  MISSING  {k}: A={va} B={vb}")

    if args.out:
        args.out.write_text(json.dumps(
            {"level": args.level, "a": {"label": args.label_a, "dir": str(args.a), "metrics": ma},
             "b": {"label": args.label_b, "dir": str(args.b), "metrics": mb},
             "changed": [k for k, *_ in changed]}, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
