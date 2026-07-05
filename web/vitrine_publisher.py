"""
web/vitrine_publisher.py — Publication automatique du catalogue vitrine.

Régénère `docs/catalogue.html` à partir du catalogue **en prod** (storage /
Dropbox = source de vérité) et le pousse — avec les photos manquantes — sur le
repo GitHub qui héberge le site vitrine (GitHub Pages, dossier `docs/`).
La publication se fait en **un seul commit atomique** via l'API Git Data de
GitHub (pas de git dans le conteneur, pas de working tree à gérer).

⚠️ Ne touche JAMAIS aux données de prod : on **lit** la prod (storage) et on
**écrit** uniquement dans le repo GitHub du vitrine. Aucun rapport avec
`push_data_to_dropbox.py`.

Config via variables d'environnement (à définir sur Render) :
  - GITHUB_TOKEN   (obligatoire) : token avec accès *écriture* "Contents" au repo.
  - VITRINE_REPO   (défaut "Alex211176/alexis-evenementiel")
  - VITRINE_BRANCH (défaut "main")
"""

import os
import base64

import requests

import storage_io
import generate_catalogue

API = "https://api.github.com"
DEFAULT_REPO = "Alex211176/alexis-evenementiel"
DEFAULT_BRANCH = "main"
DOCS = "docs"


class VitrinePublishError(Exception):
    """Erreur de publication lisible pour l'utilisateur (affichée en flash)."""


def _cfg():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise VitrinePublishError(
            "GITHUB_TOKEN n'est pas configuré. Ajoute-le dans les variables "
            "d'environnement de l'app sur Render, puis réessaie."
        )
    repo = (os.environ.get("VITRINE_REPO") or DEFAULT_REPO).strip()
    branch = (os.environ.get("VITRINE_BRANCH") or DEFAULT_BRANCH).strip()
    return token, repo, branch


def _headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _gh(method, path, token, **kw):
    """Appel API GitHub avec gestion d'erreur lisible. `path` commence par '/'."""
    r = requests.request(method, API + path, headers=_headers(token), timeout=30, **kw)
    if r.status_code >= 300:
        try:
            msg = r.json().get("message", r.text)
        except Exception:
            msg = r.text
        raise VitrinePublishError(f"GitHub {method} {path} → {r.status_code} : {msg}")
    return r


def _photos_referencees(equipements):
    """Noms de fichiers photo des équipements visibles dans le catalogue vitrine."""
    noms = []
    for e in equipements.values():
        if generate_catalogue.equipement_visible_catalogue(e):
            ph = e.get("photo")
            if ph:
                noms.append(ph)
    return list(dict.fromkeys(noms))  # unique, ordre préservé


def publier(storage) -> dict:
    """Régénère et publie la page catalogue du vitrine. Retourne un récapitulatif."""
    token, repo, branch = _cfg()

    # 1) Catalogue depuis la prod + rendu HTML (même moteur que la CLI)
    cat = storage_io.load_catalogue(storage)
    html = generate_catalogue.build_html(
        cat["equipements"], cat["prestations"], cat["packs"]
    )

    # 2) État actuel du repo : ref -> commit -> arbre
    ref = _gh("GET", f"/repos/{repo}/git/ref/heads/{branch}", token).json()
    base_commit_sha = ref["object"]["sha"]
    base_commit = _gh("GET", f"/repos/{repo}/git/commits/{base_commit_sha}", token).json()
    base_tree_sha = base_commit["tree"]["sha"]

    # 3) Blob pour docs/catalogue.html
    tree_entries = []
    blob = _gh("POST", f"/repos/{repo}/git/blobs", token,
               json={"content": html, "encoding": "utf-8"}).json()
    tree_entries.append({
        "path": f"{DOCS}/catalogue.html", "mode": "100644",
        "type": "blob", "sha": blob["sha"],
    })

    # 4) Photos référencées absentes du repo -> on les ajoute depuis la prod
    existantes = set()
    r = requests.get(API + f"/repos/{repo}/contents/{DOCS}/photos",
                     headers=_headers(token), params={"ref": branch}, timeout=30)
    if r.status_code == 200:
        for item in r.json():
            existantes.add(item.get("name"))

    photos_ajoutees = []
    for nom in _photos_referencees(cat["equipements"]):
        if nom in existantes:
            continue
        rel = f"catalogue/photos/{nom}"
        if not storage.exists(rel):
            continue  # référencée mais absente de la prod : on ignore silencieusement
        data = storage.read_bytes(rel)
        pblob = _gh("POST", f"/repos/{repo}/git/blobs", token, json={
            "content": base64.b64encode(data).decode(), "encoding": "base64",
        }).json()
        tree_entries.append({
            "path": f"{DOCS}/photos/{nom}", "mode": "100644",
            "type": "blob", "sha": pblob["sha"],
        })
        photos_ajoutees.append(nom)

    nb_eq = sum(1 for e in cat["equipements"].values()
                if generate_catalogue.equipement_visible_catalogue(e))

    # 5) Nouvel arbre — si identique à l'actuel, rien à publier (évite les commits vides)
    new_tree = _gh("POST", f"/repos/{repo}/git/trees", token,
                   json={"base_tree": base_tree_sha, "tree": tree_entries}).json()
    if new_tree["sha"] == base_tree_sha:
        return {"ok": True, "no_change": True, "equipements": nb_eq,
                "photos_ajoutees": []}

    # 6) Commit atomique + avance de la branche
    message = f"Vitrine : mise à jour catalogue (auto) — {nb_eq} équipements"
    if photos_ajoutees:
        message += f", +{len(photos_ajoutees)} photo(s)"
    commit = _gh("POST", f"/repos/{repo}/git/commits", token, json={
        "message": message, "tree": new_tree["sha"], "parents": [base_commit_sha],
    }).json()
    _gh("PATCH", f"/repos/{repo}/git/refs/heads/{branch}", token,
        json={"sha": commit["sha"]})

    return {
        "ok": True,
        "no_change": False,
        "equipements": nb_eq,
        "photos_ajoutees": photos_ajoutees,
        "commit": commit.get("html_url") or commit.get("sha"),
    }
