set -u
# Behind queue4.sh: settings put on trial (11 Sept), each a single change against a
# run that already exists, on geometry 83.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
G83=$A/s8_gci83/gci_C_volume.cgns
GM83=$A/s8_pilot/g83/gci_M_volume.cgns
[ -f "$GM83" ] || GM83=$A/s8_gci83/gci_M_volume.cgns

echo "=== waiting for queue4.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue4.out" 2>/dev/null; do sleep 60; done
sleep 20
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")

solve() {  # NAME DIR ARGS...
  local name=$1 d=$2; shift 2; mkdir -p "$d"; local t0=$(date +%s)
  "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" "$@" --no-nk --area-ref "$A83" \
    --out "$d" --i-have-authorization > "$d/run.log" 2>&1
  echo "  $name wall=$(( $(date +%s) - t0 )) s"
  $V -c "
import json;r=json.load(open('$d/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CL={f['cl']:+.6f} CD={f['cd']:.6f} CDp={f['cdp']:.6f} CDv={f['cdv']:.6f} conv={r['converged']}\")" \
    2>/dev/null || echo "    FAILED"
}

echo "=== 1/4 SA without ft2, default freestream (against mg/base and chi3/a0) $(date -Is)"
solve noft2_a0 "$O/trial/noft2_a0" --grid "$G83" --alpha 0 --no-ft2
echo "=== 2/4 second-order turbulence advection (against mg/base) $(date -Is)"
solve turb2_a0 "$O/trial/turb2_a0" --grid "$G83" --alpha 0 --turbulence-order "second order"
echo "=== 3/4 far field 60 root chords at alpha 8 (against s8_pilot/g83/gci_C_a8) $(date -Is)"
solve ff60_a8 "$O/trial/ff60_a8" --grid "$A/s8_farfield60/gci_C_volume.cgns" --alpha 8
echo "=== 4/4 freestream chi 3 at gci_M alpha 0 (against s8_pilot/g83/gci_M_a0) $(date -Is)"
solve chi3_gciM_a0 "$O/trial/chi3_gciM_a0" --grid "$GM83" --alpha 0 --eddy-vis-inf-ratio 0.21
echo "=== 5/5 Menter SST retry $(date -Is)"
# The first attempt stopped after ONE DADI iteration with a residual ratio of 9e-9
# and wrote CL -1.17, CD 2.21 as "converged": ADflow's own L2 check was satisfied by
# a bogus initial residual for this model. A tight target keeps it iterating, and
# solve_s8.py now refuses to call physically impossible forces converged.
for AL in 0 4; do
  solve "sst2 a$AL" "$O/trial/sst2_a$AL" --grid "$G83" --alpha $AL \
    --turbulence-model "Menter SST" --l2 1e-12 --time-limit 5400
done
echo "=== done $(date -Is)"
