#!/usr/bin/env bash
# Governor `performance` on the measurement cores, boost off, and perf_event_paranoid low enough for
# user-space cycle counters; `restore` puts back the state found before. Needs passwordless sudo, otherwise
# it leaves the machine as it is.
# Usage: cpufreq.sh set <core>[,<core>...] | restore | status
set -u
SAVE="$(cd "$(dirname "$0")" && pwd)/cpufreq_saved.txt"
BOOST=/sys/devices/system/cpu/cpufreq/boost
PARANOID=/proc/sys/kernel/perf_event_paranoid

status() {
  echo "boost=$(cat $BOOST 2>/dev/null || echo n/a) perf_event_paranoid=$(cat $PARANOID)"
  for c in ${1:-0}; do
    echo "cpu$c governor=$(cat /sys/devices/system/cpu/cpu$c/cpufreq/scaling_governor) cur_mhz=$(( $(cat /sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq) / 1000 ))"
  done
}

case "${1:-status}" in
  set)
    cores="${2//,/ }"
    if ! sudo -n true 2>/dev/null; then echo "no sudo: leaving cpufreq untouched" >&2; exit 0; fi
    # remember the original state once; later calls only add cores not yet recorded
    touch "$SAVE"
    grep -q '^boost=' "$SAVE" || echo "boost=$(cat $BOOST 2>/dev/null || echo none)" >> "$SAVE"
    grep -q '^paranoid=' "$SAVE" || echo "paranoid=$(cat $PARANOID)" >> "$SAVE"
    for c in $cores; do
      grep -q "^gov_$c=" "$SAVE" || echo "gov_$c=$(cat /sys/devices/system/cpu/cpu$c/cpufreq/scaling_governor)" >> "$SAVE"
    done
    for c in $cores; do echo performance | sudo -n tee /sys/devices/system/cpu/cpu$c/cpufreq/scaling_governor >/dev/null; done
    [ -e $BOOST ] && echo 0 | sudo -n tee $BOOST >/dev/null
    echo 1 | sudo -n tee $PARANOID >/dev/null
    status "$cores"
    ;;
  restore)
    [ -f "$SAVE" ] || { echo "nothing saved"; exit 0; }
    if ! sudo -n true 2>/dev/null; then echo "no sudo" >&2; exit 0; fi
    while IFS='=' read -r k v; do
      case "$k" in
        boost) [ "$v" != none ] && echo "$v" | sudo -n tee $BOOST >/dev/null ;;
        paranoid) echo "$v" | sudo -n tee $PARANOID >/dev/null ;;
        gov_*) echo "$v" | sudo -n tee /sys/devices/system/cpu/cpu${k#gov_}/cpufreq/scaling_governor >/dev/null ;;
      esac
    done < "$SAVE"
    rm -f "$SAVE"
    status 0
    ;;
  status) status "${2//,/ }" ;;
esac
