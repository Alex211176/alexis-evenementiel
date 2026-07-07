#!/usr/bin/env python3
"""
Reconstruit les manifestes des « galeries simples » (photos en vrac).

Une galerie simple = un dossier docs/<slug>/photos/ où l'on dépose des photos
SANS structure (contrairement au Photobooth IA qui a des triplets avant/après).
Le manifeste docs/<slug>/gallery.json liste les fichiers, dans l'ordre, avec
une légende auto tirée du nom de fichier.

Ajouter une future galerie = une ligne dans GALLERIES ci-dessous + une page
HTML qui lit docs/<slug>/gallery.json (voir docs/lunettes-3d.html comme modèle).

Conventions de dépôt (rien d'obligatoire) :
- Photos .jpg .jpeg .png .webp ET vidéos .mp4 .webm .mov (affichées MUETTES).
  La casse est normalisée en minuscules.
- Un préfixe « 01- », « 02- »… force l'ordre (sinon tri alphabétique).
- Le reste du nom devient la légende : « 03-monture-coeur.jpg » → « Monture coeur ».
- Les légendes déjà présentes dans gallery.json et modifiées à la main sont
  CONSERVÉES lors d'un nouveau scan (tant que le fichier n'est pas renommé).

GÉNÉRÉ / lancé par le double-clic « Publier-Photobooth-IA.command ».
"""

import json
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXT = (".mp4", ".webm", ".mov")
MEDIA_EXT = IMG_EXT + VIDEO_EXT


def media_type(suffix: str) -> str:
    return "video" if suffix.lower() in VIDEO_EXT else "image"

# --- Registre des galeries simples -----------------------------------------
# slug = nom du dossier sous docs/ (le dossier photos est docs/<slug>/photos/,
# le manifeste docs/<slug>/gallery.json). Ajoute ici tes futures options.
GALLERIES = [
    {"slug": "lunettes-3d", "titre": "Lunettes personnalisées 3D"},
    {"slug": "kids-booth", "titre": "Kids Booth"},
]


LIGATURES = {"œ": "oe", "Œ": "oe", "æ": "ae", "Æ": "ae", "ß": "ss"}


def _delig(s: str) -> str:
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return s


def clean_name(stem: str) -> str:
    """Nom de fichier propre : minuscules, sans accent, tirets. Préserve un
    éventuel préfixe d'ordre « 01- » (il sert au tri et est retiré du libellé)."""
    s = unicodedata.normalize("NFKD", _delig(stem)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s or "photo"


def humanize(stem: str) -> str:
    """Libellé lisible : retire un préfixe d'ordre « 01- » puis capitalise."""
    s = re.sub(r"^\d+[-_\s]+", "", stem)  # 01-  02_  03 …
    words = s.replace("-", " ").replace("_", " ").split()
    return " ".join(w[:1].upper() + w[1:] for w in words) or "Photo"


def _rename(path: Path, newname: str) -> Path:
    if path.name == newname:
        return path
    target = path.with_name(newname)
    if target.exists() and target.resolve() == path.resolve():
        tmp = path.with_name(newname + "___tmp")
        os.rename(path, tmp)
        os.rename(tmp, target)
    else:
        os.rename(path, target)
    return target


def load_existing_caps(manifest: Path):
    """Légendes déjà connues, indexées par nom de fichier (src)."""
    caps = {}
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for ph in data.get("photos", []):
                if ph.get("src"):
                    caps[ph["src"]] = ph.get("cap", "")
        except Exception as e:
            print(f"⚠️  {manifest.name} illisible ({e}) — on repart de zéro.")
    return caps


def build_gallery(slug: str) -> dict:
    base = ROOT / "docs" / slug
    photos_dir = base / "photos"
    manifest = base / "gallery.json"
    if not photos_dir.is_dir():
        return {"slug": slug, "count": 0, "missing": True}

    old_caps = load_existing_caps(manifest)

    # 1) normaliser les noms (extension minuscule + slug propre)
    files = [p for p in photos_dir.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXT]
    normalized = []
    for f in files:
        newname = clean_name(f.stem) + f.suffix.lower()
        # éviter les collisions après nettoyage
        if newname != f.name and (f.with_name(newname).exists()
                                  and f.with_name(newname).resolve() != f.resolve()):
            newname = clean_name(f.stem) + "-" + str(abs(hash(f.name)) % 1000) + f.suffix.lower()
        normalized.append(_rename(f, newname))

    # 2) trier (les préfixes 01- 02- pilotent l'ordre)
    normalized.sort(key=lambda p: p.name.lower())

    # 3) construire la liste, en gardant les légendes retouchées à la main
    photos = []
    for p in normalized:
        auto = humanize(Path(p.name).stem)
        cap = old_caps.get(p.name)
        # si l'ancienne légende existe et n'est pas la version auto → on la garde
        photos.append({
            "src": p.name,
            "cap": cap if cap else auto,
            "type": media_type(p.suffix),
        })

    manifest.write_text(
        json.dumps({"photos": photos}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"slug": slug, "count": len(photos), "missing": False}


def main():
    print("> Galeries simples (photos en vrac)…")
    total = 0
    for g in GALLERIES:
        res = build_gallery(g["slug"])
        if res.get("missing"):
            print(f"  · {g['slug']} : dossier photos/ absent — ignoré.")
            continue
        total += res["count"]
        print(f"  · {g['titre']} ({g['slug']}) : {res['count']} photo(s).")
    print(f"✅ {len(GALLERIES)} galerie(s) simple(s), {total} photo(s) au total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
