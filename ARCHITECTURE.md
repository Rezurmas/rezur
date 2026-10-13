# Rezur Saves Configurator — architecture

> Status: v0.2.0 — CLI + library + GUI (pywebview / WebView2, 13 panels, EN/PL).
> Overriding rule: **no logic lives in the interface**. The CLI and the GUI are thin adapters
> over the same engine.

---

## 1. TL;DR — decisions

| Question | Answer |
|---|---|
| Backend | **Python (stdlib only)** — the whole engine: `rezur.core/diag/fixes/ops`; the CLI runs with zero installs |
| Frontend | **local webview — pywebview** (WebView2 on Windows), UI in HTML+CSS+JS, no build step |
| GUI ↔ engine bridge | same Python process: pywebview hosts the window and loads local HTML; every operation goes through an in-process JSON API |
| Why not Clay (C) | dropped (no compiler on the box, slower iteration) |
| Why not Electron/Tauri | overkill — pywebview uses the WebView2 runtime already present on Windows 10/11 |
| GUI status | **built** (`python -m rezur gui`), staging-first, 13 panels |

---

## 2. Layers and dependency directions

```
                     ┌─────────────────────────────────────────┐
                     │                 CLI (rezur)             │
                     │  info · doctor · fix · stage · apply …   │
                     └───────────────────┬─────────────────────┘
                                         │  (same functions)
                     ┌───────────────────┴─────────────────────┐
                     │        GUI bridge (gui/api.py)          │
                     │   pywebview js_api — in-process, no HTTP│
                     └───────────────────┬─────────────────────┘
                                         ▼
                     ┌─────────────────────────────────────────┐
                     │  ops      (copy_slot, steamid, items, …)│
                     │  fixes    (torrent, checksums, summary, │
                     │            playerhash, weather, dlc, …) │
                     │  diag     (checks → Finding)            │
                     │  staging  (work copy + manifest)        │
                     │  risk     (impossible data scan)        │
                     └───────────────────┬─────────────────────┘
                                         ▼
                     ┌─────────────────────────────────────────┐
                     │  core     (SaveFile, Slot, checksums,   │
                     │            profiles, bnd4, reader,      │
                     │            vault, journal)              │
                     │  games    (game registry: Elden Ring)   │
                     └───────────────────┬─────────────────────┘
                                         ▼
                          %APPDATA%\EldenRing\<id>\ER0000.sl2
```

**Import rules (one-directional, no cycles):**

| layer | may import | must NOT import |
|---|---|---|
| `core` | stdlib, `core` | anything above |
| `games` | stdlib | `core` (the registry stays pure) |
| `diag` | `core` | `fixes`, `ops`, interfaces |
| `fixes` | `core` | `diag`, `ops`, interfaces |
| `ops` | `core`, `fixes` | interfaces |
| `report` | `core`, (`diag` types) | `fixes`, `ops` |
| `cli` / `gui` | everything below | each other |

The "finding → repair" coupling is loose: `Finding.fix` is a **string id** (`"torrent"`),
not a reference — so `diag` knows nothing about `fixes`, and new repairs need no changes there.

---

## 3. Directory structure (actual state)

