"""Czary — 14 gniazd pamięci, po 8 B: (id, 0xFFFFFFFF).

Puste gniazdo to (0xFFFFFFFF, 0) — zweryfikowane na realnych save'ach.
PlayerDataHash pokrywa pierwsze u32 każdego gniazda, więc po każdej zmianie
hash jest przeliczany.
"""

import struct

from ..core import checksums, items_db
from ..core.profiles import roster
from ..core.slots import Slot
from .items import inventory_hit, parse_selector

SPELL_SLOTS = 14
_EMPTY = 0xFFFFFFFF


def _parsed(save, i):
    r = roster(save)
    s = Slot(save, i)
    if s.is_empty:
        raise ValueError(f"slot{i} jest pusty")
    if not s.parse(r[i]["name"], r[i]["level"]):
        raise ValueError(f"slot{i}: {s.reason}")
    return s


def equipped(save, slot_idx):
    """Lista 14 gniazd: id + nazwa (albo puste)."""
    s = _parsed(save, slot_idx)
    out = []
    for k in range(SPELL_SLOTS):
        sid, extra = struct.unpack_from("<2I", s.raw, s.offsets["spells"] + k * 8)
        if sid == _EMPTY:
            out.append({"slot": k, "empty": True, "id": None, "name": None})
            continue
        name, _c = items_db.resolve(0x40000000 | (sid & 0x0FFFFFFF))
        if name is None:
            name, _c = items_db.resolve(sid)
        out.append({"slot": k, "empty": False, "id": sid,
                    "name": name or f"0x{sid:08X}", "extra": extra})
    return {"slot": slot_idx, "spells": out}


def _write(save, s, k, sid):
    """Pisze gniazdo (sid, 0xFFFFFFFF) albo puste (0xFFFFFFFF, 0) + refresh hash."""
    struct.pack_into(
        "<2I", save.data, s.abs_off + s.offsets["spells"] + k * 8,
        sid, _EMPTY if sid != _EMPTY else 0,
    )
    checksums.refresh_player_hash(
        save.data, s.abs_off, s.offsets["pgd"], s.offsets["item_ids"],
        s.offsets["spells"], s.tail["hash"],
    )


def memorize(save, slot_idx, selector, at=None):
    """Zapamiętuje czar (musi być w ekwipunku). at=None → pierwsze wolne gniazdo."""
    s = _parsed(save, slot_idx)
    kind, val = parse_selector(selector)
    if kind == "handle":
        base = val & 0x0FFFFFFF
        full = 0x40000000 | base
    else:
        full = val
        base = full & 0x0FFFFFFF
    handle = None
    for h in (0xB0000000 | base, 0xA0000000 | base):
        if inventory_hit(save, slot_idx, h):
            handle = h
            break
    if handle is None:
        raise ValueError(f"nie ma {selector!r} w ekwipunku — najpierw dodaj: item --slot … --add")
    ids = [struct.unpack_from("<I", s.raw, s.offsets["spells"] + k * 8)[0] for k in range(SPELL_SLOTS)]
    if at is None:
        at = next((k for k in range(SPELL_SLOTS) if ids[k] == _EMPTY), None)
        if at is None:
            raise ValueError("wszystkie 14 gniazd czarów są zajęte")
    if not (0 <= at < SPELL_SLOTS):
        raise ValueError("at 0..13")
    _write(save, s, at, base)
    save.touch_slot(slot_idx)
    name, _c = items_db.resolve(full)
    return {"slot": slot_idx, "at": at, "id": base, "name": name or f"0x{base:X}"}


def forget(save, slot_idx, at):
    """Zwalnia gniazdo."""
    s = _parsed(save, slot_idx)
    if not (0 <= at < SPELL_SLOTS):
        raise ValueError("at 0..13")
    _write(save, s, at, _EMPTY)
    save.touch_slot(slot_idx)
    return {"slot": slot_idx, "freed": at}


def clear(save, slot_idx):
    """Zwalnia wszystkie 14 gniazd."""
    s = _parsed(save, slot_idx)
    for k in range(SPELL_SLOTS):
        _write(save, s, k, _EMPTY)
    save.touch_slot(slot_idx)
    return {"slot": slot_idx, "cleared": SPELL_SLOTS}
