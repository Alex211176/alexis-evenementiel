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


def _build_prompt(theme: dict) -> str:
    parts = [
        theme.get("character_prompt", "").strip(),
        theme.get("background_prompt", "").strip(),
        "Rends une image carrée nette, qualité impression, sans texte ni filigrane.",
    ]
    return "\n".join(p for p in parts if p)


def stylize(image_bytes: bytes, theme: dict, mime_type: str = "image/jpeg") -> bytes:
    """Renvoie les octets PNG/JPEG de l'image stylisée."""
    if is_demo_mode():
        return _demo_image(image_bytes, theme)

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-image")
    api_key = os.environ["GEMINI_API_KEY"]
    url = f"{API_BASE}/{model}:generateContent"

    body = {
        "contents": [{
            "parts": [
                {"text": _build_prompt(theme)},
                {"inline_data": {"mime_type": mime_type,
                                 "data": base64.b64encode(image_bytes).decode()}},
            ]
        }],
        "generationConfig": {"responseModalities": ["IMAGE"]},
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


def _demo_image(image_bytes: bytes, theme: dict) -> bytes:
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

    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle([0, 880, 1024, 1024], fill=(0, 0, 0, 160))
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 44)
        small = ImageFont.truetype("DejaVuSans.ttf", 28)
    except Exception:
        font = small = ImageFont.load_default()
    draw.text((30, 905), "MODE DÉMO (pas de clé Gemini)", fill=(255, 215, 0), font=font)
    draw.text((30, 965), f"Thème : {theme.get('label', theme.get('id', '?'))}",
              fill=(255, 255, 255), font=small)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue()
