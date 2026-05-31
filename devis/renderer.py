"""
devis.renderer — Génération du HTML du devis.

Utilise un template Jinja2 dédié au devis (pas la fiche technique).
Le HTML produit est destiné à :
    1. Affichage sur la page web partageable
    2. Export PDF via WeasyPrint
    3. Page de validation client (signature)
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime


def render_devis_html(
    data: dict,
    result: dict,
    template_dir: Path,
    static_url: str = "",
    mode: str = "preview",
    catalogue: dict = None,
) -> str:
    """
    Génère le HTML du devis.

    Args:
        data: dict événement (avec sections document, event, client, devis...)
        result: dict résultat du event_resolver (composition, prix, retraits_appliques...)
        template_dir: dossier des templates Jinja2
        static_url: URL de base pour les statics (logo, fonts)
        mode: 'preview' (pour aperçu admin) | 'client' (page partageable client) | 'pdf'
        catalogue: dict catalogue ({equipements, prestations, packs}) — pour résoudre les noms

    Returns:
        HTML rendu
    """
    template_dir = Path(template_dir)
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Filtres custom
    env.filters["euro"] = _filter_euro
    env.filters["pct"] = _filter_pct
    env.filters["date_fr"] = _filter_date_fr

    # Construit la liste des suppléments enrichie (id → nom, prix).
    # Gère les 3 types : equipement (défaut, rétro-compat), prestation, pack.
    # Croise avec result["supplements_detail"] pour récupérer le prix facturé / offert.
    supplements_enriched = []
    if catalogue:
        from catalogue.pricing import calculer_prix
        try:
            from catalogue.packs import resoudre_pack
        except Exception:
            resoudre_pack = None
        equipements = catalogue.get("equipements", {})
        prestations = catalogue.get("prestations", {})
        packs = catalogue.get("packs", {})

        # Index des détails calculés par le resolver : (type, id) -> detail
        detail_idx = {}
        for t, key in (("equipement", "equipements"), ("prestation", "prestations"), ("pack", "packs")):
            for d in (result.get("supplements_detail", {}) or {}).get(key, []):
                detail_idx[(t, d["id"])] = d

        def _enrich(entry, supp_type, supp_id, prix_plein):
            """Ajoute prix facturé/offert/reduit à une ligne d'après le resolver."""
            d = detail_idx.get((supp_type, supp_id))
            if d:
                entry["prix"] = d.get("valeur_facturee", prix_plein)
                entry["prix_plein"] = d.get("valeur", prix_plein)
                entry["offert"] = d.get("offert", False)
                entry["reduit"] = d.get("reduit", False)
            else:
                entry["prix"] = prix_plein
                entry["prix_plein"] = prix_plein
                entry["offert"] = False
                entry["reduit"] = False
            return entry

        for supp in (data.get("supplements") or []):
            supp_id = supp.get("id")
            qte = supp.get("quantite", 1) or 1
            supp_type = supp.get("type", "equipement")
            if not supp_id:
                continue

            if supp_type == "prestation":
                pr = prestations.get(supp_id)
                if not pr:
                    continue
                supplements_enriched.append(_enrich({
                    "id": supp_id, "type": "prestation",
                    "nom": pr.get("nom", supp_id),
                    "description": pr.get("description", ""),
                    "quantite": qte,
                }, "prestation", supp_id, float(pr.get("prix", 0)) * qte))
            elif supp_type == "pack":
                pk = packs.get(supp_id)
                if not pk:
                    continue
                prix_pack = pk.get("prix_ttc", 0)
                if resoudre_pack:
                    try:
                        prix_pack = resoudre_pack(supp_id, packs).get("prix_ttc", prix_pack)
                    except Exception:
                        pass
                supplements_enriched.append(_enrich({
                    "id": supp_id, "type": "pack",
                    "nom": pk.get("nom", supp_id),
                    "description": pk.get("description", ""),
                    "quantite": qte,
                }, "pack", supp_id, float(prix_pack) * qte))
            else:  # equipement
                eq = equipements.get(supp_id)
                if not eq:
                    continue
                try:
                    prix = calculer_prix(eq, qte)
                except Exception:
                    prix = 0
                supplements_enriched.append(_enrich({
                    "id": supp_id, "type": "equipement",
                    "nom": eq.get("nom", supp_id),
                    "description": eq.get("description_courte", ""),
                    "quantite": qte,
                }, "equipement", supp_id, prix))


    # Contenu du pack groupé par catégorie (sans prix), pour l'afficher sous le pack.
    # On prend la composition PROPRE du pack résolu (héritage inclus), PAS la
    # composition globale de l'événement — sinon les suppléments/packs ajoutés
    # (qui ont déjà leur propre ligne) feraient doublon.
    pack_contenu = []
    pack_obj = result.get("pack")
    if pack_obj and catalogue:
        CAT_LABELS = {
            "son": "Son", "regie": "Régie DJ", "video": "Vidéo",
            "lumiere": "Lumière", "effet": "Effets", "effets": "Effets",
            "structure": "Structure", "energie": "Énergie", "autre": "Divers",
        }
        equipements = catalogue.get("equipements", {})
        prestations = catalogue.get("prestations", {})

        # Composition propre du pack (avec héritage), indépendante des ajouts
        try:
            from catalogue.packs import resoudre_pack
            pack_id = pack_obj.get("id") or data.get("pack_id")
            pack_resolu = resoudre_pack(pack_id, catalogue.get("packs", {}))
            compo_pack = pack_resolu.get("composition_complete", {})
        except Exception:
            compo_pack = result.get("composition", {})

        # Ids retirés (pour ne pas les lister comme inclus)
        retr = result.get("retraits_appliques", {})
        ids_retires_eq = {r["id"] for r in retr.get("equipements", [])}
        ids_retires_pr = {r["id"] for r in retr.get("prestations", [])}

        groupes = {}
        for ligne in compo_pack.get("equipements", []):
            if ligne["id"] in ids_retires_eq:
                continue
            eq = equipements.get(ligne["id"], {})
            cat = eq.get("categorie", "autre")
            label = CAT_LABELS.get(cat, cat.capitalize() if cat else "Divers")
            groupes.setdefault(label, []).append(
                f'{ligne["quantite"]}× {eq.get("nom", ligne["id"])}')
        prest_items = []
        # Pour l'animation DJ : remplacer le "(≈ 3h)" figé par l'horaire de fin réel.
        # Moment selon la catégorie du pack : dj_prive → apéritif, mariage → vin d'honneur.
        horaire_fin = (data.get("event", {}) or {}).get("horaire_fin", "").strip()
        cat_pack = pack_obj.get("categorie") or ""
        moment = "du vin d'honneur" if cat_pack == "mariage" else "de l'apéritif"
        for ligne in compo_pack.get("prestations", []):
            if ligne["id"] in ids_retires_pr:
                continue
            pr = prestations.get(ligne["id"], {})
            nom = pr.get("nom", ligne["id"])
            if pr.get("categorie") == "animation" and horaire_fin:
                prest_items.append(
                    f"Animation DJ {moment} jusqu'à approximativement {horaire_fin}")
            else:
                prest_items.append(nom)

        ordre = ["Son", "Régie DJ", "Vidéo", "Lumière", "Effets", "Structure", "Énergie", "Divers"]
        for label in ordre:
            if label in groupes:
                pack_contenu.append({"categorie": label, "elements": groupes[label]})
        for label, items in groupes.items():
            if label not in ordre:
                pack_contenu.append({"categorie": label, "elements": items})
        if prest_items:
            pack_contenu.append({"categorie": "Prestations incluses", "elements": prest_items})

    tpl = env.get_template("devis.html.j2")
    return tpl.render(
        pack_contenu=pack_contenu,
        # Métadonnées principales
        prestataire=data.get("prestataire", {}),
        electricite=data.get("electricite", {}),
        document=data.get("document", {}),
        event=data.get("event", {}),
        client=data.get("client", {}),
        devis=data.get("devis", {}),
        annulation=data.get("annulation", {}),
        # Résultat résolution catalogue
        composition=result.get("composition", {}),
        retraits=result.get("retraits_appliques", {}),
        pack=result.get("pack"),
        prix=result.get("prix", {}),
        supplements_enriched=supplements_enriched,
        # Méta-rendu
        static_url=static_url,
        mode=mode,
        now=datetime.now(),
    )


def _filter_euro(value):
    """Formate un montant en euros: '1 234 €'."""
    if value is None:
        return ""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return value
    # Espace fine insécable comme séparateur de milliers
    s = f"{n:,.0f}".replace(",", "\u202F")
    return f"{s} €"


def _filter_pct(value):
    """Formate un pourcentage: '12,5 %'."""
    if value is None:
        return ""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return value
    s = f"{n:.1f}".replace(".", ",")
    # Enlève le ,0 si entier
    if s.endswith(",0"):
        s = s[:-2]
    return f"{s} %"


def _filter_date_fr(value):
    """Affiche une date en français court."""
    if not value:
        return ""
    if isinstance(value, str):
        # Tente quelques formats
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                value = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            return value  # garde tel quel si non parsable
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    return str(value)


