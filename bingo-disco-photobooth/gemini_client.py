"""Client Google Gemini pour la stylisation d'image (édition image -> image).

Utilise l'API REST `generateContent` du modèle image (par défaut
`gemini-2.5-flash-image`, alias "Nano Banana"). On envoie la photo du joueur
+ un prompt de thème, on récupère l'image stylisée.

Si aucune clé `GEMINI_API_KEY` n'est définie, on bascule en MODE DEMO : aucune
requête réseau, on renvoie une image factice (la photo d'origine avec un
bandeau "DEMO"). Pratique pour tester tout le pipeline sans clé / sans crédit.
"""

from __future__ import annotations

import base64
import io
import os
from typing import Optional

import requests
from PIL import Image, ImageDraw, ImageFont

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(RuntimeError):
    pass


def is_demo_mode() -> bool:
    return not os.environ.get("GEMINI_API_KEY")


def build_theme_prompt(theme: dict) -> str:
    """Construit le prompt à partir d'un thème (personnage + fond + cadrage)."""
    parts = [
        theme.get("character_prompt", "").strip(),
        theme.get("background_prompt", "").strip(),
        "Rends une image carrée nette, qualité impression, sans texte ni filigrane.",
    ]
    return "\n".join(p for p in parts if p)


def stylize(image_bytes: bytes, prompt: str, demo_label: str = "",
            model: str = "", mime_type: str = "image/jpeg") -> bytes:
    """Renvoie les octets de l'image stylisée à partir d'un prompt en clair."""
    if is_demo_mode():
        return _demo_image(image_bytes, demo_label)

    model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-image")
    api_key = os.environ["GEMINI_API_KEY"]
    url = f"{API_BASE}/{model}:generateContent"

    gen_config = {"responseModalities": ["TEXT", "IMAGE"]}
    # Résolution / format de sortie (optionnels). imageSize : 1K / 2K / 4K.
    image_config = {}
    if os.environ.get("GEMINI_ASPECT_RATIO"):
        image_config["aspectRatio"] = os.environ["GEMINI_ASPECT_RATIO"]
    if os.environ.get("GEMINI_IMAGE_SIZE"):
        image_config["imageSize"] = os.environ["GEMINI_IMAGE_SIZE"]
    if image_config:
        gen_config["imageConfig"] = image_config

    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type,
                                 "data": base64.b64encode(image_bytes).decode()}},
            ]
        }],
        "generationConfig": gen_config,
    }

    try:
        resp = requests.post(url, params={"key": api_key}, json=body, timeout=120)
    except requests.RequestException as exc:
        raise GeminiError(f"Appel Gemini échoué : {exc}") from exc

    if resp.status_code != 200:
        raise GeminiError(f"Gemini {resp.status_code} : {resp.text[:500]}")

    data = resp.json()
    img_b64 = _extract_image(data)
    if not img_b64:
        raise GeminiError(f"Réponse Gemini sans image : {str(data)[:500]}")
    return base64.b64decode(img_b64)


def _extract_image(data: dict) -> Optional[str]:
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inline_data") or part.get("inlineData")
            if inline and inline.get("data"):
                return inline["data"]
    return None


def _demo_image(image_bytes: bytes, demo_label: str = "") -> bytes:
    """Image factice : photo d'origine + bandeau indiquant le mode démo et le thème."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        img = Image.new("RGB", (1024, 1024), (40, 40, 60))

    # Carré centré
    side = min(img.size)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((1024, 1024))

    # Bandeau en HAUT pour ne pas chevaucher le texte d'événement (incrusté en bas).
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle([0, 0, 1024, 130], fill=(0, 0, 0, 160))
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
        small = ImageFont.truetype("DejaVuSans.ttf", 26)
    except Exception:
        font = small = ImageFont.load_default()
    draw.text((30, 20), "MODE DÉMO (pas de clé Gemini)", fill=(255, 215, 0), font=font)
    draw.text((30, 75), demo_label or "Aperçu", fill=(255, 255, 255), font=small)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()
