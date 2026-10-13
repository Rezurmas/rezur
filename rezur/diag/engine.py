"""Silnik diagnostyki — zbiera ustalenia (Finding) o stanie save'a.

Ustalenia mają poziom: 'error' (gra nie wczyta / poważne), 'warning'
(do naprawy, ale gra sobie radzi nieidealnie) oraz 'info'. Każde może nieść
'fix' = id naprawy, która to rozwiązuje (rejestr w warstwie fixes).
"""

import struct
from dataclasses import dataclass

from ..core.profiles import roster
from ..core.slots import STATE_ACTIVE, Slot

ERROR, WARNING, INFO = "error", "warning", "info"


@dataclass
class Finding:
    level: str
    code: str
    message: str
    slot: int | None = None
    fix: str | None = None

    def line(self):
        where = f"slot{self.slot} " if self.slot is not None else ""
        f = f"  [fix: {self.fix}]" if self.fix else ""
        return f"[{self.level:7s}] {where}{self.message}{f}"


def run_diagnostics(save, expect_steamid=None):
    findings = []

    # --- kontener: sumy sekcji
    for s in save.section_md5_status():
        if not s["ok"]:
            findings.append(
                Finding(ERROR, "md5_bad", f"{s['name']}: suma MD5 sekcji się nie zgadza", fix="checksums")
            )

    # --- SteamID (opcjonalnie oczekiwany, np. nazwa folderu)
    if expect_steamid is not None and save.steam_id() != expect_steamid:
        findings.append(
            Finding(ERROR, "steamid_mismatch", f"SteamID w save = {save.steam_id()}, oczekiwany {expect_steamid}")
        )

    r = roster(save)
    for i in range(10):
        slot = Slot(save, i)
        if slot.is_empty:
            if any(slot.raw):
                findings.append(
                    Finding(INFO, "orphan_data", "pusty slot, ale zawiera niezerowe resztki danych", slot=i)
                )
            continue

        prof = r[i]
        if not slot.parse(prof["name"], prof["level"]):
            findings.append(
                Finding(ERROR, "slot_unparsed", f"nie da się sparsować slotu: {slot.reason}", slot=i)
            )
            continue

        ch = slot.character()

        # profil vs dane slotu
        if prof["name"] and prof["name"] != ch["name"]:
            findings.append(
                Finding(WARNING, "summary_name_mismatch",
                        f"profil='{prof['name']}', w slocie='{ch['name']}'", slot=i, fix="summary")
            )
        elif not prof["name"]:
            findings.append(
                Finding(WARNING, "summary_empty", "slot zajęty, a profil na ekranie wyboru pusty",
                        slot=i, fix="summary")
            )
        if prof["level"] != ch["level"]:
            findings.append(
                Finding(WARNING, "summary_level_mismatch",
                        f"profil lvl={prof['level']}, w slocie lvl={ch['level']}", slot=i, fix="summary")
            )
        if abs(prof["seconds"] - ch["seconds"]) > 300:
            findings.append(
                Finding(INFO, "summary_time_drift",
                        f"czas: profil {prof['seconds']}s vs slot {ch['seconds']}s "
                        "(drobny rozjazd to norma w save'ach pisanych przez grę)", slot=i)
            )

        # Torrent
        h = slot.horse()
        if h["hp"] == 0 and h["state"] == STATE_ACTIVE:
            findings.append(
                Finding(ERROR, "torrent_bug",
                        "Torrent: hp=0 i stan ACTIVE — zawieszka na ekranie ładowania",
                        slot=i, fix="torrent")
            )

        # weather
        w = slot.weather()
        if w["area_id"] != w["map_area_byte"]:
            findings.append(
                Finding(WARNING, "weather_mismatch",
                        f"weather area={w['area_id']} vs mapa={w['map_area_byte']}",
                        slot=i, fix="weather")
            )
        if w["timer"] > 100000:
            findings.append(
                Finding(WARNING, "weather_timer", f"weather timer={w['timer']} (podejrzanie duży)",
                        slot=i, fix="weather")
            )

        # DLC — bajty nieużywane
        d = slot.dlc_flags()
        if d[4] > 0:
            findings.append(
                Finding(WARNING, "dlc_unused", f"DLC: {d[4]} niezerowych bajtów w polach nieużywanych "
                                                "(mogą blokować wczytanie)", slot=i, fix="dlc")
            )

        # BaseVersion — postać zapisana pod starszym patchem gry
        bv = slot.base_version()
        if bv["is_latest"] == 0:
            findings.append(
                Finding(WARNING, "patch_old",
                        f"postać ze starszego patcha gry (base={bv['version']}, slot=v{ch['version']}) — "
                        "wczytaj ją raz na aktualnym patchu, żeby gra ją odświeżyła; "
                        "stare postacie potrafią crashować grę i edytory", slot=i)
            )

        # PlayerGameDataHash
        try:
            if not slot.player_hash_matches():
                findings.append(
                    Finding(WARNING, "player_hash_mismatch",
                            "PlayerGameDataHash nie zgadza się z danymi (level/staty/runy/ekwipunek)",
                            slot=i, fix="playerhash")
                )
        except (struct.error, IndexError):
            findings.append(Finding(INFO, "player_hash_unparsed", "nie udało się sprawdzić hasha", slot=i))

    return findings
