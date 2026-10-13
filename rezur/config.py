"""Konfiguracja Rezura: %APPDATA%\\rezur\\config.json + domyślne wartości.

Klucze:
    backup_retention (int)  — ile kopii *bak-* trzymać na plik (najnowsze), 0 = bez limitu
    auto_doctor (bool)      — czy po `fix --apply` pokazywać re-diagnostykę
    guard_live (bool)       — czy blokować zapis do żywego save'a przy działającej grze
    watch_interval (int)    — co ile sekund kopia (watch), gdy gra działa
    last_save (str)         — ostatnio używany plik save'a (pamięć między uruchomieniami)
    ui_lang (str)           — język GUI: "en" (domyślny) albo "pl"
"""

import json
import os
from pathlib import Path

DEFAULTS = {
    "backup_retention": 20,
    "auto_doctor": True,
    "guard_live": True,
    "watch_interval": 600,
    "last_save": None,
    "ui_lang": "en",
}


def config_dir():
    root = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return Path(root) / "rezur"


def config_path():
    return config_dir() / "config.json"


def load():
    cfg = dict(DEFAULTS)
    p = config_path()
    if p.is_file():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return cfg


def save(cfg):
    config_dir().mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(config_path())


def set_value(key, raw):
    if key not in DEFAULTS:
        raise ValueError(f"nieznany klucz {key!r} (są: {', '.join(DEFAULTS)})")
    ref = DEFAULTS[key]
    if isinstance(ref, bool):
        val = raw.strip().lower() in ("1", "true", "tak", "yes", "on")
    elif isinstance(ref, int):
        val = int(raw)
    elif key == "ui_lang":
        val = raw.strip().lower()
        if val not in ("en", "pl"):
            raise ValueError(f"ui_lang: 'en' albo 'pl' (dostałem {raw!r})")
    else:
        val = raw
    cfg = load()
    cfg[key] = val
    save(cfg)
    return key, val
