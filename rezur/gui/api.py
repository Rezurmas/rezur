"""Most GUI ↔ silnik (pywebview js_api). Bez logiki: woła te same funkcje co CLI.

Zasady:
    - każda metoda zwraca dict JSON-friendly; błędy jako {"error": "..."};
    - EDYCJE idą przez staging (`stage` → `pending` → `apply`/`discard`/`undo`);
    - zapis do żywego save'a przy działającej grze jest blokowany (guard_live);
    - restore/GOLD/piny działają wprost (to akcje na kopiach), z twardą blokadą gry.
"""

import contextlib
import io
import os
import time
from pathlib import Path

from .. import __version__, staging
from .. import config as CONF
from ..core import items_db, journal, vault
from ..core.profiles import roster
from ..core.savefile import SaveFile, default_save_path
from ..core.slots import STATE_ACTIVE, Slot
from ..diag import run_diagnostics
from .. import fixes as F
from .. import risk as riskmod
from ..ops import world as world_ops
from ..ops.appearance import read as appearance_read
from ..ops.flags import graces as graces_data
from ..ops.items import equipment as equipment_of
from ..ops.items import list_inventory
from ..ops.spells import equipped as spells_equipped
from ..ops.teleport import LOCATIONS as TELEPORT_LOCATIONS
from ..ops.teleport import info as teleport_info
from ..ops.transfer import export_character
from ..ops.watch import game_running


def _is_live(path):
    return "eldenring" in str(path).lower()


def _live(path):
    """Ścieżka do CZYTANIA: brudnopis stagingu, jeśli istnieje (podgląd zmian)."""
    try:
        if staging.op_count(path) > 0:
            work = staging.work_path(path)
            if Path(work).is_file():
                return str(work)
    except OSError:
        pass
    return str(path)


def _native_dialog(kind, **kw):
    """Natywny dialog okna (WebView2) — bez tkinter; fallback na tkinter w dev-owym Pythonie.

    kind: "open" | "save" | "folder". Zwraca ścieżkę albo None (anulowano).
    """
    try:
        import webview

        win = webview.windows[0] if getattr(webview, "windows", None) else None
        if win is not None:
            dtype = {"open": webview.OPEN_DIALOG, "save": webview.SAVE_DIALOG,
                     "folder": webview.FOLDER_DIALOG}[kind]
            res = win.create_file_dialog(dtype, **kw)
            if not res:
                return None
            return res[0] if isinstance(res, (list, tuple)) else str(res)
    except Exception:  # noqa: BLE001 — brak okna/nie ten backend → próbujemy tkinter
        pass
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        out = (filedialog.askopenfilename() if kind == "open"
               else filedialog.asksaveasfilename(defaultextension=".json",
                                                 initialfile=kw.get("save_filename", "")))
        root.destroy()
        return out or None
    except Exception:  # noqa: BLE001
        return None


