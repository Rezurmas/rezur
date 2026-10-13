"""Interfejs profilu gry — struktura pod kolejne tytuły (DS3, Sekiro, AC6...).

Gra dostarcza: wykrywanie pliku, ścieżki domyślne, stałe formatu. Reszta
warstw (core/diag/fixes/ops) jest wspólna.
"""

import os
from pathlib import Path

_GAMES = {}


def register(game):
    _GAMES[game.key] = game()
    return game


def get_game(key):
    return _GAMES.get(key)


def list_games():
    return sorted(_GAMES)


class GameSupport:
    key = "base"
    name = "Base"
    slot_count = 0
    slot_body = 0

    def detect(self, data: bytes) -> bool:
        raise NotImplementedError

    def save_paths(self):
        """Kandydaci na pliki save (najnowsze najpierw)."""
        return []

    def default_save(self):
        paths = [p for p in self.save_paths() if p.is_file()]
        if not paths:
            return None
        return max(paths, key=lambda p: p.stat().st_mtime)


def expand(path):
    return Path(os.path.expandvars(path))
