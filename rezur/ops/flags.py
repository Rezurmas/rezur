"""F4 — flagi świata i łaski.

Flagi: bity w bloku slotu (offset z parsera), adresowane BST z gry.
Łaski: graces.json (region -> [[flag, nazwa], ...]) — ustawienie flagi = wpis
odkryty (podróż z mapy). Dane pochodzą z bazy społecznościowej; przy niepewnych
flagach warto zweryfikować w grze.
"""

import json

from ..core import flags as F
from ..core.profiles import roster
from ..core.resources import data_path
from ..core.slots import SLOT_BODY, Slot


def _parsed(save, i):
    r = roster(save)
    s = Slot(save, i)
    if s.is_empty:
        raise ValueError(f"slot{i} jest pusty")
    if not s.parse(r[i]["name"], r[i]["level"]):
        raise ValueError(f"slot{i}: {s.reason}")
    return s


def get_flag(save, slot_idx, event_id):
    return _parsed(save, slot_idx).get_flag(event_id)


def set_flag(save, slot_idx, event_id, state=True):
    s = _parsed(save, slot_idx)
    work = bytearray(save.data[s.abs_off : s.abs_off + SLOT_BODY])
    ef = s.offsets["event_flags"]
    fbuf = bytearray(work[ef : ef + F.EVENT_FLAGS_SIZE])
    F.set_flag(fbuf, event_id, state)
    work[ef : ef + F.EVENT_FLAGS_SIZE] = fbuf
    save.data[s.abs_off : s.abs_off + SLOT_BODY] = work
    save.touch_slot(slot_idx)
    return {"slot": slot_idx, "event_id": event_id, "state": state}


def graces():
    with open(data_path("db_er", "graces.json"), encoding="utf-8") as f:
        return json.load(f)


def unlock_graces(save, slot_idx, region=None, apply=True):
    """Ustawia flagi łask (wszystkie regiony albo wskazany). Zwraca raport."""
    data = graces()
    if region:
        matches = {k: v for k, v in data.items() if region.lower() in k.lower()}
        if not matches:
            raise ValueError(f"nie znam regionu {region!r} (są: {len(data)} regionów)")
    else:
        matches = data

    s = _parsed(save, slot_idx)
    work = bytearray(save.data[s.abs_off : s.abs_off + SLOT_BODY])
    ef = s.offsets["event_flags"]
    fbuf = bytearray(work[ef : ef + F.EVENT_FLAGS_SIZE])

    done, skipped = [], 0
    for reg, items in matches.items():
        for fid, gname in items:
            try:
                if F.get_flag(fbuf, fid):
                    skipped += 1
                    continue
                F.set_flag(fbuf, fid, True)
                done.append((reg, fid, gname))
            except ValueError:
                skipped += 1
    if apply and done:
        work[ef : ef + F.EVENT_FLAGS_SIZE] = fbuf
        save.data[s.abs_off : s.abs_off + SLOT_BODY] = work
        save.touch_slot(slot_idx)
    return {"slot": slot_idx, "regions": len(matches), "set": len(done),
            "already_or_unknown": skipped, "sample": done[:8], "applied": apply}
