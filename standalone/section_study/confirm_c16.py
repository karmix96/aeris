"""Robustness confirmation: does the PINS effect (the main result) hold at the
PRODUCTION mesh c16s2u, not just the cheap c8s1u reference mesh? Within-family
(uniform nopin vs uniform pinned) vs the densest-affordable c16s2u ref (N=89)."""
import json, statistics, common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_total":0.0103324,"x_np":0.306318,
       "elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,"elevon_diff.Cl":0.002594}
NCH,SPW=16,2; ANG=(-2.0,0.0,4.0)
designs=C.extreme_samples()+C.convergence_subset(2)
keys=[k for k,_ in designs]
cases=[]
for k in keys:
    for a in ANG:
        cases.append(dict(sample_key=k,n_sections=89,policy="uniform",alpha_deg=a,nchord=NCH,spanw=SPW,tag="c16conf"))
        for pol in ("uniform_nopin","uniform","adaptive"):
            cases.append(dict(sample_key=k,n_sections=25,policy=pol,alpha_deg=a,nchord=NCH,spanw=SPW,tag="c16conf"))
print(f"confirm @c16s2u: {len(keys)} designs, {len(cases)} cases",flush=True)
C.parallel_by_design(cases,workers=4,tag="c16conf")
def g(k,pol,N,a,q):
    r=C._collect_one(k,pol,N,a,NCH,SPW); return r.get(q) if r and r.get("ok") else None
def worst(k,pol):
    w=0
    for q in SCALE:
        for a in ANG:
            v=g(k,pol,25,a,q); ref=g(k,"uniform",89,a,q)
            if v is None or ref is None: continue
            w=max(w,abs(v-ref)/SCALE[q]*100)
    return round(w,3)
L=[];A=L.append
A("CONFIRMATION @ PRODUCTION MESH c16s2u (ref=uniform-89, normalized worst-key %)")
A("="*70)
A(f"{'design':>16s} {'noPIN':>8s} {'pinned':>8s} {'adaptive':>9s}")
res={}
for k in keys:
    wn,wu,wa=worst(k,"uniform_nopin"),worst(k,"uniform"),worst(k,"adaptive")
    res[k]={"nopin":wn,"pinned":wu,"adaptive":wa}
    A(f"{k.split(':')[-1]:>16s} {wn:8.2f} {wu:8.2f} {wa:9.2f}")
A("")
A(f"WORST: noPIN={max(r['nopin'] for r in res.values()):.2f}  "
  f"pinned={max(r['pinned'] for r in res.values()):.2f}  "
  f"adaptive={max(r['adaptive'] for r in res.values()):.2f}")
A(f"pinned<noPIN on {sum(1 for r in res.values() if r['pinned']<r['nopin'])}/{len(keys)}; "
  f"pinned<=adaptive on {sum(1 for r in res.values() if r['pinned']<=r['adaptive'])}/{len(keys)}")
(C.CONFIG_ROOT/"confirm_c16.json").write_text(json.dumps(res,indent=2))
(C.CONFIG_ROOT/"confirm_c16.txt").write_text("\n".join(L)+"\n")
print("\n".join(L))
