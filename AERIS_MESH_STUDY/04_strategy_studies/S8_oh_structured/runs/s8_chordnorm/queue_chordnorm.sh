set -u
# Does the wall-normal increment depend on chordwise resolution?
#
# Refining ONLY the wall-normal direction raises CDp by +4.05 then +6.64 counts and
# gci.py calls the family DIVERGENT, on both mesh families. The diagnosis in
# reports/s8_normal_direction.json is that this is confounded: the family refines the
# direction carrying about -15 % of the coarse-to-fine CDp error while HOLDING the one
# carrying 88 %, so it is refining the non-limiting direction alone.
#
# This tests that by repeating the SAME wall-normal step at a finer chordwise
# resolution:
#
#   at n_side 45:  normal 65 -> 84 moves CDp by +4.054 counts   (measured)
#   at n_side 58:  normal 65 -> 84 moves CDp by ???             (these solves)
#
#   step SHRINKS  -> the directions are coupled, the chordwise error drives it, and a
#                    global refinement (which refines both) is unaffected. The
#                    divergence is an artifact of the test design.
#   step UNCHANGED -> the directions are additive and the wall-normal term is real and
#                    growing. It then matters for the global family and gci_F needs
#                    rethinking before it is bought.
#
# Honest limit, found while designing this: refining n_side does NOT refine the
# leading-edge spacing, which is set by the 10-degree turning target, so the nose cell
# aspect ratio is 25.1 -> 32.1 in BOTH pairs. This therefore tests coupling through the
# mid-chord, not the aspect-ratio hypothesis. It is still the cheapest discriminator
# available; it is not a complete answer.
#
# Meshes already built and clean: 792,852 and 1,033,416 cells, cap 2.042 on both.
#
#   bash runs/s8_chordnorm/queue_chordnorm.sh
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
log() { echo "$(date +%H:%M:%S) $*"; }
preflight() { local need=$1 w=0; while :; do
    local a=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    [ "$a" -ge $(( need * 1024 * 1024 )) ] && { log "    memory ok: $(( a / 1048576 )) GiB"; return 0; }
    [ "$w" -ge 900 ] && { log "    refusing: $(( a / 1048576 )) GiB free, need $need"; return 1; }
    sleep 30; w=$(( w + 30 )); done; }
for AL in 0 4; do
  for L in gci_C_chord_b gci_C_chord_normal_b; do
    D=$S/runs/s8_chordnorm/${L}_a$AL
    [ -f "$D/result.json" ] && { log "  $L a$AL done"; continue; }
    mkdir -p "$D"; preflight 11 || continue
    log "  $L a$AL solving"
    "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" \
      --grid "$S/runs/s8_chordnorm/${L}_volume.cgns" --alpha $AL --no-nk \
      --eddy-vis-inf-ratio 0.21 --area-ref 0.39492 --out "$D" --i-have-authorization \
      > "$D/run.log" 2>&1
    [ -f "$D/result.json" ] && $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CD {1e4*f['cd']:.3f} CDp {1e4*f['cdp']:.3f} CDv {1e4*f['cdv']:.3f} conv={r['converged']}\")" \
      || log "    FAILED"
  done
done
log "=== gating"
$V "$S/convergence_gate.py" --runs $(ls -d $S/runs/s8_chordnorm/*_a[0-9] 2>/dev/null) \
   --out "$S/runs/s8_chordnorm/gate.json" 2>&1 | tail -8
log "=== done"
