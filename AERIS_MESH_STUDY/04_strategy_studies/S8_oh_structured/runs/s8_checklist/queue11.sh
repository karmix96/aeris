set -u
# Behind queue10. The tip cap at the wing's own resolution. The default asks for a
# last spanwise cell of 10 x s0, which is what makes the cap's y+ 3-5 where the wing
# holds under 1. The cap is 0.3 % of the wetted area and it is where the tip vortex
# rolls off, so the question is whether that coarseness costs anything in the forces.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
L=gci_C
D=$O/fine_cap

echo "=== waiting for queue10.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue10.out" 2>/dev/null; do sleep 60; done
sleep 20
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")

echo "=== 1/2 build the mesh with a wall-resolved tip cap $(date -Is)"
$V "$S/build_volume.py" --level $L --index 83 --out "$D" --no-plot3d 2>&1 \
  | grep -oE '"(total_cells|negative_cells_all_blocks|tip_cap_yplus_scale_vs_oml)": [0-9.e+-]+' | tr '\n' ' '; echo
$M/python "$S/write_cgns.py" --blocks "$D/${L}_blocks.npz" > /dev/null 2>&1

echo "=== 2/2 the same three incidences as the standard grid $(date -Is)"
for AL in 0 4 8; do
  d=$D/${L}_a$AL; mkdir -p "$d"; t0=$(date +%s)
  timeout --kill-after=60 5400 \
    "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$D/${L}_volume.cgns" --alpha $AL \
    --no-nk --area-ref "$A83" --out "$d" --i-have-authorization > "$d/run.log" 2>&1
  echo "  a$AL wall=$(( $(date +%s) - t0 )) s"
  $V -c "
import json
new = json.load(open('$d/result.json'))
old = json.load(open('$A/s8_pilot/g83/gci_C_a$AL/result.json'))
f = lambda r: {k.split('_')[-1]: v for k, v in r['functions'].items()}
n, o = f(new), f(old)
print('    ' + '  '.join(f'{k.upper()} {100*(n[k]-o[k])/o[k]:+.2f}%' for k in ('cl','cd','cdp','cdv'))
      + f\"  (converged={new['converged']})\")" 2>/dev/null || echo "    FAILED"
done
echo "=== done $(date -Is)"
