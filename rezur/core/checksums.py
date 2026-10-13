"""Sumy kontrolne: MD5 sekcji BND4 + PlayerGameDataHash (wariant Adlera).

MD5 (tylko PC): 16 bajtów PRZED daną sekcją, liczone z całej sekcji po nich.
    slot k   : md5 @ 0x300 + k*0x280010, dane 0x280000
    USER_DATA_10: md5 @ wpis+0   , dane 0x60000
    USER_DATA_11: md5 @ wpis+0   , dane 0x240010  (rozmiar z tabeli wpisów BND4!)

PlayerGameDataHash: blok 0x80 w slocie (12 pozycji u32 + nieużywane).
Algorytm (zweryfikowany na realnych save'ach przez er-save-manager):
    lo starts 1, hi starts 0; po każdym bajcie: lo+=b; hi+=lo; redukcja mod 0xFFF1;
    wynik = (lo | hi<<16) * 2.  Redukcja: (0x80078071 * v) >> 32 >> 15 = v // 0xFFF1 (szybkie dzielenie).
Pokrywane pola: level, 9×u32 statystyk (8 + unk@0x54), archetype, bajt@0xB8,
runy, runes_memory, broń (10 slotów), zbroje+talizmany (9 slotów), czary (14 id).
Pozycje 4, 9, 11 pozostają nietknięte.
"""

import hashlib

EMPTY_SLOT_MD5 = bytes.fromhex("8354dcaa18a1ecb52d0895bf00888c44")

_MULT = 0x80078071
_MOD = 0xFFF1

# indeks wpisu hasha -> nazwa pola
HASH_FIELDS = {
    0: "level",
    1: "stats",
    2: "archetype",
    3: "pgd_0xb8",
    5: "runes",
    6: "runes_memory",
    7: "equipped_weapons",
    8: "equipped_armors_and_talismans",
    10: "equipped_spells",
}

_WEAPON_SLOTS = (0, 2, 4, 1, 3, 5, 6, 8, 7, 9)          # L1,L2,L3,R1,R2,R3,arrows1,arrows2,bolts1,bolts2 → ich kolejność
_HASH_ARMOR_TALISMAN_SLOTS = (12, 13, 14, 15, 17, 18, 19, 20, 21)
_SPELL_COUNT = 14
_SPELL_STRIDE = 8


def md5(data: bytes) -> bytes:
    return hashlib.md5(data).digest()


def section_md5_ok(data: bytes, entry_off: int, entry_size: int) -> bool:
    """Czy MD5 wpisu BND4 się zgadza (md5 + dane o rozmiarze entry_size)."""
    stored = data[entry_off : entry_off + 16]
    body = data[entry_off + 16 : entry_off + entry_size]
    return hashlib.md5(body).digest() == stored


def write_section_md5(buf: bytearray, entry_off: int, entry_size: int) -> bytes:
    """Przelicza i wpisuje MD5 wpisu BND4. Zwraca nowy digest."""
    body = bytes(buf[entry_off + 16 : entry_off + entry_size])
    digest = hashlib.md5(body).digest()
    buf[entry_off : entry_off + 16] = digest
    return digest


# ---------------------------------------------------------------- PlayerDataHash


def _reduce(v):
    q = ((_MULT * v) >> 32) >> 15
    return (v - q * _MOD) & 0xFFFFFFFF


def bytes_hash(data: bytes) -> int:
    lo, hi = 1, 0
    for byte in data:
        lo = (lo + byte) & 0xFFFFFFFF
        hi = (hi + lo) & 0xFFFFFFFF
    return ((_reduce(lo) | (_reduce(hi) << 16)) * 2) & 0xFFFFFFFF


def u32s_hash(values) -> int:
    import struct as _s

    return bytes_hash(b"".join(_s.pack("<I", v & 0xFFFFFFFF) for v in values))


def compute_player_hash(raw: bytes, pgd: int, item_ids_off: int, spells_off: int) -> dict:
    """Wartości hasha dla slotu; raw = dane slotu (0x280000), offsety slot-relative."""
    import struct as _s

    item_ids = _s.unpack_from("<22I", raw, item_ids_off)
    spells = [_s.unpack_from("<I", raw, spells_off + k * _SPELL_STRIDE)[0] for k in range(_SPELL_COUNT)]

    def u32(rel):
        return _s.unpack_from("<I", raw, pgd + rel)[0]

    return {
        "level": u32s_hash([u32(0x60)]),
        "stats": bytes_hash(bytes(raw[pgd + 0x34 : pgd + 0x34 + 9 * 4])),
        "archetype": u32s_hash([raw[pgd + 0xB7]]),
        "pgd_0xb8": bytes_hash(bytes([raw[pgd + 0xB8]])),
        "runes": u32s_hash([u32(0x64)]),
        "runes_memory": u32s_hash([u32(0x68)]),
        "equipped_weapons": u32s_hash([item_ids[i] for i in _WEAPON_SLOTS]),
        "equipped_armors_and_talismans": u32s_hash([item_ids[i] for i in _HASH_ARMOR_TALISMAN_SLOTS]),
        "equipped_spells": u32s_hash(spells),
    }


def player_hash_matches(raw: bytes, pgd: int, item_ids_off: int, spells_off: int, hash_off: int) -> bool:
    """Czy zapisane wpisy hasha zgadzają się z policzonymi (pozycje 0-10 poza 4 i 9)."""
    import struct as _s

    computed = compute_player_hash(raw, pgd, item_ids_off, spells_off)
    for index, name in HASH_FIELDS.items():
        stored = _s.unpack_from("<I", raw, hash_off + index * 4)[0]
        if stored != computed[name]:
            return False
    return True


def refresh_player_hash(buf: bytearray, slot_abs: int, pgd: int, item_ids_off: int, spells_off: int, hash_off: int) -> bool:
    """Przepisuje wpisy hasha w słocie (buf = bytearray całego pliku, offsety slot-relative).
    Zwraca True, jeśli cokolwiek się zmieniło."""
    import struct as _s

    raw = bytes(buf[slot_abs : slot_abs + 0x280000])
    computed = compute_player_hash(raw, pgd, item_ids_off, spells_off)
    changed = False
    for index, name in HASH_FIELDS.items():
        off = slot_abs + hash_off + index * 4
        new = _s.pack("<I", computed[name])
        if bytes(buf[off : off + 4]) != new:
            buf[off : off + 4] = new
            changed = True
    return changed
