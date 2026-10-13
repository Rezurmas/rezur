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
from .stats import _resync_summary


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


# ---------------------------------------------------------------- selektory


def parse_selector(text):
    """'handle:0x…' | '0xID' | nazwa → ('handle', h) albo ('id', full_id)."""
    t = text.strip()
    low = t.lower()
    if low.startswith("handle:"):
        return "handle", int(low.split(":", 1)[1], 16)
    if low.startswith("0x"):
        return "id", int(t, 16)
    ex = items_db.find_exact(t)
    if ex:
        return "id", ex[0]
    res = items_db.search(t, 8)
    ids = sorted({fid for fid, _n, _c in res})
    if not ids:
        raise ValueError(f"nie znalazłem itemu {t!r}")
    if len(ids) > 1:
        raise ValueError("kilka trafień — doprecyzuj: " + ", ".join(f"0x{f:08X}" for f in ids[:6]))
    return "id", ids[0]


def inventory_hit(save, slot_idx, handle):
    """(Slot, location, is_key, index) dla handle w held/storage albo None."""
    s = _parsed(save, slot_idx)
    for loc, off in (("held", s.offsets["inventory_held"]), ("storage", s.offsets["storage"])):
        inv = inventory.read(s.raw, off, loc)
        for lst, is_key in ((inv["common_items"], False), (inv["key_items"], True)):
            i = inventory.find_handle(lst, handle)
            if i != -1:
                return s, loc, is_key, i
    return None


def handle_for(save, slot_idx, full_id):
    """Handle istniejącego wpisu w ekwipunku dla pełnego id (gaitem-scan dla broni/zbroi)."""
    s = _parsed(save, slot_idx)
    cat = (full_id >> 28) & 0xF
    handle = None
    if cat in (0x0, 0x1, 0x8):
        want = full_id & 0x0FFFFFFF
        entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
        prefix = {0x0: 0x80000000, 0x1: 0x90000000, 0x8: 0xC0000000}[cat]
        want_name, _ = items_db.resolve(full_id) if cat == 0x0 else (None, None)
        loose = None
        for e in entries:
            if (e["handle"] & 0xF0000000) != prefix:
                continue
            if cat == 0x0:
                iid = e["item_id"] & 0x0FFFFFFF
                if iid == want:
                    handle = e["handle"]
                    break
                nm, _c = items_db.resolve(iid)
                if want_name and nm and (nm == want_name or nm.startswith(want_name + " ")):
                    if handle is None:
                        handle = e["handle"]
                elif nm is None and loose is None and iid // 10000 * 10000 == want // 10000 * 10000:
                    loose = e["handle"]
            elif cat == 0x1:
                if e["item_id"] == (full_id & 0xFFFFFFFF):
                    handle = e["handle"]
                    break
            else:
                if e["item_id"] in (want, full_id):
                    handle = e["handle"]
                    break
        if handle is None:
            handle = loose
        if handle is None:
            raise ValueError(f"0x{full_id:08X} nie występuje w gaitem")
    elif cat == 0x2:
        handle = 0xA0000000 | (full_id & 0x0FFFFFFF)
    elif cat == 0x4:
        handle = 0xB0000000 | (full_id & 0x0FFFFFFF)
    else:
        raise ValueError(f"kategoria 0x{cat:X} nieobsługiwana")
    if inventory_hit(save, slot_idx, handle) is None:
        raise ValueError(f"0x{full_id:08X} nie ma w ekwipunku")
    return handle


def _full_id_of_handle(s, handle):
    t = handle & 0xF0000000
    if t == 0xA0000000:
        return 0x20000000 | (handle & 0x0FFFFFFF)
    if t == 0xB0000000:
        return 0x40000000 | (handle & 0x0FFFFFFF)
    if t in (0x80000000, 0x90000000, 0xC0000000):
        entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
        for e in entries:
            if e["handle"] == handle:
                return e["item_id"] | (0x80000000 if t == 0xC0000000 else 0)
    return None


def _remove_gaitem_entry(s, work, handle):
    """Podmienia wpis gaitem na pusty 8 B; slot zostaje 0x280000 (ogon dostaje zapas)."""
    entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
    e = next((x for x in entries if x["handle"] == handle), None)
    if e is None or e["size"] <= 8:
        return False
    rel, old = e["off"], e["size"]
    work[rel:rel] = b"\x00" * 8
    del work[rel + 8 : rel + 8 + old]
    work.extend(b"\x00" * (old - 8))
    return True


