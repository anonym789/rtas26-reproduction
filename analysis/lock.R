#!/usr/bin/env Rscript
# Writes renv.lock: the R packages of requirements.R (the figure scripts and the trip-time assembly) and their
# dependencies (Depends, Imports, LinkingTo), each with the version installed in this R library, in the format that
# renv::restore() reads. The packages that come with R (priority base or recommended) are left out.
#
#   Rscript lock.R [output file]

out <- commandArgs(trailingOnly = TRUE)[1]
if (is.na(out)) out <- "renv.lock"

wanted <- trimws(readLines("requirements.R"))
wanted <- wanted[nzchar(wanted)]
installed <- installed.packages()
with_r <- rownames(installed)[installed[, "Priority"] %in% c("base", "recommended")]
closure <- tools::package_dependencies(wanted, db = installed, which = c("Depends", "Imports", "LinkingTo"), recursive = TRUE)
packages <- sort(setdiff(unique(c(wanted, unlist(closure))), c(with_r, "R")))

missing <- setdiff(packages, rownames(installed))
if (length(missing)) stop("not installed: ", paste(missing, collapse = ", "))

entry <- function(p) {
  repository <- unname(read.dcf(system.file("DESCRIPTION", package = p), fields = "Repository")[1, 1])
  sprintf('    "%s": {\n      "Package": "%s",\n      "Version": "%s",\n      "Source": "Repository",\n      "Repository": "%s"\n    }',
          p, p, installed[p, "Version"], if (is.na(repository)) "CRAN" else repository)
}

lock <- c("{",
          '  "R": {',
          sprintf('    "Version": "%s.%s",', R.version$major, R.version$minor),
          '    "Repositories": [',
          '      {',
          '        "Name": "CRAN",',
          '        "URL": "https://cloud.r-project.org"',
          '      }',
          '    ]',
          '  },',
          '  "Packages": {',
          paste(vapply(packages, entry, ""), collapse = ",\n"),
          "  }",
          "}")
writeLines(lock, out)
cat(sprintf("%s: R %s.%s, %d packages\n", out, R.version$major, R.version$minor, length(packages)))
