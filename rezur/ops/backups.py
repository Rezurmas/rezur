"""Backup manager: lista kopii obok pliku + przywracanie (z kopią bezpieczeństwa)."""

import re
import shutil
import time
from pathlib import Path

_STAMP = r"\d{8}-\d{6}"


def list_backups(save_path):
    p = Path(save_path)
    rx = re.compile(rf"^{re.escape(p.name)}\.[A-Za-z0-9_-]+-{_STAMP}$")
    out = []
    for f in p.parent.glob(f"{p.name}.*-*"):
        if not f.is_file() or not rx.match(f.name):
            continue
        st = f.stat()
        out.append({"name": f.name, "path": str(f), "size": st.st_size, "mtime": st.st_mtime})
    out.sort(key=lambda d: d["mtime"], reverse=True)
    return out


def restore(save_path, backup_path):
    save_path = Path(save_path)
    backup_path = Path(backup_path)
    if not backup_path.is_file():
        raise FileNotFoundError(backup_path)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    pre = save_path.with_name(f"{save_path.name}.prerestorebak-{stamp}")
    if save_path.exists():
        shutil.copy2(save_path, pre)
    shutil.copy2(backup_path, save_path)
    return {"restored_from": str(backup_path), "pre_restore_copy": str(pre)}
