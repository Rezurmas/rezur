"""F5 — transfer postaci: eksport/import przez plik JSON (zlib+base64)."""

import base64
import json
import zlib

from .. import __product__, __version__
from ..core.profiles import roster, summary_bytes, write_summary
from ..core.slots import SLOT_BODY, Slot


def _parsed(save, i):
    r = roster(save)
    s = Slot(save, i)
    if s.is_empty:
        raise ValueError(f"slot{i} jest pusty")
    if not s.parse(r[i]["name"], r[i]["level"]):
        raise ValueError(f"slot{i}: {s.reason}")
    return s


def export_character(save, slot_idx, out_path):
    s = _parsed(save, slot_idx)
    ch = s.character()
    doc = {
        "product": __product__,
        "version": __version__,
        "format": "rezur-character-v1",
        "meta": {
            "name": ch["name"],
            "level": ch["level"],
            "stats": ch["stats"],
            "seconds": ch["seconds"],
            "slot_version": ch["version"],
            "steam_id": save.steam_id(),
        },
        "slot_data": base64.b85encode(zlib.compress(bytes(s.raw), 9)).decode("ascii"),
        "summary": base64.b85encode(summary_bytes(save, slot_idx)).decode("ascii"),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    return {"slot": slot_idx, "out": str(out_path), "name": ch["name"], "level": ch["level"]}


def import_character(save, in_path, slot_idx):
    with open(in_path, encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("format") != "rezur-character-v1":
        raise ValueError("to nie jest plik postaci Rezura")
    block = zlib.decompress(base64.b85decode(doc["slot_data"]))
    if len(block) != SLOT_BODY:
        raise ValueError(f"zły rozmiar bloku: {len(block)}")
    summary = base64.b85decode(doc["summary"])
    if len(summary) != 0x24C:
        raise ValueError("zły rozmiar profilu")

    e = save.slot_entries[slot_idx]
    body = e["off"] + 16
    save.data[body : body + SLOT_BODY] = block
    write_summary(save, slot_idx, summary)
    save.touch_slot(slot_idx)
    return {
        "slot": slot_idx,
        "in": str(in_path),
        "name": doc["meta"]["name"],
        "level": doc["meta"]["level"],
        "note": "SteamID w slocie NIE jest przepisywany — gra go zaktualizuje przy zapisie"
                if doc["meta"].get("steam_id") != save.steam_id() else "ok",
    }
