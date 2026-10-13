"""Naprawa desynchronizacji weather (area_id != bajt mapy)."""

import struct

from .base import Fix, FixResult, iter_parsed_slots


class WeatherFix(Fix):
    id = "weather"
    title = "Weather: area_id nie zgadza się z mapą"
    description = "Ustawia area_id pogody na bajt mapy postaci; przelicza MD5 slotu."

    def detect(self, save):
        out = []
        for i, slot, _prof in iter_parsed_slots(save):
            w = slot.weather()
            if w["area_id"] != w["map_area_byte"] or w["timer"] > 100000:
                out.append(i)
        return out

    def apply(self, save, targets=None):
        targets = self.detect(save) if targets is None else targets
        res = FixResult(self.id, targets=list(targets))
        for i in targets:
            slot = next(s for idx, s, _ in iter_parsed_slots(save) if idx == i)
            w = slot.weather()
            off = slot.abs_off + slot.tail["weather"]
            if w["area_id"] != w["map_area_byte"]:
                save.data[off : off + 2] = struct.pack("<H", w["map_area_byte"])
                save.touch_slot(i)
                res.applied.append(f"slot{i}: area_id {w['area_id']} -> {w['map_area_byte']} (+MD5)")
            elif w["timer"] > 100000:
                res.skipped.append(f"slot{i}: tylko timer podejrzany ({w['timer']}) — zostawiam")
        return res
