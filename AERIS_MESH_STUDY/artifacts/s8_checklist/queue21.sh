set -u
# SU2 validation, stage 0 (agreed 2026-09-15): SU2's own validated tutorial cases, their
# configuration files unchanged except for output, judged against NASA TMR answers and, for
# the transition cases, experiment. Runs after queue20. Three cases at a time on two ranks
# each; resumable (a case whose log says Exit Success is never repeated); memory-guarded.
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

finished() {  # LOGFILE -- SU2 prints "Exit Success" even after a signal (roe_wls, 15 Sept),
              # so a skip test built on that string skips runs that were killed, not finished
  [ -f "$1" ] && grep -q "All convergence criteria satisfied" "$1" && ! grep -q "Interrupt signal" "$1"
}

run_group() {  # CASE...  (side by side, two ranks each)
  local pids=() c d
  for c in "$@"; do
    d=$A/su2_validation/$c
    if finished "$d/run.log"; then log "  $c already done"; continue; fi
    $V "$S/su2_validation.py" config --case "$c" > /dev/null || { log "  $c config FAILED"; continue; }
    ( cd "$d" && guarded 18000 run.log "$M/mpirun" -np 2 "$SU2" case.cfg ) &
    pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p"; done
  for c in "$@"; do
    finished "$A/su2_validation/$c/run.log" || log "  $c did NOT finish cleanly (killed, timed out, or still short of its convergence criteria)"
    $V "$S/su2_validation.py" compare --case "$c" 2>&1 | tail -2
  done
}

until grep -q "^=== done" "$O/queue20.out" 2>/dev/null; do sleep 60; done
log "queue20 finished; SU2 validation stage 0 starting"

log "=== 1/4 verification against NASA TMR: flat plate (compressible, incompressible) and NACA 0012"
run_group fp_comp_545 fp_inc_545 naca0012_inc_897
log "=== 2/4 coarse flat plate; transition on flat plates (B-C, Langtry-Menter T3A)"
run_group fp_comp_137 fp_bc t3a
log "=== 3/4 T3A- and Eppler 387 with Langtry-Menter (SA and SST)"
run_group t3a_minus e387_sa_lm e387_sst_lm
log "=== 4/4 natural-laminar-flow airfoil, Langtry-Menter"
run_group nlf_sst_lm
$V "$S/su2_validation.py" compare --all 2>&1 | tail -12
echo "=== done $(date -Is)"
