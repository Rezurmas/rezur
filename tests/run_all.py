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
from rezur.core import profiles as P  # noqa: E402
from rezur.core.savefile import SaveFile  # noqa: E402
from rezur.diag import run_diagnostics  # noqa: E402

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
