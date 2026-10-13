"""Rezur Saves Configurator — interfejs wiersza poleceń.

    python -m rezur info       [--save PLIK]
    python -m rezur doctor     [--save PLIK] [--json] [--expect-steamid N]
    python -m rezur fix        [--save PLIK] [--only id,id] [--apply]
    python -m rezur stats      [--save PLIK] --slot N [--set vigor=60,mind=40]
                               [--runes N] [--runes-memory N] [--name "X"] [--apply]
    python -m rezur item       [--save PLIK] --find Q
                               | --slot N --add ITEM [--upgrade N] [--storage] [--apply]
                               | --slot N --remove ITEM
                               | --slot N --set-qty "ITEM=N"
                               | --slot N --move ITEM --to storage|held
                               | --slot N --set-upgrade "ITEM=N"
                               | --slot N --affinity "ITEM=Blood"
                               | --slot N --aow "ITEM=Bloody Slash"
    python -m rezur inventory  [--save PLIK] --slot N [--storage | --all | --equipped] [--json]
    python -m rezur equipment  [--save PLIK] --slot N [--json]
    python -m rezur equip      [--save PLIK] --slot N (--handle 0x… | --item NAZWA) [--at K] [--apply]
    python -m rezur unequip    [--save PLIK] --slot N [--at K] [--apply]
    python -m rezur spells     [--save PLIK] --slot N [--memorize NAZWA [--at K] | --forget K | --clear] [--apply]
    python -m rezur appearance [--save PLIK] --slot N [--gender 0/1] [--body 0/1] [--gift N] [--apply]
    python -m rezur teleport   [--save PLIK] --slot N [--to limgrave|roundtable|liurnia|altus | --map m60_XX_XX_XX] [--xyz X,Y,Z] [--apply]
    python -m rezur world      [--save PLIK] [--groups]
                               | --slot N --group NAZWA [--filter Q] [--json]
                               | --slot N --group NAZWA (--set "NAZWA|ID" | --all) [--state 0/1] [--apply]
    python -m rezur unlock     [--save PLIK] --slot N --what KATEGORIA [--location storage|held] [--max N] [--apply]
    python -m rezur flags      [--save PLIK] --slot N (--get ID | --set ID:0/1 [--apply])
    python -m rezur graces     [--save PLIK] [--list] | --slot N [--region R] [--apply]
    python -m rezur copy       [--save PLIK] --from N --to M [--clear-source] [--apply]
    python -m rezur swap       [--save PLIK] --a N --b M [--apply]
    python -m rezur clear      [--save PLIK] --slot N [--apply]
    python -m rezur steamid    [--save PLIK] --set ID [--apply]
    python -m rezur export     [--save PLIK] --slot N --out PLIK
    python -m rezur import     [--save PLIK] --to N --in PLIK [--apply]
    python -m rezur backups    [--save PLIK] [--restore NAZWA [--apply]]
    python -m rezur config     [--set klucz=wartość]
    python -m rezur list-fixes
"""

import argparse
import json
import sys
import time
from pathlib import Path

from . import __product__, __version__
from . import config as CONF
from . import fixes as F
from . import risk
from . import staging
from .core import items_db
from .core.profiles import roster
from .core.savefile import SaveFile, default_save_path
from .core.slots import Slot
from .diag import run_diagnostics
from .ops.backups import ensure_gold, list_backups, restore, set_pin
from .ops.copy_slot import clear_character_file, copy_character_file, swap_characters_file
from .ops.watch import run_loop as watch_loop
from .ops.watch import run_once as watch_once
from .ops.flags import graces as graces_data
from .ops.flags import get_flag as flag_get
from .ops.flags import set_flag as flag_set
from .ops.flags import unlock_graces
from .ops.appearance import read as appearance_read
from .ops.appearance import set_appearance
from .ops.items import (
    CATEGORIES,
    add_item,
    category_ids,
    equip_item,
    equipment,
    grant_category,
    handle_for,
    list_inventory,
    move_item,
    parse_selector,
    remove_item,
    resolve_ash,
    set_item_qty,
    set_weapon_affinity,
    set_weapon_aow,
    set_weapon_upgrade,
    unequip,
)
from .ops.spells import clear as spells_clear
from .ops.spells import equipped as spells_equipped
from .ops.spells import forget as spells_forget
from .ops.spells import memorize as spells_memorize
from .ops.stats import STAT_NAMES, rename, set_runes, set_stats
from .ops.steamid import change_steam_id
from .ops.teleport import LOCATIONS as TELEPORT_LOCATIONS
from .ops.teleport import info as teleport_info
from .ops.teleport import parse_map_name
from .ops.teleport import teleport as teleport_do
from .ops.transfer import export_character, import_character
from .ops.world import groups as world_groups
from .ops.world import set_world
from .ops.world import view as world_view
from .report import jsonout as J
from .report import text as R


def _remember_save(path):
    if staging.is_work_path(path):
        return
    try:
        cfg = CONF.load()
        if cfg.get("last_save") != str(path):
            cfg["last_save"] = str(path)
            CONF.save(cfg)
    except OSError:
        pass


def _resolve_save(args):
    """Kolejność: --save → zapamiętany last_save → najnowszy save w %APPDATA%."""
    explicit = getattr(args, "save", None)
    if explicit:
        _remember_save(explicit)
        return explicit
    last = CONF.load().get("last_save")
    if last and Path(last).is_file():
        return last
    return str(default_save_path())


def _load(args):
    path = _resolve_save(args)
    return SaveFile(path)


def _game_running():
    import subprocess

    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq eldenring.exe"],
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout.lower()
        return "eldenring.exe" in out
    except Exception:  # noqa: BLE001
        return False


def _slot_current(sf, idx):
    r = roster(sf)
    s = Slot(sf, idx)
    if s.is_empty:
        raise ValueError(f"slot{idx} jest pusty")
    if not s.parse(r[idx]["name"], r[idx]["level"]):
        raise ValueError(f"slot{idx}: {s.reason}")
    return s, r[idx]


def _guard_game(path=""):
    """Blokuj zapis do żywego save'a przy działającej grze (kopie robocze przepuszczamy)."""
    if not CONF.load().get("guard_live", True):
        return True
    if "eldenring" not in str(path).lower():
        return True
    if _game_running():
        print("!! eldenring.exe działa — zamknij grę przed zapisem.")
        return False
    return True


def _pending_hint(path):
    n = staging.op_count(path)
    if n:
        print(f"! {n} zmian oczekujących (staging) — `rezur pending` | `rezur apply` | `rezur discard`")


def cmd_info(args):
    t0 = time.perf_counter()
    sf = _load(args)
    dt = time.perf_counter() - t0
    print(R.fmt_container(sf))
    print(f"(wczytanie: {dt * 1000:.0f} ms · {sf.path.stat().st_size / 1e6:.1f} MB)")
    print()
    print(R.fmt_characters(sf))
    _pending_hint(sf.path)
    return 0


