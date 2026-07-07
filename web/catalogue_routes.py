"""
web/catalogue_routes.py — Routes catalogue (version cloud, via storage).

Identique à l'original, mais : lecture/écriture du catalogue via le storage,
et photos servies depuis le storage (Dropbox ou local) avec cache mémoire.
"""

import sys
import json
import mimetypes
import re
import unicodedata
from pathlib import Path

from flask import (
    Blueprint, render_template, request, redirect, url_for, abort, flash, Response
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from catalogue import (
    calculer_prix, paliers_disponibles,
    resoudre_pack, calculer_valeur_a_la_carte,
)
from catalogue.queries import (
    equipements_par_categorie, packs_par_categorie,
    label_categorie, CATEGORIE_LABELS,
)
from app_storage import STORAGE
import storage_io

catalogue_bp = Blueprint("catalogue", __name__, url_prefix="/catalogue")

# Cache mémoire des photos (évite un appel API par vignette)
_PHOTO_CACHE: dict = {}
_PHOTO_CACHE_MAX = 200

# Traitement des photos uploadées
_PHOTO_MAX_SIDE = 1200  # px, plus grand côté


def _slugifier(texte: str) -> str:
    """Transforme un texte en slug propre : sans accent, minuscules, tirets."""
    s = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[-\s]+", "-", s)
    return s


def _traiter_photo_uploadee(file_storage, nom_fichier_voulu: str) -> str:
    """
    Convertit l'image uploadée en PNG, la redimensionne (max 1200px sur le
    plus grand côté) et l'écrit dans catalogue/photos/ via le storage.
    Retourne le nom de fichier final (toujours en .png), ou lève une erreur.
    """
    import io
    from PIL import Image

    # Nom de fichier final : slug + .png (on ignore l'extension d'origine)
    base = _slugifier(Path(nom_fichier_voulu).stem) if nom_fichier_voulu else ""
    if not base:
        raise ValueError("Nom de fichier photo vide après nettoyage.")
    nom_final = f"{base}.png"

    # Ouverture + conversion
    data_in = file_storage.read()
    img = Image.open(io.BytesIO(data_in))

    # Aplatir la transparence sur fond blanc si nécessaire (RGBA/P -> RGB)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        fond = Image.new("RGBA", img.size, (255, 255, 255, 255))
        fond.paste(img, mask=img.split()[-1])
        img = fond.convert("RGB")
    else:
        img = img.convert("RGB")

    # Redimensionnement proportionnel si trop grand
    w, h = img.size
    cote = max(w, h)
    if cote > _PHOTO_MAX_SIDE:
        ratio = _PHOTO_MAX_SIDE / float(cote)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # Export PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data_out = buf.getvalue()

    # Écriture via le storage (Dropbox ou local, même canal que les JSON)
    rel = f"catalogue/photos/{nom_final}"
    STORAGE.write_bytes(rel, data_out)

    # Purge du cache mémoire pour ce fichier (au cas où il existait déjà)
    _PHOTO_CACHE.pop(nom_final, None)

    return nom_final


def _load():
    return storage_io.load_catalogue(STORAGE)


@catalogue_bp.route("/")
def index():
    return redirect(url_for("catalogue.equipements_list"))


@catalogue_bp.route("/photo/<filename>")
def photo(filename):
    """Sert une photo d'équipement depuis le storage, avec cache."""
    rel = f"catalogue/photos/{filename}"
    data = _PHOTO_CACHE.get(filename)
    if data is None:
        if not STORAGE.exists(rel):
            abort(404)
        try:
            data = STORAGE.read_bytes(rel)
        except Exception:
            abort(404)
        if len(_PHOTO_CACHE) < _PHOTO_CACHE_MAX:
            _PHOTO_CACHE[filename] = data
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(data, mimetype=mime, headers={"Cache-Control": "public, max-age=86400"})


@catalogue_bp.route("/publier-vitrine", methods=["POST"])
def publier_vitrine():
    """Régénère et publie la page catalogue du site vitrine (GitHub Pages).

    Lit le catalogue en prod (storage), régénère docs/catalogue.html + les
    photos manquantes et pousse le tout sur le repo GitHub. Aucune écriture
    sur Dropbox/prod.
    """
    import vitrine_publisher
    try:
        res = vitrine_publisher.publier(STORAGE)
        if res.get("no_change"):
            flash("Vitrine déjà à jour — aucun changement à publier.", "success")
        else:
            msg = f"Catalogue vitrine publié ✅ ({res['equipements']} équipements"
            if res.get("photos_ajoutees"):
                msg += f", {len(res['photos_ajoutees'])} photo(s) ajoutée(s)"
            msg += "). Le site se met à jour dans 1–2 min."
            flash(msg, "success")
    except vitrine_publisher.VitrinePublishError as e:
        flash(f"Publication vitrine échouée : {e}", "error")
    except Exception as e:  # noqa: BLE001
        flash(f"Erreur inattendue lors de la publication : {e}", "error")
    return redirect(url_for("catalogue.equipements_list"))


# ==================== ÉQUIPEMENTS ====================

@catalogue_bp.route("/equipements")
def equipements_list():
    cat = _load()
    groupes = equipements_par_categorie(cat["equipements"])
    return render_template("catalogue/equipements_list.html",
                           groupes=groupes, label_categorie=label_categorie,
                           title="Catalogue — Équipements")


@catalogue_bp.route("/equipements/new")
def equipement_new():
    return render_template("catalogue/equipement_form.html",
                           equipement={}, equipement_id=None,
                           categories=CATEGORIE_LABELS, title="Nouvel équipement")


@catalogue_bp.route("/equipements/<eq_id>/edit")
def equipement_edit(eq_id):
    cat = _load()
    if eq_id not in cat["equipements"]:
        abort(404)
    eq = cat["equipements"][eq_id]
    return render_template("catalogue/equipement_form.html",
                           equipement=eq, equipement_id=eq_id,
                           categories=CATEGORIE_LABELS,
                           title=f"Édition · {eq.get('nom', eq_id)}")


@catalogue_bp.route("/equipements/save", methods=["POST"])
def equipement_save():
    form = request.form
    cat = _load()

    eq_id = form.get("equipement_id", "").strip()
    is_new = not eq_id

    if is_new:
        nom = form.get("nom", "").strip()
        slug = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^\w\s-]", "", slug).strip().lower()
        slug = re.sub(r"[-\s]+", "-", slug)
        eq_id = slug
        if not eq_id:
            flash("Le nom est obligatoire", "error")
            return redirect(url_for("catalogue.equipement_new"))
        if eq_id in cat["equipements"]:
            flash(f"Un équipement avec cet id existe déjà : {eq_id}", "error")
            return redirect(url_for("catalogue.equipement_new"))

    def _f(key, default="", typ=str):
        val = form.get(key, default)
        if typ == int:
            try: return int(val) if val else None
            except ValueError: return None
        if typ == float:
            try: return float(val) if val else None
            except ValueError: return None
        if typ == bool:
            return val == "on"
        return val.strip() if isinstance(val, str) else val

    mode_vente = _f("vente_mode", "forfaitaire")
    qa_type = _f("vente_qa_type", "libre")

    vente = {
        "mode": mode_vente,
        "unite_label": _f("vente_unite_label", "unité"),
        "quantites_autorisees": {"type": qa_type},
    }

    if qa_type == "multiples_de":
        vente["quantites_autorisees"]["valeur"] = _f("vente_qa_valeur_int", 1, int) or 1
    elif qa_type == "valeurs_fixes":
        valeurs_str = form.get("vente_qa_valeurs", "").strip()
        try:
            valeurs = [int(x.strip()) for x in valeurs_str.split(",") if x.strip()]
        except ValueError:
            valeurs = []
        vente["quantites_autorisees"]["valeur"] = valeurs

    if mode_vente in ("forfaitaire", "unitaire"):
        vente["prix_unitaire"] = _f("vente_prix_unitaire", 0, float) or 0
    elif mode_vente == "tranches":
        paliers_json = form.get("vente_paliers_json", "[]")
        try:
            vente["paliers"] = json.loads(paliers_json)
        except json.JSONDecodeError:
            vente["paliers"] = []

    # ---- Traitement de la photo ----
    # Priorité : si un fichier est uploadé, on le convertit/redimensionne et
    # on l'écrit dans le storage. Sinon, on garde le nom de fichier saisi.
    photo_nom = _f("photo")
    fichier = request.files.get("photo_upload")
    if fichier and fichier.filename:
        # Nom voulu : champ "photo" si rempli, sinon slug de l'id équipement
        nom_voulu = photo_nom or f"{eq_id}.png"
        try:
            photo_nom = _traiter_photo_uploadee(fichier, nom_voulu)
            flash(f"Photo importée : {photo_nom}", "success")
        except Exception as exc:
            flash(f"Échec de l'import de la photo : {exc}", "error")
            # On ne bloque pas la sauvegarde de l'équipement pour autant.
    if not photo_nom:
        photo_nom = f"{eq_id}.png"

    equipement = {
        "nom": _f("nom"),
        "marque": _f("marque") or None,
        "modele": _f("modele") or None,
        "categorie": _f("categorie", "autre"),
        "sous_categorie": _f("sous_categorie") or None,
        "description_courte": _f("description_courte") or None,
        "description_longue": _f("description_longue") or None,
        "photo": photo_nom,
        "puissance_w": _f("puissance_w", 0, float) or 0,
        "poids_kg": _f("poids_kg", 0, float) or 0,
        "dimensions": _f("dimensions") or None,
        "dmx": _f("dmx", False, bool),
        "connecteurs": [c.strip() for c in form.get("connecteurs", "").split(",") if c.strip()],
        "vente": vente,
        "quantite_possedee": _f("quantite_possedee", 1, int) or 1,
        "visible_dans": {
            "devis": _f("visible_devis", False, bool),
            "fiche_materiel": _f("visible_fiche_materiel", False, bool),
            "fiche_puissance": _f("visible_fiche_puissance", False, bool),
            "catalogue": _f("visible_catalogue", False, bool),
        },
        "tags": [t.strip() for t in form.get("tags", "").split(",") if t.strip()],
    }

    cat["equipements"][eq_id] = equipement
    storage_io.save_catalogue_section(STORAGE, cat, "equipements")
    flash(f"Équipement sauvegardé : {equipement['nom']}", "success")
    return redirect(url_for("catalogue.equipements_list"))


