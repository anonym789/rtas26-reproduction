# Hardware decoders: FPGA, GPU and Micro Blossom

The hardware experiment of the paper. It gives the FPGA and GPU row of Fig. 4 (S1), the hardware rows of the
trip-time study (F3) and the hardware numbers quoted in the text:

- **Relay-BP on IBM's FPGA design**, transferred: relay-bp counts the BP iterations of every shot of our
  syndromes, and the FPGA's published 24 ns per iteration turns the count into a time;
- **Relay-BP on an NVIDIA A100**, measured: the same configuration in CUDA-Q QEC (`nv-qldpc-decoder`);
- **Micro Blossom**, simulated: the published RTL in a cycle-accurate Verilator simulation, driven by the
  board's own embedded program, corrected with a replay of the board's CPU timeline that is fitted to the
  published board histograms.

Vocabulary: a work count passed through a published per-operation cost, or a simulation, gives an
**input-induced execution-time distribution**; the term pWCET is kept for measured distributions (the CPU
experiment, the GPU); the iteration cap of a design gives a separate **hard bound** (`hard_bound_ns`).

The experiment uses the CPU experiment's package `qecdec` (one folder up) for circuits, syndromes and
statistics; `PYTHONPATH=..` in the Makefile makes it importable.

## Running it

Every setting of a run is in `config.toml`, every step is a target of the `Makefile` (`make` lists them).
The experiment reads the Micro Blossom artifact's files in `data/literature/micro_blossom/` and writes its data
into `build/data/decoder_timing/hw/` of the repository (the layout of `data/zenodo/decoder_timing/hw/`, where the
recorded campaign lies if present); it never writes into `data/`.
The targets that need Python create `.venv` from `env/requirements.txt` on first use (Python 3.13;
`make PYTHON=/path/to/python3.13 ...` if `python3.13` is not on the PATH).

