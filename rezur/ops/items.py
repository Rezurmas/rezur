"""F3 — itemy: dodawanie (gaitem + inventory z przesunięciem), przegląd ekwipunku.

Dodawanie broni/zbroi zmienia układ slotu! Nowy wpis gaitem (21/16 B) zastępuje
pusty (8 B), a różnica jest odcinana z końcowego zapasu slotu — cały slot zostaje
0x280000 B, ale wszystko PO wpisie przesuwa się o +delta. Dlatego po wstawieniu
slot jest PARSOWANY OD NOWA (nasz parser i tak znajduje wszystko po zawartości).
"""

import struct

from ..core import checksums, gaitem, inventory, items_db
from ..core.profiles import roster, summary_from_slot, summary_bytes, write_summary
from ..core.slots import SLOT_BODY, Slot


def _parsed(save, i):
    r = roster(save)
    s = Slot(save, i)
    if s.is_empty:
        raise ValueError(f"slot{i} jest pusty")
    if not s.parse(r[i]["name"], r[i]["level"]):
        raise ValueError(f"slot{i}: {s.reason}")
    return s


def _insert_gaitem(save, slot_idx, kind, item_id_new):
    """Wstaw wpis do gaitem map (port zweryfikowanej logiki er-save-manager).

    delta==0 (AoW): nadpisanie w miejscu. delta>0: wstaw nowy wpis, usuń OSTATNI
    pusty wpis (przesunięty), utnij delta bajtów z końcowego zapasu. Slot zostaje
    0x280000 B, a wszystko za wpisem przesuwa się o +delta."""
    s = _parsed(save, slot_idx)
    entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
    idx = gaitem.find_empty_index(entries, kind)
    if idx == -1:
        raise ValueError("gaitem map jest pełna")
    handle = gaitem.next_handle(entries, kind)
    new_bytes = gaitem.make_entry_bytes(kind, handle, item_id_new)
    new_size = len(new_bytes)
    e_rel = entries[idx]["off"]
    delta = new_size - 8

    work = bytearray(save.data[s.abs_off : s.abs_off + SLOT_BODY])
    if delta == 0:
        work[e_rel : e_rel + new_size] = new_bytes
    else:
        work[e_rel:e_rel] = new_bytes
        le = gaitem.last_empty(entries)
        if le is not None:
            shifted = le + new_size
            del work[shifted : shifted + 8]
        else:
            # brak pustego wpisu — zabierz miejsce tuż przed inventory (jak referencja)
            inv_shifted = s.offsets["inventory_held"] + new_size
            del work[inv_shifted - 8 : inv_shifted]
        current_end = SLOT_BODY + new_size - 8
        del work[current_end - delta : current_end]
    save.data[s.abs_off : s.abs_off + SLOT_BODY] = work
    return handle


