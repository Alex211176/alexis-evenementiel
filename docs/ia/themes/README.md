# Exemples de thèmes — Photobooth IA

Rangement des visuels d'exemple affichés (à terme) sur la page `/photobooth-ia.html`.

## Convention : un dossier par thème

```
docs/ia/themes/<slug-du-theme>/
    apres.jpg      ← OBLIGATOIRE — le rendu généré par l'IA
    avant.jpg      ← optionnel — la photo d'origine (fond neutre)
    montage.jpg    ← optionnel — le montage avant/après composé
```

- **`<slug-du-theme>`** : minuscules, sans accent, avec tirets.
  Ex : `foot`, `retro-disco`, `cartoon`, `mariage`, `halloween`, `noel`.
- **Rôle du fichier** = son nom : `avant`, `apres` ou `montage`.
- **Formats** : `.jpg`, `.png` ou `.webp` (garder un seul fichier par rôle).
- Le **libellé affiché** (« Rétro & Disco »…) et l'ordre sont définis dans `themes.json`.

## Exemples

```
docs/ia/themes/foot/apres.jpg
docs/ia/themes/disco/avant.jpg
docs/ia/themes/disco/apres.jpg
docs/ia/themes/mariage/apres.jpg
docs/ia/themes/mariage/montage.jpg
```

## Pour ajouter un thème

1. Créer le dossier `docs/ia/themes/<slug>/` et y déposer au moins `apres.jpg`.
2. Ajouter une entrée dans `themes.json` (slug + libellé).

> Astuce : tu peux simplement m'envoyer les images en me disant
> « thème **foot** : voici l'avant et l'après » — je les range et je nomme pour toi.
