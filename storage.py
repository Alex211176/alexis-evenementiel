"""
storage.py — Abstraction de stockage pour Alexis Événementiel (cloud).

Deux backends, même interface :
  - LocalStorage   : lit/écrit dans un dossier local (dev Mac, pointe sur data/).
  - DropboxStorage : lit/écrit dans le App folder Dropbox via refresh token.

Tous les chemins sont relatifs à la racine des données, ex :
    "catalogue/equipements.json", "events/FT-2026-001.json",
    "defaults/prestataire.json", "devis/FT-2026-0042-DV01.pdf".

C'est la SEULE couche qui change entre le Mac et le cloud. Toute la logique
métier (catalogue/, devis/, fiches/) reste inchangée.
"""

import json
import os
from typing import List


class StorageError(Exception):
    pass


class BaseStorage:
    def read_bytes(self, rel_path: str) -> bytes:
        raise NotImplementedError

    def write_bytes(self, rel_path: str, data: bytes) -> None:
        raise NotImplementedError

    def list_folder(self, rel_path: str) -> List[str]:
        raise NotImplementedError

    def exists(self, rel_path: str) -> bool:
        raise NotImplementedError

    def delete(self, rel_path: str) -> None:
        raise NotImplementedError

    # Helpers communs ----------------------------------------------------
    def read_text(self, rel_path: str) -> str:
        return self.read_bytes(rel_path).decode("utf-8")

    def write_text(self, rel_path: str, text: str) -> None:
        self.write_bytes(rel_path, text.encode("utf-8"))

    def read_json(self, rel_path: str):
        return json.loads(self.read_text(rel_path))

    def write_json(self, rel_path: str, obj, indent: int = 4) -> None:
        self.write_text(rel_path, json.dumps(obj, ensure_ascii=False, indent=indent))


# --------------------------------------------------------------------------- #
# Local (dev Mac)
# --------------------------------------------------------------------------- #
class LocalStorage(BaseStorage):
    def __init__(self, base_dir: str):
        if not base_dir:
            raise StorageError("local_data_dir n'est pas défini dans la config.")
        self.base_dir = base_dir

    def _abs(self, rel_path: str) -> str:
        return os.path.join(self.base_dir, rel_path.strip().lstrip("/"))

    def read_bytes(self, rel_path: str) -> bytes:
        try:
            with open(self._abs(rel_path), "rb") as fh:
                return fh.read()
        except FileNotFoundError as exc:
            raise StorageError(f"Introuvable : {rel_path}") from exc

    def write_bytes(self, rel_path: str, data: bytes) -> None:
        abs_path = self._abs(rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as fh:
            fh.write(data)

    def list_folder(self, rel_path: str) -> List[str]:
        abs_path = self._abs(rel_path)
        if not os.path.isdir(abs_path):
            return []
        return sorted(os.listdir(abs_path))

    def exists(self, rel_path: str) -> bool:
        return os.path.exists(self._abs(rel_path))

    def delete(self, rel_path: str) -> None:
        abs_path = self._abs(rel_path)
        if os.path.exists(abs_path):
            os.remove(abs_path)


# --------------------------------------------------------------------------- #
# Dropbox (App folder, refresh token)
# --------------------------------------------------------------------------- #
class DropboxStorage(BaseStorage):
    def __init__(self, app_key: str, app_secret: str, refresh_token: str):
        if not (app_key and app_secret and refresh_token):
            raise StorageError("Identifiants Dropbox manquants (key/secret/refresh_token).")
        import dropbox

        self._dropbox = dropbox
        self._dbx = dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
        )

    @staticmethod
    def _norm(rel_path: str) -> str:
        return "/" + rel_path.strip().lstrip("/")

    def read_bytes(self, rel_path: str) -> bytes:
        try:
            _meta, res = self._dbx.files_download(self._norm(rel_path))
            return res.content
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Lecture Dropbox échouée ({rel_path}) : {exc}") from exc

    def write_bytes(self, rel_path: str, data: bytes) -> None:
        try:
            self._dbx.files_upload(
                data, self._norm(rel_path),
                mode=self._dropbox.files.WriteMode.overwrite, mute=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Écriture Dropbox échouée ({rel_path}) : {exc}") from exc

    def list_folder(self, rel_path: str) -> List[str]:
        path = self._norm(rel_path)
        if path == "/":
            path = ""
        try:
            names: List[str] = []
            res = self._dbx.files_list_folder(path)
            while True:
                names.extend(e.name for e in res.entries)
                if not res.has_more:
                    break
                res = self._dbx.files_list_folder_continue(res.cursor)
            return sorted(names)
        except Exception as exc:  # noqa: BLE001
            # Dossier inexistant => liste vide (cohérent avec LocalStorage)
            if "not_found" in str(exc):
                return []
            raise StorageError(f"Listing Dropbox échoué ({rel_path}) : {exc}") from exc

    def exists(self, rel_path: str) -> bool:
        try:
            self._dbx.files_get_metadata(self._norm(rel_path))
            return True
        except Exception:  # noqa: BLE001
            return False

    def delete(self, rel_path: str) -> None:
        try:
            self._dbx.files_delete_v2(self._norm(rel_path))
        except Exception as exc:  # noqa: BLE001
            if "not_found" in str(exc):
                return
            raise StorageError(f"Suppression Dropbox échouée ({rel_path}) : {exc}") from exc


def get_storage(config: dict) -> BaseStorage:
    mode = (config.get("storage_mode") or "dropbox").lower()
    if mode == "local":
        return LocalStorage(config.get("local_data_dir", ""))
    dbx = config.get("dropbox", {})
    return DropboxStorage(
        app_key=dbx.get("app_key", ""),
        app_secret=dbx.get("app_secret", ""),
        refresh_token=dbx.get("refresh_token", ""),
    )
