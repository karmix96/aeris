set -u
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_ranks
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
GRID=$A/s8_gci83/gci_C_volume.cgns
# Behind chord2 AND s0, so the machine is otherwise idle when timing is taken.
# A scaling curve measured alongside another solve measures the contention.
echo "=== waiting for s0 to finish $(date -Is)"
while ! grep -q "=== done" "$A/s8_aniso/s0_queue.out" 2>/dev/null; do sleep 30; done
sleep 20
echo "host: $(nproc) logical CPUs; $(lscpu | awk -F: '/^Core\(s\) per socket/{c=$2}/^Socket\(s\)/{s=$2} END{print c*s" physical cores"}')"
# FIXED work, not converge-to-target: iteration counts to a residual vary with the
# domain decomposition, so time-to-converge conflates scaling with convergence.
# The same nCycles budget at every rank count isolates the parallel speed-up.
for NP in 1 2 4 6; do
  D=$O/np$NP; mkdir -p "$D"
  echo "=== np $NP $(date -Is)"
  t0=$(date +%s.%N)
  $M/mpirun -np $NP $M/python $S/solve_s8.py --grid "$GRID" --alpha 0 --out "$D" \
    --no-nk --n-cycles 400 --l2 1e-14 --i-have-authorization > "$D/run.log" 2>&1
  t1=$(date +%s.%N)
  it=$(awk '/^ +1 +[0-9]+ +[0-9]+ /{i=$2} END{print i+0}' "$D/run.log")
  echo "  np=$NP wall=$(echo "$t1 - $t0" | bc) s  outer_iters=$it"
done
echo "=== done $(date -Is)"