```
ER-Save-Lab/
├── rezur/                        ← the package (product)
│   ├── __init__.py               product + version
│   ├── __main__.py               python -m rezur
│   ├── cli.py                    ~34 subcommands
│   ├── config.py                 %APPDATA%\rezur\config.json (retention, guard_live, ui_lang…)
│   ├── core/
│   │   ├── reader.py             safe little-endian reads (u8..u64, f32, UTF-16)
│   │   ├── bnd4.py               container: header + 12 entries
│   │   ├── checksums.py          section MD5 + PlayerDataHash
│   │   ├── slots.py              full, versioned slot parser (content-anchored)
│   │   ├── profiles.py           roster + rebuild of the character-select profile
│   │   ├── savefile.py           SaveFile: sections, slot MD5, atomic write
│   │   ├── vault.py              GOLD (once per file), pins, rotation, restore
│   │   ├── journal.py            edit journal (<save>.rezur-journal.json)
│   │   ├── items_db.py           item database lookups
│   │   ├── gaitem.py             GaItem map walker (weapons/armor/AoW)
│   │   └── inventory.py          held/storage layout, counters
│   ├── games/                    game profile interface + registry (Elden Ring)
│   ├── diag/engine.py            checks → Finding(level, code, message, slot, fix)
│   ├── fixes/                    torrent, checksum, playerhash, summary, weather, dlc, invcounters
│   ├── ops/                      stats, items, spells, appearance, teleport, world, flags,
│   │                             graces, copy_slot, steamid, transfer, backups, watch
│   ├── staging.py                work copy + manifest + per-op snapshots
│   ├── risk.py                   online-risk scan + "modified" marker
│   ├── report/                   text and JSON output
│   ├── gui/                      api.py (bridge), app.py (shell + selftest), web/ (UI + i18n)
│   └── data/db_er/               item / flag / spell / grace tables
├── tests/run_all.py              48 tests on copies of real saves
├── tests/smoke_cli.py            135 CLI invocations
├── tests/bridge_audit.py         51 GUI-bridge calls on a save copy (isolated %APPDATA%)
├── tools/                        fix_torrent, copy_slot, build_exe.cmd, sanitize_public.py, gh_login.sh
├── packaging/rezur.spec          PyInstaller → dist\rezur.exe (one file)
├── docs/screenshots/             GUI screenshots used by the README
├── web/test-bench.html           design bench (engineering-series style contract)
├── PLAN.md                       project plan F0→F7 (internal, Polish)
└── ARCHITECTURE.md               this document
```

---

## 4. Flows

**doctor** (read-only):
`CLI → diag.run_diagnostics → core (SaveFile, Slot.parse, profiles.roster) → [Finding] → report`

**fix** (the only writing path):
```
CLI → fixes.apply_fixes(dry_run=True)   → “what I would repair”, nothing written
CLI → fixes.apply_fixes(dry_run=False)  → mutation through SaveFile
     → SaveFile.write(): GOLD → tagged backup → tmp → fsync → verify → os.replace
     → diagnostics re-run → report what is left
```

**staging** (pending changes — `idle → staged → applied/discarded`):
```
CLI (stage <command …>) → staging.begin: work copy in %APPDATA%\rezur\staging\
        → the edit writes to the draft (SaveFile.write detects the work path:
          no backup, no journal; the op counter grows only on a real byte difference)
CLI (pending)  → manifest: list of operations (--diff: byte-for-byte section comparison)
CLI (apply)    → verify the draft → GOLD → backup the original (stagebak) → atomic write
                 → journal entry (with the backup name) → clean staging → 12/12 MD5
CLI (discard)  → delete the draft; the original is UNTOUCHED
verification failure on apply → the changes STAY (nothing is lost, fix and retry)
```

**GUI**: `web/app.js` → `window.pywebview.api.*` → `gui/api.py` → same engine functions as the CLI.
Read panels call `_live()`: when pending changes exist they read the **work copy**, so the UI shows
the staged draft; the original is touched only on APPLY.

---

## 5. Backend rationale

- the core has zero dependencies (stdlib), so the CLI and the tests run anywhere without installs;
- the GUI needs `pywebview` + `pythonnet` (optional extra) — WebView2 is already on Windows 10/11;
- input validation belongs to the CLI/GUI layer, never to `core`;
- the GUI bridge is in-process (no ports, no tokens, no uploads): the file never leaves the machine.

---

## 6. GUI — pywebview window (WebView2), built

- `python -m rezur gui [--save FILE]` → native WebView2 window; frontend in HTML/CSS/JS
  (`rezur/gui/web/`), bridge `window.pywebview.api.*` → `rezur/gui/api.py` (same process).
- **api.py** is a thin layer: the same functions as the CLI; every EDIT goes through staging;
  read panels show the DRAFT when pending changes exist (`_live()`).
- **Style** (engineering-series, bench `web/test-bench.html`): black anodized `#1E1F22`,
  orange `#F0501E` as the only accent, dot-matrix LCDs, keys with a hard 2px travel, hazard
  stripes only for destructive actions, **no sliders** (stats: `+`/`−` with hold-repeat plus
  click-to-type).
