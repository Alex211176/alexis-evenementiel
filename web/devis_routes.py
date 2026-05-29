"""
web/devis_routes.py — Routes devis (version cloud, via storage).

Phase 1 : aperçu + PDF (téléchargé ET archivé dans devis/), statuts admin.
Le partage client + la signature sont neutralisés (Phase 2) : les routes restent
définies (pour ne pas casser les url_for des templates) mais renvoient un message.
"""

import sys
import tempfile
from pathlib import Path

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    send_file, jsonify, abort, flash
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from catalogue import resoudre_evenement
from devis import (
    render_devis_html, export_devis_pdf,
    generate_devis_ref, current_devis_version,
)
from app_storage import STORAGE
import storage_io

DEVIS_TEMPLATE_DIR = ROOT / "devis" / "templates"
FICHE_STATIC_DIR = ROOT / "fiches" / "static"

devis_bp = Blueprint("devis", __name__, url_prefix="/devis")

_PHASE2_MESSAGE = ("Le partage et la signature client seront disponibles "
                   "dans une prochaine étape.")

# Sections héritées des defaults : on ne les ré-écrit pas dans l'événement
_DEFAULTS_SECTIONS = (
    "prestataire", "annulation", "intemperies", "deplacement",
    "personnel", "logistique", "electricite",
)


def _load_event_resolved(filename: str):
    """Charge un événement fusionné + résolu. Retourne (data, result, filename)."""
    if not STORAGE.exists(f"events/{filename}"):
        return None, None, None
    data = storage_io.load_config_merged(STORAGE, filename)

    cat = storage_io.load_catalogue(STORAGE)
    result = resoudre_evenement(data, cat)

    data.setdefault("devis", {})
    if not data["devis"].get("reference"):
        data["devis"]["reference"] = generate_devis_ref(data)
    if not data["devis"].get("statut"):
        data["devis"]["statut"] = "brouillon"

    # Tarif minoré global (prix_propose) -> remise commerciale
    if data["devis"].get("prix_propose"):
        try:
            propose = float(str(data["devis"]["prix_propose"]).replace(",", "."))
            theorique = result["prix"]["total_ttc"]
            if propose < theorique and theorique > 0:
                remise = theorique - propose
                result["prix"]["remise_commerciale"] = remise
                result["prix"]["remise_pct"] = (remise / theorique) * 100
                result["prix"]["total_ttc"] = propose
        except (ValueError, TypeError):
            pass

    return data, result, filename


def _save_event(filename: str, data: dict) -> None:
    """Sauvegarde l'événement sans les sections héritées des defaults."""
    defaults = storage_io.load_defaults(STORAGE)
    to_save = {k: v for k, v in data.items() if k not in _DEFAULTS_SECTIONS}
    if "electricite" in data and data.get("electricite") != defaults.get("electricite"):
        to_save["electricite"] = data["electricite"]
    storage_io.save_event(STORAGE, filename, to_save)


# ==================== PREVIEW ADMIN ====================

@devis_bp.route("/<event_filename>/preview")
def preview(event_filename):
    data, result, _ = _load_event_resolved(event_filename)
    if data is None:
        abort(404)
    cat = storage_io.load_catalogue(STORAGE)
    html = render_devis_html(
        data, result,
        template_dir=DEVIS_TEMPLATE_DIR,
        static_url=url_for("fiches_static", filename="").rstrip("/"),
        mode="preview", catalogue=cat,
    )
    return html


# ==================== PDF (stream + archive Dropbox) ====================

@devis_bp.route("/<event_filename>/pdf")
def pdf(event_filename):
    data, result, _ = _load_event_resolved(event_filename)
    if data is None:
        abort(404)
    cat = storage_io.load_catalogue(STORAGE)
    html = render_devis_html(
        data, result,
        template_dir=DEVIS_TEMPLATE_DIR,
        static_url=".", mode="pdf", catalogue=cat,
    )

    ref = data.get("devis", {}).get("reference", "devis")
    safe_ref = ref.replace("/", "-")
    pdf_path = Path(tempfile.gettempdir()) / f"{safe_ref}.pdf"

    try:
        export_devis_pdf(html, pdf_path, base_url=FICHE_STATIC_DIR)
    except ImportError as e:
        return f"<pre>{e}</pre>", 500

    # Archive dans devis/ (Dropbox ou local)
    try:
        STORAGE.write_bytes(f"devis/{safe_ref}.pdf", pdf_path.read_bytes())
    except Exception:
        pass  # l'archivage ne doit pas bloquer le téléchargement

    return send_file(pdf_path, as_attachment=True,
                     download_name=f"{safe_ref}.pdf", mimetype="application/pdf")


# ==================== STATUTS ADMIN ====================

@devis_bp.route("/<event_filename>/refuse", methods=["POST"])
def refuse(event_filename):
    data, _, filename = _load_event_resolved(event_filename)
    if data is None:
        abort(404)
    data.setdefault("devis", {})["statut"] = "refuse"
    _save_event(filename, data)
    flash("Devis marqué comme refusé.", "info")
    return redirect(url_for("event_preview", filename=event_filename))


@devis_bp.route("/<event_filename>/reset", methods=["POST"])
def reset(event_filename):
    data, _, filename = _load_event_resolved(event_filename)
    if data is None:
        abort(404)
    data.setdefault("devis", {})["statut"] = "brouillon"
    data["devis"].pop("signature", None)
    _save_event(filename, data)
    flash("Devis remis en brouillon.", "info")
    return redirect(url_for("event_preview", filename=event_filename))


# ==================== PARTAGE / SIGNATURE (Phase 2 — neutralisés) ====================

@devis_bp.route("/<event_filename>/send", methods=["POST"])
def send_devis(event_filename):
    # Le JS de preview.html gère proprement {ok:false, error:...}
    return jsonify({"ok": False, "error": _PHASE2_MESSAGE})


@devis_bp.route("/share/<token>")
def share(token):
    return _PHASE2_MESSAGE, 200


@devis_bp.route("/share/<token>/sign", methods=["GET", "POST"])
def sign(token):
    return _PHASE2_MESSAGE, 200


@devis_bp.route("/share/<token>/email-validate/<validation_token>")
def email_validate(token, validation_token):
    return _PHASE2_MESSAGE, 200
