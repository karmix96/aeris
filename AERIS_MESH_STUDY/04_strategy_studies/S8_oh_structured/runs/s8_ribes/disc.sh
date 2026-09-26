set -u
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin; V=$R/.venv/bin/python
D=$S/runs/s8_ribes/discriminator
"$M/mpirun" -np 6 "$M/python" $S/solve_s8.py --grid "$S/runs/s8_ribes/gci2_C_volume.cgns" \
   --alpha 0.36 --no-nk --eddy-vis-inf-ratio 0.21 --area-ref 0.815 \
   --mach 0.11494 --reynolds 1.3286e6 --reynolds-length 0.5153 --temperature 298.85 \
   --chord-ref 0.5153 --out "$D" --i-have-authorization > "$D/run.log" 2>&1
[ -f "$D/result.json" ] && $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"  alpha 0.36: CL {f['cl']:8.4f}  CD {1e4*f['cd']:8.2f} ct  CDp {1e4*f['cdp']:8.2f}  CDv {1e4*f['cdv']:7.2f}  conv={r['converged']}\")
print(f\"  RIBES T40 measured sectional Cl at alpha 0.36: 0.2638 (SEC C), 0.2260 (SEC E)\")" || echo FAILED
