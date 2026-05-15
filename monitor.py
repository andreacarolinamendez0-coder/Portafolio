"""
monitor.py — Motor de monitoreo de mercado
==========================================

FUENTES DE DATOS (responsabilidades claras):
─────────────────────────────────────────────
  Finnhub  →  precio actual en TIEMPO REAL (sin delay)
               quote: precio, apertura, max, min, cambio % del día
               Se usa SOLO para mostrar el precio real al usuario

  yfinance →  histórico OHLC de los últimos 90 días
               Se usa SOLO para calcular indicadores técnicos:
               MA20, MA50, RSI, tendencia, volumen ratio
               Tiene 15 min de delay pero no importa — los
               indicadores técnicos son diarios, no necesitan RT

FLUJO por activo:
  1. Finnhub  → precio actual RT           (lo que ve el usuario)
  2. yfinance → histórico 90d              (para calcular score)
  3. Combinar → precio RT + score técnico  (alerta inteligente)

FIXES vs versión anterior:
  ✅ Alertas de entrada: una sola vez por ticker por día
  ✅ Botones de respuesta: "Ya entré / No voy a entrar / Sigue informando"
  ✅ Anti-spam: máximo 3 intentos sin respuesta, luego silencio
  ✅ Estado persistente en disco (sobrevive reinicios de Railway)
  ✅ Cierre del mercado limpia las alertas del día automáticamente
"""

import os, json, time, threading, requests
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATOS_DIR   = os.path.join(BASE_DIR, "datos")
PORTS_DIR   = os.path.join(DATOS_DIR, "portafolios")
BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")

INTERVALO_MINUTOS  = 18
UMBRAL_ENTRADA     = 6.5
DIAS_SIN_SENAL_MAX = 5

# ─────────────────────────────────────────────────────────────
# TIEMPO
# ─────────────────────────────────────────────────────────────

from datetime import datetime
import pytz

TZ_COLOMBIA = pytz.timezone("America/Bogota")
TZ_NUEVA_YORK = pytz.timezone("America/New_York")

def hora_colombia():
    """Hora actual en Colombia."""
    return datetime.now(TZ_COLOMBIA)

def hora_nueva_york():
    """Hora actual en Nueva York (maneja DST automáticamente)."""
    return datetime.now(TZ_NUEVA_YORK)

def mercado_abierto():
    """
    NYSE abre 9:30am–4:00pm hora Nueva York, lunes a viernes.
    Usar hora NY directamente elimina el problema del DST.
    """
    ahora_ny = hora_nueva_york()
    if ahora_ny.weekday() >= 5:
        return False
    apertura = ahora_ny.replace(hour=9, minute=30, second=0, microsecond=0)
    cierre   = ahora_ny.replace(hour=16, minute=0, second=0, microsecond=0)
    return apertura <= ahora_ny <= cierre

def es_hora_buenos_dias():
    """9:00am–9:25am hora Colombia (antes de que abra NYSE)."""
    ahora_col = hora_colombia()
    if ahora_col.weekday() >= 5:
        return False
    inicio = ahora_col.replace(hour=9, minute=0, second=0, microsecond=0)
    fin    = ahora_col.replace(hour=9, minute=25, second=0, microsecond=0)
    return inicio <= ahora_col <= fin

def es_hora_cierre():
    """Ventana post-cierre NYSE, hora Colombia."""
    ahora_ny = hora_nueva_york()
    if ahora_ny.weekday() >= 5:
        return False
    # 4:00pm–4:45pm NY = cuando cierra el mercado
    inicio = ahora_ny.replace(hour=16, minute=0, second=0, microsecond=0)
    fin    = ahora_ny.replace(hour=16, minute=45, second=0, microsecond=0)
    return inicio <= ahora_ny <= fin

def es_hora_buenos_dias():
    ahora = hora_colombia()
    if ahora.weekday() >= 5:
        return False
    inicio = ahora.replace(hour=9, minute=0, second=0, microsecond=0)
    fin    = ahora.replace(hour=9, minute=25, second=0, microsecond=0)
    return inicio <= ahora <= fin

