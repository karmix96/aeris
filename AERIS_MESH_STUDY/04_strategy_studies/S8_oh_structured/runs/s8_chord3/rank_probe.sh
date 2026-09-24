set -u
# Does gci_C_chord3 (1,367,416 cells) fit this host if we drop MPI ranks?
#
# The ANK-only memory law (2.69 + 7.23 * Mcells) * 1.05 predicts 13.2 GiB against
# ~12 free, and that law was fitted at 6 ranks. ADflow duplicates halo layers per
# rank, so fewer ranks should mean less total memory -- at the cost of wall time.
# If 4 ranks fit, the fourth chordwise level can be bought here for nothing
# instead of on a rented machine. One variable: rank count.
#
# Guarded: peak RSS is sampled every 10 s and the run is abandoned if MemAvailable
# ever drops below 0.7 GiB, so a thrash cannot take the machine down.
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin; V=$R/.venv/bin/python
C3=$S/runs/s8_chord3/g83
log(){ echo "$(date +%H:%M:%S) $*"; }
NP=${1:-4}
D=$C3/gci_C_chord3_np${NP}_a0
[ -f "$D/result.json" ] && { log "np$NP already done"; exit 0; }
mkdir -p "$D"
A=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
log "np$NP: starting with $(( A / 1048576 )) GiB available"
"$M/mpirun" -np $NP "$M/python" "$S/solve_s8.py" \
   --grid "$C3/gci_C_chord3_volume.cgns" --alpha 0 --no-nk \
   --eddy-vis-inf-ratio 0.21 --area-ref 0.39492 --out "$D" --i-have-authorization \
   > "$D/run.log" 2>&1 &
PID=$!
PEAK=0; MINAV=99999999
while kill -0 $PID 2>/dev/null; do
  AV=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
  [ "$AV" -lt "$MINAV" ] && MINAV=$AV
  U=$(( $(awk '/^MemTotal:/{print $2}' /proc/meminfo) - AV ))
  [ "$U" -gt "$PEAK" ] && PEAK=$U
  if [ "$AV" -lt 734003 ]; then
    log "    ABORTING: only $(( AV / 1024 )) MiB available -- killing to protect the host"
    kill -TERM $PID 2>/dev/null; sleep 5; kill -KILL $PID 2>/dev/null
    echo "ABORTED_LOW_MEMORY" > "$D/VERDICT"; break
  fi
  sleep 10
done
wait $PID 2>/dev/null || true
log "np$NP: peak used $(echo "$PEAK" | awk '{printf "%.1f", $1/1048576}') GiB, min available $(echo "$MINAV" | awk '{printf "%.1f", $1/1048576}') GiB"
if [ -f "$D/result.json" ]; then
  $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v*1e4 for k,v in r['functions'].items()}
print(f\"    FITS.  CD {f['cd']:8.3f}  CDp {f['cdp']:8.3f}  CDv {f['cdv']:7.3f}  CL {f['cl']:9.3f}  conv={r['converged']}  iters={r['iterations_completed']}\")"
else
  log "    did NOT complete -- see $D/run.log  $( [ -f "$D/VERDICT" ] && cat "$D/VERDICT" )"
fi
