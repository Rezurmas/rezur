"""Eksport JSON (pod GUI/API i skrypty)."""

from ..core.profiles import roster
from ..core.slots import Slot


def save_to_dict(save, findings=None):
    r = roster(save)
    chars = []
    for i in range(10):
        prof = r[i]
        entry = {"slot": i, "profile": prof, "character": None, "unparsed_reason": None}
        s = Slot(save, i)
        if not s.is_empty:
            if s.parse(prof["name"], prof["level"]):
                entry["character"] = s.character()
            else:
                entry["unparsed_reason"] = s.reason
        chars.append(entry)
    out = {
        "file": str(save.path),
        "steam_id": save.steam_id(),
        "sections": save.section_md5_status(),
        "characters": chars,
    }
    if findings is not None:
        out["findings"] = [
            {"level": f.level, "code": f.code, "message": f.message, "slot": f.slot, "fix": f.fix}
            for f in findings
        ]
    return out