def es_hora_cierre():
    ahora = hora_colombia()
    if ahora.weekday() >= 5:
        return False
    inicio = ahora.replace(hour=16, minute=0, second=0, microsecond=0)
    fin    = ahora.replace(hour=16, minute=45, second=0, microsecond=0)
    return inicio <= ahora <= fin

def es_viernes():
    return hora_colombia().weekday() == 4

def segundos_hasta_apertura():
    ahora = hora_colombia()
    if ahora.weekday() >= 5:
        dias = 7 - ahora.weekday()
        prox = (ahora + timedelta(days=dias)).replace(hour=9, minute=0, second=0, microsecond=0)
    else:
        hoy_apertura = ahora.replace(hour=9, minute=0, second=0, microsecond=0)
        if ahora < hoy_apertura:
            prox = hoy_apertura
        else:
            prox = (ahora + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
            while prox.weekday() >= 5:
                prox += timedelta(days=1)
    return max(0, (prox - ahora).total_seconds())

# ─────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────

def telegram(chat_id, texto, reply_markup=None):
    if not chat_id:
        return
    try:
        payload = {"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10
        )
    except Exception as e:
        print(f"❌ Telegram error: {e}")

def teclado_decision(ticker):
    """Botones inline para que el usuario responda a una alerta de entrada."""
    return {
        "inline_keyboard": [[
            {"text": "✅ Ya entré",         "callback_data": f"entro:{ticker}"},
            {"text": "❌ No voy a entrar",  "callback_data": f"no_entro:{ticker}"},
            {"text": "📊 Sigue informando", "callback_data": f"sigue:{ticker}"},
        ]]
    }

# ─────────────────────────────────────────────────────────────
# FINNHUB — PRECIO EN TIEMPO REAL
# Responsabilidad: decirle al usuario el precio EXACTO ahora mismo
# ─────────────────────────────────────────────────────────────

def finnhub_quote(ticker):
    """
    Precio en tiempo real desde Finnhub (plan Free).
    Retorna dict con: c=precio actual, o=apertura, h=max, l=min,
                      pc=cierre anterior, dp=cambio %
    Retorna None si falla o el precio es 0.
    """
    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=8
        )
        resp.raise_for_status()
        data  = resp.json()
        precio = data.get("c", 0)
        if not precio or precio == 0:
            print(f"⚠️ Finnhub sin precio para {ticker}")
            return None
        return data
    except Exception as e:
        print(f"❌ Finnhub quote error ({ticker}): {e}")
        return None

# ─────────────────────────────────────────────────────────────
# YFINANCE — HISTÓRICO PARA INDICADORES TÉCNICOS
# Responsabilidad: proveer los 90 días de OHLC para calcular
#                  MA20, MA50, RSI, tendencia, volumen
# El delay de 15 min no importa — son indicadores diarios
# ─────────────────────────────────────────────────────────────

def yfinance_historico(ticker, dias=90):
    """
    Histórico OHLC diario desde yfinance.
    Solo se usa para calcular indicadores técnicos, NO para el precio mostrado.
    Retorna DataFrame con columnas: Close, Volume (mínimo)
    """
    try:
        hoy    = datetime.utcnow()
        inicio = (hoy - timedelta(days=dias)).strftime("%Y-%m-%d")
        df     = yf.download(
            ticker,
            start=inicio,
            end=hoy.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=True,
            progress=False
        )
        if df is None or df.empty or len(df) < 20:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        print(f"❌ yfinance histórico error ({ticker}): {e}")
        return None

# ─────────────────────────────────────────────────────────────
# ANÁLISIS TÉCNICO — combina ambas fuentes
# ─────────────────────────────────────────────────────────────

