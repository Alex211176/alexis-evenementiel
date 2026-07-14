"""
poses/loader.py — Chargement et validation de la bibliothèque de poses.

La bibliothèque est embarquée dans le repo (poses/library.json), donc versionnée
avec le code : pas de latence Dropbox, rollback git possible. Ce module la charge,
la valide sommairement et renvoie les phases triées par `order` (l'ordre
chronologique de la journée), prêtes à l'affichage côté client comme côté
photographe.

Jalon 0 : lecture seule. Aucun état d'événement ici (viendra au jalon 1).
"""

import json
from pathlib import Path
from functools import lru_cache

_HERE = Path(__file__).resolve().parent
LIBRARY_PATH = _HERE / "library.json"


class LibraryError(Exception):
    """La bibliothèque de poses est absente ou malformée."""


def _validate(lib: dict) -> None:
    """Contrôles structurels minimaux — on préfère échouer tôt et clairement."""
    if not isinstance(lib, dict):
        raise LibraryError("Racine JSON invalide (objet attendu).")
    phases = lib.get("phases")
    if not isinstance(phases, list) or not phases:
        raise LibraryError("Clé 'phases' absente ou vide.")

    seen_phase_ids = set()
    seen_pose_ids = set()
    for ph in phases:
        pid = ph.get("id")
        if not pid:
            raise LibraryError("Une phase n'a pas d'id.")
        if pid in seen_phase_ids:
            raise LibraryError(f"Id de phase dupliqué : {pid}")
        seen_phase_ids.add(pid)
        if not isinstance(ph.get("order"), int):
            raise LibraryError(f"Phase '{pid}' : 'order' manquant ou non entier.")
        poses = ph.get("poses")
        if not isinstance(poses, list) or not poses:
            raise LibraryError(f"Phase '{pid}' : 'poses' absente ou vide.")
        for pose in poses:
            poid = pose.get("id")
            if not poid:
                raise LibraryError(f"Phase '{pid}' : une pose sans id.")
            if poid in seen_pose_ids:
                raise LibraryError(f"Id de pose dupliqué (unicité globale) : {poid}")
            seen_pose_ids.add(poid)


# Catégorie transverse (« type de photo ») par phase — sert au filtre côté
# mariés et côté jour J. Recoupe les phases chronologiques.
_PHASE_CATEGORY = {
    "prep-mariee": "Préparatifs", "prep-marie": "Préparatifs",
    "details": "Détails", "details-reception": "Détails",
    "first-look": "Cérémonie", "ceremonie": "Cérémonie", "sortie": "Cérémonie",
    "famille": "Groupes", "temoins": "Groupes",
    "couple": "Couple",
    "portrait-mariee": "Portraits", "portrait-marie": "Portraits",
    "vin-honneur": "Réception", "repas": "Réception",
    "gateau": "Fête", "ouverture-bal": "Fête", "soiree": "Fête",
}
CATEGORY_ORDER = ["Préparatifs", "Détails", "Cérémonie", "Groupes",
                  "Couple", "Portraits", "Réception", "Fête"]


def categories_in_order(lib: dict) -> list:
    """Catégories réellement présentes, dans l'ordre canonique."""
    present = {ph.get("category") for ph in lib["phases"]}
    return [c for c in CATEGORY_ORDER if c in present]


@lru_cache(maxsize=1)
def load_library() -> dict:
    """
    Charge la bibliothèque, la valide et renvoie un dict avec :
      - meta   : métadonnées de la bibliothèque
      - phases : liste triée par `order` croissant (ordre chronologique)

    Mise en cache : la bibliothèque est statique en prod (embarquée). En dev, un
    redémarrage du serveur (déjà requis pour tout changement Python) rafraîchit
    le cache.
    """
    try:
        raw = LIBRARY_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise LibraryError(f"Bibliothèque introuvable : {LIBRARY_PATH}") from exc
    try:
        lib = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LibraryError(f"JSON invalide dans {LIBRARY_PATH.name} : {exc}") from exc

    _validate(lib)
    lib["phases"] = sorted(lib["phases"], key=lambda p: p["order"])
    for ph in lib["phases"]:
        ph["category"] = _PHASE_CATEGORY.get(ph["id"], "Autre")
    return lib


def count_poses(lib: dict) -> int:
    """Nombre total de poses, tous phases confondues."""
    return sum(len(ph.get("poses", [])) for ph in lib.get("phases", []))


def resolve_checklist(lib: dict, selected_ids, must_have_ids) -> list:
    """
    Check-list photographe : poses sélectionnées ∪ incontournables, groupées par
    phase et triées dans l'ordre chronologique (l'ordre `order` de la biblio).
    Fonction pure (aucun I/O), donc facile à tester.
    """
    selected = set(selected_ids or [])
    must = set(must_have_ids or [])
    shown = selected | must
    out = []
    for phase in lib["phases"]:
        rows = []
        for pose in phase["poses"]:
            if pose["id"] in shown:
                rows.append({
                    "id": pose["id"],
                    "title": pose["title"],
                    "desc": pose["desc"],
                    "selected": pose["id"] in selected,
                    "mustHave": pose["id"] in must,
                })
        if rows:
            out.append({
                "id": phase["id"],
                "label": phase["label"],
                "icon": phase["icon"],
                "order": phase["order"],
                "category": _PHASE_CATEGORY.get(phase["id"], "Autre"),
                "poses": rows,
            })
    return out


@lru_cache(maxsize=4)
def available_thumb_ids(static_root: str) -> frozenset:
    """
    Ids des poses disposant d'une vignette (web/static/poses/thumbs/<id>.webp).

    Sert au repli gracieux : le template n'affiche l'image que si le fichier
    existe, sinon carte texte seule. Cache par racine ; un redémarrage serveur
    (déjà requis à tout déploiement d'assets) rafraîchit.
    """
    d = Path(static_root) / "poses" / "thumbs"
    if not d.is_dir():
        return frozenset()
    return frozenset(p.stem for p in d.glob("*.webp"))
