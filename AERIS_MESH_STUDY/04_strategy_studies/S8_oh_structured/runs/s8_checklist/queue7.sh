set -u
# Behind queue6: closing out the settings audit.
#   - the NACA finest grid, rebuilt gently (its trailing-edge cells pinched)
#   - the two single-change NACA runs that never happened because it failed:
#     AERIS's own Mach number, and NASA's freestream turbulence
#   - a second turbulence model on the wing (SST aborts in this build)
#   - ANK-only against the governed ANK->NK on our own geometry
#   - the wall-normal direction refined PROPERLY: layers and first cell together
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
N=$A/tmr_naca0012
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
G83=$A/s8_gci83/gci_C_volume.cgns
NACA_FLAGS="--l2 1e-8 --n-cycles 300000 --time-limit 5400 --set ANKSubspaceSize=50 --set ANKPCILUFill=2 --set ANKCoupledSwitchTol=1e-4 --set NKSwitchTol=1e-5 --set NKSubspaceSize=100 --set NKPCILUFill=3 --set NKASMOverlap=2 --set NKJacobianLag=5"

echo "=== waiting for queue6.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue6.out" 2>/dev/null; do sleep 60; done
sleep 20
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")

show() { $V -c "
import json;r=json.load(open('$1/result.json'))
f=r.get('coefficients') or {k.split('_')[-1]:v for k,v in r['functions'].items()}
g=lambda k: f.get(k, f.get(k.upper(), float('nan')))
print(f\"    CL={g('cl'):+.6f} CD={g('cd'):.6f} CDp={g('cdp'):.6f} CDv={g('cdv'):.6f} \"
      f\"conv={r.get('converged')} res={r.get('relative_residual'):.1e} its={r.get('iterations_completed')}\")" 2>/dev/null || echo "    FAILED"; }
solve() {  # NAME DIR ARGS...
  local name=$1 d=$2; shift 2; mkdir -p "$d"; local t0=$(date +%s)
  "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" "$@" --area-ref "$A83" --out "$d" \
    --i-have-authorization > "$d/run.log" 2>&1
  echo "  $name wall=$(( $(date +%s) - t0 )) s"; show "$d"
}
naca() {  # NAME ARGS...
  local name=$1 d=$N/runs/$1; shift; [ -d "$d" ] && mv "$d" "${d}_old_$(date +%H%M)"
  mkdir -p "$d"; local t0=$(date +%s)
  "$M/mpirun" -np 6 "$M/python" "$S/naca0012_tmr.py" solve "$@" --out "$d" --no-nk $NACA_FLAGS \
    > "$d/run.log" 2>&1
  echo "  $name wall=$(( $(date +%s) - t0 )) s"; show "$d"
}

echo "=== 1/5 NACA finest grid, built gently: 128 cells off the wall $(date -Is)"
$M/python "$S/naca0012_tmr.py" grid --levels o1024 --normal-cells 128 --suffix n128 \
  > "$N/grid_n128.log" 2>&1 && grep -E "cells, s0" "$N/grid_n128.log"
naca o1024n128_m0.15 --grid "$N/o1024n128.cgns"

echo "=== 2/5 NACA at AERIS's Mach, and at NASA's freestream turbulence (65k grid) $(date -Is)"
naca o512_m0.0837 --grid "$N/o512.cgns" --mach 0.0837
naca o512_m0.15_chi3 --grid "$N/o512.cgns" --eddy-vis-inf-ratio 0.21
$V "$S/naca0012_tmr.py" compare

echo "=== 3/5 a second turbulence model on the wing $(date -Is)"
for AL in 0 4; do
  solve "sa-edwards a$AL" "$O/trial/edwards_a$AL" --grid "$G83" --alpha $AL --no-nk \
    --turbulence-model "SA-Edwards" --time-limit 5400
done
if ! $V -c "import json,sys;sys.exit(0 if json.load(open('$O/trial/edwards_a0/result.json')).get('converged') else 1)" 2>/dev/null; then
  echo "  SA-Edwards did not converge; trying k-omega Wilcox"
  for AL in 0 4; do
    solve "k-omega a$AL" "$O/trial/komega_a$AL" --grid "$G83" --alpha $AL --no-nk \
      --turbulence-model "k-omega Wilcox" --time-limit 5400
  done
fi

echo "=== 4/5 the governed solver route (ANK then NK) against ANK alone $(date -Is)"
solve "nk_governed a0" "$O/trial/nk_a0" --grid "$G83" --alpha 0 --time-limit 5400

echo "=== 5/5 wall-normal refined properly: layers AND first cell together $(date -Is)"
L=gci_C_normal_s0
D=$O/dir_normal_s0
$V "$S/build_volume.py" --level $L --index 83 --out "$D" --no-plot3d 2>&1 \
  | grep -oE '"(total_cells|negative_cells_all_blocks)": [0-9]*' | tr '\n' ' '; echo
$M/python "$S/write_cgns.py" --blocks "$D/${L}_blocks.npz" > /dev/null 2>&1
for AL in 0 4; do
  solve "$L a$AL" "$D/${L}_a$AL" --grid "$D/${L}_volume.cgns" --alpha $AL --no-nk
done
echo "=== done $(date -Is)"
