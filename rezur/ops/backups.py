"""Backup manager — cienka warstwa nad core.vault (API dla CLI i importów)."""

from ..core.vault import (
    GOLD_TAG,
    ensure_gold,
    gold_backup,
    is_pinned,
    list_backups,
    load_pins,
    prune,
    restore,
    set_pin,
)

__all__ = [
    "GOLD_TAG",
    "ensure_gold",
    "gold_backup",
    "is_pinned",
    "list_backups",
    "load_pins",
    "prune",
    "restore",
    "set_pin",
]

