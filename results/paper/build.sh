#!/usr/bin/env bash
# Offline build for the Springer sn-jnl paper -> main.pdf
# Prerequisite (one-time): a TeX Live install, e.g.
#   sudo apt install -y texlive-latex-base texlive-latex-recommended \
#       texlive-latex-extra texlive-science texlive-fonts-recommended latexmk
# Usage: ./build.sh   (run from the results/paper/ directory)
set -e
cd "$(dirname "$0")"

if command -v latexmk >/dev/null 2>&1; then
    latexmk -pdf -bibtex -interaction=nonstopmode main.tex
elif command -v pdflatex >/dev/null 2>&1; then
    echo "latexmk not found; using manual pdflatex + bibtex sequence"
    pdflatex -interaction=nonstopmode main.tex
    bibtex main
    pdflatex -interaction=nonstopmode main.tex
    pdflatex -interaction=nonstopmode main.tex
else
    echo "ERROR: no LaTeX found. Install TeX Live first (see header comment)." >&2
    exit 1
fi
echo ">>> Done: $(pwd)/main.pdf"
