"""
web/app.py — Alexis Événementiel (version cloud).

Identique à l'app locale d'origine, mais :
  - les lectures/écritures passent par la couche `storage` (local OU Dropbox) ;
  - toute l'admin est protégée par un mot de passe (login global) ;
  - prête pour gunicorn (Render) : `gunicorn --chdir web app:app`.

Lancement local :  python web/app.py   -> http://localhost:5001
"""

import sys
import tempfile
import unicodedata
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from flask import (
    Flask, render_template, request, redirect, url_for,
    send_file, jsonify, abort, flash, session,
)

from config_manager import load_config, is_on_render
from storage import get_storage, StorageError
import storage_io

from fiches import validate, render_html, export_pdf
from fiches.config import ConfigError
from catalogue import resoudre_pack, resoudre_evenement

# --- Config & storage --------------------------------------------------------
config = load_config()
STORAGE = get_storage(config)

# Chemins de code (templates / assets) — restent dans le conteneur, pas sur Dropbox
TEMPLATE_DIR = ROOT / "fiches" / "templates"
STATIC_DIR = ROOT / "fiches" / "static"

app = Flask(
    __name__,
    template_folder=str(ROOT / "web" / "templates"),
    static_folder=str(ROOT / "web" / "static"),
)
app.config["SECRET_KEY"] = config.get("secret_key") or "dev-key-change-in-prod"

# Blueprints existants (clonés tels quels pour ce jet ; bascule storage au tour suivant)
from catalogue_routes import catalogue_bp
from parametres_routes import parametres_bp
from devis_routes import devis_bp
app.register_blueprint(catalogue_bp)
app.register_blueprint(parametres_bp)
app.register_blueprint(devis_bp)


# --- Authentification globale ------------------------------------------------
_PUBLIC_PREFIXES = ("/login", "/static", "/healthz")


@app.before_request
def _require_login():
    password = config.get("app_password", "")
    if not password:
        return  # pas de mot de passe configuré (dev) -> pas de gate
    path = request.path
    if any(path == p or path.startswith(p + "/") or path.startswith(p) for p in _PUBLIC_PREFIXES):
        return
    if not session.get("auth"):
        return redirect(url_for("login", next=path))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password", "") == config.get("app_password", ""):
            session["auth"] = True
            session.permanent = True
            return redirect(request.args.get("next") or url_for("index"))
        flash("Mot de passe incorrect.", "error")
    return render_template("login.html", title="Connexion")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/healthz")
def healthz():
    return {"ok": True}


@app.route("/diag")
def diag():
    """Diagnostic de la connexion au stockage (protégé par le login global)."""
    info = {
        "storage_mode": config.get("storage_mode"),
        "on_render": is_on_render(),
        "dropbox_key_present": bool(config.get("dropbox", {}).get("app_key")),
        "dropbox_secret_present": bool(config.get("dropbox", {}).get("app_secret")),
        "dropbox_token_present": bool(config.get("dropbox", {}).get("refresh_token")),
        "connected": False,
        "events_found": None,
        "catalogue_counts": None,
        "error": None,
    }
    try:
        events = storage_io.list_events(STORAGE)
        info["events_found"] = events
        cat = storage_io.load_catalogue(STORAGE)
        info["catalogue_counts"] = {k: len(v) for k, v in cat.items()}
        info["connected"] = True
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"
    return jsonify(info)


# --- Statics du module fiches (logo, polices) --------------------------------
@app.route("/fiches-static/<path:filename>")
def fiches_static(filename):
    return send_file(STATIC_DIR / filename)


# --- Helpers -----------------------------------------------------------------
def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def list_events():
    events = []
    for name in storage_io.list_events(STORAGE):
        try:
            data = storage_io.load_event(STORAGE, name)
            events.append({
                "filename": name,
                "name": data.get("event", {}).get("name", "(sans nom)"),
                "location": data.get("event", {}).get("location", "—"),
                "reference": data.get("document", {}).get("reference", "—"),
                "outdoor": data.get("event", {}).get("outdoor", False),
            })
        except Exception as e:  # noqa: BLE001
            events.append({"filename": name, "name": f"⚠️ Erreur : {e}",
                           "location": "", "reference": "", "outdoor": False})
    return events


