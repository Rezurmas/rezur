#!/usr/bin/env python3
"""Testy Rezur — bez pytest, własny runner z podsumowaniem.

    python tests/run_all.py

Fikstury: pliki z backups/ (NIE są modyfikowane — mutujące testy piszą do temp).
"""

import glob
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rezur import fixes as F  # noqa: E402
from rezur import risk  # noqa: E402
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


@test
def t_world_flags_toggle():
    src = fixture(FIXED_GLOB)
    save_mod, ef_mod = _ref_modules()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.world import entries, set_world, view

        fid, fname, _d = entries("boss_defeat")[0]
        v0 = view(sf, 2, "boss_defeat", str(fid))
        before = v0["entries"][0]["value"]
        rep = set_world(sf, 2, "boss_defeat", str(fid), not before, apply=True)
        assert rep["set"] == 1, (rep, before)
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r = P.roster(chk)
        s = chk.slots()[2]
        assert s.parse(r[2]["name"], r[2]["level"]), s.reason
        assert s.get_flag(fid) == (not before)
        assert all(k["ok"] for k in chk.section_md5_status())
        if save_mod:
            ref = save_mod.load_save(str(p))
            assert ef_mod.EventFlags.get_flag(ref.get_slot(2).event_flags, fid) == (not before)


@test
def t_spells_memorize_forget():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.spells import equipped, forget, memorize

        v0 = equipped(sf, 0)
        assert any(not x["empty"] for x in v0["spells"]), "lmfh powinien mieć czar"
        at = next(k for k, x in enumerate(v0["spells"]) if x["empty"])
        rep = memorize(sf, 0, "Scholar's Armament", at=at)
        assert rep["at"] == at
        assert equipped(sf, 0)["spells"][at]["name"] == "Scholar's Armament"
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r = P.roster(chk)
        s = chk.slots()[0]
        assert s.parse(r[0]["name"], r[0]["level"]), s.reason
        assert s.player_hash_matches(), "hash po zmianie czarów rozjechany"
        assert all(k["ok"] for k in chk.section_md5_status())
        sf2 = SaveFile(p)
        forget(sf2, 0, at)
        sf2.write(backup_tag="test")
        assert equipped(SaveFile(p), 0)["spells"][at]["empty"]


@test
def t_appearance_set():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.appearance import read, set_appearance

        v0 = read(sf, 0)
        new_body = 1 if v0["body_type"] == 0 else 0
        set_appearance(sf, 0, body_type=new_body, gift=1)
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        v1 = read(chk, 0)
        assert v1["body_type"] == new_body and v1["gift"] == 1, (v0, v1)
        r = P.roster(chk)
        s = chk.slots()[0]
        assert s.parse(r[0]["name"], r[0]["level"]), s.reason
        assert s.player_hash_matches()
        assert all(k["ok"] for k in chk.section_md5_status())


@test
def t_teleport_roundtable():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.teleport import teleport

        expect = int.from_bytes(bytes([0, 0, 10, 11]), "little")
        rep = teleport(sf, 2, dest="roundtable")
        assert rep["to"]["map_id"] == expect
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r = P.roster(chk)
        assert r[2]["map_id"] == expect, (hex(r[2]["map_id"]), hex(expect))
        s = chk.slots()[2]
        assert s.parse(r[2]["name"], r[2]["level"]), s.reason
        assert s.map_id == expect
        xyz = s.coordinates()["xyz"]
        assert abs(xyz[0] - (-331.0)) < 1.0 and abs(xyz[1] - (-22.0)) < 1.0, xyz
        assert all(k["ok"] for k in chk.section_md5_status())


