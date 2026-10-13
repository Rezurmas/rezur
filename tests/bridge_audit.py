"""Audyt mostu GUI ↔ silnik (twarda weryfikacja „czy wszystko połączone").

Woła KAŻDĄ metodę `rezur.gui.api.GuiApi` na KOPII playgroundu, w izolowanym
katalogu (tymczasowy %APPDATA% — nie rusza prawdziwego configu ani stagingu),
i sprawdza, że zwraca sensowne dane (bez klucza `error` tam, gdzie go być nie ma).

Uruchomienie:  python tests/bridge_audit.py [--save PLIK] [--keep]

Kod wyjścia: 0 = wszystko połączone, 1 = coś nie działa.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRATCH = ROOT / "scratch"
PLAYGROUND = SCRATCH / "rezur_playground.sl2"

RESULTS = []


def rec(name, ok, detail=""):
    RESULTS.append({"call": name, "ok": bool(ok), "detail": str(detail)[:200]})
    mark = "OK  " if ok else "FAIL"
    print(f"[{mark}] {name:<46} {str(detail)[:90]}")
    return ok


def no_error(r, what=""):
    """dict bez 'error' → (True, opis)."""
    if not isinstance(r, dict):
        return False, f"nie dict: {type(r).__name__}"
    if "error" in r:
        return False, r["error"]
    return True, what


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", default=None, help="plik .sl2 do audytu (domyślnie kopia playgroundu)")
    ap.add_argument("--keep", action="store_true", help="nie kasuj katalogu tymczasowego")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="rezur_bridge_"))
    src = Path(args.save) if args.save else PLAYGROUND
    if not src.is_file():
        print(f"brak pliku do audytu: {src}")
        return 2
    save = tmp / "audit.sl2"
    shutil.copy2(src, save)

    # izolacja: własny %APPDATA% (config + staging) — nic nie dotyka prawdziwych
    os.environ["APPDATA"] = str(tmp)
    sys.path.insert(0, str(ROOT))

    from rezur.gui.api import GuiApi  # noqa: E402

    api = GuiApi(initial_save=str(save))

    print(f"— audyt mostu na kopii: {src} → {save}")
    print(f"— izolowany %APPDATA%: {tmp}\n")

    # ---------------------------------------------------------- język / config
    ok, d = no_error(api.initial_state())
    st = api.initial_state()
    rec("initial_state", ok and "version" in st and "config" in st,
        f"version={st.get('version')} save={str(st.get('save'))[-24:]}")

    cfg = api.config_get()
    ok, d = no_error(cfg)
    rec("config_get", ok, f"ui_lang={cfg.get('config', {}).get('ui_lang')!r}")
    rec("config: domyślnie EN", cfg.get("config", {}).get("ui_lang") == "en",
        f"ui_lang={cfg.get('config', {}).get('ui_lang')!r}")

    r = api.config_set("ui_lang", "pl")
    ok, d = no_error(r)
    back = api.config_get().get("config", {}).get("ui_lang")
    rec("config_set ui_lang=pl", ok and back == "pl", f"zapisane: {back!r}")
    r = api.config_set("ui_lang", "en")
    back = api.config_get().get("config", {}).get("ui_lang")
    rec("config_set ui_lang=en (powrót)", back == "en", f"zapisane: {back!r}")
    r = api.config_set("ui_lang", "de")
    rec("config_set ui_lang=de → błąd", "error" in r, r.get("error", "brak błędu!"))
    r = api.config_set("nonsens", "1")
    rec("config_set nieznany klucz → błąd", "error" in r, r.get("error", "brak błędu!"))
    r = api.config_set("backup_retention", "20")
    rec("config_set backup_retention", "error" not in r, r.get("value"))
    api.config_set("watch_interval", "600")
    api.config_set("guard_live", "true")
    api.config_set("auto_doctor", "true")

    st = api.initial_state()
    rec("initial_state: last_save pusty (świeży config)", st.get("save") == str(save),
        f"save={st.get('save')}")

    # ------------------------------------------------------------------ stan
    r = api.game_status()
    ok, d = no_error(r)
    rec("game_status", ok, f"running={r.get('running')}")

    # ------------------------------------------------------------------ pliki
    r = api.load(str(save))
    ok, d = no_error(r)
    chars = r.get("characters", [])
    filled = [c for c in chars if not c.get("empty")]
    rec("load", ok and len(chars) == 10, f"postać: {len(filled)} · md5 {r.get('md5', {}).get('ok')}/{r.get('md5', {}).get('total')}")

    slot = filled[0]["slot"] if filled else 0

    r = api.doctor(str(save))
    ok, d = no_error(r)
    rec("doctor", ok, f"ustaleń: {len(r.get('findings', []))} · md5 {r.get('md5', {}).get('ok')}/{r.get('md5', {}).get('total')}")

    r = api.fixes()
    ok, d = no_error(r)
    rec("fixes", ok, f"napraw: {len(r.get('fixes', []))}")

    r = api.risk_scan(str(save))
    ok, d = no_error(r)
    rec("risk_scan", ok, f"werdykt: {r.get('verdict')} · uwag: {len(r.get('findings', []))}")

    r = api.watch_once(str(save))
    ok, d = no_error(r)
    rec("watch_once", ok, f"kopia={r.get('made')} powód={r.get('reason')}")

    r = api.inventory(str(save), slot)
    ok, d = no_error(r)
    rows = r.get("rows", [])
    rec("inventory (held)", ok and rows, f"{r.get('total')} itemów, pierwszy: {rows[0]['name'] if rows else '—'}")

    r = api.inventory(str(save), slot, "storage", "", 0, 50)
    ok, d = no_error(r)
    rec("inventory (storage, limit 50)", ok, f"{r.get('total')} itemów")

    r = api.inventory(str(save), slot, "held", "seed", 0, 20)
    ok, d = no_error(r)
    rec("inventory (szukaj 'seed')", ok, f"{r.get('total')} trafień")

    r = api.inventory(str(save), slot, "held", "", 10, 10)
    ok, d = no_error(r)
    rec("inventory (offset 10, limit 10)", ok, f"zwrócone: {len(r.get('rows', []))}")

    r = api.equipment(str(save), slot)
    ok, d = no_error(r)
    eq = r.get("equipped", [])
    rec("equipment", ok and eq, f"gniazd: {len(eq)}, założone: {sum(1 for e in eq if not e.get('empty'))}")

    r = api.spells(str(save), slot)
    ok, d = no_error(r)
    rec("spells", ok and r.get("spells") is not None, f"gniazd: {len(r.get('spells', []))}")

    r = api.spell_list(str(save), slot)
    ok, d = no_error(r)
    rows = r.get("rows", [])
    owned = sum(1 for x in rows if x.get("owned"))
    rec("spell_list (katalog czarów)", ok and len(rows) > 200,
        f"czarów: {len(rows)} · w ekwipunku: {owned}")

    r = api.spell_list(str(save), slot, "heal")
    ok, d = no_error(r)
    rec("spell_list (filtr 'heal')", ok and r.get("count", 0) < len(rows),
        f"trafień: {r.get('count')}")

    r = api.appearance(str(save), slot)
    ok, d = no_error(r)
    rec("appearance", ok, f"gender={r.get('gender')} archetyp={r.get('archetype')} gift={r.get('gift')}")

    r = api.teleport_info(str(save), slot)
    ok, d = no_error(r)
    rec("teleport_info", ok and r.get("xyz"), f"{r.get('map_name')} xyz={r.get('xyz')} celów: {len(r.get('destinations', []))}")

    r = api.world_groups()
    ok, d = no_error(r)
    groups = r.get("groups", {})
    rec("world_groups", ok and groups, f"grup: {len(groups)} → {', '.join(sorted(groups)[:6])}…")

    bad = []
    for gname in sorted(groups):
        rr = api.world_view(str(save), slot, gname, "", 0, 5)
        if "error" in rr or not isinstance(rr.get("rows"), list):
            bad.append(gname)
    rec("world_view (wszystkie grupy)", not bad, f"grup sprawdzonych: {len(groups)}" + (f" · złe: {bad}" if bad else ""))

    r = api.graces_regions()
    ok, d = no_error(r)
    rec("graces_regions", ok, f"klucze: {', '.join(list(r)[:5])}")

    r = api.find("uchigatana")
    ok, d = no_error(r)
    rec("find('uchigatana')", ok and r.get("items"), f"itemy: {len(r.get('items', []))} · flagi: {len(r.get('flags', []))}")

    r = api.log(str(save))
    ok, d = no_error(r)
    rec("log (dziennik)", ok, f"wpisów: {len(r.get('entries', []))}")

    r = api.pending(str(save))
    ok, d = no_error(r)
    rec("pending (przed zmianami)", ok, f"count={r.get('count')}")

    # ------------------------------------------------- staging (na kopii!)
    r = api.stage(str(save), ["stats", "--slot", str(slot), "--set", "vigor=50,mind=20"])
    ok, d = no_error(r)
    rec("stage (stats)", ok and r.get("changed"), f"changed={r.get('changed')} pending={r.get('pending')}")

    r = api.pending(str(save))
    rec("pending (po zmianie)", r.get("count", 0) >= 1, f"count={r.get('count')} · operacji: {len(r.get('ops', []))}")

    r = api.preview(str(save))
    ok, d = no_error(r)
    rec("preview", ok, f"zmienione sekcje: {r.get('changed')}")

    r = api.load(str(save))
    rec("load czyta BRUDNOPIS (staged)", r.get("staged") is True, f"staged={r.get('staged')}")

    r = api.undo(str(save))
    ok, d = no_error(r)
    rec("undo", ok, f"cofnięte: {r.get('undone')} · zostało: {r.get('left')}")

    api.stage(str(save), ["stats", "--slot", str(slot), "--set", "endurance=25"])
    r = api.discard(str(save))
    ok, d = no_error(r)
    rec("discard", ok, f"odrzuconych operacji: {r.get('ops')}")

    # ------------------------------------------------------------------ apply
    api.stage(str(save), ["stats", "--slot", str(slot), "--set", "vigor=45"])
    r = api.apply(str(save), False)
    ok, d = no_error(r)
    rec("apply (backup + zapis + weryfikacja)", ok and r.get("md5_ok") == r.get("md5_total"),
        f"backup={Path(str(r.get('backup', ''))).name} · md5 {r.get('md5_ok')}/{r.get('md5_total')}")

    r = api.log(str(save))
    ops = [e.get("op") for e in r.get("entries", [])]
    rec("log po apply (ślad modyfikacji)", bool(ops), f"operacje: {sorted(set(ops))}")

    r = api.risk_scan(str(save))
    mod = r.get("modified", {})
    rec("risk_scan widzi znacznik modyfikacji", mod.get("count", 0) >= 1, f"licznik={mod.get('count')}")

    # ------------------------------------------------------------------ kopie
    r = api.backups(str(save))
    ok, d = no_error(r)
    bks = r.get("rows", [])
    rec("backups (lista)", ok and bks, f"kopii: {len(bks)} · retention={r.get('retention')}")

    r = api.backup_gold(str(save))
    ok, d = no_error(r)
    gold_name = None
    r2 = api.backups(str(save))
    gold = next((b for b in r2.get("rows", []) if b.get("gold")), None)
    gold_name = gold["name"] if gold else None
    rec("backup_gold (GOLD istnieje)", ok and gold_name, f"gold={gold_name}")

    r = api.backup_pin(str(save), bks[0]["name"], True)
    ok, d = no_error(r)
    rec("backup_pin (ON)", ok, f"pins={r.get('pins')}")
    r = api.backup_pin(str(save), bks[0]["name"], False)
    ok, d = no_error(r)
    rec("backup_pin (OFF)", ok, f"pins={r.get('pins')}")

    newest = next((b for b in api.backups(str(save)).get("rows", []) if not b.get("gold")), None)
    if newest:
        r = api.restore(str(save), newest["name"])
        ok, d = no_error(r)
        rec("restore (z kopii)", ok, f"kopia={Path(newest['name']).name}")
        r3 = api.load(str(save))
        rec("load po restore", "error" not in r3, f"postać: {len([c for c in r3.get('characters', []) if not c.get('empty')])}")
    else:
        rec("restore (z kopii)", False, "brak kopii nie-GOLD")

    r = api.restore(str(save), "nie-ma-takiej-kopii.sl2")
    rec("restore nieistniejącej → błąd", "error" in r, r.get("error", "brak błędu!"))

    # ------------------------------------------------- metody z oknem systemowym
    for name in ("pick_save", "pick_json", "export_char", "open_folder"):
        rec(f"{name} podpięte (dialog okna)", callable(getattr(api, name, None)),
            "dialog — pomijane w audycie headless")

    # -------------------------------------------------------------- podsumowanie
    fails = [r for r in RESULTS if not r["ok"]]
    print("\n" + "=" * 72)
    print(f"POLĄCZONE: {len(RESULTS) - len(fails)}/{len(RESULTS)} wywołań mostu")
    if fails:
        print("NIE DZIAŁA:")
        for f in fails:
            print(f"  · {f['call']}: {f['detail']}")
    (tmp / "bridge_audit_report.json").write_text(
        json.dumps({"results": RESULTS, "fails": fails}, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.keep:
        print(f"katalog audytu: {tmp}")
    else:
        try:
            shutil.rmtree(tmp)
        except OSError:
            pass
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
