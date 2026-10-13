"""Smoke CLI — przebieg WSZYSTKICH komend Rezura na tymczasowej kopii save'a.

    python tests/smoke_cli.py

Kopiuje fixture do katalogu tymczasowego, wykonuje ~85 wywołań
`python -m rezur ...` (głównie dry-run, część zapisów --apply na kopii)
i raportuje PASS/FAIL. Exit 0 = każda komenda zadziałała bez wyjątku.

Uwaga o argv: `--save` jest opcją PODKOMENDY, więc zawsze:
    rezur <komenda> [--save PLIK] [opcje...]
"""

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXED = sorted(glob.glob(str(ROOT / "backups" / "ER0000_FIXED_torrent_*.sl2")))[0]

SUBS = (
    "info", "doctor", "fix", "stats", "item", "inventory", "equipment", "equip", "unequip",
    "spells", "appearance", "teleport", "world", "unlock", "flags", "graces", "copy", "swap",
    "clear", "steamid", "export", "import", "backups", "watch", "risk",
    "stage", "pending", "apply", "discard", "log", "find", "gui", "config", "list-fixes",
)


def build(P, out_json, ash, region):
    cmds = []  # (label, argv, allowed_rcs, capture)

    def raw(label, argv, rcs=(0,), capture=None):
        cmds.append((label, argv, set(rcs), capture))

    def add(sub, *rest, rcs=(0,)):
        raw((sub + " " + " ".join(rest)).strip(), [sub, "--save", P, *rest], rcs)

    raw("help", ["--help"])
    for s in SUBS:
        raw(f"help {s}", [s, "--help"])

    add("info")
    add("doctor", rcs=(0, 1))
    add("fix")
    add("fix", "--only", "torrent")
    raw("list-fixes", ["list-fixes"])
    raw("config", ["config"])
    raw("world --groups", ["world", "--groups"])

    # --- stats
    add("stats", "--slot", "2", "--set", "vigor=60")
    add("stats", "--slot", "2", "--set", "vigor=60", "--name", "smoke", "--runes", "1234", "--apply")
    add("stats", "--slot", "2", "--set", "vigor=61")

    # --- item: dobra (goods)
    add("item", "--slot", "2", "--add", "Larval Tear", "--qty", "3", "--apply")
    add("item", "--slot", "2", "--set-qty", "Larval Tear=5", "--apply")
    add("item", "--slot", "2", "--move", "Larval Tear", "--to", "storage", "--apply")
    add("item", "--slot", "2", "--remove", "Larval Tear", "--apply")

    # --- item: broń (kolejne kroki na uchwycie złapanym z outputu)
    raw("item --add Uchigatana --apply",
        ["item", "--save", P, "--slot", "2", "--add", "Uchigatana", "--apply"], capture="h")
    add("item", "--slot", "2", "--find", "uchi")
    add("item", "--slot", "2", "--set-upgrade", "x=8", "--handle", "{H}")
    add("item", "--slot", "2", "--affinity", "x=Blood", "--handle", "{H}")
    add("item", "--slot", "2", "--aow", "x=" + ash, "--handle", "{H}")
    add("equipment", "--slot", "2")
    add("equip", "--slot", "2", "--handle", "{H}", "--at", "0", "--apply")
    add("unequip", "--slot", "2", "--at", "0")
    add("unequip", "--slot", "2", "--at", "0", "--apply")
    add("item", "--slot", "2", "--remove", "x", "--handle", "{H}", "--apply")

    # --- inventory / EQ
    add("inventory", "--slot", "2")
    add("inventory", "--slot", "2", "--storage")
    add("inventory", "--slot", "2", "--all")
    add("inventory", "--slot", "2", "--equipped")
    add("inventory", "--slot", "2", "--json")
    add("equipment", "--slot", "2", "--json")

    # --- spells / appearance / teleport
    add("spells", "--slot", "0")
    add("spells", "--slot", "0", "--json")
    add("spells", "--slot", "0", "--list")
    add("spells", "--slot", "0", "--list", "--filter", "heal")
    add("spells", "--slot", "0", "--list", "--filter", "heal", "--json")
    add("spells", "--slot", "0", "--memorize", "Scholar's Armament")
    add("spells", "--slot", "0", "--memorize", "Scholar's Armament", "--apply")
    add("spells", "--slot", "0", "--clear", "--apply")
    add("appearance", "--slot", "2")
    add("appearance", "--slot", "2", "--gender", "1")
    add("appearance", "--slot", "2", "--body", "1", "--apply")
    add("teleport", "--slot", "2")
    add("teleport", "--slot", "2", "--to", "roundtable")
    add("teleport", "--slot", "2", "--to", "roundtable", "--apply")
    add("teleport", "--slot", "2", "--map", "m60_36_42_00", "--xyz", "-10,-10,-10", "--apply")
    add("teleport", "--slot", "2")

    # --- world / unlock / flags / graces
    add("world", "--slot", "2", "--group", "boss_defeat")
    add("world", "--slot", "2", "--group", "boss_defeat", "--filter", "Godrick")
    add("world", "--slot", "2", "--group", "boss_defeat", "--filter", "Godrick", "--json")
    add("world", "--slot", "2", "--group", "boss_defeat", "--set", "9100")
    add("world", "--slot", "2", "--group", "boss_defeat", "--set", "9100", "--state", "0", "--apply")
    add("world", "--slot", "2", "--group", "whetblade", "--all", "--state", "1", "--apply")
    add("unlock", "--slot", "2", "--what", "whetblades")
    add("unlock", "--slot", "2", "--what", "whetblades", "--apply")
    add("unlock", "--slot", "2", "--what", "tears", "--max", "5", "--apply")
    add("flags", "--slot", "2", "--get", "600003")
    add("flags", "--slot", "2", "--set", "600003:1")
    add("flags", "--slot", "2", "--set", "600003:1", "--apply")
    add("graces", "--list")
    add("graces", "--slot", "2", "--region", region)
    add("graces", "--slot", "2", "--region", region, "--apply")

    # --- sloty / steamid / transfer / backupy
    add("copy", "--from", "2", "--to", "3")
    add("copy", "--from", "2", "--to", "3", "--apply")
    add("swap", "--a", "0", "--b", "1")
    add("swap", "--a", "0", "--b", "1", "--apply")
    add("clear", "--slot", "3")
    add("clear", "--slot", "3", "--apply")
    add("steamid", "--set", "76561198000000001")
    add("steamid", "--set", "76561198000000001", "--apply")
    add("steamid", "--set", "76561198000000000", "--apply")
    add("export", "--slot", "0", "--out", out_json)
    add("import", "--to", "4", "--in", out_json)
    add("import", "--to", "4", "--in", out_json, "--apply")
    add("backups")
    add("backups", "--gold")
    add("backups")
    add("backups", "--pin", "nie-ma-takiej-kopii.sl2", rcs=(2,))
    add("backups", "--unpin", "nie-ma-takiej-kopii.sl2", rcs=(2,))
    add("watch", "--once")
    add("risk")
    add("risk", "--json")
    add("risk", "--slot", "2")

    # --- staging: zmiany oczekujące
    add("pending")
    add("log")
    raw("stage stats --set vigor=62",
        ["stage", "--save", P, "stats", "--slot", "2", "--set", "vigor=62"])
    add("pending")
    add("pending", "--diff")
    add("apply")
    add("log")
    raw("stage stats --set vigor=63",
        ["stage", "--save", P, "stats", "--slot", "2", "--set", "vigor=63"])
    add("pending", "--undo")
    add("pending")
    add("discard")
    add("pending")
    add("find", "uchi")
    add("find", "godrick")
    add("find", "map", "--json")

    add("backups", "--restore", "nie-ma-takiej-kopii", rcs=(2,))

    # --- finał
    add("doctor", rcs=(0, 1))
    add("info")
    return cmds


