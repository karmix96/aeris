set -u
# IS THE BLUNT BASE GRID-LIMITED OR MODEL-LIMITED, AND IS IT TOO BIG?
#
# The base face is 0.50 % of chord (4.337 mm at g83's root), carries 22.4 counts
# -- about a fifth of total pressure drag -- and is the one region where
# refinement DIVERGES: adding wall-normal layers moves base drag +23.1 counts and
# doubles the base suction, on an unchanged base face.
#
# Two ladders, one variable each:
#
#   A. n_base 5 -> 7 -> 9.  Cells ACROSS the face, everything else held.
#      converges -> the face is GRID-limited and more cells fix it.
#      does not  -> MODEL-limited, and no mesh fixes it.
#
#   B. the opening law scaled: (te_abs_m, te_floor_frac) 0.500 % -> 0.300 % ->
#      0.200 % of chord.  How much of the 22 counts, and of the ~10 count
#      coarse-to-medium sensitivity, is an artefact of a default with no recorded
#      justification anywhere in this project?
#
# B IS A GEOMETRY CHANGE. The opening is made by ADDING thickness to the loft, so
# te60 and te40 are different wings and their drag is not comparable to gci_C as
# the same design. That is the point of the test, and it is why it is reported
# separately from A rather than mixed with it.
#
# Regression guard first: rebuild gci_C through the new code path and check it
# reproduces the existing mesh exactly. te_abs_m and te_floor_frac were until
# today unreachable from a level, so this plumbing touches every build.
R=/home/mike_kara/aeris; S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
M=/home/mike_kara/miniconda3/envs/mach-aero/bin; V=$R/.venv/bin/python
O=$S/runs/s8_base
log(){ echo "$(date +%H:%M:%S) $*"; }

log "=== regression: rebuild gci_C through the new code path"
mkdir -p $O/_regress
$V $S/build_volume.py --level gci_C --index 83 --out $O/_regress --no-plot3d > $O/_regress/build.log 2>&1
$V - <<'PYEOF'
import json, numpy as np
from pathlib import Path
S8=Path('/home/mike_kara/aeris/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured')
new=json.load(open(S8/'runs/s8_base/_regress/gci_C_summary.json'))
old=json.load(open(S8/'runs/s8_v2/g83/gci_C_summary.json'))
a=np.load(S8/'runs/s8_base/_regress/gci_C_blocks.npz')['o_wing']
b=np.load(S8/'runs/s8_v2/g83/gci_C_blocks.npz')['o_wing']
d=float(np.abs(a-b).max())
ok = new['cells']==old['cells'] and d==0.0
print(f"    cells {new['cells']:,} vs {old['cells']:,}   max node difference {d:.3e} m   "
      f"{'IDENTICAL - no regression' if ok else '*** MESH CHANGED - STOP ***'}")
Path(S8/'runs/s8_base/_regress/VERDICT').write_text('ok' if ok else 'CHANGED')
PYEOF
[ "$(cat $O/_regress/VERDICT)" = "ok" ] || { log "REGRESSION FAILED -- refusing to continue"; exit 1; }

build(){ local LV=$1
  [ -f "$O/${LV}_summary.json" ] && { log "  $LV built"; return; }
  log "  build $LV"
  $V $S/build_volume.py --level $LV --index 83 --out $O --no-plot3d > $O/${LV}_build.log 2>&1 \
    || { log "    BUILD FAILED"; return 1; }
  [ -f "$O/${LV}_volume.cgns" ] || "$M/python" $S/write_cgns.py --blocks "$O/${LV}_blocks.npz" > $O/${LV}_cgns.log 2>&1
  rm -f $O/${LV}_*.vtk
  $V -c "
import json,sys,numpy as np
sys.path[:0]=['$S','$S/..','/home/mike_kara/aeris/src']
import strategy_s8 as S
d=json.load(open('$O/${LV}_summary.json')); L=S.LEVELS['$LV']
r=np.load('$O/${LV}_blocks.npz')['o_wing'][:,0,0,:]
ch=float(r[:,0].max()-r[:,0].min()); h=float(np.linalg.norm(r[0]-r[2*L.n_side-2]))
print(f\"    {d['cells']:>9,} cells  folded {d['negative_cells_all_blocks']}  n_base {L.n_base}  \"
      f\"base {h*1000:.3f} mm = {100*h/ch:.3f} % chord  ({L.n_base-1} cells across)\")"
}
log "=== building"
for L in gci_C_nb7 gci_C_nb9 gci_C_te60 gci_C_te40; do build $L; done

run(){ local LV=$1 AL=$2
  local D=$O/${LV}_a$AL
  [ -f "$D/result.json" ] && { log "  $LV a$AL done"; return; }
  mkdir -p "$D"
  while [ "$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)" -lt 9437184 ]; do sleep 30; done
  log "  $LV a$AL solving"
  "$M/mpirun" -np 6 "$M/python" $S/solve_s8.py --grid "$O/${LV}_volume.cgns" --alpha $AL --no-nk \
     --eddy-vis-inf-ratio 0.21 --area-ref 0.39492 --out "$D" --i-have-authorization > "$D/run.log" 2>&1
  [ -f "$D/result.json" ] && $V -c "
import json;r=json.load(open('$D/result.json'));f={k.split('_')[-1]:v*1e4 for k,v in r['functions'].items()}
print(f\"    CD {f['cd']:8.3f}  CDp {f['cdp']:8.3f}  CDv {f['cdv']:7.3f}  CL {f['cl']:9.3f}  conv={r['converged']}  iters={r['iterations_completed']}\")" \
    || log "    FAILED"
}
log "=== A: n_base ladder (mesh only)"
for L in gci_C_nb7 gci_C_nb9; do for A in 0 4; do run $L $A; done; done
log "=== B: opening law (GEOMETRY change)"
for L in gci_C_te60 gci_C_te40; do for A in 0 4; do run $L $A; done; done
log "=== gating"
$V $S/convergence_gate.py --runs $(ls -d $O/*_a[0-9] 2>/dev/null) --out $O/gate.json 2>&1 | tail -10
log "=== done"