@test
def t_weapon_upgrade_affinity_aow():
    src = fixture(FIXED_GLOB)
    save_mod, _ = _ref_modules()
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        import struct as _st
        from rezur.core import gaitem
        from rezur.core.slots import Slot
        from rezur.ops.items import add_item, equip_item, set_weapon_affinity, set_weapon_aow, set_weapon_upgrade

        ex = items_db.find_exact("Uchigatana")
        rep = add_item(sf, 0, ex[0], qty=1, upgrade=0)
        h = rep["handle"]
        r = P.roster(sf)
        s = Slot(sf, 0)
        assert s.parse(r[0]["name"], r[0]["level"]), s.reason
        entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
        e = next(x for x in entries if x["handle"] == h)
        assert e["gem"] == 0, f"pusty gem ma być 0, jest {e['gem']:#x}"
        equip_item(sf, 0, h, at=0)
        set_weapon_upgrade(sf, 0, h, 12)
        set_weapon_affinity(sf, 0, h, "Blood")
        ash = list(items_db._load()["ashes"])[0]
        set_weapon_aow(sf, 0, h, ash)
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r2 = P.roster(chk)
        s2 = chk.slots()[0]
        assert s2.parse(r2[0]["name"], r2[0]["level"]), s2.reason
        entries2, _ = gaitem.walk(s2.raw, s2.version, expect_end=s2.offsets["pgd"])
        e2 = next(x for x in entries2 if x["handle"] == h)
        blood = items_db.find_exact("Blood Uchigatana")
        assert blood, "brak wariantu Blood w bazie"
        assert (e2["item_id"] & 0x0FFFFFFF) == (blood[0] & 0x0FFFFFFF) + 12, (hex(e2["item_id"]), hex(blood[0]))
        assert e2["gem"] not in (0, 0xFFFFFFFF, -1), f"gem nieprzypięty: {e2['gem']}"
        ids = _st.unpack_from("<22I", s2.raw, s2.offsets["item_ids"])
        assert ids[0] == (e2["item_id"] & 0x0FFFFFFF), "item_ids nie zaktualizowane po upgrade"
        assert s2.player_hash_matches()
        assert all(k["ok"] for k in chk.section_md5_status())
        if save_mod:
            ref = save_mod.load_save(str(p))
            g = next(x for x in ref.get_slot(0).gaitem_map if x.gaitem_handle == h)
            assert g.item_id == e2["item_id"]
            assert g.gem_gaitem_handle == e2["gem"]


@test
def t_grant_whetblades():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        from rezur.ops.items import category_ids, grant_category

        ids = category_ids("whetblades")
        assert len(ids) >= 4, ids
        rep = grant_category(sf, 2, "whetblades", location="storage")
        assert rep["added"] > 0, rep
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r = P.roster(chk)
        s = chk.slots()[2]
        assert s.parse(r[2]["name"], r[2]["level"]), s.reason
        assert all(k["ok"] for k in chk.section_md5_status())


@test
def t_vault_gold_single_and_prune_protects():
    from rezur.core import vault

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        orig = p.read_bytes()
        SaveFile(p).write(backup_tag="rezurbak")
        g = vault.gold_backup(p)
        assert g and Path(g["path"]).read_bytes() == orig, "GOLD nie trzyma stanu sprzed zapisu"
        SaveFile(p).write(backup_tag="rezurbak")
        assert len([b for b in vault.list_backups(p) if b["gold"]]) == 1, "więcej niż jeden GOLD"

        base = time.time() + 1000  # "przyszłe" czasy, żeby sortowanie było niezależne od zegara
        for i in range(5):
            dst = p.with_name(f"ER0000.sl2.rezurbak-20200101-00000{i}")
            shutil.copy(p, dst)
            os.utime(dst, (base + i, base + i))
        pinned = "ER0000.sl2.rezurbak-20200101-000000"
        vault.set_pin(p, pinned, on=True)
        assert vault.is_pinned(p, pinned)
        vault.prune(p, keep=2)
        names = {b["name"] for b in vault.list_backups(p)}
        assert vault.gold_backup(p)["name"] in names, "rotacja skasowała GOLD"
        assert pinned in names, "rotacja skasowała przypiętą kopię"
        left = [n for n in names if n.startswith("ER0000.sl2.rezurbak-20200101")]
        assert len(left) == 3, left  # 2 najnowsze + przypięta


@test
def t_write_verify_refuses_corrupt():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        orig = p.read_bytes()
        sf = SaveFile(p)
        e = sf.slot_entries[2]
        sf.data[e["off"] + 16 + 0x1000] ^= 0xFF  # psujemy dane slotu BEZ przeliczenia MD5
        denied = False
        try:
            sf.write(backup_tag="test")
        except ValueError as ex:
            denied = "weryfikacja" in str(ex)
        assert denied, "zapis z zepsutą sumą MD5 nie został odrzucony"
        assert p.read_bytes() == orig, "oryginał zmieniony mimo odrzuconej weryfikacji"
        assert not list(Path(td).glob("*.tmp-rezur")), "został plik tymczasowy"


