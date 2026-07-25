"""Is the native-vs-ASB residual caused by the airfoil COORDINATE resolution?

Task 3 attributed the residual CL (~0.7 %), CDind (~2.4 %) and speed-derivative
offsets to a difference in how many airfoil points each writer puts in the .avl.
That was asserted, not proved -- and the direction was stated wrongly: the native
writer emits 159 points per section (cst_points=80 -> 2n-1), while AeroSandbox's
AVL exporter downsamples to 99. The NATIVE side is the finer one.

Decisive test: re-run the native path at cst_points=50, which yields exactly 99
points and so matches AeroSandbox's discretisation. If the residual collapses,
the mechanism is confirmed and the native answer is the better-resolved of the
two. If it does not, there is a second cause and the story is incomplete.

Also sweeps the native resolution upward to establish which side is converged --
because "the two codes agree" is worth much less than "the two codes agree AND we
know which one is right".

Usage:
    python standalone/lowfi_avl_study/probe_airfoil_resolution.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "lowfi_avl_study" / "airfoil_resolution_probe"

ALPHA = 6.0
ELEVON_DEG = 4.0
VELOCITY = 28.0
N_SECTIONS = 25
SEEDS = [7000, 7005, 7024]          # 7005 / 7024 are the worst-|Cmu| cases
# cst_points -> points written per section = 2*n - 1
CST_LEVELS = [50, 80, 120, 160, 180]   # 99, 159, 239, 319, 359 points

TRACK = [
    ("CL", lambda r: r.cl),
    ("CDind", lambda r: r.cd_ind),
    ("cd_total", lambda r: r.cd_total),
    ("Cm", lambda r: r.cm),
    ("CLa", lambda r: (r.stability_axis_derivatives or {}).get("CLa")),
    ("Cma", lambda r: (r.stability_axis_derivatives or {}).get("Cma")),
    ("Cmu", lambda r: (r.body_axis_derivatives or {}).get("Cmu")),
    ("CZu", lambda r: (r.body_axis_derivatives or {}).get("CZu")),
    ("CXu", lambda r: (r.body_axis_derivatives or {}).get("CXu")),
]


def main() -> None:
    from aeris.aero.models import FlightCondition
    from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
        build_pygeo_sections_from_config,
        run_pygeo_avl_case,
        run_pygeo_native_avl_case,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    config = REPO / "configs" / "geometry" / "bwb.yaml"
    results: dict = {}

    for seed in SEEDS:
        ex, semispan, meta = build_pygeo_sections_from_config(
            config, n_sections=N_SECTIONS, seed=seed
        )
        fc = FlightCondition(alpha_deg=ALPHA, beta_deg=0.0, velocity_mps=VELOCITY,
                             altitude_m=0.0)
        entry: dict = {"native": {}, "asb": None}

        for cst in CST_LEVELS:
            res = run_pygeo_native_avl_case(
                flight_condition=fc, output_dir=OUT / f"seed{seed}" / f"cst{cst}",
                extracted_sections=ex, semispan_m=semispan, control=meta["control"],
                control_input_deg=ELEVON_DEG, diff_input_deg=0.0, viscous=True,
                name="native",
            ) if cst == 80 else None
            if res is None:
                # cst_points is a writer argument, so drive the runner directly.
                from aeris.aero.solvers.native_avl import run_native_avl_case
                from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
                    build_realized_section_polar_bridge,
                )
                section_map, polar_store = build_realized_section_polar_bridge(
                    ex, semispan_m=semispan, mach=0.0
                )
                res = run_native_avl_case(
                    sorted(ex, key=lambda s: float(s.y_m)),
                    flight_condition=fc,
                    output_dir=OUT / f"seed{seed}" / f"cst{cst}",
                    section_map=section_map, polar_store=polar_store,
                    control=meta["control"], control_input_deg=ELEVON_DEG,
                    diff_input_deg=0.0, cst_points=cst, name="native",
                )
            af = OUT / f"seed{seed}" / f"cst{cst}" / "airplane.avl.af0"
            entry["native"][cst] = {
                "status": res.status,
                "points_written": len(af.read_text().splitlines()) if af.exists() else None,
                **{name: fn(res) for name, fn in TRACK},
            }

        asb = run_pygeo_avl_case(
            flight_condition=fc, output_dir=OUT / f"seed{seed}" / "asb",
            extracted_sections=ex, semispan_m=semispan, control=meta["control"],
            viscous=True, name="asb",
            paneling={"spanwise_resolution": 4, "chordwise_resolution": 8},
            control_input_deg=ELEVON_DEG, diff_input_deg=0.0,
        )
        af = OUT / f"seed{seed}" / "asb" / "airplane.avl.af0"
        stab = asb.stability_axis_derivatives or {}
        body = asb.body_axis_derivatives or {}
        entry["asb"] = {
            "points_written": len(af.read_text().splitlines()) if af.exists() else None,
            "CL": asb.cl, "CDind": asb.cd_ind, "cd_total": asb.cd_total,
            "Cm": asb.cm, "CLa": stab.get("CLa"), "Cma": stab.get("Cma"),
            "Cmu": body.get("Cmu"), "CZu": body.get("CZu"), "CXu": body.get("CXu"),
        }
        results[seed] = entry
        print(f"seed {seed} done")

    (OUT / "airfoil_resolution.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )

    # ---- report --------------------------------------------------------------
    L = ["Airfoil coordinate-resolution probe",
         "native cst_points -> points written = 2n-1;  AeroSandbox writes 99", ""]
    for seed, entry in results.items():
        asb = entry["asb"]
        L += [f"=== seed {seed} ===",
              f"{'variant':<14}{'pts':>6}" + "".join(f"{k:>11}" for k, _ in TRACK)]
        for cst, r in entry["native"].items():
            tag = f"native cst{cst}"
            L.append(f"{tag:<14}{r['points_written'] or 0:>6}" +
                     "".join(f"{(r[k] if r[k] is not None else float('nan')):>11.6f}"
                             for k, _ in TRACK))
        L.append(f"{'ASB':<14}{asb['points_written'] or 0:>6}" +
                 "".join(f"{(asb.get(k) if asb.get(k) is not None else float('nan')):>11.6f}"
                         for k, _ in TRACK))
        # Does matching the resolution (cst 50 = 99 pts) close the gap?
        L.append("")
        L.append(f"{'rel diff vs ASB':<14}{'':>6}" + "".join(f"{k:>11}" for k, _ in TRACK))
        for cst in (50, 80, 180):
            r = entry["native"].get(cst)
            if not r:
                continue
            cells = []
            for k, _ in TRACK:
                a, b = r.get(k), asb.get(k)
                if a is None or b is None or max(abs(a), abs(b)) < 1e-12:
                    cells.append(f"{'-':>11}")
                else:
                    cells.append(f"{abs(a - b) / max(abs(a), abs(b)):>11.2e}")
            L.append(f"{'cst' + str(cst):<14}{'':>6}" + "".join(cells))
        L.append("")

    # Native self-convergence: is the native answer converged in cst_points?
    L += ["Native SELF-convergence in airfoil resolution "
          "(rel change vs the finest, cst=180):", ""]
    L.append(f"{'seed':>6}{'cst':>6}" + "".join(f"{k:>11}" for k, _ in TRACK))
    for seed, entry in results.items():
        fine = entry["native"][CST_LEVELS[-1]]
        for cst in CST_LEVELS[:-1]:
            r = entry["native"][cst]
            cells = []
            for k, _ in TRACK:
                a, b = r.get(k), fine.get(k)
                if a is None or b is None or max(abs(a), abs(b)) < 1e-12:
                    cells.append(f"{'-':>11}")
                else:
                    cells.append(f"{abs(a - b) / max(abs(a), abs(b)):>11.2e}")
            L.append(f"{seed:>6}{cst:>6}" + "".join(cells))

    text = "\n".join(L)
    print("\n" + text)
    (OUT / "airfoil_resolution.txt").write_text(text + "\n", encoding="utf-8")
    print(f"\nwrote {OUT / 'airfoil_resolution.json'}")


if __name__ == "__main__":
    main()
