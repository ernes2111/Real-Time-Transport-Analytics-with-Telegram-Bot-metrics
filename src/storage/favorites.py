"""
src/storage/favorites.py — Almacenamiento de paradas favoritas por usuario.

Cada usuario de Telegram tiene sus propios favoritos aislados (por user_id).
Los datos se guardan en SQLite (mismo archivo que el histórico).

Tabla: favoritos
  - user_id      → ID de Telegram del usuario
  - alias        → nombre amigable ("Casa", "Trabajo")
  - parada_id    → número de parada ("5742")
  - filtro_linea → filtro opcional de línea ("122") o NULL para todas
  - created_at   → timestamp ISO 8601
"""

import csv
import io
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from config import config

logger = logging.getLogger(__name__)


class FavoritesStorage:
    """
    Gestión de favoritos por usuario en SQLite.

    Uso:
        fav = FavoritesStorage()
        fav.agregar(user_id=123, alias="Casa", parada_id="5742", filtro_linea="122")
        mis = fav.listar(user_id=123)
        fav.eliminar(user_id=123, alias="Casa")
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._path = Path(db_path or config.DB_PATH)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        logger.info("FavoritesStorage inicializado en %s", self._path)

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS favoritos (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                alias        TEXT    NOT NULL,
                parada_id    TEXT    NOT NULL,
                filtro_linea TEXT,
                created_at   TEXT    NOT NULL,
                UNIQUE(user_id, alias)
            )
        """)
        self._conn.commit()

    # ── Escritura ─────────────────────────────────────────────────────────────

    def agregar(
        self,
        user_id: int,
        alias: str,
        parada_id: str,
        filtro_linea: Optional[str] = None,
    ) -> bool:
        """
        Guarda o actualiza un favorito.
        Si el alias ya existe para ese usuario, lo sobreescribe.
        """
        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO favoritos
                    (user_id, alias, parada_id, filtro_linea, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    alias.strip(),
                    parada_id.strip(),
                    filtro_linea.strip() if filtro_linea else None,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._conn.commit()
            logger.info("Favorito guardado: user=%s alias=%s parada=%s", user_id, alias, parada_id)
            return True
        except sqlite3.Error as e:
            logger.error("Error al guardar favorito: %s", e)
            return False

    def eliminar(self, user_id: int, alias: str) -> bool:
        """Elimina un favorito por alias. Retorna True si existía."""
        cursor = self._conn.execute(
            "DELETE FROM favoritos WHERE user_id = ? AND alias = ?",
            (user_id, alias.strip()),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ── Lectura ───────────────────────────────────────────────────────────────

    def listar(self, user_id: int) -> List[dict]:
        """Retorna todos los favoritos del usuario, ordenados por fecha de creación."""
        cursor = self._conn.execute(
            "SELECT * FROM favoritos WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def obtener(self, user_id: int, alias: str) -> Optional[dict]:
        """Retorna un favorito por alias, o None si no existe."""
        cursor = self._conn.execute(
            "SELECT * FROM favoritos WHERE user_id = ? AND alias = ?",
            (user_id, alias.strip()),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def contar(self, user_id: int) -> int:
        """Cantidad de favoritos del usuario."""
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM favoritos WHERE user_id = ?",
            (user_id,),
        )
        return cursor.fetchone()[0]

    def existe_alias(self, user_id: int, alias: str) -> bool:
        return self.obtener(user_id, alias) is not None

    # ── Exportación ───────────────────────────────────────────────────────────

    def exportar_csv(self, user_id: int) -> io.BytesIO:
        """
        Genera un archivo CSV con los favoritos del usuario.
        Retorna un BytesIO listo para enviar como documento de Telegram.
        """
        favoritos = self.listar(user_id)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["alias", "parada_id", "filtro_linea", "created_at"])
        for f in favoritos:
            writer.writerow([
                f["alias"],
                f["parada_id"],
                f["filtro_linea"] or "",
                f["created_at"],
            ])
        buffer = io.BytesIO(output.getvalue().encode("utf-8"))
        return buffer

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
