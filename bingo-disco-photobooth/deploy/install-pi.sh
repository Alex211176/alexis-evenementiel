#!/usr/bin/env bash
# Installation du module photobooth sur Raspberry Pi (Raspberry Pi OS).
# - dépendances système (Python venv, Pillow, CUPS + pilote DNP/Gutenprint)
# - environnement Python + dépendances du projet
# - service systemd : démarrage automatique au boot, relance si crash
#
# Usage :  cd bingo-disco-photobooth && bash deploy/install-pi.sh
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(whoami)"
echo "→ Dossier app : $APP_DIR"
echo "→ Utilisateur : $USER_NAME"

echo "→ Installation des dépendances système…"
sudo apt-get update
sudo apt-get install -y \
  python3-venv python3-pip \
  libjpeg-dev zlib1g-dev libfreetype6-dev \
  cups printer-driver-gutenprint
# Droit d'administrer les imprimantes (CUPS) sans sudo.
sudo usermod -aG lpadmin "$USER_NAME" || true

echo "→ Environnement Python + dépendances…"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "→ Fichier .env…"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "  .env créé depuis .env.example — PENSE à y mettre ta clé GEMINI_API_KEY."
fi

echo "→ Service systemd (démarrage auto)…"
sudo tee /etc/systemd/system/bingo-photobooth.service >/dev/null <<EOF
[Unit]
Description=Bingo Disco Photobooth (module photo IA)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/app.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable bingo-photobooth.service
sudo systemctl restart bingo-photobooth.service

IP=$(hostname -I | awk '{print $1}')
echo
echo "✅ Installé. Le photobooth démarre maintenant au boot."
echo "   Console : http://$IP:5055/console"
echo "   Selfie  : http://$IP:5055/selfie"
echo "   Écran   : http://$IP:5055/screen"
echo
echo "Prochaines étapes :"
echo "  1) Édite $APP_DIR/.env (clé Gemini, OPERATOR_PIN, DNP_PRINTER) puis :"
echo "       sudo systemctl restart bingo-photobooth"
echo "  2) Cloudflare Tunnel + impression DNP : voir docs/RASPBERRY_PI.md"
echo "  Logs en direct : journalctl -u bingo-photobooth -f"
