"""
catalogue.pricing — Calcul des prix selon les paliers et modes de vente.

Modes de vente supportés :
- forfaitaire : prix fixe quelle que soit la quantité (mais qte forcée à 1 si unique)
- unitaire    : prix × quantité
- tranches    : paliers avec prix_forfait par tranche
"""

from typing import Optional, List, Dict, Any


class PricingError(ValueError):
    """Erreur de calcul de prix (quantité invalide, palier manquant...)."""
    pass


def quantite_valide(equipement: dict, quantite: int) -> bool:
    """Vérifie si une quantité est autorisée pour cet équipement."""
    vente = equipement.get("vente", {})
    qa = vente.get("quantites_autorisees", {"type": "libre"})
    qa_type = qa.get("type", "libre")

    # Stock physique
    stock_max = equipement.get("quantite_possedee", float("inf"))
    if quantite > stock_max:
        return False
    if quantite < 1:
        return False

    if qa_type == "libre":
        return True
    elif qa_type == "unique":
        return quantite == 1
    elif qa_type == "multiples_de":
        n = qa.get("valeur", 1)
        return quantite % n == 0
    elif qa_type == "valeurs_fixes":
        return quantite in qa.get("valeur", [])
    return False


def calculer_prix(equipement: dict, quantite: int = 1) -> float:
    """
    Calcule le prix pour une quantité donnée selon le mode de vente.

    Args:
        equipement: dict équipement
        quantite: nombre d'unités souhaité

    Returns:
        Prix total HT en euros.

    Raises:
        PricingError: si la quantité n'est pas valide ou pas de palier correspondant.
    """
    if not quantite_valide(equipement, quantite):
        raise PricingError(
            f"Quantité {quantite} invalide pour {equipement.get('nom', '?')}"
        )

    vente = equipement.get("vente", {})
    mode = vente.get("mode", "forfaitaire")

    if mode == "forfaitaire":
        return float(vente.get("prix_unitaire", 0))

    if mode == "unitaire":
        return float(vente.get("prix_unitaire", 0)) * quantite

    if mode == "tranches":
        paliers = vente.get("paliers", [])
        # Trouve le palier exact (qte == valeur)
        for p in paliers:
            if p.get("qte") == quantite:
                if "prix_forfait" in p:
                    return float(p["prix_forfait"])
                if "prix_unitaire" in p:
                    return float(p["prix_unitaire"]) * quantite
        # Sinon, cherche le palier qui couvre cette quantité (pour mode libre + tranches)
        paliers_tries = sorted(paliers, key=lambda p: p.get("qte", 0))
        palier_applicable = None
        for p in paliers_tries:
            if p.get("qte", 0) <= quantite:
                palier_applicable = p
            else:
                break
        if palier_applicable:
            if "prix_forfait" in palier_applicable:
                return float(palier_applicable["prix_forfait"])
            if "prix_unitaire" in palier_applicable:
                return float(palier_applicable["prix_unitaire"]) * quantite
        raise PricingError(
            f"Aucun palier ne correspond à la quantité {quantite} pour {equipement.get('nom', '?')}"
        )

    raise PricingError(f"Mode de vente inconnu : {mode}")


def paliers_disponibles(equipement: dict) -> List[Dict[str, Any]]:
    """
    Retourne la liste des paliers disponibles pour un équipement, enrichie
    avec le prix unitaire équivalent et le label affichable.

    Utilisé pour l'affichage transparent des paliers dans le devis.
    """
    vente = equipement.get("vente", {})
    mode = vente.get("mode", "forfaitaire")
    stock = equipement.get("quantite_possedee", 999)

    resultats = []

    if mode == "forfaitaire":
        prix = vente.get("prix_unitaire", 0)
        resultats.append({
            "qte": 1,
            "prix_total": prix,
            "prix_unitaire_eq": prix,
            "label": f"{prix} €",
            "economie_vs_precedent": None,
        })

    elif mode == "unitaire":
        prix = vente.get("prix_unitaire", 0)
        for q in range(1, min(stock, 10) + 1):
            resultats.append({
                "qte": q,
                "prix_total": prix * q,
                "prix_unitaire_eq": prix,
                "label": f"{q} × {prix} € = {prix * q} €",
                "economie_vs_precedent": None,
            })

    elif mode == "tranches":
        paliers = vente.get("paliers", [])
        for i, p in enumerate(sorted(paliers, key=lambda x: x.get("qte", 0))):
            qte = p.get("qte", 1)
            if "prix_forfait" in p:
                prix_total = p["prix_forfait"]
            else:
                prix_total = p.get("prix_unitaire", 0) * qte
            prix_unit_eq = round(prix_total / qte, 2) if qte > 0 else prix_total

            # Calcul économie vs palier précédent
            eco = None
            if i > 0:
                p_prec = sorted(paliers, key=lambda x: x.get("qte", 0))[i - 1]
                qte_prec = p_prec.get("qte", 1)
                if "prix_forfait" in p_prec:
                    prix_prec_unit = p_prec["prix_forfait"] / qte_prec
                else:
                    prix_prec_unit = p_prec.get("prix_unitaire", 0)
                if prix_prec_unit > 0:
                    eco_pct = round((1 - prix_unit_eq / prix_prec_unit) * 100, 1)
                    if eco_pct > 0:
                        eco = f"-{eco_pct}%"

            resultats.append({
                "qte": qte,
                "prix_total": prix_total,
                "prix_unitaire_eq": prix_unit_eq,
                "label": f"{qte} × {equipement.get('vente', {}).get('unite_label', 'unité')} → {prix_total} € ({prix_unit_eq} €/u)",
                "economie_vs_precedent": eco,
            })

    return resultats