@catalogue_bp.route("/equipements/<eq_id>/delete", methods=["POST"])
def equipement_delete(eq_id):
    cat = _load()
    if eq_id not in cat["equipements"]:
        abort(404)
    nom = cat["equipements"][eq_id].get("nom", eq_id)
    del cat["equipements"][eq_id]
    storage_io.save_catalogue_section(STORAGE, cat, "equipements")
    flash(f"Équipement supprimé : {nom}", "success")
    return redirect(url_for("catalogue.equipements_list"))


# ==================== PACKS ====================

@catalogue_bp.route("/packs")
def packs_list():
    cat = _load()
    groupes = packs_par_categorie(cat["packs"])
    for cat_groupes in groupes.values():
        for p in cat_groupes:
            try:
                pack_resolu = resoudre_pack(p["id"], cat["packs"])
                p["_valeur_carte"] = calculer_valeur_a_la_carte(
                    pack_resolu, cat["equipements"], cat["prestations"])
            except Exception:
                p["_valeur_carte"] = None
    return render_template("catalogue/packs_list.html",
                           groupes=groupes, label_categorie=label_categorie,
                           title="Catalogue — Packs")


@catalogue_bp.route("/packs/<pack_id>/edit")
def pack_edit(pack_id):
    cat = _load()
    if pack_id not in cat["packs"]:
        abort(404)
    pack = cat["packs"][pack_id]
    pack_resolu = resoudre_pack(pack_id, cat["packs"])
    valeur_carte = calculer_valeur_a_la_carte(pack_resolu, cat["equipements"], cat["prestations"])
    return render_template("catalogue/pack_form.html",
                           pack=pack, pack_id=pack_id, pack_resolu=pack_resolu,
                           valeur_carte=valeur_carte, catalogue=cat,
                           equipements_tries=_equipements_tries(cat),
                           prestations_triees=_prestations_triees(cat),
                           packs_extends=_packs_pour_extends(cat, pack_id),
                           categories=CATEGORIE_LABELS,
                           title=f"Édition pack · {pack.get('nom', pack_id)}")


