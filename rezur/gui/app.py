"""Okno GUI (pywebview / WebView2) — cienka skorupka nad rezur.gui.api."""

import argparse
import threading
import time
from pathlib import Path

from .api import GuiApi

WINDOW_TITLE = "REZUR — Saves Configurator"


def web_dir():
    return Path(__file__).parent / "web"


def _selftest(win):
    """Test dymny okna: most, panele, język EN→PL→EN (na żywym oknie)."""
    def js(expr, default=None):
        try:
            return win.evaluate_js(expr)
        except Exception as e:  # noqa: BLE001
            print(f"[selftest] evaluate_js nie odpowiedział: {e}")
            return default

    def wait_for(expr, want, tries=60, step=0.5):
        for _ in range(tries):
            if js(expr) == want:
                return True
            time.sleep(step)
        return False

    wait_for("window.__rezurBooted === true", True, tries=120)
    time.sleep(0.5)
    booted = js("window.__rezurBooted === true")
    loaded = js("window.__rezurLoaded || 0")
    title = js("document.title")
    lang = js("(document.querySelector('#pillLang')||{}).textContent")
    tabs = js("[...document.querySelectorAll('.tab')].map(t=>t.textContent.trim()).join('|')")
    panels = js("document.querySelectorAll('.panel').length")
    apiN = js("Object.keys(window.pywebview.api||{}).length")
    status = js("(document.querySelector('#status')||{}).textContent")
    print(f"[selftest] booted={booted} characters_loaded={loaded} title={title!r}")
    print(f"[selftest] bridge_methods={apiN} panels={panels} lang={lang!r}")
    print(f"[selftest] tabs={tabs}")
    print(f"[selftest] status={status!r}")

    # --- wyszukiwanie na żywo: lista zawęża się w trakcie pisania
    js("document.querySelector('[data-tab=ekwipunek]') && document.querySelector('[data-tab=ekwipunek]').click(); 'ok'")
    time.sleep(1.5)
    before = js("document.querySelectorAll('#invRows tr').length")
    js("(function(){var i=document.querySelector('#invQ'); i.value='seed'; i.dispatchEvent(new Event('input')); return 'typed';})()")
    time.sleep(1.3)
    after = js("document.querySelectorAll('#invRows tr').length")
    print(f"[selftest] live-search INVENTORY: rows_before={before} rows_after_typing_seed={after}")

    js("document.querySelector('#invAdd') && document.querySelector('#invAdd').click(); 'open'")
    time.sleep(0.8)
    js("(function(){var i=document.querySelector('#qu2'); i.value='mimi'; i.dispatchEvent(new Event('input')); return 'typed';})()")
    time.sleep(1.4)
    sugg = js("document.querySelectorAll('#suggBox .srow').length")
    first = js("(document.querySelector('#suggBox .srow .sname')||{}).textContent")
    print(f"[selftest] suggestions('mimi'): hits={sugg} first={first!r}")
    js("document.querySelector('.mact .key') && document.querySelector('.mact .key').click(); 'close'")
    time.sleep(0.5)

    js("document.querySelector('[data-tab=swiat]') && document.querySelector('[data-tab=swiat]').click(); 'ok'")
    time.sleep(1.5)
    wbefore = js("document.querySelectorAll('#wrows .worldrow').length")
    js("(function(){var i=document.querySelector('#wq'); i.value='godrick'; i.dispatchEvent(new Event('input')); return 'typed';})()")
    time.sleep(1.4)
    wafter = js("document.querySelectorAll('#wrows .worldrow').length")
    wfirst = js("(document.querySelector('#wrows .wname')||{}).textContent")
    print(f"[selftest] live-search WORLD: rows_before={wbefore} rows_after_typing_godrick={wafter} first={wfirst!r}")

    js("document.querySelector('[data-tab=czary]') && document.querySelector('[data-tab=czary]').click(); 'ok'")
    time.sleep(1.7)
    sp_all = js("document.querySelectorAll('#spRows tr').length")
    js("(function(){var i=document.querySelector('#spQ'); i.value='heal'; i.dispatchEvent(new Event('input')); return 'typed';})()")
    time.sleep(1.5)
    sp_hits = js("document.querySelectorAll('#spRows tr').length")
    sp_first = js("(document.querySelector('#spRows .grow')||{}).textContent")
    sp_btns = js("document.querySelectorAll('#spRows [data-mem]').length")
    print(f"[selftest] SPELLS list: rows={sp_all} after_typing_heal={sp_hits} first={sp_first!r} buttons={sp_btns}")

    # --- język na żywo: EN → PL → EN (zapis w configu + przeładowanie okna)
    for step_lang, want_pill in (("pl", "PL"), ("en", "EN")):
        js(f"window.pywebview.api.config_set('ui_lang','{step_lang}'); 'ok'")
        js("setTimeout(()=>location.reload(), 150); 'reload'")
        ok = wait_for("(document.querySelector('#pillLang')||{}).textContent", want_pill)
        tabs2 = js("[...document.querySelectorAll('.tab')].map(t=>t.textContent.trim()).join('|')")
        print(f"[selftest] switch→{step_lang}: pill={'ok' if ok else '??'} tabs={tabs2}")
    cfg = js("(window.pywebview && window.pywebview.api) ? 'bridge-alive' : 'bridge-lost'")
    print(f"[selftest] after_switches={cfg}")

    time.sleep(0.8)
    try:
        win.destroy()
    except Exception:  # noqa: BLE001
        pass


def run(save=None, selftest=False):
    import webview

    index = web_dir() / "index.html"
    if not index.is_file():
        print(f"[gui] brak plików interfejsu: {index}")
        print("[gui] w spakowanym exe dodaj 'rezur/gui/web' do datas w packaging/rezur.spec")
        return 2
    api = GuiApi(initial_save=save)
    win = webview.create_window(
        WINDOW_TITLE,
        str(index),
        js_api=api,
        width=1290,
        height=840,
        min_size=(1024, 660),
        background_color="#16171A",
    )
    if selftest:
        threading.Thread(target=_selftest, args=(win,), daemon=True).start()
    webview.start()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="rezur gui", description="Rezur — okno GUI")
    p.add_argument("--save", default=None, help="plik .sl2 na start")
    p.add_argument("--selftest", action="store_true", help="otwórz, sprawdź most i przełącz język EN/PL, zamknij (~30 s)")
    a = p.parse_args(argv)
    return run(a.save, a.selftest)


if __name__ == "__main__":
    raise SystemExit(main())
