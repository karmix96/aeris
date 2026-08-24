"""Stage 3 — count convergence for PINNED UNIFORM (the winning policy).
Worst-key normalized error vs the converged uniform-201 reference, as a function
of N, split into RESOLVABLE quantities vs the placement-limited (cd_ind, hinge)."""
import json
import common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_ind":0.00355085,"cd_total":0.0103324,
       "x_np":0.306318,"elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,
       "elevon_diff.Cl":0.002594,"hinge_moments.elevon_sym":0.0002872}
RESOLVABLE=("cl","cm","cd_total","x_np","elevon_sym.CL","elevon_sym.Cm","elevon_diff.Cl")
LIMITED=("cd_ind","hinge_moments.elevon_sym")
NCH,SPW=8,1; ANG=(-2.0,0.0,4.0); NS=(25,49,101,151)
designs=C.convergence_subset(8)+C.extreme_samples()
keys=[k for k,_ in designs]
# ensure the count levels exist (mostly cached); solve missing
cases=[dict(sample_key=k,n_sections=N,policy="uniform",alpha_deg=a,nchord=NCH,spanw=SPW,tag="s3")
       for k in keys for N in (25,49,101,151,201) for a in ANG]
C.parallel_by_design(cases,workers=4,tag="s3")
def g(k,N,a,q):
    r=C._collect_one(k,"uniform",N,a,NCH,SPW); return r.get(q) if r and r.get("ok") else None
def worst(qset,N):
    w=0
    for k in keys:
        for q in qset:
            for a in ANG:
                v=g(k,N,a,q); ref=g(k,201,a,q)
                if v is None or ref is None: continue
                w=max(w,abs(v-ref)/SCALE[q]*100)
    return round(w,3)
rows={"resolvable":{N:worst(RESOLVABLE,N) for N in NS},
      "limited":{N:worst(LIMITED,N) for N in NS}}
L=[];A=L.append
A("STAGE 3 — COUNT CONVERGENCE, pinned uniform (c8s1u, ref=uniform-201, normalized worst-case %)")
A("="*76)
A(f"  {'N':>5s} {'resolvable-q':>13s} {'placement-limited':>18s}")
for N in NS:
    A(f"  {N:>5d} {rows['resolvable'][N]:13.2f} {rows['limited'][N]:18.2f}")
A("")
A("resolvable = cl,cm,cd_total,x_np,elevon_sym.CL/Cm,elevon_diff.Cl")
A("placement-limited = cd_ind (Trefftz strip-distribution), hinge (print floor)")
A("")
# knee: smallest N with resolvable < 1%
knee=next((N for N in NS if rows["resolvable"][N]<1.0), None)
A(f"KNEE: resolvable quantities reach <1% worst-case at N>={knee}" if knee
  else "resolvable quantities do NOT reach <1% by N=151 (report band)")
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(6,4.2))
    ax.plot(NS,[rows["resolvable"][N] for N in NS],"o-",color="seagreen",lw=2,label="resolvable")
    ax.plot(NS,[rows["limited"][N] for N in NS],"s--",color="crimson",lw=2,label="cd_ind / hinge")
    ax.axhline(1.0,color="k",ls=":",lw=1); ax.set_xlabel("sections N"); ax.set_ylabel("worst-case error vs converged ref [%]")
    ax.set_title("Section-count convergence (pinned uniform)"); ax.legend(); ax.set_ylim(bottom=0)
    fig.savefig(C.PLOTS_ROOT/"stage3_count.png",dpi=150,bbox_inches="tight"); plt.close(fig)
except Exception as e: A(f"plot skip {e}")
(C.CONFIG_ROOT/"stage3_count.json").write_text(json.dumps(rows,indent=2))
(C.CONFIG_ROOT/"stage3_summary.txt").write_text("\n".join(L)+"\n")
print("\n".join(L))
