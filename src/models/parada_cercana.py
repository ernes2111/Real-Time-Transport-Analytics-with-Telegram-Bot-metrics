"""
src/models/parada_cercana.py — Modelo para una parada devuelta por el endpoint de búsqueda.

Distinto al modelo Parada (que viene del endpoint de arribos), este viene del endpoint
/api/public/search y tiene menos campos pero incluye la distancia al usuario.
"""

import re
from dataclasses import dataclass


@dataclass
class ParadaCercana:
    """
    Parada resultado de una búsqueda por ubicación GPS o por texto.

    Campos del JSON de /api/public/search:
        cod_sms   → número de parada (como string en la API)
        nombre    → intersección en mayúsculas, ej: "SAN NICOLAS y PASCO"
        distancia → metros desde la ubicación del usuario
        lineasTXT → líneas en HTML, ej: "<b>122 ROJO</b> (Ribamba y Brasil) | ..."
    """
    cod_sms: int
    nombre: str
    distancia: int          # metros
    lineas_txt: str         # HTML crudo de la API

    @classmethod
    def desde_dict(cls, d: dict) -> "ParadaCercana":
        return cls(
            cod_sms=int(d.get("cod_sms", 0)),
            nombre=str(d.get("nombre", "")).title(),
            distancia=int(d.get("distancia", 0)),
            lineas_txt=str(d.get("lineasTXT", "")),
        )

    @property
    def lineas_plain(self) -> list:
        """
        Extrae las líneas en texto plano desde el HTML de lineasTXT.

        Entrada:  "<b>122 ROJO</b> (Ribamba y Brasil) | <b>128 ROJO</b> (Hospital)"
        Salida:   ["122 ROJO (Ribamba y Brasil)", "128 ROJO (Hospital)"]
        """
        # Eliminar tags HTML
        plain = re.sub(r"<[^>]+>", "", self.lineas_txt)
        # Separar por " | "
        return [l.strip() for l in plain.split("|") if l.strip()]

    @property
    def distancia_texto(self) -> str:
        """Distancia formateada: '7 m' o '1.2 km'."""
        if self.distancia < 1000:
            return f"{self.distancia} m"
        return f"{self.distancia / 1000:.1f} km"