def _prepare_catalogue_context():
    import json as _json
    cat = storage_io.load_catalogue(STORAGE)

    packs_pour_js = {}
    for pack_id in cat["packs"]:
        try:
            packs_pour_js[pack_id] = resoudre_pack(pack_id, cat["packs"])
        except Exception:
            pass

    packs_par_cat = {}
    for pack_id, pack in cat["packs"].items():
        c = pack.get("categorie", "autre")
        packs_par_cat.setdefault(c, []).append({"id": pack_id, **pack})

    equipements_par_cat = {}
    for eq_id, eq in cat["equipements"].items():
        c = eq.get("categorie", "autre")
        equipements_par_cat.setdefault(c, []).append({"id": eq_id, **eq})
    for c in equipements_par_cat:
        equipements_par_cat[c].sort(key=lambda e: e.get("nom", ""))

    catalogue_json = _json.dumps({
        "equipements": cat["equipements"],
        "packs": packs_pour_js,
        "prestations": cat["prestations"],
    }, ensure_ascii=False, default=str)

    # Prestations facturables proposables en supplément (prix > 0, hors déplacement)
    prestations_pour_js = {}
    for pid, pr in cat["prestations"].items():
        if pr.get("categorie") == "deplacement":
            continue
        prestations_pour_js[pid] = pr

    # Packs complémentaires : compatibles en tête, puis le reste.
    # La compatibilité dépend du pack principal courant ; on expose tous les packs
    # avec un groupe "Compatibles" calculé côté template via JS au besoin. Ici on
    # fournit deux groupes simples : Photobooth d'abord (cas d'usage fréquent), puis autres.
    packs_photobooth, packs_autres = [], []
    for pid, pk in cat["packs"].items():
        entry = {"id": pid, "nom": pk.get("nom", pid), "prix_ttc": pk.get("prix_ttc", 0),
                 "categorie": pk.get("categorie", "")}
        if pk.get("categorie") == "photobooth":
            packs_photobooth.append(entry)
        else:
            packs_autres.append(entry)
    packs_photobooth.sort(key=lambda x: x["prix_ttc"])
    packs_autres.sort(key=lambda x: x["nom"])
    packs_compl_groupes = []
    if packs_photobooth:
        packs_compl_groupes.append({"label": "Photobooth", "packs": packs_photobooth})
    if packs_autres:
        packs_compl_groupes.append({"label": "Autres packs", "packs": packs_autres})

    return {
        "packs_par_cat": packs_par_cat,
        "equipements_par_cat": equipements_par_cat,
        "catalogue_json": catalogue_json,
        "prestations_pour_js": prestations_pour_js,
        "packs_compl_groupes": packs_compl_groupes,
    }


def _enrichir_data_avec_catalogue(data: dict) -> dict:
    import math
    has_pack = bool(data.get("pack_id"))
    has_supps = bool(data.get("supplements"))
    has_manuel = bool(data.get("materiel_manuel"))
    has_legacy = bool(data.get("materiel"))

    if has_pack or has_supps or has_manuel:
        try:
            cat = storage_io.load_catalogue(STORAGE)
            result = resoudre_evenement(data, cat)
            data["materiel"] = {
                "son_video": result["materiel_par_bucket"]["son_video"],
                "lumiere": result["materiel_par_bucket"]["lumiere"],
                "divers": result["materiel_par_bucket"]["divers"],
            }
            puissance_w = result["puissance_totale_w"]
            if not data.get("bilan_override") and result["puissance_totale_kw"] > 0:
                data.setdefault("electricite", {})
                data["electricite"]["puissance_kw"] = f"{result['puissance_totale_kw']:.1f}".replace(".", ",")
            elif data.get("bilan_override") and data.get("puissance_manuelle"):
                data.setdefault("electricite", {})
                data["electricite"]["puissance_kw"] = data["puissance_manuelle"]
                try:
                    puissance_w = float(data["puissance_manuelle"].replace(",", ".")) * 1000
                except (ValueError, AttributeError):
                    pass

            if not data.get("prises_override") and puissance_w > 0:
                data.setdefault("electricite", {})
                voltage = data["electricite"].get("voltage", 220)
                amperage = data["electricite"].get("amperage", 16)
                plancher_prises = data["electricite"].get("nb_prises", 2) or 2
                max_par_prise_w = amperage * voltage * 0.80
                nb = math.ceil(puissance_w / max_par_prise_w)
                nb = max(plancher_prises, nb)
                nb = min(8, nb)
                data["electricite"]["nb_prises"] = nb

            data["_bilan_interne"] = {
                "poids_total_kg": result["poids_total_kg"],
                "puissance_totale_w": result["puissance_totale_w"],
            }
        except Exception:  # noqa: BLE001
            if not has_legacy:
                data["materiel"] = {"son_video": [], "lumiere": [], "divers": []}
    return data


