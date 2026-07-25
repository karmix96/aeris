"""Does CLUSTERING sections at the band edges fix the narrow-elevon failure?

Task 5 found the elevon error is set by the gain-ramp fraction = (ramp width
just outside the band edges) / (band width), r = +0.978. A narrow band has a
large ramp fraction at uniform spacing, hence elevon_narrow's 4.34%.

If the mechanism is right, the fix is NOT more sections everywhere -- it is
sections placed close to the band edges, which is exactly what an adaptive
distribution buys. Test: same 25-section budget, but with the two sections
adjacent to each band edge pulled in.
"""
import dataclasses, json
from pathlib import Path
import numpy as np
from aeris.common.config import load_yaml_config
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator
from aeris.geometry.geometric_information import adaptive_span_fractions  # noqa
from aeris.aero.models import FlightCondition
from aeris.generators.bwb_segmented_v1 import pygeo_avl_adapter as A
from aeris.aero.solvers import native_avl as na

C=Path("configs/geometry/bwb.yaml")
OUT=Path("data/lowfi_avl_study/narrow_fix"); OUT.mkdir(parents=True,exist_ok=True)
raw=load_yaml_config(C); gid,g=resolve_generator_and_config(raw)
base=get_geometry_generator(gid).sample_one(g,seed=7000)
NARROW=dataclasses.replace(base, elevon_start_frac=0.70, elevon_end_frac=0.85)

def build(fractions, sample):
    """Extract at explicit span fractions."""
    from aeris.common.config import load_yaml_config as _l
    from aeris.generators.bwb_segmented_v1.pygeo_adapter import (
        build_pygeo, extract_sections, stations_from_records)
    from aeris.generators.bwb_segmented_v1.pygeo_backend import _resolve_airfoil_database
    from aeris.generators.bwb_segmented_v1.services import (
        build_section_geometry_from_sample, generate_bwb_planform_from_sample)
    gcfg=resolve_generator_and_config(_l(C))[1]
    pl=generate_bwb_planform_from_sample(sample,gcfg)
    sg=build_section_geometry_from_sample(pl,sample,gcfg)
    st=tuple(stations_from_records(sg.sections,_resolve_airfoil_database(gcfg)))
    fm="asb_frame" if gcfg.pygeo.frame_mode=="aeris_frame" else gcfg.pygeo.frame_mode
    b=build_pygeo(st,k_span=gcfg.pygeo.k_span,frame_mode=fm,n_ctl=gcfg.pygeo.n_ctl,
                  tip=gcfg.pygeo.tip,tip_scale=gcfg.pygeo.tip_scale)
    ex=list(extract_sections(b,np.asarray(fractions),
        cst_order=gcfg.pygeo.extraction.cst_order,
        chordwise_points=gcfg.pygeo.extraction.chordwise_points))
    return ex, max(float(s.y_m) for s in ex)

S,E=0.70,0.85
ctl={"name":"elevon","hinge_point":float(NARROW.elevon_hinge_frac),"symmetric":True,
     "start_frac":S,"end_frac":E}

def uniform25():
    f=np.unique(np.concatenate([np.linspace(0,1,25),[S,E]]))
    return f
def clustered25(eps):
    """Same budget: 25 fractions, but two moved to sit eps outside each band edge."""
    f=list(np.linspace(0,1,25))
    # drop the two fractions nearest the edges from outside, re-place them tight
    f=[x for x in f if not (S-0.10<x<S) and not (E<x<E+0.10)]
    f += [S-eps, E+eps, S, E]
    f=np.unique(np.clip(np.array(f),0,1))
    return f

def ramp_frac(f):
    below=f[f<S-1e-9]; above=f[f>E+1e-9]
    r=((S-below[-1]) if len(below) else 0)+((above[0]-E) if len(above) else 0)
    return r/(E-S)

fc=FlightCondition(alpha_deg=6.0,beta_deg=0.0,velocity_mps=28.0,altitude_m=0.0)
cases={"uniform-25":uniform25(),"clustered eps=0.02":clustered25(0.02),
       "clustered eps=0.01":clustered25(0.01),"REFERENCE 49-uniform":np.unique(
           np.concatenate([np.linspace(0,1,49),[S,E]]))}
res={}
for name,f in cases.items():
    ex,semi=build(f,NARROW)
    smap,ps=A.build_realized_section_polar_bridge(ex,semispan_m=semi,mach=0.0)
    sp = 2 if len(f)>40 else 4
    r=na.run_native_avl_case(sorted(ex,key=lambda s:s.y_m),flight_condition=fc,
        output_dir=OUT/name.replace(" ","_").replace("=",""),section_map=smap,polar_store=ps,
        control=ctl,control_input_deg=4.0,diff_input_deg=0.0,
        nchordwise=24,spanwise_panels_per_section=sp,name="nf")
    cd=next(iter(r.control_derivatives.values()),{})
    res[name]={"n":len(f),"ramp_frac":ramp_frac(f),"CL_de":cd.get("CL"),
               "Cm_de":cd.get("Cm"),"CL":r.cl,"strips":r.n_strips,"status":r.status}
    print(f"{name:<22} n={len(f):>3} ramp/band={ramp_frac(f):6.1%} CL_de={cd.get('CL')}")
ref=res["REFERENCE 49-uniform"]
L=["Narrow elevon (band 0.70-0.85): does clustering sections at the band edges fix it?",
   "Same 25-section budget unless stated. nchordwise 24. Reference: 65 uniform sections.","",
   f"{'placement':<22}{'sections':>9}{'ramp/band':>11}{'CL_de':>11}{'err vs ref':>12}"]
for name,v in res.items():
    err=abs(v["CL_de"]-ref["CL_de"])/abs(ref["CL_de"])*100 if v["CL_de"] and ref["CL_de"] else float('nan')
    cl = f"{v['CL_de']:.6f}" if v["CL_de"] is not None else "FAILED"
    L.append(f"{name:<22}{v['n']:>9}{v['ramp_frac']:>10.1%}{cl:>11}{err:>11.2f}%")
t="\n".join(L); print("\n"+t)
(OUT/"narrow_fix.txt").write_text(t+"\n"); json.dump(res,open(OUT/"narrow_fix.json","w"),indent=2,default=str)
