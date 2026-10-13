"""Przejście po WSZYSTKICH panelach prawdziwego okna (exe albo `python -m rezur gui`) przez CDP.

Uruchamia GUI z `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=<port>`, klika każdą
zakładkę, czyta stan panelu (widoczny dokładnie jeden, brak „undefined/NaN”, liczba wierszy i
przycisków), robi edycję na próbę (+ w STATACH) i sprawdza licznik zmian + ODRZUĆ, potem przełącza
język na żywo. Na końcu zrzuty wybranych paneli.

    python tests/gui_panels_check.py [--exe dist/rezur.exe] [--save PLIK] [--port 9225]
                                     [--shots KATALOG]

Kod wyjścia != 0, gdy którykolwiek panel/punkt kontrolny padnie.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent

TABS = [
    ("postacie", "CHARACTERS"),
    ("doktor", "DOCTOR"),
    ("staty", "STATS"),
    ("ekwipunek", "INVENTORY"),
    ("eq", "LOADOUT"),
    ("swiat", "WORLD"),
    ("czary", "SPELLS"),
    ("wyglad", "APPEARANCE"),
    ("teleport", "TELEPORT"),
    ("ryzyko", "RISK"),
    ("kopie", "BACKUPS"),
    ("log", "HISTORY"),
    ("ustawienia", "SETTINGS"),
]

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""), flush=True)


class Cdp:
    def __init__(self, ws):
        self.ws = ws
        self.i = 0
        self.events: list[str] = []

    async def call(self, method, **params):
        self.i += 1
        mid = self.i
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=30))
            if msg.get("method") == "Runtime.exceptionThrown":
                det = msg["params"].get("exceptionDetails", {})
                desc = (det.get("exception") or {}).get("description") or det.get("text") or ""
                self.events.append("EXC: " + str(desc)[:200])
            elif msg.get("method") == "Runtime.consoleAPICalled":
                args = " ".join(str(a.get("value", a.get("description", "")))[:150]
                                  for a in msg["params"].get("args", []))
                if args.strip():
                    self.events.append(f"{msg['params'].get('type')}: {args}")
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    async def js(self, expr, await_promise=False):
        r = await self.call("Runtime.evaluate", expression=expr, returnByValue=True,
                            awaitPromise=await_promise)
        return r.get("result", {}).get("value")

    async def shot(self, path: Path):
        r = await self.call("Page.captureScreenshot", format="png")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(r["data"]))


PROBE = """
(() => {
  const vis = [...document.querySelectorAll('.panel')].filter(p => !p.classList.contains('hidden'));
  if (vis.length !== 1) return {err: 'widocznych paneli: ' + vis.length};
  const p = vis[0];
  const txt = p.innerText || '';
  const bad = [];
  for (const m of ['undefined', 'NaN', '[object Object]']) if (txt.includes(m)) bad.push(m);
  return {
    err: '',
    rows: p.querySelectorAll('tr').length,
    btns: p.querySelectorAll('button, .key, .stbtn').length,
    len: txt.length,
    bad: bad.join(','),
    head: txt.split('\\n').map(s => s.trim()).filter(Boolean).slice(0, 3).join(' / ')
  };
})()
"""


async def drive(port: int, shots: Path | None, expect_save: Path | None = None):
    ws_url = None
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=3) as r:
                tabs = json.load(r)
            pages = [t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
            if pages:
                ws_url = pages[0]["webSocketDebuggerUrl"]
                break
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(1)
    if not ws_url:
        record("CDP: okno odpowiedziało", False, f"brak /json/list na porcie {port}")
        return

    async with websockets.connect(ws_url, max_size=32 << 20) as ws:
        cdp = Cdp(ws)
        await cdp.call("Runtime.enable")
        await cdp.call("Page.enable")

        for _ in range(240):  # zimny start exe + wczytanie ~29 MB potrafi potrwać
            if await cdp.js("window.__rezurBooted === true && (window.__rezurLoaded||0) > 0"):
                break
            await asyncio.sleep(0.75)
        booted = await cdp.js("window.__rezurBooted === true")
        loaded = await cdp.js("window.__rezurLoaded || 0")
        status = await cdp.js("(document.querySelector('#status')||{}).textContent")
        if not (booted and loaded):
            tf = await cdp.js("(document.querySelector('#txtFile')||{}).textContent")
            st0 = await cdp.js("window.pywebview.api.initial_state()", await_promise=True)
            print(f"      diagnostyka: booted={booted} loaded={loaded} status={status!r} plik={tf!r}")
            print(f"      bridge.initial_state() → {json.dumps(st0, ensure_ascii=False)[:220] if isinstance(st0, dict) else st0}")
            for ev in cdp.events[-8:]:
                print("      " + ev)
        record("okno wystartowało (booted + dane wczytane)", bool(booted and loaded),
               f"loaded={loaded} status={status!r}")

        live = await cdp.js("Object.keys(window.pywebview.api||{}).length")
        record("most pywebview żyje", isinstance(live, int) and live >= 30, f"metody: {live}")

        if expect_save is not None:
            st0 = await cdp.js("window.pywebview.api.initial_state()", await_promise=True)
            got = (st0 or {}).get("save") if isinstance(st0, dict) else None
            same = bool(got) and Path(str(got)).name == expect_save.name and str(expect_save.parent).lower() in str(got).lower()
            record("podpięte okno to TA instancja (ta sama ścieżka save'a)", same,
                   f"okno: {got}")

        for tid, label in TABS:
            await cdp.js(f"document.querySelector('[data-tab={tid}]').click(); 'ok'")
            await asyncio.sleep(0.7)
            r = await cdp.js(PROBE) or {}
            detail = f"wiersze={r.get('rows')} przyciski={r.get('btns')} znaków={r.get('len')}"
            ok = (not r.get("err")) and not r.get("bad") and (r.get("len") or 0) > 30
            if not ok:
                detail += f" | err={r.get('err')} bad={r.get('bad')} | {str(r.get('head'))[:90]}"
            record(f"panel {label}", ok, detail)
            if shots:
                await cdp.shot(shots / f"{label.lower()}.png")

        # edycja na próbę: + w STATACH (statystyka < 99) → KOLEJKA (staging) → licznik → ODRZUĆ
        await cdp.js("document.querySelector('[data-tab=staty]').click(); 'ok'")
        await asyncio.sleep(0.9)
        pend0 = await cdp.js("parseInt(document.querySelector('#pendN').textContent) || 0")
        changed = await cdp.js("""
