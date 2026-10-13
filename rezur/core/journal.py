"""Dziennik edycji Rezura — znacznik „plik modyfikowany" + historia operacji.

Sidecar per plik: `<save>.rezur-journal.json` (obok save'a). Każda udana
modyfikacja wykonana przez Rezura dopisuje wpis (etykieta po tagu backupu).
GOLD + dziennik = komplet do odpowiedzi na pytanie „czy to jeszcze oryginał?".
"""

import json
import os
import time
from pathlib import Path

OP_LABELS = {
    "rezurbak": "naprawy/edycja ogólna",
    "editbak": "edycja",
    "itembak": "ekwipunek",
    "equipbak": "zakładanie EQ",
    "spellbak": "czary",
    "lookbak": "wygląd",
    "tpbak": "teleport",
    "worldbak": "flagi świata",
    "flagbak": "flagi",
    "gracebak": "łaski",
    "unlockbak": "masowe nadawanie",
    "copybak": "kopiowanie postaci",
    "swapbak": "podmiana slotów",
    "clearbak": "czyszczenie slotu",
    "steamidbak": "SteamID",
    "importbak": "import postaci",
    "restorebak": "przywrócenie kopii",
    "test": "test",
}

_MAX = 500


def path(save_path):
    return Path(str(save_path) + ".rezur-journal.json")


def load(save_path):
    p = path(save_path)
    if not p.is_file():
        return {"entries": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"entries": []}


def record(save_path, op, note=None):
    """Dopisuje wpis o udanej modyfikacji (po zapisie!). Zwraca wpis."""
    doc = load(save_path)
    entry = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "op": op}
    if note:
        entry["note"] = note
    doc["entries"].append(entry)
    doc["entries"] = doc["entries"][-_MAX:]
    p = path(save_path)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return entry


def summary(save_path):
    """{count, first, last, ops{etykieta: liczba}} — do panelu ryzyka/doctora."""
    es = load(save_path)["entries"]
    ops = {}
    for e in es:
        label = OP_LABELS.get(e.get("op"), e.get("op", "?"))
        ops[label] = ops.get(label, 0) + 1
    return {
        "count": len(es),
        "first": es[0]["ts"] if es else None,
        "last": es[-1]["ts"] if es else None,
        "ops": ops,
    }


def clear(save_path):
    p = path(save_path)
    if p.is_file():
        p.unlink()
        return True
    return False
