/* REZUR GUI — logika (most pywebview + i18n EN/PL + panele). Bez frameworków.
   Język: domyślnie EN ("en"); przełącznik: pill w nagłówku / USTAWIENIA;
   zapamiętywany w configu (ui_lang) i stosowany po przeładowaniu okna. */

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** język — ustawiany w boot() z configu; t() sięga do słownika */
let LANG = "en";
const fmtInt = n => (n ?? 0).toLocaleString(LANG === "pl" ? "pl-PL" : "en-US");

/** pasek narzędzi przyklejony u góry panelu; nagłówek tabeli ląduje dokładnie pod nim
    (wysokość paska → zmienna --barH, bo pasek się zawija przy wąskim oknie) */
function stickBars(panel) {
  const bar = panel.querySelector(".toolbar");
  if (!bar) return;
  const scroller = panel.closest(".work") || panel.parentElement;
  const padTop = parseFloat(getComputedStyle(scroller).paddingTop) || 0;
  bar.classList.add("stickbar");
  const set = () => {
    panel.style.setProperty("--padTop", padTop + "px");
    panel.style.setProperty("--barH", Math.round(bar.offsetHeight - padTop + 1) + "px");
  };
  set();
  requestAnimationFrame(set);
  window.addEventListener("resize", set);
}

/* --------------------------------------------------- wyszukiwanie na żywo -- */

/** nie zasypuj mostu przy każdym klawiszu */
function debounce(fn, ms = 170) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
/** podświetl trafiony fragment (XSS-safe) */
function mark(text, q) {
  const s = String(text ?? "");
  if (!q) return esc(s);
  const i = s.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return esc(s);
  return esc(s.slice(0, i)) + "<em>" + esc(s.slice(i, i + q.length)) + "</em>" + esc(s.slice(i + q.length));
}
/** sortowanie: najpierw „zaczyna się od", potem krótsze, potem alfabetycznie */
function rankByName(rows, q) {
  const s = (q || "").toLowerCase();
  return rows.slice().sort((a, b) => {
    const an = String(a.name || "").toLowerCase(), bn = String(b.name || "").toLowerCase();
    const ap = an.startsWith(s) ? 0 : 1, bp = bn.startsWith(s) ? 0 : 1;
    return ap - bp || an.length - bn.length || an.localeCompare(bn);
  });
}
/** Podpowiedzi pod polem: lista inline (nic na siebie nie nachodzi).
    input — pole; box — kontener .suggbox; fetchFn(q) → lista {name,...}. */
