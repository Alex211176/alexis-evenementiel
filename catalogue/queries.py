"""
catalogue.queries — Requêtes haut niveau pour l'UI admin.
"""

from typing import Dict, List


def lister_categories_equipements(equipements: Dict) -> List[str]:
    """Retourne la liste des catégories distinctes."""
    cats = set()
    for eq in equipements.values():
        cats.add(eq.get("categorie", "autre"))
    return sorted(cats)


def equipements_par_categorie(equipements: Dict) -> Dict[str, list]:
    """Groupe les équipements par catégorie."""
    groupes = {}
    for eq_id, eq in equipements.items():
        cat = eq.get("categorie", "autre")
        groupes.setdefault(cat, []).append({"id": eq_id, **eq})
    # Tri alphabétique par nom dans chaque catégorie
    for cat in groupes:
        groupes[cat].sort(key=lambda x: x.get("nom", ""))
    return groupes


def packs_par_categorie(packs: Dict) -> Dict[str, list]:
    """Groupe les packs par catégorie."""
    groupes = {}
    for pack_id, pack in packs.items():
        cat = pack.get("categorie", "autre")
        groupes.setdefault(cat, []).append({"id": pack_id, **pack})
    return groupes


# Labels lisibles pour les catégories
CATEGORIE_LABELS = {
    "son": "Son & Sonorisation",
    "lumiere": "Lumière",
    "video": "Vidéo & Projection",
    "effet": "Effets atmosphériques",
    "photo": "Photo & Photobooth",
    "regie": "Régie DJ",
    "energie": "Énergie",
    "divers": "Divers",
    "autre": "Autre",
    "dj_prive": "DJ Événements privés",
    "mariage": "Mariage",
    "photobooth": "Photobooth",
}


def label_categorie(cat: str) -> str:
    """Retourne le label lisible d'une catégorie."""
    return CATEGORIE_LABELS.get(cat, cat.replace("_", " ").title())
