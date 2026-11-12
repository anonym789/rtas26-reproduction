#!/usr/bin/env Rscript
# S1: distribution of the per-shot decoding time at p = 0.001 on every platform, first pass of each
# configuration. Histogram on a log axis and density, both scaled to their maximum, with reference lines
# for the maximum, the d-round cycle budget and the Relay-BP iteration limit.
#
#   Rscript plot_shape.R <output folder> <data folder>
#
# Reads per-shot times from raw/ (CPU) and hw/raw/ (FPGA, GPU) in the data folder. Writes S1.tex (TikZ,
# input by the paper) and S1_stats.csv (shots, maximum and 99.9th percentile per panel).

suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(readr)
  library(ggplot2)
  library(ggh4x)
  library(tikzDevice)
})

args <- commandArgs(trailingOnly = TRUE)
out_dir <- if (length(args) >= 1) args[1] else "build"
data_dir <- if (length(args) >= 2) args[2] else "../../build/data/decoder_timing"

COLOURS.LIST <- c("black", "#E69F00", "#999999", "#009371", "#beaed4", "#ed665a", "#1f78b4")
CYCLE_NS <- 1100

panels <- tribble(
  ~platform,      ~file,                                                        ~label,                         ~title,
  "CPU",          "raw/pymatching_surface_d13_p0.001.csv.gz",                   "Sparse Blossom, surface d=13", "Sparse Blossom, surface $d=13$",
  "CPU",          "raw/fusionblossom_surface_d13_p0.001.csv.gz",                "Fusion Blossom, surface d=13", "Fusion Blossom, surface $d=13$",
  "CPU",          "raw/chromobius_color_d13_p0.001.csv.gz",                     "Chromobius, colour d=13",      "Chromobius, colour $d=13$",
  "CPU",          "raw/bposd_bb_d12_p0.001.csv.gz",                             "BP+OSD, BB [[144,12,12]]",     "BP+OSD, BB $[[144,12,12]]$",
  "FPGA and GPU", "hw/raw/fpga_transfer_relaybp1_bb_d12_p0.001.csv.gz",         "Relay-BP FPGA, [[144,12,12]]", "Relay-BP FPGA, $[[144,12,12]]$",
  "FPGA and GPU", "hw/raw/fpga_sim_microblossombatch_surface_d13_p0.001.csv.gz", "Micro Blossom sim., d=13",     "Micro Blossom sim., $d=13$",
  "FPGA and GPU", "hw/raw/gpu_measured_relaybp1_bb_d12_p0.001.csv.gz",          "Relay-BP GPU, [[144,12,12]]",  "Relay-BP GPU, $[[144,12,12]]$"
)

# The hardware files have one row per shot and counter (the time repeats), hence distinct().
# hard_bound_ns is the iteration limit of Relay-BP on the FPGA; the other files do not have it.
read_shots <- function(file) {
  read_csv(file.path(data_dir, file), col_select = any_of(c("d", "shot", "rep", "time_ns", "hard_bound_ns")),
           col_types = cols(.default = col_double()), progress = FALSE) |>
    filter(rep == 1) |>
    distinct(shot, time_ns, .keep_all = TRUE)
}

shots <- panels |>
  mutate(data = lapply(file, read_shots)) |>
  unnest(data) |>
  mutate(platform = factor(platform, levels = unique(panels$platform)),
         title = factor(title, levels = panels$title))

per_panel <- shots |>
  group_by(platform, title, label) |>
  summarise(n = n(), d = first(d), min_ns = min(time_ns), max_ns = max(time_ns),
            p999_ns = quantile(time_ns, 0.999), limit_ns = first(hard_bound_ns), .groups = "drop")

# reference lines; the budget and the iteration limit only where they lie within a decade of the data
references <- per_panel |>
  transmute(platform, title, min_ns, max_ns,
            maximum = max_ns, budget = d * CYCLE_NS, limit = limit_ns) |>
  pivot_longer(c(maximum, budget, limit), names_to = "reference", values_to = "time_ns", values_drop_na = TRUE) |>
  filter(reference == "maximum" | between(time_ns, min_ns / 10, max_ns * 10))

label_time <- function(ns) {
  unit <- findInterval(ns, c(0, 1e3, 1e6, 1e9))
  ifelse(is.na(ns), NA, sprintf("%g\\,%s", ns / 1000^(unit - 1), c("ns", "\\textmu s", "ms", "s")[unit]))
}

s1 <- ggplot(shots, aes(time_ns)) +
  geom_histogram(aes(y = after_stat(ncount)), bins = 45, fill = "grey35", colour = "white", linewidth = 0.15) +
  geom_density(aes(y = after_stat(scaled)), colour = COLOURS.LIST[7], linewidth = 0.55, adjust = 1.2) +
  geom_vline(aes(xintercept = time_ns, colour = reference, linetype = reference, linewidth = reference),
             data = references) +
  facet_nested_wrap(vars(platform, title), ncol = 4, scales = "free_x") +
  scale_x_log10(breaks = 10^(1:11), minor_breaks = outer(1:9, 10^(1:11)), labels = label_time,
                expand = expansion(mult = 0.06), guide = guide_axis(minor.ticks = TRUE, check.overlap = TRUE)) +
  scale_y_continuous(breaks = c(0, 0.5, 1), expand = expansion(mult = c(0.01, 0.05))) +
  scale_colour_manual(values = c(maximum = COLOURS.LIST[6], budget = "grey45", limit = "grey30"), guide = "none") +
  scale_linetype_manual(values = c(maximum = "solid", budget = "dashed", limit = "dotted"), guide = "none") +
  scale_linewidth_manual(values = c(maximum = 0.6, budget = 0.4, limit = 0.5), guide = "none") +
  labs(x = "$T_\\mathrm{dec}$ per $d$ rounds [log], $p = 0.001$", y = "Density") +
  theme_bw(base_size = 9) +
  theme(panel.grid.minor = element_blank(),
        panel.spacing.x = unit(13, "pt"),
        strip.text = element_text(size = 7, margin = margin(2.5, 3, 2.5, 3)),
        axis.text.x = element_text(size = 6.5),
        axis.minor.ticks.length.x.bottom = rel(1))

tikz(file.path(out_dir, "S1.tex"), width = 17.8 / 2.54, height = 3.13)
print(s1)
invisible(dev.off())

per_panel |>
  transmute(label, d, n, max_us = max_ns / 1000, p999_us = p999_ns / 1000, budget_us = d * CYCLE_NS / 1000) |>
  write_csv(file.path(out_dir, "S1_stats.csv"))
