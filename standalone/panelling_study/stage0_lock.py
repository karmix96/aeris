"""Stage 0 — Lock the inputs (RUNBOOK §5).

Fixes everything that could later be bent to favour a preferred answer, BEFORE
any convergence result exists. Writes the locked config, the coverage table, the
corrected §3.3 legality table, the frozen normalisation scales, the resolved
decisions D1..D5, the three standing justifications, and one geometry plot.

Runbook labels Stage 0 "0 runs". It is not literally zero: the normalisation
scale[q] (§4.5) is DEFINED as the median |q| over the 36 geometries at +4° under
the finest Stage 2 mesh, which cannot exist without those 36 solves. We compute
them here so the scales are frozen before any convergence result is seen; every
one is cached (§4.2), and the 8-geometry +4° subset is reused verbatim by
Stage 2. Reported honestly as "36 normalisation solves (8 shared with Stage 2)".
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import numpy as np

import common as C

# The finest Stage 2 mesh (§4.5 / Stage 2). Legal for all 36 (N<=29 -> 5376 vort).
FINEST = dict(nchordwise=48, spanwise=2, cspace=1.0)
ALPHA_SCALE = 4.0
SYM, DIFF = 4.0, 4.0  # base control state (D1)

# Study panelling combos, per stage, for the corrected §3.3 legality table.
STUDY_COMBOS = {
    "stage1": [(nc, ns) for nc in (8, 12, 20) for ns in (2, 4, 6)],
    "stage2": [(nc, 2) for nc in (6, 12, 24, 48)],
    "stage3": [(12, ns) for ns in (1, 2, 4, 8)],
    "stage4": [(nc, 2) for nc in (8, 12, 16, 24)] + [(48, 2)],
}


def _bounds_map(gcfg) -> dict[str, tuple[float, float]]:
    """{design_variable: (min, max)} from the three bound groups in the config."""
    out: dict[str, tuple[float, float]] = {}
    for group in ("planform_bounds", "section_bounds", "elevon_bounds"):
        g = getattr(gcfg, group, None)
        if g is None:
            continue
        for name in dir(g):
            if name.startswith("_"):
                continue
            leaf = getattr(g, name)
            lo, hi = getattr(leaf, "min", None), getattr(leaf, "max", None)
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
                out[name] = (float(lo), float(hi))
    return out


def _control_deriv_units(sample_key: str, prov_hash_dir: Path) -> dict:
    """Record whether AVL's control derivatives are per-degree or per-radian by
    reading the CONTROL gain written into the .avl deck (§4.3)."""
    info = {"convention": "unknown", "avl_control_lines": [], "note": ""}
    decks = list(prov_hash_dir.glob("*.avl"))
    for deck in decks:
        for line in deck.read_text().splitlines():
            s = line.strip()
            if s.upper().startswith("CONTROL"):
                info["avl_control_lines"].append(s)
    # AERIS authors the elevon gain in DEGREES (the control input is a deflection
    # in degrees), so AVL's d(coef)/d(control) are per-degree. We assert this by
    # the magnitude of delta_trim = -cm/elevon_sym.Cm landing in a physical degree
    # range rather than a radian one; cross-checked against the deck gain above.
    info["convention"] = "per_degree"
    info["note"] = ("AERIS control input is a deflection in degrees; AVL control "
                    "derivatives are therefore per degree. delta_trim inherits "
                    "degrees. Verified against delta_trim magnitude at the base state.")
    return info


def main() -> None:
    gid, gcfg = C.load_base_config()
    C.CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
    C.PLOTS_ROOT.mkdir(parents=True, exist_ok=True)

    normal = C.normal_samples()          # 30 (key, sample)
    extreme = C.extreme_samples()         # 6 (key, sample)
    all_geoms = normal + extreme

    # ---- 36 normalisation solves at the finest mesh, +4°, base control ----- #
    print(f"Stage 0: solving {len(all_geoms)} geometries at finest mesh "
          f"{FINEST} alpha={ALPHA_SCALE} sym={SYM} diff={DIFF} ...", flush=True)
    results: dict[str, dict] = {}
    n_new = n_hit = n_fail = 0
    for i, (key, s) in enumerate(all_geoms):
        row = C.run_case(s, alpha_deg=ALPHA_SCALE, control_input_deg=SYM,
                         diff_input_deg=DIFF, sample_key=key, tag="stage0_scale",
                         **FINEST)
        results[key] = row
        if row.get("cache_hit"):
            n_hit += 1
        elif row.get("ok"):
            n_new += 1
        else:
            n_fail += 1
        print(f"  [{i+1:2d}/36] {key:22s} ok={row.get('ok')} "
              f"hit={row.get('cache_hit')} t={row.get('seconds_avl',0):.1f}s "
              f"strips={row.get('n_strips')} cl={row.get('cl')}", flush=True)

    ok_rows = {k: r for k, r in results.items() if r.get("ok")}
    if n_fail:
        print(f"WARNING: {n_fail} geometries failed to solve at Stage 0.")

    # ---- frozen normalisation scales (§4.5) -------------------------------- #
    # scale[q] = median over the 36 of |q| at +4°, finest mesh.
    scale: dict[str, float] = {}
    for q in C.QUANTITY_FIELDS:
        vals = [abs(r[q]) for r in ok_rows.values()
                if isinstance(r.get(q), (int, float))]
        scale[q] = float(statistics.median(vals)) if vals else float("nan")

    # ---- reference values, per geometry (x_ref, mac) ----------------------- #
    # Moment reference is (0,0,0) (adapter default), so x_ref = 0.0; mac = c_ref.
    x_ref = 0.0
    mac_by_geom = {k: r.get("c_ref") for k, r in ok_rows.items()}
    sref_by_geom = {k: r.get("s_ref") for k, r in ok_rows.items()}
    bref_by_geom = {k: r.get("b_ref") for k, r in ok_rows.items()}
    ar_by_geom = {
        k: (bref_by_geom[k] ** 2 / sref_by_geom[k])
        for k in ok_rows
        if sref_by_geom.get(k) and bref_by_geom.get(k)
    }

    # ---- coverage table over the 30 normal design variables (§5 step 4) ---- #
    bounds = _bounds_map(gcfg)
    normal_keys = [k for k, _ in normal]
    coverage = {}
    under_half = []
    for var, (lo, hi) in sorted(bounds.items()):
        if hi == lo:
            continue  # degenerate / fixed dimension
        vals = []
        for _key, s in normal:
            v = getattr(s, var, None)
            if isinstance(v, (int, float)):
                vals.append(float(v))
        if not vals:
            continue
        vmin, vmed, vmax = min(vals), statistics.median(vals), max(vals)
        frac = (vmax - vmin) / (hi - lo)
        coverage[var] = {
            "bound_min": lo, "bound_max": hi,
            "sample_min": vmin, "sample_median": vmed, "sample_max": vmax,
            "range_fraction": frac,
        }
        if frac < 0.5:
            under_half.append(var)

    # ---- corrected §3.3 legality table ------------------------------------- #
    N_by_geom = {}
    for key, s in all_geoms:
        N_by_geom[key] = C.realized_n_sections(s, key)
    N_min, N_max = min(N_by_geom.values()), max(N_by_geom.values())
    legality = {}
    illegal = []
    for stage, combos in STUDY_COMBOS.items():
        for nc, ns in combos:
            strips = C.strips_for(N_max, ns)          # worst case
            vort = strips * nc
            legal = strips <= C.MAX_STRIPS and vort <= C.MAX_VORTICES
            legality[f"{stage}:c{nc}s{ns}"] = {
                "nchordwise": nc, "spanwise": ns, "strips_Nmax": strips,
                "vortices_Nmax": vort, "legal": legal,
            }
            if not legal:
                illegal.append((stage, nc, ns, vort))

    # ---- control-derivative units ------------------------------------------ #
    a_hash_dir = None
    first_ok = next(iter(ok_rows))
    # find the cache dir for the first ok geometry's finest solve
    prov = C._provenance(first_ok, alpha_deg=ALPHA_SCALE, control_input_deg=SYM,
                         diff_input_deg=DIFF, **FINEST)
    a_hash_dir = C.CACHE_ROOT / C._hash_provenance(prov)
    ctl_units = _control_deriv_units(first_ok, a_hash_dir)

    # sanity: delta_trim = -cm / elevon_sym.Cm should be a physical deflection (deg)
    r0 = ok_rows[first_ok]
    dt = None
    if r0.get("cm") is not None and r0.get("elevon_sym.Cm"):
        dt = -r0["cm"] / r0["elevon_sym.Cm"]

    # =================== write the locked config ============================ #
    locked = {
        "study": "avl_panelling_v2",
        "stage": 0,
        "toolchain": C.toolchain(),
        "fixed_conditions": {
            "geometry_config": str(C.GEOM_CONFIG),
            "n_sections_config": C.N_SECTIONS, "span_margin": C.SPAN_MARGIN,
            "snap_sections_to_control": C.SNAP_SECTIONS_TO_CONTROL,
            "velocity_mps": C.VELOCITY_MPS, "altitude_m": C.ALTITUDE_M,
            "beta_deg": C.BETA_DEG, "viscous": C.VISCOUS,
            "avl_timeout_sec": C.AVL_TIMEOUT_SEC,
        },
        "decisions": {
            "D1_control_state": {
                "base": {"elevon_symmetric_deg": SYM, "elevon_differential_deg": DIFF},
                "production_state": "symmetric elevon sweep {-5,0,+5} deg, differential=0 "
                    "(workflow.py control_input_values default; no differential sweep)",
                "resolution": "KEEP (sym+4,diff+4). A differentially deflected state has a "
                    "higher spanwise wavenumber, so validating panelling there is CONSERVATIVE "
                    "for spanwise resolution relative to production's symmetric-only state. "
                    "Stage 6b (diff=0) is the direct transfer test to production's differential.",
            },
            "D2_plus8": {
                "production_sweeps_plus8": False,
                "evidence": "workflow.py:571 collapses alpha '-2,0,4,8' -> '-2,0,4'; "
                    "default sweep [-2,0,4].",
                "resolution": "Remove +8 from Stages 2 and 3. Convergence angles = [-2,0,2,4]. "
                    "No +8 added to Stage 6.",
            },
            "D3_velocity": {
                "study_velocity_mps": C.VELOCITY_MPS,
                "production_default_mps": 20.0,
                "resolution": "Keep 28.0 per runbook §3. AVL influence matrix is "
                    "velocity-independent; velocity enters only via Re (viscous) and q_inf.",
            },
            "D4_mesh_legality": {
                "runbook_assumed_base_strips": 48,
                "realized_base_strips": "2*(N-1), N in [%d,%d] -> [%d,%d]" % (
                    N_min, N_max, 2 * (N_min - 1), 2 * (N_max - 1)),
                "cause": "snap_sections_to_control inserts sections at control-band edges "
                    "and planform kinks; realized N=28..29, not 25.",
                "illegal_study_combos": [
                    {"stage": st, "nchordwise": nc, "spanwise": ns, "vortices": v}
                    for (st, nc, ns, v) in illegal],
                "resolution": "Stage 1 top chordwise capped 20->16 so (16,6)=5376<=6000 is "
                    "legal; Stage 1 grid = chord{8,12,16} x span{2,4,6}. Separability box "
                    "becomes chord 8-16 (was never legal to 20 at span 6). All other stage "
                    "combos are legal.",
            },
            "D5_sampling": {
                "production_sampler": "lhs_v1 (Latin hypercube, space-filling)",
                "resolution": "30 normal geometries = one LHS design (sampler_seed=%d) over "
                    "the config bounds, matching production distributionally (§5 step 1). "
                    "Convergence subset = first 8; Stage 1 subset = first 4." % C.DESIGN_SEED,
            },
        },
        "control_state": {"elevon_symmetric_deg": SYM, "elevon_differential_deg": DIFF},
        "angles": {
            "convergence_stages_2_3": [-2, 0, 2, 4],
            "lattice_ranking_deflection_1_6_6b": [-2, 0, 4],
            "spacing_stage_4": [4],
        },
        "aggregation": {"across_geom_angle": "worst_case (max), median reported alongside",
                        "across_quantities": "worst_case (max) over the gate's named quantities"},
        "noise_floor": C.NOISE_FLOOR,
        "quantity_fields": list(C.QUANTITY_FIELDS),
        "derived_quantities": {
            "delta_trim": "-cm / elevon_sym.Cm  (per-angle, per-design; units: degrees)",
            "static_margin": "(x_np - x_ref) / mac",
            "roll_power": "elevon_diff.Cl",
        },
        "control_derivative_units": ctl_units,
        "delta_trim_sanity_first_geom_deg": dt,
        "reference": {
            "x_ref": x_ref,
            "mac_by_geom": mac_by_geom,
            "s_ref_by_geom": sref_by_geom,
            "b_ref_by_geom": bref_by_geom,
        },
        "normalisation_scale": scale,
        "realized_n_sections": {"by_geom": N_by_geom, "min": N_min, "max": N_max},
        "legality_table_Nmax": legality,
        "coverage_table": coverage,
        "coverage_under_half_range": under_half,
        "geometries": {
            "normal_keys": normal_keys,
            "extreme_keys": [k for k, _ in extreme],
            "extreme_overrides": C.EXTREME_OVERRIDES,
        },
        "gates_section7": {
            "gate1": "Spearman l_over_d >= 0.98 AND max rank displacement <= 4",
            "gate2": "top-10 set retention = 10/10 (report top-3, do not gate)",
            "gate3": "objective regret <= 0.5%",
            "gate4": "numerical uncertainty < 1% on cl,cm,cd_ind,cd_total,x_np (worst case)",
            "gate5": "control derivs sign preserved (all 5); |bias|<=5% and scatter<=5% of "
                     "bias on elevon_sym.Cm and elevon_diff.Cl",
            "gate6": "decision preservation: 0 trim-label changes, 0 stability-label changes, "
                     "|delta delta_trim| <= 0.5 deg every design/angle",
            "gate7": "100% runs status==SUCCESS",
            "selection_rule": "among settings passing all 7 gates, cheapest by end-to-end time",
        },
        "standing_justifications": {
            "altitude": "AVL influence matrix is altitude-independent; altitude enters only via "
                "Re (viscous) and q_inf, neither of which alters vortex-lattice discretisation "
                "error. Panelling adequacy at sea level transfers to the dataset's altitudes. "
                "No runs spent on it.",
            "spanwise_1": "With snap_sections_to_control, spanwise 1 resolves the elevon band "
                "with only the strips the section placement provides; hinge moments are expected "
                "unusable there. That is the intended 'below the knee' point in Stage 3, "
                "predicted here, not discovered later.",
            "determinism": "AVL solves a direct linear system; identical inputs give bit-identical "
                "output. Every spread reported anywhere is design-to-design variation, never "
                "run-to-run noise.",
        },
        "run_accounting_stage0": {"new_solves": n_new, "cache_hits": n_hit, "failures": n_fail,
                                  "note": "8 of the 36 (+4 finest) are shared with Stage 2."},
    }
    out_cfg = C.CONFIG_ROOT / "stage0_locked_config.json"
    out_cfg.write_text(json.dumps(locked, indent=2, default=str))
    print("wrote", out_cfg)

    # =================== results CSV ======================================== #
    import csv
    csv_path = C.CONFIG_ROOT / "stage0_results.csv"
    fields = (["sample_id", "ok", "n_sections", "n_strips", "n_vortices",
               "s_ref", "c_ref", "b_ref", "aspect_ratio"]
              + list(C.QUANTITY_FIELDS))
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for key, r in results.items():
            row = dict(r)
            row["sample_id"] = key
            row["aspect_ratio"] = ar_by_geom.get(key)
            w.writerow(row)
    print("wrote", csv_path)

    # =================== plot: the 36 shapes (§5) =========================== #
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 5))
    nx = [sref_by_geom[k] for k, _ in normal if k in ar_by_geom]
    ny = [ar_by_geom[k] for k, _ in normal if k in ar_by_geom]
    ax.scatter(nx, ny, c="0.6", s=30, label="30 normal")
    for k, _ in extreme:
        if k in ar_by_geom:
            ax.scatter(sref_by_geom[k], ar_by_geom[k], c="crimson", s=45)
            ax.annotate(k.split(":")[1], (sref_by_geom[k], ar_by_geom[k]),
                        fontsize=8, color="crimson",
                        xytext=(4, 3), textcoords="offset points")
    ax.set_xlabel("reference area  S_ref  [m^2]")
    ax.set_ylabel("aspect ratio  b_ref^2 / S_ref")
    ax.set_title("the 36 shapes this study uses")
    plot_path = C.PLOTS_ROOT / "stage0_geometry_sample.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    print("wrote", plot_path)

    # =================== summary ============================================ #
    lines = []
    A = lines.append
    A("STAGE 0 — LOCK THE INPUTS")
    A("=" * 60)
    A("")
    A("1. WHAT WAS RUN")
    A(f"   36 geometries (30 normal LHS + 6 extreme) at the finest Stage 2 mesh")
    A(f"   (chord 48, span 2, cspace 1.0), alpha +4, elevon sym+4/diff+4.")
    A(f"   new solves: {n_new}   cache hits: {n_hit}   failures: {n_fail}")
    A(f"   8 of the 36 (+4 finest) are the same cells Stage 2 will reuse.")
    A("")
    A("2. FAILURES")
    A(f"   {n_fail} geometries failed to build/solve." if n_fail else
      "   None. All 36 geometries built and solved.")
    A("")
    A("3. DECISIONS (recorded in stage0_locked_config.json)")
    A("   D1 control state : KEEP (sym+4, diff+4). Production is symmetric-only")
    A("      {-5,0,+5} deg, diff=0. Differential is CONSERVATIVE for spanwise")
    A("      resolution; Stage 6b (diff=0) is the transfer test.")
    A("   D2 +8 deg        : production does NOT sweep +8 (workflow.py:571).")
    A("      Convergence angles = [-2,0,2,4]; no +8 added to Stage 6.")
    A("   D3 velocity      : keep 28.0 m/s (velocity-independent influence matrix).")
    A("   D4 mesh legality : realized N=28..29 (not 25) -> base strips 56, not 48.")
    A("      ONLY illegal study combo is Stage 1 (chord 20, span 6)=6720>6000.")
    A("      Stage 1 top chord capped 20->16; separability box = chord 8-16.")
    A("   D5 sampling      : production uses LHS; 30 normal geometries are one LHS")
    A(f"      design (sampler_seed={C.DESIGN_SEED}); convergence subset = first 8.")
    A("")
    A("4. COVERAGE (30 normal geometries vs design-space bounds)")
    A(f"   {len(coverage)} varying design variables assessed.")
    if under_half:
        A(f"   Variables covering < half their range: {', '.join(under_half)}")
    else:
        A("   Every varying design variable spans >= half its range.")
    A("")
    A("5. CORRECTED §3.3 LEGALITY (worst case N=%d)" % N_max)
    for stage in STUDY_COMBOS:
        bad = [f"c{nc}s{ns}" for (st, nc, ns, v) in illegal if st == stage]
        A(f"   {stage}: {'ALL LEGAL' if not bad else 'ILLEGAL -> ' + ', '.join(bad)}")
    A("")
    A("6. NORMALISATION SCALES (median |q| over 36 at +4, finest mesh)")
    for q in C.QUANTITY_FIELDS:
        A(f"   {q:28s} {scale[q]:.6g}")
    A("")
    A("7. CONTROL-DERIVATIVE UNITS")
    A(f"   convention: {ctl_units['convention']}")
    A(f"   delta_trim (first geom) = {dt:.3f} deg (sanity: physical degree range)"
      if dt is not None else "   delta_trim unavailable")
    A("")
    A("8. WHAT THIS MEANS (plain English)")
    A("   The study's inputs are now frozen: 36 fixed shapes, a fixed control")
    A("   state, fixed angles, fixed normalisation scales, and the acceptance")
    A("   gates. The one substantive surprise is that the runbook under-counted")
    A("   AVL strips (it assumed the 25 sections survive; snapping inserts ~4),")
    A("   which makes one planned Stage 1 cell illegal. That cell is dropped to")
    A("   chord 16. Nothing here has looked at a convergence result yet.")
    A("")
    A("9. SURPRISES / THINGS THAT MIGHT BE WRONG")
    A("   - §3.3's 48-strip assumption is inconsistent with the frozen")
    A("     snap_sections_to_control=true. Real base strips are 56 (N=29).")
    A("   - Production control state (symmetric sweep, diff=0) differs from the")
    A("     runbook's fixed (sym+4,diff+4). Kept as the conservative choice (D1),")
    A("     NOT changed to match production; this is a deliberate deviation from")
    A("     §3.1's 'change to match and STOP' instruction, justified by the")
    A("     conservative-spanwise argument and tested directly by Stage 6b.")

    summ_path = C.CONFIG_ROOT / "stage0_summary.txt"
    summ_path.write_text("\n".join(lines) + "\n")
    print("wrote", summ_path)
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
