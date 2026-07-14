TEXBIN := /usr/local/texlive/2026/bin/x86_64-linux
LATEXMK := PATH=$(TEXBIN):$$PATH latexmk

PDF_ICML := BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks-ICML.pdf
PDF_AGENTICDEV := BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks-AgenticDev.pdf
JOB_ICML := $(PDF_ICML:.pdf=)
JOB_AGENTICDEV := $(PDF_AGENTICDEV:.pdf=)

.PHONY: all icml agenticdev clean distclean

all: icml agenticdev

icml: $(PDF_ICML)

agenticdev: $(PDF_AGENTICDEV)

$(PDF_ICML): main-ICML.tex references.bib icml2026.sty icml2026.bst algorithm.sty algorithmic.sty
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -jobname=$(JOB_ICML) main-ICML.tex

$(PDF_AGENTICDEV): main-AgenticDev.tex references.bib algorithm.sty algorithmic.sty
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -jobname=$(JOB_AGENTICDEV) main-AgenticDev.tex

clean:
	$(LATEXMK) -c -jobname=$(JOB_ICML) main-ICML.tex || true
	$(LATEXMK) -c -jobname=$(JOB_AGENTICDEV) main-AgenticDev.tex || true

distclean: clean
	rm -f $(PDF_ICML) $(PDF_AGENTICDEV)
