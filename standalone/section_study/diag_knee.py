import statistics, common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_total":0.0103324,"x_np":0.306318,
       "elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,"elevon_diff.Cl":0.002594}
NCH,SPW=8,1; ANG=(-2.0,0.0,4.0)
keys=[k for k,_ in C.convergence_subset(8)+C.extreme_samples()]
def g(k,N,a,q):
    r=C._collect_one(k,"uniform",N,a,NCH,SPW); return r.get(q) if r and r.get("ok") else None
for N in (25,49,101,151):
    errs=[]; worst=0; wc=None
    for k in keys:
        for q in SCALE:
            for a in ANG:
                v=g(k,N,a,q); ref=g(k,201,a,q)
                if v is None or ref is None: continue
                e=abs(v-ref)/SCALE[q]*100; errs.append(e)
                if e>worst: worst,wc=e,(k.split(':')[-1],q,a)
    errs.sort()
    print(f"N={N:3d}: median={statistics.median(errs):.3f}% p90={errs[int(0.9*len(errs))]:.3f}% "
          f"worst={worst:.3f}% @{wc}")
