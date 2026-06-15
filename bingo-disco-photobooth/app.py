"""Module photo IA Bingo Disco — serveur Flask (prototype).

Pipeline :
  Joueur (selfie mobile)  ->  /api/capture
                          ->  /api/generate  (Gemini stylise selon le thème)
                          ->  [optionnel] /api/template  (incrustation cadre)
                          ->  /api/screen    (diffusion sur l'écran)
                          ->  [optionnel] /api/print     (DNP DS620)

L'opérateur pilote tout depuis /console (ouvrir le mode photo, choisir le thème,
valider et envoyer à l'écran, imprimer). L'écran public est /screen.
"""

from __future__ import annotations

import base64
import functools
import json
import os
import time
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, send_from_directory, stream_with_context)

import gemini_client
import compositor
import printer
from prompt_library import library
from store import store, CAPTURES_DIR, GENERATED_DIR, BASE_DIR

app = Flask(__name__)

# Modèles image disponibles (du moins cher au plus qualitatif), affichés dans la console.
MODELS = [
    {"id": "gemini-2.5-flash-image", "label": "Nano Banana", "price": "~0,04 €/photo",
     "note": "rapide, conservateur (1K)"},
    {"id": "gemini-3.1-flash-image", "label": "Nano Banana 2", "price": "~0,07 €/photo",
     "note": "proche du Pro, jusqu'à 4K"},
    {"id": "gemini-3-pro-image", "label": "Nano Banana Pro", "price": "~0,13 €/photo",
     "note": "qualité max (≈ app Gemini), jusqu'à 4K"},
]


# --------------------------------------------------------------------------
# Sécurité opérateur (PIN simple, suffisant pour une animation de soirée)
# --------------------------------------------------------------------------
def operator_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        pin = os.environ.get("OPERATOR_PIN", "2468")
        given = request.headers.get("X-Operator-Pin") or request.args.get("pin")
        if given != pin:
            abort(403, "PIN opérateur invalide.")
        return fn(*args, **kwargs)
    return wrapper


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@app.route("/")
def home():
    return redirect("/console")


@app.route("/selfie")
@app.route("/p")
def selfie_page():
    return render_template("selfie.html")


@app.route("/console")
def console_page():
    return render_template("console.html")


def _style(style_id: str) -> dict:
    """Renvoie l'entrée de bibliothèque pour un id, avec repli sur la 1re/Pixar."""
    return (library.get(style_id) or library.get(store.active_style_id)
            or (library.list() or [{"id": "", "name": "?", "text": ""}])[0])


@app.route("/screen")
def screen_page():
    return render_template("screen.html")


# --------------------------------------------------------------------------
# Médias (images sur disque)
# --------------------------------------------------------------------------
@app.route("/media/captures/<path:name>")
def media_capture(name):
    return send_from_directory(CAPTURES_DIR, name)


@app.route("/media/generated/<path:name>")
def media_generated(name):
    return send_from_directory(GENERATED_DIR, name)


# --------------------------------------------------------------------------
# Flux d'événements temps réel (SSE) -> console + écran
# --------------------------------------------------------------------------
@app.route("/events")
def events():
    @stream_with_context
    def gen():
        q = store.bus.subscribe()
        # État initial pour qu'un client qui se (re)connecte soit à jour.
        yield _sse("hello", {**store.settings(), "demo": gemini_client.is_demo_mode()})
        try:
            while True:
                try:
                    payload = q.get(timeout=20)
                    yield f"data: {payload}\n\n"
                except Exception:
                    yield ": keepalive\n\n"  # commentaire SSE pour garder la connexion
        finally:
            store.bus.unsubscribe(q)

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(event: str, data: dict) -> str:
    return f"data: {json.dumps({'event': event, 'data': data})}\n\n"


