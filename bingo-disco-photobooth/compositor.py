"""Compositing optionnel : intégration de l'image générée dans un template PNG.

Un "template" est un PNG (idéalement avec zone transparente) déposé dans
data/templates/. On y incruste l'image générée, soit en fond (l'image dessous,
le template par-dessus pour le cadre/logo), soit dans une fenêtre définie.

Pour le prototype : on place l'image générée en fond, puis on superpose le
template (qui doit avoir une découpe transparente). Si aucun template n'est
fourni, on renvoie l'image telle quelle.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from PIL import Image

TEMPLATES_DIR = Path(__file__).resolve().parent / "data" / "templates"


def list_templates() -> list[str]:
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(p.name for p in TEMPLATES_DIR.glob("*.png"))


def apply_template(image_bytes: bytes, template_name: Optional[str]) -> bytes:
    """Renvoie le JPEG composité. Sans template valide -> image inchangée."""
    if not template_name:
        return image_bytes
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        return image_bytes

    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    template = Image.open(template_path).convert("RGBA")

    # On cale l'image générée à la taille du template (cadrage "cover").
    base = _cover(base, template.size)
    composed = Image.alpha_composite(base, template)

    out = io.BytesIO()
    composed.convert("RGB").save(out, format="JPEG", quality=95)
    return out.getvalue()


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    img = img.resize((int(iw * scale), int(ih * scale)))
    left = (img.width - tw) // 2
    top = (img.height - th) // 2
    return img.crop((left, top, left + tw, top + th))