function attachSuggest(input, box, fetchFn, opts = {}) {
  const { min = 2, onPick = null, enterFallback = null } = opts;
  let rows = [], active = 0;
  const clear = () => { rows = []; active = 0; box.innerHTML = ""; };
  const refreshActive = () => box.querySelectorAll(".srow").forEach((r, i) => r.classList.toggle("on", i === active));
  const render = q => {
    box.innerHTML = rows.length
      ? rows.map((it, i) => `<div class="srow" data-i="${i}"><span class="sidx">${String(i + 1).padStart(2, "0")}</span>
          <span class="sname">${mark(it.name, q)}</span><span class="scat">${esc(it.cat || it.tag || "")}</span></div>`).join("")
      : `<div class="sempty">${esc(t("noHits"))}</div>`;
    box.querySelectorAll(".srow").forEach((r, i) => {
      r.onmousedown = e => e.preventDefault();      // nie zabieraj fokusu polu (inaczej lista zdąży zniknąć)
      r.onmouseenter = () => { active = i; refreshActive(); };
      r.onclick = () => pick(rows[i]);
      r.classList.toggle("on", i === active);
    });
    (box.querySelector(".srow.on") || box.querySelector(".srow"))?.scrollIntoView({ block: "nearest" });
  };
  const pick = it => {
    if (!it) return;
    input.value = it.name;
    clear();
    if (onPick) onPick(it);
  };
  const look = debounce(async () => {
    const q = input.value.trim();
    if (q.length < min) { clear(); return; }
    const items = await fetchFn(q);
    rows = rankByName(items || [], q);
    active = 0;
    render(q);
  });
  input.addEventListener("input", look);
  input.addEventListener("keydown", e => {
    if (e.key === "ArrowDown" && rows.length) {
      e.preventDefault(); active = (active + 1) % rows.length; refreshActive();
      (box.querySelector(".srow.on"))?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (e.key === "ArrowUp" && rows.length) {
      e.preventDefault(); active = (active - 1 + rows.length) % rows.length; refreshActive();
      (box.querySelector(".srow.on"))?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (e.key !== "Enter") return;
    if (rows.length) { e.preventDefault(); pick(rows[active] || rows[0]); }
    else if (enterFallback) enterFallback();
  });
  input.addEventListener("blur", () => setTimeout(clear, 200));
  return { clear, pickFirst: () => pick(rows[0]) };
}

const I18N = {
  en: {
    tabs: { postacie: "CHARACTERS", doktor: "DOCTOR", staty: "STATS", ekwipunek: "INVENTORY", eq: "LOADOUT", swiat: "WORLD", czary: "SPELLS", wyglad: "APPEARANCE", teleport: "TELEPORT", ryzyko: "RISK", kopie: "BACKUPS", log: "HISTORY", ustawienia: "SETTINGS" },
    noFile: "NO FILE", gameStop: "GAME: STOP", gameRun: "GAME: RUNNING",
    autoCopy: "AUTO COPY",
    titleFile: "loaded save file", titleMd5: "section checksums", titleGame: "game state",
    titleAuto: "a backup is made on every write", titleLang: "language / język",
    bannerLead: "WARNING", bannerTxt: "eldenring.exe is running — writing to the live save is blocked · edit the staging draft, apply after the game closes",
    pendingChange: "CHANGE", pendingChanges: "CHANGES",
    ready: "READY", pickFile: "PICK FILE…", pickFile2: "PICK .SL2 FILE", openRecent: "OPEN LAST / NEWEST",
    emptySub: "select an ER0000.sl2 file to begin",
    emptyNote: 'typical path: <span class="mono">%APPDATA%\\EldenRing\\&lt;steamid&gt;\\ER0000.sl2</span><br>edits always land in a work copy first — the original is touched only on APPLY.',
    ctxPickChar: "PICK A CHARACTER TO EDIT", ctxSlotEmpty: s => `SLOT ${s} — EMPTY`,
    tagStaging: "STAGING · DRAFT VIEW", tagOldPatch: p => `OLD PATCH (b${p})`, tagTorrent: "TORRENT !!",
    ctxSelected: "SELECTED",
    loading: "LOADING SAVE…", stagingTxt: "STAGING…", savingTxt: "WRITING + VERIFYING…", restoring: "RESTORING…",
    stageBtn: "APPLY", undoBtn: "UNDO", previewBtn: "PREVIEW", discardBtn: "DISCARD",
    savedOk: (b, ok, tot) => `saved · backup: ${b} · MD5 ${ok}/${tot}`,
    savedStatus: b => `saved (backup ${b})`, discarded: n => `discarded ${n} changes — original untouched`,
    needFile: "pick a file first", noChanges: "nothing changed", range199: "range 1..99 — that's what the game accepts",
    addQueue: r => `queued: ${r}`, stageFail: e => `failed: ${e}`,
    applyTitle: "apply changes?", applyBody: p => `<div>One <b>backup</b> of the current state will be made, then the draft is written and verified.</div><div class="lcd">file: ${p}</div>`,
    applyYes: "APPLY", stay: "BACK",
    forceTitle: "original changed outside Rezur", forceYes: "OVERWRITE (--force)",
    discardTitle: n => `discard ${n} changes?`, discardBody: '<div>The draft will be deleted. <b>The original stays untouched</b> — nothing is written.</div>', discardYes: "DISCARD",
    undone: r => `undone: ${r.op} ${r.summary} (left ${r.left})`,
    unpreviewedOps: "operations", previewSecs: "changed file sections", previewNone: "(no differences)", close: "CLOSE",
    stagingHint: n => `+1 pending change (${n})`,
    refresh: "REFRESH", exportChar: "EXPORT CHARACTER…", importChar: "IMPORT CHARACTER…",
    slotN: n => `SLOT ${String(n).padStart(2, "0")}`, emptySlot: "— empty —", freeSpot: "free slot", charBadge: "?",
    importTitle: "import character", importBody: (f, s) => `Load <b>${f}</b> into slot ${s} (as a pending change).`, importYes: "IMPORT", importQueued: "import character",
    exported: p => `exported: ${p}`, pickCharFirst: "pick a character first",
    scanAgain: "SCAN AGAIN", fixAll: "FIX EVERYTHING (to queue)", fixAllTitle: "fix everything", fixAllBody: "Runs all available repairs (torrent, sums, hash, profile, weather, DLC, counters) on the work copy.", fixAllYes: "FIX",
    md5line: (ok, tot) => `section sums: ${ok}/${tot}`, md5bad: b => ` · bad: ${b}`,
    healthy: "save looks healthy — no findings.",
    fixBtn: id => `FIX: ${id}`, fixQueued: id => "repair " + id, slotWord: "slot",
    statsHeader: s => `statistics — slot ${s}`, lvl: "level", lvlNote: "= sum − 79 (enforced by the game)",
    nameRunes: "name & runes", nameColon: "name 1–16 chars", runesColon: "runes (memory)",
    statQueue: "ADD TO QUEUE", statReset: "RESET VALUES", statHint: "no sliders: +/− (hold) or click a value and type",
    clickType: "click to type", queueStats: s => `stats slot${s}`,
    held: "ON HAND", storage: "STORAGE", searchInv: "search inventory…", search: "SEARCH", addItem: "ADD ITEM…",
    thHandle: "handle", thQty: "qty", thName: "name", thId: "id", thActions: "actions",
    remove: "REMOVE", toStorage: "TO STORAGE", toHeld: "ON HAND", qty: "QTY…", setQtyTitle: "set quantity", setQtyYes: "SET",
    empty2: "(empty)", itemRemoved: "remove item", itemMoved: "move item", itemQty: "item quantity",
    addTitle1: "add item — step 1/2", addTitle2: "add item — step 2/2", fragment: "name fragment", next: "NEXT",
    typeToSearch: "type at least 2 characters…", pickFromList: "click an entry to pick it · Enter = first one",
    liveFilters: "filters as you type",
    pickNo: "number:", qtyColon: "qty:", upgradeColon: "upgrade:", addYes: "ADD", noHits: "no matches",
    addQueued: nm => "add: " + nm,
    loadoutHeader: s => `loadout — slot ${s}`, zones: { weapon: "WEAPONS", armor: "ARMOR", talisman: "TALISMANS" },
    emptyCell: "— empty —", unequip: "UNEQUIP", upg: "+LVL", aff: "AFFINITY", aow: "AOW",
    upgTitle: "upgrade level (0–25)", affTitle: "affinity", aowTitle: "ash of war (name)", aowPh: "e.g. Bloody Slash",
    equipHeader: "equip from inventory", equipPh: "handle:0x… or name", equipAt: "slot (optional)", equipBtn: "EQUIP",
    equipQueued: "equip item", weaponUpg: "weapon upgrade", affQueued: a => "affinity: " + a, aowQueued: "ash of war",
    worldFilter: "name / ID filter…", filter: "FILTER", grantAll: "GRANT WHOLE GROUP…",
    noRows: "(no entries)", grantTitle: g => `grant whole group ${g}?`,
    grantBody: n => `I will set <b>${n}</b> flags to acquired (state 1) in the work copy. Big change — check PREVIEW before APPLY.`,
    grantYes: n => `GRANT ${n} FLAGS`, flagTitleSet: "set flag?", flagTitleClear: "clear flag?", set: "SET",
    flagQueued: id => "flag " + id, groupQueued: g => "group " + g,
    spellPh: "spell name to memorize…", memorize: "MEMORIZE", clearAll: "CLEAR ALL…", clearAllTitle: "clear all spell slots?", clearAllBody: "All 14 slots will be emptied (on the work copy).", clearYes: "CLEAR",
    spellSlotsHdr: "memorized spells — 14 slots", spellListHdr: "spell list — pick one and press MEMORIZE",
    spellFilter: "filter spells…", thKind: "type", thState: "state", spellsWord: "spells",
    kindSorc: "sorcery", kindInca: "incantation",
    memoBadge: "MEMORIZED", ownedBadge: "IN INVENTORY", missBadge: "not in inventory",
    spellSlot: n => `SLOT ${String(n).padStart(2, "0")}`, forget: "FORGET", enterSpell: "type a spell name",
    spellQueued: n => "spell: " + n, forgotQueued: "forget spell",
    appHeader: s => `appearance / archetype — slot ${s}`, sex: "sex", typeA: "0 — type A", typeB: "1 — type B",
    build: "body build", giftLabel: a => `starting gift (0–255; archetype b${a} stays)`,
    appQueued: "appearance", nothingChanged: "nothing changed",
    posHeader: s => `position — slot ${s}`, tpHeader: "teleport to location", teleportBtn: "TELEPORT",
    customCoords: "custom coordinates", setBtn: "SET", tpNote: "teleport syncs the weather with the map region (otherwise doctor reports a desync).",
    tpQueued: "teleport", tpNeed: "provide map and xyz",
    riskScan: "SCAN RISK", riskHint: "evaluates impossible data + modification marker; not a guarantee against flags.",
    clickScan: "click SCAN…", scanning: "SCANNING RISK…",
    verdicts: { red: "RED", yellow: "YELLOW", green: "GREEN" }, issues: n => `${n} note(s)`, impossible: " — impossible data!",
    markerYes: (n, last) => `marker: file MODIFIED by Rezur — ${n} operations; last ${last}`,
    markerNo: "marker: no trace of Rezur in this file",
    goldLine: g => `GOLD: ${g} — restore from the BACKUPS tab`,
    notes: "notes",
    riskNotes: ["experiment on a COPY (backup/GOLD), not on the live save", "before going online consider restoring GOLD — the game treats every edit alike", "Rezur cannot guarantee a flag-free result: the game scans for impossible data and we only check part of it"],
    backupReload: "REFRESH", makeGold: "MAKE GOLD COPY",
    retentionNote: r => `rotation keeps ${r} copies; GOLD and pinned — forever.`,
    thType: "type", thDate: "date", thSize: "size",
    restore: "RESTORE…", pin: "PIN", unpin: "UNPIN",
    restoreTitle: "restore backup?", restoreBody: name => `<div>File <b>${name}</b> will replace the current save.</div><div>The current state is copied first (pre-restore).</div>`, restoreYes: "RESTORE",
    restoredOk: "restored — you can compare and go back from the list", pinned: "pinned", unpinned: "unpinned",
    goldMade: "GOLD copy created", goldExists: "GOLD already exists", noBackup: n => `no such backup: ${n}`,
    logNote: "edit journal — every successful write (the modified marker)",
    thWhen: "when", thOp: "operation", thBackup: "backup", logEmpty: "(empty — the journal records every successful modification)",
    cfgHeader: "config", retention: "backup rotation", watchInt: "watch interval [s]",
    guardTxt: "block writes while the game runs (guard_live)", autoDocTxt: "auto-diagnostics after repairs",
    saveCfg: "SAVE SETTINGS", openFolder: "OPEN SAVE FOLDER", watchOnceBtn: "WATCH: SINGLE PASS",
    about: "about", cfgsaved: "settings saved",
    langHeader: "language", langNote: "default: English. switching reloads the window.",
    aboutTxt: "100% offline — no network calls, no telemetry. The save file never leaves this machine. Edits always go through a work copy → APPLY.",
    pickFileShown: "pick a file.", chooseChar: "pick a character (CHARACTERS tab) — the panel shows that slot.",
    noBridge: "NO PYTHON BRIDGE — launch with `python -m rezur gui`", noBridgeToast: "no pywebview bridge — this window is a preview without the engine",
    watchReason: { "gra nie działa": "game not running", "świeża kopia już jest": "a fresh copy already exists", "start gry": "game start", "interwał": "interval" },
    cancelled: "cancelled",
  },
  pl: {
    tabs: { postacie: "POSTACIE", doktor: "DOKTOR", staty: "STATY", ekwipunek: "EKWIPUNEK", eq: "ZAŁOŻONE", swiat: "ŚWIAT", czary: "CZARY", wyglad: "WYGLĄD", teleport: "TELEPORT", ryzyko: "RYZYKO", kopie: "KOPIE", log: "HISTORIA", ustawienia: "USTAWIENIA" },
    noFile: "BRAK PLIKU", gameStop: "GRA: STOP", gameRun: "GRA: DZIAŁA",
    autoCopy: "KOPIA AUTO",
    titleFile: "wczytany plik", titleMd5: "sumy sekcji", titleGame: "stan gry",
    titleAuto: "backup przy każdym zapisie", titleLang: "język / language",
    bannerLead: "UWAGA", bannerTxt: "eldenring.exe działa — zapis do żywego save'a zablokowany · edytuj kopię roboczą (staging), zastosuj po zamknięciu gry",
    pendingChange: "ZMIANA", pendingChanges: "ZMIAN",
    ready: "READY", pickFile: "WSKAŻ PLIK…", pickFile2: "WSKAŻ PLIK .SL2", openRecent: "OTWÓRZ OSTATNI / NAJNOWSZY",
    emptySub: "wskaż plik ER0000.sl2, żeby zacząć",
    emptyNote: 'typowa ścieżka: <span class="mono">%APPDATA%\\EldenRing\\&lt;steamid&gt;\\ER0000.sl2</span><br>edycje zawsze lądują najpierw w kopii roboczej — oryginał rusza dopiero przy ZASTOSUJ.',
    ctxPickChar: "WYBIERZ POSTAĆ, ABY EDYTOWAĆ", ctxSlotEmpty: s => `SLOT ${s} — PUSTY`,
    tagStaging: "STAGING · PODGLĄD ZMIAN", tagOldPatch: p => `STARY PATCH (b${p})`, tagTorrent: "TORRENT !!",
    ctxSelected: "WYBRANA",
    loading: "WCZYTYWANIE SAVE'A…", stagingTxt: "STAGING…", savingTxt: "ZAPIS + WERYFIKACJA…", restoring: "PRZYWRACANIE…",
    stageBtn: "ZASTOSUJ", undoBtn: "COFNIJ", previewBtn: "PODGLĄD", discardBtn: "ODRZUĆ",
    savedOk: (b, ok, tot) => `zapisane · backup: ${b} · MD5 ${ok}/${tot}`,
    savedStatus: b => `zapisane (backup ${b})`, discarded: n => `odrzucono ${n} zmian — oryginał nietknięty`,
    needFile: "najpierw wskaż plik", noChanges: "bez zmian danych", range199: "zakres 1..99 — tyle przyjmuje gra",
    addQueue: r => `dodano do zmian: ${r}`, stageFail: e => `nie udało się: ${e}`,
    applyTitle: "zastosować zmiany?", applyBody: p => `<div>Zostanie zrobiony <b>jeden backup</b> stanu obecnego, brudnopis trafi do pliku i przejdzie weryfikację sum.</div><div class="lcd">plik: ${p}</div>`,
    applyYes: "ZASTOSUJ", stay: "WRÓĆ",
    forceTitle: "oryginał zmienił się poza Rezurem", forceYes: "NADPISZ (--force)",
    discardTitle: n => `odrzucić ${n} zmian?`, discardBody: '<div>Brudnopis zostanie skasowany. <b>Oryginał pozostaje nietknięty</b> — nic nie zapisujemy.</div>', discardYes: "ODRZUĆ",
    undone: r => `cofnięte: ${r.op} ${r.summary} (zostało ${r.left})`,
    unpreviewedOps: "operacje", previewSecs: "zmienione sekcje pliku", previewNone: "(brak różnic)", close: "ZAMKNIJ",
    stagingHint: n => `+1 zmiana oczekująca (${n})`,
    refresh: "ODŚWIEŻ", exportChar: "EKSPORT POSTACI…", importChar: "IMPORT POSTACI…",
    slotN: n => `SLOT ${String(n).padStart(2, "0")}`, emptySlot: "— pusty —", freeSpot: "wolne miejsce", charBadge: "?",
    importTitle: "import postaci", importBody: (f, s) => `Wczytam <b>${f}</b> do slotu ${s} (jako zmiana oczekująca).`, importYes: "IMPORTUJ", importQueued: "import postaci",
    exported: p => `wyeksportowano: ${p}`, pickCharFirst: "najpierw wybierz postać",
    scanAgain: "SKANUJ PONOWNIE", fixAll: "NAPRAW WSZYSTKO (do kolejki)", fixAllTitle: "napraw wszystko", fixAllBody: "Wykona dostępne naprawy (torrent, sumy, hash, profil, weather, DLC, liczniki) na kopii roboczej.", fixAllYes: "NAPRAW",
    md5line: (ok, tot) => `sumy sekcji: ${ok}/${tot}`, md5bad: b => ` · złe: ${b}`,
    healthy: "save wygląda zdrowo — brak ustaleń.",
    fixBtn: id => `NAPRAW: ${id}`, fixQueued: id => "naprawa " + id, slotWord: "slot",
    statsHeader: s => `statystyki — slot ${s}`, lvl: "level", lvlNote: "= suma − 79 (gra wymusza zgodność)",
    nameRunes: "imię i runy", nameColon: "imię 1–16 znaków", runesColon: "runy (pamięć)",
    statQueue: "DODAJ DO KOLEJKI", statReset: "PRZYWRÓĆ WARTOŚCI", statHint: "bez suwaków: +/- (przytrzymaj) albo kliknij wartość i wpisz",
    clickType: "kliknij, aby wpisać", queueStats: s => `staty slot${s}`,
    held: "PRZY SOBIE", storage: "SKRZYNIA", searchInv: "szukaj w ekwipunku…", search: "SZUKAJ", addItem: "DODAJ ITEM…",
    thHandle: "handle", thQty: "ilość", thName: "nazwa", thId: "id", thActions: "akcje",
    remove: "ZDEJMIJ", toStorage: "DO SKRZYNI", toHeld: "PRZY SOBIE", qty: "ILOŚĆ…", setQtyTitle: "ustaw ilość", setQtyYes: "USTAW",
    empty2: "(pusto)", itemRemoved: "usuń item", itemMoved: "przenieś item", itemQty: "ilość itemu",
    addTitle1: "dodaj item — krok 1/2", addTitle2: "dodaj item — krok 2/2", fragment: "fragment nazwy", next: "DALEJ",
    typeToSearch: "wpisz min. 2 znaki…", pickFromList: "kliknij pozycję, żeby wybrać · Enter = pierwsza",
    liveFilters: "filtruje w trakcie pisania",
    pickNo: "numer:", qtyColon: "ilość:", upgradeColon: "upgrade:", addYes: "DODAJ", noHits: "brak trafień",
    addQueued: nm => "dodaj: " + nm,
    loadoutHeader: s => `wyposażenie — slot ${s}`, zones: { weapon: "BROŃ", armor: "ZBROJA", talisman: "TALIZMANY" },
    emptyCell: "— puste —", unequip: "ZDEJMIJ", upg: "+POZ", aff: "AFIN.", aow: "AOW",
    upgTitle: "poziom ulepszenia (0–25)", affTitle: "affinity", aowTitle: "ash of war (nazwa)", aowPh: "np. Bloody Slash",
    equipHeader: "założ z ekwipunku", equipPh: "handle:0x… albo nazwa", equipAt: "gniazdo (opc.)", equipBtn: "ZAŁÓŻ",
    equipQueued: "założ item", weaponUpg: "upgrade broni", affQueued: a => "affinity: " + a, aowQueued: "ash of war",
    worldFilter: "filtr nazwy / ID…", filter: "FILTRUJ", grantAll: "NADAJ CAŁĄ GRUPĘ…",
    noRows: "(brak wpisów)", grantTitle: g => `nadać całą grupę ${g}?`,
    grantBody: n => `Ustawię <b>${n}</b> flag na zdobyte (stan 1) w kopii roboczej. Duża zmiana — sprawdź PODGLĄD przed ZASTOSUJ.`,
    grantYes: n => `NADAJ ${n} FLAG`, flagTitleSet: "ustawić flagę?", flagTitleClear: "zdjąć flagę?", set: "USTAW",
    flagQueued: id => "flaga " + id, groupQueued: g => "grupa " + g,
    spellPh: "nazwa czaru do zapamiętania…", memorize: "ZAPAMIĘTAJ", clearAll: "WYCZYŚĆ WSZYSTKO…", clearAllTitle: "wyczyścić wszystkie gniazda czarów?", clearAllBody: "Wszystkie 14 gniazd zostaną opróżnione (na kopii roboczej).", clearYes: "WYCZYŚĆ",
    spellSlotsHdr: "zapamiętane czary — 14 gniazd", spellListHdr: "lista czarów — wybierz i kliknij ZAPAMIĘTAJ",
    spellFilter: "filtruj czary…", thKind: "typ", thState: "stan", spellsWord: "czarów",
    kindSorc: "czar", kindInca: "inkantacja",
    memoBadge: "ZAPAMIĘTANY", ownedBadge: "W EKWIPUNKU", missBadge: "brak w ekwipunku",
    spellSlot: n => `GNIAZDO ${String(n).padStart(2, "0")}`, forget: "ZAPOMNIJ", enterSpell: "wpisz nazwę czaru",
    spellQueued: n => "czar: " + n, forgotQueued: "zapomnij czar",
    appHeader: s => `wygląd / archetyp — slot ${s}`, sex: "płeć", typeA: "0 — typ A", typeB: "1 — typ B",
    build: "budowa ciała", giftLabel: a => `dar początkowy (0–255; archetyp b${a} zostaje)`,
    appQueued: "wygląd", nothingChanged: "nic nie zmieniono",
    posHeader: s => `pozycja — slot ${s}`, tpHeader: "teleport do lokacji", teleportBtn: "TELEPORTUJ",
    customCoords: "własne współrzędne", setBtn: "USTAW", tpNote: "teleport zsynchronizuje pogodę z regionem mapy (inaczej doctor zgłasza desync).",
    tpQueued: "teleport", tpNeed: "podaj mapę i xyz",
    riskScan: "SKANUJ RYZYKO", riskHint: "ocenia dane niemożliwe + znacznik modyfikacji; to nie jest gwarancja braku flagi.",
    clickScan: "kliknij SKANUJ…", scanning: "SKAN RYZYKA…",
    verdicts: { red: "CZERWONY", yellow: "ŻÓŁTY", green: "ZIELONY" }, issues: n => `${n} uwag`, impossible: " — dane niemożliwe!",
    markerYes: (n, last) => `znacznik: plik MODYFIKOWANY przez Rezura — ${n} operacji; ostatnia ${last}`,
    markerNo: "znacznik: brak śladów Rezura w tym pliku",
    goldLine: g => `GOLD: ${g} — powrót do oryginału z zakładki KOPIE`,
    notes: "notatki",
    riskNotes: ["eksperymentuj na KOPII (backup/GOLD), nie na żywym save'ie", "przed grą online rozważ powrót do GOLD — gra nie odróżnia grzecznych edycji od reszty", "Rezur nie gwarantuje braku flagi: skaner gry patrzy na dane niemożliwe, a my potrafimy sprawdzić tylko część z nich"],
    backupReload: "ODŚWIEŻ", makeGold: "ZRÓB KOPIĘ GOLD",
    retentionNote: r => `rotacja trzyma ${r} kopii; GOLD i przypięte — na zawsze.`,
    thType: "typ", thDate: "data", thSize: "rozmiar",
    restore: "PRZYWRÓĆ…", pin: "PRZYPINIJ", unpin: "ODEPNIJ",
    restoreTitle: "przywrócić kopię?", restoreBody: name => `<div>Plik <b>${name}</b> zastąpi obecny save.</div><div>Przed przywróceniem zrobimy kopię stanu obecnego (pre-restore).</div>`, restoreYes: "PRZYWRÓĆ",
    restoredOk: "przywrócono — możesz porównać i wrócić do nowszego stanu z listy", pinned: "przypięto", unpinned: "odpięto",
    goldMade: "zrobiono kopię GOLD", goldExists: "GOLD już istnieje", noBackup: n => `nie ma kopii: ${n}`,
    logNote: "dziennik edycji — każdy udany zapis (znacznik modyfikowany)",
    thWhen: "kiedy", thOp: "operacja", thBackup: "backup", logEmpty: "(pusto — dziennik zapisuje każdą udaną modyfikację)",
    cfgHeader: "config", retention: "rotacja kopii", watchInt: "interwał watch [s]",
    guardTxt: "blokada zapisu przy działającej grze (guard_live)", autoDocTxt: "auto-diagnostyka po naprawach",
    saveCfg: "ZAPISZ USTAWIENIA", openFolder: "OTWÓRZ FOLDER SAVE'A", watchOnceBtn: "WATCH: JEDEN PRZEBIEG",
    about: "o programie", cfgsaved: "ustawienia zapisane",
    langHeader: "język", langNote: "domyślny: angielski. przełączenie przeładowuje okno.",
    aboutTxt: "100% offline — zero połączeń sieciowych, zero telemetrii. Plik save'a nie opuszcza tego komputera. Edycje zawsze przez kopię roboczą → ZASTOSUJ.",
    pickFileShown: "wskaż plik.", chooseChar: "wybierz postać (zakładka POSTACIE) — panel pokaże dane tego slotu.",
    noBridge: "BRAK MOSTU PYTHONA — otwórz przez `python -m rezur gui`", noBridgeToast: "brak mostu pywebview — to okno podglądu bez silnika",
    watchReason: {},
    cancelled: "anulowano",
  },
};
function t(key, ...a) {
  const v = (I18N[LANG] && I18N[LANG][key]) ?? I18N.en[key];
  return typeof v === "function" ? v(...a) : v;
}
/** tłumaczenie ustaleń doctora po kodzie (EN); PL → oryginalny komunikat silnika */
const FIND_EN = {
  md5_bad: "section MD5 mismatch", steamid_mismatch: "SteamID in the save differs from the folder name",
  summary_name_mismatch: "profile name differs from the slot name", summary_empty: "slot occupied but the selection profile is empty",
  summary_level_mismatch: "profile level differs from the slot level", summary_time_drift: "playtime drift (normal in game-written saves)",
  torrent_bug: "Torrent: hp=0 while state=ACTIVE — loading hang", weather_mismatch: "weather area differs from the map region",
  weather_timer: "weather timer suspiciously large", dlc_unused: "DLC: non-zero bytes in unused fields",
  player_hash_mismatch: "PlayerGameDataHash does not match the data (level/stats/runes/gear)", player_hash_unparsed: "could not verify the hash",
  patch_old: "character saved under an older game patch — load it once on the current patch; old characters can crash the game and editors",
  inv_counter_mismatch: "inventory counters disagree with the actual occupancy", items_unresolved: "items outside our database (newer DLC or mod leftovers — not judging)",
  slot_unparsed: "cannot verify stats (sum−79 ≠ level or foreign format)", orphan_data: "empty slot but contains non-zero leftovers",
  modified_marker: "file modified by Rezur — consider restoring GOLD before going online",
  gaitem_walk: "cannot walk the item table", upgrade_impossible: "impossible weapon upgrade", stats_out_of_range: "a stat is outside 1..99",
  level_out_of_range: "level outside 1..713", qty_over: "items with quantity > 999",
};
const findMsg = f => (LANG === "en" && FIND_EN[f.code]) ? FIND_EN[f.code] : f.message;

const STAT_NAMES = ["vigor", "mind", "endurance", "strength", "dexterity", "intelligence", "faith", "arcane"];

const MOCK = window.location.search.includes("mock");
const S = {
  save: null, info: null, slot: null, tab: "postacie",
  cfg: {}, game: false, pending: 0, busy: false, version: "",
  inv: { loc: "held", q: "", offset: 0, total: 0, rows: [] },
  world: { group: "", q: "", offset: 0, total: 0, rows: [], groups: {} },
};

/* ---------------------------------------------------------------- most ---- */

function P(name, ...args) {
  if (MOCK) return mockApi(name, args);
  if (!window.pywebview || !window.pywebview.api) return Promise.resolve({ error: t("noBridge") });
  return window.pywebview.api[name](...args).catch(e => ({ error: String(e) }));
}
async function bridgeReady() {
  if (MOCK) return true;
  for (let i = 0; i < 60; i++) {
    if (window.pywebview && window.pywebview.api) return true;
    await new Promise(r => setTimeout(r, 100));
  }
  return false;
}

/* ------------------------------------------------------- status / UI ---- */

function setStatus(msg, kind = "") {
  const el = $("#status");
  el.innerHTML = kind === "am" ? `<span class="am">${esc(msg)}</span>` : `<span>${esc(msg)}</span>`;
}
function toast(msg, kind = "info", ms = 4200) {
  const d = document.createElement("div");
  d.className = `toast ${kind}`;
  d.textContent = msg;
  $("#toasts").appendChild(d);
  setTimeout(() => d.remove(), ms);
}
function busy(on, text = null) {
  S.busy = on;
  $("#busy").classList.toggle("hidden", !on);
  $("#busyTxt").textContent = text || t("loading");
  updateStagebar();
}
function modal({ title, body = "", warn = false, actions = [], setup = null }) {
  return new Promise(resolve => {
    const m = $("#modal"), box = $("#mbox");
    box.innerHTML = `
      <div class="mhead ${warn ? "warn" : ""}"><span>${esc(title)}</span></div>
      <div class="mbod">${body}</div>
      <div class="mact"></div>`;
    const done = v => { m.classList.add("hidden"); resolve(v); };
    const act = box.querySelector(".mact");
    actions.forEach(a => {
      const b = document.createElement("button");
      b.className = `key ${a.klass || ""}`;
      b.textContent = a.label;
      b.onclick = () => done(a.value);
      act.appendChild(b);
    });
    if (setup) setup(box, done);   // modale z własną logiką (np. podpowiedzi na żywo)
    m.classList.remove("hidden");
    act.querySelector(".key")?.focus();
  });
}
const confirmDlg = (title, body, warn = false, yes = "OK") =>
  modal({ title, body, warn, actions: [
    { label: yes, value: true, klass: "orange" },
    { label: t("stay"), value: false },
  ] });

/* ------------------------------------------------------------ stan ----- */

function charOfSlot() {
  if (!S.info || S.slot === null) return null;
  return S.info.characters.find(c => c.slot === S.slot && !c.empty) || null;
}
function needSlot() {
  return `<div class="note">${esc(t("chooseChar"))}</div>`;
}
function pluralPending(n) {
  if (LANG === "en") return n === 1 ? t("pendingChange") : t("pendingChanges");
  return n === 1 ? t("pendingChange") : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) ? "ZMIANY" : "ZMIAN";
}
function updateStagebar() {
  $("#pendN").textContent = S.pending;
  $("#pendW").textContent = pluralPending(S.pending);
  $("#btnApply").disabled = S.busy || !S.save || S.pending === 0;
  $("#btnDiscard").disabled = S.busy || !S.save || S.pending === 0;
  $("#btnUndo").disabled = S.busy || !S.save || S.pending === 0;
  $("#btnPreview").disabled = S.busy || !S.save || S.pending === 0;
  const led = $("#ledOk");
  led.className = "led " + (S.busy ? "a blink" : S.info && S.info.md5.ok === S.info.md5.total ? "g" : S.info ? "r" : "");
}
function updateHeader() {
  $("#txtVer").textContent = "FW " + (S.version || "—");
  $("#ledFile").className = "led " + (S.save ? "g" : "");
  $("#txtFile").textContent = S.info ? `${S.info.file} · ${S.info.size_mb} MB` : t("noFile");
  if (S.info) {
    $("#ledMd5").className = "led " + (S.info.md5.ok === S.info.md5.total ? "g" : "r");
    $("#txtMd5").textContent = `MD5 ${S.info.md5.ok}/${S.info.md5.total}`;
  }
  $("#ledGame").className = "led " + (S.game ? "r" : "g");
  $("#txtGame").textContent = S.game ? t("gameRun") : t("gameStop");
  $("#gameBanner").classList.toggle("hidden", !(S.game && S.info && S.info.live));
  $("#railPath").textContent = S.save || "—";
}
function renderCtx() {
  const c = charOfSlot();
  const tags = [];
  if (S.info && S.info.staged) tags.push(`<span class="tag stage">${esc(t("tagStaging"))}</span>`);
  if (c && !c.patch_latest) tags.push(`<span class="tag warn">${esc(t("tagOldPatch", c.patch))}</span>`);
  if (c && c.horse_bug) tags.push(`<span class="tag warn">${esc(t("tagTorrent"))}</span>`);
  if (S.slot === null) { $("#ctx").innerHTML = `<span>${esc(t("ctxPickChar"))}</span>`; return; }
  if (!c) { $("#ctx").innerHTML = `<span>${esc(t("ctxSlotEmpty", String(S.slot).padStart(2, "0")))}</span>${tags.join("")}`; return; }
  $("#ctx").innerHTML =
    `<b>${esc(t("slotN", S.slot))}</b> <b>${esc(c.name)}</b>` +
    `<span>LVL ${c.level}</span><span>${(c.seconds / 3600).toFixed(1)} h</span>` +
    `<span>${esc(c.map_name)}</span><span>RM ${fmtInt(c.runes)}</span>` + tags.join("");
}

/* ----------------------------------------------------------- akcje ----- */

async function doStage(argv, note = "") {
  if (!S.save) return toast(t("needFile"), "err");
  busy(true, t("stagingTxt"));
  const r = await P("stage", S.save, argv);
  busy(false);
  if (r.error) {
    toast(t("stageFail", r.error), "err");
    if (r.output) console.warn(r.output);
    setStatus(r.error);
    return r;
  }
  if (!r.changed) { setStatus(t("noChanges")); toast(t("noChanges"), "info", 2400); await refreshPending(); return r; }
  await refreshPending();
  setStatus(t("stagingHint", S.pending));
  toast(t("addQueue", note || argv[0]) + ` (${S.pending})`, "ok", 2600);
  await refreshCurrent();
  return r;
}
async function refreshPending() {
  if (!S.save) { S.pending = 0; updateStagebar(); return; }
  const r = await P("pending", S.save);
  S.pending = r.error ? 0 : r.count;
  updateStagebar();
}
async function onPreview() {
  const p = await P("pending", S.save);
  const d = await P("preview", S.save);
  const ops = (p.ops || []).map((o, i) => `${String(i + 1).padStart(2, "0")}. [${esc(o.ts)}] ${esc(o.op)} ${esc(o.summary)}`).join("\n");
  const secs = (d.changed || []).join(", ") || t("previewNone");
  await modal({
    title: `${t("previewBtn")} — ${S.pending} ${pluralPending(S.pending).toLowerCase()}`,
    body: `<div class="cap">${esc(t("unpreviewedOps"))}</div><div class="lcd">${ops || "(—)"}</div>
           <div class="cap" style="margin-top:10px">${esc(t("previewSecs"))}</div><div class="lcd">${esc(secs)}</div>`,
    actions: [{ label: t("close"), value: true }],
  });
}
async function onApply() {
  const ok = await confirmDlg(t("applyTitle"), t("applyBody", esc(S.save)), false, t("applyYes"));
  if (!ok) return;
  busy(true, t("savingTxt"));
  let r = await P("apply", S.save, false);
  if (r.error && r.needs_force) {
    busy(false);
    const f = await confirmDlg(t("forceTitle"), `<div>${esc(r.error)}</div>`, true, t("forceYes"));
    if (!f) return;
    busy(true, t("savingTxt"));
    r = await P("apply", S.save, true);
  }
  busy(false);
  if (r.error) { toast(r.error, "err", 7000); setStatus(r.error); return; }
  toast(t("savedOk", r.backup || "—", r.md5_ok, r.md5_total), "ok", 6000);
  setStatus(t("savedStatus", String(r.backup || "").split("\\").pop()));
  await loadSave();
}
async function onDiscard() {
  const p = await P("pending", S.save);
  const ok = await confirmDlg(t("discardTitle", p.count), t("discardBody"), true, t("discardYes"));
  if (!ok) return;
  const r = await P("discard", S.save);
  if (r.error) { toast(r.error, "err"); return; }
  toast(t("discarded", r.ops), "ok");
  setStatus(t("discarded", r.ops));
  await loadSave();
}
async function onUndo() {
  const r = await P("undo", S.save);
  if (r.error) { toast(r.error, "err"); return; }
  toast(t("undone", r.undone), "ok");
  await refreshPending();
  await refreshCurrent();
}

/* ------------------------------------------------------- ładowanie ----- */

async function pickAndLoad() {
  const r = await P("pick_save");
  if (r.error) return toast(r.error, "err");
  if (r.cancelled) return;
  S.save = r.path;
  await loadSave();
}
async function loadSave() {
  if (!S.save) { $("#empty").classList.remove("hidden"); return; }
  busy(true, t("loading"));
  const info = await P("load", S.save);
  busy(false);
  if (info.error) {
    $("#empty").classList.remove("hidden");
    $("#emptyNote").innerHTML = `<span style="color:var(--led-r)">${esc(info.error)}</span>`;
    return;
  }
  S.info = info;
  S.game = info.game_running;
  if (S.slot === null || !info.characters.some(c => c.slot === S.slot && !c.empty)) {
    const first = info.characters.find(c => !c.empty);
    S.slot = first ? first.slot : null;
  }
  $("#empty").classList.add("hidden");
  updateHeader();
  await refreshPending();
  render();
  setStatus(`${info.load_ms} ms · ${info.md5.ok}/${info.md5.total} OK`);
  window.__rezurLoaded = info.characters.filter(c => !c.empty).length;
}
async function refreshCurrent() {
  updateHeader();
  renderCtx();
  const tab = S.tab;
  if (tab === "postacie") renderChars();
  else if (tab === "doktor") renderDoctor();
  else if (tab === "staty") renderStats();
  else if (tab === "ekwipunek") renderInventory();
  else if (tab === "eq") renderEQ();
  else if (tab === "swiat") renderWorld();
  else if (tab === "czary") renderSpells();
  else if (tab === "wyglad") renderLooks();
  else if (tab === "teleport") renderTeleportPanel();
  else if (tab === "ryzyko") renderRisk();
  else if (tab === "kopie") renderBackups();
  else if (tab === "log") renderLog();
  else if (tab === "ustawienia") renderSettings();
}

/* ----------------------------------------------------- panel: POSTACIE -- */

function renderChars() {
  const el = $("#panel-postacie");
  el.innerHTML = `
    <div class="toolbar">
      <button class="key small" data-act="reload">${esc(t("refresh"))}</button>
      <button class="key small" data-act="export">${esc(t("exportChar"))}</button>
      <button class="key small" data-act="import">${esc(t("importChar"))}</button>
    </div>
    <div class="cards">${S.info.characters.map(c => {
      if (c.empty) return `<div class="card empty" data-slot="${c.slot}"><div class="slot mono">${esc(t("slotN", c.slot))}</div>
        <h4>${esc(t("emptySlot"))}</h4><div class="meta">${esc(t("freeSpot"))}</div></div>`;
      const tags = [];
      if (!c.patch_latest) tags.push(`<span class="minitag wa">b${c.patch} !</span>`);
      if (c.horse_bug) tags.push(`<span class="minitag wa">TORRENT</span>`);
      if (!c.parsed) tags.push(`<span class="minitag wa">${esc(t("charBadge"))}</span>`);
      return `<div class="card ${S.slot === c.slot ? "sel" : ""}" data-slot="${c.slot}">
        <div class="slot mono">${esc(t("slotN", c.slot))}${S.slot === c.slot ? " · " + esc(t("ctxSelected")) : ""}</div>
        <div class="pills">${tags.join("")}</div>
        <h4>${esc(c.parsed ? c.name : (c.name || t("charBadge")))}</h4>
        <span class="lcd">LVL ${c.parsed ? c.level : "?"} · ${(c.seconds / 3600).toFixed(1)}H</span>
        <div class="meta">${esc(c.map_name || "")} · RM ${fmtInt(c.runes || 0)}</div>
      </div>`;
    }).join("")}</div>`;
  el.querySelectorAll(".card").forEach(card => card.onclick = async () => {
    S.slot = +card.dataset.slot;
    if (S.info.characters[S.slot].empty) toast(t("ctxSlotEmpty", String(S.slot).padStart(2, "0")), "info");
    await refreshCurrent();
  });
  el.querySelector("[data-act=reload]").onclick = () => loadSave();
  el.querySelector("[data-act=export]").onclick = async () => {
    if (!charOfSlot()) return toast(t("pickCharFirst"), "err");
    const r = await P("export_char", S.save, S.slot);
    if (r.error) toast(r.error, "err");
    else if (!r.cancelled) toast(t("exported", r.out), "ok");
  };
  el.querySelector("[data-act=import]").onclick = async () => {
    if (!charOfSlot()) return toast(t("pickCharFirst"), "err");
    const j = await P("pick_json");
    if (j.error) return toast(j.error, "err");
    if (j.cancelled) return;
    const ok = await confirmDlg(t("importTitle"), t("importBody", esc(j.path.split("\\").pop()), S.slot), false, t("importYes"));
    if (!ok) return;
    await doStage(["import", "--to", String(S.slot), "--in", j.path], t("importQueued"));
  };
}

/* ------------------------------------------------------- panel: DOKTOR -- */

async function renderDoctor() {
  const el = $("#panel-doktor");
  el.innerHTML = `<div class="toolbar">
      <button class="key small" data-act="scan">${esc(t("scanAgain"))}</button>
      <button class="key small orange" data-act="fixall">${esc(t("fixAll"))}</button>
      <span class="note" id="md5line"></span>
    </div><div id="findings"></div>`;
  el.querySelector("[data-act=scan]").onclick = () => loadDoctor();
  el.querySelector("[data-act=fixall]").onclick = async () => {
    const ok = await confirmDlg(t("fixAllTitle"), t("fixAllBody"), false, t("fixAllYes"));
    if (ok) await doStage(["fix"], t("fixAllTitle"));
  };
  await loadDoctor();
}
async function loadDoctor() {
  const r = await P("doctor", S.save);
  if (r.error) { $("#findings").innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  $("#md5line").textContent = t("md5line", r.md5.ok, r.md5.total) + (r.md5.bad.length ? t("md5bad", r.md5.bad.join(", ")) : "");
  const el = $("#findings");
  if (!r.findings.length) { el.innerHTML = `<div class="frow"><span class="sev ok"></span><div class="fbody"><div class="fmsg">${esc(t("healthy"))}</div></div></div>`; return; }
  el.innerHTML = r.findings.map(f => `
    <div class="frow">
      <span class="sev ${f.level === "error" ? "err" : f.level === "warning" ? "war" : "ok"}"></span>
      <div class="fbody">
        <div class="fmsg">${esc(findMsg(f))}</div>
        <div class="fcode">${esc(f.code)}${f.slot !== null && f.slot !== undefined ? ` · ${esc(t("slotWord"))} ${f.slot}` : ""}</div>
      </div>
      ${f.fix ? `<button class="key small" data-fix="${esc(f.fix)}">${esc(t("fixBtn", f.fix))}</button>` : ""}
    </div>`).join("");
  el.querySelectorAll("[data-fix]").forEach(b => b.onclick = () =>
    doStage(["fix", "--only", b.dataset.fix], t("fixQueued", b.dataset.fix)));
}

/* -------------------------------------------------------- panel: STATY -- */

function renderStats() {
  const el = $("#panel-staty");
  const c = charOfSlot();
  if (!c) { el.innerHTML = needSlot(); return; }
  let draft = c.stats.slice();
  const row = (i, name) => `
    <div class="statrow">
      <span class="sname">${name}</span>
      <span class="sval lcd" data-i="${i}" title="${esc(t("clickType"))}">${draft[i]}</span>
      <span class="stbtn" data-plus="1" data-i="${i}">+</span>
      <span class="stbtn" data-plus="-1" data-i="${i}">−</span>
    </div>`;
  el.innerHTML = `
    <div class="statmod">
      <h3 class="sect">${esc(t("statsHeader", String(S.slot).padStart(2, "0")))}</h3>
      ${STAT_NAMES.map((n, i) => row(i, n)).join("")}
      <div class="statrow lvl"><span class="sname">${esc(t("lvl"))}</span>
        <span class="sval lcd big" id="lvlPrev">${draft.reduce((a, b) => a + b, 0) - 79}</span>
        <span class="ednote">${esc(t("lvlNote"))}</span></div>
      <h3 class="sect">${esc(t("nameRunes"))}</h3>
      <div class="inline">
        <input class="lcdin" id="statName" style="width:220px" maxlength="16" value="${esc(c.name)}">
        <input class="lcdin" id="statRunes" style="width:150px" type="number" value="${c.runes}">
        <span class="ednote">${esc(t("nameColon"))} · ${esc(t("runesColon"))}</span>
      </div>
      <div class="keyrow" style="margin-top:14px">
        <button class="key orange" id="statStage">${esc(t("statQueue"))}</button>
        <button class="key" id="statReset">${esc(t("statReset"))}</button>
        <span class="ednote">${esc(t("statHint"))}</span>
      </div>
    </div>`;
  const lvl = () => { $("#lvlPrev").textContent = draft.reduce((a, b) => a + b, 0) - 79; };
  el.querySelectorAll(".stbtn").forEach(b => {
    const i = +b.dataset.i, dir = +b.dataset.plus;
    let hold, rep;
    const bang = () => {
      const v = Math.max(1, Math.min(99, draft[i] + dir));
      if (v === draft[i]) { toast(t("range199"), "info", 1800); return; }
      draft[i] = v;
      el.querySelector(`.sval[data-i="${i}"]`).textContent = v;
      lvl();
    };
    b.addEventListener("pointerdown", e => { e.preventDefault(); bang(); hold = setTimeout(() => { rep = setInterval(bang, 70); }, 380); });
    ["pointerup", "pointerleave", "pointercancel"].forEach(ev => b.addEventListener(ev, () => { clearTimeout(hold); clearInterval(rep); }));
  });
  el.querySelectorAll(".sval[data-i]").forEach(sv => sv.onclick = () => {
    const i = +sv.dataset.i;
    const inp = document.createElement("input");
    inp.className = "lcdin"; inp.style.width = "62px"; inp.style.fontSize = "15px"; inp.style.textAlign = "right";
    inp.value = draft[i];
    sv.replaceWith(inp); inp.focus(); inp.select();
    const commit = ok => {
      if (ok) {
        const v = parseInt(inp.value, 10);
        if (Number.isNaN(v) || v < 1 || v > 99) toast(t("range199"), "err");
        else { draft[i] = v; lvl(); }
      }
      const back = document.createElement("span");
      back.className = "sval lcd"; back.dataset.i = i; back.title = t("clickType");
      back.textContent = draft[i];
      inp.replaceWith(back);
      back.onclick = sv.onclick;
    };
    inp.onkeydown = e => { if (e.key === "Enter") commit(true); if (e.key === "Escape") commit(false); };
    inp.onblur = () => commit(true);
  });
  el.querySelector("#statReset").onclick = () => renderStats();
  el.querySelector("#statStage").onclick = async () => {
    const argv = ["stats", "--slot", String(S.slot)];
    const parts = draft.map((v, i) => v !== c.stats[i] ? `${STAT_NAMES[i]}=${v}` : null).filter(Boolean);
    if (parts.length) argv.push("--set", parts.join(","));
    const name = el.querySelector("#statName").value.trim();
    if (name && name !== c.name) argv.push("--name", name);
    const runes = parseInt(el.querySelector("#statRunes").value, 10);
    if (!Number.isNaN(runes) && runes !== c.runes) argv.push("--runes", String(runes));
    if (argv.length === 2) return toast(t("nothingChanged"), "info");
    await doStage(argv, t("queueStats", S.slot));
  };
}

/* --------------------------------------------------- panel: EKWIPUNEK -- */

function renderInventory() {
  const el = $("#panel-ekwipunek");
  const c = charOfSlot();
  if (!c) { el.innerHTML = needSlot(); return; }
  el.innerHTML = `
    <div class="toolbar">
      <div class="swbox ${S.inv.loc === "held" ? "on" : ""}" id="invLoc" title="${esc(t("held"))} / ${esc(t("storage"))}"><i></i></div>
      <span class="ednote">${S.inv.loc === "held" ? esc(t("held")) : esc(t("storage"))}</span>
      <input class="lcdin" id="invQ" placeholder="${esc(t("searchInv"))}" style="width:230px" value="${esc(S.inv.q)}" autocomplete="off">
      <button class="key small" id="invGo">${esc(t("search"))}</button>
      <button class="key small orange" id="invAdd">${esc(t("addItem"))}</button>
      <span class="livehint" id="invLive">${esc(t("liveFilters"))}</span>
    </div>
    <table class="tbl"><thead><tr><th class="mono" style="width:110px">${esc(t("thHandle"))}</th><th style="width:64px">${esc(t("thQty"))}</th>
      <th>${esc(t("thName"))}</th><th class="mono" style="width:110px">${esc(t("thId"))}</th><th style="width:330px">${esc(t("thActions"))}</th></tr></thead>
      <tbody id="invRows"></tbody></table>
    <div class="pager"><button class="key" id="invPrev">‹</button><span id="invInfo"></span>
      <button class="key" id="invNext">›</button></div>`;
  stickBars(el);
  const load = async () => {
    const r = await P("inventory", S.save, S.slot, S.inv.loc, S.inv.q, S.inv.offset, 100);
    if (r.error) { toast(r.error, "err"); return; }
    S.inv.total = r.total;
    const rows = S.inv.q ? rankByName(r.rows, S.inv.q) : r.rows;
    $("#invRows").innerHTML = rows.map(x => `
      <tr><td class="mono">${x.handle_hex}</td><td class="mono">${x.qty}</td>
      <td class="grow" title="${esc(x.name)}">${esc(x.name)}</td><td class="mono">${x.hex}</td>
      <td><div class="acts">
        <button class="key small" data-a="rm" data-h="${x.handle}">${esc(t("remove"))}</button>
        <button class="key small" data-a="mv" data-h="${x.handle}">${esc(S.inv.loc === "held" ? t("toStorage") : t("toHeld"))}</button>
        <button class="key small" data-a="qty" data-h="${x.handle}" data-q="${x.qty}">${esc(t("qty"))}</button>
      </div></td></tr>`).join("") || `<tr><td colspan="5" class="note">${esc(t("empty2"))}</td></tr>`;
    $("#invInfo").textContent = `${S.inv.offset + 1}–${Math.min(S.inv.offset + 100, r.total)} / ${r.total}`;
    $("#invRows").querySelectorAll("[data-a]").forEach(b => b.onclick = async () => {
      const h = "handle:0x" + (+b.dataset.h >>> 0).toString(16).toUpperCase();
      if (b.dataset.a === "rm")
        await doStage(["item", "--slot", String(S.slot), "--remove", "x", "--handle", b.dataset.h], t("itemRemoved"));
      else if (b.dataset.a === "mv")
        await doStage(["item", "--slot", String(S.slot), "--move", h, "--to", S.inv.loc === "held" ? "storage" : "held"], t("itemMoved"));
      else {
        const qv0 = b.dataset.q;
        const ok = await modal({ title: t("setQtyTitle"), body: `<input class="lcdin" id="qtyIn" style="width:140px" value="${qv0}">`,
          actions: [{ label: t("setQtyYes"), value: true, klass: "orange" }, { label: t("stay"), value: false }] });
        if (ok !== true) return;
        const qv = $("#qtyIn")?.value ?? qv0;
        await doStage(["item", "--slot", String(S.slot), "--set-qty", `${h}=${qv}`], t("itemQty"));
      }
      load();
    });
  };
  el.querySelector("#invLoc").onclick = () => { S.inv.loc = S.inv.loc === "held" ? "storage" : "held"; S.inv.offset = 0; renderInventory(); };
  const applyQ = () => {
    S.inv.q = $("#invQ").value.trim();
    S.inv.offset = 0;
    const hint = $("#invLive");
    if (hint) {
      hint.classList.toggle("on", !!S.inv.q);
      hint.textContent = S.inv.q ? `${t("liveFilters")} · „${S.inv.q}"` : t("liveFilters");
    }
    load();
  };
  el.querySelector("#invGo").onclick = () => applyQ();
  $("#invQ").oninput = debounce(applyQ, 170);
  $("#invQ").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); applyQ(); } };
  el.querySelector("#invPrev").onclick = () => { S.inv.offset = Math.max(0, S.inv.offset - 100); load(); };
  el.querySelector("#invNext").onclick = () => { if (S.inv.offset + 100 < S.inv.total) { S.inv.offset += 100; load(); } };
  el.querySelector("#invAdd").onclick = () => addItemFlow();
  load();
}
async function addItemFlow() {
  const pick = await modal({
    title: t("addTitle1"),
    body: `<div class="field" style="max-width:none">
             <label>${esc(t("fragment"))}</label>
             <input class="lcdin" id="qu2" style="width:340px" autocomplete="off" placeholder="${esc(t("typeToSearch"))}">
           </div>
           <div class="suggbox" id="suggBox"></div>
           <div class="note" style="margin-top:8px">${esc(t("pickFromList"))}</div>`,
    actions: [{ label: t("stay"), value: false }],
    setup: (box, done) => {
      const inp = box.querySelector("#qu2"), list = box.querySelector("#suggBox");
      attachSuggest(inp, list, async q => {
        const r = await P("find", q, 24);
        if (r.error) { toast(r.error, "err"); return []; }
        return r.items || [];
      }, { onPick: it => done(it) });
      setTimeout(() => inp.focus(), 40);
    },
  });
  if (!pick) return;
  const ok2 = await modal({
    title: t("addTitle2"),
    body: `<div class="lcd" style="padding:8px 10px">${esc(pick.name)} <span class="scat">${esc(pick.cat || "")}</span></div>
      <div class="inline" style="margin-top:10px">
        <span class="ednote">${esc(t("qtyColon"))}</span><input class="lcdin" id="qt" type="number" value="1" style="width:70px">
        <span class="ednote">${esc(t("upgradeColon"))}</span><input class="lcdin" id="up" type="number" value="0" style="width:70px">
      </div>`,
    actions: [{ label: t("addYes"), value: true, klass: "orange" }, { label: t("stay"), value: false }],
  });
  if (ok2 !== true) return;
  const argv = ["item", "--slot", String(S.slot), "--add", pick.name, "--qty", $("#qt")?.value || "1"];
  const upg = parseInt($("#up")?.value || "0", 10);
  if (upg > 0) argv.push("--upgrade", String(upg));
  if (S.inv.loc === "storage") argv.push("--storage");
  await doStage(argv, t("addQueued", pick.name));
  S.inv.q = ""; renderInventory();
}

