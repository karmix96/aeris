set -u
# 2026-09-24 batch. Three decisions, one difference from baseline each.
#
# WHY NOT THE WAKE TEST I PROPOSED ON 2026-09-23: it was answered for free from
# meshes already built and solved. Wake resolution at one chord behind the TE
# correlates with dCD at +0.017 across six variants; the two chordwise variants
# move CD by -16.3 and -26.3 counts while changing wake resolution NOT AT ALL
# (2.9 cells/chord in all three), and the one variant that DOES improve the wake
# (gci_C_normal, 2.9 -> 4.1) moves drag +8.2 counts, the wrong way. The wake
# hypothesis is dead. This batch goes where the data points instead.
#
# 1. g83 gci_C_chordC  -- 35 chordwise, giving 35/45/58/75 and TWO triplets.
#    Decides: does the chordwise observed order (p = 1.91 CD, 1.83 CDp at a0,
#    condition ok, GCI21 11.0 %) hold when checked against itself?  If the two
#    triplets disagree, the chordwise family is no better founded than the
#    global one and nothing should be bought on it.
#
# 2. g83 gci_C_ff60    -- 60 root chords instead of 40. Decides: is the domain
#    big enough? Never tested on forces in this study. If dCD is large, every
#    drag number in the report carries a domain error that no amount of grid
#    refinement would ever expose.
#
# 3. g47 + g13 chord, chord2 -- decides whether "the error is chordwise" is a
#    property of this mesh strategy or of geometry 83. Two more geometries, the
#    same two chordwise steps, same settings. If it does not reproduce, the
#    re-scoping argument dies here rather than after the cloud invoice.
#
# area_ref is PER GEOMETRY (g83 0.39492, g47 0.29775, g13 0.5162). Everything
# else matches the existing runs exactly: ANK-only, SA, L2 1e-6, chi 3.
#
#   bash runs/s8_chordgen/queue.sh
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
log(){ echo "$(date +%H:%M:%S) $*"; }
preflight(){ local need=$1 w=0; while :; do
    local a=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    [ "$a" -ge $(( need * 1024 * 1024 )) ] && { log "    mem ok ${need}<=$(( a / 1048576 )) GiB"; return 0; }
    [ "$w" -ge 900 ] && { log "    REFUSING: $(( a / 1048576 )) GiB free, need $need"; return 1; }
    sleep 30; w=$(( w + 30 )); done; }
run(){ local DIR=$1 CG=$2 AL=$3 AR=$4 NEED=$5 TAG=$6
  [ -f "$DIR/result.json" ] && { log "  $TAG done"; return 0; }
  mkdir -p "$DIR"; preflight "$NEED" || return 1
  log "  $TAG solving"
  "$M/mpirun" -np 6 "$M/python" "$S/solve_s8.py" --grid "$CG" --alpha "$AL" --no-nk \
     --eddy-vis-inf-ratio 0.21 --area-ref "$AR" --out "$DIR" --i-have-authorization \
     > "$DIR/run.log" 2>&1
  if [ -f "$DIR/result.json" ]; then
    $V -c "
import json;r=json.load(open('$DIR/result.json'));f={k.split('_')[-1]:v*1e4 for k,v in r['functions'].items()}
print(f\"    CD {f['cd']:8.3f}  CDp {f['cdp']:8.3f}  CDv {f['cdv']:7.3f}  CL {f['cl']:9.3f}  conv={r['converged']}  iters={r['iterations_completed']}\")"
  else log "    FAILED -- see $DIR/run.log"; fi; }
C3=$S/runs/s8_chord3/g83
log "=== 1. chordwise order stability (g83)"
for AL in 0 4; do run "$C3/gci_C_chordC_a$AL" "$C3/gci_C_chordC_volume.cgns" $AL 0.39492 7 "chordC a$AL"; done
log "=== 2. far-field independence (g83)"
for AL in 0 4; do run "$C3/gci_C_ff60_a$AL"   "$C3/gci_C_ff60_volume.cgns"   $AL 0.39492 8 "ff60 a$AL"; done
log "=== 3. does chordwise dominance generalise?"
for GX in 47:0.29775 13:0.5162; do
  IX=${GX%%:*}; AR=${GX##*:}; G=$S/runs/s8_chordgen/g$IX
  for L in gci_C_chord gci_C_chord2; do
    NEED=9; [ "$L" = gci_C_chord2 ] && NEED=11
    for AL in 0 4; do run "$G/${L}_a$AL" "$G/${L}_volume.cgns" $AL "$AR" $NEED "g$IX $L a$AL"; done
  done
done
log "=== gating"
$V "$S/convergence_gate.py" --runs $(ls -d $C3/*_a[0-9] $S/runs/s8_chordgen/g*/*_a[0-9] 2>/dev/null) \
   --out "$S/runs/s8_chordgen/gate.json" 2>&1 | tail -20
log "=== batch done"
