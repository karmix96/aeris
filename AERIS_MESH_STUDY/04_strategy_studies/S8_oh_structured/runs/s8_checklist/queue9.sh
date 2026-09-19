set -u
# Behind queue8. The second turbulence model, now that the reason all three failed is
# known: ADflow ships a residual scaling for SA and Menter SST only, and the others
# raise on one rank and hang the other five -- which is also why a 90-minute limit let
# a run reach four and three quarter hours. Every solve here is wrapped in `timeout`,
# which does not depend on the solver noticing anything.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
G83=$A/s8_gci83/gci_C_volume.cgns

echo "=== waiting for queue8.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue8.out" 2>/dev/null; do sleep 60; done
sleep 20
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")

solve() {  # NAME DIR ARGS...
  local name=$1 d=$2; shift 2; mkdir -p "$d"; local t0=$(date +%s)
  timeout --kill-after=60 5400 \
    "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" "$@" --no-nk --area-ref "$A83" \
    --out "$d" --i-have-authorization > "$d/run.log" 2>&1
  local rc=$?
  echo "  $name wall=$(( $(date +%s) - t0 )) s exit=$rc"
  $V -c "
import json;r=json.load(open('$d/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CL={f['cl']:+.6f} CD={f['cd']:.6f} CDp={f['cdp']:.6f} CDv={f['cdv']:.6f} \"
      f\"conv={r['converged']} its={r.get('iterations_completed')}\")" 2>/dev/null \
    || echo "    no result: $(strings '$d/run.log' | grep -m1 -A2 'Error:' | tr '\n' ' ' | cut -c1-140)"
}

echo "=== 1/3 SA-Edwards, with SA's residual scaling $(date -Is)"
for AL in 0 4; do
  solve "edwards a$AL" "$O/trial/edwards2_a$AL" --grid "$G83" --alpha $AL \
    --turbulence-model "SA-Edwards" --turb-res-scale 10000
done
echo "=== 2/3 k-omega Wilcox, with a two-equation scaling $(date -Is)"
for AL in 0 4; do
  solve "k-omega a$AL" "$O/trial/komega2_a$AL" --grid "$G83" --alpha $AL \
    --turbulence-model "k-omega Wilcox" --turb-res-scale 1e3 1e-6
done
echo "=== 3/3 Menter SST once more, at the campaign target $(date -Is)"
for AL in 0 4; do
  solve "sst a$AL" "$O/trial/sst3_a$AL" --grid "$G83" --alpha $AL \
    --turbulence-model "Menter SST" --turb-res-scale 1e3 1e-6
done
echo "=== done $(date -Is)"
