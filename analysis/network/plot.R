#!/usr/bin/env Rscript
# N1: transport time T_up (99.9th percentile over the simulated cycles) against the number of controllers N,
# scenario S1 on 10GbE links, without and with aggregation.
#
#   Rscript plot.R <output folder> <data folder>
#
# Reads the aggregated simulation runs sim/stats/summary.csv (the sweep) and sim/stats/edge_summary.csv (the
# largest stable and the first unstable N of each saturating series) in the data folder. Writes N1.tex (TikZ,
# input by the paper).

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(ggplot2)
  library(scales)
  library(tikzDevice)
})

args <- commandArgs(trailingOnly = TRUE)
out_dir <- if (length(args) >= 1) args[1] else "build"
data_dir <- if (length(args) >= 2) args[2] else "../../build/data/network"

COLOURS.LIST <- c("black", "#E69F00", "#999999", "#009371", "#beaed4", "#ed665a", "#1f78b4")
GREY <- COLOURS.LIST[3]
CYCLE_NS <- 1100
QUBITS_PER_CONTROLLER <- 64

# the 10GbE link of each topology; T3-k7 is the two-level tree with at most seven controllers per leaf
LINK_10GBE <- c(T1 = "L4", T2 = "L5-10G", T3 = "L5-10G", `T3-k7` = "L5-10G", T4 = "L6-10G")
TOPOLOGIES <- c(T1 = "T1 one link per controller (L4)", T2 = "T2 aggregator star (L5)",
                T3 = "T3 two-level tree (L5)", T4 = "T4 switch (L6, latency assumed)")
VARIANTS <- c(balanced = "balanced, $k = \\lceil\\sqrt{N}\\rceil$", capped = "port-capped, $k = 7$ per leaf (U55)")
UNSTABLE <- "unstable: port\nutilisation above one"

runs <- bind_rows(read_csv(file.path(data_dir, "sim", "stats", "summary.csv"), show_col_types = FALSE),
                  read_csv(file.path(data_dir, "sim", "stats", "edge_summary.csv"), show_col_types = FALSE)) |>
  filter(scenario == "S1", Q_c == QUBITS_PER_CONTROLLER, cycle_ns == CYCLE_NS, cycle_class == "steady",
         link == LINK_10GBE[topology]) |>
  distinct(config_id, .keep_all = TRUE)

# T1 and T4 do not aggregate; they appear in the aggregation-on panel for reference
runs <- bind_rows(runs, runs |> filter(topology %in% c("T1", "T4")) |> mutate(aggregation = 1))

# one row per stable configuration; the last one of a series that saturates at a larger N carries the cross
n1 <- runs |>
  group_by(topology, aggregation) |>
  mutate(saturates = any(stable == 0)) |>
  filter(stable == 1) |>
  mutate(last_stable = saturates & N == max(N)) |>
  ungroup() |>
  mutate(family = factor(TOPOLOGIES[sub("-k7", "", topology)], levels = TOPOLOGIES),
         variant = factor(VARIANTS[if_else(topology == "T3-k7", "capped", "balanced")], levels = VARIANTS),
         panel = factor(if_else(aggregation == 1, "Aggregation on", "Aggregation off")))

# system sizes from the text, as vertical lines labelled along the line; each label starts at y (ns) on a
# stretch of its line that no series crosses in that panel, left or right of the line. The lines sit at
# round numbers of controllers close to |Q| / Q_c (312.5 and 15,625).
system_sizes <- tribble(
  ~N,    ~label,
  300,   "$|Q| = 20 \\cdot 10^3$~\\cite{mohseni_HowBuildQuantum_2026}",
  16000, "$|Q| = 10^6$~\\cite{gidney_rsa_2025}"
)
size_labels <- tribble(
  ~N,    ~panel,            ~y,   ~side,
  300,   "Aggregation off", 395,  "left",
  300,   "Aggregation on",  660,  "right",
  16000, "Aggregation off", 395,  "left",
  16000, "Aggregation on",  1045, "left"
) |>
  left_join(system_sizes, by = "N") |>
  mutate(vjust = if_else(side == "left", -0.4, 1.4))

