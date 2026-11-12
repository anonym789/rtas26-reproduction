# Timing of QEC decoders

Per-shot decoding times of five decoders on three code families, measured on one CPU core, with their
statistics and probabilistic worst-case execution times (pWCET). The paper's Fig. 4 (S1) is drawn from the
raw files by `analysis/decoder_timing`; the statistics feed the trip-time study. The hardware experiment
(FPGA, GPU, Micro Blossom) is in `hw/` and has its own README.

## Codes, decoders and noise model

| code | circuit | d | decoders |
|---|---|---|---|
| surface | Stim `surface_code:rotated_memory_z`, noise stripped | 3..17, 21, 25 | PyMatching 2, fusion-blossom, BP+OSD-0 (d <= 15) |
| color | superdense 6.6.6 colour code, Z memory (`clorco`, Gidney & Jones 2023, vendored from Chromobius v1.1.1) | 3..15 | Chromobius, BP+OSD-0 |
| bb | bivariate bicycle [[72,12,6]] (d = 6) and [[144,12,12]] (d = 12), Bravyi et al. 2024 cycle, circuits from tesseract-decoder test data, noise stripped | 6, 12 | BP+OSD-0, BP+LSD-0 |

rounds = d everywhere, p in {1e-3, 3e-3, 5e-3}, 100,000 shots (20,000 for surface d in {21, 25}),
k = 3 interleaved passes (k = 1 for the BB code). One noise model for every code:
`gen.NoiseModel.uniform_depolarizing(p)` (vendored, see `vendor/VENDOR.md`): depolarising after every one-
and two-qubit Clifford gate, idle depolarisation in every gate layer, measurement results flipped and reset
outcomes flipped with probability p. Native per-shot timing (C++/Rust drivers) for PyMatching,
fusion-blossom and Chromobius; Python-timed BP+OSD-0 and BP+LSD-0 (`ldpc` `BpOsdDecoder` /
`BpLsdDecoder`, product-sum BP, 30 iterations, order-0 post-processing).

## Usage

Every setting of the campaign is in `config.toml`: grid, decoders, measurement protocol, checks and the
measurement machine. The sourced speed anchor is a row of `data/literature/decoder_anchors.csv`. The
experiment writes its data into `build/data/decoder_timing/` of the repository (the layout of
`data/zenodo/decoder_timing/`, where the recorded campaign lies if present); it never writes into `data/`.

```
make                # list the targets
make data           # the whole measurement campaign (campaign.sh), on the measurement machine
make stats          # statistics and pWCET fits of the campaign in paths.campaign -> stats/
make sanity         # plausibility checks -> SANITY.md
make check          # regenerate the recorded statistics into build/check/decoder_timing and compare
make test           # unit and regression tests
make syndromes      # circuits, DEMs and detection events, regenerated from the seeds -> syndromes/ (about 1 GB)
make graphs         # fusion-blossom graphs of the surface-code DEMs
make drivers        # the C++/Rust timing drivers
make env            # machine, software and build flags -> env/ENVIRONMENT.md
make clean          # remove this experiment's files under build/ (hw/ stays)
make <target> CONFIG=<file>   # another settings file
```

The Python targets create a virtual environment in `.venv` with Python 3.12 and the pinned versions in
`env/requirements.txt`. `make check` computes the statistics of the recorded campaign
(`data/zenodo/decoder_timing`) into `build/check/decoder_timing/` and requires them to be identical to the recorded
ones; the syndrome index of the output is compared when the syndromes have been regenerated (every regenerated grid
point must appear verbatim in the recorded index). Without the recorded campaign the check is skipped. Every stage is also available on its own:

```
.venv/bin/python -m qecdec [--config FILE] syndromes | graphs | stats | sanity [--anchor-only] | check
.venv/bin/python -m qecdec [--config FILE] measure --decoder DEC --code CODE --d D --p P [--core C] [--shots N] [--reps R]
.venv/bin/python -m qecdec [--config FILE] jobs {native,python,anchor,stability}
.venv/bin/python -m qecdec [--config FILE] queue --cores LIST --jobs FILE
.venv/bin/python -m qecdec cores --n 12 --socket 1 [--exclude LIST]
.venv/bin/python -m qecdec [--config FILE] config KEY
```

