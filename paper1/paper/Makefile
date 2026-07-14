TEXBIN := /usr/local/texlive/2026/bin/x86_64-linux
LATEXMK := PATH=$(TEXBIN):$$PATH latexmk

PDF_ICML := BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks-ICML.pdf
PDF_ACM := BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks-ACM.pdf
JOB_ICML := $(PDF_ICML:.pdf=)
JOB_ACM := $(PDF_ACM:.pdf=)

.PHONY: all icml acm clean distclean

all: icml acm

icml: $(PDF_ICML)

acm: $(PDF_ACM)

$(PDF_ICML): main-ICML.tex references.bib icml2026.sty icml2026.bst algorithm.sty algorithmic.sty
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -jobname=$(JOB_ICML) main-ICML.tex

$(PDF_ACM): main-ACM.tex references.bib algorithm.sty algorithmic.sty
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -jobname=$(JOB_ACM) main-ACM.tex

clean:
	$(LATEXMK) -c -jobname=$(JOB_ICML) main-ICML.tex || true
	$(LATEXMK) -c -jobname=$(JOB_ACM) main-ACM.tex || true
	rm -f main-ICML.pdf main-ACM.pdf

distclean: clean
	rm -f $(PDF_ICML) $(PDF_ACM)
