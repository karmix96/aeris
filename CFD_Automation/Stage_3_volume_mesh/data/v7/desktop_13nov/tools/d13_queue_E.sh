#!/bin/bash
# 13 Nov desktop plan, block E after G1, M1, M2 (Mike: "E387 ... after G1, M1, M2"): E1 SA + LM, E2 SA-BCM, 2-D, on the
# recipe; waits for the ADflow queue (runs/d13_queue.sh) to end so that one run goes at a time.
cd /home/mike_kara/aeris/CFD_Automation/Stage_3_volume_mesh
T=data/v7/su2_transition/tools; Q=runs/d13_queue_log.txt
while pgrep -f "runs/d13_queue.sh" > /dev/null || pgrep -f "solve/run_adflow.py" > /dev/null; do sleep 30; done
echo "$(date '+%F %T') E queue begins (the ADflow queue ended)" >> $Q
run() { [ -f runs/STOP_D13 ] && { echo "$(date '+%F %T') STOP_D13: skipping $2" >> $Q; return; }; echo "$(date '+%F %T') start $2" >> $Q; "$@" >> $Q 2>&1; echo "$(date '+%F %T') end $2" >> $Q; }
run $T/run_su2.sh E1 runs/d13_E e1_sa_lm.cfg E1_sa_lm
run $T/run_su2.sh E2 runs/d13_E e2_sa_bcm.cfg E2_sa_bcm
echo "$(date '+%F %T') d13 E queue done" >> $Q
