"""
devis — Module de génération et gestion des devis.

Workflow:
    1. L'événement contient les données métier (pack, retraits, supplements, client)
    2. devis.renderer génère le HTML du devis depuis l'événement résolu
    3. devis.exporter génère le PDF via WeasyPrint
    4. devis.signature gère les 3 modes de signature client
    5. devis.numbering gère la numérotation auto (FT-2026-XXXX-DV01)
"""

from .renderer import render_devis_html
from .exporter import export_devis_pdf
from .numbering import generate_devis_ref, current_devis_version
from .signature import (
    save_signature_canvas,
    save_signature_bon_accord,
    init_signature_email,
    verify_signature_token,
)

__version__ = "1.0.0"
__all__ = [
    "render_devis_html", "export_devis_pdf",
    "generate_devis_ref", "current_devis_version",
    "save_signature_canvas", "save_signature_bon_accord",
    "init_signature_email", "verify_signature_token",
]
