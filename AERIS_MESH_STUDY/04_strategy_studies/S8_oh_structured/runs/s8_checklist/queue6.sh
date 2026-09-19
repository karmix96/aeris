set -u
# Behind queue5: the freestream-turbulence switch you approved. NASA's standard for
# this turbulence model is chi = 3 (eddy-viscosity ratio 0.21); every run so far used
# ADflow's default, chi ~1.3. Runs go to a SEPARATE tree so the old results stay
# intact and the offset can be measured run against run.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
C=$A/s8_chi3
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python

echo "=== waiting for queue5.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue5.out" 2>/dev/null; do sleep 60; done
sleep 20

area() { $V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['$1']['half_area_m2'])"; }
run() {  # INDEX LEVEL ALPHA GRID
  local i=$1 l=$2 al=$3 grid=$4 d=$C/g$1/${2}_a$3
  [ -f "$d/result.json" ] && { echo "  g$i $l a$al already done"; return; }
  mkdir -p "$d"; local t0=$(date +%s)
  "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$grid" --alpha "$al" --no-nk \
    --area-ref "$(area $i)" --eddy-vis-inf-ratio 0.21 --out "$d" --i-have-authorization \
    > "$d/run.log" 2>&1
  echo "  g$i $l a$al wall=$(( $(date +%s) - t0 )) s"
  $V -c "
import json;r=json.load(open('$d/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CL={f['cl']:+.6f} CD={f['cd']:.6f} CDp={f['cdp']:.6f} CDv={f['cdv']:.6f} conv={r['converged']}\")" \
    2>/dev/null || echo "    FAILED"
}

echo "=== 1/2 reference wing 83, both desktop levels, chi 3 $(date -Is)"
for AL in -2 0 4 8; do run 83 gci_C $AL "$A/s8_gci83/gci_C_volume.cgns"; done
for AL in -2 0 4 8; do run 83 gci_M $AL "$A/s8_pilot/g83/gci_M_volume.cgns"; done

echo "=== 2/2 the other nine wings, coarse grid, chi 3 $(date -Is)"
for I in 12 13 16 23 29 36 47 65 81; do
  for AL in -2 0 4 8; do run $I gci_C $AL "$A/s8_pilot/g$I/gci_C_volume.cgns"; done
done

echo "=== comparison against the default-chi runs $(date -Is)"
$V $S/chi_offset.py --out $R/AERIS_MESH_STUDY/05_s6_cfd_qualification/reports/s8_freestream_turbulence.json 2>&1 | tail -20
echo "=== done $(date -Is)"
