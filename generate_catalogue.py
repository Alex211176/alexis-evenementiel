#!/usr/bin/env python3
"""
Génère une page catalogue statique (HTML autonome) à partir du catalogue.
Réexécutable : relancer après chaque mise à jour du catalogue pour resynchroniser.

Usage :
    python3 generate_catalogue.py [chemin_catalogue] [chemin_sortie]

Par défaut, lit les JSON dans le dossier courant et écrit catalogue.html.
Les photos sont copiées dans <sortie>/photos/ pour une page autonome.
"""
import json
import sys
import shutil
from pathlib import Path
from datetime import datetime
from html import escape


# ----- Libellés et ordre d'affichage -----
PACK_CATEGORIES = {
    "dj_prive": "DJ privé",
    "mariage": "Mariage",
    "photobooth": "Photobooth",
}
EQUIP_CATEGORIES = {
    "son": "Sonorisation",
    "regie": "Régie DJ",
    "lumiere": "Lumière",
    "effet": "Effets",
    "video": "Vidéo",
    "photo": "Photo / Booth",
    "energie": "Énergie",
}
# Prestations : on n'affiche en vitrine que ces catégories "vendables"
PRESTA_CATEGORIES_VITRINE = {
    "animation": "Animation",
    "captation": "Photo & Vidéo",
    "service": "Services",
}


def _clean(d):
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_catalogue(base: Path):
    eq = _clean(json.loads((base / "equipements.json").read_text(encoding="utf-8"))["equipements"])
    pr = _clean(json.loads((base / "prestations.json").read_text(encoding="utf-8"))["prestations"])
    pk = _clean(json.loads((base / "packs.json").read_text(encoding="utf-8"))["packs"])
    return eq, pr, pk


