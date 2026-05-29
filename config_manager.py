"""
config_manager.py — Configuration de l'app.

Priorité : variable d'environnement > config.json > défaut.
En local on lit config.json ; sur Render tout passe par les variables AE_*.
"""

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_HERE, "config.json")

ENV_OVERRIDES = {
    "AE_STORAGE_MODE":          ("storage_mode",),
    "AE_APP_PASSWORD":          ("app_password",),
    "AE_SECRET_KEY":            ("secret_key",),
    "AE_LOCAL_DATA_DIR":        ("local_data_dir",),
    "AE_DROPBOX_APP_KEY":       ("dropbox", "app_key"),
    "AE_DROPBOX_APP_SECRET":    ("dropbox", "app_secret"),
    "AE_DROPBOX_REFRESH_TOKEN": ("dropbox", "refresh_token"),
}

_DEFAULTS = {
    "storage_mode": "dropbox",
    "app_password": "",
    "secret_key": "dev-secret-a-changer",
    "local_data_dir": "",
    "dropbox": {"app_key": "", "app_secret": "", "refresh_token": ""},
}


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _set_path(cfg: dict, path: tuple, value) -> None:
    node = cfg
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def load_config() -> dict:
    cfg = json.loads(json.dumps(_DEFAULTS))
    if os.path.exists(_CONFIG_PATH):
        with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
            cfg = _deep_merge(cfg, json.load(fh))
    for env_name, path in ENV_OVERRIDES.items():
        val = os.environ.get(env_name)
        if val:
            _set_path(cfg, path, val)
    return cfg


def is_on_render() -> bool:
    return os.environ.get("RENDER", "").lower() == "true"
