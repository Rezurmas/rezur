"""Profile ekranu wyboru postaci (USER_DATA_10).

Zweryfikowane offsety (save 1.16-era):
    summaries[0] @ 0x195E, krok 0x24C (10 wpisów)
    10 bajtów "active" @ 0x1954 — w realnych save'ach ZAWSZE ZEROWE (nawet przy
    zajętych slotach); NIE traktować jako źródła prawdy. Prawdą jest obecność imienia.

Wpis profilu (0x24C): imię 16×u16+term, level u32@0x22, sekundy u32@0x26,
runes_memory u32@0x2A, map u32@0x2E, place_name u32@0x32, FACE 0x124@0x36,
ekwipunek 58×u32@0x15A, body_type/archetype/gift @0x242..0x244.
"""

import struct

PROFILE_BASE = 0x195E
PROFILE_SIZE = 0x24C
ACTIVE_BASE = 0x1954

# offsety w profilu
_P_NAME = 0x00
_P_LEVEL = 0x22
_P_SECONDS = 0x26
_P_RUNES_MEM = 0x2A
_P_MAP = 0x2E
_P_FACE = 0x36
_P_FACE_SIZE = 0x124
_P_EQUIP = 0x15A
_P_BODY = 0x242

# offsety w slocie
_S_HEADER_MAP = 0x04
_S_HEADER_PLAY_MS = 0x08
_S_PGD_NAME = 0x94
_S_PGD_NAME_SIZE = 0x22
_S_PGD_LEVEL = 0x60
_S_PGD_RUNES_MEM = 0x68
_S_PGD_GENDER = 0xB6
_S_PGD_ARCHETYPE = 0xB7
_S_PGD_GIFT = 0xBB

_EQUIP_ACTIVE_SLOTS = 2
_EQUIP_TAGGED = 9
_EQUIP_ITEM_IDS = 31
_EQUIP_SLOT_COUNT = 22
_ARMOR_SLOTS = range(12, 17)
_TALISMAN_SLOTS = range(17, 22)


def _tagged(slot_index, item_id):
    if item_id == 0xFFFFFFFF:
        return 0
    if slot_index in _ARMOR_SLOTS:
        return 0x90000000 | item_id
    if slot_index in _TALISMAN_SLOTS:
        return 0xA0000000 | item_id
    return 0x80000000 | (item_id & 0x7FFFFF)


def summary_base(sf, index):
    return sf.ud10_body + PROFILE_BASE + index * PROFILE_SIZE


def summary_bytes(sf, index):
    b = summary_base(sf, index)
    return bytes(sf.data[b : b + PROFILE_SIZE])


def write_summary(sf, index, blk):
    b = summary_base(sf, index)
    sf.data[b : b + PROFILE_SIZE] = blk[:PROFILE_SIZE]
    sf.touch_ud10()


def zero_summary(sf, index):
    write_summary(sf, index, b"\x00" * PROFILE_SIZE)


def roster(sf):
    """Lista 10 wpisów: imię/level/czas/runy/mapa + surowe bajty active."""
    out = []
    for k in range(10):
        blk = summary_bytes(sf, k)
        name = blk[0:34].decode("utf-16-le", "ignore").split("\x00")[0]
        level, secs, runes = struct.unpack_from("<3I", blk, _P_LEVEL)
        map_id = struct.unpack_from("<I", blk, _P_MAP)[0]
        active = bool(sf.data[sf.ud10_body + ACTIVE_BASE + k])
        out.append(
            {
                "slot": k,
                "active_flag": active,
                "used": bool(name),
                "name": name,
                "level": level,
                "seconds": secs,
                "runes_memory": runes,
                "map_id": map_id,
                "has_face": blk[_P_FACE + 4 : _P_FACE + 8] == b"FACE",
            }
        )
    return out


def summary_from_slot(sf, slot, profile):
    """Rebuild profilu z danych slotu (pola, które slot też ma, bierzemy ze slotu).

    Zachowuje: place_name_id, słowa-unknown ekwipunku, FACE gdy profil ma własny.
    (Port zweryfikowanej logiki er-save-manager/profile_sync.py.)
    """
    out = bytearray(profile)
    raw = slot.raw
    pgd = slot.offsets["pgd"]

    name = bytes(raw[pgd + _S_PGD_NAME : pgd + _S_PGD_NAME + _S_PGD_NAME_SIZE - 2])
    end = next((k for k in range(0, len(name), 2) if name[k : k + 2] == b"\0\0"), None)
    if end is not None:
        name = name[:end]
    out[_P_NAME : _P_NAME + _S_PGD_NAME_SIZE] = name.ljust(_S_PGD_NAME_SIZE, b"\0")

    out[_P_LEVEL : _P_LEVEL + 4] = raw[pgd + _S_PGD_LEVEL : pgd + _S_PGD_LEVEL + 4]
    play_ms = struct.unpack_from("<Q", raw, _S_HEADER_PLAY_MS)[0]
    struct.pack_into("<I", out, _P_SECONDS, min(play_ms // 1000, 0xFFFFFFFF))
    out[_P_RUNES_MEM : _P_RUNES_MEM + 4] = raw[pgd + _S_PGD_RUNES_MEM : pgd + _S_PGD_RUNES_MEM + 4]
    out[_P_MAP : _P_MAP + 4] = raw[_S_HEADER_MAP : _S_HEADER_MAP + 4]

    if out[_P_FACE + 4 : _P_FACE + 8] != b"FACE":
        face = slot.offsets["face"]
        out[_P_FACE : _P_FACE + _P_FACE_SIZE] = raw[face : face + _P_FACE_SIZE]

    item_ids = struct.unpack_from("<22I", raw, slot.offsets["item_ids"])
    words = list(struct.unpack_from("<58I", out, _P_EQUIP))
    words[_EQUIP_ACTIVE_SLOTS : _EQUIP_ACTIVE_SLOTS + 7] = struct.unpack_from(
        "<7I", raw, slot.offsets["active_weapons"]
    )
    words[_EQUIP_TAGGED : _EQUIP_TAGGED + _EQUIP_SLOT_COUNT] = [
        _tagged(i, item_id) for i, item_id in enumerate(item_ids)
    ]
    words[_EQUIP_ITEM_IDS : _EQUIP_ITEM_IDS + _EQUIP_SLOT_COUNT] = list(item_ids)
    struct.pack_into("<58I", out, _P_EQUIP, *words)

    out[_P_BODY] = raw[pgd + _S_PGD_GENDER]
    out[_P_BODY + 1] = raw[pgd + _S_PGD_ARCHETYPE]
    out[_P_BODY + 2] = raw[pgd + _S_PGD_GIFT]
    return bytes(out)