def euro(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if v == int(v):
        return f"{int(v)} €"
    return f"{v:.2f} €".replace(".", ",")


def prix_equipement(e):
    """Retourne (montant, prefixe) pour l'affichage.
    - mode forfaitaire : prix_unitaire, sans préfixe
    - mode tranches : prix du palier 1 unité, préfixe 'à partir de'
    - sinon : (None, '')
    """
    vente = e.get("vente", {}) or {}
    mode = vente.get("mode")
    if mode == "tranches":
        paliers = vente.get("paliers", []) or []
        if paliers:
            # palier le plus bas (généralement 1 unité)
            p = min(paliers, key=lambda x: x.get("qte", 1))
            montant = p.get("prix_forfait")
            if montant:
                return montant, "à partir de "
        return None, ""
    # forfaitaire
    return vente.get("prix_unitaire"), ""


def equipement_visible_catalogue(e):
    """L'équipement est-il affiché dans le catalogue public ?
    Par défaut True ; on l'exclut seulement si visible_dans.catalogue == False."""
    vd = e.get("visible_dans", {}) or {}
    return vd.get("catalogue", True)


def prestation_visible_catalogue(p):
    """La prestation est-elle affichée dans le catalogue public ?
    Par défaut True ; on l'exclut seulement si visible_dans.catalogue == False."""
    vd = p.get("visible_dans", {}) or {}
    return vd.get("catalogue", True)


def resoudre_pack_simple(pid, packs, _seen=None):
    """Résout l'héritage d'un pack pour lister son contenu (équipements + prestations)."""
    if _seen is None:
        _seen = []
    if pid in _seen or pid not in packs:
        return {"equipements": [], "prestations": []}
    p = packs[pid]
    comp = p.get("composition", {}) or {}
    eqs = list(comp.get("equipements", []))
    prs = list(comp.get("prestations", []))
    parent = p.get("extends")
    if parent:
        h = resoudre_pack_simple(parent, packs, _seen + [pid])
        eqs = h["equipements"] + eqs
        prs = h["prestations"] + prs
    return {"equipements": eqs, "prestations": prs}


# ----- Panier / demande de devis -----
# Articles qui peuvent recevoir l'option « impressions » (consommable ; l'imprimante
# est ajoutée à part par le panier). Se rattache par id d'article.
PRINT_OPTION_ITEMS = {"mobile-booth", "kids-booth"}


def _cart_button(item_type, item_id, nom, kind, prix=None, paliers=None, max_qty=1, unite="unité", impr=False):
    """Bouton « + Ajouter au devis » — les infos de tarif sont portées en data-*
    et lues côté client par le panier (aucune donnée serveur nécessaire)."""
    a = [
        f'data-id="{escape(str(item_id), quote=True)}"',
        f'data-type="{item_type}"',
        f'data-nom="{escape(nom or str(item_id), quote=True)}"',
        f'data-kind="{kind}"',
        f'data-max="{int(max_qty or 1)}"',
        f'data-unite="{escape(unite or "unité", quote=True)}"',
    ]
    if prix is not None:
        a.append(f'data-prix="{prix}"')
    if paliers:
        a.append("data-paliers='" + escape(json.dumps(paliers, ensure_ascii=False), quote=False) + "'")
    if impr:
        a.append('data-impr="1"')
    return '<button type="button" class="add-cart" ' + " ".join(a) + '>+ Ajouter au devis</button>'


def _equip_cart_button(eid, e):
    vente = e.get("vente", {}) or {}
    mode = vente.get("mode")
    unite = vente.get("unite_label", "unité")
    maxq = e.get("quantite_possedee", 1) or 1
    nom = e.get("nom", eid)
    impr = eid in PRINT_OPTION_ITEMS
    if mode == "tranches":
        return _cart_button("equip", eid, nom, "tranches", paliers=vente.get("paliers", []) or [], max_qty=maxq, unite=unite, impr=impr)
    if mode == "unitaire":
        return _cart_button("equip", eid, nom, "unitaire", prix=vente.get("prix_unitaire", 0) or 0, max_qty=maxq, unite=unite, impr=impr)
    pv = vente.get("prix_unitaire")
    if pv:
        return _cart_button("equip", eid, nom, "fixe", prix=pv, max_qty=1, unite=unite, impr=impr)
    return _cart_button("equip", eid, nom, "devis", max_qty=1, unite=unite, impr=impr)


# ----- Génération HTML -----
def render_pack_card(pid, pack, packs, equipements, prestations):
    nom = escape(pack.get("nom", pid))
    prix = euro(pack.get("prix_ttc", 0))
    desc = escape(pack.get("description", "") or "")
    duree = escape(pack.get("duree_estimee", "") or "")

    # Contenu résolu (héritage), groupé en une liste courte de noms
    compo = resoudre_pack_simple(pid, packs)
    items = []
    for l in compo["equipements"]:
        e = equipements.get(l["id"])
        if e:
            q = l.get("quantite", 1)
            items.append(f'{q}× {escape(e.get("nom", l["id"]))}')
    for l in compo["prestations"]:
        pr = prestations.get(l["id"])
        if pr:
            items.append(escape(pr.get("nom", l["id"])))
    contenu = "".join(f"<li>{it}</li>" for it in items)

    duree_html = f'<span class="card-meta">{duree}</span>' if duree else ""
    btn = _cart_button("pack", pid, pack.get("nom", pid), "fixe", prix=pack.get("prix_ttc", 0) or 0, max_qty=1)
    return f"""
        <article class="card pack-card">
            <div class="card-head">
                <h3>{nom}</h3>
                <div class="price">{prix}</div>
            </div>
            {duree_html}
            <p class="card-desc">{desc}</p>
            <details class="card-contenu">
                <summary>Voir le contenu</summary>
                <ul>{contenu}</ul>
            </details>
            {btn}
        </article>"""


def render_presta_card(pid, pr):
    nom = escape(pr.get("nom", pid))
    desc = escape(pr.get("description", "") or "")
    prix_v = pr.get("prix", 0)
    prefixe = "à partir de " if "a_partir_de" in (pr.get("tags") or []) else ""
    prix = (prefixe + euro(prix_v)) if prix_v else "Sur devis"
    if prix_v:
        btn = _cart_button("presta", pid, pr.get("nom", pid), "fixe", prix=prix_v, max_qty=1)
    else:
        btn = _cart_button("presta", pid, pr.get("nom", pid), "devis", max_qty=1)
    return f"""
        <article class="card presta-card">
            <div class="card-head">
                <h3>{nom}</h3>
                <div class="price">{prix}</div>
            </div>
            <p class="card-desc">{desc}</p>
            {btn}
        </article>"""


def render_equip_card(eid, e, photos_rel="photos"):
    nom = escape(e.get("nom", eid))
    marque = escape(e.get("marque", "") or "")
    desc = escape(e.get("description_courte", "") or "")
    prix_v, prefixe = prix_equipement(e)
    if prix_v:
        prix = f'{escape(prefixe)}{euro(prix_v)}'
    else:
        prix = "Sur devis"
    photo = e.get("photo")
    img = ""
    if photo:
        img = f'<div class="equip-photo"><img src="{photos_rel}/{escape(photo)}" alt="{nom}" loading="lazy"></div>'
    marque_html = f'<span class="equip-marque">{marque}</span>' if marque else ""
    btn = _equip_cart_button(eid, e)
    return f"""
        <article class="card equip-card">
            {img}
            <div class="equip-body">
                {marque_html}
                <h3>{nom}</h3>
                <p class="card-desc">{desc}</p>
                <div class="price">{prix} <span class="price-unit">/ location</span></div>
                {btn}
            </div>
        </article>"""


IA_PROMO_CARD = """
        <article class="card ia-promo">
            <a href="photobooth-ia.html">
                <div class="ia-badge">Nouveauté</div>
                <div class="card-head">
                    <h3>Option Photobooth <span style="color:var(--or-clair)">IA</span></h3>
                    <div class="price">à partir de 100 €</div>
                </div>
                <p class="card-desc">Chaque photo transformée par IA sur le thème de votre choix (foot, disco, cartoon, mariage…), avec votre marque intégrée.</p>
                <span class="ia-cta">Découvrir l'option IA →</span>
            </a>
        </article>"""

TEMPLATES_PROMO_CARD = """
        <article class="card ia-promo">
            <a href="templates-photobooth.html">
                <div class="ia-badge">850+ designs</div>
                <div class="card-head">
                    <h3>Templates <span style="color:var(--or-clair)">photobooth</span></h3>
                </div>
                <p class="card-desc">Parcourez notre bibliothèque de plus de 850 mises en page (mariage, anniversaire, fêtes…) pour personnaliser les impressions de vos invités.</p>
                <span class="ia-cta">Parcourir les templates →</span>
            </a>
        </article>"""

LUNETTES_PROMO_CARD = """
        <article class="card ia-promo">
            <a href="lunettes-3d.html">
                <div class="ia-badge">Sur-mesure</div>
                <div class="card-head">
                    <h3>Lunettes <span style="color:var(--or-clair)">3D</span></h3>
                    <div class="price">à partir de 50 €</div>
                </div>
                <p class="card-desc">Montures personnalisées imprimées en 3D à vos couleurs (prénoms, date, thème…). Un accessoire photobooth unique que vos invités gardent.</p>
                <span class="ia-cta">Voir les lunettes 3D →</span>
            </a>
        </article>"""

KIDS_BOOTH_PROMO_CARD = """
        <article class="card ia-promo">
            <div class="ia-badge">Spécial enfants</div>
            <div class="card-head">
                <h3>Kids <span style="color:var(--or-clair)">Booth</span></h3>
                <div class="price">100 €</div>
            </div>
            <p class="card-desc">Un photobooth pensé pour ravir les boutchous : hauteur adaptée, accessoires rigolos et souvenirs à emporter. Impressions en option.</p>
            <a class="ia-cta" href="kids-booth.html">Voir la galerie &rarr;</a>
            <button type="button" class="add-cart" data-id="kids-booth" data-type="pack" data-nom="Kids Booth" data-kind="fixe" data-max="1" data-unite="prestation" data-prix="100" data-impr="1">+ Ajouter au devis</button>
        </article>"""


def build_html(equipements, prestations, packs) -> str:
    """Assemble le HTML de la page catalogue à partir des dicts du catalogue.

    Fonction pure (aucune I/O disque) réutilisée par la CLI `generate()` ET par
    la publication vitrine côté serveur (web/vitrine_publisher.py), qui lit le
    catalogue depuis le storage (Dropbox) au lieu des fichiers locaux.
    """
    # --- Section PACKS, groupés par catégorie ---
    packs_html = ""
    for cat, label in PACK_CATEGORIES.items():
        cat_packs = [(pid, p) for pid, p in packs.items() if p.get("categorie") == cat]
        if not cat_packs:
            continue
        cat_packs.sort(key=lambda x: x[1].get("prix_ttc", 0))
        cards = "".join(render_pack_card(pid, p, packs, equipements, prestations)
                        for pid, p in cat_packs)
        if cat == "photobooth":
            cards += IA_PROMO_CARD + TEMPLATES_PROMO_CARD + LUNETTES_PROMO_CARD + KIDS_BOOTH_PROMO_CARD
        gid = ' id="photobooth"' if cat == "photobooth" else ''
        packs_html += f'<div class="cat-group"{gid}><h3 class="cat-title">{escape(label)}</h3><div class="card-grid">{cards}</div></div>'

    # --- Section PRESTATIONS (vitrine seulement), avec prix > 0 ou sur devis ---
    presta_html = ""
    for cat, label in PRESTA_CATEGORIES_VITRINE.items():
        cat_pr = [(pid, p) for pid, p in prestations.items()
                  if p.get("categorie") == cat and prestation_visible_catalogue(p)]
        if not cat_pr:
            continue
        cat_pr.sort(key=lambda x: (-(x[1].get("prix", 0) or 0), x[1].get("nom", "")))
        cards = "".join(render_presta_card(pid, p) for pid, p in cat_pr)
        gid = ' id="photo-video"' if cat == "captation" else ''
        presta_html += f'<div class="cat-group"{gid}><h3 class="cat-title">{escape(label)}</h3><div class="card-grid">{cards}</div></div>'

    # --- Section LOCATION (équipements), groupés par catégorie ---
    equip_html = ""
    for cat, label in EQUIP_CATEGORIES.items():
        cat_eq = [(eid, e) for eid, e in equipements.items()
                  if e.get("categorie") == cat and equipement_visible_catalogue(e)]
        if not cat_eq:
            continue
        cat_eq.sort(key=lambda x: x[1].get("nom", ""))
        cards = "".join(render_equip_card(eid, e) for eid, e in cat_eq)
        equip_html += f'<div class="cat-group"><h3 class="cat-title">{escape(label)}</h3><div class="card-grid equip-grid">{cards}</div></div>'

    maj = datetime.now().strftime("%d/%m/%Y")
    return HTML_TEMPLATE.format(
        packs=packs_html, prestations=presta_html, equipements=equip_html, maj=maj,
        cart_css=CART_CSS, cart_html=CART_HTML, cart_js=CART_JS,
    )


def generate(base: Path, out_path: Path):
    equipements, prestations, packs = load_catalogue(base)
    html = build_html(equipements, prestations, packs)

    out_path.write_text(html, encoding="utf-8")

    # Copier les photos pour rendre la page autonome
    photos_src = base / "photos"
    if photos_src.exists():
        photos_dst = out_path.parent / "photos"
        photos_dst.mkdir(exist_ok=True)
        for img in photos_src.iterdir():
            if img.is_file():
                shutil.copy2(img, photos_dst / img.name)

    print(f"✅ Page générée : {out_path}")
    print(f"   {len(packs)} packs · {len(prestations)} prestations · {len(equipements)} équipements")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Catalogue — Alexis Événementiel</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Jost:wght@300;400;500&display=swap" rel="stylesheet">
<style>
    :root {{
        --noir: #0a0a0c; --noir-2: #121116; --noir-3: #1a1820;
        --or: #c9a55c; --or-clair: #e6c986; --or-sombre: #8a7138;
        --creme: #f4efe6; --gris: #8b8794; --gris-clair: #b8b4bf;
        --line: rgba(201,165,92,0.18);
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
        font-family: 'Jost', sans-serif; background: var(--noir); color: var(--creme);
        line-height: 1.7; font-weight: 300; -webkit-font-smoothing: antialiased;
    }}
    h1, h2, h3 {{ font-family: 'Cormorant Garamond', serif; font-weight: 500; }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 0 32px; }}

    nav {{
        position: fixed; top: 0; left: 0; right: 0; z-index: 100; padding: 20px 0;
        background: rgba(10,10,12,0.85); backdrop-filter: blur(16px);
        border-bottom: 1px solid var(--line);
    }}
    nav .wrap {{ display: flex; align-items: center; justify-content: space-between; }}
    .logo {{ font-family: 'Cormorant Garamond', serif; font-size: 1.5rem; font-weight: 600; color: var(--creme); text-decoration: none; }}
    .logo span {{ color: var(--or); }}
    .nav-links {{ display: flex; gap: 32px; align-items: center; }}
    .nav-links a {{ color: var(--gris-clair); text-decoration: none; font-size: 0.8rem; letter-spacing: 0.14em; text-transform: uppercase; transition: color 0.3s; }}
    .nav-links a:hover {{ color: var(--or-clair); }}

    header.hero {{
        padding: 160px 0 80px; text-align: center; position: relative; overflow: hidden;
        background:
            radial-gradient(ellipse 70% 60% at 50% 0%, rgba(201,165,92,0.14), transparent 60%),
            linear-gradient(180deg, var(--noir) 0%, var(--noir-2) 100%);
    }}
    .hero .eyebrow {{ font-size: 0.8rem; letter-spacing: 0.4em; text-transform: uppercase; color: var(--or); margin-bottom: 20px; }}
    .hero h1 {{ font-size: clamp(2.6rem, 6vw, 4.5rem); line-height: 1.02; margin-bottom: 22px; }}
    .hero h1 .italic {{ font-style: italic; color: var(--or-clair); }}
    .hero p {{ color: var(--gris-clair); max-width: 560px; margin: 0 auto; font-size: 1.08rem; }}

    nav.sticky-sub {{ position: sticky; top: 61px; z-index: 50; background: rgba(18,17,22,0.92); backdrop-filter: blur(10px); border-bottom: 1px solid var(--line); padding: 14px 0; }}
    nav.sticky-sub .wrap {{ display: flex; gap: 30px; justify-content: center; flex-wrap: wrap; }}
    nav.sticky-sub a {{ color: var(--gris-clair); text-decoration: none; font-size: 0.82rem; letter-spacing: 0.12em; text-transform: uppercase; transition: color 0.3s; }}
    nav.sticky-sub a:hover {{ color: var(--or-clair); }}

    section {{ padding: 90px 0; }}
    section:nth-of-type(even) {{ background: var(--noir-2); }}
    .section-head {{ text-align: center; margin-bottom: 56px; }}
    .section-head .num {{ font-family: 'Cormorant Garamond', serif; font-size: 0.9rem; color: var(--or); letter-spacing: 0.3em; font-style: italic; }}
    .section-head h2 {{ font-size: clamp(2rem, 4vw, 3rem); margin-top: 8px; }}
    .section-head h2 .italic {{ font-style: italic; color: var(--or-clair); }}
    .section-head p {{ color: var(--gris-clair); margin-top: 12px; max-width: 520px; margin-left: auto; margin-right: auto; }}

    .cat-group {{ margin-bottom: 50px; scroll-margin-top: 120px; }}
    .cat-title {{ font-family: 'Cormorant Garamond', serif; font-size: 1.5rem; color: var(--or-clair); margin-bottom: 22px; padding-bottom: 10px; border-bottom: 1px solid var(--line); }}

    .card-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 18px; }}
    .equip-grid {{ grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }}

    .card {{ background: var(--noir-3); border: 1px solid var(--line); border-radius: 6px; padding: 26px; transition: transform 0.3s ease, border-color 0.3s ease; }}
    .card:hover {{ transform: translateY(-4px); border-color: var(--or-sombre); }}
    .card-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }}
    .card h3 {{ font-size: 1.35rem; }}
    .price {{ font-family: 'Cormorant Garamond', serif; font-weight: 600; color: var(--or-clair); font-size: 1.3rem; white-space: nowrap; }}
    .price-unit {{ font-size: 0.7rem; color: var(--gris); font-weight: 400; font-family: 'Jost', sans-serif; }}
    .card-meta {{ font-size: 0.82rem; color: var(--or); letter-spacing: 0.08em; }}
    .card-desc {{ color: var(--gris-clair); font-size: 0.92rem; margin-top: 10px; }}

    .card-contenu {{ margin-top: 16px; }}
    .card-contenu summary {{ cursor: pointer; font-size: 0.8rem; color: var(--or); letter-spacing: 0.08em; text-transform: uppercase; list-style: none; }}
    .card-contenu summary::-webkit-details-marker {{ display: none; }}
    .card-contenu summary::before {{ content: "＋ "; }}
    .card-contenu[open] summary::before {{ content: "− "; }}
    .card-contenu ul {{ margin-top: 12px; padding-left: 18px; }}
    .card-contenu li {{ font-size: 0.85rem; color: var(--gris-clair); margin-bottom: 5px; }}

    .equip-card {{ padding: 0; overflow: hidden; display: flex; flex-direction: column; }}
    .equip-photo {{ aspect-ratio: 4/3; background: #fff; overflow: hidden; display: flex; align-items: center; justify-content: center; }}
    .equip-photo img {{ width: 100%; height: 100%; object-fit: contain; padding: 14px; }}
    .equip-body {{ padding: 20px; flex: 1; display: flex; flex-direction: column; }}
    .equip-marque {{ font-size: 0.7rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--or); font-weight: 500; }}
    .equip-body h3 {{ font-size: 1.15rem; margin: 5px 0 0; }}
    .equip-body .price {{ margin-top: auto; padding-top: 14px; font-size: 1.15rem; }}

    .ia-promo {{ position: relative; border-color: var(--or-sombre); }}
    .ia-promo a {{ text-decoration: none; color: inherit; display: block; }}
    .ia-promo:hover {{ border-color: var(--or); box-shadow: 0 12px 30px rgba(201,165,92,0.15); }}
    .ia-badge {{ position: absolute; top: 16px; right: 16px; font-size: 0.62rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--noir); background: var(--or); padding: 3px 10px; border-radius: 99px; }}
    .ia-cta {{ display: inline-block; margin-top: 16px; color: var(--or-clair); font-size: 0.82rem; letter-spacing: 0.08em; text-transform: uppercase; transition: color .3s; }}
    .ia-promo:hover .ia-cta {{ color: var(--or); }}

    footer {{ background: var(--noir); border-top: 1px solid var(--line); padding: 60px 0 36px; text-align: center; }}
    footer .brand {{ font-family: 'Cormorant Garamond', serif; font-size: 1.5rem; color: var(--creme); margin-bottom: 10px; }}
    footer .brand span {{ color: var(--or); }}
    footer p {{ color: var(--gris); font-size: 0.9rem; margin-bottom: 6px; }}
    footer a {{ color: var(--or-clair); text-decoration: none; }}
    footer .maj {{ margin-top: 18px; font-size: 0.76rem; color: var(--gris); }}

    @media (max-width: 700px) {{
        .nav-links {{ display: none; }}
        section {{ padding: 60px 0; }}
        .equip-grid {{ grid-template-columns: 1fr; }}
    }}
{cart_css}
</style>
</head>
<body>

