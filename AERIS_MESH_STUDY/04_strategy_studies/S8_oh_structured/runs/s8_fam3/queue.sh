set -u
# FAMILY 3: family 2 with the blunt base at 0.200 % of chord instead of 0.500 %.
#
# Family 2 already carries the n_base finding for free -- the chordwise rebase
# scales n_base with n_side, so gci2_C has 8 cells across the base, exactly the
# gci_C_nb9 configuration the ladder showed best. Only the OPENING remains.
#
# Builds the whole ladder on g83 and g47 so the cloud meshes exist and are
# verified, then solves the coarse level at alpha 0 and 4 on both geometries to
# measure what the combined change is worth.
#
# gci3 is NOT comparable to gci2 or gci1 as the same design: the opening is made
# by adding thickness to the loft, so this is a different wing. C_L moved 28
# counts across the opening ladder. That is why it has its own name.
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin; V=$R/.venv/bin/python
log(){ echo "$(date +%H:%M:%S) $*"; }
build(){ local LV=$1 IX=$2 O=$S/runs/s8_fam3/g$2
  mkdir -p "$O"
  if [ ! -f "$O/${LV}_summary.json" ]; then
    log "  build $LV g$IX"
    $V $S/build_volume.py --level $LV --index $IX --out "$O" --no-plot3d > "$O/${LV}_build.log" 2>&1 \
      || { log "    BUILD FAILED -> $O/${LV}_build.log"; return 1; }
  fi
  rm -f "$O"/${LV}_*.vtk
  $V -c "
import json,sys,numpy as np
sys.path[:0]=['$S','$S/..','/home/mike_kara/aeris/src']
import strategy_s8 as S
d=json.load(open('$O/${LV}_summary.json')); L=S.LEVELS['$LV']
r=np.load('$O/${LV}_blocks.npz')['o_wing'][:,0,0,:]
ch=float(r[:,0].max()-r[:,0].min()); h=float(np.linalg.norm(r[0]-r[2*L.n_side-2]))
print(f\"    g$IX {'$LV':<8s} {d['cells']:>9,} cells  folded {d['negative_cells_all_blocks']}  \"
      f\"wall {d['volume']['wall_layer_error_m']:.0e}  cap {d['outboard']['first_cell_in_s0']:.2f}  \"
      f\"base {100*h/ch:.3f} % chord, {L.n_base-1} cells  LEturn {d['surface']['worst_le_turn_per_cell_deg']:.2f}  \"
      f\"solve~{(2.69+7.23*d['cells']/1e6)*1.05:.1f} GiB\")"
}
log "=== building family 3"
for IX in 83 47; do for LV in gci3_C gci3_M gci3_F gci3_FF; do build $LV $IX; done; done
run(){ local LV=$1 IX=$2 AR=$3 AL=$4 O=$S/runs/s8_fam3/g$2
  local D=$O/${LV}_a$AL
  [ -f "$D/result.json" ] && { log "  g$IX $LV a$AL done"; return; }
  [ -f "$O/${LV}_volume.cgns" ] || { log "  cgns $LV g$IX"
    "$M/python" $S/write_cgns.py --blocks "$O/${LV}_blocks.npz" > "$O/${LV}_cgns.log" 2>&1 || return 1; }
  mkdir -p "$D"
  while [ "$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)" -lt 11534336 ]; do sleep 30; done
  log "  g$IX $LV a$AL solving"
  "$M/mpirun" -np 6 "$M/python" $S/solve_s8.py --grid "$O/${LV}_volume.cgns" --alpha $AL --no-nk \
     --eddy-vis-inf-ratio 0.21 --area-ref "$AR" --out "$D" --i-have-authorization > "$D/run.log" 2>&1
  [ -f "$D/result.json" ] && $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v*1e4 for k,v in r['functions'].items()}
print(f\"    CD {f['cd']:8.3f}  CDp {f['cdp']:8.3f}  CDv {f['cdv']:7.3f}  CL {f['cl']:9.3f}  conv={r['converged']}  iters={r['iterations_completed']}\")" \
    || log "    FAILED"
}
log "=== solving gci3_C"
for GX in 83:0.39492 47:0.29775; do
  IX=${GX%%:*}; AR=${GX##*:}
  for AL in 0 4; do run gci3_C $IX "$AR" $AL; done
done
log "=== gating"
$V $S/convergence_gate.py --runs $(ls -d $S/runs/s8_fam3/g*/gci3_C_a[0-9] 2>/dev/null) \
   --out $S/runs/s8_fam3/gate.json 2>&1 | tail -8
log "=== done"