| target | does | runs on |
|---|---|---|
| `make data` | `syndromes`, `transfer` and `stats`: the part that runs on any machine | any machine |
| `make syndromes` | bivariate-bicycle syndromes of the runs (`[syndromes]`) -> `syndromes/` | any machine |
| `make transfer` | Relay-BP iteration counts of every run in `[transfer]` -> `raw/` | any machine (counts only) |
| `make gpu` | Relay-BP on the GPU, every run in `[gpu]` -> `raw/`; locks the SM clock (`sudo -n nvidia-smi -lgc`), records the GPU state in `env/gpu_env.txt`, resets the clock | the GPU machine |
| `make gpu-remote` | `make syndromes gpu` on `gpu.host`: pushes the code and `data/literature`, pulls `raw/gpu_*` and `env/gpu_env.txt` back | any machine with ssh access |
| `make mb-inputs` | the CPU experiment's surface-code syndromes as Micro Blossom input (`microblossom.convert`) -> `level2/inputs/` | any machine |
| `make mb-sim` | the simulation queues (`[[microblossom.queues]]`), each a `docker exec` into `microblossom.container` | the simulation host |
| `make mb-collect` | the campaign's simulation logs to per-shot tables (`microblossom.collect`) -> `level2/` | any machine |
| `make mb-calibrate` | board correction, validation, and the corrected rows (S1's Micro Blossom input) -> `stats/`, `raw/` | any machine |
| `make stats` | statistics of the campaign's raw files -> `stats/` | any machine |
| `make sanity` | plausibility checks -> `SANITY.md` | any machine |
| `make check` | regenerate the recorded tables into `build/check/decoder_timing/hw` and compare | any machine |
| `make test` | unit and regression tests (12 tests, about 25 s) | any machine |
| `make env` | environment record `env/ENVIRONMENT.md` | any machine |
| `make clean` | remove this experiment's folders under `build/` | any machine |

`make <target> CONFIG=<file>` runs a target with another settings file. The command line behind the targets
also runs single runs: `python -m qechw transfer --only 0 1` (indices into the run list), `--force` to redo a
run whose raw file exists. The statistics and the calibration read the campaign in `paths.campaign`, by default
this experiment's own.

`make check` collects, calibrates and computes the statistics of the recorded campaign
(`data/zenodo/decoder_timing/hw`) into `build/check/decoder_timing/hw/` and compares the statistics (`summary.csv`,
`counters.csv`), the calibration tables (`level2_batch_correction.csv`, `level2_batch_validation.csv`) and the
corrected Micro Blossom rows with the recorded ones; all must be identical. The syndrome index of the output is
compared when the syndromes have been regenerated. Without the recorded campaign the check is skipped.

### Relay-BP

```
make syndromes          # d = 6 and 12 at p = 1e-3 (100,000 shots each; the CPU experiment's seeds)
make transfer           # 4 runs; the int4 runs take longest (capped shots cost 36,080 iterations)
make gpu                # on the GPU machine; or set gpu.host and run make gpu-remote
make stats
```

The transfer uses all cores but two (`transfer.workers`). The GPU target installs `env/requirements-gpu.txt`
(CUDA-Q QEC 0.8.1, cupti-python) into the same venv. Without a matching syndrome file the GPU harness falls back
to the CPU experiment's syndromes (`paths.e2_syndromes`).

### Micro Blossom

The simulation runs in the toolchain container of the Micro Blossom repository (commit 468af5d of the
artifact 10.5281/zenodo.14773458; Verilator 5.014, SpinalHDL with sbt, Rust nightly-2023-11-16). Once per
simulation host:

```
docker build --tag micro-blossom:e4 - < micro-blossom/Dockerfile     # in a clone of the repository at 468af5d
# start the container (name: microblossom.container) with the repository at /root/micro-blossom, patched with
# level2/patches/e4_instrumentation.diff (print-only counters in benchmark_decoding.rs, configurable Java heap
# in util.rs), the artifact's board syndromes at /root/board, and level2/scripts/* in /root/level2
```

Then:

```
make mb-inputs           # our syndromes -> level2/inputs/<name>.syndromes, .graph.json (copy them to /root/level2/inputs)
# in the container: defects file and chunks (microblossom.chunks: 2,000 shots x 25 at d = 9, 2,500 x 8 at d = 13)
micro_blossom parser <name>.syndromes --graph-file <name>.graph.json --defects-file <name>.defects
python level2/scripts/split_defects.py <name>.defects chunks/<source>_d<d><tag> <shots per chunk> <chunks>
make mb-sim              # the five queues of config.toml, one after the other
# copy the container's /root/level2/logs* into build/data/decoder_timing/hw/level2/
make mb-collect mb-calibrate stats
```

`mb-sim` generates each queue's job list from `[microblossom.sources]` and `chunks` (one line per chunk and
source: graph, defects file, layers per shot, clock, log name) and hands it to the container on standard input
(`queue_<prefix>.txt`). The two stream queues run first (`s9_`, `s13_`); the batch queues start with
`prep_slots.sh`, which clones their slots with the Verilator cache, so the batch queues reuse the compiled model
(seconds instead of about 4 min at d = 9 and about 2 h at d = 13 per slot). To split the work over two hosts,
run `python -m qechw mb-sim --only 0 2` (d = 9) on one and `--only 1 3 4` (d = 13) on the other; `--dry-run`
prints the commands. The d = 13 design needs a 32 GB Java heap (`java_heap`) and about 17 GB resident memory
per slot. A job (2,000 shots at d = 9, 2,500 at d = 13) takes about 10 to 12 min at d = 9 and 25 to 38 min at
d = 13 in batch mode; stream mode is several times slower, as it simulates the 1 us gaps between rounds.
`run_queue.sh` skips jobs whose log ends with `SIM_EXIT 0`, so a queue can be restarted. The queues simulate
more than the paper uses (the stream queues on our syndromes and the batch queue on the artifact's stream-folder
syndromes); `mb-collect` reads only the log sets of `microblossom.collect`.

## Configuration