**The campaign** (`./campaign.sh [CONFIG]`, about 1-2 days) records the environment, sets the CPU governor
(`env/cpufreq.sh`, needs passwordless sudo, otherwise the machine is left as it is), generates syndromes and
graphs, builds the drivers, checks the speed anchor, runs the BP+OSD / BP+LSD jobs in parallel on the 12
quietest L3 complexes of the second socket while the native decoders run one after the other on the
measurement core, then the seed check and the stability rerun, and finally the statistics. It writes into
`build/data/decoder_timing/` and analyses that campaign (the default of `paths.campaign`). Its machine settings are the `[campaign]` section
of `config.toml` (measurement core, BP cores, frequency setting, stop on a failed anchor). From a
workstation, `make push|run|status|pull` drive the campaign on `campaign.host` (the repository is mirrored
under `campaign.remote_root` there; `pull` fetches its output into `build/data/decoder_timing/` here).

**The drivers** fetch PyMatching (tag v2.4.0), Chromobius (tag v1.1.1) and fusion-blossom (rev fa69060)
themselves, and need cmake, a C++20 compiler and cargo. fusion-blossom uses a nightly feature: rustup takes
nightly from `rust-toolchain.toml`; with a stable toolchain build it with `make drivers CARGO="env
RUSTC_BOOTSTRAP=1 cargo"`. Compilers newer than GCC 13 need `CMAKE_ARGS='-DCMAKE_CXX_FLAGS=-include\
cstdint'` for the fetched Stim sources.

## Layout

| Path | Content |
|---|---|
| `config.toml` | paths, grid, decoder settings, measurement protocol (passes, warm-up, floor, budgets), checks, measurement machine |
| `qecdec/parameters.py` | the parameters as the modules use them, read from `config.toml` and `decoder_anchors.csv` |
| `qecdec/grid.py` | `GridPoint` (code, d, p) with its name, seed, rounds, shots and passes; the campaign's jobs |
| `qecdec/circuits.py` | memory circuits of the three codes with the common noise model |
| `qecdec/syndromes.py` | circuits, DEMs, detection events and `syndromes/index.csv` per grid point |
| `qecdec/fbgraph.py` | PyMatching's merged matching graph as a fusion-blossom graph |
| `qecdec/decoders.py` | the decoders: `NativeDecoder` (timing drivers) and `LdpcDecoder` (BP family, timed in Python) |
| `qecdec/measure.py` | one decoder on one grid point -> tidy raw file, `runs.csv`, `machine_snapshots.csv` |
| `qecdec/machine.py` | load and frequency snapshots, the `perf_event` cycle counter |
| `qecdec/hosttools.py` | the job queue (one pinned core per job) and the choice of quiet L3 complexes |
| `qecdec/stats.py` | statistics and pWCET fits |
| `qecdec/sanity.py` | `SANITY.md` |
| `qecdec/check.py` | comparison of the output with the recorded tables |
| `qecdec/data.py` | `DataDir`: the output folder and the campaign folder every stage receives |
| `qecdec/__main__.py` | command line |
| `campaign.sh` | the measurement campaign |
| `drivers/` | C++/Rust per-shot timing drivers on the PyMatching, Chromobius and fusion-blossom libraries |
| `vendor/` | pinned third-party circuit generators and circuits (`VENDOR.md`) |
| `env/` | pinned requirements, `collect_env.sh`, `cpufreq.sh` |
| `tests/` | unit tests of the settings, grid, syndromes, graphs, statistics and comparison; regression tests against the recorded campaign |

Grid points are value objects (`GridPoint`). A decoder is a strategy looked up by name in
`decoders.DECODERS`: the native ones hand the decoding problem to their driver, the BP family runs in this
process, and both follow the same protocol (call-overhead floor, warm-up, interleaved timed passes). The
timed region is the decode call alone. The settings are read once (`parameters.py`); the output and campaign
folders are passed in.

