"""
devis.numbering — Numérotation automatique des devis.

Format: <REF_EVENEMENT>-DV<NN>
    - REF_EVENEMENT : ex "FT-2026-0042"
    - NN : numéro de version du devis pour cet événement, 2 chiffres (01, 02, ...)

Permet de gérer plusieurs versions d'un devis pour un même événement (renégociation).
"""

import re


def current_devis_version(event: dict) -> int:
    """
    Retourne le numéro de version courant du devis dans l'événement.
    0 si pas de devis encore généré.
    """
    devis = event.get("devis", {}) or {}
    return int(devis.get("version", 0))


def generate_devis_ref(event: dict, force_new_version: bool = False) -> str:
    """
    Génère la référence devis pour l'événement.

    Args:
        event: dict événement (doit contenir document.reference)
        force_new_version: si True, incrémente la version (re-négociation)

    Returns:
        ex: "FT-2026-0042-DV01"
    """
    ref_event = event.get("document", {}).get("reference", "FT-XXXX")
    version = current_devis_version(event)

    if force_new_version or version == 0:
        version += 1

    return f"{ref_event}-DV{version:02d}"
