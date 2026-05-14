"""
config.py — Configuración central del bot.
Todas las variables sensibles se cargan desde el archivo .env
"""

import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Telegram ─────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # ── API de Cuándo Llega ───────────────────────────────────────────────────
    API_BASE_URL: str = "https://app.cuandollegarosario.com/api/public"
    API_REFERER: str = "https://app.cuandollegarosario.com/"
    API_USER_AGENT: str = (
        "Mozilla/5.0 (Linux; Android 12; Pixel 5) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    )
    API_TIMEOUT: int = 10        # segundos por request
    API_MAX_RETRIES: int = 3     # reintentos ante fallos temporales

    # ── Almacenamiento (desactivado por defecto, listo para el futuro) ────────
    STORAGE_ENABLED: bool = os.getenv("STORAGE_ENABLED", "false").lower() == "true"
    DB_PATH: str = os.getenv("DB_PATH", "data/bot.db")
    FAVORITOS_MAX: int = int(os.getenv("FAVORITOS_MAX", "10"))

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/app.log")

    # ── IDs de admins de Telegram (lista separada por comas en .env) ──────────
    ADMIN_IDS: List[int] = [
        int(x.strip())
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    ]


config = Config()
