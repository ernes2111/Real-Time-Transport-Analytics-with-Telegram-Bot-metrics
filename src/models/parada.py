"""
src/models/parada.py — Modelo de datos para una parada de colectivo.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Parada:
    """
    Representa una parada de colectivo.

    Campos principales extraídos del JSON de la API:
        id_parada   → id interno de la parada
        cod_sms     → número de parada (el que ingresa el usuario, ej: 5742)
        calle1Nombre / calle2Nombre → intersección de calles
        ochava      → esquina (N, S, E, O, NE, NO, SE, SO)
        distrito    → zona de la ciudad (NORTE, SUR, ESTE, OESTE, CENTRO)
        punto_x / punto_y → coordenadas GPS (lat, lon)
    """
    id_parada: int
    cod_sms: int
    calle1: str
    calle2: str
    ochava: Optional[str]
    distrito: Optional[str]
    lat: float      # punto_x en el JSON (eje Y geográfico)
    lon: float      # punto_y en el JSON (eje X geográfico)

    @classmethod
    def desde_dict(cls, d: dict) -> "Parada":
        """Crea una Parada a partir del dict raw que devuelve la API."""
        return cls(
            id_parada=int(d.get("id_parada", 0)),
            cod_sms=int(d.get("cod_sms", 0)),
            calle1=str(d.get("calle1Nombre", "")).title(),
            calle2=str(d.get("calle2Nombre", "")).title(),
            ochava=d.get("ochava"),
            distrito=d.get("distrito"),
            lat=float(d.get("punto_x", 0.0)),
            lon=float(d.get("punto_y", 0.0)),
        )

    @property
    def interseccion(self) -> str:
        """Formato legible de la ubicación: 'San Nicolas y Pasco'."""
        return f"{self.calle1} y {self.calle2}"

    @property
    def descripcion(self) -> str:
        """Descripción completa: 'San Nicolas y Pasco (Distrito OESTE)'."""
        distrito = f" — Distrito {self.distrito}" if self.distrito else ""
        return f"{self.interseccion}{distrito}"
