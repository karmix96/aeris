set -u
# Behind queue9. The test nothing has done yet: OUR mesher, on the one wing with
# public wind-tunnel measurements. Every external check so far validated the
# solver -- the M6 comparison ran on NASA's grid, the NACA 0012 verification on
# pyHyp grids. This puts our own O-H mesh, our own marching and our own tip cap
# in front of Schmitt & Charpin's 1979 measurements.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
Q=$R/AERIS_MESH_STUDY/05_s6_cfd_qualification
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
GRID=$A/m6_oh/m6_oh_volume.cgns

echo "=== waiting for queue9.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue9.out" 2>/dev/null; do sleep 60; done
sleep 20

D=$A/onera_m6/run_ourmesh
mkdir -p "$D"
echo "=== solving the M6 on our own mesh, 955k cells, y+ ~0.45 $(date -Is)"
t0=$(date +%s)
timeout --kill-after=120 21600 \
  "$M/mpirun" -np 6 "$M/python" "$S/onera_m6.py" solve --grid "$GRID" --out "$D" \
  --lift-index 3 --no-nk > "$D/run.log" 2>&1
echo "  wall=$(( $(date +%s) - t0 )) s"
$V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"  CL={f['cl']:+.6f} CD={f['cd']:.6f} CDp={f['cdp']:.6f} CDv={f['cdv']:.6f} \"
      f\"converged={r['converged']} res={r['relative_residual']:.2e}\")" 2>/dev/null || echo "  FAILED"

echo "=== against the 1979 measurements, all seven stations $(date -Is)"
$V "$S/onera_m6.py" compare --run "$D" --span-axis y \
  --out "$Q/reports/s8_onera_m6_our_mesh.json" 2>&1 | tail -14
$V "$S/onera_m6.py" plot --run "$D" --span-axis y --out "$A/onera_m6/m6_our_mesh_cp.png" 2>&1 | tail -1

echo "=== the same wing, both meshes, side by side $(date -Is)"
$V - <<'PY'
import json
from pathlib import Path
q = Path("/home/mike_kara/aeris/AERIS_MESH_STUDY/05_s6_cfd_qualification/reports")
ours = json.loads((q / "s8_onera_m6_our_mesh.json").read_text())
nasa = json.loads((q / "s8_onera_m6_comparison_nonk.json").read_text())
for tag, r in (("NASA's grid, 295k cells", nasa), ("our mesh, 955k cells", ours)):
    print(f"  {tag:<26} suction peak {100*r['cp_min_mean_relative_error']:.1f}%   "
          f"shock {r['shock_position_mean_abs_error_x_over_c']:.4f} x/c   "
          f"RMS dcp {r['rms_dcp_all_stations']:.3f}")
PY
echo "=== done $(date -Is)"
