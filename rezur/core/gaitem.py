"""GaItem map — tablica instancji itemów w slocie (start 0x20, rekordy 8/16/21 B).

Rozmiar rekordu zależy od górnego nibbla HANDLE'a:
    handle 0x0 (pusty)   → 8 B
    handle 0x8 (broń)    → 21 B  (handle, id, unk, unk, gem_handle(AoW), unk)
    handle 0x9 (zbroja)  → 16 B  (handle, id, unk, unk)
    handle 0xC (AoW)     → 8 B   (tylko wpis w gaitem, bez inventory)
    handle inny != 0     → 16 B (ochrona na nieznane)
Liczba wpisów: 5118 (version <= 81) albo 5120.
Koniec spaceru MUSI trafić w początek PlayerGameData (pgd = anchor−0x34) — to
najmocniejsza walidacja poprawności.

Handle: bity 28-31 kategoria, 16-23 generacja (0x80-0xFF, pierścień), 0-15
indeks (unikalny w obrębie wszystkich kategorii).
"""

import struct

GAITEM_START = 0x20
COUNT_OLD = 0x13FE   # 5118
COUNT_NEW = 0x1400   # 5120

PREFIX_WEAPON = 0x80000000
PREFIX_ARMOR = 0x90000000
PREFIX_GEM = 0xC0000000


def count_for(version):
    return COUNT_OLD if version <= 81 else COUNT_NEW


def entry_size(handle):
    if handle == 0:
        return 8
    t = handle & 0xF0000000
    if t == PREFIX_GEM:
        return 8
    if t == PREFIX_WEAPON:
        return 21
    return 16


def walk(raw, version, expect_end=None):
    """Zwraca (entries, end_offset). entries: dict(off, handle, item_id, size, ...).
    expect_end: jeśli podane, waliduje koniec spaceru (zgodność z PGD)."""
    entries = []
    o = GAITEM_START
    for _ in range(count_for(version)):
        handle = struct.unpack_from("<I", raw, o)[0]
        item_id = struct.unpack_from("<I", raw, o + 4)[0]
        e = {"off": o, "handle": handle, "item_id": item_id, "size": entry_size(handle)}
        if e["size"] >= 16:
            e["unk10"] = struct.unpack_from("<i", raw, o + 8)[0]
            e["unk14"] = struct.unpack_from("<i", raw, o + 12)[0]
        if e["size"] == 21:
            e["gem"] = struct.unpack_from("<i", raw, o + 16)[0]
            e["unk1c"] = raw[o + 20]
        entries.append(e)
        o += e["size"]
    if expect_end is not None and o != expect_end:
        raise ValueError(f"gaitem walk end 0x{o:X} != PGD 0x{expect_end:X}")
    return entries, o


def make_entry_bytes(kind, handle, item_id):
    """Serializuje nowy wpis: kind ∈ weapon/armor/gem."""
    if kind == "weapon":
        return struct.pack("<IIiiIB", handle, item_id, 0, 0, 0xFFFFFFFF, 0)
    if kind == "armor":
        return struct.pack("<IIii", handle, item_id, 0, 0)
    return struct.pack("<II", handle, item_id)


def kind_of(full_id):
    """Kategoria po górnym nibblu pełnego item id."""
    t = (full_id >> 28) & 0xF
    return {0x0: "weapon", 0x1: "armor", 0x2: None, 0x4: None, 0x8: "gem"}.get(t)


def next_handle(entries, kind):
    """Następny wolny handle wg logiki gry (pierścień generacji 0x80-0xFF).

    Port z er-save-manager (zweryfikowany na realnych save'ach)."""
    limit = len(entries)
    used = set()
    by_gen = {}
    for g in entries:
        h = g["handle"]
        if h == 0:
            continue
        index = h & 0xFFFF
        used.add(index)
        if (h & 0xF0000000) not in (PREFIX_WEAPON, PREFIX_ARMOR, PREFIX_GEM) or index >= limit:
            continue
        gen = (h >> 16) & 0xFF
        if gen & 0x80:
            by_gen[gen] = max(by_gen.get(gen, -1), index)

    if by_gen:
        gens = sorted(by_gen)
        gaps = [((gens[(i + 1) % len(gens)] - g - 1) % 0x80, g) for i, g in enumerate(gens)]
        gen = max(gaps)[1]
        index = by_gen[gen]
    else:
        gen, index = 0x80, -1

    for _ in range(limit):
        index += 1
        if index >= limit:
            index = 0
            gen = 0x80 if gen == 0xFF else gen + 1
        if index not in used:
            break
    else:
        raise ValueError("gaitem handle space is full")

    prefix = {"weapon": 0x80, "armor": 0x90, "gem": 0xC0}[kind]
    return (prefix << 24) | (gen << 16) | index


def find_empty_index(entries, kind):
    """Wybór pustego wpisu: AoW przed pierwszym orężem; broń/zbroja — OSTATNI pusty
    za pierwszym orężem (wymóg algorytmu wstawiania bez sierot)."""
    first_weapon = -1
    for i, g in enumerate(entries):
        if g["handle"] != 0 and (g["handle"] & 0xF0000000) == PREFIX_WEAPON:
            first_weapon = i
            break
    if kind == "gem":
        for i, g in enumerate(entries):
            if first_weapon != -1 and i >= first_weapon:
                break
            if g["handle"] == 0:
                return i
        return -1
    start = first_weapon + 1 if first_weapon != -1 else 0
    result = -1
    for i in range(start, len(entries)):
        if entries[i]["handle"] == 0:
            result = i
    return result


def last_empty(entries):
    result = None
    for g in entries:
        if g["handle"] == 0:
            result = g["off"]
    return result
