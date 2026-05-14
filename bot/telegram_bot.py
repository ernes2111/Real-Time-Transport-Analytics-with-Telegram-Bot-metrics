"""
bot/telegram_bot.py — Bot de Telegram para consulta de colectivos de Rosario.

Comandos:
    /start, /ayuda, /parada <N>
    /favorito <N> <alias> [linea], /mis_paradas, /borrar <alias>, /exportar
    (Live tracking activado con botones inline bajo cada resultado)

parse_mode="HTML". JobQueue activo para live tracking.
"""

import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import telegram.error

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from src.services.consulta_service import ConsultaService
from src.api.client import APIError, ParadaNoEncontrada, UbicacionNoSoportada
from src.storage.favorites import FavoritesStorage
from src.storage.history import HistoryStorage
from src.formatters.text_formatter import (
    formato_telegram,
    formato_tracking,
    formato_sin_paradas,
    formato_error_conexion,
    formato_ubicacion_no_soportada,
    formato_paradas_cercanas,
    formato_lista_favoritos,
)

# ── Logging ───────────────────────────────────────────────────────────────────

def _setup_logging() -> None:
    log_path = Path(config.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.handlers.RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO), handlers=[fh, ch])

logger = logging.getLogger(__name__)

# Instancias globales de storage
_favorites = FavoritesStorage()
_history = HistoryStorage()

# Duración máxima del tracking en segundos
TRACKING_DURACION = 600  # 10 minutos
# Umbral de alerta (minutos)
TRACKING_ALERTA_MIN = 3

# ── Helpers de UI ─────────────────────────────────────────────────────────────

