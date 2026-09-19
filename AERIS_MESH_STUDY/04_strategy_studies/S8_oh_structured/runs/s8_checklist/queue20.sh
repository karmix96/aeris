set -u
# The settings tests agreed on 2026-09-15 after queue17. On the coarse mesh drag moved
# -20.6 / +35.1 counts with vis4 halved / doubled, and about -10.5 counts with the
# trailing edge at 0.1 % of chord -- far more than the tip cap. These decide the settings
# the re-run uses; the re-run itself waits for that decision and is NOT started here.
# Resumable (a run with a result.json is never repeated) and memory-guarded. Every
# comparison is against a baseline with the SAME tip cap.
#
# Rewritten at 20:50 the same day. The first matrix-dissipation run stalled under ANK:
# CFL 42-88 against the baseline's 1e5, residual flat from iteration 175 to 239
# (settings/matrix_C_a0/run.log). So matrix dissipation gets ONE attempt with NK allowed,
# and its alpha 4 and gci_M runs only if that converges. A setting that cannot converge
# on the wing is not a candidate for sixty production solves, whatever it does to drag.
# And the SU2 variants, which need hours rather than minutes, run last, side by side.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
N4=$A/tmr_naca4412
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
SU2=$R/AERIS_MESH_STUDY/tools/su2_8.5.0/bin/SU2_CFD
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
      f"CL {100*(n['cl']-o['cl'])/abs(o['cl']):+.2f} %  converged={new['converged']}  "
      f"residual {new.get('relative_residual')}")
PY
}

solve() {  # DIR GRID ALPHA BASELINE_DIR LABEL TIMEOUT NK(yes|no) EXTRA...
  local d=$1 grid=$2 al=$3 base=$4 label=$5 limit=$6 nk=$7; shift 7
  local flags=(--no-nk)
  [ "$nk" = yes ] && flags=()
  mkdir -p "$d"
  if [ ! -f "$d/result.json" ]; then
    guarded "$limit" "$d/run.log" "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$grid" \
      --alpha "$al" "${flags[@]}" --area-ref "$A83" "$@" --out "$d" --i-have-authorization
  else log "  $label already done"; fi
  if [ -f "$d/result.json" ]; then delta "$d" "$base" "$label"; else echo "    $label FAILED, see $d/run.log"; fi
}

converged() { $V -c "import json,sys; sys.exit(0 if json.load(open('$1/result.json'))['converged'] else 1)" 2>/dev/null; }

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

log "=== 1/7 matrix dissipation on gci_C alpha 0, NK allowed (it stalled under ANK alone)"
solve "$O/settings/matrix_C_a0_nk" "$CAP_C/gci_C_volume.cgns" 0 "$CAP_C/gci_C_a0" \
  "matrix dissipation gci_C a0, ANK then NK" 5400 yes --set-option "$MATRIX"

log "=== 2/7 does the dissipation effect shrink on the medium mesh? vis4 halved, gci_M alpha 0 (old tip cap)"
log "    for scale, on gci_C: vis4 halved -20.6 counts"
solve "$O/settings/vis4_low_M_a0" "$OLD_M/gci_M_volume.cgns" 0 "$OLD_M/gci_M_a0" "vis4 halved gci_M a0" \
  7200 no --set-option vis4=0.0078

log "=== 3/7 trailing edge at 0.1 % of chord on the medium mesh (old tip cap)"
log "    for scale, on gci_C: about -10.5 counts once the tip cap is taken out"
D=$O/settings/gci_M_te
if build gci_M_te "$D" --allow-coarse-tip-cap; then
  solve "$D/gci_M_te_a0" "$D/gci_M_te_volume.cgns" 0 "$OLD_M/gci_M_a0" "trailing edge 0.1 % gci_M a0" 7200 no
fi

log "=== 4/7 far field 100 chords with gci_C's own 65 layers (wall-resolved tip cap)"
log "    the queue17 version also went to 95 layers, so its +4.2 counts mixed two changes"
D=$O/settings/gci_C_ff100_65
if build gci_C "$D" --farfield-chords 100; then
  for AL in 0 8; do
    solve "$D/gci_C_a$AL" "$D/gci_C_volume.cgns" $AL "$CAP_C/gci_C_a$AL" "far field 100, 65 layers, a$AL" 7200 no
  done
fi

log "=== 5/7 matrix dissipation at alpha 4 and on gci_M -- only if alpha 0 converged"
if [ -f "$O/settings/matrix_C_a0_nk/result.json" ] && converged "$O/settings/matrix_C_a0_nk"; then
  solve "$O/settings/matrix_C_a4_nk" "$CAP_C/gci_C_volume.cgns" 4 "$CAP_C/gci_C_a4" \
    "matrix dissipation gci_C a4" 5400 yes --set-option "$MATRIX"
  solve "$O/settings/matrix_M_a0_nk" "$OLD_M/gci_M_volume.cgns" 0 "$OLD_M/gci_M_a0" \
    "matrix dissipation gci_M a0" 7200 yes --set-option "$MATRIX"
else
  log "    skipped: matrix dissipation did not converge at alpha 0, so it is not a candidate setting"
fi

log "=== 6/7 NACA 4412 o1024 again: NK stalled at line-search step 0.01, so a stronger NK"
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

log "=== 7/7 SU2 on NACA 0012: numerics variants to convergence, three side by side on two ranks each"
cd "$S"
pids=()
for v in wls wls_muscl_turb roe_wls; do
  vd=$A/su2_naca0012/$v
  if ! grep -q "Exit Success" "$vd/run.log" 2>/dev/null; then
    $V su2_naca0012.py config --variant $v > /dev/null
    rm -f "$vd/forces_breakdown.dat" "$vd/history.csv"
    ( cd "$vd" && guarded 21600 run.log "$M/mpirun" -np 2 "$SU2" case.cfg ) &
    pids+=($!)
  fi
done
for p in "${pids[@]}"; do wait "$p"; done
for v in wls wls_muscl_turb roe_wls; do $V su2_naca0012.py compare --variant $v > /dev/null 2>&1 || echo "    SU2 $v: no forces"; done
$V su2_naca0012.py compare --variant wing 2>&1 | tail -7
echo "=== done $(date -Is)"