# --------------------------------------------------------------------------
# API joueur
# --------------------------------------------------------------------------
@app.route("/api/capture", methods=["POST"])
def api_capture():
    # L'opérateur (PIN valide) peut importer une photo de test même mode fermé.
    operator = (request.headers.get("X-Operator-Pin") == os.environ.get("OPERATOR_PIN", "2468"))
    if not store.photo_mode_enabled and not operator:
        return jsonify(error="Le mode photo n'est pas ouvert pour le moment."), 423

    payload = request.get_json(silent=True) or {}
    player_name = (payload.get("player_name") or "").strip()[:40]
    data_url = payload.get("image", "")
    if "," not in data_url:
        return jsonify(error="Image manquante ou invalide."), 400

    raw = base64.b64decode(data_url.split(",", 1)[1])
    # Style : imposé par l'animateur, ou choisi par le joueur si mode "libre".
    requested = payload.get("style_id")
    if store.style_mode == "free" and library.get(requested):
        style_id = requested
    else:
        style_id = store.active_style_id
    pid_name = f"{int(time.time())}_{os.urandom(3).hex()}.jpg"
    (CAPTURES_DIR / pid_name).write_bytes(raw)

    photo = store.add_photo(player_name, style_id, pid_name)
    return jsonify(ok=True, photo=photo.public())


# --------------------------------------------------------------------------
# API opérateur
# --------------------------------------------------------------------------
@app.route("/api/state")
def api_state():
    return jsonify(
        settings=store.settings(),
        photos=store.all_photos(),
        models=MODELS,
        prompts=library.list(),
        demo=gemini_client.is_demo_mode(),
        print_enabled=printer.is_enabled(),
        templates=compositor.list_templates(),
    )


@app.route("/api/mode", methods=["POST"])
@operator_required
def api_mode():
    enabled = bool((request.get_json(silent=True) or {}).get("enabled"))
    store.set_mode(enabled)
    return jsonify(ok=True, enabled=enabled)


@app.route("/api/style", methods=["POST"])
@operator_required
def api_style():
    style_id = (request.get_json(silent=True) or {}).get("style_id")
    if not library.get(style_id):
        return jsonify(error="Style inconnu."), 400
    store.set_active_style(style_id)
    return jsonify(ok=True, active_style_id=style_id)


def _finalize(photo) -> None:
    """Reconstruit l'image finale à partir de la sortie brute Gemini (base_file).

    - Template "bande photo" (repères rouge/vert) : photo originale dans
      l'emplacement 1, photo modifiée dans l'emplacement 2.
    - Template classique (cadre PNG) : cadre superposé + texte événement.
    - Sans template : sortie Gemini + texte événement.
    """
    if not photo.base_file:
        return
    template = store.active_template
    if template and photo.capture_file and compositor.is_photostrip(template):
        original = (CAPTURES_DIR / photo.capture_file).read_bytes()
        stylized = (GENERATED_DIR / photo.base_file).read_bytes()
        img = compositor.build_photostrip(template, original, stylized)
    else:
        img = (GENERATED_DIR / photo.base_file).read_bytes()
        img = compositor.apply_template(img, template or None)
        img = compositor.draw_caption(img, store.event_text)
    out_name = photo.generated_file or f"gen_{photo.id}.jpg"
    (GENERATED_DIR / out_name).write_bytes(img)
    store.update(photo, generated_file=out_name)


@app.route("/api/generate", methods=["POST"])
@operator_required
def api_generate():
    pid = (request.get_json(silent=True) or {}).get("photo_id")
    photo = store.get(pid)
    if not photo or not photo.capture_file:
        return jsonify(error="Photo introuvable."), 404

    store.update(photo, status="generating", error=None)
    # Le prompt vient du style de la photo (bibliothèque de prompts).
    style = _style(photo.style_id)
    prompt, label = style["text"], style["name"]
    try:
        src = (CAPTURES_DIR / photo.capture_file).read_bytes()
        out = gemini_client.stylize(src, prompt, demo_label=label, model=store.model)
        base_name = f"gen_{photo.id}_base.jpg"
        (GENERATED_DIR / base_name).write_bytes(out)
        store.update(photo, status="generated", base_file=base_name,
                     generated_file=f"gen_{photo.id}.jpg")
        _finalize(photo)  # applique template + texte événement
        return jsonify(ok=True, photo=photo.public())
    except Exception as exc:
        store.update(photo, status="captured", error=str(exc))
        return jsonify(error=str(exc)), 502


@app.route("/api/active_template", methods=["POST"])
@operator_required
def api_active_template():
    name = (request.get_json(silent=True) or {}).get("template", "")
    store.set_template(name)
    # Ré-applique sur les photos déjà générées (rendu cohérent partout).
    for photo in list(store.photos.values()):
        if photo.base_file:
            _finalize(photo)
    return jsonify(ok=True, active_template=store.active_template,
                   is_photostrip=compositor.is_photostrip(store.active_template))


