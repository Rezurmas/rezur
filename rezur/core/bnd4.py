"""Kontener BND4 — nagłówek + tabela wpisów (12 sekcji save'a ER na PC).

Layout (zweryfikowany):
    0x00  magic "BND4"
    0x0C  u32 liczba wpisów (12)
    0x10  u64 header size (0x40)
    0x18  char[8] wersja ("00000001")
    0x40  tabela wpisów: 12 × 0x20
        +0x00 u32 flags (0x50)
        +0x04 i32 -1
        +0x08 u64 rozmiar wpisu (16 + dane)
        +0x10 u32 offset danych wpisu (dla slotów: offset MD5)
        +0x14 u32 offset nazwy wpisu (absolutny, UTF-16)
    0x1C0 tabela nazw (USER_DATA000..011)

Slot k: dane @ 0x310 + k*0x280010, 0x280000 B; md5 @ wpis-16.
"""

import struct

MAGIC = b"BND4"
SLOT_STRIDE = 0x280010
SLOT_BODY = 0x280000


def is_plaintext_bnd4(data: bytes) -> bool:
    return data[:4] == MAGIC


def parse_entries(data: bytes) -> list[dict]:
    """Zwraca 12 wpisów: {name, size, off} (off = offset danych wpisu, tj. MD5 dla sekcji z sumą)."""
    count = struct.unpack_from("<I", data, 0x0C)[0]
    out = []
    for i in range(count):
        base = 0x40 + i * 0x20
        _flags, _u, size, _s2, dataoff, nameoff, _a, _b = struct.unpack_from("<IIIIIIII", data, base)
        name = data[nameoff : nameoff + 26].decode("utf-16-le", "ignore").split("\x00")[0]
        out.append({"name": name, "size": size, "off": dataoff})
    return out


def slot_body_offset(entry: dict) -> int:
    """Offset danych slotu (za 16-bajtową sumą MD5)."""
    return entry["off"] + 16