def cmd_doctor(args):
    sf = _load(args)
    findings = run_diagnostics(sf, expect_steamid=args.expect_steamid)
    if args.json:
        print(json.dumps(J.save_to_dict(sf, findings), indent=2, ensure_ascii=False))
    else:
        print(R.fmt_doctor(sf, findings))
    _pending_hint(sf.path)
    return 1 if any(f.level == "error" for f in findings) else 0


def cmd_fix(args):
    sf = _load(args)
    ids = [x.strip() for x in args.only.split(",")] if args.only else None
    unknown = [x for x in (ids or []) if not F.get_fix(x)]
    if unknown:
        print(f"nieznane naprawy: {', '.join(unknown)} (lista: rezur list-fixes)")
        return 2
    if not args.apply:
        results = F.apply_fixes(sf, ids, dry_run=True)
        if not results:
            print("nic do naprawy.")
            return 0
        print("DRY-RUN — do naprawy:")
        for r_ in results:
            f = F.get_fix(r_.fix_id)
            print(f"  {r_.fix_id:<11s} {f.title}: {r_.targets}")
        print("\ndodaj --apply, aby wykonać (backup robi się automatycznie).")
        return 0
    if not _guard_game(sf.path):
        return 3
    results = F.apply_fixes(sf, ids, dry_run=False)
    if not any(r_.applied for r_ in results):
        print("nic do naprawy (albo wszystko pominięte).")
        return 0
    for r_ in results:
        print(f"[{r_.fix_id}] {F.get_fix(r_.fix_id).title}")
        for a in r_.applied:
            print("  +", a)
        for s in r_.skipped:
            print("  -", s)
    bak = sf.write(backup_tag="rezurbak")
    print(f"\nzapisane (backup: {bak})")
    if CONF.load().get("auto_doctor", True):
        findings = run_diagnostics(sf)
        errs = sum(1 for f in findings if f.level == "error")
        warns = sum(1 for f in findings if f.level == "warning")
        print(f"po naprawie: {errs} błędów, {warns} ostrzeżeń")
    return 0


def cmd_stats(args):
    sf = _load(args)
    changes = {}
    if args.set:
        for part in args.set.split(","):
            if "=" not in part:
                raise ValueError(f"zły format --set: {part!r} (np. vigor=60)")
            k, v = part.split("=", 1)
            changes[k.strip()] = int(v)
    if not (changes or args.runes is not None or args.runes_memory is not None or args.name):
        print("nic do zmiany — podaj --set / --runes / --runes-memory / --name")
        return 2
    if args.name is not None and not (1 <= len(args.name) <= 16):
        raise ValueError("imię: 1..16 znaków")

    if not args.apply:
        s, _ = _slot_current(sf, args.slot)
        stats = s.pgd_stats()
        print(f"slot{args.slot} '{s.pgd_name()}' — obecnie:")
        print("  staty: " + ", ".join(f"{n}={v}" for n, v in zip(STAT_NAMES, stats))
              + f"  → level {s.pgd_level()}")
        print(f"  runy: {s.pgd_runes():,}  runes_memory: {s.pgd_runes_memory():,}  imię: {s.pgd_name()!r}")
        if changes:
            bad = [k for k in changes if k not in STAT_NAMES]
            if bad:
                raise ValueError(f"nieznane statystyki: {bad}")
            new = stats[:]
            for k, v in changes.items():
                new[STAT_NAMES.index(k)] = v
            print(f"  po zmianie: {new} → level {sum(new) - 79}")
        if args.runes is not None:
            print(f"  runy → {args.runes:,}")
        if args.runes_memory is not None:
            print(f"  runes_memory → {args.runes_memory:,}")
        if args.name:
            print(f"  imię → {args.name!r}")
        print("\nDRY-RUN. dodaj --apply, aby zapisać.")
        return 0

    if not _guard_game(sf.path):
        return 3
    out = {}
    if changes:
        out["stats"] = set_stats(sf, args.slot, changes)
    if args.runes is not None or args.runes_memory is not None:
        out["runes"] = set_runes(sf, args.slot, runes=args.runes, runes_memory=args.runes_memory)
    if args.name:
        out["name"] = rename(sf, args.slot, args.name)
    bak = sf.write(backup_tag="editbak")
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print(f"zapisane. backup: {bak}")
    return 0


def _sel_handle(sf, slot, sel):
    kind, val = parse_selector(sel)
    if kind == "handle":
        return val
    return handle_for(sf, slot, val)


