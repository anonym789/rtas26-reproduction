#!/usr/bin/env Rscript
# Trip time of the QEC correction loop for the configurations of F3 (Fig. 7 of the paper):
#
#   T_trip = T_meas + T_syn + T_up + T_dec + T_down + T_corr
#
# per shot, from the measured or simulated decoding times T_dec at p = 0.001 and the constant terms of the
# qubit technology and the interconnect. Literature decoders enter with their published mean (and maximum,
# where one is stated). Every decoder source is combined with every technology and with the interconnects
# that serve its platform.
#
#   Rscript assemble.R <output folder> <data folder> <literature folder>
#
# The data folder holds the experiments' data (build/data, or the recorded data/zenodo): decoder_timing/raw and
# decoder_timing/hw/raw (per-shot decoding times), network/sim/stats/summary.csv (simulated up-link term of the
# aggregator star). The literature folder holds trip_technology.csv, trip_interconnect.csv and
# trip_decoder_literature.csv. Writes trip_summary.csv, one row per technology, decoder source and interconnect.

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(readr)
})

args <- commandArgs(trailingOnly = TRUE)
out_dir <- if (length(args) >= 1) args[1] else "build"
data_dir <- if (length(args) >= 2) args[2] else "../../build/data"
literature_dir <- if (length(args) >= 3) args[3] else "../../data/literature"

P <- 0.001

# Decoder sources with per-shot times: the CPU experiment's decoders, Relay-BP on the FPGA (transfer) and the
# GPU, and the Micro Blossom simulation (block at once)
sources <- tribble(
  ~platform, ~method,     ~decoder,            ~code,     ~d, ~file,
  "cpu",     "measured",  "pymatching",        "surface",  5, "decoder_timing/raw/pymatching_surface_d5_p0.001.csv.gz",
  "cpu",     "measured",  "pymatching",        "surface",  9, "decoder_timing/raw/pymatching_surface_d9_p0.001.csv.gz",
  "cpu",     "measured",  "pymatching",        "surface", 13, "decoder_timing/raw/pymatching_surface_d13_p0.001.csv.gz",
  "cpu",     "measured",  "pymatching",        "surface", 17, "decoder_timing/raw/pymatching_surface_d17_p0.001.csv.gz",
  "cpu",     "measured",  "pymatching",        "surface", 25, "decoder_timing/raw/pymatching_surface_d25_p0.001.csv.gz",
  "cpu",     "measured",  "fusionblossom",     "surface",  9, "decoder_timing/raw/fusionblossom_surface_d9_p0.001.csv.gz",
  "cpu",     "measured",  "fusionblossom",     "surface", 13, "decoder_timing/raw/fusionblossom_surface_d13_p0.001.csv.gz",
  "cpu",     "measured",  "chromobius",        "color",    5, "decoder_timing/raw/chromobius_color_d5_p0.001.csv.gz",
  "cpu",     "measured",  "chromobius",        "color",    9, "decoder_timing/raw/chromobius_color_d9_p0.001.csv.gz",
  "cpu",     "measured",  "chromobius",        "color",   13, "decoder_timing/raw/chromobius_color_d13_p0.001.csv.gz",
  "cpu",     "measured",  "bposd",             "bb",      12, "decoder_timing/raw/bposd_bb_d12_p0.001.csv.gz",
  "cpu",     "measured",  "bplsd",             "bb",      12, "decoder_timing/raw/bplsd_bb_d12_p0.001.csv.gz",
  "cpu",     "measured",  "bposd",             "surface",  9, "decoder_timing/raw/bposd_surface_d9_p0.001.csv.gz",
  "fpga",    "transfer",  "relaybp1",          "bb",       6, "decoder_timing/hw/raw/fpga_transfer_relaybp1_bb_d6_p0.001.csv.gz",
  "fpga",    "transfer",  "relaybp1",          "bb",      12, "decoder_timing/hw/raw/fpga_transfer_relaybp1_bb_d12_p0.001.csv.gz",
  "fpga",    "simulated", "microblossombatch", "surface",  9, "decoder_timing/hw/raw/fpga_sim_microblossombatch_surface_d9_p0.001.csv.gz",
  "fpga",    "simulated", "microblossombatch", "surface", 13, "decoder_timing/hw/raw/fpga_sim_microblossombatch_surface_d13_p0.001.csv.gz",
  "gpu",     "measured",  "relaybp1",          "bb",       6, "decoder_timing/hw/raw/gpu_measured_relaybp1_bb_d6_p0.001.csv.gz",
  "gpu",     "measured",  "relaybp1",          "bb",      12, "decoder_timing/hw/raw/gpu_measured_relaybp1_bb_d12_p0.001.csv.gz"
)

