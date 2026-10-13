"""Tekstowe raporty (konsola)."""

from ..core.profiles import roster
from ..core.slots import STATE_ACTIVE, Slot


def fmt_container(save):
    st = save.section_md5_status()
    ok = sum(1 for s in st if s["ok"])
    lines = [f"PLIK: {save.path}", f"SteamID: {save.steam_id()}"]
    bad = [s["name"] for s in st if not s["ok"]]
    if not bad:
        lines.append(f"KONTENER: {ok}/{len(st)} sum MD5 OK")
    else:
        lines.append(f"KONTENER: {ok}/{len(st)} sum MD5 OK — ZŁE: {', '.join(bad)}")
    return "\n".join(lines)


def fmt_characters(save):
    r = roster(save)
    lines = [
        f"{'slot':<4s} {'postać':<18s} {'lvl':>4s} {'czas':>8s} {'runy (pamięć)':>14s}  "
        f"{'mapa':<12s} {'torrent':<9s} {'patch':<7s}"
    ]
    for i in range(10):
        prof = r[i]
        s = Slot(save, i)
        if s.is_empty:
            continue
        if not s.parse(prof["name"], prof["level"]):
            lines.append(f"{i:<4d} {prof['name'] or '?':<18s}  !! nieparsowalny ({s.reason})")
            continue
        ch = s.character()
        h = ch["horse"]
        t = h["state_name"]
        if h["hp"] == 0 and h["state"] == STATE_ACTIVE:
            t += " !!"
        pv = ch["patch"]
        ptxt = f"b{pv['version']}" + ("  !!" if pv["is_latest"] == 0 else "")
        lines.append(
            f"{i:<4d} {ch['name']:<18s} {ch['level']:>4d} {ch['seconds']/3600:7.1f}h "
            f"{ch['runes_memory']:>14,d}  {ch['map_name']:<12s} {t:<9s} {ptxt:<7s}"
        )
    return "\n".join(lines)


def fmt_findings(findings):
    if not findings:
        return "USTALENIA: brak — save wygląda zdrowo."
    errs = sum(1 for f in findings if f.level == "error")
    warns = sum(1 for f in findings if f.level == "warning")
    infos = sum(1 for f in findings if f.level == "info")
    lines = [f"USTALENIA ({errs} błędów, {warns} ostrzeżeń, {infos} info):"]
    lines += [f.line() for f in findings]
    return "\n".join(lines)


def fmt_doctor(save, findings):
    return "\n".join(
        [
            fmt_container(save),
            "",
            "POSTACIE:",
            fmt_characters(save),
            "",
            fmt_findings(findings),
        ]
    )
