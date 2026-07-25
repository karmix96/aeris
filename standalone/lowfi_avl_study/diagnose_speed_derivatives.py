"""Diagnose the Cmu / CZu (speed-derivative) disagreement between the two AVL paths.

Task 3 found Cmu and CZu disagree by up to 10.3 % / 4.2 % while every other
well-conditioned derivative agrees to <= 1.7 %. An earlier ablation appeared to
rule out the `.avl` header Mach -- but it dumped only `st`, and Cmu/CZu come from
`sb` (the geometry-axis dump). That test was therefore inconclusive for exactly
the quantities in question. This redoes it properly.

Hypotheses tested, each independently:

  H1  header Mach. The native writer puts the operating Mach in the .avl header;
      AeroSandbox writes 0 and relies on OPER `mn`. If AVL uses the header value
      for the Prandtl-Glauert transform of the LATTICE at load time, the two
      paths would build different lattices while reporting the same run Mach.
      Test: same .avl, header Mach in {0, 0.0823}, dump `sb`.

  H2  Mach sensitivity. If dCmu/dM is steep at M ~ 0.08, then any tiny
      difference in effective Mach is amplified into the u-derivatives while
      leaving alpha-derivatives untouched. Test: sweep the OPER Mach.

  H3  reference-length normalisation. Cmu is normalised by Cref, which differs
      0.13 % between paths (native int c^2 dy / S vs ASB mean_aerodynamic_chord).
      Test: rewrite Cref in the header and measure the induced change in Cmu.

  H4  conditioning. If Cmu is a small residual of large terms, its relative
      error is amplified from the ~0.5 % CL difference. Test: compare
      d(Cmu)/d(alpha) against d(Cma)/d(alpha) -- i.e. how much Cmu moves for a
      perturbation that moves CL by 0.5 %.

Usage:
    python standalone/lowfi_avl_study/diagnose_speed_derivatives.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "lowfi_avl_study" / "speed_derivative_diagnosis"

ALPHA = 6.0
MACH_RUN = 0.08228176556477905
ELEVON_DEG = 4.0


def run_avl(avl_dir: Path, *, alpha: float, mach: float) -> dict:
    """Run AVL on an existing .avl and return totals + BOTH derivative dumps."""
    from aeris.aero.solvers.avl_output import (
        parse_stability_file,
        parse_totals_text,
    )

    keys = [
        "plop", "g", "", "oper", "o", "r", "d", "",
        "m", f"mn {mach}", "v 28.0", "d 1.225", "g 9.81", "",
        f"a a {alpha}", "b b 0",
        "d1", "d1", f"{ELEVON_DEG}", "d2", "d2", "0.0",
        "x", "ft", "t.txt", "st", "s.txt", "sb", "b.txt", "", "quit",
    ]
    for f in ("t.txt", "s.txt", "b.txt"):
        (avl_dir / f).unlink(missing_ok=True)
    with open(avl_dir / "log.txt", "w") as lg:
        p = subprocess.Popen(["avl", "airplane.avl"], cwd=avl_dir,
                             stdin=subprocess.PIPE, stdout=lg, stderr=lg, text=True)
        p.communicate("\n".join(keys), timeout=300)

    tot = parse_totals_text((avl_dir / "t.txt").read_text())
    st = parse_stability_file(avl_dir / "s.txt")
    sb = parse_stability_file(avl_dir / "b.txt")
    return {
        "Mach_run": tot.get("Mach"), "CL": tot.get("CLtot"), "Cm": tot.get("Cmtot"),
        "Cref": tot.get("Cref"), "Bref": tot.get("Bref"), "Sref": tot.get("Sref"),
        "CLa": st.get("CLa"), "Cma": st.get("Cma"),
        "CXu": sb.get("CXu"), "CZu": sb.get("CZu"), "Cmu": sb.get("Cmu"),
        "CZw": sb.get("CZw"), "Cmw": sb.get("Cmw"),
    }


def stage(src: Path, dst: Path, *, header_mach=None, cref=None) -> Path:
    """Copy an .avl case, optionally rewriting the header Mach or Cref."""
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("airplane.avl.af*"):
        shutil.copy(f, dst / f.name)
    lines = (src / "airplane.avl").read_text().splitlines()
    if header_mach is not None:
        lines[2] = str(header_mach)              # the #Mach value line
    if cref is not None:
        sref, _, bref = lines[6].split()          # "#Sref Cref Bref" value line
        lines[6] = f"{sref} {cref} {bref}"
    (dst / "airplane.avl").write_text("\n".join(lines) + "\n")
    return dst


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    src = REPO / "data/lowfi_avl_study/doe_native_vs_asb/seed7000/visc_native"
    if not (src / "airplane.avl").exists():
        raise SystemExit(f"missing {src}; run doe_native_vs_asb.py first")

    report: dict = {}

    # ---- H1: header Mach, dumping sb this time -------------------------------
    h1 = {}
    for tag, hm in (("header_0", "0"), ("header_run_mach", MACH_RUN)):
        d = stage(src, OUT / f"h1_{tag}", header_mach=hm)
        h1[tag] = run_avl(d, alpha=ALPHA, mach=MACH_RUN)
    a, b = h1["header_0"], h1["header_run_mach"]
    h1["delta_Cmu_pct"] = 100 * abs(a["Cmu"] - b["Cmu"]) / abs(b["Cmu"])
    h1["delta_CZu_pct"] = 100 * abs(a["CZu"] - b["CZu"]) / abs(b["CZu"])
    h1["delta_CL_pct"] = 100 * abs(a["CL"] - b["CL"]) / abs(b["CL"])
    report["H1_header_mach"] = h1

    # ---- H2: Mach sensitivity of the u-derivatives ---------------------------
    d = stage(src, OUT / "h2_mach_sweep", header_mach=MACH_RUN)
    h2 = {}
    for m in (0.0, 0.02, 0.05, MACH_RUN, 0.12, 0.20):
        h2[f"M={m:.5f}"] = run_avl(d, alpha=ALPHA, mach=m)
    report["H2_mach_sweep"] = h2

    # ---- H3: Cref normalisation ---------------------------------------------
    base_cref = h1["header_run_mach"]["Cref"]
    d0 = stage(src, OUT / "h3_cref_base", header_mach=MACH_RUN)
    r0 = run_avl(d0, alpha=ALPHA, mach=MACH_RUN)
    # +0.13 %, the measured native-vs-ASB Cref gap
    d1 = stage(src, OUT / "h3_cref_plus", header_mach=MACH_RUN,
               cref=f"{base_cref * 1.0013:.10g}")
    r1 = run_avl(d1, alpha=ALPHA, mach=MACH_RUN)
    report["H3_cref"] = {
        "cref_base": r0["Cref"], "cref_perturbed": r1["Cref"],
        "cref_change_pct": 100 * abs(r1["Cref"] - r0["Cref"]) / r0["Cref"],
        "Cmu_change_pct": 100 * abs(r1["Cmu"] - r0["Cmu"]) / abs(r0["Cmu"]),
        "CZu_change_pct": 100 * abs(r1["CZu"] - r0["CZu"]) / abs(r0["CZu"]),
        "Cma_change_pct": 100 * abs(r1["Cma"] - r0["Cma"]) / abs(r0["Cma"]),
    }

    # ---- H4: conditioning — how much does Cmu move for a small alpha change? -
    d = stage(src, OUT / "h4_alpha", header_mach=MACH_RUN)
    h4 = {}
    for al in (ALPHA - 0.1, ALPHA, ALPHA + 0.1):
        h4[f"alpha={al:.2f}"] = run_avl(d, alpha=al, mach=MACH_RUN)
    lo, mid, hi = h4[f"alpha={ALPHA - 0.1:.2f}"], h4[f"alpha={ALPHA:.2f}"], h4[f"alpha={ALPHA + 0.1:.2f}"]
    # Sensitivity ratio: fractional change in each quantity per fractional
    # change in CL. >> 1 means the quantity is ill-conditioned relative to CL.
    dcl = abs(hi["CL"] - lo["CL"]) / abs(mid["CL"])
    h4["amplification_vs_CL"] = {
        key: (abs(hi[key] - lo[key]) / abs(mid[key])) / dcl if dcl > 0 else None
        for key in ("Cmu", "CZu", "CXu", "Cma", "CLa", "CZw", "Cmw")
    }
    h4["dCL_fractional"] = dcl
    report["H4_conditioning"] = h4

    (OUT / "diagnosis.json").write_text(json.dumps(report, indent=2, default=str),
                                        encoding="utf-8")

    # ---- report --------------------------------------------------------------
    L = ["Speed-derivative (Cmu / CZu) diagnosis", ""]
    L += [
        "H1 — .avl HEADER Mach (native writes the run Mach, ASB writes 0):",
        f"{'header':<18}{'run Mach':>10}{'CL':>10}{'Cmu':>12}{'CZu':>12}{'CXu':>12}",
    ]
    for tag in ("header_0", "header_run_mach"):
        r = h1[tag]
        L.append(f"{tag:<18}{r['Mach_run']:>10.4f}{r['CL']:>10.5f}"
                 f"{r['Cmu']:>12.6f}{r['CZu']:>12.6f}{r['CXu']:>12.6f}")
    L.append(f"  -> header Mach changes Cmu by {h1['delta_Cmu_pct']:.3f} %, "
             f"CZu by {h1['delta_CZu_pct']:.3f} %, CL by {h1['delta_CL_pct']:.3f} %")
    verdict_h1 = ("CONFIRMED: the header Mach IS the cause"
                  if h1["delta_Cmu_pct"] > 1.0 else
                  "REJECTED: the header Mach is not the cause")
    L.append(f"  VERDICT: {verdict_h1}")

    L += ["", "H2 — Mach sensitivity of the u-derivatives at fixed geometry:",
          f"{'run Mach':>10}{'CL':>10}{'Cmu':>12}{'CZu':>12}{'CXu':>12}{'CLa':>10}"]
    for k, r in h2.items():
        L.append(f"{r['Mach_run']:>10.4f}{r['CL']:>10.5f}{r['Cmu']:>12.6f}"
                 f"{r['CZu']:>12.6f}{r['CXu']:>12.6f}{r['CLa']:>10.5f}")

    h3 = report["H3_cref"]
    L += ["", f"H3 — Cref perturbed by {h3['cref_change_pct']:.3f} % "
          "(the measured native-vs-ASB gap):",
          f"  Cmu moves {h3['Cmu_change_pct']:.3f} %, "
          f"CZu {h3['CZu_change_pct']:.3f} %, Cma {h3['Cma_change_pct']:.3f} %"]

    L += ["", "H4 — conditioning: fractional response per fractional CL change",
          "     (>1 = amplifies the CL difference; >>1 = ill-conditioned)"]
    for key, val in h4["amplification_vs_CL"].items():
        if val is not None:
            L.append(f"  {key:<6} amplification = {val:8.2f}x")
    L.append(f"  (probe: alpha +/-0.1 deg moved CL by "
             f"{100 * h4['dCL_fractional']:.3f} %)")

    text = "\n".join(L)
    print(text)
    (OUT / "diagnosis.txt").write_text(text + "\n", encoding="utf-8")
    print(f"\nwrote {OUT / 'diagnosis.json'}")


if __name__ == "__main__":
    main()
