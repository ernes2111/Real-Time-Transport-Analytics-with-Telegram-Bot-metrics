# Roadmap

Mejoras planificadas para el bot de consultas de colectivos de Rosario.

---

## ✅ Implementado

### v0.1–0.2 — Base
- Arquitectura modular en capas (api → models → services → formatters)
- Consulta por número de parada y por GPS
- Distancia del colectivo a la parada
- Formato HTML (reemplazó MarkdownV2)

### v0.3 — Favoritos
- Sistema de favoritos por usuario con persistencia SQLite
- Comandos: `/favorito`, `/mis_paradas`, `/borrar`, `/exportar`
- Botón ⭐ Favoritos en teclado inferior permanente

### v0.4 — Live Tracking
- Seguimiento en tiempo real (edita un mensaje cada 30 seg)
- Alerta push a ≤ 3 min de arribo
- Detención automática a los 10 min o al llegar el colectivo
- Formato compacto optimizado para móvil

### v0.5 — Sistema de Analytics (en curso)
- Base de datos histórica activa (`consultas` + `arribos_historico`)
- Campo `es_primer_avistamiento` para deduplicación por `id_coche`
- Colector autónomo 24hs con intervalo dinámico (3 min diurno / 15 min nocturno)
- Paradas monitoreadas: 5742 y 7881
- Script de inspección `scripts/inspeccionar_db.py`

---

## 🔵 Próximos pasos inmediatos

### Servicios systemd en Raspberry Pi
Cuando se migre el proyecto a la Pi, crear:
- `colectivos-bot.service` — bot de Telegram
- `colectivos-collector.service` — colector autónomo
- `colectivos-dashboard.service` — dashboard Streamlit (cuando esté listo)

### Dashboard de Analytics (Fase 4 — en ~2–4 semanas)
Una vez acumulados suficientes datos, construir el dashboard Streamlit en `dashboard/`:
- **KPIs**: arrivals totales, usuarios únicos, % GPS confiable, % flota accesible
- **Análisis por línea**: espera promedio, mediana, mín/máx (filtrando primeros avistamientos)
- **Análisis temporal**: espera por hora del día, heatmap día × hora
- **Frecuencia del servicio**: intervalo promedio entre colectivos por línea
- **Seguimiento de vehículos**: análisis de `id_coche` entre consultas
- **Confiabilidad GPS**: % de GPS fresco por línea
- Filtros: período (24hs / 7d / 30d / todo), línea, parada, día de semana

**Deploy:** Streamlit en puerto `:8501` con nginx reverse proxy → `ernestollampa.com.ar/dashboard`

### Integrar histórico en el tracking
Llamar a `HistoryStorage.guardar()` también desde el job periódico del live tracking, con `origen='tracking'`.

---

## 🟡 Media prioridad

### Manejo global de errores
Agregar `error_handler` en `telegram_bot.py` para capturar excepciones no manejadas y loggearlas.

### Rate limiting por usuario
Limitar a N consultas por minuto con `cachetools` para evitar abuso.

### Umbral de alerta configurable
La alerta push está fija en ≤ 3 min. Permitir configurarlo:
`/favorito 5742 Casa 122 5` (alertar a 5 min).

### Configuración de duración del tracking
Actualmente fijo en 10 min:
`/seguir 5742 122 VERDE 15` (15 minutos).

### Modo silencioso / avisos de servicio
Avisar cuando el servicio tiene baja frecuencia (madrugada).

### Comando `/lineas <parada>`
Mostrar qué líneas pasan por una parada sin consultar los tiempos de arribo.

---

## 🟢 Largo plazo / Portfolio

### Análisis narrativo (Jupyter Notebook)
`notebooks/exploracion.ipynb` — EDA con storytelling sobre los datos recolectados:
- ¿A qué hora hay más demanda?
- ¿Cuál es la línea más puntual?
- ¿Son confiables las estimaciones del GPS?

### Tests automatizados
- `test_client.py` — mockear requests y validar manejo de errores
- `test_models.py` — validar parsing de dicts crudos de la API
- `test_service.py` — filtros y lógica de negocio
- `test_formatter.py` — output HTML

### Detección de desvíos activos
La API parece exponer información de desvíos. Incorporar aviso al usuario si su línea tiene desvío activo.

### Comando `/mapa`
Botón inline que abre Google Maps con la ubicación exacta de la parada.

### Soporte multi-ciudad
Parametrizar la URL base de la API para otras ciudades con el mismo sistema Cuándo Llega.

---

## Notas de arquitectura

- **Raspberry Pi Zero 2W**: 512 MB RAM. Evitar Pydantic v2, pandas en el bot, o librerías con extensiones C sin wheels ARM. El bot + colector consumen ~80 MB en total.
- **SQLite + WAL mode**: suficiente para el volumen esperado (~200K records/mes). WAL permite escrituras concurrentes desde bot y colector.
- **El campo `id_coche`** es clave para análisis de exactitud: si aparece el mismo coche en consultas consecutivas, se puede calcular cuánto tardó realmente vs. lo estimado.
- **Streamlit** consume ~150 MB RAM extra. Correrlo como servicio separado en la Pi Zero puede ser ajustado. Si hay problemas de memoria, considerar correrlo solo bajo demanda o en otra máquina.
