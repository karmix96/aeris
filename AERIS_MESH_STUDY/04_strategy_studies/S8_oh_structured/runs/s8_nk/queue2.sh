set -u
# THE REAL NK TEST. The first attempt did not test anything.
#
# Arms A and B both came back BIT-IDENTICAL to the ANK-only production runs --
# same forces to every digit, same iteration count (286 / 196 / 190 / 159 /
# 307 / 195). The iteration table says why: all 286 iterations carry
# IterType = ANK. NK never engaged in any arm, including the one with ADflow's
# full preconditioner correctly applied (result.json records NKSubspaceSize 60,
# NKPCILUFill 2).
#
# Cause: NKSwitchTol is 1.0e-6 and the L2 stopping target is also 1e-6. The run
# terminates at its convergence criterion before the NK switch can fire. So
# --no-nk has been a NO-OP on every production run at this tolerance, and the
# "ANK-only" caveat in the reports is true for a different reason than stated.
#
# To actually exercise NK the switch must sit ABOVE the stopping target. This
# hands over at 1e-4 and lets NK drive the last two decades to 1e-6.
#
#   C  NK from 1e-4, project preconditioner (subspace 20, ILU fill 1)
#   D  NK from 1e-4, ADflow default preconditioner (subspace 60, ILU fill 2)
#
# Same mesh, same alphas, same area_ref. Baseline is the ANK-only result.
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
      sleep 5; kill -KILL $PID 2>/dev/null; echo ABORTED_LOW_MEMORY > "$D/VERDICT"; break; fi
    sleep 10; done
  wait $PID 2>/dev/null || true
  log "    peak $(echo $PEAK | awk '{printf "%.1f", $1/1048576}') GiB"; }
run(){ local D=$1 AL=$2; shift 2
  [ -f "$D/result.json" ] && { log "  $(basename $D) done"; return; }
  mkdir -p "$D"
  while [ "$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)" -lt 10485760 ]; do sleep 30; done
  log "  $(basename $D) solving"
  guarded "$D" "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" \
     --grid "$S/runs/s8_v2/g83/gci_C_volume.cgns" --alpha "$AL" --nk-switch-tol 1e-4 \
     --eddy-vis-inf-ratio 0.21 --area-ref 0.39492 --out "$D" --i-have-authorization "$@"
  if [ -f "$D/result.json" ]; then
    NKIT=$(grep -cE "^\s+[0-9]+\s+[0-9]+\s+[0-9]+\s+NK\s" "$D/run.log" 2>/dev/null || echo 0)
    $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v*1e4 for k,v in r['functions'].items()}
print(f\"    CD {f['cd']:9.4f}  CDp {f['cdp']:9.4f}  CDv {f['cdv']:8.4f}  CL {f['cl']:10.4f}  \"
      f\"conv={r['converged']}  iters={r['iterations_completed']}  relres={r['relative_residual']:.2e}  NKiters=$NKIT\")"
  else log "    NO RESULT -- see $D/run.log $( [ -f "$D/VERDICT" ] && cat "$D/VERDICT" )"; fi; }
log "=== arm C: NK from 1e-4, project preconditioner"
for AL in 0 4; do run "$S/runs/s8_nk/g83/nk4_a$AL" $AL; done
log "=== arm D: NK from 1e-4, ADflow default preconditioner"
for AL in 0 4; do run "$S/runs/s8_nk/g83/nk4full_a$AL" $AL --set-option NKSubspaceSize=60 --set-option NKPCILUFill=2; done
log "=== gating"
$V "$S/convergence_gate.py" --runs $(ls -d $S/runs/s8_nk/g83/nk4*_a[0-9] 2>/dev/null) \
   --out "$S/runs/s8_nk/gate_nk4.json" 2>&1 | tail -8
log "=== done"
