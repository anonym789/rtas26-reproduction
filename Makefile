# Reproduction package of "Too late to React? An End-to-End Timing Study of Fault-Tolerant Quantum Computers".
# The experiments (experiments/) produce the data in build/data, the figure scripts (analysis/) draw S1, N1 and F3
# from it. See README.md.
#   make                list the targets
#   make data           the experiments that run on an ordinary machine -> build/data (days; settings in README.md)
#   make trip           the trip-time summary of F3 (needs the GPU and Micro Blossom data as well)
#   make figures        S1, N1 and F3 from build/data -> build/figures/data
#   make figures DATA=data/zenodo   from the recorded data, if present -> build/figures/zenodo
#   make check          regenerate the recorded tables of every experiment and compare (skipped without data/zenodo)
#   make test           unit and regression tests of the experiments
#   make clean          remove build/ and the figure folders' build/
#   make docker         run a target in the Docker image (TARGET=test by default; outputs in build/)
#   make docker-image   build the Docker image
DATA ?= build/data
FIGURES = build/figures/$(notdir $(DATA))
EXPERIMENTS = experiments/network experiments/decoder_timing experiments/decoder_timing/hw

help:
	@sed -n '4,13p' Makefile | sed 's/^# //'

data:
	$(MAKE) -C experiments/network data
	$(MAKE) -C experiments/decoder_timing data
	$(MAKE) -C experiments/decoder_timing/hw data
	@echo "next: the GPU runs and the Micro Blossom simulation (README.md), then make trip figures"

trip:
	$(MAKE) -C experiments/trip_time data

figures:
	$(MAKE) -C analysis DATA=$(abspath $(DATA)) OUTPUT=$(abspath $(FIGURES))

check:
	for e in $(EXPERIMENTS) experiments/trip_time; do $(MAKE) -C $$e check || exit 1; done

test:
	for e in $(EXPERIMENTS); do $(MAKE) -C $$e test || exit 1; done

clean:
	rm -rf build
	$(MAKE) -C analysis clean

# The image holds the repository (without data and environments) and every tool; build/ is mounted for the outputs,
# data/zenodo read-only when it exists. Examples: make docker TARGET=check, make docker TARGET="figures DATA=data/zenodo"
IMAGE = rtas-reproduction
TARGET = test
docker-image:
	docker build -t $(IMAGE) .

docker: docker-image
	mkdir -p build
	docker run --rm -u $$(id -u):$$(id -g) -e HOME=/tmp -v $(CURDIR)/build:/repro/build \
	  $(if $(wildcard data/zenodo),-v $(CURDIR)/data/zenodo:/repro/data/zenodo:ro) $(IMAGE) make $(TARGET)

.PHONY: help data trip figures check test clean docker docker-image
