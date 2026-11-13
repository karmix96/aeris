#!/bin/bash
# One ADflow run of the 13 Nov desktop plan (solve/DESKTOP_13NOV.md), with the watchdog (solve/rss_watch.py),
# the host logger (tools/host_watch.py), the start and end times and the exit code (timing.json).
#   run_adflow_d13.sh <run id> <case dir> <cap s> <out dir> <log prefix> [run_adflow.py options...]
# Run from anywhere; works in CFD_Automation/Stage_3_volume_mesh. A hard stop at the cap + 30 min is a safety net
# only (ADflow's own timeLimit = the cap ends the solve first). timeLimit goes as "<cap>.0": ADflow refuses an int
# (11 Nov 23:48, A1 attempt 1: "Datatype for option timeLimit is not valid ... Received data type is <class 'int'>").
set -u
cd /home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh
P=/home/mike_kara/miniconda3/envs/mach-aero/bin
PY=/home/mike_kara/aeris/.venv/bin/python
TOOLS=data/v7/night_11nov/tools
RID=$1; C=$2; CAP=$3; OUT=$4; LP=$5; shift 5
mkdir -p "$OUT"
echo "[$RID] preflight $(date '+%F %T')"
$P/mpirun -np 6 $P/python solve/run_adflow.py --case "$C" --preflight "$@" > "$C/${LP}_preflight_log.txt" 2>&1
PRC=$?
if [ $PRC -ne 0 ] || ! grep -q '"accepted": true' "$OUT/preflight.json" 2>/dev/null; then
  echo "{\"run\": \"$RID\", \"stage\": \"preflight\", \"exit\": $PRC, \"note\": \"preflight failed: no solve\"}" > "$OUT/timing.json"
  echo "[$RID] PREFLIGHT FAILED exit=$PRC"; exit 1
fi
$PY solve/rss_watch.py --match run_adflow.py --out "$OUT/rss.csv" > "$C/${LP}_rss_log.txt" 2>&1 &
W1=$!
HOST_WATCH_MATCH=run_adflow.py $PY $TOOLS/host_watch.py --out "$OUT/host.csv" > "$C/${LP}_host_log.txt" 2>&1 &
W2=$!
CMD="$P/mpirun -np 6 $P/python solve/run_adflow.py --case $C --set-option timeLimit=${CAP}.0 $*"
echo "[$RID] solve $(date '+%F %T'): $CMD"
T0=$(date +%s); U0=$(cut -d' ' -f1 /proc/uptime)
timeout --signal=TERM $((CAP + 1800)) $P/mpirun -np 6 $P/python solve/run_adflow.py --case "$C" \
    --set-option timeLimit=${CAP}.0 "$@" > "$C/${LP}_log.txt" 2>&1
RC=$?
T1=$(date +%s); U1=$(cut -d' ' -f1 /proc/uptime)
# the watchers end 30 s (rss_watch) and up to 120 s (host_watch) after the ranks are gone; one that never saw
# a rank (a solve that died before its first sample) would wait 10 min: stop both after 150 s at most
for i in $(seq 150); do kill -0 $W1 2>/dev/null || kill -0 $W2 2>/dev/null || break; sleep 1; done
kill -TERM $W1 $W2 2>/dev/null; wait $W1 $W2 2>/dev/null
cat > "$OUT/timing.json" <<J
{"run": "$RID", "command": "$CMD", "cwd": "$(pwd)", "start": "$(date -d @$T0 '+%F %T')", "end": "$(date -d @$T1 '+%F %T')",
 "wall_seconds": $((T1 - T0)), "wall_seconds_monotonic": $(echo "$U1 - $U0" | bc), "exit": $RC, "hard_stop_seconds": $((CAP + 1800)), "ranks": 6}
J
$PY solve/read_results.py --case "$C" > "$C/${LP}_read_results.txt" 2>&1
echo "[$RID] done $(date '+%F %T') exit=$RC wall=$((T1 - T0)) s"
