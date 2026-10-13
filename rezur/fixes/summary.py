"""Naprawa profilu na ekranie wyboru (USER_DATA_10) — rebuild z danych slotu.

Wykrywa: zajęty slot z pustym profilem / niezgodnym imieniem lub level.
Naprawia: pełny rebuild wpisu profilu (imię, level, czas, runy, mapa, twarz,
ekwipunek, typ ciała/klasa/prezent) z danych slotu + przeliczenie MD5 UD10.
"""

from ..core import profiles as P
from .base import Fix, FixResult, iter_parsed_slots


class SummaryFix(Fix):
    id = "summary"
    title = "Profil postaci (ekran wyboru)"
    description = "Odbudowuje wpis profilu z danych slotu i przelicza MD5 USER_DATA_10."

    def detect(self, save):
        out = []
        for i, slot, prof in iter_parsed_slots(save):
            name = slot.pgd_name()
            level = slot.pgd_level()
            if not prof["name"] or prof["name"] != name or prof["level"] != level:
                out.append(i)
        return out

    def apply(self, save, targets=None):
        targets = self.detect(save) if targets is None else targets
        res = FixResult(self.id, targets=list(targets))
        for i in targets:
            slot = next(s for idx, s, _ in iter_parsed_slots(save) if idx == i)
            cur = P.summary_bytes(save, i)
            new = P.summary_from_slot(save, slot, cur)
            if new == cur:
                res.skipped.append(f"slot{i}: profil już zgodny")
                continue
            P.write_summary(save, i, new)
            res.applied.append(
                f"slot{i}: profil -> '{slot.pgd_name()}' lvl={slot.pgd_level()} (+MD5 UD10)"
            )
        return res
