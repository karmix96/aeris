"""Pre-declared single test of the standard remedy for equidistribution failure.

Diagnosis: pure equidistribution left a max section gap 4.4x larger than uniform,
starving the inboard region. Mesh-adaptation theory's remedy is gradation control
-- bound how far cell size may depart from uniform. Implemented here as the
existing `floor` knob (uniform density mixed back in), raised from 0.15 to 0.50,
declared BEFORE running and tested once. Whatever it gives is what gets reported.
"""
import dataclasses, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0,"standalone/lowfi_avl_study")
from validate_adaptive_sections import build_loft, extract_at, run, CASES, N_BUDGET, REF_SECTIONS
from aeris.common.config import load_yaml_config
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator
from aeris.geometry.geometric_information import (
    spanwise_information_profile, adaptive_span_fractions, ramp_fraction)

FLOOR = 0.50
raw=load_yaml_config(Path("configs/geometry/bwb.yaml")); gid,g=resolve_generator_and_config(raw)
base=get_geometry_generator(gid).sample_one(g,seed=7000)
out={}
for name in ("benign","elevon_narrow","max_gradient"):
    s=dataclasses.replace(base,**CASES[name])
    b,gc=build_loft(s); band=(float(s.elevon_start_frac),float(s.elevon_end_frac))
    ctl={"name":"elevon","hinge_point":float(s.elevon_hinge_frac),"symmetric":True,
         "start_frac":band[0],"end_frac":band[1]}
    prof=spanwise_information_profile(b,n_probe=301,chordwise_probe=21,
                                      control_band=band,floor=FLOOR)
    ada=adaptive_span_fractions(prof,N_BUDGET,must_include=band)
    uni=np.unique(np.concatenate([np.linspace(0,1,N_BUDGET),list(band)]))
    ref=np.unique(np.concatenate([np.linspace(0,1,REF_SECTIONS),list(band)]))
    ex_a,s_a=extract_at(b,gc,ada); ex_u,s_u=extract_at(b,gc,uni); ex_r,s_r=extract_at(b,gc,ref)
    ra=run(ex_a,s_a,ctl,f"grad_{name}_ada"); ru=run(ex_u,s_u,ctl,f"grad_{name}_uni")
    rr=run(ex_r,s_r,ctl,f"grad_{name}_ref",spanwise=2)
    ea=abs(ra["CL_de"]-rr["CL_de"])/abs(rr["CL_de"]); eu=abs(ru["CL_de"]-rr["CL_de"])/abs(rr["CL_de"])
    gu=np.diff(np.sort(uni)).max(); ga=np.diff(np.sort(ada)).max()
    out[name]={"floor":FLOOR,"ramp_u":ramp_fraction(uni,band),"ramp_a":ramp_fraction(ada,band),
               "err_u":eu,"err_a":ea,"maxgap_u":gu,"maxgap_a":ga,"gain":eu/ea if ea else None}
    print(f"{name:<15} ramp {out[name]['ramp_u']:.1%}->{out[name]['ramp_a']:.1%}  "
          f"maxgap {gu:.4f}->{ga:.4f} ({ga/gu:.1f}x)  "
          f"CL_de err {eu*100:.2f}% -> {ea*100:.2f}%  gain {eu/ea if ea else 0:.2f}x")
json.dump(out,open("data/lowfi_avl_study/adaptive_sections/gradation.json","w"),indent=2,default=str)
