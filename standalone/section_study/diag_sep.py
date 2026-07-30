"""Separability spot-check: is the placement effect (uniform->adaptive delta)
independent of the panel mesh? Compare c16s2u vs chord8/span1 at N=89."""
import common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_ind":0.00355085,"cd_total":0.0103324,
       "x_np":0.306318,"elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,
       "hinge_moments.elevon_sym":0.0002872}
def run(k,s,pol,a,nch,sp):
    return C.run_section_case(s,sample_key=k,n_sections=89,policy=pol,alpha_deg=a,
                              tag="sep",nchord=nch,spanw=sp)
keys=[k for k,_ in C.convergence_subset(2)]
print("placement delta (uniform vs adaptive), scale-floored, per mesh:")
for k in keys:
    s=C.sample_by_key(k)
    for (nch,sp,lbl) in [(16,2,"c16s2u"),(8,1,"c8s1u")]:
        worst=0; where=None
        for a in (-2.0,0.0,4.0):
            ru=run(k,s,"uniform",a,nch,sp); ra=run(k,s,"adaptive",a,nch,sp)
            if not(ru["ok"] and ra["ok"]): 
                print(f"  {k} {lbl} a{a}: FAILED"); continue
            for q in SCALE:
                u=ru.get(q); ad=ra.get(q)
                if not isinstance(u,(int,float)) or not isinstance(ad,(int,float)): continue
                denom=max(abs(u),abs(ad),0.1*SCALE[q])
                sp_=abs(u-ad)/denom*100
                if sp_>worst: worst,where=sp_,(a,q)
        print(f"  {k} {lbl:8s}: worst placement delta={worst:.3f}% @{where}")
