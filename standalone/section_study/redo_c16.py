"""FULL placement study at the PRODUCTION mesh c16s2u, all 30 normal + 6 extreme
designs. Reference = densest-affordable uniform-89 (vortex-capped). Produces:
reference legitimacy (uniform Richardson 25/49/89), the hard-point ablation
(nopin / pinned / adaptive), and the placement spectrum. Normalized metric."""
import json, statistics, common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_ind":0.00355085,"cd_total":0.0103324,
       "x_np":0.306318,"elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,
       "elevon_diff.Cl":0.002594,"hinge_moments.elevon_sym":0.0002872}
RESOLVABLE=("cl","cm","cd_total","x_np","elevon_sym.CL","elevon_sym.Cm","elevon_diff.Cl")
NCH,SPW=16,2; ANG=(-2.0,0.0,4.0); REF=89
designs=C.normal_samples()+C.extreme_samples()
keys=[k for k,_ in designs]
cases=[]
for k in keys:
    for a in ANG:
        for N in (25,49,89): cases.append(dict(sample_key=k,n_sections=N,policy="uniform",alpha_deg=a,nchord=NCH,spanw=SPW,tag="redo16"))
        for pol in ("uniform_nopin","adaptive"): cases.append(dict(sample_key=k,n_sections=25,policy=pol,alpha_deg=a,nchord=NCH,spanw=SPW,tag="redo16"))
print(f"REDO @c16s2u: {len(keys)} designs, {len(cases)} cases",flush=True)
C.parallel_by_design(cases,workers=4,tag="redo16")
def g(k,pol,N,a,q):
    r=C._collect_one(k,pol,N,a,NCH,SPW); return r.get(q) if r and r.get("ok") else None
def nrm(v,ref,q): return None if v is None or ref is None else abs(v-ref)/SCALE[q]*100
# reference legitimacy: uniform 49 vs 89 (densest pair), normalized
legit={}
for k in keys:
    w=max((nrm(g(k,"uniform",49,a,q),g(k,"uniform",89,a,q),q) or 0) for a in ANG for q in SCALE)
    legit[k]=round(w,3)
# ablation worst-key (resolvable only) vs uniform-89
def wk(k,pol):
    return max((nrm(g(k,pol,25,a,q),g(k,"uniform",89,a,q),q) or 0) for a in ANG for q in RESOLVABLE)
abl={}
for k in keys:
    abl[k]={"nopin":round(wk(k,"uniform_nopin"),3),"pinned":round(wk(k,"uniform"),3),
            "adaptive":round(wk(k,"adaptive"),3)}
def worstall(f): return max(f(k) for k in keys)
L=[];A=L.append
A("REDO — FULL PLACEMENT STUDY @ PRODUCTION MESH c16s2u (36 designs, ref=uniform-89, normalized)")
A("="*80)
A(f"reference legitimacy (uniform 49v89, worst over designs): {max(legit.values()):.3f}%")
A(f"  (a fully-converged <0.5% reference is vortex-capped out at c16s2u; N=89 is the densest legal)")
A("")
A("HARD-POINT ABLATION, worst-key resolvable error vs uniform-89 [%]:")
A(f"  {'placement':>24s} {'worst':>7s} {'median':>7s}")
for pol in ("nopin","pinned","adaptive"):
    vals=[abl[k][pol] for k in keys]
    A(f"  {pol:>24s} {max(vals):7.2f} {statistics.median(vals):7.2f}")
A("")
npin=sum(1 for k in keys if abl[k]["pinned"]<abl[k]["nopin"])
pad=sum(1 for k in keys if abl[k]["pinned"]<=abl[k]["adaptive"])
A(f"pinned < nopin on {npin}/{len(keys)}   |   pinned <= adaptive on {pad}/{len(keys)}")
A("")
A("WORST OFFENDERS (pinned uniform, resolvable):")
for k in sorted(keys,key=lambda k:-abl[k]["pinned"])[:5]:
    A(f"  {k:>22s}: pinned={abl[k]['pinned']:.2f}%  nopin={abl[k]['nopin']:.2f}%  adaptive={abl[k]['adaptive']:.2f}%")
out={"mesh":"c16s2u","ref":"uniform-89","n_designs":len(keys),"legit":legit,"ablation":abl,
     "worst":{"nopin":worstall(lambda k:abl[k]['nopin']),"pinned":worstall(lambda k:abl[k]['pinned']),
              "adaptive":worstall(lambda k:abl[k]['adaptive'])},
     "pinned_lt_nopin":f"{npin}/{len(keys)}","pinned_le_adaptive":f"{pad}/{len(keys)}"}
(C.CONFIG_ROOT/"redo_c16_full.json").write_text(json.dumps(out,indent=2))
(C.CONFIG_ROOT/"redo_c16_summary.txt").write_text("\n".join(L)+"\n")
print("\n".join(L))
