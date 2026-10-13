"""F4+ — nazwane flagi świata (bossowie, cookbooki, łzy, mapy, wspomnienia...).

Źródło: db_er/event_flags.json — 22 grupy, ~4200 flag z nazwami (baza
społecznościowa, jak w ER-Save-Editor). Ustawianie idzie przez BST gry
(te same offsety co gra): 1 = zdobyte/zabity/odkryte, 0 = skasowane/ożywiony boss.
"""

import json

from ..core import flags as F
from ..core.profiles import roster
from ..core.resources import data_path
from ..core.slots import SLOT_BODY, Slot

_cache = None
_EXTRA = "event_flags_extra.json"  # grupy spoza bazy głównej: colosseums, baseny, regiony inwazji


def _db():
    global _cache
    if _cache is None:
        with open(data_path("db_er", "event_flags.json"), encoding="utf-8") as f:
            _cache = json.load(f)
        try:
            with open(data_path("db_er", _EXTRA), encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    _cache.setdefault(k, v)
        except OSError:
            pass
    return _cache


def search_names(query, limit=60):
    """Szuka fragmentu nazwy po WSZYSTKICH grupach flag. [(grupa, id, nazwa)]."""
    q = (query or "").lower()
    out = []
    for group, rows in _db().items():
        for row in rows:
            fid, name = row[0], row[1]
            if q in name.lower() or q == str(fid):
                out.append((group, fid, name))
                if len(out) >= limit:
                    return out
    return out


def groups():
    """{nazwa_grupy: liczba_flag}."""
    return {k: len(v) for k, v in _db().items()}


def entries(group, query=None, limit=200):
    data = _db()
    if group not in data:
        raise ValueError(f"nie znam grupy {group!r} (są: {', '.join(sorted(data))})")
    out = []
    q = (query or "").lower()
    for row in data[group]:
        fid, name = row[0], row[1]
        desc = row[2] if len(row) > 2 else ""
        if q and q not in name.lower() and q not in str(fid):
            continue
        out.append((fid, name, desc))
        if len(out) >= limit:
            break
    return out


def _parsed(save, i):
    r = roster(save)
    s = Slot(save, i)
    if s.is_empty:
        raise ValueError(f"slot{i} jest pusty")
    if not s.parse(r[i]["name"], r[i]["level"]):
        raise ValueError(f"slot{i}: {s.reason}")
    return s


def view(save, slot_idx, group, query=None, limit=200):
    """Lista flag grupy z aktualnym stanem w savie."""
    s = _parsed(save, slot_idx)
    ef = s.event_flags()
    out = []
    for fid, name, desc in entries(group, query, limit):
        try:
            cur = F.get_flag(ef, fid)
        except ValueError:
            cur = None
        out.append({"id": fid, "name": name, "desc": desc, "value": cur})
    return {"slot": slot_idx, "group": group, "entries": out}


def set_world(save, slot_idx, group, selector=None, value=True, query=None,
              set_all=False, apply=True):
    """Ustawia flagę(-gi) grupy. selector: 'ID' albo fragment nazwy.
    set_all=True: cała grupa (opcjonalnie zawężona --query)."""
    s = _parsed(save, slot_idx)
    work = bytearray(save.data[s.abs_off : s.abs_off + SLOT_BODY])
    ef_off = s.offsets["event_flags"]
    fbuf = bytearray(work[ef_off : ef_off + F.EVENT_FLAGS_SIZE])

    if set_all:
        cands = entries(group, query, limit=100000)
    else:
        if selector is None:
            raise ValueError("podaj selector (ID albo fragment nazwy) albo --all")
        sel = str(selector).strip()
        if sel.isdigit():
            row = next((r for r in _db()[group] if str(r[0]) == sel), None)
            cands = [row] if row else []
            if not cands:
                raise ValueError(f"nie ma flagi o ID {sel} w grupie {group!r}")
        else:
            cands = entries(group, sel, limit=100000)
            if not cands:
                raise ValueError(f"nic nie pasuje do {sel!r} w grupie {group!r}")

    done, skipped = [], 0
    for row in cands:
        if row is None:
            continue
        fid, name = row[0], row[1]
        try:
            cur = F.get_flag(fbuf, fid)
            if cur == value:
                skipped += 1
                continue
            F.set_flag(fbuf, fid, value)
            done.append((fid, name))
        except ValueError:
            skipped += 1

    if apply and done:
        work[ef_off : ef_off + F.EVENT_FLAGS_SIZE] = fbuf
        save.data[s.abs_off : s.abs_off + SLOT_BODY] = work
        save.touch_slot(slot_idx)
    return {"slot": slot_idx, "group": group, "value": value, "set": len(done),
            "already_or_unknown": skipped, "sample": done[:10], "applied": apply}