@test
def t_watch_once():
    from rezur.ops import watch

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        res = watch.run_once(p, interval=600)
        if watch.game_running():
            assert res["made"], f"gra działa, a nie zrobiono kopii: {res}"
            assert Path(res["made"]).is_file()
            assert ".launchbak-" in res["made"]
        else:
            assert res == {"running": False, "made": None, "reason": "gra nie działa"}


@test
def t_patch_old_flagged():
    sf = SaveFile(fixture(PREFIX_GLOB))
    fs = run_diagnostics(sf)
    hits = [f for f in fs if f.code == "patch_old"]
    assert hits, "postacie ze starego patcha nie zostały oflagowane"
    slots = {f.slot for f in hits}
    assert 0 in slots and 1 in slots, slots
    assert 2 not in slots, "postać na aktualnym patchu oflagowana bez powodu"


@test
def t_journal_marks_modifications():
    from rezur.core import journal, vault

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        assert journal.summary(p)["count"] == 0
        SaveFile(p).write(backup_tag="itembak")
        s = journal.summary(p)
        assert s["count"] == 1 and s["last"], s
        assert s["ops"].get("ekwipunek") == 1, s
        g = vault.gold_backup(p)
        vault.restore(p, g["path"])
        s2 = journal.summary(p)
        assert s2["count"] == 2 and s2["ops"].get("przywrócenie kopii") == 1, s2


@test
def t_risk_clean_fixture_then_marks_modified():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        res = risk.scan(sf)
        errs = [f for f in res["findings"] if f["level"] == "error"]
        assert not errs, errs
        assert res["verdict"] == "green", (res["verdict"], res["findings"])
        assert res["modified"]["count"] == 0
        sf.write(backup_tag="editbak")
        res2 = risk.scan(SaveFile(p))
        assert res2["modified"]["count"] == 1, res2["modified"]
        assert res2["gold"], "GOLD powinien istnieć po pierwszym zapisie"


@test
def t_risk_detects_impossible_upgrade():
    import struct as st

    from rezur.core import gaitem

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        r = P.roster(sf)
        s = sf.slots()[0]
        assert s.parse(r[0]["name"], r[0]["level"]), s.reason
        entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
        w = next(
            x for x in entries
            if x["handle"] and ((x["handle"] >> 28) & 0xF) == 0x8 and items_db.resolve(x["item_id"])[0]
        )
        body = sf.entries[0]["off"] + 16
        new_id = w["item_id"] + (47 - w["item_id"] % 100)
        st.pack_into("<I", sf.data, body + w["off"] + 4, new_id)
        sf.touch_slot(0)
        sf.write(backup_tag="test")
        res = risk.scan(SaveFile(p))
        codes = {f["code"] for f in res["findings"]}
        assert "upgrade_impossible" in codes, codes
        assert res["verdict"] == "red", res["verdict"]


@test
def t_staging_flow_apply_once():
    from rezur import staging
    from rezur.core import journal

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        assert staging.op_count(p) == 0
        work = staging.begin(p)
        assert work.is_file() and work.read_bytes() == p.read_bytes()

        # edycja brudnopisu: pyknięcie w zapas slotu + przeliczenie MD5
        sf = SaveFile(work)
        e = sf.slot_entries[0]
        sf.data[e["off"] + 16 + 0x280000 - 1] ^= 0xFF
        sf.touch_slot(0)
        sf.write(backup_tag="stagework")  # brudnopis: bez backupu, bez dziennika
        assert not list(Path(work).parent.glob("*stagework*")), "brudnopis nie robi backupów"
        assert journal.summary(p)["count"] == 0, "brudnopis nie pisze do dziennika oryginału"

        staging.record_op(p, "stats", "--set vigor=61 (test)")
        assert staging.op_count(p) == 1
        orig_before = p.read_bytes()
        staged = work.read_bytes()
        res = staging.apply(p)
        assert res["md5_ok"] == res["md5_total"] == 12, res
        assert res["backup"] and "stagebak" in res["backup"]
        assert p.read_bytes() == staged and p.read_bytes() != orig_before
        assert staging.op_count(p) == 0 and not work.exists()
        j = journal.summary(p)
        assert j["count"] == 1 and j["ops"].get("zatwierdzenie zmian (staging)") == 1, j
        assert "stagebak" in journal.load(p)["entries"][-1]["note"]


