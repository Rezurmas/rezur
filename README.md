# Rezur Saves Configurator

Konfigurator i naprawiacz save'ów **Elden Ring** (PC, Steam, `ER0000.sl2`):
diagnostyka błędów (m.in. słynna zawieszka Torrenta po Alt+F4), automatyczne
naprawy, kopiowanie postaci między slotami, patcher SteamID, raporty.
Zbudowany na zweryfikowanym od podstaw formacie zapisu (v250–261, 1.16-era).

**Status:** v0.1.0 — **backend kompletny** (CLI, bez GUI). Silnik: czytanie/pisanie
formatu, diagnostyka, naprawy, edycja statów/runów/itemów/flag, ekwipunek (dodaj/usuń/ilość/przenieś),
EQ postaci (22 gniazda), broń (poziom/affinity/AoW), czary, wygląd, teleport,
nazwane flagi świata (22 grupy: bossowie, mapy, cookbooki…), masowe nadawanie kategorii,
kopiowanie/podmiana/czyszczenie slotów, transfer postaci, backupy z rotacją.
GUI (F6): lokalny webview (pywebview) — **start dopiero na GO**; plan w `ARCHITECTURE.md`.

## Szybki start

```bash
cd C:\Users\Dawid\Desktop\ER-Save-Lab

python -m rezur info                      # postacie + stan kontenera
python -m rezur doctor                    # diagnostyka (czyta, nie pisze)
python -m rezur fix                       # co da się naprawić (dry-run)
python -m rezur fix --apply               # napraw wszystko (backup automatycznie)
python -m rezur fix --only torrent --apply

python -m rezur stats --slot 0            # staty/runy/imie (dry-run)
python -m rezur stats --slot 0 --set vigor=60,mind=40 --runes 5000000 --apply
python -m rezur item --find uchigatana    # szukaj w bazie itemów
python -m rezur item --slot 0 --add "Uchigatana" --upgrade 5 --apply
python -m rezur item --slot 0 --remove "Uchigatana"           # usuń z ekwipunku
python -m rezur item --slot 0 --set-qty "Larval Tear=12"      # ustaw ilość
python -m rezur item --slot 0 --move "Larval Tear" --to storage
python -m rezur inventory --slot 0 --equipped                 # co założone
python -m rezur equipment --slot 0                            # pełne EQ (22 gniazda)
python -m rezur equip --slot 0 --item "Uchigatana" --at 0 --apply
python -m rezur unequip --slot 0 --at 0 --apply
python -m rezur item --slot 0 --set-upgrade "Uchigatana=10" --apply     # poziom broni
python -m rezur item --slot 0 --affinity "Uchigatana=Blood" --apply     # affinity
python -m rezur item --slot 0 --aow "Uchigatana=Bloody Slash" --apply   # Ash of War
python -m rezur spells --slot 0                                         # czary (--memorize/--forget/--clear)
python -m rezur appearance --slot 0                                     # gender / typ ciała / dar
python -m rezur teleport --slot 0 --to roundtable --apply               # teleport (limgrave/liurnia/altus)
python -m rezur world --groups                                          # 22 grupy nazwanych flag
python -m rezur world --slot 0 --group boss_defeat --filter Godrick     # podgląd stanu
python -m rezur world --slot 0 --group boss_defeat --set "Godrick" --state 1 --apply
python -m rezur unlock --slot 0 --what maps --apply                     # masowo: weapons/armors/…/tears
python -m rezur inventory --slot 0        # ekwipunek (--storage = skrzynia)
python -m rezur flags --slot 0 --get 600003
python -m rezur flags --slot 0 --set 600003:1 --apply
python -m rezur graces --list             # regiony łask
python -m rezur graces --slot 0 [--region "Limgrave"] --apply

python -m rezur copy --from 2 --to 3      # kopiowanie postaci (dry-run)
python -m rezur copy --from 2 --to 3 --apply [--clear-source]
python -m rezur swap --a 1 --b 2 --apply  # podmień postacie miejscami
python -m rezur clear --slot 3 --apply    # wyczyść slot
python -m rezur export --slot 0 --out lmfh.json
python -m rezur import --to 3 --in lmfh.json --apply
python -m rezur steamid --set 7656119xxxxxxxxxx [--apply]
python -m rezur backups                   # kopie obok save'a (+ --restore NAZWA [--apply])
python -m rezur config                    # backup_retention / auto_doctor / guard_live
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
  ops/     staty/runy/imie, itemy (gaitem+inventory: dodaj/usuń/ilość/przenieś/upgrade/affinity/AoW),
           EQ (22 gniazda), czary, wygląd, teleport, świat (nazwane flagi), masowe nadawanie,
           kopie/podmiana/czyszczenie slotów, SteamID, transfer JSON, backupy
  report/  wyjście tekstowe i JSON
  api/     warstwa HTTP/JSON pod GUI (F6 — most do webview; placeholder)
  cli.py   python -m rezur
tests/     run_all.py — 28 testów na kopiach prawdziwych save'ów (+ weryfikacja krzyżowa z parserem referencyjnym)
ARCHITECTURE.md   frontend/backend, przepływy, roadmapa
```

## Zasady bezpieczeństwa

- zapis **tylko** przez `SaveFile.write()`: backup obok pliku + zapis atomowy,
- CLI domyślnie w trybie dry-run; `--apply` wymagany do zapisu,
- przy działającej grze zapis jest blokowany,
- po naprawie automatyczna re-diagnostyka.

Szczegóły techniczne formatu i zweryfikowane pułapki: skill `elden-ring-save-repair`.