label_pow10 <- function(x) sprintf("$10^{%d}$", round(log10(x)))
log_minor <- outer(1:9, 10^(0:5))
text_size <- function(pt) pt / .pt

# physical qubits for Q_c qubits per controller, as a small grey axis inside each panel
QUBIT_AXIS_NS <- 200
qubit_ticks <- tibble(qubits = 10^(3:6), N = qubits / QUBITS_PER_CONTROLLER, label = label_pow10(qubits))

n1_plot <- ggplot(n1, aes(N, p999_ns, colour = family)) +
  geom_vline(aes(xintercept = N), data = system_sizes, colour = GREY, linewidth = 0.25, linetype = "dotted") +
  geom_text(aes(N, y, label = label, vjust = vjust), data = size_labels, inherit.aes = FALSE,
            angle = 90, hjust = 0, colour = GREY, size = text_size(4.4)) +
  annotate("segment", x = 7, xend = 2e4, y = QUBIT_AXIS_NS, colour = GREY, linewidth = 0.3) +
  geom_segment(aes(x = N, y = QUBIT_AXIS_NS, yend = QUBIT_AXIS_NS / 1.06), data = qubit_ticks, inherit.aes = FALSE,
               colour = GREY, linewidth = 0.3) +
  geom_text(aes(x = N, y = QUBIT_AXIS_NS / 1.08, label = label), data = qubit_ticks, inherit.aes = FALSE,
            vjust = 1, colour = GREY, size = text_size(5.6)) +
  annotate("text", x = 7, y = QUBIT_AXIS_NS * 1.05, label = "Qubits $Q$", hjust = 0, vjust = 0,
           colour = GREY, size = text_size(5.6)) +
  geom_line(aes(linetype = variant, group = topology), linewidth = 0.5) +
  geom_point(size = 1.2, shape = 16, show.legend = FALSE) +
  geom_point(aes(shape = UNSTABLE), data = \(d) filter(d, last_stable), size = 1.8, stroke = 0.7,
             show.legend = c(colour = FALSE)) +
  facet_wrap(vars(panel)) +
  scale_x_log10("Controllers $N$", breaks = 10^(0:5), minor_breaks = log_minor, labels = label_pow10,
                guide = guide_axis(minor.ticks = TRUE)) +
  scale_y_log10("Transport Time $T_\\mathrm{up}$ (ns)", breaks = c(250, 500, 1000, 2000), minor_breaks = log_minor,
                labels = label_comma(), guide = guide_axis(minor.ticks = TRUE)) +
  scale_colour_manual("Topology", values = setNames(COLOURS.LIST[c(1, 2, 4, 7)], TOPOLOGIES)) +
  scale_linetype_manual("Tree Variant", values = setNames(c("solid", "42"), VARIANTS), breaks = unname(VARIANTS["capped"])) +
  scale_shape_manual("Stability", values = 4) +
  coord_cartesian(xlim = c(7, 2e4), ylim = c(150, 2000)) +
  guides(colour = guide_legend(order = 1, nrow = 2),
         linetype = guide_legend(order = 2, nrow = 2),
         shape = guide_legend(order = 3, override.aes = list(colour = "black"))) +
  theme_bw(base_size = 8) +
  theme(panel.grid.minor = element_blank(),
        panel.grid.major = element_line(linewidth = 0.2, colour = "grey90"),
        strip.background = element_rect(fill = "grey85", colour = "grey20"),
        strip.text = element_text(size = 7, colour = "grey10"),
        axis.ticks = element_line(linewidth = 0.3),
        axis.minor.ticks.length = rel(1),
        legend.position = "bottom",
        legend.location = "plot",
        legend.title.position = "top",
        legend.title = element_text(size = 7),
        legend.text = element_text(size = 6.5),
        legend.key.height = unit(3, "mm"),
        legend.key.width = unit(5, "mm"),
        legend.margin = margin(0, 0, 0, 0),
        legend.box.spacing = unit(1, "mm"),
        plot.margin = margin(2, 4, 2, 2))

tikz(file.path(out_dir, "N1.tex"), width = 17.8 / 2.54, height = 2.65)
print(n1_plot)
invisible(dev.off())