@app.route("/api/event_text", methods=["POST"])
@operator_required
def api_event_text():
    text = (request.get_json(silent=True) or {}).get("event_text", "")
    store.set_event_text(text)
    # Ré-applique le texte sur toutes les photos déjà générées (même rendu partout).
    for photo in list(store.photos.values()):
        if photo.base_file:
            _finalize(photo)
    return jsonify(ok=True, event_text=store.event_text)


@app.route("/api/style_mode", methods=["POST"])
@operator_required
def api_style_mode():
    mode = (request.get_json(silent=True) or {}).get("style_mode")
    store.set_style_mode(mode)
    return jsonify(ok=True, style_mode=store.style_mode)


@app.route("/api/model", methods=["POST"])
@operator_required
def api_model():
    model = (request.get_json(silent=True) or {}).get("model", "").strip()
    if not model:
        return jsonify(error="Modèle manquant."), 400
    store.set_model(model)
    return jsonify(ok=True, model=store.model)


# --- Bibliothèque de prompts (gestionnaire) ---
@app.route("/api/prompts/save", methods=["POST"])
@operator_required
def api_prompts_save():
    body = request.get_json(silent=True) or {}
    if not (body.get("text") or "").strip():
        return jsonify(error="Le prompt est vide."), 400
    preset = library.save(body.get("name", ""), body.get("text", ""), body.get("id"))
    return jsonify(ok=True, preset=preset, prompts=library.list())


@app.route("/api/prompts/delete", methods=["POST"])
@operator_required
def api_prompts_delete():
    library.delete((request.get_json(silent=True) or {}).get("id", ""))
    return jsonify(ok=True, prompts=library.list())


@app.route("/api/screen", methods=["POST"])
@operator_required
def api_screen():
    body = request.get_json(silent=True) or {}
    pid = body.get("photo_id")
    if pid is None:  # null explicite -> on vide l'écran
        store.set_on_screen(None)
        return jsonify(ok=True, cleared=True)
    photo = store.get(pid)
    if not photo or not photo.generated_file:
        return jsonify(error="Photo non générée."), 400
    store.update(photo, status="on_screen")
    store.set_on_screen(pid)
    return jsonify(ok=True, photo=photo.public())


@app.route("/api/simulate", methods=["POST"])
@operator_required
def api_simulate():
    """Compose le template avec deux images fournies (avant/après), SANS appeler
    Gemini : permet de régler le template gratuitement, autant qu'on veut."""
    body = request.get_json(silent=True) or {}

    def decode(key):
        d = body.get(key, "")
        return base64.b64decode(d.split(",", 1)[1]) if "," in d else None

    original, modified = decode("original"), decode("modified")
    if not modified:
        return jsonify(error="Fournis au moins la photo « après »."), 400
    template = store.active_template
    if template and original and compositor.is_photostrip(template):
        img = compositor.build_photostrip(template, original, modified)
    else:
        img = compositor.apply_template(modified, template or None)
        img = compositor.draw_caption(img, store.event_text)
    (GENERATED_DIR / "_simulation.jpg").write_bytes(img)
    return jsonify(ok=True, url="/media/generated/_simulation.jpg")


@app.route("/api/print", methods=["POST"])
@operator_required
def api_print():
    photo = store.get((request.get_json(silent=True) or {}).get("photo_id"))
    if not photo or not photo.generated_file:
        return jsonify(error="Photo non générée."), 400
    result = printer.print_image(GENERATED_DIR / photo.generated_file)
    return (jsonify(ok=True, message=result.message) if result.ok
            else (jsonify(error=result.message), 500))


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5055"))
    mode = "DÉMO (sans clé Gemini)" if gemini_client.is_demo_mode() else "Gemini ACTIF"
    print(f"\n  Bingo Disco — module photo  [{mode}]")
    print(f"  Console opérateur : http://localhost:{port}/console")
    print(f"  Page selfie       : http://localhost:{port}/selfie")
    print(f"  Écran public      : http://localhost:{port}/screen\n")
    # debug=False : sinon Werkzeug réserve l'URL /console pour son propre
    # débogueur (et l'expose, ce qui est risqué). On garde threaded pour le SSE.
    app.run(host=host, port=port, threaded=True, debug=False)
