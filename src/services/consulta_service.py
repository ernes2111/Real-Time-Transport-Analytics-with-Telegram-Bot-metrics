"""
src/services/consulta_service.py — Lógica de negocio para las consultas de colectivos.

Esta capa orquesta la API, los modelos y los formatters.
No conoce nada de Telegram ni de CLI — es puro dominio de negocio.
"""

import logging
from typing import Optional, List, Union

from src.api.client import BusAPIClient, APIError, ParadaNoEncontrada, UbicacionNoSoportada
from src.models.arribo import Arribo
from src.models.parada import Parada
from src.models.parada_cercana import ParadaCercana

logger = logging.getLogger(__name__)


class ResultadoConsulta:
    """Resultado completo de una consulta a una parada."""

    def __init__(self, parada: Parada, arribos: List[Arribo]):
        self.parada = parada
        self.arribos = arribos

    @property
    def tiene_arribos(self) -> bool:
        return len(self.arribos) > 0

    @property
    def lineas_unicas(self) -> List[str]:
        """Lista de carteles de línea únicos, sin repetir."""
        vistas = set()
        resultado = []
        for a in self.arribos:
            if a.cartel not in vistas:
                vistas.add(a.cartel)
                resultado.append(a.cartel)
        return resultado


class ConsultaService:
    """
    Servicio principal de consultas.

    Uso:
        with ConsultaService() as service:
            # Consulta por número de parada:
            resultado = service.consultar_parada(5742)

            # Consulta por GPS (busca la parada más cercana automáticamente):
            resultado = service.consultar_por_ubicacion(-32.953553, -60.675559)

            # Solo buscar paradas cercanas sin consultar arribos:
            paradas = service.buscar_paradas_cercanas(-32.953553, -60.675559)
    """

    def __init__(self, client: Optional[BusAPIClient] = None) -> None:
        self._client = client or BusAPIClient()

    # ── Consulta por número de parada ─────────────────────────────────────────

    def consultar_parada(self, parada_id: Union[int, str]) -> ResultadoConsulta:
        """
        Consulta los arribos de una parada por su número (cod_sms).

        Args:
            parada_id: número de parada (ej: 5742)

        Returns:
            ResultadoConsulta con parada y lista de Arribo.

        Raises:
            ParadaNoEncontrada: si el número de parada no existe.
            APIError: ante cualquier fallo de red.
        """
        raw = self._client.get_arribos(parada_id)

        # Parsear parada
        parada_list = raw.get("parada", [])
        if not parada_list:
            raise ParadaNoEncontrada(f"No se encontró información de la parada {parada_id}.")
        parada = Parada.desde_dict(parada_list[0])

        # Parsear y ordenar arribos
        arribos_raw = raw.get("arribos", [])
        arribos = [Arribo.desde_dict(a) for a in arribos_raw]
        arribos.sort(key=lambda a: a.minutos)

        logger.info(
            "Parada %s (%s): %d arribo(s) encontrado(s).",
            parada.cod_sms,
            parada.interseccion,
            len(arribos),
        )
        return ResultadoConsulta(parada=parada, arribos=arribos)

    # ── Búsqueda de paradas por GPS ───────────────────────────────────────────

    def buscar_paradas_cercanas(self, lat: float, lon: float) -> List[ParadaCercana]:
        """
        Busca las paradas más cercanas a las coordenadas GPS.
        Devuelve la lista completa ordenada por distancia (metros).

        Útil para mostrar un menú de opciones al usuario.

        Raises:
            UbicacionNoSoportada: si la API no responde o no hay paradas.
        """
        raw_list = self._client.buscar_paradas_cercanas(lat, lon)
        return [ParadaCercana.desde_dict(p) for p in raw_list]

    # ── Consulta por ubicación GPS (flujo completo) ───────────────────────────

    def consultar_por_ubicacion(self, lat: float, lon: float) -> ResultadoConsulta:
        """
        Busca la parada más cercana a las coordenadas y consulta sus arribos.
        Toma automáticamente la primera parada de la lista (la más cercana).

        Args:
            lat: latitud decimal (ej: -32.953553)
            lon: longitud decimal (ej: -60.675559)

        Returns:
            ResultadoConsulta de la parada más cercana.

        Raises:
            UbicacionNoSoportada: si no se puede determinar la parada cercana.
            ParadaNoEncontrada / APIError: heredados de consultar_parada.
        """
        paradas = self.buscar_paradas_cercanas(lat, lon)
        mas_cercana = paradas[0]

        logger.info(
            "Parada más cercana: %s (%s) a %s",
            mas_cercana.cod_sms,
            mas_cercana.nombre,
            mas_cercana.distancia_texto,
        )
        return self.consultar_parada(mas_cercana.cod_sms)

    # ── Filtros útiles ────────────────────────────────────────────────────────

    @staticmethod
    def filtrar_por_linea(resultado: ResultadoConsulta, linea: str) -> ResultadoConsulta:
        """
        Filtra los arribos de un resultado por número de línea.

        Args:
            resultado: ResultadoConsulta completo.
            linea: número de línea a filtrar (ej: "122")

        Returns:
            Nuevo ResultadoConsulta con solo los arribos de esa línea.
        """
        filtrados = [
            a for a in resultado.arribos
            if linea.strip() in a.numero_linea or linea.strip() in a.cartel
        ]
        return ResultadoConsulta(parada=resultado.parada, arribos=filtrados)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