@test
def t_staging_failure_keeps_changes():
    from rezur import staging

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        orig = p.read_bytes()
        work = staging.begin(p)
        work.write_bytes(b"to nie jest save")  # brudnopis psujemy
        staging.record_op(p, "stats", "test")
        denied = ""
        try:
            staging.apply(p)
        except ValueError as ex:
            denied = str(ex)
        assert "weryfikacja" in denied, denied or "apply nie odrzucił zepsutego brudnopisu"
        assert p.read_bytes() == orig, "oryginał ruszony mimo błędu"
        assert staging.op_count(p) == 1 and work.is_file(), "zmiany muszą ZOSTAĆ po błędzie"
        staging.discard(p)
        assert staging.op_count(p) == 0 and not work.exists()


@test
def t_staging_blocks_when_original_changed():
    from rezur import staging

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        staging.begin(p)
        staging.record_op(p, "stats", "test")
        os.utime(p, (time.time() + 10, time.time() + 10))
        assert staging.original_changed(p)
        blocked = ""
        try:
            staging.apply(p)
        except RuntimeError as ex:
            blocked = str(ex)
        assert "zmienił się" in blocked, blocked or "apply nie wstrzymał się przy zmienionym oryginale"
        assert staging.op_count(p) == 1
        staging.discard(p)


@test
def t_world_extra_groups_and_toggle():
    from rezur.ops import world

    g = world.groups()
    assert g.get("colosseums") == 3, g.get("colosseums")
    assert g.get("summoning_pools", 0) >= 150, g.get("summoning_pools")
    assert g.get("invasion_regions", 0) >= 200, g.get("invasion_regions")

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        rows = world.view(sf, 2, "colosseums", limit=5)["entries"]
        target = next((e for e in rows if e["value"] == 0), rows[0])
        want = 0 if target["value"] == 1 else 1
        rep = world.set_world(sf, 2, "colosseums", selector=str(target["id"]), value=want)
        assert rep["set"] == 1, rep
        sf.write(backup_tag="test")
        chk = SaveFile(p)
        r = P.roster(chk)
        s = chk.slots()[2]
        assert s.parse(r[2]["name"], r[2]["level"]), s.reason
        assert s.get_flag(target["id"]) == want


@test
def t_invcounters_fix():
    import struct as st

    from rezur.core import inventory

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        r = P.roster(sf)
        s = sf.slots()[0]
        assert s.parse(r[0]["name"], r[0]["level"]), s.reason
        inv = inventory.read(s.raw, s.offsets["inventory_held"], "held")
        L = inv["layout"]
        abs_off = s.abs_off + L["common_count"]
        good = st.unpack_from("<I", sf.data, abs_off)[0]
        st.pack_into("<I", sf.data, abs_off, good + 5)  # rozjazd licznika
        sf.touch_slot(0)
        sf.write(backup_tag="test")

        sf2 = SaveFile(p)
        fs = run_diagnostics(sf2)
        assert any(f.code == "inv_counter_mismatch" for f in fs), [f.line() for f in fs]
        res = F.apply_fixes(sf2, ["invcounters"], dry_run=False)
        assert any(x.applied for x in res), res
        sf2.write(backup_tag="test")
        fs3 = run_diagnostics(SaveFile(p))
        assert not any(f.code == "inv_counter_mismatch" for f in fs3), [f.line() for f in fs3]


@test
def t_torn_detected():
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "torn.sl2"
        p.write_bytes(Path(src).read_bytes()[: 10 * 1024 * 1024])
        msg = ""
        try:
            SaveFile(p)
        except ValueError as ex:
            msg = str(ex)
        assert "urwan" in msg, msg or "SaveFile nie wykrył urwanego pliku"


