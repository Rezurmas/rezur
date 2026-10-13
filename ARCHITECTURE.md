# Rezur Saves Configurator — architektura i plan

> Status: v0.1.0 — działa warstwa CLI + biblioteka. GUI zaplanowane (F6).
> Zasada nadrzędna: **żadna logika nie żyje w interfejsie**. CLI i przyszłe API/GUI
> są cienkimi adapterami nad tym samym rdzeniem.

---

## 1. TL;DR — decyzje

| Pytanie | Odpowiedź |
|---|---|
| Backend | **Python (stdlib) + FastAPI** — cienka warstwa HTTP nad `rezur.core/diag/fixes/ops` |
| Frontend | **lokalna aplikacja webowa (SPA)**: HTML + CSS + vanilla JS, bez build-stepu, serwowana przez backend na `127.0.0.1` |
| Teraz | CLI `python -m rezur` (ta sama logika, bez sieci) |
| Później (opcjonalnie) | owinięcie SPA w natywne okno (`pywebview`) i/lub `.exe` (PyInstaller) — F7 |
| Dlaczego nie Qt/Tkinter | web daje drag&drop, tabele, motywy CSS i zero instalek po stronie użytkownika; jeden stack UI działa na każdym OS |
| Dlaczego nie Electron/Tauri | przerost formy na tym etapie; Tauri wróci, gdyby powstała potrzeba pełnej paczki „app" bez Pythona |

---

## 2. Warstwy i kierunki zależności

```
                     ┌─────────────────────────────────────────┐
   DZIŚ              │              CLI (rezur)                │
                     │   info · doctor · fix · copy · steamid  │
                     └───────────────────┬─────────────────────┘
                                         │  (te same funkcje)
   F6 (plan)         ┌───────────────────┴─────────────────────┐
   ┌─────────────┐   │        API HTTP (FastAPI, 127.0.0.1)    │
   │  SPA (web)  │◄──┤   /api/save · /api/diagnostics ·        │
   │  drag&drop  │   │   /api/fixes/apply · /api/ops/*  + SSE  │
   └─────────────┘   └───────────────────┬─────────────────────┘
                                         ▼
                     ┌─────────────────────────────────────────┐
                     │  ops      (copy_slot, steamid, …)       │
                     │  fixes    (torrent, checksums, summary, │
                     │            playerhash, weather, dlc)    │
                     │  diag     (checks → Finding)            │
                     └───────────────────┬─────────────────────┘
                                         ▼
                     ┌─────────────────────────────────────────┐
                     │  core     (SaveFile, Slot, checksums,   │
                     │            profiles, bnd4, reader)      │
                     │  games    (rejestr gier: Elden Ring)    │
                     └───────────────────┬─────────────────────┘
                                         ▼
                          %APPDATA%\EldenRing\<id>\ER0000.sl2
```

**Reguły importów (jednokierunkowe, bez cykli):**

| warstwa | może importować | NIE może |
|---|---|---|
| `core` | stdlib, `core` | nic wyżej |
| `games` | stdlib | `core` (rejestr czysty) |
| `diag` | `core` | `fixes`, `ops`, interfejsy |
| `fixes` | `core` | `diag`, `ops`, interfejsy |
| `ops` | `core`, `fixes` | interfejsy |
| `report` | `core`, (`diag` typy) | `fixes`, `ops` |
| `cli` / `api` | wszystko niżej | siebie nawzajem |

Sprzężenie „finding → naprawa" jest luźne: `Finding.fix` to **string id** naprawy
(`"torrent"`), nie referencja. CLI/API robi tłumaczenie. Dzięki temu diag nie wie
o fixes, a nowe naprawy nie wymagają zmian w diag.

---

## 3. Struktura katalogów (stan faktyczny)

```
ER-Save-Lab/
├── rezur/                        ← pakiet (produkt)
│   ├── __init__.py               produkt + wersja
│   ├── __main__.py               python -m rezur
│   ├── cli.py                    komendy: info/doctor/fix/copy/steamid/list-fixes
│   ├── core/
│   │   ├── reader.py             bezpieczne odczyty LE (u8..u64, f32, UTF-16)
│   │   ├── bnd4.py               kontener: nagłówek + 12 wpisów
│   │   ├── checksums.py          MD5 sekcji + PlayerDataHash (Adler-variant)
│   │   ├── slots.py              pełny parser slotu (wersjonowany, zweryfikowany)
│   │   ├── profiles.py           roster + rebuild profilu ekranu wyboru
│   │   └── savefile.py           SaveFile: sekcje, touch-MD5, zapis atomowy
│   ├── games/
│   │   ├── base.py               interfejs profilu gry + rejestr
│   │   └── eldenring.py          ER: ścieżki, wykrywanie, stałe
│   ├── diag/
│   │   └── engine.py             checks → Finding(level, code, msg, slot, fix)
│   ├── fixes/
│   │   ├── base.py               Fix + FixResult + iter_parsed_slots
│   │   ├── torrent.py            hp=0+ACTIVE → DEAD  (1 bajt + MD5)
│   │   ├── checksum.py           MD5 sekcji + PlayerDataHash refresh
│   │   ├── summary.py            rebuild profilu z slotu (+MD5 UD10)
│   │   ├── weather.py            area_id ← bajt mapy
│   │   └── dlc.py                zerowanie nieużywanych pól DLC
│   ├── ops/
│   │   ├── copy_slot.py          dane 0x280000 + profil + MD5 (+clear-source)
│   │   └── steamid.py            wymiana SteamID w UD10 + slotach
│   ├── report/
│   │   ├── text.py               tabele i raport konsolowy
│   │   └── jsonout.py            eksport JSON (dla GUI/API)
│   └── api/
│       └── server.py             FastAPI (placeholder F6 + kontrakt w docstringu)
├── tests/run_all.py              testy na kopiach realnych save'ów (8 sztuk)
├── tools/                        pierwsze narzędzia bojowe (fix_torrent, copy_slot)
├── references/                   6 sklonowanych repo (materiał źródłowy, do nauki)
├── backups/                      historia save'ów (fixture'y testów)
├── PLAN.md                       plan projektu ER Save Lab (F0→F7)
└── ARCHITECTURE.md               ten dokument
```