def _unequip_handle(save, s, handle):
    """Zeruje gniazda eq wskazujące na handle (item_ids + ga_handles)."""
    changed = []
    base = s.abs_off
    for k in range(22):
        if struct.unpack_from("<I", save.data, base + s.offsets["ga_handles"] + k * 4)[0] == handle:
            struct.pack_into("<I", save.data, base + s.offsets["item_ids"] + k * 4, 0)
            struct.pack_into("<I", save.data, base + s.offsets["ga_handles"] + k * 4, 0)
            changed.append(k)
    return changed


def remove_item(save, slot_idx, handle):
    """Usuwa item z ekwipunku (held/storage), zdejmuje z eq, czyści wpis gaitem."""
    hit = inventory_hit(save, slot_idx, handle)
    if hit is None:
        raise ValueError(f"nie ma handle 0x{handle:08X} w ekwipunku slot{slot_idx}")
    s, loc, is_key, i = hit
    off = s.offsets["inventory_held"] if loc == "held" else s.offsets["storage"]
    work = bytearray(save.data[s.abs_off : s.abs_off + SLOT_BODY])
    _h, old_qty = inventory.clear_entry(work, off, loc, i, is_key)
    gaitem_removed = False
    if (handle & 0xF0000000) in (0x80000000, 0x90000000, 0xC0000000):
        gaitem_removed = _remove_gaitem_entry(s, work, handle)
    save.data[s.abs_off : s.abs_off + SLOT_BODY] = work

    s2 = _parsed(save, slot_idx)
    unequipped = _unequip_handle(save, s2, handle)
    checksums.refresh_player_hash(
        save.data, s2.abs_off, s2.offsets["pgd"], s2.offsets["item_ids"], s2.offsets["spells"], s2.tail["hash"]
    )
    if unequipped:
        _resync_summary(save, slot_idx, s2)
    save.touch_slot(slot_idx)
    full = _full_id_of_handle(s, handle)
    name, _c = items_db.resolve(full) if full else (None, None)
    return {
        "slot": slot_idx,
        "handle": handle,
        "item": name or f"0x{handle:08X}",
        "location": loc,
        "old_quantity": old_qty,
        "gaitem_removed": gaitem_removed,
        "unequipped_slots": unequipped,
    }


def set_item_qty(save, slot_idx, handle, qty):
    """Ustawia ilość istniejącego wpisu."""
    if qty < 1:
        raise ValueError("qty >= 1")
    hit = inventory_hit(save, slot_idx, handle)
    if hit is None:
        raise ValueError(f"nie ma handle 0x{handle:08X} w ekwipunku slot{slot_idx}")
    s, loc, is_key, i = hit
    off = s.offsets["inventory_held"] if loc == "held" else s.offsets["storage"]
    work = bytearray(save.data[s.abs_off : s.abs_off + SLOT_BODY])
    L = inventory.layout(off, loc)
    base = (L["key"] if is_key else L["common"]) + i * inventory.ENTRY
    old = struct.unpack_from("<I", work, base + 4)[0]
    inventory.set_quantity(work, off, loc, i, is_key, qty)
    save.data[s.abs_off : s.abs_off + SLOT_BODY] = work
    save.touch_slot(slot_idx)
    return {"slot": slot_idx, "handle": handle, "location": loc, "old_quantity": old, "new_quantity": qty}


def move_item(save, slot_idx, handle, to_location):
    """Przenosi wpis między held a skrzynią (zachowuje handle, ilość i typ listy)."""
    if to_location not in ("held", "storage"):
        raise ValueError("to_location: 'held' albo 'storage'")
    hit = inventory_hit(save, slot_idx, handle)
    if hit is None:
        raise ValueError(f"nie ma handle 0x{handle:08X} w ekwipunku slot{slot_idx}")
    s, loc, is_key, i = hit
    if loc == to_location:
        raise ValueError(f"handle 0x{handle:08X} już jest w {to_location!r}")
    src_off = s.offsets["inventory_held" if loc == "held" else "storage"]
    dst_off = s.offsets["inventory_held" if to_location == "held" else "storage"]
    work = bytearray(save.data[s.abs_off : s.abs_off + SLOT_BODY])
    _h, qty = inventory.clear_entry(work, src_off, loc, i, is_key)
    inv_dst = inventory.read(work, dst_off, to_location)
    lst = inv_dst["key_items"] if is_key else inv_dst["common_items"]
    j = inventory.first_empty(lst)
    if j == -1:
        raise ValueError(f"{to_location!r} jest pełne")
    acq = inventory.next_acq_index(work, s.offsets["inventory_held"], s.offsets["storage"])
    inventory.write_entry(work, dst_off, to_location, j, is_key, handle, qty, acq)
    save.data[s.abs_off : s.abs_off + SLOT_BODY] = work
    save.touch_slot(slot_idx)
    return {"slot": slot_idx, "handle": handle, "from": loc, "to": to_location, "qty": qty, "target_slot": j}


def _zone(k):
    if k < 12:
        return "weapon"
    if k <= 16:
        return "armor"
    return "talisman"


