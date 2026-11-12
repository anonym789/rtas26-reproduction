#!/usr/bin/env bash
# Writes env/ENVIRONMENT.md: the GPU record of the last `make gpu` (env/gpu_env.txt), this machine's Python packages,
# and the versions and commits of the decoders and the Micro Blossom toolchain.
#   env/collect_env.sh [python]      (default: .venv/bin/python)
set -u
cd "$(dirname "$0")/.."
PY="${1:-.venv/bin/python}"
{
echo "# Environment of the hardware experiment"; echo
echo "Generated $(date -I) by \`env/collect_env.sh\`."; echo
echo "## GPU (Relay-BP in CUDA-Q QEC)"; echo '```'
cat env/gpu_env.txt 2>/dev/null || echo "env/gpu_env.txt missing (written by make gpu on the GPU machine)"
echo "exclusive use: one process per GPU, no MPS; SM clock locked with nvidia-smi -lgc for the runs (gpu.sm_clock_mhz)"
echo '```'; echo
echo "## Relay-BP transfer and analysis (counters only, independent of the machine)"; echo '```'
echo "machine: $(uname -r); $(lscpu | grep 'Model name' | sed 's/ *Model name: *//')"
echo "python: $("$PY" --version 2>&1)"
"$PY" -m pip freeze 2>/dev/null
echo '```'; echo
echo "## Software versions and commits"; echo '```'
cat <<'TXT'
relay-bp 0.2.2 (PyPI, Rust core; repo github.com/trmue/relay, commit d185194 'Fix syndrome pruning (#42)', Apache-2.0)
cudaq-qec 0.8.1 (PyPI; nv-qldpc-decoder 23f4a805b2cd9494b747df839ac5c3192171404d; closed binary libcudaq-qec-nv-qldpc-decoder.so under the NVIDIA Software License Agreement)
cupti-python 13.4.0 (CUPTI activity API for kernel timing)
Micro Blossom: artifact 10.5281/zenodo.14773458 (data files vendored under vendor_data/micro_blossom); repository commit 468af5d0286a42c58539bec260504423bee81e28
Simulation toolchain: docker image micro-blossom:e4 built from the repository's Dockerfile (ubuntu 22.04)
  Verilator 5.014 2023-08-06 rev v5.014; SpinalHDL 1.9.3, Scala 2.12.12, OpenJDK 11.0.32.1; rustc 1.76.0-nightly (6b771f6b5 2023-11-15)
  patches: level2/patches/e4_instrumentation.diff (print-only counters; Java heap via MB_JAVA_XMX, 4 GB at d = 9, 32 GB at d = 13)
  and level2/patches/e4_matching.diff (print-only final matching, applied by level2/scripts/e4m_apply.py)
  simulation results are cycle counts, independent of the host
Vivado: not used (no synthesis; clocks from Table 4 of arXiv 2502.14787)
TXT
echo '```'
} > env/ENVIRONMENT.md
echo "wrote env/ENVIRONMENT.md"
