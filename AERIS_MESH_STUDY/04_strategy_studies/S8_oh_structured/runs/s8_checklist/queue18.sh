set -u
# After queue17: the one validation case in AERIS's own regime, and the wall-normal
# direction's third level. Waits for queue17's final line. Resumable and
# memory-guarded like queue17: a run with a result.json is never repeated.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
N4=$A/tmr_naca4412
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")
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

until grep -q "^=== done" "$O/queue17.out" 2>/dev/null; do sleep 60; done
log "queue17 finished; starting"

log "=== 1/2 NACA 4412, TMR 2DN44: M 0.09, Re 1.52e6, alpha 13.87, trailing-edge separation"
cd "$S"
for L in o256 o512 o1024; do
  d=$N4/runs/$L
  if [ ! -f "$d/result.json" ]; then
    mkdir -p "$d"
    # ANK alone stalls on the NACA 0012 case; these are the settings that converged it
    guarded 14400 "$d/run.log" "$M/mpirun" -np 6 "$M/python" naca4412_tmr.py solve \
      --grid "$N4/$L.cgns" --out "$d" --l2 1e-8 --n-cycles 300000 --time-limit 12600 \
      --set ANKSubspaceSize=50 --set ANKPCILUFill=2 --set ANKCoupledSwitchTol=1e-4 \
      --set NKSwitchTol=1e-5 --set NKSubspaceSize=100 --set NKPCILUFill=3 \
      --set NKASMOverlap=2 --set NKJacobianLag=5
  else log "  $L already done"; fi
  $V -c "
import json; r = json.load(open('$d/result.json')); c = r['coefficients']
print('    $L', '  '.join(f'{k} {v:.5f}' for k, v in c.items()), '  residual', r['relative_residual'])" \
    2>/dev/null || echo "    $L FAILED, see $d/run.log"
done
$V naca4412_tmr.py compare 2>&1 | tail -25

log "=== 2/2 wall-normal third level: 109 layers, s0 at gci_F's, gci_C's chord and span, old tip cap"
L=gci_C_normal_s0_2; D=$O/dir_normal_s0_2; mkdir -p "$D"
if [ ! -f "$D/${L}_volume.cgns" ]; then
  $V "$S/build_volume.py" --level $L --index 83 --out "$D" --no-plot3d --allow-coarse-tip-cap \
    > "$D.build.log" 2>&1 && $M/python "$S/write_cgns.py" --blocks "$D/${L}_blocks.npz" > /dev/null 2>&1 \
    || log "  build FAILED, see $D.build.log"
fi
for AL in 0 4; do
  d=$D/${L}_a$AL
  if [ -f "$D/${L}_volume.cgns" ] && [ ! -f "$d/result.json" ]; then
    mkdir -p "$d"
    guarded 7200 "$d/run.log" "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$D/${L}_volume.cgns" \
      --alpha $AL --no-nk --area-ref "$A83" --out "$d" --i-have-authorization
  fi
done
$V - "$A" <<'PY'
import json, math, sys
A = sys.argv[1]
family = {"gci_C, 65 layers": "s8_pilot/g83/gci_C_a{}",
          "84 layers, s0/1.3": "s8_checklist/dir_normal_s0/gci_C_normal_s0_a{}",
          "109 layers, s0/1.69": "s8_checklist/dir_normal_s0_2/gci_C_normal_s0_2_a{}"}
for al in (0, 4):
    cd = []
    for label, path in family.items():
        try:
            r = json.load(open(f"{A}/{path.format(al)}/result.json"))
        except OSError:
            print(f"    a{al} {label}: missing"); continue
        f = {k.split("_")[-1]: v for k, v in r["functions"].items()}
        cd.append(f["cd"])
        print(f"    a{al} {label:<22} CD {1e4*f['cd']:7.2f}  CDp {1e4*f['cdp']:7.2f}  "
              f"CDv {1e4*f['cdv']:6.2f}  converged={r['converged']}")
    if len(cd) == 3:
        coarse_step, fine_step = cd[1] - cd[0], cd[2] - cd[1]
        if fine_step and coarse_step / fine_step > 0:
            p = math.log(abs(coarse_step / fine_step)) / math.log(1.3)
            extrapolated = cd[2] + fine_step / (1.3 ** p - 1)
            print(f"    a{al} wall-normal direction: order {p:.2f}, extrapolated CD "
                  f"{1e4*extrapolated:.2f}; gci_C is {1e4*(cd[0]-extrapolated):+.2f} counts from it")
        else:
            print(f"    a{al} wall-normal direction NOT monotone: {1e4*coarse_step:+.2f} then "
                  f"{1e4*fine_step:+.2f} counts")
PY
echo "=== done $(date -Is)"