<nav>
    <div class="wrap">
        <a href="index.html" class="logo">Alexis <span>Événementiel</span></a>
        <div class="nav-links">
            <a href="index.html#prestations">Prestations</a>
            <a href="catalogue.html">Catalogue</a>
            <a href="index.html#realisations">Réalisations</a>
            <a href="index.html#contact">Contact</a>
        </div>
    </div>
</nav>

<header class="hero">
    <div class="wrap">
        <div class="eyebrow">Packs · Prestations · Location</div>
        <h1>Le <span class="italic">catalogue</span></h1>
        <p>Formules clés en main, prestations à la carte et location de matériel professionnel.</p>
    </div>
</header>

<nav class="sticky-sub">
    <div class="wrap">
        <a href="#packs">Nos formules</a>
        <a href="#prestations">Prestations</a>
        <a href="#location">Location</a>
    </div>
</nav>

<section id="packs">
    <div class="wrap">
        <div class="section-head">
            <div class="num">01</div>
            <h2>Nos <span class="italic">formules</span></h2>
            <p>Des packs clés en main, du cocktail à la soirée complète.</p>
        </div>
        {packs}
    </div>
</section>

<section id="prestations">
    <div class="wrap">
        <div class="section-head">
            <div class="num">02</div>
            <h2>Prestations</h2>
            <p>À la carte, pour composer votre événement sur-mesure.</p>
        </div>
        {prestations}
    </div>
