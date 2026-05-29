# Alexis Événementiel — migration cloud

Principe : on **clone l'app Fiche technique qui fonctionne** dans un nouveau dossier
`Alexis évènementiel`, et on ajoute une couche `storage` (local OU Dropbox), un
login, et un Dockerfile. **Toute la logique métier reste identique** (catalogue,
packs, prix, moins-value, devis, PDF).

Cette étape (Stage 1) assemble le projet et le fait tourner **en mode local**,
à l'identique de ton app actuelle, mais derrière un mot de passe. La bascule sur
Dropbox et le déploiement Render viennent ensuite.

---

## 1. Récupérer mes fichiers

Mets **tous les fichiers que je t'ai fournis** dans un dossier :

```
~/Downloads/alexis-overlay/
```

(storage.py, config_manager.py, storage_io.py, app.py, login.html, Dockerfile,
requirements.txt, Procfile, config.example.json, get_refresh_token.py,
README_MIGRATION.md, et .gitignore s'il est présent)

## 2. Assembler le projet

```bash
bash ~/Downloads/alexis-overlay/assemble.sh
```

Le script :
- clone `Fiche technique/` → `Alexis évènementiel/` (sans `.venv`, caches, `data/output`) ;
- dépose la couche cloud par-dessus (et remplace `web/app.py` par la version cloud).

## 3. Tester en local (identique à ton app actuelle, + login)

```bash
cd "/Volumes/CORSAIR/.CloudStorage/Data/Dropbox/Programmation/Python/Alexis évènementiel"
cp config.example.json config.json
```

Édite `config.json` :
- `storage_mode` : `"local"`
- `app_password` : ton mot de passe
- `local_data_dir` : déjà pré-rempli vers `…/Alexis évènementiel/data`

Puis :

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# WeasyPrint sur Mac a besoin des libs Homebrew :
brew install pango gdk-pixbuf libffi 2>/dev/null || true
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
python web/app.py
```

Ouvre <http://localhost:5001> → page de connexion → ton mot de passe →
tu retrouves **exactement** ton app (événements, catalogue, devis), mais lue/écrite
via la couche `storage`. Crée/édite un événement, génère un PDF de devis : tout doit
fonctionner comme avant. C'est le test « zéro régression ».

---

## Et après (prochaines étapes)

- **Stage 2** : je bascule les blueprints `catalogue_routes`, `devis_routes`,
  `parametres_routes` sur le `storage` (pour qu'ils marchent aussi en mode Dropbox),
  + archivage des PDF de devis dans `Dropbox/devis/`. On teste en mode `dropbox`.
- **Stage 3** : app Dropbox dédiée + refresh token (`get_refresh_token.py`),
  on copie `data/catalogue`, `data/defaults`, `data/events` dans le App folder
  (`Applications/alexis-evenementiel/`, **sans** le niveau `data/`), puis
  déploiement Render en Docker.

Disposition cible du App folder Dropbox :

```
Applications/alexis-evenementiel/
├── catalogue/   (equipements.json, packs.json, prestations.json, photos/)
├── defaults/    (prestataire.json)
├── events/
└── devis/       (archives PDF)
```
