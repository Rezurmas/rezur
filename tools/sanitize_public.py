"""Przygotowanie repo do publikacji: usuwa dane osobowe ze śledzonych plików.

Podmienia: prawdziwy SteamID64 i ścieżki z nazwą użytkownika na wersje generyczne.
Uruchomienie: python tools/sanitize_public.py [--check]
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SUBS = [
    ("76561199197611190", "76561198000000001"),
    ("76561199197611189", "76561198000000000"),
    (r"C:\Users\Dawid\Desktop\ER-Save-Lab", r"%USERPROFILE%\Desktop\ER-Save-Lab"),
    (r"C:\\Users\\Dawid\\AppData\\Roaming", r"C:\\Users\\<user>\\AppData\\Roaming"),
    (r"C:\Users\Dawid\AppData\Roaming", r"C:\Users\<user>\AppData\Roaming"),
    ("Dawid's", "user's"),
]

# pliki, których nie ruszamy (narzędzie logowania pisze nazwy zmiennych, nie dane)
SKIP = {"tools/gh_login.sh"}


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [Path(p) for p in out.stdout.splitlines() if p]


def main():
    check = "--check" in sys.argv
    hits = []
    changed = []
    for rel in tracked():
        if rel.as_posix() in SKIP:
            continue
        p = ROOT / rel
        try:
            txt = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = txt
        for a, b in SUBS:
            new = new.replace(a, b)
        if new != txt:
            hits.append(rel.as_posix())
            if not check:
                p.write_text(new, encoding="utf-8")
                changed.append(rel.as_posix())
        # kontrola końcowa: żadnych resztek
        left = re.findall(r"7656119919761118\d|Dawid", new)
        if left:
            print(f"  ! zostało {set(left)} w {rel}")

    if check:
        print("do poprawy:", hits or "brak ✓")
        return 0
    print("poprawione:", changed or "brak zmian")
    return 0


if __name__ == "__main__":
    sys.exit(main())
