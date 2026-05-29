#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate.py — Génération CLI d'une fiche technique HTML/PDF.

Usage:
    python scripts/generate.py data/events/exemple_mariage.json
    python scripts/generate.py data/events/exemple_mariage.json --pdf
    python scripts/generate.py data/events/exemple_mariage.json --pdf -o data/output/
"""

import argparse
import sys
import unicodedata
import re
from pathlib import Path

# Ajouter la racine du projet au PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fiches import load_config, validate, render_html, export_pdf
from fiches.config import ConfigError

DEFAULTS = ROOT / "data" / "defaults" / "prestataire.json"
TEMPLATE_DIR = ROOT / "fiches" / "templates"
STATIC_DIR = ROOT / "fiches" / "static"
OUTPUT_DIR = ROOT / "data" / "output"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def main():
    parser = argparse.ArgumentParser(
        description="Génère une fiche technique HTML (et PDF optionnel)."
    )
    parser.add_argument("event_json", help="Chemin du JSON événement")
    parser.add_argument("--defaults", default=str(DEFAULTS),
                        help=f"JSON de défauts (défaut: {DEFAULTS.relative_to(ROOT)})")
    parser.add_argument("--output", "-o", default=str(OUTPUT_DIR),
                        help=f"Dossier de sortie (défaut: {OUTPUT_DIR.relative_to(ROOT)})")
    parser.add_argument("--pdf", action="store_true", help="Génère aussi un PDF")
    parser.add_argument("--name", default=None, help="Nom de fichier (sans extension)")
    parser.add_argument("--open", action="store_true",
                        help="Ouvre le résultat dans le navigateur (HTML) ou Preview (PDF, macOS)")
    args = parser.parse_args()

    # Charge & valide
    try:
        data = load_config(Path(args.defaults), Path(args.event_json))
        validate(data)
    except ConfigError as e:
        sys.exit(f"❌ {e}")

    # Rend
    # Pour la sortie HTML standalone, on utilise un chemin relatif vers les statics
    # depuis le dossier de sortie. Pour le PDF, WeasyPrint utilise base_url.
    html = render_html(
        data,
        template_dir=TEMPLATE_DIR,
        static_url=str(STATIC_DIR.as_uri()),  # file:// URL absolue pour HTML standalone
    )

    # Nom de fichier
    if args.name:
        stem = args.name
    else:
        ref = data["document"]["reference"]
        ev = slugify(data["event"]["name"])
        stem = f"fiche-{ref}-{ev}"

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / f"{stem}.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"✅ HTML : {html_path}")

    if args.pdf:
        try:
            pdf_path = output_dir / f"{stem}.pdf"
            # Pour le PDF on rerend avec un static_url relatif et base_url pointant
            # vers fiches/static, WeasyPrint résoudra les ressources via le filesystem
            html_for_pdf = render_html(
                data,
                template_dir=TEMPLATE_DIR,
                static_url=".",  # WeasyPrint résoudra via base_url
            )
            export_pdf(html_for_pdf, pdf_path, base_url=STATIC_DIR)
            print(f"✅ PDF  : {pdf_path}")
        except ImportError as e:
            sys.exit(f"❌ {e}")

    if args.open:
        import subprocess, platform
        target = pdf_path if args.pdf else html_path
        if platform.system() == "Darwin":
            subprocess.run(["open", str(target)])
        elif platform.system() == "Linux":
            subprocess.run(["xdg-open", str(target)])
        else:
            print(f"ℹ️  Ouvre manuellement : {target}")


if __name__ == "__main__":
    main()
