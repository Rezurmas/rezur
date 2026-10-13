"""F2 — edycja postaci: statystyki, runy, imię. Z walidacją levelu i synchronizacją."""
import struct

from ..core import checksums
from ..core.profiles import roster, summary_from_slot, summary_bytes, write_summary
from ..core.slots import Slot

STAT_NAMES = ("vigor", "mind", "endurance", "strength", "dexterity", "intelligence", "faith", "arcane")


def _parsed(save, i):
    r = roster(save)
    s = Slot(save, i)
    if s.is_empty:
        raise ValueError(f"slot{i} jest pusty")
    if not s.parse(r[i]["name"], r[i]["level"]):
        raise ValueError(f"slot{i}: {s.reason}")
    return s


def _resync_summary(save, i, s=None):
    if s is None:
        s = _parsed(save, i)
    else:
        # świeży widok na dane PO edycji (stary snapshot `raw` kłamałby),
        # offsety i ogon bierzemy z już sparsowanego slotu
        fresh = Slot(save, i)
        fresh.offsets = dict(s.offsets)
        fresh.tail = dict(s.tail)
        fresh.ok = True
        s = fresh
    cur = summary_bytes(save, i)
    new = summary_from_slot(save, s, cur)
    if new != cur:
        write_summary(save, i, new)


def set_stats(save, slot_idx, changes, resync_summary=True):
    """changes: dict nazwa->wartość (np. {"vigor": 60}). Zwraca raport."""
    s = _parsed(save, slot_idx)
    stats = s.pgd_stats()
    old = list(stats)
    for k, v in changes.items():
        if k not in STAT_NAMES:
            raise ValueError(f"nieznana statystyka {k!r} (dozwolone: {', '.join(STAT_NAMES)})")
        if not (1 <= v <= 99):
            raise ValueError(f"{k}={v} poza zakresem 1..99")
        stats[STAT_NAMES.index(k)] = v
    level = sum(stats) - 79
    if not (1 <= level <= 713):
        raise ValueError(f"level {level} poza zakresem")
    pgd_abs = s.abs_off + s.offsets["pgd"]
    struct.pack_into("<8I", save.data, pgd_abs + 0x34, *stats)
    struct.pack_into("<I", save.data, pgd_abs + 0x60, level)
    checksums.refresh_player_hash(
        save.data, s.abs_off, s.offsets["pgd"], s.offsets["item_ids"], s.offsets["spells"], s.tail["hash"]
    )
    save.touch_slot(slot_idx)
    if resync_summary:
        _resync_summary(save, slot_idx, s)
    return {"slot": slot_idx, "old_stats": old, "new_stats": stats, "new_level": level}


def set_runes(save, slot_idx, runes=None, runes_memory=None, resync_summary=True):
    s = _parsed(save, slot_idx)
    pgd_abs = s.abs_off + s.offsets["pgd"]
    out = {"slot": slot_idx}
    if runes is not None:
        if not (0 <= runes <= 0xFFFFFFFF):
            raise ValueError("runes poza zakresem")
        out["old_runes"] = s.pgd_runes()
        struct.pack_into("<I", save.data, pgd_abs + 0x64, runes)
        out["runes"] = runes
    if runes_memory is not None:
        if not (0 <= runes_memory <= 0xFFFFFFFF):
            raise ValueError("runes_memory poza zakresem")
        out["old_runes_memory"] = s.pgd_runes_memory()
        struct.pack_into("<I", save.data, pgd_abs + 0x68, runes_memory)
        out["runes_memory"] = runes_memory
    checksums.refresh_player_hash(
        save.data, s.abs_off, s.offsets["pgd"], s.offsets["item_ids"], s.offsets["spells"], s.tail["hash"]
    )
    save.touch_slot(slot_idx)
    if resync_summary:
        _resync_summary(save, slot_idx, s)
    return out


def rename(save, slot_idx, name):
    if not name or len(name) > 16:
        raise ValueError("imię: 1..16 znaków")
    s = _parsed(save, slot_idx)
    old = s.pgd_name()
    enc = name.encode("utf-16-le")
    pgd_abs = s.abs_off + s.offsets["pgd"]
    save.data[pgd_abs + 0x94 : pgd_abs + 0x94 + 32] = enc.ljust(32, b"\x00")
    save.data[pgd_abs + 0xB4 : pgd_abs + 0xB6] = b"\x00\x00"
    save.touch_slot(slot_idx)
    _resync_summary(save, slot_idx, s)
    return {"slot": slot_idx, "old_name": old, "new_name": name}