# --- Routes ------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html", events=list_events(), title="Fiches Techniques")


@app.route("/event/new")
def event_new():
    today = datetime.now().strftime("%d/%m/%Y")
    skeleton = {
        "document": {"reference": f"FT-{datetime.now().strftime('%Y')}-____", "date_emission": today},
        "event": {"name": "", "location": "", "outdoor": False, "horaire_fin": ""},
        "mode_composition": "catalogue",
        "pack_id": None,
        "supplements": [],
        "materiel_manuel": {"son_video": [], "lumiere": [], "divers": []},
        "bilan_override": False,
        "puissance_manuelle": None,
    }
    ctx = _prepare_catalogue_context()
    return render_template("event_form.html", data=skeleton, filename=None,
                           title="Nouvel événement", **ctx)


@app.route("/event/edit/<filename>")
def event_edit(filename):
    if not STORAGE.exists(f"events/{filename}"):
        abort(404)
    try:
        data = storage_io.load_event(STORAGE, filename)
    except StorageError as e:
        flash(str(e), "error")
        return redirect(url_for("index"))
    if "materiel" in data and not data.get("mode_composition"):
        data.setdefault("mode_composition", "manuel")
        data.setdefault("materiel_manuel", {
            "son_video": data["materiel"].get("son_video", []),
            "lumiere": data["materiel"].get("lumiere", []),
            "divers": [],
        })
    ctx = _prepare_catalogue_context()
    return render_template("event_form.html", data=data, filename=filename,
                           title=f"Édition · {filename}", **ctx)


@app.route("/event/save", methods=["POST"])
def event_save():
    form = request.form
    mode = form.get("mode_composition", "catalogue")
    materiel_son = [l.strip() for l in form.get("materiel_son", "").splitlines() if l.strip()]
    materiel_lum = [l.strip() for l in form.get("materiel_lum", "").splitlines() if l.strip()]
    materiel_div = [l.strip() for l in form.get("materiel_div", "").splitlines() if l.strip()]

    supplements = []
    for key in form.keys():
        if key.startswith("supp_id_"):
            idx = key.split("_")[-1]
            supp_id = form.get(f"supp_id_{idx}", "").strip()
            supp_type = form.get(f"supp_type_{idx}", "equipement").strip() or "equipement"
            try:
                supp_qte = int(form.get(f"supp_qte_{idx}", "1"))
            except ValueError:
                supp_qte = 1
            if supp_id:
                supplements.append({"type": supp_type, "id": supp_id, "quantite": supp_qte})

    retraits_eq, retraits_pr = [], []
    for key in form.keys():
        if key.startswith("retrait_eq_"):
            val = form.get(key, "").strip()
            if val:
                retraits_eq.append(val)
        elif key.startswith("retrait_pr_"):
            val = form.get(key, "").strip()
            if val:
                retraits_pr.append(val)

    data = {
        "document": {
            "reference": form.get("reference", "").strip(),
            "date_emission": form.get("date_emission", "").strip(),
        },
        "event": {
            "name": form.get("event_name", "").strip(),
            "location": form.get("event_location", "").strip(),
            "outdoor": form.get("event_outdoor") == "on",
            "horaire_fin": form.get("event_horaire_fin", "").strip(),
        },
        "client": {
            "prenom": form.get("client_prenom", "").strip(),
            "nom": form.get("client_nom", "").strip(),
            "email": form.get("client_email", "").strip(),
            "telephone": form.get("client_telephone", "").strip(),
            "adresse": form.get("client_adresse", "").strip(),
            "entreprise": form.get("client_entreprise", "").strip(),
            "siret": form.get("client_siret", "").strip(),
        },
        "mode_composition": mode,
    }

    existing_devis = {}
    existing_filename = form.get("filename", "").strip()
    if existing_filename and STORAGE.exists(f"events/{existing_filename}"):
        try:
            existing_devis = storage_io.load_event(STORAGE, existing_filename).get("devis", {}) or {}
        except Exception:
            pass

    devis_section = dict(existing_devis)
    if form.get("devis_prix_propose", "").strip():
        devis_section["prix_propose"] = form.get("devis_prix_propose", "").strip()
    elif "prix_propose" in devis_section:
        del devis_section["prix_propose"]
    if form.get("devis_acompte_pct", "").strip():
        try:
            devis_section["acompte_pct"] = int(form.get("devis_acompte_pct"))
        except ValueError:
            pass
    if form.get("devis_validite_jours", "").strip():
        try:
            devis_section["validite_jours"] = int(form.get("devis_validite_jours"))
        except ValueError:
            pass
    if devis_section:
        data["devis"] = devis_section

    if mode == "catalogue":
        pack_id = form.get("pack_id", "").strip()
        data["pack_id"] = pack_id if pack_id else None
        data["supplements"] = supplements
        if retraits_eq or retraits_pr:
            data["retraits"] = {"equipements": retraits_eq, "prestations": retraits_pr}
    else:
        data["materiel_manuel"] = {"son_video": materiel_son, "lumiere": materiel_lum, "divers": materiel_div}

    if form.get("bilan_override") == "on":
        data["bilan_override"] = True
        data["puissance_manuelle"] = form.get("puissance_manuelle", "").strip() or None
    else:
        data["bilan_override"] = False

    if form.get("prises_override") == "on":
        data["prises_override"] = True
        try:
            data["electricite"] = data.get("electricite", {})
            data["electricite"]["nb_prises"] = int(form.get("nb_prises_manuel", "4"))
        except ValueError:
            pass
    else:
        data["prises_override"] = False
        if "electricite" in data and "nb_prises" in data["electricite"]:
            del data["electricite"]["nb_prises"]

    filename = form.get("filename", "").strip()
    if not filename:
        ref = data["document"]["reference"] or "sans-ref"
        ev = slugify(data["event"]["name"] or "sans-nom")
        filename = f"{ref}-{ev}.json"
    if not filename.endswith(".json"):
        filename += ".json"

    storage_io.save_event(STORAGE, filename, data)
    flash(f"Événement sauvegardé : {filename}", "success")
    return redirect(url_for("event_preview", filename=filename))


