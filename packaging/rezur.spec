# -*- mode: python ; coding: utf-8 -*-
# PyInstaller:  python -m PyInstaller packaging/rezur.spec
# Wynik:        dist/rezur.exe  (onefile, bez instalatora, bez zależności poza systemem)
import glob
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821  (packaging/ -> katalog repo)

datas = []
# dane + interfejs GUI (bez web/ okno w spakowanym exe nie wystartuje)
for sub in ("data", "gui/web"):
    for p in (ROOT / "rezur" / sub).rglob("*"):
        if p.is_file():
            rel = p.relative_to(ROOT)
            datas.append((str(p), str(rel.parent)))

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # GUI w jednym pliku: pywebview + pythonnet (WebView2)
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr",
        "clr_loader",
        "pythonnet",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["unittest.mock", "pydoc"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="rezur",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)
