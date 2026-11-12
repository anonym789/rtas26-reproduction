#!/usr/bin/env bash
# The measurement campaign, on the measurement machine; every setting comes from config.toml ([campaign]):
#     ./campaign.sh [CONFIG]           environment, syndromes, drivers, anchor, sweeps, seed check, stability rerun,
#                                      statistics, SANITY.md (the BP queue runs in parallel; about 1-2 days)
#     ./campaign.sh [CONFIG] analysis  statistics and SANITY.md of the runs in paths.output (build/data/decoder_timing)
# Everything is written into paths.output; the statistics and checks read that campaign, not the recorded one.
set -euo pipefail
cd "$(dirname "$0")"
CONFIG=config.toml; MODE=all
for arg in "$@"; do case "$arg" in analysis) MODE=analysis ;; *) CONFIG="$arg" ;; esac; done
PY=.venv/bin/python
SETTING=("$PY" -m qecdec --config "$CONFIG" config)
OUT="$("${SETTING[@]}" paths.output)"
CORE="$("${SETTING[@]}" campaign.core)"
export PATH="$HOME/.cargo/bin:$PATH"
export OMP_NUM_THREADS=1
QECDEC=("$PY" -m qecdec --config "$CONFIG" --campaign "$OUT")
log() { echo "[$(date -Is)] $*"; }

analysis() {
  log "statistics"; "${QECDEC[@]}" stats
  log "sanity";     "${QECDEC[@]}" sanity || true
  log "env";        env/collect_env.sh "$CORE" "$PY"
}
if [ "$MODE" = analysis ]; then analysis; exit 0; fi

# 1. environment and CPU frequency
mkdir -p "$OUT/raw/logs"
BP_CORES="$("${SETTING[@]}" campaign.bp_cores)"
[ -n "$BP_CORES" ] || BP_CORES="$("${QECDEC[@]}" cores --n 12 --socket "$("${SETTING[@]}" campaign.bp_socket)" --exclude "$CORE")"
SET_CPUFREQ="$("${SETTING[@]}" campaign.set_cpufreq)"
log "measurement core $CORE, BP queue cores $BP_CORES"
QPID=""
cleanup() {
  if [ -n "$QPID" ] && kill -0 "$QPID" 2>/dev/null; then
    log "stopping BP queue (pgid $QPID) and its jobs"
    kill -TERM -- "-$QPID" 2>/dev/null; sleep 2; kill -KILL -- "-$QPID" 2>/dev/null
  fi
  [ "$SET_CPUFREQ" = true ] && env/cpufreq.sh restore
}
trap cleanup EXIT
if [ "$SET_CPUFREQ" = true ]; then env/cpufreq.sh set "$CORE,$BP_CORES"; fi
env/collect_env.sh "$CORE" "$PY"

# 2. syndromes, fusion-blossom graphs, timing drivers
log "syndromes (all codes)"; "${QECDEC[@]}" syndromes
log "fusion-blossom graphs"; "${QECDEC[@]}" graphs
log "drivers"; make --no-print-directory drivers

# 3. speed anchor: the campaign stops if PyMatching is far slower than published
read -r A_DEC A_CODE A_D A_P <<< "$("${QECDEC[@]}" jobs anchor)"
log "anchor"; "${QECDEC[@]}" measure --decoder "$A_DEC" --code "$A_CODE" --d "$A_D" --p "$A_P" --core "$CORE"
"${QECDEC[@]}" sanity --anchor-only || {
  log "ANCHOR FAILED (see $OUT/SANITY.md); set campaign.stop_on_anchor = false to continue"
  [ "$("${SETTING[@]}" campaign.stop_on_anchor)" = false ] || exit 1; }

# 4. BP+OSD / BP+LSD queue in the background (Python-timed, slow; longest jobs first)
JOBS="$OUT/raw/logs/bp_jobs.txt"
"${QECDEC[@]}" jobs python > "$JOBS"
log "BP queue: $(wc -l < "$JOBS") jobs on cores $BP_CORES"
setsid "${QECDEC[@]}" queue --cores "$BP_CORES" --jobs "$JOBS" > "$OUT/raw/logs/bp_queue.log" 2>&1 &
QPID=$!

# 5. native decoders, one after the other on the measurement core
"${QECDEC[@]}" jobs native | while read -r dec code d p; do
  "${QECDEC[@]}" measure --decoder "$dec" --code "$code" --d "$d" --p "$p" --core "$CORE" 2>&1 | tail -1
done

# 6. seed check: the same grid point sampled with another seed
log "seed check"
read -r SC_DEC SC_CODE SC_D SC_P SC_OFFSET <<< "$("${SETTING[@]}" checks.seed_check.decoder) $("${SETTING[@]}" checks.seed_check.code) $("${SETTING[@]}" checks.seed_check.d) $("${SETTING[@]}" checks.seed_check.p) $("${SETTING[@]}" checks.seed_check.seed_offset)"
"${QECDEC[@]}" syndromes --code "$SC_CODE" --d "$SC_D" --p "$SC_P" --outdir "$OUT/syndromes/seedcheck" --seed-offset "$SC_OFFSET"
"${QECDEC[@]}" measure --decoder "$SC_DEC" --code "$SC_CODE" --d "$SC_D" --p "$SC_P" --core "$CORE" \
  --syndromes "$OUT/syndromes/seedcheck" --subdir seedcheck

# 7. wait for the queue, then the stability rerun at a later time of day
log "waiting for BP queue (pid $QPID)"; wait $QPID || log "BP queue reported failures, see $OUT/raw/logs"
TS=$(date +%Y%m%dT%H%M)
log "stability rerun -> raw/stability/$TS"
"${QECDEC[@]}" jobs stability | while read -r dec code d p; do
  "${QECDEC[@]}" measure --decoder "$dec" --code "$code" --d "$d" --p "$p" --core "$CORE" --subdir "stability/$TS"
done

# 8. statistics and checks
analysis
log "done"
