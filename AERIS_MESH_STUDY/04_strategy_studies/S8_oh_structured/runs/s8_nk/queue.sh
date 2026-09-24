set -u
# DOES THE ANSWER DEPEND ON THE SOLVER PATH?
#
# The whole production campaign runs ANK-only (--no-nk), which is NOT ADflow's
# governed configuration. It was chosen because on gci_M (1,111,152 cells) ANK
# reached 3.3e-05 by iteration 300, NK took over at 302, the residual went UP to
# 2.8e-04 and froze for 450 iterations with Step 0.01 and LinRes 1.000 -- the
# Krylov solve achieving nothing -- while the forces sat still to THIRTEEN
# significant figures.
#
# Two things were never tested, and both matter:
#
#   A. Do ANK-only and ANK+NK reach the SAME forces? If the L2 1e-6 stopping
#      rule is tight enough, the solution must not depend on how it was reached.
#      Every drag number this project has ever quoted assumes that and has never
#      checked it. This is iterative-convergence verification and the study has
#      none.
#
#   B. Was the freeze the PRECONDITIONER or NK itself? The code says "the likely
#      cause is the preconditioner" -- this project runs NKSubspaceSize 20 and
#      NKPCILUFill 1 against ADflow's defaults of 60 and 2, chosen because gci_M
#      peaks at 12.7 GiB against 12.8 available. On gci_C (603,592 cells) there
#      IS room to restore the defaults, so the hypothesis is testable here and
#      was never tested.
#
# Arms, all on gci_C, same mesh, same alphas, same area_ref as production:
#   A  NK on, project-governed lean preconditioner  (just drop --no-nk)
#   B  NK on, ADflow default preconditioner         (subspace 60, ILU fill 2)
#   baseline = the existing ANK-only production results, already on disk
#
# Guarded: aborts any run if MemAvailable falls below 0.7 GiB.
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin; V=$R/.venv/bin/python
log(){ echo "$(date +%H:%M:%S) $*"; }
guarded(){ local D=$1; shift
  "$@" > "$D/run.log" 2>&1 &
  local PID=$! PEAK=0
  while kill -0 $PID 2>/dev/null; do
    local AV=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    local U=$(( $(awk '/^MemTotal:/{print $2}' /proc/meminfo) - AV ))
    [ "$U" -gt "$PEAK" ] && PEAK=$U
    if [ "$AV" -lt 734003 ]; then
      log "    ABORTING: $(( AV / 1024 )) MiB left"; kill -TERM $PID 2>/dev/null
      sleep 5; kill -KILL $PID 2>/dev/null; echo ABORTED_LOW_MEMORY > "$D/VERDICT"; break
    fi
    sleep 10
  done
  wait $PID 2>/dev/null || true
  log "    peak $(echo $PEAK | awk '{printf "%.1f", $1/1048576}') GiB"
}
run(){ local D=$1 G=$2 AL=$3 AR=$4; shift 4
  [ -f "$D/result.json" ] && { log "  $(basename $D) done"; return; }
  mkdir -p "$D"
  while [ "$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)" -lt 10485760 ]; do sleep 30; done
  log "  $(basename $D) solving"
  guarded "$D" "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$G" --alpha "$AL" \
     --eddy-vis-inf-ratio 0.21 --area-ref "$AR" --out "$D" --i-have-authorization "$@"
  if [ -f "$D/result.json" ]; then
    $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v*1e4 for k,v in r['functions'].items()}
print(f\"    CD {f['cd']:9.4f}  CDp {f['cdp']:9.4f}  CDv {f['cdv']:8.4f}  CL {f['cl']:10.4f}  \"
      f\"conv={r['converged']}  iters={r['iterations_completed']}  relres={r['relative_residual']:.2e}\")"
  else log "    NO RESULT -- see $D/run.log $( [ -f "$D/VERDICT" ] && cat "$D/VERDICT" )"; fi
}
log "=== arm A: NK on, project preconditioner (subspace 20, ILU fill 1)"
for GX in 83:0.39492 47:0.29775 13:0.5162; do
  IX=${GX%%:*}; AR=${GX##*:}
  for AL in 0 4; do
    run "$S/runs/s8_nk/g$IX/nk_a$AL" "$S/runs/s8_v2/g$IX/gci_C_volume.cgns" $AL $AR
  done
done
log "=== arm B: NK on, ADflow default preconditioner (subspace 60, ILU fill 2)"
for AL in 0 4; do
  run "$S/runs/s8_nk/g83/nkfull_a$AL" "$S/runs/s8_v2/g83/gci_C_volume.cgns" $AL 0.39492 \
      --set-option NKSubspaceSize=60 --set-option NKPCILUFill=2
done
log "=== gating"
$V "$S/convergence_gate.py" --runs $(ls -d $S/runs/s8_nk/g*/*_a[0-9] 2>/dev/null) \
   --out "$S/runs/s8_nk/gate.json" 2>&1 | tail -12
log "=== nk study done"