@catalogue_bp.route("/packs/new")
def pack_new():
    cat = _load()
    return render_template("catalogue/pack_form.html",
                           pack={}, pack_id=None, pack_resolu=None,
                           valeur_carte=0, catalogue=cat,
                           equipements_tries=_equipements_tries(cat),
                           prestations_triees=_prestations_triees(cat),
                           packs_extends=_packs_pour_extends(cat, None),
                           categories=CATEGORIE_LABELS, title="Nouveau pack")


def _equipements_tries(cat):
    items = [{"id": eid, "nom": e.get("nom", eid), "categorie": e.get("categorie", "")}
             for eid, e in cat["equipements"].items()]
    items.sort(key=lambda x: (x["categorie"], x["nom"]))
    return items


def _prestations_triees(cat):
    items = [{"id": pid, "nom": p.get("nom", pid), "categorie": p.get("categorie", "")}
             for pid, p in cat["prestations"].items()]
    items.sort(key=lambda x: (x["categorie"], x["nom"]))
    return items


def _packs_pour_extends(cat, exclude_id):
    """Liste des packs pouvant servir de parent (héritage), en excluant le pack courant."""
    items = [{"id": pid, "nom": p.get("nom", pid)}
             for pid, p in cat["packs"].items() if pid != exclude_id]
    items.sort(key=lambda x: x["nom"])
    return items


