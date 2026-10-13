"""Profile gier — rejestr wspieranych tytułów (na razie Elden Ring)."""

from .base import GameSupport, get_game, list_games  # noqa: F401
from . import eldenring  # noqa: F401  (rejestracja przy imporcie)