</section>

<section id="location">
    <div class="wrap">
        <div class="section-head">
            <div class="num">03</div>
            <h2>Location de <span class="italic">matériel</span></h2>
            <p>Notre parc son, lumière et vidéo, à louer pour vos propres événements. Tarif à la journée ou au week-end selon le matériel — contactez-nous.</p>
        </div>
        {equipements}
    </div>
</section>

<footer>
    <div class="wrap">
        <div class="brand">Alexis<span>.</span> Événementiel</div>
        <p>Albi & Tarn (81) — déplacements jusqu'à 200 km</p>
        <p><a href="tel:0618855892">06 18 85 58 92</a> · <a href="mailto:contact@alexisevenementiel.fr">contact@alexisevenementiel.fr</a></p>
        <p class="maj">Catalogue mis à jour le {maj} · TVA non applicable, art. 293 B du CGI</p>
        <p class="visit-counter" style="margin-top:10px; font-size:0.76rem; color:var(--gris); letter-spacing:0.05em;"><span id="vc-val">…</span> visites depuis juin 2026</p>
        <script>
        (function(){{
            fetch('https://api.counterapi.dev/v1/alexis-evenementiel/visites-site/up')
                .then(function(r){{ return r.json(); }})
                .then(function(d){{ var el = document.getElementById('vc-val'); if (el && d && typeof d.count === 'number') {{ el.textContent = d.count.toLocaleString('fr-FR'); }} }})
                .catch(function(){{ var p = document.querySelector('.visit-counter'); if (p) {{ p.style.display = 'none'; }} }});
        }})();
        </script>
    </div>