def analizar_activo(ticker):
    """
    Análisis completo de un activo combinando:
      - Finnhub: precio RT para mostrar al usuario
      - yfinance: histórico para calcular score técnico

    El precio que aparece en las alertas es siempre el de Finnhub (RT).
    El score se calcula con los datos históricos de yfinance.
    """
    try:
        # ── PASO 1: Precio en tiempo real (Finnhub) ───────────
        quote = finnhub_quote(ticker)
        if not quote:
            print(f"⚠️ Sin precio RT para {ticker} — omitiendo")
            return None

        precio_rt  = float(quote["c"])    # ← precio real, sin delay
        apertura   = float(quote.get("o",  0))
        maximo_dia = float(quote.get("h",  0))
        minimo_dia = float(quote.get("l",  0))
        cierre_ant = float(quote.get("pc", 0))
        cambio_dia = float(quote.get("dp", 0))  # % cambio del día

        # ── PASO 2: Histórico para indicadores (yfinance) ─────
        df = yfinance_historico(ticker, dias=90)
        if df is None:
            # Sin histórico no podemos calcular score — skip
            print(f"⚠️ Sin histórico para {ticker} — no se puede calcular score")
            return None

        close  = df["Close"].squeeze()
        volume = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series([1] * len(df))

        # ── PASO 3: Indicadores técnicos (sobre histórico) ────
        # MA20 y MA50: medias móviles del histórico
        # No usamos precio_rt aquí para no distorsionar las medias
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else ma20

        # Tendencia: % cambio en últimos 20 días (histórico)
        tend = round(
            ((float(close.iloc[-1]) - float(close.iloc[-20])) / float(close.iloc[-20])) * 100, 2
        )

        # Volumen ratio vs promedio 20 días
        vol_media = float(volume.rolling(20).mean().iloc[-1])
        vol_r     = round(float(volume.iloc[-1]) / vol_media, 2) if vol_media > 0 else 1.0

        # RSI 14 períodos (sobre histórico)
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, 1e-9)
        rsi   = round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

        # ── PASO 4: Score de entrada ───────────────────────────
        # Compara precio RT vs medias históricas (esto sí tiene sentido)
        score = 0.0
        if rsi < 30:                        score += 3.0
        elif rsi < 45:                      score += 2.5
        elif rsi < 55:                      score += 1.5
        elif rsi < 65:                      score += 0.5
        if precio_rt < ma20:                score += 2.0   # precio RT vs MA histórica
        elif precio_rt < ma50:              score += 1.0
        if -10 <= tend <= -3:               score += 2.5
        elif -3 < tend <= 0:                score += 1.5
        elif 0 < tend <= 3:                 score += 1.0
        elif tend < -10:                    score += 1.5
        if vol_r > 1.5:                     score += 0.5
        score = round(min(score, 10.0), 1)

        if score >= UMBRAL_ENTRADA:   senal = "ENTRAR"
        elif score >= 4.5:            senal = "VIGILAR"
        else:                         senal = "NEUTRAL"

        # ── RESULTADO FINAL ────────────────────────────────────
        return {
            # Precio en tiempo real (Finnhub) — lo que ve el usuario
            "ticker":     ticker,
            "precio":     round(precio_rt, 2),    # ← FINNHUB RT
            "apertura":   round(apertura, 2),     # ← FINNHUB RT
            "maximo_dia": round(maximo_dia, 2),   # ← FINNHUB RT
            "minimo_dia": round(minimo_dia, 2),   # ← FINNHUB RT
            "cierre_ant": round(cierre_ant, 2),   # ← FINNHUB RT
            "cambio_dia": round(cambio_dia, 2),   # ← FINNHUB RT (% día)
            # Indicadores técnicos (yfinance histórico) — para el score
            "ma20":       round(ma20, 2),         # ← YFINANCE histórico
            "ma50":       round(ma50, 2),         # ← YFINANCE histórico
            "rsi":        rsi,                    # ← YFINANCE histórico
            "tendencia":  tend,                   # ← YFINANCE histórico
            "vol_ratio":  vol_r,                  # ← YFINANCE histórico
            # Score y señal
            "score":      score,
            "senal":      senal,
            # Metadata
            "fuente_precio": "finnhub_rt",
            "fuente_score":  "yfinance_historico",
            "timestamp":  hora_colombia().strftime("%Y-%m-%d %H:%M"),
        }

    except Exception as e:
        print(f"❌ Error analizando {ticker}: {e}")
        return None

