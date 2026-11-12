#!/usr/bin/env bash
# E4 level 2: run Micro Blossom's embedded decoding benchmark against the cycle-accurate
# Verilator model (SpinalHDL simulation host), inside the micro-blossom:e4 container.
# usage: run_sim.sh <graph.json> <defects> <num_layers> <max_round> <tag> [freq_hz]
set -euo pipefail
graph=$1; defects=$2; layers=$3; maxround=$4; tag=$5; freq=${6:-93e6}
src=/root/micro-blossom-$tag            # one source copy per concurrent run (embedded.defects is compiled in)
if [ ! -d "$src" ]; then cp -r /root/micro-blossom "$src"; fi
cp "$defects" "$src/src/cpu/embedded/embedded.defects"
cd "$src/src/cpu/blossom"
export EMBEDDED_BLOSSOM_MAIN=benchmark_decoding USE_LAYER_FUSION=1 NUM_LAYER_FUSION=$layers MEASUREMENT_CYCLE_NS=1000
export MAX_ROUND=$maxround SUPPORT_LAYER_FUSION=1 SUPPORT_LOAD_STALL_EMULATOR=1 SUPPORT_OFFLOADING=1
export INJECT_REGISTERS=execute,update BUS_TYPE=Axi4 MICRO_BLOSSOM_FREQUENCY=$freq NO_WAVEFORM=1 NO_DEBUGGER_FILES=1
export MB_JAVA_XMX=${MB_JAVA_XMX:-4G}
cargo run --release --features=compact --bin embedded_simulator -- "$graph"
