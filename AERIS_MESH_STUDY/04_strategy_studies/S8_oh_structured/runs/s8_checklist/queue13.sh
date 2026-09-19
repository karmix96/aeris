set -u
# Behind queue11, ahead of the big re-run. The same wing, the same mesh, the same
# model, a different code. SU2's CGNS reader takes one zone per file and our grid has
# three, so su2_mesh.py welds the blocks into one unstructured hex mesh first --
# 567,256 elements, 16,701 shared nodes merged, the same 4,584 wall faces.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
Q=$R/AERIS_MESH_STUDY/05_s6_cfd_qualification
V=$R/.venv/bin/python
SU2=$R/AERIS_MESH_STUDY/tools/su2_8.5.0/bin/SU2_CFD
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
MESH=$A/su2_check/gci_C.su2
A83=0.394920

echo "=== waiting for queue11.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue11.out" 2>/dev/null; do sleep 60; done
sleep 20

for AL in 0 4; do
  d=$A/su2_check/a$AL
  $V "$S/su2_config.py" --mesh "$MESH" --alpha $AL --area $A83 --out "$d" > /dev/null
  echo "=== SU2, alpha $AL $(date -Is)"
  t0=$(date +%s)
  ( cd "$d" && timeout --kill-after=120 10800 "$M/mpirun" -np 6 "$SU2" case.cfg > run.log 2>&1 )
  echo "  wall=$(( $(date +%s) - t0 )) s exit=$?"
  $V - "$d" <<'PY' 2>/dev/null || echo "  no forces written; see run.log"
import re, sys
from pathlib import Path
text = (Path(sys.argv[1]) / "forces_breakdown.dat").read_text()
def grab(label):
    m = re.search(rf"Total {label}:\s+([-\d.eE+]+)", text)
    return float(m.group(1)) if m else float("nan")
print(f"    SU2   CL={grab('CL'):+.6f} CD={grab('CD'):.6f}")
PY
done

echo "=== the same points from ADflow, for comparison $(date -Is)"
$V - <<'PY'
import json
from pathlib import Path
base = Path("/home/mike_kara/aeris/AERIS_MESH_STUDY/artifacts/s8_pilot/g83")
for al in (0, 4):
    r = json.loads((base / f"gci_C_a{al}/result.json").read_text())
    f = {k.split("_")[-1]: v for k, v in r["functions"].items()}
    print(f"    ADflow a{al}  CL={f['cl']:+.6f} CD={f['cd']:.6f} CDp={f['cdp']:.6f} CDv={f['cdv']:.6f}")
PY
echo "=== done $(date -Is)"
