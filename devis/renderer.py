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

    # Construit la liste des suppléments enrichie (id → nom, prix)
    supplements_enriched = []
    if catalogue and "equipements" in catalogue:
        from catalogue.pricing import calculer_prix
        for supp in (data.get("supplements") or []):
            eq = catalogue["equipements"].get(supp["id"])
            if not eq:
                continue
            try:
                prix = calculer_prix(eq, supp["quantite"])
            except Exception:
                prix = 0
            supplements_enriched.append({
                "id": supp["id"],
                "nom": eq.get("nom", supp["id"]),
                "description": eq.get("description_courte", ""),
                "quantite": supp["quantite"],
                "prix": prix,
            })

    tpl = env.get_template("devis.html.j2")
    return tpl.render(
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
