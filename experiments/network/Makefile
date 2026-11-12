# The syndrome network under load: transport time from N controllers to the decoder (paper: Fig. 5, N1).
# Every setting is in config.toml. The experiment writes its data into paths.output (build/data/network of the
# repository, the layout of data/zenodo/network); it never writes into data/.
#   make                list the targets
#   make data           the whole experiment: load model, bounds, simulation runs, statistics
#   make load           frame sizes of the load model
#   make bound          network-calculus bounds, crossings, R x L grid, saturation
#   make simulate       all simulation runs (about 7 h with 12 workers); existing runs are skipped
#   make stats          statistics of the simulation runs (paths.runs)
#   make sanity         plausibility checks -> SANITY.md
#   make check          regenerate the recorded tables (data/zenodo/network) into build/check and compare
#   make test           unit and regression tests
#   make env            machine and package versions -> env/ENVIRONMENT.md
#   make clean          remove this experiment's data and check folders under build/
#   make <target> CONFIG=<file>   use another settings file
PYTHON ?= python3.14
CONFIG ?= config.toml
VENV=.venv
PY=$(VENV)/bin/python
QECNET=$(PY) -m qecnet --config $(CONFIG)
# the default output folders (paths.output, paths.check)
OUT=../../build/data/network
CHECK=../../build/check/network

help:
	@sed -n '4,15p' Makefile | sed 's/^# //'

$(VENV)/.installed: env/requirements.txt env/requirements-test.txt
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet -r env/requirements-test.txt
	touch $@

data: load bound simulate
	$(MAKE) stats

bound stats load: | $(VENV)/.installed
	$(QECNET) $@

simulate: | $(VENV)/.installed
	for set in checks s1 s3 edge; do $(QECNET) simulate $$set || exit 1; done

sanity: stats bound
	$(QECNET) sanity

check: | $(VENV)/.installed
	$(QECNET) check

test: | $(VENV)/.installed
	$(PY) -m pytest -q

env: | $(VENV)/.installed
	env/collect_env.sh $(PY)

clean:
	rm -rf $(OUT) $(CHECK)

.PHONY: help data load bound simulate stats sanity check test env clean
