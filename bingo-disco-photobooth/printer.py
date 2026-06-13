"""Impression optionnelle sur DNP DS620 (macOS).

Deux modes, choisis par variables d'environnement :
  1. CUPS / lp   -> DNP_PRINTER = nom de la file (voir `lpstat -p`).
  2. Hot folder  -> DNP_HOTFOLDER = dossier surveillé par le logiciel DNP ;
                    on y copie simplement le JPEG.

Si aucun n'est configuré, l'impression est désactivée (no-op) et on le signale.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


class PrintResult:
    def __init__(self, ok: bool, message: str):
        self.ok = ok
        self.message = message


def is_enabled() -> bool:
    return bool(os.environ.get("DNP_PRINTER") or os.environ.get("DNP_HOTFOLDER"))


def print_image(file_path: Path) -> PrintResult:
    printer = os.environ.get("DNP_PRINTER")
    hotfolder = os.environ.get("DNP_HOTFOLDER")

    if hotfolder:
        try:
            dest = Path(hotfolder) / f"{int(time.time())}_{file_path.name}"
            shutil.copy(file_path, dest)
            return PrintResult(True, f"Déposé dans le hot folder : {dest}")
        except Exception as exc:
            return PrintResult(False, f"Hot folder échoué : {exc}")

    if printer:
        cmd = ["lp", "-d", printer]
        media = os.environ.get("DNP_MEDIA")
        if media:
            cmd += ["-o", f"media={media}"]
        cmd.append(str(file_path))
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if out.returncode == 0:
                return PrintResult(True, out.stdout.strip() or "Envoyé à l'imprimante.")
            return PrintResult(False, out.stderr.strip() or "Échec lp.")
        except FileNotFoundError:
            return PrintResult(False, "Commande `lp` introuvable (CUPS non dispo).")
        except Exception as exc:
            return PrintResult(False, f"Impression échouée : {exc}")

    return PrintResult(False, "Impression non configurée (DNP_PRINTER / DNP_HOTFOLDER vides).")
