"""Zmiany oczekujące (staging) — edytuj brudnopis, zatwierdź jednym zapisem.

Model:
    kopia robocza:  %APPDATA%\\rezur\\staging\\<klucz>.sl2
    manifest:       %APPDATA%\\rezur\\staging\\<klucz>.json
        {save, created, orig_size, orig_mtime, ops: [{ts, op, summary}]}

Przepływ: `rezur stage <komenda edycji> …` → edycje lądują w kopii roboczej
(oryginał NIETKNIĘTY) → `rezur pending` (licznik + podgląd różnic) →
`rezur apply` (jeden backup + jeden zapis + wpis w dzienniku) albo
`rezur discard` (kasuj brudnopis, oryginał zostaje jak był).

To jest także model stanu dla GUI: „zmiany oczekujące + [Zapisz / Odrzuć / Wróć]".
Nieudany zapis NIE kasuje zmian — brudnopis zostaje do poprawy.
"""

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

from . import config


def staging_dir():
    d = config.config_dir() / "staging"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _key(save_path):
    return hashlib.md5(str(Path(save_path).resolve()).lower().encode("utf-8")).hexdigest()[:16]


def work_path(save_path):
    return staging_dir() / f"{_key(save_path)}.sl2"


def manifest_path(save_path):
    return staging_dir() / f"{_key(save_path)}.json"


def is_work_path(path):
    """Czy to kopia robocza stagingu (zapis wtedy = bez backupu i dziennika)."""
    try:
        return Path(path).resolve().parent == staging_dir().resolve()
    except OSError:
        return False


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(save_path):
    p = manifest_path(save_path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_manifest(save_path, man):
    p = manifest_path(save_path)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(man, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def begin(save_path):
    """Zaczyna (albo wznawia) staging dla pliku. Zwraca ścieżkę kopii roboczej."""
    save_path = Path(save_path)
    if not save_path.is_file():
        raise FileNotFoundError(save_path)
    work = work_path(save_path)
    man = load_manifest(save_path)
    if man and work.is_file():
        return work
    if not work.is_file():
        shutil.copy2(save_path, work)
    st = save_path.stat()
    _save_manifest(save_path, {
        "save": str(save_path),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "orig_size": st.st_size,
        "orig_mtime": st.st_mtime,
        "ops": [],
    })
    return work


def record_op(save_path, op, summary):
    """Dopisuje zmianę oczekującą do manifestu. Zwraca licznik."""
    man = load_manifest(save_path)
    if man is None:
        begin(save_path)
        man = load_manifest(save_path)
    man["ops"].append({"ts": time.strftime("%H:%M:%S"), "op": op, "summary": summary})
    _save_manifest(save_path, man)
    return len(man["ops"])


def op_count(save_path):
    man = load_manifest(save_path)
    return len(man["ops"]) if man else 0


def original_changed(save_path):
    """Czy oryginał zmienił się od rozpoczęcia stagingu (np. gra zapisała)."""
    man = load_manifest(save_path)
    if not man:
        return False
    p = Path(save_path)
    if not p.is_file():
        return True
    st = p.stat()
    return st.st_size != man.get("orig_size") or abs(st.st_mtime - man.get("orig_mtime", 0)) > 1.0


def discard(save_path):
    """Kasuje brudnopis (bez dotykania oryginału). Zwraca {ops, removed}."""
    n = op_count(save_path)
    removed = False
    for p in (work_path(save_path), manifest_path(save_path)):
        if p.is_file():
            p.unlink()
            removed = True
    return {"ops": n, "removed": removed}


def apply(save_path, backup_tag="stagebak", force=False):
    """Zatwierdza brudnopis na oryginale.

    Kolejność: weryfikacja brudnopisu → GOLD → backup oryginału → atomowy zapis
    → wpis w dzienniku → skasowanie stagingu. Każdy błąd ZOSTAWIA zmiany.
    """
    from .core import journal, vault
    from .core.savefile import SaveFile, verify_save_bytes

    save_path = Path(save_path)
    man = load_manifest(save_path)
    work = work_path(save_path)
    if not man or not work.is_file():
        raise ValueError("brak zmian oczekujących")
    if not force and original_changed(save_path):
        raise RuntimeError(
            "oryginał zmienił się od rozpoczęcia stagingu (gra zapisała?) — "
            "odrzuć i zacznij od nowa, albo użyj --force"
        )
    data = work.read_bytes()
    verify_save_bytes(data)  # brudnopis musi być zdrowy, ZANIM ruszymy oryginał

    bak = None
    if save_path.exists():
        vault.ensure_gold(save_path)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bak = save_path.with_name(f"{save_path.name}.{backup_tag}-{stamp}")
        shutil.copy2(save_path, bak)
        vault.prune(save_path, config.load().get("backup_retention", 0))

    tmp = save_path.with_name(save_path.name + ".tmp-rezur")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, save_path)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    journal.record(save_path, backup_tag, note=Path(bak).name if bak else None)
    n = op_count(save_path)
    discard(save_path)

    sf = SaveFile(save_path)
    st = sf.section_md5_status()
    return {
        "backup": str(bak) if bak else None,
        "ops": n,
        "md5_ok": sum(1 for s in st if s["ok"]),
        "md5_total": len(st),
    }
