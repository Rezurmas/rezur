"""Punkt wejścia dla PyInstallera.

`rezur/__main__.py` używa importów relatywnych (`from .cli import …`), więc nie da się
go uruchomić jako skryptu najwyższego poziomu — stąd ten cienki launcher pakietu.
"""

import sys

from rezur.cli import main

if __name__ == "__main__":
    sys.exit(main())
