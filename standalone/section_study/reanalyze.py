"""Recompute Stage 1b with NORMALIZED discrepancy (error/frozen-scale) — the
§4.5 rule that removes the near-zero-at-alpha=0 inflation. No new solves."""
import common_sections as C
SCALE={"cl":0.195025,"cm":0.10417,"cd_ind":0.00355085,"cd_total":0.0103324,
       "x_np":0.306318,"elevon_sym.CL":0.010146,"elevon_sym.Cm":0.00701,
       "elevon_diff.Cl":0.002594,"hinge_moments.elevon_sym":0.0002872}
KEY=tuple(SCALE); NCH,SPW=8,1; ANG=(-2.0,0.0,4.0)
keys=[k for k,_ in C.convergence_subset(8)]
def g(k,pol,N,a,q):
    r=C._collect_one(k,pol,N,a,NCH,SPW); return r.get(q) if r and r.get("ok") else None
def nrm(v,ref,q):  # normalized discrepancy, % of typical scale
    return None if v is None or ref is None else abs(v-ref)/SCALE[q]*100

print("LEGITIMACY (uniform N151 vs N201), NORMALIZED, worst over q,a per design:")
worstL=0
for k in keys:
    w=0; wc=None
    for a in ANG:
        for q in KEY:
            e=nrm(g(k,"uniform",151,a,q),g(k,"uniform",201,a,q),q)
            if e and e>w: w,wc=e,(a,q)
    worstL=max(worstL,w)
    print(f"  {k}: {w:.3f}%  @{wc}")
print(f"  => worst {worstL:.3f}%  reference legitimate={worstL<0.5}\n")

print("PLACEMENT ERROR vs uniform-201 ref, NORMALIZED, worst over designs&angles:")
print(f"  {'quantity':>24s} {'uni25':>7s} {'ada25':>7s} {'uni49':>7s} {'ada49':>7s}   winner@25")
for q in KEY:
    row={}
    for pol in ("uniform","adaptive"):
        for N in (25,49):
            w=0
            for k in keys:
                for a in ANG:
                    e=nrm(g(k,pol,N,a,q),g(k,"uniform",201,a,q),q)
                    if e: w=max(w,e)
            row[(pol,N)]=w
    u,ad=row[("uniform",25)],row[("adaptive",25)]
    win="adaptive" if ad<u-0.1 else "uniform" if u<ad-0.1 else "tie"
    print(f"  {q:>24s} {row[('uniform',25)]:7.2f} {row[('adaptive',25)]:7.2f} "
          f"{row[('uniform',49)]:7.2f} {row[('adaptive',49)]:7.2f}   {win}")
