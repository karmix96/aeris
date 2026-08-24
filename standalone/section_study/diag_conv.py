"""Does the placement disagreement shrink with N? (chord8/span1, N up to 201)"""
import common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_ind":0.00355085,"cd_total":0.0103324,
       "x_np":0.306318,"elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,
       "hinge_moments.elevon_sym":0.0002872}
def delta(k,s,N,a,q):
    ru=C.run_section_case(s,sample_key=k,n_sections=N,policy="uniform",alpha_deg=a,tag="conv",nchord=8,spanw=1)
    ra=C.run_section_case(s,sample_key=k,n_sections=N,policy="adaptive",alpha_deg=a,tag="conv",nchord=8,spanw=1)
    u=ru.get(q); ad=ra.get(q)
    if not isinstance(u,(int,float)) or not isinstance(ad,(int,float)): return None,None,None
    return u,ad,abs(u-ad)/max(abs(u),abs(ad),0.1*SCALE[q])*100
for k in ["lhs30s2000:00","lhs30s2000:01"]:
    s=C.sample_by_key(k)
    print(f"\n{k}: placement delta vs N (c8s1u)")
    for q,a in [("cd_ind",0.0),("cd_ind",4.0),("hinge_moments.elevon_sym",-2.0),("cl",0.0)]:
        row=[]
        for N in (89,151,201):
            u,ad,d=delta(k,s,N,a,q)
            row.append(f"N{N}:{d:.2f}%" if d is not None else f"N{N}:--")
        print(f"  {q:26s} a{a:+.0f}: "+"  ".join(row))
