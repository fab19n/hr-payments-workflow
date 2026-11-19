r"""Settings isolation on made-up data only: with HRP_DATA_DIR set, settings.json lives in that folder and the program
folder's own settings.json is neither read nor written (it is only fingerprinted, never printed).

1. config.SETTINGS_FILE is inside the temporary folder.
2. save_settings writes the temporary file and leaves the program folder's settings.json byte for byte as it was (or
   still absent).
3. The program folder's settings.json is not read: the loaded settings are the defaults, then the temporary file's values.
4. The .tmp file used for the swap is created beside the real target only.

Run: .venv\Scripts\python -m synthetic_tests.settings_isolation_test
"""
import json
import os
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="hrp-settings-isolation-test-"))
os.environ["HRP_DATA_DIR"] = str(tmp)

from hrp import config  # noqa: E402

assert config.DATA_DIR == tmp, "the test must never open the real records folder"

passed = []


def check(name, ok, detail=""):
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
        sys.exit(1)
    passed.append(name)
    print(f"PASS {name}")


def fingerprint(p):
    """The file's bytes, or None when absent. Never printed."""
    return p.read_bytes() if p.exists() else None


REAL = config.PROGRAM_DIR / "settings.json"
real_before = fingerprint(REAL)
real_tmp = config.PROGRAM_DIR / "settings.json.tmp"
real_tmp_before = real_tmp.exists()

# ---------- 1. where the settings live ----------
check("settings.json is inside the temporary data folder", config.SETTINGS_FILE == tmp / "settings.json"
      and config.SETTINGS_FILE.parent == tmp and config.SETTINGS_FILE != REAL)
check("with no file there yet, the settings are the defaults (the program folder's values are not read)",
      not (tmp / "settings.json").exists() and config.load_settings() == config.DEFAULTS
      and config.SETTINGS["sql_exports_dir"] == config.DEFAULTS["sql_exports_dir"])

# ---------- 2. saving ----------
mine = {"data_dir": str(tmp), "backup_dir": "", "sql_exports_dir": str(tmp / "made-up-exports"), "port": 8626}
config.save_settings(mine)
check("save_settings writes the temporary file", (tmp / "settings.json").exists()
      and json.loads((tmp / "settings.json").read_text(encoding="utf-8")) == mine)
check("the program folder's settings.json is byte for byte unchanged (or still absent)", fingerprint(REAL) == real_before)

# ---------- 3. loading ----------
check("the temporary file's values are the ones loaded", config.load_settings()["sql_exports_dir"] == mine["sql_exports_dir"])
if real_before is not None:
    try:
        real_dir = json.loads(real_before.decode("utf-8")).get("sql_exports_dir", "")
    except (ValueError, AttributeError):
        real_dir = None
    check("the program folder's sql_exports_dir is not what loads", real_dir is None or real_dir == mine["sql_exports_dir"]
          or config.load_settings()["sql_exports_dir"] != real_dir)
else:
    check("the program folder has no settings.json here, and none was created", not REAL.exists())

# ---------- 4. the .tmp file ----------
check("no stray .tmp is left after a save", not (tmp / "settings.json.tmp").exists())
seen = []
_replace = os.replace


def spy(src, dst):
    seen.append((Path(src), Path(dst)))
    return _replace(src, dst)


config.os.replace = spy
try:
    config.save_settings({**mine, "backup_dir": ""})
finally:
    config.os.replace = _replace
check("the .tmp file is created beside the real target only",
      seen == [(tmp / "settings.json.tmp", tmp / "settings.json")] and real_tmp.exists() == real_tmp_before)
check("the program folder's settings.json is still unchanged at the end", fingerprint(REAL) == real_before)

print(f"\nAll {len(passed)} checks passed. Records folder used: {tmp}")
