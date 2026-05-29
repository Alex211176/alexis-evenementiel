# Raccourcis pour le projet Fiche Technique
# Usage : make <cible>

# Sur macOS Apple Silicon, WeasyPrint a besoin de trouver les libs Homebrew.
# SIP empêche l'héritage de DYLD_* depuis le shell, on le redéfinit ici.
export DYLD_FALLBACK_LIBRARY_PATH := /opt/homebrew/lib:$(DYLD_FALLBACK_LIBRARY_PATH)

.PHONY: help install web cli example clean

help:
	@echo "Cibles disponibles :"
	@echo "  make install   - Installe les dépendances Python"
	@echo "  make web       - Lance l'UI web Flask (http://localhost:5001)"
	@echo "  make example   - Génère la fiche mariage exemple (HTML + PDF)"
	@echo "  make clean     - Supprime les fichiers générés (data/output/)"

install:
	pip install -r requirements.txt

web:
	python web/app.py

example:
	python scripts/generate.py data/events/exemple_mariage.json --pdf

clean:
	rm -f data/output/*.html data/output/*.pdf
	@echo "✅ Sortie nettoyée"
