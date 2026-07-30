"""Visuals the section study was missing:
 1) placement vs complexity ("money figure") — where uniform vs adaptive put
    sections, over the information density rho(y), with control band + hard points;
 2) the spanwise distributions of the geometry+aero characteristics;
 3) what drives the complexity — per-channel information density + shares.
"""
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import common_sections as C
from aeris.geometry.geometric_information import (
    spanwise_information_profile, probe_spanwise_geometry)

ACC="#1f4e79"; ADA="#b3243b"; UNI="#1c6b4a"; BAND="#f2c94c"
P=C.PLOTS_ROOT

def ctx_for(key):
    s=C.sample_by_key(key); ctx=C.build_context(s,key)
    prof=spanwise_information_profile(ctx["build"],n_probe=301,chordwise_probe=21,
                                      control_band=ctx["band"])
    geo=probe_spanwise_geometry(ctx["build"],n_probe=301,chordwise_probe=21)
    return ctx,prof,geo

# ---------- FIG 1: placement vs complexity ---------------------------------- #
def money(keys,fname):
    fig,axes=plt.subplots(len(keys),1,figsize=(7.2,3.1*len(keys)),squeeze=False)
    for ax,(key,title) in zip(axes[:,0],keys):
        ctx,prof,_=ctx_for(key)
        x=prof.span_fraction; rho=prof.density/np.trapezoid(prof.density,x)
        ax.fill_between(x,rho,color=ACC,alpha=.18,lw=0)
        ax.plot(x,rho,color=ACC,lw=1.6,label="information density ρ(y)")
        if ctx["band"]:
            ax.axvspan(ctx["band"][0],ctx["band"][1],color=BAND,alpha=.28,lw=0,label="elevon band")
        for p in ctx["pins"]:
            if 0<p<1: ax.axvline(p,color="#555",ls=":",lw=.9)
        uni=C.fractions_for(ctx,25,"uniform"); ada=C.fractions_for(ctx,25,"adaptive")
        yl=ax.get_ylim()[1]
        ax.plot(uni,[yl*1.02]*len(uni),"|",color=UNI,ms=13,mew=1.8)
        ax.plot(ada,[yl*-0.05]*len(ada),"|",color=ADA,ms=13,mew=1.8)
        ax.text(0.01,yl*1.06,f"uniform ({len(uni)})",color=UNI,fontsize=8,fontweight="bold")
        ax.text(0.01,yl*-0.14,f"adaptive ({len(ada)})",color=ADA,fontsize=8,fontweight="bold")
        ax.set_ylim(yl*-0.18,yl*1.18); ax.set_xlim(0,1)
        ax.set_title(title,fontsize=10,loc="left")
        ax.set_yticks([]); ax.set_xlabel("span fraction (root → tip)")
    axes[0,0].legend(loc="upper right",fontsize=7.5,framealpha=.9)
    fig.suptitle("Where the sections land vs geometric complexity",fontweight="bold",y=0.995)
    fig.tight_layout(); fig.savefig(P/fname,dpi=150,bbox_inches="tight"); plt.close(fig)
    print("wrote",fname)

# ---------- FIG 2: geometry+aero distributions ------------------------------ #
def distributions(key,fname):
    ctx,prof,geo=ctx_for(key)
    x=geo["span_fraction"]
    gain=prof.channels["control_gain"].normalised if "control_gain" in prof.channels else np.zeros_like(x)
    panels=[("chord [m]",geo["chord"],UNI),("LE sweep  x_le [m]",geo["x_le"],ACC),
            ("dihedral  z_le [m]",geo["z_le"],"#1b998b"),("twist [deg]",geo["twist_deg"],"#8a6410"),
            ("thickness  t/c",geo["thickness"],"#6a3d9a"),("camber",geo["camber"],"#e07b39"),
            ("control gain (elevon)",gain,ADA)]
    fig,axes=plt.subplots(2,4,figsize=(11.5,5))
    axes.ravel()[-1].axis("off")
    for ax,(t,v,col) in zip(axes.ravel(),panels):
        ax.plot(x,v,color=col,lw=1.8)
        if ctx["band"]: ax.axvspan(ctx["band"][0],ctx["band"][1],color=BAND,alpha=.25,lw=0)
        for p in ctx["pins"]:
            if 0<p<1: ax.axvline(p,color="#999",ls=":",lw=.7)
        ax.set_title(t,fontsize=9,loc="left"); ax.set_xlim(0,1)
        ax.tick_params(labelsize=7)
    for ax in axes[-1,:]: ax.set_xlabel("span fraction",fontsize=8)
    fig.suptitle(f"Spanwise distribution of geometry + control characteristics — {key.split(':')[-1]}",
                 fontweight="bold",fontsize=11)
    fig.tight_layout(); fig.savefig(P/fname,dpi=150,bbox_inches="tight"); plt.close(fig)
    print("wrote",fname)

# ---------- FIG 3: complexity drivers --------------------------------------- #
def drivers(keys,fname):
    fig,axes=plt.subplots(1,2,figsize=(9,3.8))
    # left: per-channel density for design 0
    ctx,prof,_=ctx_for(keys[0])
    x=prof.span_fraction
    for name,ch in prof.channels.items():
        d=ch.weight*ch.density
        if np.trapezoid(d,x)>1e-6:
            axes[0].plot(x,d/np.trapezoid(prof.density,x),lw=1.5,label=name)
    if ctx["band"]: axes[0].axvspan(*ctx["band"],color=BAND,alpha=.2,lw=0)
    axes[0].set_title(f"per-channel information density — {keys[0].split(':')[-1]}",fontsize=9,loc="left")
    axes[0].set_xlabel("span fraction"); axes[0].set_yticks([]); axes[0].legend(fontsize=6.5,ncol=2)
    # right: channel shares bar for the listed designs
    names=None; data={}
    for k in keys:
        _,prof,_=ctx_for(k); sh=prof.channel_shares()
        names=list(sh.keys()); data[k.split(':')[-1]]=[sh[n]*100 for n in names]
    y=np.arange(len(names)); w=0.8/len(keys)
    for i,(lbl,vals) in enumerate(data.items()):
        axes[1].barh(y+i*w,vals,w,label=lbl)
    axes[1].set_yticks(y+w*(len(keys)-1)/2); axes[1].set_yticklabels(names,fontsize=7.5)
    axes[1].set_xlabel("share of blended complexity [%]"); axes[1].legend(fontsize=7)
    axes[1].set_title("which features drive the complexity",fontsize=9,loc="left")
    fig.tight_layout(); fig.savefig(P/fname,dpi=150,bbox_inches="tight"); plt.close(fig)
    print("wrote",fname)

if __name__=="__main__":
    money([("lhs30s2000:00","normal design (LHS #00)"),
           ("extreme:narrow_elevon","narrow_elevon extreme — adaptive bunches at the band")],
          "sections_placement_map.png")
    distributions("lhs30s2000:00","sections_distributions.png")
    drivers(["lhs30s2000:00","extreme:narrow_elevon"],"sections_complexity_drivers.png")