def add_item(save, slot_idx, full_id, qty=1, upgrade=0, location="held"):
    """Dodaje item. full_id: pełne id (z bitami kategorii) albo base broni (cat 0).
    Zwraca raport."""
    cat = (full_id >> 28) & 0xF
    if cat not in (0x0, 0x1, 0x2, 0x4, 0x8):
        raise ValueError(f"nieznana kategoria itemu 0x{full_id:08X}")
    if qty < 1:
        raise ValueError("qty >= 1")

    # --- krok 1: gaitem (bron/zbroja/AoW)
    handle = None
    if cat in (0x0, 0x1, 0x8):
        if cat == 0x0:
            item_id_new = full_id + max(0, upgrade)
            handle = _insert_gaitem(save, slot_idx, "weapon", item_id_new)
        elif cat == 0x1:
            item_id_new = full_id
            handle = _insert_gaitem(save, slot_idx, "armor", item_id_new)
        else:  # AoW — tylko gaitem, bez wpisu w inventory (jak gra)
            _insert_gaitem(save, slot_idx, "gem", full_id & 0x0FFFFFFF)
            return {"slot": slot_idx, "category": "ashes", "gaitem_handle": None, "note": "AoW: wpis tylko w gaitem"}

    # --- krok 2: re-parse (gaitem mohło przesunąć układ) i wpis do inventory
    s = _parsed(save, slot_idx)

    if handle is None:  # talizman/ goods: bezpośredni handle
        base = full_id & 0x0FFFFFFF
        handle = (0xA0000000 | base) if cat == 0x2 else (0xB0000000 | base)

    is_key = cat == 0x4 and (full_id & 0x0FFFFFFF) in items_db.key_item_ids()

    held_off = s.offsets["inventory_held"]
    storage_off = s.offsets["storage"]
    work = bytearray(save.data[s.abs_off : s.abs_off + SLOT_BODY])

    def _find_existing():
        for loc, off in (("held", held_off), ("storage", storage_off)):
            inv = inventory.read(work, off, loc)
            for lst, key in ((inv["common_items"], False), (inv["key_items"], True)):
                i = inventory.find_handle(lst, handle)
                if i != -1:
                    return loc, off, inv, i, key
        return None

    if cat == 0x4:  # dobra: jeśli już jest — podbij ilość
        found = _find_existing()
        if found:
            loc, off, inv, i, key = found
            L = inventory.layout(off, loc)
            base_off = (L["key"] if key else L["common"]) + i * inventory.ENTRY
            old_qty = struct.unpack_from("<3I", work, base_off)[1]
            struct.pack_into("<I", work, base_off + 4, old_qty + qty)
            save.data[s.abs_off : s.abs_off + SLOT_BODY] = work
            save.touch_slot(slot_idx)
            return {"slot": slot_idx, "handle": handle, "qty": old_qty + qty, "location": loc,
                    "note": "istniał — zwiększono ilość"}

    def _place(loc, off):
        inv = inventory.read(work, off, loc)
        lst = inv["key_items"] if is_key else inv["common_items"]
        i = inventory.first_empty(lst)
        if i == -1:
            return None
        acq = inventory.next_acq_index(work, held_off, storage_off)
        inventory.write_entry(work, off, loc, i, is_key, handle, qty, acq)
        return loc, i, acq

    placed = _place(location, held_off if location == "held" else storage_off)
    if placed is None and location == "held":
        placed = _place("storage", storage_off)
    if placed is None:
        raise ValueError("inventory jest pełne")
    loc, inv_slot, acq = placed

    save.data[s.abs_off : s.abs_off + SLOT_BODY] = work
    checksums.refresh_player_hash(
        save.data, s.abs_off, s.offsets["pgd"], s.offsets["item_ids"], s.offsets["spells"], s.tail["hash"]
    )
    save.touch_slot(slot_idx)
    name, _ = items_db.resolve(full_id + (upgrade if cat == 0x0 else 0))
    return {
        "slot": slot_idx,
        "handle": handle,
        "item": name or f"0x{full_id:08X}",
        "qty": qty,
        "location": loc,
        "inventory_slot": inv_slot,
        "acquisition_index": acq,
    }


def list_inventory(save, slot_idx, location="held"):
    """Lista ekwipunku z nazwami. Rozwiązuje handle przez gaitem mapę."""
    s = _parsed(save, slot_idx)
    off = s.offsets["inventory_held"] if location == "held" else s.offsets["storage"]
    inv = inventory.read(s.raw, off, location)

    entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
    by_handle = {e["handle"]: e for e in entries if e["handle"]}

    out = []
    for kind_items in (inv["key_items"], inv["common_items"]):
        for h, q, a in kind_items:
            if h == 0:
                continue
            t = h & 0xF0000000
            name = None
            item_id = None
            if t in (0x80000000, 0x90000000, 0xC0000000):
                g = by_handle.get(h)
                if g:
                    item_id = g["item_id"]
                    if t == 0x90000000:
                        name, _ = items_db.resolve(item_id)
                    elif t == 0x80000000:
                        name, _ = items_db.resolve(item_id)
                    else:
                        name, _ = items_db.resolve(item_id | 0x80000000)
            elif t == 0xA0000000:
                item_id = 0x20000000 | (h & 0x0FFFFFFF)
                name, _ = items_db.resolve(item_id)
            elif t == 0xB0000000:
                item_id = 0x40000000 | (h & 0x0FFFFFFF)
                name, _ = items_db.resolve(item_id)
            out.append({"handle": h, "qty": q, "acq": a, "item_id": item_id,
                        "name": name or f"0x{h:08X}"})
    return out
