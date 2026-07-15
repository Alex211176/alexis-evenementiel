#!/bin/bash
# Publication NON-INTERACTIVE du Photobooth IA.
#   rebuild registres -> commit/push GitHub (Render) -> sync des visuels vers la borne.
# Utilisé par :
#   - Desktop/Publier-Photobooth-IA.command  (double-clic, wrapper interactif)
#   - l'agent launchd (bouton « Publier » dans la console borne)
# Sortie : log humain sur stdout ; dernière ligne "PUBLISH_SUMMARY: ..." ; exit 0 (ok) / 1 (échec).

set -o pipefail
REPO="/Users/macbookpro/Desktop/alexis-evenementiel"
BORNE_SYNC="/Volumes/CORSAIR/.CloudStorage/Data/Dropbox/Programmation/Borne impression diaporama/scripts/sync_borne_themes.py"

fail(){ echo "PUBLISH_SUMMARY: $1"; exit 1; }

cd "$REPO" || fail "dépôt site introuvable"

echo "> Récupération des montages avant/après CONSENTIS depuis la borne…"
python3 scripts/pull_consented_montages.py || echo "  (pull ignoré — borne hors-ligne)"

echo "> Reconstruction des registres (thèmes IA + galeries)…"
python3 scripts/rebuild_ia_themes.py       || fail "rebuild themes.json a échoué"
python3 scripts/rebuild_simple_galleries.py || fail "rebuild galeries a échoué"

git config core.ignorecase false
git add -A docs/ia/themes/ docs/lunettes-3d/ docs/kids-booth/ docs/exemples/
site_changed=0
if git diff --cached --quiet; then
  echo "> Rien de nouveau côté site."
else
  git commit -q -m "Photobooth IA : mise à jour des exemples (bouton console)" || fail "commit échoué"
  git fetch origin main -q
  # Push direct (fast-forward) d'abord : le cas courant, et ça NE touche PAS l'arbre de
  # travail (donc un web/app.py modifié non lié ne bloque rien). Rebase seulement si
  # origin a divergé, avec autoStash pour survivre à des changements non commités.
  if ! git push origin main >/dev/null 2>&1; then
    if ! git -c rebase.autoStash=true rebase origin/main >/dev/null 2>&1; then
      git rebase --abort >/dev/null 2>&1
      fail "conflit git (rebase) — à résoudre à la main"
    fi
    git push origin main >/dev/null 2>&1 || fail "push GitHub échoué (connexion ? identifiants ?)"
  fi
  site_changed=1
  echo "> Site publié (GitHub -> Render, en ligne dans 1-2 min)."
fi

echo "> Synchronisation des visuels vers la borne…"
borne_out="$(python3 "$BORNE_SYNC" 2>&1)"
echo "$borne_out"

# Résumé compact renvoyé à la console borne.
if [ "$site_changed" = "1" ]; then sum="site publié"; else sum="site déjà à jour"; fi
if echo "$borne_out" | grep -q "Borne joignable"; then sum="$sum, borne à jour"; else sum="$sum, borne hors-ligne"; fi
echo "PUBLISH_SUMMARY: $sum"
exit 0
