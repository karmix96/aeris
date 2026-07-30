import json, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, numpy as np, common_sections as C
d=json.load(open(C.CONFIG_ROOT/"confirm_c16.json"))
ks=list(d); sh=[k.split(':')[-1][:10] for k in ks]; x=np.arange(len(ks)); w=0.27
fig,ax=plt.subplots(figsize=(8,4.2))
ax.bar(x-w,[d[k]["nopin"] for k in ks],w,label="uniform, NO pins",color="#c0203a")
ax.bar(x,[d[k]["pinned"] for k in ks],w,label="uniform + pins",color="seagreen")
ax.bar(x+w,[d[k]["adaptive"] for k in ks],w,label="adaptive",color="navy")
ax.set_xticks(x); ax.set_xticklabels(sh,rotation=90,fontsize=7)
ax.set_ylabel("worst-case error [%]"); ax.legend()
ax.set_title("Confirmed at production mesh c16s2u: pins 22%->1.3%, adaptive worse 8/8")
fig.savefig(C.PLOTS_ROOT/"confirm_c16.png",dpi=150,bbox_inches="tight"); plt.close(fig)
print("ok")
