# Rezur Saves Configurator — architektura i plan

> Status: v0.2.0 — CLI + biblioteka + GUI (pywebview/WebView2, 13 paneli, EN/PL).
> Zasada nadrzędna: **żadna logika nie żyje w interfejsie**. CLI i przyszłe API/GUI
> są cienkimi adapterami nad tym samym rdzeniem.

---

## 1. TL;DR — decyzje

| Pytanie | Odpowiedź |
|---|---|
| Backend | **Python (stdlib)** — cały silnik: `rezur.core/diag/fixes/ops`; CLI działa bez żadnych instalacji |
| Frontend (F6) | **lokalny webview — pywebview** (Windows: WebView2), UI w HTML+CSS+JS, bez build-stepu. Decyzja: He |
| Most GUI ↔ silnik | ten sam proces Pythona: pywebview daje okno i ładuje lokalny HTML; operacje przez lokalne API JSON (plan niżej) |
| Dlaczego nie Clay (C) | odpuszczony przez He („w clayu odpuszczamy") — brak kompilatora i wolniejsze iterowanie |
| Dlaczego nie Electron/Tauri | przerost — pywebview korzysta z WebView2 obecnego w każdym Windows 10/11 |
| Status | GUI startuje **dopiero na wyraźne GO od He**; na teraz liczy się wyłącznie backend |

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
├── tests/run_all.py              testy na kopiach realnych save'ów (47 testów)
├── tools/                        narzędzia bojowe (fix_torrent, copy_slot, build_exe.cmd)
├── packaging/rezur.spec          PyInstaller → dist\rezur.exe (onefile)
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

**staging** (zmiany oczekujące — stan `idle → staged → applied/discarded`):
```
CLI (stage <komenda …>) → staging.begin: kopia robocza w %APPDATA%\rezur\staging\
        → komenda edycji pisze do brudnopisu (SaveFile.write rozpoznaje work-path:
          bez backupu, bez dziennika; licznik zmian rośnie tylko przy realnej różnicy bajtów)
CLI (pending)  → manifest: lista operacji (+ --diff: porównanie sekcji bajt w bajt z oryginałem)
CLI (apply)    → weryfikacja brudnopisu → GOLD → backup oryginału (stagebak) → atomowy zapis
                 → wpis w dzienniku (z nazwą backupu) → sprzątanie stagingu → 12/12 MD5
CLI (discard)  → skasowanie brudnopisu; oryginał NIETKNIĘTY
Błąd weryfikacji przy apply → zmiany ZOSTAJĄ (nic nie tracimy, można poprawić)
```

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

## 6. GUI (F6) — okno pywebview (WebView2), ZBUDOWANE

- `python -m rezur gui [--save PLIK]` → natywne okno WebView2; frontend w HTML/CSS/JS
  (`rezur/gui/web/`), most `window.pywebview.api.*` do `rezur/gui/api.py` (ten sam proces,
  bez HTTP i portów; `rezur/api/` pozostaje nieużywany).
- **api.py** to cienka warstwa: te same funkcje co CLI; wszystkie EDYCJE przez staging;
  czytanie paneli pokazuje BRUDNOPIS gdy istnieją zmiany oczekujące (`_live()`), więc UI
  od razu pokazuje efekt edycji, a oryginał rusza dopiero na ZASTOSUJ.
- Styl: engineering-series (bench `web/test-bench.html`) — czarna anoda `#1E1F22`,
  pomarańcz `#F0501E` jako jedyny akcent, LCD dot-matrix, klawisze z twardym skokiem,
  hazard tylko dla destrukcyjnych, **zero suwaków** (staty: −/+ z auto-repeat + wpis z klawiatury).
- 13 paneli: POSTACIE · DOKTOR · STATY · EKWIPUNEK · ZAŁOŻONE · ŚWIAT · CZARY · WYGLĄD ·
  TELEPORT · RYZYKO · KOPIE · HISTORIA · USTAWIENIA; pasek zmian na dole (PODGLĄD/COFNIJ/
  ZASTOSUJ/ODRZUĆ), dialogi wprost (ZAPISZ/ODRZUĆ/WRÓĆ), blokada przy działającej grze.
- **Język (i18n):** domyślnie **EN**; przełącznik `EN/PL` — pill w nagłówku i przyciski
  w USTAWIENIACH; wybór idzie do configu (`ui_lang`, walidacja `en|pl`) i przeładowuje okno;
  słowniki `I18N.en/pl` w `app.js`, `t()` czyta klucz, komunikaty doctora tłumaczone po kodzie
  (`FIND_EN`), liczby przez `toLocaleString` wg języka.
- **Wyszukiwanie na żywo:** każde pole szukania filtruje/podpowiada w trakcie pisania
  (debounce 170 ms, min. 2 znaki) — ekwipunek i świat filtrują listę pod spodem
  (ranking: „zaczyna się od" → krótsze → alfabet), a dodawanie itemu / czary / zakładanie
  pokazują listę podpowiedzi z podświetlonym trafieniem (klik albo Enter = pierwsza,
  strzałki = wybór). Listy są inline (nic nie nachodzi na treść), wpisy buduje
  `attachSuggest()` w `app.js`, styl `.suggbox` w `style.css`.
- `--selftest`: okno otwiera się, odpytuje `window.__rezurBooted`/`__rezurLoaded`, liczy
  metody mostu (`Object.keys(window.pywebview.api).length`) i panele, drukuje etykiety 13
  zakładek, potem PRZEŁĄCZA JĘZYK na żywo (EN→PL→EN, zapis w configu + reload) i zamyka —
  dymny test mostu bez klikania (używane przy każdej zmianie).
- **`tests/bridge_audit.py`:** audyt „czy wszystko połączone" — woła KAŻDĄ metodę `GuiApi`
  na kopii save'a w izolowanym `%APPDATA%` (49 wywołań: load/doctor/risk/staging/apply/
  backupy/restore/config/panele) i raportuje wynik; kod wyjścia ≠0 gdy coś nie działa.
- **Testy strażnicze:** `t_ui_lang_default_and_switch` (EN domyślnie, zapis wyboru, śmieci
  odrzucane), `t_gui_i18n_and_wiring` (klucze EN/PL zgodne, każdy `t(...)` ma tłumaczenie,
  każdy uchwyt JS istnieje w HTML, 13 zakładek = 13 paneli i etykiety w obu językach) oraz
  `t_db_no_cjk_names` (baza flag bez japońskich nazw z datamine'u; przypięte 9100=Margit,
  9101=Godrick, 9134=Mimic Tear + bossowie mają niepuste lokacje).

### Stany aplikacji (kontrakt dla GUI — „żeby nic nie zaskakiwało")

| stan | kiedy | UI |
|---|---|---|
| `empty` | brak wybranego pliku | „wskaż lub przeciągnij ER0000.sl2" + lista ostatnich |
| `loading` | wczytywanie ~29 MB | wskaźnik nieoznaczony + czas (info pokazuje ms); okno nie może zamarznąć |
| `ready` | plik wczytany | karty postaci, panele aktywne |
| `staged` | ≥1 zmiana oczekująca | licznik zmian + PODGLĄD / ZASTOSUJ / ODRZUĆ (= staging: `stage/pending/apply/discard`) |
| `busy` | apply w toku | blokada kontrolek + faza („zapisuję", „weryfikuję") |
| `failed` | błąd zapisu | zmiany ZOSTAJĄ, komunikat co poszło nie tak (staging nienaruszony) |
| `done` | zapis OK | zielony: nazwa backupu + 12/12 MD5 + wpis w historii (`log`) |

- Zamknięcie okna w stanie `staged` → dialog wprost: **Zapisz / Odrzuć / Wróć** (nigdy OK/Anuluj).
- Oryginał zmieniony poza sesją (gra zapisała) → `apply` wstrzymane z komunikatem;
  w CLI świadomy override to `--force`.
- Historia operacji (`rezur log` = dziennik edycji) jest jednym ze źródeł panelu
  „ostatnie zmiany" i znacznika „plik modyfikowany" (patrz `risk`).

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
| F2 | edycja statystyk/runów/imienia (walidacja levelu) | `ops/stats.py` | ✅ |
| F3 | itemy (gaitem + inventory + baza `db_er`) | `core/gaitem.py`, `ops/items.py` | ✅ |
| F4 | świat: event flags, łaski, bossy | `core/flags.py`, `ops/flags.py` | ✅ |
| F5 | transfer: import/eksport postaci (JSON), cross-save | `ops/transfer.py` | ✅ |
| F5b | zaufanie: vault (GOLD/piny), watch, risk, staging + log | `core/vault.py`, `ops/watch.py`, `risk.py`, `staging.py` | ✅ |
| F5c | luki: torn-write, liczniki ekwipunku, grupy colosseum/baseny/regiony, `find`, cofanie zmian | `core/savefile.py`, `fixes/invcounters.py`, `db_er/event_flags_extra.json`, `cli.find`, `staging.undo` | ✅ |
| F6 | GUI: pywebview (WebView2) + most JS↔silnik, 13 paneli w stylu engineering-series, i18n EN (domyślny) / PL, audyt mostu + testy strażnicze | `gui/api.py`, `gui/app.py`, `gui/web/`, `tests/bridge_audit.py` | ✅ v0.2 |
| F7 | pakowanie: `.exe` / pywebview / skróty | `packaging/` | plan |

## 9. Konwencje

- identyfikatory EN, komunikaty dla użytkownika PL; **GUI ma warstwę języka** (`ui_lang`:
  EN domyślnie, PL opcjonalnie) — teksty w `I18N`, komunikaty silnika tłumaczone po kodzie;
- zero zależności w `core`; wszystko opcjonalne przez extras w `pyproject.toml`;
- każdy zapis = backup + atomic + (w CLI) re-diagnostyka;
- zakaz pisania do żywego save'a przy działającej grze (`_guard_game`, sprawdza
  tylko pliki w folderze EldenRing — kopie robocze są przepuszczane);
- test mutujący zawsze na kopii w `tempfile`; fixture = historyczne backupy.
