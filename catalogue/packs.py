"""
catalogue.packs — Résolution de l'héritage des packs et calcul de la valeur à la carte.
"""

from typing import Dict, List, Any
from .pricing import calculer_prix


class PackError(Exception):
    """Erreur de résolution de pack (boucle d'héritage, pack introuvable, etc.)."""
    pass


def resoudre_pack(pack_id: str, packs: Dict[str, Any], _visites: list = None) -> Dict[str, Any]:
    """
    Résout récursivement l'héritage d'un pack.
    Retourne un dict avec la composition complète (héritée + ajouts - retraits).

    Args:
        pack_id: id du pack à résoudre
        packs: dict de tous les packs
        _visites: liste interne pour détecter les boucles

    Returns:
        dict {
            "id": ...,
            "nom": ...,
            "prix_ttc": ...,
            "composition_complete": {
                "equipements": [ { "id": ..., "quantite": ... }, ... ],
                "prestations": [ { "id": ..., "quantite": ... }, ... ]
            },
            "chaine_heritage": [pack_id1, pack_id2, ...]  # du plus ancestral au pack lui-même
        }
    """
    if _visites is None:
        _visites = []

    if pack_id in _visites:
        raise PackError(f"Boucle d'héritage détectée : {' → '.join(_visites + [pack_id])}")

    if pack_id not in packs:
        raise PackError(f"Pack introuvable : {pack_id}")

    pack = packs[pack_id]
    parent_id = pack.get("extends")

    # Résout le parent d'abord
    if parent_id:
        parent_resolu = resoudre_pack(parent_id, packs, _visites + [pack_id])
        composition_heritee = dict(parent_resolu["composition_complete"])
        # On copie en profondeur les listes
        composition_heritee = {
            "equipements": list(composition_heritee.get("equipements", [])),
            "prestations": list(composition_heritee.get("prestations", [])),
        }
        chaine = list(parent_resolu["chaine_heritage"]) + [pack_id]
    else:
        composition_heritee = {"equipements": [], "prestations": []}
        chaine = [pack_id]

    # Applique les ajouts de ce pack
    ajouts = pack.get("composition", {})
    composition_finale = {
        "equipements": _fusionner_lignes(
            composition_heritee["equipements"],
            ajouts.get("equipements", [])
        ),
        "prestations": _fusionner_lignes(
            composition_heritee["prestations"],
            ajouts.get("prestations", [])
        ),
    }

    # Applique les retraits
    for retrait in pack.get("retraits", []):
        _retirer_ligne(composition_finale, retrait)

    return {
        "id": pack_id,
        "nom": pack.get("nom", pack_id),
        "categorie": pack.get("categorie", ""),
        "prix_ttc": pack.get("prix_ttc", 0),
        "description": pack.get("description", ""),
        "duree_estimee": pack.get("duree_estimee", ""),
        "extends": parent_id,
        "chaine_heritage": chaine,
        "composition_complete": composition_finale,
        "bundle_compatible": pack.get("bundle_compatible", []),
    }


def _fusionner_lignes(lignes_base: List[Dict], lignes_a_ajouter: List[Dict]) -> List[Dict]:
    """
    Fusionne 2 listes de lignes {id, quantite}. Si même id, additionne les quantités.
    """
    resultat = {}
    for ligne in lignes_base + lignes_a_ajouter:
        item_id = ligne.get("id")
        qte = ligne.get("quantite", 1)
        if item_id in resultat:
            resultat[item_id]["quantite"] += qte
        else:
            resultat[item_id] = {"id": item_id, "quantite": qte}
    return list(resultat.values())


def _retirer_ligne(composition: Dict, retrait: Dict) -> None:
    """Retire une ligne ou réduit sa quantité."""
    section = retrait.get("section", "equipements")
    item_id = retrait.get("id")
    qte_a_retirer = retrait.get("quantite", None)  # None = retire complètement

    if section not in composition:
        return
    nouvelles = []
    for ligne in composition[section]:
        if ligne.get("id") == item_id:
            if qte_a_retirer is None:
                continue  # on saute = retrait complet
            nouvelle_qte = ligne["quantite"] - qte_a_retirer
            if nouvelle_qte > 0:
                nouvelles.append({"id": item_id, "quantite": nouvelle_qte})
        else:
            nouvelles.append(ligne)
    composition[section] = nouvelles


def calculer_valeur_a_la_carte(
    pack_resolu: Dict,
    equipements: Dict[str, Any],
    prestations: Dict[str, Any]
) -> float:
    """
    Calcule la valeur cumulée à la carte d'un pack résolu.

    Pour chaque équipement, on applique le prix selon les paliers définis.
    Pour chaque prestation, on prend son prix forfait.
    """
    total = 0.0
    composition = pack_resolu["composition_complete"]

    for ligne in composition["equipements"]:
        eq_id = ligne["id"]
        qte = ligne["quantite"]
        if eq_id not in equipements:
            continue
        try:
            total += calculer_prix(equipements[eq_id], qte)
        except Exception:
            # En cas de quantité non standard (ex: pack qui en demande 3 mais paliers sont 1/2),
            # on prend le palier 1 multiplié
            try:
                total += calculer_prix(equipements[eq_id], 1) * qte
            except Exception:
                pass

    for ligne in composition["prestations"]:
        presta_id = ligne["id"]
        qte = ligne["quantite"]
        if presta_id not in prestations:
            continue
        prix = prestations[presta_id].get("prix", 0)
        total += prix * qte

    return total
