set -u
# Behind queue3.sh. queue3's three o1024 NACA runs all froze the moment NK took over
# at 1e-4 (step 0.01, linear residual 1.000, 3500 iterations) -- the gci_M signature --
# and stopped on the cycle budget near 1e-4. Two stronger NK set-ups, in order; the
# first that meets the campaign rule (1e-6) is reused for the chi 3 and Mach runs.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
N=$A/tmr_naca0012
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python

echo "=== waiting for queue3.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue3.out" 2>/dev/null; do sleep 60; done
sleep 20

BASE="--l2 1e-8 --n-cycles 300000 --time-limit 5400 --set ANKSubspaceSize=50 --set ANKPCILUFill=2 --set ANKCoupledSwitchTol=1e-4"
CFG1="--set NKSwitchTol=1e-5 --set NKSubspaceSize=100 --set NKPCILUFill=3 --set NKASMOverlap=2 --set NKJacobianLag=5"
CFG2="--set NKSwitchTol=1e-6 --set NKSubspaceSize=150 --set NKPCILUFill=4 --set NKASMOverlap=3 --set NKOuterPreconIts=2 --set NKJacobianLag=3"

ok() { $V -c "import json,sys;r=json.load(open('$1/result.json'));sys.exit(0 if (r.get('relative_residual') or 1) <= 1e-6 else 1)" 2>/dev/null; }
run() {  # NAME ARGS... ; a failed attempt is kept beside, never overwritten
  local name=$1; shift; local d=$N/runs/$name
  [ -d "$d" ] && mv "$d" "${d}_failed_$(date +%H%M)"
  mkdir -p "$d"; local t0=$(date +%s)
  "$M/mpirun" -np 6 "$M/python" "$S/naca0012_tmr.py" solve --out "$d" $BASE "$@" > "$d/run.log" 2>&1
  echo "  $name wall=$(( $(date +%s) - t0 )) s $($V -c "import json;r=json.load(open('$d/result.json'));print('res %.1e' % r['relative_residual'], {k: round(v, 6) for k, v in r['coefficients'].items()})" 2>/dev/null || echo FAILED)"
}

echo "=== NACA 0012 o1024, stronger NK $(date -Is)"
USE=""
for C in "$CFG1" "$CFG2"; do
  run o1024_m0.15 --grid "$N/o1024.cgns" $C
  if ok "$N/runs/o1024_m0.15"; then USE="$C"; break; fi
done
if [ -n "$USE" ]; then
  run o1024_m0.15_chi3 --grid "$N/o1024.cgns" --eddy-vis-inf-ratio 0.21 $USE
  run o1024_m0.0837 --grid "$N/o1024.cgns" --mach 0.0837 $USE
else
  echo "  o1024 met the campaign rule with neither set-up"
fi
$V "$S/naca0012_tmr.py" compare
echo "=== done $(date -Is)"
