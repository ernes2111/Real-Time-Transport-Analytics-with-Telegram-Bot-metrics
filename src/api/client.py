"""
src/api/client.py — Cliente HTTP para la API pública de Cuándo Llega Rosario.

Responsabilidades:
  - Ejecutar requests con headers correctos (Referer, User-Agent).
  - Manejar timeouts y reintentos automáticos con tenacity.
  - Lanzar excepciones tipadas para que las capas superiores las manejen.
"""

import logging

import requests
from typing import List, Union
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from config import config
from src.api.endpoints import url_arribos_parada, url_busqueda

logger = logging.getLogger(__name__)


# ── Excepciones propias ────────────────────────────────────────────────────────

class APIError(Exception):
    """Error genérico de la API."""
    pass


class ParadaNoEncontrada(APIError):
    """La parada consultada no existe o no devolvió datos."""
    pass


class UbicacionNoSoportada(APIError):
    """El endpoint de ubicación no está disponible o no retornó parada cercana."""
    pass


# ── Cliente principal ──────────────────────────────────────────────────────────

class BusAPIClient:
    """
    Cliente para la API de Cuándo Llega Rosario.

    Endpoints utilizados:
        - GET /api/public/parada/{id}/arribos   → Colectivos próximos a una parada
        - GET /api/public/search?lat=&lon=      → Paradas cercanas a coordenadas GPS
                                                  (descubierto por ingeniería inversa)
    Uso:
        with BusAPIClient() as client:
            datos = client.get_arribos(5742)
            paradas = client.buscar_paradas_cercanas(-32.9535, -60.6756)
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": config.API_USER_AGENT,
            "Referer": config.API_REFERER,
            "Accept": "application/json",
            "Accept-Language": "es-AR,es;q=0.9",
        })

    # ── Método de request con retry ───────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(requests.Timeout),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str) -> dict:
        """
        Ejecuta un GET y devuelve el JSON parseado.
        Reintenta automáticamente ante timeouts (hasta 3 veces).
        """
        try:
            response = self._session.get(url, timeout=config.API_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            logger.warning("Timeout al consultar %s — reintentando...", url)
            raise
        except requests.HTTPError as e:
            raise APIError(f"Error HTTP {response.status_code} al consultar {url}: {e}") from e
        except requests.ConnectionError as e:
            raise APIError(f"Sin conexión al consultar {url}: {e}") from e
        except ValueError as e:
            raise APIError(f"Respuesta inválida (no es JSON) de {url}: {e}") from e

    # ── Métodos públicos ──────────────────────────────────────────────────────

    def get_arribos(self, parada_id: Union[int, str]) -> dict:
        """
        Consulta los arribos de una parada por su número (cod_sms).

        Returns:
            dict con claves 'arribos', 'parada', 'timestamp'.

        Raises:
            ParadaNoEncontrada: si la API devuelve error o sin datos.
            APIError: cualquier otro error de red o respuesta.
        """
        url = url_arribos_parada(parada_id)
        logger.info("Consultando parada %s...", parada_id)
        data = self._get(url)

        if data.get("error"):
            raise ParadaNoEncontrada(
                f"La parada {parada_id} no fue encontrada o hubo un error en la API: "
                f"{data.get('mensaje', 'sin mensaje')}"
            )
        return data

    def buscar_paradas_cercanas(self, lat: float, lon: float) -> List[dict]:
        """
        Busca las paradas más cercanas a las coordenadas GPS dadas.

        Endpoint real: GET /api/public/search?query=&lat={lat}&lon={lon}
        Descubierto por ingeniería inversa de cuandollegarosario.com

        Returns:
            Lista de dicts ordenada por distancia (metros), cada uno con:
                - cod_sms  (str): número de parada, ej: "5742"
                - nombre   (str): intersección, ej: "SAN NICOLAS y PASCO"
                - distancia (int): metros desde la ubicación enviada
                - lineasTXT (str): líneas en formato HTML

        Raises:
            UbicacionNoSoportada: si la API no devuelve paradas.
            APIError: ante cualquier fallo de red.
        """
        url = url_busqueda(query="", lat=lat, lon=lon)
        logger.info("Buscando paradas cercanas a lat=%.6f, lon=%.6f...", lat, lon)

        data = self._get(url)

        if data.get("error"):
            raise UbicacionNoSoportada(
                f"La API devolvió error al buscar paradas cercanas: {data.get('mensaje')}"
            )

        paradas = data.get("paradas", [])
        if not paradas:
            raise UbicacionNoSoportada(
                "No se encontraron paradas cercanas a esa ubicación."
            )

        logger.info(
            "Se encontraron %d paradas cercanas. La más próxima: %s (%d m)",
            len(paradas),
            paradas[0].get("nombre", "?"),
            paradas[0].get("distancia", 0),
        )
        return paradas

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