def _teclado_principal() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📍 Usar mi ubicación", request_location=True)],
            [KeyboardButton("⭐ Favoritos")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def _teclado_favoritos_inline(favoritos: list) -> InlineKeyboardMarkup:
    botones = []
    fila = []
    for f in favoritos:
        filtro = f["filtro_linea"] or ""
        fila.append(InlineKeyboardButton(f"🚏 {f['alias']}", callback_data=f"fav:{f['parada_id']}:{filtro}"))
        if len(fila) == 2:
            botones.append(fila)
            fila = []
    if fila:
        botones.append(fila)
    return InlineKeyboardMarkup(botones)


def _botones_seguir(resultado, parada_id: str) -> InlineKeyboardMarkup:
    """Botones 'Seguir línea X' bajo cada resultado de consulta."""
    vistas = []
    for a in resultado.arribos:
        if a.cartel not in vistas:
            vistas.append(a.cartel)
        if len(vistas) >= 4:
            break
    filas = []
    fila = []
    for linea in vistas:
        cb = f"seguir:{parada_id}:{linea}"
        fila.append(InlineKeyboardButton(f"🔄 {linea}", callback_data=cb))
        if len(fila) == 2:
            filas.append(fila)
            fila = []
    if fila:
        filas.append(fila)
    return InlineKeyboardMarkup(filas) if filas else None


def _boton_detener(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⏹ Detener seguimiento", callback_data=f"parar:{user_id}")]])


def _hora_actual() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── Handlers de comandos ──────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    nombre = update.effective_user.first_name or "viajero"
    texto = (
        f"👋 ¡Hola, <b>{nombre}</b>!\n\n"
        "Soy el bot de colectivos de <b>Rosario</b> 🚌\n\n"
        "Podés consultarme de estas formas:\n\n"
        "🔢 <b>Por número de parada:</b>\n"
        "Enviame el número directamente (ej: <code>5742</code>) o usá <code>/parada 5742</code>\n\n"
        "📍 <b>Por tu ubicación:</b>\n"
        "Compartí tu ubicación con el botón de abajo.\n\n"
        "🔄 <b>Live tracking:</b>\n"
        "Después de cada consulta aparecen botones para seguir una línea en tiempo real.\n\n"
        "🔖 <b>Favoritos:</b>\n"
        "Guardá tus paradas con <code>/favorito 5742 Casa</code>\n\n"
        "Escribí <code>/ayuda</code> para ver todos los comandos."
    )
    await update.message.reply_text(texto, parse_mode="HTML", reply_markup=_teclado_principal())


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto = (
        "🛠️ <b>Comandos disponibles</b>\n\n"
        "<b>Consultas</b>\n"
        "<code>/parada 5742</code> — consulta la parada 5742\n"
        "Enviar el número directamente también funciona: <code>5742</code>\n\n"
        "<b>Live tracking</b>\n"
        "Después de cada consulta, tocá <code>🔄 [Línea]</code> para seguirla en tiempo real.\n"
        "Se actualiza cada 30 seg · te avisa cuando falta ≤ 3 min · para solo a los 10 min.\n\n"
        "<b>Favoritos</b>\n"
        "<code>/favorito 5742 Casa</code> — guarda parada 5742 como \"Casa\"\n"
        "<code>/favorito 5742 Casa 122</code> — igual, filtrando solo línea 122\n"
        "<code>/mis_paradas</code> — lista y consulta tus favoritos\n"
        "<code>/borrar Casa</code> — elimina el favorito \"Casa\"\n"
        "<code>/exportar</code> — descarga tus favoritos en CSV\n\n"
        "<b>Otros</b>\n"
        "<code>/start</code> — bienvenida\n"
        "<code>/ayuda</code> — este mensaje"
    )
    await update.message.reply_text(texto, parse_mode="HTML")


async def cmd_parada(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "❓ Indicá el número de parada.\nEjemplo: <code>/parada 5742</code>", parse_mode="HTML"
        )
        return
    await _responder_parada(update, context, parada_id=context.args[0])


async def cmd_favorito(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    if len(args) < 2 or not args[0].isdigit():
        await update.message.reply_text(
            "❓ Formato incorrecto. Usá:\n"
            "<code>/favorito 5742 Casa</code>  — todas las líneas\n"
            "<code>/favorito 5742 Casa 122</code>  — solo la línea 122",
            parse_mode="HTML",
        )
        return
    parada_id, alias = args[0], args[1]
    filtro_linea = args[2] if len(args) >= 3 else None
    user_id = update.effective_user.id

    es_nuevo = not _favorites.existe_alias(user_id, alias)
    if es_nuevo and _favorites.contar(user_id) >= config.FAVORITOS_MAX:
        await update.message.reply_text(
            f"⚠️ Límite de <b>{config.FAVORITOS_MAX} favoritos</b> alcanzado.\n"
            "Borrá uno con <code>/borrar &lt;alias&gt;</code>.",
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(f"🔍 Verificando parada <code>{parada_id}</code>...", parse_mode="HTML")
    try:
        with ConsultaService() as service:
            service.consultar_parada(parada_id)
    except ParadaNoEncontrada:
        await update.message.reply_text(f"❌ La parada <code>{parada_id}</code> no existe.", parse_mode="HTML")
        return
    except APIError:
        await update.message.reply_text(formato_error_conexion(), parse_mode="HTML")
        return

    era_existente = _favorites.existe_alias(user_id, alias)
    _favorites.agregar(user_id, alias, parada_id, filtro_linea)
    detalle = f"Parada <code>{parada_id}</code>" + (f", solo línea <code>{filtro_linea}</code>" if filtro_linea else ", todas las líneas")
    accion = "Actualicé" if era_existente else "Guardé"
    await update.message.reply_text(
        f"✅ <b>{accion} \"{alias}\"</b>\n{detalle}\n\nConsultalo con <code>/mis_paradas</code>.",
        parse_mode="HTML",
    )


async def cmd_mis_paradas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    favoritos = _favorites.listar(user_id)
    texto = formato_lista_favoritos(favoritos)
    kb = _teclado_favoritos_inline(favoritos) if favoritos else None
    await update.message.reply_text(texto, parse_mode="HTML", reply_markup=kb)


async def cmd_borrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("❓ Indicá el alias.\nEjemplo: <code>/borrar Casa</code>", parse_mode="HTML")
        return
    alias = " ".join(context.args)
    user_id = update.effective_user.id
    if _favorites.eliminar(user_id, alias):
        await update.message.reply_text(f"🗑️ Eliminé el favorito <b>\"{alias}\"</b>.", parse_mode="HTML")
    else:
        favs = _favorites.listar(user_id)
        aliases = ", ".join(f"<b>{f['alias']}</b>" for f in favs) or "ninguno"
        await update.message.reply_text(
            f"❌ No encontré <b>\"{alias}\"</b>.\nTus favoritos: {aliases}", parse_mode="HTML"
        )


async def cmd_exportar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    favoritos = _favorites.listar(user_id)
    if not favoritos:
        await update.message.reply_text(
            "🔖 No tenés favoritos guardados.\nUsá <code>/favorito 5742 Casa</code>", parse_mode="HTML"
        )
        return
    buffer = _favorites.exportar_csv(user_id)
    await update.message.reply_document(
        document=buffer, filename=f"favoritos_{user_id}.csv",
        caption=f"📤 {len(favoritos)} favorito(s) exportados.",
    )


# ── Handlers de mensajes ──────────────────────────────────────────────────────

async def msg_numero(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _responder_parada(update, context, parada_id=update.message.text.strip())


async def msg_boton_favoritos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_mis_paradas(update, context)


async def msg_ubicacion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    location = update.message.location
    lat, lon = location.latitude, location.longitude
    logger.info("Usuario %s envió ubicación: lat=%.6f, lon=%.6f", update.effective_user.id, lat, lon)

    await update.message.reply_text("📍 Buscando paradas cercanas...")

    try:
        with ConsultaService() as service:
            paradas = service.buscar_paradas_cercanas(lat, lon)
            await update.message.reply_text(formato_paradas_cercanas(paradas), parse_mode="HTML")
            mas_cercana = paradas[0]
            resultado = service.consultar_parada(mas_cercana.cod_sms)

        # Guardar en histórico (origen ubicacion)
        _history.guardar(
            parada=resultado.parada,
            arribos=resultado.arribos,
            origen="ubicacion",
            user_id=update.effective_user.id,
        )

        botones = _botones_seguir(resultado, str(mas_cercana.cod_sms))
        await update.message.reply_text(formato_telegram(resultado), parse_mode="HTML", reply_markup=botones)

    except UbicacionNoSoportada:
        await update.message.reply_text(formato_ubicacion_no_soportada(), parse_mode="HTML")
    except (ParadaNoEncontrada, APIError) as e:
        logger.error("Error desde ubicación: %s", e)
        await update.message.reply_text(formato_error_conexion(), parse_mode="HTML")


# ── Callbacks inline ──────────────────────────────────────────────────────────

async def callback_favorito(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        _, parada_id, filtro_linea = query.data.split(":", 2)
    except ValueError:
        return
    filtro = filtro_linea if filtro_linea else None
    logger.info("Favorito: parada=%s filtro=%s", parada_id, filtro)
    try:
        with ConsultaService() as service:
            resultado = service.consultar_parada(parada_id)
            if filtro:
                resultado = service.filtrar_por_linea(resultado, filtro)
    # Guardar en histórico (origen favorito)
        _history.guardar(
            parada=resultado.parada,
            arribos=resultado.arribos,
            origen="favorito",
            user_id=update.effective_user.id,
        )
        botones = _botones_seguir(resultado, parada_id)
        await query.message.reply_text(formato_telegram(resultado), parse_mode="HTML", reply_markup=botones)
    except ParadaNoEncontrada:
        await query.message.reply_text(formato_sin_paradas(parada_id), parse_mode="HTML")
    except APIError as e:
        logger.error("Error callback favorito: %s", e)
        await query.message.reply_text(formato_error_conexion(), parse_mode="HTML")


async def callback_seguir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inicia el live tracking de una línea en una parada."""
    query = update.callback_query
    await query.answer("🔄 Iniciando seguimiento...")

    try:
        _, parada_id, linea = query.data.split(":", 2)
    except ValueError:
        return

    user_id = update.effective_user.id
    chat_id = query.message.chat_id

    # Cancelar tracking previo si existía
    for job in context.job_queue.get_jobs_by_name(f"tracking_{user_id}"):
        job.schedule_removal()

    # Consulta inicial filtrada
    try:
        with ConsultaService() as service:
            resultado_completo = service.consultar_parada(parada_id)
            resultado = service.filtrar_por_linea(resultado_completo, linea)
    except (ParadaNoEncontrada, APIError) as e:
        logger.error("Error iniciando tracking: %s", e)
        await query.message.reply_text(formato_error_conexion(), parse_mode="HTML")
        return

    # Enviar el mensaje de tracking inicial
    texto = formato_tracking(
        resultado, linea, parada_id,
        hora=_hora_actual(),
        segundos_restantes=TRACKING_DURACION,
    )
    tracking_msg = await query.message.reply_text(
        texto, parse_mode="HTML",
        reply_markup=_boton_detener(user_id),
    )

    logger.info("Tracking iniciado: user=%s parada=%s linea=%s", user_id, parada_id, linea)

    # Programar el job periódico
    context.job_queue.run_repeating(
        _tracking_job,
        interval=30,
        first=30,
        data={
            "chat_id": chat_id,
            "message_id": tracking_msg.message_id,
            "parada_id": parada_id,
            "linea": linea,
            "user_id": user_id,
            "start_time": datetime.now(timezone.utc),
            "alert_sent": False,
        },
        name=f"tracking_{user_id}",
        chat_id=chat_id,
        user_id=user_id,
    )


async def callback_parar_seguir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detiene el live tracking manualmente."""
    query = update.callback_query
    try:
        _, uid_str = query.data.split(":", 1)
    except ValueError:
        await query.answer()
        return

    if str(update.effective_user.id) != uid_str:
        await query.answer("No podés detener el seguimiento de otro usuario.", show_alert=True)
        return

    for job in context.job_queue.get_jobs_by_name(f"tracking_{uid_str}"):
        job.schedule_removal()

    await query.answer("⏹ Seguimiento detenido.")
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except telegram.error.BadRequest:
        pass
    logger.info("Tracking detenido manualmente: user=%s", uid_str)


# ── Job de tracking ───────────────────────────────────────────────────────────

async def _tracking_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job periódico que actualiza el mensaje de live tracking cada 30 segundos."""
    data = context.job.data
    chat_id = data["chat_id"]
    message_id = data["message_id"]
    parada_id = data["parada_id"]
    linea = data["linea"]
    user_id = data["user_id"]
    start_time: datetime = data["start_time"]
    alert_sent: bool = data.get("alert_sent", False)

    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    segundos_restantes = max(0, int(TRACKING_DURACION - elapsed))

    # ── Timeout: detener después de 10 minutos ────────────────────────────────
    if elapsed >= TRACKING_DURACION:
        context.job.schedule_removal()
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=(
                    f"⏹ <b>Seguimiento finalizado</b> · {linea}\n"
                    f"🚏 Parada {parada_id}\n\n"
                    "<i>Tiempo máximo de 10 min alcanzado.</i>"
                ),
                parse_mode="HTML",
            )
        except telegram.error.BadRequest:
            pass
        logger.info("Tracking expirado: user=%s parada=%s linea=%s", user_id, parada_id, linea)
        return

    # ── Consultar API ─────────────────────────────────────────────────────────
    try:
        with ConsultaService() as service:
            resultado_completo = service.consultar_parada(parada_id)
            resultado = service.filtrar_por_linea(resultado_completo, linea)
    except (APIError, Exception) as e:
        logger.warning("Error en tracking job (se reintentará): %s", e)
        return  # silently skip, try again in 30 sec

    hora = _hora_actual()

    # ── Colectivo llegando: notificación final + detener ──────────────────────
    if resultado.tiene_arribos and resultado.arribos[0].esta_llegando:
        context.job.schedule_removal()
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🚨 <b>¡El {linea} está llegando!</b>\n🚏 Parada {parada_id}",
            parse_mode="HTML",
        )
        try:
            texto_final = formato_tracking(resultado, linea, parada_id, hora, 0, finalizado=True)
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=texto_final, parse_mode="HTML",
            )
        except telegram.error.BadRequest:
            pass
        logger.info("Tracking finalizado (llegando): user=%s linea=%s", user_id, linea)
        return

    # ── Alerta de proximidad ≤ 3 min (solo una vez) ───────────────────────────
    if resultado.tiene_arribos and not alert_sent:
        primer = resultado.arribos[0]
        if primer.minutos <= TRACKING_ALERTA_MIN:
            data["alert_sent"] = True
            from src.formatters.text_formatter import _distancia_texto, _limpiar_tiempo
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🔔 <b>¡{linea} a {_limpiar_tiempo(primer.tiempo_texto)}!</b>\n"
                    f"🚏 Parada {parada_id} · {_distancia_texto(primer.distancia_km)}"
                ),
                parse_mode="HTML",
            )
            logger.info("Alerta de proximidad enviada: user=%s linea=%s min=%s", user_id, linea, primer.minutos)

    # ── Editar mensaje con datos actualizados ─────────────────────────────────
    texto = formato_tracking(resultado, linea, parada_id, hora, segundos_restantes)
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=texto, parse_mode="HTML",
            reply_markup=_boton_detener(user_id),
        )
    except telegram.error.BadRequest as e:
        if "not modified" not in str(e).lower():
            logger.warning("Error editando tracking message: %s", e)


# ── Función interna de consulta ───────────────────────────────────────────────

async def _responder_parada(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    parada_id: str,
    filtro_linea: str = None,
    origen: str = "parada",
) -> None:
    user_id = update.effective_user.id
    logger.info("Usuario %s consulta parada: %s", user_id, parada_id)
    try:
        with ConsultaService() as service:
            resultado = service.consultar_parada(parada_id)
            if filtro_linea:
                resultado = service.filtrar_por_linea(resultado, filtro_linea)
        texto = formato_telegram(resultado)
        botones = _botones_seguir(resultado, parada_id)
        # Guardar en histórico
        _history.guardar(
            parada=resultado.parada,
            arribos=resultado.arribos,
            origen=origen,
            user_id=user_id,
        )
    except ParadaNoEncontrada:
        logger.warning("Parada no encontrada: %s", parada_id)
        texto, botones = formato_sin_paradas(parada_id), None
    except APIError as e:
        logger.error("Error API parada %s: %s", parada_id, e)
        texto, botones = formato_error_conexion(), None

    await update.message.reply_text(texto, parse_mode="HTML", reply_markup=botones)


# ── Punto de entrada ──────────────────────────────────────────────────────────

def main() -> None:
    _setup_logging()
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN no configurado.")
        sys.exit(1)

    logger.info("Iniciando bot de colectivos de Rosario...")
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler(["ayuda", "help"], cmd_ayuda))
    app.add_handler(CommandHandler("parada", cmd_parada))
    app.add_handler(CommandHandler("favorito", cmd_favorito))
    app.add_handler(CommandHandler("mis_paradas", cmd_mis_paradas))
    app.add_handler(CommandHandler("borrar", cmd_borrar))
    app.add_handler(CommandHandler("exportar", cmd_exportar))

    # Callbacks inline (orden importa: más específico primero)
    app.add_handler(CallbackQueryHandler(callback_seguir,      pattern=r"^seguir:"))
    app.add_handler(CallbackQueryHandler(callback_parar_seguir, pattern=r"^parar:"))
    app.add_handler(CallbackQueryHandler(callback_favorito,    pattern=r"^fav:"))

    # Mensajes
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^\d+$"), msg_numero))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^⭐ Favoritos$"), msg_boton_favoritos))
    app.add_handler(MessageHandler(filters.LOCATION, msg_ubicacion))

    logger.info("Bot corriendo. Presioná Ctrl+C para detener.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
