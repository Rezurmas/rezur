"""Vault — cykl życia kopii zapisu.

Nazwa kopii: <plik>.<tag>-RRRRMMDD-GGMMSS (np. ER0000.sl2.rezurbak-20261013-221501).

Zasady:
    GOLD  — jeden na plik, tworzony przy pierwszej modyfikacji (trzyma stan
            SPRZED niej); rotacja nigdy go nie kasuje.
    PIN   — przypięte kopie w .rezur-pins.json obok save'a; rotacja je omija.
    prune — trzyma N najnowszych kopii *bak-* (poza GOLD i przypiętymi).
"""

import json
import os
import re
import shutil
import time
from pathlib import Path

GOLD_TAG = "goldbak"
_STAMP = r"\d{8}-\d{6}"
_PINS_NAME = ".rezur-pins.json"


def _rx(save: Path):
    return re.compile(rf"^{re.escape(save.name)}\.([A-Za-z0-9_-]+)-{_STAMP}$")


def pins_path(save_path):
    return Path(save_path).parent / _PINS_NAME


def load_pins(save_path):
    p = pins_path(save_path)
    if not p.is_file():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _write_pins(save_path, pins):
    p = pins_path(save_path)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(sorted(set(pins)), indent=1), encoding="utf-8")
    os.replace(tmp, p)


def set_pin(save_path, backup_name, on=True):
    """Przypina/odpina kopię; zwraca aktualną listę przypiętych."""
    pins = set(load_pins(save_path))
    if on:
        pins.add(backup_name)
    else:
        pins.discard(backup_name)
    _write_pins(save_path, pins)
    return sorted(pins)


def is_pinned(save_path, backup_name):
    return backup_name in load_pins(save_path)


def list_backups(save_path):
    """Lista kopii (najnowsze pierwsze) z flagami gold/pinned/tag."""
    p = Path(save_path)
    rx = _rx(p)
    pins = set(load_pins(p))
    out = []
    for f in p.parent.glob(f"{p.name}.*"):
        if not f.is_file():
            continue
        m = rx.match(f.name)
        if not m:
            continue
        st = f.stat()
        out.append(
            {
                "name": f.name,
                "path": str(f),
                "size": st.st_size,
                "mtime": st.st_mtime,
                "tag": m.group(1),
                "gold": m.group(1) == GOLD_TAG,
                "pinned": f.name in pins,
            }
        )
    out.sort(key=lambda d: d["mtime"], reverse=True)
    return out


def gold_backup(save_path):
    hits = [b for b in list_backups(save_path) if b["gold"]]
    return hits[0] if hits else None


def ensure_gold(save_path):
    """Jeden GOLD na plik: kopia stanu sprzed pierwszej modyfikacji. Idempotentne."""
    p = Path(save_path)
    have = gold_backup(p)
    if have:
        return {"created": False, "path": have["path"]}
    if not p.is_file():
        raise FileNotFoundError(p)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = p.with_name(f"{p.name}.{GOLD_TAG}-{stamp}")
    shutil.copy2(p, dst)
    return {"created": True, "path": str(dst)}


def prune(save_path, keep):
    """Rotacja: zostaw `keep` najnowszych *bak-*; GOLD i przypięte przeżywają zawsze."""
    p = Path(save_path)
    if not keep or keep <= 0:
        return []
    pins = set(load_pins(p))
    baks = [
        b
        for b in list_backups(p)
        if b["tag"].endswith("bak") and not b["gold"] and b["name"] not in pins
    ]
    deleted = []
    for old in baks[keep:]:
        try:
            Path(old["path"]).unlink()
            deleted.append(old["name"])
        except OSError:
            pass
    return deleted


def restore(save_path, backup_path):
    """Przywrócenie kopii — najpierw GOLD (jeśli brak) i kopia stanu obecnego."""
    save_path = Path(save_path)
    backup_path = Path(backup_path)
    if not backup_path.is_file():
        raise FileNotFoundError(backup_path)
    if save_path.exists():
        ensure_gold(save_path)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    pre = save_path.with_name(f"{save_path.name}.prerestorebak-{stamp}")
    if save_path.exists():
        shutil.copy2(save_path, pre)
    shutil.copy2(backup_path, save_path)
    return {"restored_from": str(backup_path), "pre_restore_copy": str(pre)}
