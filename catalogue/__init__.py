"""
catalogue — Module de gestion du catalogue matériel, packs et prestations.

Architecture:
    catalogue.loader      -> chargement JSON
    catalogue.pricing     -> calcul des paliers tarifaires
    catalogue.packs       -> résolution de l'héritage des packs
    catalogue.queries     -> requêtes haut niveau (filtre, recherche)

Conçu pour permettre l'ajout futur du module devis sans modification.
"""

from .loader import load_catalogue, save_catalogue, CatalogueError
from .pricing import calculer_prix, paliers_disponibles
from .packs import resoudre_pack, calculer_valeur_a_la_carte
from .event_resolver import resoudre_evenement, bucket_label, BUCKET_LABELS

__version__ = "1.0.0"
__all__ = [
    "load_catalogue", "save_catalogue", "CatalogueError",
    "calculer_prix", "paliers_disponibles",
    "resoudre_pack", "calculer_valeur_a_la_carte",
    "resoudre_evenement", "bucket_label", "BUCKET_LABELS",
]
