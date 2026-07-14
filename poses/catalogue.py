"""
poses/catalogue.py — Catalogue imprimable des poses (à présenter aux mariés).

PDF A4 paginé : couverture + une section par phase (vignette + titre + description,
3 cartes par ligne). Sert de « book » que le photographe montre aux couples.

Rendu avec reportlab (pur Python, aucune dépendance système — fonctionne en local
comme sur Render). Les vignettes web/static/poses/thumbs/<id>.webp sont converties
en PNG à la volée ; une pose sans vignette affiche « croquis à venir ».
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak,
)

from poses.loader import load_library

GOLD = colors.HexColor("#c9a24b")
CREAM = colors.HexColor("#f3ede1")
INK = colors.HexColor("#2b2b2b")
GREY = colors.HexColor("#7a7a7a")

_TITLE = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=8, leading=9.5, textColor=INK)
_DESC = ParagraphStyle("d", fontName="Helvetica", fontSize=6.6, leading=8, textColor=GREY)
_PH = ParagraphStyle("ph", fontName="Helvetica", fontSize=15, textColor=INK)
_COVER_EYE = ParagraphStyle("ce", fontName="Helvetica", fontSize=11, alignment=TA_CENTER,
                            textColor=GOLD, spaceAfter=16, tracking=3)
_COVER_H1 = ParagraphStyle("ch", fontName="Helvetica", fontSize=34, alignment=TA_CENTER,
                           textColor=INK, spaceAfter=14)
_COVER_P = ParagraphStyle("cp", fontName="Helvetica", fontSize=11.5, alignment=TA_CENTER,
                          textColor=GREY, leading=17)

_COLS = 3
_CARD_W = 168          # points
_IMG_W = 150


def _thumb_flowable(thumbs_dir: Path, pose_id: str):
    p = thumbs_dir / f"{pose_id}.webp"
    if p.exists():
        try:
            im = PILImage.open(p).convert("RGB")
            if im.width > 500:                      # allège le PDF (impression ~240 dpi)
                im = im.resize((500, round(500 * im.height / im.width)), PILImage.LANCZOS)
            buf = io.BytesIO(); im.save(buf, "PNG", optimize=True); buf.seek(0)
            w, h = im.size
            return RLImage(buf, width=_IMG_W, height=_IMG_W * h / w)
        except Exception:  # noqa: BLE001
            pass
    return Paragraph("<i>croquis à venir</i>", _DESC)


def _card(thumbs_dir: Path, pose: dict):
    inner = Table(
        [[_thumb_flowable(thumbs_dir, pose["id"])],
         [Paragraph(pose["title"], _TITLE)],
         [Paragraph(pose["desc"], _DESC)]],
        colWidths=[_CARD_W - 8],
    )
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), CREAM),
        ("BOX", (0, 0), (0, 0), 0.5, colors.HexColor("#e6e0d2")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 1), (0, 1), 4),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return inner


def _chunk(seq, n):
    for i in range(0, len(seq), n):
        row = list(seq[i:i + n])
        row += [""] * (n - len(row))   # complète la dernière ligne
        yield row


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#b0a68f"))
    canvas.drawCentredString(A4[0] / 2, 10 * mm, str(doc.page))
    canvas.restoreState()


def build_story(thumbs_dir):
    thumbs_dir = Path(thumbs_dir)
    lib = load_library()
    phases = lib["phases"]
    total = sum(len(p["poses"]) for p in phases)

    story = [
        Spacer(1, 70 * mm),
        Paragraph("ALEXIS ÉVÉNEMENTIEL", _COVER_EYE),
        Paragraph("Vos poses de mariage", _COVER_H1),
        Spacer(1, 6 * mm),
        Paragraph(
            f"Un répertoire de {total} poses, organisé selon le déroulé d'une journée "
            "de mariage — des préparatifs à la soirée dansante.<br/>Parcourez, repérez "
            "celles qui vous ressemblent, et nous les réaliserons le jour J.", _COVER_P),
        PageBreak(),
    ]

    for phase in phases:
        head = Table(
            [[Paragraph(f"<font color='#c9a24b'>{phase['order']:02d}</font>  "
                        f"{phase.get('icon','')}  {phase['label']}", _PH),
              Paragraph(f"<font color='#a59a80'>{phase.get('moment','').upper()}</font>",
                        ParagraphStyle("m", fontName="Helvetica", fontSize=8, alignment=2))]],
            colWidths=[380, 130])
        head.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#e3ddcf")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(head)
        story.append(Spacer(1, 5 * mm))

        cards = [_card(thumbs_dir, pose) for pose in phase["poses"]]
        grid = Table(list(_chunk(cards, _COLS)), colWidths=[_CARD_W] * _COLS)
        grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(grid)
        story.append(PageBreak())

    return story


def render_pdf(thumbs_dir, out_path) -> str:
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
        title="Poses de mariage — Alexis Événementiel",
    )
    doc.build(build_story(thumbs_dir), onFirstPage=_footer, onLaterPages=_footer)
    return str(out_path)
