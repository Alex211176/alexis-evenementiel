"""
fiches.renderer — Rendu Jinja2 du template HTML.
"""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

DEFAULT_TEMPLATE = "fiche_technique.html.j2"


def render_html(
    data: dict,
    template_dir: Path,
    template_name: str = DEFAULT_TEMPLATE,
    static_url: str = "static",
) -> str:
    """
    Rend le template Jinja2 avec les données fournies.

    Args:
        data: dict fusionné (défauts + événement).
        template_dir: chemin du dossier contenant le template.
        template_name: nom du fichier template.
        static_url: préfixe d'URL pour les ressources statiques
                    (utile pour différencier export PDF / serveur web).
    """
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=False,
        lstrip_blocks=False,
    )
    template = env.get_template(template_name)
    return template.render(static_url=static_url, **data)
