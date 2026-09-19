set -u
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
O=$R/AERIS_MESH_STUDY/artifacts/s8_aniso
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
# PLAN 0.2: one measurement at a time. Wait for chord2 to finish completely --
# both angles -- before starting anything that competes for memory or CPU.
echo "=== waiting for chord2 to finish $(date -Is)"
while ! grep -q "=== done" "$O/chord2.out" 2>/dev/null; do sleep 30; done
sleep 20   # let the last ranks release their memory
L=gci_C_s0
echo "=== $L build $(date -Is)"
$R/.venv/bin/python $S/build_volume.py --level $L --index 83 --out "$O" --no-plot3d 2>&1 \
  | grep -oE '"(total_cells|negative_cells_all_blocks|normal_growth_ratio)": [0-9.e-]*' | tr '\n' ' '; echo
$M/python $S/write_cgns.py --blocks "$O/${L}_blocks.npz" >/dev/null 2>&1
for A in 0 4; do
  mkdir -p "$O/${L}_a$A"
  echo "=== $L alpha $A solve $(date -Is)"
  $M/mpirun -np 6 $M/python $S/solve_s8.py --grid "$O/${L}_volume.cgns" \
    --alpha $A --out "$O/${L}_a$A" --no-nk --i-have-authorization > "$O/${L}_a$A/run.log" 2>&1
  $R/.venv/bin/python -c "
import json;r=json.load(open('$O/${L}_a$A/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"  $L a=$A CL={f['cl']:+.6f} CD={f['cd']:.6f} CDp={f['cdp']:.6f} CDv={f['cdv']:.6f}\")" 2>/dev/null || echo "  $L a=$A FAILED"
done
echo "=== done $(date -Is)"
