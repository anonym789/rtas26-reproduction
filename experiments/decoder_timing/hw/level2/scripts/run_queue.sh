#!/usr/bin/env bash
# E4 level 2: run a list of simulation jobs on N parallel slots inside the container.
# jobs file lines: <graph.json> <defects> <num_layers> <freq_hz> <log name>
# Each slot has its own source copy (/root/micro-blossom-slot<k>); finished jobs (SIM_EXIT 0) are skipped.
# Optional environment (sec. 14): SIM = driver script (default run_sim.sh, stream mode; run_sim_batch.sh for batch
# mode), LOGDIR = log directory (default /root/level2/logs), STAGGER = seconds between slot starts (default 25).
set -u
jobs=$1; nslots=$2; prefix=${3:-slot}
sim=${SIM:-/root/level2/run_sim.sh}; logdir=${LOGDIR:-/root/level2/logs}; stagger=${STAGGER:-25}
mkdir -p "$logdir"
for ((s = 0; s < nslots; s++)); do
  (
    sleep $((s * stagger))   # stagger slot starts: sbt hits the inotify instance limit when many start at once
    awk -v n="$nslots" -v s="$s" 'NR % n == s' "$jobs" | while read -r graph defects layers freq name; do
      log=$logdir/$name.log
      if [ -f "$log" ] && grep -q "SIM_EXIT 0" "$log"; then continue; fi
      "$sim" "$graph" "$defects" "$layers" 0 "$prefix$s" "$freq" > "$log" 2>&1
      echo "SIM_EXIT $?" >> "$log"
    done
  ) &
done
wait
echo "QUEUE_DONE $(date -Is)"
