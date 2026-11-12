# N1 (Fig. 5 of the paper): transport time T_up against the number of controllers on 10GbE, from the network
# statistics (default: the experiment's build/data/network; DATA=../../data/zenodo/network for the recorded data).
#   make          build/N1.tex (input by the paper) and build/N1.pdf (preview)
#   make clean    remove build/
OUTPUT=build
DATA=../../build/data/network
R=Rscript
LATEX=pdflatex -interaction=batchmode -halt-on-error
PREVIEW_DOC=\documentclass{standalone}\usepackage{tikz}\renewcommand{\rmdefault}{ptm}\begin{document}\input{$*.tex}\end{document}

# Inputs: the aggregated simulation runs (sweep and edge set)
SIM=$(addprefix $(DATA)/sim/stats/,summary.csv edge_summary.csv)

# Outputs
FIG=$(OUTPUT)/N1.tex
PREVIEW=$(OUTPUT)/N1.pdf

OUTDIRS=$(OUTPUT)

repro: $(FIG) $(PREVIEW)
	@echo "Up to date!"

$(OUTDIRS):
	mkdir -p $@

$(FIG): plot.R $(SIM) | $(OUTDIRS)
	$(R) $< $(OUTPUT) $(DATA)

# PDF preview of the TikZ figure, typeset on its own with the Times text font of IEEEtran
$(OUTPUT)/%.pdf: $(OUTPUT)/%.tex
	cd $(OUTPUT) && $(LATEX) -jobname=$* '$(PREVIEW_DOC)' > /dev/null && rm $*.aux $*.log

clean:
	rm -rf $(OUTPUT)

.PHONY: repro clean
