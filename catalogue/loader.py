"""
catalogue.loader — Chargement et sauvegarde des fichiers JSON du catalogue.
"""

import json
from pathlib import Path
from typing import Optional


class CatalogueError(Exception):
    """Erreur de chargement, validation ou sauvegarde du catalogue."""
    pass


def load_json(path: Path) -> dict:
    """Charge un JSON. Lève CatalogueError si problème."""
    path = Path(path)
    if not path.exists():
        raise CatalogueError(f"Fichier introuvable : {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise CatalogueError(f"JSON invalide ({path.name}) : {e}")


def save_json(path: Path, data: dict) -> None:
    """Sauvegarde un dict en JSON avec indentation 4."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_catalogue(catalogue_dir: Path) -> dict:
    """
    Charge l'intégralité du catalogue depuis un dossier.

    Args:
        catalogue_dir: chemin du dossier data/catalogue/

    Returns:
        dict avec clés 'equipements', 'packs', 'prestations'
    """
    catalogue_dir = Path(catalogue_dir)
    equipements = load_json(catalogue_dir / "equipements.json").get("equipements", {})
    packs = load_json(catalogue_dir / "packs.json").get("packs", {})
    prestations = load_json(catalogue_dir / "prestations.json").get("prestations", {})

    # Filtre les clés _doc_* (commentaires)
    packs = {k: v for k, v in packs.items() if not k.startswith("_")}
    prestations = {k: v for k, v in prestations.items() if not k.startswith("_")}
    equipements = {k: v for k, v in equipements.items() if not k.startswith("_")}

    return {
        "equipements": equipements,
        "packs": packs,
        "prestations": prestations,
    }


def save_catalogue(catalogue_dir: Path, catalogue: dict, section: Optional[str] = None) -> None:
    """
    Sauvegarde tout ou partie du catalogue.

    Args:
        catalogue_dir: dossier de destination
        catalogue: dict catalogue complet
        section: si fourni, ne sauve que cette section ('equipements', 'packs', 'prestations')
    """
    catalogue_dir = Path(catalogue_dir)
    sections = [section] if section else ["equipements", "packs", "prestations"]

    for sec in sections:
        if sec not in catalogue:
            raise CatalogueError(f"Section inconnue : {sec}")
        # Recharge le fichier existant pour préserver les clés _doc
        path = catalogue_dir / f"{sec}.json"
        if path.exists():
            existing = load_json(path)
        else:
            existing = {"_doc": "", "_schema_version": "1.0", sec: {}}
        existing[sec] = catalogue[sec]
        save_json(path, existing)


def get_photo_path(equipement_id: str, photos_dir: Path) -> Optional[Path]:
    """
    Trouve la photo d'un équipement. Essaie .png, .jpg, .webp dans l'ordre.

    Args:
        equipement_id: slug de l'équipement
        photos_dir: dossier contenant les photos

    Returns:
        Le chemin trouvé, ou None si aucune photo n'existe.
    """
    photos_dir = Path(photos_dir)
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = photos_dir / f"{equipement_id}{ext}"
        if candidate.exists():
            return candidate
    return None