# ─────────────────────────────────────────────────────────────
# CONTROL DE ALERTAS — una por ticker por día
# ─────────────────────────────────────────────────────────────

def ya_alerte_hoy(estado, ticker):
    hoy     = hora_colombia().strftime("%Y-%m-%d")
    alertas = estado.get("alertas_enviadas_hoy", {})
    return alertas.get(ticker) == hoy

def marcar_alerta_enviada(estado, ticker):
    hoy = hora_colombia().strftime("%Y-%m-%d")
    if "alertas_enviadas_hoy" not in estado:
        estado["alertas_enviadas_hoy"] = {}
    estado["alertas_enviadas_hoy"][ticker] = hoy

def decision_usuario(estado, ticker):
    """Retorna 'entro', 'no_entro', 'sigue', o None."""
    hoy        = hora_colombia().strftime("%Y-%m-%d")
    decisiones = estado.get("decisiones_usuario", {})
    entrada    = decisiones.get(ticker, {})
    if entrada.get("fecha") == hoy:
        return entrada.get("decision")
    return None

def registrar_decision(archivo, ticker, decision):
    """Guarda la decisión del usuario. Llamado desde el webhook de Telegram."""
    estado = leer_estado(archivo)
    hoy    = hora_colombia().strftime("%Y-%m-%d")
    if "decisiones_usuario" not in estado:
        estado["decisiones_usuario"] = {}
    estado["decisiones_usuario"][ticker] = {"decision": decision, "fecha": hoy}
    guardar_estado(archivo, estado)
    print(f"  💾 Decisión '{decision}' guardada para {ticker}")

# ─────────────────────────────────────────────────────────────
# ANÁLISIS IA (Claude)
# ─────────────────────────────────────────────────────────────

def analisis_ia(resultados, portafolio, tipo="ciclo"):
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        resumen = ""
        for r in resultados:
            resumen += (
                f"- {r['ticker']}: ${r['precio']} (RT) | RSI {r['rsi']} | "
                f"Score {r['score']}/10 | Señal {r['senal']} | "
                f"Tendencia {r['tendencia']:+.1f}% | MA20 ${r['ma20']} | MA50 ${r['ma50']}"
            )
            if r.get("cambio_dia") is not None:
                resumen += f" | Hoy {r['cambio_dia']:+.2f}%"
            resumen += "\n"

        if tipo == "cierre":
            prompt = (
                f"Eres analista financiero de {portafolio['propietario']}. "
                f"Cierre NYSE {hora_colombia().strftime('%A %d de %B')}.\n\n"
                f"MÉTRICAS FINALES:\n{resumen}\n\n"
                f"Reporte de cierre en español, máximo 5 párrafos. "
                f"Sin asteriscos. Usa los números exactos."
            )
        elif tipo == "suboptimal":
            prompt = (
                f"Analista de {portafolio['propietario']}. "
                f"{DIAS_SIN_SENAL_MAX}+ días hábiles sin señal.\n\n"
                f"ESTADO:\n{resumen}\n\n"
                f"Recomendación especial, máximo 4 párrafos. Sin asteriscos. Directo."
            )
        elif tipo == "buenos_dias":
            tickers = list(portafolio.get("composicion", {}).keys())
            prompt = (
                f"Analista de {portafolio['propietario']}. "
                f"9:15am Colombia, NYSE abre en 15 min.\n"
                f"PORTAFOLIO: {', '.join(tickers)}\n"
                f"UN párrafo corto de buenos días, máximo 3 oraciones. Sin asteriscos."
            )
        else:
            entradas = [r for r in resultados if r["senal"] == "ENTRAR"]
            prompt = (
                f"Analista de {portafolio['propietario']}. "
                f"Ciclo {hora_colombia().strftime('%H:%M')}.\n\n"
                f"SEÑALES:\n{resumen}\n\n"
                f"{'ENTRADAS: ' + ', '.join(r['ticker'] for r in entradas) if entradas else 'Sin entradas.'}\n\n"
                f"2-3 oraciones máximo. Sin asteriscos."
            )

        resp = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=500 if tipo in ("cierre", "suboptimal") else 150,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.content[0].text.strip()
    except Exception as e:
        print(f"❌ IA error: {e}")
        return ""

