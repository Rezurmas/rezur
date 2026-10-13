#!/usr/bin/env python3
"""
erlab · copy_slot.py — kopiowanie postaci między slotami w ER .sl2 (PC).

Kopiuje komplet:
  * dane postaci    — 0x280000 B slotu źródłowego (z naprawioną annesee: stan Torrenta DEAD),
  * profil na ekranie wyboru — wpis 0x24C w USER_DATA_10 (imię, lvl, czas gry, runy, twarz, ekwipunek),
i przelicza:
  * MD5 slotu docelowego,
  * MD5 USER_DATA_10 (bo zmienił się profil).

--clear-source dodatkowo zeruje slot źródłowy + jego profil (czysty "delete"),
co daje efekt przeniesienia postaci na nowy slot.

Usage:
  python copy_slot.py SAVE.sl2 --from 2 --to 3                          # dry-run
  python copy_slot.py SAVE.sl2 --from 2 --to 3 --apply                  # kopia
  python copy_slot.py SAVE.sl2 --from 2 --to 3 --apply --clear-source   # przeniesienie
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
PROFILE_BASE = 0x195E   # profile_summaries[0] w USER_DATA_10 (save 1.16-era)
PROFILE_SIZE = 0x24C
EMPTY_MD5 = bytes.fromhex("8354dcaa18a1ecb52d0895bf00888c44")


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


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


def slot_info(data, k, entries):
    body = entries[k]["off"] + 16
    version = u32(data, body)
    return {"body": body, "md5": entries[k]["off"], "version": version}


def profile_read(data, entries, k):
    ud = entries[10]["off"] + 16
    base = ud + PROFILE_BASE + k * PROFILE_SIZE
    blk = data[base : base + PROFILE_SIZE]
    return {
        "base": base,
        "name": utf16(blk, 0),
        "level": u32(blk, 0x22),
        "seconds": u32(blk, 0x26),
        "runes_memory": u32(blk, 0x2A),
    }


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
    ap = argparse.ArgumentParser(description="Kopiowanie postaci między slotami w ER .sl2")
    ap.add_argument("save")
    ap.add_argument("--from", dest="src", type=int, required=True, help="slot źródłowy 0-9")
    ap.add_argument("--to", dest="dst", type=int, required=True, help="slot docelowy 0-9")
    ap.add_argument("--apply", action="store_true", help="wykonaj (domyślnie dry-run)")
    ap.add_argument("--clear-source", action="store_true", help="wyczyść slot źródłowy po kopii")
    ap.add_argument("--force", action="store_true", help="pomiń kontrolę 'gra działa' (tylko testy na kopiach!)")
    args = ap.parse_args()

    if not (0 <= args.src <= 9 and 0 <= args.dst <= 9) or args.src == args.dst:
        print("!! złe sloty (0-9, różne).")
        return 2

    data = bytearray(open(args.save, "rb").read())
    if data[:4] != b"BND4":
        print("!! to nie jawny BND4 (.sl2 PC) — stop.")
        return 2
    entries = read_entries(bytes(data))

    s = slot_info(data, args.src, entries)
    d = slot_info(data, args.dst, entries)
    sp = profile_read(data, entries, args.src)
    dp = profile_read(data, entries, args.dst)

    print(f"plik: {args.save}")
    print(f"  źródło  slot{args.src}: v{s['version']}  profil='{sp['name']}' lvl={sp['level']} "
          f"czas={sp['seconds']/3600:.1f}h" if sp["name"] else f"  źródło  slot{args.src}: (pusty!)")
    print(f"  cel     slot{args.dst}: v{d['version']}  profil='{dp['name']}' lvl={dp['level']} "
          f"czas={dp['seconds']/3600:.1f}h" if dp["name"] else f"  cel     slot{args.dst}: (pusty)")
    if s["version"] == 0:
        print("!! slot źródłowy jest pusty — nie ma czego kopiować.")
        return 2
    if sp["name"] == dp["name"] and sp["name"]:
        print("  uwaga: oba sloty mają to samo imię — po kopii będą dwie identyczne postacie "
              "(--clear-source usuwa oryginał).")

    print(f"\nplan: slot{args.src} -> slot{args.dst}: dane 0x280000 B + profil 0x24C B, "
          f"przeliczę MD5 slotu@0x{d['md5']:X} i USER_DATA_10"
          + (", wyczyszczę slot źródłowy" if args.clear_source else ""))

    if not args.apply:
        print("\nDRY-RUN. Dodaj --apply, aby wykonać.")
        return 0

    if game_running():
        print("\n!! eldenring.exe działa — zamknij grę przed zapisem.")
        return 3

    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = f"{args.save}.copybak-{stamp}"
    shutil.copy2(args.save, bak)
    print(f"\nbackup: {bak}")

    # 1. dane slotu
    data[d["body"] : d["body"] + SLOT_BODY] = data[s["body"] : s["body"] + SLOT_BODY]
    data[d["md5"] : d["md5"] + 16] = hashlib.md5(bytes(data[d["body"] : d["body"] + SLOT_BODY])).digest()

    # 2. profil (ekran wyboru)
    ud = entries[10]["off"] + 16
    src_p = ud + PROFILE_BASE + args.src * PROFILE_SIZE
    dst_p = ud + PROFILE_BASE + args.dst * PROFILE_SIZE
    data[dst_p : dst_p + PROFILE_SIZE] = data[src_p : src_p + PROFILE_SIZE]

    # 3. opcjonalne czyszczenie źródła
    if args.clear_source:
        data[s["body"] : s["body"] + SLOT_BODY] = b"\x00" * SLOT_BODY
        data[s["md5"] : s["md5"] + 16] = EMPTY_MD5
        data[src_p : src_p + PROFILE_SIZE] = b"\x00" * PROFILE_SIZE

    # 4. MD5 USER_DATA_10 (na końcu, po zmianach profili)
    ud_body = bytes(data[ud : ud + 0x60000])
    data[ud - 16 : ud] = hashlib.md5(ud_body).digest()

    tmp = args.save + ".tmp-erlab"
    with open(tmp, "wb") as f:
        f.write(bytes(data))
    os.replace(tmp, args.save)
    print("zapisane (atomic replace).")

    # --- weryfikacja po zapisie ---
    chk = open(args.save, "rb").read()
    ok = True
    e2 = read_entries(chk)

    def md5_ok(entry):
        return (
            hashlib.md5(chk[entry["off"] + 16 : entry["off"] + 16 + SLOT_BODY]).digest()
            == chk[entry["off"] : entry["off"] + 16]
        )

    checks = [("slot docelowy", md5_ok(e2[args.dst]))]
    if args.clear_source:
        checks.append(("slot źródłowy (zerowany)", md5_ok(e2[args.src])))
    ud_check = hashlib.md5(chk[e2[10]["off"] + 16 : e2[10]["off"] + 16 + 0x60000]).digest() == chk[
        e2[10]["off"] : e2[10]["off"] + 16
    ]
    checks.append(("USER_DATA_10", ud_check))
    for label, res in checks:
        ok = ok and res
        print(f"  verify {label}: md5={'OK' if res else 'BAD'}")

    for k in (args.src, args.dst):
        p = profile_read(chk, e2, k)
        print(f"  profil slot{k}: '{p['name']}' lvl={p['level']} czas={p['seconds']/3600:.1f}h")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
