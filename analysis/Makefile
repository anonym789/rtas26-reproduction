# The paper's figures: S1 (Fig. 4), N1 (Fig. 5) and F3 (Fig. 7), from one data folder with the layout of
# data/zenodo (default: the experiments' data in build/data). Each figure folder has its own Makefile.
#   make                          all three into each folder's build/ (make -j3 runs them in parallel)
#   make DATA=../data/zenodo      from the recorded data
#   make OUTPUT=<folder>          all three into one folder
#   make -C network               one of them
#   make clean                    remove the figure folders' build/
#   make r-deps                   install the R packages listed in requirements.R (current versions)
#   make r-lock                   write renv.lock, the versions installed here (the Docker image restores it)
R=Rscript
DATA=../build/data
LITERATURE=../data/literature
DIRS=decoder_timing network trip_time
# the figure folders write into their own build/ unless OUTPUT is given
OUT=$(if $(OUTPUT),OUTPUT=$(abspath $(OUTPUT)))

repro: $(DIRS)

decoder_timing network:
	$(MAKE) -C $@ repro DATA=$(abspath $(DATA))/$@ $(OUT)

trip_time:
	$(MAKE) -C $@ repro DATA=$(abspath $(DATA))/trip_time LITERATURE=$(abspath $(LITERATURE)) $(OUT)

clean:
	for d in $(DIRS); do $(MAKE) -C $$d clean; done

r-deps: requirements.R
	$(R) -e "pkgs <- trimws(readLines('$<')); install.packages(pkgs[nzchar(pkgs)], repos = 'https://cloud.r-project.org', Ncpus = parallel::detectCores())"

# renv.lock: the tested versions of these packages and their dependencies (the Docker image restores them)
r-lock: requirements.R lock.R
	$(R) lock.R renv.lock

.PHONY: repro clean r-deps r-lock $(DIRS)
