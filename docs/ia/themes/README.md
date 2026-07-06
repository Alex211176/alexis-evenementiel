# Exemples Photobooth IA — thèmes & montages

Contenu affiché sur `/photobooth-ia.html` (galerie de sliders avant/après) et sur
les fiches détail `/ia/montage.html?theme=<t>&montage=<m>`.

## Structure : thème → montage → photos

```
docs/ia/themes/<theme>/<montage>/
    avant.jpg       ← photo d'origine (fond neutre)
    apres.jpg       ← rendu IA (sert au comparateur avant/après)
    montage.jpg     ← montage composé (optionnel)
    extra-01.jpg    ← photos en plus liées au montage (optionnel)
    extra-02.jpg
```

- **`<theme>`** : slug minuscule-sans-accent-avec-tirets (`disco`, `mariage`, `foot`…).
- **`<montage>`** : slug d'un exemple précis (`couple`, `soiree-paul`…). Un thème peut en avoir plusieurs.
- **Rôle = nom de fichier** : `avant`, `apres`, `montage`, puis `extra-XX` pour le reste.

## Le registre `themes.json`

```json
{
  "slug": "disco", "label": "Rétro & Disco",
  "montages": [
    { "slug": "couple", "label": "Couple pailleté",
      "avant": "avant.jpg", "apres": "apres.jpg",
      "montage": "montage.jpg", "extras": ["extra-01.jpg", "extra-02.jpg"] }
  ]
}
```

- Chaque rôle = **nom de fichier** ou `null`. `extras` = liste (peut être vide).
- Un montage n'apparaît en slider que s'il a **`avant` ET `apres`**.
- La fiche détail affiche **toutes** les photos du montage (avant, après, montage, extras).

## Pour ajouter un montage

1. Créer `docs/ia/themes/<theme>/<montage>/` et y déposer les images.
2. Ajouter le montage dans `themes.json` (sous le bon thème).

> Le plus simple : envoie-moi les photos en disant *« thème disco, montage “soirée Paul” : avant, après, + 2 photos »* — je range et je complète le registre.
