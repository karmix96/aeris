"""Reference wings of both types: planform and front view, same scale.

Reads the built wings in data/wings/<type>/reference/; writes figures/reference_wings.png.

    python scripts/plot_reference_wings.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TYPES = ("bwb", "conventional", "tapered")


def load(wing_type):
    rules = json.loads((ROOT / "data" / "sets" / wing_type / "reference.json").read_text())["rules"]
    out = []
    for i, rule in enumerate(rules):
        d = ROOT / "data" / "wings" / wing_type / "reference" / f"{i:03d}"
        if not (d / "measured.json").is_file():
            out.append((rule, None))
            continue
        a = {k: np.asarray(v) for k, v in json.loads((d / "measured.json").read_text())["along_span"].items()}
        a["x_te"] = a["x_le"] + a["chord"] * np.cos(np.radians(a["twist_deg"]))
        out.append((rule, a))
    return out


def main():
    wings = {t: load(t) for t in TYPES}
    built = [a for t in TYPES for _, a in wings[t] if a is not None]
    span = max(a["y"][-1] for a in built)
    dx = max(a["x_te"].max() for a in built) + 0.4             # planform spacing between wings
    dz = max(np.ptp(a["z_le"]) for a in built) + 0.25          # front-view spacing

    fig, axes = plt.subplots(2, 2, figsize=(18, 12), sharex=True,
                             gridspec_kw={"height_ratios": [5 * dx, 5 * dz]})
    for col, t in enumerate(TYPES):
        top, front = axes[0, col], axes[1, col]
        for k, (rule, a) in enumerate(wings[t]):
            label = rule.replace("_", " ")
            if a is None:
                top.text(0, k * dx + 0.5, f"{label}: refused", ha="center")
                continue
            for sgn in (1, -1):
                top.plot(sgn * a["y"], k * dx + a["x_le"], "k-", lw=1)
                top.plot(sgn * a["y"], k * dx + a["x_te"], "k-", lw=1)
                top.plot(sgn * a["y"][[-1, -1]], k * dx + np.array([a["x_le"][-1], a["x_te"][-1]]), "k-", lw=1)
                front.plot(sgn * a["y"], -k * dz + a["z_le"], "k-", lw=1)
            top.text(-span, k * dx + 0.15, label, fontsize=9, va="top")
            front.text(-span, -k * dz + 0.08, label, fontsize=9)
        top.set_title(f"{t}: planform (x down = downstream)", fontsize=10)
        front.set_title(f"{t}: front view (leading edge)", fontsize=10)
        top.set_ylim(5 * dx, -0.2)
        front.set_ylim(-4 * dz - 0.15, dz)
        for ax in (top, front):
            ax.set_xlim(-span * 1.02, span * 1.02)
            ax.set_aspect("equal")
            ax.tick_params(labelsize=8)
        top.set_ylabel("x [m] (wings offset)", fontsize=9)
        front.set_ylabel("z [m] (wings offset)", fontsize=9)
        front.set_xlabel("y [m]", fontsize=9)
    fig.suptitle("Reference wings, all at one scale", fontsize=12)
    fig.tight_layout()
    out = ROOT / "figures" / "reference_wings.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=120)
    print(out)


if __name__ == "__main__":
    main()