@catalogue_bp.route("/packs/save", methods=["POST"])
def pack_save():
    import re as _re
    import unicodedata as _ud
    form = request.form
    cat = _load()

    pack_id = form.get("pack_id", "").strip()
    is_new = not pack_id

    if is_new:
        nom = form.get("nom", "").strip()
        slug = _ud.normalize("NFKD", nom).encode("ascii", "ignore").decode()
        slug = _re.sub(r"[^\w\s-]", "", slug).strip().lower()
        slug = _re.sub(r"[-\s]+", "-", slug)
        pack_id = slug
        if not pack_id:
            flash("Le nom est obligatoire", "error")
            return redirect(url_for("catalogue.pack_new"))
        if pack_id in cat["packs"]:
            flash(f"Un pack avec cet id existe déjà : {pack_id}", "error")
            return redirect(url_for("catalogue.pack_new"))

    def _float(key, default=0):
        try:
            return float(form.get(key, default))
        except (ValueError, TypeError):
            return default

    # Composition : champs comp_eq_id_N / comp_eq_qte_N et comp_pr_id_N / comp_pr_qte_N
    def _collect(prefix):
        out = []
        for k in form.keys():
            if k.startswith(f"{prefix}_id_"):
                idx = k.rsplit("_", 1)[-1]
                cid = form.get(f"{prefix}_id_{idx}", "").strip()
                try:
                    q = int(form.get(f"{prefix}_qte_{idx}", "1"))
                except ValueError:
                    q = 1
                if cid:
                    out.append({"id": cid, "quantite": q})
        return out

    pack = {
        "nom": form.get("nom", "").strip(),
        "categorie": form.get("categorie", "autre").strip() or "autre",
        "prix_ttc": _float("prix_ttc", 0),
        "duree_estimee": form.get("duree_estimee", "").strip(),
        "description": form.get("description", "").strip(),
        "composition": {
            "equipements": _collect("comp_eq"),
            "prestations": _collect("comp_pr"),
        },
        "retraits": [r.strip() for r in form.getlist("retraits") if r.strip()],
        "bundle_compatible": [b.strip() for b in form.getlist("bundle_compatible") if b.strip()],
        "visible_dans": {
            "devis": form.get("visible_devis") == "on",
            "catalogue": form.get("visible_catalogue") == "on",
        },
    }
    extends = form.get("extends", "").strip()
    if extends:
        pack["extends"] = extends

    # Préserver d'éventuelles clés non gérées par le formulaire
    if not is_new and pack_id in cat["packs"]:
        for k, v in cat["packs"][pack_id].items():
            if k not in pack and k not in ("extends",):
                pack[k] = v

    cat["packs"][pack_id] = pack
    storage_io.save_catalogue_section(STORAGE, cat, "packs")
    flash(f"Pack sauvegardé : {pack['nom']}", "success")
    return redirect(url_for("catalogue.packs_list"))


