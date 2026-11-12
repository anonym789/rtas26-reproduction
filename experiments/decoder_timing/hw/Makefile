# Hardware decoders (paper: Fig. 4, S1, FPGA and GPU row). Every setting is in config.toml. The experiment writes its
# data into paths.output (build/data/decoder_timing/hw of the repository, the layout of data/zenodo/decoder_timing/hw);
# it never writes into data/.
#   make                list the targets
#   make data           the part that runs on any machine: syndromes, Relay-BP transfer, statistics
#   make syndromes      bivariate-bicycle syndromes of the runs (regenerated from their seeds)
#   make transfer       Relay-BP work-counter transfer, every run in config.toml (counters only, any machine)
#   make gpu            Relay-BP on the GPU, every run (on the GPU machine: SM clock locked, reset afterwards)
#   make gpu-remote     the same on gpu.host: code pushed there, raw files pulled back
#   make mb-inputs      Micro Blossom input from the CPU experiment's surface-code syndromes
#   make mb-sim         Micro Blossom simulation queues in the container (on the simulation host)
#   make mb-collect     simulation logs of the campaign -> per-shot tables
#   make mb-calibrate   board correction of the simulation (writes S1's Micro Blossom rows)
#   make stats          statistics of the campaign's raw files
#   make sanity         plausibility checks -> SANITY.md
#   make check          regenerate the recorded tables (data/zenodo/decoder_timing/hw) into build/check and compare
#   make test           unit and regression tests
#   make env            environment record -> env/ENVIRONMENT.md
#   make clean          remove this experiment's data and check folders under build/
#   make <target> CONFIG=<file>   use another settings file
PYTHON ?= python3.13
CONFIG ?= config.toml
VENV=.venv
PY=$(VENV)/bin/python
# the CPU experiment's package (qecdec, one folder up) provides circuits, syndromes and statistics
QECHW=PYTHONPATH=.. $(PY) -m qechw --config $(CONFIG)
# settings that a target needs before the environment exists (standard library only)
SETTING=python3 -m qechw --config $(CONFIG) config
# the default output folders (paths.output, paths.check)
OUT=../../../build/data/decoder_timing/hw
CHECK=../../../build/check/decoder_timing/hw

help:
	@sed -n '4,20p' Makefile | sed 's/^# //'

$(VENV)/.installed: env/requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet -r env/requirements.txt
	touch $@

$(VENV)/.installed-gpu: env/requirements-gpu.txt | $(VENV)/.installed
	$(PY) -m pip install --quiet -r env/requirements-gpu.txt
	touch $@

data: syndromes transfer
	$(MAKE) stats

syndromes transfer mb-inputs mb-collect stats sanity: | $(VENV)/.installed
	$(QECHW) $@

mb-calibrate: mb-collect
	$(QECHW) $@

check: | $(VENV)/.installed
	$(QECHW) check

gpu: | $(VENV)/.installed-gpu
	@dev=$$($(SETTING) gpu.device); clk=$$($(SETTING) gpu.sm_clock_mhz); \
	sudo -n nvidia-smi -i $$dev -lgc $$clk,$$clk > /dev/null 2>&1 && echo "SM clock locked at $$clk MHz"; \
	{ nvidia-smi -i $$dev -q | grep -E "Product Name|Driver Version|CUDA Version|Persistence|Compute Mode|Max Clocks" ; \
	  nvidia-smi --query-gpu=index,name,driver_version,pstate,clocks.sm,clocks.max.sm,clocks.mem,persistence_mode,compute_mode --format=csv ; \
	  $(PY) -m pip freeze | grep -iE "^(cudaq-qec|cupti-python)=" ; } > env/gpu_env.txt 2>&1; \
	$(QECHW) gpu; status=$$?; \
	sudo -n nvidia-smi -i $$dev -rgc > /dev/null 2>&1 && echo "SM clock reset"; exit $$status

# gpu.host: the repository is mirrored under gpu.remote_root there (the CPU and hardware experiments and
# data/literature); the syndromes are generated there, the GPU raw files come back into $(OUT)/raw
gpu-remote:
	@host=$$($(SETTING) gpu.host); root=$$($(SETTING) gpu.remote_root); \
	test -n "$$host" || { echo "set gpu.host in $(CONFIG)"; exit 1; }; \
	ssh $$host "mkdir -p $$root/experiments/decoder_timing $$root/data/literature" && \
	rsync -az --exclude .venv --exclude __pycache__ --exclude build --exclude target ../ $$host:$$root/experiments/decoder_timing/ && \
	rsync -az ../../../data/literature/ $$host:$$root/data/literature/ && \
	ssh $$host "cd $$root/experiments/decoder_timing/hw && make syndromes gpu CONFIG=$(CONFIG)" && \
	mkdir -p $(OUT)/raw && \
	rsync -az "$$host:$$root/build/data/decoder_timing/hw/raw/gpu_*" $(OUT)/raw/ && \
	rsync -az $$host:$$root/experiments/decoder_timing/hw/env/gpu_env.txt env/

# on the simulation host, standard library only: runs the queues of config.toml inside microblossom.container
mb-sim:
	python3 -m qechw --config $(CONFIG) mb-sim

test: | $(VENV)/.installed
	PYTHONPATH=.. $(PY) -m pytest -q

env: | $(VENV)/.installed
	env/collect_env.sh $(PY)

clean:
	rm -rf $(OUT) $(CHECK)

.PHONY: help data syndromes transfer gpu gpu-remote mb-inputs mb-sim mb-collect mb-calibrate stats sanity check test env clean
