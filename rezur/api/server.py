"""Rezur API (placeholder F6) — FastAPI nad warstwami core/diag/fixes/ops.

Uruchomienie (po doinstalowaniu `fastapi` + `uvicorn`):

    uvicorn rezur.api.server:create_app --factory --host 127.0.0.1 --port 8777

Kontrakt docelowy (patrz ARCHITECTURE.md):
    GET  /api/health
    POST /api/session          {path}      -> wczytanie save'a do sesji
    GET  /api/save             -> kontener + postacie (jak `rezur info`)
    GET  /api/diagnostics      -> findings (jak `rezur doctor --json`)
    POST /api/fixes/apply      {ids: [...]}-> naprawy + zapis + re-diagnostyka
    POST /api/ops/copy         {from,to,clear_source}
    POST /api/ops/steamid      {new_id}
    GET  /api/backups          -> lista plików *.rezurbak-*
    POST /api/backups/restore  {name}
    SSE /api/events            -> postęp operacji

Zasady: bind wyłącznie 127.0.0.1; nagłówek X-Rezur-Token z lokalnego pliku
sesji; żadnych uploadów do sieci — plik nigdy nie opuszcza maszyny.
"""

from .. import __product__, __version__


def create_app():
    from fastapi import FastAPI  # import leniwy — bez fastapi moduł da się importować

    app = FastAPI(title=__product__, version=__version__)

    @app.get("/api/health")
    def health():
        return {"ok": True, "product": __product__, "version": __version__}

    # TODO(F6): implementacja endpointów wg kontraktu w docstringu modułu.
    # Wzorzec: z cli importujemy te same funkcje i owijamy je w JSON.
    return app