</footer>

{cart_html}
<script>
{cart_js}
</script>

</body>
</html>"""


# ── Panier / demande de devis (blocs injectés tels quels via .format) ─────────
CART_CSS = """
    .add-cart{ margin-top:16px; width:100%; background:transparent; color:var(--or-clair);
        border:1px solid var(--or-sombre); border-radius:4px; padding:10px 14px; font-family:'Jost',sans-serif;
        font-size:0.78rem; letter-spacing:0.1em; text-transform:uppercase; cursor:pointer; transition:all .25s; }
    .add-cart:hover{ background:var(--or); color:var(--noir); border-color:var(--or); }
    .add-cart.added{ background:var(--or-sombre); color:var(--creme); border-color:var(--or-sombre); }
    .equip-card .add-cart{ margin:auto 20px 20px; width:calc(100% - 40px); }
    #cart-fab{ position:fixed; bottom:24px; right:24px; z-index:200; background:var(--or); color:var(--noir);
        border:none; border-radius:50px; padding:14px 22px; font-family:'Jost',sans-serif; font-size:0.85rem;
        font-weight:500; letter-spacing:0.06em; cursor:pointer; box-shadow:0 8px 30px rgba(0,0,0,.45);
        display:flex; align-items:center; gap:8px; }
    #cart-fab .count{ background:var(--noir); color:var(--or-clair); border-radius:50px; min-width:22px; height:22px;
        display:inline-flex; align-items:center; justify-content:center; font-size:0.78rem; padding:0 6px; }
    #cart-fab .count.hide{ display:none; }
    #cart-overlay{ position:fixed; inset:0; background:rgba(0,0,0,.6); z-index:300; opacity:0; pointer-events:none; transition:opacity .3s; }
    #cart-overlay.open{ opacity:1; pointer-events:auto; }
    #cart-panel{ position:fixed; top:0; right:0; bottom:0; width:min(440px,100%); background:var(--noir-2);
        border-left:1px solid var(--line); z-index:301; transform:translateX(100%); transition:transform .3s ease;
        display:flex; flex-direction:column; }
    #cart-panel.open{ transform:translateX(0); }
    #cart-panel .ch{ padding:20px 24px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; align-items:center; }
    #cart-panel .ch h3{ font-size:1.45rem; color:var(--creme); }
    #cart-panel .ch button{ background:none; border:none; color:var(--gris-clair); font-size:1.7rem; cursor:pointer; line-height:1; }
    #cart-form{ display:flex; flex-direction:column; flex:1; min-height:0; }
    #cart-scroll{ flex:1; overflow-y:auto; padding:6px 24px 12px; }
    .brief-grp{ margin-bottom:4px; }
    .brief-lbl{ font-size:0.72rem; letter-spacing:0.14em; text-transform:uppercase; color:var(--or);
        margin:16px 0 11px; padding-top:13px; border-top:1px solid var(--line); }
    .brief-grp:first-child .brief-lbl{ border-top:none; padding-top:2px; margin-top:2px; }
    .brief-lbl span{ color:var(--gris); text-transform:none; letter-spacing:0.01em; font-size:0.82em; font-style:italic; }
    .cart-empty{ color:var(--gris); text-align:center; padding:26px 10px; font-size:0.88rem; line-height:1.6; }
    .ci{ padding:12px 0; border-bottom:1px solid var(--line); }
    .ci-nom{ font-size:0.95rem; color:var(--creme); }
    .ci-line{ font-size:0.8rem; color:var(--or-clair); margin-top:2px; }
    .ci-ctrl{ display:flex; align-items:center; gap:8px; margin-top:8px; }
    .ci-ctrl button{ width:26px; height:26px; border:1px solid var(--line); background:transparent; color:var(--creme); border-radius:4px; cursor:pointer; font-size:1rem; }
    .ci-qty{ min-width:22px; text-align:center; font-size:0.85rem; }
    .ci-del{ background:none; border:none; color:var(--gris); cursor:pointer; font-size:0.76rem; text-decoration:underline; margin-top:8px; display:inline-block; }
    .ci-opt{ display:flex; align-items:center; gap:8px; margin-top:8px; }
    .ci-opt > span{ font-size:0.64rem; color:var(--gris); letter-spacing:0.06em; text-transform:uppercase; white-space:nowrap; }
    .ci-opt select{ margin:0 !important; flex:1; padding:7px 10px; font-size:0.8rem; }
    .ci.ci-auto{ opacity:0.92; }
    .ci-note{ font-size:0.72rem; color:var(--gris); font-style:italic; margin-top:2px; }
    .ci-note b{ color:var(--or-clair); font-style:normal; }
    .cart-total{ display:flex; justify-content:space-between; font-size:1.02rem; color:var(--creme); margin:14px 0 4px; }
    .cart-total b{ font-family:'Cormorant Garamond',serif; color:var(--or-clair); font-size:1.3rem; }
    .cart-note{ font-size:0.72rem; color:var(--gris); }
    #cart-scroll input, #cart-scroll select, #cart-scroll textarea{ width:100%; background:var(--noir-3);
        border:1px solid var(--line); border-radius:4px; padding:10px 12px; color:var(--creme);
        font-family:'Jost',sans-serif; font-size:0.85rem; margin-bottom:8px; }
    #cart-scroll input[type=checkbox], #cart-scroll input[type=radio]{ width:auto; margin:0; }
    .row2{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .fld{ display:flex; flex-direction:column; gap:3px; }
    .fld > span{ font-size:0.66rem; color:var(--gris); letter-spacing:0.05em; text-transform:uppercase; }
    .sub-q{ font-size:0.83rem; color:var(--gris-clair); margin:6px 0 8px; }
    .opt-row{ display:flex; flex-wrap:wrap; gap:8px 16px; margin-bottom:6px; }
    .chk{ display:inline-flex; align-items:center; gap:6px; font-size:0.83rem; color:var(--gris-clair); cursor:pointer; }
    #cart-foot{ border-top:1px solid var(--line); padding:14px 24px 20px; }
    #cart-foot button[type=submit]{ background:var(--or); color:var(--noir); border:none; border-radius:4px; width:100%; padding:14px;
        font-family:'Jost',sans-serif; font-size:0.82rem; letter-spacing:0.1em; text-transform:uppercase; cursor:pointer; font-weight:500; }
    #cart-msg{ font-size:0.85rem; text-align:center; padding:8px 0 0; }
