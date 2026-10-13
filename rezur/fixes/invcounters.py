"""Naprawa liczników ekwipunku — liczby zajętych wpisów muszą zgadzać się
z realną zawartością (common_count / key_count w held i storage).

Rozjazd tych liczników potrafi wywołać „no space for items" w grze mimo
wolnych miejsc (albo odwrotnie — nadpisać wpisy). Naprawa nic nie przenosi,
tylko PRZELICZA liczniki na podstawie zawartości.
"""

import struct

from ..core import inventory
from .base import Fix, FixResult, iter_parsed_slots

_LOCS = (("held", "inventory_held"), ("storage", "storage"))


def _diff(slot):
    """[(loc, kind, declared, actual), ...] dla policzalnych rozjazdów."""
    out = []
    for loc, key in _LOCS:
        inv = inventory.read(slot.raw, slot.offsets[key], loc)
        for kind in ("common", "key"):
            declared = inv[f"{kind}_count"]
            actual = sum(1 for h, _q, _a in inv[f"{kind}_items"] if h)
            if declared != actual:
                out.append((loc, kind, declared, actual))
    return out


class InvCountersFix(Fix):
    id = "invcounters"
    title = "Liczniki ekwipunku"
    description = "Przelicza liczby zajętych wpisów (held/skrzynia, common/key) na podstawie zawartości."

    def detect(self, save):
        targets = []
        for i, slot, _prof in iter_parsed_slots(save):
            for loc, kind, declared, actual in _diff(slot):
                targets.append(f"slot{i} {loc}/{kind}: {declared} → {actual}")
        return targets

    def apply(self, save, targets=None):
        res = FixResult(self.id)
        for i, slot, _prof in iter_parsed_slots(save):
            diffs = _diff(slot)
            if not diffs:
                continue
            for loc, key in _LOCS:
                inv = inventory.read(slot.raw, slot.offsets[key], loc)
                L = inv["layout"]
                for kind in ("common", "key"):
                    actual = sum(1 for h, _q, _a in inv[f"{kind}_items"] if h)
                    if inv[f"{kind}_count"] != actual:
                        struct.pack_into(
                            "<I", save.data, slot.abs_off + L[f"{kind}_count"], actual
                        )
            save.touch_slot(i)
            res.applied.append(
                f"slot{i}: " + ", ".join(f"{loc}/{k} {d}→{a}" for loc, k, d, a in diffs)
            )
        if not res.applied:
            res.skipped.append("liczniki już się zgadzają")
        return res