- 13 panels: CHARACTERS · DOCTOR · STATS · INVENTORY · LOADOUT · WORLD · SPELLS · APPEARANCE ·
  TELEPORT · RISK · BACKUPS · HISTORY · SETTINGS; change bar at the bottom
  (PREVIEW / UNDO / APPLY / DISCARD); writes blocked while the game is running.
- **i18n:** English by default; `EN/PL` pill in the header and buttons in SETTINGS; the choice is
  persisted as `ui_lang` (validated `en|pl`) and reloads the window; dictionaries `I18N.en/pl` in
  `app.js`, engine diagnostics translated by code (`FIND_EN`), numbers via `toLocaleString`.
- **Tables:** the toolbar is sticky at the top of the panel (`stickBars()` sets `--barH`) and the
  table header docks right below it (`table-layout: fixed` keeps header and body cells aligned);
  nothing overlaps the buttons.
- **Spells:** 14 slots plus a **catalogue of 213 spells** (`db_er/magic.json`, derived from
  SaveForge `sorceries.go`/`incantations.go`) with a live filter and a state badge
  (in inventory / memorized); MEMORIZE stages the change. CLI equivalent:
  `python -m rezur spells --slot N --list`.
- **Live search:** every search field filters or suggests while you type (170 ms debounce, min.
  2 characters) — inventory and world filter the list below (ranking: prefix → shorter → alpha);
  item / spell / equip inputs show inline suggestion lists with the matched fragment highlighted
  (click, `Enter` = first, arrows = move). Lists are inline, so nothing is ever covered.
- `--selftest`: the window opens, evaluates `window.__rezurBooted` / `__rezurLoaded`, counts bridge
  methods and panels, prints the 13 tab labels, exercises the live search, then switches the UI
  language live (EN→PL→EN via `config_set ui_lang` + reload) and closes.
- **`tests/bridge_audit.py`:** calls EVERY `GuiApi` method on a save copy inside an isolated
  `%APPDATA%` (51 calls: load/doctor/risk/staging/apply/backups/restore/config/panels) and exits
  non-zero when any bridge call fails.
- **Guard tests:** `t_ui_lang_default_and_switch`, `t_gui_i18n_and_wiring` (EN/PL key parity, every
  `t("…")` key translated, every JS handle present in the HTML, 13 tabs = 13 panels with labels in
  both languages) and `t_db_no_cjk_names` (no Japanese datamine names in the flag database).

### Application states (GUI contract)

| state | when | UI |
|---|---|---|
| `empty` | no file selected | “pick or drop ER0000.sl2” + recent list |
| `loading` | reading ~29 MB | indeterminate indicator + time; the window must not freeze |
| `ready` | file loaded | character cards, panels active |
| `staged` | ≥1 pending change | change counter + PREVIEW / APPLY / DISCARD |
| `busy` | apply running | controls blocked + phase (“writing”, “verifying”) |
| `failed` | write error | changes STAY, an explicit message (staging untouched) |
| `done` | write OK | green: backup name + 12/12 MD5 + history entry (`log`) |

---

## 7. Save format (verified on real 1.16-era saves)

- `%APPDATA%\EldenRing\<SteamID64>\ER0000.sl2`; BND4 header `0x300`, then 10 slots of
  `0x10 MD5 + 0x280000 data`, then UserData10 (`0x10 + 0x60000`) and UserData11 (`0x10 + 0x240000`).
- Slot: `u32 version @0x00` (0 = empty), `u32 map_id @0x04`, GaItem map from `0x20`.
  The slot tail (coords → netman → weather/time → steam_id → dlc → PlayerDataHash) ends wherever
  the data ends — **never assume tail-at-slot-end**; anchor by content instead.
- The stat anchor is found by CONTENT (`level == sum(8 stats) − 79` with the UTF-16 name at
  `anchor+0x60`); walk FORWARD from it.
- UserData10: profile summaries start at `0x195E`, `0x24C` each; `name = 16×u16`,
  `level @+0x22`, `seconds @+0x26`, `runes @+0x2A`, `map_id @+0x2E`.
- Consistency rules the game itself enforces: `level == sum(stats) − 79`; each slot MD5 covers the
  body after the digest; empty slot = zero body (MD5 `8354dcaa18a1ecb52d0895bf00888c44`).