class GuiApi:
    def __init__(self, initial_save=None):
        self.initial_save = initial_save

    # ------------------------------------------------------------- stan ogólny

    def initial_state(self):
        try:
            save = self.initial_save
            if not save:
                last = CONF.load().get("last_save")
                if last and Path(last).is_file():
                    save = last
                else:
                    try:
                        save = str(default_save_path())
                    except FileNotFoundError:
                        save = None
            return {
                "version": __version__,
                "save": save,
                "config": CONF.load(),
                "game_running": game_running(),
            }
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def config_get(self):
        try:
            return {"config": CONF.load(), "path": str(CONF.config_path())}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def config_set(self, key, value):
        try:
            k, v = CONF.set_value(str(key), str(value))
            return {"ok": True, "key": k, "value": v, "config": CONF.load()}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def game_status(self):
        try:
            return {"running": game_running()}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # ------------------------------------------------------------------ pliki

    def pick_save(self):
        try:
            p = _native_dialog("open", file_types=("Elden Ring save (*.sl2)", "All files (*.*)"))
            return {"path": p} if p else {"cancelled": True}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def open_folder(self, path):
        try:
            os.startfile(str(Path(path).parent))
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # ------------------------------------------------------------- wczytywanie

    def load(self, path):
        try:
            t0 = time.perf_counter()
            sf = SaveFile(_live(path))
            r = roster(sf)
            chars = []
            for i in range(10):
                s = Slot(sf, i)
                entry = {"slot": i, "empty": s.is_empty}
                if not s.is_empty:
                    if s.parse(r[i]["name"], r[i]["level"]):
                        ch = s.character()
                        h = ch["horse"]
                        pv = ch["patch"]
                        entry.update({
                            "name": ch["name"], "level": ch["level"],
                            "seconds": ch["seconds"], "runes": ch["runes_memory"],
                            "stats": ch["stats"],
                            "map_name": ch["map_name"],
                            "patch": pv["version"], "patch_latest": bool(pv["is_latest"]),
                            "horse": h["state_name"],
                            "horse_bug": h["hp"] == 0 and h["state"] == STATE_ACTIVE,
                            "parsed": True,
                        })
                    else:
                        entry.update({"parsed": False, "reason": s.reason,
                                      "name": r[i]["name"] or "?"})
                chars.append(entry)
            md5 = sf.section_md5_status()
            return {
                "ok": True,
                "path": str(path),
                "file": Path(path).name,
                "size_mb": round(Path(path).stat().st_size / 1e6, 1),
                "steamid": str(sf.steam_id()),
                "load_ms": int((time.perf_counter() - t0) * 1000),
                "md5": {"ok": sum(1 for s in md5 if s["ok"]), "total": len(md5)},
                "characters": chars,
                "game_running": game_running(),
                "live": _is_live(path),
                "staged": staging.op_count(path) > 0,
            }
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # ------------------------------------------------------------ diagnostyka

    def doctor(self, path):
        try:
            sf = SaveFile(_live(path))
            findings = run_diagnostics(sf)
            md5 = sf.section_md5_status()
            return {
                "ok": True,
                "findings": [
                    {"level": f.level, "code": f.code, "message": f.message,
                     "slot": f.slot, "fix": f.fix}
                    for f in findings
                ],
                "md5": {"ok": sum(1 for s in md5 if s["ok"]), "total": len(md5),
                        "bad": [s["name"] for s in md5 if not s["ok"]]},
            }
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def fixes(self):
        try:
            return {"fixes": [
                {"id": f.id, "title": getattr(f, "title", f.id),
                 "description": getattr(f, "description", "")}
                for f in F.list_fixes()
            ]}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def risk_scan(self, path):
        try:
            sf = SaveFile(_live(path))
            return {"ok": True, **riskmod.scan(sf)}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def watch_once(self, path):
        try:
            from ..ops.watch import run_once

            return {"ok": True, **run_once(path)}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # ------------------------------------------------------------ czytanie ops

    def inventory(self, path, slot, location="held", search="", offset=0, limit=200):
        try:
            sf = SaveFile(_live(path))
            rows = list_inventory(sf, int(slot), location)
            q = (search or "").lower()
            if q:
                rows = [r for r in rows if q in r["name"].lower() or q in hex(r["item_id"])]
            total = len(rows)
            page = rows[int(offset): int(offset) + int(limit)]
            return {
                "ok": True, "total": total,
                "rows": [
                    {**r, "hex": f"0x{r['item_id']:08X}", "handle_hex": f"0x{r['handle']:08X}"}
                    for r in page
                ],
            }
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def equipment(self, path, slot):
        try:
            return {"ok": True, **equipment_of(SaveFile(_live(path)), int(slot))}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def spells(self, path, slot):
        try:
            return {"ok": True, **spells_equipped(SaveFile(_live(path)), int(slot))}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def spell_list(self, path, slot, query="", limit=400):
        """Katalog czarów do wyboru (z filtrem) + czy w ekwipunku / zapamiętany."""
        try:
            from ..ops.spells import status as spells_status

            return {"ok": True, **spells_status(SaveFile(_live(path)), int(slot), query, int(limit))}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def appearance(self, path, slot):
        try:
            return {"ok": True, **appearance_read(SaveFile(_live(path)), int(slot))}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def teleport_info(self, path, slot):
        try:
            return {"ok": True, **teleport_info(SaveFile(_live(path)), int(slot)),
                    "destinations": sorted(TELEPORT_LOCATIONS)}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def world_groups(self):
        try:
            return {"ok": True, "groups": world_ops.groups()}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def world_view(self, path, slot, group, query="", offset=0, limit=200):
        try:
            sf = SaveFile(_live(path))
            data = world_ops.view(sf, int(slot), group, query=query or None, limit=100000)
            rows = data["entries"]
            total = len(rows)
            return {"ok": True, "total": total,
                    "rows": rows[int(offset): int(offset) + int(limit)]}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def graces_regions(self):
        try:
            g = graces_data()
            return {"ok": True, "regions": {k: len(v) for k, v in g.items()}}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def find(self, query, limit=40):
        try:
            q = str(query or "")
            items = items_db.search(q, limit=int(limit))
            flags = world_ops.search_names(q, limit=int(limit))
            locs = [k for k in TELEPORT_LOCATIONS if q.lower() in k.lower()]
            graces_hits = []
            try:
                graces_hits = [
                    {"region": region, "name": gname}
                    for region, rows in graces_data().items()
                    for _fid, gname in rows
                    if q.lower() in gname.lower()
                ][: int(limit)]
            except OSError:
                pass
            return {"ok": True,
                    "items": [{"id": f"0x{fid:08X}", "name": name, "cat": cat}
                              for fid, name, cat in items],
                    "flags": [{"group": g, "id": fid, "name": name} for g, fid, name in flags],
                    "graces": graces_hits, "locations": locs}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def log(self, path):
        try:
            return {"ok": True, "entries": journal.load(path)["entries"],
                    "labels": journal.OP_LABELS}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # -------------------------------------------------------------- staging

    def stage(self, path, argv):
        """Wykonuje komendę edycji na kopii roboczej (jedna zmiana oczekująca)."""
        from ..cli import STAGEABLE, main as cli_main

        try:
            argv = [str(a) for a in argv]
            if not argv:
                return {"error": "puste polecenie"}
            cmd, op_args = argv[0], argv[1:]
            if cmd not in STAGEABLE:
                return {"error": f"nie edytuję tą drogą: {cmd}"}
            work = staging.begin(path)
            before = staging.md5_file(work)
            snap = staging.make_snapshot(path)
            full = [cmd, "--save", str(work), *op_args]
            if "--apply" not in full:
                full.append("--apply")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = cli_main(full)
            out = buf.getvalue()
            if rc != 0:
                staging.drop_snapshot(path, snap)
                return {"error": "komenda odmówiła", "rc": rc, "output": out}
            if staging.md5_file(work) == before:
                staging.drop_snapshot(path, snap)
                return {"ok": True, "changed": False, "output": out,
                        "pending": staging.op_count(path)}
            n = staging.record_op(path, cmd, " ".join(op_args), snap=snap)
            return {"ok": True, "changed": True, "pending": n, "output": out}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def pending(self, path):
        try:
            man = staging.load_manifest(path)
            return {
                "ok": True,
                "count": len(man["ops"]) if man else 0,
                "created": man["created"] if man else None,
                "ops": man["ops"] if man else [],
                "original_changed": staging.original_changed(path),
            }
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def preview(self, path):
        """Zmienione sekcje: brudnopis vs oryginał (bajt w bajt)."""
        try:
            if staging.op_count(path) == 0:
                return {"ok": True, "changed": [], "note": "brak zmian oczekujących"}
            so = SaveFile(path)
            sw = SaveFile(staging.work_path(path))
            changed = []
            for e in so.entries:
                a = so.data[e["off"] + 16: e["off"] + e["size"]]
                b = sw.data[e["off"] + 16: e["off"] + e["size"]]
                if a != b:
                    changed.append(e["name"])
            return {"ok": True, "changed": changed}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def undo(self, path):
        try:
            res = staging.undo_last(path)
            return {"ok": True, **res}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def discard(self, path):
        try:
            res = staging.discard(path)
            return {"ok": True, **res}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def apply(self, path, force=False):
        try:
            if game_running() and _is_live(path):
                return {"error": "gra działa — zapis do żywego save'a zablokowany (guard_live)"}
            if staging.op_count(path) == 0:
                return {"error": "brak zmian oczekujących"}
            try:
                res = staging.apply(path, force=bool(force))
            except RuntimeError as e:
                return {"error": str(e), "needs_force": True}
            except ValueError as e:
                return {"error": str(e), "kept": True}
            return {"ok": True, **res}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # ------------------------------------------------------------------ kopie

    def backups(self, path):
        try:
            rows = vault.list_backups(path)
            return {"ok": True,
                    "rows": [{k: b[k] for k in ("name", "tag", "gold", "pinned", "size", "mtime")}
                             for b in rows],
                    "retention": CONF.load().get("backup_retention")}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def backup_gold(self, path):
        try:
            return {"ok": True, **vault.ensure_gold(path)}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def backup_pin(self, path, name, on=True):
        try:
            pins = vault.set_pin(path, name, on=bool(on))
            return {"ok": True, "pins": pins}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def restore(self, path, name):
        try:
            if game_running() and _is_live(path):
                return {"error": "gra działa — przywracanie do żywego save'a zablokowane"}
            rows = vault.list_backups(path)
            hit = next((b for b in rows if b["name"] == name), None)
            if not hit:
                return {"error": f"nie ma kopii: {name}"}
            rep = vault.restore(path, hit["path"])
            return {"ok": True, **rep}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # --------------------------------------------------------------- transfer

    def export_char(self, path, slot):
        try:
            out = _native_dialog("save", save_filename=f"slot{int(slot)}.json")
            if not out:
                return {"cancelled": True}
            rep = export_character(SaveFile(path), int(slot), out)
            return {"ok": True, "out": out, **rep}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def pick_json(self):
        try:
            p = _native_dialog("open", file_types=("JSON (*.json)",))
            return {"path": p} if p else {"cancelled": True}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
