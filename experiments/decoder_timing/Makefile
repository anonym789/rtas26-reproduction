# Timing of QEC decoders on a CPU (paper: Fig. 4, S1, CPU row). Every setting is in config.toml. The experiment
# writes its data into paths.output (build/data/decoder_timing of the repository, the layout of
# data/zenodo/decoder_timing); it never writes into data/.
#   make                list the targets
#   make data           the whole experiment: the measurement campaign (campaign.sh, about 1-2 days; set [campaign] first)
#   make syndromes      circuits, DEMs and detection events, regenerated from the seeds (about 1 GB)
#   make graphs         fusion-blossom graphs of the surface-code DEMs (needs the syndromes)
#   make drivers        build the C++/Rust timing drivers
#   make stats          statistics and pWCET fits of the campaign in paths.campaign
#   make sanity         plausibility checks -> SANITY.md
#   make check          regenerate the recorded statistics (data/zenodo/decoder_timing) into build/check and compare
#   make test           unit and regression tests
#   make env            machine, software and build flags -> env/ENVIRONMENT.md
#   make clean          remove this experiment's data and check files under build/ (the drivers and hw/ stay)
#   make push|run|status|pull   the campaign on the measurement machine campaign.host, from here
#   make <target> CONFIG=<file>   use another settings file
PYTHON ?= python3.12
CONFIG ?= config.toml
VENV=.venv
PY=$(VENV)/bin/python
QECDEC=$(PY) -m qecdec --config $(CONFIG)
# settings that a target needs before the environment exists (standard library only)
SETTING=python3 -m qecdec --config $(CONFIG) config
# the default output folders (paths.output, paths.check); the hardware experiment writes into $(OUT)/hw
OUT=../../build/data/decoder_timing
CHECK=../../build/check/decoder_timing
# extra cmake arguments; newer compilers need CMAKE_ARGS='-DCMAKE_CXX_FLAGS=-include\ cstdint'
CMAKE_ARGS ?=
# the fusion-blossom driver needs a nightly feature: rustup picks nightly from rust-toolchain.toml,
# a stable toolchain builds it with RUSTC_BOOTSTRAP=1
CARGO ?= cargo

PM=drivers/pymatching/build/pm_timing
CB=drivers/chromobius/build/cb_timing
FB=drivers/fusionblossom/target/release/fb_timing

help:
	@sed -n '4,16p' Makefile | sed 's/^# //'

$(VENV)/.installed: env/requirements.txt env/requirements-test.txt
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet -r env/requirements-test.txt
	touch $@

syndromes: | $(VENV)/.installed
	$(QECDEC) syndromes

graphs: | $(VENV)/.installed
	$(QECDEC) graphs

drivers: $(PM) $(CB) $(FB)

$(PM): drivers/pymatching/pm_timing.cc drivers/pymatching/CMakeLists.txt
	cmake -S drivers/pymatching -B drivers/pymatching/build -DCMAKE_BUILD_TYPE=Release $(CMAKE_ARGS) > drivers/pymatching/cmake.log
	cmake --build drivers/pymatching/build --target pm_timing -j8 > drivers/pymatching/make.log

$(CB): drivers/chromobius/cb_timing.cc drivers/chromobius/CMakeLists.txt
	cmake -S drivers/chromobius -B drivers/chromobius/build -DCMAKE_BUILD_TYPE=Release $(CMAKE_ARGS) > drivers/chromobius/cmake.log
	cmake --build drivers/chromobius/build --target cb_timing -j8 > drivers/chromobius/make.log

$(FB): drivers/fusionblossom/src/main.rs drivers/fusionblossom/Cargo.toml
	cd drivers/fusionblossom && $(CARGO) build --release > cargo.log 2>&1

data: | $(VENV)/.installed
	./campaign.sh $(CONFIG)

stats: | $(VENV)/.installed
	$(QECDEC) stats

sanity: stats
	$(QECDEC) sanity

check: | $(VENV)/.installed
	$(QECDEC) check

test: | $(VENV)/.installed
	$(PY) -m pytest -q

env: | $(VENV)/.installed
	env/collect_env.sh 0 $(PY)

clean:
	rm -rf $(OUT)/syndromes $(OUT)/raw $(OUT)/stats $(OUT)/SANITY.md $(CHECK)/stats

# The measurement machine campaign.host: the repository is mirrored under campaign.remote_root there (this
# experiment and data/literature), the campaign runs with the same settings file, and pull fetches its output
# (without the syndrome samples) into $(OUT) here.
REMOTE=$$($(SETTING) campaign.host)
REMOTE_ROOT=$$($(SETTING) campaign.remote_root)
REMOTE_EXP=$(REMOTE_ROOT)/experiments/decoder_timing
REMOTE_OUT=$(REMOTE_ROOT)/build/data/decoder_timing
need-remote:
	@test -n "$$($(SETTING) campaign.host)" || { echo "set campaign.host in $(CONFIG)"; exit 1; }

push: need-remote
	ssh $(REMOTE) "mkdir -p $(REMOTE_EXP) $(REMOTE_ROOT)/data/literature"
	rsync -az --delete --exclude .venv --exclude build --exclude target --exclude __pycache__ --exclude hw ./ $(REMOTE):$(REMOTE_EXP)/
	rsync -az ../../data/literature/ $(REMOTE):$(REMOTE_ROOT)/data/literature/

run: push
	ssh $(REMOTE) "cd $(REMOTE_EXP) && nohup ./campaign.sh $(CONFIG) > campaign.log 2>&1 < /dev/null &"; echo started

status: need-remote
	ssh $(REMOTE) "cd $(REMOTE_EXP) && tail -5 campaign.log; tail -3 $(REMOTE_OUT)/raw/logs/bp_queue.log 2>/dev/null; ls $(REMOTE_OUT)/raw/*.csv.gz 2>/dev/null | wc -l"

pull: need-remote
	mkdir -p $(OUT)/syndromes
	rsync -az --exclude /syndromes/ --exclude /hw/ $(REMOTE):$(REMOTE_OUT)/ $(OUT)/
	rsync -az $(REMOTE):$(REMOTE_OUT)/syndromes/index.csv $(OUT)/syndromes/
	rsync -az $(REMOTE):$(REMOTE_EXP)/env/ env/
	rsync -az $(REMOTE):$(REMOTE_EXP)/campaign.log ./

.PHONY: help syndromes graphs drivers data stats sanity check test env clean need-remote push run status pull
