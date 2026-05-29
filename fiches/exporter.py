"""
fiches.exporter — Export PDF via WeasyPrint.

WeasyPrint est importé paresseusement pour ne pas bloquer le projet
si l'utilisateur ne veut que du HTML.
"""

from pathlib import Path


def export_pdf(html: str, output_path: Path, base_url: Path) -> Path:
    """
    Convertit le HTML rendu en PDF.

    Args:
        html: contenu HTML complet.
        output_path: chemin de sortie du PDF.
        base_url: chemin de base pour résoudre les ressources statiques
                  (polices, images, CSS).

    Returns:
        Le chemin du PDF généré.

    Raises:
        ImportError: si WeasyPrint n'est pas installé.
    """
    try:
        from weasyprint import HTML
    except ImportError:
        raise ImportError(
            "WeasyPrint est requis pour l'export PDF. "
            "Installe-le avec : pip install weasyprint"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(base_url)).write_pdf(str(output_path))
    return output_path
