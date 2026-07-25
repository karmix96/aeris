"""Total discretisation error: production grid vs recommended grid, against the
best reference affordable inside AVL's array limits (33 sections / 4 spanwise /
20 chordwise = 256 strips, 5120 vortices)."""
import json, numpy as np
from pathlib import Path
from aeris.aero.models import FlightCondition
from aeris.generators.bwb_segmented_v1.pygeo_avl_adapter import (
    build_pygeo_sections_from_config, run_pygeo_native_avl_case)
OUT=Path("data/lowfi_avl_study/joint_grid_check"); OUT.mkdir(parents=True,exist_ok=True)
GRIDS=[("production", 25,4,8),("recommended_16",25,4,16),("recommended_24",25,4,24),
       ("REFERENCE",33,4,20)]
TRACK=["CL","cd_total","CDind","Cm","e","Xnp","CLa","Cma","Clp","Cnb","Cmq","CL_de","Cm_de"]
def ext(r):
    s=r.stability_axis_derivatives or {}; c=next(iter(r.control_derivatives.values()),{})
    return {"CL":r.cl,"cd_total":r.cd_total,"CDind":r.cd_ind,"Cm":r.cm,"e":r.span_efficiency,
            "Xnp":r.x_np,"CLa":s.get("CLa"),"Cma":s.get("Cma"),"Clp":s.get("Clp"),
            "Cnb":s.get("Cnb"),"Cmq":s.get("Cmq"),"CL_de":c.get("CL"),"Cm_de":c.get("Cm"),
            "n_strips":r.n_strips,"n_vortices":r.n_vortices,"status":r.status}
data={}
for seed in (7000,7001,7002):
    per={}
    for name,ns,sp,ch in GRIDS:
        ex,semi,meta=build_pygeo_sections_from_config(Path("configs/geometry/bwb.yaml"),n_sections=ns,seed=seed)
        fc=FlightCondition(alpha_deg=6.0,beta_deg=0.0,velocity_mps=28.0,altitude_m=0.0)
        r=run_pygeo_native_avl_case(flight_condition=fc,output_dir=OUT/f"s{seed}_{name}",
            extracted_sections=ex,semispan_m=semi,control=meta["control"],
            control_input_deg=4.0,diff_input_deg=0.0,viscous=True,
            nchordwise=ch,spanwise_panels_per_section=sp,name="j")
        per[name]=ext(r)
    data[seed]=per
    print("seed",seed,"done")
err={}
for name,_,_,_ in GRIDS[:-1]:
    err[name]={}
    for k in TRACK:
        e=[]
        for seed in data:
            a,b=data[seed][name][k],data[seed]["REFERENCE"][k]
            if a is None or b is None: continue
            d=max(abs(a),abs(b))
            if d>1e-9: e.append(abs(a-b)/d)
        if e: err[name][k]={"median":float(np.median(e)),"worst":float(np.max(e))}
json.dump({"data":data,"errors":err,"grids":GRIDS},open(OUT/"joint.json","w"),indent=2,default=str)
L=["TOTAL discretisation error vs the best affordable reference (33 sec / 4 span / 20 chord)",
   f"{'grid':<16}{'strips':>7}{'vort':>7}"+"".join(f"{k:>10}" for k in TRACK)]
for name,ns,sp,ch in GRIDS:
    d0=data[7000][name]
    if name=="REFERENCE":
        L.append(f"{name:<16}{d0['n_strips']:>7}{d0['n_vortices']:>7}"+"".join(f"{'--':>10}" for k in TRACK)); continue
    L.append(f"{name:<16}{d0['n_strips']:>7}{d0['n_vortices']:>7}"+
             "".join(f"{err[name].get(k,{}).get('worst',float('nan')):>10.2e}" for k in TRACK))
t="\n".join(L); print("\n"+t); (OUT/"joint.txt").write_text(t+"\n")