# Interconnects per platform
links <- tribble(
  ~platform, ~interconnect,
  "cpu",     "backline_cpu",
  "gpu",     "nvqlink",
  "fpga",    "qeciphy",
  "fpga",    "sakata_agg_N8",
  "asic",    "qeciphy",
  "asic",    "sakata_agg_N8"
)

# Decoding time of every shot in its first pass (a cold run). The hardware files have one row per shot and
# counter, with the time repeated on each, hence distinct().
read_first_pass <- function(file) {
  read_csv(file.path(data_dir, file), col_select = c(rounds, shot, rep, time_ns),
           col_types = cols(.default = col_double()), show_col_types = FALSE) |>
    distinct() |>
    filter(rep == 1)
}

source_name <- function(platform, method, decoder, code, d) {
  sprintf("%s/%s%s/%s/d%d/p%g", platform, decoder, if_else(method == "simulated", "-sim", ""), code, d, P)
}

shots <- sources |>
  mutate(source_id = source_name(platform, method, decoder, code, d),
         decoder_source = if_else(platform == "cpu", "E2 (this work), basis first",
                                  paste0("E4 (this work), method ", method)),
         first_pass = lapply(file, read_first_pass)) |>
  unnest(first_pass) |>
  group_by(source_id, platform, method, decoder, code, d, decoder_source) |>
  summarise(rounds = first(rounds), t_dec = list(time_ns), .groups = "drop")

literature <- read_csv(file.path(literature_dir, "trip_decoder_literature.csv"), show_col_types = FALSE) |>
  transmute(source_id, platform, method = "literature", decoder, code, d, rounds, mean_ns, max_ns,
            max_kind = case_when(is.na(max_ns) ~ "none", grepl("hard", status) ~ "hard_cap", .default = "observed"),
            decoder_source = reference)

technologies <- read_csv(file.path(literature_dir, "trip_technology.csv"), show_col_types = FALSE) |>
  transmute(technology, tech_label = label, T_meas_ns, T_syn_ns, T_corr_ns, T_c_ns, T_coh_ns, D_react_ns,
            tech_status = status)

# The up-link term of the aggregator star is the simulated round-completion time of the network experiment
# (deterministic for fixed link latencies, so its p99.9 is the value)
network <- read_csv(file.path(data_dir, "network", "sim", "stats", "summary.csv"), show_col_types = FALSE) |>
  select(e3_config_id = config_id, network_up_ns = p999_ns)

interconnects <- read_csv(file.path(literature_dir, "trip_interconnect.csv"), show_col_types = FALSE) |>
  left_join(network, by = "e3_config_id") |>
  separate_longer_delim(platforms, ";") |>
  inner_join(links, by = c("platforms" = "platform", "interconnect")) |>
  transmute(platform = platforms, interconnect, ic_label = label, ic_class = class,
            T_up_ns = coalesce(network_up_ns, up_ns), T_down_ns = down_ns, up_kind, down_kind,
            interconnect_source = source)
stopifnot(all(interconnects$up_kind == "constant"), all(interconnects$down_kind == "constant"))

configurations <- function(decoders) {
  decoders |>
    cross_join(technologies) |>
    inner_join(interconnects, by = "platform", relationship = "many-to-many") |>
    mutate(T_rest_ns = T_meas_ns + T_syn_ns + T_corr_ns)
}

q <- function(x, prob) quantile(x, prob, names = FALSE, type = 7)

