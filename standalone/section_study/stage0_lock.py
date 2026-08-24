"""Stage 0 — lock the inputs (RUNBOOK §8 Stage 0).

Freezes the mesh (c16s2u), the reference count N_ref, the placement policies, the
angle/control sets, the gates, the design set and — critically — the mandatory
node (hard-point) list per design. Proves the provenance hash distinguishes two
placements at the same N (§9), so cache cannot collide. No heavy solves.
"""
from __future__ import annotations

import json
import subprocess

import common as pc
import common_sections as C

N_REF = 89          # realized ~92 -> 5824 vortices <= 6000 cap at c16s2u (smoke-verified)
RICH_LEVELS = (25, 49, 89)   # ratio-~2 in 1/N for the reference Richardson band
ANGLES = (-2.0, 0.0, 4.0)
POLICIES = ("uniform", "adaptive", "clustered")

GATES = {
    "G1a_neutrality_pct": 0.5, "G1b_richardson_pct": 0.5,
    "G3_accuracy_pct": 1.0, "G4_trim_deg": 0.5, "G4_bias_pct": 5.0,
    "G5_spearman": 0.98, "G5_disp": 4, "G5_regret_pct": 0.5,
    "G6_predictivity_rho": 0.7, "G8_gap_ratio": 2.0,
}
KEY_Q = ("cl", "cm", "cd_ind", "cd_total", "x_np",
         "elevon_sym.CL", "elevon_sym.Cm", "hinge_moments.elevon_sym")


def git_sha():
    try:
        return subprocess.check_output(["git", "-C", str(pc.REPO), "rev-parse", "HEAD"],
                                       text=True).strip()
    except Exception:
        return None


def main():
    normals = C.normal_samples()
    extremes = C.extreme_samples()
    designs = normals + extremes

    # mandatory nodes per design + legality at N_ref
    per_design = {}
    illegal = []
    for key, s in designs:
        ctx = C.build_context(s, key)
        fr = C.fractions_for(ctx, N_REF, "uniform")
        strips = pc.strips_for(len(fr), C.SPANW); vort = strips * C.NCHORD
        legal = strips <= C.MAX_STRIPS and vort <= C.MAX_VORTICES
        if not legal:
            illegal.append((key, len(fr), vort))
        per_design[key] = {
            "band": ctx["band"], "pins": ctx["pins"],
            "n_realized_at_Nref": len(fr), "strips": strips, "vortices": vort,
            "legal": legal,
        }

    # §9 hash-distinctness proof on design 0, at two counts
    k0, s0 = normals[0]
    ctx0 = C.build_context(s0, k0)
    proofs = {}
    for N in (25, N_REF):
        hu, _ = C.hash_for(ctx0, k0, n_sections=N, policy="uniform", alpha_deg=4.0)
        ha, _ = C.hash_for(ctx0, k0, n_sections=N, policy="adaptive", alpha_deg=4.0)
        hc, _ = C.hash_for(ctx0, k0, n_sections=N, policy="clustered", alpha_deg=4.0)
        distinct = len({hu, ha, hc}) == 3
        proofs[N] = {"uniform": hu, "adaptive": ha, "clustered": hc, "distinct": distinct}
        if not distinct:
            raise SystemExit(f"§9 STOP: placements collide in hash at N={N}: {proofs[N]}")

    locked = {
        "study": "section_positioning_v1", "git_sha": git_sha(),
        "mesh": {"nchordwise": C.NCHORD, "spanwise": C.SPANW, "cspace": C.CSPACE,
                 "label": "c16s2u", "source": "panelling study selection"},
        "N_ref": N_REF, "richardson_levels": RICH_LEVELS,
        "angles": ANGLES, "policies": POLICIES,
        "control_states": {"validation": [4.0, 4.0], "transfer": [[0.0, 0.0]],
                           "production_sweep_sym": [-5.0, 0.0, 5.0]},
        "key_quantities_gate3": KEY_Q, "gates": GATES,
        "geom_config_sha256": pc._sha256_file(pc.GEOM_CONFIG),
        "n_normal": len(normals), "n_extreme": len(extremes),
        "extreme_names": [k for k, _ in extremes],
        "hash_distinctness_proof": proofs,
        "per_design": per_design,
        "caps": {"max_strips": C.MAX_STRIPS, "max_vortices": C.MAX_VORTICES},
    }
    (C.CONFIG_ROOT / "stage0_locked_config.json").write_text(json.dumps(locked, indent=2))

    # summary
    L = []; A = L.append
    A("STAGE 0 — LOCK THE INPUTS (section positioning)")
    A("=" * 60)
    A(f"1. MESH FROZEN: c16s2u (chord {C.NCHORD}, span x{C.SPANW}, cspace {C.CSPACE}=uniform)")
    A(f"2. REFERENCE COUNT N_ref={N_REF} (realized ~{per_design[k0]['n_realized_at_Nref']}, "
      f"{per_design[k0]['vortices']} vortices <= {C.MAX_VORTICES})")
    A(f"   Richardson levels (1/N chain): {RICH_LEVELS}")
    A(f"3. DESIGN SET: {len(normals)} normal + {len(extremes)} extreme")
    A(f"4. MANDATORY NODES per design: span ends + planform breaks + elevon edges")
    A(f"   design 0 pins: {per_design[k0]['pins']}")
    A(f"5. §9 HASH DISTINCTNESS (design 0): "
      f"N=25 distinct={proofs[25]['distinct']}, N={N_REF} distinct={proofs[N_REF]['distinct']}")
    A(f"   uniform={proofs[25]['uniform'][:10]} adaptive={proofs[25]['adaptive'][:10]} "
      f"clustered={proofs[25]['clustered'][:10]}")
    if illegal:
        A(f"6. !! ILLEGAL at N_ref (STOP): {illegal}")
    else:
        A(f"6. LEGALITY: all {len(designs)} designs legal at N_ref={N_REF} "
          f"(max vort {max(d['vortices'] for d in per_design.values())})")
    A(f"7. GATES frozen: {GATES}")
    A(f"8. git_sha={locked['git_sha']}")
    (C.CONFIG_ROOT / "stage0_summary.txt").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    if illegal:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
