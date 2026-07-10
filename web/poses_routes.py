"""
web/poses_routes.py — Blueprint « Poses Mariage » (greffé sur l'app existante).

Additif : n'altère aucune route devis/fiches. Réutilise la couche storage
(STORAGE partagé) et le service Render en place.

Routes
------
Lecture seule (jalon 0)
    GET  /poses/library                     bibliothèque par phase

Admin — DERRIÈRE le mot de passe global (jalon 1, minimal)
    GET  /poses/admin                       liste + formulaire de création
    POST /poses/admin/new                   crée un événement -> lien client

Client — PUBLIC par token (jalon 1) ; exempté du gate via _PUBLIC_PREFIXES
    GET  /poses/s/<token>                   page de sélection (charte nocturne)
    POST /poses/s/<token>/api/save          autosave {selections, notes, custom}
    POST /poses/s/<token>/api/validate      valide la sélection
"""

import sys
from pathlib import Path

from flask import (
    Blueprint, render_template, request, redirect, url_for, jsonify, abort,
    current_app, Response, send_from_directory,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app_storage import STORAGE
from poses.loader import (
    load_library, count_poses, available_thumb_ids, resolve_checklist, LibraryError,
)
from poses import events as ev
from poses.tokens import is_valid_token

poses_bp = Blueprint("poses", __name__, url_prefix="/poses")


# --------------------------------------------------------------------------- #
# Lecture seule — bibliothèque (jalon 0)
# --------------------------------------------------------------------------- #
@poses_bp.route("/library")
def library():
    try:
        lib = load_library()
    except LibraryError as exc:
        return f"<pre>Bibliothèque de poses indisponible : {exc}</pre>", 500
    return render_template(
        "poses/library.html",
        lib=lib,
        total_poses=count_poses(lib),
        total_phases=len(lib["phases"]),
        title="Poses — Bibliothèque",
    )


# --------------------------------------------------------------------------- #
# Admin (protégé par le gate global) — jalon 1 minimal
# --------------------------------------------------------------------------- #
@poses_bp.route("/admin")
def admin():
    return render_template(
        "poses/admin.html",
        events=ev.list_events(STORAGE),
        title="Poses — Événements",
    )


@poses_bp.route("/admin/new", methods=["POST"])
def admin_new():
    couple = request.form.get("couple", "").strip()
    date = request.form.get("date", "").strip()
    if not couple:
        # Retour simple : on renvoie sur l'admin (le formulaire est court).
        return redirect(url_for("poses.admin"))
    event = ev.new_event(STORAGE, couple, date)
    return redirect(url_for("poses.admin", created=event["clientToken"]))


# --------------------------------------------------------------------------- #
# Client (public par token) — jalon 1
# --------------------------------------------------------------------------- #
def _load_event_or_404(token: str) -> dict:
    if not is_valid_token(token):
        abort(404)
    event = ev.load_by_token(STORAGE, token)
    if event is None:
        abort(404)
    return event


@poses_bp.route("/s/<token>")
def client(token):
    event = _load_event_or_404(token)
    try:
        lib = load_library()
    except LibraryError as exc:
        return f"<pre>Bibliothèque indisponible : {exc}</pre>", 500
    return render_template(
        "poses/client.html",
        lib=lib,
        event=event,
        total_poses=count_poses(lib),
        thumbs=available_thumb_ids(current_app.static_folder),
        title=f"Vos poses — {event.get('couple', '')}",
    )


@poses_bp.route("/s/<token>/api/save", methods=["POST"])
def client_save(token):
    if not is_valid_token(token):
        abort(404)
    payload = request.get_json(silent=True) or {}
    try:
        event = ev.save_client_state(
            STORAGE, token,
            payload.get("selections"),
            payload.get("notes"),
            payload.get("custom"),
        )
    except ev.EventLocked:
        return jsonify({"ok": False, "locked": True,
                        "error": "Sélection verrouillée par le photographe."}), 409
    except ev.EventError:
        abort(404)
    return jsonify({
        "ok": True,
        "nb_selections": len(event.get("selections", [])),
        "updatedAt": event.get("updatedAt"),
    })


@poses_bp.route("/s/<token>/api/validate", methods=["POST"])
def client_validate(token):
    if not is_valid_token(token):
        abort(404)
    try:
        event = ev.set_validated(STORAGE, token, True)
    except ev.EventLocked:
        return jsonify({"ok": False, "locked": True}), 409
    except ev.EventError:
        abort(404)
    return jsonify({"ok": True, "validatedAt": event.get("validatedAt")})


# --------------------------------------------------------------------------- #
# Mode photographe jour J (protégé par le gate global) — jalon 2
# --------------------------------------------------------------------------- #
@poses_bp.route("/field/<token>")
def field(token):
    event = _load_event_or_404(token)
    try:
        lib = load_library()
    except LibraryError as exc:
        return f"<pre>Bibliothèque indisponible : {exc}</pre>", 500

    checklist = resolve_checklist(lib, event.get("selections"), event.get("mustHave"))
    shown_total = sum(len(p["poses"]) for p in checklist) + len(event.get("custom", []))
    return render_template(
        "poses/field.html",
        lib=lib,
        event=event,
        checklist=checklist,
        shown_total=shown_total,
        title=f"Jour J — {event.get('couple', '')}",
    )


@poses_bp.route("/field/<token>/api/done", methods=["POST"])
def field_done(token):
    if not is_valid_token(token):
        abort(404)
    payload = request.get_json(silent=True) or {}
    try:
        event = ev.toggle_done(STORAGE, token, payload.get("pose_id"), bool(payload.get("done")))
    except ev.EventError:
        abort(404)
    return jsonify({"ok": True, "done": event.get("done", [])})


@poses_bp.route("/field/<token>/api/musthave", methods=["POST"])
def field_musthave(token):
    if not is_valid_token(token):
        abort(404)
    payload = request.get_json(silent=True) or {}
    try:
        event = ev.set_must_have(STORAGE, token, payload.get("pose_id"), bool(payload.get("add")))
    except ev.EventError:
        abort(404)
    return jsonify({"ok": True, "mustHave": event.get("mustHave", [])})


@poses_bp.route("/field/<token>/api/lock", methods=["POST"])
def field_lock(token):
    if not is_valid_token(token):
        abort(404)
    payload = request.get_json(silent=True) or {}
    try:
        event = ev.set_lock(STORAGE, token, bool(payload.get("locked")))
    except ev.EventError:
        abort(404)
    return jsonify({"ok": True, "locked": event.get("locked", False)})


# --------------------------------------------------------------------------- #
# PWA — service worker, manifest et assets SERVIS DANS LE PÉRIMÈTRE /poses/
# (un SW ne peut intercepter que les URL de son scope ; les assets Flask
# /static/… seraient hors scope, donc introuvables hors-ligne). Jalon 3.
# --------------------------------------------------------------------------- #
def _poses_static_dir() -> Path:
    return Path(current_app.static_folder) / "poses"


# Fichiers autorisés au service via /poses/a/<...> (liste blanche = pas de traversal).
_PWA_ASSETS = {
    "field.css": "text/css",
    "field.js": "application/javascript",
    "icons/icon-192.png": "image/png",
    "icons/icon-512.png": "image/png",
}


@poses_bp.route("/sw.js")
def service_worker():
    js = (_poses_static_dir() / "sw.js").read_text(encoding="utf-8")
    resp = Response(js, mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache"      # le SW doit toujours être revérifié
    resp.headers["Service-Worker-Allowed"] = "/poses/"
    return resp


@poses_bp.route("/app.webmanifest")
def manifest():
    data = {
        "name": "Poses — Jour J",
        "short_name": "Poses",
        "start_url": "/poses/admin",
        "scope": "/poses/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#14181f",
        "icons": [
            {"src": "/poses/a/icons/icon-192.png", "sizes": "192x192",
             "type": "image/png", "purpose": "any maskable"},
            {"src": "/poses/a/icons/icon-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "any maskable"},
        ],
    }
    return Response(jsonify(data).get_data(), mimetype="application/manifest+json")


@poses_bp.route("/a/<path:filename>")
def pwa_asset(filename):
    if filename not in _PWA_ASSETS:
        abort(404)
    resp = send_from_directory(_poses_static_dir(), filename,
                               mimetype=_PWA_ASSETS[filename])
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp
