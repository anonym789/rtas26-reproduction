#!/usr/bin/env Rscript
# F3: trip time of the correction loop per decoder configuration for three qubit technologies: p50 and
# p99.9 (or the published mean where only that is known), the maximum, and a cross where the decoder cannot
# keep up. One row per configuration, panels by code family and distance.
#
#   Rscript plot_trip.R <output folder> <trip-time folder> <literature folder>
#
# Reads trip_summary.csv (one row per configuration and technology) in the trip-time folder and trip_technology.csv
# in the literature folder. Writes F3.tex (TikZ, input by the paper unscaled at the IEEEtran text width).

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
trip_dir <- if (length(args) >= 2) args[2] else "../../build/data/trip_time"
literature_dir <- if (length(args) >= 3) args[3] else "../../data/literature"

COLOURS.LIST <- c("black", "#E69F00", "#999999", "#009371", "#beaed4", "#ed665a", "#1f78b4")

# The trapped-ion chain is left out: its readout (8.63 ms) nearly coincides with the neutral atom's (10 ms).
TECHNOLOGIES <- c(superconducting = "superconducting", trapped_ion_qccd = "trapped ion, QCCD", neutral_atom = "neutral atom")
TECHNOLOGY_COLOURS <- setNames(COLOURS.LIST[c(1, 2, 4)], names(TECHNOLOGIES))
# Vertical offset within a row (fraction of a row). Superconducting sits on the row's tick, since the rows
# are ordered by its median.
OFFSET <- c(trapped_ion_qccd = 0.2, superconducting = 0, neutral_atom = -0.2)

DECODERS <- c(pymatching = "Sparse Blossom", fusionblossom = "Fusion Blossom", chromobius = "Chromobius",
              bposd = "BP+OSD", bplsd = "BP+LSD", relaybp1 = "Relay-BP", `Relay-BP (IBM FPGA)` = "Relay-BP",
              microblossombatch = "Micro Blossom", `Helios (Liu et al.)` = "Helios")
METHODS <- c(literature = " lit.", transfer = " transf.", simulated = " sim.", measured = "")
INTERCONNECTS <- c(qeciphy = "serial", sakata_agg_N8 = "10GbE agg. $N=8$", backline_cpu = "RoCE", nvqlink = "NVQLink")

trip <- read_csv(file.path(trip_dir, "trip_summary.csv"), show_col_types = FALSE) |>
  filter(in_plot_set, technology %in% names(TECHNOLOGIES)) |>
  mutate(row = sprintf("%s [%s%s] %s", coalesce(DECODERS[decoder], decoder), platform, METHODS[method],
                       INTERCONNECTS[interconnect]),
         row_id = paste(row, d),
         family = factor(code, levels = c("surface", "color", "bb"), labels = c("surface", "colour", "BB")),
         technology = factor(technology, levels = names(TECHNOLOGIES)),
         offset = OFFSET[as.character(technology)],
         published_mean = method == "literature")

# every configuration needs a row for each technology, since the rows are ordered by superconducting
stopifnot(all(count(trip, row_id)$n == length(TECHNOLOGIES)))

# Within a panel the superconducting median grows upwards (the first level sits at the bottom).
row_order <- trip |> filter(technology == "superconducting") |> arrange(trip_p50, trip_p999) |> pull(row_id)
row_labels <- trip |> distinct(row_id, row) |> tibble::deframe()
trip <- trip |>
  mutate(row_id = factor(row_id, levels = row_order)) |>
  arrange(technology == "superconducting")   # drawn last, so on top

statistics <- trip |>
  transmute(row_id, family, d, technology, offset,
            p50 = if_else(published_mean, NA, trip_p50),
            p99.9 = if_else(published_mean, NA, trip_p999),
            `published mean` = if_else(published_mean, trip_mean, NA)) |>
  pivot_longer(c(p50, p99.9, `published mean`), names_to = "statistic", values_to = "ns", values_drop_na = TRUE) |>
  mutate(statistic = factor(statistic, levels = c("p50", "p99.9", "published mean")))

