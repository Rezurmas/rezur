"""Ryzyko online — co w save'ie może zwrócić uwagę skanera gry.

Rezur nie daje gwarancji braku flagi: gra skanuje save'y pod kątem danych
niemożliwych (staty, ulepszenia, ilości). Ten moduł wyłapuje to, co da się
sprawdzić po naszej stronie, i pokazuje znacznik „plik modyfikowany przez
Rezura" (dziennik edycji) razem z drogą powrotu do kopii GOLD.

Ustalenia: level ∈ {error, warning, info}; werdykt: red > yellow > green.
"""

from .core import gaitem, inventory, items_db, journal
from .core.profiles import roster
from .core.slots import Slot

RED, YELLOW, GREEN = "red", "yellow", "green"

NOTES = [
    "eksperymentuj na KOPII (backup/GOLD), nie na żywym save'ie",
    "przed grą online rozważ powrót do GOLD — gra nie odróżnia „grzecznych\" edycji od reszty",
    "Rezur nie gwarantuje braku flagi: skaner gry patrzy na dane niemożliwe, "
    "a my potrafimy sprawdzić tylko część z nich",
]


def _f(level, code, msg, slot=None):
    return {"level": level, "code": code, "message": msg, "slot": slot}


def scan_slot(save, i, prof):
    out = []
    s = Slot(save, i)
    if s.is_empty:
        return out
    if not s.parse(prof["name"], prof["level"]):
        out.append(
            _f("error", "slot_unparsed",
               f"nie da się zweryfikować statów (suma statów−79 ≠ poziom albo obcy format): {s.reason}", i)
        )
        return out
    ch = s.character()

    stats = ch["stats"]
    if any(not (1 <= x <= 99) for x in stats):
        out.append(_f("error", "stats_out_of_range", f"stat poza zakresem 1..99: {stats}", i))
    if not (1 <= ch["level"] <= 713):
        out.append(_f("error", "level_out_of_range", f"poziom poza 1..713: {ch['level']}", i))

    # broń: ulepszenia i itemy spoza bazy
    try:
        entries, _ = gaitem.walk(s.raw, s.version, expect_end=s.offsets["pgd"])
    except ValueError as e:
        out.append(_f("error", "gaitem_walk", f"nie da się przejść tablicy itemów: {e}", i))
        return out

    unresolved = 0
    bad_upg = []
    for e in entries:
        h = e["handle"]
        if not h or (h >> 28) & 0xF != 0x8:
            continue
        nm, _cat = items_db.resolve(e["item_id"])
        if nm is None:
            unresolved += 1
        elif e["item_id"] % 100 > 25:
            bad_upg.append(f"{nm} (id%100={e['item_id'] % 100})")
    for b in bad_upg[:3]:
        out.append(_f("error", "upgrade_impossible", f"niemożliwe ulepszenie broni: {b}", i))

    # ilości w ekwipunku i skrzyni
    ho, so = s.inventory_offsets()
    qover = 0
    for off, loc in ((ho, "held"), (so, "storage")):
        inv = inventory.read(s.raw, off, loc)
        for ls in (inv["common_items"], inv["key_items"]):
            for hd, q, _a in ls:
                if hd and q > 999:
                    qover += 1
    if qover:
        out.append(_f("warning", "qty_over", f"{qover} itemów z ilością > 999 (możliwe flagowanie)", i))

    if unresolved:
        out.append(
            _f("info", "items_unresolved",
               f"{unresolved} itemów spoza naszej bazy (nowszy dodatek albo pozostałość po modach "
               "— nie przesądzamy)", i)
        )
    return out


def scan(save, only_slot=None):
    """Pełny skan: findings + werdykt + znacznik modyfikacji + GOLD."""
    r = roster(save)
    findings = []
    idxs = range(10) if only_slot is None else [only_slot]
    for i in idxs:
        findings += scan_slot(save, i, r[i])

    jsum = journal.summary(save.path)
    gold = None
    try:
        from .core import vault

        g = vault.gold_backup(save.path)
        gold = g["name"] if g else None
    except OSError:
        gold = None

    if any(f["level"] == "error" for f in findings):
        verdict = RED
    elif any(f["level"] == "warning" for f in findings):
        verdict = YELLOW
    else:
        verdict = GREEN

    return {
        "findings": findings,
        "verdict": verdict,
        "modified": jsum,
        "gold": gold,
        "notes": NOTES,
    }
