set -u
# The BASELINE at gci_CC: the third point on the trailing-edge credit.
#
# The credit is measured at gci_C (-8.11 to -9.15 counts) and gci_M (-2.05 to
# -3.03). Extrapolating those two with the order measured on absolute drag
# (p = 1.75-1.88) sends the credit through zero to about +9 to +10 counts at every
# incidence -- the change would ADD drag. Two points cannot say that. These four
# solves make it three points, so the credit gets its OWN observed order and its own
# extrapolation instead of borrowing absolute drag's.
#
# Pairing: baseline is the pre-change family -- trailing edge at 0.4 % of chord, old
# 10 x s0 cap -- which is what runs/s8_chi3 used at gci_C and gci_M. Treatment is
# runs/s8_gciCC/g83 (0.1 % edge, wall-resolved cap). Same solver settings on both:
# chi 3, ANK only, L2 1e-6, own area 0.39492.
#
#   bash runs/s8_ccbase/queue_ccbase.sh
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
log() { echo "$(date +%H:%M:%S) $*"; }
preflight() { local need=$1 w=0; while :; do
    local a=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    [ "$a" -ge $(( need * 1024 * 1024 )) ] && return 0
    [ "$w" -ge 900 ] && { log "    refusing: $(( a / 1048576 )) GiB free"; return 1; }
    sleep 30; w=$(( w + 30 )); done; }
for AL in 0 4 -2 8; do
  D=$S/runs/s8_ccbase/g83/gci_CC_baseline_a$AL
  [ -f "$D/result.json" ] && { log "  a$AL done"; continue; }
  mkdir -p "$D"; preflight 6 || continue
  log "  baseline gci_CC a$AL solving"
  "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" \
    --grid "$S/runs/s8_ccbase/g83/gci_CC_baseline_volume.cgns" --alpha $AL --no-nk \
    --eddy-vis-inf-ratio 0.21 --area-ref 0.39492 --out "$D" --i-have-authorization \
    > "$D/run.log" 2>&1
  [ -f "$D/result.json" ] && $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CD {1e4*f['cd']:.3f} CDp {1e4*f['cdp']:.3f} conv={r['converged']}\")" || log "    a$AL FAILED"
done
log "=== gating"
$V "$S/convergence_gate.py" --runs $(ls -d $S/runs/s8_ccbase/g83/gci_CC_baseline_a* 2>/dev/null) \
   --out "$S/runs/s8_ccbase/g83/gci_CC_baseline_gate.json" 2>&1 | tail -7
log "=== done"
