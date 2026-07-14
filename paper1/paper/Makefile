TEXBIN := /usr/local/texlive/2026/bin/x86_64-linux
LATEXMK := PATH=$(TEXBIN):$$PATH latexmk

PDF_ICML := BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks-ICML.pdf
PDF_ACM := BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks-ACM.pdf

.PHONY: all icml acm clean distclean

all: icml acm

icml: $(PDF_ICML)

acm: $(PDF_ACM)

$(PDF_ICML): main-ICML.tex references.bib icml2026.sty icml2026.bst algorithm.sty algorithmic.sty
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -jobname=main-ICML main-ICML.tex
	cp main-ICML.pdf $(PDF_ICML)

$(PDF_ACM): main-ACM.tex references.bib algorithm.sty algorithmic.sty
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error -jobname=main-ACM main-ACM.tex
	cp main-ACM.pdf $(PDF_ACM)

clean:
	$(LATEXMK) -c -jobname=main-ICML main-ICML.tex || true
	$(LATEXMK) -c -jobname=main-ACM main-ACM.tex || true

distclean: clean
	rm -f main-ICML.pdf main-ACM.pdf $(PDF_ICML) $(PDF_ACM)