(() => {
  for (const r of [...document.querySelectorAll('.statrow')]) {
    const v = r.querySelector('.sval[data-i]'), b = r.querySelector('.stbtn[data-plus="1"]');
    if (v && b && +v.textContent < 99) {
      const before = v.textContent;
      b.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
      b.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
      return (r.querySelector('.sname') || {}).textContent + ': ' + before + '→' + v.textContent;
    }
  }
  return 'brak statystyki < 99';
})()
""")
        await asyncio.sleep(0.5)
        await cdp.js("document.querySelector('#statStage').click(); 'ok'")
        await asyncio.sleep(2.2)
        pend1 = await cdp.js("parseInt(document.querySelector('#pendN').textContent) || 0")
        record("edycja (+ w STATACH → KOLEJKA) trafia do brudnopisu", (pend1 or 0) > (pend0 or 0),
               f"zmian: {pend0} → {pend1} [{changed}]")
        await cdp.js("document.querySelector('#btnDiscard').click(); 'ok'")
        await asyncio.sleep(0.8)
        await cdp.js("(document.querySelector('#modal.hidden') ? 'brak modala' : (document.querySelector('.mact .key').click(), 'potwierdzone'))")
        await asyncio.sleep(2.2)
        pend2 = await cdp.js("parseInt(document.querySelector('#pendN').textContent) || 0")
        record("ODRZUĆ (z potwierdzeniem) czyści brudnopis", (pend2 or 0) == 0, f"zmian po odrzuceniu: {pend2}")

        # język na żywo: EN → PL → EN
        await cdp.js("window.pywebview.api.config_set('ui_lang','pl'); 'ok'", await_promise=True)
        await cdp.js("setTimeout(()=>location.reload(), 120); 'ok'")
        await asyncio.sleep(3.5)
        pl = await cdp.js("(document.querySelector('[data-tab=postacie]')||{}).textContent")
        await cdp.js("window.pywebview.api.config_set('ui_lang','en'); 'ok'", await_promise=True)
        await cdp.js("setTimeout(()=>location.reload(), 120); 'ok'")
        await asyncio.sleep(3.5)
        en = await cdp.js("(document.querySelector('[data-tab=postacie]')||{}).textContent")
        record("język EN/PL na żywo", (pl or "").strip() != (en or "").strip()
               and "CHARACTERS" in (en or ""), f"pl={pl!r} en={en!r}")

        # wyszukiwanie na żywo w EKWIPUNKU (lista zawęża się w trakcie pisania)
        await cdp.js("document.querySelector('.card[data-slot]') && document.querySelector('.card[data-slot]').click(); 'ok'")
        await asyncio.sleep(0.8)
        await cdp.js("document.querySelector('[data-tab=ekwipunek]').click(); 'ok'")
        await asyncio.sleep(1.2)
        before = await cdp.js("document.querySelectorAll('#invRows tr').length")
        await cdp.js("(function(){var i=document.querySelector('#invQ'); i.value='seed'; i.dispatchEvent(new Event('input')); return 'ok';})()")
        await asyncio.sleep(1.6)
        after = await cdp.js("document.querySelectorAll('#invRows tr').length")
        record("wyszukiwanie na żywo (EKWIPUNEK)", (before or 0) > 0 and (after or 99) < (before or 0),
               f"wiersze: {before} → {after}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=str(ROOT / "dist" / "rezur.exe"))
    ap.add_argument("--save", default=r"C:\ER-Rezur-Demo\ER0000.sl2")
    ap.add_argument("--port", type=int, default=9225)
    ap.add_argument("--shots", default=None)
    a = ap.parse_args()

    sandbox = Path(tempfile.mkdtemp(prefix="rezur-gui-"))
    work = sandbox / "work"
    work.mkdir()
    appdata = sandbox / "appdata"
    appdata.mkdir()
    save = Path(a.save)
    if not save.is_file():
        print(f"brak save'a: {save}")
        return 2
    copy = work / "ER0000.sl2"
    shutil.copy2(save, copy)

    env = dict(os.environ)
    env["APPDATA"] = str(appdata)
    env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={a.port}"

    # Stare instancje exe trzymają port CDP i WebView2 — bez tego podpinamy się do martwego okna
    # (objaw: okno z poprzedniego przebiegu, pusta ścieżka pliku, „NO FILE”).
    subprocess.run(["taskkill", "/F", "/IM", "rezur.exe", "/T"], capture_output=True)
    time.sleep(1.0)

    exe = Path(a.exe)
    if exe.suffix.lower() == ".py":
        cmd = [sys.executable, "-m", "rezur", "gui", "--save", str(copy)]
    elif exe.is_file():
        cmd = [str(exe), "gui", "--save", str(copy)]
    else:
        cmd = [sys.executable, "-m", "rezur", "gui", "--save", str(copy)]
    print("start: " + " ".join(cmd))
    shots = Path(a.shots) if a.shots else None
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        asyncio.run(drive(a.port, shots, expect_save=copy))
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()

    ok = sum(1 for _n, o, _d in results if o)
    fail = len(results) - ok
    print(f"\n{'=' * 72}\nGUI PANELE: {ok}/{len(results)} PASS, {fail} FAIL")
    for n, o, d in results:
        if not o:
            print(f"  - {n}: {d}")
    shutil.rmtree(sandbox, ignore_errors=True)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
