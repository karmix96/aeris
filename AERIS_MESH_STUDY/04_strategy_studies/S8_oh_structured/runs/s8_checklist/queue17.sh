set -u
# EVERYTHING still to run, in one resumable chain. The previous chain died when the WSL
# VM itself restarted at 2026-09-13 23:23, 25 minutes into an SU2 run on six ranks --
# most likely memory. So this one:
#   * skips any run whose result.json already exists, so a restart costs nothing done;
#   * watches available memory and kills a run cleanly before WSL runs out;
#   * stops before the big re-run if an earlier test moved drag by a drag count or more,
#     because then the re-run's configuration is a decision, not a default.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
N=$A/tmr_naca0012
Q=$R/AERIS_MESH_STUDY/05_s6_cfd_qualification
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
SU2=$R/AERIS_MESH_STUDY/tools/su2_8.5.0/bin/SU2_CFD
G83=$A/s8_gci83/gci_C_volume.cgns
BASE=$A/s8_pilot/g83
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")
MIN_FREE_GIB=1.5
FLAG=$O/decision_needed.txt
rm -f "$FLAG"

log() { echo "$(date +%H:%M) $*"; }

# run a command in its own process group; kill it if free memory falls too low
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

# one S8 solve against an existing baseline run; skipped if already done
counts() {  # NEW_DIR BASELINE_DIR LABEL -> prints drag counts and % changes, returns |dCD| in counts
  $V - "$1" "$2" "$3" <<'PY'
import json, sys
new = json.load(open(sys.argv[1] + "/result.json")); old = json.load(open(sys.argv[2] + "/result.json"))
f = lambda r: {k.split("_")[-1]: v for k, v in r["functions"].items()}
n, o = f(new), f(old)
dc = 1e4 * (n["cd"] - o["cd"])
print(f"    {sys.argv[3]}: CD {dc:+.2f} counts  CL {100*(n['cl']-o['cl'])/o['cl']:+.2f}%  "
      f"CDp {100*(n['cdp']-o['cdp'])/o['cdp']:+.2f}%  CDv {100*(n['cdv']-o['cdv'])/o['cdv']:+.2f}%  "
      f"converged={new['converged']}")
open("/tmp/last_counts", "w").write(f"{abs(dc):.3f}")
PY
}
solve() {  # DIR GRID ALPHA LABEL EXTRA...
  local d=$1 grid=$2 al=$3 label=$4; shift 4
  mkdir -p "$d"
  if [ ! -f "$d/result.json" ]; then
    guarded 7200 "$d/run.log" "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$grid" \
      --alpha "$al" --no-nk --area-ref "$A83" "$@" --out "$d" --i-have-authorization
  else log "  $label already done"; fi
  [ -f "$d/result.json" ] && counts "$d" "$BASE/gci_C_a$al" "$label" || echo "    $label FAILED"
}
material() {  # LABEL: if the last change was >= 1 drag count, record it
  local c=$(cat /tmp/last_counts 2>/dev/null || echo 0)
  if awk "BEGIN{exit !($c >= 1.0)}"; then echo "$1 moved CD by $c counts" >> "$FLAG"; fi
}
build() {  # LEVEL DIR
  local L=$1 D=$2
  if [ ! -f "$D/${L}_volume.cgns" ]; then
    $V "$S/build_volume.py" --level "$L" --index 83 --out "$D" --no-plot3d > "$D.build.log" 2>&1 \
      || { log "  build of $L FAILED, see $D.build.log"; return 1; }
    $M/python "$S/write_cgns.py" --blocks "$D/${L}_blocks.npz" > /dev/null 2>&1
  fi
  $V "$S/mesh_guidelines.py" --blocks "$D/${L}_blocks.npz" --summary "$D/${L}_summary.json" | grep "criteria met"
}

log "=== 1/8 tip cap wall-resolved (the new default gci_C) against the old archive"
D=$O/tipcap; mkdir -p "$D"; build gci_C "$D" && for AL in 0 4 8; do
  solve "$D/gci_C_a$AL" "$D/gci_C_volume.cgns" $AL "tip cap a$AL"; material "tip cap a$AL"; done

log "=== 2/8 SU2 on the same mesh, two ranks, memory-guarded"
for AL in 0 4; do
  d=$A/su2_check/a$AL
  $V "$S/su2_config.py" --mesh "$A/su2_check/gci_C.su2" --alpha $AL --area 0.394920 --out "$d" > /dev/null
  if [ ! -f "$d/forces_breakdown.dat" ]; then
    ( cd "$d" && guarded 14400 run.log "$M/mpirun" -np 2 "$SU2" case.cfg )
  fi
  $V - "$d" "$BASE/gci_C_a$AL" <<'PY' 2>/dev/null || echo "    SU2 a$AL no forces; see run.log"
