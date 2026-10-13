#!/usr/bin/env python3
"""
erlab · fix_torrent.py — naprawa buga Torrenta w save'ach Elden Ring (PC .sl2).

Bug: RideGameData (koń) ma hp == 0 i state == ACTIVE(13) jednocześnie.
Stan "active z zerowym HP" blokuje wczytanie postaci — gra wisi na ekranie
ładowania (infinite loading). Typowy efekt wyjścia z gry przez Alt+F4 / crasha
w momencie, gdy Torrent był aktywny.

Naprawa: state 13 (ACTIVE) -> 3 (DEAD). Minimalna, jednobajtowa zmiana danych,
potem przeliczenie MD5 slotu. Hash gracza (PlayerGameDataHash) tego nie obejmuje,
a ProfileSummary też nie — więc nic więcej nie trzeba ruszać.

Layout slotu (format v250-261, zweryfikowany na 3 realnych slotach):
  PGD (PlayerGameData) -> ... łańcuch offsetów ... -> unlocked_regions ->
  RideGameData { f32x3 coords, MapId, f32x4 angle, i32 hp, u32 state }

Usage:
  python fix_torrent.py SAVE.sl2                  # dry-run: raport, nic nie pisze
  python fix_torrent.py SAVE.sl2 --apply          # napraw (backup obok pliku)
  python fix_torrent.py SAVE.sl2 --apply --slot 2 # tylko wskazany slot
"""

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import time

SLOT_STRIDE = 0x280010
SLOT_BODY = 0x280000
PROFILE_BASE = 0x195E   # profile_summaries[0] w UserData10 (save 1.16-era)
PROFILE_SIZE = 0x24C

HORSE_STATE_OFF = 0x24  # w RideGameData: coords(12) + mapid(4) + angle(16) + hp(4)
HORSE_HP_OFF = 0x20
STATE_INACTIVE, STATE_DEAD, STATE_ACTIVE = 1, 3, 13


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def utf16(b, o, maxlen=24):
    try:
        return b[o : o + maxlen * 2].decode("utf-16-le", "ignore").split("\x00")[0]
    except Exception:
        return ""


def read_entries(data):
    out = []
    for i in range(12):
        off = 0x40 + i * 0x20
        _f, _u, size, _s2, dataoff, nameoff, _a, _b = struct.unpack_from("<IIIIIIII", data, off)
        out.append({"name": utf16(data, nameoff, 26), "size": size, "off": dataoff})
    return out


def read_roster(data, entries):
    ud10 = next(e for e in entries if e["name"] == "USER_DATA010")
    ud = data[ud10["off"] + 16 : ud10["off"] + 16 + 0x60000]
    out = []
    for i in range(10):
        blk = ud[PROFILE_BASE + i * PROFILE_SIZE : PROFILE_BASE + (i + 1) * PROFILE_SIZE]
        out.append((utf16(blk, 0, 17), u32(blk, 0x22)))
    return out


def find_stat_anchor(slot, level, name):
    """Zwraca offset pola Vigor, albo None. Walidacja: 8 statystyk 1..99,
    sum-79 == level, imię w UTF-16 na +0x60."""
    pat = struct.pack("<I", level)
    at = slot.find(pat)
    while at >= 0:
        v = at - 44
        if v >= 0x40:
            stats = [u32(slot, v + k * 4) for k in range(8)]
            if all(1 <= x <= 99 for x in stats) and sum(stats) - 79 == level:
                if not name or utf16(slot, v + 0x60) == name:
                    return v
        at = slot.find(pat, at + 1)
    return None


def find_horse(slot, v, version):
    """Przejście łańcuchem od kotwicy statystyk do RideGameData.
    Zwraca (horse_offset, hp, state) lub None."""
    o = (v - 0x34) + 0x1B0  # PGD koniec -> sp_effects
    o += 0xD0 + 0x58 + 0x1C + 0x58 + 0x58  # speffects, equip index, slots, ids, handles
    o += 4 + 0xA80 * 12 + 4 + 0x180 * 12 + 8  # inventory_held (stały rozmiar)
    o += 0x74 + 0x8C + 0x18  # spells, equipped items, gesture wheel
    nproj = u32(slot, o)
    if nproj > 256:
        return None
    o += 4 + nproj * 8  # acquired projectiles
    o += 0x9C + 0xC + 0x12F  # armaments, physics, face data
    o += 4 + 0x780 * 12 + 4 + 0x80 * 12 + 8  # storage box
    o += 0x100  # gesture game data
    nreg = u32(slot, o)
    if nreg > 1024:
        return None
    o += 4 + nreg * 4  # unlocked regions
    hp = i32(slot, o + HORSE_HP_OFF)
    state = u32(slot, o + HORSE_STATE_OFF)
    return o, hp, state


