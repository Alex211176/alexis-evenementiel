"""
poses/events.py — État par événement (mariage), persisté via la couche storage.

Un fichier JSON par mariage : /poses/events/<clientToken>.json. Le token est le
nom de fichier (lookup public O(1)) ; le champ `id` lisible reste stocké dedans
pour l'admin.

DISCIPLINE DE PROPRIÉTÉ DES CHAMPS (essentielle, cf. stratégie de fusion) :
  - Champs CLIENT   : selections, notes, custom, validated, validatedAt
  - Champs PHOTOGRAPHE (jalon 2) : mustHave, done, doneAt, locked
Une écriture client recharge l'événement et ne réécrit QUE ses champs, préservant
les champs photographe (et inversement plus tard). Jamais d'écrasement global.
"""
from __future__ import annotations  # annotations paresseuses -> compat Python 3.9+

import re
import unicodedata
from datetime import datetime

from poses.tokens import generate_token, is_valid_token

EVENTS_DIR = "poses/events"

# Garde-fous (endpoints publics) : on borne tout ce qui vient du client.
_MAX_SELECTIONS = 400
_MAX_NOTE_LEN = 500
_MAX_CUSTOM = 50
_MAX_CUSTOM_TITLE = 120
_MAX_CUSTOM_DESC = 500
_MAX_ID_LEN = 40
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class EventError(Exception):
    pass


class EventLocked(Exception):
    """L'événement est verrouillé : écriture client refusée."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def _rel(token: str) -> str:
    return f"{EVENTS_DIR}/{token}.json"


def _clean_id(v) -> str | None:
    if not isinstance(v, str):
        return None
    v = v.strip()
    return v if _ID_RE.match(v) else None


def _clean_selections(raw) -> list:
    if not isinstance(raw, list):
        return []
    out, seen = [], set()
    for item in raw[:_MAX_SELECTIONS]:
        cid = _clean_id(item)
        if cid and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def _clean_notes(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in list(raw.items())[:_MAX_SELECTIONS]:
        cid = _clean_id(k)
        if cid and isinstance(v, str):
            txt = v.strip()[:_MAX_NOTE_LEN]
            if txt:
                out[cid] = txt
    return out


def _clean_custom(raw) -> list:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[:_MAX_CUSTOM]:
        if not isinstance(item, dict):
            continue
        cid = _clean_id(item.get("id"))
        title = (item.get("title") or "").strip()[:_MAX_CUSTOM_TITLE]
        if not cid or not title:
            continue
        entry = {
            "id": cid,
            "phaseId": _clean_id(item.get("phaseId")),  # None accepté (jalon 1)
            "title": title,
            "desc": (item.get("desc") or "").strip()[:_MAX_CUSTOM_DESC],
        }
        out.append(entry)
    return out


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def new_event(storage, couple: str, date: str) -> dict:
    """Crée un événement vierge et le persiste. Renvoie le dict complet."""
    couple = (couple or "").strip()
    date = (date or "").strip()
    if not couple:
        raise EventError("Le nom du couple est requis.")

    token = generate_token()
    # collision de token quasi impossible, mais on garantit l'unicité du fichier
    while storage.exists(_rel(token)):
        token = generate_token()

    year = date[:4] if len(date) >= 4 and date[:4].isdigit() else datetime.now().strftime("%Y")
    event_id = f"evt_{year}_{_slugify(couple) or 'couple'}"

    event = {
        "id": event_id,
        "couple": couple,
        "date": date,
        "clientToken": token,
        "locked": False,
        "selections": [],
        "mustHave": [],
        "notes": {},
        "custom": [],
        "done": [],
        "doneAt": {},
        "validated": False,
        "validatedAt": None,
        "createdAt": _now_iso(),
        "updatedAt": _now_iso(),
    }
    storage.write_json(_rel(token), event)
    return event


def load_by_token(storage, token: str):
    """Renvoie l'événement ou None. Rejette tout token malformé (anti-traversal)."""
    if not is_valid_token(token):
        return None
    rel = _rel(token)
    if not storage.exists(rel):
        return None
    return storage.read_json(rel)


def _ensure_defaults(ev: dict) -> dict:
    """Complète les champs manquants (rétro-compat / robustesse)."""
    ev.setdefault("selections", [])
    ev.setdefault("mustHave", [])
    ev.setdefault("notes", {})
    ev.setdefault("custom", [])
    ev.setdefault("done", [])
    ev.setdefault("doneAt", {})
    ev.setdefault("locked", False)
    ev.setdefault("validated", False)
    ev.setdefault("validatedAt", None)
    return ev


