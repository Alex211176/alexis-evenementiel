"""
devis.signature — Gestion des 3 modes de signature client.

Modes supportés:
    1. 'canvas'    : signature manuscrite numérique (image PNG base64)
    2. 'bon_accord': case "Bon pour accord" + nom + date
    3. 'email'     : validation par lien email (token)

Chaque signature stocke en plus : timestamp, IP, user agent (traçabilité).
"""

import secrets
import hashlib
from datetime import datetime, timedelta


def _now_iso() -> str:
    """Timestamp ISO 8601 pour traçabilité."""
    return datetime.now().isoformat(timespec="seconds")


def save_signature_canvas(
    event_data: dict,
    signature_b64: str,
    nom_signataire: str,
    ip: str,
    user_agent: str,
) -> dict:
    """
    Sauvegarde une signature manuscrite (canvas → PNG base64).

    Args:
        event_data: dict événement (sera muté)
        signature_b64: image PNG en base64 (data:image/png;base64,...)
        nom_signataire: nom saisi par le client
        ip: IP du client
        user_agent: navigateur du client

    Returns:
        dict signature (pour confirmation UI)
    """
    sig = {
        "mode": "canvas",
        "image_b64": signature_b64,
        "nom": nom_signataire,
        "timestamp": _now_iso(),
        "ip": ip,
        "user_agent": user_agent,
    }
    event_data.setdefault("devis", {})["signature"] = sig
    event_data["devis"]["statut"] = "accepte"
    return sig


def save_signature_bon_accord(
    event_data: dict,
    nom_signataire: str,
    date_signature: str,
    ip: str,
    user_agent: str,
) -> dict:
    """
    Sauvegarde une validation 'Bon pour accord'.

    Args:
        event_data: dict événement
        nom_signataire: nom saisi
        date_signature: date saisie (format libre, ex "19/05/2026")
        ip: IP
        user_agent: navigateur

    Returns:
        dict signature
    """
    sig = {
        "mode": "bon_accord",
        "nom": nom_signataire,
        "date_signature": date_signature,
        "mention": "Bon pour accord",
        "timestamp": _now_iso(),
        "ip": ip,
        "user_agent": user_agent,
    }
    event_data.setdefault("devis", {})["signature"] = sig
    event_data["devis"]["statut"] = "accepte"
    return sig


def init_signature_email(
    event_data: dict,
    expire_jours: int = 30,
) -> str:
    """
    Crée un token de validation par email.
    Le client recevra un lien contenant ce token. Cliquer dessus = validation.

    Returns:
        Le token (à inclure dans l'URL envoyée par email)
    """
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=expire_jours)).isoformat(timespec="seconds")

    event_data.setdefault("devis", {})["pending_email_validation"] = {
        "token_hash": _hash_token(token),
        "expires_at": expires,
        "created_at": _now_iso(),
    }
    return token


def verify_signature_token(
    event_data: dict,
    token: str,
    ip: str,
    user_agent: str,
) -> bool:
    """
    Vérifie un token email et valide le devis si correct.

    Returns:
        True si validation réussie, False sinon.
    """
    pending = event_data.get("devis", {}).get("pending_email_validation")
    if not pending:
        return False

    # Vérif expiration
    try:
        expires = datetime.fromisoformat(pending["expires_at"])
        if datetime.now() > expires:
            return False
    except (ValueError, KeyError):
        return False

    # Vérif token
    if _hash_token(token) != pending.get("token_hash"):
        return False

    # OK : valide
    sig = {
        "mode": "email",
        "client_email": event_data.get("client", {}).get("email", ""),
        "timestamp": _now_iso(),
        "ip": ip,
        "user_agent": user_agent,
    }
    event_data.setdefault("devis", {})["signature"] = sig
    event_data["devis"]["statut"] = "accepte"
    # Supprime le pending
    event_data["devis"].pop("pending_email_validation", None)
    return True


def _hash_token(token: str) -> str:
    """Hash SHA-256 d'un token (on ne stocke jamais le token en clair)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
