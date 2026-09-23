set -u
# Meshes for the 2026-09-24 batch. Three questions, one difference each:
#   g83 gci_C_chord3  -- does the chordwise observed order hold on a 4th level?
#   g83 gci_C_ff60    -- is 40 root chords far enough?  (never tested on forces)
#   g47/g13 chord,chord2 -- is "chordwise is the lever" general, or g83-specific?
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
log(){ echo "$(date +%H:%M:%S) $*"; }
build(){ local LV=$1 IX=$2 OUT=$3
  mkdir -p "$OUT"
  if [ ! -f "$OUT/${LV}_summary.json" ]; then
    log "  build $LV g$IX"
    $V "$S/build_volume.py" --level "$LV" --index "$IX" --out "$OUT" --no-plot3d \
       > "$OUT/${LV}_build.log" 2>&1 || { log "    BUILD FAILED -> $OUT/${LV}_build.log"; return 1; }
  fi
  if [ ! -f "$OUT/${LV}_volume.cgns" ]; then
    log "  cgns  $LV g$IX"
    "$M/python" "$S/write_cgns.py" --blocks "$OUT/${LV}_blocks.npz" \
       > "$OUT/${LV}_cgns.log" 2>&1 || { log "    CGNS FAILED"; return 1; }
  fi
  rm -f "$OUT"/${LV}_*.vtk
  $V -c "
import json;d=json.load(open('$OUT/${LV}_summary.json'))
gib=(2.69+7.23*d['cells']/1e6)*1.05
print(f\"    {d['cells']:>9,} cells  folded {d['negative_cells_all_blocks']}  wall_err {d['volume']['wall_layer_error_m']:.1e}  cap {d['outboard']['first_cell_in_s0']:.3f}  solve~{gib:.1f} GiB\")"
}
build gci_C_chord3 83 "$S/runs/s8_chord3/g83"
build gci_C_ff60   83 "$S/runs/s8_chord3/g83"
for IX in 47 13; do
  build gci_C_chord  $IX "$S/runs/s8_chordgen/g$IX"
  build gci_C_chord2 $IX "$S/runs/s8_chordgen/g$IX"
done
log "=== builds done"
