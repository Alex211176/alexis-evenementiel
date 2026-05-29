"""
web/parametres_routes.py — Page Paramètres (version cloud, via storage).

GET  /parametres          page complète
POST /parametres/api/save autosave d'un champ (chemin pointé)
"""

import sys
from pathlib import Path

from flask import Blueprint, render_template, request, jsonify

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app_storage import STORAGE
import storage_io

parametres_bp = Blueprint("parametres", __name__, url_prefix="/parametres")


@parametres_bp.route("/")
def index():
    data = storage_io.load_defaults(STORAGE)
    return render_template("parametres/index.html", data=data, title="Paramètres")


@parametres_bp.route("/api/save", methods=["POST"])
def api_save():
    payload = request.get_json(silent=True) or {}
    path = payload.get("path", "")
    value = payload.get("value", None)
    if not path:
        return jsonify({"ok": False, "error": "path manquant"}), 400

    data = storage_io.load_defaults(STORAGE)
    _set_by_path(data, path, value)
    storage_io.save_defaults(STORAGE, data)
    return jsonify({"ok": True, "path": path, "value": value})


def _set_by_path(data: dict, path: str, value) -> None:
    parts = path.split(".")
    cur = data
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    last = parts[-1]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            value = None
        else:
            try:
                v_int = int(stripped)
                old_val = cur.get(last)
                if isinstance(old_val, int) and not isinstance(old_val, bool):
                    value = v_int
            except (ValueError, TypeError):
                pass
    cur[last] = value
