set -u
# Behind queue.sh: low-speed verification (TMR NACA 0012) and the freestream
# turbulence check on S8 itself. One solve at a time (PLAN 0.2).
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
N=$A/tmr_naca0012
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
G83=$A/s8_gci83/gci_C_volume.cgns

echo "=== waiting for queue.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue.out" 2>/dev/null; do sleep 60; done
sleep 20

run() {  # name np args...
  local name=$1 np=$2; shift 2; local d=$N/runs/$name; mkdir -p "$d"
  local t0=$(date +%s)
  "$M/mpirun" -np "$np" "$M/python" "$S/naca0012_tmr.py" solve "$@" --out "$d" --no-nk \
    > "$d/run.log" 2>&1
  echo "  $name wall=$(( $(date +%s) - t0 )) s"
  $V -c "import json;r=json.load(open('$d/result.json'));print('   ',r['converged'],r['coefficients'])" \
    2>/dev/null || echo "    FAILED"
}

echo "=== 1/3 NACA 0012 grids $(date -Is)"
$M/python "$S/naca0012_tmr.py" grid --levels o256 o512 o1024 o2048 > "$N/grid.log" 2>&1 \
  || echo "  grid FAILED, see $N/grid.log"
grep -E "cells, s0" "$N/grid.log"

echo "=== 2/3 NACA 0012 solves, M 0.15 Re 6e6 alpha 10 $(date -Is)"
for L in o256 o512 o1024 o2048; do run "${L}_m0.15" 6 --grid "$N/$L.cgns"; done
run o1024_m0.15_chi3 6 --grid "$N/o1024.cgns" --eddy-vis-inf-ratio 0.21
run o1024_m0.0837 6 --grid "$N/o1024.cgns" --mach 0.0837
$V "$S/naca0012_tmr.py" compare

echo "=== 3/3 S8 freestream turbulence, geometry 83 gci_C $(date -Is)"
A83=$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")
for AL in 0 4; do
  d=$O/chi3/a$AL; mkdir -p "$d"
  t0=$(date +%s)
  "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$G83" --alpha $AL --no-nk \
    --area-ref "$A83" --eddy-vis-inf-ratio 0.21 --out "$d" --i-have-authorization \
    > "$d/run.log" 2>&1
  echo "  chi3 a$AL wall=$(( $(date +%s) - t0 )) s"
  $V -c "
import json;r=json.load(open('$d/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CL={f['cl']:+.6f} CD={f['cd']:.6f} CDp={f['cdp']:.6f} CDv={f['cdv']:.6f} conv={r['converged']}\")" \
    2>/dev/null || echo "    FAILED"
done
echo "=== done $(date -Is)"
