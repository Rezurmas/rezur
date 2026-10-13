"""Inventory: wpisy 12 B (handle, quantity, acquisition_index).

Układ bloku: [common_count u32][common×12 B][key_count u32][key×12 B]
             [equip_index_counter u32][acquisition_index_counter u32]
Pojemności: held (0xA80 common, 0x180 key), storage (0x780, 0x80).
Liczniki to liczba ZAJĘTYCH wpisów; equip_index_counter to high-water mark
indeksów. Nowe acquisition_index = max(wszystkie niezerowe wpisy)+2 (port).
"""

import struct

CAPS = {"held": (0xA80, 0x180), "storage": (0x780, 0x80)}
ENTRY = 12


def layout(off, location):
    common_cap, key_cap = CAPS[location]
    common_count_off = off
    common_off = off + 4
    key_count_off = common_off + common_cap * ENTRY
    key_off = key_count_off + 4
    equip_off = key_off + key_cap * ENTRY
    acq_off = equip_off + 4
    return {
        "common_count": common_count_off,
        "common": common_off,
        "key_count": key_count_off,
        "key": key_off,
        "equip_counter": equip_off,
        "acq_counter": acq_off,
        "common_cap": common_cap,
        "key_cap": key_cap,
    }


def read(raw, off, location):
    L = layout(off, location)
    out = {
        "common_count": struct.unpack_from("<I", raw, L["common_count"])[0],
        "key_count": struct.unpack_from("<I", raw, L["key_count"])[0],
        "equip_counter": struct.unpack_from("<I", raw, L["equip_counter"])[0],
        "acq_counter": struct.unpack_from("<I", raw, L["acq_counter"])[0],
        "common_items": [],
        "key_items": [],
        "layout": L,
    }
    for i in range(L["common_cap"]):
        h, q, a = struct.unpack_from("<3I", raw, L["common"] + i * ENTRY)
        out["common_items"].append((h, q, a))
    for i in range(L["key_cap"]):
        h, q, a = struct.unpack_from("<3I", raw, L["key"] + i * ENTRY)
        out["key_items"].append((h, q, a))
    return out


def first_empty(items):
    for i, (h, _q, _a) in enumerate(items):
        if h == 0:
            return i
    return -1


def find_handle(items, handle):
    for i, (h, _q, _a) in enumerate(items):
        if h == handle:
            return i
    return -1


def next_acq_index(raw, held_off, storage_off):
    """max(acquisition_index po obu inventory) + 2 (jak w grze/er-save-manager)."""
    top = 0
    for off, loc in ((held_off, "held"), (storage_off, "storage")):
        inv = read(raw, off, loc)
        for lst in (inv["common_items"], inv["key_items"]):
            for h, _q, a in lst:
                if h != 0 and a < 0x7FFFFFFF and a > top:
                    top = a
    return top + 2


def write_entry(buf, off, location, inv_slot, is_key, handle, qty, acq_idx):
    """Wpisuje wpis i aktualizuje liczniki. buf = bytearray slotu (slot-relative)."""
    L = layout(off, location)
    base = (L["key"] if is_key else L["common"]) + inv_slot * ENTRY
    struct.pack_into("<3I", buf, base, handle, qty, acq_idx)

    common_items = [
        struct.unpack_from("<3I", buf, L["common"] + i * ENTRY) for i in range(L["common_cap"])
    ]
    key_items = [
        struct.unpack_from("<3I", buf, L["key"] + i * ENTRY) for i in range(L["key_cap"])
    ]
    struct.pack_into("<I", buf, L["common_count"], sum(1 for h, _q, _a in common_items if h))
    struct.pack_into("<I", buf, L["key_count"], sum(1 for h, _q, _a in key_items if h))

    index = inv_slot if is_key else L["key_cap"] + inv_slot
    top = L["key_cap"] + L["common_cap"] - 1
    equip = struct.unpack_from("<I", buf, L["equip_counter"])[0]
    struct.pack_into("<I", buf, L["equip_counter"], min(max(equip, index), top))
    struct.pack_into("<I", buf, L["acq_counter"], acq_idx)
    return base
