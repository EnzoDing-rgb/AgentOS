TEXBIN := /usr/local/texlive/2026/bin/x86_64-linux
LATEXMK := PATH=$(TEXBIN):$$PATH latexmk

SRC_DIR := src
BUILD_DIR := build

ICML_TEX := $(SRC_DIR)/main-ICML.tex
AAAI_TEX := $(SRC_DIR)/main-AAAI.tex

ICML_PDF := BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks-ICML.pdf
AAAI_PDF := BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks-AAAI.pdf
AAAI_CHECKLIST_PDF := BudgetFlow_Reproducibility_Checklist-AAAI2027.pdf

ICML_JOB := $(ICML_PDF:.pdf=)
AAAI_JOB := $(AAAI_PDF:.pdf=)

.PHONY: all pdf pdf-icml pdf-aaai pdf-aaai-checklist clean distclean

all: pdf

pdf: pdf-icml pdf-aaai

pdf-icml: $(ICML_PDF)

pdf-aaai: $(AAAI_PDF)

pdf-aaai-checklist: $(AAAI_CHECKLIST_PDF)

$(ICML_PDF): $(ICML_TEX) $(SRC_DIR)/references.bib \
		$(SRC_DIR)/icml2026.sty $(SRC_DIR)/icml2026.bst \
		$(SRC_DIR)/algorithm.sty $(SRC_DIR)/algorithmic.sty
	mkdir -p $(BUILD_DIR)
	cd $(SRC_DIR) && $(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error \
		-outdir=../$(BUILD_DIR) -jobname=$(ICML_JOB) main-ICML.tex
	cp -f $(BUILD_DIR)/$(ICML_PDF) $(ICML_PDF)

$(AAAI_PDF): $(AAAI_TEX) $(SRC_DIR)/references.bib \
		$(SRC_DIR)/aaai2027.sty $(SRC_DIR)/aaai2027.bst \
		$(SRC_DIR)/placeins.sty \
		$(SRC_DIR)/algorithm.sty $(SRC_DIR)/algorithmic.sty
	mkdir -p $(BUILD_DIR)
	cd $(SRC_DIR) && $(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error \
		-outdir=../$(BUILD_DIR) -jobname=$(AAAI_JOB) main-AAAI.tex
	cp -f $(BUILD_DIR)/$(AAAI_PDF) $(AAAI_PDF)

$(AAAI_CHECKLIST_PDF): $(SRC_DIR)/ReproducibilityChecklist-AAAI2027.tex \
		$(SRC_DIR)/aaai2027.sty $(SRC_DIR)/placeins.sty
	mkdir -p $(BUILD_DIR)
	cd $(SRC_DIR) && $(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error \
		-outdir=../$(BUILD_DIR) -jobname=$(AAAI_CHECKLIST_PDF:.pdf=) ReproducibilityChecklist-AAAI2027.tex
	cp -f $(BUILD_DIR)/$(AAAI_CHECKLIST_PDF) $(AAAI_CHECKLIST_PDF)

clean:
	cd $(SRC_DIR) && $(LATEXMK) -C -outdir=../$(BUILD_DIR) -jobname=$(ICML_JOB) main-ICML.tex || true
	cd $(SRC_DIR) && $(LATEXMK) -C -outdir=../$(BUILD_DIR) -jobname=$(AAAI_JOB) main-AAAI.tex || true
	cd $(SRC_DIR) && $(LATEXMK) -C -outdir=../$(BUILD_DIR) -jobname=$(AAAI_CHECKLIST_PDF:.pdf=) ReproducibilityChecklist-AAAI2027.tex || true
	rm -rf $(BUILD_DIR)
	mkdir -p $(BUILD_DIR)

distclean: clean
	rm -f $(ICML_PDF) $(AAAI_PDF) $(AAAI_CHECKLIST_PDF)