def cmd_item(args):
    if args.find:
        res = items_db.search(args.find)
        print(f"trafienia: {len(res)}")
        for fid, name, cat in res:
            print(f"  0x{fid:08X}  {name:<44s} [{cat}]")
        return 0

    if args.add is None and args.remove is None and args.set_qty is None and args.move is None \
            and args.set_upgrade is None and args.affinity is None and args.aow is None:
        print('użyj: --find Q | --slot N (--add ITEM | --remove ITEM | --set-qty "ITEM=N" | --move ITEM --to held|storage'
              ' | --set-upgrade "ITEM=N" | --affinity "ITEM=Blood" | --aow "ITEM=Ash of War")')
        return 2
    if args.slot is None:
        print("podaj --slot N")
        return 2
    sf = _load(args)

    if args.add is not None:
        a = args.add.strip()
        if a.lower().startswith("0x"):
            full_id, disp = int(a, 16), a
        else:
            ex = items_db.find_exact(a)
            if ex:
                full_id, disp = ex[0], ex[1]
            else:
                res = items_db.search(a, 6)
                if not res:
                    print("nie znalazłem nic o tej nazwie")
                    return 2
                if len({fid for fid, _, _ in res}) > 1:
                    print("kilka trafień — doprecyzuj (nazwa albo 0xID):")
                    for fid, name, cat in res:
                        print(f"  0x{fid:08X}  {name} [{cat}]")
                    return 2
                full_id, disp = res[0][0], res[0][1]
        if not args.apply:
            print(f"DRY-RUN: dodałbym do slot{args.slot}: 0x{full_id:08X} '{disp}'")
            print(f"  qty={args.qty}  upgrade={args.upgrade}  location={'storage' if args.storage else 'held'}")
            return 0
        if not _guard_game(sf.path):
            return 3
        rep = add_item(
            sf, args.slot, full_id, qty=args.qty, upgrade=args.upgrade,
            location="storage" if args.storage else "held",
        )
        bak = sf.write(backup_tag="itembak")
        for k, v in rep.items():
            print(f"  {k}: {v}")
        print(f"zapisane. backup: {bak}")
        return 0

    if args.remove is not None:
        h = args.handle if args.handle is not None else _sel_handle(sf, args.slot, args.remove)
        if not args.apply:
            print(f"DRY-RUN: usunąłbym handle 0x{h:08X} ze slot{args.slot}")
            return 0
        if not _guard_game(sf.path):
            return 3
        rep = remove_item(sf, args.slot, h)
        bak = sf.write(backup_tag="itembak")
        for k, v in rep.items():
            print(f"  {k}: {v}")
        print(f"zapisane. backup: {bak}")
        return 0

    if args.set_qty is not None:
        if "=" not in args.set_qty:
            print('format: --set-qty "ITEM=N" (albo 0xID=N / handle:0x…=N)')
            return 2
        sel, qs = args.set_qty.rsplit("=", 1)
        qty = int(qs)
        h = args.handle if args.handle is not None else _sel_handle(sf, args.slot, sel.strip())
        if not args.apply:
            print(f"DRY-RUN: handle 0x{h:08X} → ilość {qty} (slot{args.slot})")
            return 0
        if not _guard_game(sf.path):
            return 3
        rep = set_item_qty(sf, args.slot, h, qty)
        bak = sf.write(backup_tag="itembak")
        for k, v in rep.items():
            print(f"  {k}: {v}")
        print(f"zapisane. backup: {bak}")
        return 0

    if args.set_upgrade is not None:
        if "=" not in args.set_upgrade:
            print('format: --set-upgrade "ITEM=N"')
            return 2
        sel, ns = args.set_upgrade.rsplit("=", 1)
        lvl = int(ns)
        h = args.handle if args.handle is not None else _sel_handle(sf, args.slot, sel.strip())
        if not args.apply:
            print(f"DRY-RUN: ulepszyłbym broń 0x{h:08X} na +{lvl} (slot{args.slot})")
            return 0
        if not _guard_game(sf.path):
            return 3
        rep = set_weapon_upgrade(sf, args.slot, h, lvl)
        bak = sf.write(backup_tag="itembak")
        for k, v in rep.items():
            print(f"  {k}: {v}")
        print(f"zapisane. backup: {bak}")
        return 0

    if args.affinity is not None:
        if "=" not in args.affinity:
            print('format: --affinity "ITEM=Blood"')
            return 2
        sel, aff = args.affinity.rsplit("=", 1)
        h = args.handle if args.handle is not None else _sel_handle(sf, args.slot, sel.strip())
        if not args.apply:
            print(f"DRY-RUN: affinity broni 0x{h:08X} → {aff.strip()} (slot{args.slot})")
            return 0
        if not _guard_game(sf.path):
            return 3
        rep = set_weapon_affinity(sf, args.slot, h, aff.strip())
        bak = sf.write(backup_tag="itembak")
        for k, v in rep.items():
            print(f"  {k}: {v}")
        print(f"zapisane. backup: {bak}")
        return 0

    if args.aow is not None:
        if "=" not in args.aow:
            print('format: --aow "ITEM=Bloody Slash"')
            return 2
        sel, ash = args.aow.rsplit("=", 1)
        h = args.handle if args.handle is not None else _sel_handle(sf, args.slot, sel.strip())
        ash_id = resolve_ash(ash.strip())
        if not args.apply:
            print(f"DRY-RUN: przypnę Ash 0x{ash_id:08X} do broni 0x{h:08X} (slot{args.slot})")
            return 0
        if not _guard_game(sf.path):
            return 3
        rep = set_weapon_aow(sf, args.slot, h, ash_id)
        bak = sf.write(backup_tag="itembak")
        for k, v in rep.items():
            print(f"  {k}: {v}")
        print(f"zapisane. backup: {bak}")
        return 0

    # --move
    to = (args.to or "storage").strip()
    h = args.handle if args.handle is not None else _sel_handle(sf, args.slot, args.move)
    if not args.apply:
        print(f"DRY-RUN: przeniósłbym handle 0x{h:08X} → {to} (slot{args.slot})")
        return 0
    if not _guard_game(sf.path):
        return 3
    rep = move_item(sf, args.slot, h, to)
    bak = sf.write(backup_tag="itembak")
    for k, v in rep.items():
        print(f"  {k}: {v}")
    print(f"zapisane. backup: {bak}")
    return 0


def cmd_inventory(args):
    sf = _load(args)
    if args.equipped:
        eq = equipment(sf, args.slot)
        if args.json:
            print(json.dumps(eq, ensure_ascii=False, indent=2))
            return 0
        print(f"slot{args.slot} — założone:")
        for e in eq["equipped"]:
            if e["empty"]:
                continue
            print(f"  [{e['slot']:>2}] {e['zone']:<9} 0x{e['handle']:08X}  {e['name']}")
        return 0
    locs = ["storage"] if args.storage else (["held", "storage"] if args.all else ["held"])
    for loc in locs:
        items = list_inventory(sf, args.slot, loc)
        if args.json:
            print(json.dumps({"slot": args.slot, "location": loc, "items": items}, ensure_ascii=False, indent=2))
            continue
        label = "skrzynia" if loc == "storage" else "przy sobie"
        print(f"slot{args.slot} — ekwipunek ({label}): {len(items)} pozycji")
        for it in items[:500]:
            print(f"  0x{it['handle']:08X}  x{it['qty']:<4d}  {it['name']}")
        if len(items) > 500:
            print(f"  ... i {len(items) - 500} więcej")
    return 0


def cmd_flags(args):
    sf = _load(args)
    if args.get is not None:
        print(f"flag {args.get} = {flag_get(sf, args.slot, args.get)}")
        return 0
    if args.set is not None:
        eid_s, st_s = args.set.split(":", 1)
        eid = int(eid_s)
        st = st_s.strip().lower() in ("1", "true", "on", "tak")
        if not args.apply:
            print(f"DRY-RUN: flag {eid} → {st} (slot{args.slot})")
            return 0
        if not _guard_game(sf.path):
            return 3
        rep = flag_set(sf, args.slot, eid, st)
        bak = sf.write(backup_tag="flagbak")
        print(f"{rep}  backup: {bak}")
        return 0
    print("podaj --get ID albo --set ID:0/1")
    return 2


def cmd_graces(args):
    if args.list or args.slot is None:
        data = graces_data()
        for reg, items in data.items():
            print(f"  {reg} ({len(items)})")
        print(f"regionów: {len(data)}")
        return 0
    sf = _load(args)
    if not args.apply:
        rep = unlock_graces(sf, args.slot, args.region, apply=False)
        print(f"DRY-RUN: regionów {rep['regions']}, flag do ustawienia {rep['set']} "
              f"(już ustawione/nieznane: {rep['already_or_unknown']})")
        for reg, fid, name in rep["sample"]:
            print(f"   {reg}: {name} (flag {fid})")
        print("dodaj --apply, aby zapisać.")
        return 0
    if not _guard_game(sf.path):
        return 3
    rep = unlock_graces(sf, args.slot, args.region, apply=True)
    bak = sf.write(backup_tag="gracebak")
    print(f"ustawiono {rep['set']} flag łask ({rep['regions']} regionów); backup: {bak}")
    return 0


