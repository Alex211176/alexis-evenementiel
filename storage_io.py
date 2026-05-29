"""
storage_io.py — Helpers d'entrées/sorties basés sur le storage.

Ces fonctions remplacent les lectures/écritures disque de l'app locale.
Elles NE dupliquent pas la logique métier : elles se contentent de fournir
les mêmes dicts à tes fonctions pures (resoudre_pack, resoudre_evenement,
render_devis_html...). Le filtrage des clés "_" et le deep_merge réutilisent
ton code existant (fiches.config.deep_merge).
"""

from datetime import datetime

from fiches.config import deep_merge

DEFAULTS_REL = "defaults/prestataire.json"


def _clean(section: dict) -> dict:
    return {k: v for k, v in section.items() if not k.startswith("_")}


def load_catalogue(storage) -> dict:
    """Charge le catalogue (3 fichiers) via le storage. Même forme que catalogue.loader."""
    eq = storage.read_json("catalogue/equipements.json").get("equipements", {})
    pk = storage.read_json("catalogue/packs.json").get("packs", {})
    pr = storage.read_json("catalogue/prestations.json").get("prestations", {})
    return {
        "equipements": _clean(eq),
        "packs": _clean(pk),
        "prestations": _clean(pr),
    }


def save_catalogue_section(storage, catalogue: dict, section: str) -> None:
    """Sauvegarde une section du catalogue en préservant les clés _doc."""
    rel = f"catalogue/{section}.json"
    if storage.exists(rel):
        existing = storage.read_json(rel)
    else:
        existing = {"_doc": "", "_schema_version": "1.0", section: {}}
    existing[section] = catalogue[section]
    storage.write_json(storage_path := rel, existing)


def load_defaults(storage) -> dict:
    return storage.read_json(DEFAULTS_REL)


def save_defaults(storage, data: dict) -> None:
    storage.write_json(DEFAULTS_REL, data)


def list_events(storage) -> list:
    """Noms de fichiers .json dans events/."""
    return [n for n in storage.list_folder("events") if n.endswith(".json")]


def load_event(storage, filename: str) -> dict:
    return storage.read_json(f"events/{filename}")


def save_event(storage, filename: str, data: dict) -> None:
    storage.write_json(f"events/{filename}", data)


def delete_event(storage, filename: str) -> None:
    storage.delete(f"events/{filename}")


def load_config_merged(storage, event_filename: str) -> dict:
    """
    Équivalent storage de fiches.config.load_config :
    fusionne defaults + événement et auto-remplit la date d'émission.
    """
    defaults = storage.read_json(DEFAULTS_REL)
    event = storage.read_json(f"events/{event_filename}")
    data = deep_merge(defaults, event)
    doc = data.setdefault("document", {})
    if not doc.get("date_emission"):
        doc["date_emission"] = datetime.now().strftime("%d/%m/%Y")
    return data
