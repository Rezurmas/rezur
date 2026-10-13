"""Teleport — przenoszenie postaci na bezpieczne lokacje.

Ustawia map_id nagłówka slotu + koordynaty w ogonie (główne i drugie, jak
referencja er-save-manager) i synchronizuje mapę w profilu. Koordynaty są
zapisywane tylko, gdy lokacja je definiuje albo podasz --xyz.

Użycie: postać uwięziona w DLC bez dodatku, w zepsutej lokacji, po „warp
sickness" — teleport do Limgrave/Roundtable.
"""

import struct

from ..core.profiles import roster
from ..core.slots import Slot
from .stats import _resync_summary

LOCATIONS = {
    "limgrave": {"label": "Limgrave — First Step", "map": bytes([0, 36, 42, 60]), "xyz": None},
    "roundtable": {"label": "Roundtable Hold", "map": bytes([0, 0, 10, 11]), "xyz": (-331.0, -22.0, -305.8)},
    "liurnia": {"label": "Liurnia — Lake-Facing Cliffs", "map": bytes([0, 37, 44, 60]), "xyz": None},
    "altus": {"label": "Altus — Erdtree-Gazing Hill", "map": bytes([0, 38, 46, 60]), "xyz": None},
}


def parse_map_name(text):
    """'m60_36_42_00' → int (u32, little-endian względem map_id gry)."""
    t = text.strip().lower()
    if not t.startswith("m"):
        raise ValueError('mapa w formacie "m60_36_42_00"')
    parts = t[1:].split("_")
    if len(parts) != 4:
        raise ValueError('mapa w formacie "m60_36_42_00"')
    a, b, c, d = (int(x) for x in parts)
    return (a << 24) | (b << 16) | (c << 8) | d


def _parsed(save, i):
    r = roster(save)
    s = Slot(save, i)
    if s.is_empty:
        raise ValueError(f"slot{i} jest pusty")
    if not s.parse(r[i]["name"], r[i]["level"]):
        raise ValueError(f"slot{i}: {s.reason}")
    return s


def info(save, slot_idx):
    s = _parsed(save, slot_idx)
    c = s.coordinates()
    return {"slot": slot_idx, "map_id": s.map_id, "map_name": s.map_name(),
            "xyz": c["xyz"], "spawn": s.spawn()}


def teleport(save, slot_idx, dest=None, map_id=None, xyz=None):
    s = _parsed(save, slot_idx)
    before = {"map_id": s.map_id, "map_name": s.map_name()}

    if dest:
        loc = LOCATIONS.get(dest.lower())
        if loc is None:
            raise ValueError(f"nie znam lokacji {dest!r} (są: {', '.join(LOCATIONS)})")
        mid = int.from_bytes(loc["map"], "little")
        if xyz is None and loc["xyz"]:
            xyz = loc["xyz"]
        label = loc["label"]
    elif map_id is not None:
        mid = map_id
        label = None
    else:
        raise ValueError("podaj --to NAZWA albo --map m60_XX_XX_XX")

    # nagłówek slotu: map_id
    struct.pack_into("<I", save.data, s.abs_off + 0x04, mid)
    # ogon: koordynaty (map_id + xyz + drugie xyz)
    c = s.tail["coords"]
    struct.pack_into("<I", save.data, s.abs_off + c + 12, mid)
    if xyz is not None:
        struct.pack_into("<3f", save.data, s.abs_off + c, *xyz)
        struct.pack_into("<3f", save.data, s.abs_off + c + 33, *xyz)

    # pogoda: area_id = bajt regionu nowej mapy (dokładnie to, co robi fix „weather")
    w = s.tail["weather"]
    struct.pack_into("<H", save.data, s.abs_off + w, (mid >> 24) & 0xFF)

    _resync_summary(save, slot_idx, s)
    save.touch_slot(slot_idx)
    s2 = _parsed(save, slot_idx)
    return {
        "slot": slot_idx,
        "from": before,
        "to": {"map_id": mid, "map_name": s2.map_name(), "label": label},
        "xyz_set": list(xyz) if xyz is not None else None,
    }