"""

CART_HTML = """
<button id="cart-fab" onclick="AECart.open()" aria-label="Demander un devis">
  &#128722; Demander un devis <span class="count hide" id="cart-count">0</span>
</button>
<div id="cart-overlay" onclick="AECart.close()"></div>
<aside id="cart-panel" aria-label="Demande de devis">
  <div class="ch"><h3>Ma demande de devis</h3><button type="button" onclick="AECart.close()" aria-label="Fermer">&times;</button></div>
  <form id="cart-form" onsubmit="return AECart.submit(event)">
    <div id="cart-scroll">

      <div class="brief-grp">
        <div class="brief-lbl">Ma sélection</div>
        <div id="cart-items"></div>
        <div class="cart-total"><span>Estimation à la carte</span><b id="cart-subtotal">0 &euro;</b></div>
        <div class="cart-note">Montant indicatif — vous recevrez un <strong>prix pack personnalisé</strong> adapté à votre événement.</div>
      </div>

      <div class="brief-grp">
        <div class="brief-lbl">Votre événement <span>— quelques infos, on affine ensemble</span></div>
        <select name="occasion">
          <option value="">Type d'occasion (facultatif)…</option>
          <option>Mariage</option><option>Anniversaire</option><option>Soirée d'entreprise</option>
          <option>Association / comité des fêtes</option><option>Bar / restaurant</option><option>Autre</option>
        </select>
        <div class="row2">
          <label class="fld"><span>Date (si connue)</span><input name="date" type="date"></label>
          <label class="fld"><span>Nombre de personnes</span>
            <select name="pers"><option value="">—</option><option>Moins de 50</option><option>50 à 100</option><option>100 à 200</option><option>200 à 300</option><option>Plus de 300</option></select>
          </label>
        </div>
        <div class="row2">
          <label class="fld"><span>Début (approx.)</span><input name="debut" type="time"></label>
          <label class="fld"><span>Fin (approx.)</span><input name="fin" type="time"></label>
        </div>
        <input name="lieu" placeholder="Lieu / ville de l'événement">
      </div>

      <div class="brief-grp">
        <div class="brief-lbl">Vos besoins</div>
        <div class="sub-q">Quelles prestations vous intéressent ?</div>
        <div class="opt-row">
          <label class="chk"><input type="checkbox" name="presta" value="DJ / Animateur"> DJ / Animateur</label>
          <label class="chk"><input type="checkbox" name="presta" value="Photographe"> Photographe</label>
          <label class="chk"><input type="checkbox" name="presta" value="Photobooth"> Photobooth</label>
          <label class="chk"><input type="checkbox" name="presta" value="Sonorisation"> Sonorisation</label>
          <label class="chk"><input type="checkbox" name="presta" value="Éclairage"> Éclairage</label>
          <label class="chk"><input type="checkbox" name="presta" value="Autre"> Autre</label>
        </div>
        <div class="sub-q">Sonorisation déjà sur place&nbsp;?</div>
        <div class="opt-row">
          <label class="chk"><input type="radio" name="son" value="Oui, déjà fournie"> Oui, déjà là</label>
          <label class="chk"><input type="radio" name="son" value="Non, à prévoir"> Non, à prévoir</label>
        </div>
        <div class="sub-q">Éclairage déjà sur place&nbsp;?</div>
        <div class="opt-row">
          <label class="chk"><input type="radio" name="eclairage" value="Oui, déjà fourni"> Oui, déjà là</label>
          <label class="chk"><input type="radio" name="eclairage" value="Non, à prévoir"> Non, à prévoir</label>
        </div>
      </div>

      <div class="brief-grp">
        <div class="brief-lbl">Vos coordonnées</div>
        <div class="row2"><input name="prenom" placeholder="Prénom *" required><input name="nom" placeholder="Nom"></div>
        <div class="row2"><input name="email" type="email" placeholder="Email *" required><input name="tel" placeholder="Téléphone"></div>
        <textarea name="message" rows="2" placeholder="Un mot sur votre projet (optionnel)"></textarea>
      </div>

    </div>
    <div id="cart-foot">
      <button type="submit">Envoyer ma demande de devis</button>
      <div id="cart-msg"></div>
    </div>
  </form>
