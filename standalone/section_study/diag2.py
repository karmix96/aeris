import common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_ind":0.00355085,"cd_total":0.0103324,
       "x_np":0.306318,"elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,
       "hinge_moments.elevon_sym":0.0002872}
KEY=tuple(SCALE)
def val(res,k,p,a,q):
    r=res.get((k,p,89,a,4.0,4.0)); return r.get(q) if r and r.get("ok") else None
keys=[k for k,_ in C.convergence_subset(8)]
cases=[dict(sample_key=k,n_sections=89,policy=p,alpha_deg=a) for k in keys for p in ("uniform","adaptive") for a in (-2.0,0.0,4.0)]
res=C.collect(cases)
print("magnitudes at a=0 (uniform):  cl, hinge_sym, cd_ind")
for k in keys:
    print(f"  {k}: cl={val(res,k,'uniform',0.0,'cl')}, hinge={val(res,k,'uniform',0.0,'hinge_moments.elevon_sym')}, cd_ind={val(res,k,'uniform',0.0,'cd_ind')}")
print("\nuniform-vs-adaptive spread, SCALE-FLOORED denom max(|v|,0.1*scale):")
for k in keys:
    worst=0; where=None
    for a in (-2.0,0.0,4.0):
        for q in KEY:
            u=val(res,k,'uniform',a,q); ad=val(res,k,'adaptive',a,q)
            if u is None or ad is None: continue
            denom=max(abs(u),abs(ad),0.1*SCALE[q])
            sp=abs(u-ad)/denom*100
            if sp>worst: worst,where=sp,(a,q)
    print(f"  {k}: worst={worst:.3f}% @{where}")
