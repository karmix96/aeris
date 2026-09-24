set -u
# gci2_C on both target geometries. What this decides, before any cloud money:
#
# gci2_C and gci_C_chord2 carry the SAME chordwise count (o_wing xi = 157, n_side 75).
# chord2 is already solved on g83 and g47 at alpha 0 and 4. So differencing them
# measures exactly what family 2's other changes are worth:
#     - leading/trailing edge spacing scaled with the chordwise count (edges=True)
#     - far field 40 -> 60 root chords  (isolated value already measured: +0.633 counts)
#
# It also puts gci_F's chordwise AND leading-edge resolution (xi 157, LE turn 4.74 deg)
# on this desktop for 1,059,152 cells instead of gci_F's 2,322,128 -- so the chordwise
# hypothesis gets tested at fine-mesh resolution without renting anything.
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin; V=$R/.venv/bin/python
log(){ echo "$(date +%H:%M:%S) $*"; }
preflight(){ local need=$1 w=0; while :; do
    local a=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    [ "$a" -ge $(( need * 1024 * 1024 )) ] && { log "    mem ok ${need}<=$(( a / 1048576 )) GiB"; return 0; }
    [ "$w" -ge 900 ] && { log "    REFUSING: $(( a / 1048576 )) GiB free"; return 1; }
    sleep 30; w=$(( w + 30 )); done; }
for GX in 83:0.39492 47:0.29775; do
  IX=${GX%%:*}; AR=${GX##*:}; O=$S/runs/s8_fam2/g$IX
  if [ ! -f "$O/gci2_C_volume.cgns" ]; then
    log "  cgns gci2_C g$IX"
    "$M/python" "$S/write_cgns.py" --blocks "$O/gci2_C_blocks.npz" > "$O/gci2_C_cgns.log" 2>&1 \
      || { log "    CGNS FAILED"; continue; }
  fi
  for AL in 0 4; do
    D=$O/gci2_C_a$AL
    [ -f "$D/result.json" ] && { log "  g$IX gci2_C a$AL done"; continue; }
    mkdir -p "$D"; preflight 11 || continue
    log "  g$IX gci2_C a$AL solving"
    "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$O/gci2_C_volume.cgns" \
       --alpha $AL --no-nk --eddy-vis-inf-ratio 0.21 --area-ref "$AR" \
       --out "$D" --i-have-authorization > "$D/run.log" 2>&1
    if [ -f "$D/result.json" ]; then
      $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v*1e4 for k,v in r['functions'].items()}
print(f\"    CD {f['cd']:8.3f}  CDp {f['cdp']:8.3f}  CDv {f['cdv']:7.3f}  CL {f['cl']:9.3f}  conv={r['converged']}  iters={r['iterations_completed']}\")"
    else log "    FAILED -- see $D/run.log"; fi
  done
done
log "=== gating"
$V "$S/convergence_gate.py" --runs $(ls -d $S/runs/s8_fam2/g*/gci2_C_a[0-9] 2>/dev/null) \
   --out "$S/runs/s8_fam2/gate.json" 2>&1 | tail -8
log "=== fam2 gci2_C done"
