# Architecture — Fiche Technique

## Principe directeur

**Séparation stricte entre données, présentation et orchestration.**

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  data/           │    │  fiches/         │    │  scripts/ + web/ │
│                  │    │                  │    │                  │
│  defaults/       │ ──▶│  config.py       │ ──▶│  generate.py     │
│  events/         │    │  renderer.py     │    │  app.py (Flask)  │
│  output/         │    │  exporter.py     │    │                  │
│  (JSON)          │    │  templates/      │    │  (orchestration) │
└──────────────────┘    └──────────────────┘    └──────────────────┘
     données                  métier                  interface
```

## Modules

### `fiches/` — cœur métier (réutilisable)

C'est ici que vit la logique. **Importable depuis n'importe quel script Python**, y compris à terme depuis Bingo Disco.

- `config.py` : `load_config()`, `deep_merge()`, `validate()`, `ConfigError`
- `renderer.py` : `render_html()` — Jinja2 only, aucune dépendance lourde
- `exporter.py` : `export_pdf()` — WeasyPrint en import paresseux
- `templates/` : templates Jinja2 (un seul pour l'instant)
- `static/` : ressources servies par le template (fonts, images, css)

### `data/` — données pures (zéro code)

- `defaults/prestataire.json` : valeurs fixes du prestataire (SIRET, RC, matériel par défaut, barème d'annulation, identité visuelle)
- `events/` : un JSON par événement, **ne contient que les overrides** (nom, lieu, matériel ponctuel)
- `output/` : HTML et PDF générés (gitignore)

### `scripts/` — CLI

- `generate.py` : interface en ligne de commande, parse args, appelle `fiches`

### `web/` — UI Flask locale

- `app.py` : Flask app
- `templates/` : templates Jinja2 de l'UI (distincts des templates de fiches)
- `static/admin.css` : CSS de l'UI

**Important** : les templates de fiches et ceux de l'admin Flask sont **séparés** dans des dossiers distincts pour éviter toute collision.

---

## Fusion des données (deep_merge)

Comportement :

| Type de valeur | Comportement |
|----------------|--------------|
| Scalaire (string, int, bool, null) | **Remplacement** : event écrase defaults |
| Dictionnaire | **Fusion récursive** : on descend dans la structure |
| Liste | **Remplacement intégral** : on prend la liste de l'event si présente |
| Clé commençant par `_` | **Ignorée** (utilisée pour les docstrings JSON) |

Pourquoi remplacer les listes plutôt que les concaténer ? Parce que pour le matériel, l'utilisateur veut souvent **redéfinir** ce qui est fourni pour un événement spécifique, pas ajouter à une liste générique.

---

## Ajout futur du module devis

Quand le module devis arrivera, l'architecture prévoit :

```
fiche_technique_project/
├── fiches/            (existant)
├── devis/             ← NOUVEAU module métier, indépendant
│   ├── __init__.py
│   ├── config.py      (peut réutiliser deep_merge depuis fiches)
│   ├── calculator.py  (calcul HT/TTC, totaux)
│   ├── renderer.py    (Jinja2 propre au devis)
│   ├── templates/
│   │   └── devis.html.j2
│   └── static/
│
├── data/
│   ├── defaults/
│   │   └── prestataire.json   (partagé, c'est la même structure)
│   ├── catalogue/             ← NOUVEAU : catalogue de prestations
│   │   └── prestations.json
│   ├── devis/                 ← NOUVEAU : un fichier par devis
│   └── events/                (existant)
│
├── scripts/
│   ├── generate.py       (fiches)
│   └── generate_devis.py ← NOUVEAU
│
└── web/
    └── app.py            (étendu avec les routes /devis/*)
```

L'interface Flask gagnera un onglet "Devis" déjà esquissé (greyed out) dans la nav top.

Aucune refonte de `fiches/` ne sera nécessaire — les deux modules vivront en parallèle.

---

## Choix techniques

| Choix | Raison |
|-------|--------|
| **Jinja2** (et pas string `.format()`) | Logique conditionnelle (section intempéries), boucles (matériel) |
| **JSON** (et pas YAML/TOML) | Lisible, éditable depuis n'importe où, compatible JS si export web futur |
| **WeasyPrint** (et pas pdfkit/reportlab) | CSS-first, contrôle visuel total, supporte les @font-face |
| **Flask** (et pas FastAPI) | Tu l'utilises déjà dans Bingo Disco, écosystème familier |
| **Import paresseux de WeasyPrint** | Permet d'utiliser le module HTML-only sans les deps système de Pango |
| **Pas de base de données** | Un événement = un fichier JSON, versionnable Git, éditable à la main |
