set -u
# eddyVisInfRatio 0.21 is chi = 3, chosen for the S8 mission. Spalart-Allmaras
# needs enough freestream eddy viscosity for the boundary layer to stay
# turbulent; too little and it relaminarises, which gives very low skin friction
# and a boundary layer that separates early. CDv of 4.1 counts against the AERIS
# mesh's 93.8, with CDp at 2644, is exactly that signature. This drops the
# override and uses ADflow's own default instead. One variable.
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin; V=$R/.venv/bin/python
D=$S/runs/s8_ribes/chi_default
"$M/mpirun" -np 6 "$M/python" $S/solve_s8.py --grid "$S/runs/s8_ribes/gci2_C_volume.cgns" \
   --alpha 0.36 --no-nk --area-ref 0.815 \
   --mach 0.11494 --reynolds 1.3286e6 --reynolds-length 0.5153 --temperature 298.85 \
   --chord-ref 0.5153 --out "$D" --i-have-authorization > "$D/run.log" 2>&1
[ -f "$D/result.json" ] && $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"  ADflow default chi: CL {f['cl']:8.4f}  CD {1e4*f['cd']:8.2f} ct  CDp {1e4*f['cdp']:8.2f}  CDv {1e4*f['cdv']:7.2f}  conv={r['converged']}\")
print(f\"  with chi=3 it was : CL  -0.1526  CD  2648.04 ct  CDp  2643.94  CDv    4.10\")
print(f\"  AERIS g83 for scale: CDv about 93.8 counts\")" || echo FAILED
