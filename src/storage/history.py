"""
src/storage/history.py — Persistencia de histórico de consultas y arrivals.

Esquema (2 tablas):
    consultas         → cada evento de consulta (quién, cuándo, desde dónde)
    arribos_historico → cada colectivo en cada consulta (tabla principal de análisis)

El user_id se guarda hasheado (SHA-256 truncado a 16 chars) por privacidad.
El colector autónomo usa origen='collector' y user_id_hash=NULL.
"""

import hashlib
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import config
from src.models.arribo import Arribo
from src.models.parada import Parada

logger = logging.getLogger(__name__)

# Cache en memoria de coches recientemente vistos.
# key: (parada_id, id_coche, cartel) → datetime del primer avistamiento.
# Se limpia automáticamente al guardar (TTL = 90 min).
_COCHE_TTL = timedelta(minutes=90)
_recent_coches: Dict[Tuple[str, str, str], datetime] = {}


def _hash_user_id(user_id: int) -> str:
    """SHA-256 del user_id truncado a 16 caracteres. No reversible."""
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:16]


class HistoryStorage:
    """
    Almacena consultas y arrivals en SQLite para análisis estadístico.

    Uso:
        with HistoryStorage() as storage:
            storage.guardar(
                parada=resultado.parada,
                arribos=resultado.arribos,
                origen="parada",
                user_id=325475687,   # None para el colector
            )
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._path = Path(db_path or config.DB_PATH)
        self._conn: Optional[sqlite3.Connection] = None

        if config.STORAGE_ENABLED:
            self._init_db()
        else:
            logger.debug("Histórico INACTIVO (STORAGE_ENABLED=false).")

    # ── Inicialización ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Crea directorio, tablas e índices si no existen."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._path),
            check_same_thread=False,
            timeout=10,
        )
        self._conn.execute("PRAGMA journal_mode=WAL;")   # mejor concurrencia
        self._conn.execute("PRAGMA foreign_keys=ON;")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS consultas (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp     TEXT    NOT NULL,
                parada_id     TEXT    NOT NULL,
                parada_nombre TEXT,
                distrito      TEXT,
                origen        TEXT    NOT NULL DEFAULT 'parada',
                user_id_hash  TEXT
            );

            CREATE TABLE IF NOT EXISTS arribos_historico (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                consulta_id       INTEGER NOT NULL
                                  REFERENCES consultas(id) ON DELETE CASCADE,
                timestamp         TEXT    NOT NULL,
                hora_dia          INTEGER NOT NULL,
                dia_semana        INTEGER NOT NULL,
                parada_id         TEXT    NOT NULL,
                codigo_linea      TEXT,
                numero_linea      TEXT,
                cartel            TEXT,
                minutos_estimados INTEGER,
                distancia_km      REAL,
                es_adaptado       INTEGER NOT NULL DEFAULT 0,
                gps_fresco        INTEGER NOT NULL DEFAULT 1,
                id_coche          TEXT,
                esta_llegando     INTEGER NOT NULL DEFAULT 0,
                es_primer_avistamiento INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_ah_timestamp
                ON arribos_historico(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ah_hora_dia
                ON arribos_historico(hora_dia);
            CREATE INDEX IF NOT EXISTS idx_ah_cartel
                ON arribos_historico(cartel);
            CREATE INDEX IF NOT EXISTS idx_ah_parada
                ON arribos_historico(parada_id);
            CREATE INDEX IF NOT EXISTS idx_ah_coche
                ON arribos_historico(id_coche);
            CREATE INDEX IF NOT EXISTS idx_c_origen
                ON consultas(origen);
            CREATE INDEX IF NOT EXISTS idx_c_user
                ON consultas(user_id_hash);
            CREATE INDEX IF NOT EXISTS idx_ah_primer
                ON arribos_historico(es_primer_avistamiento);
        """)
        self._conn.commit()
        self._migrate_db()
        logger.info("Histórico inicializado en %s", self._path)

    def _migrate_db(self) -> None:
        """
        Aplica migraciones incrementales sobre una DB ya existente.
        Cada ALTER TABLE es idempotente (no falla si la columna ya existe).
        """
        migraciones = [
            "ALTER TABLE arribos_historico ADD COLUMN es_primer_avistamiento INTEGER NOT NULL DEFAULT 1",
        ]
        for sql in migraciones:
            try:
                self._conn.execute(sql)
                self._conn.commit()
                logger.debug("Migración aplicada: %s", sql[:60])
            except sqlite3.OperationalError:
                pass  # columna ya existe

    # ── Caché de primeros avistamientos ──────────────────────────────────────

    @staticmethod
    def _limpiar_cache_expirado() -> None:
        """Elimina entradas del caché que superaron el TTL de 90 min."""
        ahora = datetime.now()
        expirados = [
            k for k, t in _recent_coches.items()
            if ahora - t > _COCHE_TTL
        ]
        for k in expirados:
            del _recent_coches[k]

    @staticmethod
    def _es_primer_avistamiento(parada_id: str, id_coche: str, cartel: str) -> bool:
        """
        True si este id_coche no fue visto en los últimos 90 min para esta parada.
        False si es una repetición del mismo vehículo acercándose.

        Los coches sin id (cadena vacía) siempre se marcan como primeros.
        """
        if not id_coche:
            return True  # id desconocido → no podemos deduplicar

        HistoryStorage._limpiar_cache_expirado()

        key = (parada_id, id_coche, cartel)
        ahora = datetime.now()

        if key in _recent_coches:
            return False  # ya visto recientemente

        # Primera vez → registrar en caché
        _recent_coches[key] = ahora
        return True

    # ── API pública ───────────────────────────────────────────────────────────

    def guardar(
        self,
        parada: Parada,
        arribos: List[Arribo],
        origen: str = "parada",
        user_id: Optional[int] = None,
    ) -> None:
        """
        Guarda una consulta completa con todos sus arrivals.

        Args:
            parada:   objeto Parada con cod_sms, descripcion, distrito.
            arribos:  lista de Arribo (puede estar vacía).
            origen:   'parada' | 'ubicacion' | 'favorito' | 'tracking' | 'collector'
            user_id:  int del usuario de Telegram. None para el colector.
        """
        if not config.STORAGE_ENABLED or self._conn is None:
            return

        now = datetime.now(timezone.utc)
        ts = now.isoformat()
        hora_dia = now.hour
        dia_semana = now.weekday()   # 0=lun … 6=dom
        uid_hash = _hash_user_id(user_id) if user_id is not None else None

        try:
            cur = self._conn.execute(
                """
                INSERT INTO consultas
                    (timestamp, parada_id, parada_nombre, distrito, origen, user_id_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ts, str(parada.cod_sms), parada.descripcion,
                 getattr(parada, "distrito", None), origen, uid_hash),
            )
            consulta_id = cur.lastrowid

            self._conn.executemany(
                """
                INSERT INTO arribos_historico (
                    consulta_id, timestamp, hora_dia, dia_semana,
                    parada_id, codigo_linea, numero_linea, cartel,
                    minutos_estimados, distancia_km,
                    es_adaptado, gps_fresco, id_coche, esta_llegando,
                    es_primer_avistamiento
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        consulta_id, ts, hora_dia, dia_semana,
                        str(parada.cod_sms),
                        a.codigo_linea, a.numero_linea, a.cartel,
                        a.minutos, a.distancia_km,
                        int(a.es_adaptado), int(a.gps_fresco),
                        a.id_coche, int(a.esta_llegando),
                        int(self._es_primer_avistamiento(
                            str(parada.cod_sms), a.id_coche, a.cartel
                        )),
                    )
                    for a in arribos
                ],
            )
            self._conn.commit()
            logger.debug(
                "Guardado: parada=%s origen=%s arrivals=%d",
                parada.cod_sms, origen, len(arribos),
            )
        except sqlite3.Error as e:
            logger.error("Error guardando histórico: %s", e)
            try:
                self._conn.rollback()
            except Exception:
                pass

    # ── Context manager ───────────────────────────────────────────────────────

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
