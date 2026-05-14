# Changelog

Todos los cambios relevantes del proyecto se documentan en este archivo.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).

---

## [0.5.0] — 2026-05-07

### Añadido
- **Sistema de recolección de datos históricos** — almacenamiento persistente en SQLite para análisis estadístico
  - Rediseño completo de `src/storage/history.py` con esquema de **2 tablas normalizadas**:
    - `consultas`: registro de cada evento de consulta (quién, cuándo, desde dónde)
    - `arribos_historico`: un registro por cada colectivo en cada consulta (tabla principal de análisis)
  - Campo `es_primer_avistamiento` — flag que identifica si un vehículo aparece por primera vez en los últimos 90 min para esa parada, usando `id_coche` como identificador único del vehículo físico
  - Caché en memoria (`_recent_coches`) con TTL de 90 minutos para deduplicación eficiente sin queries extra a la DB
  - Sistema de migración incremental `_migrate_db()` — aplica `ALTER TABLE` de forma idempotente sobre DBs ya existentes
  - `user_id_hash` — SHA-256 truncado a 16 chars del user_id de Telegram (privacidad por diseño)
  - Índices optimizados para queries analíticos: `timestamp`, `hora_dia`, `cartel`, `parada_id`, `id_coche`, `es_primer_avistamiento`
  - WAL mode (`PRAGMA journal_mode=WAL`) para concurrencia segura entre bot y colector
- **Colector autónomo** (`collector/colector.py`) — proceso independiente al bot que consulta paradas cada N minutos
  - Configuración externa en `collector/config_colector.py` (paradas y franjas horarias editables)
  - **Intervalo dinámico** según franja horaria:
    - 06:00–23:59 → cada **3 minutos** (hora pico, servicio frecuente)
    - 00:00–05:59 → cada **15 minutos** (madrugada, servicio reducido)
  - Paradas monitoreadas: `5742` (San Nicolas y Pasco) y `7881` (Pellegrini y Constitucion)
  - Logging propio en `logs/colector.log` con rotación
  - Manejo de errores robusto: errores de API se saltean silenciosamente y se reintentan en el próximo ciclo
- **Script `scripts/inspeccionar_db.py`** — resumen del estado de la DB en cualquier momento
  - Muestra: total de consultas por origen, arrivals totales, primeros avistamientos vs. repeticiones, top líneas con espera promedio, período registrado, usuarios únicos del bot

### Cambiado
- `HistoryStorage.guardar()` integrado en el bot en 3 puntos: `_responder_parada`, `msg_ubicacion` y `callback_favorito`
- `origen` distingue la fuente de cada consulta: `'parada'` | `'ubicacion'` | `'favorito'` | `'tracking'` | `'collector'`
- `STORAGE_ENABLED=true` y `DB_PATH=data/bot.db` activados en `.env`
- `requirements.txt` actualizado con `APScheduler` (job-queue del bot)

### Detalles de diseño
- El dato repetido **no se descarta** — se conserva con `es_primer_avistamiento=0` para análisis avanzados (evolución de estimaciones, exactitud del sistema)
- Los análisis de métricas limpias filtran con `WHERE es_primer_avistamiento=1`
- El colector corre en paralelo al bot usando **WAL mode** para evitar locks de SQLite

---

## [0.4.0] — 2026-05-06

### Añadido
- **Live tracking** — seguimiento en tiempo real de una línea en una parada
  - Botones `🔄 [Línea]` inline bajo cada resultado (hasta 4 líneas únicas)
  - Mensaje de tracking editado automáticamente cada **30 segundos**
  - **Alerta push** cuando el colectivo está a ≤ 3 minutos (una sola vez)
  - **Notificación de llegada** `🚨` con detención automática del job
  - **Detención automática** después de 10 minutos (timeout)
  - **Botón ⏹ Detener** inline
  - Si el usuario activa un nuevo tracking, el anterior se cancela
  - Dependencia: `APScheduler` via `python-telegram-bot[job-queue]`
- **Botón ⭐ Favoritos** en el teclado inferior permanente

### Cambiado
- **Formato compacto Opción A**: `🚌 122 VERDE — 8 min · 2.4 km`
- Encabezado en una línea: `🚏 Parada 5742 · San Nicolas y Pasco`
- Tiempo simplificado: "7 min. aprox." → "7 min"
- Eliminado monospace `<code>` — mejora la visualización en iPhone
- `one_time_keyboard=False` — teclado inferior permanente

---

## [0.3.0] — 2026-05-06

### Añadido
- **Sistema de favoritos** con persistencia en SQLite (`data/bot.db`)
  - `/favorito <parada> <alias>` — guarda parada con alias amigable
  - `/favorito <parada> <alias> <linea>` — filtrando solo una línea
  - `/mis_paradas` — lista con teclado inline para consulta instantánea
  - `/borrar <alias>` — elimina un favorito
  - `/exportar` — envía CSV con todos los favoritos del usuario
- Límite de 10 favoritos por usuario (`FAVORITOS_MAX`)
- Validación de parada al guardar (consulta real a la API)
- `src/storage/favorites.py` con clase `FavoritesStorage`
- `CallbackQueryHandler` para botones inline de `/mis_paradas`

---

## [0.2.0] — 2026-04-26

### Añadido
- **Distancia del colectivo** en cada arribo (`647 m` / `3.2 km`)
- **Búsqueda por GPS** — muestra paradas cercanas y auto-consulta la más próxima
- Modelo `ParadaCercana` para resultados de búsqueda

### Cambiado
- **Formato HTML** en lugar de MarkdownV2 — elimina errores de escape
- Colectivos adaptados sin ♿ (campo `es_adaptado` conservado en el modelo)
- Eliminado número de coche del mensaje visible (campo `id_coche` conservado)

### Corregido
- Compatibilidad Python 3.9 (`Union`, `List` de `typing`)
- Error `Message can't be edited` que silenciaba todas las respuestas

---

## [0.1.0] — 2026-04-26

### Añadido
- Estructura base con arquitectura en capas (`api` → `models` → `services` → `formatters`)
- `BusAPIClient` con reintentos automáticos via `tenacity`
- Modelos `Arribo` y `Parada` con `dataclasses` nativas
- `ConsultaService` con soporte para consulta por parada y por GPS
- Bot de Telegram con handlers para `/start`, `/ayuda`, `/parada`, texto numérico y ubicación GPS
- Script CLI `scripts/query_parada.py`
- Logging con rotación de archivos (5 MB, 3 backups)
