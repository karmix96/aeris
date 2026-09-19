set -u
# Behind queue13, AHEAD of the re-run, because if this changes the answer the re-run
# must carry it. ADflow has a low-speed preconditioner and every run so far has had it
# off -- the default, never chosen. At M 0.0837 a central scheme's artificial
# dissipation scales with the speed of sound rather than the flow speed, so it is
# about twelve times larger than the physics it damps. The preconditioner exists for
# exactly that. Two runs on the wing, and one on the case with a known answer.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
N=$A/tmr_naca0012
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
G83=$A/s8_gci83/gci_C_volume.cgns
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")

echo "=== waiting for queue13.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue13.out" 2>/dev/null; do sleep 60; done
sleep 20

echo "=== 1/2 the wing, with the low-speed preconditioner $(date -Is)"
for AL in 0 4; do
  d=$O/trial/precon_a$AL; mkdir -p "$d"; t0=$(date +%s)
  timeout --kill-after=60 5400 "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" \
    --grid "$G83" --alpha $AL --no-nk --area-ref "$A83" --low-speed-preconditioner \
    --out "$d" --i-have-authorization > "$d/run.log" 2>&1
  echo "  a$AL wall=$(( $(date +%s) - t0 )) s"
  $V -c "
import json
new = json.load(open('$d/result.json'))
old = json.load(open('$A/s8_pilot/g83/gci_C_a$AL/result.json'))
f = lambda r: {k.split('_')[-1]: v for k, v in r['functions'].items()}
n, o = f(new), f(old)
print('    ' + '  '.join(f'{k.upper()} {100*(n[k]-o[k])/o[k]:+.2f}%' for k in ('cl','cd','cdp','cdv'))
      + f\"  converged={new['converged']} its={new.get('iterations_completed')}\")" \
    2>/dev/null || echo "    FAILED"
done

echo "=== 2/2 the same switch on the case whose answer is known $(date -Is)"
d=$N/runs/o512_m0.15_precon; [ -d "$d" ] && mv "$d" "${d}_old"; mkdir -p "$d"
t0=$(date +%s)
timeout --kill-after=120 7200 "$M/mpirun" -np 6 "$M/python" "$S/naca0012_tmr.py" solve \
  --grid "$N/o512.cgns" --out "$d" --no-nk --l2 1e-8 --n-cycles 300000 \
  --set lowSpeedPreconditioner=true --set ANKSubspaceSize=50 --set ANKPCILUFill=2 \
  --set ANKCoupledSwitchTol=1e-4 --set NKSwitchTol=1e-5 --set NKSubspaceSize=100 \
  --set NKPCILUFill=3 --set NKASMOverlap=2 --set NKJacobianLag=5 > "$d/run.log" 2>&1
echo "  wall=$(( $(date +%s) - t0 )) s"
$V -c "
import json
r = json.load(open('$d/result.json')); c = r['coefficients']
ref = {'CL':1.09094,'CD':0.01227275,'CDp':0.006067,'CDv':0.0062059}
print('    with preconditioner: ' + '  '.join(f'{k} {100*(c[k]-ref[k])/ref[k]:+.2f}%' for k in ref))
print('    without (measured)  : CL +0.74%  CD +4.40%  CDp +8.59%  CDv +0.31%')" \
  2>/dev/null || echo "    FAILED"
echo "=== done $(date -Is)"
