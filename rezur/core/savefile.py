"""SaveFile — otwarcie, sekcje, sloty, sumy, zapis atomowy z backupem."""

import os
import shutil
import time
from pathlib import Path

from . import bnd4, checksums
from .slots import Slot
from .reader import u64


class SaveFile:
    def __init__(self, path):
        self.path = Path(path)
        self.data = bytearray(self.path.read_bytes())
        if not bnd4.is_plaintext_bnd4(self.data):
            raise ValueError(
                "To nie jest jawny BND4 (PS4/zaszyfrowany save?) — Rezur obsługuje na razie PC .sl2."
            )
        self.entries = bnd4.parse_entries(self.data)
        # sekcje: 10 slotów + USER_DATA010 + USER_DATA011
        self.slot_entries = self.entries[:10]
        self.ud10_entry = next(e for e in self.entries if e["name"] == "USER_DATA010")
        self.ud11_entry = next(e for e in self.entries if e["name"] == "USER_DATA011")
        self.ud10_body = self.ud10_entry["off"] + 16
        self.ud11_body = self.ud11_entry["off"] + 16

    # ------------------------------------------------------------------ sekcje

    def section_md5_status(self):
        out = []
        for e in self.entries:
            ok = checksums.section_md5_ok(self.data, e["off"], e["size"])
            out.append({"name": e["name"], "ok": ok, "size": e["size"]})
        return out

    def steam_id(self):
        return u64(self.data, self.ud10_body + 0x04)

    def slots(self):
        return [Slot(self, i) for i in range(10)]

    def characters(self):
        """Roster + sparsowane sloty (te, co się dają). Lista dictów."""
        from . import profiles

        roster = profiles.roster(self)
        out = []
        for k in range(10):
            r = roster[k]
            entry = {"index": k, "profile": r, "slot": None}
            s = Slot(self, k)
            if not s.is_empty:
                s.parse(r["name"], r["level"])
                entry["slot"] = s
            out.append(entry)
        return out

    # ------------------------------------------------------------------ zapis

    def touch_slot(self, index):
        """Przelicza MD5 slotu po zmianach jego danych."""
        e = self.slot_entries[index]
        checksums.write_section_md5(self.data, e["off"], e["size"])

    def touch_ud10(self):
        checksums.write_section_md5(self.data, self.ud10_entry["off"], self.ud10_entry["size"])

    def touch_ud11(self):
        checksums.write_section_md5(self.data, self.ud11_entry["off"], self.ud11_entry["size"])

    def recalc_all_md5(self):
        for e in self.entries:
            checksums.write_section_md5(self.data, e["off"], e["size"])

    def write(self, backup_tag="rezurbak"):
        """Backup obok pliku (z rotacją wg config) + zapis atomowy. Zwraca ścieżkę backupu."""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bak = self.path.with_name(f"{self.path.name}.{backup_tag}-{stamp}")
        if self.path.exists():
            shutil.copy2(self.path, bak)
            self._prune_backups()
        tmp = self.path.with_name(self.path.name + ".tmp-rezur")
        with open(tmp, "wb") as f:
            f.write(bytes(self.data))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        return bak

    def _prune_backups(self):
        from .. import config

        keep = config.load().get("backup_retention", 0)
        if not keep:
            return
        baks = sorted(
            self.path.parent.glob(f"{self.path.name}.*bak-*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in baks[keep:]:
            try:
                old.unlink()
            except OSError:
                pass


def default_save_path():
    """Najnowszy ER0000.sl2 w %APPDATA%\\EldenRing\\<steamid>\\."""
    root = Path(os.path.expandvars(r"%APPDATA%\EldenRing"))
    cands = [p for p in root.glob("*/ER0000.sl2") if p.is_file()]
    if not cands:
        raise FileNotFoundError(f"nie znaleziono save'a w {root}")
    return max(cands, key=lambda p: p.stat().st_mtime)
