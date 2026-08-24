"""Stage 1d — hard-point ablation: is the benefit in the PINS or the density?
Compare uniform_nopin-25 (no mandatory nodes) vs uniform-25 (pinned) vs
adaptive-25, all vs the converged uniform-201 reference, on the extremes."""
import json
import common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_ind":0.00355085,"cd_total":0.0103324,
       "x_np":0.306318,"elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,
       "elevon_diff.Cl":0.002594,"hinge_moments.elevon_sym":0.0002872}
KEY=tuple(SCALE); NCH,SPW=8,1; ANG=(-2.0,0.0,4.0)
POLS=("uniform_nopin","uniform","adaptive")
designs=C.extreme_samples()+C.convergence_subset(4)  # 6 extremes + 4 normals
keys=[k for k,_ in designs]
cases=[]
for k in keys:
    for a in ANG:
        cases.append(dict(sample_key=k,n_sections=201,policy="uniform",alpha_deg=a,nchord=NCH,spanw=SPW,tag="s1d"))
        for pol in POLS:
            cases.append(dict(sample_key=k,n_sections=25,policy=pol,alpha_deg=a,nchord=NCH,spanw=SPW,tag="s1d"))
print(f"Stage 1d: {len(keys)} designs, {len(cases)} cases",flush=True)
C.parallel_by_design(cases,workers=4,tag="s1d")
def g(k,pol,N,a,q):
    r=C._collect_one(k,pol,N,a,NCH,SPW); return r.get(q) if r and r.get("ok") else None
def worstkey(k,pol):
    w=0;wc=None
    for q in KEY:
        for a in ANG:
            v=g(k,pol,25,a,q); ref=g(k,"uniform",201,a,q)
            if v is None or ref is None: continue
            e=abs(v-ref)/SCALE[q]*100
            if e>w: w,wc=e,(q,a)
    return w,wc
L=[];A=L.append
A("STAGE 1d — HARD-POINT ABLATION (c8s1u, ref=uniform-201, normalized worst-key %)")
A("="*74)
A(f"{'design':>16s} {'noPIN':>8s} {'uniform':>8s} {'adaptive':>8s}   what the pins buy")
res={}
for k in keys:
    wn,_=worstkey(k,"uniform_nopin"); wu,_=worstkey(k,"uniform"); wa,cu=worstkey(k,"adaptive")
    res[k]={"nopin":round(wn,3),"uniform":round(wu,3),"adaptive":round(wa,3)}
    gain=wn-wu
    A(f"{k.split(':')[-1]:>16s} {wn:8.2f} {wu:8.2f} {wa:8.2f}   pins cut {gain:+.2f}pp")
A("")
A(f"WORST over all designs: noPIN={max(r['nopin'] for r in res.values()):.2f}%  "
  f"uniform(pinned)={max(r['uniform'] for r in res.values()):.2f}%  "
  f"adaptive={max(r['adaptive'] for r in res.values()):.2f}%")
A("")
A("READ: if pinned-uniform << noPIN and adaptive >= pinned-uniform, the value is")
A("in the HARD POINTS (control edges + planform breaks), not the density rule.")
(C.CONFIG_ROOT/"stage1d_ablation.json").write_text(json.dumps(res,indent=2))
(C.CONFIG_ROOT/"stage1d_summary.txt").write_text("\n".join(L)+"\n")
print("\n".join(L))
