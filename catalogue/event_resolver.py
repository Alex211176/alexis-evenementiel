"""
catalogue.event_resolver — Résout un événement et calcule la liste matériel,
le bilan électrique, le poids et le prix final à partir du pack, des retraits
et des suppléments.

Règle de compensation (moins-value retraits) :
    - Retraits sans ajouts → pas de moins-value (prix pack conservé)
    - Retraits avec ajouts → moins-value plafonnée au montant des ajouts
"""

from typing import Dict, List, Any
from .packs import resoudre_pack
from .pricing import calculer_prix


CATEGORIE_VERS_BUCKET = {
    "son": "son_video",
    "video": "son_video",
    "regie": "son_video",
    "lumiere": "lumiere",
    "effet": "lumiere",
    "photo": "divers",
    "energie": "divers",
    "divers": "divers",
    "autre": "divers",
}

BUCKET_LABELS = {
    "son_video": "Sonorisation & vidéo",
    "lumiere": "Lumière & atmosphère",
    "divers": "Divers",
}


def _puissance_totale_item(equipement: dict, quantite: int) -> float:
    if "puissance_w_unitaire" in equipement:
        return float(equipement["puissance_w_unitaire"]) * quantite
    return float(equipement.get("puissance_w", 0)) * quantite


def _poids_total_item(equipement: dict, quantite: int) -> float:
    if "poids_kg_unitaire" in equipement:
        return float(equipement["poids_kg_unitaire"]) * quantite
    return float(equipement.get("poids_kg", 0)) * quantite


def _format_ligne_materiel(equipement: dict, quantite: int) -> str:
    nom = equipement.get("nom", "?")
    return f"{quantite}× {nom}"


def _valeur_catalogue_item(equipement: dict, quantite: int) -> float:
    """Prix catalogue d'un équipement pour une quantité donnée."""
    try:
        return calculer_prix(equipement, quantite)
    except Exception:
        try:
            return calculer_prix(equipement, 1) * quantite
        except Exception:
            return 0.0


