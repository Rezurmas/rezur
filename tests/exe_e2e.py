"""Koncowy test gotowego exe: wszystkie komendy CLI, zapisy na KOPIACH, most GUI.

Uruchamia `dist/rezur.exe` jako podproces w izolowanym `%APPDATA%` (config/staging nie ruszają
prawdziwego profilu) i na kopiach save'ów — żywy zapis jest tylko czytany.

    python tests/exe_e2e.py [--exe dist/rezur.exe] [--live "%APPDATA%\\EldenRing"]
                            [--demo C:/ER-Rezur-Demo/ER0000.sl2] [--gui]

Bez `--gui` pomija uruchomienie okna (selftest GUI trwa ~1 min). Kod wyjścia != 0, gdy cokolwiek padło.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXE = ROOT / "dist" / "rezur.exe"
BACKUPS = ROOT / "backups"

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tail(out: str, n: int = 120) -> str:
    lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
    return " | ".join(lines[-2:])[:n]


class Exe:
    def __init__(self, path: Path, appdata: Path):
        self.path = path
        self.env = dict(os.environ)
        self.env["APPDATA"] = str(appdata)
        self.env["PYTHONIOENCODING"] = "utf-8"

    def run(self, *args: str, timeout: int = 240) -> tuple[int, str]:
        p = subprocess.run(
            [str(self.path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.env,
            timeout=timeout,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    def check(self, name: str, args: list[str], want: str | None = None,
              timeout: int = 240) -> str:
        """want = fragment, który MUSI pojawić się w wyjściu (obok exit=0)."""
        code, out = self.run(*args, timeout=timeout)
        ok = code == 0 and (want is None or want.lower() in out.lower())
        detail = "" if ok else f"exit={code} brak={want!r} | {tail(out)}"
        record(name, ok, detail)
        return out

    def write_op(self, name: str, args: list[str], timeout: int = 240) -> str:
        """Zapis: exit=0 + komunikat o backupie (invariant bezpieczeństwa)."""
        return self.check(name, args, want="backup", timeout=timeout)

    def check_save_ok(self, name: str, save: Path) -> None:
        code, out = self.run("info", "--save", str(save))
        ok = code == 0 and "12/12" in out
        record(name, ok, "kontener 12/12" if ok else tail(out))

    def check_doctor(self, name: str, save: Path) -> None:
        """doctor: 0 = czysto, 1 = ostrzeżenia (np. postać ze starszego patcha), 2 = błąd."""
        code, out = self.run("doctor", "--save", str(save))
        warns = sum(1 for ln in out.splitlines() if ln.strip().startswith(("[warning]", "[warn]"))
                    or "[warning]" in ln)
        ok = code in (0, 1) and bool(out.strip())
        record(name, ok, f"exit={code}, ostrzeżeń: {warns}" if ok else f"exit={code} | {tail(out)}")


def find_saves(live_dir: Path, demo: Path | None) -> list[Path]:
    out: list[Path] = []
    if live_dir.is_dir():
        hits = sorted(live_dir.glob("*/ER0000.sl2"), key=lambda p: p.stat().st_mtime, reverse=True)
        if hits:
            out.append(hits[0])
    if demo and demo.is_file():
        out.append(demo)
    for pat in ("ER0000_backup_*.sl2", "ER0000_FIXED_torrent_*.sl2"):
        out += sorted(BACKUPS.glob(pat))[:2]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=str(DEFAULT_EXE))
    ap.add_argument("--live", default=os.path.expandvars(r"%APPDATA%\EldenRing"))
    ap.add_argument("--demo", default=r"C:\ER-Rezur-Demo\ER0000.sl2")
    ap.add_argument("--gui", action="store_true", help="dodaj selftest okna (~1 min)")
    a = ap.parse_args()

    exe_path = Path(a.exe)
    if not exe_path.is_file():
        print(f"brak exe: {exe_path}")
        return 2

    saves = find_saves(Path(a.live), Path(a.demo) if a.demo else None)
    if not saves:
        print("nie znalazłem żadnego save'a do testu")
        return 2

    sandbox = Path(tempfile.mkdtemp(prefix="rezur-e2e-"))
    work = sandbox / "work"
    work.mkdir()
    appdata = sandbox / "appdata"
    appdata.mkdir()
    exe = Exe(exe_path, appdata)

    print(f"exe:  {exe_path}  ({exe_path.stat().st_size / 1e6:.1f} MB)")
    print(f"savy: {len(saves)} → " + ", ".join(f"{s.name} [{s.parent.name}]" for s in saves))
    print(f"sandbox: {sandbox}\n")

    # --- 1. interfejs i dane wbudowane w exe ---------------------------------------------
    code, out = exe.run("--help")
    subs = ["info", "doctor", "fix", "stats", "item", "inventory", "equipment", "spells", "world",
            "unlock", "flags", "graces", "copy", "swap", "clear", "steamid", "export", "import",
            "backups", "watch", "risk", "stage", "pending", "apply", "discard", "log", "find",
            "gui", "config", "list-fixes"]
    miss = [s for s in subs if s not in out]
    record("--help: wszystkie podkomendy obecne", code == 0 and not miss,
           f"brakuje: {miss}" if miss else f"{len(subs)} komend")
    exe.check("list-fixes: naprawy wbudowane", ["list-fixes"], want="torrent")
    exe.check("world --groups (baza flag)", ["world", "--groups"], want="boss_defeat")
    exe.check("spells --list (katalog czarów, filtr)",
              ["spells", "--save", str(saves[0]), "--slot", "0", "--list", "--filter", "heal"],
              want="Heal")
    exe.check("item --find (baza itemów)", ["item", "--find", "uchigatana"], want="Uchigatana")
    exe.check("find (silnik szukania)", ["find", "uchi"], want="Uchigatana")
    exe.check("graces --list (łaski)", ["graces", "--list"], want="Limgrave")
    exe.check("config (izolowany APPDATA)", ["config"])

    # --- 2. każdy save: tylko odczyt ------------------------------------------------------
    for s in saves:
        tag = s.parent.name
        before = md5(s)
        exe.check(f"info [{tag}]", ["info", "--save", str(s)], want="KONTENER: 12/12")
        exe.check_doctor(f"doctor [{tag}]", s)
        exe.check(f"risk [{tag}]", ["risk", "--save", str(s)])
        exe.check(f"backups [{tag}]", ["backups", "--save", str(s)])
        exe.check(f"log [{tag}]", ["log", "--save", str(s)])
        exe.check(f"inventory --slot 0 [{tag}]", ["inventory", "--save", str(s), "--slot", "0"])
        exe.check(f"equipment --slot 0 [{tag}]", ["equipment", "--save", str(s), "--slot", "0"])
        exe.check(f"stats (dry-run) [{tag}]", ["stats", "--save", str(s), "--slot", "0", "--set", "vigor=60"])
        record(f"odczyt nie zmienił pliku [{tag}]", md5(s) == before, "MD5 bez zmian")

    # --- 3. zapisy: wyłącznie na kopii ----------------------------------------------------
    src = saves[0]
    copy = work / "ER0000.sl2"
    shutil.copy2(src, copy)
    copy_before = md5(copy)
    print(f"\nzapisy na kopii: {copy}\n")

    exe.check("backups --gold (kopia GOLD)", ["backups", "--save", str(copy), "--gold"], want="gold")
    code, _out = exe.run("stats", "--save", str(copy), "--slot", "0", "--set", "vigor=61")
    record("stats bez --apply = tylko podgląd", code == 0 and md5(copy) == copy_before,
           "MD5 bez zmian" if md5(copy) == copy_before else "PLIK ZMIENIONY!")

    exe.write_op("stats --set --apply", ["stats", "--save", str(copy), "--slot", "0",
                                         "--set", "vigor=61", "--apply"])
    record("apply zmienił plik", md5(copy) != copy_before, "MD5 inny po zapisie")
    record("apply zostawił backup", bool(list(work.glob("*bak*"))), "backup w katalogu kopii")
    exe.check_save_ok("kontener po apply", copy)
    exe.check("log: historia zmian", ["log", "--save", str(copy)])

    # staging: stage → pending → apply / discard
    exe.write_op("stage: zmiana do brudnopisu", ["stage", "stats", "--save", str(copy),
                                                 "--slot", "0", "--set", "mind=41"])
    exe.check("pending --diff: widać sekcje", ["pending", "--save", str(copy), "--diff"],
              want="USER_DATA")
    exe.check("pending: widać operację", ["pending", "--save", str(copy)], want="mind")
    before_apply = md5(copy)
    exe.write_op("apply: zatwierdzenie brudnopisu", ["apply", "--save", str(copy)])
    exe.check("pending po apply: pusto", ["pending", "--save", str(copy)])
    record("apply z brudnopisu zmienił plik", md5(copy) != before_apply, "MD5 inny")
    exe.check_save_ok("kontener po apply z brudnopisu", copy)

    exe.write_op("stage #2 (do odrzucenia)", ["stage", "stats", "--save", str(copy),
                                              "--slot", "0", "--set", "endurance=42"])
    before_discard = md5(copy)
    code, _ = exe.run("discard", "--save", str(copy))
    record("discard: porzucenie zmian", code == 0, f"exit={code}")
    exe.check("pending po discard: pusto", ["pending", "--save", str(copy)])
    record("discard nie tknął pliku", md5(copy) == before_discard, "MD5 bez zmian")

    # itemy / ekwipunek / czary / świat / łaski / teleport / kopie / transfer
    exe.write_op("item --add --upgrade --apply", ["item", "--save", str(copy), "--slot", "0",
                                                  "--add", "Uchigatana", "--upgrade", "3", "--apply"])
    exe.check("inventory widzi dodany item", ["inventory", "--save", str(copy), "--slot", "0"],
              want="Uchigatana")
    exe.write_op("item --add (Larval Tear)", ["item", "--save", str(copy), "--slot", "0",
                                              "--add", "Larval Tear", "--apply"])
    exe.write_op("item --set-qty --apply", ["item", "--save", str(copy), "--slot", "0",
                                            "--set-qty", "Larval Tear=12", "--apply"])
    exe.write_op("item --set-upgrade --apply", ["item", "--save", str(copy), "--slot", "0",
                                                "--set-upgrade", "Uchigatana=10", "--apply"])
    exe.write_op("item --aow --apply", ["item", "--save", str(copy), "--slot", "0",
                                        "--aow", "Uchigatana=Bloody Slash", "--apply"])
    exe.write_op("item --affinity --apply", ["item", "--save", str(copy), "--slot", "0",
                                             "--affinity", "Uchigatana=Blood", "--apply"])
    # equip: broń, która JEST w gaitem postaci (świeżo dodany item nie ma tam wpisu — to normalne)
    eq = exe.check("equipment --slot 0 (odczyt)", ["equipment", "--save", str(copy), "--slot", "0"])
    name, at = None, 0
    for ln in eq.splitlines():
        m = re.search(r"\[\s*(\d+)\]\s+weapon\s+0x[0-9A-Fa-f]+\s+(.+?)\s*$", ln)
        if m and "puste" not in ln:
            at, name = int(m.group(1)), re.sub(r"\s*\+\d+$", "", m.group(2)).strip()
            break
    if name:
        exe.write_op(f"unequip --at {at} --apply", ["unequip", "--save", str(copy), "--slot", "0",
                                                    "--at", str(at), "--apply"])
        exe.write_op(f"equip '{name}' --at 0 --apply", ["equip", "--save", str(copy), "--slot", "0",
                                                        "--item", name, "--at", "0", "--apply"])
        exe.check(f"equipment pokazuje '{name}' na slocie 0", ["equipment", "--save", str(copy),
                                                               "--slot", "0"], want=name.split()[0])
    else:
        record("equip/unequip (broń w gaitem)", False, "nie znalazłem broni w wyposażeniu")
    exe.write_op("spells --memorize --apply", ["spells", "--save", str(copy), "--slot", "0",
                                               "--memorize", "Heal", "--apply"])
    exe.write_op("world --set (boss) --apply", ["world", "--save", str(copy), "--slot", "0",
                                                "--group", "boss_defeat", "--set", "Godrick",
                                                "--state", "1", "--apply"])
    exe.check("flags --get (odczyt flagi)", ["flags", "--save", str(copy), "--slot", "0",
                                             "--get", "600003"])
    exe.write_op("unlock --what maps --apply", ["unlock", "--save", str(copy), "--slot", "0",
                                                "--what", "maps", "--apply"], timeout=300)
    exe.write_op("graces --region --apply", ["graces", "--save", str(copy), "--slot", "0",
                                             "--region", "Limgrave", "--apply"])
    exe.write_op("teleport --to roundtable --apply", ["teleport", "--save", str(copy), "--slot", "0",
                                                      "--to", "roundtable", "--apply"])
    exe.check("appearance (odczyt)", ["appearance", "--save", str(copy), "--slot", "0"])
    exe.check("risk po edycjach", ["risk", "--save", str(copy), "--slot", "0"])
    exe.check("watch --once", ["watch", "--save", str(copy), "--once"])
    exe.check("backups po edycjach (GOLD widoczny)", ["backups", "--save", str(copy)], want="gold")
    exe.check_save_ok("kontener po wszystkich edycjach", copy)

    js = work / "char0.json"
    exe.check("export postaci do JSON", ["export", "--save", str(copy), "--slot", "0", "--out", str(js)],
              want="char0.json")
    record("plik JSON powstał", js.is_file() and js.stat().st_size > 200,
           f"{js.stat().st_size} B" if js.is_file() else "brak pliku")
    exe.write_op("import do slotu 3", ["import", "--save", str(copy), "--to", "3", "--in", str(js), "--apply"])
    exe.write_op("copy slot 0 → 4", ["copy", "--save", str(copy), "--from", "0", "--to", "4", "--apply"])
    exe.write_op("swap 1 ↔ 2", ["swap", "--save", str(copy), "--a", "1", "--b", "2", "--apply"])
    exe.check("info po swapie: 12/12", ["info", "--save", str(copy)], want="KONTENER: 12/12")
    exe.write_op("clear slot 4 (niepusty)", ["clear", "--save", str(copy), "--slot", "4", "--apply"])
    exe.check_save_ok("kontener po transferach", copy)

    # fix na fixture z bugiem torrenta
    tor = sorted(BACKUPS.glob("ER0000_backup_*.sl2"))
    if tor:
        tcopy = work / "ER0000_torrent.sl2"
        shutil.copy2(tor[0], tcopy)
        exe.check("fix --only torrent (dry-run)", ["fix", "--save", str(tcopy), "--only", "torrent"],
                  want="torrent")
        exe.write_op("fix --only torrent --apply", ["fix", "--save", str(tcopy), "--only", "torrent", "--apply"])
        exe.check_save_ok("kontener po fixie torrenta", tcopy)

    # torn write: ucięty plik musi zostać odrzucony, nie „naprawiony”
    torn = work / "ER0000_torn.sl2"
    data = copy.read_bytes()
    torn.write_bytes(data[: int(len(data) * 0.6)])
    code, out = exe.run("info", "--save", str(torn))
    record("ucięty save odrzucony z komunikatem",
           code != 0 and any(w in out.lower() for w in ("urwan", "ucię", "uszkodz")), tail(out))

    # --- 4. GUI (most + panele) ----------------------------------------------------------
    if a.gui:
        print("\nGUI: selftest okna...")
        code, out = exe.run("gui", "--selftest", "--save", str(copy), timeout=600)
        want = ["booted=True", "panels=13", "bridge_methods=34", "live-search INVENTORY",
                "SPELLS list", "switch→pl: pill=ok", "switch→en: pill=ok", "bridge-alive"]
        miss = [w for w in want if w not in out]
        record("gui --selftest (okno, most, panele, EN/PL)", code == 0 and not miss,
               f"exit={code}" + (f" brak: {miss}" if miss else ""))
        for line in out.splitlines():
            if line.startswith("[selftest]"):
                print("      " + line)

    # --- podsumowanie --------------------------------------------------------------------
    ok = sum(1 for _n, o, _d in results if o)
    fail = len(results) - ok
    print(f"\n{'=' * 72}\nE2E EXE: {ok}/{len(results)} PASS, {fail} FAIL")
    if fail:
        print("\npalone:")
        for n, o, d in results:
            if not o:
                print(f"  - {n}: {d}")
    shutil.rmtree(sandbox, ignore_errors=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
