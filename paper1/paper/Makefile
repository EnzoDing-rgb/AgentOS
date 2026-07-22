TEXBIN := /usr/local/texlive/2026/bin/x86_64-linux
LATEXMK := PATH=$(TEXBIN):$$PATH latexmk

SRC_DIR := src
BUILD_DIR := build
TEX := $(SRC_DIR)/main-ICML.tex

PDF_NAME := BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks-ICML.pdf
JOB := $(PDF_NAME:.pdf=)
BUILD_PDF := $(BUILD_DIR)/$(PDF_NAME)

.PHONY: all pdf clean distclean

all: pdf

pdf: $(PDF_NAME)

# Compile in src/ so \bibliography{references} and local .sty/.bst resolve;
# write every intermediate into build/; install the finished PDF at paper/.
$(PDF_NAME): $(TEX) $(SRC_DIR)/references.bib \
		$(SRC_DIR)/icml2026.sty $(SRC_DIR)/icml2026.bst \
		$(SRC_DIR)/algorithm.sty $(SRC_DIR)/algorithmic.sty
	mkdir -p $(BUILD_DIR)
	cd $(SRC_DIR) && $(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error \
		-outdir=../$(BUILD_DIR) -jobname=$(JOB) main-ICML.tex
	cp -f $(BUILD_PDF) $(PDF_NAME)

clean:
	cd $(SRC_DIR) && $(LATEXMK) -C -outdir=../$(BUILD_DIR) -jobname=$(JOB) main-ICML.tex || true
	rm -rf $(BUILD_DIR)
	mkdir -p $(BUILD_DIR)

distclean: clean
	rm -f $(PDF_NAME)
