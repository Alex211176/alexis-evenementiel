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
                  if p.get("categorie") == cat]
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
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Outfit:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
    :root {{
        --ink: #1a1410;
        --ink-soft: #5a4f47;
        --paper: #faf6f0;
        --paper-2: #f3ece2;
        --accent: #c2410c;
        --accent-soft: #fdebd9;
        --gold: #b8893a;
        --line: #e4d9ca;
        --shadow: 0 2px 20px rgba(40,25,10,0.06);
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: 'Outfit', sans-serif;
        background: var(--paper);
        color: var(--ink);
        line-height: 1.6;
        -webkit-font-smoothing: antialiased;
    }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 0 24px; }}

    /* Hero */
    header.hero {{
        background: linear-gradient(135deg, #1a1410 0%, #2d2018 55%, #3d2a18 100%);
        color: var(--paper);
        padding: 90px 0 80px;
        text-align: center;
        position: relative;
        overflow: hidden;
    }}
    header.hero::before {{
        content: "";
        position: absolute; inset: 0;
        background: radial-gradient(circle at 20% 30%, rgba(194,65,12,0.25), transparent 45%),
                    radial-gradient(circle at 80% 70%, rgba(184,137,58,0.18), transparent 40%);
    }}
    .hero-content {{ position: relative; z-index: 1; }}
    .hero .eyebrow {{
        font-size: 13px; letter-spacing: 0.35em; text-transform: uppercase;
        color: var(--gold); margin-bottom: 18px;
    }}
    .hero h1 {{
        font-family: 'Fraunces', serif;
        font-size: clamp(2.4rem, 6vw, 4rem);
        font-weight: 600; line-height: 1.05; margin-bottom: 20px;
    }}
    .hero p {{ font-size: 1.1rem; color: rgba(250,246,240,0.8); max-width: 560px; margin: 0 auto; }}

    /* Navigation par ancres */
    nav.sticky {{
        position: sticky; top: 0; z-index: 10;
        background: rgba(250,246,240,0.92);
        backdrop-filter: blur(10px);
        border-bottom: 1px solid var(--line);
        padding: 14px 0;
    }}
    nav.sticky .wrap {{ display: flex; gap: 28px; justify-content: center; flex-wrap: wrap; }}
    nav.sticky a {{
        color: var(--ink-soft); text-decoration: none; font-weight: 500;
        font-size: 15px; transition: color 0.2s; position: relative;
    }}
    nav.sticky a:hover {{ color: var(--accent); }}

    /* Sections */
    section {{ padding: 70px 0; }}
    section:nth-child(even) {{ background: var(--paper-2); }}
    .section-head {{ text-align: center; margin-bottom: 50px; }}
    .section-head .num {{
        font-family: 'Fraunces', serif; font-size: 14px; color: var(--accent);
        letter-spacing: 0.2em;
    }}
    .section-head h2 {{
        font-family: 'Fraunces', serif; font-size: clamp(1.8rem, 4vw, 2.6rem);
        font-weight: 600; margin-top: 6px;
    }}
    .section-head p {{ color: var(--ink-soft); margin-top: 10px; }}

    .cat-group {{ margin-bottom: 44px; }}
    .cat-title {{
        font-family: 'Fraunces', serif; font-size: 1.3rem; font-weight: 600;
        margin-bottom: 20px; padding-bottom: 8px; border-bottom: 2px solid var(--accent-soft);
        display: inline-block;
    }}

    .card-grid {{
        display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 20px;
    }}
    .equip-grid {{ grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }}

    .card {{
        background: #fff; border: 1px solid var(--line); border-radius: 14px;
        padding: 22px; box-shadow: var(--shadow);
        transition: transform 0.25s ease, box-shadow 0.25s ease;
    }}
    .card:hover {{ transform: translateY(-4px); box-shadow: 0 12px 32px rgba(40,25,10,0.12); }}
    .card-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }}
    .card h3 {{ font-family: 'Fraunces', serif; font-size: 1.2rem; font-weight: 600; }}
    .price {{
        font-weight: 600; color: var(--accent); font-size: 1.15rem; white-space: nowrap;
    }}
    .price-unit {{ font-size: 0.75rem; color: var(--ink-soft); font-weight: 400; }}
    .card-meta {{ font-size: 0.85rem; color: var(--gold); font-weight: 500; }}
    .card-desc {{ color: var(--ink-soft); font-size: 0.92rem; margin-top: 10px; }}

    .card-contenu {{ margin-top: 14px; }}
    .card-contenu summary {{
        cursor: pointer; font-size: 0.85rem; color: var(--accent); font-weight: 500;
        list-style: none; user-select: none;
    }}
    .card-contenu summary::-webkit-details-marker {{ display: none; }}
    .card-contenu summary::before {{ content: "＋ "; }}
    .card-contenu[open] summary::before {{ content: "− "; }}
    .card-contenu ul {{ margin-top: 12px; padding-left: 18px; }}
    .card-contenu li {{ font-size: 0.85rem; color: var(--ink-soft); margin-bottom: 4px; }}

    /* Cartes équipement avec photo */
    .equip-card {{ padding: 0; overflow: hidden; display: flex; flex-direction: column; }}
    .equip-photo {{
        aspect-ratio: 4/3; background: var(--paper-2); overflow: hidden;
        display: flex; align-items: center; justify-content: center;
    }}
    .equip-photo img {{ width: 100%; height: 100%; object-fit: contain; padding: 12px; }}
    .equip-body {{ padding: 18px; flex: 1; display: flex; flex-direction: column; }}
    .equip-marque {{
        font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase;
        color: var(--gold); font-weight: 600;
    }}
    .equip-body h3 {{ font-size: 1.05rem; margin: 4px 0 0; }}
    .equip-body .price {{ margin-top: auto; padding-top: 12px; }}

    /* Footer */
    footer {{
        background: var(--ink); color: rgba(250,246,240,0.85);
        text-align: center; padding: 50px 0; font-size: 0.9rem;
    }}
    footer .brand {{ font-family: 'Fraunces', serif; font-size: 1.3rem; color: var(--paper); margin-bottom: 8px; }}
    footer a {{ color: var(--gold); text-decoration: none; }}
    footer .maj {{ margin-top: 16px; font-size: 0.78rem; color: rgba(250,246,240,0.5); }}

    @media (max-width: 600px) {{
        section {{ padding: 48px 0; }}
        header.hero {{ padding: 64px 0 56px; }}
    }}
