import os
from config_manager import load_config
from storage import get_storage

SKIP_DIRS = {"output"}
SKIP_FILES = {".DS_Store"}

cfg = dict(load_config()); cfg["storage_mode"] = "dropbox"
st = get_storage(cfg)

if not os.path.isdir("data"):
    print("❌ Lance depuis la racine du projet (dossier data/ introuvable)"); raise SystemExit

sent = 0
for root, dirs, files in os.walk("data"):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for name in files:
        if name in SKIP_FILES: continue
        abs_path = os.path.join(root, name)
        rel = os.path.relpath(abs_path, "data").replace(os.sep, "/")
        with open(abs_path, "rb") as fh:
            st.write_bytes(rel, fh.read())
        print("  ↑", rel); sent += 1

print(f"\n✅ {sent} fichiers envoyés.")
print("Racine API :", st.list_folder(""))
for sub in ("catalogue", "defaults", "events"):
    print(f"  {sub}/ :", len(st.list_folder(sub)), "éléments")
