set -u
# WHY DOES NK FREEZE?  LinRes 1.000 means the Krylov solve reduced the linear
# residual by a factor of 1.0 -- zero progress. That is a PRECONDITIONER
# failure, not a nonlinear one, so the knobs that matter are ILU fill, subspace
# size, ASM overlap and whether viscous terms are in the PC.
#
# This project runs all three of ADflow's NK controls leaner AND later than
# stock:   NKSwitchTol 1e-6 (stock 1e-5), NKSubspaceSize 20 (60), NKPCILUFill 1 (2).
#
# Diagnostic on gci_C, cheap and disposable. Switch forced to 1e-4 so NK really
# engages, 35 min cap each, and the summary reports the LinRes DISTRIBUTION --
# which tells us whether a preconditioner helped even on a run that did not
# finish. Whatever wins here gets applied to gci_M, which is the mesh asked for
# and the one where the freeze was first recorded.
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin; V=$R/.venv/bin/python
log(){ echo "$(date +%H:%M:%S) $*"; }
try(){ local TAG=$1; shift
  local D=$S/runs/s8_nk/diag/$TAG
  [ -f "$D/summary.txt" ] && { log "  $TAG done"; cat "$D/summary.txt"; return; }
  mkdir -p "$D"
  while [ "$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)" -lt 9437184 ]; do sleep 30; done
  log "  $TAG"
  "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" \
     --grid "$S/runs/s8_v2/g83/gci_C_volume.cgns" --alpha 0 --nk-switch-tol 1e-4 \
     --eddy-vis-inf-ratio 0.21 --area-ref 0.39492 --time-limit 2100 \
     --out "$D" --i-have-authorization "$@" > "$D/run.log" 2>&1 &
  local PID=$! PEAK=0
  while kill -0 $PID 2>/dev/null; do
    local AV=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    local U=$(( $(awk '/^MemTotal:/{print $2}' /proc/meminfo) - AV ))
    [ "$U" -gt "$PEAK" ] && PEAK=$U
    [ "$AV" -lt 734003 ] && { log "    ABORT low mem"; kill -9 $PID 2>/dev/null; break; }
    sleep 10; done
  wait $PID 2>/dev/null || true
  $V - "$D" "$PEAK" <<'PYEOF' | tee "$D/summary.txt"
import sys, re, json, os
from pathlib import Path
D=Path(sys.argv[1]); peak=int(sys.argv[2])/1048576
rows=[l.split() for l in (D/'run.log').read_text(errors='ignore').splitlines()
      if re.match(r'^\s+\d+\s+\d+\s+\d+\s+(ANK|NK|DADI)\s', l)]
nk=[r for r in rows if r[3]=='NK']
lin=[]
for r in nk:
    try: lin.append(float(r[6]))
    except (ValueError, IndexError): pass
rho=[]
for r in rows:
    try: rho.append(float(r[7]))
    except (ValueError, IndexError): pass
res = json.load(open(D/'result.json')) if (D/'result.json').exists() else None
lin_s = (f"min {min(lin):.3f}  median {sorted(lin)[len(lin)//2]:.3f}  "
         f"frac<0.9 {sum(1 for x in lin if x<0.9)/len(lin):.2f}") if lin else "no NK iterations"
print(f"    iters {len(rows):>4d} ({len(nk)} NK)  peak {peak:.1f} GiB  rho {rho[0]:.2e} -> {rho[-1]:.2e}"
      if rho else f"    no iterations parsed")
print(f"    LinRes: {lin_s}")
if res:
    f={k.split('_')[-1]:v*1e4 for k,v in res['functions'].items()}
    print(f"    CONVERGED  CD {f['cd']:.4f}  CDp {f['cdp']:.4f}  CDv {f['cdv']:.4f}  CL {f['cl']:.4f}  relres {res['relative_residual']:.2e}")
else:
    print(f"    did not converge in the cap")
PYEOF
}
log "=== NK preconditioner diagnostic, gci_C alpha 0, switch 1e-4"
try pc_lean                                                              # subspace 20, fill 1 (project)
try pc_stock  --set-option NKSubspaceSize=60 --set-option NKPCILUFill=2  # ADflow default
try pc_fill3  --set-option NKSubspaceSize=60 --set-option NKPCILUFill=3 --set-option NKASMOverlap=2
try pc_viscpc --set-option NKSubspaceSize=60 --set-option NKPCILUFill=2 --set-option NKViscPC=True
log "=== diagnostic done"
