# Trip time of the configurations of F3 (Fig. 7 of the paper), assembled from the decoder and network data of the
# experiments (build/data) and the trip-time parameters (data/literature). Writes build/data/trip_time/trip_summary.csv.
#   make                list the targets
#   make data           build/data/trip_time/trip_summary.csv from the experiments' data in build/data
#   make check          assemble it from the recorded data (data/zenodo) into build/check and compare with the record
#   make clean          remove this step's data and check folders under build/
#   make <target> DATA=<folder>   assemble from another data folder (with the layout of data/zenodo)
DATA=../../build/data
LITERATURE=../../data/literature
OUTPUT=../../build/data/trip_time
RECORD=../../data/zenodo
CHECK=../../build/check/trip_time
R=Rscript

# Inputs: per-shot decoding times of the decoder sources and the network summary, relative to a data folder
INPUTS=$(addprefix decoder_timing/raw/,pymatching_surface_d5_p0.001.csv.gz pymatching_surface_d9_p0.001.csv.gz \
	pymatching_surface_d13_p0.001.csv.gz pymatching_surface_d17_p0.001.csv.gz pymatching_surface_d25_p0.001.csv.gz \
	fusionblossom_surface_d9_p0.001.csv.gz fusionblossom_surface_d13_p0.001.csv.gz chromobius_color_d5_p0.001.csv.gz \
	chromobius_color_d9_p0.001.csv.gz chromobius_color_d13_p0.001.csv.gz bposd_bb_d12_p0.001.csv.gz \
	bplsd_bb_d12_p0.001.csv.gz bposd_surface_d9_p0.001.csv.gz) \
	$(addprefix decoder_timing/hw/raw/,fpga_transfer_relaybp1_bb_d6_p0.001.csv.gz \
	fpga_transfer_relaybp1_bb_d12_p0.001.csv.gz fpga_sim_microblossombatch_surface_d9_p0.001.csv.gz \
	fpga_sim_microblossombatch_surface_d13_p0.001.csv.gz gpu_measured_relaybp1_bb_d6_p0.001.csv.gz \
	gpu_measured_relaybp1_bb_d12_p0.001.csv.gz) \
	network/sim/stats/summary.csv
TERMS=$(addprefix $(LITERATURE)/,trip_technology.csv trip_interconnect.csv trip_decoder_literature.csv)

help:
	@sed -n '3,7p' Makefile | sed 's/^# //'

data: $(OUTPUT)/trip_summary.csv

$(OUTPUT)/trip_summary.csv: assemble.R $(addprefix $(DATA)/,$(INPUTS)) $(TERMS)
	mkdir -p $(OUTPUT)
	$(R) $< $(OUTPUT) $(DATA) $(LITERATURE)

check: assemble.R check.R
	@if [ -f $(RECORD)/trip_time/trip_summary.csv ]; then \
	  mkdir -p $(CHECK) && $(R) assemble.R $(CHECK) $(RECORD) $(LITERATURE) && \
	  $(R) check.R $(CHECK)/trip_summary.csv $(RECORD)/trip_time/trip_summary.csv; \
	else echo "no recorded campaign in $(RECORD): check skipped"; fi

clean:
	rm -rf $(OUTPUT) $(CHECK)

.PHONY: help data check clean
