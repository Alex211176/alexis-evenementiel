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
from store import store, CAPTURES_DIR, GENERATED_DIR, BASE_DIR

app = Flask(__name__)

THEMES = json.loads((BASE_DIR / "themes.json").read_text(encoding="utf-8"))["themes"]
THEME_BY_ID = {t["id"]: t for t in THEMES}


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
    return render_template("selfie.html",
                           themes=[t for t in THEMES if t.get("active")])


@app.route("/console")
def console_page():
    return render_template("console.html", themes=THEMES)


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
    theme_id = store.current_theme_id
    pid_name = f"{int(time.time())}_{os.urandom(3).hex()}.jpg"
    (CAPTURES_DIR / pid_name).write_bytes(raw)

    photo = store.add_photo(player_name, theme_id, pid_name)
    return jsonify(ok=True, photo=photo.public())


# --------------------------------------------------------------------------
# API opérateur
# --------------------------------------------------------------------------
@app.route("/api/state")
def api_state():
    return jsonify(
        settings=store.settings(),
        photos=store.all_photos(),
        themes=THEMES,
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


@app.route("/api/theme", methods=["POST"])
@operator_required
def api_theme():
    theme_id = (request.get_json(silent=True) or {}).get("theme_id")
    if theme_id not in THEME_BY_ID:
        return jsonify(error="Thème inconnu."), 400
    store.set_theme(theme_id)
    return jsonify(ok=True, theme_id=theme_id)


@app.route("/api/generate", methods=["POST"])
@operator_required
def api_generate():
    pid = (request.get_json(silent=True) or {}).get("photo_id")
    photo = store.get(pid)
    if not photo or not photo.capture_file:
        return jsonify(error="Photo introuvable."), 404

    store.update(photo, status="generating", error=None)
    theme = THEME_BY_ID.get(photo.theme_id, THEMES[0])
    try:
        src = (CAPTURES_DIR / photo.capture_file).read_bytes()
        out = gemini_client.stylize(src, theme)
        out_name = f"gen_{photo.id}.jpg"
        (GENERATED_DIR / out_name).write_bytes(out)
        store.update(photo, status="generated", generated_file=out_name)
        return jsonify(ok=True, photo=photo.public())
    except Exception as exc:
        store.update(photo, status="captured", error=str(exc))
        return jsonify(error=str(exc)), 502


@app.route("/api/template", methods=["POST"])
@operator_required
def api_template():
    body = request.get_json(silent=True) or {}
    photo = store.get(body.get("photo_id"))
    template_name = body.get("template")
    if not photo or not photo.generated_file:
        return jsonify(error="Photo non générée."), 400
    src = (GENERATED_DIR / photo.generated_file).read_bytes()
    out = compositor.apply_template(src, template_name)
    (GENERATED_DIR / photo.generated_file).write_bytes(out)
    store.update(photo, status="generated")
    return jsonify(ok=True, photo=photo.public())


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
    app.run(host=host, port=port, threaded=True, debug=True)
