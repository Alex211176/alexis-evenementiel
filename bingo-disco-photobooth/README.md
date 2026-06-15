# Bingo Disco — Module photo IA (prototype)

Module « test » qui permet, **quand l'animateur le décide**, à un ou plusieurs
joueurs de prendre un selfie depuis leur téléphone, de l'envoyer à **Google
Gemini** pour le styliser selon un **thème** (ex. personnage Pixar + fond
disco), puis — en option — de l'**incruster dans un template**, de l'**imprimer
sur la DNP DS620** et de l'**afficher** sur l'écran de la soirée.

> ⚠️ **Prototype autonome.** Cette mini-app est volontairement séparée de tout
> autre code. Elle est destinée à vivre dans le dépôt `bingo-disco`
> (voir « Relocalisation » plus bas). Elle a été livrée ici parce que c'était le
> seul canal de push disponible dans la session Claude Code.

---

## Le pipeline

```
 📱 Joueur (selfie.html)                🎛️  Opérateur (console.html)        🖥️ Écran (screen.html)
        │  prend un selfie                       │                                   │
        ▼                                        │                                   │
   POST /api/capture  ───────────────────────►  apparaît dans la console            │
                                                 │  ① Générer ✨ (Gemini)             │
                                                 │  ② [option] Template               │
                                                 │  ③ [option] Imprimer 🖨️ (DNP)      │
                                                 │  ④ Envoyer à l'écran ──────────►  affichage animé
```

L'opérateur **ouvre/ferme** le mode photo et **choisit le thème** : tant que
c'est fermé, la page selfie affiche « pas encore ouvert ».

---

## Voir le workflow en 2 minutes (sur un seul Mac, sans téléphone)

Pour valider la boucle **captation → Gemini → écran** sans rien installer côté
téléphone :

```bash
cd bingo-disco-photobooth
cp .env.example .env        # mets ta GEMINI_API_KEY dedans (sinon : mode démo)
./run.sh                    # crée le venv, installe, démarre
```

