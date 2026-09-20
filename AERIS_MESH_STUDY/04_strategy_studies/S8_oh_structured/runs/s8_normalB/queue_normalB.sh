set -u
# Does the wall-normal divergence survive the tip-cap rebuild?
# 2 solves at alpha 0, about 1 hour. THE go/no-go gate for a third grid level.
#
# WHY
#
# On family A, refining only the wall-normal direction at fixed first cell made
# drag WORSE, and faster each step: CD 208.237 -> 209.134 -> 213.330 counts, the
# second step 4.7x the first. `gci.py` returns p = -5.97 and refuses a GCI:
# "this family has no demonstrated limit". A global refinement refines that
# direction too, so gci_F bought while this stands is a third point on a family
# that may have no limit to extrapolate to.
#
# But family A carries the tip cap declared DEFECTIVE on 13 September (y+ 2.9-4.5
# against a mandatory <= 1) and since rebuilt. The production dataset is family B.
# So the one result saying the grid family has no limit was measured on a mesh the
# campaign abandoned.
#
# And there is a specific reason to expect the rebuild to matter. The divergence
# signature is CDp RISING while CDv FALLS as layers are added at fixed s0 -- an
# outer-region effect, not a boundary-layer one. The cap fix changed the outboard
# extrusion from 48 to 54 layers, because a 5x finer cap first cell needs about six
# more layers to reach the same far field. That is exactly the region the signature
# points at.
#
#   decision this changes:
#     divergence GONE on family B  -> the go/no-go gate is clear, the third level
#       can be read, and the cloud pilot is justified.
#     divergence SURVIVES          -> no global refinement is interpretable until
#       the cause is found, and renting hardware first would buy an unreadable
#       point. Next step becomes localisation, not purchase.
#
# EXACTLY ONE DIFFERENCE
#
# The three levels differ in the wall-normal direction only -- layers and first
# cell together at 1.3 and 1.3^2, every other count held -- and ALL THREE now carry
# the same wall-resolved cap at 2.04 x s0. That last part needed fixing in
# `strategy_s8.py` first: `gci_C_normal_s0` inherited a default cap that has since
# moved from 10.0 to 2.0, and `gci_C_normal_s0_2` pinned 10.0 explicitly to match
# it, so rebuilding the family today would have produced 2.0 / 2.0 / 10.0 -- a
# mixed family, with the cap's 1.5-2.3 counts landing inside "the normal
# direction". Both families now state their own cap.
#
#   level 1  gci_C (family B)         603,592 cells   already solved
#   level 2  gci_C_normal_s0_b        787,944 cells   cap 2.042, 0 folded
#   level 3  gci_C_normal_s0_2_b    1,032,648 cells   cap 2.042, 0 folded
#
# Baseline is runs/s8_v2/g83/gci_C_a0 -- same own area 0.39492, moment ref
# [0.4,0,0], chi 3, ANK only, L2 1e-6.
#
#   bash runs/s8_normalB/queue_normalB.sh
#
# Written 2026-09-21. docs/AUDIT_2026-09-20_reliability.md 3.3; the independent
# assessment of commit 7de0861, step 2.

R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
OUT=$S/runs/s8_normalB
AREA=0.39492
MIN_AVAIL_KB=$((1024 * 1024))
MAX_SWAP_KB=$((1536 * 1024))

log() { echo "$(date +%H:%M:%S) $*"; }
[ -x "$M/mpirun" ] || { echo "FATAL: no mpirun at $M/mpirun"; exit 1; }

guarded() {  # TIMEOUT_S LOGFILE CMD...
  local limit=$1 logf=$2; shift 2
  setsid "$@" > "$logf" 2>&1 &
  local pid=$! t0=$(date +%s)
  while kill -0 "$pid" 2>/dev/null; do
    sleep 15
    local free_kb=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    local swap_kb=$(awk '/^SwapTotal:/{t=$2} /^SwapFree:/{f=$2} END{print t-f}' /proc/meminfo)
    if [ "$swap_kb" -gt "$MAX_SWAP_KB" ]; then
      echo "MEMORY GUARD: ${swap_kb} kB swap in use, paging" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "    KILLED: paging"; return 97
    fi
    if [ "$free_kb" -lt "$MIN_AVAIL_KB" ]; then
      echo "MEMORY GUARD: ${free_kb} kB available" >> "$logf"
      kill -TERM -"$pid" 2>/dev/null; sleep 20; kill -KILL -"$pid" 2>/dev/null
      log "    KILLED by the memory guard"; return 99
    fi
  done
  wait "$pid"
}

for L in gci_C_normal_s0_b gci_C_normal_s0_2_b; do
  D=$OUT/${L}_a0
  mkdir -p "$D"
  if [ -f "$D/result.json" ]; then log "  $L a0 already done"; continue; fi
  log "  $L a0 solving (6 ranks, ANK only, chi 3)"
  guarded 9000 "$D/run.log" "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" \
    --grid "$OUT/${L}_volume.cgns" --alpha 0 --no-nk --eddy-vis-inf-ratio 0.21 \
    --area-ref "$AREA" --out "$D" --i-have-authorization
  if [ -f "$D/result.json" ]; then
    $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"    CD {1e4*f['cd']:.3f} ct  CDp {1e4*f['cdp']:.3f}  CDv {1e4*f['cdv']:.3f}  converged={r['converged']}\")"
  else
    log "    FAILED, see $D/run.log"
  fi
done

log "=== gating"
DIRS=$(ls -d $OUT/*_a0 2>/dev/null | tr '\n' ' ')
[ -n "$DIRS" ] && $V "$S/convergence_gate.py" --runs $DIRS --out "$OUT/gate.json" 2>&1 | tail -6

log "=== the wall-normal family, both mesh families, through gci.py"
$V "$S/normal_direction.py" 2>&1 | tail -40
log "=== done"
