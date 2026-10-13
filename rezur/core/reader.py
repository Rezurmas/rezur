"""Bezpieczne czytanie wartości little-endian z buforów bajtów.

Wszystkie offsety są liczone od początku przekazanego bufora.
Funkcje rzucają struct.error / IndexError poza zakresem — wołający łapie.
"""

import struct


def u8(b, o):
    return b[o]


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def i16(b, o):
    return struct.unpack_from("<h", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def u64(b, o):
    return struct.unpack_from("<Q", b, o)[0]


def i64(b, o):
    return struct.unpack_from("<q", b, o)[0]


def f32(b, o):
    return struct.unpack_from("<f", b, o)[0]


def v3f(b, o):
    """Trzy floaty (wektor pozycji)."""
    return (f32(b, o), f32(b, o + 4), f32(b, o + 8))


def v4f(b, o):
    """Cztery floaty (kąt/kwaternion)."""
    return (f32(b, o), f32(b, o + 4), f32(b, o + 8), f32(b, o + 12))


def utf16(b, o, maxlen=24):
    """Ciąg UTF-16LE zakończony \\x00 (max maxlen znaków)."""
    try:
        return b[o : o + maxlen * 2].decode("utf-16-le", "ignore").split("\x00")[0]
    except Exception:
        return ""


def find_all(b, pattern, limit=64):
    """Wszystkie wystąpienia wzorca w buforze (do limitu)."""
    out = []
    i = b.find(pattern)
    while i >= 0 and len(out) < limit:
        out.append(i)
        i = b.find(pattern, i + 1)
    return out