def cmd_copy(args):
    path = _resolve_save(args)
    if args.apply and not _guard_game(path):
        return 3
    r = copy_character_file(
        path, args.src, args.dst, clear_source=args.clear_source, apply=args.apply
    )
    for k, v in r.items():
        print(f"  {k}: {v}")
    if not args.apply:
        print("\nDRY-RUN. dodaj --apply, aby wykonać.")
    return 0


def cmd_steamid(args):
    path = _resolve_save(args)
    raw = str(args.set).strip()
    if not (raw.isdigit() and len(raw) == 17):
        print("SteamID64 to 17 cyfr, np. 76561199197611189")
        return 2
    sf = SaveFile(path)
    new = int(raw)
    if not args.apply:
        print(f"obecny SteamID: {sf.steam_id()}  ->  po zmianie: {new}")
        print("DRY-RUN. dodaj --apply, aby wykonać.")
        return 0
    if not _guard_game(path):
        return 3
    rep = change_steam_id(sf, new)
    bak = sf.write(backup_tag="steamidbak")
    print(f"SteamID {rep['old']} -> {rep['new']}; sloty: {rep['slots'] or 'brak'}; backup: {bak}")
    return 0


def cmd_swap(args):
    path = _resolve_save(args)
    if args.apply and not _guard_game(path):
        return 3
    r = swap_characters_file(path, args.a, args.b, apply=args.apply)
    for k, v in r.items():
        print(f"  {k}: {v}")
    if not args.apply:
        print("\nDRY-RUN. dodaj --apply, aby wykonać.")
    return 0


def cmd_clear(args):
    path = _resolve_save(args)
    if args.apply and not _guard_game(path):
        return 3
    r = clear_character_file(path, args.slot, apply=args.apply)
    for k, v in r.items():
        print(f"  {k}: {v}")
    if not args.apply:
        print("\n[!] czyści postać z tego slotu (profil + slot + MD5) — bez --apply nic się nie dzieje;"
              " przy --apply zadziała backup automatyczny")
        print("DRY-RUN. dodaj --apply, aby wykonać.")
    return 0


def cmd_equipment(args):
    sf = _load(args)
    eq = equipment(sf, args.slot)
    if args.json:
        print(json.dumps(eq, ensure_ascii=False, indent=2))
        return 0
    print(f"slot{args.slot} — wyposażenie:")
    for e in eq["equipped"]:
        mark = "(puste)" if e["empty"] else f"0x{e['handle']:08X}  {e['name']}"
        print(f"  [{e['slot']:>2}] {e['zone']:<9} {mark}")
    return 0


def cmd_equip(args):
    sf = _load(args)
    if args.handle is not None:
        h = args.handle
    elif args.item is not None:
        h = _sel_handle(sf, args.slot, args.item)
    else:
        print("podaj --handle 0x… albo --item NAZWA")
        return 2
    if not args.apply:
        where = f" na gniazdo {args.at}" if args.at is not None else " (pierwsze wolne)"
        print(f"DRY-RUN: założę handle 0x{h:08X} w slot{args.slot}{where}")
        return 0
    if not _guard_game(sf.path):
        return 3
    rep = equip_item(sf, args.slot, h, args.at)
    bak = sf.write(backup_tag="equipbak")
    for k, v in rep.items():
        print(f"  {k}: {v}")
    print(f"zapisane. backup: {bak}")
    return 0


def cmd_unequip(args):
    sf = _load(args)
    if not args.apply:
        what = f"gniazdo {args.at} (slot{args.slot})" if args.at is not None else f"wszystko (slot{args.slot})"
        print(f"DRY-RUN: zdejmę {what}")
        return 0
    if not _guard_game(sf.path):
        return 3
    rep = unequip(sf, args.slot, args.at)
    bak = sf.write(backup_tag="equipbak")
    for k, v in rep.items():
        print(f"  {k}: {v}")
    print(f"zapisane. backup: {bak}")
    return 0


def cmd_spells(args):
    sf = _load(args)
    if getattr(args, "catalog", False):
        from .ops.spells import status as spells_status

        st = spells_status(sf, args.slot, args.filter, 500)
        if args.json:
            print(json.dumps(st, ensure_ascii=False, indent=2))
            return 0
        print(f"slot{args.slot} — katalog czarów ({st['count']}):")
        for row in st["rows"]:
            state = "zapamiętany" if row["memorized"] else ("w ekwipunku" if row["owned"] else "brak")
            kind = "czar" if row["kind"] == "sorcery" else "inkantacja"
            print(f"  {row['id']:>5}  [{kind:>10}] {row['name']:<34} {state}")
        return 0
    if args.memorize is not None:
        if not args.apply:
            where = f" w gnieździe {args.at}" if args.at is not None else " (pierwsze wolne)"
            print(f"DRY-RUN: zapamiętam {args.memorize!r}{where}")
            return 0
        if not _guard_game(sf.path):
            return 3
        rep = spells_memorize(sf, args.slot, args.memorize, args.at)
        bak = sf.write(backup_tag="spellbak")
        for k, v in rep.items():
            print(f"  {k}: {v}")
        print(f"zapisane. backup: {bak}")
        return 0
    if args.forget is not None:
        if not args.apply:
            print(f"DRY-RUN: zwolnię gniazdo {args.forget}")
            return 0
        if not _guard_game(sf.path):
            return 3
        rep = spells_forget(sf, args.slot, args.forget)
        bak = sf.write(backup_tag="spellbak")
        print(f"  {rep}")
        print(f"zapisane. backup: {bak}")
        return 0
    if args.clear:
        if not args.apply:
            print("DRY-RUN: wyczyszczę wszystkie gniazda czarów")
            return 0
        if not _guard_game(sf.path):
            return 3
        rep = spells_clear(sf, args.slot)
        bak = sf.write(backup_tag="spellbak")
        print(f"  {rep}")
        print(f"zapisane. backup: {bak}")
        return 0
    v = spells_equipped(sf, args.slot)
    if args.json:
        print(json.dumps(v, ensure_ascii=False, indent=2))
        return 0
    used = sum(1 for x in v["spells"] if not x["empty"])
    print(f"slot{args.slot} — czary ({used}/14):")
    for x in v["spells"]:
        mark = "(puste)" if x["empty"] else x["name"]
        print(f"  [{x['slot']:>2}] {mark}")
    return 0


def cmd_appearance(args):
    sf = _load(args)
    if args.gender is None and args.body is None and args.gift is None:
        v = appearance_read(sf, args.slot)
        body = "B" if v["body_type"] else "A"
        print(f"slot{args.slot}: gender={v['gender']}  typ ciała={body}  archetyp={v['archetype']}  dar={v['gift']}")
        return 0
    if not args.apply:
        print(f"DRY-RUN: wygląd slot{args.slot} (gender={args.gender}, body={args.body}, gift={args.gift})")
        return 0
    if not _guard_game(sf.path):
        return 3
    rep = set_appearance(sf, args.slot, gender=args.gender, body_type=args.body, gift=args.gift)
    bak = sf.write(backup_tag="lookbak")
    for k, v in rep.items():
        print(f"  {k}: {v}")
    print(f"zapisane. backup: {bak}")
    return 0


