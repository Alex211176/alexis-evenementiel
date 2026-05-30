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

        # 2. Application des retraits.
        #    Format rétro-compatible : un retrait peut être
        #      - un id simple "xxx"                       -> non déduit (info seule)
        #      - un objet {"id","deduire":bool,"montant"} -> déduction manuelle
        #    deduction_totale = somme des montants des retraits cochés "deduire".
        retraits = event.get("retraits", {}) or {}

        def _norm_retraits(lst):
            """Retourne {id: {"deduire":bool, "montant":float|None}} depuis une liste mixte."""
            out = {}
            for item in (lst or []):
                if isinstance(item, dict):
                    rid = item.get("id")
                    if not rid:
                        continue
                    out[rid] = {
                        "deduire": bool(item.get("deduire", False)),
                        "montant": item.get("montant", None),
                    }
                else:
                    out[item] = {"deduire": False, "montant": None}
            return out

        retraits_eq_map = _norm_retraits(retraits.get("equipements"))
        retraits_pr_map = _norm_retraits(retraits.get("prestations"))
        retraits_appliques = {"equipements": [], "prestations": []}
        deduction_totale = 0.0

        if retraits_eq_map:
            nouvelle_compo = []
            for ligne in composition["equipements"]:
                if ligne["id"] in retraits_eq_map:
                    eq = catalogue["equipements"].get(ligne["id"], {})
                    valeur_cat = _valeur_catalogue_item(eq, ligne["quantite"])
                    meta = retraits_eq_map[ligne["id"]]
                    montant = meta["montant"] if meta["montant"] is not None else valeur_cat
                    try:
                        montant = float(montant)
                    except (TypeError, ValueError):
                        montant = valeur_cat
                    deduit = meta["deduire"]
                    if deduit:
                        deduction_totale += montant
                    retraits_appliques["equipements"].append({
                        "id": ligne["id"],
                        "nom": eq.get("nom", ligne["id"]),
                        "quantite": ligne["quantite"],
                        "valeur": valeur_cat,
                        "deduire": deduit,
                        "montant": montant,
                    })
                else:
                    nouvelle_compo.append(ligne)
            composition["equipements"] = nouvelle_compo

        if retraits_pr_map:
            nouvelle_pr = []
            for ligne in composition["prestations"]:
                if ligne["id"] in retraits_pr_map:
                    pr = catalogue["prestations"].get(ligne["id"], {})
                    valeur_cat = float(pr.get("prix", 0)) * ligne["quantite"]
                    meta = retraits_pr_map[ligne["id"]]
                    montant = meta["montant"] if meta["montant"] is not None else valeur_cat
                    try:
                        montant = float(montant)
                    except (TypeError, ValueError):
                        montant = valeur_cat
                    deduit = meta["deduire"]
                    if deduit:
                        deduction_totale += montant
                    retraits_appliques["prestations"].append({
                        "id": ligne["id"],
                        "nom": pr.get("nom", ligne["id"]),
                        "quantite": ligne["quantite"],
                        "valeur": valeur_cat,
                        "deduire": deduit,
                        "montant": montant,
                    })
                else:
                    nouvelle_pr.append(ligne)
            composition["prestations"] = nouvelle_pr

        # 3. Ajout des suppléments (équipements, prestations, packs complémentaires)
        #    Plus de compensation croisée automatique : TOUT s'additionne.
        #    Les déductions de retraits sont gérées manuellement (section 2).
        ajouts_ttc = 0.0                 # suppléments équipement
        ajouts_hors_compensation = 0.0   # prestations + packs complémentaires (toujours en plus)
        supplements_detail = {"equipements": [], "prestations": [], "packs": []}

        for supp in event.get("supplements", []):
            supp_id = supp.get("id")
            qte = supp.get("quantite", 1) or 1
            supp_type = supp.get("type", "equipement")  # défaut = équipement (rétro-compat)
            if not supp_id:
                continue

            if supp_type == "prestation":
                pr = catalogue["prestations"].get(supp_id)
                if not pr:
                    continue
                valeur = float(pr.get("prix", 0)) * qte
                ajouts_hors_compensation += valeur
                supplements_detail["prestations"].append({
                    "id": supp_id, "nom": pr.get("nom", supp_id),
                    "quantite": qte, "valeur": valeur,
                })
                # Ajout à la composition prestations (pour la fiche technique)
                found = False
                for ligne in composition["prestations"]:
                    if ligne["id"] == supp_id:
                        ligne["quantite"] += qte
                        found = True
                        break
                if not found:
                    composition["prestations"].append({"id": supp_id, "quantite": qte})

            elif supp_type == "pack":
                pk = catalogue["packs"].get(supp_id)
                if not pk:
                    continue
                try:
                    pack_comp = resoudre_pack(supp_id, catalogue["packs"])
                except Exception:
                    pack_comp = None
                valeur = float((pack_comp or pk).get("prix_ttc", 0)) * qte
                ajouts_hors_compensation += valeur
                supplements_detail["packs"].append({
                    "id": supp_id, "nom": pk.get("nom", supp_id),
                    "quantite": qte, "valeur": valeur,
                })
                # Fusion du matériel + prestations du pack complémentaire dans la composition
                if pack_comp:
                    for ligne in pack_comp["composition_complete"]["equipements"]:
                        existe = next((l for l in composition["equipements"] if l["id"] == ligne["id"]), None)
                        if existe:
                            existe["quantite"] += ligne["quantite"] * qte
                        else:
                            composition["equipements"].append({"id": ligne["id"], "quantite": ligne["quantite"] * qte})
                    for ligne in pack_comp["composition_complete"]["prestations"]:
                        existe = next((l for l in composition["prestations"] if l["id"] == ligne["id"]), None)
                        if existe:
                            existe["quantite"] += ligne["quantite"] * qte
                        else:
                            composition["prestations"].append({"id": ligne["id"], "quantite": ligne["quantite"] * qte})

            else:  # equipement (comportement historique inchangé)
                eq = catalogue["equipements"].get(supp_id)
                if eq:
                    ajouts_ttc += _valeur_catalogue_item(eq, qte)
                    supplements_detail["equipements"].append({
                        "id": supp_id, "nom": eq.get("nom", supp_id),
                        "quantite": qte, "valeur": _valeur_catalogue_item(eq, qte),
                    })
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

        # 5. Prix final (règle simplifiée, tout explicite) :
        #    total = pack − déductions manuelles + suppléments équipement
        #            + prestations/packs complémentaires
        total_ttc = prix_pack - deduction_totale + ajouts_ttc + ajouts_hors_compensation

        return {
            "mode": "catalogue",
            "pack": pack_resolu,
            "composition": composition,
            "retraits_appliques": retraits_appliques,
            "materiel_par_bucket": materiel_par_bucket,
            "puissance_totale_w": puissance_totale,
            "puissance_totale_kw": round(puissance_totale / 1000, 2),
            "poids_total_kg": round(poids_total, 1),
            "supplements_detail": supplements_detail,
            "prix": {
                "pack_ttc": prix_pack,
                "ajouts_ttc": ajouts_ttc,
                "ajouts_hors_compensation": ajouts_hors_compensation,
                "deduction_totale": deduction_totale,
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
            "ajouts_hors_compensation": 0,
            "deduction_totale": 0,
            "total_ttc": 0,
        },
    }


def bucket_label(key: str) -> str:
    return BUCKET_LABELS.get(key, key)