# the reaction budget assumed in superconducting resource estimates, and the coherence time per technology
references <- read_csv(file.path(literature_dir, "trip_technology.csv"), show_col_types = FALSE) |>
  filter(technology %in% names(TECHNOLOGIES)) |>
  transmute(technology = factor(technology, levels = names(TECHNOLOGIES)),
            budget = D_react_ns, coherence = T_coh_ns) |>
  pivot_longer(c(budget, coherence), names_to = "reference", values_to = "ns", values_drop_na = TRUE)

label_time <- function(ns) {
  unit <- findInterval(ns, c(0, 1e3, 1e6, 1e9))
  ifelse(is.na(ns), NA, sprintf("%g\\,%s", ns / 1000^(unit - 1), c("ns", "\\textmu s", "ms", "s")[unit]))
}

f3 <- ggplot(trip, aes(y = row_id, colour = technology)) +
  # trains each panel's y scale on all of its rows before the range layer, which lacks the published means
  geom_blank() +
  geom_vline(aes(xintercept = ns, colour = technology, linetype = reference), data = references,
             linewidth = 0.4, show.legend = FALSE) +
  geom_linerange(aes(xmin = trip_p50, xmax = trip_p999, nudge_y = offset), data = \(d) filter(d, !published_mean),
                 position = position_nudge(), alpha = 0.6, linewidth = 0.3, show.legend = FALSE) +
  geom_errorbar(aes(xmin = trip_max, xmax = trip_max, nudge_y = offset), data = \(d) filter(d, !is.na(trip_max)),
                position = position_nudge(), orientation = "y", width = 0.55, linewidth = 0.2, show.legend = FALSE) +
  geom_point(aes(x = ns, shape = statistic, nudge_y = offset), data = statistics,
             position = position_nudge(), size = 1.4) +
  geom_point(aes(x = trip_p999, nudge_y = offset), data = \(d) filter(d, stability == "unstable"),
             position = position_nudge(), shape = 4, size = 2.2, stroke = 0.6, show.legend = FALSE) +
  facet_nested(rows = vars(family, d), scales = "free_y", space = "free_y",
               labeller = labeller(d = \(d) sprintf("$d=%s$", d))) +
  scale_x_log10("Correction Loop $T_\\mathrm{trip}$ [log] (bar = maximum)", breaks = 10^(2:10),
                minor_breaks = outer(1:9, 10^(2:10)), labels = label_time, guide = guide_axis(minor.ticks = TRUE)) +
  scale_y_discrete(NULL, labels = row_labels) +
  scale_colour_manual("Technology", values = TECHNOLOGY_COLOURS, labels = TECHNOLOGIES, breaks = names(TECHNOLOGIES)) +
  scale_shape_manual("Trip Time Statistics", values = c(p50 = 1, p99.9 = 15, `published mean` = 2)) +
  scale_linetype_manual(values = c(budget = "solid", coherence = "dotted"), guide = "none") +
  guides(colour = guide_legend(order = 1, override.aes = list(shape = 15, size = 2.2))) +
  theme_bw(base_size = 8) +
  theme(panel.grid.minor = element_blank(),
        panel.spacing.y = unit(1, "pt"),
        strip.text.y = element_text(angle = 0, margin = margin(1.5, 3.2, 1.5, 3.2)),
        axis.text.y = element_text(size = 6.5),
        axis.minor.ticks.length.x.bottom = rel(1),
        legend.position = "top",
        legend.location = "plot",
        legend.justification.top = "right",
        legend.title.position = "left",
        legend.text = element_text(size = 6.5),
        legend.key.width = unit(10, "pt"),
        legend.key.spacing.x = unit(2, "pt"),
        legend.margin = margin(0, 3, 0, 3))

tikz(file.path(out_dir, "F3.tex"), width = 516 / 72.27, height = 6.16)
print(f3)
invisible(dev.off())
