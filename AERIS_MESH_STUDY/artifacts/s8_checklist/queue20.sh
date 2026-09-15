set -u
# The settings tests agreed on 2026-09-15 after queue17. On the coarse mesh drag moved
# -20.6 / +35.1 counts with vis4 halved / doubled, and about -10.5 counts with the
# trailing edge at 0.1 % of chord -- far more than the tip cap. These decide the settings
# the re-run uses; the re-run itself waits for that decision and is NOT started here.
# Runs after queue18. Resumable (a run with a result.json is never repeated) and
# memory-guarded. Every comparison is against a baseline with the SAME tip cap.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
N4=$A/tmr_naca4412
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")
MIN_FREE_GIB=1.5
CAP_C=$O/tipcap        # gci_C, wall-resolved tip cap: the mesh and its alpha 0 / 4 / 8 runs
OLD_M=$A/s8_pilot/g83  # gci_M, old tip cap: the mesh and its alpha 0 run
MATRIX="discretization=central plus matrix dissipation"

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

delta() {  # NEW_DIR BASELINE_DIR LABEL
  $V - "$1" "$2" "$3" <<'PY'
import json, sys
new, old = (json.load(open(p + "/result.json")) for p in sys.argv[1:3])
f = lambda r: {k.split("_")[-1]: v for k, v in r["functions"].items()}
n, o = f(new), f(old)
print(f"    {sys.argv[3]}: CD {1e4*(n['cd']-o['cd']):+.2f} counts ({1e4*o['cd']:.1f} -> {1e4*n['cd']:.1f})  "
      f"CDp {1e4*(n['cdp']-o['cdp']):+.2f}  CDv {1e4*(n['cdv']-o['cdv']):+.2f}  "
      f"CL {100*(n['cl']-o['cl'])/abs(o['cl']):+.2f} %  converged={new['converged']}")
PY
}

solve() {  # DIR GRID ALPHA BASELINE_DIR LABEL EXTRA...
  local d=$1 grid=$2 al=$3 base=$4 label=$5; shift 5
  mkdir -p "$d"
  if [ ! -f "$d/result.json" ]; then
    guarded 7200 "$d/run.log" "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$grid" \
      --alpha "$al" --no-nk --area-ref "$A83" "$@" --out "$d" --i-have-authorization
  else log "  $label already done"; fi
  if [ -f "$d/result.json" ]; then delta "$d" "$base" "$label"; else echo "    $label FAILED, see $d/run.log"; fi
}

build() {  # LEVEL DIR EXTRA_BUILD_FLAGS...
  local L=$1 D=$2; shift 2
  mkdir -p "$D"
  if [ ! -f "$D/${L}_volume.cgns" ]; then
    $V "$S/build_volume.py" --level "$L" --index 83 --out "$D" --no-plot3d "$@" > "$D.build.log" 2>&1 \
      && $M/python "$S/write_cgns.py" --blocks "$D/${L}_blocks.npz" > /dev/null 2>&1 \
      || { log "  build of $L FAILED, see $D.build.log"; return 1; }
  fi
  $V "$S/mesh_guidelines.py" --blocks "$D/${L}_blocks.npz" --summary "$D/${L}_summary.json" 2>/dev/null \
    | grep -E "growth ratio|trailing-edge|far field|criteria met"
}

until grep -q "^=== done" "$O/queue18.out" 2>/dev/null; do sleep 60; done
log "queue18 finished; starting"

log "=== 1/5 matrix dissipation on gci_C (wall-resolved tip cap)"
for AL in 0 4; do
  solve "$O/settings/matrix_C_a$AL" "$CAP_C/gci_C_volume.cgns" $AL "$CAP_C/gci_C_a$AL" \
    "matrix dissipation gci_C a$AL" --set-option "$MATRIX"
done

log "=== 2/5 does the dissipation effect shrink on the medium mesh? gci_M alpha 0 (old tip cap)"
log "    for scale, on gci_C: vis4 halved -20.6 counts"
solve "$O/settings/vis4_low_M_a0" "$OLD_M/gci_M_volume.cgns" 0 "$OLD_M/gci_M_a0" "vis4 halved gci_M a0" \
  --set-option vis4=0.0078
solve "$O/settings/matrix_M_a0" "$OLD_M/gci_M_volume.cgns" 0 "$OLD_M/gci_M_a0" "matrix dissipation gci_M a0" \
  --set-option "$MATRIX"

log "=== 3/5 trailing edge at 0.1 % of chord on the medium mesh (old tip cap)"
log "    for scale, on gci_C: about -10.5 counts once the tip cap is taken out"
D=$O/settings/gci_M_te
if build gci_M_te "$D" --allow-coarse-tip-cap; then
  solve "$D/gci_M_te_a0" "$D/gci_M_te_volume.cgns" 0 "$OLD_M/gci_M_a0" "trailing edge 0.1 % gci_M a0"
fi

log "=== 4/5 far field 100 chords with gci_C's own 65 layers (wall-resolved tip cap)"
log "    the queue17 version also went to 95 layers, so its +4.2 counts mixed two changes"
D=$O/settings/gci_C_ff100_65
if build gci_C "$D" --farfield-chords 100; then
  for AL in 0 8; do
    solve "$D/gci_C_a$AL" "$D/gci_C_volume.cgns" $AL "$CAP_C/gci_C_a$AL" "far field 100, 65 layers, a$AL"
  done
fi

log "=== 5/5 NACA 4412 o1024 again: NK stalled at line-search step 0.01, so a stronger NK"
d=$N4/runs/o1024
if [ -f "$d/result.json" ] && ! $V -c "import json,sys; sys.exit(0 if json.load(open('$d/result.json'))['relative_residual'] <= 1e-6 else 1)"; then
  mv "$d" "$N4/runs/o1024_stalled_nk"
  log "  the stalled run is kept as runs/o1024_stalled_nk"
fi
if [ ! -f "$d/result.json" ]; then
  mkdir -p "$d"
  ( cd "$S" && guarded 21600 "$d/run.log" "$M/mpirun" -np 6 "$M/python" naca4412_tmr.py solve \
      --grid "$N4/o1024.cgns" --out "$d" --l2 1e-8 --n-cycles 300000 --time-limit 19800 \
      --set ANKSubspaceSize=50 --set ANKPCILUFill=2 --set ANKCoupledSwitchTol=1e-4 \
      --set NKSwitchTol=1e-5 --set NKADPC=true --set NKOuterPreconIts=3 --set NKInnerPreconIts=2 \
      --set NKSubspaceSize=150 --set NKPCILUFill=3 --set NKASMOverlap=2 --set NKJacobianLag=3 )
fi
( cd "$S" && $V naca4412_tmr.py compare 2>&1 | grep -E "^ *(o256|o512|o1024|CFL3D|FUN3D|CL|CD|CDp|CDv):|separation|yplus|no converged" )
echo "=== done $(date -Is)"
