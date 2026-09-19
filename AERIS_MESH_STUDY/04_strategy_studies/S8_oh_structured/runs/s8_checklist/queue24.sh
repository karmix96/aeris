set -u
# THE RE-RUN, with the configuration approved on 2026-09-15 and 2026-09-16:
#   wall-resolved tip cap (2 x s0)     +1.5 / +1.7 / +2.3 counts, and y+ <= 1 is mandatory
#   SA freestream chi 3                the TMR's prescription, not ADflow's default
#   trailing edge 0.1 % of chord       about -10.5 counts at gci_C, -3.8 at gci_M, no extra cells
#   far field 40 root chords           100 is worth +1.5 counts, carried as a stated offset
#   ADflow default dissipation         its error halves per refinement; matrix would not converge
#
# Ten wings at gci_C and three at gci_M (83, and the smallest and largest wings 47 and 13 --
# geometries 29 and 65 were cut because the coarse-to-medium offset already holds across size
# to 7 %). Every mesh is rebuilt: the trailing-edge change moves points on every ring.
#
# Runs after queue23, so the SU2 validation the principal investigator asked to come first is
# not competing with it for cores.
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
Q=$R/AERIS_MESH_STUDY/05_s6_cfd_qualification
V=$R/.venv/bin/python

log() { echo "$(date +%H:%M) $*"; }

until grep -q "^=== done" "$O/queue23.out" 2>/dev/null; do sleep 60; done
log "SU2 validation finished; starting the approved re-run"

log "=== 1/3 gci_C, ten wings, four angles"
$V "$S/run_campaign.py" pilot --level gci_C --ranks 6 --no-nk --eddy-vis-inf-ratio 0.21 \
  --out-root "$A/s8_v2" > "$O/rerun_gci_C.log" 2>&1
log "  gci_C exit $?"

log "=== 2/3 gci_M on 83, 47 and 13"
$V "$S/run_campaign.py" pilot --level gci_M --indices 83 47 13 --ranks 6 --watch-memory \
  --no-nk --eddy-vis-inf-ratio 0.21 --out-root "$A/s8_v2" > "$O/rerun_gci_M.log" 2>&1
log "  gci_M exit $?"

log "=== 3/3 dataset v2 and its audit"
$V "$S/collect_dataset.py" --runs "$A/s8_v2" --out "$Q/dataset_v2" 2>&1 | tail -2
$V "$S/audit_runs.py" --rows "$Q/dataset_v2/rows.json" --out "$Q/reports/s8_archive_audit_v2.json" | tail -5
echo "=== done $(date -Is)"
