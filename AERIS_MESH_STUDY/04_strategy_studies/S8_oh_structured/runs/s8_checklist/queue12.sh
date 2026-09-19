set -u
# Behind queue11. THE RE-RUN. Two things changed that every campaign number depends on:
#   the tip cap is now wall-resolved (first cell 2 x s0, not 10 -- y+ 0.85, not 4.2)
#   the freestream turbulence is the TMR's chi = 3, not ADflow's unchosen default
# Both were decided on evidence, so both go in at once: one pass, not two. Results go to
# a SEPARATE tree, so the old ones survive for comparison rather than being overwritten.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
Q=$R/AERIS_MESH_STUDY/05_s6_cfd_qualification
V=$R/.venv/bin/python
NEW=$A/s8_v2

echo "=== waiting for queue16.sh $(date -Is)"
while ! grep -q "=== done" "$O/queue16.out" 2>/dev/null; do sleep 60; done
sleep 20

echo "=== 1/4 SA-Edwards again, with the TMR freestream $(date -Is)"
# its friction drag came out 68 % below SA's, which is what a relaminarised boundary
# layer looks like: SA-Edwards drops the ft2 term, so it needs freestream turbulence to
# sustain itself. If chi 3 restores CDv, that explains it and we have a second model.
d=$O/trial/edwards_chi3_a0; mkdir -p "$d"
timeout --kill-after=60 5400 /home/mike_kara/miniconda3/envs/mach-aero/bin/mpirun -np 6 \
  /home/mike_kara/miniconda3/envs/mach-aero/bin/python "$S/solve_s8.py" \
  --grid "$A/s8_gci83/gci_C_volume.cgns" --alpha 0 --no-nk \
  --area-ref "$($V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['83']['half_area_m2'])")" \
  --turbulence-model "SA-Edwards" --turb-res-scale 10000 --eddy-vis-inf-ratio 0.21 \
  --out "$d" --i-have-authorization > "$d/run.log" 2>&1
$V -c "
import json;r=json.load(open('$d/result.json'));f={k.split('_')[-1]:v for k,v in r['functions'].items()}
print(f\"  CL={f['cl']:+.6f} CD={f['cd']:.6f} CDv={f['cdv']:.6f} (SA gives 0.008996) conv={r['converged']}\")" \
  2>/dev/null || echo "  FAILED"

echo "=== 2/4 the ten wings, coarse grid, new cap + TMR freestream $(date -Is)"
$V "$S/run_campaign.py" pilot --level gci_C --ranks 6 --no-nk \
  --eddy-vis-inf-ratio 0.21 --out-root "$NEW" > "$O/rerun_gci_C.log" 2>&1
grep -E "cells,|CL=|abort|FAIL|refus" "$O/rerun_gci_C.log" | tail -8

echo "=== 3/4 the medium grid where it exists: 83, 29, 65, 47, 13 $(date -Is)"
$V "$S/run_campaign.py" pilot --level gci_M --indices 83 29 65 47 13 --ranks 6 \
  --watch-memory --no-nk --eddy-vis-inf-ratio 0.21 --out-root "$NEW" \
  > "$O/rerun_gci_M.log" 2>&1
grep -E "cells,|abort|FAIL|refus" "$O/rerun_gci_M.log" | tail -6

echo "=== 4/4 archive and audit the new tree $(date -Is)"
$V "$S/collect_dataset.py" --runs "$NEW" --out "$Q/dataset_v2" 2>&1 | tail -3
$V "$S/audit_runs.py" --rows "$Q/dataset_v2/rows.json" \
  --out "$Q/reports/s8_archive_audit_v2.json" 2>&1 | tail -6
echo "=== done $(date -Is)"
