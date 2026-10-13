"""Kopiowanie postaci slot↔slot: dane 0x280000 + profil 0x24C + MD5.

--clear-source (opcja): po skopiowaniu zeruje slot źródłowy + jego profil
(elekt "przeniesienia"). Zweryfikowane na żywym savie (annesee -> slot 0).
"""

import struct

from ..core import profiles as P
from ..core.checksums import EMPTY_SLOT_MD5
from ..core.reader import utf16


def _slot_summary_name(save, idx):
    return P.summary_bytes(save, idx)[:34].decode("utf-16-le", "ignore").split("\x00")[0]


def copy_character(save, src, dst, clear_source=False):
    """Kopiuje na żywym SaveFile (mutuje). Zwraca raport (dict)."""
    if src == dst or not (0 <= src <= 9 and 0 <= dst <= 9):
        raise ValueError("złe sloty (0-9, różne)")
    se = save.slot_entries[src]
    de = save.slot_entries[dst]
    src_body = se["off"] + 16
    dst_body = de["off"] + 16
    src_version = struct.unpack_from("<I", save.data, src_body)[0]
    if src_version == 0:
        raise ValueError(f"slot{src} jest pusty — nie ma czego kopiować")

    src_name = _slot_summary_name(save, src)
    dst_name = _slot_summary_name(save, dst)

    # 1. dane slotu
    save.data[dst_body : dst_body + 0x280000] = save.data[src_body : src_body + 0x280000]
    save.touch_slot(dst)

    # 2. profil
    P.write_summary(save, dst, P.summary_bytes(save, src))

    # 3. opcjonalne czyszczenie źródła
    if clear_source:
        save.data[src_body : src_body + 0x280000] = b"\x00" * 0x280000
        save.data[se["off"] : se["off"] + 16] = EMPTY_SLOT_MD5
        P.zero_summary(save, src)
        save.touch_ud10()

    return {
        "from": src,
        "to": dst,
        "from_name": src_name,
        "to_name_before": dst_name,
        "clear_source": clear_source,
    }


def copy_character_file(path, src, dst, clear_source=False, apply=False):
    """Wariant plikowy: suchy przebieg domyślnie; apply=True zapisuje (backup+atomic)."""
    from ..core.savefile import SaveFile

    sf = SaveFile(path)
    report = {"path": str(path), "from": src, "to": dst}
    # dry-run: tylko odczyt nagłówków
    se = sf.slot_entries[src]
    de = sf.slot_entries[dst]
    src_version = struct.unpack_from("<I", sf.data, se["off"] + 16)[0]
    if src_version == 0:
        raise ValueError(f"slot{src} jest pusty — nie ma czego kopiować")
    report["from_name"] = _slot_summary_name(sf, src)
    report["from_level"] = P.roster(sf)[src]["level"]
    report["to_name"] = _slot_summary_name(sf, dst) or "(pusty)"
    report["to_level"] = P.roster(sf)[dst]["level"]
    if not apply:
        report["applied"] = False
        return report

    res = copy_character(sf, src, dst, clear_source=clear_source)
    report.update(res)
    report["backup"] = str(sf.write(backup_tag="copybak"))
    report["applied"] = True
    # weryfikacja
    from ..core.savefile import SaveFile as SF

    chk = SF(path)
    report["verify_md5_ok"] = all(s["ok"] for s in chk.section_md5_status())
    report["verify_to_name"] = _slot_summary_name(chk, dst)
    return report
