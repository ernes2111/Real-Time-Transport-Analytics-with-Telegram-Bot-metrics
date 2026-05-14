"""
src/models/arribo.py — Modelo de datos para un arribo de colectivo.

Usamos dataclasses nativas de Python para máxima compatibilidad
(sin dependencias externas, funciona en cualquier ARM/Raspberry Pi).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Arribo:
    """
    Representa un colectivo próximo a arribar a una parada.

    Campos principales extraídos del JSON de la API:
        codigoLinea            → codigo_linea
        descripcionLinea       → numero_linea  (ej: "122")
        descripcionCartelBandera → cartel       (ej: "122 ROJA")
        descripcionBandera     → destino        (ej: "CENTENARIO Y SERRANO")
        tiempoRestanteArribo  → tiempo_texto   (ej: "14 min. aprox.")
        tiempoArriboMinutos   → minutos        (ej: 14)
        esAdaptado             → es_adaptado
        identificadorCoche    → id_coche
        distanciaKm           → distancia_km
        minutosDesdeUltimaGPS → minutos_ultima_gps
        parada                 → parada_id
    """
    codigo_linea: str
    numero_linea: str        # descripcionLinea
    cartel: str              # descripcionCartelBandera — lo que aparece en el frente del colectivo
    destino: str             # descripcionBandera
    tiempo_texto: str        # tiempoRestanteArribo
    minutos: int             # tiempoArriboMinutos
    es_adaptado: bool
    id_coche: str            # identificadorCoche
    distancia_km: float
    minutos_ultima_gps: int  # frescura del GPS
    parada_id: str
    descripcion_corta: Optional[str] = None  # descripcionCortaBandera (ej: "ROJO")

    @classmethod
    def desde_dict(cls, d: dict) -> "Arribo":
        """Crea un Arribo a partir del dict raw que devuelve la API."""
        return cls(
            codigo_linea=str(d.get("codigoLinea", "")),
            numero_linea=str(d.get("descripcionLinea", "")),
            cartel=str(d.get("descripcionCartelBandera", "")),
            destino=str(d.get("descripcionBandera", "")),
            tiempo_texto=str(d.get("tiempoRestanteArribo", "")),
            minutos=int(d.get("tiempoArriboMinutos", 0)),
            es_adaptado=bool(d.get("esAdaptado", False)),
            id_coche=str(d.get("identificadorCoche", "")),
            distancia_km=float(d.get("distanciaKm", 0.0)),
            minutos_ultima_gps=int(d.get("minutosDesdeUltimaGPS", 0)),
            parada_id=str(d.get("parada", "")),
            descripcion_corta=d.get("descripcionCortaBandera"),
        )

    @property
    def esta_llegando(self) -> bool:
        """True si el colectivo está llegando ahora mismo (0 minutos)."""
        return self.minutos == 0

    @property
    def gps_fresco(self) -> bool:
        """True si el GPS del colectivo se actualizó en los últimos 3 minutos."""
        return self.minutos_ultima_gps <= 3
