#!/usr/bin/env python3
"""Testy Rezur — bez pytest, własny runner z podsumowaniem.

    python tests/run_all.py

Fikstury: pliki z backups/ (NIE są modyfikowane — mutujące testy piszą do temp).
"""

import glob
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rezur import fixes as F  # noqa: E402
from rezur.core import flags as coreflags  # noqa: E402
from rezur.core import items_db  # noqa: E402
from rezur.core import profiles as P  # noqa: E402
from rezur.core.savefile import SaveFile  # noqa: E402
from rezur.diag import run_diagnostics  # noqa: E402


def _ref_modules():
    """Moduły referencyjnego parsera (er-save-manager) do weryfikacji krzyżowej.
    Zwraca (save_mod, eventflags_mod) albo (None, None), gdy repo nieobecne."""
    src = str(ROOT / "references" / "er-save-manager" / "src")
    if not Path(src).exists():
        return None, None
    import importlib
    import types

    if "er_save_manager" not in sys.modules:
        pkg = types.ModuleType("er_save_manager")
        pkg.__path__ = [src + "/er_save_manager"]
        sys.modules["er_save_manager"] = pkg
        sys.path.insert(0, src)
    return (
        importlib.import_module("er_save_manager.parser.save"),
        importlib.import_module("er_save_manager.parser.event_flags"),
    )

PREFIX_GLOB = "ER0000_backup_*.sl2"        # oryginał z bugiem torrenta
FIXED_GLOB = "ER0000_FIXED_torrent_*.sl2"  # po naprawie torrenta

_tests = []


def test(fn):
    _tests.append(fn)
    return fn


def fixture(pattern):
    hits = sorted(glob.glob(str(ROOT / "backups" / pattern)))
    if not hits:
        raise SystemExit(f"brak fikstury: backups/{pattern}")
    return hits[0]


@test
def t_container_fixed():
    sf = SaveFile(fixture(FIXED_GLOB))
    bad = [s for s in sf.section_md5_status() if not s["ok"]]
    assert not bad, bad


@test
def t_roster_names_fixed():
    sf = SaveFile(fixture(FIXED_GLOB))
    names = [r["name"] for r in P.roster(sf)]
    for want in ("let me fight him", "hajime", "annesee"):
        assert want in names, (want, names)


@test
def t_doctor_finds_torrent_in_prefix():
    sf = SaveFile(fixture(PREFIX_GLOB))
    fs = run_diagnostics(sf)
    hits = [f for f in fs if f.code == "torrent_bug"]
    assert any(f.slot == 2 for f in hits), [f.line() for f in fs]


@test
def t_doctor_clean_torrent_in_fixed():
    sf = SaveFile(fixture(FIXED_GLOB))
    fs = run_diagnostics(sf)
    assert not any(f.code == "torrent_bug" for f in fs), [f.line() for f in fs]