| section | holds |
|---|---|
| `[paths]` | the literature folder, the recorded campaign, the campaign to analyse, the output, the CPU experiment's syndromes (relative to `config.toml`) |
| `[syndromes]` | code, distances, error rates, shots; `shared_p` are the error rates whose syndromes are the CPU experiment's (its seeds), others would be seeded with 400000 + 1000 d + round(1e5 p) |
| `[relay]` | the Relay-BP parameters of the FPGA paper, 24 ns per iteration, c0 = 0, and the variants (`relaybp1`, the integer emulation `relaybp1int4`) |
| `[transfer]` | workers, chunk size (chunk k seeds its decoders with 1000 k and 1000 k + 1), per-leg logging, the 4 runs |
| `[gpu]` | GPU host and device, locked SM clock, passes, warm-up, CUPTI and batch settings, the 2 runs, the stopping criterion |
| `[microblossom]` | accelerator clocks and board histograms, layers per shot, the bus read-latency model, which CPU timeline the batch rows use, the conversion list, the container, the chunks, the log sets to collect |
| `[microblossom.sources]` | simulation inputs per source inside the container: graph, defects files, layers |
| `[[microblossom.queues]]` | one entry per simulation queue: slots, mode, log folder, job blocks, Java heap, slot preparation |

## Layout

| path | content |
|---|---|
| `config.toml` | every setting |
| `Makefile` | every step |
| `qechw/config.py` | the settings as value objects (`Relay` and its `RelayVariant`s, `Run`, `Transfer`, `Gpu`, `MicroBlossom` with the job lists, `CollectSet`) |
| `qechw/data.py` | `DataDir`: the output, campaign and literature folders; `RAW_COLUMNS`, the raw-file schema |
| `qechw/xz.py` | split X/Z decoding matrices from a Stim detector error model (H_X from the Z-type detector rows, H_Z from the X-type rows, parallel columns merged) |
| `qechw/syndromes.py` | bivariate-bicycle syndromes and their index |
| `qechw/transfer.py` | Relay-BP iteration counts per shot, in parallel chunks |
| `qechw/gpu.py` | GPU harness: host-timed single-shot passes, CUPTI kernel timing on a subsample, batched throughput |
| `qechw/microblossom/convert.py` | our syndromes in the artifact's input format |
| `qechw/microblossom/logs.py` | simulation logs to per-shot tables |
| `qechw/microblossom/board.py` | the board timeline (`Timeline`, `corrected`, `fit`) and the distribution statistics |
| `qechw/microblossom/calibrate.py` | fit, transfer, validation and the corrected rows, stream and batch mode |
| `qechw/stats.py`, `qechw/sanity.py` | statistics (with `qecdec.stats`) and the plausibility report |
| `qechw/check.py` | comparison of the output with the recorded tables |
| `qechw/__main__.py` | the command line (`python -m qechw --help`) |
| `level2/scripts/` | container side of the simulation: drivers `run_sim.sh` (stream) and `run_sim_batch.sh` (batch), `run_queue.sh`, `prep_slots.sh` with `e4m_apply.py` (applies the matching print), `split_defects.py` |
| `level2/patches/` | print-only instrumentation of the embedded program: counters (`e4_instrumentation.diff`), final matching (`e4_matching.diff`) |
| `env/` | requirements (`requirements.txt`, `requirements-gpu.txt`), `collect_env.sh`, the recorded GPU state `gpu_env.txt`, the CUDA-Q QEC licence |
| `tests/` | configuration, simulation queues and timeline model; GPU harness with a stand-in decoder (`fake_cudaq_qec.py`); regression against the recorded campaign |

The recorded campaign (`paths.data`) holds `raw/` (the per-shot files of the transfer, GPU and corrected Micro
Blossom rows), `level2/logs/` and `level2/logs_batch/` (the simulation logs), `stats/` (the recorded tables)
and `syndromes/index.csv`.

## Data model

`raw/<platform>_<method>_<decoder>_<code>_d<d>_p<p>.csv.gz`, one row per shot, pass and counter:

```
config_id,platform,method,decoder,code,d,p,rounds,shot,rep,counter_name,counter_value,time_ns,hard_bound_ns,logical_error,logical_flips,timing_method,source
```

