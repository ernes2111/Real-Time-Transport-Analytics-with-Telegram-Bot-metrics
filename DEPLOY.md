# Guía de Despliegue — Raspberry Pi Zero 2W

Pasos para migrar el proyecto desde la Mac a la Raspberry Pi y dejarlo corriendo como servicios permanentes.

---

## Requisitos previos

- Raspberry Pi Zero 2W con DietPi o Raspberry Pi OS (Lite recomendado)
- Python 3.9 o superior instalado en la Pi
- Acceso SSH a la Pi (ya configurado)
- IP de la Pi: `192.168.100.140` — usuario: `root`

Verificar la versión de Python en la Pi:
```bash
ssh root@192.168.100.140
python3 --version   # debe ser 3.9+
```

---

## Paso 1 — Instalar dependencias del sistema

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv git
```

---

## Paso 2 — Transferir el proyecto desde la Mac

Desde tu **Mac**, en la terminal:

```bash
rsync -av --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' --exclude='data/' --exclude='logs/' \
  "/Users/ernesto/Desktop/bot de consultas v2/" \
  root@192.168.100.140:/root/bot-colectivos/
```

> `rsync` es mejor que `scp` para proyectos: es incremental (solo transfiere lo que cambió), excluye el `venv` (que se recrea en la Pi) y excluye la DB (para no sobrescribir datos existentes).

---

## Paso 3 — Configurar el entorno en la Pi

Conectarse a la Pi:
```bash
ssh root@192.168.100.140
cd /root/bot-colectivos
```

Crear entorno virtual e instalar dependencias:
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> En la Pi Zero 2W el `pip install` puede tardar 3–5 minutos porque compila algunas dependencias en ARM. Es normal.

---

## Paso 4 — Configurar las variables de entorno

```bash
cp .env.example .env
nano .env
```

Contenido final del `.env`:
```env
TELEGRAM_BOT_TOKEN=(insert here)

ADMIN_IDS=(telegram ID user here)

STORAGE_ENABLED=true
DB_PATH=data/bot.db

LOG_LEVEL=INFO
LOG_FILE=logs/app.log

FAVORITOS_MAX=10
```

Guardar con `Ctrl+O`, `Enter`, `Ctrl+X`.

---

## Paso 5 — Crear los directorios necesarios

```bash
mkdir -p data logs
```

---

## Paso 6 — Probar que todo funciona (antes de crear los servicios)

```bash
source venv/bin/activate

# Probar el bot (Ctrl+C para detener)
python bot/telegram_bot.py
```

En otra sesión SSH, probar el colector:
```bash
cd ~/bot-colectivos
source venv/bin/activate
python collector/colector.py
```

Si ambos arrancan sin errores, continuar.

Verificar que la DB se creó:
```bash
python scripts/inspeccionar_db.py
```

---

## Paso 7 — Crear los servicios systemd

Los servicios permiten que el bot y el colector arranquen solos al reiniciar la Pi y se reinicien si se caen.

### Servicio del Bot

```bash
sudo nano /etc/systemd/system/colectivos-bot.service
```

Pegar este contenido (ajustar el usuario si no es `pi`):
```ini
[Unit]
Description=Bot de Colectivos Rosario
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/root/bot-colectivos
ExecStart=/root/bot-colectivos/venv/bin/python bot/telegram_bot.py
Restart=always
RestartSec=10
User=root
StandardOutput=append:/root/bot-colectivos/logs/app.log
StandardError=append:/root/bot-colectivos/logs/app.log

[Install]
WantedBy=multi-user.target
```

### Servicio del Colector

```bash
sudo nano /etc/systemd/system/colectivos-collector.service
```

```ini
[Unit]
Description=Colector de Datos — Colectivos Rosario
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/root/bot-colectivos
ExecStart=/root/bot-colectivos/venv/bin/python collector/colector.py
Restart=always
RestartSec=15
User=root
StandardOutput=append:/root/bot-colectivos/logs/colector.log
StandardError=append:/root/bot-colectivos/logs/colector.log

[Install]
WantedBy=multi-user.target
```

---

## Paso 8 — Habilitar y arrancar los servicios

```bash
sudo systemctl daemon-reload
sudo systemctl enable colectivos-bot colectivos-collector
sudo systemctl start colectivos-bot colectivos-collector
```

Verificar que están corriendo:
```bash
sudo systemctl status colectivos-bot
sudo systemctl status colectivos-collector
```

Deberías ver `Active: active (running)` en verde en ambos.

---

## Paso 9 — Verificar los logs en vivo

```bash
# Log del bot en tiempo real
tail -f ~/bot-colectivos/logs/app.log

# Log del colector en tiempo real
tail -f ~/bot-colectivos/logs/colector.log
```

---

## Comandos útiles del día a día

```bash
# Ver estado de los servicios
sudo systemctl status colectivos-bot
sudo systemctl status colectivos-collector

# Reiniciar un servicio (ej: después de actualizar el código)
sudo systemctl restart colectivos-bot
sudo systemctl restart colectivos-collector

# Detener un servicio
sudo systemctl stop colectivos-bot

# Ver los últimos 50 logs del servicio
sudo journalctl -u colectivos-bot -n 50

# Inspeccionar la base de datos
cd /root/bot-colectivos
source venv/bin/activate
python scripts/inspeccionar_db.py
```

---

## Paso 10 — Actualizar el código desde la Mac

Cuando hagas cambios en la Mac, para sincronizarlos a la Pi:

```bash
# Desde la Mac
rsync -av --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' --exclude='data/' --exclude='logs/' \
  "/Users/ernesto/Desktop/bot de consultas v2/" \
  root@192.168.100.140:/root/bot-colectivos/

# Luego reiniciar los servicios en la Pi
ssh root@192.168.100.140 "sudo systemctl restart colectivos-bot colectivos-collector"
```

O todo en un solo comando desde la Mac:
```bash
rsync -av --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' --exclude='data/' --exclude='logs/' \
  "/Users/ernesto/Desktop/bot de consultas v2/" \
  root@192.168.100.140:/root/bot-colectivos/ && \
  ssh root@192.168.100.140 "systemctl restart colectivos-bot colectivos-collector && echo 'Servicios reiniciados OK'"
```

---

## Resolución de problemas comunes

### El bot no arranca — error de token

```bash
sudo journalctl -u colectivos-bot -n 20
```
Si aparece `Unauthorized`: el token en `.env` es incorrecto. Verificar con `cat /root/bot-colectivos/.env`.

### Error `No module named 'src'`

El `WorkingDirectory` del servicio no apunta al directorio correcto. Verificar:
```bash
ls /root/bot-colectivos/bot/telegram_bot.py  # debe existir
```

### El pip install falla en alguna dependencia

En la Pi Zero 2W, algunas librerías requieren compilar código C. Si falla:
```bash
apt-get install -y python3-dev libffi-dev
pip install -r requirements.txt
```

### La DB no se crea

Verificar que el directorio `data/` existe:
```bash
ls -la /root/bot-colectivos/data/
# Si no existe:
mkdir -p /root/bot-colectivos/data
```

### Verificar consumo de memoria

La Pi Zero 2W tiene 512 MB. Bot + colector deberían usar ~80 MB en total:
```bash
free -h
ps aux --sort=-%mem | head -10
```

### Ver logs en vivo

```bash
tail -f /root/bot-colectivos/logs/app.log
tail -f /root/bot-colectivos/logs/colector.log
```
