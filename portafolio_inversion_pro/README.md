# 📊 Inversión Pro — Sistema de Portafolios Multi-Usuario

Sistema profesional de gestión de portafolios de inversión con monitoreo en tiempo real, analista IA conversacional, alertas Telegram y panel de administración.

---

## 🚀 Inicio Rápido

### Windows (doble clic)
```
iniciar.bat
```

### Manual
```bash
cd "C:\Users\Grupo QAB\Desktop\Andrea\Portafolio"
pip install -r requirements.txt
python app.py
```

Abrir: **http://localhost:5000**

---

## 👤 Credenciales por Defecto

| Campo | Valor |
|-------|-------|
| Admin Email | admin@portafolio.com |
| Admin Password | admin123 |

> ⚠️ Cambia la contraseña del admin después del primer login.

---

## 🗂 Estructura del Proyecto

```
Portafolio/
├── app.py              # Aplicación principal Flask
├── config.py           # Configuración (API keys, etc.)
├── database.py         # Modelos SQLAlchemy
├── monitor.py          # Monitor paralelo de precios
├── ai_analyst.py       # Analista IA con Groq
├── telegram_bot.py     # Notificaciones Telegram
├── requirements.txt    # Dependencias
├── iniciar.bat         # Script de inicio Windows
├── instance/
│   └── portafolio.db   # Base de datos SQLite (auto-creada)
├── logs/
│   └── app.log         # Logs del sistema
└── templates/
    ├── base.html        # Layout base con sidebar
    ├── landing.html     # Página de inicio
    ├── login.html       # Login
    ├── register.html    # Registro
    ├── dashboard.html   # Dashboard principal
    ├── portfolio.html   # Vista de portafolio
    ├── settings.html    # Configuración de usuario
    └── admin.html       # Panel de administración
```

---

## ✨ Funcionalidades

### Multi-usuario
- Registro y login con email/contraseña
- Cada usuario ve **solo** sus propios portafolios
- Sesiones persistentes

### Portafolios
- Múltiples portafolios por usuario
- Añadir/eliminar posiciones con ticker, acciones, precio de compra
- Soporte para acciones, ETFs, crypto (formato BTC-USD) via yfinance

### Monitor Paralelo
- **Un hilo independiente por portafolio** para actualizaciones simultáneas
- Actualización de precios cada 60 segundos
- Caché de precios para evitar rate limiting

### Alertas
- Tipos: precio supera, precio cae, sube X%, baja X%
- Cooldown de 1 hora para evitar spam
- Notificación por Telegram (con tu Chat ID)

### Analista IA (Andrea)
- Chat conversacional con contexto del portafolio
- Análisis automático completo del portafolio
- Powered by Groq LLaMA 3.3 70B

### Panel Admin
- Ver y gestionar todos los usuarios
- Activar/desactivar cuentas
- Estadísticas del sistema
- Log de acciones administrativas

---

## 📱 Configurar Telegram

1. Abre Telegram y busca **@userinfobot**
2. Envía `/start` — te responderá con tu **Chat ID**
3. En Configuración del sistema, ingresa ese Chat ID
4. El bot usará el token: `8332465511:AAH-PlentkDhWWNenLGOdvJCLC6OXNEnrA8`

---

## 🔧 Configuración

Edita `config.py` para cambiar:
- `SECRET_KEY` — clave secreta de sesiones
- `MONITOR_INTERVAL` — segundos entre actualizaciones (default: 60)
- API Keys de Groq y Telegram

---

## 📡 API Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/portfolios` | Lista portafolios del usuario |
| POST | `/api/portfolios` | Crear portafolio |
| GET | `/api/portfolios/{id}` | Detalle + stocks + gráfico |
| POST | `/api/portfolios/{id}/stocks` | Agregar acción |
| DELETE | `/api/stocks/{id}` | Eliminar posición |
| GET | `/api/price/{ticker}` | Precio actual de un ticker |
| GET/POST | `/api/alerts` | Listar/crear alertas |
| POST | `/api/ai/chat` | Chat con Andrea |
| GET | `/api/ai/analyze/{id}` | Análisis automático de portafolio |
| GET | `/api/admin/users` | (Admin) Lista de usuarios |
| GET | `/api/admin/stats` | (Admin) Estadísticas del sistema |