- Horse (RideGameData): `hp i32 @+0x20`, `state u32 @+0x24`; states 1 INACTIVE, 3 DEAD, 13 ACTIVE —
  `hp=0` while ACTIVE is the classic Torrent hang after a crash.
- Appearance: `gender u8 @0xB6`, `archetype @0xB7`, body type `@0xB8` (hash-covered), gift `@0xBB`.
- Teleport: slot header `map_id` + tail coordinates + weather `area_id` → `(map_id >> 24) & 0xFF`.

Exact offsets and pitfalls discovered while implementing this (including the whole translation
workflow for the datamined flag names) live in the helper notes shipped with the project.

---

## 8. Roadmap

| phase | scope | files | status |
|---|---|---|---|
| F1 | parser + report + doctor | `core/`, `diag/`, `report/` | ✅ v0.1.0 |
| F2 | stats / runes / name editing (level validation) | `ops/stats.py` | ✅ |
| F3 | items (gaitem + inventory + `db_er`) | `core/gaitem.py`, `ops/items.py` | ✅ |
| F4 | world: event flags, graces, bosses | `core/flags.py`, `ops/flags.py` | ✅ |
| F5 | transfer: character import/export (JSON) | `ops/transfer.py` | ✅ |
| F5b | trust: vault (GOLD/pins), watch, risk, staging + log | `core/vault.py`, `ops/watch.py`, `risk.py`, `staging.py` | ✅ |
| F5c | gaps: torn write, inventory counters, colosseum/pool/region groups, `find`, undo | `core/savefile.py`, `fixes/invcounters.py`, `db_er/event_flags_extra.json`, `cli.find`, `staging.undo` | ✅ |
| F6 | GUI: pywebview (WebView2) + JS↔engine bridge, 13 panels, i18n EN/PL, bridge audit + guard tests | `gui/`, `tests/bridge_audit.py` | ✅ v0.2 |
| F7 | packaging: `.exe` / shortcuts | `packaging/`, `tools/build_exe.cmd` | ✅ spec ready (build runs locally) |

## 9. Conventions

- identifiers in English, user-facing messages localized; the GUI has a language layer
  (`ui_lang`: EN by default, PL optional) — UI strings in `I18N`, engine messages translated by code;
- zero dependencies in `core`; everything else optional via extras in `pyproject.toml`;
- every write = GOLD + backup + atomic replace + verification;
- writing to the live save is blocked while the game runs (`_guard_game`, config `guard_live`);
- tests: `run_all.py` (behaviour), `smoke_cli.py` (every command), `bridge_audit.py` (GUI bridge);
  the GUI itself is verified in a real window via `--selftest`.

---

## 10. One-file build (PyInstaller)

`dist/rezur.exe` is a single self-contained file holding the GUI **and** the CLI.

- `packaging/entry.py` is the entry point: `rezur/__main__.py` uses relative imports and PyInstaller
  runs its script as a top-level module, so `from .cli import …` blows up there. `entry.py` does
  `from rezur.cli import main`.
- `packaging/rezur.spec` bundles `rezur/data/**` **and** `rezur/gui/web/**`. Without the web assets
  the window opens with no interface; `gui.app.run()` now detects the missing `index.html` and exits
  with code 2 and an explicit message instead of hanging.
- pywebview + pythonnet come in as hidden imports (`webview.platforms.edgechromium`, `clr`,
  `clr_loader`). **tkinter is not needed**: file dialogs are native WebView2 dialogs
  (`_native_dialog` in `gui/api.py`, with a tkinter fallback for dev runs).
- `cli.main()` forces UTF-8 on stdout/stderr: in a Windows pipe (or inside the frozen exe) Python
  falls back to the locale code page (cp1252) and **any Polish character crashed the process** —
  `rezur.exe list-fixes | head` must work.
- `tools/build_exe.cmd` builds; `tools/make_release_zip.py` assembles
  `dist/Rezur-v<version>-win64.zip` (`rezur.exe` + `START-REZUR.cmd` + `HOW-TO-RUN.txt`);
  the launcher, instructions and release notes are versioned in `packaging/release/`;
  `t_release_packaging_ready` (run_all) guards all of it, including the .cmd's CRLF/ASCII encoding.
