# ER Save Lab — plan projektu

> **Note:** this is the internal project plan and it is kept in Polish. The public docs
> (`README.md`, `ARCHITECTURE.md`) are in English. / *Plan wewnętrzny — po polsku; dokumentacja
> publiczna (README, ARCHITECTURE) jest po angielsku.*

**Cel:** własne narzędzie do czytania i modyfikowania plików zapisu Elden Ring (`ER0000.sl2`),
zbudowane od zera, w Pythonie, z pełnym zrozumieniem formatu — nie "magic box", tylko kod,
który oboje rozumiemy linia po linii.

**Root projektu:** `%USERPROFILE%\Desktop\ER-Save-Lab\`

```
ER-Save-Lab/
├── PLAN.md            ← ten plik
├── backups/           ← kopie save'ów (timestamped, przed każdą operacją)
├── references/        ← 6 sklonowanych repozytoriów (materiał do nauki, read-only)
├── erlab/             ← NASZE narzędzie (do zbudowania, fazy F1+)
│   └── data/          ← bazy itemów (skopiowane JSON-y z sl2-analyzer)
├── tests/             ← testy na kopiach save'a
└── scratch/           ← eksperymenty
```

---

## 0. Stan wyjściowy (F0 — zrobione 2026-10-13)

- Sklonowane referencje (6 repo, ~550 MB) — patrz sekcja 2.
- Backup twojego save'a: `backups/ER0000_backup_20261013_1911.sl2`.
- **Twój save jest zdrowy** — wszystkie 12 MD5 OK, wszystkie 3 postacie przechodzą kontrolę
  `level == suma(8 statystyk) − 79`:

| slot | imię | lvl | czas gry | runy (pamięć) | format (version) |
|---|---|---|---|---|---|
| 0 | `let me fight him` | 93 | 71,7 h | 3 403 551 | 250 |
| 1 | `hajime` | 36 | 12,8 h | 211 158 | 252 |
| 2 | `annesee` | 54 | 13,9 h | 494 950 | 261 |
| 3–9 | puste | | | | |

Ścieżka save'a: `%APPDATA%\EldenRing\76561198000000000\ER0000.sl2` (SteamID64 = nazwa folderu).

### F0.5 — zrobione przy okazji (2026-10-13, wieczór)

- `tools/fix_torrent.py` — naprawa zawieszki na ładowaniu (Torrent `hp=0` + `state=ACTIVE` → `DEAD`):
  jeden bajt + MD5 slotu. Uratowana postać annesee (save zjechany przez Alt+F4).
- `tools/copy_slot.py` — kopiowanie postaci slot↔slot: dane 0x280000 + profil 0x24C + oba MD5;
  `--clear-source` = efekt przeniesienia. Przetestowane na 3 scenariuszach, użyte na żywym savie.
- Zweryfikowany pełny układ slotu v250-261: **ogon slotu NIE leży na końcu** — dane kończą się tam,
  gdzie się kończą, dalej do ~2.4 MB zapasu do 0x280000; SteamID w slocie znajduje się bajtowym
  szukaniem. Szczegóły i pułapki: skill `elden-ring-save-repair`.

---

## 1. Odpowiedź na pytanie "co mam pobrać"

**Nic.** Wszystkie potrzebne narzędzia są open source i zostały już sklonowane do `references/`.
Dekompilacja NIE jest potrzebna — dekompiluje się zamknięte binarki, a tu każdy liczący się
edytor ma publiczny kod źródłowy, który jest dokładniejszy niż jakikolwiek decompile
(komentarze, nazwy struktur, historia commitów). Dekompilacja (Ghidra/ILSpy) miałaby sens
tylko dla zamkniętych narzędzi (Save Wizard, trainerу) — nie potrzebujemy ich do niczego.

Instalacje `pip` pojawią się dopiero w fazach GUI/pakowania (F6/F7: `fastapi`, `uvicorn`,
`pyinstaller`) — i sam je zrobię, gdy będzie trzeba.

---

## 2. Referencje — co jest w każdym repo i po co nam to

| # | Repo | Język | Co z niego bierzemy |
|---|---|---|---|
| 1 | `ER-Save-Editor` (ClayAmore) | Rust | **Główne źródło struktury slotu** — `src/save/` (structy PC/PS), `src/write/` (serializacja), `src/db/` (itemy, łaski, bossy, flagi, mapy jako kod) |
| 2 | `ER-Save-Lib` (ClayAmore) | Rust | Biblioteka + pełna implementacja **hashu integralności** slotu (`compute_hashed_value`, mult. `0x80078071`, mod `0xFFF1`) |
| 3 | `er-save-manager` (Hapfel1) | Python | **Najbliższy wzorzec dla nas**: `src/er_save_manager/parser/` — save.py, slot_rebuild.py, inventory_ops.py, player_data_hash.py + **testy pytest z fixture'ami** (checksum, event flags, item data) |
| 4 | `EldenRing-Save-Manager` (Ariescyn) | Python | Prosty `hexedit.py` — statystyki, imiona, kopiowanie postaci, SteamID (dobre do szybkiego porównania) |
| 5 | `sl2-analyzer` (darthdemono) | Python | Czysty parser + **gotowe bazy JSON**: `db_er/` (weapons 142 KB, armors, talismans, goods, ashes, graces, event_flags 288 KB, classes, remembrances…) + `edit.py`, `crypto.py` |
| 6 | `EldenRing-SaveForge` (oisis) | Go | **Najlepsza dokumentacja formatu**: `docs/sl2-binary-format-spec.md` (pełny łańcuch offsetów, tabela GaItem 8/16/21 B, stałe) |

Dodatkowo w sieci (znane, nie wymaga klonowania):
- `elden-ring-save-manager.readthedocs.io` — opis każdego pola slotu po nazwie (PlayerGameData
  pole po polu, FaceData, NetMan, ProfileSummary, checksums).
- Paramdex / soulsmodding wiki — ID itemów, flagi (jeśli będzie trzeba uzupełnić bazy).

---

## 3. Format — to, co już wiemy (fundament)

### Kontener (PC)
```
0x000  0x300        nagłówek BND4 (12 wpisów: USER_DATA000..009 + 010 + 011)
0x300 + k*0x280010  slot k: [0x10 MD5][0x280000 danych]
0x19003A0           USER_DATA_10: [MD5][0x60000]  (profile, SteamID, opcje)
0x19603B0           USER_DATA_11: [MD5][0x240010] (regulation)
razem               0x1BA03D0 = 28 967 888 B
```
- PC desktop = **plaintext** (żadnego AES na .sl2; AES128 dotyczy tylko Steam Deck / PS4).
- MD5 liczone z `[0x10:]` każdej sekcji; po edycji trzeba przeliczyć 12 sum.

### Slot (0x280000 B — czytany SEKWENCYJNIE, nie po sztywnych offsetach)
- `version u32@0` (0 = pusty; >81 → GaItem ma 5120 wpisów, ≤81 → 5118;
  ≥65 i ≥66 dokładają pola ogona), `map_id`, `play_time_ms`
- **gaitem_map** — tablica instancji itemów od `0x20`, rekordy zmiennej długości:
  broń 21 B / zbroja 16 B / talizman,item 8 B (typ w górnym nibblu handle'a)
- **PlayerGameData** (0x1B0) — statystyki, level, runy, imię (16×u16), klasa, płeć,
  scadutree blessing, hasła multiplayer… (pełna mapa pól w readtheocs, offset −379 od MagicOffset)
- ekwipunek (0x58×3 równoległe), inventory trzymane (0x9010) + skrzynia (0x6010),
  zaklęcia, fiolki, gesty, FaceData (0x12F), Torrent, MenuProfile, tutorial
- **event_flags** — 0x1BF99F B flag świata (bitowe) — tu siedzi cały stan gry
- ogon: współrzędne, spawn point, NetMan (0x20004), weather/time, steam_id (u64!),
  dlc (0x32), **player_data_hash (0x80 przy 0x27FF80)**, reszta = bufor "rest"
- Kotwice przy parsowaniu: MagicPattern `00 FF FF FF FF 00×12` ×4 = MagicOffset;
  dwa pola dynamiczne (projSize — max 256; unlockedRegSz — max 1024).

### Zasady zapisu (z dokumentacji + praktyki narzędzi)
1. Pozycje bierzemy **z parsowania**, nigdy ze stałych (bloki po gaitem-mapie się ruszają).
2. Slot zawsze zostaje 0x280000 — wzrost zabiera z `rest`, spadek dopisuje padding.
3. Po edycji zsynchronizować: **MD5 sekcji**, **PlayerDataHash**, **ProfileSummary**
   w UD10 (imię, lvl, czas, runy, mapa, ekwipunek) — inaczej load screen pokaże stare
   dane albo gra odrzuci slot.
4. Zapis atomowy: temp file → rename. Auto-backup przed każdą operacją. Sprawdzenie,
   że `eldenring.exe` nie działa.
5. Round-trip (parse → serialize → porównanie bajt w bajt) MUSI przechodzić zanim
   cokolwiek zapiszemy na oryginale.

---

## 4. Architektura naszego narzędzia (`erlab`, Python 3.14)

```
erlab/
├── bnd4.py       kontener: parse / rebuild header, wpisy, tabela nazw
├── checksums.py  MD5 sekcji + PlayerDataHash (Adler-like, 0x80078071)
├── reader.py     bezpieczne czytanie LE (u8/u16/u32/u64, UTF-16, float) — bounds-checked
├── slot.py       pełny parse slotu (sekwencyjny, wersjonowany) → struktury z offsetami
├── gaitem.py     gaitem_map: read/write rekordów 8/16/21 B, handle↔typ, nowe handle
├── inventory.py  inventory held/skrzynia: wpisy 12 B, liczniki, acquisition index
├── player.py     PlayerGameData: statystyki, level (walidacja sum−79), runy, imię, klasa
├── items.py      bazy ID→nazwa (z data/*.json), kategorie, upgrade/affinity
├── flags.py      event_flags: odczyt/zapis bitów, nazwy flag (z bazy)
├── world.py      łaski, bossy, summoning pools, regiony (z baz + flag)
├── savefile.py   warstwa wysoka: open→edytuj→validate→write (atomowo, z backupem)
└── cli.py        komendy (poniżej)
```

**CLI (docelowo):**
```
erlab report  <save>                      # raport: postacie, statystyki, zawartość, sumy
erlab check   <save>                      # doktor: MD5, hash, spójność leveli/ogonów
erlab stats   <save> --slot 0 --set vigor=60,arcane=80   # + auto-przeliczenie levelu
erlab runes   <save> --slot 0 --set 9999999
erlab rename  <save> --slot 0 --name "nowe imie"
erlab item    <save> --slot 0 add "Moonveil" --level 10
erlab item    <save> --slot 0 find "katalizator"
erlab flags   <save> --slot 0 find <tekst> | --set <flag>=1
erlab graces  <save> --slot 0 unlock --all | --region Limgrave
erlab copy    <saveA> --char 2 <saveB> --to 5 # kopiowanie postaci
erlab steamid <save> --set <id64>         # patcher dla savów z netu
erlab serve                               # GUI webowe (F6)
```

---

## 5. Fazy realizacji

| Faza | Zakres | Rozmiar | Kryterium akceptacji |
|---|---|---|---|
| **F1** | Parser + `report` + `check` (read-only) | M | round-trip bajt-w-bajt na twoim save; 3 postacie z bogatym raportem (statystyki, ekwipunek, liczby itemów); `check` potwierdza 12×MD5 + hash slotów; wynik zgodny z `sl2-analyzer` i `edytorem ClayAmore` (cross-check) |
| **F2** | Edycja rdzenia: `stats`/`runes`/`rename` + pełny write path | M | edycja na kopii → gra ładuje save bez ostrzeżeń; diff pokazuje wyłącznie zamierzone bajty + przeliczone hash/e (zero zmian śmieciowych); level zawsze spójny |
| **F3** | Itemey: `item add/find`, upgrade, affinity, Ashes of War | L | dodany item widoczny w grze (inwentarz + skrzynia); brak duplikatów handle; rekordy 8/16/21 B poprawne per typ |
| **F4** | Świat: `flags`, `graces unlock`, bossy, regiony | L | odblokowane łaski widoczne na mapie; flaga bossa ustawiona → boss martwy; pełna zgodność z nazwaną bazą flag |
| **F5** | Chirurgia: `copy` postaci (slot↔slot, save↔save), SteamID patcher, import PS4 | M | skopiowana postać ładuje się jako osobny slot; SteamID podmieniony → gra przyjmuje save na innym koncie |
| **F6** | GUI w lokalnym webview (pywebview / WebView2) + API JSON | M | karty postaci, panel napraw, ekwipunek + EQ (22 gniazda), suwaki, flagi; HTML/CSS/JS bez build-stepu; start dopiero na GO od He |
| **F7** | Pakowanie: `.exe` (PyInstaller) + skróty + README | S | dwuklik działa na twoim PC bez Pythona |

Kolejność jest zależna: F1→F2→F3 to szkielet. F4 może iść równolegle po F2 (flagi to osobny
blok pamięci). F6 dopiero gdy rdzeń jest nie do zepsucia. **Startujemy: F1.**

---

## 6. Strategia testów (zanim dotkniemy oryginału)

1. **Fixture:** kopia twojego save'a w `tests/fixtures/` (3 postacie, wszystkie wersje slotów:
   250/252/261 — świetny materiał testowy).
2. **Round-trip:** parse→serialize→`cmp` z oryginałem (kryterium zero-diff dla read/write).
3. **Cross-check parserów:** ten sam plik przez `sl2-analyzer` (Python, uruchamialny lokalnie)
   i — jeśli build przejdzie — `ER-Save-Editor`; porównujemy odczyty pole-po-polu.
4. **Testy edycji:** każda operacja na kopii; asercje na diff (dokładnie te bajty, które mają się
   zmienić) + ponowny parse po zapisie.
5. **Gra:** test in-game dopiero po zielonych testach na plikach, zawsze: Steam Cloud OFF,
   kopia w `backups/`, gra zamknięta przy edycji.

**Ryzyka / pułapki (znane z referencji):**
- Po błędnym parsowaniu gaitem-mapy wszystko się przesuwa → śmieci i crash. Dlatego round-trip
  jest krytykiem pierwszej klasy, nie "nice to have".
- UD10 ProfileSummary: różne źródła podają różne offsety (0x31A vs 0x195E) — ufamy parsowaniu
  z walidacją, nie stałym. Twoje sloty v250-261 to świeży format (1.16) — kalibrujemy na nich.
- Gra od 1.08 potrafi raportować "file tampering" dla edytowanych savów w trybie online
  (opisane w README hapfelowego menedżera). Do testów: tryb offline.
- `steam_autocloud.vdf` + Steam Cloud potrafią przywrócić stary plik po edycji — Cloud off
  na czas operacji (appid 1245620).

---

## 7. Otwarte decyzje (do potwierdzenia przez He)

1. Zakres F4: pełny edytor flag (jak w Hapfel1) czy tylko "unlock all łaski + bossy + regiony"?
2. Tempo prac: F1+F2 jednym cięgiem (mamy działający edytor statystyk), czy po każdej fazie
   przerwa na testy w grze?
3. Nazwa/CLI: **rozstrzygnięte** — produkt to *Rezur Saves Configurator*, komenda `rezur`.
