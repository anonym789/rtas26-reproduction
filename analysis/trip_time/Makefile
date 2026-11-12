# F3 (Fig. 7 of the paper): trip time per configuration for three qubit technologies, from the trip-time summary
# (default: build/data/trip_time; DATA=../../data/zenodo/trip_time for the recorded one) and data/literature.
#   make          build/F3.tex (input by the paper) and build/F3.pdf (preview)
#   make clean    remove build/
OUTPUT=build
DATA=../../build/data/trip_time
LITERATURE=../../data/literature
R=Rscript
LATEX=pdflatex -interaction=batchmode -halt-on-error
PREVIEW_DOC=\documentclass{standalone}\usepackage{tikz}\renewcommand{\rmdefault}{ptm}\begin{document}\input{$*.tex}\end{document}

# Inputs: the assembled trip times per configuration and the technology parameters
INPUTS=$(DATA)/trip_summary.csv $(LITERATURE)/trip_technology.csv

# Outputs
FIG=$(OUTPUT)/F3.tex
PREVIEW=$(OUTPUT)/F3.pdf

OUTDIRS=$(OUTPUT)

repro: $(FIG) $(PREVIEW)
	@echo "Up to date!"

$(OUTDIRS):
	mkdir -p $@

$(FIG): plot_trip.R $(INPUTS) | $(OUTDIRS)
	$(R) $< $(OUTPUT) $(DATA) $(LITERATURE)

# PDF preview of the TikZ figure, typeset on its own with the Times text font of IEEEtran
$(OUTPUT)/%.pdf: $(OUTPUT)/%.tex
	cd $(OUTPUT) && $(LATEX) -jobname=$* '$(PREVIEW_DOC)' > /dev/null && rm $*.aux $*.log

clean:
	rm -rf $(OUTPUT)

.PHONY: repro clean