import json, re, sys
from pathlib import Path
t = (Path(sys.argv[1]) / "forces_breakdown.dat").read_text()
g = lambda k: float(re.search(rf"Total {k}:\s+([-\d.eE+]+)", t).group(1))
r = json.load(open(sys.argv[2] + "/result.json")); f = {k.split("_")[-1]: v for k, v in r["functions"].items()}
print(f"    SU2 CL {g('CL'):+.5f} CD {g('CD'):.5f}   ADflow CL {f['cl']:+.5f} CD {f['cd']:.5f}   "
      f"difference {1e4*(g('CD')-f['cd']):+.1f} counts")
PY
done

log "=== 3/8 low-speed preconditioner, wing"
for AL in 0 4 8; do
  solve "$O/trial/precon_a$AL" "$G83" $AL "preconditioner a$AL" --low-speed-preconditioner
  material "preconditioner a$AL"; done

log "=== 4/8 low-speed preconditioner on the case with a known answer"
d=$N/runs/o512_m0.15_precon
if [ ! -f "$d/result.json" ]; then
  mkdir -p "$d"
  guarded 7200 "$d/run.log" "$M/mpirun" -np 6 "$M/python" "$S/naca0012_tmr.py" solve \
    --grid "$N/o512.cgns" --out "$d" --no-nk --l2 1e-8 --n-cycles 300000 \
    --set lowSpeedPreconditioner=true --set ANKSubspaceSize=50 --set ANKPCILUFill=2 \
    --set ANKCoupledSwitchTol=1e-4 --set NKSwitchTol=1e-5 --set NKSubspaceSize=100 \
    --set NKPCILUFill=3 --set NKASMOverlap=2 --set NKJacobianLag=5
fi
$V -c "
import json; c = json.load(open('$d/result.json'))['coefficients']
ref = {'CL':1.09094,'CD':0.01227275,'CDp':0.006067,'CDv':0.0062059}
print('    with preconditioner: ' + '  '.join(f'{k} {100*(c[k]-ref[k])/ref[k]:+.2f}%' for k in ref))
print('    without it         : CL +0.74%  CD +4.40%  CDp +8.59%  CDv +0.31%')" 2>/dev/null || echo "    FAILED"

log "=== 5/8 dissipation coefficient vis4 halved and doubled"
solve "$O/trial/vis4_low_a0"  "$G83" 0 "vis4 halved"  --set-option vis4=0.0078; material "vis4 halved"
solve "$O/trial/vis4_high_a0" "$G83" 0 "vis4 doubled" --set-option vis4=0.0312; material "vis4 doubled"

log "=== 6/8 published gridding guidelines: far field 100 chords, trailing edge 0.1 %"
D=$O/guideline/gci_C_ff100; mkdir -p "$D"; build gci_C_ff100 "$D" && for AL in 0 8; do
  solve "$D/gci_C_ff100_a$AL" "$D/gci_C_ff100_volume.cgns" $AL "far field 100 a$AL"; material "far field 100 a$AL"; done
D=$O/guideline/gci_C_te; mkdir -p "$D"; build gci_C_te "$D" && for AL in 0 4; do
  solve "$D/gci_C_te_a$AL" "$D/gci_C_te_volume.cgns" $AL "trailing edge a$AL"; material "trailing edge a$AL"; done

log "=== 7/8 SA-Edwards with the TMR freestream"
d=$O/trial/edwards_chi3_a0
solve "$d" "$G83" 0 "SA-Edwards chi3" --turbulence-model SA-Edwards --turb-res-scale 10000 \
  --eddy-vis-inf-ratio 0.21

if [ -s "$FLAG" ]; then
  log "=== STOPPING BEFORE THE RE-RUN: these changed drag by a count or more"
  cat "$FLAG"
  log "The re-run's configuration is a decision now. Nothing expensive was started."
  echo "=== done $(date -Is)"
  exit 0
fi

log "=== 8/8 THE RE-RUN: ten wings coarse, five medium, wall-resolved cap, chi 3"
$V "$S/run_campaign.py" pilot --level gci_C --ranks 6 --no-nk --eddy-vis-inf-ratio 0.21 \
  --out-root "$A/s8_v2" > "$O/rerun_gci_C.log" 2>&1
$V "$S/run_campaign.py" pilot --level gci_M --indices 83 29 65 47 13 --ranks 6 --watch-memory \
  --no-nk --eddy-vis-inf-ratio 0.21 --out-root "$A/s8_v2" > "$O/rerun_gci_M.log" 2>&1
$V "$S/collect_dataset.py" --runs "$A/s8_v2" --out "$Q/dataset_v2" 2>&1 | tail -2
$V "$S/audit_runs.py" --rows "$Q/dataset_v2/rows.json" --out "$Q/reports/s8_archive_audit_v2.json" | tail -4
echo "=== done $(date -Is)"
