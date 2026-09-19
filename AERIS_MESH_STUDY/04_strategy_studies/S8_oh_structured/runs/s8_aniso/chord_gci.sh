set -u
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
Q=$R/AERIS_MESH_STUDY/05_s6_cfd_qualification/reports
PY=$R/.venv/bin/python
echo "=== waiting for chord2 $(date -Is)"
while ! grep -q "=== done" "$A/s8_aniso/chord2.out" 2>/dev/null; do sleep 30; done
# Read-only analysis of finished result.json files: it contends for nothing, so it
# may run beside the s0 solve that starts at the same moment.
RUNS_ALPHA() { echo "$A/s8_pilot/g83/gci_C_a$1 $A/s8_aniso/gci_C_chord_a$1 $A/s8_aniso/gci_C_chord2_a$1"; }
$PY $S/convergence_gate.py --runs $(RUNS_ALPHA 0) $(RUNS_ALPHA 4) --out $Q/s8_chord_gate.json | sed -n '3,9p'
# Ratios are INTERVAL ratios in the one direction that refined: directional_level
# takes 44 -> 57 -> 74 chordwise intervals. (N1/N2)^(1/3) would return ~1.09.
CELLS='{"gci_C":567256,"gci_C_chord":744828,"gci_C_chord2":974800}'
for AL in 0 4; do
  echo "=== chordwise GCI, alpha $AL"
  $PY $S/gci.py --runs $(RUNS_ALPHA $AL) --cells "$CELLS" --ratios 1.2982 1.2955 \
    --gate $Q/s8_chord_gate.json --out $Q/s8_chord_gci_a$AL.json | sed -n '/grids, finest/,$p'
done
echo "=== reference: global gci_M CDp  a0 0.009079  a4 0.007760  (1,111,152 cells)"
echo "=== done $(date -Is)"