1. Ouvre **deux onglets** : `http://localhost:5055/console` et `http://localhost:5055/screen`.
2. Dans la console, clique **« ＋ Photo test »** et choisis une photo (un portrait) → elle apparaît dans la grille. *(Pas besoin d'ouvrir le mode photo : le bouton test passe outre via le PIN.)*
3. Clique **« Générer ✨ »** : la photo part chez Gemini avec le prompt du thème choisi (menu en haut), l'image stylisée revient dans la 2ᵉ vignette.
4. Clique **« Écran 🖥️ »** : l'onglet `/screen` affiche l'image, animée, avec le prénom.

C'est exactement le workflow joueur, mais déclenché depuis la console. Côté
joueur réel, c'est la page `/selfie` (caméra) qui remplace l'étape 2.

> Sans clé Gemini, l'étape 3 renvoie ta photo avec un bandeau « MODE DÉMO » :
> tu vois quand même toute la mécanique (capture → traitement → retour écran).

## Lancer en local (MacBook)

```bash
cd bingo-disco-photobooth
./run.sh                    # raccourci tout-en-un
# — ou à la main —
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # puis édite .env (au minimum GEMINI_API_KEY)
set -a; source .env; set +a # charge les variables dans le shell
python app.py
```

Puis :

| Page | URL | Pour qui |
|------|-----|----------|
| Console opérateur | http://localhost:5055/console | toi (PIN) |
| Page selfie | http://localhost:5055/selfie | les joueurs |
| Écran | http://localhost:5055/screen | la TV / le vidéoproj |

### Mode DÉMO (sans clé)

Si `GEMINI_API_KEY` est vide, **tout le pipeline fonctionne sans appel réseau** :
Gemini est simulé et renvoie le selfie avec un bandeau « MODE DÉMO ». Idéal pour
tester l'enchaînement capture → écran → impression avant de consommer du crédit.

---

## Exposer aux téléphones via Cloudflare Tunnel

Les joueurs ne sont pas sur ton réseau : il faut exposer le serveur local. Le
plus simple, **Cloudflare Tunnel** (voir `tools/cloudflared-notes.md`) :

```bash
cloudflared tunnel --url http://localhost:5055
```

Tu obtiens une URL publique `https://xxxx.trycloudflare.com`. Donne
`…/selfie` aux joueurs (QR code), garde `…/console` pour toi, et mets
`…/screen` en plein écran sur la TV.

> Si tu as déjà un tunnel nommé + un domaine Cloudflare (ton « cloudflare »
> existant), ajoute juste une route `ingress` vers `http://localhost:5055`.

---

## Configuration (.env)

| Variable | Rôle |
|----------|------|
| `GEMINI_API_KEY` | clé Google AI Studio. Vide = mode démo. |
| `GEMINI_MODEL` | modèle image, défaut `gemini-2.5-flash-image`. |
| `OPERATOR_PIN` | code d'accès à la console (défaut `2468`). |
| `PORT` | port local (défaut `5055`). |
| `DNP_PRINTER` | nom de la file CUPS de la DS620 (`lpstat -p`). Vide = pas d'impression. |
| `DNP_MEDIA` | format papier (ex. `4x6`), optionnel. |
| `DNP_HOTFOLDER` | alternative : dossier surveillé par le logiciel DNP. |

### Styles (gestionnaire de prompts) : imposé ou libre

Les **styles** sont gérés depuis une **seule liste** (le gestionnaire de styles
de la console), persistée dans `data/prompts.json`. Chaque style = un **nom** +
un **prompt** envoyé à Gemini. Au premier lancement, la bibliothèque contient
Pixar, Disco années 80, Super-héros et Aquarelle (éditables / supprimables).

- **Menu « Style »** (en haut) : choisit le style **actif** ; le gestionnaire en
  dessous édite son prompt (Enregistrer / Nouveau / Supprimer).
- Bouton **« Style : imposé / libre »** :
  - **Imposé** (défaut) : le style actif s'applique à **tous** les joueurs.
  - **Libre** : chaque joueur choisit son style sur la page selfie (dans la même
    liste). Le style actif sert alors de **valeur par défaut**.

Tout est **persistant** (par événement). C'est cette unique liste qui sert à la
fois à l'opérateur et aux joueurs (plus de `themes.json` séparé).

### Texte d'événement / lieu (incrusté sur chaque photo)

Champ **« Texte événement / lieu »** dans la console : le texte saisi (ex.
« Mariage de Léa & Max — Château de Rabastens ») est incrusté **à l'identique
en bas de chaque photo générée**. Il est :

- **persistant** (survit à un redémarrage) — tu le règles une fois par soirée ;
- **rétro-appliqué** : si tu le modifies, toutes les photos déjà générées sont
  refaites avec le nouveau texte (rendu strictement identique partout) ;
- **combinable avec un template** : l'image finale = sortie Gemini → template
  (optionnel) → texte. Si ton template PNG contient déjà le texte, laisse le
  champ vide.

### Templates / bande photo

Dépose tes PNG dans `data/templates/`, puis choisis-en un dans le menu
**« Template »** de la console (persistant ; ré-appliqué à toutes les photos).

Deux modes, détectés automatiquement :

1. **Bande photo (2 emplacements)** — recommandé. Sur ton template, marque les
   zones photo avec **deux aplats de couleur** :
   - **rouge** = emplacement 1 → la **photo originale** ;
   - **vert** = emplacement 2 → la **photo modifiée (Gemini)**.
   Le code détecte ces zones (à n'importe quelle résolution) et y colle les
   photos (cadrage *cover*). Tout le décor autour (cadres, fond, titres) est
   conservé. C'est la convention de la « trame nue » fournie.
2. **Cadre simple** — un PNG sans repère couleur : il est superposé à l'image
   générée (utile pour un logo/cadre avec découpe transparente).

> Astuce : pour la bande photo, les deux repères doivent être des aplats de
> rouge vif et de vert vif distincts. Le titre/les noms peuvent être dessinés
> directement dans le PNG, autour des emplacements.

### Impression DNP DS620

- **CUPS** : installe la DS620, repère son nom via `lpstat -p`, mets-le dans
  `DNP_PRINTER`. Le bouton « Imprimer » lance `lp -d <file> <image>`.
- **Hot folder** : si tu utilises le *Hot Folder Print* DNP, mets le dossier
  surveillé dans `DNP_HOTFOLDER` ; on y copie le JPEG.

---

## Intégrer à TES écrans existants (screen.html / player.html)

Le `screen.html` fourni est un exemple plein écran. Pour brancher la diffusion
photo sur **tes** pages existantes, ajoute simplement un abonnement SSE :

```js
const es = new EventSource('https://<ton-domaine>/events');
es.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.event === 'screen_show' && m.data.generated_url) {
    // affiche m.data.generated_url (+ m.data.player_name) dans ta scène
    montrerPhotoJoueur(m.data.generated_url, m.data.player_name);
  }
};
```

Aucune dépendance : c'est du Server-Sent Events natif. `player.html` peut
s'abonner de la même façon (ou ignorer ces events s'il ne veut afficher que la
musique).

---

## Endpoints (référence rapide)

| Méthode | Route | Accès | Rôle |
|---------|-------|-------|------|
| POST | `/api/capture` | joueur | envoyer un selfie (si mode ouvert) |
| GET | `/api/state` | public | état complet (photos, réglages, thèmes) |
| GET | `/events` | public | flux SSE temps réel |
| POST | `/api/mode` | PIN | ouvrir/fermer le mode photo |
| POST | `/api/style` | PIN | choisir le style actif (id de la bibliothèque) |
| POST | `/api/style_mode` | PIN | basculer style imposé / libre |
| POST | `/api/prompts/save` | PIN | créer / mettre à jour un style |
| POST | `/api/prompts/delete` | PIN | supprimer un style |
| POST | `/api/model` | PIN | changer le modèle Gemini (Nano Banana / 2 / Pro) |
| POST | `/api/event_text` | PIN | définir le texte incrusté (événement / lieu) |
| POST | `/api/active_template` | PIN | choisir le template / la bande photo |
| POST | `/api/generate` | PIN | styliser via Gemini |
| POST | `/api/screen` | PIN | envoyer (ou retirer) une photo de l'écran |
| POST | `/api/print` | PIN | imprimer sur la DNP |

Les routes PIN attendent l'en-tête `X-Operator-Pin`.

---

## Relocalisation vers le dépôt `bingo-disco`

Ce dossier a été poussé sur la branche `claude/bingo-disco-photo-gemini-yry8er`
du dépôt `alexis-evenementiel` (seul canal disponible). Pour le mettre dans son
vrai dépôt depuis ton Mac :

```bash
# 1. Crée le dépôt sur github.com (bouton "New", nom: bingo-disco, privé).

# 2. Récupère ce dossier depuis la branche :
git clone https://github.com/Alex211176/alexis-evenementiel.git /tmp/ae
cd /tmp/ae && git checkout claude/bingo-disco-photo-gemini-yry8er

# 3. Copie le dossier dans ton projet bingo-disco local, à côté de ton code existant :
cp -R bingo-disco-photobooth ~/chemin/vers/bingo-disco/

# 4. Dans bingo-disco : git add / commit / push vers le nouveau dépôt.
```

(Ton code bingo disco actuellement en local sur le Mac n'est pas accessible
depuis l'environnement cloud : c'est à toi de le pousser sur `bingo-disco`.)

---

## Limites du prototype (assumées)

- État **en mémoire** : un redémarrage du serveur vide la liste des photos
  (les fichiers restent sur disque). Suffisant pour une soirée.
- Mono-process (serveur de dev Flask). Pour la prod : `gunicorn` + un vrai
  bus d'events, ou conserver le tunnel Cloudflare devant le dev server.
- Pas de modération automatique des photos : c'est l'opérateur qui valide
  avant l'écran (rien n'arrive à l'écran sans clic).
- Le `screen.html` fourni est un exemple ; l'intégration à tes pages réelles
  se fait via SSE (voir plus haut).
