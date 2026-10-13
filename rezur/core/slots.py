"""Parser slotu postaci — zweryfikowany układ formatu v250-261 (1.16-era).

Slot = 0x280000 B, czytany SEKWENCYJNIE. Kotwica: blok statystyk znajdowany
po zawartości (level == suma 8 statystyk − 79, wymagane imię w UTF-16 pod
kotwicą+0x60). Łańcuch offsetów od kotwicy do Torrenta, potem ogon lokalizowany
bajtowym szukaniem SteamID64 (w tych wersjach ogon NIE leży na końcu slotu —
za nim jest do ~2.4 MB zapasu do 0x280000).

Ogon (slot-relative, bez przerw — zweryfikowane):
    PlayerCoordinates(0x3D) + 5be/5bf(2) + spawn(4) + b64(4)
    + temp(4, v>=65) + cb3(1, v>=66) + NetMan(4+0x20000)
    + weather(0xC) + time(0xC) + base_version(0x10) + steam_id(8)
    + ps5_activity(0x20) + dlc(0x32) + PlayerDataHash(0x80)
"""

import struct

from .reader import f32, i32, u8, u16, u32, u64, utf16, v3f, v4f

SLOT_BODY = 0x280000
HORSE_HP_OFF = 0x20
HORSE_STATE_OFF = 0x24
STATE_NAMES = {1: "INACTIVE", 3: "DEAD", 13: "ACTIVE"}
STATE_INACTIVE, STATE_DEAD, STATE_ACTIVE = 1, 3, 13

_NETMAN_SIZE = 4 + 0x20000
_COORDS_SIZE = 0x3D
_PROJ_MAX = 256
_REGIONS_MAX = 1024


