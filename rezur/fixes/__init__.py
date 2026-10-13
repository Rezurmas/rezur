"""Fixes — rejestr napraw. Każda naprawa: detect() (co naprawić) + apply() (zrób).

Naprawy piszą wyłącznie przez SaveFile (patch danych + touch MD5 sekcji).
"""

from .base import Fix, FixResult, iter_parsed_slots  # noqa: F401
from .torrent import TorrentFix
from .checksum import ChecksumFix, PlayerHashFix
from .summary import SummaryFix
from .weather import WeatherFix
from .dlc import DLCFix

_FIXES = [TorrentFix(), ChecksumFix(), PlayerHashFix(), SummaryFix(), WeatherFix(), DLCFix()]
_REGISTRY = {f.id: f for f in _FIXES}


def list_fixes():
    return list(_FIXES)


def get_fix(fix_id):
    return _REGISTRY.get(fix_id)


def apply_fixes(save, fix_ids=None, dry_run=False):
    """Zbiera targetsy i (opcjonalnie) aplikuje. Zwraca listę FixResult."""
    results = []
    for f in _FIXES:
        if fix_ids and f.id not in fix_ids:
            continue
        targets = f.detect(save)
        if not targets:
            continue
        if dry_run:
            results.append(FixResult(f.id, targets=list(targets)))
        else:
            results.append(f.apply(save, targets))
    return results
