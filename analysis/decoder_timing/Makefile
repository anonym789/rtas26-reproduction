# S1 (Fig. 4 of the paper): per-shot decoding-time distributions on every platform, from the CPU and hardware data
# (default: the experiments' build/data/decoder_timing; DATA=../../data/zenodo/decoder_timing for the recorded data).
#   make          build/S1.tex (input by the paper), build/S1_stats.csv and build/S1.pdf (preview)
#   make clean    remove build/
OUTPUT=build
DATA=../../build/data/decoder_timing
R=Rscript
LATEX=pdflatex -interaction=batchmode -halt-on-error
PREVIEW_DOC=\documentclass{standalone}\usepackage{tikz}\renewcommand{\rmdefault}{ptm}\begin{document}\input{$*.tex}\end{document}

# Inputs: the per-shot files of the seven panels (CPU row, FPGA and GPU row)
RAW=$(addprefix $(DATA)/raw/,pymatching_surface_d13_p0.001.csv.gz fusionblossom_surface_d13_p0.001.csv.gz \
	chromobius_color_d13_p0.001.csv.gz bposd_bb_d12_p0.001.csv.gz)
RAW_HW=$(addprefix $(DATA)/hw/raw/,fpga_transfer_relaybp1_bb_d12_p0.001.csv.gz \
	fpga_sim_microblossombatch_surface_d13_p0.001.csv.gz gpu_measured_relaybp1_bb_d12_p0.001.csv.gz)

# Outputs
FIG=$(OUTPUT)/S1.tex
STATS=$(OUTPUT)/S1_stats.csv
PREVIEW=$(OUTPUT)/S1.pdf

OUTDIRS=$(OUTPUT)

repro: $(FIG) $(STATS) $(PREVIEW)
	@echo "Up to date!"

$(OUTDIRS):
	mkdir -p $@

$(FIG) $(STATS) &: plot_shape.R $(RAW) $(RAW_HW) | $(OUTDIRS)
	$(R) $< $(OUTPUT) $(DATA)

# PDF preview of the TikZ figure, typeset on its own with the Times text font of IEEEtran
$(OUTPUT)/%.pdf: $(OUTPUT)/%.tex
	cd $(OUTPUT) && $(LATEX) -jobname=$* '$(PREVIEW_DOC)' > /dev/null && rm $*.aux $*.log

clean:
	rm -rf $(OUTPUT)

.PHONY: repro clean
