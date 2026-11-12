# Trip time

The trip time of the QEC correction loop for the configurations of F3 (Fig. 7 of the paper):

```
T_trip = T_meas + T_syn + T_up + T_dec + T_down + T_corr
```

per shot, from the decoding times of the CPU and hardware experiments at p = 0.001 and the constant terms
of the qubit technology and the interconnect.

```
make          list the targets
make data     build/data/trip_time/trip_summary.csv from the experiments' data in build/data
make check    assemble it from the recorded data (data/zenodo) into build/check/trip_time and compare with the record
make clean    remove this step's folders under build/
```

`make <target> DATA=<folder>` reads another data folder with the layout of `data/zenodo` (default `../../build/data`). The script is R, like the
figure scripts, so its paths are Makefile variables rather than a `config.toml`; the configurations it assembles
are the tables `sources` and `links` at the top of `assemble.R`. R with dplyr, tidyr and readr
(`make -C ../../analysis r-deps`).

## Inputs and method

- **Decoding time T_dec**: the first pass of every shot of 19 decoder sources (`sources` in `assemble.R`):
  - the CPU decoders Sparse Blossom (surface code d = 5, 9, 13, 17, 25), Fusion Blossom (surface code d = 9,
    13), Chromobius (colour code d = 5, 9, 13), BP+OSD and BP+LSD (bivariate-bicycle code d = 12), and BP+OSD
    (surface code d = 9), from `decoder_timing/raw/` of the data folder;
  - Relay-BP on the FPGA (transfer) and on the GPU (bivariate-bicycle codes d = 6 and 12) and the Micro
    Blossom simulation in batch mode (surface code d = 9 and 13), from `decoder_timing/hw/raw/`;
  - the literature decoders of `literature/trip_decoder_literature.csv`, with their published mean (it
    stands for the median and the p99.9) and, where stated, their maximum.
- **Technology terms** T_meas, T_syn, T_corr, the cycle time, the coherence time and the reaction budget:
  `literature/trip_technology.csv` (superconducting, trapped-ion QCCD, trapped-ion chain, neutral atom).
- **Interconnect terms** T_up and T_down: `literature/trip_interconnect.csv`, per platform (CPU: RoCE to the
  host; GPU: NVQLink; FPGA and ASIC: QECIPHY and the 10GbE aggregator star). The up-link term of the
  aggregator star is the simulated round-completion time of the network experiment
  (`network/sim/stats/summary.csv`).

Every decoder source is combined with every technology and with the interconnects of its platform. Per
configuration the summary holds the quantiles (p50, p90, p99, p99.9, maximum, mean) of T_dec and T_trip,
the decoder utilisation (mean T_dec per round over the cycle time; stable at most one), the reaction budget
check on the p99.9 and the maximum (superconducting only, a design's hard cap counts as met), the
coherence flag, the verdict and the term that dominates the p99.9.

## Relation to the recorded summary

The recorded `data/zenodo/trip_time/trip_summary.csv` holds the 148 configurations of F3 (four technologies;
F3 shows three of them), as assembled from the complete campaign; `make check` compares them field by field with
the assembled ones. The campaign's summary listed further configurations outside F3, which are not part of this
package.
