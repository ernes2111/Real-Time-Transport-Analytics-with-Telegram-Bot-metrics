# Project Overview — Bot de Analítica de Transporte Urbano

> Documento técnico de referencia para presentar el proyecto en entrevistas de trabajo.
> Cubre arquitectura, decisiones técnicas, tecnologías y posibles preguntas.

---

## Descripción en una oración

> Sistema end-to-end de recolección, almacenamiento y análisis de datos de transporte público urbano, implementado como un bot de Telegram con un pipeline de datos automatizado y un dashboard de métricas en tiempo real.

---

## El problema que resuelve

La app oficial de colectivos de Rosario muestra los tiempos de arribo en tiempo real, pero **no guarda ningún historial**. Eso significa que no hay datos disponibles para responder preguntas como:

- ¿A qué hora el 122 VERDE tarda menos en llegar?
- ¿Qué tan frecuente es realmente el servicio?
- ¿Es confiable el GPS de los colectivos?
- ¿Cuál es la línea más puntual?

Este proyecto resuelve ese problema construyendo **el pipeline de datos desde cero**: capturando, almacenando y analizando los datos que la app oficial no conserva.

---

## Arquitectura general

```
┌─────────────────────────────────────────────────────────┐
│                  Raspberry Pi Zero 2W                   │
│                                                         │
│  ┌──────────────────┐    ┌───────────────────────────┐  │
│  │  Bot de Telegram │    │   Colector Autónomo       │  │
│  │                  │    │                           │  │
│  │  Usuario consulta│    │  Cada 3 min (día)         │  │
│  │  → API externa   │    │  Cada 15 min (madrugada)  │  │
│  │  → formatea resp.│    │  → API externa            │  │
│  │  → responde user │    │  → guarda en DB           │  │
│  └────────┬─────────┘    └────────────┬──────────────┘  │
│           │                           │                  │
│           └──────────┬────────────────┘                  │
│                      ▼                                   │
│               data/bot.db (SQLite)                       │
│           consultas + arribos_historico                  │
│                      │                                   │
│           ┌──────────▼──────────────┐                    │
│           │  Dashboard Streamlit    │                    │
│           │  (próximamente)         │                    │
│           └─────────────────────────┘                    │
│                      │                                   │
│                    nginx                                 │
└──────────────────────┼──────────────────────────────────┘
                       │ Cloudflare Tunnel
                       ▼
              ernestollampa.com.ar/dashboard
```

---

## Stack tecnológico — justificación de cada elección

### Python 3.9
- Compatibilidad garantizada con Raspberry Pi Zero 2W (ARM)
- Sin dependencias nativas que requieran compilación
- `dataclasses` nativas (sin Pydantic) → menos overhead de memoria

### python-telegram-bot v20+ (async)
- Framework async basado en `asyncio` — maneja múltiples usuarios simultáneos sin threads
- `JobQueue` integrado (via APScheduler) para los jobs periódicos del live tracking

### APScheduler
- Permite ejecutar funciones en background mientras el bot sigue respondiendo
- Usado para el job de tracking cada 30 segundos por usuario activo

### SQLite con WAL mode
- **WAL** (Write-Ahead Logging): permite lecturas y escrituras simultáneas desde dos procesos (bot + colector) sin bloqueos
- Sin servidor, sin configuración, ideal para dispositivos embebidos
- Suficiente para el volumen esperado (~200K records/mes)

### tenacity (reintentos HTTP)
- La API de Cuándo Llega no tiene SLA garantizado
- Reintentos automáticos con backoff exponencial → el bot no falla si la API tiene un pico de latencia

### requests (en lugar de httpx/aiohttp)
- La API es consultada en el `ConsultaService`, no directamente en el handler async
- El `ConsultaService` corre en un thread separado (context manager), compatible con async bot

---

## Diseño de la base de datos

### Por qué 2 tablas en lugar de 1

La primera versión del módulo de storage guardaba la consulta como un evento único con las líneas en un campo JSON:
```sql
consultas(id, timestamp, parada_id, lineas_json)
-- lineas_json = '["122 ROJA", "128 R"]'
```

**Problema**: ese diseño es imposible de analizar. No podés calcular tiempos promedio, hacer joins, ni filtrar por línea eficientemente desde un campo JSON.

