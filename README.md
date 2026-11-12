# Reproduction package: Too late to React? An End-to-End Timing Study of Fault-Tolerant Quantum Computers

This repository reproduces the data-driven figures of the paper and every number its text quotes from them:

| Figure | Content | Drawn by |
|---|---|---|
| Fig. 4 (S1) | per-shot decoding-time distributions of CPU, FPGA and GPU decoders | `analysis/decoder_timing` |
| Fig. 5 (N1) | transport time of a syndrome round from N controllers on 10GbE | `analysis/network` |
| Fig. 7 (F3) | trip time of the correction loop per configuration for three qubit technologies | `analysis/trip_time` |

The other figures and the tables of the paper are drawn or written by hand.

The repository holds code and the literature values the experiments use, but no measured or simulated data: you
produce the data with the experiments, and the figure scripts draw from it.

## Layout

| Path | Content |
|---|---|
| `experiments/network/` | the syndrome network: network-calculus bounds and discrete-event simulation (Python) |
| `experiments/decoder_timing/` | decoding times of five decoders on three code families, measured on a CPU (Python, C++/Rust drivers) |
| `experiments/decoder_timing/hw/` | hardware decoders: Relay-BP on IBM's FPGA design (transferred) and on a GPU (measured), Micro Blossom (cycle-accurate simulation) |
| `experiments/trip_time/` | the trip time of F3, assembled from the decoder and network data (R) |
| `analysis/` | the figure scripts S1, N1, F3 (R, ggplot2, TikZ output) |
| `data/literature/` | values compiled by hand from publications and third-party measurement files, each with its source |
| `data/zenodo/` | the recorded data of the paper's campaign, if present (not in the repository) |
| `build/` | everything the package produces: `build/data/` (the experiments' data), `build/check/`, `build/figures/` |
| `Dockerfile`, `.github/` | the Docker image (see Docker) and the continuous integration |

Each experiment has one settings file (`config.toml`; the trip time, an R script, uses Makefile variables) and one
Makefile with the same targets (`make` lists them), and writes only into `build/data/<experiment>/`, which has the
layout of `data/zenodo/<experiment>/`. Each folder has a README with the methods, the settings and the data model.

## Quick start

```
make test           # unit and regression tests of the experiments (creates their Python environments)
make data           # network simulation, CPU decoder campaign, Relay-BP transfer -> build/data (days, see below)
# GPU runs and Micro Blossom simulation on their machines (see below)
make trip           # trip-time summary
make figures        # S1, N1, F3 -> build/figures/data
```

`make` lists all targets. With the recorded data in `data/zenodo/`:

```
make check                      # regenerate the recorded tables of every experiment and compare
make figures DATA=data/zenodo   # the figures from the recorded data -> build/figures/zenodo
```

## Producing the data

| Step | Command | Needs | Time |
|---|---|---|---|
| network simulation | `make -C experiments/network data` | any machine | about 7 h with 12 workers |
| CPU decoder campaign | `make -C experiments/decoder_timing data` | a quiet multi-core Linux machine; set `[campaign]` in its `config.toml` first (measurement core, cores of the BP queue; the paper used an AMD EPYC 7662 at a fixed 1.98 GHz) | about 1 to 2 days |
| Relay-BP transfer | `make -C experiments/decoder_timing/hw data` | any machine (iteration counts only) | hours to days, mostly the int4 runs |
| Relay-BP on the GPU | `make -C experiments/decoder_timing/hw gpu` (or `gpu-remote`) | an NVIDIA GPU with CUDA-Q QEC 0.8.1 (the paper: A100-SXM4-40GB) | hours |
| Micro Blossom simulation | `make -C experiments/decoder_timing/hw mb-inputs mb-sim mb-collect mb-calibrate` | Docker with the Micro Blossom toolchain container, 32 GB per d = 13 slot (see the hardware README) | days with 25 and 16 parallel slots |
| trip time | `make trip` | the data of all steps above | minutes |

`make data` runs the first three steps. The network simulation, the Relay-BP iteration counts and the Micro
Blossom simulation are deterministic and give the recorded data again; the CPU and GPU timings are new measurements
of your machine.

## Docker

The `Dockerfile` builds an image with every tool of the package: R 4.6.1 with the package versions of
`analysis/renv.lock`, TeX Live, Python 3.12.8, 3.13.1 and 3.14.7 with the experiments' virtual environments, and
the compilers of the CPU timing drivers. `make docker` builds it and runs a target inside, with `build/` mounted for
the outputs and `data/zenodo` mounted read-only when it exists:

```
make docker                                  # make test in the image
make docker TARGET=check                     # make check in the image
make docker TARGET="figures DATA=data/zenodo"
```

The image covers the tests, the checks, the figures and the steps of `make data` that run on any machine. The CPU
campaign measures the machine it runs on, so its timings mean something only on a quiet host; the GPU runs and
the Micro Blossom simulation need their own machines.

## Continuous integration

`.github/workflows/ci.yml` builds the Docker image and runs, inside it, `make test`, `make check` (skipped there,
as the recorded data are not in the repository) and `.github/smoke.sh`, a few runs of every experiment as own data
(minutes) that checks that the steps run and write where the next steps read.

## Make targets

| Target | Does |
|---|---|
| `make data` | the experiments that run on an ordinary machine (network, CPU decoders, Relay-BP transfer) |
| `make trip` | the trip-time summary from `build/data` |
| `make figures [DATA=<folder>]` | S1, N1 and F3 from `build/data` (or another folder with the layout of `data/zenodo`) |
| `make check` | every experiment regenerates the tables of the recorded campaign into `build/check/` and compares them with the record; skipped without `data/zenodo` |
| `make test` | the tests of the three Python experiments |
| `make clean` | remove `build/` and the figure folders' `build/` |
| `make docker [TARGET=...]` | build the Docker image and run a target inside (default `test`) |

## Requirements

- Python 3.14 (network), 3.12 (CPU decoders) and 3.13 (hardware), each experiment in its own virtual environment
  with pinned versions (`env/requirements*.txt`), created by its Makefile; `PYTHON=` names the interpreter.
- R with the packages of `analysis/requirements.R` (`make -C analysis r-deps`; the tested versions of these
  packages and their dependencies are in `analysis/renv.lock`) and pdflatex with TikZ and the Times fonts.
- Or Docker instead of all of these (see above).
- For the CPU campaign: cmake, a C++20 compiler and cargo for the timing drivers (see the CPU README).
- For the GPU runs and the Micro Blossom simulation: the hardware named in the table above.

## Scope

The package covers the configurations the paper's figures and quoted numbers use. The measurement campaign of the
paper covered more (other error rates and decoder variants, Micro Blossom in stream mode, a cost model of Micro
Blossom); those results are not part of this package.