def main():
    td = tempfile.mkdtemp(prefix="rezur-smoke-")
    sp = Path(td) / "smoke.sl2"
    shutil.copy2(FIXED, sp)
    P = str(sp)
    out_json = str(Path(td) / "char.json")

    # izolacja: własny %APPDATA% (config + staging) — smoke nie rusza ustawień użytkownika
    os.environ["APPDATA"] = str(Path(td) / "appdata")
    Path(os.environ["APPDATA"]).mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(ROOT))
    from rezur.core import items_db
    from rezur.ops.flags import graces

    ash = next(f"0x{k:08X}" for k in items_db._load()["ashes"])
    region = next(iter(graces()))
    cmds = build(P, out_json, ash, region)

    handle = None
    fails = []
    npass = 0
    for label, argv, rcs, capture in cmds:
        real = [a.replace("{H}", f"0x{handle:X}" if handle else "0x0") for a in argv]
        r = subprocess.run(
            [sys.executable, "-m", "rezur", *real],
            cwd=str(ROOT), capture_output=True, text=True, timeout=180,
        )
        outp = (r.stdout or "") + (r.stderr or "")
        ok = r.returncode in rcs and "Traceback" not in outp
        if capture == "h" and ok:
            m = re.search(r"handle:\s*(\d+)", outp)
            if m:
                handle = int(m.group(1))
            else:
                ok = False
                outp += "\n[smoke] nie złapałem handle z outputu"
        if ok:
            npass += 1
            print(f"PASS  {label}")
        else:
            fails.append((label, r.returncode, outp[-800:]))
            print(f"FAIL  {label}  (rc={r.returncode}, dozwolone={sorted(rcs)})")

    print(f"\n{npass}/{len(cmds)} PASS")
    for label, rc, tail in fails:
        print(f"\n=== FAIL: {label} (rc={rc}) ===\n{tail}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
