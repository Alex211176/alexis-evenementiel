# Photobooth sur Raspberry Pi (autonome)

Le Pi héberge le « moteur » (serveur Flask). Les invités prennent leur selfie
depuis **leur téléphone en 4G** via un **tunnel Cloudflare**, une **tablette
dédiée** sert de console/écran, et l'impression part sur la **DNP DS620** en USB.

```
[Tél. invités en 4G] ── Internet ──► Cloudflare ──► tunnel ──┐
[Tablette console/écran] ── Wi-Fi/LAN ──────────────────────►│
                                                             ▼
                                            [Raspberry Pi : app.py (Flask)]
                                                  │ Internet ─► API Gemini
                                                  └ USB ─► imprimante DNP DS620
```

> Le Pi a juste besoin d'**Internet** (pour Gemini). Tout le reste est local.

## Matériel conseillé
- **Raspberry Pi 4 (4 Go) ou Pi 5**, Raspberry Pi OS **64-bit**.
- Carte SD rapide (ou SSD USB), alimentation officielle.
- Imprimante **DNP DS620** (USB) + papier/ruban.
- Une tablette (n'importe quel navigateur) pour la console et/ou l'écran.

---

## 1. Récupérer le projet sur le Pi
```bash
cd ~
git clone https://github.com/Alex211176/alexis-evenementiel.git
cp -r alexis-evenementiel/bingo-disco-photobooth ~/bingo-disco-photobooth
```
*(ou copie le dossier `bingo-disco-photobooth` par clé USB / scp.)*

## 2. Installer (venv + service auto + dépendances impression)
```bash
cd ~/bingo-disco-photobooth
bash deploy/install-pi.sh
```
Le script installe tout, crée le service **systemd** (démarrage au boot, relance
auto) et affiche les URL locales. Logs en direct :
```bash
journalctl -u bingo-photobooth -f
```

## 3. Configurer le `.env`
```bash
nano ~/bingo-disco-photobooth/.env
```
Renseigne au minimum :
```
GEMINI_API_KEY=AIza...        # ta clé
OPERATOR_PIN=2468             # change-le
TEMPLATES_DIR=                # vide = data/templates ; ou un dossier à toi
DNP_PRINTER=                  # nom CUPS de la DS620 (voir étape 5)
```
Puis applique :
```bash
sudo systemctl restart bingo-photobooth
```

## 4. Tunnel Cloudflare (accès 4G des invités, URL stable)

Installe `cloudflared` (paquet ARM) :
```bash
# Raspberry Pi OS 64-bit (arm64) :
curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb
```

**Tunnel nommé** (recommandé : l'URL ne change pas, tu peux imprimer le QR avant) :
```bash
cloudflared tunnel login                      # autorise ton domaine Cloudflare
cloudflared tunnel create bingo-photobooth     # crée le tunnel (note le TUNNEL_ID)
# Route un sous-domaine vers le tunnel :
cloudflared tunnel route dns bingo-photobooth photo.tondomaine.fr
```
Crée `~/.cloudflared/config.yml` à partir de `deploy/cloudflared-config.example.yml`
(remplace `<TUNNEL_ID>` et le domaine), puis installe le service :
```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```
Les invités vont sur **https://photo.tondomaine.fr/selfie** (génère un **QR code**
de cette URL). Toi : `…/console`. Écran : `…/screen`.

> **Sans domaine ?** Tunnel rapide jetable (URL aléatoire à chaque lancement) :
> `cloudflared tunnel --url http://localhost:5055`. Pratique pour tester.

## 5. Impression DNP DS620 (CUPS)
La DS620 est gérée par **Gutenprint** (installé par le script).
```bash
lpinfo -v                       # repère l'imprimante USB
# Interface web CUPS : https://<ip-du-pi>:631  → Administration → Ajouter
```
Dans CUPS : ajoute la DS620, choisis le pilote **DNP DS620 (Gutenprint)**, règle
le **format papier** (pour des bandes : media **2x6** / dual-strip selon ton ruban).
Note le **nom de la file** (ex. `DS620`) et mets-le dans `.env` :
```
DNP_PRINTER=DS620
DNP_MEDIA=2x6
```
`sudo systemctl restart bingo-photobooth`. Le bouton « Imprimer 🖨️ » de la console
enverra alors les bandes à l'imprimante. (Alternative : `DNP_HOTFOLDER=` si tu
utilises un dossier surveillé.)

---

## Jour J — check-list
- [ ] Pi allumé, connecté à Internet (Ethernet conseillé).
- [ ] `systemctl status bingo-photobooth` → **active (running)**.
- [ ] `systemctl status cloudflared` → **active** ; `https://photo.tondomaine.fr/console` répond.
- [ ] Tablette sur `…/console` (PIN), écran sur `…/screen` en plein écran.
- [ ] QR code de `…/selfie` imprimé/affiché pour les invités.
- [ ] Template McDo sélectionné, style Pixar actif, imprimante testée.
- [ ] **Ouvrir le mode photo** quand l'animation commence.

## Dépannage
- **Logs app** : `journalctl -u bingo-photobooth -f`
- **Logs tunnel** : `journalctl -u cloudflared -f`
- **Redémarrer** : `sudo systemctl restart bingo-photobooth cloudflared`
- **Gemini en erreur 429/billing** : facturation à activer sur le projet Google.
- **Impression muette** : vérifie la file dans CUPS (`lpstat -p`) et `DNP_PRINTER`.