`config_id = <platform>/<decoder>/<code>/d<d>/p<p>`; `time_ns` repeats on every counter row of a shot.
Counters of the Relay-BP rows: `iterations_x`, `iterations_z` (BP iterations of the X- and Z-error decoder
over all legs), `iterations_window = max(iterations_x, iterations_z)` (the FPGA runs the two decoders in
parallel), `legs_x`, `legs_z` (relay legs, 1 = the first leg converged; -1 beyond the logged shots),
`converged_x`, `converged_z`, and `cpu_wall_ns_x`, `cpu_wall_ns_z` (wall time of the reference run on the
CPU, not a result). GPU rows carry `host_ns_*`; `raw/gpu_cupti_*.csv.gz` holds the CUPTI decomposition
(`kernel_ns_*`, `memcpy_ns_*`, `gpu_span_ns_*`, `n_kernels_*`), `raw/gpu_batch_*.csv` the throughput runs (not in
the record), `raw/gpu_runs.csv` the GPU state per run.
Micro Blossom rows carry the simulation counters (`cycles`, `instructions`, `post_find`, `post_resolve`,
`total_find`, `total_resolve`) and no logical-error flag.

`stats/summary.csv`: one row per configuration with `mean_ns`, `median_ns`, `p90_ns`, `p99_ns`, `p999_ns`,
`max_ns`, the per-round variants, `hard_bound_ns`, `calibration`, `logical_error_rate` and
`above_hard_bound`; `summary_long.csv` is its tidy companion, `counters.csv` the counter statistics,
`pwcet.csv` the generalised-Pareto fits of the CPU experiment with a column that says whether the fit
describes a measured or an input-induced distribution. The statistics read the per-shot files of the transfer,
the simulation and the host-timed GPU passes; the CUPTI decomposition and the throughput runs are separate
measurements in their own files.

## Methods

**Syndromes.** The gross code [[144,12,12]] (d = 12, 12 rounds) and the [[72,12,6]] code (d = 6, 6 rounds) at
p = 1e-3, Gidney's uniform depolarising circuit-level noise, 100,000 shots each: the CPU experiment's syndromes.
Micro Blossom decodes the CPU experiment's rotated surface code at d = 9 and 13, p = 1e-3.

**Relay-BP on the FPGA.** IBM's relay-bp 0.2.2 (Rust core) in split X/Z mode with the configuration of the
FPGA paper (arXiv 2510.21600, captions of Fig. 7 and 8: gamma_0 = 0.125, gamma in [-0.24, 0.66], T_0 = 80,
T_r = 60, R = 600; S = 1) counts, per shot, the BP iterations of each decoder, the relay legs and the
convergence. The window work is max(iterations_X, iterations_Z), and the paper's 24 ns per iteration (12 ns
decoder clock, two clocks per flooding iteration, sec. 5) gives time = 24 ns x iterations; the paper states
no fixed per-call overhead (c_0 = 0). The cap T_0 + R T_r = 36,080 iterations gives the hard bound of
865,920 ns per window. The integer variant uses relay-bp's integer decoder with message magnitudes bounded
to 4 bits plus sign and priors scaled by 2 (the paper's int4.2.8 without the quantisation of the memory
strengths to multiples of 1/8); 20,000 shots per point.

**Relay-BP on the GPU.** NVIDIA CUDA-Q QEC 0.8.1 (`nv-qldpc-decoder`, closed binary) ran the same
configuration (bp_method 3, composition 1, 60 iterations per leg, pre_iter 80, num_sets 600, FirstConv,
fp32) on the same matrices on one A100-SXM4-40GB (driver 580.126.09, CUDA 13.0), SM clock locked at 1410 MHz,
no other GPU process, MPS off. Every single-shot `decode()` was timed on the host with a monotonic clock
(1,000 warm-up calls, three interleaved passes), the X- and Z-error decoders one after the other,
time = host_X + host_Z. On 2,000 shots per point CUPTI recorded every kernel and copy, attributed to its call
by timestamps (CUDA events cannot be placed inside the closed binary), giving the kernel-only time, the GPU
span and the launch and host overhead. Throughput is measured with `decode_batch` at batch sizes 1, 16, 256
and 4,096.