## Data model (tidy)

**`raw/<decoder>_<code>_d<d>_p<p>.csv.gz`**: one row per timed decode call.

```
decoder,code,d,p,rounds,shot,rep,time_ns,cycles,n_detections,logical_error,logical_flips,bp_iterations,osd_triggered,timing_method
```

`logical_error` is the per-block error (any of the code's observables mispredicted), `logical_flips` the
number of mispredicted observables (12 for the BB codes, 1 otherwise); the per-logical-qubit error rate is
its mean divided by the number of observables. `osd_triggered` is 1 when BP did not converge and the
post-processor ran (OSD for `bposd`, LSD for `bplsd`). `bp_iterations` of a shot with an empty syndrome
repeats the count of the previous decode, because `ldpc` leaves it unchanged when there is nothing to
decode; `osd_triggered` is 0 for every empty syndrome.

`rep` in {1,2,3} is the interleaved pass; the first pass is `rep == 1`, the per-shot minimum is
`groupby(shot).min()`. Shot-level variables (`n_detections`, `logical_error`, `bp_iterations`,
`osd_triggered`) are repeated per row. `cycles` are hardware core cycles from `perf_event`
(`PERF_COUNT_HW_CPU_CYCLES`, user space) and empty if not available. `timing_method` in {native, python,
batch}.

**`raw/runs.csv`**: one row per run (decoder, d, p, subdir): core, seed, shots requested vs. run, floor,
graph-build time, wall time, governor/boost, mean of the first pass. **`raw/machine_snapshots.csv`**: one
row per run and phase (start/end): load average, running processes, logged-in users, core MHz, governor,
boost. **`raw/skipped.csv`**: grid points skipped by the 1 s stop rule. Subfolders `raw/stability/<time>/`,
`raw/seedcheck/`, `raw/anchor_boost_on/`, `raw/anchor_boost_off/` hold the check runs.

**`stats/summary.csv`**: one row per (decoder, code, d, p, basis, statistic):

```
decoder,code,d,p,rounds,timing_method,basis,statistic,value
```

`basis` = `first` (rep 1), `min` (per-shot minimum over the passes) or `shot` (statistics that do not
depend on timing: shots, reps, logical_error_rate, logical_error_rate_per_logical_qubit, num_observables,
mean_n_detections, osd_trigger_fraction, mean_bp_iterations, bp_nonconverged_fraction,
mean_ghz_from_cycles). Timing statistics: mean_ns, median_ns, p90_ns, p99_ns, p999_ns, max_ns, min_ns,
std_ns and the `_per_round` variants (divided by `rounds`); under basis `min` also
`interference_estimate_ns` (mean first minus mean min) and its fraction. `stats/summary_wide.csv` is a
pivot of the first-pass rows plus `*_min` columns.

**`stats/pwcet.csv`**: one row per (decoder, code, d, p, basis): peaks-over-threshold GPD fit
(`scipy.stats.genpareto`, loc = 0) above the 90th percentile: threshold_ns, shape_xi, scale, n_exceedances,
exceedance_fraction, q_1e-6_ns, q_1e-9_ns (time exceeded with probability 1e-6 / 1e-9 per shot under the
fit), per-round variants, empirical max, `fit_ok` and `note`. `fit_ok = 0` if xi > 0.5, or the shape varies
by more than 0.3 or q_1e-9 by more than 3x across thresholds p85..p95, or fewer than 100 exceedances. For
BP+OSD and BP+LSD the tail is fitted on the post-processor-triggered mode only whenever that mode is a
strict subset of the shots. **`stats/pwcet_stability.csv`** holds the fits at all five thresholds,
**`stats/ecdf.csv`** and **`stats/mean_excess.csv`** the empirical CDFs and mean excesses,
**`stats/overhead_floor.csv`** the call-overhead floor per run.

## Measurement decisions

- **Noise model.** Two of the three code families have no circuit generator with Stim's noise model, so
  every code, the surface code included, uses Gidney's `gen.NoiseModel.uniform_depolarizing(p)`. It
  depolarises idle qubits in every gate layer and yields about 1.6x the detection-event density of Stim's
  model at equal p.
- **Speed anchor.** At the fixed 2.0 GHz base clock and the denser noise model PyMatching needs 3,935 ns per
  round at d = 17 (2,223 ns under Stim's model; 1,361 ns with boost on under Stim's model). The harness is
  native and the cycle counter confirms 1.98 GHz; the anchor threshold of 2 x 1 us per round assumes
  PyMatching's published laptop clock and noise model, so `SANITY.md` records it as FAIL by construction.
- **Colour-code circuits.** Stim's `color_code:memory_xyz` lacks the colour/basis detector annotation
  Chromobius needs; the superdense circuits come from the `clorco` generator of the Chromobius repository at
  v1.1.1. Z-basis memory, d up to 15 (13 and 15 for qubit-count parity with surface d = 13).
- **BB circuits.** No public syndrome-cycle generator exists; the circuits are the tesseract-decoder test
  circuits for [[72,12,6]] and [[144,12,12]] (Bravyi et al. cycle), noise stripped and re-applied (commit in
  `vendor/VENDOR.md`). The LSD decoder is `ldpc.BpLsdDecoder` (BP + LSD-0). BB runs use one pass (k = 1)
  of up to 1e5 shots under a 12 h budget; BP+LSD at [[144,12,12]], p >= 3e-3 got only 2,000-4,600 shots.
- **Shared machine.** No batch scheduler: k = 3 interleaved passes, load and frequency snapshots, the
  per-shot minimum and a stability rerun stand in for exclusive access; the BP queue ran on the 12 least
  busy L3 complexes of socket 1 while the native decoders ran on core 96.
- **Skipped points.** BP+OSD-0 colour d = 15 (all p), colour d = 13 (p = 3e-3, 5e-3) and [[144,12,12]]
  (p = 3e-3, 5e-3) exceeded 1 s per shot in the pilot and were not run (`raw/skipped.csv`). Other BP points
  had their shot counts reduced by the time budget (`raw/runs.csv`, `shots_requested` vs `shots`).
- **Plain BP** is implemented but not part of the grid (five decoders in total).

## Results at a glance

All times at the fixed 2.0 GHz base clock of the EPYC 7662. "first" = first interleaved pass, "min" =
per-shot minimum over the passes.

(a) PyMatching (surface) per-round time against the 1,100 ns superconducting period (first / min basis):

| p | mean exceeds at d | p99.9 exceeds at d | max exceeds at d |
|---|---|---|---|
| 1e-3 | 11 / 11 | 3 / 3 | 3 / 3 |
| 5e-3 | 5 / 5 | 3 / 3 | 3 / 3 |

(b) PyMatching max/mean at d = 13: 54 (p=1e-3), 23 (3e-3), 15 (5e-3) on the first pass; 3.9, 5.6, 3.7 on
the per-shot minimum (shared-machine outliers).

(c) BP+OSD-0 on the surface code is bimodal where OSD triggers on a fraction of the shots (p = 1e-3); the
trigger fraction grows monotonically with d and p for every code (surface d=13, p=3e-3: 0.997). On the
colour code OSD triggers from d = 7 on nearly every shot at p = 1e-3 (0.52 at d=7, 0.99 at d=13); on the BB
codes BP almost never converges (0.77 at [[72,12,6]], 1.00 at [[144,12,12]]), so their distributions are
unimodal post-processing time.

Cross-code picture at p = 1e-3 (mean per round, min basis): Chromobius on the colour code costs 5-7x
PyMatching on the surface code at equal d (525 ns vs 92 ns at d=3, 19 us vs 2.2 us at d=13) and 2x less
than fusion-blossom; BP+OSD-0 is 10^3-10^4x slower than the matching decoders on both topological codes; on
the BB codes BP+OSD-0 and BP+LSD-0 cost 0.17 s ([[72,12,6]]) and 0.95-1.0 s ([[144,12,12]]) per shot, i.e.
28-85 ms per round, with LSD slightly slower than OSD at p = 1e-3 and 10-20 s per shot at p >= 3e-3.
Logical error rates per block at p = 1e-3: Chromobius 6.6e-3 (d=3) to 4e-5 (d=15), BP+OSD-0 on the colour
code 3-10x worse than Chromobius; [[144,12,12]] 3.3e-3 per block, 1.5e-3 per logical qubit (both decoders
identical); at p >= 3e-3 the BB codes are above threshold under this model (block error 45-99 %) and the
colour code is near threshold. pWCET fits (GPD above p90, min basis) are stable for 90-100 % of the
native-decoder grid points; PyMatching's q(1e-9) per round settles at 14-20 us for d >= 9, Chromobius' at
85-100 us for d >= 9, fusion-blossom's grows to 540 us at d = 25.

## Methods (paper style)

All measurements were taken on one machine, a dual-socket AMD EPYC 7662 server (64 cores per socket, 4
cores per 16 MB L3 complex, 1 TB RAM, Ubuntu 24.04, kernel 6.8) shared with other users but with root
access; no cores were isolated at boot. For the duration of the campaign the measurement cores ran the
`performance` governor with frequency boost disabled, which pins the clock to the 2.0 GHz base frequency
(confirmed by the ratio of hardware cycles to wall time, 1.98 GHz). Every decoder process is single
threaded and pinned to one physical core with `taskset`; the native decoders ran sequentially on one core,
the belief-propagation decoders in parallel on the twelve least loaded L3 complexes of the other socket,
each alone in its complex. Three code families were measured as Z-basis memory experiments with
`rounds = d`: the rotated planar surface code (Stim's generator, d = 3..17, 21, 25), the superdense 6.6.6
colour code (Gidney and Jones's generator as shipped with Chromobius v1.1.1, d = 3..15) and the bivariate
bicycle codes [[72,12,6]] and [[144,12,12]] with the syndrome cycle of Bravyi et al. (circuits from the
tesseract-decoder test set). All circuits were stripped of noise and re-noised with the same circuit-level
depolarising model (`gen.NoiseModel.uniform_depolarizing(p)`): single- and two-qubit depolarisation after
every Clifford gate, idle depolarisation in every layer, measurement results and reset outcomes flipped,
all with probability p in {1e-3, 3e-3, 5e-3}. Detector error models kept hyperedges (decomposed into
graphlike components only for the matching decoders); 100,000 shots per grid point (20,000 for surface d in
{21, 25}) with one fixed seed each were fed to every decoder. PyMatching 2.4.0, fusion-blossom 0.2.13 and
Chromobius 1.1.1 were timed inside C++ or Rust drivers linked against the libraries, with a monotonic clock
around the decode call only (graph construction and input loading untimed; fusion-blossom decodes
PyMatching's exported matching graph and reaches identical logical error rates). BP+OSD-0 and BP+LSD-0
(`ldpc` 2.4.1, product-sum BP, 30 iterations, order-0 post-processing) were timed through their Python
bindings with `time.perf_counter_ns` around `decode()`; the all-zero-syndrome floor is reported per run.
Hardware cycles were read from `perf_event` outside the timed window. The first 1,000 shots of every file
were decoded untimed as warm-up; every shot was then decoded k = 3 times in interleaved passes (k = 1 for
the BB codes), and statistics are reported for the first pass and for the per-shot minimum, whose
difference (median 2.0 % for PyMatching, 1.3 % fusion-blossom, 1.5 % Chromobius, <= 0.4 % for the BP
decoders) is the interference estimate. Each shot's predicted observables were compared with the sampled
ones (per block and, for the BB codes, per logical qubit). Probabilistic worst-case execution times were
obtained by fitting a generalised Pareto distribution to the exceedances above the 90th percentile and
checking threshold stability from the 85th to the 95th percentile; shots are independent samples by
construction. BP decoders were subject to a wall-clock budget per pass (2 h; 12 h for the BB codes), which
reduced the shot count at large d (`raw/runs.csv`), and grid points whose pilot exceeded 1 s per shot were
skipped (`raw/skipped.csv`).
