set -u
# After SU2 validation stage 0 (queue21): the Roe variant again, this time limited.
#
# Why. On ADflow's o512 grid at alpha 10, `roe_wls` -- Roe with MUSCL and NO slope limiter --
# never converged: over its last 3,000 iterations drag swung between 49 and 150 counts against
# the three-code answer of 122.7, with the residual wandering between -2.4 and -6.1. That is a
# limit cycle, and the single mid-run write that read -0.52 % of the TMR answer was one point
# of it, not a result. SU2's own airfoil tutorials (E387, NLF) pair Roe with the Venkatakrishnan
# limiter; only the flat-plate tutorial, where the flow is benign, leaves it off.
#
# Runs alone, after stage 0, so it is not fighting stage 0 for cores.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
SU2=$R/AERIS_MESH_STUDY/tools/su2_8.5.0/bin/SU2_CFD
MIN_FREE_GIB=1.5

log() { echo "$(date +%H:%M) $*"; }

guarded() {  # TIMEOUT_S LOGFILE CMD...
  local limit=$1 logf=$2; shift 2
  setsid "$@" > "$logf" 2>&1 &
  local pid=$! t0=$(date +%s)
  while kill -0 "$pid" 2>/dev/null; do
    sleep 10
    local free_kb=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    if [ "$free_kb" -lt $((${MIN_FREE_GIB%.*} * 1024 * 1024 + 512 * 1024)) ]; then
      echo "MEMORY GUARD: ${free_kb} kB free, killing" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "  killed by the memory guard"; return 99
    fi
    if [ $(( $(date +%s) - t0 )) -gt "$limit" ]; then
      echo "TIME LIMIT ${limit}s, killing" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "  killed at the time limit"; return 98
    fi
  done
  wait "$pid"
}

finished() {  # SU2 prints "Exit Success" after a signal too, so ask for the real thing
  [ -f "$1" ] && grep -q "All convergence criteria satisfied" "$1" && ! grep -q "Interrupt signal" "$1"
}

until grep -q "^=== done" "$O/queue21.out" 2>/dev/null; do sleep 60; done
log "stage 0 finished; the limited Roe variant on our own o512 grid"

d=$A/su2_naca0012/roe_wls_venk
if finished "$d/run.log"; then
  log "  roe_wls_venk already done"
else
  $V "$S/su2_naca0012.py" config --variant roe_wls_venk > /dev/null
  rm -f "$d/forces_breakdown.dat" "$d/history.csv"
  ( cd "$d" && guarded 21600 run.log "$M/mpirun" -np 4 "$SU2" case.cfg )
  finished "$d/run.log" || log "  roe_wls_venk did NOT converge either"
fi
$V "$S/su2_naca0012.py" compare --variant roe_wls_venk 2>&1 | tail -9
echo "=== done $(date -Is)"
