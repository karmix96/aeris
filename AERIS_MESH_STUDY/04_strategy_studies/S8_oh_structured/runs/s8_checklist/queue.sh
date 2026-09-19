set -u
# Pre-cloud checklist runs (AUDIT_2026-09-10.md next steps), one at a time so no
# two compete for memory and the timing runs see an idle machine (PLAN 0.2).
R=/home/mike_kara/aeris
S=$R/AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured
A=$R/AERIS_MESH_STUDY/artifacts
O=$A/s8_checklist
M=/home/mike_kara/miniconda3/envs/mach-aero/bin
V=$R/.venv/bin/python
G83=$A/s8_gci83/gci_C_volume.cgns

area() { $V -c "import json;print(json.load(open('$S/reference_areas.json'))['areas']['$1']['half_area_m2'])"; }
forces() {
  $V - "$1" "$2" <<'PY' 2>/dev/null || echo "  $2 FAILED"
import json, sys
r = json.load(open(sys.argv[1] + "/result.json"))
f = {k.split("_")[-1]: v for k, v in r["functions"].items()}
res = r.get("relative_residual")
print(f"  {sys.argv[2]} CL={f['cl']:+.6f} CD={f['cd']:.6f} CDp={f.get('cdp', float('nan')):.6f} "
      f"CDv={f.get('cdv', float('nan')):.6f} converged={r.get('converged')} "
      f"res={res if res is None else f'{res:.2e}'}")
PY
}
iters() { awk '/^ +1 +[0-9]+ +[0-9]+ /{i=$2} END{print i+0}' "$1"; }
# timed NAME DIR NP SCRIPT ARGS... ; run.log goes INSIDE the run directory, where the gate looks
timed() {
  local name=$1 dir=$2 np=$3 script=$4; shift 4; mkdir -p "$dir"
  local t0=$(date +%s)
  "$M/mpirun" -np "$np" "$M/python" "$script" "$@" --out "$dir" > "$dir/run.log" 2>&1
  local t1=$(date +%s)
  echo "  $name np=$np wall=$((t1 - t0)) s outer_iters=$(iters "$dir/run.log")"
  forces "$dir" "$name"
}
solve() { timed "$1" "$2" "$3" "$S/solve_s8.py" "${@:4}" --i-have-authorization; }

echo "=== 1/6 gci_FF mesh build, geometry 83, no solve $(date -Is)"
T=""; [ -x /usr/bin/time ] && T="/usr/bin/time -v"
$T $V $S/build_volume.py --level gci_FF --index 83 --out "$O/ff" --no-plot3d > "$O/ff_build.log" 2>&1
grep -oE '"(total_cells|negative_cells_all_blocks)": [0-9]*' "$O/ff_build.log" | tr '\n' ' '
grep -E "Maximum resident" "$O/ff_build.log"; echo

echo "=== 2/6 ONERA M6 L0 L1 L2, ANK only (campaign configuration) $(date -Is)"
for L in 0 1 2; do
  timed "m6_L$L" "$A/onera_m6/run_L${L}_nonk" 6 "$S/onera_m6.py" solve \
    --grid "$A/onera_m6/m6_L$L.cgns" --no-nk
done

echo "=== 3/6 multigrid vs ANK-only, geometry 83 gci_C alpha 0 $(date -Is)"
A83=$(area 83)
solve mg_base  "$O/mg/base" 6 --grid "$G83" --alpha 0 --no-nk --area-ref "$A83"
solve mg_2w    "$O/mg/mg2w" 6 --grid "$G83" --alpha 0 --no-nk --area-ref "$A83" \
  --mg-cycle 2w --smoother DADI --ank-switch-tol 1e-2 --time-limit 3600
solve mg_3w    "$O/mg/mg3w" 6 --grid "$G83" --alpha 0 --no-nk --area-ref "$A83" \
  --mg-cycle 3w --smoother DADI --ank-switch-tol 1e-2 --time-limit 3600

echo "=== 4/6 gci_M on the smallest (47) and largest (13) wing $(date -Is)"
$V $S/run_campaign.py pilot --level gci_M --indices 47 13 --ranks 6 --watch-memory \
  --no-nk > "$O/gciM_pilot.log" 2>&1
grep -E "CL=|abort|FAIL|refus" "$O/gciM_pilot.log" | tail -12
for I in 47 13; do for AL in -2 0 4 8; do
  forces "$A/s8_pilot/g$I/gci_M_a$AL" "g$I gci_M a$AL"; done; done

echo "=== 5/6 chordwise refinement on the smallest and largest wing $(date -Is)"
L=gci_C_chord
for I in 47 13; do
  D=$O/dir_g$I
  $V $S/build_volume.py --level $L --index $I --out "$D" --no-plot3d 2>&1 \
    | grep -oE '"(total_cells|negative_cells_all_blocks)": [0-9]*' | tr '\n' ' '; echo
  $M/python $S/write_cgns.py --blocks "$D/${L}_blocks.npz" > /dev/null 2>&1
  for AL in 0 4; do
    solve "g$I $L a$AL" "$D/${L}_a$AL" 6 --grid "$D/${L}_volume.cgns" --alpha $AL \
      --no-nk --area-ref "$(area $I)"
  done
done

echo "=== 6/6 turbulence model and time-to-residual, geometry 83 gci_C $(date -Is)"
for AL in 0 4; do
  solve "sst a$AL" "$O/sst/a$AL" 6 --grid "$G83" --alpha $AL --no-nk --area-ref "$A83" \
    --turbulence-model "Menter SST" --time-limit 5400
done
# Time to the 1e-6 target, not a fixed cycle budget: the fixed-budget test showed
# outer iterations falling 45 -> 24 with rank count, so only time-to-answer
# measures what a campaign pays. np 6 is mg_base above.
for NP in 1 2 4; do
  solve "ttr np$NP" "$O/ttr/np$NP" $NP --grid "$G83" --alpha 0 --no-nk --area-ref "$A83"
done

echo "=== done $(date -Is)"