**Solución**: normalización. Una fila por arribo, con todos los atributos del colectivo:
```sql
consultas(id, timestamp, parada_id, origen, user_id_hash)
arribos_historico(id, consulta_id, cartel, minutos_estimados, id_coche, ...)
```

Esto permite queries SQL directos como:
```sql
SELECT cartel, AVG(minutos_estimados) as espera_prom
FROM arribos_historico
WHERE es_primer_avistamiento = 1 AND minutos_estimados > 0
GROUP BY cartel
ORDER BY espera_prom;
```

### El problema de la duplicación y cómo se resuelve

Cuando el colector consulta cada 3 minutos, el mismo colectivo físico aparece múltiples veces mientras se acerca:
```
22:00 → coche 4919 a 10 min
22:03 → coche 4919 a  7 min  ← mismo bus
22:06 → coche 4919 a  4 min  ← mismo bus
```

Calcular el promedio de `minutos_estimados` sin considerar esto sesgaría los resultados.

**Solución**: campo `es_primer_avistamiento` (0/1) usando `id_coche` como identificador del vehículo físico.

**Implementación**: caché en memoria con TTL de 90 minutos. Antes de insertar cada arribo, se consulta si el `(parada_id, id_coche, cartel)` fue visto recientemente. Si sí → `es_primer_avistamiento=0`. Si no → `=1` y se registra en caché.

**Por qué no descartar los duplicados**: los datos repetidos son útiles para analizar la evolución de las estimaciones (¿son lineales? ¿el GPS es preciso?). Se guardan y se filtra en la query de análisis con `WHERE es_primer_avistamiento=1`.

### Índices

```sql
-- Los más importantes para el dashboard:
CREATE INDEX idx_ah_timestamp ON arribos_historico(timestamp);
CREATE INDEX idx_ah_hora_dia  ON arribos_historico(hora_dia);  -- para heatmaps
CREATE INDEX idx_ah_cartel    ON arribos_historico(cartel);    -- group by linea
CREATE INDEX idx_ah_primer    ON arribos_historico(es_primer_avistamiento);
```

---

## El colector autónomo — decisión de diseño

### Por qué un proceso separado al bot

El bot solo genera datos cuando un usuario hace una consulta. Si nadie usa el bot de 14:00 a 17:00, ese período no tiene datos. Para el análisis estadístico necesitamos **datos continuos e independientes del comportamiento del usuario**.

### Intervalo dinámico

En lugar de un intervalo fijo, el colector adapta la frecuencia según la hora:
- **06:00–23:59**: cada 3 minutos → ~480 consultas/día en hora pico
- **00:00–05:59**: cada 15 minutos → madrugada, servicio menos frecuente

La función `intervalo_actual()` recalcula la franja antes de cada sleep, por lo que la transición es automática.

### Volumen de datos en un mes

| Período | Consultas (2 paradas) | Arrivals estimados |
|---------|----------------------|--------------------|
| Por día | ~848 | ~5.900 |
| Por semana | ~5.936 | ~41.000 |
| Por mes | ~25.440 | ~176.000 |

---

## Pipeline de datos completo

```
API de Cuándo Llega Rosario
         │
         │ HTTP GET (tenacity, reintentos)
         ▼
   BusAPIClient.get()
         │
         │ dict raw de la API
         ▼
   Arribo.desde_dict()    ← parsing + validación de tipos
   Parada.desde_dict()
         │
         │ objetos tipados
         ▼
   ConsultaService        ← lógica de negocio, filtros
         │
         ├──► text_formatter  → mensaje HTML para Telegram
         │
         └──► HistoryStorage  → SQLite (consultas + arribos_historico)
                    │
                    ▼
              data/bot.db
                    │
              (próximamente)
                    ▼
         Dashboard Streamlit (pandas + plotly)
```

---

## Decisiones de privacidad

- **user_id de Telegram**: se almacena hasheado (SHA-256 truncado a 16 chars). No hay forma de revertir el hash al ID original.
- **Qué se guarda del usuario**: solo el hash del ID y la parada consultada. Sin nombre, sin número de teléfono, sin historial de mensajes.
- **El colector**: usa `user_id_hash=NULL` ya que no es una consulta humana.

---

## Métricas del dashboard (diseño)

El dashboard tendrá filtros globales (período: 24hs / 7d / 30d / todo) y mostrará:

