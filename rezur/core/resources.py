"""Ścieżki do zasobów pakietu (bazy itemów, BST flag)."""

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def data_path(*parts):
    return DATA_DIR.joinpath(*parts)
