"""Closing the last open axis: does the recommended grid hold at other angles of
attack? Everything so far was at alpha = 6 deg."""
import json
from pathlib import Path
import numpy as np
from aeris.aero.models import FlightCondition
from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
    build_pygeo_sections_from_config, run_pygeo_native_avl_case)
C=Path("configs/geometry/bwb.yaml"); OUT=Path("data/lowfi_avl_study/alpha_sweep")
OUT.mkdir(parents=True,exist_ok=True)
ALPHAS=[0.0,3.0,6.0,10.0,14.0]
GRIDS={"prod":(25,4,24),"ref":(33,4,20)}
TRACK=["CL","cd_total","CDind","Cm","Xnp","CLa","Cma","Clp","CL_de"]
def ext(r):
    s=r.stability_axis_derivatives or {}; c=next(iter(r.control_derivatives.values()),{})
    return {"CL":r.cl,"cd_total":r.cd_total,"CDind":r.cd_ind,"Cm":r.cm,"Xnp":r.x_np,
            "CLa":s.get("CLa"),"Cma":s.get("Cma"),"Clp":s.get("Clp"),"CL_de":c.get("CL"),
            "n_extrap":r.n_extrapolated_strips,"status":r.status,"warn":len(r.warnings)}
res={}
for a in ALPHAS:
    per={}
    for gname,(ns,sp,ch) in GRIDS.items():
        ex,semi,meta=build_pygeo_sections_from_config(C,n_sections=ns,seed=7000)
        fc=FlightCondition(alpha_deg=a,beta_deg=0.0,velocity_mps=28.0,altitude_m=0.0)
        r=run_pygeo_native_avl_case(flight_condition=fc,output_dir=OUT/f"a{a}_{gname}",
            extracted_sections=ex,semispan_m=semi,control=meta["control"],
            control_input_deg=4.0,diff_input_deg=0.0,viscous=True,
            nchordwise=ch,spanwise_panels_per_section=sp,name="al")
        per[gname]=ext(r)
    errs={}
    for k in TRACK:
        x,y=per["prod"][k],per["ref"][k]
        if x is None or y is None: continue
        d=max(abs(x),abs(y))
        if d>1e-9: errs[k]=abs(x-y)/d
    res[a]={"prod":per["prod"],"ref":per["ref"],"err":errs}
    print(f"alpha {a:>5.1f}  CL={per['prod']['CL']:.4f}  worst err={max(errs.values())*100:.2f}%  "
          f"clamped strips={per['prod']['n_extrap']}")
json.dump(res,open(OUT/"alpha.json","w"),indent=2,default=str)
L=["Does the recommended grid hold across angle of attack?",
   "25/4/24 vs 33/4/20 reference, seed 7000, viscous on","",
   f"{'alpha':>7}{'CL':>9}{'clamped':>9}"+"".join(f"{k:>9}" for k in ("CL","CDind","Cm","CL_de","WORST"))]
for a,v in res.items():
    e=v["err"]
    L.append(f"{a:>7.1f}{v['prod']['CL']:>9.4f}{str(v['prod']['n_extrap']):>9}"+
             "".join(f"{e.get(k,float('nan'))*100:8.2f}%" for k in ("CL","CDind","Cm","CL_de"))+
             f"{max(e.values())*100:8.2f}%")
t="\n".join(L); print("\n"+t); (OUT/"alpha.txt").write_text(t+"\n")
