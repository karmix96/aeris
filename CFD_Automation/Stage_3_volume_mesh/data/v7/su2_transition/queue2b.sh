#!/bin/bash
# Second queue, version 2 (13 Nov 2026): R5 (ft2), R6 (SA + LM on light VC, asked by Mike), then R3 and R4.
# ft2 test (R5, asked by Mike) before R3 and R4. Same wrapper, monitor and watchdog; no time limit.
D=/home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh/runs/su2t_VVC_a4
T=/home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh/data/v7/su2_transition/tools
Q=$D/queue_log.txt
while pgrep -f "su2t_VVC_a4/queue.sh|^/bin/bash ./queue.sh" > /dev/null || pgrep -x SU2_CFD > /dev/null; do sleep 30; done
rm -f $D/STOP_QUEUE; echo "$(date '+%F %T') queue2 begins (queue.sh ended)" >> $Q
run() { [ -f $D/STOP_QUEUE2 ] && { echo "$(date '+%F %T') STOP_QUEUE2: skipping $2" >> $Q; return; }; echo "$(date '+%F %T') start $2" >> $Q; "$@" >> $Q 2>&1; echo "$(date '+%F %T') end $2" >> $Q; }
run $T/run_su2.sh R5 runs/su2t_VVC_a4 r_sa_ft2.cfg R5_sa_ft2
run $T/run_su2.sh R6 runs/su2t_VVC_a4 r_sa_lm_lightvc.cfg R6_sa_lm_lightvc
run $T/run_su2.sh R3 runs/su2t_VVC_a4 r_sa_bcm.cfg R3_sa_bcm
run $T/run_su2.sh R4 runs/su2t_VVC_a4 r_sst_lm.cfg R4_sst_lm
echo "$(date '+%F %T') queue2 done" >> $Q
