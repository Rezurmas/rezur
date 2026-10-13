"""Wygląd — gender (0xB6), typ ciała (0xB8), archetyp (0xB7), dar (0xBB).

PlayerDataHash pokrywa archetyp i bajt 0xB8, więc po zmianie hash jest
przeliczany; profil na ekranie wyboru postaci jest synchronizowany.
Typ ciała: 0 = A, 1 = B (jak „Body Type" w ER-Save-Editor).
"""

from ..core import checksums
from ..core.profiles import roster
from ..core.slots import Slot
from .stats import _resync_summary

_OFF_GENDER = 0xB6
_OFF_BODY = 0xB8
_OFF_GIFT = 0xBB


def _parsed(save, i):
    r = roster(save)
    s = Slot(save, i)
    if s.is_empty:
        raise ValueError(f"slot{i} jest pusty")
    if not s.parse(r[i]["name"], r[i]["level"]):
        raise ValueError(f"slot{i}: {s.reason}")
    return s


def read(save, slot_idx):
    s = _parsed(save, slot_idx)
    pgd = s.offsets["pgd"]
    return {
        "slot": slot_idx,
        "gender": s.pgd_gender(),
        "body_type": s.raw[pgd + _OFF_BODY],
        "archetype": s.pgd_archetype(),
        "gift": s.pgd_gift(),
    }


def set_appearance(save, slot_idx, gender=None, body_type=None, gift=None):
    s = _parsed(save, slot_idx)
    pgd = s.abs_off + s.offsets["pgd"]
    out = {"slot": slot_idx}
    if gender is not None:
        if gender not in (0, 1):
            raise ValueError("gender: 0 albo 1")
        out["old_gender"] = save.data[pgd + _OFF_GENDER]
        save.data[pgd + _OFF_GENDER] = gender
        out["gender"] = gender
    if body_type is not None:
        if body_type not in (0, 1):
            raise ValueError("body_type: 0 (A) albo 1 (B)")
        out["old_body_type"] = save.data[pgd + _OFF_BODY]
        save.data[pgd + _OFF_BODY] = body_type
        out["body_type"] = body_type
    if gift is not None:
        if not (0 <= gift <= 255):
            raise ValueError("gift 0..255")
        out["old_gift"] = save.data[pgd + _OFF_GIFT]
        save.data[pgd + _OFF_GIFT] = gift
        out["gift"] = gift
    if len(out) == 1:
        raise ValueError("nic do zmiany (--gender / --body / --gift)")
    checksums.refresh_player_hash(
        save.data, s.abs_off, s.offsets["pgd"], s.offsets["item_ids"],
        s.offsets["spells"], s.tail["hash"],
    )
    _resync_summary(save, slot_idx, s)
    save.touch_slot(slot_idx)
    return out
