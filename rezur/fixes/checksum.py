"""Naprawy sum kontrolnych: MD5 sekcji + PlayerGameDataHash w slocie."""

from ..core import checksums
from .base import Fix, FixResult, iter_parsed_slots


class ChecksumFix(Fix):
    id = "checksums"
    title = "Sumy MD5 sekcji"
    description = "Przelicza MD5 sekcji, którym suma się nie zgadza (dane uznaje za prawdziwe)."

    def detect(self, save):
        return [s["name"] for s in save.section_md5_status() if not s["ok"]]

    def apply(self, save, targets=None):
        targets = self.detect(save) if targets is None else targets
        res = FixResult(self.id, targets=list(targets))
        fixed = set()
        for name in targets:
            entry = next(e for e in save.entries if e["name"] == name)
            if checksums.section_md5_ok(save.data, entry["off"], entry["size"]):
                res.skipped.append(f"{name}: suma już OK")
                continue
            checksums.write_section_md5(save.data, entry["off"], entry["size"])
            fixed.add(name)
            res.applied.append(f"{name}: MD5 przeliczony")
        return res


class PlayerHashFix(Fix):
    id = "playerhash"
    title = "PlayerGameDataHash w slocie"
    description = "Przepisuje wpisy hasha (level/staty/runy/ekwipunek) i przelicza MD5 slotu."

    def detect(self, save):
        out = []
        for i, slot, _prof in iter_parsed_slots(save):
            try:
                if not slot.player_hash_matches():
                    out.append(i)
            except Exception:  # noqa: BLE001
                continue
        return out

    def apply(self, save, targets=None):
        targets = self.detect(save) if targets is None else targets
        res = FixResult(self.id, targets=list(targets))
        for i in targets:
            slot = next(s for idx, s, _ in iter_parsed_slots(save) if idx == i)
            changed = checksums.refresh_player_hash(
                save.data,
                slot.abs_off,
                slot.offsets["pgd"],
                slot.offsets["item_ids"],
                slot.offsets["spells"],
                slot.tail["hash"],
            )
            save.touch_slot(i)
            res.applied.append(f"slot{i}: hash {'zaktualizowany' if changed else 'bez zmian'} (+MD5)")
        return res
