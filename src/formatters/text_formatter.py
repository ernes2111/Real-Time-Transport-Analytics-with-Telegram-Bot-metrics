"""
src/formatters/text_formatter.py — Genera texto formateado para Telegram y consola.

Usa parse_mode="HTML" que es mucho más robusto que MarkdownV2:
  - Solo requiere escapar < > & en el contenido
  - No hay problema con guiones, puntos, paréntesis, etc.
  - Fácil de debuggear visualmente
"""

from typing import List, Union

from src.models.arribo import Arribo
from src.models.parada import Parada
from src.services.consulta_service import ResultadoConsulta


# ── Helpers ───────────────────────────────────────────────────────────────────

def _escape_html(text: str) -> str:
    """Escapa los 3 caracteres especiales de HTML para Telegram."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _emoji_bus(arribo: Arribo) -> str:
    """Elige el emoji según el tipo de colectivo."""
    if arribo.esta_llegando:
        return "🚨"
    return "🚌"


def _distancia_texto(km: float) -> str:
    """Formatea la distancia del colectivo a la parada."""
    if km < 1.0:
        metros = int(km * 1000)
        return f"{metros} m"
    return f"{km:.1f} km"


def _limpiar_tiempo(texto: str) -> str:
    """Simplifica el texto de tiempo de la API para que sea más corto."""
    return (
        texto
        .replace(" aprox.", "")
        .replace("min.", "min")
        .replace("..", "")
        .strip()
    )


def _linea_arribo(arribo: Arribo, html: bool = True) -> str:
    """Formatea una línea de arribo en formato compacto."""
    emoji = _emoji_bus(arribo)
    gps_warn = " ⚠️" if not arribo.gps_fresco else ""
    tiempo = _limpiar_tiempo(arribo.tiempo_texto)
    distancia = _distancia_texto(arribo.distancia_km)

    if html:
        cartel = _escape_html(arribo.cartel)
        return f"{emoji} <b>{cartel}</b> — {_escape_html(tiempo)} · {_escape_html(distancia)}{gps_warn}"
    else:
        return f"  {emoji} {arribo.cartel} — {tiempo} · {distancia}{gps_warn}"


# ── Funciones principales ─────────────────────────────────────────────────────

def formato_telegram(resultado: ResultadoConsulta) -> str:
    """
    Genera el mensaje completo para Telegram con formato HTML.

    Ejemplo de output:
        🚏 <b>Parada 5742</b>
        📍 San Nicolas y Pasco — Distrito OESTE

        🚨 <code>128 R         </code> → <b>Arribando...</b>  [Coche 4199]
        ♿ <code>128 R         </code> → <b>2 min. aprox.</b>  [Coche 3724] ⚠️
    """
    p = resultado.parada
    lineas = []

    # Encabezado compacto en una línea
    lineas.append(f"🚏 <b>Parada {_escape_html(str(p.cod_sms))}</b> · {_escape_html(p.descripcion)}")
    lineas.append("")

    if not resultado.tiene_arribos:
        lineas.append("<i>No hay colectivos próximos para esta parada.</i>")
        return "\n".join(lineas)

    # Arribos
    for arribo in resultado.arribos:
        lineas.append(_linea_arribo(arribo, html=True))

    # Advertencia de GPS desactualizado
    sin_gps_fresco = [a for a in resultado.arribos if not a.gps_fresco]
    if sin_gps_fresco:
        lineas.append("")
        lineas.append("<i>⚠️ Algunos colectivos tienen GPS desactualizado</i>")

    return "\n".join(lineas)


def formato_consola(resultado: ResultadoConsulta) -> str:
    """Genera el mensaje completo para imprimir en consola (sin HTML)."""
    p = resultado.parada
    sep = "─" * 50
    lineas = []

    lineas.append(sep)
    lineas.append(f"🚏 Parada {p.cod_sms} — {p.descripcion}")
    lineas.append(sep)

    if not resultado.tiene_arribos:
        lineas.append("  (Sin colectivos próximos)")
        return "\n".join(lineas)

    for arribo in resultado.arribos:
        lineas.append(_linea_arribo(arribo, html=False))

    lineas.append(sep)
    return "\n".join(lineas)


def formato_sin_paradas(parada_id: Union[int, str]) -> str:
    """Mensaje para Telegram cuando la parada no existe."""
    return (
        f"❌ No encontré la parada <b>{_escape_html(parada_id)}</b>.\n\n"
        "Verificá que el número sea correcto. Podés buscar el número "
        "en la señal física o en la web oficial."
    )


def formato_error_conexion() -> str:
    """Mensaje para Telegram cuando hay error de conexión."""
    return (
        "⚠️ <b>Error de conexión</b>\n\n"
        "No pude comunicarme con el servidor de colectivos. "
        "Intentá de nuevo en unos segundos."
    )


def formato_ubicacion_no_soportada() -> str:
    """Mensaje para Telegram cuando la búsqueda por ubicación no funciona."""
    return (
        "📍 <b>No encontré paradas cercanas</b>\n\n"
        "No pude determinar la parada más cercana a tu ubicación.\n"
        "Por favor, enviame el <b>número de parada</b> directamente."
    )


def formato_paradas_cercanas(paradas: list) -> str:
    """
    Formatea la lista de paradas cercanas para Telegram (HTML).
    Muestra las primeras 5 paradas con su distancia y líneas.
    """
    lineas = []
    lineas.append("📍 <b>Paradas cercanas a tu ubicación</b>")
    lineas.append("")

    for i, p in enumerate(paradas[:5], 1):
        nombre = _escape_html(p.nombre)
        cod = _escape_html(str(p.cod_sms))
        dist = _escape_html(p.distancia_texto)
        lineas.append(f"<b>{i}. {nombre}</b> — {dist}")
        lineas.append(f"   🔢 Parada <code>{cod}</code>")
        for lb in p.lineas_plain[:2]:
            lineas.append(f"   🚌 {_escape_html(lb)}")
        lineas.append("")

    lineas.append("<i>Enviame el número de parada para ver los próximos colectivos.</i>")
    return "\n".join(lineas)


def formato_lista_favoritos(favoritos: List[dict]) -> str:
    """
    Formatea la lista de favoritos del usuario para Telegram (HTML).

    Ejemplo de output:
        🔖 <b>Tus paradas favoritas</b>

        1. <b>Casa</b> — Parada <code>5742</code>, línea <code>122</code>
        2. <b>Trabajo</b> — Parada <code>3271</code>, todas las líneas

        Tocá un botón para consultar al instante.
    """
    if not favoritos:
        return (
            "🔖 <b>No tenés favoritos guardados.</b>\n\n"
            "Guardá una parada con:\n"
            "<code>/favorito 5742 Casa</code>\n"
            "<code>/favorito 5742 Casa 122</code>  (filtrando solo la línea 122)"
        )

    lineas = ["🔖 <b>Tus paradas favoritas</b>", ""]
    for i, f in enumerate(favoritos, 1):
        alias = _escape_html(f["alias"])
        parada = _escape_html(f["parada_id"])
        if f.get("filtro_linea"):
            filtro_txt = f"línea <code>{_escape_html(f['filtro_linea'])}</code>"
        else:
            filtro_txt = "todas las líneas"
        lineas.append(f"{i}. <b>{alias}</b> — Parada <code>{parada}</code>, {filtro_txt}")

    lineas.append("")
    lineas.append("<i>Tocá un botón para consultar al instante:</i>")
    return "\n".join(lineas)


def formato_tracking(
    resultado: ResultadoConsulta,
    linea: str,
    parada_id: str,
    hora: str,
    segundos_restantes: int,
    finalizado: bool = False,
) -> str:
    """
    Formato para el mensaje de live tracking (se edita cada 30 seg).

    Muestra solo los arribos de la línea seguida.
    Incluye timestamp de última actualización y tiempo restante del seguimiento.
    """
    p = resultado.parada
    lineas_msg = []

    if finalizado:
        lineas_msg.append(f"⏹ <b>Seguimiento finalizado · {_escape_html(linea)}</b>")
    else:
        lineas_msg.append(f"🔄 <b>Seguimiento activo · {_escape_html(linea)}</b>")

    lineas_msg.append(f"🚏 <b>Parada {_escape_html(str(parada_id))}</b> · {_escape_html(p.descripcion)}")
    lineas_msg.append("")

    if resultado.tiene_arribos:
        for arribo in resultado.arribos[:5]:
            lineas_msg.append(_linea_arribo(arribo, html=True))
    else:
        lineas_msg.append("<i>No hay próximos colectivos de esta línea en este momento.</i>")

    lineas_msg.append("")
    if finalizado:
        lineas_msg.append(f"<i>🕐 Última actualización: {_escape_html(hora)}</i>")
    else:
        mins = segundos_restantes // 60
        lineas_msg.append(
            f"<i>🕐 {_escape_html(hora)} · quedan {mins} min de seguimiento</i>"
        )

    return "\n".join(lineas_msg)
