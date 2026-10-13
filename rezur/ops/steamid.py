"""Patcher SteamID — przenoszenie save'ów między kontami Steam.

SteamID64 występuje: w USER_DATA_10 (+0x04) oraz raz w każdym zajętym slocie
(w ogonie, przed ps5_activity/dlc). Wymienia wszystkie wystąpienia starego ID.
"""

import struct

from ..core.reader import find_all


def change_steam_id(save, new_sid):
    """Wymienia SteamID w UD10 i we wszystkich zajętych slotach. Zwraca raport."""
    if not (10**16 <= new_sid < 10**17):
        raise ValueError("SteamID64 to 17 cyfr")
    old = save.steam_id()
    if old == new_sid:
        return {"old": old, "new": new_sid, "slots": [], "skipped": "taki sam"}
    oldb = struct.pack("<Q", old)
    newb = struct.pack("<Q", new_sid)

    # UD10
    save.data[save.ud10_body + 0x04 : save.ud10_body + 0x0C] = newb
    save.touch_ud10()

    touched = []
    for i in range(10):
        e = save.slot_entries[i]
        if struct.unpack_from("<I", save.data, e["off"] + 16)[0] == 0:
            continue
        body = e["off"] + 16
        raw = bytes(save.data[body : body + 0x280000])
        offs = find_all(raw, oldb)
        if not offs:
            continue
        for o in offs:
            save.data[body + o : body + o + 8] = newb
        save.touch_slot(i)
        touched.append(i)
    return {"old": old, "new": new_sid, "slots": touched}
