"""Elden Ring (PC, Steam) — profil gry."""

from .base import GameSupport, expand, register


@register
class EldenRing(GameSupport):
    key = "eldenring"
    name = "Elden Ring"
    slot_count = 10
    slot_body = 0x280000
    slot_stride = 0x280010
    save_filename = "ER0000.sl2"

    def detect(self, data: bytes) -> bool:
        return data[:4] == b"BND4"

    def save_paths(self):
        root = expand(r"%APPDATA%\EldenRing")
        if not root.is_dir():
            return []
        return sorted(root.glob(f"*/{self.save_filename}"))