/* ----------------------------------------------------------- panel: EQ -- */

async function renderEQ() {
  const el = $("#panel-eq");
  const c = charOfSlot();
  if (!c) { el.innerHTML = needSlot(); return; }
  const r = await P("equipment", S.save, S.slot);
  if (r.error) { el.innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  const byZone = {};
  r.equipped.forEach(e => { (byZone[e.zone] = byZone[e.zone] || []).push(e); });
  const seg = zone => `<div class="eqzone">${esc(t("zones")[zone] || zone)}</div><div class="grid eqgrid">` +
    (byZone[zone] || []).map(e => `
      <div class="cell ${e.empty ? "empty" : ""}">
        <div class="cslot">${String(e.slot).padStart(2, "0")}</div>
        <div class="cname" title="${esc(e.name || "")}">${e.empty ? esc(t("emptyCell")) : esc(e.name || `0x${(e.item_id || 0).toString(16).toUpperCase()}`)}</div>
        ${e.empty ? "" : `<div class="cact">
          <button class="key small" data-eu="${e.slot}">${esc(t("unequip"))}</button>
          ${zone === "weapon" ? `
            <button class="key small" data-up="${e.handle}">${esc(t("upg"))}</button>
            <button class="key small" data-af="${e.handle}">${esc(t("aff"))}</button>
            <button class="key small" data-aw="${e.handle}">${esc(t("aow"))}</button>` : ""}
        </div>`}
      </div>`).join("") + `</div>`;
  el.innerHTML = `<h3 class="sect">${esc(t("loadoutHeader", String(S.slot).padStart(2, "0")))}</h3>`
    + ["weapon", "armor", "talisman"].map(seg).join("")
    + `<h3 class="sect">${esc(t("equipHeader"))}</h3>
       <div class="inline"><input class="lcdin" id="eqH" style="width:230px" placeholder="${esc(t("equipPh"))}" autocomplete="off">
       <input class="lcdin" id="eqAt" type="number" style="width:90px" placeholder="${esc(t("equipAt"))}">
       <button class="key orange" id="eqGo">${esc(t("equipBtn"))}</button>
       <span class="livehint" id="eqLive">${esc(t("liveFilters"))}</span></div>
       <div class="suggbox" id="eqSugg"></div>`;
  el.querySelectorAll("[data-eu]").forEach(b => b.onclick = () => doStage(["unequip", "--slot", String(S.slot), "--at", b.dataset.eu], t("unequip")));
  el.querySelectorAll("[data-up]").forEach(b => b.onclick = async () => {
    const v = await modal({ title: t("upgTitle"), body: `<input class="lcdin" id="upv" type="number" value="10" style="width:90px">`,
      actions: [{ label: t("set"), value: true, klass: "orange" }, { label: t("stay"), value: false }] });
    if (v !== true) return;
    await doStage(["item", "--slot", String(S.slot), "--set-upgrade", "x=" + ($("#upv")?.value || "10"), "--handle", b.dataset.up], t("weaponUpg"));
    renderEQ();
  });
  el.querySelectorAll("[data-af]").forEach(b => b.onclick = async () => {
    const opts = ["Standard", "Heavy", "Keen", "Quality", "Fire", "Flame Art", "Lightning", "Sacred", "Magic", "Cold", "Poison", "Blood", "Occult"];
    const v = await modal({ title: t("affTitle"), body: `<div class="lcd" style="white-space:pre">` + opts.map((o, i) => `${i + 1}. ${o}`).join("\n") + `</div>
      <div class="inline" style="margin-top:8px"><span class="ednote">${esc(t("pickNo"))}</span><input class="lcdin" id="afv" type="number" value="1" style="width:70px"></div>`,
      actions: [{ label: t("set"), value: true, klass: "orange" }, { label: t("stay"), value: false }] });
    if (v !== true) return;
    const name = opts[Math.min(opts.length, Math.max(1, parseInt($("#afv")?.value || "1", 10))) - 1];
    await doStage(["item", "--slot", String(S.slot), "--affinity", "x=" + name, "--handle", b.dataset.af], t("affQueued", name));
    renderEQ();
  });
  el.querySelectorAll("[data-aw]").forEach(b => b.onclick = async () => {
    const v = await modal({ title: t("aowTitle"), body: `<input class="lcdin" id="awv" style="width:300px" placeholder="${esc(t("aowPh"))}">`,
      actions: [{ label: t("set"), value: true, klass: "orange" }, { label: t("stay"), value: false }] });
    if (v !== true) return;
    await doStage(["item", "--slot", String(S.slot), "--aow", "x=" + ($("#awv")?.value || ""), "--handle", b.dataset.aw], t("aowQueued"));
    renderEQ();
  });
  el.querySelector("#eqGo").onclick = async () => {
    const v = $("#eqH").value.trim();
    if (!v) return;
    const argv = ["equip", "--slot", String(S.slot)];
    const m = v.match(/^(?:handle:)?(0x[0-9a-f]+)$/i);
    if (m) argv.push("--handle", m[1]);
    else argv.push("--item", v);
    const at = $("#eqAt").value.trim();
    if (at !== "") argv.push("--at", at);
    await doStage(argv, t("equipQueued"));
    renderEQ();
  };
  attachSuggest($("#eqH"), $("#eqSugg"), async q => {
    const r = await P("inventory", S.save, S.slot, "held", q, 0, 14);
    return r.error ? [] : r.rows.map(x => ({ name: x.name, cat: x.handle_hex }));
  }, { min: 2, enterFallback: () => el.querySelector("#eqGo").click() });
}

/* -------------------------------------------------------- panel: ŚWIAT -- */

async function renderWorld() {
  const el = $("#panel-swiat");
  const c = charOfSlot();
  if (!c) { el.innerHTML = needSlot(); return; }
  if (!Object.keys(S.world.groups).length) {
    const g = await P("world_groups");
    if (!g.error) S.world.groups = g.groups;
  }
  const groups = Object.keys(S.world.groups).sort();
  if (!S.world.group) S.world.group = groups.includes("boss_defeat") ? "boss_defeat" : groups[0];
  el.innerHTML = `
    <div class="toolbar">
      <select class="lcdin" id="wgrp" style="width:230px">${groups.map(g =>
        `<option value="${g}" ${g === S.world.group ? "selected" : ""}>${g} (${S.world.groups[g]})</option>`).join("")}</select>
      <input class="lcdin" id="wq" placeholder="${esc(t("worldFilter"))}" style="width:210px" value="${esc(S.world.q)}" autocomplete="off">
      <button class="key small" id="wgo">${esc(t("filter"))}</button>
      <button class="key small orange" id="wall">${esc(t("grantAll"))}</button>
      <span class="livehint" id="wLive">${esc(t("liveFilters"))}</span>
    </div>
    <div id="wrows"></div>
    <div class="pager"><button class="key" id="wPrev">‹</button><span id="wInfo">—</span><button class="key" id="wNext">›</button></div>`;
  stickBars(el);

  const loadW = async () => {
    const r = await P("world_view", S.save, S.slot, S.world.group, S.world.q, S.world.offset, 200);
    S.world.total = r.error ? 0 : r.total;
    S.world.rows = r.error ? [] : r.rows;
    $("#wrows").innerHTML = S.world.rows.map(e => `
      <div class="worldrow">
        <span class="wid">${e.id}</span>
        <span class="wname">${mark(e.name, S.world.q)}</span>
        <span class="wdesc">${esc(e.desc || "")}</span>
        <span class="swbox ${e.value ? "on" : ""}" data-fl="${e.id}" data-v="${e.value ? 1 : 0}"><i></i></span>
      </div>`).join("") || `<div class="note">${esc(t("noRows"))}</div>`;
    $("#wInfo").textContent = S.world.total
      ? `${S.world.offset + 1}–${Math.min(S.world.offset + 200, S.world.total)} / ${S.world.total}` : "0 / 0";
    $("#wrows").querySelectorAll("[data-fl]").forEach(b => b.onclick = async () => {
      const id = b.dataset.fl, cur = b.dataset.v === "1";
      const ok = await confirmDlg(cur ? t("flagTitleClear") : t("flagTitleSet"), `ID <span class="mono">${id}</span> → ${cur ? 0 : 1}`, false, t("set"));
      if (!ok) return;
      await doStage(["world", "--slot", String(S.slot), "--group", S.world.group, "--set", id, "--state", cur ? "0" : "1"], t("flagQueued", id));
      loadW();
    });
  };
  const applyW = () => {
    S.world.q = $("#wq").value.trim();
    S.world.offset = 0;
    const hint = $("#wLive");
    if (hint) {
      hint.classList.toggle("on", !!S.world.q);
      hint.textContent = S.world.q ? `${t("liveFilters")} · „${S.world.q}"` : t("liveFilters");
    }
    loadW();
  };
  el.querySelector("#wgrp").onchange = e => { S.world.group = e.target.value; S.world.offset = 0; loadW(); };
  el.querySelector("#wgo").onclick = () => applyW();
  $("#wq").oninput = debounce(applyW, 170);
  $("#wq").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); applyW(); } };
  el.querySelector("#wPrev").onclick = () => { if (S.world.offset > 0) { S.world.offset = Math.max(0, S.world.offset - 200); loadW(); } };
  el.querySelector("#wNext").onclick = () => { if (S.world.offset + 200 < S.world.total) { S.world.offset += 200; loadW(); } };
  el.querySelector("#wall").onclick = async () => {
    const n = S.world.total;
    const ok = await confirmDlg(t("grantTitle", S.world.group), t("grantBody", n), false, t("grantYes", n));
    if (ok) { await doStage(["world", "--slot", String(S.slot), "--group", S.world.group, "--all", "--state", "1"], t("groupQueued", S.world.group)); loadW(); }
  };
  await loadW();
}

