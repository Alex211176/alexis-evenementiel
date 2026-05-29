"""
devis.exporter — Génération du PDF du devis via WeasyPrint.
"""

from pathlib import Path


def export_devis_pdf(html: str, output_path: Path, base_url: Path = None) -> Path:
    """
    Génère un PDF depuis du HTML.

    Args:
        html: HTML rendu du devis
        output_path: chemin du PDF à générer
        base_url: dossier racine pour résoudre les URLs relatives (CSS, images)

    Returns:
        Le chemin du PDF généré.

    Raises:
        ImportError si WeasyPrint n'est pas disponible.
    """
    try:
        from weasyprint import HTML
    except ImportError as e:
        raise ImportError(
            "WeasyPrint n'est pas disponible. "
            "Sur macOS : `brew install pango gdk-pixbuf libffi` "
            "et lance avec `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`."
        ) from e

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base = str(base_url) if base_url else None
    HTML(string=html, base_url=base).write_pdf(str(output_path))

    return output_path
