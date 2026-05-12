# 📊 Sistema de Portafolio de Inversión con IA

Aplicación web full-stack para gestión de portafolios de renta variable americana, con monitor de mercado en tiempo real, análisis por inteligencia artificial y alertas automáticas por Telegram. Desplegada en producción en Railway.

---

## 🚀 Demo en producción

🔗 [Ver aplicación](https://web-production-07c9d.up.railway.app)

---

## ¿Qué hace el sistema?

### 📈 Monitor de mercado automático
- Analiza RSI (14), medias móviles (MA20/MA50), tendencia y volumen cada 18 minutos durante el horario NYSE (9:30am–4:00pm hora Colombia)
- Calcula un score de entrada de 0 a 10 por activo
- Emite señales: **ENTRAR** (≥ 6.5), **VIGILAR** (≥ 4.5) o **NEUTRAL**

### 🤖 Inteligencia Artificial (Claude — Anthropic)
- **Buenos días automático** a las 9:00am con resumen del día
- **Alertas de entrada** con justificación en lenguaje natural cuando hay oportunidad
- **Reporte de cierre** a las 4:00pm con análisis del día y recomendaciones
- **Analista de portafolio** conversacional para construir y actualizar composiciones
- **Asistente personal** que responde preguntas sobre el portafolio con datos reales
- **Análisis de TRM** con interpretación técnica de la tasa de cambio COP/USD

### 📲 Alertas por Telegram
- Notificación inmediata cuando un activo alcanza señal de entrada
- Reporte diario de cierre con tabla de scores y análisis IA
- Alerta subóptima si pasan 5+ días hábiles sin señal ideal
- Mensaje de buenos días con los activos monitoreados

### 📊 Dashboard interactivo
- Valor del portafolio en tiempo real (deflactado por inflación colombiana)
- Gráfica de TRM con medias móviles y análisis técnico automático
- Composición del portafolio con gráfica de torta
- Ganancia real vs inflación por activo
- Historial y evolución del portafolio

### 🧮 Optimización de portafolios
- Algoritmo de Markowitz (Modern Portfolio Theory)
- Maximización del Sharpe Ratio ajustado por contexto macro
- Filtros de correlación, consistencia histórica y volatilidad
- Proyecciones Monte Carlo con y sin DCA, comparadas contra CDT colombiano

---

## 🛠 Stack tecnológico

| Tecnología | Uso |
|---|---|
| **Python / Flask** | Backend y servidor web |
| **Claude API (Anthropic)** | Análisis IA, chat y reportes |
| **yfinance** | Precios de acciones en tiempo real |
| **Pandas / NumPy / SciPy** | Análisis de datos y optimización |
| **Plotly** | Visualizaciones interactivas |
| **Telegram Bot API** | Alertas automáticas |
| **Railway** | Deploy en producción con volumen persistente |
| **Parquet** | Almacenamiento eficiente de series de tiempo |

---

## 🏗 Arquitectura del sistema

```
dashboard.py      — App Flask principal · todas las rutas y vistas
monitor.py        — Daemon de monitoreo · corre en hilo independiente
analista.py       — Optimización Markowitz · proyecciones Monte Carlo
recolector.py     — Datos macro: TRM, inflación COL/USA, Banrep, Risk Free
scheduler.py      — Tareas programadas · resúmenes diarios 8:00am
gestor_portafolio.py — CRUD de portafolios y usuarios
styles.py         — CSS global del sistema
```

### Flujo del monitor
```
9:00am  →  ☀️ Buenos días + activos a monitorear hoy
9:30am  →  🔍 Primer ciclo de análisis técnico
cada 18min →  🔄 Ciclo de análisis (RSI, MA, volumen, score)
            →  🟢 Alerta ENTRAR si score ≥ 6.5 (Telegram inmediato)
4:00pm  →  📋 Reporte de cierre con análisis IA
viernes →  ⚠️ Alerta subóptima si 5+ días sin señal
```

---

## ⚙️ Variables de entorno requeridas

```env
SECRET_KEY=
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=
GMAIL_USER=
GMAIL_PASS=
```

---

## 📦 Instalación local

```bash
git clone https://github.com/andreacarolinamendez0-coder/portfolio-inversiones.git
cd portfolio-inversiones
pip install -r requirements.txt
# Crea un archivo .env con las variables de entorno
python dashboard.py
```

---

## 📁 Estructura de datos

```
datos/
  macro/        →  TRM, inflación COL/USA, tasa Banrep, risk free (Parquet)
  precios/      →  Histórico de precios de acciones (Parquet)
  portafolios/  →  JSON por portafolio + estado del monitor
```

---

## 🔐 Seguridad

- Autenticación por usuario y contraseña con hash SHA-256
- Bloqueo automático tras 5 intentos fallidos (15 minutos)
- Acceso a portafolios restringido por `owner`
- Todas las credenciales via variables de entorno (nunca en el código)
- Registro de actividad: logins, registros, IPs y dispositivos

---

## 👤 Sobre el proyecto

Desarrollado como sistema personal de inversión a largo plazo (10 años) en acciones americanas desde Colombia. El objetivo fue construir una herramienta que automatizara el monitoreo del mercado, eliminara el ruido emocional de las decisiones de inversión y aprovechara la IA para análisis que normalmente requieren un analista financiero.

**Aprendizajes clave del proyecto:**
- Integración de LLMs (Claude) en aplicaciones de producción con prompts especializados
- Diseño de sistemas de monitoreo con hilos daemon y gestión de estado persistente
- Optimización financiera con algoritmos de Markowitz y simulaciones Monte Carlo
- Deploy y gestión de variables de entorno en Railway
- Manejo de datos financieros en tiempo real con yfinance y Parquet

---

*Construido con Python · Flask · Claude API · Railway*