def equipment(save, slot_idx):
    """Podgląd założonego sprzętu: 22 gniazda item_ids + handles (+ aktywne bronie)."""
    s = _parsed(save, slot_idx)
    ids = list(struct.unpack_from("<22I", s.raw, s.offsets["item_ids"]))
    hs = list(struct.unpack_from("<22I", s.raw, s.offsets["ga_handles"]))
    entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
    by_handle = {e["handle"]: e for e in entries if e["handle"]}
    out = []
    for k, (iid, h) in enumerate(zip(ids, hs)):
        if iid in (0, 0xFFFFFFFF):
            out.append({"slot": k, "zone": _zone(k), "empty": True, "item_id": None, "handle": None, "name": None})
            continue
        gid = by_handle[h]["item_id"] if h in by_handle else None
        cands = [iid, iid | 0x10000000, iid | 0x20000000, iid | 0x40000000, iid | 0x80000000]
        if gid is not None:
            cands += [gid, gid | 0x10000000, gid | 0x20000000, gid | 0x40000000, gid | 0x80000000]
        name = None
        for cand in cands:
            if cand & 0xFFFFFFFF:
                nm, _c = items_db.resolve(cand & 0xFFFFFFFF)
                if nm:
                    name = nm
                    break
        out.append({"slot": k, "zone": _zone(k), "empty": False, "item_id": iid,
                    "handle": h, "name": name or f"0x{iid:08X}"})
    return {
        "slot": slot_idx,
        "equipped": out,
        "active_weapons": list(struct.unpack_from("<7I", s.raw, s.offsets["active_weapons"])),
    }


def equip_item(save, slot_idx, handle, at=None):
    """Zakłada item z ekwipunku. at=None → pierwsze wolne gniazdo w strefie kategorii."""
    s = _parsed(save, slot_idx)
    t = handle & 0xF0000000
    if t == 0x80000000:
        allowed = range(0, 12)
    elif t == 0x90000000:
        allowed = range(12, 17)
    elif t == 0xA0000000:
        allowed = range(17, 22)
    else:
        raise ValueError("założyć można broń (0x8…), zbroję (0x9…) albo talizman (0xA…)")

    ids = list(struct.unpack_from("<22I", s.raw, s.offsets["item_ids"]))
    if at is None:
        at = next((k for k in allowed if ids[k] in (0, 0xFFFFFFFF)), None)
        if at is None:
            raise ValueError("brak wolnego gniazda w tej strefie")
    if at not in allowed:
        raise ValueError(f"gniazdo {at} nie należy do strefy tej kategorii")

    if t in (0x80000000, 0x90000000):
        entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
        e = next((x for x in entries if x["handle"] == handle), None)
        if e is None:
            raise ValueError(f"handle 0x{handle:08X} nie występuje w gaitem")
        iid = e["item_id"] & 0x0FFFFFFF
    else:
        iid = handle & 0x0FFFFFFF

    struct.pack_into("<I", save.data, s.abs_off + s.offsets["item_ids"] + at * 4, iid)
    struct.pack_into("<I", save.data, s.abs_off + s.offsets["ga_handles"] + at * 4, handle)
    checksums.refresh_player_hash(
        save.data, s.abs_off, s.offsets["pgd"], s.offsets["item_ids"], s.offsets["spells"], s.tail["hash"]
    )
    _resync_summary(save, slot_idx, s)
    save.touch_slot(slot_idx)
    return {"slot": slot_idx, "handle": handle, "at": at, "item_id": iid}


def unequip(save, slot_idx, at=None):
    """Zdejmuje gniazdo (at) albo wszystko (at=None)."""
    s = _parsed(save, slot_idx)
    idxs = range(22) if at is None else [at]
    changed = []
    for k in idxs:
        iid = struct.unpack_from("<I", save.data, s.abs_off + s.offsets["item_ids"] + k * 4)[0]
        h = struct.unpack_from("<I", save.data, s.abs_off + s.offsets["ga_handles"] + k * 4)[0]
        if iid in (0, 0xFFFFFFFF) and h in (0, 0xFFFFFFFF):
            continue
        struct.pack_into("<I", save.data, s.abs_off + s.offsets["item_ids"] + k * 4, 0)
        struct.pack_into("<I", save.data, s.abs_off + s.offsets["ga_handles"] + k * 4, 0)
        changed.append(k)
    if changed:
        checksums.refresh_player_hash(
            save.data, s.abs_off, s.offsets["pgd"], s.offsets["item_ids"], s.offsets["spells"], s.tail["hash"]
        )
        _resync_summary(save, slot_idx, s)
        save.touch_slot(slot_idx)
    return {"slot": slot_idx, "unequipped": changed}
