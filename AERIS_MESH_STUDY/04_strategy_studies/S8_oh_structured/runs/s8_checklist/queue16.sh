set -u
# Behind queue15, ahead of the re-run. The published gridding guidelines (AIAA Drag
# Prediction Workshop) that this family does not meet, measured rather than argued:
#   far field 40 root chords against the recommended ~100
#   trailing-edge spacing 0.40 % of local chord against the recommended ~0.1 %
# One drag count is 1e-4 in CD, and CD here is about 208 counts. If a change moves
# fewer than one count it is noise against the grid effect of 28 counts; if it moves
# several, it belongs in the production grids and therefore in the re-run.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")

echo "=== waiting for queue15.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue15.out" 2>/dev/null; do sleep 60; done
sleep 20

build_and_run() {   # LEVEL ALPHAS...
  local L=$1; shift
  local D=$O/guideline/$L
  echo "=== $L $(date -Is)"
  $V "$S/build_volume.py" --level "$L" --index 83 --out "$D" --no-plot3d 2>&1 \
    | grep -oE '"(total_cells|negative_cells_all_blocks)": [0-9]+' | tr '\n' ' '; echo
  $M/python "$S/write_cgns.py" --blocks "$D/${L}_blocks.npz" > /dev/null 2>&1
  $V "$S/mesh_guidelines.py" --blocks "$D/${L}_blocks.npz" --summary "$D/${L}_summary.json" \
    2>&1 | tail -3
  for AL in "$@"; do
    local d=$D/${L}_a$AL; mkdir -p "$d"; local t0=$(date +%s)
    timeout --kill-after=60 7200 "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" \
      --grid "$D/${L}_volume.cgns" --alpha "$AL" --no-nk --area-ref "$A83" \
      --out "$d" --i-have-authorization > "$d/run.log" 2>&1
    echo "  a$AL wall=$(( $(date +%s) - t0 )) s"
    $V -c "
import json
new = json.load(open('$d/result.json'))
old = json.load(open('$A/s8_pilot/g83/gci_C_a$AL/result.json'))
f = lambda r: {k.split('_')[-1]: v for k, v in r['functions'].items()}
n, o = f(new), f(old)
counts = 1e4 * (n['cd'] - o['cd'])
print(f\"    CD {counts:+.2f} drag counts   CL {100*(n['cl']-o['cl'])/o['cl']:+.2f} %   \"
      f\"CDp {100*(n['cdp']-o['cdp'])/o['cdp']:+.2f} %   converged={new['converged']}\")" \
      2>/dev/null || echo "    FAILED"
  done
}

build_and_run gci_C_ff100 0 8
build_and_run gci_C_te 0 4
echo "=== done $(date -Is)"
