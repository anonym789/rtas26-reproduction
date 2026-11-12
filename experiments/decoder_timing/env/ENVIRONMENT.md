# Measurement environment

Generated 2026-10-11T15:23:54+00:00 on im-redstone01 by `scripts/collect_env.sh`.

## Machine
```
Model name:                              AMD EPYC 7662 64-Core Processor
Thread(s) per core:                      2
Core(s) per socket:                      64
Socket(s):                               2
Frequency boost:                         disabled
CPU max MHz:                             2154.2959
CPU min MHz:                             1500.0000
L1d cache:                               4 MiB (128 instances)
L1i cache:                               4 MiB (128 instances)
L2 cache:                                64 MiB (128 instances)
L3 cache:                                512 MiB (32 instances)
NUMA node(s):                            2
               total        used        free      shared  buff/cache   available
Mem:            1003         230          48           1         738         772
kernel: 6.8.0-136-generic  (#136-Ubuntu SMP PREEMPT_DYNAMIC Wed Jul  1 21:53:05 UTC 2026)
os: Ubuntu 24.04.4 LTS
```

## CPU frequency / isolation state at collection time
```
scaling_driver: acpi-cpufreq
governor cpu96: performance
boost (/sys/devices/system/cpu/cpufreq/boost): 0
isolated cpus (/sys/devices/system/cpu/isolated): ''
nohz_full: '                                                                                                                                                                                                                                                          (null)'
cmdline: BOOT_IMAGE=/boot/vmlinuz-6.8.0-136-generic root=UUID=24ed4590-7800-43ad-be60-5e346db02c47 ro crashkernel=256M nvme_core.default_ps_max_latency_us=0 crashkernel=2G-4G:320M,4G-32G:512M,32G-64G:1024M,64G-128G:2048M,128G-:4096M
perf_event_paranoid: 1
measurement core: 96 (siblings 96,224, L3 shared with 96-99,224-227)
TSC: constant_tsc nonstop_tsc  -> rdtsc runs at nominal rate; HW cycles taken from perf_event PERF_COUNT_HW_CPU_CYCLES instead
loadavg: 16.76 16.13 16.64 15/33695 2418759   users: 2
```

## Software
```
python: Python 3.12.3
fusion_blossom    0.2.13
ldpc              2.4.1
matplotlib        3.11.2
numpy             2.5.3
pandas            3.0.6
PyMatching        2.4.0
scipy             1.18.1
sinter            1.16.0
stim              1.16.0
stimbposd         0.2.0
gcc: gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
g++: g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cmake: cmake version 3.28.3
rustc: rustc 1.98.1 (48a229cea 2026-09-01)
cargo: cargo 1.98.1 (797e8a9bc 2026-08-05)
```

## Decoder sources and build flags
```
PyMatching (C++ driver): v2.4.0 commit 6f63b2b9474ba0fa7e511fe52bffdce858a06984
Stim C++ (via PyMatching FetchContent): commit 1320ad7eac7de34d2e9c70daa44fbc6d84174450
pm_timing flags: -O3 -mno-avx2 -std=c++20 (CMAKE_BUILD_TYPE=Release); links libpymatching + libstim built with PyMatching's own CMake (-O3 -mno-avx2)
fb_timing: cargo --release (opt-level=3), features remove_blossom_v,dangerous_pointer,u32_index,i32_weight,disable_visualizer (= released wheel minus python_binding); default features (progress_bar) off
ldpc / stimbposd: pip wheels (versions above); BpDecoder/BpOsdDecoder with omp_thread_count=1, OMP_NUM_THREADS=1
```
