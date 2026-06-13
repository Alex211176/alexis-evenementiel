"""État en mémoire + bus d'événements SSE pour le module photo Bingo Disco.

Volontairement simple (un seul process Flask, animation d'une soirée).
Pas de base de données : les images sont sur disque, les métadonnées en RAM.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
CAPTURES_DIR = BASE_DIR / "data" / "captures"
GENERATED_DIR = BASE_DIR / "data" / "generated"
# Réglages "événement" persistés (survivent à un redémarrage du serveur).
SETTINGS_FILE = BASE_DIR / "data" / "settings.json"


@dataclass
class Photo:
    """Une photo soumise par un joueur, à différents stades du pipeline."""

    id: str
    player_name: str
    theme_id: str
    status: str = "captured"  # captured -> generating -> generated -> on_screen
    capture_file: Optional[str] = None     # nom de fichier dans data/captures
    base_file: Optional[str] = None        # sortie brute Gemini (avant template/texte)
    generated_file: Optional[str] = None   # image finale affichée (template + texte)
    template_name: Optional[str] = None    # template choisi pour cette photo
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()

    def public(self) -> dict:
        d = asdict(self)
        # URLs servies par Flask plutôt que les noms de fichiers bruts.
        d["capture_url"] = f"/media/captures/{self.capture_file}" if self.capture_file else None
        d["generated_url"] = f"/media/generated/{self.generated_file}" if self.generated_file else None
        return d


class EventBus:
    """Diffuse des événements à tous les abonnés SSE (console + écran)."""

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue] = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=64)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, event: str, data: dict) -> None:
        payload = json.dumps({"event": event, "data": data})
        with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    pass  # abonné lent : on saute, l'écran se resynchronisera au prochain event


class Store:
    """Conteneur central : config de la soirée, photos, bus d'événements."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.photos: dict[str, Photo] = {}
        self.bus = EventBus()
        # Réglages pilotés par l'opérateur depuis la console.
        self.photo_mode_enabled: bool = False   # le mode photo est-il ouvert aux joueurs ?
        self.current_on_screen: Optional[str] = None  # photo id affichée sur screen.html
        # --- Réglages "événement" (persistés) ---
        self.current_theme_id: str = "pixar"
        self.theme_mode: str = "imposed"        # "imposed" (animateur) | "free" (joueur choisit)
        self.event_text: str = ""               # texte fixe incrusté sur chaque photo (nom / lieu)
        self.custom_prompt: str = ""             # prompt libre : s'il est défini, il prime sur le thème
        self._load_persisted()

    # --- Persistance des réglages événement ---------------------------
    def _load_persisted(self) -> None:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            self.current_theme_id = data.get("current_theme_id", self.current_theme_id)
            self.theme_mode = data.get("theme_mode", self.theme_mode)
            self.event_text = data.get("event_text", self.event_text)
            self.custom_prompt = data.get("custom_prompt", self.custom_prompt)
        except (FileNotFoundError, ValueError):
            pass

    def _save_persisted(self) -> None:
        SETTINGS_FILE.write_text(json.dumps({
            "current_theme_id": self.current_theme_id,
            "theme_mode": self.theme_mode,
            "event_text": self.event_text,
            "custom_prompt": self.custom_prompt,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- Photos -------------------------------------------------------
    def add_photo(self, player_name: str, theme_id: str, capture_file: str) -> Photo:
        pid = uuid.uuid4().hex[:10]
        photo = Photo(id=pid, player_name=player_name or "Invité",
                      theme_id=theme_id, capture_file=capture_file)
        with self.lock:
            self.photos[pid] = photo
        self.bus.publish("photo_added", photo.public())
        return photo

    def get(self, pid: str) -> Optional[Photo]:
        return self.photos.get(pid)

    def update(self, photo: Photo, **changes) -> Photo:
        with self.lock:
            for k, v in changes.items():
                setattr(photo, k, v)
            photo.touch()
        self.bus.publish("photo_updated", photo.public())
        return photo

    def all_photos(self) -> list[dict]:
        with self.lock:
            items = sorted(self.photos.values(), key=lambda p: p.created_at, reverse=True)
        return [p.public() for p in items]

    def set_on_screen(self, pid: Optional[str]) -> None:
        with self.lock:
            self.current_on_screen = pid
        photo = self.photos.get(pid) if pid else None
        self.bus.publish("screen_show", photo.public() if photo else {"cleared": True})

    # --- Réglages -----------------------------------------------------
    def set_mode(self, enabled: bool) -> None:
        with self.lock:
            self.photo_mode_enabled = enabled
        self.bus.publish("mode_changed", {"enabled": enabled})

    def set_theme(self, theme_id: str) -> None:
        with self.lock:
            self.current_theme_id = theme_id
            self._save_persisted()
        self.bus.publish("theme_changed", {"theme_id": theme_id})

    def set_theme_mode(self, mode: str) -> None:
        with self.lock:
            self.theme_mode = "free" if mode == "free" else "imposed"
            self._save_persisted()
        self.bus.publish("theme_mode_changed", {"theme_mode": self.theme_mode})

    def set_event_text(self, text: str) -> None:
        with self.lock:
            self.event_text = (text or "")[:60]
            self._save_persisted()
        self.bus.publish("event_text_changed", {"event_text": self.event_text})

    def set_custom_prompt(self, text: str) -> None:
        with self.lock:
            self.custom_prompt = (text or "").strip()
            self._save_persisted()
        self.bus.publish("custom_prompt_changed", {"custom_prompt": self.custom_prompt})

    def settings(self) -> dict:
        return {
            "photo_mode_enabled": self.photo_mode_enabled,
            "current_theme_id": self.current_theme_id,
            "theme_mode": self.theme_mode,
            "event_text": self.event_text,
            "custom_prompt": self.custom_prompt,
            "current_on_screen": self.current_on_screen,
        }


# Singleton importé par app.py
store = Store()