@test
def t_staging_undo():
    from rezur import staging

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        orig = p.read_bytes()
        work = staging.begin(p)

        def poke(n):
            sf = SaveFile(work)
            e = sf.slot_entries[0]
            sf.data[e["off"] + 16 + 0x280000 - 1 - n] ^= 0xFF
            sf.touch_slot(0)
            sf.write(backup_tag="w")

        snap1 = staging.make_snapshot(p)
        poke(0)
        staging.record_op(p, "stats", "op1", snap=snap1)
        md5_1 = staging.md5_file(work)
        snap2 = staging.make_snapshot(p)
        poke(1)
        staging.record_op(p, "stats", "op2", snap=snap2)
        assert staging.op_count(p) == 2

        res = staging.undo_last(p)
        assert res["undone"]["summary"] == "op2" and res["left"] == 1, res
        assert staging.md5_file(work) == md5_1, "cofnięcie nie przywróciło stanu sprzed op2"

        res2 = staging.undo_last(p)
        assert res2["left"] == 0
        assert work.read_bytes() == orig, "po cofnięciu wszystkiego brudnopis != oryginał"

        msg = ""
        try:
            staging.undo_last(p)
        except ValueError as ex:
            msg = str(ex)
        assert "brak zmian" in msg, msg or "undo na pustym stosie nie zgłosił błędu"
        staging.discard(p)


@test
def t_find_engine():
    from rezur.core import items_db
    from rezur.ops import world

    hits = items_db.search("uchigatana", limit=10)
    assert any("Uchigatana" in h[1] for h in hits), hits
    assert world.search_names("godrick"), "brak trafień flag dla 'godrick'"
    assert world.search_names("6100090"), "brak trafienia flagi po ID"


@test
def t_gui_api_flow():
    from rezur.gui.api import GuiApi

    api = GuiApi()
    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        info = api.load(str(p))
        assert "error" not in info, info
        assert info["md5"]["ok"] == info["md5"]["total"] == 12, info["md5"]
        names = {c.get("name") for c in info["characters"]}
        assert "annesee" in names, names

        d = api.doctor(str(p))
        assert "findings" in d, d
        rr = api.risk_scan(str(p))
        assert rr.get("verdict") in ("green", "yellow", "red"), rr

        inv = api.inventory(str(p), 2, "held", search="map")
        assert inv["total"] >= 1 and all("map" in e["name"].lower() for e in inv["rows"]), inv

        st = api.stage(str(p), ["stats", "--slot", "0", "--set", "vigor=61"])
        assert "error" not in st, st
        assert api.pending(str(p))["count"] == 1
        pv = api.preview(str(p))
        assert pv["changed"], pv
        res = api.apply(str(p), force=False)
        assert res.get("md5_ok") == 12, res
        assert api.pending(str(p))["count"] == 0
        bk = api.backups(str(p))
        assert any(b["gold"] for b in bk["rows"]), bk

        st2 = api.stage(str(p), ["stats", "--slot", "0", "--set", "vigor=62"])
        assert "error" not in st2, st2
        un = api.undo(str(p))
        assert un.get("left") == 0, un
        api.discard(str(p))


@test
def t_ui_lang_default_and_switch():
    """ui_lang: domyślnie EN, przełączanie EN↔PL zapisuje się, śmieci odrzucane."""
    from rezur import config as CONF

    with tempfile.TemporaryDirectory() as td:
        old = os.environ.get("APPDATA")
        os.environ["APPDATA"] = td  # izolacja: własny config.json
        try:
            assert CONF.load()["ui_lang"] == "en", CONF.load()
            CONF.set_value("ui_lang", "pl")
            assert CONF.load()["ui_lang"] == "pl"
            CONF.set_value("ui_lang", "PL")  # normalizacja wielkości liter
            assert CONF.load()["ui_lang"] == "pl"
            CONF.set_value("ui_lang", "en")
            assert CONF.load()["ui_lang"] == "en"
            bad = ""
            try:
                CONF.set_value("ui_lang", "de")
            except ValueError as ex:
                bad = str(ex)
            assert bad, "ui_lang przyjął nieobsługiwany język"
            assert CONF.load()["ui_lang"] == "en", "config zmieniony po błędzie"
            assert (Path(td) / "rezur" / "config.json").is_file()
        finally:
            if old is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = old