| Sección | Métricas |
|---------|---------|
| KPIs | Arrivals totales, usuarios únicos, % GPS confiable, % flota accesible |
| Por línea | Espera promedio (primer avistamiento), mediana, min/max, nº de registros |
| Temporal | Espera por hora del día, heatmap día×hora |
| Frecuencia | Intervalo promedio entre colectivos por línea |
| Vehículos | Análisis de `id_coche`: seguimiento de buses individuales |
| Confiabilidad | % GPS fresco por línea, histograma de tiempos |

---

## Posibles preguntas en entrevista

### ¿Por qué SQLite y no PostgreSQL/MySQL?

SQLite es ideal para este caso porque:
1. La Raspberry Pi Zero 2W tiene 512 MB de RAM — un servidor de base de datos consumiría ~100 MB extra
2. El volumen de datos (~200K records/mes) está bien dentro de los límites de SQLite
3. WAL mode resuelve el problema de concurrencia entre el bot y el colector
4. Sin configuración, sin servidor, sin mantenimiento

Si el proyecto escalara a múltiples ciudades o usuarios (>10K/día), migrar a PostgreSQL sería el paso natural. El código del `HistoryStorage` está diseñado para facilitar esa migración (todo el SQL está centralizado).

### ¿Cómo manejas la concurrencia entre el bot y el colector?

Con `PRAGMA journal_mode=WAL`. En WAL mode, múltiples procesos pueden leer simultáneamente y un proceso puede escribir sin bloquear los lectores. El bot y el colector escritores no se pisan porque sus ventanas de escritura son cortas (< 100 ms cada vez).

### ¿Los datos son reales o estimados?

Los datos son **tiempos de arribo estimados** en el momento de la consulta, no tiempos reales. La API de Cuándo Llega calcula el tiempo basándose en la posición GPS del colectivo y la distancia a la parada.

Esto hay que declararlo en el análisis. Sin embargo, el campo `id_coche` permite un análisis más sofisticado: si el mismo coche aparece en dos consultas consecutivas con diferentes `minutos_estimados`, se puede calcular la velocidad real de acercamiento y evaluar la exactitud del sistema.

### ¿Qué harías diferente si lo reescribieras?

- Separar el proceso de colección en un microservicio con su propia API REST (FastAPI), para que el bot sea solo un cliente más
- Agregar tests unitarios desde el inicio (mockear la API con `responses` o `pytest-httpx`)
- Usar `asyncio` también para el colector en lugar de `time.sleep` bloqueante

### ¿Cómo garantizás que el colector no sobrecarga la API?

- El intervalo mínimo es 3 minutos, que son 20 requests/hora por parada
- Pausa de 2 segundos entre paradas en cada ciclo
- Manejo de errores con `except APIError`: si la API devuelve error, se loggea y se salta al próximo ciclo sin reintentar agresivamente
- `tenacity` en el cliente HTTP ya incluye backoff exponencial para errores transitorios

### ¿Cómo escalarías el sistema?

**Corto plazo** (más paradas, más líneas):
- Agregar paradas al array `PARADAS` en `config_colector.py`
- Ajustar el intervalo si hace falta

**Mediano plazo** (múltiples ciudades):
- Parametrizar la URL base de la API en `config.py`
- Agregar campo `ciudad` en las tablas

**Largo plazo** (escala de producción):
- Migrar a PostgreSQL + Alembic para migraciones
- Reemplazar `time.sleep` por un scheduler robusto (Celery, APScheduler)
- Separar el ETL en un microservicio independiente
- Agregar monitoring (Prometheus + Grafana)

---

## Habilidades que demuestra este proyecto

| Área | Demostración |
|------|-------------|
| **Ingeniería de datos** | Pipeline ETL completo, diseño de esquema normalizado, índices, WAL mode |
| **Python avanzado** | async/await, dataclasses, context managers, decoradores (tenacity) |
| **SQL** | Queries analíticos, GROUP BY, AVG, índices, PRAGMA, ALTER TABLE idempotente |
| **Arquitectura** | Separación de capas, Single Responsibility, módulos desacoplados |
| **DevOps básico** | Systemd services, nginx reverse proxy, Cloudflare Tunnel, logging con rotación |
| **Resolución de problemas** | Ingeniería inversa de API, deduplicación por id_coche, WAL concurrencia |
| **Pensamiento estadístico** | Diseño de métricas, identificación de sesgos (duplicación), primer avistamiento |
