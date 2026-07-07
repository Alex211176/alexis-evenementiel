#!/bin/bash
# Double-clic = publie les nouveaux exemples Photobooth IA sur le site.
# (scanne les dossiers, met à jour le registre, envoie sur GitHub)

REPO="/Users/macbookpro/Desktop/alexis-evenementiel"
cd "$REPO" || { echo "Depot introuvable : $REPO"; echo; read -n1 -s -p "Touche pour fermer..."; exit 1; }

echo "============================================"
echo "   Publication Photobooth IA - exemples"
echo "============================================"
echo
echo "> Lecture des dossiers Photobooth IA + mise a jour du registre..."
python3 scripts/rebuild_ia_themes.py || { echo "ERREUR lors du scan IA."; echo; read -n1 -s -p "Touche pour fermer..."; exit 1; }
echo "> Lecture des galeries simples (lunettes 3D, etc.)..."
python3 scripts/rebuild_simple_galleries.py || { echo "ERREUR lors du scan galeries."; echo; read -n1 -s -p "Touche pour fermer..."; exit 1; }
echo
echo "> Enregistrement..."
git config core.ignorecase false
git add -A docs/ia/themes/ docs/lunettes-3d/ docs/kids-booth/
if git diff --cached --quiet; then
  echo "Rien de nouveau a publier."
  echo; read -n1 -s -p "Touche pour fermer..."; exit 0
fi
git commit -q -m "Photobooth IA : mise a jour des exemples (script)"

echo "> Synchronisation + envoi sur le site..."
git fetch origin main -q
if ! git rebase origin/main >/dev/null 2>&1; then
  git rebase --abort >/dev/null 2>&1
  echo "ATTENTION : conflit de synchro. Ne ferme pas, previens Claude."
  echo; read -n1 -s -p "Touche pour fermer..."; exit 1
fi
if git push origin main >/dev/null 2>&1; then
  echo
  echo "OK - Publie ! Le site (alexisevenementiel.fr) se met a jour dans 1-2 min."
else
  echo
  echo "ECHEC de l'envoi (connexion GitHub ?). Reessaie ou previens Claude."
fi
echo
read -n1 -s -p "Termine - appuie sur une touche pour fermer..."
