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
        </article>"""


def render_presta_card(pid, pr):
    nom = escape(pr.get("nom", pid))
    desc = escape(pr.get("description", "") or "")
    prix_v = pr.get("prix", 0)
    prix = euro(prix_v) if prix_v else "Sur devis"
    return f"""
        <article class="card presta-card">
            <div class="card-head">
                <h3>{nom}</h3>
                <div class="price">{prix}</div>
            </div>
            <p class="card-desc">{desc}</p>
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
    return f"""
        <article class="card equip-card">
            {img}
            <div class="equip-body">
                {marque_html}
                <h3>{nom}</h3>
                <p class="card-desc">{desc}</p>
                <div class="price">{prix} <span class="price-unit">/ location</span></div>
            </div>
        </article>"""


def generate(base: Path, out_path: Path):
    equipements, prestations, packs = load_catalogue(base)

    # --- Section PACKS, groupés par catégorie ---
    packs_html = ""
    for cat, label in PACK_CATEGORIES.items():
        cat_packs = [(pid, p) for pid, p in packs.items() if p.get("categorie") == cat]
        if not cat_packs:
            continue
        cat_packs.sort(key=lambda x: x[1].get("prix_ttc", 0))
        cards = "".join(render_pack_card(pid, p, packs, equipements, prestations)
                        for pid, p in cat_packs)
        packs_html += f'<div class="cat-group"><h3 class="cat-title">{escape(label)}</h3><div class="card-grid">{cards}</div></div>'

    # --- Section PRESTATIONS (vitrine seulement), avec prix > 0 ou sur devis ---
    presta_html = ""
    for cat, label in PRESTA_CATEGORIES_VITRINE.items():
        cat_pr = [(pid, p) for pid, p in prestations.items()
                  if p.get("categorie") == cat and prestation_visible_catalogue(p)]
        if not cat_pr:
            continue
        cat_pr.sort(key=lambda x: (-(x[1].get("prix", 0) or 0), x[1].get("nom", "")))
        cards = "".join(render_presta_card(pid, p) for pid, p in cat_pr)
        presta_html += f'<div class="cat-group"><h3 class="cat-title">{escape(label)}</h3><div class="card-grid">{cards}</div></div>'

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
    html = HTML_TEMPLATE.format(
        packs=packs_html, prestations=presta_html, equipements=equip_html, maj=maj
    )

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

    .cat-group {{ margin-bottom: 50px; }}
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
    </div>
</footer>

</body>
</html>"""


if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("catalogue.html")
    generate(base, out)