**Micro Blossom.** The repository generates the accelerator's Verilog for a decoding graph and simulates it
cycle by cycle in Verilator, driven over a simulated AXI4 bus by the program that ran on the VMK180 board
(`benchmark_decoding`, offloading, registers injected at execute and update, 4-bit weights). The
instrumentation prints, per shot, the clock cycles from the last layer to the result and the obstacle reads
and resolutions per CPU loop iteration. The simulator treats CPU time as zero and bus transactions as a few
cycles; on the board every loop iteration costs bus latency and primal-module time. The board timeline is
therefore replayed per shot: iteration i costs a + b r_i (r_i obstacles resolved) and cannot start before
its layer is ready. a and b are fitted at d = 9 (93 MHz) to the board histogram of the very same 100,014
syndromes (minimum L1 distance of log-latency quantiles 0.01 to 0.9999) and transferred to d = 13 (62 MHz)
without refitting, scaled by the bus read-latency ratio from the artifact's BRAM speed measurements (1.305);
the d = 13 board histogram is the out-of-sample check. Our syndromes enter in the artifact's format: the
Z-type half of the surface-code graph (the half that carries the logical observable; the design decodes one
basis), weights re-quantised to 4 bits, the boundary merged into two virtual vertices.

The paper's rows decode one block at once, so they use the program's batch mode (`run_sim_batch.sh` unsets
`USE_LAYER_FUSION`; every batch log records `USE_LAYER_FUSION: false`, and the collector refuses logs whose
build parameter does not match the mode). The batch rows use a and b fitted in batch mode to the artifact's
batch board histogram (`microblossom.batch_timeline = "batch fit"`); the stream-mode values, fitted to the
stream-mode board histogram at d = 9, overestimate the batch histogram (mean +28 %, p99.9 +40 % at d = 13) and
stay in the validation table for comparison.

**Statistics.** Mean, median, p90, p99, p99.9, maximum, per-round variants and the peaks-over-threshold fit
come from the CPU experiment's code for every configuration.

## Results

Recorded values; the numbers of the paper come from the files named here, not from this page.

Relay-BP, FPGA transfer (`stats/summary.csv`, `counters.csv`), ns per decode of a d-round block; hard bound
865,920 ns; no shot above it:

| configuration | shots | mean iterations | mean | p50 | p99.9 | max | mean per round | block logical error rate |
|---|---|---|---|---|---|---|---|---|
| fpga/relaybp1/bb/d6/p0.001 | 100,000 | 14.9 | 359 | 144 | 10,464 | 71,808 | 60 | 0.34 % |
| fpga/relaybp1/bb/d12/p0.001 | 100,000 | 30.4 | 729 | 312 | 18,336 | 471,192 | 61 | 0.001 % |
| fpga/relaybp1int4/bb/d6/p0.001 | 20,000 | 38.0 | 913 | 216 | 51,672 | 865,920 | 152 | 0.33 % |
| fpga/relaybp1int4/bb/d12/p0.001 | 20,000 | 83.8 | 2,012 | 672 | 106,297 | 865,920 | 168 | 0 % |

The generalised-Pareto fits in `pwcet.csv` are flagged unstable for every transfer row (discrete iteration
counts with a hard cap); the hard bound is the upper bound of these rows.

Relay-BP, GPU (`stats/summary.csv`, `counters.csv`), us per decode (X plus Z):

| configuration | shots | mean iterations | mean | p50 | p99.9 | max | block logical error rate |
|---|---|---|---|---|---|---|---|
| gpu/relaybp1/bb/d6/p0.001 | 100,000 | 14.7 | 316 | 241 | 3,683 | 49,753 | 0.34 % |
| gpu/relaybp1/bb/d12/p0.001 | 100,000 | 31.3 | 807 | 531 | 12,180 | 615,677 | 0.0030 % |

Micro Blossom in batch mode (`stats/level2_batch_validation.csv`, `level2_batch_correction.csv`,
`summary.csv`), ns per decode. CPU timeline: a = 76 ns, b = 300 ns per resolved obstacle at d = 9 (fit),
a = 99 ns, b = 392 ns at d = 13 (transferred). KS: Kolmogorov-Smirnov distance to the board histogram with a
3 % latency tolerance (the plain distance is dominated by discrete latency levels a few cycles apart):

