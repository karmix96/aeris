set -u
# Behind queue7. The finest NACA grid converged once it was built gently -- and that
# grid is 1024 surface points on the SAME 128 wall-normal cells as the 512 one, i.e.
# a chordwise-only refinement. That is exactly the one-direction family the wing study
# leans on, so completing it here tests the method against an answer that is known.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
O=$R/AERIS_MESH_STUDY/artifacts/s8_checklist
N=$R/AERIS_MESH_STUDY/artifacts/tmr_naca0012
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
NACA_FLAGS="--l2 1e-8 --n-cycles 300000 --time-limit 5400 --set ANKSubspaceSize=50 --set ANKPCILUFill=2 --set ANKCoupledSwitchTol=1e-4 --set NKSwitchTol=1e-5 --set NKSubspaceSize=100 --set NKPCILUFill=3 --set NKASMOverlap=2 --set NKJacobianLag=5"

echo "=== waiting for queue7.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue7.out" 2>/dev/null; do sleep 60; done
sleep 20

naca() {
  local name=$1 d=$N/runs/$1; shift
  [ -f "$d/result.json" ] && { echo "  $name already done"; return; }
  mkdir -p "$d"; local t0=$(date +%s)
  "$M/mpirun" -np 6 "$M/python" "$S/naca0012_tmr.py" solve "$@" --out "$d" --no-nk $NACA_FLAGS \
    > "$d/run.log" 2>&1
  echo "  $name wall=$(( $(date +%s) - t0 )) s"
  $V -c "
import json;r=json.load(open('$d/result.json'));c=r['coefficients']
print('    ' + '  '.join(f'{k}={v:.6f}' for k,v in c.items()) + f\"  conv={r['converged']}\")" \
    2>/dev/null || echo "    FAILED"
}

echo "=== chordwise family at fixed wall spacing: 256, 512, 1024 surface points $(date -Is)"
$M/python "$S/naca0012_tmr.py" grid --levels o256 o512 --normal-cells 128 --s0 1e-6 --suffix s0 \
  > "$N/grid_s0.log" 2>&1 && grep -E "cells, s0" "$N/grid_s0.log"
naca o256s0_m0.15 --grid "$N/o256s0.cgns"
naca o512s0_m0.15 --grid "$N/o512s0.cgns"
echo "=== the family, extrapolated, against NASA's answer $(date -Is)"
$V "$S/naca0012_tmr.py" compare --family o256s0_m0.15 o512s0_m0.15 o1024n128_m0.15
echo "=== done $(date -Is)"
