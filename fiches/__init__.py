"""
fiches — Module de génération de fiches techniques.

Architecture:
    fiches.config    -> chargement & fusion JSON défauts + événement
    fiches.renderer  -> rendu Jinja2 -> HTML
    fiches.exporter  -> export PDF via WeasyPrint
    fiches.validator -> validation des données

Conçu pour permettre l'ajout futur d'un module 'devis' sans modification.
"""

from .config import load_config, deep_merge, validate
from .renderer import render_html
from .exporter import export_pdf

__version__ = "1.0.0"
__all__ = ["load_config", "deep_merge", "validate", "render_html", "export_pdf"]
