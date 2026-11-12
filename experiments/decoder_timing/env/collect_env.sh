#!/usr/bin/env bash
# Writes env/ENVIRONMENT.md: machine, kernel, CPU frequency and isolation state, software and the decoder
# sources and build flags of the timing drivers.
#   env/collect_env.sh [measurement core] [python]      (defaults: 0, .venv/bin/python)
set -u
cd "$(dirname "$0")/.."
CORE="${1:-0}"
PY="${2:-.venv/bin/python}"
{
echo "# Measurement environment"
echo
echo "Generated $(date -Is) by \`env/collect_env.sh\`."
echo
echo "## Machine"
echo '```'
lscpu | grep -E "Model name|Socket|Core\(s\)|Thread\(s\)|NUMA node\(s\)|L1d|L1i|L2|L3|CPU max MHz|CPU min MHz|Frequency boost"
free -g | head -2
echo "kernel: $(uname -r)  ($(uname -v))"
echo "os: $(. /etc/os-release && echo "$PRETTY_NAME")"
echo '```'
echo
echo "## CPU frequency / isolation state at collection time"
echo '```'
echo "scaling_driver: $(cat /sys/devices/system/cpu/cpu$CORE/cpufreq/scaling_driver)"
echo "governor cpu$CORE: $(cat /sys/devices/system/cpu/cpu$CORE/cpufreq/scaling_governor)"
echo "boost (/sys/devices/system/cpu/cpufreq/boost): $(cat /sys/devices/system/cpu/cpufreq/boost 2>/dev/null || echo n/a)"
echo "isolated cpus (/sys/devices/system/cpu/isolated): '$(cat /sys/devices/system/cpu/isolated)'"
echo "nohz_full: '$(cat /sys/devices/system/cpu/nohz_full 2>/dev/null)'"
echo "cmdline: $(cat /proc/cmdline)"
echo "perf_event_paranoid: $(cat /proc/sys/kernel/perf_event_paranoid)"
echo "measurement core: $CORE (siblings $(cat /sys/devices/system/cpu/cpu$CORE/topology/thread_siblings_list), L3 shared with $(cat /sys/devices/system/cpu/cpu$CORE/cache/index3/shared_cpu_list))"
echo "TSC: $(grep -o -m1 'constant_tsc\|nonstop_tsc' /proc/cpuinfo | sort -u | tr '\n' ' ') -> rdtsc runs at nominal rate; HW cycles taken from perf_event PERF_COUNT_HW_CPU_CYCLES instead"
echo "loadavg: $(cat /proc/loadavg)   users: $(who | wc -l)"
echo '```'
echo
echo "## Software"
echo '```'
echo "python: $("$PY" --version 2>&1)"
"$PY" -m pip freeze 2>/dev/null
echo "gcc: $(gcc --version | head -1)"
echo "g++: $(g++ --version | head -1)"
echo "cmake: $(cmake --version | head -1)"
echo "rustc: $(${CARGO_HOME:-$HOME/.cargo}/bin/rustc --version 2>/dev/null || rustc --version)"
echo "cargo: $(${CARGO_HOME:-$HOME/.cargo}/bin/cargo --version 2>/dev/null || cargo --version)"
echo '```'
echo
echo "## Decoder sources and build flags"
echo '```'
PMSRC="drivers/pymatching/build/_deps/pymatching-src"
if [ -d "$PMSRC" ]; then echo "PyMatching (C++ driver): $(git -C $PMSRC describe --tags --always) commit $(git -C $PMSRC rev-parse HEAD)"; fi
STIMSRC="drivers/pymatching/build/_deps/stim-src"
if [ -d "$STIMSRC" ]; then echo "Stim C++ (via PyMatching FetchContent): commit $(git -C $STIMSRC rev-parse HEAD)"; fi
echo "pm_timing flags: -O3 -mno-avx2 -std=c++20 (CMAKE_BUILD_TYPE=Release); links libpymatching + libstim built with PyMatching's own CMake (-O3 -mno-avx2)"
FBLOCK="drivers/fusionblossom/Cargo.lock"
if [ -f "$FBLOCK" ]; then grep -A3 'name = "fusion-blossom"' $FBLOCK | tr '\n' ' '; echo; fi
echo "fb_timing: cargo --release (opt-level=3), features remove_blossom_v,dangerous_pointer,u32_index,i32_weight,disable_visualizer (= released wheel minus python_binding); default features (progress_bar) off"
echo "ldpc / stimbposd: pip wheels (versions above); BpDecoder/BpOsdDecoder with omp_thread_count=1, OMP_NUM_THREADS=1"
echo '```'
} > env/ENVIRONMENT.md
echo "wrote env/ENVIRONMENT.md"
