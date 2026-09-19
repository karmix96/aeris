set -u
# Behind queue14, ahead of the re-run. The last two settings the audit turned up that
# nobody ever chose, and the one incidence where they should matter most.
#   vis4: the fourth-difference dissipation coefficient of a central scheme. It IS the
#   scheme's drag error knob, and ours is ADflow's default, 1/64.
#   the low-speed preconditioner at 8 degrees, where lift -- and so the error a
#   sound-speed-scaled dissipation makes -- is largest.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
G83=$A/s8_gci83/gci_C_volume.cgns
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")

echo "=== waiting for queue14.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue14.out" 2>/dev/null; do sleep 60; done
sleep 20

run() {  # NAME DIR ALPHA EXTRA...
  local name=$1 d=$2 al=$3; shift 3; mkdir -p "$d"; local t0=$(date +%s)
  timeout --kill-after=60 5400 "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" \
    --grid "$G83" --alpha "$al" --no-nk --area-ref "$A83" "$@" \
    --out "$d" --i-have-authorization > "$d/run.log" 2>&1
  echo "  $name wall=$(( $(date +%s) - t0 )) s"
  $V -c "
import json
new = json.load(open('$d/result.json'))
old = json.load(open('$A/s8_pilot/g83/gci_C_a$al/result.json'))
f = lambda r: {k.split('_')[-1]: v for k, v in r['functions'].items()}
n, o = f(new), f(old)
print('    ' + '  '.join(f'{k.upper()} {100*(n[k]-o[k])/o[k]:+.2f}%' for k in ('cl','cd','cdp','cdv'))
      + f\"  converged={new['converged']}\")" 2>/dev/null || echo "    FAILED"
}

echo "=== 1/2 the dissipation coefficient, halved and doubled $(date -Is)"
run "vis4 halved"  "$O/trial/vis4_low_a0"  0 --set-option vis4=0.0078
run "vis4 doubled" "$O/trial/vis4_high_a0" 0 --set-option vis4=0.0312
echo "=== 2/2 the low-speed preconditioner at 8 degrees $(date -Is)"
run "precon a8" "$O/trial/precon_a8" 8 --low-speed-preconditioner
echo "=== done $(date -Is)"