# ─────────────────────────────────────────────────────────────
# PERSISTENCIA
# ─────────────────────────────────────────────────────────────

def leer_estado(archivo):
    ruta = os.path.join(PORTS_DIR, f"monitor_{archivo}")
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def guardar_estado(archivo, estado):
    ruta = os.path.join(PORTS_DIR, f"monitor_{archivo}")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Error guardando estado: {e}")

def leer_portafolios_activos():
    activos = []
    if not os.path.exists(PORTS_DIR):
        return activos
    for fn in os.listdir(PORTS_DIR):
        if not fn.endswith(".json") or fn.startswith("monitor_"):
            continue
        ruta = os.path.join(PORTS_DIR, fn)
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                p = json.load(f)
            if p.get("monitoreo_activo") and p.get("composicion"):
                print(f"✅ Portafolio activo: {p.get('nombre','?')} — {len(p['composicion'])} activos")
                activos.append((fn, p))
        except:
            continue
    if not activos:
        print("💤 Sin portafolios activos")
    return activos

def chat_id_de(portafolio):
    try:
        import sys
        sys.path.insert(0, BASE_DIR)
        from gestor_portafolio import get_usuario
        owner = portafolio.get("owner", "")
        if owner:
            u = get_usuario(owner)
            if u:
                cid = u.get("telegram_chat_id", "").strip()
                if cid:
                    print(f"📲 chat_id encontrado para {owner}: {cid}")
                    return cid
    except Exception as e:
        print(f"⚠️ No pudo leer usuario para chat_id: {e}")
    cid = portafolio.get("telegram_chat_id", "").strip()
    if cid:
        return cid
    print(f"⚠️ Sin chat_id para portafolio: {portafolio.get('nombre','?')}")
    return ""

# ─────────────────────────────────────────────────────────────
# BUENOS DÍAS
# ─────────────────────────────────────────────────────────────

def enviar_buenos_dias(archivo, portafolio):
    chat_id = chat_id_de(portafolio)
    if not chat_id:
        return

    tickers     = list(portafolio.get("composicion", {}).keys())
    nombre_port = portafolio.get("nombre", "tu portafolio")
    ahora       = hora_colombia()
    dia_semana  = ["lunes", "martes", "miércoles", "jueves", "viernes"][ahora.weekday()]

    msg = (
        f"☀️ <b>Buenos días — {dia_semana} {ahora.strftime('%d/%m')}</b>\n\n"
        f"📋 Portafolio: <b>{nombre_port}</b>\n"
        f"🔍 Monitoreando: <b>{', '.join(tickers)}</b>\n\n"
        f"El mercado NYSE abre a las 9:30am. "
        f"Estaré analizando cada 18 minutos y te aviso si encuentro señales.\n\n"
        f"<i>Cuando recibas una alerta podrás responder:\n"
        f"✅ Ya entré · ❌ No voy a entrar · 📊 Sigue informando</i>"
    )

    try:
        ia_saludo = analisis_ia([], portafolio, tipo="buenos_dias")
        if ia_saludo:
            msg += f"\n\n💬 <i>{ia_saludo}</i>"
    except:
        pass

    telegram(chat_id, msg)
    print(f"  ☀️ Buenos días enviado: {portafolio['nombre']}")

# ─────────────────────────────────────────────────────────────
# CICLO PRINCIPAL
# ─────────────────────────────────────────────────────────────

