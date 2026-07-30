import json, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, numpy as np, statistics, common_sections as C
d=json.load(open(C.CONFIG_ROOT/"redo_c16_full.json")); ab=d["ablation"]
pols=["nopin","pinned","adaptive"]; labels=["uniform\nno pins","uniform\n+ pins","adaptive\ndensity"]
med=[statistics.median([ab[k][p] for k in ab]) for p in pols]
wor=[max([ab[k][p] for k in ab]) for p in pols]
x=np.arange(3); w=0.38
fig,ax=plt.subplots(figsize=(6.4,4.3))
b1=ax.bar(x-w/2,med,w,label="median (36 designs)",color="seagreen")
b2=ax.bar(x+w/2,wor,w,label="worst-case",color="#c0203a")
ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_ylabel("section error vs uniform-89 [%]")
ax.legend(); ax.set_title("Production mesh c16s2u, 36 designs: pins do the work, adaptive never wins")
for b in list(b1)+list(b2):
    ax.annotate(f"{b.get_height():.1f}",(b.get_x()+b.get_width()/2,b.get_height()),
                ha="center",va="bottom",fontsize=8)
fig.savefig(C.PLOTS_ROOT/"redo_c16_ablation.png",dpi=150,bbox_inches="tight"); plt.close(fig)
print("ok median",med,"worst",wor)
