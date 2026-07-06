#!/usr/bin/env python3
"""
Reconstruit docs/ia/themes/themes.json en scannant les dossiers.

Arbo attendue :  docs/ia/themes/<theme>/<montage>/  avec des fichiers
nommés par rôle : avant.*  apres.*  montage.*  extra-01.* extra-02.* …

- Les libellés déjà présents dans themes.json sont CONSERVÉS.
- Un nouveau thème/montage reçoit un libellé auto (à partir du slug), à raffiner
  ensuite dans themes.json si besoin.
- L'ordre existant est préservé ; les nouveautés sont ajoutées à la fin.
"""

import json
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEMES_DIR = ROOT / "docs" / "ia" / "themes"
JSON_PATH = THEMES_DIR / "themes.json"
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")

DEFAULT_DOC = (
    "Registre Photobooth IA. Arbo : docs/ia/themes/<theme>/<montage>/ avec "
    "avant.jpg, apres.jpg (pour le slider), montage.jpg (optionnel) et extras "
    "(autres photos). La galerie affiche un slider par montage ayant avant + "
    "apres ; le clic ouvre ia/montage.html?theme=<t>&montage=<m>. "
    "GÉNÉRÉ PAR scripts/rebuild_ia_themes.py — voir README.md."
)


def humanize(slug: str) -> str:
    words = slug.replace("-", " ").replace("_", " ").split()
    return " ".join(w[:1].upper() + w[1:] for w in words)


def clean_slug(name: str) -> str:
    """Nom de dossier propre : minuscules, sans accent, tirets."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s or "sans-nom"


def _rename(path: Path, newname: str) -> Path:
    if path.name == newname:
        return path
    target = path.with_name(newname)
    if target.exists() and target.resolve() == path.resolve():
        # changement de casse seul (FS insensible) → passer par un temporaire
        tmp = path.with_name(newname + "___tmp")
        os.rename(path, tmp)
        os.rename(tmp, target)
    else:
        os.rename(path, target)
    return target


def normalize_tree():
    """Renomme fichiers (extension en minuscules) + dossiers (slug propre)."""
    changed = []
    for tdir in [d for d in THEMES_DIR.iterdir() if d.is_dir()]:
        for mdir in [d for d in tdir.iterdir() if d.is_dir()]:
            for f in [p for p in mdir.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT]:
                newf = f.stem.lower() + f.suffix.lower()
                if newf != f.name:
                    _rename(f, newf)
                    changed.append(f"{tdir.name}/{mdir.name}/{f.name} → {newf}")
            newm = clean_slug(mdir.name)
            if newm != mdir.name:
                _rename(mdir, newm)
                changed.append(f"dossier {tdir.name}/{mdir.name} → {newm}")
        newt = clean_slug(tdir.name)
        if newt != tdir.name:
            _rename(tdir, newt)
            changed.append(f"dossier {tdir.name} → {newt}")
    return changed


def find_role(folder: Path, role: str):
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix.lower() in IMG_EXT and p.stem.lower() == role:
            return p.name
    return None


def find_extras(folder: Path):
    extras = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix.lower() in IMG_EXT and re.match(r"extra[-_]?\d+$", p.stem.lower()):
            extras.append(p.name)
    return extras


def load_existing():
    labels_t, labels_m, order_t, order_m, doc = {}, {}, [], {}, DEFAULT_DOC
    if JSON_PATH.exists():
        try:
            data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
            doc = data.get("_doc", DEFAULT_DOC)
            for t in data.get("themes", []):
                s = t["slug"]
                labels_t[s] = t.get("label")
                order_t.append(s)
                order_m[s] = []
                labels_m[s] = {}
                for m in t.get("montages", []):
                    labels_m[s][m["slug"]] = m.get("label")
                    order_m[s].append(m["slug"])
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  themes.json existant illisible ({e}) — on repart de zéro.")
    return labels_t, labels_m, order_t, order_m, doc


def ordered(existing_order, present):
    seen, out = set(), []
    for s in existing_order:
        if s in present:
            out.append(s)
            seen.add(s)
    for s in sorted(present):
        if s not in seen:
            out.append(s)
    return out


def main():
    if not THEMES_DIR.exists():
        print(f"❌ Dossier introuvable : {THEMES_DIR}")
        sys.exit(1)

    renamed = normalize_tree()
    if renamed:
        print("🧹 Noms normalisés (minuscules, sans accent) :")
        for r in renamed:
            print(f"   · {r}")

    labels_t, labels_m, order_t, order_m, doc = load_existing()

    disk = {}
    for tdir in sorted(d for d in THEMES_DIR.iterdir() if d.is_dir()):
        montages = {}
        for mdir in sorted(d for d in tdir.iterdir() if d.is_dir()):
            montages[mdir.name] = {
                "avant": find_role(mdir, "avant"),
                "apres": find_role(mdir, "apres"),
                "montage": find_role(mdir, "montage"),
                "extras": find_extras(mdir),
            }
        disk[tdir.name] = montages

    themes, warns, n_montages, n_sliders = [], [], 0, 0
    for tslug in ordered(order_t, disk):
        tlabel = labels_t.get(tslug) or humanize(tslug)
        if not labels_t.get(tslug):
            warns.append(f"nouveau thème « {tslug} » → libellé auto « {tlabel} » (modifiable dans themes.json)")
        montages = []
        for mslug in ordered(order_m.get(tslug, []), disk[tslug]):
            info = disk[tslug][mslug]
            mlabel = labels_m.get(tslug, {}).get(mslug) or humanize(mslug)
            montages.append({
                "slug": mslug, "label": mlabel,
                "avant": info["avant"], "apres": info["apres"],
                "montage": info["montage"], "extras": info["extras"],
            })
            n_montages += 1
            if info["avant"] and info["apres"]:
                n_sliders += 1
            else:
                warns.append(f"« {tslug}/{mslug} » sans avant+apres → n'apparaîtra PAS en slider")
        themes.append({"slug": tslug, "label": tlabel, "montages": montages})

    out = {"_doc": doc, "themes": themes}
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"✅ themes.json reconstruit : {len(themes)} thème(s), {n_montages} montage(s), {n_sliders} slider(s).")
    for w in warns:
        print(f"   ⚠️  {w}")


if __name__ == "__main__":
    main()
