"""Diagnose the G1 failure: is cd_ind intrinsically section-sensitive, or is the
adversarial 'clustered' (t^2, root-heavy) placement starving the tip?"""
import common_sections as C

def val(res, k, pol, N, a, q):
    r = res.get((k, pol, N, a, 4.0, 4.0))
    return r.get(q) if r and r.get("ok") else None

def main():
    keys = [k for k, _ in C.convergence_subset(8)]
    POL = ("uniform", "adaptive", "clustered")
    cases = [dict(sample_key=k, n_sections=89, policy=p, alpha_deg=a)
             for k in keys for p in POL for a in (-2.0, 0.0, 4.0)]
    res = C.collect(cases)

    print("cd_ind across placements at N_ref=89 (design 0):")
    for a in (-2.0, 0.0, 4.0):
        vs = {p: val(res, keys[0], p, 89, a, "cd_ind") for p in POL}
        print(f"  a{a:+.0f}: uniform={vs['uniform']}  adaptive={vs['adaptive']}  clustered={vs['clustered']}")

    print("\nuniform-vs-adaptive ONLY spread (drop adversarial clustered), worst over key-q:")
    KEY = ("cl", "cm", "cd_ind", "cd_total", "x_np",
           "elevon_sym.CL", "elevon_sym.Cm", "hinge_moments.elevon_sym")
    for k in keys:
        worst = 0.0; where = None
        worst_nocd = 0.0; where_nocd = None
        for a in (-2.0, 0.0, 4.0):
            for q in KEY:
                u = val(res, k, "uniform", 89, a, q)
                ad = val(res, k, "adaptive", 89, a, q)
                if u is None or ad is None: continue
                mag = max(abs(u), abs(ad))
                if mag < C.NOISE_FLOOR: continue
                sp = abs(u - ad) / mag * 100
                if sp > worst: worst, where = sp, (a, q)
                if q != "cd_ind" and sp > worst_nocd: worst_nocd, where_nocd = sp, (a, q)
        print(f"  {k}: u-vs-a worst={worst:.3f}% @{where} | excl cd_ind={worst_nocd:.3f}% @{where_nocd}")

if __name__ == "__main__":
    main()
