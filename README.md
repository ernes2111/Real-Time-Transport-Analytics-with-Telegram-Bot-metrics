# 🚌 Bot de Consultas de Colectivos — Rosario

Bot de Telegram para consultar en tiempo real los próximos arribos de colectivos a cualquier parada de Rosario, con sistema de favoritos, seguimiento en vivo y recolección automática de datos para análisis estadístico.

Consume la API pública de [Cuándo Llega Rosario](https://app.cuandollegarosario.com) descubierta por ingeniería inversa.

---

## Funcionalidades

- 🔢 **Consulta por número de parada** — `5742` o `/parada 5742`
- 📍 **Consulta por ubicación GPS** — muestra paradas cercanas y auto-consulta la más próxima
- ⭐ **Favoritos** — guarda paradas con alias y filtros de línea por usuario
- 🔄 **Live tracking** — seguimiento en tiempo real editando un mensaje cada 30 seg
- 🔔 **Alertas push** — notificación proactiva cuando el colectivo está a ≤ 3 minutos
- 📊 **Recolección de datos** — histórico automático de arrivals en SQLite para analítica

---

## Estructura del proyecto

```
bot de consultas v2/
├── bot/
│   └── telegram_bot.py          # Punto de entrada — handlers, tracking, teclado
├── src/
│   ├── api/
│   │   ├── client.py            # Cliente HTTP con reintentos automáticos (tenacity)
│   │   └── endpoints.py         # Constructores de URLs de la API
│   ├── models/
│   │   ├── arribo.py            # Dataclass: colectivo con tiempo, distancia, id_coche
│   │   ├── parada.py            # Dataclass: parada con coordenadas y descripción
│   │   └── parada_cercana.py    # Dataclass: resultado de búsqueda por GPS
│   ├── services/
│   │   └── consulta_service.py  # Lógica de negocio y filtros
│   ├── formatters/
│   │   └── text_formatter.py    # Formato HTML para Telegram (compacto, mobile-first)
│   └── storage/
│       ├── favorites.py         # CRUD de favoritos por usuario (SQLite)
│       └── history.py           # Histórico de arrivals para analítica (SQLite)
├── collector/
│   ├── colector.py              # Proceso autónomo de recolección de datos
│   └── config_colector.py      # Paradas y franjas horarias configurables
├── scripts/
│   ├── query_parada.py          # CLI de prueba sin Telegram
│   └── inspeccionar_db.py       # Resumen del estado de la base de datos
├── data/
│   └── bot.db                   # Base de datos SQLite (favoritos + histórico)
├── logs/
│   ├── app.log                  # Log del bot
│   └── colector.log             # Log del colector
├── config.py                    # Configuración central (carga .env)
├── requirements.txt
├── .env.example
├── CHANGELOG.md
├── ROADMAP.md
└── PROJECT_OVERVIEW.md          # Guía técnica del proyecto
```

---

## Instalación

### 1. Clonar y preparar entorno virtual

```bash
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
nano .env
```

Contenido mínimo de `.env`:
```env
TELEGRAM_BOT_TOKEN=tu_token_aqui

STORAGE_ENABLED=true
DB_PATH=data/bot.db

LOG_LEVEL=INFO
LOG_FILE=logs/app.log

FAVORITOS_MAX=10
```

> Obtené el token creando un bot con [@BotFather](https://t.me/BotFather) en Telegram.

---

## Cómo correr el proyecto

### Bot de Telegram

```bash
source venv/bin/activate
python bot/telegram_bot.py
```

### Colector autónomo (proceso separado)

```bash
source venv/bin/activate
python collector/colector.py
```

> El colector y el bot pueden correr en paralelo. Usan WAL mode en SQLite para evitar conflictos de escritura.

### Inspeccionar el estado de la base de datos

```bash
python scripts/inspeccionar_db.py
```

Ejemplo de salida:
```
📂 Base de datos: data/bot.db  (52.0 KB)
🔖 Favoritos guardados:        3

📊 Consultas totales:          25
   • collector           23
   • parada               2

🚌 Arrivals totales:           92
   • Primeros avistamientos:  89
   • Repeticiones:             3

📈 Top líneas:
   153 R     →  53.1 min prom
   122 VERDE →  14.4 min prom
   120       →  11.8 min prom  ← más rápida
```

### Probar consultas desde la terminal (sin Telegram)

```bash
python scripts/query_parada.py 5742
python scripts/query_parada.py 5742 --linea 122
```

---

## Configurar en Raspberry Pi como servicios systemd

### 1. Instalar dependencias del sistema

```bash
sudo apt-get update
sudo apt-get install python3-pip python3-venv -y
```

### 2. Clonar y configurar el proyecto

```bash
cd /home/pi
git clone <repo> "bot de consultas v2"
cd "bot de consultas v2"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # configurar token
```

### 3. Crear servicios systemd

**Bot de Telegram** (`/etc/systemd/system/colectivos-bot.service`):
```ini
[Unit]
Description=Bot de Colectivos Rosario
After=network.target

[Service]
WorkingDirectory=/home/pi/bot de consultas v2
ExecStart=/home/pi/bot de consultas v2/venv/bin/python bot/telegram_bot.py
Restart=always
RestartSec=10
User=pi

[Install]
WantedBy=multi-user.target
```

**Colector autónomo** (`/etc/systemd/system/colectivos-collector.service`):
```ini
[Unit]
Description=Colector de Datos — Colectivos Rosario
After=network.target

[Service]
WorkingDirectory=/home/pi/bot de consultas v2
ExecStart=/home/pi/bot de consultas v2/venv/bin/python collector/colector.py
Restart=always
RestartSec=15
User=pi

[Install]
WantedBy=multi-user.target
```

**Habilitar y arrancar:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable colectivos-bot colectivos-collector
sudo systemctl start colectivos-bot colectivos-collector
sudo systemctl status colectivos-bot
```

---

## Configurar nginx (para el futuro dashboard)

Cuando el dashboard Streamlit esté listo, agregar a la config de nginx:

```nginx
location /dashboard {
    proxy_pass         http://localhost:8501;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade $http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_set_header   Host $host;
    proxy_read_timeout 86400;
}
```

---

## Endpoints de API utilizados

Descubiertos por ingeniería inversa de [cuandollegarosario.com](https://cuandollegarosario.com):

| Endpoint | Uso |
|----------|-----|
| `GET /api/public/parada/{id}/arribos` | Colectivos próximos a una parada |
| `GET /api/public/search?query=&lat=&lon=` | Paradas cercanas a coordenadas GPS |

---

## Tecnologías

| Tecnología | Uso |
|-----------|-----|
| **Python 3.9+** | Lenguaje principal (compatible con ARM/Pi Zero) |
| **python-telegram-bot v20+** | Framework async para el bot |
| **APScheduler** | Jobs periódicos del live tracking |
| **requests + tenacity** | HTTP con reintentos automáticos |
| **SQLite (WAL mode)** | Persistencia de favoritos e histórico |
| **dataclasses** | Modelos de datos sin dependencias externas |
| **Streamlit** _(próximamente)_ | Dashboard de analítica |
| **pandas** _(próximamente)_ | Procesamiento de datos históricos |
| **Plotly** _(próximamente)_ | Visualizaciones interactivas |

---

## Licencia

Uso personal / educativo. Los datos provienen de la API pública de Cuándo Llega Rosario.
