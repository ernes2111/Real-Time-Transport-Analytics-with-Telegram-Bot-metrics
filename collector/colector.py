"""
collector/colector.py — Colector autónomo de datos de arrivals.

Consulta las paradas configuradas cada N minutos (intervalo dinámico
según franja horaria) y guarda los arrivals en SQLite para análisis.

Corre 24hs como servicio systemd independiente del bot de Telegram.

Intervalos:
    06:00–23:59 → cada 3 minutos  (hora pico, servicio frecuente)
    00:00–05:59 → cada 15 minutos (madrugada, servicio reducido)

Uso:
    python -m collector.colector
    # o directamente:
    python collector/colector.py
"""

import logging
import logging.handlers
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from collector.config_colector import PARADAS, FRANJAS_HORARIAS
from config import config
from src.api.client import APIError, ParadaNoEncontrada
from src.services.consulta_service import ConsultaService
from src.storage.history import HistoryStorage

# ── Logging ───────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    log_path = Path("logs/colector.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        handlers=[fh, ch],
    )

logger = logging.getLogger(__name__)


# ── Lógica de intervalo dinámico ──────────────────────────────────────────────

def intervalo_actual() -> int:
    """
    Devuelve el intervalo en minutos según la hora del día.

    FRANJAS_HORARIAS = [
        (hora_inicio, hora_fin_inclusive, intervalo_min, descripcion),
        ...
    ]
    La primera franja que coincida gana.
    """
    hora = datetime.now().hour
    for inicio, fin, intervalo, _ in FRANJAS_HORARIAS:
        if inicio <= hora <= fin:
            return intervalo
    # Fallback: intervalo conservador
    return 10


def descripcion_franja() -> str:
    hora = datetime.now().hour
    for inicio, fin, intervalo, desc in FRANJAS_HORARIAS:
        if inicio <= hora <= fin:
            return f"{desc} ({intervalo} min)"
    return "franja no definida"


# ── Ciclo principal ───────────────────────────────────────────────────────────

def consultar_y_guardar(storage: HistoryStorage) -> None:
    """Consulta todas las paradas configuradas y guarda los arrivals."""
    for parada_id in PARADAS:
        try:
            with ConsultaService() as service:
                resultado = service.consultar_parada(parada_id)

            storage.guardar(
                parada=resultado.parada,
                arribos=resultado.arribos,
                origen="collector",
                user_id=None,
            )
            logger.info(
                "Parada %s → %d arrivals guardados",
                parada_id,
                len(resultado.arribos),
            )

        except ParadaNoEncontrada:
            logger.warning("Parada %s no encontrada — ¿cambió el número?", parada_id)

        except APIError as e:
            logger.warning("Error API en parada %s: %s — se reintentará en el próximo ciclo", parada_id, e)

        except Exception as e:
            logger.error("Error inesperado en parada %s: %s", parada_id, e)

        # Pequeña pausa entre paradas para no sobrecargar la API
        time.sleep(2)


def main() -> None:
    _setup_logging()
    logger.info("=" * 60)
    logger.info("Colector autónomo iniciado.")
    logger.info("Paradas: %s", ", ".join(PARADAS))
    logger.info("=" * 60)

    storage = HistoryStorage()

    ciclo = 0
    try:
        while True:
            ciclo += 1
            intervalo = intervalo_actual()
            now_str = datetime.now().strftime("%H:%M:%S")
            logger.info(
                "── Ciclo #%d (%s) │ Franja: %s",
                ciclo, now_str, descripcion_franja(),
            )

            consultar_y_guardar(storage)

            proxima = datetime.now().strftime("%H:%M:%S")
            logger.info(
                "Ciclo #%d completado. Próxima consulta en %d min.",
                ciclo, intervalo,
            )
            time.sleep(intervalo * 60)

    except KeyboardInterrupt:
        logger.info("Colector detenido manualmente.")
    finally:
        storage.close()
        logger.info("Conexión DB cerrada. Hasta luego.")


if __name__ == "__main__":
    main()
