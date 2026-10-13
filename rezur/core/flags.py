"""Event flags — bity w bloku 0x1BF99F B, adresowane przez BST z gry.

Mapowanie (zweryfikowane przez er-save-manager): block = event_id // 1000;
linia BST: "block,offset" gdzie offset = pozycja_bajtowa // 125. Pozycja bitu:
byte = bst[block]*125 + (event_id % 1000) // 8; bit = 7 - (event_id % 1000) % 8
(MSB-first w bajcie). Bloki spoza BST = gra ich nie zna.
"""

from .resources import data_path

FLAG_DIVISOR = 1000
BLOCK_SIZE = 125
EVENT_FLAGS_SIZE = 0x1BF99F

_bst = None


def _load_bst():
    global _bst
    if _bst is None:
        _bst = {}
        with open(data_path("eventflag_bst.txt"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "," not in line:
                    continue
                block, offset = line.split(",")
                _bst[int(block)] = int(offset)
    return _bst


def has_block(event_id):
    return event_id >= 0 and event_id // FLAG_DIVISOR in _load_bst()


def flag_pos(event_id):
    """(byte_pos, bit) albo ValueError, gdy blok nie istnieje w BST."""
    bst = _load_bst()
    block = event_id // FLAG_DIVISOR
    index = event_id - block * FLAG_DIVISOR
    if block not in bst:
        raise ValueError(f"event id {event_id} (block {block}) nie istnieje w BST")
    byte_pos = bst[block] * BLOCK_SIZE + index // 8
    bit = 7 - (index % 8)
    if byte_pos >= EVENT_FLAGS_SIZE:
        raise ValueError(f"event id {event_id} poza blokiem flag")
    return byte_pos, bit


def get_flag(event_flags: bytes, event_id: int) -> bool:
    pos, bit = flag_pos(event_id)
    return (event_flags[pos] >> bit) & 1 == 1


def set_flag(event_flags: bytearray, event_id: int, state: bool):
    pos, bit = flag_pos(event_id)
    if state:
        event_flags[pos] |= 1 << bit
    else:
        event_flags[pos] &= ~(1 << bit)
