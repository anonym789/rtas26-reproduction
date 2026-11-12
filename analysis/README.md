# analysis

Regenerates the three data-driven figures of the paper from one data folder with the layout of `data/zenodo/`:
by default the experiments' data in `../build/data/`, or the recorded data in `../data/zenodo/`.

| Figure in the paper | Folder | Script | Inputs (relative to the data folder) | Outputs (in the folder's `build/`) |
|---|---|---|---|---|
| Fig. 4, per-shot decoding-time distributions (S1) | `decoder_timing/` | `plot_shape.R` | `decoder_timing/raw/` (4 files), `decoder_timing/hw/raw/` (3 files) | `S1.tex`, `S1.pdf`, `S1_stats.csv` |
| Fig. 5, transport time against the number of controllers (N1) | `network/` | `plot.R` | `network/sim/stats/summary.csv`, `network/sim/stats/edge_summary.csv` | `N1.tex`, `N1.pdf` |
| Fig. 7, trip time per configuration (F3) | `trip_time/` | `plot_trip.R` | `trip_time/trip_summary.csv`, and `data/literature/trip_technology.csv` | `F3.tex`, `F3.pdf` |

Figures 1 to 3 and 6 are drawn by hand in TikZ, and Tables 1 and 2 are written by hand; none of them
is generated here.

## Usage

```
make                        # all three figures from ../build/data (make -j3 builds them in parallel)
make DATA=../data/zenodo    # from the recorded data
make OUTPUT=<folder>        # all three into one folder
make -C network             # one figure (DATA= is then the figure's own folder, e.g. ../../data/zenodo/network)
make clean                  # remove the build/ folders
make r-deps                 # install the R packages listed in requirements.R
```

The repository's `make figures` calls this Makefile. Each folder holds one R script and a Makefile, and writes
everything into its own `build/` unless `OUTPUT` is given. A figure is rebuilt only when its script or one of its
input files changes. A script can also be run directly:

```
cd network && Rscript plot.R <output folder> <network data folder>
cd trip_time && Rscript plot_trip.R <output folder> <trip-time data folder> <literature folder>
```

The `.tex` files are TikZ pictures (tikzDevice) that the paper `\input`s. The `.pdf` files are previews:
the Makefile typesets each TikZ file on its own with pdflatex, in the Times text font of IEEEtran.
Citations inside a figure (N1) resolve only in the paper and show as [?] in the preview.

## Requirements

- R 4.1 or newer with dplyr, tidyr, readr, ggplot2 (4.0 or newer), scales, ggh4x and tikzDevice
  (`requirements.R`). Tested with R 4.6.1, ggplot2 4.0.3, ggh4x 0.3.1, tikzDevice 0.12.6, dplyr 1.2.1,
  tidyr 1.3.2, readr 2.2.0 and scales 1.4.0; `renv.lock` lists these and all their dependencies at the tested
  versions (written by `make r-lock` from the installed library, restored by the Docker image).
- pdflatex with the TikZ and Times (psnfss) packages. tikzDevice calls it to measure every label, so it
  is needed for the `.tex` files as well, not only for the previews.
- The data folder `../data/` (see its README).

## The figures

### S1: per-shot decoding time on every platform

Seven panels at a physical error rate of p = 0.001, first pass (`rep == 1`) of each configuration, one
row per platform class:

| Row | Panel | File (relative to `data/zenodo/decoder_timing/`) |
|---|---|---|
| CPU | Sparse Blossom, surface d = 13 | `raw/pymatching_surface_d13_p0.001.csv.gz` |
| CPU | Fusion Blossom, surface d = 13 | `raw/fusionblossom_surface_d13_p0.001.csv.gz` |
| CPU | Chromobius, colour d = 13 | `raw/chromobius_color_d13_p0.001.csv.gz` |
| CPU | BP+OSD, BB [[144,12,12]] | `raw/bposd_bb_d12_p0.001.csv.gz` |
| FPGA and GPU | Relay-BP FPGA (transferred from iteration counts) | `hw/raw/fpga_transfer_relaybp1_bb_d12_p0.001.csv.gz` |
| FPGA and GPU | Micro Blossom, cycle-accurate simulation in batch mode, d = 13 | `hw/raw/fpga_sim_microblossombatch_surface_d13_p0.001.csv.gz` |
| FPGA and GPU | Relay-BP GPU (measured) | `hw/raw/gpu_measured_relaybp1_bb_d12_p0.001.csv.gz` |

Each panel shows a histogram (45 bins on a log axis, own range per panel) and a density, both scaled to
their maximum. The red line is the largest observed time. The dashed line is the d-round budget
d x 1.1 us and the dotted line the Relay-BP iteration limit (the `hard_bound_ns` column of the FPGA
file, 866 us); both are drawn only where they lie within a factor of ten of the data.
`S1_stats.csv` lists the shots, the maximum, the 99.9th percentile and the budget per panel; BP+OSD has
45,461 shots and the Micro Blossom simulation 20,000, the others 100,000.

### N1: transport time against the number of controllers

The 99.9th percentile of the transport time T_up over the simulated steady-state cycles, for scenario S1
(hard outcomes) at Q_c = 64 qubits per controller and a 1.1 us cycle, on the 10GbE link of each
topology: T1 on L4, T2 and both trees on L5-10G, T4 on L6-10G. The left panel forwards every frame, the
right panel aggregates; T1 and T4 do not aggregate and are repeated in the right panel for reference.

`summary.csv` holds the sweep over N, `edge_summary.csv` the largest stable and the first unstable N of
each series that saturates, so that every line runs to the point where its port saturates. A cross
marks the last stable point of such a series. The dotted lines mark the system sizes
|Q| = 20 * 10^3 and |Q| = 10^6 from the text at the round controller counts N = 300 and 16,000 (for
Q_c = 64 the exact values are 312.5 and 15,625). The grey axis inside each panel gives the number of
physical qubits for Q_c = 64.

### F3: trip time per configuration

One row per decoder configuration in the plot set (`in_plot_set` in `trip_summary.csv`): 37
configurations, 14 of which are known only by a published mean. Each row carries three qubit
technologies, offset vertically within the row: trapped ion (QCCD) above, superconducting on the row,
neutral atom below. The trapped-ion chain is left out, because its readout (8.63 ms) nearly coincides
with the neutral atom's (10 ms).

For each technology the row shows the p50 (open circle) and the p99.9 (filled square) joined by a line,
or a single open triangle at the published mean, and a bar at the maximum where it is known. A cross
marks an unstable configuration (`stability == "unstable"`, decoder utilisation above one): 13
superconducting and 2 neutral-atom rows. The vertical lines come from `technology.csv`: the 10 us
reaction budget of superconducting resource estimates (solid, `D_react_ns`) and the coherence time of
each technology (dotted, `T_coh_ns`).

Panels group the rows by code family (surface, colour, BB) and distance d; within a panel the
superconducting median grows upwards. Row labels name the decoder by its algorithm, the platform with a
tag for published means (lit.), values transferred from measured iteration counts (transf.) and
cycle-accurate simulation (sim.), and the interconnect: direct serial link, RoCE to a host CPU,
NVQLink to a GPU, or the 10GbE aggregator star at N = 8 controllers. F3 is as wide as the IEEEtran
text (516 pt) and is included unscaled; S1 and N1 are 17.8 cm wide.

## What is not reproduced here

The figures are drawn from recorded data. Producing that data needs the experiment code in
`../experiments/` and, for the measurements, the original hardware: the CPU decoder timings, the Relay-BP
FPGA transfer and GPU runs, the Micro Blossom cycle-accurate simulation and the network simulation. See
the README files there and `../data/README.md` for which experiment produced which file.

`trip_summary.csv` is assembled from the per-shot data of the decoder experiments, the network summary
and the trip-time parameters in `data/literature/`; `../experiments/trip_time/` assembles its 148
configurations from the data in this package and checks them against the recorded rows (`make check` there).
