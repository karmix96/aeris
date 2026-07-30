import json, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, numpy as np
import common_sections as C
P=C.PLOTS_ROOT
# 1) ablation bars
ab=json.load(open(C.CONFIG_ROOT/"stage1d_ablation.json"))
designs=[k for k in ab]; short=[k.split(':')[-1][:10] for k in designs]
x=np.arange(len(designs)); w=0.27
fig,axx=plt.subplots(figsize=(8,4.2))
axx.bar(x-w,[ab[k]["nopin"] for k in designs],w,label="uniform, NO pins",color="#c0203a")
axx.bar(x,[ab[k]["uniform"] for k in designs],w,label="uniform + hard-point pins",color="seagreen")
axx.bar(x+w,[ab[k]["adaptive"] for k in designs],w,label="adaptive density",color="navy")
axx.set_xticks(x); axx.set_xticklabels(short,rotation=90,fontsize=7)
axx.set_ylabel("worst-case section error [%]"); axx.legend()
axx.set_title("Hard-point pins do the work; adaptive density hurts")
fig.savefig(P/"section_ablation.png",dpi=150,bbox_inches="tight"); plt.close(fig)
# 2) extremes head-to-head
ex=json.load(open(C.CONFIG_ROOT/"stage1c_extremes.json"))
ks=[k for k in ex]; sh=[k.split(':')[-1] for k in ks]
x=np.arange(len(ks)); w=0.38
fig,axx=plt.subplots(figsize=(7,4.2))
axx.bar(x-w/2,[ex[k]["uniform"] for k in ks],w,label="uniform+pins",color="seagreen")
axx.bar(x+w/2,[ex[k]["adaptive"] for k in ks],w,label="adaptive",color="navy")
axx.set_xticks(x); axx.set_xticklabels(sh,rotation=30,ha="right",fontsize=8)
axx.set_ylabel("worst-case error [%]"); axx.legend()
axx.set_title("Hard cases: uniform+pins beats adaptive 6/6")
fig.savefig(P/"section_extremes.png",dpi=150,bbox_inches="tight"); plt.close(fig)
print("wrote", P/"section_ablation.png", P/"section_extremes.png")
