# Fiche Technique

Générateur de fiches techniques (HTML + PDF) pour les prestations d'Alexis Arokiassamy (DJ-animateur, Bingo Disco, sonorisation événementielle).

Architecture pensée pour accueillir ultérieurement un **module devis** sans refonte.

---

## Installation

Prérequis : Python 3.11+, macOS / Linux / Windows.

```bash
cd "/Volumes/CORSAIR/.CloudStorage/Data/Dropbox/Programmation/Python/Fiche technique"
python -m venv .venv
source .venv/bin/activate           # macOS / Linux
# .venv\Scripts\activate            # Windows
pip install -r requirements.txt
```

L'installation de **WeasyPrint** (export PDF) nécessite quelques bibliothèques système sur macOS :

```bash
brew install pango gdk-pixbuf libffi
```

---

## Utilisation

### A — En ligne de commande

```bash
# HTML seul
python scripts/generate.py data/events/exemple_mariage.json

# HTML + PDF
python scripts/generate.py data/events/exemple_mariage.json --pdf

# Avec ouverture automatique du résultat
python scripts/generate.py data/events/exemple_mariage.json --pdf --open

# Sortie dans un dossier custom
python scripts/generate.py data/events/exemple_mariage.json --pdf -o ~/Desktop/
```

### B — Interface web locale

```bash
python web/app.py
# Ouvrir http://localhost:5001
```

Liste les événements, formulaire d'édition, aperçu en iframe, export PDF en un clic.

---

## Structure du projet

```
Fiche technique/
├── README.md
├── requirements.txt
├── Makefile                       # raccourcis pratiques
│
├── fiches/                        # module métier (cœur)
│   ├── __init__.py
│   ├── config.py                  # chargement & fusion JSON
│   ├── renderer.py                # rendu Jinja2
│   ├── exporter.py                # export PDF WeasyPrint
│   ├── templates/
│   │   └── fiche_technique.html.j2
│   └── static/
│       ├── fonts/                 # ← TA POLICE CUSTOM ICI quand prête
│       ├── images/                # ← TON LOGO ICI quand prêt
│       └── css/                   # (réservé, CSS actuellement inline)
│
├── data/
│   ├── defaults/
│   │   └── prestataire.json       # SIRET, matériel par défaut, etc.
│   ├── events/                    # un fichier .json par événement
│   │   ├── exemple_mariage.json
│   │   └── exemple_soiree.json
│   └── output/                    # HTML/PDF générés (gitignore)
│
├── web/                           # UI Flask locale
│   ├── app.py
│   ├── templates/
│   └── static/
│
├── scripts/
│   └── generate.py                # CLI principal
│
└── docs/
    ├── ARCHITECTURE.md
    └── BRANDING.md                # comment intégrer logo + police custom
```

---

## Personnalisation du document

Trois niveaux :

1. **Défauts permanents** (SIRET, matériel par défaut, barème d'annulation) → `data/defaults/prestataire.json`
2. **Spécifique à un événement** (nom, lieu, outdoor, matériel ponctuel) → `data/events/*.json`
3. **Identité visuelle** (logo, police, couleur d'accent) → voir `docs/BRANDING.md`

La fusion est récursive : un événement ne renseigne **que** ce qui diffère des défauts.

---

## Roadmap

- ✅ **v1.0** — Fiches techniques HTML/PDF, CLI + UI web, paramétrage JSON
- ⏳ **v1.1** — Logo + police custom (slots prêts, en attente des assets)
- ⏳ **v2.0** — Module devis (lignes, calcul TTC, conditions de règlement)
- ⏳ **v2.1** — Numérotation auto des références
- ⏳ **v2.2** — Export depuis Bingo Disco (intégration avec l'admin existant)
