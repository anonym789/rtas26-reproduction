#!/usr/bin/env bash
# E4 sec. 14: Micro Blossom's embedded decoding benchmark in batch mode (block at once) against the cycle-accurate
# Verilator model, inside the micro-blossom:e4 container. Identical to run_sim.sh except that USE_LAYER_FUSION is
# absent from the environment: benchmark_decoding.rs tests it for presence (option_env!(..).is_some()), so any value,
# including 0, selects stream mode. In batch mode the program loads layers 0 .. NUM_LAYER_FUSION-2 before the timer
# starts, then loads the last layer and solves in one pass (load-stall interval 0); the latency runs from the last
# layer's load to "decoding finished". MEASUREMENT_CYCLE_NS is unused in this mode and kept only for identity.
# usage: run_sim_batch.sh <graph.json> <defects> <num_layers> <max_round> <tag> [freq_hz]
set -euo pipefail
graph=$1; defects=$2; layers=$3; maxround=$4; tag=$5; freq=${6:-93e6}
src=/root/micro-blossom-$tag            # per-slot source copy made by prep_slots.sh (Verilator cache, E4 patches)
if [ ! -d "$src" ]; then echo "missing slot copy $src (run prep_slots.sh first)" >&2; exit 2; fi
cp "$defects" "$src/src/cpu/embedded/embedded.defects"
cd "$src/src/cpu/blossom"
unset USE_LAYER_FUSION
export EMBEDDED_BLOSSOM_MAIN=benchmark_decoding NUM_LAYER_FUSION=$layers MEASUREMENT_CYCLE_NS=1000
export MAX_ROUND=$maxround SUPPORT_LAYER_FUSION=1 SUPPORT_LOAD_STALL_EMULATOR=1 SUPPORT_OFFLOADING=1
export INJECT_REGISTERS=execute,update BUS_TYPE=Axi4 MICRO_BLOSSOM_FREQUENCY=$freq NO_WAVEFORM=1 NO_DEBUGGER_FILES=1
export MB_JAVA_XMX=${MB_JAVA_XMX:-4G}
cargo run --release --features=compact --bin embedded_simulator -- "$graph"
