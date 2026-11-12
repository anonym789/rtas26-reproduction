#!/usr/bin/env bash
# Writes env/ENVIRONMENT.md: machine, Python and package versions of the environment that runs the
# experiment. The simulation is deterministic given the seed and measures no time on this machine, so
# the machine only sets the wall time of a run, not its results.
#   env/collect_env.sh [python]      (default: .venv/bin/python)
set -eu
cd "$(dirname "$0")/.."
PY="${1:-.venv/bin/python}"
{
  echo "# Environment"
  echo
  echo "Generated $(date -I) by \`env/collect_env.sh\`."
  echo
  echo "## Machine"
  echo '```'
  lscpu | grep -E "Model name|^CPU\(s\)|Thread\(s\)|Core\(s\)|Socket|CPU max MHz"
  free -g | head -2
  echo "kernel: $(uname -r)"
  echo "os: $(. /etc/os-release && echo "$PRETTY_NAME")"
  echo '```'
  echo
  echo "## Python"
  echo '```'
  echo "$("$PY" --version 2>&1) (multiprocessing start method: $("$PY" -c 'import multiprocessing as m; print(m.get_start_method())'))"
  "$PY" -m pip freeze
  echo '```'
} > env/ENVIRONMENT.md
echo "wrote env/ENVIRONMENT.md"
