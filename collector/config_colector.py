"""
collector/config_colector.py — Configuración del colector autónomo.

Editá este archivo para cambiar paradas, intervalos o franjas horarias.
"""

# Paradas a monitorear (números de parada SMS)
PARADAS = [
    "5742",   # San Nicolas y Pasco — líneas: 122 VERDE, 122 ROJA, 128 R
    "7881",   # Pellegrini y Constitucion — líneas: 153 R, 153 N, 123, 120
]

# Intervalo dinámico según franja horaria
# Formato: (hora_inicio, hora_fin_inclusive, intervalo_minutos, descripcion)
# La primera franja que coincida con la hora actual gana.
FRANJAS_HORARIAS = [
    (6,  23,  3,  "hora pico — alta frecuencia de servicio"),
    (0,   5, 15,  "madrugada — baja frecuencia de servicio"),
]
