#!/usr/bin/env bash
# Lancement en une commande du module photo Bingo Disco.
# Crée le venv au besoin, installe les dépendances, charge .env, démarre le serveur.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "→ Création de l'environnement Python…"
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

if [ -f .env ]; then
  set -a; source .env; set +a
else
  echo "⚠️  Pas de .env : démarrage en MODE DÉMO (copie .env.example en .env pour la vraie clé Gemini)."
fi

python app.py
