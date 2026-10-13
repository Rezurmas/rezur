## Rezur v0.2.0 — CLI + GUI in one file

### Download

**`Rezur-v0.2.0-win64.zip`** — in the Assets section below. No Python required.

1. unpack the ZIP anywhere (e.g. `C:\Rezur`),
2. double-click **`START-REZUR.cmd`** → the configurator window opens.

SmartScreen may warn once (the exe is unsigned): *More info → Run anyway*. Full instructions,
in English and Polish, are in `HOW-TO-RUN.txt` inside the ZIP.

### What you get

- one self-contained `rezur.exe` holding **both** the GUI (13 panels) and the CLI (~34 subcommands)
  — `rezur.exe gui`, `rezur.exe doctor`, `rezur.exe fix --apply`, `rezur.exe --help` …
- automatic save detection (`%APPDATA%\EldenRing\*\ER0000.sl2`), **100% offline**
- every write: GOLD copy once per file → tagged backup with rotation → atomic replace, and the new
  file is verified (BND4 + every section MD5) **before** the original is touched
- writes are blocked while `eldenring.exe` is running; GUI edits land in a work copy first

### Highlights

- **diagnostics + repairs** — checksums, player hash, profile summary, weather/region desync,
  inventory counters, and the **Torrent hang** bug after a crash
- **editing** — stats / runes / name, items (quantity, move, upgrade, affinity, Ash of War), the
  22-slot loadout, spells (213-spell catalogue with badges), appearance, teleport, ~4 200 named
  world flags with locations
- **trust features** — staging-first edits with undo, edit journal + online-risk scan with a return
  path to GOLD, `watch` auto-backups, pinned backups
- **GUI** — English by default (Polish optional), live search everywhere, no sliders
- verified by 48 behaviour tests, 135 CLI smoke invocations, 51 GUI-bridge calls and a live-window
  selftest

From source instead: `git clone https://github.com/Rezurmas/rezur.git && python -m rezur gui`
(Python 3.10+; the GUI additionally needs pywebview + the WebView2 runtime).