---

## 4. Przepływy (co się dzieje po drodze)

**doctor** (tylko czyta):
`CLI → diag.run_diagnostics → core(SaveFile, Slot.parse, profiles.roster) → [Finding] → report`

**fix** (jedyny piszący tor):
```
CLI → fixes.apply_fixes(dry_run=True)  → pokaz „co bym naprawił"   (bez zapisu)
CLI → fixes.apply_fixes(dry_run=False) → mutacja przez SaveFile
     → SaveFile.write():  backup obok pliku → tmp → fsync → os.replace
     → diag re-run → raport resztek
```

**copy**:
`CLI → ops.copy_character → (slot 0x280000 + profil 0x24C + touch_slot/touch_ud10) → write`

**GUI (F6, docelowo)**: SPA wysyła JSON do `/api/*`; endpointy wołają **te same
funkcje** co CLI; SSE `/api/events` niesie postęp (np. „dodano 240 itemów…").

---

## 5. Backend — dlaczego FastAPI + stdlib core

- rdzeń nie ma żadnych zależności (stdlib), więc CLI i testy działają wszędzie bez instalacji;
- FastAPI doda tylko warstwę HTTP (opcjonalny extra: `pip install rezur-saves-configurator[web]`);
- walidacja wejścia (pydantic) należy do API, nie do core;
- wątek roboczy osobny od event-loopu (operacje na 29 MB pliku) — uvicorn + `run_in_threadpool`;
- bind **wyłącznie 127.0.0.1** + nagłówek `X-Rezur-Token` (token w pliku sesji);
- żadnych uploadów w świat: plik krąży tylko między przeglądarką a lokalnym procesem.

Kontrakt (F6): szczegółowa lista endpointów — docstring w `rezur/api/server.py`.

## 6. Frontend — co konkretnie powstanie (F6)

- jeden ekran: karty postaci (jak `rezur info`, ale ładniej), status kontenera,
  panel ustaleń z przyciskami „napraw" per finding;
- drag&drop save'a **albo** wybór z listy save'ów znalezionych w `%APPDATA%`;
- tryb bezpieczny jak CLI: najpierw dry-run („pokaż co się zmieni"), potem zapis;
- podgląd diffa naprawy (przed/po, liczba zmienionych bajtów);
- historia backupów z przyciskiem „przywróć";
- bez frameworka i bez build-stepu: `index.html + app.js + style.css` → serwowane statycznie.

## 7. Rozszerzalność

- **nowa gra** = nowy plik w `games/` (+ przeniesienie formatu pod profil gry, gdy
  dojdzie drugi tytuł — dziś parser jest ER-specyficzny w `core/slots.py`);
- **nowa naprawa** = klasa `Fix` w `fixes/` + rejestracja + test w `tests/run_all.py`;
- **nowy check** = `Finding` z kodem i opcjonalnym `fix` (string id);
- **poziomy**: `error` (gra nie ruszy), `warning` (do naprawy), `info` (ciekawostka).

## 8. Roadmapa → moduły

| Faza | Zakres | Gdzie | Status |
|---|---|---|---|
| F1 | parser + raport + doctor | `core/`, `diag/`, `report/` | ✅ v0.1.0 |
| F2 | edycja statystyk/runów/imienia (walidacja levelu) | `ops/stats.py` | następne |
| F3 | itemy (gaitem + inventory + baza `db_er`) | `core/gaitem.py`, `ops/items.py` | plan |
| F4 | świat: event flags, łaski, bossy | `core/flags.py`, `ops/flags.py` | plan |
| F5 | transfer: import/eksport postaci (JSON), cross-save | `ops/transfer.py` | plan |
| F6 | GUI: API + SPA | `api/`, `web/` | plan (kontrakt gotowy) |
| F7 | pakowanie: `.exe` / pywebview / skróty | `packaging/` | plan |

## 9. Konwencje

- identyfikatory EN, komunikaty dla użytkownika PL;
- zero zależności w `core`; wszystko opcjonalne przez extras w `pyproject.toml`;
- każdy zapis = backup + atomic + (w CLI) re-diagnostyka;
- zakaz pisania do żywego save'a przy działającej grze (`_guard_game`, sprawdza
  tylko pliki w folderze EldenRing — kopie robocze są przepuszczane);
- test mutujący zawsze na kopii w `tempfile`; fixture = historyczne backupy.