@catalogue_bp.route("/packs/<pack_id>/delete", methods=["POST"])
def pack_delete(pack_id):
    cat = _load()
    if pack_id not in cat["packs"]:
        abort(404)
    nom = cat["packs"][pack_id].get("nom", pack_id)
    del cat["packs"][pack_id]
    storage_io.save_catalogue_section(STORAGE, cat, "packs")
    flash(f"Pack supprimé : {nom}", "success")
    return redirect(url_for("catalogue.packs_list"))


# ==================== PRESTATIONS ====================

@catalogue_bp.route("/prestations")
def prestations_list():
    cat = _load()
    prestations = [{"id": pid, **p} for pid, p in cat["prestations"].items()]
    prestations.sort(key=lambda x: (x.get("categorie", ""), x.get("nom", "")))
    return render_template("catalogue/prestations_list.html",
                           prestations=prestations, title="Catalogue — Prestations")


PRESTATION_CATEGORIES = ["animation", "captation", "consommable", "deplacement", "service"]


@catalogue_bp.route("/prestations/new")
def prestation_new():
    return render_template("catalogue/prestation_form.html",
                           prestation={}, presta_id=None,
                           categories=PRESTATION_CATEGORIES,
                           title="Nouvelle prestation")


@catalogue_bp.route("/prestations/<presta_id>/edit")
def prestation_edit(presta_id):
    cat = _load()
    if presta_id not in cat["prestations"]:
        abort(404)
    p = cat["prestations"][presta_id]
    return render_template("catalogue/prestation_form.html",
                           prestation=p, presta_id=presta_id,
                           categories=PRESTATION_CATEGORIES,
                           title=f"Édition · {p.get('nom', presta_id)}")


@catalogue_bp.route("/prestations/save", methods=["POST"])
def prestation_save():
    form = request.form
    cat = _load()

    presta_id = form.get("prestation_id", "").strip()
    is_new = not presta_id

    if is_new:
        nom = form.get("nom", "").strip()
        slug = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^\w\s-]", "", slug).strip().lower()
        slug = re.sub(r"[-\s]+", "-", slug)
        presta_id = slug
        if not presta_id:
            flash("Le nom est obligatoire", "error")
            return redirect(url_for("catalogue.prestation_new"))
        if presta_id in cat["prestations"]:
            flash(f"Une prestation avec cet id existe déjà : {presta_id}", "error")
            return redirect(url_for("catalogue.prestation_new"))

    def _f(key, default="", typ=str):
        val = form.get(key, default)
        if typ == int:
            try: return int(val) if val else None
            except ValueError: return None
        if typ == float:
            try: return float(val) if val else None
            except ValueError: return None
        if typ == bool:
            return val == "on"
        return val.strip() if isinstance(val, str) else val

    # Préserver les clés existantes non gérées par le formulaire
    existing = cat["prestations"].get(presta_id, {}) if not is_new else {}

    prestation = {
        **existing,
        "nom": _f("nom"),
        "categorie": _f("categorie", "service"),
        "description": _f("description") or "",
        "prix": _f("prix", 0, float) or 0,
        "unite_facturation": _f("unite_facturation", "forfait"),
        "visible_dans": {
            "devis": _f("visible_devis", False, bool),
            "catalogue": _f("visible_catalogue", False, bool),
        },
        "tags": [t.strip() for t in form.get("tags", "").split(",") if t.strip()],
    }

    cat["prestations"][presta_id] = prestation
    storage_io.save_catalogue_section(STORAGE, cat, "prestations")
    flash(f"Prestation sauvegardée : {prestation['nom']}", "success")
    return redirect(url_for("catalogue.prestations_list"))


@catalogue_bp.route("/prestations/<presta_id>/delete", methods=["POST"])
def prestation_delete(presta_id):
    cat = _load()
    if presta_id not in cat["prestations"]:
        abort(404)
    nom = cat["prestations"][presta_id].get("nom", presta_id)
    del cat["prestations"][presta_id]
    storage_io.save_catalogue_section(STORAGE, cat, "prestations")
    flash(f"Prestation supprimée : {nom}", "success")
    return redirect(url_for("catalogue.prestations_list"))
