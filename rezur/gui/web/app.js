/* REZUR GUI — logika (most pywebview + stan + panele). Bez frameworków. */

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtInt = n => (n ?? 0).toLocaleString("pl-PL");

const STAT_NAMES = ["vigor", "mind", "endurance", "strength", "dexterity", "intelligence", "faith", "arcane"];
const GEAR_ZONES = { weapon: "BROŃ", armor: "ZBROJA", talisman: "TALIZMANY" };

const MOCK = window.location.search.includes("mock");
const S = {
  save: null, info: null, slot: null, tab: "postacie",
  cfg: {}, game: false, pending: 0, busy: false,
  doctor: null, risk: null, bakSel: null,
  inv: { loc: "held", q: "", offset: 0, total: 0, rows: [] },
  world: { group: "", q: "", offset: 0, total: 0, rows: [], groups: {} },
  eqCache: null,
};

/* ---------------------------------------------------------------- most ---- */

function P(name, ...args) {
  if (MOCK) return mockApi(name, args);
  if (!window.pywebview || !window.pywebview.api) return Promise.resolve({ error: "brak mostu pywebview (podgląd w przeglądarce?)" });
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

function setStatus(t, kind = "") {
  const el = $("#status");
  el.innerHTML = kind === "am" ? `<span class="am">${esc(t)}</span>` : `<span>${esc(t)}</span>`;
}
function toast(msg, kind = "info", ms = 4200) {
  const d = document.createElement("div");
  d.className = `toast ${kind}`;
  d.textContent = msg;
  $("#toasts").appendChild(d);
  setTimeout(() => d.remove(), ms);
}
function busy(on, text = "PRACUJĘ…") {
  S.busy = on;
  $("#busy").classList.toggle("hidden", !on);
  $("#busyTxt").textContent = text;
  updateStagebar();
}
function modal({ title, body = "", warn = false, actions = [] }) {
  return new Promise(resolve => {
    const m = $("#modal"), box = $("#mbox");
    box.innerHTML = `
      <div class="mhead ${warn ? "warn" : ""}">${warn ? `<span>${esc(title)}</span>` : `<span>${esc(title)}</span>`}</div>
      <div class="mbod">${body}</div>
      <div class="mact"></div>`;
    const act = box.querySelector(".mact");
    actions.forEach((a, i) => {
      const b = document.createElement("button");
      b.className = `key ${a.klass || ""}`;
      b.textContent = a.label;
      b.onclick = () => { m.classList.add("hidden"); resolve(a.value); };
      act.appendChild(b);
    });
    m.classList.remove("hidden");
    act.querySelector(".key")?.focus();
  });
}
const confirmDlg = (title, body, warn = false, yes = "WYKONAJ", no = "WRÓĆ") =>
  modal({ title, body, warn, actions: [
    { label: yes, value: true, klass: warn ? "orange" : "orange" },
    { label: no, value: false },
  ] });

/* ------------------------------------------------------------ stan ----- */

function charOfSlot() {
  if (!S.info || S.slot === null) return null;
  return S.info.characters.find(c => c.slot === S.slot && !c.empty) || null;
}
function needSlot() {
  return `<div class="note">wybierz postać (zakładka POSTACIE) — panel pokaże dane tego slotu.</div>`;
}
function updateStagebar() {
  $("#pendN").textContent = S.pending;
  const n = S.pending;
  $("#pendW").textContent = n === 1 ? "ZMIANA" : (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) ? "ZMIANY" : "ZMIAN";
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
  $("#txtFile").textContent = S.info ? `${S.info.file} · ${S.info.size_mb} MB` : S.save ? S.save.split("\\").pop() : "BRAK PLIKU";
  $("#txtFile").textContent = S.info ? `${S.info.file} · ${S.info.size_mb} MB` : $("#txtFile").textContent;
  if (S.info) {
    $("#ledMd5").className = "led " + (S.info.md5.ok === S.info.md5.total ? "g" : "r");
    $("#txtMd5").textContent = `MD5 ${S.info.md5.ok}/${S.info.md5.total}`;
  }
  $("#ledGame").className = "led " + (S.game ? "r" : "g");
  $("#txtGame").textContent = "GRA: " + (S.game ? "DZIAŁA" : "STOP");
  $("#gameBanner").classList.toggle("hidden", !(S.game && S.info && S.info.live));
  $("#railPath").textContent = S.save || "—";
}
function renderCtx() {
  const c = charOfSlot();
  const tags = [];
  if (S.info && S.info.staged) tags.push(`<span class="tag stage">STAGING · PODGLĄD ZMIAN</span>`);
  if (c && !c.patch_latest) tags.push(`<span class="tag warn">STARY PATCH (b${c.patch})</span>`);
  if (c && c.horse_bug) tags.push(`<span class="tag warn">TORRENT !!</span>`);
  if (S.slot === null) { $("#ctx").innerHTML = `<span>WYBIERZ POSTAĆ, ABY EDYTOWAĆ</span>`; return; }
  if (!c) { $("#ctx").innerHTML = `<span>SLOT ${String(S.slot).padStart(2, "0")} — PUSTY</span>${tags.join("")}`; return; }
  $("#ctx").innerHTML =
    `<b>SLOT ${String(S.slot).padStart(2, "0")}</b> <b>${esc(c.name)}</b>` +
    `<span>LVL ${c.level}</span><span>${(c.seconds / 3600).toFixed(1)} h</span>` +
    `<span>${esc(c.map_name)}</span><span>RM ${fmtInt(c.runes)}</span>` + tags.join("");
}

/* ----------------------------------------------------------- akcje ----- */

async function doStage(argv, note = "") {
  if (!S.save) return toast("najpierw wskaż plik", "err");
  busy(true, "STAGING…");
  const r = await P("stage", S.save, argv);
  busy(false);
  if (r.error) {
    toast(`nie udało się: ${r.error}`, "err");
    if (r.output) console.warn(r.output);
    setStatus("BŁĄD — " + r.error);
    return r;
  }
  if (!r.changed) { setStatus("bez zmian danych"); toast("bez zmian danych", "info", 2400); await refreshPending(); return r; }
  await refreshPending();
  setStatus(`+1 zmiana oczekująca (${S.pending})`);
  toast(`dodano do zmian: ${note || argv[0]} (${S.pending})`, "ok", 2600);
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
  const secs = (d.changed || []).join(", ") || "(brak różnic)";
  await modal({
    title: `podgląd ${S.pending} zmian`,
    body: `<div class="cap">operacje</div><div class="lcd">${ops || "(pusto)"}</div>
           <div class="cap" style="margin-top:10px">zmienione sekcje pliku</div><div class="lcd">${esc(secs)}</div>`,
    actions: [{ label: "ZAMKNIJ", value: true }],
  });
}
async function onApply() {
  const ok = await confirmDlg("zastosować zmiany?", `
    <div>Zostanie zrobiony <b>jeden backup</b> stanu obecnego, brudnopis trafi do pliku i przejdzie weryfikację sum.</div>
    <div class="lcd">plik: ${esc(S.save)}</div>`, false, "ZASTOSUJ");
  if (!ok) return;
  busy(true, "ZAPIS + WERYFIKACJA…");
  let r = await P("apply", S.save, false);
  if (r.error && r.needs_force) {
    busy(false);
    const f = await confirmDlg("oryginał zmienił się poza Rezurem", `<div>${esc(r.error)}</div>`, true, "NADPISZ (--force)");
    if (!f) return;
    busy(true, "ZAPIS + WERYFIKACJA…");
    r = await P("apply", S.save, true);
  }
  busy(false);
  if (r.error) { toast("zapis odrzucony: " + r.error, "err", 7000); setStatus("ODRZUCONO — zmiany zostają"); return; }
  toast(`zapisane · backup: ${r.backup || "—"} · MD5 ${r.md5_ok}/${r.md5_total}`, "ok", 6000);
  setStatus(`zapisane (backup ${String(r.backup || "").split("\\").pop()})`);
  await loadSave(true);
}
async function onDiscard() {
  const p = await P("pending", S.save);
  const ok = await confirmDlg(`odrzucić ${p.count} zmian?`, `
    <div>Brudnopis zostanie skasowany. <b>Oryginał pozostaje nietknięty</b> — nic nie zapisujemy.</div>`, true, "ODRZUĆ");
  if (!ok) return;
  const r = await P("discard", S.save);
  if (r.error) { toast(r.error, "err"); return; }
  toast(`odrzucono ${r.ops} zmian — oryginał nietknięty`, "ok");
  setStatus("zmiany odrzucone");
  await loadSave(true);
}
async function onUndo() {
  const r = await P("undo", S.save);
  if (r.error) { toast(r.error, "err"); return; }
  toast(`cofnięte: ${r.undone.op} ${r.undone.summary} (zostało ${r.left})`, "ok");
  await refreshPending();
  await refreshCurrent();
}

/* ------------------------------------------------------- ładowanie ----- */

async function pickAndLoad() {
  const r = await P("pick_save");
  if (r.error) return toast(r.error, "err");
  if (r.cancelled) return;
  S.save = r.path;
  await loadSave(true);
}
async function loadSave(resetTab = false) {
  if (!S.save) { $("#empty").classList.remove("hidden"); return; }
  busy(true, "WCZYTYWANIE SAVE'A…");
  const info = await P("load", S.save);
  busy(false);
  if (info.error) {
    $("#empty").classList.remove("hidden");
    $("#emptyNote").innerHTML = `<span style="color:var(--led-r)">${esc(info.error)}</span><br>wskaż inny plik .sl2`;
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
  setStatus(`wczytano w ${info.load_ms} ms · ${info.md5.ok}/${info.md5.total} sum OK`);
}
async function refreshCurrent() {
  updateHeader();
  renderCtx();
  const t = S.tab;
  if (t === "postacie") renderChars();
  else if (t === "doktor") renderDoctor();
  else if (t === "staty") renderStats();
  else if (t === "ekwipunek") renderInventory();
  else if (t === "eq") renderEQ();
  else if (t === "swiat") renderWorld();
  else if (t === "czary") renderSpells();
  else if (t === "wyglad") renderLooks();
  else if (t === "teleport") renderTeleportPanel();
  else if (t === "ryzyko") renderRisk();
  else if (t === "kopie") renderBackups();
  else if (t === "log") renderLog();
  else if (t === "ustawienia") renderSettings();
}

/* ----------------------------------------------------- panel: POSTACIE -- */

function renderChars() {
  const el = $("#panel-postacie");
  const chars = S.info.characters;
  el.innerHTML = `
    <div class="toolbar">
      <button class="key small" data-act="reload">ODŚWIEŻ</button>
      <button class="key small" data-act="export">EKSPORT POSTACI…</button>
      <button class="key small" data-act="import">IMPORT POSTACI…</button>
    </div>
    <div class="cards">${chars.map(c => {
      if (c.empty) return `<div class="card empty" data-slot="${c.slot}"><div class="slot mono">SLOT ${String(c.slot).padStart(2, "0")}</div>
        <h4>— pusty —</h4><div class="meta">wolne miejsce</div></div>`;
      const tags = [];
      if (!c.patch_latest) tags.push(`<span class="minitag wa">b${c.patch} !</span>`);
      if (c.horse_bug) tags.push(`<span class="minitag wa">TORRENT</span>`);
      if (!c.parsed) tags.push(`<span class="minitag wa">?</span>`);
      return `<div class="card ${S.slot === c.slot ? "sel" : ""}" data-slot="${c.slot}">
        <div class="slot mono">SLOT ${String(c.slot).padStart(2, "0")}${S.slot === c.slot ? " · WYBRANA" : ""}</div>
        <div class="pills">${tags.join("")}</div>
        <h4>${esc(c.parsed ? c.name : (c.name || "?"))}</h4>
        <span class="lcd">LVL ${c.parsed ? c.level : "?"} · ${(c.seconds / 3600).toFixed(1)}H</span>
        <div class="meta">${esc(c.map_name || "")} · RM ${fmtInt(c.runes || 0)}</div>
      </div>`;
    }).join("")}</div>`;
  el.querySelectorAll(".card").forEach(card => card.onclick = async () => {
    S.slot = +card.dataset.slot;
    const c = S.info.characters[S.slot];
    if (c.empty) toast(`slot ${S.slot} jest pusty`, "info");
    await refreshCurrent();
  });
  el.querySelector("[data-act=reload]").onclick = () => loadSave();
  el.querySelector("[data-act=export]").onclick = async () => {
    if (!charOfSlot()) return toast("najpierw wybierz postać", "err");
    const r = await P("export_char", S.save, S.slot);
    if (r.error) toast(r.error, "err");
    else if (!r.cancelled) toast("wyeksportowano: " + r.out, "ok");
  };
  el.querySelector("[data-act=import]").onclick = async () => {
    if (!charOfSlot()) return toast("najpierw wybierz postać (cel importu)", "err");
    const j = await P("pick_json");
    if (j.error) return toast(j.error, "err");
    if (j.cancelled) return;
    const ok = await confirmDlg("import postaci", `Wczytam <b>${esc(j.path.split("\\").pop())}</b> do slotu ${S.slot} (jako zmiana oczekująca).`, false, "IMPORTUJ");
    if (!ok) return;
    await doStage(["import", "--to", String(S.slot), "--in", j.path], "import postaci");
  };
}

/* ------------------------------------------------------- panel: DOKTOR -- */

async function renderDoctor() {
  const el = $("#panel-doktor");
  el.innerHTML = `<div class="toolbar">
      <button class="key small" data-act="scan">SKANUJ PONOWNIE</button>
      <button class="key small orange" data-act="fixall">NAPRAW WSZYSTKO (do kolejki)</button>
      <span class="note" id="md5line"></span>
    </div><div id="findings"></div>`;
  el.querySelector("[data-act=scan]").onclick = () => loadDoctor();
  el.querySelector("[data-act=fixall]").onclick = async () => {
    const ok = await confirmDlg("napraw wszystko", "Wykona dostępne naprawy (torrent, sumy, hash, profil, weather, DLC, liczniki) na kopii roboczej.", false, "NAPRAW");
    if (ok) await doStage(["fix"], "naprawy");
  };
  await loadDoctor();
}
async function loadDoctor() {
  const r = await P("doctor", S.save);
  if (r.error) { $("#findings").innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  S.doctor = r;
  $("#md5line").textContent = `sumy sekcji: ${r.md5.ok}/${r.md5.total}` + (r.md5.bad.length ? ` · złe: ${r.md5.bad.join(", ")}` : "");
  const el = $("#findings");
  if (!r.findings.length) { el.innerHTML = `<div class="frow"><span class="sev ok"></span><div class="fbody"><div class="fmsg">save wygląda zdrowo — brak ustaleń.</div></div></div>`; return; }
  el.innerHTML = r.findings.map((f, i) => `
    <div class="frow">
      <span class="sev ${f.level === "error" ? "err" : f.level === "warning" ? "war" : "ok"}"></span>
      <div class="fbody">
        <div class="fmsg">${esc(f.message)}</div>
        <div class="fcode">${esc(f.code)}${f.slot !== null && f.slot !== undefined ? ` · slot ${f.slot}` : ""}</div>
      </div>
      ${f.fix ? `<button class="key small" data-fix="${esc(f.fix)}">NAPRAW: ${esc(f.fix)}</button>` : ""}
    </div>`).join("");
  el.querySelectorAll("[data-fix]").forEach(b => b.onclick = () =>
    doStage(["fix", "--only", b.dataset.fix], "naprawa " + b.dataset.fix));
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
      <span class="sval lcd" data-i="${i}" title="kliknij, aby wpisać z klawiatury">${draft[i]}</span>
      <span class="stbtn" data-plus="1" data-i="${i}">+</span>
      <span class="stbtn" data-plus="-1" data-i="${i}">−</span>
    </div>`;
  el.innerHTML = `
    <div class="statmod">
      <h3 class="sect">statystyki — slot ${String(S.slot).padStart(2, "0")}</h3>
      ${STAT_NAMES.map((n, i) => row(i, n)).join("")}
      <div class="statrow lvl"><span class="sname">level</span>
        <span class="sval lcd big" id="lvlPrev">${draft.reduce((a, b) => a + b, 0) - 79}</span>
        <span class="ednote">= suma − 79 (gra wymusza zgodność)</span></div>
      <h3 class="sect">imię i runy</h3>
      <div class="inline">
        <input class="lcdin" id="statName" style="width:220px" maxlength="16" value="${esc(c.name)}">
        <input class="lcdin" id="statRunes" style="width:150px" type="number" value="${c.runes}">
        <span class="ednote">imię 1–16 znaków · runy (pamięć)</span>
      </div>
      <div class="keyrow" style="margin-top:14px">
        <button class="key orange" id="statStage">DODAJ DO KOLEJKI</button>
        <button class="key" id="statReset">PRZYWRÓĆ WARTOŚCI</button>
        <span class="ednote">bez suwaków: +/- (przytrzymaj) albo kliknij wartość i wpisz</span>
      </div>
    </div>`;
  const lvl = () => { $("#lvlPrev").textContent = draft.reduce((a, b) => a + b, 0) - 79; };
  el.querySelectorAll(".stbtn").forEach(b => {
    const i = +b.dataset.i, dir = +b.dataset.plus;
    let hold, rep;
    const bang = () => {
      const v = Math.max(1, Math.min(99, draft[i] + dir));
      if (v === draft[i]) { toast("zakres 1..99", "info", 1800); return; }
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
        if (Number.isNaN(v) || v < 1 || v > 99) toast("gra przyjmuje 1..99", "err");
        else { draft[i] = v; lvl(); }
      }
      const back = document.createElement("span");
      back.className = "sval lcd"; back.dataset.i = i; back.title = "kliknij, aby wpisać";
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
    if (argv.length === 2) return toast("nic nie zmieniono", "info");
    await doStage(argv, `staty slot${S.slot}`);
  };
}

/* --------------------------------------------------- panel: EKWIPUNEK -- */

function renderInventory() {
  const el = $("#panel-ekwipunek");
  const c = charOfSlot();
  if (!c) { el.innerHTML = needSlot(); return; }
  el.innerHTML = `
    <div class="toolbar">
      <div class="swbox ${S.inv.loc === "held" ? "on" : ""}" id="invLoc" title="przy sobie / skrzynia"><i></i></div>
      <span class="ednote">${S.inv.loc === "held" ? "PRZY SOBIE" : "SKRZYNIA"}</span>
      <input class="lcdin" id="invQ" placeholder="szukaj w ekwipunku…" style="width:230px" value="${esc(S.inv.q)}">
      <button class="key small" id="invGo">SZUKAJ</button>
      <button class="key small orange" id="invAdd">DODAJ ITEM…</button>
    </div>
    <table class="tbl"><thead><tr><th class="mono" style="width:110px">handle</th><th style="width:64px">ilość</th>
      <th>nazwa</th><th class="mono" style="width:110px">id</th><th style="width:250px">akcje</th></tr></thead>
      <tbody id="invRows"></tbody></table>
    <div class="pager"><button class="key" id="invPrev">‹</button><span id="invInfo"></span>
      <button class="key" id="invNext">›</button></div>`;
  const load = async () => {
    const r = await P("inventory", S.save, S.slot, S.inv.loc, S.inv.q, S.inv.offset, 100);
    if (r.error) { toast(r.error, "err"); return; }
    S.inv.total = r.total; S.inv.rows = r.rows;
    $("#invRows").innerHTML = r.rows.map(x => `
      <tr><td class="mono">${x.handle_hex}</td><td class="mono">${x.qty}</td>
      <td class="grow" title="${esc(x.name)}">${esc(x.name)}</td><td class="mono">${x.hex}</td>
      <td><div class="acts">
        <button class="key small" data-a="rm" data-h="${x.handle}">ZDEJMIJ</button>
        <button class="key small" data-a="mv" data-h="${x.handle}">${S.inv.loc === "held" ? "DO SKRZYNI" : "PRZY SOBIE"}</button>
        <button class="key small" data-a="qty" data-h="${x.handle}" data-q="${x.qty}">ILOŚĆ…</button>
      </div></td></tr>`).join("") || `<tr><td colspan="5" class="note">(pusto)</td></tr>`;
    $("#invInfo").textContent = `${S.inv.offset + 1}–${Math.min(S.inv.offset + 100, r.total)} / ${r.total}`;
    $("#invRows").querySelectorAll("[data-a]").forEach(b => b.onclick = async () => {
      const h = "handle:0x" + (+b.dataset.h >>> 0).toString(16).toUpperCase();
      if (b.dataset.a === "rm")
        await doStage(["item", "--slot", String(S.slot), "--remove", "x", "--handle", b.dataset.h], "usuń item");
      else if (b.dataset.a === "mv")
        await doStage(["item", "--slot", String(S.slot), "--move", h, "--to", S.inv.loc === "held" ? "storage" : "held"], "przenieś item");
      else {
        const inp = await modal({ title: "ustaw ilość", body: `<input class="lcdin" id="qtyIn" style="width:140px" value="${b.dataset.q}">`,
          actions: [{ label: "USTAW", value: true, klass: "orange" }, { label: "WRÓĆ", value: false }] });
        if (inp !== true) return;
        await doStage(["item", "--slot", String(S.slot), "--set-qty", `${h}=${$("#qtyIn")?.value ?? b.dataset.q}`.replace("undefined", b.dataset.q)], "ilość itemu");
      }
      load();
    });
  };
  el.querySelector("#invLoc").onclick = async () => { S.inv.loc = S.inv.loc === "held" ? "storage" : "held"; S.inv.offset = 0; renderInventory(); };
  el.querySelector("#invGo").onclick = () => { S.inv.q = $("#invQ").value.trim(); S.inv.offset = 0; renderInventory(); };
  $("#invQ").onkeydown = e => { if (e.key === "Enter") el.querySelector("#invGo").click(); };
  el.querySelector("#invPrev").onclick = () => { S.inv.offset = Math.max(0, S.inv.offset - 100); renderInventory(); };
  el.querySelector("#invNext").onclick = () => { if (S.inv.offset + 100 < S.inv.total) { S.inv.offset += 100; renderInventory(); } };
  el.querySelector("#invAdd").onclick = () => addItemModal();
  load();
}
async function addItemModal() {
  const r = await modal({
    title: "dodaj item z bazy",
    body: `<div class="field"><label>szukaj (nazwa)</label>
      <input class="lcdin" id="addQ" style="width:320px" placeholder="np. uchigatana, larval, map"></div>
      <div class="lcd" id="addHits" style="max-height:180px;overflow:auto">wpisz fragment nazwy i naciśnij SZUKAJ</div>
      <div class="field" style="margin-top:10px"><label>ilość / upgrade (+N dla broni)</label>
      <div class="inline"><input class="lcdin" id="addQty" type="number" value="1" style="width:90px">
      <input class="lcdin" id="addUpg" type="number" value="0" style="width:90px"></div></div>`,
    actions: [{ label: "SZUKAJ", value: "search" }, { label: "DODAJ ZAZNACZONY", value: "add", klass: "orange" }, { label: "WRÓĆ", value: false }],
  });
  // SZUKAJ obsługujemy po zamknięciu — uproszczenie: modal prosty, ale skuteczny
  if (r === "search") return addItemSearchFlow();
  if (r === "add") return addItemSearchFlow(true);
}
async function addItemSearchFlow(autoPickFirst = true) {
  const q = await modal({ title: "dodaj item — krok 1/2",
    body: `<div class="field"><label>fragment nazwy</label><input class="lcdin" id="qu2" style="width:300px"></div>`,
    actions: [{ label: "DALEJ", value: true, klass: "orange" }, { label: "WRÓĆ", value: false }] });
  if (q !== true) return;
  const needle = $("#qu2")?.value ?? "";
  const r = await P("find", needle, 30);
  if (r.error) return toast(r.error, "err");
  const list = r.items.slice(0, 30);
  if (!list.length) return toast("brak trafień", "info");
  const picked = await modal({ title: "dodaj item — krok 2/2",
    body: `<div class="lcd" style="max-height:220px;overflow:auto;white-space:pre">` +
      list.map((it, i) => `${String(i + 1).padStart(2)}. ${esc(it.name)}  [${it.cat}]`).join("\n") + `</div>
      <div class="inline" style="margin-top:10px">
        <span class="ednote">numer:</span><input class="lcdin" id="pk" type="number" value="1" style="width:70px">
        <span class="ednote">ilość:</span><input class="lcdin" id="qt" type="number" value="1" style="width:70px">
        <span class="ednote">upgrade:</span><input class="lcdin" id="up" type="number" value="0" style="width:70px">
      </div>`, actions: [{ label: "DODAJ", value: true, klass: "orange" }, { label: "WRÓĆ", value: false }] });
  if (picked !== true) return;
  const it = list[Math.min(list.length, Math.max(1, parseInt($("#pk")?.value ?? "1", 10))) - 1];
  const argv = ["item", "--slot", String(S.slot), "--add", it.name, "--qty", $("#qt")?.value || "1"];
  const upg = parseInt($("#up")?.value || "0", 10);
  if (upg > 0) argv.push("--upgrade", String(upg));
  if (S.inv.loc === "storage") argv.push("--storage");
  await doStage(argv, "dodaj: " + it.name);
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
  const seg = (zone) => `<div class="eqzone">${GEAR_ZONES[zone] || zone}</div><div class="grid eqgrid">` +
    (byZone[zone] || []).map(e => `
      <div class="cell ${e.empty ? "empty" : ""}">
        <div class="cslot">${String(e.slot).padStart(2, "0")}</div>
        <div class="cname" title="${esc(e.name || "")}">${e.empty ? "— puste —" : esc(e.name || `0x${(e.item_id || 0).toString(16).toUpperCase()}`)}</div>
        ${e.empty ? "" : `<div class="cact">
          <button class="key small" data-eu="${e.slot}">ZDEJMIJ</button>
          ${zone === "weapon" ? `
            <button class="key small" data-up="${e.handle}">+POZ</button>
            <button class="key small" data-af="${e.handle}">AFIN.</button>
            <button class="key small" data-aw="${e.handle}">AOW</button>` : ""}
        </div>`}
      </div>`).join("") + `</div>`;
  el.innerHTML = `<h3 class="sect">wyposażenie — slot ${String(S.slot).padStart(2, "0")}</h3>`
    + ["weapon", "armor", "talisman"].map(seg).join("")
    + `<h3 class="sect">założ z ekwipunku</h3>
       <div class="inline"><input class="lcdin" id="eqH" style="width:230px" placeholder="handle:0x… albo nazwa">
       <input class="lcdin" id="eqAt" type="number" style="width:80px" placeholder="gniazdo (opc.)">
       <button class="key orange" id="eqGo">ZAŁÓŻ</button></div>`;
  el.querySelectorAll("[data-eu]").forEach(b => b.onclick = () => doStage(["unequip", "--slot", String(S.slot), "--at", b.dataset.eu], "zdejmij EQ"));
  el.querySelectorAll("[data-up]").forEach(b => b.onclick = async () => {
    const v = await modal({ title: "poziom ulepszenia (0–25)", body: `<input class="lcdin" id="upv" type="number" value="10" style="width:90px">`,
      actions: [{ label: "USTAW", value: true, klass: "orange" }, { label: "WRÓĆ", value: false }] });
    if (v !== true) return;
    await doStage(["item", "--slot", String(S.slot), "--set-upgrade", "x=" + ($("#upv")?.value || "10"), "--handle", b.dataset.up], "upgrade broni");
    renderEQ();
  });
  el.querySelectorAll("[data-af]").forEach(b => b.onclick = async () => {
    const opts = ["Standard", "Heavy", "Keen", "Quality", "Fire", "Flame Art", "Lightning", "Sacred", "Magic", "Cold", "Poison", "Blood", "Occult"];
    const v = await modal({ title: "affinity", body: `<div class="lcd" style="white-space:pre">` + opts.map((o, i) => `${i + 1}. ${o}`).join("\n") + `</div>
      <div class="inline" style="margin-top:8px"><span class="ednote">numer:</span><input class="lcdin" id="afv" type="number" value="1" style="width:70px"></div>`,
      actions: [{ label: "USTAW", value: true, klass: "orange" }, { label: "WRÓĆ", value: false }] });
    if (v !== true) return;
    const name = opts[Math.min(opts.length, Math.max(1, parseInt($("#afv")?.value || "1", 10))) - 1];
    await doStage(["item", "--slot", String(S.slot), "--affinity", "x=" + name, "--handle", b.dataset.af], "affinity: " + name);
    renderEQ();
  });
  el.querySelectorAll("[data-aw]").forEach(b => b.onclick = async () => {
    const v = await modal({ title: "ash of war (nazwa)", body: `<input class="lcdin" id="awv" style="width:300px" placeholder="np. Bloody Slash">`,
      actions: [{ label: "USTAW", value: true, klass: "orange" }, { label: "WRÓĆ", value: false }] });
    if (v !== true) return;
    await doStage(["item", "--slot", String(S.slot), "--aow", "x=" + ($("#awv")?.value || ""), "--handle", b.dataset.aw], "ash of war");
    renderEQ();
  });
  el.querySelector("#eqGo").onclick = async () => {
    const h = $("#eqH").value.trim();
    if (!h) return;
    const argv = ["equip", "--slot", String(S.slot), "--handle", h.startsWith("handle:") ? h.split(":")[1] : h.replace(/^0x/i, "")];
    const at = $("#eqAt").value.trim();
    if (at !== "") argv.push("--at", at);
    await doStage(argv, "założ item");
    renderEQ();
  };
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
  const r = await P("world_view", S.save, S.slot, S.world.group, S.world.q, S.world.offset, 200);
  S.world.total = r.error ? 0 : r.total;
  S.world.rows = r.error ? [] : r.rows;
  el.innerHTML = `
    <div class="toolbar">
      <select class="lcdin" id="wgrp" style="width:230px">${groups.map(g =>
        `<option value="${g}" ${g === S.world.group ? "selected" : ""}>${g} (${S.world.groups[g]})</option>`).join("")}</select>
      <input class="lcdin" id="wq" placeholder="filtr nazwy / ID…" style="width:210px" value="${esc(S.world.q)}">
      <button class="key small" id="wgo">FILTRUJ</button>
      <button class="key small orange" id="wall">NADAJ CAŁĄ GRUPĘ…</button>
    </div>
    <div id="wrows">${S.world.rows.map(e => `
      <div class="worldrow">
        <span class="wid">${e.id}</span>
        <span class="wname">${esc(e.name)}</span>
        <span class="wdesc">${esc(e.desc || "")}</span>
        <span class="swbox ${e.value ? "on" : ""}" data-fl="${e.id}" data-v="${e.value ? 1 : 0}"><i></i></span>
      </div>`).join("") || `<div class="note">(brak wpisów)</div>`}</div>
    <div class="pager"><button class="key" id="wPrev">‹</button><span>${S.world.offset + 1}–${Math.min(S.world.offset + 200, S.world.total)} / ${S.world.total}</span><button class="key" id="wNext">›</button></div>`;
  el.querySelector("#wgrp").onchange = e => { S.world.group = e.target.value; S.world.offset = 0; renderWorld(); };
  el.querySelector("#wgo").onclick = () => { S.world.q = $("#wq").value.trim(); S.world.offset = 0; renderWorld(); };
  $("#wq").onkeydown = e => { if (e.key === "Enter") el.querySelector("#wgo").click(); };
  el.querySelector("#wPrev").onclick = () => { S.world.offset = Math.max(0, S.world.offset - 200); renderWorld(); };
  el.querySelector("#wNext").onclick = () => { if (S.world.offset + 200 < S.world.total) { S.world.offset += 200; renderWorld(); } };
  el.querySelector("#wall").onclick = async () => {
    const n = S.world.total;
    const ok = await confirmDlg(`nadać całą grupę ${S.world.group}?`,
      `Ustawię <b>${n}</b> flag na „zdobyte" (stan 1) w kopii roboczej. To duża zmiana — sprawdź podgląd przed ZASTOSUJ.`, false, `NADAJ ${n} FLAG`);
    if (ok) { await doStage(["world", "--slot", String(S.slot), "--group", S.world.group, "--all", "--state", "1"], "grupa " + S.world.group); renderWorld(); }
  };
  el.querySelectorAll("[data-fl]").forEach(b => b.onclick = async () => {
    const id = b.dataset.fl, cur = b.dataset.v === "1";
    const ok = await confirmDlg(cur ? "zdjąć flagę?" : "ustawić flagę?", `ID <span class="mono">${id}</span> → stan ${cur ? 0 : 1}`, false, "USTAW");
    if (!ok) return;
    await doStage(["world", "--slot", String(S.slot), "--group", S.world.group, "--set", id, "--state", cur ? "0" : "1"], "flaga " + id);
    renderWorld();
  });
}

/* -------------------------------------------------------- panel: CZARY -- */

async function renderSpells() {
  const el = $("#panel-czary");
  const c = charOfSlot();
  if (!c) { el.innerHTML = needSlot(); return; }
  const r = await P("spells", S.save, S.slot);
  if (r.error) { el.innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  el.innerHTML = `
    <div class="toolbar">
      <input class="lcdin" id="spQ" placeholder="nazwa czaru do zapamiętania…" style="width:260px">
      <button class="key small orange" id="spAdd">ZAPAMIĘTAJ</button>
      <button class="key small hazardk" id="spClr" style="display:none"></button>
      <button class="key small" id="spClear">WYCZYŚĆ WSZYSTKO…</button>
    </div>
    <div class="grid spellgrid">${r.spells.map(sp => `
      <div class="cell ${sp.empty ? "empty" : ""}">
        <div class="cslot">GNIAZDO ${String(sp.slot).padStart(2, "0")}</div>
        <div class="cname">${sp.empty ? "— puste —" : esc(sp.name)}</div>
        ${sp.empty ? "" : `<div class="cact"><button class="key small" data-fg="${sp.slot}">ZAPOMNIJ</button></div>`}
      </div>`).join("")}</div>`;
  el.querySelector("#spAdd").onclick = async () => {
    const name = $("#spQ").value.trim();
    if (!name) return toast("wpisz nazwę czaru", "err");
    await doStage(["spells", "--slot", String(S.slot), "--memorize", name], "czar: " + name);
    renderSpells();
  };
  el.querySelector("#spClear").onclick = async () => {
    const ok = await confirmDlg("wyczyścić wszystkie gniazda czarów?", "Wszystkie 14 gniazd zostaną opróżnione (na kopii roboczej).", true, "WYCZYŚĆ");
    if (ok) { await doStage(["spells", "--slot", String(S.slot), "--clear"], "czary: czyść"); renderSpells(); }
  };
  el.querySelectorAll("[data-fg]").forEach(b => b.onclick = async () => {
    await doStage(["spells", "--slot", String(S.slot), "--forget", b.dataset.fg], "zapomnij czar");
    renderSpells();
  });
}

/* ------------------------------------------------------ panel: WYGLĄD --- */

async function renderLooks() {
  const el = $("#panel-wyglad");
  const c = charOfSlot();
  if (!c) { el.innerHTML = needSlot(); return; }
  const r = await P("appearance", S.save, S.slot);
  if (r.error) { el.innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  el.innerHTML = `
    <h3 class="sect">wygląd / archetyp — slot ${String(S.slot).padStart(2, "0")}</h3>
    <div class="field"><label>płeć</label>
      <select class="lcdin" id="apG" style="width:170px"><option value="0" ${r.gender === 0 ? "selected" : ""}>0 — typ A</option>
      <option value="1" ${r.gender === 1 ? "selected" : ""}>1 — typ B</option></select></div>
    <div class="field"><label>budowa ciała</label>
      <select class="lcdin" id="apB" style="width:170px"><option value="0" ${r.body_type === 0 ? "selected" : ""}>0</option>
      <option value="1" ${r.body_type === 1 ? "selected" : ""}>1</option></select></div>
    <div class="field"><label>dar początkowy (0–255; archetyp b${r.archetype} zostaje)</label>
      <input class="lcdin" id="apGift" type="number" min="0" max="255" style="width:170px" value="${r.gift}"></div>
    <button class="key orange" id="apGo">DODAJ DO KOLEJKI</button>`;
  el.querySelector("#apGo").onclick = async () => {
    const argv = ["appearance", "--slot", String(S.slot)];
    const g = $("#apG").value, b = $("#apB").value, gift = $("#apGift").value;
    if (+g !== r.gender) argv.push("--gender", g);
    if (+b !== r.body_type) argv.push("--body", b);
    if (+gift !== r.gift) argv.push("--gift", gift);
    if (argv.length === 2) return toast("nic nie zmieniono", "info");
    await doStage(argv, "wygląd");
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
    <h3 class="sect">pozycja — slot ${String(S.slot).padStart(2, "0")}</h3>
    <div class="lcd" style="padding:9px 12px;display:inline-block">${esc(r.map_name)} · x=${r.xyz[0].toFixed(1)} y=${r.xyz[1].toFixed(1)} z=${r.xyz[2].toFixed(1)}</div>
    <h3 class="sect">teleport do lokacji</h3>
    <div class="inline">
      <select class="lcdin" id="tpSel" style="width:250px">${r.destinations.map(d => `<option>${d}</option>`).join("")}</select>
      <button class="key orange" id="tpGo">TELEPORTUJ</button>
    </div>
    <h3 class="sect">własne współrzędne</h3>
    <div class="inline">
      <input class="lcdin" id="tpMap" placeholder="m60_43_38_00" style="width:170px">
      <input class="lcdin" id="tpXyz" placeholder="x,y,z" style="width:190px">
      <button class="key" id="tpGo2">USTAW</button>
    </div>
    <div class="note" style="margin-top:12px">teleport zsynchronizuje pogodę z regionem mapy (inaczej doctor zgłasza desync).</div>`;
  el.querySelector("#tpGo").onclick = () =>
    doStage(["teleport", "--slot", String(S.slot), "--to", el.querySelector("#tpSel").value], "teleport").then(renderTeleportPanel);
  el.querySelector("#tpGo2").onclick = () => {
    const m = $("#tpMap").value.trim(), xyz = $("#tpXyz").value.trim();
    if (!m || !xyz) return toast("podaj mapę i xyz", "err");
    doStage(["teleport", "--slot", String(S.slot), "--map", m, "--xyz", xyz], "teleport").then(renderTeleportPanel);
  };
}

/* -------------------------------------------------------- panel: RYZYKO -- */

async function renderRisk() {
  const el = $("#panel-ryzyko");
  if (!S.save) { el.innerHTML = `<div class="note">wskaż plik.</div>`; return; }
  el.innerHTML = `<div class="toolbar"><button class="key small" data-act="scan">SKANUJ RYZYKO</button>
    <span class="note">ocenia dane niemożliwe + znacznik modyfikacji; to nie jest gwarancja braku flagi.</span></div>
    <div id="riskBody" class="note">kliknij SKANUJ…</div>`;
  el.querySelector("[data-act=scan]").onclick = async () => {
    busy(true, "SKAN RYZYKA…");
    const r = await P("risk_scan", S.save);
    busy(false);
    if (r.error) { $("#riskBody").innerHTML = esc(r.error); return; }
    const perSlot = {};
    r.findings.forEach(f => { if (f.slot !== null) (perSlot[f.slot] = perSlot[f.slot] || []).push(f); });
    const chars = S.info.characters.filter(c => !c.empty);
    const bars = chars.map(c => {
      const fs = perSlot[c.slot] || [];
      const v = fs.some(f => f.level === "error") ? "red" : fs.some(f => f.level === "warning") ? "yellow" : "green";
      return `<div class="riskbar ${v}"><span class="verdict">${v === "red" ? "CZERWONY" : v === "yellow" ? "ŻÓŁTY" : "ZIELONY"}</span>
        <b>slot ${String(c.slot).padStart(2, "0")} ${esc(c.name)}</b>
        <span class="note">${fs.filter(f => f.level !== "info").length} uwag${fs.some(f => f.level === "error") ? " — dane niemożliwe!" : ""}</span></div>`;
    }).join("");
    const rows = r.findings.map(f => `<div class="frow"><span class="sev ${f.level === "error" ? "err" : f.level === "warning" ? "war" : "ok"}"></span>
      <div class="fbody"><div class="fmsg">${esc(f.message)}</div><div class="fcode">${esc(f.code)}${f.slot !== null ? " · slot " + f.slot : ""}</div></div></div>`).join("");
    const mod = r.modified || {};
    $("#riskBody").innerHTML = bars +
      (mod.count ? `<div class="lcd" style="padding:8px 11px;margin-bottom:10px">znacznik: plik MODYFIKOWANY przez Rezura — ${mod.count} operacji; ostatnia ${esc(mod.last)}</div>`
                 : `<div class="lcd" style="padding:8px 11px;margin-bottom:10px">znacznik: brak śladów Rezura w tym pliku</div>`) +
      (r.gold ? `<div class="lcd" style="padding:8px 11px;margin-bottom:10px">GOLD: ${esc(r.gold)} — powrót do oryginału z zakładki KOPIE</div>` : "") +
      rows +
      `<h3 class="sect">notatki</h3><div class="note">${(r.notes || []).map(n => "• " + esc(n)).join("<br>")}</div>`;
  };
}

/* --------------------------------------------------------- panel: KOPIE -- */

async function renderBackups() {
  const el = $("#panel-kopie");
  if (!S.save) { el.innerHTML = `<div class="note">wskaż plik.</div>`; return; }
  const r = await P("backups", S.save);
  if (r.error) { el.innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  const hasGold = r.rows.some(b => b.gold);
  el.innerHTML = `
    <div class="toolbar">
      <button class="key small" data-act="reload">ODŚWIEŻ</button>
      ${hasGold ? "" : `<button class="key small orange" data-act="gold">ZRÓB KOPIĘ GOLD</button>`}
      <span class="note">rotacja trzyma ${r.retention} kopii; GOLD i przypięte — na zawsze.</span>
    </div>
    <table class="tbl"><thead><tr><th style="width:64px">typ</th><th class="mono" style="width:130px">data</th>
      <th>nazwa</th><th class="mono" style="width:80px">rozmiar</th><th style="width:230px">akcje</th></tr></thead>
      <tbody>${r.rows.map(b => `
        <tr><td>${b.gold ? `<span class="mark gold">GOLD</span>` : b.pinned ? `<span class="mark pin">PIN</span>` : ""}</td>
        <td class="mono">${new Date(b.mtime * 1000).toLocaleString("pl-PL")}</td>
        <td class="grow">${esc(b.name)}</td><td class="mono">${(b.size / 1e6).toFixed(1)} MB</td>
        <td><div class="acts">
          <button class="key small" data-rs="${esc(b.name)}">PRZYWRÓĆ…</button>
          <button class="key small" data-pin="${esc(b.name)}" data-on="${b.pinned ? 0 : 1}">${b.pinned ? "ODEPNIJ" : "PRZYPINIJ"}</button>
        </div></td></tr>`).join("")}</tbody></table>`;
  el.querySelector("[data-act=reload]").onclick = () => renderBackups();
  el.querySelector("[data-act=gold]")?.addEventListener("click", async () => {
    const g = await P("backup_gold", S.save);
    if (g.error) toast(g.error, "err");
    else toast(g.created ? "zrobiono kopię GOLD" : "GOLD już istnieje", "ok");
    renderBackups();
  });
  el.querySelectorAll("[data-rs]").forEach(b => b.onclick = async () => {
    const name = b.dataset.rs;
    const ok = await confirmDlg("przywrócić kopię?", `
      <div>Plik <b>${esc(name)}</b> zastąpi obecny save.</div>
      <div>Przed przywróceniem zrobimy kopię stanu obecnego (pre-restore).</div>`, true, "PRZYWRÓĆ");
    if (!ok) return;
    busy(true, "PRZYWRACANIE…");
    const r2 = await P("restore", S.save, name);
    busy(false);
    if (r2.error) return toast(r2.error, "err", 6000);
    toast("przywrócono — możesz porównać i wrócić do nowszego stanu z listy", "ok", 6000);
    await loadSave(true);
  });
  el.querySelectorAll("[data-pin]").forEach(b => b.onclick = async () => {
    const r2 = await P("backup_pin", S.save, b.dataset.pin, b.dataset.on === "1");
    if (r2.error) toast(r2.error, "err"); else toast(b.dataset.on === "1" ? "przypięto" : "odpięto", "ok");
    renderBackups();
  });
}

/* ----------------------------------------------------------- panel: LOG -- */

async function renderLog() {
  const el = $("#panel-log");
  if (!S.save) { el.innerHTML = `<div class="note">wskaż plik.</div>`; return; }
  const r = await P("log", S.save);
  if (r.error) { el.innerHTML = `<div class="note">${esc(r.error)}</div>`; return; }
  el.innerHTML = `
    <div class="toolbar"><button class="key small" data-act="reload">ODŚWIEŻ</button>
    <span class="note">dziennik edycji — każdy udany zapis (znacznik „modyfikowany")</span></div>
    <table class="tbl"><thead><tr><th class="mono" style="width:150px">kiedy</th><th style="width:220px">operacja</th><th>backup</th></tr></thead>
    <tbody>${[...r.entries].reverse().map(e => `
      <tr><td class="mono">${esc(e.ts)}</td><td>${esc(r.labels[e.op] || e.op)}</td><td class="grow mono">${esc(e.note || "—")}</td></tr>`).join("")
      || `<tr><td colspan="3" class="note">(pusto — dziennik zapisuje każdą udaną modyfikację)</td></tr>`}</tbody></table>`;
  el.querySelector("[data-act=reload]").onclick = () => renderLog();
}

/* ---------------------------------------------------- panel: USTAWIENIA -- */

function renderSettings() {
  const el = $("#panel-ustawienia");
  const c = S.cfg || {};
  el.innerHTML = `
    <div class="statmod">
      <h3 class="sect">config</h3>
      <div class="inline" style="margin-bottom:10px">
        <span class="cap">rotacja kopii</span>
        <input class="lcdin" id="cfRet" type="number" min="0" style="width:80px" value="${c.backup_retention ?? 20}">
        <span class="cap">interwał watch [s]</span>
        <input class="lcdin" id="cfWatch" type="number" min="60" style="width:100px" value="${c.watch_interval ?? 600}">
      </div>
      <div class="inline" style="margin-bottom:10px">
        <span class="swbox ${c.guard_live ? "on" : ""}" id="cfGuard"><i></i></span>
        <span class="cap">blokada zapisu przy działającej grze (guard_live)</span>
      </div>
      <div class="inline" style="margin-bottom:14px">
        <span class="swbox ${c.auto_doctor ? "on" : ""}" id="cfDoc"><i></i></span>
        <span class="cap">auto-diagnostyka po naprawach</span>
      </div>
      <div class="keyrow">
        <button class="key orange" id="cfSave">ZAPISZ USTAWIENIA</button>
        <button class="key" id="cfFolder">OTWÓRZ FOLDER SAVE'A</button>
        <button class="key" id="cfWatch1">WATCH: JEDEN PRZEBIEG</button>
      </div>
      <h3 class="sect">o programie</h3>
      <div class="note">
        REZUR v${esc(S.version || "")} — silnik + CLI + GUI (pywebview/WebView2).<br>
        100% offline — zero połączeń sieciowych, zero telemetrii.<br>
        plik save'a nie opuszcza tego komputera. edycje zawsze przez kopię roboczą → ZASTOSUJ.
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
      S.cfg = r.config;
    }
    toast("ustawienia zapisane", "ok");
  };
  el.querySelector("#cfFolder").onclick = async () => {
    if (!S.save) return toast("brak pliku", "err");
    const r = await P("open_folder", S.save);
    if (r.error) toast(r.error, "err");
  };
  el.querySelector("#cfWatch1").onclick = async () => {
    if (!S.save) return toast("brak pliku", "err");
    const r = await P("watch_once", S.save);
    if (r.error) return toast(r.error, "err");
    toast(r.made ? `kopia: ${r.made}` : `bez kopii (${r.reason})`, r.made ? "ok" : "info", 5000);
  };
}

/* ------------------------------------------------------------ start ---- */

function render() {
  $$(".tab").forEach(t => t.classList.toggle("on", t.dataset.tab === S.tab));
  $$(".panel").forEach(p => p.classList.toggle("hidden", p.id !== "panel-" + S.tab));
  renderCtx();
  refreshCurrent();
}

async function boot() {
  $$(".tab").forEach(t => t.onclick = () => { S.tab = t.dataset.tab; render(); });
  $("#btnPick").onclick = pickAndLoad;
  $("#btnPick2").onclick = pickAndLoad;
  $("#btnApply").onclick = onApply;
  $("#btnDiscard").onclick = onDiscard;
  $("#btnUndo").onclick = onUndo;
  $("#btnPreview").onclick = onPreview;
  updateStagebar();

  const ready = await bridgeReady();
  if (!ready && !MOCK) {
    window.__rezurBooted = "no-bridge";
    setStatus("BRAK MOSTU PYTHONA — otwórz przez `python -m rezur gui`");
    toast("brak mostu pywebview — to okno podglądu bez silnika", "err", 8000);
    return;
  }
  const st = await P("initial_state");
  if (st.error) { window.__rezurBooted = "init-error"; toast(st.error, "err"); return; }
  S.version = st.version;
  S.cfg = st.config || {};
  S.game = !!st.game_running;
  $("#txtVer").textContent = "FW " + (st.version || "—");
  $("#emptyNote").innerHTML = $("#emptyNote").innerHTML; // static
  if (st.save) { S.save = st.save; await loadSave(); }
  else { $("#empty").classList.remove("hidden"); }
  updateHeader();
  window.__rezurBooted = true;
  window.__rezurLoaded = S.info ? S.info.characters.filter(c => !c.empty).length : 0;

  setInterval(async () => {
    const g = await P("game_status");
    if (!g.error && g.running !== S.game) { S.game = g.running; updateHeader(); }
  }, 20000);

  $("#btnRecent").onclick = pickAndLoad;
}

boot();

/* ============================================================ MOCK ====== */
/* Podgląd UI w przeglądarce (?mock=1) — dane atrapa, zero mostu. */

function mockApi(name, args) {
  const c = (slot, nm, lvl, h, runes, stats, patch, latest, bug) =>
    ({ slot, empty: false, parsed: true, name: nm, level: lvl, seconds: h * 3600, runes, stats, map_name: "m60_48_41_00", patch, patch_latest: latest, horse: bug ? "ACTIVE" : "INACTIVE", horse_bug: bug });
  const DATA = {
    info: {
      ok: true, path: "C:\\Users\\Dawid\\AppData\\Roaming\\EldenRing\\76561199197611189\\ER0000.sl2",
      file: "ER0000.sl2", size_mb: 29.0, steamid: "76561199197611189", load_ms: 287,
      md5: { ok: 12, total: 12 }, game_running: false, live: true, staged: true,
      characters: [
        c(0, "lmfh test", 162, 71.7, 3403551, [99,28,18,30,50,60,70,50], 230, false, false),
        c(1, "hajime", 36, 12.8, 211158, [20,14,12,16,14,10,12,9], 250, false, true),
        c(2, "annesee", 54, 13.9, 494950, [14,20,8,16,16,12,31,16], 261, true, false),
        { slot: 3, empty: true }, { slot: 4, empty: true }, { slot: 5, empty: true },
        { slot: 6, empty: true }, { slot: 7, empty: true }, { slot: 8, empty: true }, { slot: 9, empty: true },
      ],
    },
    pending: { ok: true, count: 2, created: "2026-10-13 21:40", original_changed: false,
      ops: [{ ts: "21:41", op: "stats", summary: "--slot 0 --set vigor=99,mind=28" }, { ts: "21:42", op: "item", summary: "--add Uchigatana --upgrade 5" }] },
  };
  const R = {
    initial_state: { version: "0.1.0", save: DATA.info.path, config: { backup_retention: 20, watch_interval: 600, guard_live: true, auto_doctor: true }, game_running: false },
    config_get: { config: { backup_retention: 20, watch_interval: 600, guard_live: true, auto_doctor: true } },
    game_status: { running: false },
    load: () => DATA.info,
    pending: () => DATA.pending,
    preview: { ok: true, changed: ["USER_DATA000", "USER_DATA010"] },
    doctor: { ok: true, md5: { ok: 12, total: 12, bad: [] }, findings: [
      { level: "warning", code: "patch_old", message: "postać ze starszego patcha gry (base=230, slot=v250) — wczytaj ją raz na aktualnym patchu", slot: 0, fix: null },
      { level: "warning", code: "torrent_bug", message: "Torrent: hp=0 i stan ACTIVE — zawieszka na ładowaniu", slot: 1, fix: "torrent" },
      { level: "warning", code: "inv_counter_mismatch", message: "liczniki ekwipunku się nie zgadzają (held/common: 304≠309)", slot: 2, fix: "invcounters" },
      { level: "info", code: "items_unresolved", message: "8 itemów spoza naszej bazy (nowszy dodatek albo pozostałość po modach — nie przesądzamy)", slot: 2, fix: null },
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
    undo: { ok: true, undone: { op: "stats", summary: "..." }, left: 1 },
    discard: { ok: true, ops: 2 },
    apply: { ok: true, backup: "ER0000.sl2.stagebak-x", ops: 2, md5_ok: 12, md5_total: 12 },
    backup_gold: { ok: true, created: false, path: "x" },
    backup_pin: { ok: true, pins: [] },
    restore: { ok: true },
    config_set: { ok: true, config: {} },
    open_folder: { ok: true },
    pick_save: { cancelled: true },
  };
  const v = R[name];
  const out = typeof v === "function" ? v(...args) : v;
  return Promise.resolve(out === undefined ? { ok: true } : JSON.parse(JSON.stringify(out)));
}
