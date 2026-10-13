"""Okno GUI (pywebview / WebView2) — cienka skorupka nad rezur.gui.api."""

import argparse
import threading
import time
from pathlib import Path

from .api import GuiApi

WINDOW_TITLE = "REZUR — Saves Configurator"


def web_dir():
    return Path(__file__).parent / "web"


def run(save=None, selftest=False):
    import webview

    api = GuiApi(initial_save=save)
    win = webview.create_window(
        WINDOW_TITLE,
        str(web_dir() / "index.html"),
        js_api=api,
        width=1290,
        height=840,
        min_size=(1024, 660),
        background_color="#16171A",
    )
    if selftest:
        def _close():
            time.sleep(5)
            try:
                booted = win.evaluate_js("window.__rezurBooted === true")
                loaded = win.evaluate_js("window.__rezurLoaded || 0")
                title = win.evaluate_js("document.title")
                print(f"[selftest] booted={booted} characters_loaded={loaded} title={title!r}")
            except Exception as e:  # noqa: BLE001
                print(f"[selftest] evaluate_js nie odpowiedział: {e}")
            time.sleep(2)
            try:
                win.destroy()
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_close, daemon=True).start()
    webview.start()
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="rezur gui", description="Rezur — okno GUI")
    p.add_argument("--save", default=None, help="plik .sl2 na start")
    p.add_argument("--selftest", action="store_true", help="otwórz i zamknij po 6 s (test dymny)")
    a = p.parse_args(argv)
    return run(a.save, a.selftest)


if __name__ == "__main__":
    raise SystemExit(main())