def resoudre_evenement(event: dict, catalogue: dict) -> dict:
    """
    Résout un événement avec son pack, ses retraits et ses suppléments.
    Retourne la composition complète, les agrégats techniques et le détail du prix.
    """
    pack_id = event.get("pack_id")
    mode = event.get("mode_composition", "catalogue" if pack_id else "manuel")

    # === Mode catalogue ===
    if mode == "catalogue":
        pack_resolu = None
        composition = {"equipements": [], "prestations": []}
        prix_pack = 0.0

        # 1. Résolution du pack
        if pack_id and pack_id in catalogue["packs"]:
            pack_resolu = resoudre_pack(pack_id, catalogue["packs"])
            composition = {
                "equipements": list(pack_resolu["composition_complete"]["equipements"]),
                "prestations": list(pack_resolu["composition_complete"]["prestations"]),
            }
            prix_pack = float(pack_resolu.get("prix_ttc", 0))

        # 2. Application des retraits
        retraits = event.get("retraits", {}) or {}
        retraits_eq_ids = set(retraits.get("equipements", []))
        retraits_pr_ids = set(retraits.get("prestations", []))
        retraits_appliques = {"equipements": [], "prestations": []}
        retraits_valeur_brute = 0.0

        if retraits_eq_ids:
            nouvelle_compo = []
            for ligne in composition["equipements"]:
                if ligne["id"] in retraits_eq_ids:
                    eq = catalogue["equipements"].get(ligne["id"], {})
                    valeur = _valeur_catalogue_item(eq, ligne["quantite"])
                    retraits_appliques["equipements"].append({
                        "id": ligne["id"],
                        "nom": eq.get("nom", ligne["id"]),
                        "quantite": ligne["quantite"],
                        "valeur": valeur,
                    })
                    retraits_valeur_brute += valeur
                else:
                    nouvelle_compo.append(ligne)
            composition["equipements"] = nouvelle_compo

        if retraits_pr_ids:
            nouvelle_pr = []
            for ligne in composition["prestations"]:
                if ligne["id"] in retraits_pr_ids:
                    pr = catalogue["prestations"].get(ligne["id"], {})
                    valeur = float(pr.get("prix", 0)) * ligne["quantite"]
                    retraits_appliques["prestations"].append({
                        "id": ligne["id"],
                        "nom": pr.get("nom", ligne["id"]),
                        "quantite": ligne["quantite"],
                        "valeur": valeur,
                    })
                    retraits_valeur_brute += valeur
                else:
                    nouvelle_pr.append(ligne)
            composition["prestations"] = nouvelle_pr

        # 3. Ajout des suppléments
        ajouts_ttc = 0.0
        for supp in event.get("supplements", []):
            supp_id = supp.get("id")
            qte = supp.get("quantite", 1)
            if not supp_id:
                continue
            eq = catalogue["equipements"].get(supp_id)
            if eq:
                ajouts_ttc += _valeur_catalogue_item(eq, qte)
            # Fusion dans composition
            found = False
            for ligne in composition["equipements"]:
                if ligne["id"] == supp_id:
                    ligne["quantite"] += qte
                    found = True
                    break
            if not found:
                composition["equipements"].append({"id": supp_id, "quantite": qte})

        # 4. Agrégats techniques
        materiel_par_bucket = {"son_video": [], "lumiere": [], "divers": []}
        puissance_totale = 0.0
        poids_total = 0.0

        for ligne in composition["equipements"]:
            eq_id = ligne["id"]
            qte = ligne["quantite"]
            eq = catalogue["equipements"].get(eq_id)
            if not eq:
                continue

            visible = eq.get("visible_dans", {})
            cat = eq.get("categorie", "autre")
            bucket = CATEGORIE_VERS_BUCKET.get(cat, "divers")

            if visible.get("fiche_materiel", True):
                materiel_par_bucket[bucket].append(_format_ligne_materiel(eq, qte))

            if visible.get("fiche_puissance", True):
                puissance_totale += _puissance_totale_item(eq, qte)

            poids_total += _poids_total_item(eq, qte)

        # 5. Prix final avec règle de compensation
        retraits_valeur_appliquee = min(retraits_valeur_brute, ajouts_ttc)
        total_ttc = prix_pack + ajouts_ttc - retraits_valeur_appliquee

        return {
            "mode": "catalogue",
            "pack": pack_resolu,
            "composition": composition,
            "retraits_appliques": retraits_appliques,
            "materiel_par_bucket": materiel_par_bucket,
            "puissance_totale_w": puissance_totale,
            "puissance_totale_kw": round(puissance_totale / 1000, 2),
            "poids_total_kg": round(poids_total, 1),
            "prix": {
                "pack_ttc": prix_pack,
                "ajouts_ttc": ajouts_ttc,
                "retraits_valeur_brute": retraits_valeur_brute,
                "retraits_valeur_appliquee": retraits_valeur_appliquee,
                "total_ttc": total_ttc,
            },
        }

    # === Mode manuel ===
    materiel_manuel = event.get("materiel_manuel", {})
    return {
        "mode": "manuel",
        "pack": None,
        "composition": {"equipements": [], "prestations": []},
        "retraits_appliques": {"equipements": [], "prestations": []},
        "materiel_par_bucket": {
            "son_video": materiel_manuel.get("son_video", []),
            "lumiere": materiel_manuel.get("lumiere", []),
            "divers": materiel_manuel.get("divers", []),
        },
        "puissance_totale_w": 0,
        "puissance_totale_kw": 0,
        "poids_total_kg": 0,
        "prix": {
            "pack_ttc": 0,
            "ajouts_ttc": 0,
            "retraits_valeur_brute": 0,
            "retraits_valeur_appliquee": 0,
            "total_ttc": 0,
        },
    }


def bucket_label(key: str) -> str:
    return BUCKET_LABELS.get(key, key)
