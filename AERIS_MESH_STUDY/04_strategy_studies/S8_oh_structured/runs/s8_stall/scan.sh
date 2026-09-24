set -u
# STALL-FINDING SCAN. Cheapest mesh, one geometry, alpha 10 -> 24.
#
# WHY THIS BEFORE THE F/FF POST-STALL MATRIX. That matrix is 4 levels x 2
# geometries x 14 alphas = 112 solves, ~318 h at the attached-flow rate and
# nearer 800 h once separated cases take longer. Three things make it
# unsizeable today, and all three are answered here for ~4 hours on gci_C:
#
#   1. WHERE IS STALL. The CL curve is still dead linear at alpha 8 (departure
#      from a 3-point linear fit: +0.0026 on g83). Linear extrapolation puts
#      CL=1.0 at 16.5 deg on g83, 15.1 on g47, 20.4 on g13 -- a 5 degree spread
#      between geometries, so one fixed alpha list cannot serve them all.
#   2. DOES STEADY RANS CONVERGE UP THERE AT ALL. Massively separated flow is
#      unsteady; a steady solver may stall its residual, or settle on a
#      non-physical steady state.
#   3. DOES THE GATE ACCEPT ANYTHING POST-STALL. It needs 5 orders of residual
#      OR settled forces. If neither happens, those 112 runs produce results
#      nothing downstream is allowed to use.
#
# --time-limit 3600 is 2.7x the ~22 min this mesh normally takes, so a run that
# will not converge is cut off rather than burning the default 6 hours. A run
# that hits the cap is DATA, not a failure: it is the answer to question 2.
#
# Held fixed against the existing alpha sweep: same mesh (runs/s8_v2/g83,
# gci_C, 603,592 cells), same solver settings, same area_ref. Only alpha moves.
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin; V=$R/.venv/bin/python
G=$S/runs/s8_v2/g83/gci_C_volume.cgns
O=$S/runs/s8_stall
log(){ echo "$(date +%H:%M:%S) $*"; }

# wait for the fam2 batch: one measurement at a time, PLAN 0.2
while pgrep -f "mach-aero/bin/python.*solve_s8" > /dev/null 2>&1; do sleep 60; done
log "machine idle -- starting stall scan"

for AL in 10 12 14 16 18 20 22 24; do
  D=$O/gci_C_a$AL
  [ -f "$D/result.json" ] && { log "  a$AL done"; continue; }
  mkdir -p "$D"
  W=0
  while :; do
    A=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    [ "$A" -ge 8388608 ] && break
    [ "$W" -ge 900 ] && { log "  a$AL REFUSING: $(( A / 1048576 )) GiB free"; break; }
    sleep 30; W=$(( W + 30 ))
  done
  [ "$W" -ge 900 ] && continue
  log "  a$AL solving"
  "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$G" --alpha $AL --no-nk \
     --eddy-vis-inf-ratio 0.21 --area-ref 0.39492 --time-limit 3600 \
     --out "$D" --i-have-authorization > "$D/run.log" 2>&1
  if [ -f "$D/result.json" ]; then
    $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CL {f['cl']:8.4f}  CD {1e4*f['cd']:8.2f}  CDp {1e4*f['cdp']:8.2f}  CMy {f['cmy']:8.5f}  \"
      f\"conv={r['converged']}  iters={r['iterations_completed']}  relres={r['relative_residual']:.2e}\")"
  else log "    NO RESULT -- hit the time limit or failed; see $D/run.log"; fi
done

log "=== gating (expect rejections: that is the finding, not a fault)"
$V "$S/convergence_gate.py" --runs $(ls -d $S/runs/s8_v2/g83/gci_C_a[0-9] $O/gci_C_a[0-9]* 2>/dev/null) \
   --out "$O/gate.json" 2>&1 | tail -16
log "=== lift curve"
$V - <<'PYEOF'
import json, os, glob
rows=[]
for p in sorted(glob.glob('/home/mike_kara/aeris/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_v2/g83/gci_C_a*/result.json')
              + glob.glob('/home/mike_kara/aeris/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/runs/s8_stall/gci_C_a*/result.json')):
    d=json.load(open(p)); f={k.split('_')[-1]:v for k,v in d['functions'].items()}
    rows.append((d['alpha_deg'],f['cl'],f['cd']*1e4,f['cmy'],d['converged'],d['iterations_completed'],d['relative_residual']))
rows.sort()
print(f"\n  {'alpha':>6s} {'CL':>9s} {'dCL':>8s} {'CD ct':>9s} {'CMy':>9s} {'conv':>6s} {'iters':>6s} {'rel res':>10s}")
prev=None
for a,cl,cd,cm,cv,it,rr in rows:
    d=f"{cl-prev:+8.4f}" if prev is not None else "       -"
    print(f"  {a:>6.1f} {cl:>9.4f} {d} {cd:>9.2f} {cm:>9.5f} {str(cv):>6s} {it:>6d} {rr:>10.2e}")
    prev=cl
mx=max(rows,key=lambda r:r[1])
print(f"\n  peak CL in the scan: {mx[1]:.4f} at alpha {mx[0]:.1f}"
      + ("  <- CL still rising at the top of the ladder; stall is beyond 24 deg" if mx[0]>=24 else ""))
PYEOF
log "=== stall scan done"
