# -*- mode: python ; coding: utf-8 -*-
# PyInstaller:  python -m PyInstaller packaging/rezur.spec
# Wynik:        dist/rezur.exe  (onefile, bez instalatora, bez zależności poza systemem)
import glob
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821  (packaging/ -> katalog repo)

datas = []
for p in (ROOT / "rezur" / "data").rglob("*"):
    if p.is_file():
        rel = p.relative_to(ROOT)
        datas.append((str(p), str(rel.parent)))

a = Analysis(
    [str(ROOT / "rezur" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest.mock", "pydoc"],
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
