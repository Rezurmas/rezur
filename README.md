# Rezur Saves Configurator

Konfigurator i naprawiacz save'ów **Elden Ring** (PC, Steam, `ER0000.sl2`):
diagnostyka błędów (m.in. słynna zawieszka Torrenta po Alt+F4), automatyczne
naprawy, kopiowanie postaci między slotami, patcher SteamID, raporty.
Zbudowany na zweryfikowanym od podstaw formacie zapisu (v250–261, 1.16-era).

**Status:** v0.1.0 — **backend kompletny** (CLI, bez GUI). Silnik: czytanie/pisanie
formatu, diagnostyka, naprawy, edycja statów/runów/itemów/flag, ekwipunek (dodaj/usuń/ilość/przenieś),
EQ postaci (22 gniazda), broń (poziom/affinity/AoW), czary, wygląd, teleport,
nazwane flagi świata (22 grupy: bossowie, mapy, cookbooki…; **nazwy po angielsku z lokacjami** —
japońskie nazwy z datamine'u przetłumaczone), masowe nadawanie kategorii,
kopiowanie/podmiana/czyszczenie slotów, transfer postaci. **Zaufanie do pliku:** kopie
GOLD (niekasowalne) + przypinane + rotacja, auto-kopiec `watch` przy grze, zapis atomowy
z weryfikacją kandydata przed podmianą, wersja patcha per postać z ostrzeżeniem `patch_old`.
**Świadomość banów:** `rezur risk` — skan danych niemożliwych (staty, ulepszenia broni,
ilości), znacznik „plik modyfikowany" (dziennik edycji) i gotowa droga powrotu do GOLD.
**Stany bezpieczne (staging):** `stage → pending → apply/discard` — edycje na kopii roboczej,
jeden backup przy zatwierdzeniu, historia operacji w `rezur log`.
**GUI (F6):** `python -m rezur gui` — natywne okno pywebview (WebView2) w stylu
engineering-series (czarna anoda + pomarańcz, LCD dot-matrix, zero suwaków): postacie,
doktor, staty, ekwipunek, założone, świat, czary, wygląd, teleport, ryzyko, kopie,
historia, ustawienia — każda edycja przez kopię roboczą, na dole pasek zmian.
**Wyszukiwanie na żywo:** lista filtruje się w trakcie pisania (ekwipunek, świat), a pola
dodawania itemu / czarów / zakładania podpowiadają pozycje z podświetlonym trafieniem.
**Język GUI:** domyślnie **angielski**; przełącznik `EN/PL` w nagłówku (pill) i w
Ustawieniach — zapisywany w configu (`ui_lang`), okno przeładowuje się samo.
Most JS↔silnik ma audyt: `python tests/bridge_audit.py` (każde wywołanie API na kopii save'a).

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
python -m rezur backups                   # kopie obok save'a (markery GOLD/PIN)
python -m rezur backups --gold            # niekasowalna kopia GOLD (powstaje raz na plik)
python -m rezur backups --pin NAZWA       # przypnij kopię (rotacja jej nie ruszy)
python -m rezur backups --restore NAZWA [--apply]
python -m rezur watch [--interval 600]    # auto-kopie: start gry + co interwał (Ctrl+C kończy)
python -m rezur watch --once              # jeden przebieg kontrolny
python -m rezur risk [--slot N] [--json]  # ryzyko online: dane niemożliwe + znacznik modyfikacji + powrót do GOLD
python -m rezur stage stats --slot 0 --set vigor=61   # edytuj w kopii roboczej (bez ryzyka)
python -m rezur pending [--diff] [--undo] # zmiany oczekujące: licznik, podgląd sekcji, cofnij ostatnią
python -m rezur apply                     # zatwierdź: 1 backup + 1 zapis + wpis w historii
python -m rezur discard                   # odrzuć: oryginał nietknięty
python -m rezur log [--json]              # historia operacji (dziennik edycji)
python -m rezur find "uchi" [--json]      # szukaj: itemy, flagi świata, łaski, lokacje
python -m rezur gui [--save PLIK]         # OKNO GUI (pywebview/WebView2), język: EN (domyślny) / PL
python -m rezur gui --selftest            # test dymny okna: most, 13 paneli, przełączenie EN→PL→EN (~30 s)
python -m rezur config                    # backup_retention / auto_doctor / guard_live / watch_interval / ui_lang
python -m rezur list-fixes                # lista napraw

# audyty (poza CLI):
python tests/bridge_audit.py              # most GUI↔silnik: 49 wywołań API na kopii save'a (izolowany config)
python tests/run_all.py                   # 47 testów na kopiach prawdziwych save'ów
python tests/smoke_cli.py                 # każda komenda CLI (132 wywołania)
```

Bez `--save` narzędzie bierze najnowszy save z `%APPDATA%\EldenRing\*\ER0000.sl2`.

## Struktura

```
rezur/
  core/    format: bnd4, sloty, sumy (MD5 + PlayerDataHash), profile, SaveFile, vault (GOLD/piny/rotacja),
           journal (dziennik edycji → znacznik „modyfikowany")
  risk.py  ryzyko online: dane niemożliwe (staty/ulepszenia/ilości) + znacznik + droga do GOLD
  staging.py  zmiany oczekujące: kopia robocza + manifest + migawki (stage/pending/apply/discard/undo)
  games/   rejestr gier (teraz: Elden Ring; struktura pod kolejne)
  diag/    silnik diagnostyki (checks → Finding z kodem i przypisaną naprawą)
  fixes/   rejestr napraw: torrent, checksums, playerhash, summary, weather, dlc, invcounters
  ops/     staty/runy/imie, itemy (gaitem+inventory: dodaj/usuń/ilość/przenieś/upgrade/affinity/AoW),
           EQ (22 gniazda), czary, wygląd, teleport, świat (nazwane flagi), masowe nadawanie,
           kopie/podmiana/czyszczenie slotów, SteamID, transfer JSON, backupy, watch (auto-kopie przy grze)
  report/  wyjście tekstowe i JSON
  gui/     okno pywebview: api.py (most JS↔silnik), app.py (shell + selftest), web/ (index.html+style.css+app.js, i18n EN/PL)
  api/     warstwa HTTP/JSON pod GUI (F6 — most do webview; placeholder)
  cli.py   python -m rezur
tests/     run_all.py — 47 testów na kopiach prawdziwych save'ów (+ weryfikacja krzyżowa z parserem referencyjnym)
           smoke_cli.py — przebieg KAŻDEJ komendy CLI (132 wywołania) na kopii save'a
           bridge_audit.py — audyt mostu GUI↔silnik: każde wywołanie API (49) na kopii save'a
ARCHITECTURE.md   frontend/backend, przepływy, roadmapa
```

## Zasady bezpieczeństwa

- zapis **tylko** przez `SaveFile.write()`: GOLD (raz na plik) + backup z rotacją + zapis atomowy;
  kandydat jest weryfikowany (BND4 + sumy MD5 wszystkich sekcji) ZANIM podmieni oryginał,
- kopie GOLD i przypięte (`--pin`) są niekasowalne — rotacja je omija,
- `rezur watch` robi auto-kopie przy starcie gry i co `watch_interval` sekund (weryfikacja odrzuca kopię zrobioną w trakcie zapisu gry),
- CLI domyślnie w trybie dry-run; `--apply` wymagany do zapisu,
- przy działającej grze zapis jest blokowany,
- każda udana modyfikacja dopisuje wpis do dziennika (`<save>.rezur-journal.json`);
  `rezur risk` pokazuje znacznik „plik modyfikowany" i dokładną komendę powrotu do GOLD,
- urwany plik (torn write) jest wykrywany przy wczytaniu z jasnym komunikatem i drogą do kopii,
- Rezur działa w 100% offline — zero połączeń sieciowych, zero telemetrii,
- po naprawie automatyczna re-diagnostyka; `doctor` flaguje też postacie ze starego patcha gry (`patch_old`).

## Pakowanie (.exe)

```cmd
python -m pip install pyinstaller
tools\build_exe.cmd          :: albo: python -m PyInstaller packaging\rezur.spec
:: wynik: dist\rezur.exe (jednoplikowy, bez instalatora; dane db_er wkompilowane)
```

Szczegóły techniczne formatu i zweryfikowane pułapki: skill `elden-ring-save-repair`.
