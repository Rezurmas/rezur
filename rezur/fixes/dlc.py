"""Naprawa flag DLC: zerowanie nieużywanych bajtów [4..49] w bloku CSDlc.

Niezerowe wartości w nieużywanych polach potrafią blokować wczytanie save'a.
"""

from .base import Fix, FixResult, iter_parsed_slots


class DLCFix(Fix):
    id = "dlc"
    title = "DLC: niezerowe pola nieużywane"
    description = "Zeruje bajty 4..49 bloku DLC; przelicza MD5 slotu."

    def detect(self, save):
        out = []
        for i, slot, _prof in iter_parsed_slots(save):
            if slot.dlc_flags()[4] > 0:
                out.append(i)
        return out

    def apply(self, save, targets=None):
        targets = self.detect(save) if targets is None else targets
        res = FixResult(self.id, targets=list(targets))
        for i in targets:
            slot = next(s for idx, s, _ in iter_parsed_slots(save) if idx == i)
            off = slot.abs_off + slot.tail["dlc"] + 4
            if any(save.data[off : off + 46]):
                save.data[off : off + 46] = b"\x00" * 46
                save.touch_slot(i)
                res.applied.append(f"slot{i}: wyzerowane nieużywane pola DLC (+MD5)")
            else:
                res.skipped.append(f"slot{i}: już zerowe")
        return res
