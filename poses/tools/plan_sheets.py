#!/usr/bin/env python3
"""
plan_sheets.py — Planificateur de planches de croquis (Poses Mariage).

Objectif : générer le MOINS de planches possible dans Gemini, puis les découper.
Ce script ne génère aucune image : il prépare le travail.

Pour chaque planche il produit :
  - un PROMPT prêt à coller dans Gemini (style figé + liste ordonnée des cases) ;
  - une entrée de MANIFESTE (case n° k -> pose_id) que le slicer utilisera pour
    nommer les découpes thumbs/<id>.webp.

L'ordre des cases (gauche→droite, haut→bas) EST le contrat de mapping : le slicer
coupe dans cet ordre. C'est ce qui rend le découpage fiable malgré la dérive IA.

Usage :
  python3 poses/tools/plan_sheets.py                 # dense, 3 col x 4 rangées (12/planche)
  python3 poses/tools/plan_sheets.py --cols 4 --rows 4   # 16/planche (moins de planches)
  python3 poses/tools/plan_sheets.py --by-phase      # une planche ne mélange pas les phases
  python3 poses/tools/plan_sheets.py --out /chemin/sortie
"""

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from poses.loader import load_library  # noqa: E402


def _style_prefix(cols: int, rows: int, count: int) -> str:
    return f"""Illustration de mariage en PLANCHE DE CROQUIS, style éditorial haut de gamme.

STYLE (strictement identique pour toutes les cases) :
- trait à l'encre noire, monoligne, fin et régulier ; minimaliste et élégant ;
- aucun ombrage, aucune couleur ; personnages stylisés, visages à peine suggérés ;
- fond CRÈME UNI (#f3ede1), identique partout.

MISE EN PAGE (impératif pour le découpage automatique) :
- grille RÉGULIÈRE de {cols} colonnes × {rows} rangées, cases de TAILLE STRICTEMENT ÉGALE ;
- cases séparées par des GOUTTIÈRES BLANCHES nettes et larges ; marges égales sur les 4 bords ;
- UNE seule pose par case, bien centrée ;
- AUCUN texte, chiffre, cadre ni légende où que ce soit dans l'image ;
- {count} cases remplies au total ; toute case restante de la dernière rangée reste VIDE (blanche).

CONTENU des cases (ordre de lecture : gauche→droite puis haut→bas) :"""


def chunk(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def build_sheets(lib, cols, rows, by_phase):
    per_sheet = cols * rows
    # Liste globale ordonnée (phase.order puis ordre des poses dans la phase)
    flat = []
    for phase in lib["phases"]:
        for pose in phase["poses"]:
            flat.append({
                "pose_id": pose["id"],
                "title": pose["title"],
                "desc": pose["desc"],
                "phase_id": phase["id"],
                "phase_label": phase["label"],
            })

    groups = []
    if by_phase:
        for phase in lib["phases"]:
            items = [p for p in flat if p["phase_id"] == phase["id"]]
            for part in chunk(items, per_sheet):
                groups.append((phase["label"], part))
    else:
        for part in chunk(flat, per_sheet):
            labels = {p["phase_label"] for p in part}
            title = next(iter(labels)) if len(labels) == 1 else "phases mêlées"
            groups.append((title, part))

    sheets = []
    for idx, (label, items) in enumerate(groups, start=1):
        sheet_id = f"sheet_{idx:02d}"
        used_rows = math.ceil(len(items) / cols)
        cells = []
        for k, it in enumerate(items):
            cells.append({
                "index": k,               # 0-based, ordre de lecture
                "row": k // cols,
                "col": k % cols,
                **it,
            })
        sheets.append({
            "sheet_id": sheet_id,
            "hint": label,
            "cols": cols,
            "rows": used_rows,
            "count": len(items),
            "cells": cells,
        })
    return sheets


def render_prompt(sheet):
    lines = [_style_prefix(sheet["cols"], sheet["rows"], sheet["count"])]
    for c in sheet["cells"]:
        lines.append(f"{c['index'] + 1}. {c['title']} — {c['desc']}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Planifie les planches de croquis à générer.")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--by-phase", action="store_true",
                    help="Ne pas mélanger les phases sur une même planche.")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "out"))
    args = ap.parse_args()

    lib = load_library()
    sheets = build_sheets(lib, args.cols, args.rows, args.by_phase)

    out = Path(args.out)
    (out / "prompts").mkdir(parents=True, exist_ok=True)

    manifest = {
        "cols": args.cols,
        "rows": args.rows,
        "by_phase": args.by_phase,
        "n_sheets": len(sheets),
        "sheets": sheets,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    for sheet in sheets:
        (out / "prompts" / f"{sheet['sheet_id']}.txt").write_text(
            render_prompt(sheet), encoding="utf-8")

    total = sum(s["count"] for s in sheets)
    print(f"✅ {len(sheets)} planches pour {total} poses "
          f"({args.cols}×{args.rows} = {args.cols * args.rows}/planche, "
          f"{'par phase' if args.by_phase else 'dense'})")
    print(f"   Manifeste : {out / 'manifest.json'}")
    print(f"   Prompts   : {out / 'prompts'}/  (un .txt par planche)")
    for s in sheets:
        print(f"     - {s['sheet_id']} : {s['count']:2d} cases · {s['hint']}")


if __name__ == "__main__":
    main()
