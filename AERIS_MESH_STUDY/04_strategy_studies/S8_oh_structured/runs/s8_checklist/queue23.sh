set -u
# Continue the three stage-0 cases that queue21's five-hour guard stopped, and give them the
# output they were missing.
#
# Two things went wrong with that first group, both fixed here:
#   1. all three hit the 18000 s cap while still converging -- the incompressible flat plate was
#      within 0.6 % of NASA's drag, the compressible within 1.4 %, the NACA 0012 still 6 % out.
#      Each wrote a restart file, so they continue rather than start again.
#   2. their surface files carried only solution variables: SU2's SURFACE_CSV does not write skin
#      friction, y+ or the pressure coefficient, which is exactly what the flat-plate criterion
#      (cf at x = 0.97) needs. su2_validation.py now also asks for SURFACE_TECPLOT_ASCII.
#
# Runs after queue22, two at a time, with a longer cap.
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

continue_group() {  # CASE...
  local pids=() c d
  for c in "$@"; do
    d=$A/su2_validation/$c
    if finished "$d/run_cont.log"; then log "  $c already continued to convergence"; continue; fi
    [ -f "$d/restart.dat" ] || { log "  $c has no restart file; skipping"; continue; }
    $V "$S/su2_validation.py" config --case "$c" --restart > /dev/null || { log "  $c config FAILED"; continue; }
    ( cd "$d" && guarded 28800 run_cont.log "$M/mpirun" -np 3 "$SU2" case.cfg ) &
    pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p"; done
  for c in "$@"; do
    d=$A/su2_validation/$c
    # the continuation writes history_cont.csv; keep both, and let compare read the newer one
    [ -f "$d/history_cont.csv" ] && cp -f "$d/history_cont.csv" "$d/history.csv"
    [ -f "$d/run_cont.log" ] && cp -f "$d/run_cont.log" "$d/run.log"
    finished "$d/run_cont.log" || log "  $c still short of its convergence criterion"
    $V "$S/su2_validation.py" compare --case "$c" 2>&1 | tail -2
  done
}

until grep -q "^=== done" "$O/queue22.out" 2>/dev/null; do sleep 60; done
log "queue22 finished; continuing the capped stage-0 cases with skin-friction output"

continue_group fp_comp_545 naca0012_inc_897
continue_group fp_inc_545
$V "$S/su2_validation.py" compare --all 2>&1 | tail -12
echo "=== done $(date -Is)"
