#!/usr/bin/env bash
# E4 sec. 14: prepare per-slot source copies for a rerun from the slot copies of the stream run, so that the compiled
# Verilator model (SpinalHDL cache simWorkspace/MicroBlossomHost/.cache, keyed by a hash of the generated RTL) and the
# Rust build are reused, then apply the print-only matching patch (e4m_apply.py, = patches/e4_matching.diff).
# usage: prep_slots.sh <source prefix> <new prefix> <n slots> [source slot map: "k:j ..."]
#   copies /root/micro-blossom-<source prefix><j> to /root/micro-blossom-<new prefix><k> for k = 0 .. n-1
#   (j = k unless remapped, e.g. "0:0 1:2 2:4" to give every new slot a source slot holding a given graph's model)
set -euo pipefail
from=$1; to=$2; n=$3; map=${4:-}
declare -A src
for kv in $map; do src[${kv%%:*}]=${kv##*:}; done
for ((k = 0; k < n; k++)); do
  j=${src[$k]:-$k}
  dst=/root/micro-blossom-$to$k
  rm -rf "$dst"
  cp -a "/root/micro-blossom-$from$j" "$dst"
  python3 /root/level2/e4m_apply.py "$dst"
done
echo "PREP_DONE $to: $n slots"
