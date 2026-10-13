"""Rezur Saves Configurator — konfigurator i naprawiacz save'ów Elden Ring (.sl2).

Warstwy (od dołu):
    core/   — czytanie/pisanie formatu (bnd4, sloty, sumy, profile)
    games/  — profil gry (na razie Elden Ring; struktura pod kolejne)
    diag/   — silnik diagnostyki (wykrywanie błędów)
    fixes/  — rejestr napraw (torrent, sumy, profil, weather, dlc)
    ops/    — operacje wyższego rzędu (kopiowanie postaci itd.)
    report/ — formatowanie wyników (tekst, json)
    cli.py  — interfejs wiersza poleceń          (teraz)
    api/    — HTTP (FastAPI) pod przyszłe GUI    (plan, F6)

Zasada: core nie wie nic o diag/fixes; fixes piszą tylko przez SaveFile;
cli/api są cienkimi adapterami nad warstwami.
"""

__product__ = "Rezur Saves Configurator"
__version__ = "0.2.0"
__short__ = "rezur"
