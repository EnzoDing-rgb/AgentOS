PDF := BudgetFlow_Value_Aware_Budget_Governance_for_Agent_Tasks.pdf
TEXBIN := /usr/local/texlive/2026/bin/x86_64-linux
LATEXMK := PATH=$(TEXBIN):$$PATH latexmk

.PHONY: all clean distclean

all: $(PDF)

$(PDF): main.tex references.bib icml2026.sty icml2026.bst algorithm.sty algorithmic.sty
	$(LATEXMK) -pdf -interaction=nonstopmode -halt-on-error main.tex
	cp main.pdf $(PDF)

clean:
	$(LATEXMK) -c main.tex

distclean: clean
	rm -f main.pdf $(PDF)
