"""
poses/tokens.py — Génération et validation des jetons.

Le clientToken sert à la fois de secret d'accès (URL non devinable envoyée aux
mariés) ET de nom de fichier de l'événement (/poses/events/<token>.json), ce qui
permet un lookup public en une seule lecture. Il doit donc être :
  - imprévisible (secrets, pas random) ;
  - sûr comme composant d'URL et de nom de fichier (alphabet url-safe) ;
  - validable strictement pour barrer tout path traversal côté requête publique.
"""

import re
import secrets

# token_urlsafe produit un alphabet [A-Za-z0-9_-]. On le fige comme contrat.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def generate_token(nbytes: int = 9) -> str:
    """Jeton url-safe (~12 caractères pour 9 octets). Non devinable."""
    return secrets.token_urlsafe(nbytes)


def is_valid_token(token: str) -> bool:
    """Vrai si le jeton respecte l'alphabet et la longueur attendus.

    Barrière anti path-traversal : tout ce qui contient '/', '.', espaces, etc.
    est rejeté avant la moindre lecture de fichier.
    """
    return bool(token) and bool(_TOKEN_RE.match(token))