/* -------------------------------------------------------- panel: CZARY -- */

let SPQ = "";   // filtr listy czarów (trzymany między odświeżeniami panelu)

async function renderSpells() {
  const el = $("#panel-czary");
  const c = charOfSlot();
  if (!c) { el.innerHTML = needSlot(); return; }
  const r = await P("spells", S.save, S.slot);
  if (r.error) { el.innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  el.innerHTML = `
    <h3 class="sect">${esc(t("spellSlotsHdr"))}</h3>
    <div class="grid spellgrid">${r.spells.map(sp => `
      <div class="cell ${sp.empty ? "empty" : ""}">
        <div class="cslot">${esc(t("spellSlot", sp.slot))}</div>
        <div class="cname">${sp.empty ? esc(t("emptyCell")) : esc(sp.name)}</div>
        ${sp.empty ? "" : `<div class="cact"><button class="key small" data-fg="${sp.slot}">${esc(t("forget"))}</button></div>`}
      </div>`).join("")}</div>
    <h3 class="sect">${esc(t("spellListHdr"))}</h3>
    <div class="toolbar">
      <input class="lcdin" id="spQ" placeholder="${esc(t("spellFilter"))}" style="width:260px" autocomplete="off" value="${esc(SPQ)}">
      <button class="key small" id="spReload">${esc(t("refresh"))}</button>
      <button class="key small" id="spClear">${esc(t("clearAll"))}</button>
      <span class="livehint" id="spLive">${esc(t("liveFilters"))}</span>
    </div>
    <table class="tbl"><thead><tr>
      <th style="width:110px">${esc(t("thKind"))}</th><th>${esc(t("thName"))}</th>
      <th class="mono" style="width:80px">${esc(t("thId"))}</th>
      <th style="width:170px">${esc(t("thState"))}</th><th style="width:150px">${esc(t("thActions"))}</th>
    </tr></thead><tbody id="spRows"></tbody></table>`;
  stickBars(el);

  const load = async () => {
    const res = await P("spell_list", S.save, S.slot, SPQ, 400);
    if (res.error) { $("#spRows").innerHTML = `<tr><td colspan="5" class="note">${esc(res.error)}</td></tr>`; return; }
    const rows = SPQ ? rankByName(res.rows, SPQ) : res.rows;
    const hint = $("#spLive");
    if (hint) {
      hint.classList.toggle("on", !!SPQ);
      hint.textContent = SPQ ? `${t("liveFilters")} · „${SPQ}" (${res.count})` : `${res.count} ${t("spellsWord")}`;
    }
    $("#spRows").innerHTML = rows.map(row => `
      <tr class="${row.memorized ? "sel" : ""}">
        <td class="mono">${esc(row.kind === "sorcery" ? t("kindSorc") : t("kindInca"))}</td>
        <td class="grow" title="${esc(row.name)}">${mark(row.name, SPQ)}</td>
        <td class="mono">${row.id}</td>
        <td>${row.memorized ? `<span class="mark pin">${esc(t("memoBadge"))}</span>`
              : row.owned ? `<span class="mark gold">${esc(t("ownedBadge"))}</span>`
              : `<span class="note">${esc(t("missBadge"))}</span>`}</td>
        <td><div class="acts"><button class="key small orange" data-mem="${esc(row.name)}"${row.memorized ? " disabled" : ""}>${esc(t("memorize"))}</button></div></td>
      </tr>`).join("") || `<tr><td colspan="5" class="note">${esc(t("noHits"))}</td></tr>`;
    $("#spRows").querySelectorAll("[data-mem]").forEach(b => b.onclick = async () => {
      await doStage(["spells", "--slot", String(S.slot), "--memorize", b.dataset.mem], t("spellQueued", b.dataset.mem));
      renderSpells();
    });
  };

  $("#spQ").oninput = debounce(() => { SPQ = $("#spQ").value.trim(); load(); }, 170);
  $("#spQ").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); SPQ = $("#spQ").value.trim(); load(); } };
  el.querySelector("#spReload").onclick = () => renderSpells();
  el.querySelector("#spClear").onclick = async () => {
    const ok = await confirmDlg(t("clearAllTitle"), t("clearAllBody"), true, t("clearYes"));
    if (ok) { await doStage(["spells", "--slot", String(S.slot), "--clear"], t("clearAll")); renderSpells(); }
  };
  el.querySelectorAll("[data-fg]").forEach(b => b.onclick = async () => {
    await doStage(["spells", "--slot", String(S.slot), "--forget", b.dataset.fg], t("forgotQueued"));
    renderSpells();
  });
  await load();
}

