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

from PIL import Image, ImageDraw, ImageFont

TEMPLATES_DIR = Path(__file__).resolve().parent / "data" / "templates"

# Polices candidates (Mac puis Linux) ; repli sur la police bitmap de Pillow.
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
]


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


def draw_caption(image_bytes: bytes, text: str) -> bytes:
    """Incruste un texte fixe (nom d'événement / lieu) en bas de l'image.

    Rendu identique pour toutes les photos : bandeau sombre + texte doré
    centré, taille auto-ajustée à la largeur. Sans texte -> image inchangée.
    """
    text = (text or "").strip()
    if not text:
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    margin = int(w * 0.06)
    max_text_w = w - 2 * margin
    font = _fit_font(draw, text, max_text_w, start=int(h * 0.06))

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    band_h = th + int(h * 0.05)
    # Bandeau translucide en bas
    draw.rectangle([0, h - band_h, w, h], fill=(0, 0, 0, 150))
    tx = (w - tw) // 2 - bbox[0]
    ty = h - band_h + (band_h - th) // 2 - bbox[1]
    # Légère ombre puis texte doré
    draw.text((tx + 2, ty + 2), text, font=font, fill=(0, 0, 0, 200))
    draw.text((tx, ty), text, font=font, fill=(232, 193, 74, 255))

    out = Image.alpha_composite(img, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_font(draw, text: str, max_w: int, start: int) -> ImageFont.FreeTypeFont:
    """Réduit la taille jusqu'à ce que le texte tienne dans max_w."""
    size = start
    while size > 12:
        font = _load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_w:
            return font
        size -= 4
    return _load_font(12)


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    img = img.resize((int(iw * scale), int(ih * scale)))
    left = (img.width - tw) // 2
    top = (img.height - th) // 2
    return img.crop((left, top, left + tw, top + th))
