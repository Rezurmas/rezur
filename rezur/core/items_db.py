"""Baza itemów (JSON-y z db_er): id -> nazwa + rozwiązywanie i szukanie.

Kategorie po górnym nibblu pełnego id:
    0x0 weapons (klucze = gołe base id, bez bitów kategorii)
    0x1 armors, 0x2 talismans, 0x4 goods, 0x8 ashes (klucze = pełne id)

Bronie: id = base + affinity*100 + reinforcement; nazwę niesie wiersz
afinitetu (id - id%100), fallback: goły base (id - id%10000).
"""

import json

from .resources import data_path

CAT_BY_NIBBLE = {0x0: "weapons", 0x1: "armors", 0x2: "talismans", 0x4: "goods", 0x8: "ashes"}
FILES = ("weapons", "armors", "talismans", "goods", "ashes")

_tables = None


def _load():
    global _tables
    if _tables is None:
        _tables = {}
        for cat in FILES:
            with open(data_path("db_er", cat + ".json"), encoding="utf-8") as f:
                _tables[cat] = {int(k, 16): v for k, v in json.load(f).items()}
    return _tables


def category_of(full_id):
    return CAT_BY_NIBBLE.get((full_id >> 28) & 0xF)


def resolve(full_id):
    """(nazwa, kategoria) albo (None, kategoria/None)."""
    tables = _load()
    cat = category_of(full_id)
    if cat is None:
        return None, None
    table = tables.get(cat, {})
    name = table.get(full_id)
    if name is not None or cat != "weapons":
        return name, cat
    level = full_id % 100
    if level > 25:
        level = 0
    for step in (100, 10000):
        name = table.get(full_id - full_id % step)
        if name is not None:
            return (f"{name} +{level}" if level else name), cat
    return None, cat


def search(query, limit=40):
    """Szukanie po podłańcuchu nazwy (case-insensitive). [(full_id, nazwa, kategoria)]."""
    tables = _load()
    q = query.lower()
    out = []
    for cat, table in tables.items():
        for fid, name in table.items():
            if q in name.lower():
                out.append((fid, name, cat))
                if len(out) >= limit:
                    return out
    return out


def find_exact(name):
    tables = _load()
    q = name.strip().lower()
    for cat, table in tables.items():
        for fid, nm in table.items():
            if nm.lower() == q:
                return fid, nm, cat
    return None


def weapon_full_id(base, upgrade=0):
    return base + max(0, upgrade)


def direct_full_id(cat, base):
    prefix = {"armors": 0x10000000, "talismans": 0x20000000, "goods": 0x40000000, "ashes": 0x80000000}[cat]
    return prefix | (base & 0x0FFFFFFF)


def key_item_ids():
    with open(data_path("db_er", "key_item_ids.json"), encoding="utf-8") as f:
        return frozenset(json.load(f))