/* ------------------------------------------------------ panel: WYGLĄD --- */

async function renderLooks() {
  const el = $("#panel-wyglad");
  const c = charOfSlot();
  if (!c) { el.innerHTML = needSlot(); return; }
  const r = await P("appearance", S.save, S.slot);
  if (r.error) { el.innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  el.innerHTML = `
    <h3 class="sect">${esc(t("appHeader", String(S.slot).padStart(2, "0")))}</h3>
    <div class="field"><label>${esc(t("sex"))}</label>
      <select class="lcdin" id="apG" style="width:170px"><option value="0" ${r.gender === 0 ? "selected" : ""}>${esc(t("typeA"))}</option>
      <option value="1" ${r.gender === 1 ? "selected" : ""}>${esc(t("typeB"))}</option></select></div>
    <div class="field"><label>${esc(t("build"))}</label>
      <select class="lcdin" id="apB" style="width:170px"><option value="0" ${r.body_type === 0 ? "selected" : ""}>0</option>
      <option value="1" ${r.body_type === 1 ? "selected" : ""}>1</option></select></div>
    <div class="field"><label>${esc(t("giftLabel", r.archetype))}</label>
      <input class="lcdin" id="apGift" type="number" min="0" max="255" style="width:170px" value="${r.gift}"></div>
    <button class="key orange" id="apGo">${esc(t("statQueue"))}</button>`;
  el.querySelector("#apGo").onclick = async () => {
    const argv = ["appearance", "--slot", String(S.slot)];
    const g = $("#apG").value, b = $("#apB").value, gift = $("#apGift").value;
    if (+g !== r.gender) argv.push("--gender", g);
    if (+b !== r.body_type) argv.push("--body", b);
    if (+gift !== r.gift) argv.push("--gift", gift);
    if (argv.length === 2) return toast(t("nothingChanged"), "info");
    await doStage(argv, t("appQueued"));
  };
}

/* --------------------------------------------------- panel: TELEPORT ---- */

async function renderTeleportPanel() {
  const el = $("#panel-teleport");
  const c = charOfSlot();
  if (!c) { el.innerHTML = needSlot(); return; }
  const r = await P("teleport_info", S.save, S.slot);
  if (r.error) { el.innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  el.innerHTML = `
    <h3 class="sect">${esc(t("posHeader", String(S.slot).padStart(2, "0")))}</h3>
    <div class="lcd" style="padding:9px 12px;display:inline-block">${esc(r.map_name)} · x=${r.xyz[0].toFixed(1)} y=${r.xyz[1].toFixed(1)} z=${r.xyz[2].toFixed(1)}</div>
    <h3 class="sect">${esc(t("tpHeader"))}</h3>
    <div class="inline">
      <select class="lcdin" id="tpSel" style="width:250px">${r.destinations.map(d => `<option>${d}</option>`).join("")}</select>
      <button class="key orange" id="tpGo">${esc(t("teleportBtn"))}</button>
    </div>
    <h3 class="sect">${esc(t("customCoords"))}</h3>
    <div class="inline">
      <input class="lcdin" id="tpMap" placeholder="m60_43_38_00" style="width:170px">
      <input class="lcdin" id="tpXyz" placeholder="x,y,z" style="width:190px">
      <button class="key" id="tpGo2">${esc(t("setBtn"))}</button>
    </div>
    <div class="note" style="margin-top:12px">${esc(t("tpNote"))}</div>`;
  el.querySelector("#tpGo").onclick = () =>
    doStage(["teleport", "--slot", String(S.slot), "--to", el.querySelector("#tpSel").value], t("tpQueued")).then(renderTeleportPanel);
  el.querySelector("#tpGo2").onclick = () => {
    const m = $("#tpMap").value.trim(), xyz = $("#tpXyz").value.trim();
    if (!m || !xyz) return toast(t("tpNeed"), "err");
    doStage(["teleport", "--slot", String(S.slot), "--map", m, "--xyz", xyz], t("tpQueued")).then(renderTeleportPanel);
  };
}

/* -------------------------------------------------------- panel: RYZYKO -- */

async function renderRisk() {
  const el = $("#panel-ryzyko");
  if (!S.save) { el.innerHTML = `<div class="note">${esc(t("pickFileShown"))}</div>`; return; }
  el.innerHTML = `<div class="toolbar"><button class="key small" data-act="scan">${esc(t("riskScan"))}</button>
    <span class="note">${esc(t("riskHint"))}</span></div>
    <div id="riskBody" class="note">${esc(t("clickScan"))}</div>`;
  el.querySelector("[data-act=scan]").onclick = async () => {
    busy(true, t("scanning"));
    const r = await P("risk_scan", S.save);
    busy(false);
    if (r.error) { $("#riskBody").innerHTML = esc(r.error); return; }
    const perSlot = {};
    r.findings.forEach(f => { if (f.slot !== null) (perSlot[f.slot] = perSlot[f.slot] || []).push(f); });
    const chars = S.info.characters.filter(c => !c.empty);
    const V = t("verdicts");
    const bars = chars.map(c => {
      const fs = perSlot[c.slot] || [];
      const v = fs.some(f => f.level === "error") ? "red" : fs.some(f => f.level === "warning") ? "yellow" : "green";
      return `<div class="riskbar ${v}"><span class="verdict">${esc(V[v])}</span>
        <b>${esc(t("slotN", c.slot))} ${esc(c.name)}</b>
        <span class="note">${esc(t("issues", fs.filter(f => f.level !== "info").length))}${fs.some(f => f.level === "error") ? esc(t("impossible")) : ""}</span></div>`;
    }).join("");
    const rows = r.findings.map(f => `<div class="frow"><span class="sev ${f.level === "error" ? "err" : f.level === "warning" ? "war" : "ok"}"></span>
      <div class="fbody"><div class="fmsg">${esc(findMsg(f))}</div><div class="fcode">${esc(f.code)}${f.slot !== null ? " · " + esc(t("slotWord")) + " " + f.slot : ""}</div></div></div>`).join("");
    const mod = r.modified || {};
    const notes = t("riskNotes") || r.notes || [];
    $("#riskBody").innerHTML = bars +
      (mod.count ? `<div class="lcd" style="padding:8px 11px;margin-bottom:10px">${esc(t("markerYes", mod.count, mod.last))}</div>`
                 : `<div class="lcd" style="padding:8px 11px;margin-bottom:10px">${esc(t("markerNo"))}</div>`) +
      (r.gold ? `<div class="lcd" style="padding:8px 11px;margin-bottom:10px">${esc(t("goldLine", r.gold))}</div>` : "") +
      rows +
      `<h3 class="sect">${esc(t("notes"))}</h3><div class="note">${notes.map(n => "• " + esc(n)).join("<br>")}</div>`;
  };
}

/* --------------------------------------------------------- panel: KOPIE -- */

async function renderBackups() {
  const el = $("#panel-kopie");
  if (!S.save) { el.innerHTML = `<div class="note">${esc(t("pickFileShown"))}</div>`; return; }
  const r = await P("backups", S.save);
  if (r.error) { el.innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  const hasGold = r.rows.some(b => b.gold);
  el.innerHTML = `
    <div class="toolbar">
      <button class="key small" data-act="reload">${esc(t("backupReload"))}</button>
      ${hasGold ? "" : `<button class="key small orange" data-act="gold">${esc(t("makeGold"))}</button>`}
      <span class="note">${esc(t("retentionNote", r.retention))}</span>
    </div>
    <table class="tbl"><thead><tr><th style="width:64px">${esc(t("thType"))}</th><th class="mono" style="width:150px">${esc(t("thDate"))}</th>
      <th>${esc(t("thName"))}</th><th class="mono" style="width:80px">${esc(t("thSize"))}</th><th style="width:250px">${esc(t("thActions"))}</th></tr></thead>
      <tbody>${r.rows.map(b => `
        <tr><td>${b.gold ? `<span class="mark gold">GOLD</span>` : b.pinned ? `<span class="mark pin">PIN</span>` : ""}</td>
        <td class="mono">${new Date(b.mtime * 1000).toLocaleString(LANG === "pl" ? "pl-PL" : "en-GB")}</td>
        <td class="grow">${esc(b.name)}</td><td class="mono">${(b.size / 1e6).toFixed(1)} MB</td>
        <td><div class="acts">
          <button class="key small" data-rs="${esc(b.name)}">${esc(t("restore"))}</button>
          <button class="key small" data-pin="${esc(b.name)}" data-on="${b.pinned ? 0 : 1}">${esc(b.pinned ? t("unpin") : t("pin"))}</button>
        </div></td></tr>`).join("")}</tbody></table>`;
  stickBars(el);
  el.querySelector("[data-act=reload]").onclick = () => renderBackups();
  el.querySelector("[data-act=gold]")?.addEventListener("click", async () => {
    const g = await P("backup_gold", S.save);
    if (g.error) toast(g.error, "err");
    else toast(g.created ? t("goldMade") : t("goldExists"), "ok");
    renderBackups();
  });
  el.querySelectorAll("[data-rs]").forEach(b => b.onclick = async () => {
    const name = b.dataset.rs;
    const ok = await confirmDlg(t("restoreTitle"), t("restoreBody", esc(name)), true, t("restoreYes"));
    if (!ok) return;
    busy(true, t("restoring"));
    const r2 = await P("restore", S.save, name);
    busy(false);
    if (r2.error) return toast(r2.error, "err", 6000);
    toast(t("restoredOk"), "ok", 6000);
    await loadSave();
  });
  el.querySelectorAll("[data-pin]").forEach(b => b.onclick = async () => {
    const r2 = await P("backup_pin", S.save, b.dataset.pin, b.dataset.on === "1");
    if (r2.error) toast(r2.error, "err"); else toast(b.dataset.on === "1" ? t("pinned") : t("unpinned"), "ok");
    renderBackups();
  });
}

/* ----------------------------------------------------------- panel: LOG -- */

async function renderLog() {
  const el = $("#panel-log");
  if (!S.save) { el.innerHTML = `<div class="note">${esc(t("pickFileShown"))}</div>`; return; }
  const r = await P("log", S.save);
  if (r.error) { el.innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  el.innerHTML = `
    <div class="toolbar"><button class="key small" data-act="reload">${esc(t("backupReload"))}</button>
    <span class="note">${esc(t("logNote"))}</span></div>
    <table class="tbl"><thead><tr><th class="mono" style="width:160px">${esc(t("thWhen"))}</th><th style="width:240px">${esc(t("thOp"))}</th><th>${esc(t("thBackup"))}</th></tr></thead>
    <tbody>${[...r.entries].reverse().map(e => `
      <tr><td class="mono">${esc(e.ts)}</td><td>${esc(r.labels[e.op] || e.op)}</td><td class="grow mono">${esc(e.note || "—")}</td></tr>`).join("")
      || `<tr><td colspan="3" class="note">${esc(t("logEmpty"))}</td></tr>`}</tbody></table>`;
  stickBars(el);
  el.querySelector("[data-act=reload]").onclick = () => renderLog();
}

/* ---------------------------------------------------- panel: USTAWIENIA -- */

function renderSettings() {
  const el = $("#panel-ustawienia");
  const c = S.cfg || {};
  el.innerHTML = `
    <div class="statmod">
      <h3 class="sect">${esc(t("cfgHeader"))}</h3>
      <div class="inline" style="margin-bottom:10px">
        <span class="cap">${esc(t("retention"))}</span>
        <input class="lcdin" id="cfRet" type="number" min="0" style="width:80px" value="${c.backup_retention ?? 20}">
        <span class="cap">${esc(t("watchInt"))}</span>
        <input class="lcdin" id="cfWatch" type="number" min="60" style="width:100px" value="${c.watch_interval ?? 600}">
      </div>
      <div class="inline" style="margin-bottom:10px">
        <span class="swbox ${c.guard_live ? "on" : ""}" id="cfGuard"><i></i></span>
        <span class="cap">${esc(t("guardTxt"))}</span>
      </div>
      <div class="inline" style="margin-bottom:14px">
        <span class="swbox ${c.auto_doctor ? "on" : ""}" id="cfDoc"><i></i></span>
        <span class="cap">${esc(t("autoDocTxt"))}</span>
      </div>
      <div class="keyrow">
        <button class="key orange" id="cfSave">${esc(t("saveCfg"))}</button>
        <button class="key" id="cfFolder">${esc(t("openFolder"))}</button>
        <button class="key" id="cfWatch1">${esc(t("watchOnceBtn"))}</button>
      </div>
      <h3 class="sect">${esc(t("langHeader"))}</h3>
      <div class="inline">
        <button class="key ${LANG === "en" ? "orange" : ""}" id="langEN">ENGLISH</button>
        <button class="key ${LANG === "pl" ? "orange" : ""}" id="langPL">POLSKI</button>
        <span class="ednote">${esc(t("langNote"))}</span>
      </div>
      <h3 class="sect">${esc(t("about"))}</h3>
      <div class="note">
        REZUR v${esc(S.version || "")} — engine + CLI + GUI (pywebview/WebView2).<br>
        ${esc(t("aboutTxt"))}
      </div>
    </div>`;
  el.querySelector("#cfGuard").onclick = e => e.currentTarget.classList.toggle("on");
  el.querySelector("#cfDoc").onclick = e => e.currentTarget.classList.toggle("on");
  el.querySelector("#cfSave").onclick = async () => {
    const sets = [
      ["backup_retention", $("#cfRet").value],
      ["watch_interval", $("#cfWatch").value],
      ["guard_live", $("#cfGuard").classList.contains("on") ? "true" : "false"],
      ["auto_doctor", $("#cfDoc").classList.contains("on") ? "true" : "false"],
    ];
    for (const [k, v] of sets) {
      const r = await P("config_set", k, v);
      if (r.error) return toast(`${k}: ${r.error}`, "err");
      S.cfg = r.config || S.cfg;
    }
    toast(t("cfgsaved"), "ok");
  };
  el.querySelector("#cfFolder").onclick = async () => {
    if (!S.save) return toast(t("needFile"), "err");
    const r = await P("open_folder", S.save);
    if (r.error) toast(r.error, "err");
  };
  el.querySelector("#cfWatch1").onclick = async () => {
    if (!S.save) return toast(t("needFile"), "err");
    const r = await P("watch_once", S.save);
    if (r.error) return toast(r.error, "err");
    const reason = (t("watchReason") || {})[r.reason] || r.reason;
    toast(r.made ? `backup: ${r.made}` : `${reason}`, r.made ? "ok" : "info", 5000);
  };
  const setLang = async lang => {
    const r = await P("config_set", "ui_lang", lang);
    if (r.error) return toast(r.error, "err");
    setTimeout(() => window.location.reload(), 120);
  };
  el.querySelector("#langEN").onclick = () => setLang("en");
  el.querySelector("#langPL").onclick = () => setLang("pl");
}

/* ------------------------------------------------------------ start ---- */

function applyLangChrome() {
  $$(".tab").forEach(tb => {
    const key = tb.dataset.tab;
    tb.innerHTML = `<span class="dot"></span>${esc(t("tabs")[key] || key.toUpperCase())}`;
    tb.classList.toggle("on", key === S.tab);
  });
  $("#pillLang").textContent = LANG.toUpperCase();
  $("#txtAuto").textContent = t("autoCopy");
  $("#pillFile").title = t("titleFile");
  $("#pillMd5").title = t("titleMd5");
  $("#pillGame").title = t("titleGame");
  $("#pillAuto").title = t("titleAuto");
  $("#pillLang").title = t("titleLang");
  $("#btnPick").textContent = t("pickFile");
  $("#btnPick2").textContent = t("pickFile2");
  $("#btnRecent").textContent = t("openRecent");
  $("#emptySub").textContent = t("emptySub");
  $("#emptyNote").innerHTML = t("emptyNote");
  $("#bannerLead").textContent = t("bannerLead");
  $("#bannerTxt").textContent = t("bannerTxt");
  $("#btnPreview").textContent = t("previewBtn");
  $("#btnUndo").textContent = t("undoBtn");
  $("#btnApply").textContent = t("stageBtn");
  const dspan = $("#btnDiscard span");
  if (dspan) dspan.textContent = t("discardBtn");
  updateStagebar();
}
function render() {
  $$(".tab").forEach(tb => tb.classList.toggle("on", tb.dataset.tab === S.tab));
  $$(".panel").forEach(p => p.classList.toggle("hidden", p.id !== "panel-" + S.tab));
  renderCtx();
  refreshCurrent();
}

async function boot() {
  $$(".tab").forEach(tb => tb.onclick = () => { S.tab = tb.dataset.tab; render(); });
  $("#btnPick").onclick = pickAndLoad;
  $("#btnPick2").onclick = pickAndLoad;
  $("#btnRecent").onclick = pickAndLoad;
  $("#btnApply").onclick = onApply;
  $("#btnDiscard").onclick = onDiscard;
  $("#btnUndo").onclick = onUndo;
  $("#btnPreview").onclick = onPreview;
  $("#pillLang").onclick = async () => {
    const next = LANG === "en" ? "pl" : "en";
    const r = await P("config_set", "ui_lang", next);
    if (r.error) return toast(r.error, "err");
    setTimeout(() => window.location.reload(), 120);
  };
  updateStagebar();

  const ready = await bridgeReady();
  if (!ready && !MOCK) {
    window.__rezurBooted = "no-bridge";
    setStatus(t("noBridge"));
    toast(t("noBridgeToast"), "err", 8000);
    return;
  }
  const st = await P("initial_state");
  if (st.error) { window.__rezurBooted = "init-error"; toast(st.error, "err"); return; }
  S.version = st.version;
  S.cfg = st.config || {};
  LANG = (S.cfg.ui_lang === "pl" || S.cfg.ui_lang === "en") ? S.cfg.ui_lang : "en";
  applyLangChrome();
  S.game = !!st.game_running;
  $("#txtVer").textContent = "FW " + (st.version || "—");
  if (st.save) { S.save = st.save; await loadSave(); }
  else { $("#empty").classList.remove("hidden"); }
  updateHeader();
  window.__rezurBooted = true;
  window.__rezurLoaded = S.info ? S.info.characters.filter(c => !c.empty).length : 0;

  setInterval(async () => {
    const g = await P("game_status");
    if (!g.error && g.running !== S.game) { S.game = g.running; updateHeader(); }
  }, 20000);
}

boot();

/* ============================================================ MOCK ====== */
/* Podgląd UI w przeglądarce (?mock=1&lang=pl|en) — dane atrapa, zero mostu. */

function mockApi(name, args) {
  const c = (slot, nm, lvl, h, runes, stats, patch, latest, bug) =>
    ({ slot, empty: false, parsed: true, name: nm, level: lvl, seconds: h * 3600, runes, stats, map_name: "m60_48_41_00", patch, patch_latest: latest, horse: bug ? "ACTIVE" : "INACTIVE", horse_bug: bug });
  const DATA = {
    info: {
      ok: true, path: "C:\\Users\\<user>\\AppData\\Roaming\\EldenRing\\76561198000000000\\ER0000.sl2",
      file: "ER0000.sl2", size_mb: 29.0, steamid: "76561198000000000", load_ms: 287,
      md5: { ok: 12, total: 12 }, game_running: false, live: true, staged: true,
      characters: [
        c(0, "lmfh test", 162, 71.7, 3403551, [99, 28, 18, 30, 50, 60, 70, 50], 230, false, false),
        c(1, "hajime", 36, 12.8, 211158, [20, 14, 12, 16, 14, 10, 12, 9], 250, false, true),
        c(2, "annesee", 54, 13.9, 494950, [14, 20, 8, 16, 16, 12, 31, 16], 261, true, false),
        { slot: 3, empty: true }, { slot: 4, empty: true }, { slot: 5, empty: true },
        { slot: 6, empty: true }, { slot: 7, empty: true }, { slot: 8, empty: true }, { slot: 9, empty: true },
      ],
    },
    pending: { ok: true, count: 2, created: "2026-10-13 21:40", original_changed: false,
      ops: [{ ts: "21:41", op: "stats", summary: "--slot 0 --set vigor=99,mind=28" }, { ts: "21:42", op: "item", summary: "--add Uchigatana --upgrade 5" }] },
  };
  const R = {
    initial_state: { version: "0.1.0", save: DATA.info.path, config: { backup_retention: 20, watch_interval: 600, guard_live: true, auto_doctor: true, ui_lang: (new URLSearchParams(window.location.search)).get("lang") || "en" }, game_running: false },
    config_get: { config: { backup_retention: 20, watch_interval: 600, guard_live: true, auto_doctor: true, ui_lang: "en" } },
    game_status: { running: false },
    load: () => DATA.info,
    pending: () => DATA.pending,
    preview: { ok: true, changed: ["USER_DATA000", "USER_DATA010"] },
    doctor: { ok: true, md5: { ok: 12, total: 12, bad: [] }, findings: [
      { level: "warning", code: "patch_old", message: "postać ze starszego patcha gry (base=230, slot=v250)", slot: 0, fix: null },
      { level: "warning", code: "torrent_bug", message: "Torrent: hp=0 i stan ACTIVE", slot: 1, fix: "torrent" },
      { level: "warning", code: "inv_counter_mismatch", message: "liczniki ekwipunku się nie zgadzają", slot: 2, fix: "invcounters" },
      { level: "info", code: "items_unresolved", message: "8 itemów spoza naszej bazy", slot: 2, fix: null },
    ] },
    risk_scan: { ok: true, verdict: "yellow", gold: "ER0000.sl2.goldbak-20261013-205427", modified: { count: 2, last: "2026-10-13 21:42", ops: { edycja: 2 } },
      findings: [{ level: "info", code: "items_unresolved", message: "8 itemów spoza bazy", slot: 2 }],
      notes: ["eksperymentuj na KOPII (backup/GOLD), nie na żywym save'ie", "przed grą online rozważ powrót do GOLD", "Rezur nie gwarantuje braku flagi"] },
    inventory: { ok: true, total: 74, rows: [
      { handle: 2155872440, qty: 1, item_id: 34080001, name: "Dragon Communion Seal +1", hex: "0x0207F041", handle_hex: "0x808000B8" },
      { handle: 2155872441, qty: 1, item_id: 8995904, name: "Uchigatana +5", hex: "0x00895440", handle_hex: "0x808000B9" },
      { handle: 2952798616, qty: 12, item_id: 1073750424, name: "Larval Tear", hex: "0x40001FD8", handle_hex: "0xB0001FF8" },
      { handle: 2952798617, qty: 1, item_id: 1073751144, name: "Armorer's Cookbook [1]", hex: "0x40002208", handle_hex: "0xB0001FF9" },
      { handle: 2952798618, qty: 3, item_id: 1073749982, name: "Spirit Calling Bell", hex: "0x40001E1E", handle_hex: "0xB0001FFA" },
    ] },
    equipment: { ok: true, equipped: [
      { slot: 0, zone: "weapon", empty: false, item_id: 8995904, handle: 2155872441, name: "Uchigatana +5" },
      { slot: 1, zone: "weapon", empty: false, item_id: 34080001, handle: 2155872440, name: "Dragon Communion Seal +1" },
      { slot: 2, zone: "weapon", empty: true }, { slot: 3, zone: "weapon", empty: true }, { slot: 4, zone: "weapon", empty: true }, { slot: 5, zone: "weapon", empty: true },
      { slot: 6, zone: "armor", empty: false, name: "White Reed Armor" }, { slot: 7, zone: "armor", empty: true }, { slot: 8, zone: "armor", empty: true }, { slot: 9, zone: "armor", empty: true },
      { slot: 10, zone: "armor", empty: true }, { slot: 11, zone: "armor", empty: true },
      { slot: 12, zone: "talisman", empty: false, name: "Blessed Dew Talisman" }, { slot: 13, zone: "talisman", empty: true },
      { slot: 14, zone: "talisman", empty: true }, { slot: 15, zone: "talisman", empty: true },
    ] },
    spells: { ok: true, spells: [
      { slot: 0, empty: false, id: 6420, name: "Urgent Heal" }, { slot: 1, empty: false, id: 6010, name: "Flame Sling" },
      { slot: 2, empty: true }, { slot: 3, empty: true }, { slot: 4, empty: true }, { slot: 5, empty: true },
      { slot: 6, empty: true }, { slot: 7, empty: true }, { slot: 8, empty: true }, { slot: 9, empty: true },
      { slot: 10, empty: true }, { slot: 11, empty: true }, { slot: 12, empty: true }, { slot: 13, empty: true },
    ] },
    appearance: { ok: true, gender: 0, body_type: 0, archetype: 5, gift: 2 },
    teleport_info: { ok: true, map_id: 1009460736, map_name: "m60_43_38_00", xyz: [71.1, 130.2, 65.8], spawn: {}, destinations: ["roundtable", "limgrave", "liurnia", "altus", "caelid", "mountaintop"] },
    world_groups: { ok: true, groups: { boss_defeat: 48, item_pickup: 3079, colosseums: 3, summoning_pools: 162, invasion_regions: 210, maps: 19, cookbook_acquired: 60, great_runes: 8 } },
    world_view: { ok: true, total: 48, rows: [
      { id: 1000, name: "Godrick the Grafted", desc: "Stormveil", value: 1 },
      { id: 1001, name: "Margit, the Fell Omen", desc: "Stormveil", value: 1 },
      { id: 9100, name: "Malenia, Blade of Miquella", desc: "Elphael", value: 0 },
      { id: 9101, name: "Starscourge Radahn", desc: "Caelid", value: 1 },
      { id: 9102, name: "Rennala, Queen of the Full Moon", desc: "Academy", value: 1 },
    ] },
    backups: { ok: true, retention: 20, rows: [
      { name: "ER0000.sl2.goldbak-20261013-205427", tag: "goldbak", gold: true, pinned: false, size: 28967872, mtime: 1791887000 },
      { name: "ER0000.sl2.rezurbak-20261013-214000", tag: "rezurbak", gold: false, pinned: true, size: 28967872, mtime: 1791889000 },
      { name: "ER0000.sl2.rezurbak-20261013-213500", tag: "rezurbak", gold: false, pinned: false, size: 28967872, mtime: 1791888000 },
    ] },
    log: { ok: true, labels: { rezurbak: "naprawy/edycja ogólna", itembak: "ekwipunek", stagebak: "zatwierdzenie zmian (staging)" },
      entries: [
        { ts: "2026-10-13 21:01:37", op: "editbak", note: "ER0000.sl2.editbak-20261013-210137" },
        { ts: "2026-10-13 21:07:33", op: "stagebak", note: "ER0000.sl2.stagebak-20261013-210733" },
      ] },
    find: { ok: true, items: [{ id: "0x00895440", name: "Uchigatana", cat: "weapons" }], flags: [], graces: [], locations: [] },
    watch_once: { ok: true, running: false, made: null, reason: "gra nie działa" },
    stage: { ok: true, changed: true, pending: 3 },
    undo: { ok: true, undone: { op: "stats", summary: "…" }, left: 1 },
    discard: { ok: true, ops: 2 },
    apply: { ok: true, backup: "ER0000.sl2.stagebak-x", ops: 2, md5_ok: 12, md5_total: 12 },
    backup_gold: { ok: true, created: false, path: "x" },
    backup_pin: { ok: true, pins: [] },
    restore: { ok: true },
    config_set: { ok: true, config: { backup_retention: 20, watch_interval: 600, guard_live: true, auto_doctor: true, ui_lang: "en" } },
    open_folder: { ok: true },
    pick_save: { cancelled: true },
  };
  const v = R[name];
  const out = typeof v === "function" ? v(...args) : v;
  return Promise.resolve(out === undefined ? { ok: true } : JSON.parse(JSON.stringify(out)));
}
