#!/usr/bin/env python3
"""
slice_sheet.py — Découpe une planche de croquis Gemini en vignettes individuelles.

Entrée  : une image de planche (grille de poses) + le manifeste produit par
          plan_sheets.py (qui dit quelle case = quelle pose, dans l'ordre de lecture).
Sortie  : web/static/poses/thumbs/<pose_id>.webp (une vignette par case)
          + une PLANCHE DE CONTRÔLE qa_<sheet_id>.png pour valider l'alignement.

Robustesse à la dérive IA (les grilles générées ne sont jamais millimétrées) :
  1. découpe grossière par grille uniforme (marge + gouttière réglables) ;
  2. AUTO-TRIM par case : on recadre sur la boîte englobante de l'encre (pixels
     sombres), donc le croquis est recentré même si la case a un peu bougé ;
  3. composition sur fond crème à taille constante (rendu homogène).

Calibrage : si l'alignement est mauvais, jouer sur --margin / --gutter / --ink-threshold
et re-regarder la planche de contrôle. On peut re-trancher UNE planche sans toucher aux autres.

Usage :
  python3 poses/tools/slice_sheet.py --sheet planche.png --sheet-id sheet_07 \
      --manifest poses/tools/out/manifest.json
  python3 poses/tools/slice_sheet.py --sheet p.png --sheet-id sheet_07 \
      --manifest .../manifest.json --margin 0.03 --gutter 0.025 --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "web" / "static" / "poses" / "thumbs"

CREAM = (243, 237, 225)          # #f3ede1
CANVAS = (720, 540)              # taille de sortie constante (4:3)
INNER_PAD = 0.07                 # marge interne autour du croquis, en fraction


def _find_sheet(manifest: dict, sheet_id: str) -> dict:
    for s in manifest.get("sheets", []):
        if s["sheet_id"] == sheet_id:
            return s
    raise SystemExit(f"Planche '{sheet_id}' absente du manifeste. "
                     f"Disponibles : {', '.join(s['sheet_id'] for s in manifest.get('sheets', []))}")


def _coarse_cells(w, h, cols, rows, margin, gutter):
    """Rectangles grossiers (x0,y0,x1,y1) par case, ordre lecture."""
    mx, my = margin * w, margin * h
    gw, gh = gutter * w, gutter * h
    cell_w = (w - 2 * mx) / cols
    cell_h = (h - 2 * my) / rows
    rects = []
    for r in range(rows):
        for c in range(cols):
            x0 = mx + c * cell_w + gw / 2
            x1 = mx + (c + 1) * cell_w - gw / 2
            y0 = my + r * cell_h + gh / 2
            y1 = my + (r + 1) * cell_h - gh / 2
            rects.append((int(x0), int(y0), int(x1), int(y1)))
    return rects


def _ink_bbox(cell_rgb: Image.Image, threshold: int, keep_largest: bool = False):
    """
    Boîte englobante du DESSIN (pixels sombres). None si case vide.

    Détecte et IGNORE automatiquement un éventuel bandeau-titre en texte que
    Gemini aurait ajouté en haut de la case : une bande d'encre fine, large et
    située en haut, suivie d'un blanc. On distingue un titre (s'étale en largeur)
    d'une tête de personnage (étroite) pour ne jamais rogner le dessin.

    keep_largest : ne conserver que le plus gros bloc d'encre connexe (utile pour
    un PORTRAIT SOLO qui a débordé de sa case / capté un voisin). À NE PAS utiliser
    sur une scène de groupe (les personnages séparés seraient supprimés).
    """
    gray = np.asarray(cell_rgb.convert("L"))
    H, W = gray.shape
    inkmask = gray < threshold
    if not inkmask.any():
        return None

    if keep_largest:
        from scipy import ndimage
        lbl, n = ndimage.label(inkmask, structure=np.ones((3, 3)))
        if n >= 1:
            sizes = ndimage.sum(inkmask, lbl, range(1, n + 1))
            inkmask = lbl == (int(np.argmax(sizes)) + 1)

    ink_rows = inkmask.sum(axis=1) > max(3, int(W * 0.01))
    # bandes d'encre contiguës (verticalement)
    bands, start = [], None
    for i, v in enumerate(ink_rows):
        if v and start is None:
            start = i
        elif not v and start is not None:
            bands.append((start, i)); start = None
    if start is not None:
        bands.append((start, len(ink_rows)))
    if not bands:
        return None

    # titre présumé : 1re bande fine + haute + LARGE, suivie d'un blanc
    if len(bands) >= 2:
        t0, t1 = bands[0]
        band_h, gap = t1 - t0, bands[1][0] - t1
        top_cols = np.where(inkmask[t0:t1, :].any(axis=0))[0]
        top_width = (top_cols.max() - top_cols.min()) if len(top_cols) else 0
        if t0 < H * 0.30 and band_h < H * 0.16 and gap > H * 0.025 and top_width > W * 0.45:
            bands = bands[1:]  # -> on saute le titre

    y0, y1 = bands[0][0], bands[-1][1]
    cols = np.where(inkmask[y0:y1, :].any(axis=0))[0]
    if not len(cols):
        return None
    return int(cols.min()), int(y0), int(cols.max()) + 1, int(y1)


def _compose(crop: Image.Image) -> Image.Image:
    """Place le croquis recadré, centré, sur un canevas crème de taille constante."""
    canvas = Image.new("RGB", CANVAS, CREAM)
    max_w = int(CANVAS[0] * (1 - 2 * INNER_PAD))
    max_h = int(CANVAS[1] * (1 - 2 * INNER_PAD))
    cw, ch = crop.size
    scale = min(max_w / cw, max_h / ch)
    new = crop.resize((max(1, int(cw * scale)), max(1, int(ch * scale))), Image.LANCZOS)
    x = (CANVAS[0] - new.size[0]) // 2
    y = (CANVAS[1] - new.size[1]) // 2
    canvas.paste(new, (x, y))
    return canvas


def _qa_montage(thumbs, cols):
    """Assemble les vignettes produites en une planche de contrôle avec les ids."""
    if not thumbs:
        return None
    tw, th = CANVAS
    scale = 0.32
    cw, ch = int(tw * scale), int(th * scale)
    label_h = 20
    rows = (len(thumbs) + cols - 1) // cols
    board = Image.new("RGB", (cols * cw, rows * (ch + label_h)), (30, 33, 40))
    draw = ImageDraw.Draw(board)
    for i, (pid, img) in enumerate(thumbs):
        r, c = divmod(i, cols)
        x, y = c * cw, r * (ch + label_h)
        board.paste(img.resize((cw, ch), Image.LANCZOS), (x, y))
        draw.text((x + 4, y + ch + 4), pid, fill=(230, 200, 120))
    return board


def main():
    ap = argparse.ArgumentParser(description="Découpe une planche en vignettes.")
    ap.add_argument("--sheet", required=True, help="Image de la planche (png/jpg/webp).")
    ap.add_argument("--sheet-id", required=True, help="ex. sheet_07")
    ap.add_argument("--manifest", required=True, help="manifest.json de plan_sheets.py")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--margin", type=float, default=0.02, help="marge externe (fraction)")
    ap.add_argument("--gutter", type=float, default=0.02, help="gouttière (fraction)")
    ap.add_argument("--ink-threshold", type=int, default=200, help="seuil encre (0-255)")
    ap.add_argument("--pad", type=float, default=0.06, help="marge autour du croquis recadré (fraction de case)")
    ap.add_argument("--top-crop", type=float, default=0.0,
                    help="retire cette fraction du HAUT de chaque case avant recadrage "
                         "(utile si Gemini a ajouté un titre en texte)")
    ap.add_argument("--largest-blob", action="store_true",
                    help="ne garder que le plus gros bloc d'encre par case "
                         "(PORTRAITS SOLO uniquement — jamais sur des groupes)")
    ap.add_argument("--dry-run", action="store_true", help="ne fabrique QUE la planche de contrôle")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    sheet = _find_sheet(manifest, args.sheet_id)
    cols, rows = sheet["cols"], sheet["rows"]
    cells = sheet["cells"]

    img = Image.open(args.sheet).convert("RGB")
    w, h = img.size
    rects = _coarse_cells(w, h, cols, rows, args.margin, args.gutter)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = out_dir.parent / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    produced, empty = [], []
    for cell in cells:                       # ordre lecture = contrat de mapping
        k = cell["index"]
        if k >= len(rects):
            break
        x0, y0, x1, y1 = rects[k]
        coarse = img.crop((x0, y0, x1, y1))
        if args.top_crop > 0:                          # retire la bande de titre en haut
            cw0, ch0 = coarse.size
            coarse = coarse.crop((0, int(ch0 * args.top_crop), cw0, ch0))
        bbox = _ink_bbox(coarse, args.ink_threshold, keep_largest=args.largest_blob)
        if bbox is None:
            empty.append(cell["pose_id"])
            continue
        padx = int((x1 - x0) * args.pad)
        pady = int((y1 - y0) * args.pad)
        bx0 = max(0, bbox[0] - padx)
        by0 = max(0, bbox[1] - pady)
        bx1 = min(coarse.size[0], bbox[2] + padx)
        by1 = min(coarse.size[1], bbox[3] + pady)
        thumb = _compose(coarse.crop((bx0, by0, bx1, by1)))
        produced.append((cell["pose_id"], thumb))
        if not args.dry_run:
            thumb.save(out_dir / f"{cell['pose_id']}.webp", "WEBP", quality=88, method=6)

    board = _qa_montage(produced, cols)
    qa_path = qa_dir / f"qa_{args.sheet_id}.png"
    if board:
        board.save(qa_path)

    mode = "DRY-RUN (aucune vignette écrite)" if args.dry_run else "vignettes écrites"
    print(f"✅ {args.sheet_id} : {len(produced)} vignettes ({mode})")
    if not args.dry_run:
        print(f"   → {out_dir}/  ({', '.join(p for p, _ in produced[:6])}{'…' if len(produced) > 6 else ''})")
    print(f"   Planche de contrôle : {qa_path}")
    if empty:
        print(f"   ⚠️  {len(empty)} case(s) vue(s) VIDES (rien d'encré) : {', '.join(empty)}")
        print(f"      → si ce n'est pas normal, ajuste --margin/--gutter/--ink-threshold.")


if __name__ == "__main__":
    main()
