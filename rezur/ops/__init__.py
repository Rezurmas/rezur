"""Ops — operacje wyższego rzędu na save'ach (kopiowanie, steamid, transfer).

Planowane (roadmapa):
    F2: ops/stats.py     — edycja statystyk/runów/imienia (z walidacją levelu)
    F3: ops/items.py     — dodawanie przedmiotów (gaitem + inventory, baza db_er)
    F4: ops/flags.py     — event flags, łaski, bossy (bitowe flagi świata)
    F5: ops/transfer.py  — import/eksport postaci między save'ami (JSON/plik)
"""

from .copy_slot import copy_character, copy_character_file  # noqa: F401
from .steamid import change_steam_id  # noqa: F401