def cmd_teleport(args):
    sf = _load(args)
    if args.to is None and args.map is None:
        v = teleport_info(sf, args.slot)
        print(f"slot{args.slot}: {v['map_name']} (0x{v['map_id']:08X})  xyz={[round(c, 1) for c in v['xyz']]}")
        print(f"spawn: {v['spawn']}")
        return 0
    mid = parse_map_name(args.map) if args.map is not None else None
    xyz = None
    if args.xyz:
        parts = [float(x) for x in args.xyz.split(",")]
        if len(parts) != 3:
            raise ValueError("--xyz X,Y,Z")
        xyz = tuple(parts)
    if not args.apply:
        where = args.to or args.map
        print(f"DRY-RUN: teleport slot{args.slot} → {where}" + (f"  xyz={xyz}" if xyz else ""))
        return 0
    if not _guard_game(sf.path):
        return 3
    rep = teleport_do(sf, args.slot, dest=args.to, map_id=mid, xyz=xyz)
    bak = sf.write(backup_tag="tpbak")
    label = f"  ({rep['to']['label']})" if rep["to"].get("label") else ""
    print(f"  {rep['from']['map_name']}  →  {rep['to']['map_name']}{label}")
    if rep["xyz_set"]:
        print(f"  xyz: {rep['xyz_set']}")
    print(f"zapisane. backup: {bak}")
    return 0


def cmd_world(args):
    if args.groups or args.group is None:
        for g, n in sorted(world_groups().items()):
            print(f"  {g:<20s} {n:5d}")
        print("podgląd:  world --slot N --group NAZWA [--filter Q]")
        print('zmiana:   world --slot N --group NAZWA (--set "fragment" | --all) [--state 0/1] --apply')
        return 0
    sf = _load(args)
    if args.slot is None:
        print("podaj --slot N")
        return 2
    if args.set is None and not args.all:
        v = world_view(sf, args.slot, args.group, args.filter)
        if args.json:
            print(json.dumps(v, ensure_ascii=False, indent=2))
            return 0
        for e in v["entries"]:
            mark = {True: "[x]", False: "[ ]", None: "[?]"}[e["value"]]
            tail = f"   ({e['desc']})" if e["desc"] else ""
            print(f"  {mark} {e['id']:>9}  {e['name']}{tail}")
        return 0
    value = True if args.state is None else bool(args.state)
    if not args.apply:
        rep = set_world(sf, args.slot, args.group, args.set, value, args.filter, args.all, apply=False)
        print(f"DRY-RUN [{args.group} → {value}]: do zmiany {rep['set']}, już/nieznane: {rep['already_or_unknown']}")
        for fid, name in rep["sample"]:
            print(f"   {fid:>9}  {name}")
        print("dodaj --apply")
        return 0
    if not _guard_game(sf.path):
        return 3
    rep = set_world(sf, args.slot, args.group, args.set, value, args.filter, args.all, apply=True)
    bak = sf.write(backup_tag="worldbak")
    print(f"ustawiono {rep['set']} flag [{args.group}] → {value} (pominięto {rep['already_or_unknown']})")
    for fid, name in rep["sample"][:6]:
        print(f"   {fid:>9}  {name}")
    print(f"zapisane. backup: {bak}")
    return 0


def cmd_unlock(args):
    sf = _load(args)
    if not args.apply:
        ids = category_ids(args.what)
        print(f"DRY-RUN: kategoria {args.what}: {len(ids)} pozycji w bazie (istniejące pomijam)")
        return 0
    if not _guard_game(sf.path):
        return 3
    rep = grant_category(sf, args.slot, args.what, location=args.location, limit=args.max)
    bak = sf.write(backup_tag="unlockbak")
    for k, v in rep.items():
        print(f"  {k}: {v}")
    print(f"zapisane. backup: {bak}")
    return 0


def cmd_export(args):
    sf = _load(args)
    rep = export_character(sf, args.slot, args.out)
    for k, v in rep.items():
        print(f"  {k}: {v}")
    return 0


def cmd_import(args):
    path = _resolve_save(args)
    if not args.apply:
        print(f"DRY-RUN: zaimportuję {args.file_in} → slot{args.to}")
        return 0
    if not _guard_game(path):
        return 3
    sf = SaveFile(path)
    rep = import_character(sf, args.file_in, args.to)
    bak = sf.write(backup_tag="importbak")
    for k, v in rep.items():
        print(f"  {k}: {v}")
    print(f"zapisane. backup: {bak}")
    return 0


def cmd_backups(args):
    path = _resolve_save(args)
    if getattr(args, "gold", False):
        try:
            res = ensure_gold(path)
        except FileNotFoundError:
            print(f"nie ma pliku: {path}")
            return 2
        print(("zrobiono" if res["created"] else "już jest") + f" kopia GOLD: {res['path']}")
        return 0
    if args.pin or args.unpin:
        raw = args.pin or args.unpin
        baks = list_backups(path)
        hit = next((b for b in baks if b["name"] in (raw, Path(raw).name)), None)
        name = hit["name"] if hit else Path(raw).name
        if not hit and not Path(raw).is_file():
            print(f"nie znalazłem kopii: {raw}")
            return 2
        pins = set_pin(path, name, on=bool(args.pin))
        print(("przypięto" if args.pin else "odpięto") + f": {name}")
        print("przypięte: " + (", ".join(pins) if pins else "(brak)"))
        return 0
    if args.restore:
        baks = list_backups(path)
        hit = next((b for b in baks if b["name"] == args.restore), None)
        target = hit["path"] if hit else args.restore
        if not Path(target).is_file():
            print(f"nie znalazłem kopii: {args.restore}")
            return 2
        if not args.apply:
            print(f"DRY-RUN: przywrócę {target} → {path}")
            return 0
        if not _guard_game(path):
            return 3
        rep = restore(path, target)
        print(f"przywrócono z {rep['restored_from']}")
        print(f"kopia stanu sprzed przywrócenia: {rep['pre_restore_copy']}")
        return 0
    baks = list_backups(path)
    print(f"kopie dla {path}:")
    for b in baks[:60]:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(b["mtime"]))
        mark = "GOLD" if b["gold"] else ("PIN " if b["pinned"] else "    ")
        print(f"  {mark} {when}  {b['name']}  ({b['size'] / 1e6:.1f} MB)")
    if not baks:
        print("  (brak — powstają przy każdym zapisie)")
    else:
        g = next((b for b in baks if b["gold"]), None)
        print("  " + (f"GOLD: {g['name']}" if g else "GOLD: (brak — powstanie przy pierwszej modyfikacji)"))
        n_pin = sum(1 for b in baks if b["pinned"])
        if n_pin:
            print(f"  przypięte: {n_pin}")
    return 0


