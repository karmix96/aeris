import numpy as np, common_sections as C
from aeris.geometry.geometric_information import spanwise_information_profile, probe_spanwise_geometry
for key in ["lhs30s2000:00","extreme:narrow_elevon"]:
    s=C.sample_by_key(key); ctx=C.build_context(s,key)
    geo=probe_spanwise_geometry(ctx["build"],n_probe=201,chordwise_probe=21)
    prof=spanwise_information_profile(ctx["build"],n_probe=201,chordwise_probe=21,control_band=ctx["band"])
    z=geo["z_le"]
    print(f"\n{key}")
    print(f"  z_le (dihedral height) range: {z.min():.4f} .. {z.max():.4f} m  (span-varying rise = {z.max()-z.min():.4f} m)")
    sh=prof.channel_shares()
    print("  channel shares [%]:", {k:round(v*100,1) for k,v in sorted(sh.items(),key=lambda x:-x[1])})
