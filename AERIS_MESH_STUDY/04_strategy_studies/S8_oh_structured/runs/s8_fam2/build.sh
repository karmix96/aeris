set -u
# FAMILY 2 meshes: gci_F / gci_FF with the chordwise resolution moved to where
# the 2026-09-24 batch measured the error to be, plus edge spacing that scales
# with the chordwise count, plus a 60-chord far field.
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
V=$R/.venv/bin/python
log(){ echo "$(date +%H:%M:%S) $*"; }
for IX in 83 47; do
  O=$S/runs/s8_fam2/g$IX; mkdir -p $O
  for L in gci2_C gci2_M gci2_F gci2_FF; do
    if [ ! -f "$O/${L}_summary.json" ]; then
      log "  build $L g$IX"
      $V $S/build_volume.py --level $L --index $IX --out $O --no-plot3d > $O/${L}_build.log 2>&1 \
        || { log "    BUILD FAILED -> $O/${L}_build.log"; continue; }
    fi
    rm -f $O/${L}_*.vtk
    $V -c "
import json;d=json.load(open('$O/${L}_summary.json'))
c=d['cells']
print(f\"    g$IX {'$L':<8s} {c:>10,} cells  folded {d['negative_cells_all_blocks']}  wall {d['volume']['wall_layer_error_m']:.1e}  cap {d['outboard']['first_cell_in_s0']:.3f}  LEturn {d['surface']['worst_le_turn_per_cell_deg']:.2f}  solve~{(2.69+7.23*c/1e6)*1.05:.1f} GiB\")"
  done
done
log "=== fam2 builds done"
