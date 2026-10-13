"""Baza napraw: klasa Fix + wspólny iterator sparsowanych slotów."""

from dataclasses import dataclass, field

from ..core.profiles import roster
from ..core.slots import Slot


@dataclass
class FixResult:
    fix_id: str
    applied: list = field(default_factory=list)   # opisy wykonanych działań
    skipped: list = field(default_factory=list)   # opisy pominiętych
    targets: list = field(default_factory=list)   # wykryte cele (dry-run)


class Fix:
    id = "base"
    title = "Base"
    description = ""

    def detect(self, save):  # -> lista celów (slot idx lub opisy)
        raise NotImplementedError

    def apply(self, save, targets=None):  # -> FixResult
        raise NotImplementedError


def iter_parsed_slots(save):
    """(idx, slot, profile_dict) dla zajętych i sparsowanych slotów."""
    r = roster(save)
    for i in range(10):
        slot = Slot(save, i)
        if slot.is_empty:
            continue
        if slot.parse(r[i]["name"], r[i]["level"]):
            yield i, slot, r[i]