</style>
</head>
<body>

<header class="hero">
    <div class="wrap hero-content">
        <div class="eyebrow">Alexis Événementiel</div>
        <h1>Packs, prestations<br>& location de matériel</h1>
        <p>DJ-animateur dans le Tarn — sonorisation, lumière, photobooth et animations pour vos événements.</p>
    </div>
</header>

<nav class="sticky">
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
            <h2>Nos formules</h2>
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
            <p>À la carte, pour compléter votre événement.</p>
        </div>
        {prestations}
    </div>
</section>

<section id="location">
    <div class="wrap">
        <div class="section-head">
            <div class="num">03</div>
            <h2>Location de matériel</h2>
            <p>Notre parc son, lumière et vidéo, à louer pour vos propres événements. Tarif à la journée ou au week-end selon le matériel — contactez-nous.</p>
        </div>
        {equipements}
    </div>
</section>

<footer>
    <div class="wrap">
        <div class="brand">Alexis Événementiel</div>
        <div>Albi & Tarn (81) — déplacements jusqu'à 200 km</div>
        <div><a href="tel:0618855892">06 18 85 58 92</a> · <a href="mailto:alexis.arokiassamy@gmail.com">alexis.arokiassamy@gmail.com</a></div>
        <div class="maj">Catalogue mis à jour le {maj} · TVA non applicable, art. 293 B du CGI</div>
    </div>
</footer>

</body>
</html>"""


if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("catalogue.html")
    generate(base, out)