| d | syndromes | series | shots | mean | p50 | p90 | p99 | p99.9 | max | KS |
|---|---|---|---|---|---|---|---|---|---|---|
| 9 | artifact, batch | board (VMK180) | 100,014 | 600 | 377 | 1,676 | 3,920 | 6,313 | 13,039 | |
| 9 | artifact, batch | simulated, hardware only | 50,000 | 414 | 301 | 968 | 2,301 | 3,806 | 7,548 | 0.393 |
| 9 | artifact, batch | simulated, corrected (fit) | 50,000 | 600 | 377 | 1,644 | 3,877 | 6,561 | 12,724 | 0.002 |
| 13 | artifact, batch | board (VMK180) | 100,014 | 1,689 | 646 | 4,002 | 8,265 | 12,002 | 21,441 | |
| 13 | artifact, batch | simulated, hardware only | 20,000 | 1,245 | 548 | 2,677 | 5,903 | 8,161 | 12,387 | 0.209 |
| 13 | artifact, batch | simulated, corrected (transferred) | 20,000 | 1,849 | 648 | 4,343 | 9,527 | 13,319 | 19,927 | 0.165 |
| 9 | ours (Z-type half) | simulated, corrected | 50,000 | 1,202 | 442 | | | 10,084 | 22,667 | |
| 13 | ours (Z-type half) | simulated, corrected | 20,000 | 4,236 | 3,661 | | | 22,033 | 33,054 | |

The last two rows are `fpga/microblossombatch/surface/d<d>/p0.001` in `summary.csv`, the input of S1 at
d = 13 and of F3.

## Checks

`make sanity` writes `SANITY.md` into the output: IBM's anchor (mean 30.4 iterations, 61 ns per cycle on the gross code
at p = 1e-3), the stream-mode simulation against the board, the batch-mode validation and counters, GPU
stability, hard bounds, noise models.

## Limitations

- **Unit of work.** The Relay-BP rows decode the whole d-round memory experiment as one window (no commit
  region); IBM's FPGA decodes 12-cycle windows. The counts compare with IBM's 12-cycle statements for the
  gross code (12 rounds), not with its sliding-window throughput.
- **Noise model.** Our syndromes use uniform depolarising noise; IBM's and Micro Blossom's published numbers
  use their own circuit-level models, so transferred means are not directly comparable with published means.
- **Integer emulation.** The memory strengths are not quantised as on the FPGA; 20,000 shots per point.
- **Micro Blossom.** Our graphs differ from the published designs (10 instead of 9 layers at d = 9, 402
  instead of 362 vertices) and the clocks of the paper's Table 4 are assumed for them; only one basis is
  decoded (a two-instance system finishes at the later of the two); the CPU timeline at d = 13 is
  transferred, not fitted. No Relay-BP RTL is public, so Relay-BP has no simulation counterpart.
- **GPU.** The NVIDIA SLA of the closed decoder binary (sec. 2.13) restricts disclosure of benchmark results
  to third parties without NVIDIA's permission; check the numbers in `raw/gpu_*` against that clause before
  publication.

## Scope

The package holds the configurations the paper uses (figures and quoted numbers): Relay-BP-1 on the FPGA and
the GPU and the integer emulation at d = 6 and 12, p = 1e-3, and Micro Blossom in batch mode at d = 9 and 13.
The measurement campaign covered more (other error rates, Relay-BP-5, Micro Blossom in stream mode, a cost
model of Micro Blossom fitted to the published mean latencies, a reconstruction of its logical-error flag);
those results are not part of this package.

## Environment

Analysis and transfer: Python 3.13.1 with `env/requirements.txt` (relay-bp 0.2.2, numpy 2.2.6, stim 1.16.0,
ldpc 2.4.1, PyMatching 2.4.0, beliefmatching 0.2.0; pygltflib only for the vendored circuit generators).
GPU: in addition `env/requirements-gpu.txt` (cudaq-qec 0.8.1, cupti-python 13.4.0); the recorded GPU state is
`env/gpu_env.txt`. Micro Blossom: the repository's container (see above). `make env` writes the record of
the current machine to `env/ENVIRONMENT.md`.
