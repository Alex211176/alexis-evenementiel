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
import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageChops, ImageDraw, ImageFont

# Dossier des templates : configurable via la variable d'environnement
# TEMPLATES_DIR (ex. un dossier sur le Bureau), sinon data/templates/.
_DEFAULT_TEMPLATES = Path(__file__).resolve().parent / "data" / "templates"
TEMPLATES_DIR = Path(os.environ.get("TEMPLATES_DIR") or _DEFAULT_TEMPLATES)
try:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

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


# --------------------------------------------------------------------------
# Bande photo : détection des emplacements par couleur (rouge / vert)
# --------------------------------------------------------------------------
def _largest_blob_bbox(img: Image.Image, predicate, sample: int = 320):
    """Boîte englobante du PLUS GRAND bloc connexe validant `predicate`.

    On travaille sur une miniature (rapide), on isole les composantes connexes
    (4-voisinage) et on garde la plus grande : ça ignore les petits éléments
    parasites de la même couleur ailleurs dans le template (badges, logos…).
    """
    w, h = img.size
    scale = max(w, h) / sample
    small = img.resize((max(1, int(w / scale)), max(1, int(h / scale)))).convert("RGB")
    sw, sh = small.size
    px = small.load()
    mask = [[predicate(*px[x, y]) for x in range(sw)] for y in range(sh)]
    visited = [[False] * sw for _ in range(sh)]
    best = None
    best_count = 0
    for sy in range(sh):
        for sx in range(sw):
            if not mask[sy][sx] or visited[sy][sx]:
                continue
            stack = [(sx, sy)]
            visited[sy][sx] = True
            minx = maxx = sx
            miny = maxy = sy
            count = 0
            while stack:
                cx, cy = stack.pop()
                count += 1
                minx, maxx = min(minx, cx), max(maxx, cx)
                miny, maxy = min(miny, cy), max(maxy, cy)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < sw and 0 <= ny < sh and mask[ny][nx] and not visited[ny][nx]:
                        visited[ny][nx] = True
                        stack.append((nx, ny))
            if count > best_count:
                best_count, best = count, (minx, miny, maxx, maxy)
    if not best:
        return None
    minx, miny, maxx, maxy = best
    # Remise à l'échelle + petite marge pour couvrir entièrement le repère.
    pad = int(scale) + 1
    return (max(0, int(minx * scale) - pad), max(0, int(miny * scale) - pad),
            min(w, int((maxx + 1) * scale) + pad), min(h, int((maxy + 1) * scale) + pad))


def _is_red(r, g, b):
    return r > 150 and g < 120 and b < 120 and r - max(g, b) > 50


def _is_green(r, g, b):
    return g > 130 and b < 130 and g - r > 25 and g - b > 25


def detect_slots(template: Image.Image) -> dict:
    """Renvoie {'slot1': bbox_rouge, 'slot2': bbox_vert} si détectés."""
    slots = {}
    red = _largest_blob_bbox(template, _is_red)
    green = _largest_blob_bbox(template, _is_green)
    if red:
        slots["slot1"] = red
    if green:
        slots["slot2"] = green
    return slots


def is_photostrip(template_name: Optional[str]) -> bool:
    """True si le template contient les deux repères couleur (rouge + vert).
    Résultat mis en cache par (nom, date de modification) pour rester rapide."""
    if not template_name:
        return False
    path = TEMPLATES_DIR / template_name
    if not path.exists():
        return False
    key = (template_name, path.stat().st_mtime)
    if key in _strip_cache:
        return _strip_cache[key]
    slots = detect_slots(Image.open(path).convert("RGB"))
    val = "slot1" in slots and "slot2" in slots
    _strip_cache[key] = val
    return val


_strip_cache: dict = {}


def _punch_holes(template: Image.Image) -> Image.Image:
    """Rend transparents les pixels rouges/verts (les repères des emplacements),
    en gardant opaque tout ce qui est dessiné par-dessus (ballons, déco au
    premier plan). Renvoie le template "troué" en RGBA."""
    r, g, b, a = template.split()

    def m(band, fn):
        return band.point(lambda v: 255 if fn(v) else 0)

    def AND(*masks):
        out = masks[0]
        for mk in masks[1:]:
            out = ImageChops.multiply(out, mk)   # 0/255 -> ET logique
        return out

    red = AND(m(r, lambda v: v > 150), m(g, lambda v: v < 120), m(b, lambda v: v < 120))
    green = AND(m(g, lambda v: v > 130), m(r, lambda v: v < 140), m(b, lambda v: v < 140))
    holes = ImageChops.lighter(red, green)          # 255 là où il y a un repère
    new_alpha = ImageChops.subtract(a, holes)       # alpha -> 0 sur les repères
    out = template.copy()
    out.putalpha(new_alpha)
    return out


def build_photostrip(template_name: str, original_bytes: bytes,
                     stylized_bytes: bytes) -> bytes:
    """Compose la bande finale : on place les photos DERRIÈRE le template, qui
    est troué aux emplacements couleur. Tout ce qui est dessiné par-dessus les
    repères (ballons, etc.) reste au PREMIER PLAN devant les photos.

    Emplacement 1 (rouge) = photo originale, emplacement 2 (vert) = modifiée."""
    template = Image.open(TEMPLATES_DIR / template_name).convert("RGBA")
    slots = detect_slots(template.convert("RGB"))

    # 1) Calque du fond : photos collées aux emplacements détectés.
    back = Image.new("RGBA", template.size, (255, 255, 255, 255))

    def place(slot_key, img_bytes):
        box = slots.get(slot_key)
        if not box:
            return
        x0, y0, x1, y1 = box
        photo = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
        back.paste(_cover(photo, (max(1, x1 - x0), max(1, y1 - y0))), (x0, y0))

    place("slot1", original_bytes)
    place("slot2", stylized_bytes)

    # 2) Template troué (repères -> transparents) posé PAR-DESSUS les photos.
    result = Image.alpha_composite(back, _punch_holes(template))

    out = io.BytesIO()
    result.convert("RGB").save(out, format="JPEG", quality=95)
    return out.getvalue()