def game_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq eldenring.exe"],
            capture_output=True, text=True, timeout=20,
        ).stdout.lower()
        return "eldenring.exe" in out
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="Naprawa buga Torrenta (HP=0 + ACTIVE) w ER .sl2")
    ap.add_argument("save", help="ścieżka do ER0000.sl2")
    ap.add_argument("--apply", action="store_true", help="wykonaj naprawę (domyślnie dry-run)")
    ap.add_argument("--slot", type=int, default=None, help="tylko wskazany slot 0-9")
    ap.add_argument("--force", action="store_true", help="napraw nawet gdy gra działa (nie rób tego)")
    args = ap.parse_args()

    with open(args.save, "rb") as f:
        data = bytearray(f.read())
    if data[:4] != b"BND4":
        print("!! to nie jest jawny BND4 (.sl2 PC). PS4 / zaszyfrowany? — stop.")
        return 2

    entries = read_entries(bytes(data))
    roster = read_roster(bytes(data), entries)
    print(f"plik: {args.save}  ({len(data)} B)")

    # sloty = 10 pierwszych wpisów
    bugs = []
    for k in range(10):
        off = entries[k]["off"] + 16
        if off + SLOT_BODY > len(data):
            continue
        slot = data[off : off + SLOT_BODY]
        version = u32(slot, 0)
        if version == 0:
            continue
        name, lvl = roster[k]
        v = find_stat_anchor(slot, lvl, name)
        if v is None:
            print(f"  slot{k} '{name}': !! kotwica statystyk nie znaleziona (pomijam)")
            continue
        horse = find_horse(slot, v, version)
        if horse is None:
            print(f"  slot{k} '{name}': !! przelot do Torrenta nie doszedł (pomijam)")
            continue
        hoff, hp, state = horse
        sname = {1: "INACTIVE", 3: "DEAD", 13: "ACTIVE"}.get(state, f"?{state}")
        bug = hp == 0 and state == STATE_ACTIVE
        flag = "  <<< BUG (infinite loading)" if bug else ""
        print(f"  slot{k} '{name}' v{version}: Torrent hp={hp} state={sname}{flag}")
        if bug and (args.slot is None or args.slot == k):
            bugs.append((k, off, hoff))

    if not bugs:
        print("\nnic do naprawy — Torrent we wszystkich sprawdzonych slotach OK.")
        return 0

    if not args.apply:
        print(f"\nDRY-RUN: do naprawy {len(bugs)} slot(y). Uruchom z --apply, aby zapisać.")
        return 0

    if game_running() and not args.force:
        print("\n!! eldenring.exe działa — zamknij grę przed zapisem (albo --force).")
        return 3

    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = f"{args.save}.fixbak-{stamp}"
    shutil.copy2(args.save, bak)
    print(f"\nbackup: {bak}")

    for k, off, hoff in bugs:
        abs_state = off + hoff + HORSE_STATE_OFF
        abs_md5 = 0x300 + k * SLOT_STRIDE
        old = data[abs_state : abs_state + 4]
        if old != struct.pack("<I", STATE_ACTIVE):
            print(f"  slot{k}: stan zmienił się w międzyczasie ({old.hex()}) — pomijam")
            continue
        data[abs_state : abs_state + 4] = struct.pack("<I", STATE_DEAD)
        body = bytes(data[abs_md5 + 16 : abs_md5 + 16 + SLOT_BODY])
        data[abs_md5 : abs_md5 + 16] = hashlib.md5(body).digest()
        print(f"  slot{k}: state ACTIVE->DEAD @0x{abs_state:X}, MD5 przeliczony @0x{abs_md5:X}")

    tmp = args.save + ".tmp-erlab"
    with open(tmp, "wb") as f:
        f.write(bytes(data))
    os.replace(tmp, args.save)
    print("zapisane (atomic replace).")

    # weryfikacja po zapisie
    chk = open(args.save, "rb").read()
    ok = True
    for k, off, hoff in bugs:
        body = chk[0x300 + k * SLOT_STRIDE + 16 : 0x300 + k * SLOT_STRIDE + 16 + SLOT_BODY]
        md5_ok = hashlib.md5(body).digest() == chk[0x300 + k * SLOT_STRIDE : 0x300 + k * SLOT_STRIDE + 16]
        hp = i32(chk, off + hoff + HORSE_HP_OFF)
        state = u32(chk, off + hoff + HORSE_STATE_OFF)
        ok = ok and md5_ok and state == STATE_DEAD
        print(f"  verify slot{k}: md5={'OK' if md5_ok else 'BAD'} hp={hp} state={state}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