def cmd_watch(args):
    """Auto-kopiec: kopia przy starcie gry i co interwał, dopóki gra działa."""
    path = _resolve_save(args)
    interval = args.interval if args.interval is not None else CONF.load().get("watch_interval", 600)
    if args.once:
        res = watch_once(path, interval=interval)
        if not res["running"]:
            print("gra nie działa — nic do robienia (kopia powstanie, gdy wystartuje).")
        elif res["made"]:
            print(f"gra działa ({res['reason']}) → kopia: {res['made']}")
        else:
            print(f"gra działa; nic nie robię ({res['reason']})")
        return 0
    return watch_loop(path, interval=interval)


def cmd_risk(args):
    """Ryzyko online: dane niemożliwe + znacznik modyfikacji + droga do GOLD."""
    sf = _load(args)
    res = risk.scan(sf, only_slot=args.slot)
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 1 if res["verdict"] == "red" else 0
    mark = {"green": "ZIELONY", "yellow": "ŻÓŁTY", "red": "CZERWONY"}
    m = res["modified"]
    print(f"RYZYKO ONLINE — {sf.path}")
    if m["count"]:
        ops = ", ".join(f"{k}×{v}" for k, v in m["ops"].items())
        print(f"znacznik: plik MODYFIKOWANY przez Rezura — {m['count']} operacji ({ops}); ostatnia {m['last']}")
    else:
        print("znacznik: brak śladów Rezura w tym pliku")
    if res["gold"]:
        print(f"GOLD:    {res['gold']}")
        print(f"powrót:  python -m rezur backups --restore \"{res['gold']}\" --apply")
    else:
        print("GOLD:    brak (powstanie przy pierwszej modyfikacji)")
    print()
    per = {}
    for f in res["findings"]:
        per.setdefault(f["slot"], []).append(f)
    for i in range(10):
        s = Slot(sf, i)
        if s.is_empty or (args.slot is not None and i != args.slot):
            continue
        fs = per.get(i, [])
        if any(f["level"] == "error" for f in fs):
            v = "red"
        elif any(f["level"] == "warning" for f in fs):
            v = "yellow"
        else:
            v = "green"
        print(f"slot{i}: {mark[v]}")
        for f in fs:
            print(f"   [{f['level']}] {f['message']}")
        if not fs:
            print("   brak danych niemożliwych, które potrafimy sprawdzić")
    print()
    print("NOTATKI:")
    for n in res["notes"]:
        print(f"  • {n}")
    return 1 if res["verdict"] == "red" else 0


