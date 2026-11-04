"""Where records live. Everything the app stores goes under DATA_DIR, never inside the program folder."""
import json
import os
from pathlib import Path

PROGRAM_DIR = Path(__file__).resolve().parent.parent
SETTINGS_FILE = PROGRAM_DIR / "settings.json"

DEFAULTS = {
    "data_dir": r"C:\HR-Records",
    "backup_dir": "",  # e.g. an external drive like E:\HR-Backup
    "port": 8626,
}


def load_settings():
    s = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    return s


def save_settings(s):
    SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")


SETTINGS = load_settings()
if os.environ.get("HRP_PORT"):  # lets a test copy run beside the real app
    SETTINGS["port"] = int(os.environ["HRP_PORT"])
DATA_DIR = Path(os.environ.get("HRP_DATA_DIR") or SETTINGS["data_dir"])
DOCS_DIR = DATA_DIR / "documents"
PACKS_DIR = DATA_DIR / "audit-packs"
BACKUP_DIR = DATA_DIR / "backups"
DB_PATH = DATA_DIR / "records.db"
SEED_PATH = DATA_DIR / "seed.json"

for d in (DATA_DIR, DOCS_DIR, PACKS_DIR, BACKUP_DIR):
    d.mkdir(parents=True, exist_ok=True)