def ciclo_portafolio(archivo, portafolio):
    composicion = portafolio.get("composicion", {})
    tickers     = list(composicion.keys())
    if not tickers:
        return

    print(f"  🔍 Analizando {len(tickers)} activos de {portafolio['nombre']}...")
    resultados = []
    for tk in tickers:
        r = analizar_activo(tk)
        if r:
            resultados.append(r)
        time.sleep(0.5)  # pequeña pausa entre tickers

    if not resultados:
        return

    estado    = leer_estado(archivo)
    chat_id   = chat_id_de(portafolio)
    ahora_str = hora_colombia().strftime("%Y-%m-%d %H:%M")
    hoy_str   = hora_colombia().strftime("%Y-%m-%d")

    entradas = [r for r in resultados if r["senal"] == "ENTRAR"]
    vigilar  = [r for r in resultados if r["senal"] == "VIGILAR"]

    if entradas:
        ia_txt = analisis_ia(resultados, portafolio, tipo="ciclo")

        for r in entradas:
            ticker = r["ticker"]
            dec    = decision_usuario(estado, ticker)

            # ── Silenciar según decisión del usuario ───────────
            if dec == "no_entro":
                print(f"  ⏭ {ticker}: usuario dijo NO entrar — silenciado hoy")
                continue

            if dec == "entro":
                print(f"  ⏭ {ticker}: usuario ya entró — silenciado hoy")
                continue

            # ── Anti-spam: máximo 3 intentos sin respuesta ─────
            if ya_alerte_hoy(estado, ticker) and dec != "sigue":
                clave   = f"ciclos_sin_respuesta_{ticker}"
                ciclos  = estado.get(clave, 0) + 1
                estado[clave] = ciclos
                if ciclos >= 3:
                    print(f"  🔇 {ticker}: 3 intentos sin respuesta — silenciando hoy")
                    continue
                print(f"  🔁 {ticker}: reintento {ciclos}/3 sin respuesta del usuario")

            # ── Construir y enviar alerta ──────────────────────
            msg = (
                f"🟢 <b>SEÑAL DE ENTRADA — {ticker}</b>\n\n"
                # Precio en tiempo real (Finnhub)
                f"💵 Precio: <b>${r['precio']:,.2f} USD</b> "
                f"({r['cambio_dia']:+.2f}% hoy)\n"
                f"🕐 Apertura: ${r['apertura']:,.2f} · "
                f"Max: ${r['maximo_dia']:,.2f} · Min: ${r['minimo_dia']:,.2f}\n\n"
                # Indicadores técnicos (yfinance histórico)
                f"📊 Score: <b>{r['score']}/10</b> · RSI: {r['rsi']} · "
                f"Tendencia 20d: {r['tendencia']:+.1f}%\n"
                f"📈 MA20: ${r['ma20']:,.2f} · MA50: ${r['ma50']:,.2f}\n"
            )
            if ia_txt:
                msg += f"\n💬 {ia_txt}"
            if dec == "sigue":
                msg += "\n\n<i>(Actualización — pediste seguir informado)</i>"

            telegram(chat_id, msg, reply_markup=teclado_decision(ticker))
            marcar_alerta_enviada(estado, ticker)
            estado[f"ciclos_sin_respuesta_{ticker}"] = 0
            print(f"  ✅ Alerta enviada: {ticker} — precio RT ${r['precio']} (Finnhub)")

        estado["ultimo_dia_con_senal"] = hoy_str
        estado["dias_consecutivos_sin_senal"] = 0

    else:
        ultimo = estado.get("ultimo_dia_con_senal")
        if ultimo:
            try:
                dias = sum(
                    1 for i in range(
                        (datetime.strptime(hoy_str, "%Y-%m-%d") -
                         datetime.strptime(ultimo, "%Y-%m-%d")).days
                    )
                    if (datetime.strptime(ultimo, "%Y-%m-%d") + timedelta(days=i+1)).weekday() < 5
                )
                estado["dias_consecutivos_sin_senal"] = dias
            except:
                estado["dias_consecutivos_sin_senal"] = estado.get("dias_consecutivos_sin_senal", 0)
        else:
            estado["dias_consecutivos_sin_senal"] = estado.get("dias_consecutivos_sin_senal", 0) + 1

    estado["resultados"]        = resultados
    estado["timestamp"]         = ahora_str
    estado["prediccion"]        = (
        f"🟢 {len(entradas)} entrada(s) detectada(s)" if entradas
        else f"👁 {len(vigilar)} en vigilancia" if vigilar
        else "⚪ Sin señales este ciclo"
    )
    estado["justificacion"]     = analisis_ia(resultados, portafolio, tipo="ciclo") if not entradas else ""
    estado["nombre_portafolio"] = portafolio["nombre"]
    guardar_estado(archivo, estado)
    return estado