# Configurations with per-shot times: statistics of T_dec and of the per-shot T_trip
measured <- configurations(shots) |>
  rowwise() |>
  mutate(t_trip = list(t_dec + T_up_ns + T_down_ns + T_rest_ns),
         dec_p50 = q(t_dec, 0.5), dec_p90 = q(t_dec, 0.9), dec_p99 = q(t_dec, 0.99), dec_p999 = q(t_dec, 0.999),
         dec_max = max(t_dec), dec_mean = mean(t_dec),
         trip_p50 = q(t_trip, 0.5), trip_p90 = q(t_trip, 0.9), trip_p99 = q(t_trip, 0.99), trip_p999 = q(t_trip, 0.999),
         trip_max = max(t_trip), trip_mean = mean(t_trip),
         shots = length(t_dec)) |>
  ungroup() |>
  mutate(has_tail = TRUE, max_kind = "observed")

# Literature configurations: the published mean stands for the median and the p99.9, the stated maximum for the
# maximum; the other quantiles are unknown
published <- configurations(literature) |>
  mutate(trip_mean = mean_ns + T_up_ns + T_down_ns + T_rest_ns,
         dec_p50 = mean_ns, dec_p90 = NA_real_, dec_p99 = NA_real_, dec_p999 = mean_ns, dec_max = max_ns, dec_mean = mean_ns,
         trip_p50 = trip_mean, trip_p90 = NA_real_, trip_p99 = NA_real_, trip_p999 = trip_mean,
         trip_max = max_ns + T_up_ns + T_down_ns + T_rest_ns,
         shots = 1L, has_tail = FALSE)

# The term that dominates the trip time at the p99.9 (the first one on ties)
dominant_term <- function(...) {
  terms <- cbind(...)
  colnames(terms)[max.col(terms, ties.method = "first")]
}

# Criteria: D1 decoder throughput (utilisation of the decoder by one d-round block per d cycles), D2 the reaction
# budget, which only the superconducting technology has (on the p99.9 and on the maximum; a design's hard cap
# counts as met), D3 the coherence time (a reference scale, not part of the verdict)
trip <- bind_rows(measured, published) |>
  mutate(p = P,
         config_id = paste(technology, source_id, interconnect, sep = "|"),
         has_budget = !is.na(D_react_ns),
         utilisation = (dec_mean / rounds) / T_c_ns,
         D1_throughput = utilisation <= 1,
         D2_reaction_p999 = if_else(has_budget, trip_p999 <= D_react_ns, NA),
         D2_reaction_max = case_when(!has_budget ~ NA,
                                     max_kind == "hard_cap" ~ TRUE,
                                     .default = !is.na(trip_max) & trip_max <= D_react_ns),
         D3_coherence = is.na(trip_max) | max_kind == "hard_cap" | trip_max <= T_coh_ns,
         stability = if_else(D1_throughput, "stable", "unstable"),
         trip_p999_cycles = trip_p999 / T_c_ns,
         verdict = case_when(!has_budget ~ NA,
                             D1_throughput & D2_reaction_p999 & (D2_reaction_max | is.na(trip_max)) ~ "PASS",
                             D1_throughput & D2_reaction_p999 ~ "MARGINAL",
                             .default = "FAIL"),
         dominant_term_p999 = dominant_term(T_meas = T_meas_ns, T_syn = T_syn_ns, T_up = T_up_ns, T_dec = dec_p999,
                                            T_down = T_down_ns, T_corr = T_corr_ns),
         cap_exceeds_coh = max_kind == "hard_cap" & !is.na(trip_max) & trip_max > T_coh_ns,
         # every row is drawn in F3; the column keeps the layout of the summary that also lists other configurations
         in_plot_set = TRUE) |>
  select(config_id, technology, tech_label, source_id, platform, method, decoder, code, d, p, rounds,
         interconnect, ic_label, ic_class, T_meas_ns, T_syn_ns, T_up_ns, T_down_ns, T_corr_ns, T_c_ns, T_coh_ns,
         D_react_ns, dec_p50, dec_p90, dec_p99, dec_p999, dec_max, dec_mean,
         trip_p50, trip_p90, trip_p99, trip_p999, trip_max, trip_mean, utilisation, D1_throughput,
         D2_reaction_p999, D2_reaction_max, D3_coherence, stability, trip_p999_cycles, verdict, dominant_term_p999,
         has_tail, max_kind, cap_exceeds_coh, shots, in_plot_set, decoder_source, interconnect_source, tech_status)

dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
write_csv(trip, file.path(out_dir, "trip_summary.csv"))
