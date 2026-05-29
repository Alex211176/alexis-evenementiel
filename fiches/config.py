"""
fiches.config — Chargement, fusion et validation des données de fiche.
"""

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Erreur de configuration ou de validation."""
    pass


def load_json(path: Path) -> dict:
    """Charge un JSON depuis un chemin, lève ConfigError si introuvable."""
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Fichier introuvable : {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"JSON invalide ({path.name}) : {e}")


def deep_merge(base: dict, override: dict) -> dict:
    """
    Fusion récursive : override gagne sur base.
    - sous-dicts fusionnés en profondeur
    - listes remplacées intégralement (logique pour matériel par ex.)
    - clés commençant par '_' ignorées (docstrings JSON)
    """
    result = deepcopy(base)
    for key, value in override.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(defaults_path: Path, event_path: Path) -> dict:
    """Charge et fusionne défauts + événement, auto-remplit la date si vide."""
    defaults = load_json(defaults_path)
    event = load_json(event_path)
    data = deep_merge(defaults, event)

    # Auto-fill date d'émission si absente
    doc = data.setdefault("document", {})
    if not doc.get("date_emission"):
        doc["date_emission"] = datetime.now().strftime("%d/%m/%Y")

    return data


REQUIRED_FIELDS = {
    "prestataire": ["nom", "siret"],
    "document": ["reference", "date_emission"],
    "event": ["name", "location"],
}


def validate(data: dict) -> None:
    """Vérifie la présence des champs critiques. Lève ConfigError sinon."""
    missing = []
    for section, fields in REQUIRED_FIELDS.items():
        section_data = data.get(section, {})
        if not isinstance(section_data, dict):
            missing.append(f"{section} (section manquante ou invalide)")
            continue
        for field in fields:
            if not section_data.get(field):
                missing.append(f"{section}.{field}")
    if missing:
        raise ConfigError(
            "Champs obligatoires manquants : " + ", ".join(missing)
        )
