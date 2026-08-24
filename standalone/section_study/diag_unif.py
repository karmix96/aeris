"""Corrected legitimacy: does DENSE UNIFORM converge in N (Richardson)?
That, not cross-placement neutrality, is the reference test."""
import common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_ind":0.00355085,"cd_total":0.0103324,
       "x_np":0.306318,"elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,
       "hinge_moments.elevon_sym":0.0002872}
def u(k,s,N,a,q):
    r=C.run_section_case(s,sample_key=k,n_sections=N,policy="uniform",alpha_deg=a,tag="conv",nchord=8,spanw=1)
    return r.get(q) if r.get("ok") else None
for k in ["lhs30s2000:00","lhs30s2000:01"]:
    s=C.sample_by_key(k)
    print(f"\n{k}: uniform |N201-N151| as % (converged if small), key quantities @a=+4 and a=0")
    for q in ["cl","cm","cd_total","x_np","elevon_sym.CL","elevon_sym.Cm","cd_ind","hinge_moments.elevon_sym"]:
        cells=[]
        for a in (0.0,4.0):
            v151=u(k,s,151,a,q); v201=u(k,s,201,a,q)
            if isinstance(v151,(int,float)) and isinstance(v201,(int,float)):
                d=abs(v201-v151)/max(abs(v201),0.1*SCALE[q])*100
                cells.append(f"a{a:+.0f}:{d:.2f}%")
        print(f"  {q:26s} "+"  ".join(cells))
