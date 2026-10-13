## Rezur v0.2.1 — one file, no Python

### Download

**`Rezur-v0.2.1-win64.zip`** — in the Assets section below.

1. unpack the ZIP anywhere (e.g. `C:\Rezur`),
2. double-click **`START-REZUR.cmd`** → the configurator window opens.

Windows SmartScreen may warn once (the exe is unsigned): *More info → Run anyway*. The same
instructions, in English and Polish, are in `HOW-TO-RUN.txt` inside the ZIP.

### What you get

- one self-contained `rezur.exe` holding **both** the GUI (13 panels) and the CLI (~34 subcommands)
  — `rezur.exe gui`, `rezur.exe doctor`, `rezur.exe fix --apply`, `rezur.exe --help` …
- automatic save detection (`%APPDATA%\EldenRing\*\ER0000.sl2`), **100% offline**
- every write: GOLD copy once per file → tagged backup with rotation → atomic replace; the new file
  is verified (BND4 + every section MD5) **before** the original is touched
- writes are blocked while `eldenring.exe` is running; GUI edits land in a work copy first

### New in 0.2.1

- **one-file Windows build** — PyInstaller `--onefile`, bundled data tables and GUI assets, so the
  window cannot come up blank; native WebView2 file dialogs (tkinter no longer needed)
- **`stage` honours `--save` given after the inner command** — `rezur stage stats --save FILE …`
  now stages that file (the flag used to be swallowed by the staging layer, which then fell back to
  the default save and could even hand the inner `--save` to the original file)
- **CLI survives Windows pipes** — output is forced to UTF-8; every command usable from `cmd`,
  PowerShell and Git Bash (`rezur.exe list-fixes | head` works)
- **repo cleanup** — English `README.md`/`ARCHITECTURE.md` with a screenshot gallery, MIT `LICENSE`,
  release tooling (`tools/make_release_zip.py`, `packaging/release/`), and the stale experimental
  HTTP bridge (`rezur/api/`) removed
- verified by **49 behaviour tests**, **135 CLI smoke invocations**, **51 GUI-bridge calls** and a
  live-window selftest run against the packaged exe

### Highlights

- **diagnostics + repairs** — checksums, player hash, profile summary, weather/region desync,
  inventory counters, and the **Torrent hang** after a crash
- **editing** — stats / runes / name, items (quantity, move, upgrade, affinity, Ash of War), the
  22-slot loadout, spells (213-spell catalogue with badges), appearance, teleport, ~4 200 named
  world flags with locations
- **trust features** — staging-first edits with undo, edit journal + online-risk scan with a return
  path to GOLD, `watch` auto-backups, pinned backups
- **GUI** — English by default (Polish optional), live search everywhere, no sliders

From source instead: `git clone https://github.com/Rezurmas/rezur.git && python -m rezur gui`
(Python 3.10+; the GUI additionally needs pywebview + the WebView2 runtime — `pip install -e ".[gui]"`).
