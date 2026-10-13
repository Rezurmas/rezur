"""Rezur Saves Configurator — interfejs wiersza poleceń.

    python -m rezur info     [--save PLIK]     # postacie + kontener
    python -m rezur doctor   [--save PLIK]     # diagnostyka (czyta, nie pisze)
    python -m rezur fix      [--save PLIK] [--only id,id] [--apply]
    python -m rezur copy     [--save PLIK] --from N --to M [--apply] [--clear-source]
    python -m rezur steamid  [--save PLIK] --set 17-CYFROWY-ID [--apply]
    python -m rezur list-fixes
"""

import argparse
import json
import sys

from . import __product__, __version__
from . import fixes as F
from .core.savefile import SaveFile, default_save_path
from .diag import run_diagnostics
from .ops.copy_slot import copy_character_file
from .ops.steamid import change_steam_id
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


def _guard_game(path=""):
    """Nie pozwól zapisywać do ŻYWEGO save'a, gdy gra działa (nadpisze plik w locie).
    Pliki spoza folderu EldenRing (kopie robocze) przepuszczamy."""
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
    findings = run_diagnostics(sf)
    errs = sum(1 for f in findings if f.level == "error")
    warns = sum(1 for f in findings if f.level == "warning")
    print(f"po naprawie: {errs} błędów, {warns} ostrzeżeń")
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

    sp = sub.add_parser("copy", help="kopiuj postać slot -> slot")
    add_save(sp)
    sp.add_argument("--from", dest="src", type=int, required=True)
    sp.add_argument("--to", dest="dst", type=int, required=True)
    sp.add_argument("--clear-source", action="store_true")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_copy)

    sp = sub.add_parser("steamid", help="patcher SteamID (savvy z sieci)")
    add_save(sp)
    sp.add_argument("--set", required=True, help="nowy SteamID64 (17 cyfr)")
    sp.add_argument("--apply", action="store_true")
    sp.set_defaults(func=cmd_steamid)

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
