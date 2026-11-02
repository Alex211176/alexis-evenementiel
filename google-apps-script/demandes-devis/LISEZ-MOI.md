# Demandes de devis → Google Sheets + Agenda + e-mail

Le formulaire « Ma demande de devis » du catalogue (alexisevenementiel.fr) envoie chaque demande au script `Code.gs`, qui :

1. ajoute une ligne au tableau **Demandes de devis — Alexis Événementiel** (Drive), avec une colonne **Statut** (Nouveau, Rappelé, Devis envoyé, Signé, Perdu) ;
2. crée un événement dans l'agenda dédié **Demandes de devis** (créneau début → fin, ou journée entière si pas d'horaires ; rien si pas de date). L'événement ne bloque pas la journée et n'envoie aucune invitation ;
3. envoie une notification à `contact@alexisevenementiel.fr` — « Répondre » écrit directement au client.

Anti-spam : champ piège invisible, envoi en moins de 3 s ignoré, 30 demandes/heure maximum, pas de doublon sur double clic.
Tant que l'URL n'est pas renseignée dans le site, le formulaire garde l'ancien fonctionnement (ouverture de la messagerie du visiteur). Si le script est injoignable, il y revient aussi.

## Installation (une fois, ~5 min, avec le compte Google qui doit recevoir les demandes)

1. Aller sur <https://script.google.com> → **Nouveau projet**, le nommer « Demandes de devis — site ».
2. Remplacer le contenu de `Code.gs` par celui de ce dossier, puis **Enregistrer**.
3. **Paramètres du projet** (roue dentée) → Fuseau horaire : **(GMT+01:00) Paris**.
4. Revenir à l'éditeur, choisir la fonction **`installer`** → **Exécuter** → accepter les autorisations (Agenda, Sheets, Drive, envoi d'e-mails). Le journal affiche le lien du tableau.
5. Choisir **`testerDemande`** → **Exécuter** : une ligne TEST dans le tableau, un événement « TEST — Devis · Mariage… » le mois prochain dans l'agenda *Demandes de devis*, et un e-mail « [TEST] ». Supprimer ensuite la ligne et l'événement.
6. **Déployer** → **Nouveau déploiement** → type **Application Web** :
   - Exécuter en tant que : **Moi**
   - Qui a accès : **Tout le monde**
   → **Déployer**, copier l'**URL de l'application Web** (elle finit par `/exec`).
7. Coller cette URL dans `DEVIS_ENDPOINT` de `docs/catalogue.html` **et** de `generate_catalogue.py` (ou la donner à Claude), puis publier le site.

## Modifier le script plus tard

Après une modification de `Code.gs` : **Déployer** → **Gérer les déploiements** → crayon → Version : **Nouvelle version** → Déployer. L'URL reste la même.

Réglages en tête de `Code.gs` (`CONFIG`) : adresse de notification, nom de l'agenda, `RECAP_CLIENT: true` pour envoyer aussi un accusé de réception au client.
