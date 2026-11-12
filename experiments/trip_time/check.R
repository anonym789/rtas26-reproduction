#!/usr/bin/env Rscript
# Compares the assembled trip_summary.csv with the recorded one: both must list the same configurations, and every
# assembled row must equal, field by field as written, the recorded row of the same configuration.
#
#   Rscript check.R <assembled trip_summary.csv> <recorded trip_summary.csv>

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
})

args <- commandArgs(trailingOnly = TRUE)
as_text <- function(file) read_csv(file, col_types = cols(.default = col_character()), na = character())

assembled <- as_text(args[1]) |> arrange(config_id)
recorded <- as_text(args[2]) |> arrange(config_id)

stopifnot(identical(names(assembled), names(recorded)), identical(assembled$config_id, recorded$config_id))
differing <- which(as.matrix(assembled) != as.matrix(recorded), arr.ind = TRUE)
if (nrow(differing) > 0) {
  print(tibble(config_id = assembled$config_id[differing[, "row"]], column = names(assembled)[differing[, "col"]],
               assembled = as.matrix(assembled)[differing], recorded = as.matrix(recorded)[differing]))
  stop(nrow(differing), " fields differ")
}
cat("trip_summary.csv:", nrow(assembled), "rows equal to the recorded ones\n")
