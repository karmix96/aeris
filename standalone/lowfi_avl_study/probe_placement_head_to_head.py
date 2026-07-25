"""Does uniform placement still fail on a narrow elevon, now that band-edge
snapping INSERTS rather than moves? This decides whether DECISION-0011's
adaptive placement is still justified."""
import dataclasses, json
from pathlib import Path
from aeris.common.config import load_yaml_config
from aeris.geometry.config_resolver import resolve_generator_and_config
from aeris.geometry.registry import get_geometry_generator
from aeris.aero.models import FlightCondition
from aeris.generators.bwb_segmented_v1 import pygeo_avl_adapter as A

C=Path("configs/geometry/bwb.yaml")
raw=load_yaml_config(C); gid,g=resolve_generator_and_config(raw)
base=get_geometry_generator(gid).sample_one(g,seed=7000)
OUT=Path("data/lowfi_avl_study/decisive"); OUT.mkdir(parents=True,exist_ok=True)

def run(sample, placement, ns, sp, ch, tag):
    import aeris.generators.bwb_segmented_v1.params as P
    gc=resolve_generator_and_config(load_yaml_config(C))[1]
    gc2=dataclasses.replace(gc, aero_discretisation=dataclasses.replace(
        gc.aero_discretisation, section_placement=placement, n_sections=ns))
    # patch the resolver for this call
    import aeris.geometry.config_resolver as CR
    orig=CR.resolve_generator_and_config
    CR.resolve_generator_and_config=lambda raw: (gid, gc2)
    A_resolve = A.__dict__.get("resolve_generator_and_config")
    try:
        ex,semi,meta=A.build_pygeo_sections_from_config(C,sample=sample,n_sections=ns)
    finally:
        CR.resolve_generator_and_config=orig
    fc=FlightCondition(alpha_deg=6.0,beta_deg=0.0,velocity_mps=28.0,altitude_m=0.0)
    r=A.run_pygeo_native_avl_case(flight_condition=fc,output_dir=OUT/tag,
        extracted_sections=ex,semispan_m=semi,control=meta["control"],
        control_input_deg=4.0,diff_input_deg=0.0,viscous=True,
        nchordwise=ch,spanwise_panels_per_section=sp,name="d")
    cd=next(iter(r.control_derivatives.values()),{})
    return {"placement":meta["section_placement"],"ramp":meta.get("ramp_fraction"),
            "n":meta["n_sections"],"CL_de":cd.get("CL"),"CL":r.cl}

narrow=dataclasses.replace(base, elevon_start_frac=0.70, elevon_end_frac=0.85)
normal=base
print(f"{'design':<10}{'placement':<10}{'n':>4}{'ramp':>8}{'CL_de':>11}{'err vs ref':>12}")
for nm,s in (("narrow",narrow),("normal",normal)):
    ref=run(s,"never",49,2,24,f"{nm}_ref")
    for mode in ("never","always"):
        v=run(s,mode,25,4,24,f"{nm}_{mode}")
        err=abs(v["CL_de"]-ref["CL_de"])/abs(ref["CL_de"])*100
        print(f"{nm:<10}{v['placement']:<10}{v['n']:>4}{v['ramp']:>7.1%}{v['CL_de']:>11.6f}{err:>11.2f}%")
    print(f"{'':<10}{'REF 49':<10}{ref['n']:>4}{ref['ramp']:>7.1%}{ref['CL_de']:>11.6f}{'--':>12}")