# ─────────────────────────────────────────────────────────────
# REPORTE DE CIERRE
# ─────────────────────────────────────────────────────────────

def reporte_cierre(archivo, portafolio, estado):
    resultados = estado.get("resultados", [])
    if not resultados:
        return

    chat_id  = chat_id_de(portafolio)
    hoy_str  = hora_colombia().strftime("%A %d de %B de %Y")
    dias_sin = estado.get("dias_consecutivos_sin_senal", 0)

    lineas = [f"📋 <b>REPORTE DE CIERRE — {portafolio['nombre']}</b>", f"📅 {hoy_str}\n"]
    for r in sorted(resultados, key=lambda x: x["score"], reverse=True):
        emoji      = {"ENTRAR": "🟢", "VIGILAR": "🟡", "NEUTRAL": "⚪"}.get(r["senal"], "⚪")
        cambio_str = f" ({r['cambio_dia']:+.2f}%)" if r.get("cambio_dia") is not None else ""
        lineas.append(
            f"{emoji} <b>{r['ticker']}</b> ${r['precio']:,.2f}{cambio_str}\n"
            f"   Score {r['score']}/10 | RSI {r['rsi']} | {r['tendencia']:+.1f}% | Vol {r['vol_ratio']}x"
        )

    entradas = [r for r in resultados if r["senal"] == "ENTRAR"]
    lineas.append(
        f"\n🎯 Señales: {', '.join(r['ticker'] for r in entradas)}" if entradas
        else "\n⚪ Sin señales hoy"
    )
    if dias_sin > 0:
        lineas.append(f"📆 Días sin señal: {dias_sin}")

    ia_cierre = analisis_ia(resultados, portafolio, tipo="cierre")
    msg_final = "\n".join(lineas)
    if ia_cierre:
        msg_final += f"\n\n💬 <b>Análisis:</b>\n<i>{ia_cierre}</i>"

    if dias_sin >= DIAS_SIN_SENAL_MAX and es_viernes():
        ia_sub = analisis_ia(resultados, portafolio, tipo="suboptimal")
        msg_final += (
            f"\n\n⚠️ <b>ALERTA: {dias_sin} días sin señal ideal</b>\n"
            + (f"<i>{ia_sub}</i>" if ia_sub else "")
        )

    telegram(chat_id, msg_final)
    print(f"  📋 Reporte cierre enviado: {portafolio['nombre']}")

    # Limpiar alertas del día al cerrar — mañana arrancan limpias
    estado["alertas_enviadas_hoy"] = {}
    estado["decisiones_usuario"]   = {}
    estado["reporte_cierre"]       = msg_final
    estado["reporte_cierre_fecha"] = hora_colombia().strftime("%Y-%m-%d")
    estado["cierre_enviado_hoy"]   = hora_colombia().strftime("%Y-%m-%d")
    guardar_estado(archivo, estado)

# ─────────────────────────────────────────────────────────────
# ALERTA SUBÓPTIMA
# ─────────────────────────────────────────────────────────────

def verificar_alerta_suboptimal(archivo, portafolio, estado):
    dias_sin = estado.get("dias_consecutivos_sin_senal", 0)
    if dias_sin < DIAS_SIN_SENAL_MAX:
        return
    resultados = estado.get("resultados", [])
    if not resultados:
        return
    semana = hora_colombia().strftime("%Y-W%W")
    if estado.get("alerta_suboptimal_semana") != semana:
        ia_sub = analisis_ia(resultados, portafolio, tipo="suboptimal")
        estado["alerta_suboptimal"]        = ia_sub
        estado["alerta_suboptimal_semana"] = semana
        estado["dias_sin_senal_display"]   = dias_sin
        guardar_estado(archivo, estado)

