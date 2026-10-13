"""Naprawa buga Torrenta: hp=0 + stan ACTIVE(13) → DEAD(3).

Objaw: zawieszka (infinite loading) przy wczytywaniu postaci — typowy efekt
wyjścia z gry przez Alt+F4 w trakcie jazdy. Zmiana: jeden u32 w RideGameData
(+0x24) + przeliczenie MD5 slotu. PlayerDataHash tego nie obejmuje.
"""

import struct

from ..core.slots import HORSE_STATE_OFF, STATE_ACTIVE, STATE_DEAD, STATE_NAMES
from .base import Fix, FixResult, iter_parsed_slots


class TorrentFix(Fix):
    id = "torrent"
    title = "Torrent: hp=0 + ACTIVE (zawieszka przy wczytywaniu)"
    description = "Ustawia stan Torrenta na DEAD; przelicza MD5 slotu."

    def detect(self, save):
        out = []
        for i, slot, _prof in iter_parsed_slots(save):
            h = slot.horse()
            if h["hp"] == 0 and h["state"] == STATE_ACTIVE:
                out.append(i)
        return out

    def apply(self, save, targets=None):
        targets = self.detect(save) if targets is None else targets
        res = FixResult(self.id, targets=list(targets))
        for i in targets:
            slot = next(s for idx, s, _ in iter_parsed_slots(save) if idx == i)
            h = slot.horse()
            if not (h["hp"] == 0 and h["state"] == STATE_ACTIVE):
                res.skipped.append(f"slot{i}: bug już nie występuje")
                continue
            off = slot.abs_off + slot.offsets["horse"] + HORSE_STATE_OFF
            save.data[off : off + 4] = struct.pack("<I", STATE_DEAD)
            save.touch_slot(i)
            res.applied.append(
                f"slot{i}: Torrent {STATE_NAMES[STATE_ACTIVE]} -> {STATE_NAMES[STATE_DEAD]} (+MD5)"
            )
        return res