@test
def t_gui_i18n_and_wiring():
    """Most GUI: słowniki EN/PL zgodne, każdy t(...) ma tłumaczenie, uchwyty HTML istnieją."""
    import re

    root = Path(__file__).resolve().parent.parent
    js = (root / "rezur" / "gui" / "web" / "app.js").read_text(encoding="utf-8")
    html = (root / "rezur" / "gui" / "web" / "index.html").read_text(encoding="utf-8")

    i_en = js.index("\n  en: {") + 9
    i_pl_raw = js.index("\n  pl: {")
    i_pl = i_pl_raw + 9
    i_end = js.index("\n};", i_pl)
    en, pl = js[i_en:i_pl_raw], js[i_pl:i_end]
    key = re.compile(r"(?:^|, ) *([A-Za-z_][A-Za-z0-9_]*):", re.M)
    ken, kpl = set(key.findall(en)), set(key.findall(pl))
    assert len(ken) > 120, f"nie sparsowano słownika EN (kluczy: {len(ken)})"
    assert ken == kpl, f"rozjazd kluczy EN/PL: {sorted(ken ^ kpl)}"

    used = set(re.findall(r'(?<![A-Za-z0-9_])t\("([A-Za-z0-9_]+)"', js))
    missing = sorted(u for u in used if u not in ken)
    assert not missing, f"klucze w kodzie bez tłumaczenia: {missing}"

    chrome = ["status", "toasts", "busy", "busyTxt", "modal", "mbox", "pendN", "pendW",
              "btnApply", "btnDiscard", "btnUndo", "btnPreview", "ledOk", "ledFile", "ledMd5",
              "ledGame", "txtFile", "txtMd5", "txtGame", "txtVer", "gameBanner", "railPath",
              "pillFile", "pillMd5", "pillGame", "pillAuto", "txtAuto",
              "ctx", "empty", "emptyNote", "emptySub", "btnPick", "btnPick2", "btnRecent",
              "bannerLead", "bannerTxt", "pillLang"]
    miss = [c for c in chrome if f'id="{c}"' not in html]
    assert not miss, f"JS szuka uchwytów, których nie ma w HTML: {miss}"
    assert 'id="btnDiscard"' in html and "btnDiscard span" in js, "przycisk ODRZUĆ bez <span>"

    # wyszukiwanie na żywo podpięte (realny dowód daje --selftest w WebView2)
    css = (root / "rezur" / "gui" / "web" / "style.css").read_text(encoding="utf-8")
    for needle in ("function debounce(", "function attachSuggest(", "function rankByName(",
                   "id=\"invQ\"", "id=\"wq\"", "id=\"suggBox\"", "id=\"eqSugg\"",
                   ".oninput = debounce(", "livehint", "spell_list", "id=\"spRows\"", "function stickBars(",
                   "stickbar", "table-layout:fixed"):
        assert needle in js or needle in html or needle in css, f"brak elementu wyszukiwania na żywo: {needle}"
    assert 'id="spQ"' in js, "brak pola filtra czarów"
    assert ".suggbox" in css and ".suggbox .srow" in css, "brak stylu listy podpowiedzi"
    assert js.count("stickBars(") >= 5, "paski narzędzi nie są przyklejane we wszystkich panelach"

    tabs = re.findall(r'data-tab="([a-z]+)"', html)
    assert len(tabs) == 13, f"zakładek w HTML: {len(tabs)}"
    miss2 = [t for t in tabs if f'id="panel-{t}"' not in html]
    assert not miss2, f"zakładki bez paneli: {miss2}"
    for t in tabs:
        for name, d in (("en", en), ("pl", pl)):
            assert re.search(rf"^    tabs: \{{.*\b{t}:", d, re.M), f"brak etykiety zakładki {t} ({name})"