# ─────────────────────────────────────────────────────────────
# WEBHOOK: procesar respuestas del usuario desde Telegram
# ─────────────────────────────────────────────────────────────

def procesar_callback_telegram(callback_data, chat_id):
    """
    Procesa los botones inline del usuario.
    callback_data: "entro:AAPL", "no_entro:AAPL", "sigue:AAPL"
    Llamado desde /telegram-webhook en dashboard.py
    """
    try:
        partes   = callback_data.split(":", 1)
        decision = partes[0]
        ticker   = partes[1] if len(partes) > 1 else ""
        if not ticker:
            return

        for fn in os.listdir(PORTS_DIR):
            if not fn.endswith(".json") or fn.startswith("monitor_"):
                continue
            try:
                with open(os.path.join(PORTS_DIR, fn), "r", encoding="utf-8") as f:
                    p = json.load(f)
                if chat_id_de(p) == str(chat_id):
                    registrar_decision(fn, ticker, decision)
                    mensajes = {
                        "entro":    f"✅ Registrado: entraste a <b>{ticker}</b>. No te molesto más con este hoy.",
                        "no_entro": f"❌ Ok, no te aviso más de <b>{ticker}</b> hoy.",
                        "sigue":    f"📊 Perfecto, te sigo informando de <b>{ticker}</b> si el precio mejora."
                    }
                    telegram(str(chat_id), mensajes.get(decision, "Decisión registrada."))
                    print(f"  📲 Decisión '{decision}' para {ticker} — chat {chat_id}")
                    break
            except:
                continue
    except Exception as e:
        print(f"❌ Error procesando callback Telegram: {e}")

# ─────────────────────────────────────────────────────────────
# LOOP PRINCIPAL
# ─────────────────────────────────────────────────────────────

_monitor_activo = False

def iniciar_monitor():
    global _monitor_activo
    if _monitor_activo:
        return
    _monitor_activo = True
    threading.Thread(target=_loop_monitor, daemon=True).start()
    print("🚀 Monitor iniciado")

def _loop_monitor():
    ultimo_ciclo   = {}
    buenos_enviado = {}

    while True:
        try:
            portafolios = leer_portafolios_activos()
            ahora       = hora_colombia()
            hoy         = ahora.strftime("%Y-%m-%d")

            # ── Buenos días (una vez por día) ──────────────────
            if es_hora_buenos_dias():
                for archivo, portafolio in portafolios:
                    if buenos_enviado.get(archivo) != hoy:
                        try:
                            with open(os.path.join(PORTS_DIR, archivo), "r", encoding="utf-8") as f:
                                pf = json.load(f)
                            enviar_buenos_dias(archivo, pf)
                        except Exception as e:
                            print(f"❌ Error buenos días {archivo}: {e}")
                        buenos_enviado[archivo] = hoy
                time.sleep(60)

            # ── Mercado abierto: ciclos de análisis ────────────
            elif mercado_abierto():
                for archivo, portafolio in portafolios:
                    ultimo = ultimo_ciclo.get(archivo)
                    if ultimo is None or (ahora - ultimo).total_seconds() >= INTERVALO_MINUTOS * 60:
                        try:
                            with open(os.path.join(PORTS_DIR, archivo), "r", encoding="utf-8") as f:
                                pf = json.load(f)
                            estado = ciclo_portafolio(archivo, pf)
                            if estado:
                                verificar_alerta_suboptimal(archivo, pf, estado)
                        except Exception as e:
                            print(f"❌ Error ciclo {archivo}: {e}")
                        ultimo_ciclo[archivo] = ahora
                time.sleep(60)

            # ── Hora de cierre ─────────────────────────────────
            elif es_hora_cierre():
                print("📋 Ventana de cierre — el scheduler envía el reporte.")
                time.sleep(60)

            # ── Mercado cerrado ────────────────────────────────
            else:
                segs = segundos_hasta_apertura()
                print(f"💤 Mercado cerrado. Próxima apertura en {segs/3600:.1f}h")
                time.sleep(min(segs, 300))

        except Exception as e:
            print(f"❌ Error loop monitor: {e}")
            time.sleep(60)