# data

The data the experiments and the analysis read; none of them writes into this folder.

- **`literature/`**, tracked in git: sourced constants that no experiment produces, one value per row with its
  source.
- **`zenodo/`**, not in the repository (`.gitignore`, section 3): the recorded campaign of the paper, if present,
  that is the measured timings, the outputs of the long-running simulations and the tables that the paper's
  numbers come from. The experiments' `make check` regenerates these tables from the recorded campaign and
  compares.

The recorded campaign holds what the paper's figures and quoted numbers need, and the reference tables hold the
rows the package regenerates from it (every value as recorded).

Git tracks `literature/`, the README files and `SHA256SUMS`.

## How the scripts find it

The experiments write their own data into `build/data/` of the repository, a tree with the layout of `zenodo/`;
the recorded campaign in `zenodo/` is read only by their `make check`. The figure scripts draw from either tree
(`make figures` from `build/data/`, `make figures DATA=data/zenodo` from the record). Every script gets its
folders from its settings: `paths` in the `config.toml` of `experiments/network`, `experiments/decoder_timing`
and `experiments/decoder_timing/hw`, `DATA` and `LITERATURE` in the Makefiles of `experiments/trip_time` and
`analysis/`. No script reaches the data through a fixed path or a symbolic link.

## Contents

| Folder | Produced by | Contents |
|---|---|---|
| `zenodo/decoder_timing/syndromes/` | E2, `python -m qecdec syndromes` | `index.csv` only; the syndrome samples themselves are regenerated from the seeds |
| `zenodo/decoder_timing/raw/` | E2, `python -m qecdec measure` | per-shot decoding times of the CPU decoders (128 configurations), `runs.csv`, `skipped.csv` |
| `zenodo/decoder_timing/stats/` | E2, `python -m qecdec stats` | `summary.csv` (long format), `summary_wide.csv` |
| `literature/decoder_anchors.csv` | compiled by hand from the literature | the published decoding speed the campaign checks first (Sparse Blossom) |
| `zenodo/decoder_timing/hw/syndromes/` | E4, `python -m qechw syndromes` | `index.csv` of the two grid points (d = 6 and 12, p = 1e-3); the samples are regenerated from the seeds |
| `zenodo/decoder_timing/hw/raw/` | E4, `python -m qechw transfer`, `gpu`, `mb-calibrate` | per-shot times of Relay-BP on the FPGA (transfer, float and int4) and the GPU (host-timed passes; CUPTI pass at d = 12), d = 6 and 12, and of the Micro Blossom batch simulation, d = 9 and 13; `gpu_runs.csv` |
| `zenodo/decoder_timing/hw/level2/` | E4, Micro Blossom cycle-accurate simulation (`hw/level2/scripts/`, `python -m qechw mb-sim`) | the simulation logs: `logs/` (stream mode, artifact syndromes, d = 9), `logs_batch/` (batch mode, artifact batch syndromes and ours, d = 9 and 13) |
| `zenodo/decoder_timing/hw/stats/` | E4, `python -m qechw stats`, `mb-calibrate` | `summary.csv`, `counters.csv`, `level2_batch_correction.csv`, `level2_batch_validation.csv` |
| `literature/micro_blossom/` | third party: the Micro Blossom artifact (see its README) | board latency histograms and batch means the calibration uses |
| `literature/hardware_decoders.csv`, `hardware_decoders_unverified.csv` | compiled by hand from the literature | published hardware decoder latencies with section or page; candidates that could not be verified |
| `literature/network_parameters.csv` | compiled by hand from the literature and IEEE 802.3 | cycle time, reaction budget, controller sizes, bits per outcome, Ethernet framing, node delays, saturation anchor |
| `literature/network_links.csv` | compiled by hand from the paper's network table | rate, latency, framing and source of every link |
| `zenodo/network/load/` | E3, `python -m qecnet load` | `frame_sizes.csv` |
| `zenodo/network/bound/` | E3, `python -m qecnet bound` | analytic bounds, crossings, grids, saturation points |
| `zenodo/network/sim/` | E3, `python -m qecnet simulate` (`raw/`), `python -m qecnet stats` (`stats/`) | simulation runs with their metadata; `stats/summary.csv`, `edge_summary.csv`, check summaries |
| `zenodo/trip_time/` | the trip-time assembly (`experiments/trip_time`) from the E2 and E4 per-shot data, the E3 summary and the trip-time parameters | `trip_summary.csv`, the 148 configurations of F3 |
| `literature/trip_technology.csv`, `trip_interconnect.csv`, `trip_decoder_literature.csv` | compiled by hand from the literature (a source column in every file) | technology, interconnect and literature-decoder parameters of the trip time |

E2 is the CPU decoder experiment (`experiments/decoder_timing/`), E4 the hardware experiment
(`experiments/decoder_timing/hw/`), E3 the network experiment (`experiments/network/`).

## Checksums

`SHA256SUMS` lists every file in this folder except the README files and itself. Check a copy with

```
cd data && sha256sum -c --quiet SHA256SUMS
```

and regenerate the list after data have changed with

```
cd data && find . -type f ! -name SHA256SUMS ! -name README.md | LC_ALL=C sort | xargs -d '\n' sha256sum > SHA256SUMS
```