@test
def t_fix_torrent_end_to_end():
    src = fixture(PREFIX_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        res = F.apply_fixes(sf, ["torrent"])
        assert any(r.applied for r in res), [r for r in res]
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        assert not any(f.code == "torrent_bug" for f in run_diagnostics(chk))
        assert all(s["ok"] for s in chk.section_md5_status())
        orig = Path(src).read_bytes()
        new = p.read_bytes()
        dcount = sum(1 for a, b in zip(orig, new) if a != b)
        assert dcount <= 17, f"diff={dcount} (oczekiwane ≤17)"


@test
def t_copy_character():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops import copy_character

        copy_character(sf, 2, 3)
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r = P.roster(chk)
        assert r[2]["name"] == r[3]["name"] == "annesee", (r[2]["name"], r[3]["name"])
        assert all(s["ok"] for s in chk.section_md5_status())


@test
def t_summary_matches_slot_fields():
    sf = SaveFile(fixture(FIXED_GLOB))
    r = P.roster(sf)
    for i in (0, 1, 2):
        slot = sf.slots()[i]
        if slot.is_empty:
            continue
        assert slot.parse(r[i]["name"], r[i]["level"]), slot.reason
        assert r[i]["name"] == slot.pgd_name(), (i, r[i]["name"], slot.pgd_name())
        assert r[i]["level"] == slot.pgd_level(), (i,)


@test
def t_steamid_change_roundtrip():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        old = sf.steam_id()
        from rezur.ops.steamid import change_steam_id

        rep = change_steam_id(sf, old + 12345)
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        assert chk.steam_id() == old + 12345, rep
        assert all(s["ok"] for s in chk.section_md5_status())


@test
def t_stats_edit():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.stats import set_stats

        set_stats(sf, 2, {"vigor": 60, "mind": 40})
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r = P.roster(chk)
        slot = chk.slots()[2]
        assert slot.parse(r[2]["name"], r[2]["level"]), slot.reason
        stats = slot.pgd_stats()
        assert stats[0] == 60 and stats[1] == 40, stats
        assert slot.pgd_level() == sum(stats) - 79
        assert r[2]["level"] == slot.pgd_level(), "profil nie zsynchronizowany"
        assert slot.player_hash_matches(), "PlayerDataHash rozjechany"
        assert all(s["ok"] for s in chk.section_md5_status())


@test
def t_rename_sync():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.stats import rename

        rename(sf, 2, "rezur test")
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r = P.roster(chk)
        slot = chk.slots()[2]
        assert slot.parse("rezur test", r[2]["level"]), slot.reason
        assert slot.pgd_name() == "rezur test"
        assert r[2]["name"] == "rezur test"


@test
def t_item_add_goods():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.items import add_item, list_inventory

        kys = items_db.key_item_ids()
        gid, gname = next(
            (fid, nm)
            for fid, nm in items_db._load()["goods"].items()
            if (fid & 0x0FFFFFFF) not in kys and "dummy" not in nm.lower()
        )
        rep = add_item(sf, 2, gid, qty=7)
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        items = list_inventory(chk, 2, "held")
        assert any(i["handle"] == rep["handle"] and i["qty"] >= 7 for i in items), rep
        assert all(s["ok"] for s in chk.section_md5_status())
        save_mod, _ = _ref_modules()
        if save_mod:
            ref = save_mod.load_save(str(p))
            inv = ref.get_slot(2).inventory_held
            found = [it for it in inv.common_items + inv.key_items if it.gaitem_handle == rep["handle"]]
            assert found and found[0].quantity >= 7, "referencja nie widzi itemu"


@test
def t_item_add_weapon():
    src = fixture(FIXED_GLOB)
    save_mod, _ = _ref_modules()
    assert save_mod, "test wymaga repo referencyjnego"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.items import add_item

        ex = items_db.find_exact("Uchigatana")
        assert ex, "brak Uchigatany w bazie"
        base = ex[0]
        rep = add_item(sf, 2, base, qty=1, upgrade=5)
        assert rep.get("handle"), rep
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        assert all(s["ok"] for s in chk.section_md5_status())
        ref = save_mod.load_save(str(p))
        s2 = ref.get_slot(2)
        ge = [g for g in s2.gaitem_map if g.gaitem_handle == rep["handle"]]
        assert ge, "brak wpisu w gaitem wg referencji"
        assert ge[0].item_id == base + 5, (hex(ge[0].item_id), hex(base + 5))
        inv = s2.inventory_held
        assert any(it.gaitem_handle == rep["handle"] for it in inv.common_items + inv.key_items)
        assert not any(f.level == "error" for f in run_diagnostics(chk))


@test
def t_flags_match_reference():
    save_mod, ef_mod = _ref_modules()
    if not save_mod:
        return
    src = fixture(FIXED_GLOB)
    sf = SaveFile(src)
    slot = sf.slots()[2]
    r = P.roster(sf)
    assert slot.parse(r[2]["name"], r[2]["level"]), slot.reason
    ours_ef = slot.event_flags()
    ref = save_mod.load_save(src)
    ref_slot = ref.get_slot(2)
    ids = [b * 1000 + 7 for b in sorted(coreflags._load_bst())[::290][:40]]
    ours = [coreflags.get_flag(ours_ef, i) for i in ids]
    theirs = [ef_mod.EventFlags.get_flag(ref_slot.event_flags, i) for i in ids]
    assert ours == theirs, [(i, o, t) for i, o, t in zip(ids, ours, theirs) if o != t][:5]


@test
def t_flag_set_visible_to_reference():
    save_mod, ef_mod = _ref_modules()
    if not save_mod:
        return
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.flags import get_flag, set_flag

        eid = sorted(coreflags._load_bst())[100] * 1000 + 3
        before = get_flag(sf, 2, eid)
        set_flag(sf, 2, eid, not before)
        sf.write(backup_tag="test")
        ref = save_mod.load_save(str(p))
        val = ef_mod.EventFlags.get_flag(ref.get_slot(2).event_flags, eid)
        assert val == (not before)


@test
def t_export_import_roundtrip():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "a.sl2"
        b = Path(td) / "b.sl2"
        shutil.copy2(src, a)
        shutil.copy2(src, b)
        sfa = SaveFile(a)
        from rezur.ops.transfer import export_character, import_character

        out = Path(td) / "annesee.json"
        export_character(sfa, 2, out)
        sfb = SaveFile(b)
        import_character(sfb, out, 3)
        sfb.write(backup_tag="test")
        chk = SaveFile(b)
        r = P.roster(chk)
        assert r[3]["name"] == "annesee" and r[3]["level"] == 54, r[3]
        blk_a = bytes(sfa.data[sfa.slot_entries[2]["off"] + 16 : sfa.slot_entries[2]["off"] + 16 + 0x280000])
        blk_b = bytes(chk.data[chk.slot_entries[3]["off"] + 16 : chk.slot_entries[3]["off"] + 16 + 0x280000])
        assert blk_a == blk_b
        assert all(s["ok"] for s in chk.section_md5_status())


@test
def t_backups_roundtrip():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        sf.write(backup_tag="test")
        from rezur.ops.backups import list_backups, restore

        lst = list_backups(p)
        assert lst, "brak kopii po zapisie"
        rep = restore(p, lst[0]["path"])
        assert Path(rep["pre_restore_copy"]).exists()


@test
def t_item_set_qty_move_remove():
    src = fixture(FIXED_GLOB)
    save_mod, _ = _ref_modules()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.items import add_item, list_inventory, move_item, remove_item, set_item_qty

        kys = items_db.key_item_ids()
        gid = next(
            fid
            for fid, nm in items_db._load()["goods"].items()
            if (fid & 0x0FFFFFFF) not in kys and "dummy" not in nm.lower()
        )
        rep = add_item(sf, 2, gid, qty=3)
        h = rep["handle"]
        set_item_qty(sf, 2, h, 9)
        move_item(sf, 2, h, "storage")
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        held = list_inventory(chk, 2, "held")
        stor = list_inventory(chk, 2, "storage")
        assert not any(i["handle"] == h for i in held)
        assert any(i["handle"] == h and i["qty"] == 9 for i in stor), (h, stor[:3])
        assert all(s["ok"] for s in chk.section_md5_status())
        if save_mod:
            ref = save_mod.load_save(str(p))
            s2 = ref.get_slot(2)
            box = s2.inventory_storage_box
            got = [it for it in box.common_items + box.key_items if it.gaitem_handle == h]
            assert got and got[0].quantity == 9, "referencja nie widzi w skrzyni"
        sf2 = SaveFile(p)
        remove_item(sf2, 2, h)
        sf2.write(backup_tag="test")
        chk2 = SaveFile(p)
        assert not any(i["handle"] == h for i in list_inventory(chk2, 2, "storage"))
        assert not any(i["handle"] == h for i in list_inventory(chk2, 2, "held"))
        assert all(s["ok"] for s in chk2.section_md5_status())


@test
def t_item_remove_weapon():
    src = fixture(FIXED_GLOB)
    save_mod, _ = _ref_modules()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.items import add_item, remove_item

        ex = items_db.find_exact("Uchigatana")
        assert ex, "brak Uchigatany"
        rep = add_item(sf, 2, ex[0], qty=1, upgrade=3)
        h = rep["handle"]
        remove_item(sf, 2, h)
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r = P.roster(chk)
        s = chk.slots()[2]
        assert s.parse(r[2]["name"], r[2]["level"]), s.reason
        assert all(ok["ok"] for ok in chk.section_md5_status())
        if save_mod:
            ref = save_mod.load_save(str(p))
            s2 = ref.get_slot(2)
            assert not any(g.gaitem_handle == h for g in s2.gaitem_map), "gaitem nie wyczyszczony"
            inv = s2.inventory_held
            assert not any(it.gaitem_handle == h for it in inv.common_items + inv.key_items)


@test
def t_swap_slots():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.copy_slot import swap_characters

        sf_orig = SaveFile(src)
        blk2 = bytes(sf_orig.data[sf_orig.slot_entries[2]["off"] + 16 : sf_orig.slot_entries[2]["off"] + 16 + 0x280000])
        swap_characters(sf, 1, 2)
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r = P.roster(chk)
        assert r[1]["name"] == "annesee" and r[2]["name"] == "hajime", (r[1]["name"], r[2]["name"])
        blk1 = bytes(chk.data[chk.slot_entries[1]["off"] + 16 : chk.slot_entries[1]["off"] + 16 + 0x280000])
        assert blk1 == blk2, "dane slotu nie podmienione"
        for k in (1, 2):
            s = chk.slots()[k]
            assert s.parse(r[k]["name"], r[k]["level"]), s.reason
        assert all(s["ok"] for s in chk.section_md5_status())


@test
def t_clear_slot():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.core.checksums import EMPTY_SLOT_MD5
        from rezur.ops.copy_slot import clear_character

        clear_character(sf, 1)
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        assert chk.slots()[1].is_empty
        e = chk.slot_entries[1]
        assert bytes(chk.data[e["off"] : e["off"] + 16]) == EMPTY_SLOT_MD5
        r = P.roster(chk)
        assert not r[1]["used"], r[1]
        assert all(s["ok"] for s in chk.section_md5_status())


@test
def t_equipment_equip_unequip():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.items import add_item, equip_item, equipment, unequip

        eq0 = equipment(sf, 0)
        assert len(eq0["equipped"]) == 22
        assert any(not e["empty"] for e in eq0["equipped"]), "lmfh powinien mieć coś założone"
        ex = items_db.find_exact("Uchigatana")
        rep = add_item(sf, 0, ex[0], qty=1, upgrade=0)
        h = rep["handle"]
        equip_item(sf, 0, h, at=0)
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        eq1 = equipment(chk, 0)
        assert eq1["equipped"][0]["handle"] == h, eq1["equipped"][0]
        r = P.roster(chk)
        s = chk.slots()[0]
        assert s.parse(r[0]["name"], r[0]["level"]), s.reason
        assert s.player_hash_matches(), "hash po eq rozjechany"
        assert all(ok["ok"] for ok in chk.section_md5_status())
        sf2 = SaveFile(p)
        rep2 = unequip(sf2, 0, at=0)
        assert rep2["unequipped"] == [0], rep2
        sf2.write(backup_tag="test")
        chk2 = SaveFile(p)
        assert equipment(chk2, 0)["equipped"][0]["empty"]
        r2 = P.roster(chk2)
        s2 = chk2.slots()[0]
        assert s2.parse(r2[0]["name"], r2[0]["level"]), s2.reason
        assert s2.player_hash_matches()
        assert all(ok["ok"] for ok in chk2.section_md5_status())


@test
def t_handle_for_prefers_exact_weapon():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.core import gaitem
        from rezur.core.slots import Slot
        from rezur.ops.items import add_item, handle_for

        ex = items_db.find_exact("Uchigatana")
        assert ex, "brak Uchigatany w bazie"
        rep = add_item(sf, 0, ex[0], qty=1, upgrade=0)
        h_new = rep["handle"]
        h_got = handle_for(sf, 0, ex[0])
        assert h_got == h_new, (hex(h_got), hex(h_new), "handle_for złapał nie tę broń (kolizja /10000)")
        s = Slot(sf, 0)
        r = P.roster(sf)
        assert s.parse(r[0]["name"], r[0]["level"]), s.reason
        entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
        e = next(x for x in entries if x["handle"] == h_got)
        nm, _c = items_db.resolve(e["item_id"] & 0x0FFFFFFF)
        assert nm and nm.startswith("Uchigatana"), nm


def main():
    ok = fail = 0
    for t in _tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            ok += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            fail += 1
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            fail += 1
    print(f"\n{ok} passed, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