@app.route("/event/delete/<filename>", methods=["POST"])
def event_delete(filename):
    if STORAGE.exists(f"events/{filename}"):
        storage_io.delete_event(STORAGE, filename)
        flash(f"Événement supprimé : {filename}", "success")
    return redirect(url_for("index"))


@app.route("/event/preview/<filename>")
def event_preview(filename):
    return render_template("preview.html", filename=filename, title=f"Aperçu · {filename}")


@app.route("/event/render/<filename>")
def event_render(filename):
    if not STORAGE.exists(f"events/{filename}"):
        abort(404)
    try:
        data = storage_io.load_config_merged(STORAGE, filename)
        validate(data)
    except (ConfigError, StorageError) as e:
        return f"<pre>Erreur : {e}</pre>", 400
    data = _enrichir_data_avec_catalogue(data)
    html = render_html(data, template_dir=TEMPLATE_DIR,
                       static_url=url_for("fiches_static", filename="").rstrip("/"))
    return html


@app.route("/event/pdf/<filename>")
def event_pdf(filename):
    if not STORAGE.exists(f"events/{filename}"):
        abort(404)
    try:
        data = storage_io.load_config_merged(STORAGE, filename)
        validate(data)
    except (ConfigError, StorageError) as e:
        return f"<pre>Erreur : {e}</pre>", 400
    data = _enrichir_data_avec_catalogue(data)
    html = render_html(data, template_dir=TEMPLATE_DIR, static_url=".")

    stem = Path(filename).stem
    pdf_path = Path(tempfile.gettempdir()) / f"{stem}.pdf"
    try:
        export_pdf(html, pdf_path, base_url=STATIC_DIR)
    except ImportError as e:
        return f"<pre>{e}</pre>", 500
    return send_file(pdf_path, as_attachment=True, download_name=f"{stem}.pdf")


@app.route("/event/raw/<filename>")
def event_raw(filename):
    if not STORAGE.exists(f"events/{filename}"):
        abort(404)
    return jsonify(storage_io.load_event(STORAGE, filename))


if __name__ == "__main__":
    print(f"📂 Projet : {ROOT}")
    print(f"💾 Stockage : {config.get('storage_mode')}")
    print("🌐 http://localhost:5001  (Ctrl+C pour arrêter)")
    app.run(host="127.0.0.1", port=5001, debug=False, use_reloader=False)
