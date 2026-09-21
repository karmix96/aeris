set -u
# The THIRD GLOBAL LEVEL, and it fits this machine.
#
# The study's central limitation is stated everywhere: two levels, no observed
# order, no Richardson extrapolation, no uncertainty band -- and gci_F needs 22 GiB
# against 13.65, so a third level "needs a different machine"
# (reports/s8_level_selection.json).
#
# That is true only for refining UPWARD. gci_CC is defined in strategy_s8.py,
# refines at r = 1.3 in every direction exactly as the rest of the family does,
# carries the wall-resolved cap, and is 316,992 cells -- about 4.3 GiB. So
#
#     gci_CC  ->  gci_C  ->  gci_M
#     316,992    603,592    1,172,856
#
# is a complete three-level GLOBAL family on the production mesh family, and the
# two finer levels are already solved. It costs one build and four solves to get
# the observed order this study has said for three weeks it cannot have.
#
# What it can and cannot settle. It IS an observed order on the global family,
# measured rather than assumed, and gci.py will refuse it if the family is not
# monotone or runs away. It is NOT the same as an order measured on C -> M -> F:
# a coarser triplet sits further from the asymptotic range, so a clean order here
# is evidence the family is well behaved, not proof that gci_F will land where an
# extrapolation from here predicts. Read it as the cheapest available check on
# whether the family has an asymptotic range at all, before renting one.
#
#   bash runs/s8_gciCC/queue_gciCC.sh
#
# Written 2026-09-21.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
log() { echo "$(date +%H:%M:%S) $*"; }
preflight() { local need=$1 w=0; while :; do
    local a=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    [ "$a" -ge $(( need * 1024 * 1024 )) ] && return 0
    [ "$w" -ge 900 ] && { log "    refusing: $(( a / 1048576 )) GiB free, need $need"; return 1; }
    sleep 30; w=$(( w + 30 )); done; }
for AL in 0 4 -2 8; do
  D=$S/runs/s8_gciCC/gci_CC_a$AL
  [ -f "$D/result.json" ] && { log "  a$AL done"; continue; }
  mkdir -p "$D"; preflight 6 || continue
  log "  gci_CC a$AL solving"
  "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$S/runs/s8_gciCC/gci_CC_volume.cgns" \
    --alpha $AL --no-nk --eddy-vis-inf-ratio 0.21 --area-ref 0.39492 \
    --out "$D" --i-have-authorization > "$D/run.log" 2>&1
  [ -f "$D/result.json" ] && $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CD {1e4*f['cd']:.3f} CDp {1e4*f['cdp']:.3f} CDv {1e4*f['cdv']:.3f} conv={r['converged']}\")" \
    || log "    a$AL FAILED"
done
log "=== gating"
$V "$S/convergence_gate.py" --runs $(ls -d $S/runs/s8_gciCC/gci_CC_a* 2>/dev/null) \
   --out "$S/runs/s8_gciCC/gate.json" 2>&1 | tail -8
log "=== done"