def cmd_find(args):
    """Szukajka po wszystkim: itemy, flagi świata (wszystkie grupy), łaski, lokacje."""
    q = args.query
    from .core import items_db
    from .ops.flags import graces as graces_data
    from .ops import world as world_ops

    items = items_db.search(q, limit=args.limit)
    flags = world_ops.search_names(q, limit=args.limit)
    locs = [(k, v) for k, v in TELEPORT_LOCATIONS.items() if q.lower() in k.lower()]
    try:
        graces_hits = [
            (region, gname)
            for region, rows in graces_data().items()
            for fid, gname in rows
            if q.lower() in gname.lower()
        ][: args.limit]
    except OSError:
        graces_hits = []

    if args.json:
        print(json.dumps({
            "query": q, "items": items, "flags": flags,
            "graces": graces_hits, "locations": locs,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"ITEMY ({len(items)}):")
    for fid, name, cat in items[:20]:
        print(f"  0x{fid:08X}  {name}  [{cat}]")
    if not items:
        print("  (brak)")
    print(f"\nFLAGI ŚWIATA ({len(flags)}):")
    for group, fid, name in flags[:20]:
        print(f"  {fid:>8}  {name}  [{group}]")
    if not flags:
        print("  (brak)")
    if graces_hits:
        print(f"\nŁASKI ({len(graces_hits)}):")
        for region, gname in graces_hits[:12]:
            print(f"  {gname}  [{region}]")
    if locs:
        print(f"\nLOKACJE TELEPORTU ({len(locs)}): " + ", ".join(k for k, _ in locs))
    if not (items or flags or graces_hits or locs):
        print("\nnic nie pasuje — szukaj po fragmencie nazwy (np. 'uchi', 'godrick', 'map')")
    return 0


STAGEABLE = {
    "fix", "stats", "item", "equip", "unequip", "spells", "appearance", "teleport",
    "world", "unlock", "flags", "graces", "copy", "swap", "clear", "steamid", "import",
}


def cmd_stage(args):
    """Edytuj w kopii roboczej (oryginał nietknięty) — zmiany oczekujące."""
    path = _resolve_save(args)
    rest = list(args.rest)
    if not rest or rest[0].startswith("-"):
        print("użycie: rezur stage <komenda edycji> [opcje...]")
        print("  np.: rezur stage stats --slot 0 --set vigor=61")
        print(f"  komendy: {', '.join(sorted(STAGEABLE))}")
        return 2
    cmd, op_args = rest[0], rest[1:]
    if cmd not in STAGEABLE:
        print(f"staging dotyczy komend edytujących: {', '.join(sorted(STAGEABLE))}")
        return 2
    try:
        work = staging.begin(path)
    except FileNotFoundError:
        print(f"nie ma pliku: {path}")
        return 2
    before = staging.md5_file(work)
    snap = staging.make_snapshot(path)
    argv = [cmd, "--save", str(work), *op_args]
    if "--apply" not in argv:
        argv.append("--apply")
    print(f"staging → {work}")
    rc = main(argv)
    if rc != 0:
        staging.drop_snapshot(path, snap)
        print("(komenda nie przeszła — nic nie doliczam)")
        return rc
    if staging.md5_file(work) == before:
        staging.drop_snapshot(path, snap)
        print("bez zmian danych — nic nie doliczam do zmian oczekujących.")
        return 0
    n = staging.record_op(path, cmd, " ".join(op_args) or "(bez opcji)", snap=snap)
    print(f"→ zmiany oczekujące: {n}   (`rezur apply` zatwierdza, `rezur discard` odrzuca,"
          " `rezur pending --undo` cofa ostatnią)")
    return 0


def cmd_pending(args):
    path = _resolve_save(args)
    if args.undo:
        try:
            res = staging.undo_last(path)
        except ValueError as e:
            print(f"nie ma czego cofnąć: {e}")
            return 2
        u = res["undone"]
        print(f"cofnięto: [{u['op']}] {u['summary']}   (pozostało zmian: {res['left']})")
        return 0
    man = staging.load_manifest(path)
    if not man:
        print("brak zmian oczekujących — edytuj przez: rezur stage <komenda> ...")
        return 0
    print(f"ZMIANY OCZEKUJĄCE: {len(man['ops'])} (od {man['created']})")
    for i, op in enumerate(man["ops"], 1):
        print(f"  {i:>2d}. [{op['ts']}] {op['op']}: {op['summary']}")
    last = man["ops"][-1] if man["ops"] else None
    if last and last.get("snap"):
        print("  (ostatnią zmianę cofniesz: rezur pending --undo)")
    if staging.original_changed(path):
        print("  !! oryginał zmienił się od rozpoczęcia stagingu (gra zapisała?) — apply wymaga --force")
    if args.diff:
        try:
            so = SaveFile(path)
            sw = SaveFile(staging.work_path(path))
            changed = []
            for e in so.entries:
                a = so.data[e["off"] + 16: e["off"] + e["size"]]
                b = sw.data[e["off"] + 16: e["off"] + e["size"]]
                if a != b:
                    changed.append(e["name"])
            print("  zmienione sekcje: " + (", ".join(changed) if changed else "brak różnic bajtowych"))
        except (OSError, ValueError) as e:
            print(f"  (nie udało się policzyć różnic: {e})")
    print("  → zatwierdź: python -m rezur apply   |   odrzuć: python -m rezur discard")
    return 0


def cmd_apply(args):
    path = _resolve_save(args)
    if staging.op_count(path) == 0:
        print("brak zmian oczekujących — edytuj przez: rezur stage <komenda> ...")
        return 2
    if not _guard_game(path):
        return 3
    try:
        res = staging.apply(path, force=args.force)
    except RuntimeError as e:
        print(f"wstrzymane: {e}")
        return 3
    except ValueError as e:
        print(f"ODRZUCONO ZAPIS: {e}")
        print("zmiany oczekujące ZOSTAJĄ — popraw brudnopis albo `rezur discard`")
        return 1
    print(f"zastosowano {res['ops']} zmian. backup: {res['backup']}")
    print(f"sumy sekcji po zapisie: {res['md5_ok']}/{res['md5_total']} OK")
    return 0


def cmd_discard(args):
    path = _resolve_save(args)
    res = staging.discard(path)
    if res["ops"]:
        print(f"odrzucono {res['ops']} zmian — oryginał nietknięty.")
    elif res["removed"]:
        print("usunięto brudnopis stagingu (bez zmian do odrzucenia).")
    else:
        print("brak zmian oczekujących.")
    return 0


def cmd_log(args):
    path = _resolve_save(args)
    from .core import journal

    es = journal.load(path)["entries"]
    if args.json:
        print(json.dumps(es, indent=2, ensure_ascii=False))
        return 0
    print(f"HISTORIA OPERACJI — {path}")
    if not es:
        print("  (pusto — dziennik zapisuje każdą udaną modyfikację)")
        return 0
    for e in es[-40:]:
        note = f"  ← backup: {e['note']}" if e.get("note") else ""
        print(f"  {e['ts']}  {journal.OP_LABELS.get(e['op'], e['op']):<28s}{note}")
    n = staging.op_count(path)
    if n:
        print(f"  (+ {n} zmian oczekujących — jeszcze niezapisanych)")
    return 0


def cmd_gui(args):
    from .gui.app import run

    return run(args.save, selftest=getattr(args, "selftest", False))


def cmd_config(args):
    if args.set:
        if "=" not in args.set:
            print("format: --set klucz=wartość")
            return 2
        k, v = args.set.split("=", 1)
        key, val = CONF.set_value(k.strip(), v)
        print(f"{key} = {val}")
        print(f"({CONF.config_path()})")
        return 0
    print(f"config: {CONF.config_path()}")
    for k, v in CONF.load().items():
        print(f"  {k} = {v}")
    return 0


def cmd_list_fixes(args):
    print(f"{__product__} v{__version__} — naprawy:")
    for f in F.list_fixes():
        print(f"  {f.id:<11s} {f.title}")
        print(f"              {f.description}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="rezur", description=f"{__product__} v{__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_save(sp):
        sp.add_argument(
            "--save",
            default=None,
            help=r"ścieżka do .sl2 (domyślnie: najnowszy w %%APPDATA%%\EldenRing)",
        )

    sp = sub.add_parser("info", help="postacie + stan kontenera")
    add_save(sp)
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("doctor", help="diagnostyka (tylko czyta)")
    add_save(sp)
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--expect-steamid", type=int, default=None)
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("fix", help="naprawy (dry-run domyślnie)")
    add_save(sp)
    sp.add_argument("--only", default=None, help="np. torrent,checksums")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_fix)

    sp = sub.add_parser("stats", help="statystyki / runy / imię")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--set", default=None, help="np. vigor=60,mind=40")
    sp.add_argument("--runes", type=int, default=None)
    sp.add_argument("--runes-memory", type=int, default=None)
    sp.add_argument("--name", default=None)
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("item", help="itemy: szukaj / dodaj / usuń / ilość / przenieś")
    add_save(sp)
    sp.add_argument("--find", default=None)
    sp.add_argument("--slot", type=int, default=None)
    sp.add_argument("--add", default=None)
    sp.add_argument("--remove", default=None, help="nazwa / 0xID / handle:0x…")
    sp.add_argument("--set-qty", default=None, help='np. "Crimson Flask=14"')
    sp.add_argument("--move", default=None, help="nazwa / 0xID / handle:0x…")
    sp.add_argument("--to", default=None, help="held albo storage (dla --move)")
    sp.add_argument("--set-upgrade", default=None, help='np. "Uchigatana=10"')
    sp.add_argument("--affinity", default=None, help='np. "Uchigatana=Blood"')
    sp.add_argument("--aow", default=None, help='np. "Uchigatana=Bloody Slash"')
    sp.add_argument("--handle", type=lambda s: int(s, 16), default=None)
    sp.add_argument("--qty", type=int, default=1)
    sp.add_argument("--upgrade", type=int, default=0)
    sp.add_argument("--storage", action="store_true")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_item)

    sp = sub.add_parser("inventory", help="podgląd ekwipunku")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--storage", action="store_true")
    sp.add_argument("--all", action="store_true", help="przy sobie + skrzynia")
    sp.add_argument("--equipped", action="store_true", help="pokaz to, co zalozone")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_inventory)

    sp = sub.add_parser("flags", help="flagi świata (get/set)")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--get", type=int, default=None)
    sp.add_argument("--set", default=None, help="ID:0/1")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_flags)

    sp = sub.add_parser("graces", help="łaski: lista / odblokowanie")
    add_save(sp)
    sp.add_argument("--list", action="store_true")
    sp.add_argument("--slot", type=int, default=None)
    sp.add_argument("--region", default=None)
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_graces)

    sp = sub.add_parser("swap", help="podmień miejscami dwie postacie")
    add_save(sp)
    sp.add_argument("--a", type=int, required=True)
    sp.add_argument("--b", type=int, required=True)
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_swap)

    sp = sub.add_parser("clear", help="wyczyść slot postaci")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_clear)

    sp = sub.add_parser("equipment", help="co postać ma na sobie")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_equipment)

    sp = sub.add_parser("equip", help="załóż item z ekwipunku")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--handle", type=lambda s: int(s, 16), default=None)
    sp.add_argument("--item", default=None)
    sp.add_argument("--at", type=int, default=None)
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_equip)

    sp = sub.add_parser("unequip", help="zdejmij gniazdo albo wszystko")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--at", type=int, default=None)
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_unequip)

    sp = sub.add_parser("spells", help="czary: podgląd / zapamiętaj / zwolnij")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--memorize", default=None)
    sp.add_argument("--forget", type=int, default=None)
    sp.add_argument("--clear", action="store_true")
    sp.add_argument("--at", type=int, default=None)
    sp.add_argument("--list", dest="catalog", action="store_true",
                    help="katalog czarów do wyboru (z filtrem i stanem: w ekwipunku / zapamiętany)")
    sp.add_argument("--filter", default=None, help="filtr katalogu (nazwa albo ID)")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_spells)

    sp = sub.add_parser("appearance", help="wygląd: gender / typ ciała / dar")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--gender", type=int, default=None, choices=(0, 1))
    sp.add_argument("--body", type=int, default=None, choices=(0, 1))
    sp.add_argument("--gift", type=int, default=None)
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_appearance)

    sp = sub.add_parser("teleport", help="przenieś postać (Limgrave/Roundtable/...)")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--to", default=None, choices=tuple(TELEPORT_LOCATIONS))
    sp.add_argument("--map", default=None, help='np. m60_36_42_00')
    sp.add_argument("--xyz", default=None, help='np. "-331,-22,-305.8"')
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_teleport)

    sp = sub.add_parser("world", help="nazwane flagi świata (bossowie, mapy, cookbooki…)")
    add_save(sp)
    sp.add_argument("--slot", type=int, default=None)
    sp.add_argument("--groups", action="store_true")
    sp.add_argument("--group", default=None)
    sp.add_argument("--filter", default=None)
    sp.add_argument("--set", default=None, help="fragment nazwy albo ID")
    sp.add_argument("--all", action="store_true", help="cała grupa")
    sp.add_argument("--state", type=int, default=None, choices=(0, 1))
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_world)

    sp = sub.add_parser("unlock", help="masowo nadaj kategorię itemów")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--what", required=True, choices=CATEGORIES)
    sp.add_argument("--location", default="storage", choices=("storage", "held"))
    sp.add_argument("--max", type=int, default=None)
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_unlock)

    sp = sub.add_parser("copy", help="kopiuj postać slot -> slot")
    add_save(sp)
    sp.add_argument("--from", dest="src", type=int, required=True)
    sp.add_argument("--to", dest="dst", type=int, required=True)
    sp.add_argument("--clear-source", action="store_true")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_copy)

    sp = sub.add_parser("steamid", help="patcher SteamID (np. dla save'ów z internetu)")
    add_save(sp)
    sp.add_argument("--set", required=True, help="nowy SteamID64 (17 cyfr)")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_steamid)

    sp = sub.add_parser("export", help="eksport postaci do JSON")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--out", required=True)
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("import", help="import postaci z JSON")
    add_save(sp)
    sp.add_argument("--to", type=int, required=True)
    sp.add_argument("--in", dest="file_in", required=True)
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("backups", help="kopie: lista / przywracanie / GOLD / przypinanie")
    add_save(sp)
    sp.add_argument("--restore", default=None, help="nazwa pliku kopii")
    sp.add_argument("--gold", action="store_true", help="zrób niekasowalną kopię GOLD (raz na plik)")
    sp.add_argument("--pin", default=None, help="przypnij kopię — rotacja jej nie skasuje")
    sp.add_argument("--unpin", default=None, help="odepnij kopię")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_backups)

    sp = sub.add_parser("watch", help="auto-kopiec: kopia przy starcie gry i co interwał")
    add_save(sp)
    sp.add_argument("--interval", type=int, default=None,
                    help="sekundy między kopiami (domyślnie z config: watch_interval)")
    sp.add_argument("--once", action="store_true", help="jeden przebieg kontrolny i wyjście")
    sp.set_defaults(func=cmd_watch)

    sp = sub.add_parser("risk", help="ryzyko online: dane niemożliwe + znacznik modyfikacji")
    add_save(sp)
    sp.add_argument("--slot", type=int, default=None, help="tylko jeden slot")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_risk)

    sp = sub.add_parser("stage", help="edytuj w kopii roboczej (zmiany oczekujące)")
    add_save(sp)
    sp.add_argument("rest", nargs=argparse.REMAINDER, help="komenda edycji i jej opcje")
    sp.set_defaults(func=cmd_stage)

    sp = sub.add_parser("pending", help="zmiany oczekujące: licznik + podgląd")
    add_save(sp)
    sp.add_argument("--diff", action="store_true", help="pokaż zmienione sekcje (bajt w bajt)")
    sp.add_argument("--undo", action="store_true", help="cofnij ostatnią zmianę oczekującą")
    sp.set_defaults(func=cmd_pending)

    sp = sub.add_parser("apply", help="zatwierdź zmiany oczekujące (1 backup + 1 zapis)")
    add_save(sp)
    sp.add_argument("--force", action="store_true",
                    help="nawet jeśli oryginał zmienił się od rozpoczęcia stagingu")
    sp.set_defaults(func=cmd_apply)

    sp = sub.add_parser("discard", help="odrzuć zmiany oczekujące (oryginał nietknięty)")
    add_save(sp)
    sp.set_defaults(func=cmd_discard)

    sp = sub.add_parser("log", help="historia operacji (dziennik edycji)")
    add_save(sp)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_log)

    sp = sub.add_parser("find", help="szukaj: itemy, flagi świata, łaski, lokacje")
    add_save(sp)
    sp.add_argument("query", help="fragment nazwy (np. uchi, godrick, map)")
    sp.add_argument("--limit", type=int, default=40)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_find)

    sp = sub.add_parser("gui", help="okno GUI (pywebview / WebView2)")
    add_save(sp)
    sp.add_argument("--selftest", action="store_true", help="otwórz, sprawdź most i przełącz język EN/PL, zamknij (~30 s)")
    sp.set_defaults(func=cmd_gui)

    sp = sub.add_parser("config", help="konfiguracja Rezura")
    sp.add_argument("--set", default=None, help="klucz=wartość")
    sp.set_defaults(func=cmd_config)

    sp = sub.add_parser("list-fixes", help="lista dostępnych napraw")
    sp.set_defaults(func=cmd_list_fixes)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"błąd: {e}")
        return 2
    except ValueError as e:
        print(f"błąd: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
