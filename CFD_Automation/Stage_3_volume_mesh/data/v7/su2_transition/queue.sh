#!/bin/bash
# SU2 study queue (13 Nov 2026): one run at a time, no time limit; each run ends at the acceptance rule (monitor.py),
# by hand on a measured stall, or by a crash. Detached so it survives the Claude session (not a WSL shutdown).
T=/home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh/data/v7/su2_transition/tools
Q=/home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh/runs/su2t_VVC_a4/queue_log.txt
run() { [ -f STOP_QUEUE ] && { echo "$(date "+%F %T") STOP_QUEUE: skipping $2" >> $Q; return; }; echo "$(date '+%F %T') start $1" >> $Q; "$@" >> $Q 2>&1; echo "$(date '+%F %T') end $2" >> $Q; }
MONITOR_ARGS="--res-ref -4.734098" run $T/run_su2.sh R1f-cont runs/su2t_VVC_a4 inc_sa_recipe_cont.cfg R1f_cont
run $T/run_su2.sh R2 runs/su2t_VVC_a4 r_sa_lm.cfg R2_sa_lm
run $T/run_su2.sh R3 runs/su2t_VVC_a4 r_sa_bcm.cfg R3_sa_bcm
run $T/run_su2.sh R4 runs/su2t_VVC_a4 r_sst_lm.cfg R4_sst_lm
echo "$(date '+%F %T') queue done" >> $Q
