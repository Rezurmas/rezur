"""Składa ZIP z wydaniem: dist/Rezur-<wersja>-win64.zip.

Zawartość: rezur.exe (jednoplikowy), START-REZUR.cmd (odpala GUI), HOW-TO-RUN.txt
(instrukcja EN/PL). Pliki pomocnicze leżą w packaging/release/ i są wersjonowane,
więc ZIP odtwarza się jedną komendą:

    python tools/make_release_zip.py
"""

import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def version():
    txt = (ROOT / "rezur" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', txt)
    return m.group(1) if m else "0.0.0"


def main():
    exe = ROOT / "dist" / "rezur.exe"
    if not exe.is_file():
        print("brak dist/rezur.exe — najpierw: python -m PyInstaller --clean --noconfirm packaging/rezur.spec")
        return 1
    ver = version()
    out = ROOT / "dist" / f"Rezur-v{ver}-win64.zip"

    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / f"Rezur-v{ver}"
        stage.mkdir()
        shutil.copy2(exe, stage / "rezur.exe")
        for extra in ("START-REZUR.cmd", "HOW-TO-RUN.txt"):
            shutil.copy2(ROOT / "packaging" / "release" / extra, stage / extra)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for f in sorted(stage.iterdir()):
                z.write(f, arcname=f"{stage.name}/{f.name}")

    size_mb = out.stat().st_size / 1e6
    print(f"gotowe: {out}  ({size_mb:.1f} MB)")
    with zipfile.ZipFile(out) as z:
        for i in z.infolist():
            print(f"  {i.filename}  ({i.file_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
