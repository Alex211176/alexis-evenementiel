"""Bibliothèque de prompts nommés, persistée dans data/prompts.json.

Permet à l'opérateur d'enregistrer / choisir / modifier / supprimer ses prompts
depuis la console, sans toucher au code. Au premier lancement, le fichier est
créé avec un prompt "Pixar" validé.
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

PROMPTS_FILE = Path(__file__).resolve().parent / "data" / "prompts.json"

# Prompt Pixar validé, utilisé pour amorcer la bibliothèque au premier lancement.
_PIXAR = (
    "Analyse la photo jointe et génère une caricature 3D de style dessin animé "
    "(type Pixar/Dreamworks). Applique les caractéristiques suivantes : "
    "1. Exagération : Accentue les traits distinctifs du visage (sourire, regard, "
    "forme du visage) de manière humoristique mais bienveillante. Donne au "
    "personnage une tête légèrement plus grande que le corps (style 'bobblehead'). "
    "2. Expression : Rends l'expression faciale très expressive et joyeuse. "
    "3. Style Visuel : Utilise un rendu 3D haute définition avec un éclairage "
    "cinématographique doux. Les textures de la peau et des vêtements doivent être "
    "nettes mais stylisées. 4. Arrière-plan : Garde un fond coloré simple et flouté "
    "pour faire ressortir le personnage. Respecte fidèlement les couleurs (cheveux, "
    "yeux, vêtements) de la personne sur la photo."
)
_SEED = [{"id": "pixar", "name": "Pixar (caricature 3D)", "text": _PIXAR}]


class PromptLibrary:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.prompts: list[dict] = []
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
            self.prompts = data.get("prompts", [])
        except (FileNotFoundError, ValueError):
            self.prompts = list(_SEED)
            self._save()

    def _save(self) -> None:
        PROMPTS_FILE.write_text(
            json.dumps({"prompts": self.prompts}, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def list(self) -> list[dict]:
        with self.lock:
            return list(self.prompts)

    def get(self, pid: str) -> dict | None:
        return next((p for p in self.prompts if p["id"] == pid), None)

    def save(self, name: str, text: str, pid: str | None = None) -> dict:
        """Crée un prompt (pid vide) ou met à jour celui dont l'id == pid."""
        name = (name or "Sans nom").strip()[:60]
        text = (text or "").strip()
        with self.lock:
            existing = self.get(pid) if pid else None
            if existing:
                existing["name"], existing["text"] = name, text
                preset = existing
            else:
                preset = {"id": uuid.uuid4().hex[:8], "name": name, "text": text}
                self.prompts.append(preset)
            self._save()
        return preset

    def delete(self, pid: str) -> None:
        with self.lock:
            self.prompts = [p for p in self.prompts if p["id"] != pid]
            self._save()


library = PromptLibrary()
