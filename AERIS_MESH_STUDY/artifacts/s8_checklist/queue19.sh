set -u
# THE RE-RUN: ten wings at gci_C, five at gci_M, wall-resolved tip cap, chi 3.
# Approved by the principal investigator on 2026-09-15 ("approve the re-run with the
# new tip cap") after the tip cap moved drag by +1.5 / +1.7 / +2.3 counts at alpha
# 0 / 4 / 8. Runs after queue18.
#
# The approval covers the TIP CAP. queue17 flags every wing test that moved drag by a
# count or more; if anything other than the tip cap is flagged, or a wing test did not
# finish, the re-run's configuration is still an open decision and this stops without
# starting anything expensive. SU2 and NACA results do not change the wing
# configuration and do not block.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
Q=$R/AERIS_MESH_STUDY/05_s6_cfd_qualification
V=$R/.venv/bin/python

log() { echo "$(date +%H:%M) $*"; }

until grep -q "^=== done" "$O/queue18.out" 2>/dev/null; do sleep 60; done
log "queue18 finished"

others=$(grep -v "^tip cap " "$O/decision_needed.txt" 2>/dev/null || true)
unfinished=$(grep -E "(tip cap|preconditioner a|vis4|far field|trailing edge)[^:]* FAILED|build of .* FAILED" \
             "$O/queue17.out" 2>/dev/null || true)
if [ -n "$others" ] || [ -n "$unfinished" ]; then
  log "=== NOT STARTING THE RE-RUN: it was approved for the tip cap, and something else needs a decision"
  if [ -n "$others" ]; then echo "  other wing tests that moved drag by a count or more:"; echo "$others"; fi
  if [ -n "$unfinished" ]; then echo "  wing tests that did not finish:"; echo "$unfinished"; fi
  echo "=== done $(date -Is)"
  exit 0
fi

log "=== the re-run: gci_C, ten wings, four angles"
$V "$S/run_campaign.py" pilot --level gci_C --ranks 6 --no-nk --eddy-vis-inf-ratio 0.21 \
  --out-root "$A/s8_v2" > "$O/rerun_gci_C.log" 2>&1
log "  gci_C exit $?"
log "=== the re-run: gci_M, five wings, four angles"
$V "$S/run_campaign.py" pilot --level gci_M --indices 83 29 65 47 13 --ranks 6 --watch-memory \
  --no-nk --eddy-vis-inf-ratio 0.21 --out-root "$A/s8_v2" > "$O/rerun_gci_M.log" 2>&1
log "  gci_M exit $?"
log "=== dataset v2 and its audit"
$V "$S/collect_dataset.py" --runs "$A/s8_v2" --out "$Q/dataset_v2" 2>&1 | tail -2
$V "$S/audit_runs.py" --rows "$Q/dataset_v2/rows.json" --out "$Q/reports/s8_archive_audit_v2.json" | tail -4
echo "=== done $(date -Is)"
