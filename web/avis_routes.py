"""
web/avis_routes.py — Avis clients (formulaire public + modération admin).

Deux canaux, UN SEUL store (storage : avis/avis.json) :
  - Formulaire public  GET/POST /avis           (SANS login)  -> statut "en_attente"
  - API borne          POST     /api/avis        (SANS login)  -> statut "en_attente"
  - Modération admin    /moderation/avis          (login global) -> approuver/rejeter/supprimer

⚠️ RIEN n'est auto-publié : tout avis reçu est "en_attente" jusqu'à ta validation.
Les avis APPROUVÉS sont recopiés sur le site vitrine (docs/avis.json) au moment du
« Publier vitrine » (voir vitrine_publisher.publier).

Rappel auth : /avis et /api/avis doivent figurer dans _PUBLIC_PREFIXES de app.py.
"""

import time
import hashlib

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, jsonify
)

from app_storage import STORAGE

avis_bp = Blueprint("avis", __name__)

AVIS_REL = "avis/avis.json"

# Liste FIXE des prestations évaluables (clé -> libellé).
# « booth » = Photobooth (englobe le Photobooth IA), décision Alexis.
PRESTATIONS = [
    ("dj",     "DJ / Animation"),
    ("bingo",  "Bingo Musical"),
    ("booth",  "Photobooth"),
    ("sonlum", "Sono & Lumière"),
    ("ecran",  "Écran géant"),
    ("loc",    "Location matériel"),
    ("photo",  "Photo / Vidéo"),
]
PRESTA_KEYS = {k for k, _ in PRESTATIONS}
PRESTA_LABELS = dict(PRESTATIONS)

_MOIS = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
         "août", "septembre", "octobre", "novembre", "décembre"]


def fmt_date(ts) -> str:
    """Timestamp -> « 12 juin 2026 » (best effort ; UTC côté Render, suffisant ici)."""
    try:
        t = time.localtime(float(ts))
        return f"{t.tm_mday} {_MOIS[t.tm_mon]} {t.tm_year}"
    except Exception:
        return ""


def _load() -> dict:
    try:
        d = STORAGE.read_json(AVIS_REL)
    except Exception:
        d = None
    if not isinstance(d, dict) or "avis" not in d:
        d = {"avis": []}
    return d


def _save(d) -> None:
    STORAGE.write_json(AVIS_REL, d)


def _gen_id(ts, pseudo) -> str:
    return hashlib.sha1(f"{ts}-{pseudo}".encode("utf-8")).hexdigest()[:10]


def _clean_entry(*, pseudo, stars, prestations, comment, event_type, consent, source):
    """Construit une entrée d'avis normalisée (bornée en longueur)."""
    try:
        stars = int(stars or 0)
    except (TypeError, ValueError):
        stars = 0
    stars = max(0, min(5, stars))
    prest = [k for k in (prestations or []) if k in PRESTA_KEYS]
    ts = time.time()
    return {
        "id": _gen_id(ts, pseudo),
        "ts": ts,
        "pseudo": (pseudo or "").strip()[:60] or "Anonyme",
        "stars": stars,
        "prestations": prest,
        "comment": (comment or "").strip()[:800],
        "event_type": (event_type or "").strip()[:40],
        "consent": bool(consent),
        "source": source,
        "status": "en_attente",
    }


# ============================ PUBLIC : formulaire ============================

@avis_bp.route("/avis", methods=["GET"])
def form():
    return render_template(
        "avis_form.html", prestations=PRESTATIONS, title="Laisser un avis",
        sent=bool(request.args.get("sent")), form=None,
    )


@avis_bp.route("/avis", methods=["POST"])
def submit():
    # Honeypot anti-bot : le champ caché "website" doit rester vide.
    if (request.form.get("website") or "").strip():
        return redirect(url_for("avis.form", sent="1"))  # on simule un succès

    pseudo = (request.form.get("pseudo") or "").strip()
    comment = (request.form.get("comment") or "").strip()
    stars = request.form.get("stars") or 0
    event_type = (request.form.get("event_type") or "").strip()
    prestations = request.form.getlist("prestations")
    consent = bool(request.form.get("consent"))

    try:
        stars_i = int(stars)
    except (TypeError, ValueError):
        stars_i = 0

    # Validation minimale : prénom + consentement + (note OU commentaire).
    if not pseudo or not consent or (not stars_i and not comment):
        flash("Merci d'indiquer votre prénom, une note ou un commentaire, "
              "et d'accepter la publication de votre avis.", "error")
        return render_template(
            "avis_form.html", prestations=PRESTATIONS, title="Laisser un avis",
            sent=False,
            form={"pseudo": pseudo, "comment": comment, "stars": stars_i,
                  "event_type": event_type, "prestations": prestations},
        )

    d = _load()
    d["avis"].append(_clean_entry(
        pseudo=pseudo, stars=stars, prestations=prestations, comment=comment,
        event_type=event_type, consent=consent, source="site",
    ))
    _save(d)
    return redirect(url_for("avis.form", sent="1"))


# ===================== API (canal borne — même store) =======================

@avis_bp.route("/api/avis", methods=["POST"])
def api_submit():
    """Réception d'un avis depuis la borne photobooth (JSON). Même store, source=borne."""
    body = request.get_json(silent=True) or {}
    pseudo = body.get("pseudo") or body.get("player_name") or ""
    consent = bool(body.get("consent") or body.get("consent_site"))
    comment = body.get("comment") or ""
    stars = body.get("stars") or 0
    if not (str(comment).strip() or int(stars or 0)):
        return jsonify(ok=False, error="avis vide"), 400
    d = _load()
    d["avis"].append(_clean_entry(
        pseudo=pseudo, stars=stars, prestations=body.get("prestations") or ["booth"],
        comment=comment, event_type=body.get("event_type") or "",
        consent=consent, source="borne",
    ))
    _save(d)
    return jsonify(ok=True)


# ========================== ADMIN : modération ==============================

@avis_bp.route("/moderation/avis")
def moderation():
    d = _load()
    avis = sorted(d["avis"], key=lambda a: a.get("ts", 0), reverse=True)
    noted = [a for a in avis if a.get("stars")]
    stats = {
        "total": len(avis),
        "en_attente": sum(1 for a in avis if a.get("status") == "en_attente"),
        "approuve": sum(1 for a in avis if a.get("status") == "approuve"),
        "moyenne": round(sum(a["stars"] for a in noted) / len(noted), 1) if noted else None,
    }
    return render_template(
        "avis_moderation.html", avis=avis, stats=stats,
        labels=PRESTA_LABELS, fmt_date=fmt_date, title="Avis clients",
    )


@avis_bp.route("/moderation/avis/<aid>/<action>", methods=["POST"])
def moderer(aid, action):
    d = _load()
    changed = False
    for a in list(d["avis"]):
        if a.get("id") != aid:
            continue
        if action == "approuver":
            a["status"] = "approuve"; changed = True
        elif action == "rejeter":
            a["status"] = "rejete"; changed = True
        elif action == "supprimer":
            d["avis"].remove(a); changed = True
        break
    if changed:
        _save(d)
        flash("Avis mis à jour.", "success")
    else:
        flash("Avis introuvable.", "error")
    return redirect(url_for("avis.moderation"))