@test
def t_db_no_cjk_names():
    """Baza flag nie może wracać do japońskich nazw z datamine'u (mamy tłumaczenia + lokacje)."""
    import re

    cjk = re.compile(r"[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")
    root = Path(__file__).resolve().parent.parent / "rezur" / "data" / "db_er"
    bad = []
    for name in ("event_flags.json", "event_flags_extra.json"):
        p = root / name
        if not p.is_file():
            continue
        hits = sorted({m.group(0) for m in cjk.finditer(p.read_text(encoding="utf-8"))})
        if hits:
            bad.append((name, hits))
    assert not bad, f"japońskie znaki w bazie: {bad}"

    import json as _json

    d = _json.loads((root / "event_flags.json").read_text(encoding="utf-8"))
    boss = {r[0]: r for r in d["boss_defeat"]}
    assert boss[9100][1].startswith("Margit"), boss[9100]      # wcześniej zamienione z Godrickiem
    assert boss[9101][1].startswith("Godrick"), boss[9101]
    assert boss[9134][1] == "Mimic Tear", boss[9134]
    for fid in (9100, 9112, 9130, 9184):
        assert boss[fid][2], f"boss {fid} bez lokacji"
    tut = {r[0]: r for r in d["tutorial_seen"]}
    assert tut[710610][1] == "About Birdseye Telescopes", tut[710610]
    assert tut[710570][1] == "About Item Crafting", tut[710570]


@test
def t_spell_catalogue():
    """Katalog czarów: 200+ pozycji, filtr działa, status widzi ekwipunek i gniazda."""
    from rezur.ops import spells as SP

    cat = SP.catalogue()
    assert len(cat) > 200, f"katalog czarów ma {len(cat)} pozycji"
    names = {n for _i, n, _k in cat}
    assert "Urgent Heal" in names and "Flame Sling" in names and "Glintstone Pebble" in names, sorted(names)[:5]
    kinds = {k for _i, _n, k in cat}
    assert kinds == {"sorcery", "incantation"}, kinds
    hits = SP.catalogue("heal")
    assert hits and all("heal" in n.lower() or str(i) == "heal" for i, n, _k in hits), hits[:4]

    src = fixture(FIXED_GLOB)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ER0000.sl2"
        shutil.copy2(src, p)
        sf = SaveFile(p)
        st = SP.status(sf, 0)
        assert st["count"] == len(cat) and st["rows"], st["count"]
        for row in st["rows"]:
            assert set(row) == {"id", "name", "kind", "owned", "memorized"}, row
        # po zapamiętaniu czaru (który jest w ekwipunku) status musi to widzieć
        owned = [r for r in st["rows"] if r["owned"] and not r["memorized"]]
        if owned:
            SP.memorize(sf, 0, owned[0]["name"])
            st2 = SP.status(sf, 0)
            again = next(r for r in st2["rows"] if r["id"] == owned[0]["id"])
            assert again["memorized"], again


@test
def t_release_packaging_ready():
    """Wydanie jednoplikowe: entry.py + interfejs w datas + launcher/instrukcja + UTF-8 w CLI."""
    spec = (ROOT / "packaging" / "rezur.spec").read_text(encoding="utf-8")
    assert "gui/web" in spec, "spec nie pakuje rezur/gui/web — exe otworzy się bez interfejsu"
    assert "entry.py" in spec, "spec nie używa packaging/entry.py (importy relatywne w __main__)"
    entry = ROOT / "packaging" / "entry.py"
    assert entry.is_file() and "from rezur.cli import main" in entry.read_text(encoding="utf-8"), (
        "brak packaging/entry.py z importem pakietu"
    )
    for f in ("START-REZUR.cmd", "HOW-TO-RUN.txt", "RELEASE-NOTES.md"):
        assert (ROOT / "packaging" / "release" / f).is_file(), f"brak packaging/release/{f}"
    cmd = (ROOT / "packaging" / "release" / "START-REZUR.cmd").read_bytes()
    assert b"\r\n" in cmd, "launcher .cmd musi mieć końce linii CRLF"
    assert all(b < 128 for b in cmd), "launcher .cmd musi być ASCII"
    assert (ROOT / "tools" / "make_release_zip.py").is_file(), "brak tools/make_release_zip.py"
    cli = (ROOT / "rezur" / "cli.py").read_text(encoding="utf-8")
    assert "_force_utf8()" in cli, "cli.main bez _force_utf8 — polskie znaki wywalą się w pipe/exe"


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
