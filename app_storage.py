"""
app_storage.py — Point d'accès unique à la configuration et au storage.

Importé par les blueprints (catalogue_routes, devis_routes, parametres_routes)
pour partager la même instance de stockage (un seul client Dropbox).
"""

from config_manager import load_config
from storage import get_storage

config = load_config()
STORAGE = get_storage(config)
