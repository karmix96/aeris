"""Smoke test: context build, placement policies, hash distinctness, one solve."""
import common_sections as C

def main():
    key, sample = C.normal_samples()[0]
    ctx = C.build_context(sample, key)
    print("design:", key)
    print("band:", ctx["band"])
    print("pins:", ctx["pins"])
    for pol in ("uniform", "adaptive", "clustered"):
        fr = C.fractions_for(ctx, 25, pol)
        pins_ok = all(any(abs(f - p) < 1e-6 for f in fr) for p in ctx["pins"])
        print(f"  {pol:10s} N_real={len(fr):2d} pins_present={pins_ok} "
              f"first5={[round(x,3) for x in fr[:5]]}")

    # hash must distinguish placements at the SAME N
    hu, _ = C.hash_for(ctx, key, n_sections=25, policy="uniform", alpha_deg=4.0)
    ha, _ = C.hash_for(ctx, key, n_sections=25, policy="adaptive", alpha_deg=4.0)
    print(f"hash uniform={hu} adaptive={ha}  distinct={hu != ha}")
    if hu == ha:
        raise SystemExit("STOP: placements hash identically — cache would collide.")

    # legality ceiling at c16s2u
    import common as pc
    for N in (25, 49, 89, 93, 97):
        fr = C.fractions_for(ctx, N, "uniform")
        strips = pc.strips_for(len(fr), C.SPANW); vort = strips * C.NCHORD
        legal = strips <= C.MAX_STRIPS and vort <= C.MAX_VORTICES
        print(f"  N_req={N:3d} N_real={len(fr):3d} strips={strips} vort={vort} legal={legal}")

    # one real solve at uniform 25, alpha +4, sym+4/diff+4
    print("solving uniform N=25 ...", flush=True)
    r = C.run_section_case(sample, sample_key=key, n_sections=25, policy="uniform",
                           alpha_deg=4.0, tag="smoke")
    print("ok:", r["ok"], "status:", r["status"], "cl:", r.get("cl"),
          "cm:", r.get("cm"), "CL_de:", r.get("elevon_sym.CL"),
          "n_strips:", r.get("n_strips"), "n_sec:", r.get("n_sections"),
          "ramp:", round(r.get("ramp_fraction") or 0, 3),
          "sec_avl:", round(r.get("seconds_avl") or 0, 1))

if __name__ == "__main__":
    main()
