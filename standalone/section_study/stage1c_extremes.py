"""Stage 1c — the decisive test: does adaptive placement beat uniform on the
HARD cases (where DECISION-0011 says it should)? Both candidates vs the
converged uniform-201 reference, NORMALIZED discrepancy, at c8s1u."""
import json
import common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_ind":0.00355085,"cd_total":0.0103324,
       "x_np":0.306318,"elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,
       "elevon_diff.Cl":0.002594,"hinge_moments.elevon_sym":0.0002872}
KEY=tuple(SCALE); NCH,SPW=8,1; ANG=(-2.0,0.0,4.0)
designs=C.extreme_samples()
keys=[k for k,_ in designs]
cases=[]
for k in keys:
    for a in ANG:
        for N in (151,201): cases.append(dict(sample_key=k,n_sections=N,policy="uniform",alpha_deg=a,nchord=NCH,spanw=SPW,tag="s1c"))
        for pol in ("uniform","adaptive"): cases.append(dict(sample_key=k,n_sections=25,policy=pol,alpha_deg=a,nchord=NCH,spanw=SPW,tag="s1c"))
print(f"Stage 1c: {len(keys)} extremes, {len(cases)} cases @c8s1u",flush=True)
C.parallel_by_design(cases,workers=4,tag="s1c")
def g(k,pol,N,a,q):
    r=C._collect_one(k,pol,N,a,NCH,SPW); return r.get(q) if r and r.get("ok") else None
def nrm(v,ref,q): return None if v is None or ref is None else abs(v-ref)/SCALE[q]*100
def ramp(k,pol):
    r=C._collect_one(k,pol,25,4.0,NCH,SPW); return r.get("ramp_fraction") if r else None
L=[];A=L.append
A("STAGE 1c — ADAPTIVE vs UNIFORM ON HARD CASES (c8s1u, ref=uniform-201, normalized)")
A("="*74)
# legitimacy
wl=max((nrm(g(k,"uniform",151,a,q),g(k,"uniform",201,a,q),q) or 0)
       for k in keys for a in ANG for q in KEY)
A(f"reference legitimacy (uniform 151v201, worst): {wl:.3f}% -> {'ok' if wl<1 else 'marginal'}")
A("")
A(f"{'design':>16s} {'ramp_u':>7s} {'ramp_a':>7s} | worst-key uniform-25 -> adaptive-25 (normalized %)")
res={}
for k in keys:
    wu=wa=0; qu=qa=None
    for q in KEY:
        for a in ANG:
            eu=nrm(g(k,"uniform",25,a,q),g(k,"uniform",201,a,q),q)
            ea=nrm(g(k,"adaptive",25,a,q),g(k,"uniform",201,a,q),q)
            if eu and eu>wu: wu,qu=eu,(q,a)
            if ea and ea>wa: wa,qa=ea,(q,a)
    res[k]={"uniform":wu,"adaptive":wa,"win":"adaptive" if wa<wu-0.1 else "uniform" if wu<wa-0.1 else "tie"}
    A(f"{k.split(':')[-1]:>16s} {str(round(ramp(k,'uniform') or 0,2)):>7s} "
      f"{str(round(ramp(k,'adaptive') or 0,2)):>7s} | uni={wu:5.2f}%@{qu}  ada={wa:5.2f}%@{qa}  -> {res[k]['win']}")
A("")
nu=sum(1 for k in keys if res[k]['win']=='uniform'); na=sum(1 for k in keys if res[k]['win']=='adaptive')
A(f"WORST-CASE per design: adaptive wins {na}/{len(keys)}, uniform wins {nu}/{len(keys)}")
A(f"worst-case over ALL extremes: uniform={max(res[k]['uniform'] for k in keys):.2f}%  "
  f"adaptive={max(res[k]['adaptive'] for k in keys):.2f}%")
(C.CONFIG_ROOT/"stage1c_extremes.json").write_text(json.dumps(res,indent=2))
(C.CONFIG_ROOT/"stage1c_summary.txt").write_text("\n".join(L)+"\n")
print("\n".join(L))
