"""Complexity metric across ALL 36 designs (not one geom): channel shares +
information concentration, to show the pattern is universal."""
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import common_sections as C
from aeris.geometry.geometric_information import spanwise_information_profile

designs=C.normal_samples()+C.extreme_samples()
chans=["control_gain","camber","twist","x_le","chord","z_le","thickness"]
shares={c:[] for c in chans}; conc=[]; rhos=[]
for key,s in designs:
    ctx=C.build_context(s,key)
    prof=spanwise_information_profile(ctx["build"],n_probe=201,chordwise_probe=21,control_band=ctx["band"])
    sh=prof.channel_shares()
    for c in chans: shares[c].append(sh.get(c,0)*100)
    conc.append(prof.concentration())
    rhos.append((prof.span_fraction, prof.density/np.trapezoid(prof.density,prof.span_fraction)))
    print(key.split(":")[-1], "control_gain%", round(sh.get("control_gain",0)*100,1))

fig,axes=plt.subplots(1,2,figsize=(10,4))
# left: box of channel shares across 36 designs
bp=axes[0].boxplot([shares[c] for c in chans],vert=False,tick_labels=chans,patch_artist=True,widths=.6)
for patch in bp['boxes']: patch.set_facecolor("#1f4e79"); patch.set_alpha(.6)
axes[0].set_xlabel("share of blended complexity [%]  —  across all 36 designs")
axes[0].set_title("Which features drive complexity — every design",fontsize=10,loc="left")
axes[0].invert_yaxis()
# right: rho(y) for all 36 (thin) to show the universal pattern
for x,r in rhos: axes[1].plot(x,r,color="#1f4e79",alpha=.18,lw=.9)
axes[1].set_xlabel("span fraction"); axes[1].set_yticks([])
axes[1].set_title(f"Information density ρ(y), all 36 designs\n(control-edge peaks universal; median concentration {np.median(conc):.2f})",fontsize=10,loc="left")
axes[1].set_xlim(0,1)
fig.tight_layout(); fig.savefig(C.PLOTS_ROOT/"sections_complexity_allgeoms.png",dpi=150,bbox_inches="tight")
print("\ncontrol_gain share: min %.1f  median %.1f  max %.1f  (n=%d designs)"%(
    min(shares["control_gain"]),np.median(shares["control_gain"]),max(shares["control_gain"]),len(designs)))
