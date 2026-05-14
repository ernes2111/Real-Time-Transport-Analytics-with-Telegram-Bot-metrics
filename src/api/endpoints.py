"""
src/api/endpoints.py — Constructores de URLs para la API pública de Cuándo Llega Rosario.

Endpoints descubiertos por ingeniería inversa de https://cuandollegarosario.com/
(análisis de tráfico de red en DevTools)

API disponible:
  - GET /api/public/parada/{id}/arribos  → Arribos de una parada por número
  - GET /api/public/search               → Buscar paradas por texto o por coordenadas GPS
"""

import time
from typing import Optional, Union


# ── Base URL ──────────────────────────────────────────────────────────────────
BASE_URL = "https://app.cuandollegarosario.com/api/public"


def _timestamp_ms() -> int:
    """Timestamp en milisegundos, requerido por la API como parámetro _t."""
    return int(time.time() * 1000)


def url_arribos_parada(parada_id: Union[int, str]) -> str:
    """
    URL para consultar los arribos de una parada por su número (cod_sms).

    Ejemplo:
        url_arribos_parada(5742)
        → '.../parada/5742/arribos?multiparada=true&_t=...'
    """
    return f"{BASE_URL}/parada/{parada_id}/arribos?multiparada=true&_t={_timestamp_ms()}"


def url_busqueda(
    query: str = "",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> str:
    """
    URL para buscar paradas por texto o por coordenadas GPS.

    Descubierto por ingeniería inversa (DevTools Network tab en cuandollegarosario.com).

    Modos de uso:
        1. Por texto:      url_busqueda(query="San Nicolas")
        2. Por ubicación:  url_busqueda(lat=-32.9535, lon=-60.6756)
        3. Combinado:      url_busqueda(query="", lat=-32.9535, lon=-60.6756)
           → Devuelve paradas cercanas ordenadas por distancia (en metros)

    Respuesta de ejemplo:
        {
          "paradas": [
            {
              "cod_sms": "5742",
              "nombre": "SAN NICOLAS y PASCO",
              "distancia": 7,           ← metros desde la ubicación enviada
              "lineasTXT": "<b>122 ROJO</b> (Ribamba y Brasil) | ..."
            },
            ...
          ]
        }
    """
    params = [f"query={query}"]
    if lat is not None and lon is not None:
        params.append(f"lat={lat}")
        params.append(f"lon={lon}")
    return f"{BASE_URL}/search?{'&'.join(params)}"
