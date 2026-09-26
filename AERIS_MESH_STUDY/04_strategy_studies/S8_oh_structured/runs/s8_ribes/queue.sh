set -u
# RIBES VALIDATION. The first time our own mesh, at our own kind of operating
# point, is put in front of a measurement.
#
# Mesh: gci2_C level -- the cloud family -- on the RIBES wing. 1,038,064 cells,
# 0 folded, wall layer at 1e-16, tip cap 2.004 x s0, LE turning target met at
# every one of 49 stations.
#
# Condition: the EXPERIMENT's, not ours, and taken from the measured columns of
# appendix A rather than the test matrix's nominal figures --
#
#     measured over 22 runs at V > 38 m/s:  39.83 m/s, 25.7 C, Re 1.329e6
#     the test matrix rounds that to "40 m/s, 1.43 mill."
#
#     Mach            0.11494      (39.83 m/s at 298.8 K)
#     Reynolds        1.3286e6     on the 0.5153 m mean aerodynamic chord
#     reference area  0.815 m2     the value the report forms its coefficients with
#
# Incidences: the four RIBES T40 corrected alphas nearest the S8 sweep, so the
# experiment is read directly rather than interpolated:
#
#     S8 runs    -2      0      4      8
#     RIBES T40  -1.94   0.36   4.75   8.12
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin; V=$R/.venv/bin/python
O=$S/runs/s8_ribes
log(){ echo "$(date +%H:%M:%S) $*"; }
[ -f "$O/gci2_C_volume.cgns" ] || { log "cgns"; "$M/python" $S/write_cgns.py --blocks "$O/gci2_C_blocks.npz" > "$O/cgns.log" 2>&1; }
for AL in -1.94 0.36 4.75 8.12; do
  D=$O/a$AL
  [ -f "$D/result.json" ] && { log "  a$AL done"; continue; }
  mkdir -p "$D"
  while [ "$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)" -lt 11534336 ]; do sleep 30; done
  log "  alpha $AL solving"
  "$M/mpirun" -np 6 "$M/python" $S/solve_s8.py --grid "$O/gci2_C_volume.cgns" --alpha $AL --no-nk \
     --eddy-vis-inf-ratio 0.21 --area-ref 0.815 \
     --mach 0.11494 --reynolds 1.3286e6 --reynolds-length 0.5153 --temperature 298.85 \
     --chord-ref 0.5153 --out "$D" --i-have-authorization > "$D/run.log" 2>&1
  [ -f "$D/result.json" ] && $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CL {f['cl']:8.4f}  CD {1e4*f['cd']:8.2f} ct  CDp {1e4*f['cdp']:8.2f}  CDv {1e4*f['cdv']:7.2f}  CMy {f['cmy']:+8.5f}  conv={r['converged']} iters={r['iterations_completed']}\")" \
    || log "    FAILED"
done
log "=== gating"
$V $S/convergence_gate.py --runs $(ls -d $O/a-*[0-9] $O/a[0-9]* 2>/dev/null) --out $O/gate.json 2>&1 | tail -8
log "=== done"