class Slot:
    """Widok jednego slotu postaci. Czytanie z self.raw; pisanie przez SaveFile."""

    def __init__(self, save, index):
        self.save = save
        self.index = index
        entry = save.entries[index]
        self.entry = entry
        self.md5_off = entry["off"]
        self.abs_off = entry["off"] + 16
        self.raw = bytes(save.data[self.abs_off : self.abs_off + SLOT_BODY])
        self.offsets = {}      # nazwa -> offset slot-relative (PGD, ekwipunek, inventory, horse...)
        self.tail = {}         # offset slot-relative (steam, dlc, hash, coords, netman, weather...)
        self.ok = False
        self.reason = None
        self.torrent_ok = None

    # ------------------------------------------------------------- pola proste

    @property
    def version(self):
        return u32(self.raw, 0)

    @property
    def map_id(self):
        return u32(self.raw, 4)

    @property
    def play_time_ms(self):
        return u64(self.raw, 8)

    @property
    def is_empty(self):
        return self.version == 0

    def map_name(self, map_id=None):
        m = self.map_id if map_id is None else map_id
        d, c, b, a = m & 0xFF, (m >> 8) & 0xFF, (m >> 16) & 0xFF, (m >> 24) & 0xFF
        return f"m{a:02d}_{b:02d}_{c:02d}_{d:02d}"

    # ---------------------------------------------------------------- parsery

    def find_anchor(self, level, name):
        """Offset pola Vigor. level wymagany; name (jeśli podane) egzekwowane."""
        if level is None or not (1 <= level <= 8 * 99 - 79):
            return None
        pat = struct.pack("<I", level)
        at = self.raw.find(pat)
        while at >= 0:
            v = at - 44
            if v >= 0x40:
                stats = [u32(self.raw, v + k * 4) for k in range(8)]
                if all(1 <= x <= 99 for x in stats) and sum(stats) - 79 == level:
                    if not name or utf16(self.raw, v + 0x60) == name:
                        return v
            at = self.raw.find(pat, at + 1)
        return None

    def parse(self, profile_name=None, profile_level=None):
        """Pełny przelot slotu. profile_name/level z profilu (roster)."""
        if self.is_empty:
            self.reason = "empty"
            return False
        v = self.version
        anchor = self.find_anchor(profile_level, profile_name)
        if anchor is None:
            self.reason = "stat anchor not found"
            return False
        self.offsets["anchor_vigor"] = anchor
        pgd = anchor - 0x34
        self.offsets["pgd"] = pgd

        # --- łańcuch do Torrenta (rozmiary stałe; dwa pola dynamiczne z licznikami)
        o = pgd + 0x1B0
        self.offsets["sp_effects"] = o
        o += 0xD0
        self.offsets["equip_index"] = o
        o += 0x58
        self.offsets["active_weapons"] = o
        o += 0x1C
        self.offsets["item_ids"] = o
        o += 0x58
        self.offsets["ga_handles"] = o
        o += 0x58
        self.offsets["inventory_held"] = o
        o += 4 + 0xA80 * 12 + 4 + 0x180 * 12 + 8
        self.offsets["spells"] = o
        o += 0x74
        self.offsets["quick_items"] = o
        o += 0x8C
        self.offsets["gesture_wheel"] = o
        o += 0x18
        self.offsets["projectiles"] = o
        nproj = u32(self.raw, o)
        if not (0 <= nproj <= _PROJ_MAX):
            self.reason = f"projectiles count {nproj} out of range"
            return False
        o += 4 + nproj * 8
        self.offsets["armaments"] = o
        o += 0x9C
        self.offsets["physics"] = o
        o += 0xC
        self.offsets["face"] = o
        o += 0x12F
        self.offsets["storage"] = o
        o += 4 + 0x780 * 12 + 4 + 0x80 * 12 + 8
        self.offsets["gesture_gd"] = o
        o += 0x100
        self.offsets["regions"] = o
        nreg = u32(self.raw, o)
        if not (0 <= nreg <= _REGIONS_MAX):
            self.reason = f"regions count {nreg} out of range"
            return False
        o += 4 + nreg * 4
        self.offsets["horse"] = o
        if o + 0x28 > SLOT_BODY:
            self.reason = "horse offset out of slot"
            return False

        # --- ogon: szukanie SteamID64 (8 B LE)
        sidb = struct.pack("<Q", self.save.steam_id())
        i = self.raw.find(sidb)
        if i < 0:
            self.reason = "steam_id not found in slot"
            return False
        t = {}
        t["steam"] = i
        t["dlc"] = i + 0x28
        t["hash"] = i + 0x5A
        t["basever"] = i - 0x10
        t["time"] = i - 0x1C
        t["weather"] = i - 0x28
        t["netman"] = i - 0x2002C  # = weather − 0x20004 (steam − (weather+time+basever sizes))
        gap = 2 + 4 + 4 + (4 if v >= 65 else 0) + (1 if v >= 66 else 0)
        t["coords"] = t["netman"] - gap - _COORDS_SIZE
        if t["coords"] < 0x40 or t["hash"] + 0x80 > SLOT_BODY:
            self.reason = "tail out of bounds"
            return False
        self.tail = t

        hp = i32(self.raw, o + HORSE_HP_OFF)
        state = u32(self.raw, o + HORSE_STATE_OFF)
        self.torrent_ok = not (hp == 0 and state == STATE_ACTIVE)
        self.ok = True
        return True

    def parse_or_raise(self, profile_name=None, profile_level=None):
        if not self.parse(profile_name, profile_level):
            raise ValueError(f"slot{self.index}: {self.reason}")
        return self

    # ---------------------------------------------------------------- odczyty

    def pgd_name(self):
        return utf16(self.raw, self.offsets["pgd"] + 0x94)

    def pgd_level(self):
        return u32(self.raw, self.offsets["pgd"] + 0x60)

    def pgd_stats(self):
        p = self.offsets["pgd"]
        return [u32(self.raw, p + 0x34 + k * 4) for k in range(8)]

    def pgd_runes(self):
        return u32(self.raw, self.offsets["pgd"] + 0x64)

    def pgd_runes_memory(self):
        return u32(self.raw, self.offsets["pgd"] + 0x68)

    def pgd_gender(self):
        return u8(self.raw, self.offsets["pgd"] + 0xB6)

    def pgd_archetype(self):
        return u8(self.raw, self.offsets["pgd"] + 0xB7)

    def pgd_gift(self):
        return u8(self.raw, self.offsets["pgd"] + 0xBB)

    def item_ids(self):
        return list(struct.unpack_from("<22I", self.raw, self.offsets["item_ids"]))

    def active_weapon_slots(self):
        return list(struct.unpack_from("<7I", self.raw, self.offsets["active_weapons"]))

    def horse(self):
        h = self.offsets["horse"]
        hp = i32(self.raw, h + HORSE_HP_OFF)
        state = u32(self.raw, h + HORSE_STATE_OFF)
        return {
            "hp": hp,
            "state": state,
            "state_name": STATE_NAMES.get(state, f"?{state}"),
            "coords": v3f(self.raw, h),
            "map_id": u32(self.raw, h + 12),
        }

    def coordinates(self):
        c = self.tail["coords"]
        return {
            "xyz": v3f(self.raw, c),
            "map_id": u32(self.raw, c + 12),
            "angle": v4f(self.raw, c + 16),
            "unk_xyz": v3f(self.raw, c + 33),
        }

    def spawn(self):
        n = self.tail["netman"]
        v = self.version
        d = {
            "b5be": u8(self.raw, n - 15),
            "b5bf": u8(self.raw, n - 14),
            "spawn_point": u32(self.raw, n - 13),
            "game_man_0xb64": u32(self.raw, n - 9),
        }
        if v >= 65:
            d["temp_spawn"] = u32(self.raw, n - 5)
        if v >= 66:
            d["cb3"] = u8(self.raw, n - 1)
        return d

    def weather(self):
        w = self.tail["weather"]
        area = u16(self.raw, w)
        return {
            "area_id": area,
            "weather_type": u16(self.raw, w + 2),
            "timer": u32(self.raw, w + 4),
            "map_area_byte": (self.map_id >> 24) & 0xFF,
        }

    def time_of_day(self):
        t = self.tail["time"]
        return (u32(self.raw, t), u32(self.raw, t + 4), u32(self.raw, t + 8))

    def dlc_flags(self):
        d = self.tail["dlc"]
        return list(self.raw[d : d + 4]) + [sum(1 for x in self.raw[d + 4 : d + 50] if x)]

    def player_hash_matches(self):
        from .checksums import player_hash_matches

        return player_hash_matches(
            self.raw,
            self.offsets["pgd"],
            self.offsets["item_ids"],
            self.offsets["spells"],
            self.tail["hash"],
        )

    def character(self):
        """Skrót postaci do raportów."""
        return {
            "slot": self.index,
            "version": self.version,
            "name": self.pgd_name(),
            "level": self.pgd_level(),
            "stats": self.pgd_stats(),
            "runes": self.pgd_runes(),
            "runes_memory": self.pgd_runes_memory(),
            "seconds": self.play_time_ms // 1000,
            "map_id": self.map_id,
            "map_name": self.map_name(),
            "horse": self.horse(),
        }
