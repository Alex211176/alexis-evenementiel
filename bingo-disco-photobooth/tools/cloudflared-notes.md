# Exposer le module via Cloudflare Tunnel

## Option A — Tunnel rapide (jetable, idéal pour tester)

```bash
brew install cloudflared          # macOS
python app.py                     # serveur sur :5055 dans un autre terminal
cloudflared tunnel --url http://localhost:5055
```

Cloudflare affiche une URL `https://<aléatoire>.trycloudflare.com`. Elle change
à chaque lancement et n'a pas besoin de compte.

- Joueurs : `https://<aléatoire>.trycloudflare.com/selfie`
- Toi : `…/console`
- Écran TV : `…/screen`

Génère un QR code de l'URL `/selfie` pour les joueurs.

## Option B — Tunnel nommé sur ton domaine (ton « cloudflare » existant)

Si tu as déjà un domaine géré par Cloudflare et un tunnel nommé, ajoute une
règle d'ingress vers le port local dans `~/.cloudflared/config.yml` :

```yaml
tunnel: <ton-tunnel-id>
credentials-file: /Users/<toi>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: photo.tondomaine.fr
    service: http://localhost:5055
  # ... tes autres règles (bingo, player, etc.) ...
  - service: http_status:404
```

Puis :

```bash
cloudflared tunnel run <ton-tunnel>
```

Les joueurs vont sur `https://photo.tondomaine.fr/selfie`.

## Notes

- Le flux temps réel utilise **Server-Sent Events** (`/events`). Cloudflare le
  supporte ; on envoie déjà l'en-tête `X-Accel-Buffering: no` pour éviter la
  mise en tampon.
- Garde la **console** (`/console`) protégée par le PIN (`OPERATOR_PIN`), ou
  ajoute une règle Cloudflare Access si tu veux verrouiller davantage.
