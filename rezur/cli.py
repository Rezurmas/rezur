"""Rezur Saves Configurator — interfejs wiersza poleceń.

    python -m rezur info       [--save PLIK]
    python -m rezur doctor     [--save PLIK] [--json] [--expect-steamid N]
    python -m rezur fix        [--save PLIK] [--only id,id] [--apply]
    python -m rezur stats      [--save PLIK] --slot N [--set vigor=60,mind=40]
                               [--runes N] [--runes-memory N] [--name "X"] [--apply]
    python -m rezur item       [--save PLIK] (--find Q | --slot N --add ITEM
                               [--qty N] [--upgrade N] [--storage] [--apply])
    python -m rezur inventory  [--save PLIK] --slot N [--storage]
    python -m rezur flags      [--save PLIK] --slot N (--get ID | --set ID:0/1 [--apply])
    python -m rezur graces     [--save PLIK] [--list] | --slot N [--region R] [--apply]
    python -m rezur copy       [--save PLIK] --from N --to M [--clear-source] [--apply]
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
from .core import items_db
from .core.profiles import roster
from .core.savefile import SaveFile, default_save_path
from .core.slots import Slot
from .diag import run_diagnostics
from .ops.backups import list_backups, restore
from .ops.copy_slot import copy_character_file
from .ops.flags import graces as graces_data
from .ops.flags import get_flag as flag_get
from .ops.flags import set_flag as flag_set
from .ops.flags import unlock_graces
from .ops.items import add_item, list_inventory
from .ops.stats import STAT_NAMES, rename, set_runes, set_stats
from .ops.steamid import change_steam_id
from .ops.transfer import export_character, import_character
from .report import jsonout as J
from .report import text as R


def _load(args):
    path = args.save or str(default_save_path())
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


def cmd_info(args):
    sf = _load(args)
    print(R.fmt_container(sf))
    print()
    print(R.fmt_characters(sf))
    return 0


def cmd_doctor(args):
    sf = _load(args)
    findings = run_diagnostics(sf, expect_steamid=args.expect_steamid)
    if args.json:
        print(json.dumps(J.save_to_dict(sf, findings), indent=2, ensure_ascii=False))
    else:
        print(R.fmt_doctor(sf, findings))
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


def cmd_item(args):
    if args.find:
        res = items_db.search(args.find)
        print(f"trafienia: {len(res)}")
        for fid, name, cat in res:
            print(f"  0x{fid:08X}  {name:<44s} [{cat}]")
        return 0
    if args.add is None or args.slot is None:
        print("użyj: --find Q  albo  --slot N --add ITEM")
        return 2
    sf = _load(args)
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


def cmd_inventory(args):
    sf = _load(args)
    items = list_inventory(sf, args.slot, "storage" if args.storage else "held")
    loc = "skrzynia" if args.storage else "przy sobie"
    print(f"slot{args.slot} — ekwipunek ({loc}): {len(items)} pozycji")
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
    path = args.save or str(default_save_path())
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
    path = args.save or str(default_save_path())
    sf = SaveFile(path)
    new = int(args.set)
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


def cmd_export(args):
    sf = _load(args)
    rep = export_character(sf, args.slot, args.out)
    for k, v in rep.items():
        print(f"  {k}: {v}")
    return 0


def cmd_import(args):
    path = args.save or str(default_save_path())
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
    path = args.save or str(default_save_path())
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
    for b in baks[:40]:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(b["mtime"]))
        print(f"  {when}  {b['name']}  ({b['size'] / 1e6:.1f} MB)")
    if not baks:
        print("  (brak — powstają przy każdym zapisie)")
    return 0


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

    sp = sub.add_parser("item", help="itemy: szukaj / dodaj")
    add_save(sp)
    sp.add_argument("--find", default=None)
    sp.add_argument("--slot", type=int, default=None)
    sp.add_argument("--add", default=None)
    sp.add_argument("--qty", type=int, default=1)
    sp.add_argument("--upgrade", type=int, default=0)
    sp.add_argument("--storage", action="store_true")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_item)

    sp = sub.add_parser("inventory", help="podgląd ekwipunku")
    add_save(sp)
    sp.add_argument("--slot", type=int, required=True)
    sp.add_argument("--storage", action="store_true")
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

    sp = sub.add_parser("backups", help="kopie: lista / przywracanie")
    add_save(sp)
    sp.add_argument("--restore", default=None, help="nazwa pliku kopii")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_backups)

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