</aside>
"""

CART_JS = """
(function(){
  var KEY='ae_cart_v1';
  var FORMSPREE_ENDPOINT='';                     // <-- à remplir : "https://formspree.io/f/XXXXXXXX" (sinon repli mailto)
  var CONTACT='contact@alexisevenementiel.fr';
  // Option « impressions » (consommable seul) — l'imprimante est ajoutée à part, une fois.
  var IMPR=[{v:'',lbl:'Sans impression',prix:0},{v:'100',lbl:'100 impressions',prix:50},{v:'200',lbl:'200 impressions',prix:100},{v:'400',lbl:'400 impressions',prix:150}];
  var PRINTER_ID='imprimante-dnp', PRINTER_NOM='Imprimante DNP DS620', PRINTER_PRIX=70;
  function imprPrix(v){ for(var i=0;i<IMPR.length;i++){ if(IMPR[i].v===v) return IMPR[i].prix; } return 0; }
  function imprLbl(v){ for(var i=0;i<IMPR.length;i++){ if(IMPR[i].v===v) return IMPR[i].lbl; } return ''; }
  function anyImpr(){ for(var i=0;i<cart.length;i++){ if(cart[i].hasImpr && cart[i].impr) return true; } return false; }
  function hasPrinter(){ for(var i=0;i<cart.length;i++){ if(cart[i].id===PRINTER_ID) return true; } return false; }
  function printerAuto(){ return anyImpr() && !hasPrinter(); }
  var cart=[]; try{ cart=JSON.parse(localStorage.getItem(KEY))||[]; }catch(e){ cart=[]; }
  function save(){ try{ localStorage.setItem(KEY, JSON.stringify(cart)); }catch(e){} }
  function fmt(n){ n=Math.round(n*100)/100; return (n%1===0? n.toFixed(0): n.toFixed(2).replace('.',',')) + ' \\u20ac'; }
  function esc(s){ return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
  function palierPrice(p, q){ if(!p||!p.length) return 0; var b=null;
    for(var i=0;i<p.length;i++){ if(p[i].qte<=q && (b===null||p[i].qte>b.qte)) b=p[i]; }
    if(!b){ b=p[0]; for(var j=0;j<p.length;j++){ if(p[j].qte<b.qte) b=p[j]; } }
    return b.prix_forfait||0; }
  function lineTotal(it){ if(it.kind==='devis') return null;
    var base = (it.kind==='tranches') ? palierPrice(it.paliers, it.qty)
             : (it.kind==='unitaire') ? (it.prix||0)*it.qty
             : (it.prix||0);
    if(it.hasImpr && it.impr) base += imprPrix(it.impr);
    return base; }
  function count(){ var c=0; cart.forEach(function(it){ c+=it.qty; }); return c; }
  function find(k){ for(var i=0;i<cart.length;i++){ if(cart[i].key===k) return cart[i]; } return null; }
  function add(btn){ var d=btn.dataset, key=d.type+':'+d.id, it=find(key), max=parseInt(d.max)||1;
    if(it){ if(it.qty<max) it.qty++; }
    else{ var pal=null; if(d.paliers){ try{ pal=JSON.parse(d.paliers); }catch(e){} }
      cart.push({key:key,type:d.type,id:d.id,nom:d.nom,kind:d.kind,prix:parseFloat(d.prix)||0,paliers:pal,max:max,unite:d.unite||'unité',qty:1,hasImpr:(d.impr==='1'),impr:''}); }
    save(); render(); pulse(btn); }
  function pulse(btn){ btn.classList.add('added'); var t=btn.textContent; btn.textContent='\\u2713 Ajouté';
    setTimeout(function(){ btn.classList.remove('added'); btn.textContent='+ Ajouter au devis'; }, 1100); }
  function q(k,d){ var it=find(k); if(!it) return; it.qty+=d; if(it.qty<1) it.qty=1; if(it.qty>it.max) it.qty=it.max; save(); render(); }
  function del(k){ cart=cart.filter(function(it){ return it.key!==k; }); save(); render(); }
  function setImpr(k,v){ var it=find(k); if(it){ it.impr=v; save(); render(); } }
  function render(){ var w=document.getElementById('cart-items'); if(!w) return;
    var badge=document.getElementById('cart-count'); if(badge){ badge.textContent=count(); badge.classList.toggle('hide', count()===0); }
    if(cart.length===0){ w.innerHTML='<div class=\"cart-empty\">Aucun matériel ajouté pour l\\'instant.<br>Ajoutez des packs, prestations ou du matériel — ou décrivez simplement votre besoin ci-dessous.</div>';
      var st=document.getElementById('cart-subtotal'); if(st) st.textContent='0 \\u20ac'; return; }
    var html='', sub=0;
    cart.forEach(function(it){ var lt=lineTotal(it), ctrl='', opt='';
      if(it.kind==='tranches'||it.kind==='unitaire'){ ctrl='<div class=\"ci-ctrl\"><button onclick=\"AECart.q(\\''+it.key+'\\',-1)\">\\u2212</button><span class=\"ci-qty\">'+it.qty+'</span><button onclick=\"AECart.q(\\''+it.key+'\\',1)\">+</button></div>'; }
      if(it.hasImpr){ opt='<div class=\"ci-opt\"><span>Impressions</span><select onchange=\"AECart.setImpr(\\''+it.key+'\\',this.value)\">';
        for(var k=0;k<IMPR.length;k++){ var o=IMPR[k]; opt+='<option value=\"'+o.v+'\"'+(o.v===it.impr?' selected':'')+'>'+esc(o.lbl)+(o.prix?(' (+'+o.prix+' \\u20ac)'):'')+'</option>'; }
        opt+='</select></div>'; }
      var txt=(lt===null)?'Sur devis':fmt(lt)+((it.qty>1&&it.kind==='unitaire')?' ('+it.qty+'\\u00d7)':''); if(lt!==null) sub+=lt;
      html+='<div class=\"ci\"><div class=\"ci-nom\">'+esc(it.nom)+'</div><div class=\"ci-line\">'+txt+'</div>'+opt+ctrl+'<button class=\"ci-del\" onclick=\"AECart.del(\\''+it.key+'\\')\">Retirer</button></div>'; });
    if(printerAuto()){ sub+=PRINTER_PRIX;
      html+='<div class=\"ci ci-auto\"><div class=\"ci-nom\">'+esc(PRINTER_NOM)+'</div><div class=\"ci-line\">'+fmt(PRINTER_PRIX)+'</div><div class=\"ci-note\">Ajout\\u00e9e automatiquement \\u2014 <b>requise pour les impressions</b></div></div>'; }
    w.innerHTML=html; document.getElementById('cart-subtotal').textContent=fmt(sub); }
  function open(){ document.getElementById('cart-overlay').classList.add('open'); document.getElementById('cart-panel').classList.add('open'); render(); }
  function close(){ document.getElementById('cart-overlay').classList.remove('open'); document.getElementById('cart-panel').classList.remove('open'); }
  function cartLines(){ if(cart.length===0) return '(aucun matériel sélectionné — à définir ensemble)';
    var l=[], sub=0; cart.forEach(function(it){ var lt=lineTotal(it), p=(lt===null)?'sur devis':fmt(lt); if(lt!==null) sub+=lt;
      var nom=it.nom; if(it.hasImpr&&it.impr) nom+=' + '+imprLbl(it.impr); l.push('- '+nom+' x'+it.qty+' : '+p); });
    if(printerAuto()){ sub+=PRINTER_PRIX; l.push('- '+PRINTER_NOM+' (requise pour les impressions) x1 : '+fmt(PRINTER_PRIX)); }
    l.push('Estimation à la carte : '+fmt(sub)+' (prix pack à définir)'); return l.join('\\n'); }
  function briefText(d){ var L=[];
    L.push('=== ÉVÉNEMENT ===');
    if(d.occasion) L.push('Occasion : '+d.occasion);
    if(d.date) L.push('Date : '+d.date);
    if(d.debut||d.fin) L.push('Horaires : '+(d.debut||'?')+' \\u2192 '+(d.fin||'?'));
    if(d.lieu) L.push('Lieu : '+d.lieu);
    if(d.pers) L.push('Nombre de personnes : '+d.pers);
    L.push(''); L.push('=== BESOINS ===');
    L.push('Prestations souhaitées : '+(d.prestations.length?d.prestations.join(', '):'à définir'));
    if(d.son) L.push('Sonorisation sur place : '+d.son);
    if(d.eclairage) L.push('Éclairage sur place : '+d.eclairage);
    L.push(''); L.push('=== SÉLECTION ==='); L.push(cartLines());
    return L.join('\\n'); }
  function msg(t,err){ var m=document.getElementById('cart-msg'); if(m){ m.textContent=t; m.style.color=err?'#e88':'var(--or-clair)'; } }
  function submit(ev){ ev.preventDefault();
    var f=ev.target;
    var g=function(n){ var el=f.querySelector('[name=\"'+n+'\"]'); return el?(''+el.value).trim():''; };
    var checks=function(n){ var out=[], els=f.querySelectorAll('[name=\"'+n+'\"]:checked'); for(var i=0;i<els.length;i++) out.push(els[i].value); return out; };
    var rad=function(n){ var el=f.querySelector('[name=\"'+n+'\"]:checked'); return el?el.value:''; };
    var d={ occasion:g('occasion'), date:g('date'), debut:g('debut'), fin:g('fin'), lieu:g('lieu'), pers:g('pers'),
      prestations:checks('presta'), son:rad('son'), eclairage:rad('eclairage'),
      prenom:g('prenom'), nom:g('nom'), email:g('email'), tel:g('tel'), message:g('message') };
    var brief=briefText(d);
    var b=f.querySelector('button[type=submit]'); b.disabled=true; b.textContent='Envoi…';
    var done=function(ok){ b.disabled=false; b.textContent='Envoyer ma demande de devis';
      if(ok){ cart=[]; save(); render(); f.reset(); msg('Demande envoyée. Nous revenons vers vous avec une proposition de prix pack.', false); }
      else{ msg('Échec de l\\'envoi. Réessayez ou écrivez à '+CONTACT, true); } };
    if(FORMSPREE_ENDPOINT){
      var payload=Object.assign({}, d, {prestations:d.prestations.join(', '), selection:cartLines(), brief:brief, _subject:'Demande de devis — '+d.prenom+' '+d.nom});
      fetch(FORMSPREE_ENDPOINT,{method:'POST',headers:{'Accept':'application/json','Content-Type':'application/json'}, body:JSON.stringify(payload)})
        .then(function(r){ done(r.ok); }).catch(function(){ done(false); });
    } else {
      var body='Bonjour,\\n\\nVoici ma demande de devis :\\n\\n'+brief+'\\n\\n=== CONTACT ===\\n'+d.prenom+' '+d.nom+'\\nEmail : '+d.email+'\\nTéléphone : '+d.tel+(d.message?('\\nMessage : '+d.message):'')+'\\n';
      window.location.href='mailto:'+CONTACT+'?subject='+encodeURIComponent('Demande de devis — '+d.prenom+' '+d.nom)+'&body='+encodeURIComponent(body);
      setTimeout(function(){ done(true); }, 500);
    }
    return false; }
  document.addEventListener('click', function(e){ var b=e.target.closest?e.target.closest('.add-cart'):null; if(b) add(b); });
  window.AECart={ open:open, close:close, q:q, del:del, submit:submit, setImpr:setImpr };
  function maybeAutoOpen(){ var h=(location.hash||'').toLowerCase(); if(h.indexOf('devis')>=0||h.indexOf('demande')>=0) open(); }
  window.addEventListener('hashchange', maybeAutoOpen);
  function init(){ render(); maybeAutoOpen(); }
  if(document.readyState!=='loading') init(); else document.addEventListener('DOMContentLoaded', init);
})();
"""


if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("catalogue.html")
    generate(base, out)
