"""Watcher gry: auto-kopia przy starcie Elden Ring i co interwał, gdy działa.

    run_once(save, interval)   — jeden przebieg kontrolny (testy/cron)
    run_loop(save, interval)   — pętla do Ctrl+C

Kopie: launchbak-* (raz na start gry), runbak-* (co interwał w trakcie gry).
Kandydat jest weryfikowany (BND4 + MD5) — jeśli gra właśnie pisze plik,
kopia jest pomijana zamiast zapisu uszkodzonego stanu.
"""

import shutil
import subprocess
import time
from pathlib import Path

from ..core import vault
from ..core.savefile import verify_save_bytes

GAME_EXE = "eldenring.exe"
POLL_S = 15
LAUNCH_WINDOW_S = 900  # 15 min — okno "świeżego startu" dla trybu --once


def game_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return GAME_EXE.lower() in out.lower()


def _newest_tagged(save_path, tag_part):
    hits = [b for b in vault.list_backups(save_path) if tag_part in b["tag"]]
    return max(hits, key=lambda b: b["mtime"], default=None)


def make_backup(save_path, tag):
    """Kopia z weryfikacją. Zwraca (ścieżka|None, uwaga|None)."""
    from .. import config

    p = Path(save_path)
    vault.ensure_gold(p)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = p.with_name(f"{p.name}.{tag}-{stamp}")
    shutil.copy2(p, dst)
    try:
        verify_save_bytes(dst.read_bytes())
    except ValueError:
        dst.unlink(missing_ok=True)
        return None, "plik w trakcie zapisu przez grę — kopia pominięta"
    vault.prune(p, config.load().get("backup_retention", 0))
    return str(dst), None


def run_once(save_path, interval=600):
    """Jeden przebieg: start gry → launchbak; potem runbak co `interval` sekund."""
    if not game_running():
        return {"running": False, "made": None, "reason": "gra nie działa"}
    lb = _newest_tagged(save_path, "launchbak")
    if lb is None or (time.time() - lb["mtime"]) > LAUNCH_WINDOW_S:
        made, note = make_backup(save_path, "launchbak")
        return {"running": True, "made": made, "reason": note or "start gry"}
    rb = _newest_tagged(save_path, "runbak")
    if rb is None or (time.time() - rb["mtime"]) >= interval:
        made, note = make_backup(save_path, "runbak")
        return {"running": True, "made": made, "reason": note or "interwał"}
    return {"running": True, "made": None, "reason": "świeża kopia już jest"}


def run_loop(save_path, interval=600, log=print, poll=POLL_S):
    """Pętla watch: blokuje do Ctrl+C. Kopie robi 'on change', nie notorycznie."""
    was = False
    log(f"watch: {save_path}")
    log(f"  start gry → launchbak; potem runbak co {interval}s; poll {poll}s; Ctrl+C kończy")
    try:
        while True:
            running = game_running()
            now = time.strftime("%H:%M:%S")
            if running and not was:
                made, note = make_backup(save_path, "launchbak")
                log(f"[{now}] gra wystartowała → {made or note}")
            elif running:
                rb = _newest_tagged(save_path, "runbak")
                if rb is None or (time.time() - rb["mtime"]) >= interval:
                    made, note = make_backup(save_path, "runbak")
                    log(f"[{now}] gra działa → {made or note}")
            elif was:
                log(f"[{now}] gra zamknięta — czekam na start.")
            was = running
            time.sleep(poll)
    except KeyboardInterrupt:
        log("watch: zakończony (Ctrl+C).")
    return 0
