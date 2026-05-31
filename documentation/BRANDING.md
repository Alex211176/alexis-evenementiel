# Branding — intégration du logo et de la police custom

Le template est prêt à accueillir ton logo et ta police custom quand ils seront disponibles. **Aucune modification du code n'est nécessaire** : tout passe par `data/defaults/prestataire.json`.

---

## 1. Logo

### Étapes

1. Dépose le fichier dans `fiches/static/images/`. Recommandations :
   - Format **SVG** de préférence (scalable, pour PDF haute qualité)
   - Sinon **PNG** avec transparence, ≥ 256 px de haut
   - Nom de fichier sans espaces ni accents (ex : `logo.svg`, `logo-bingo-disco.png`)

2. Édite `data/defaults/prestataire.json`, section `prestataire.brand` :

   ```json
   "brand": {
       "logo_file": "logo.svg",
       "accent_color": "#B45309",
       "accent_soft": "#FEF3C7"
   }
   ```

3. C'est tout. Le logo s'affichera automatiquement à gauche du nom dans l'en-tête.

### Sortir le logo de l'en-tête

Pour le retirer, repasse `logo_file` à `null` :
```json
"logo_file": null
```

---

## 2. Police custom

### Étapes

1. Convertis ta police en **WOFF2** (meilleur ratio compression/qualité). Outils :
   - [Transfonter](https://transfonter.org) (en ligne, gratuit)
   - `fonttools` en CLI : `pyftsubset MaPolice.ttf --flavor=woff2 --output-file=ma-police.woff2`

2. Dépose le(s) fichier(s) dans `fiches/static/fonts/`. Exemple :
   ```
   fiches/static/fonts/
   ├── arokiassamy-display.woff2
   └── arokiassamy-body.woff2     ← optionnel
   ```

3. Édite `data/defaults/prestataire.json`, section `prestataire.fonts` :

   ```json
   "fonts": {
       "custom": true,
       "display_name": "Arokiassamy Display",
       "display_file": "arokiassamy-display.woff2",
       "display_format": "woff2",
       "body_name": "Arokiassamy Body",
       "body_file": "arokiassamy-body.woff2",
       "body_format": "woff2"
   }
   ```

4. C'est tout. Le template chargera ta police via `@font-face` et l'utilisera pour tous les titres (`--font-display`) et le corps de texte (`--font-body`).

### Une seule police pour tout

Si tu n'as qu'une seule police custom (ex. pour les titres uniquement, et tu veux garder une sans-serif pour le corps), laisse `body_file` à `null` :

```json
"fonts": {
    "custom": true,
    "display_name": "Arokiassamy Display",
    "display_file": "arokiassamy-display.woff2",
    "display_format": "woff2",
    "body_name": null,
    "body_file": null,
    "body_format": null
}
```

Dans ce cas, le corps utilisera Google Fonts (IBM Plex Sans) comme avant. Si tu veux que le corps utilise aussi ta police custom (mais comme une seule famille), mets `body_name` égal à `display_name` et laisse `body_file` à null — le CSS fera le fallback proprement.

### Revenir aux Google Fonts

```json
"fonts": { "custom": false, ... }
```

Le template rechargera Fraunces + IBM Plex Sans.

---

## 3. Couleur d'accent

La couleur d'accent (orange/ambre par défaut) se règle dans `prestataire.brand` :

```json
"brand": {
    "accent_color": "#B45309",
    "accent_soft": "#FEF3C7"
}
```

`accent_color` = teinte forte (bordures, sections, micro-typo)
`accent_soft` = teinte pâle (fond du callout)

### Suggestions cohérentes

| Identité visuelle | accent_color | accent_soft |
|-------------------|--------------|-------------|
| Ambre (actuel) | `#B45309` | `#FEF3C7` |
| Rouge brique | `#B91C1C` | `#FEE2E2` |
| Bleu encre | `#1E40AF` | `#DBEAFE` |
| Vert émeraude | `#047857` | `#D1FAE5` |
| Violet profond | `#6D28D9` | `#EDE9FE` |

---

## 4. Vérification

Après modification du JSON :

```bash
# Régénère l'exemple
make example

# Ou via la web UI
make web
# puis ouvre http://localhost:5001 et clique "Aperçu" sur n'importe quel événement
```

Si la police ne s'affiche pas dans le PDF, vérifie que :
- Le chemin du fichier est bien sous `fiches/static/fonts/`
- Le format déclaré (`woff2`) correspond à l'extension réelle
- WeasyPrint peut accéder au fichier (pas de droits exotiques)

Pour un debug avancé, lance WeasyPrint avec `--verbose` en CLI.