def save_client_state(storage, token: str, selections, notes, custom) -> dict:
    """
    Sauvegarde les champs CLIENT en préservant les champs photographe.
    Lève EventError si introuvable, EventLocked si verrouillé.
    """
    ev = load_by_token(storage, token)
    if ev is None:
        raise EventError("Événement introuvable.")
    _ensure_defaults(ev)
    if ev.get("locked"):
        raise EventLocked()

    ev["selections"] = _clean_selections(selections)
    ev["notes"] = _clean_notes(notes)
    ev["custom"] = _clean_custom(custom)
    ev["updatedAt"] = _now_iso()
    storage.write_json(_rel(token), ev)
    return ev


def set_validated(storage, token: str, value: bool = True) -> dict:
    """Marque la sélection comme validée par les mariés (champ client)."""
    ev = load_by_token(storage, token)
    if ev is None:
        raise EventError("Événement introuvable.")
    _ensure_defaults(ev)
    if ev.get("locked"):
        raise EventLocked()
    ev["validated"] = bool(value)
    ev["validatedAt"] = _now_iso() if value else None
    ev["updatedAt"] = _now_iso()
    storage.write_json(_rel(token), ev)
    return ev


# --------------------------------------------------------------------------- #
# Opérations PHOTOGRAPHE (jalon 2)
# Champs photographe : done, doneAt, mustHave, locked.
# Elles préservent les champs client (selections/notes/custom) et IGNORENT le
# verrou (le verrou vise le client ; le photographe coche même après avoir verrouillé).
# --------------------------------------------------------------------------- #
def toggle_done(storage, token: str, pose_id: str, done: bool) -> dict:
    """Coche/décoche une pose faite le jour J. `done`/`doneAt` en ensemble."""
    ev = load_by_token(storage, token)
    if ev is None:
        raise EventError("Événement introuvable.")
    _ensure_defaults(ev)
    pid = _clean_id(pose_id)
    if not pid:
        raise EventError("Identifiant de pose invalide.")

    done_set = set(ev.get("done", []))
    done_at = dict(ev.get("doneAt", {}))
    if done:
        done_set.add(pid)
        done_at[pid] = _now_iso()
    else:
        done_set.discard(pid)
        done_at.pop(pid, None)
    ev["done"] = sorted(done_set)
    ev["doneAt"] = done_at
    ev["updatedAt"] = _now_iso()
    storage.write_json(_rel(token), ev)
    return ev


def set_must_have(storage, token: str, pose_id: str, add: bool) -> dict:
    """Ajoute/retire un incontournable (pose imposée par le photographe)."""
    ev = load_by_token(storage, token)
    if ev is None:
        raise EventError("Événement introuvable.")
    _ensure_defaults(ev)
    pid = _clean_id(pose_id)
    if not pid:
        raise EventError("Identifiant de pose invalide.")

    mh = set(ev.get("mustHave", []))
    if add:
        mh.add(pid)
    else:
        mh.discard(pid)
    ev["mustHave"] = sorted(mh)
    ev["updatedAt"] = _now_iso()
    storage.write_json(_rel(token), ev)
    return ev


def set_lock(storage, token: str, locked: bool) -> dict:
    """Verrouille/déverrouille la sélection côté client."""
    ev = load_by_token(storage, token)
    if ev is None:
        raise EventError("Événement introuvable.")
    _ensure_defaults(ev)
    ev["locked"] = bool(locked)
    ev["updatedAt"] = _now_iso()
    storage.write_json(_rel(token), ev)
    return ev


def list_events(storage) -> list:
    """Résumés de tous les événements (usage admin)."""
    out = []
    for name in storage.list_folder(EVENTS_DIR):
        if not name.endswith(".json"):
            continue
        try:
            ev = storage.read_json(f"{EVENTS_DIR}/{name}")
        except Exception:  # noqa: BLE001
            continue
        out.append({
            "id": ev.get("id", "—"),
            "couple": ev.get("couple", "(sans nom)"),
            "date": ev.get("date", ""),
            "clientToken": ev.get("clientToken", name[:-5]),
            "locked": bool(ev.get("locked")),
            "validated": bool(ev.get("validated")),
            "nb_selections": len(ev.get("selections", [])),
        })
    out.sort(key=lambda e: (e.get("date") or "9999", e.get("couple") or ""))
    return out
