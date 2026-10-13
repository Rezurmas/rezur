# Rezur Saves Configurator

Konfigurator i naprawiacz save'ów **Elden Ring** (PC, Steam, `ER0000.sl2`):
diagnostyka błędów (m.in. słynna zawieszka Torrenta po Alt+F4), automatyczne
naprawy, kopiowanie postaci między slotami, patcher SteamID, raporty.
Zbudowany na zweryfikowanym od podstaw formacie zapisu (v250–261, 1.16-era).

**Status:** v0.1.0 — CLI działa (bez GUI; patrz `ARCHITECTURE.md` — plan warstwy web).

## Szybki start

```bash
cd C:\Users\Dawid\Desktop\ER-Save-Lab

python -m rezur info                      # postacie + stan kontenera
python -m rezur doctor                    # diagnostyka (czyta, nie pisze)
python -m rezur fix                       # co da się naprawić (dry-run)
python -m rezur fix --apply               # napraw wszystko (backup automatycznie)
python -m rezur fix --only torrent --apply
python -m rezur copy --from 2 --to 3      # kopiowanie postaci (dry-run)
python -m rezur copy --from 2 --to 3 --apply [--clear-source]
python -m rezur steamid --set 7656119xxxxxxxxxx [--apply]
python -m rezur list-fixes                # lista napraw
```

Bez `--save` narzędzie bierze najnowszy save z `%APPDATA%\EldenRing\*\ER0000.sl2`.

## Struktura

```
rezur/
  core/    format: bnd4, sloty, sumy (MD5 + PlayerDataHash), profile, SaveFile
  games/   rejestr gier (teraz: Elden Ring; struktura pod kolejne)
  diag/    silnik diagnostyki (checks → Finding z kodem i przypisaną naprawą)
  fixes/   rejestr napraw: torrent, checksums, playerhash, summary, weather, dlc
  ops/     kopiowanie postaci, patcher SteamID (+ plan: staty, itemy, flagi)
  report/  wyjście tekstowe i JSON
  api/     FastAPI pod przyszłe GUI (F6, placeholder)
  cli.py   python -m rezur
tests/     run_all.py — testy na kopiach prawdziwych save'ów
ARCHITECTURE.md   frontend/backend, przepływy, roadmapa
```

## Zasady bezpieczeństwa

- zapis **tylko** przez `SaveFile.write()`: backup obok pliku + zapis atomowy,
- CLI domyślnie w trybie dry-run; `--apply` wymagany do zapisu,
- przy działającej grze zapis jest blokowany,
- po naprawie automatyczna re-diagnostyka.

Szczegóły techniczne formatu i zweryfikowane pułapki: skill `elden-ring-save-repair`.
