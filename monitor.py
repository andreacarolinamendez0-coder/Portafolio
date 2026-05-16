"""
monitor.py — Motor de monitoreo de mercado
==========================================

ARQUITECTURA NUEVA:
─────────────────────────────────────────────
  8:00am        →  precalcular_rangos()  UNA SOLA VEZ
                   Descarga histórico yfinance
                   Calcula RSI, MA20, MA50, tendencia, volumen (fijos todo el día)
                   Determina rangos de precio para ENTRAR y VIGILAR
                   Guarda en disco → sobrevive reinicios de Railway

  8:30am-3:00pm →  vigilar_precios()  CADA 9 SEGUNDOS
                   Solo consulta precio actual a Finnhub
                   Compara precio vs rangos precalculados
                   Si cruza un rango → alerta Telegram inmediata
                   Guarda precio actualizado → el display lo lee

  3:00pm        →  reporte de cierre

FUENTES DE DATOS:
─────────────────────────────────────────────
  Finnhub  →  precio actual TIEMPO REAL cada 9 segundos
  yfinance →  histórico 90 días UNA VEZ a las 8am
"""

import os, json, time, threading, requests
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import pytz
import warnings
warnings.filterwarnings("ignore")

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATOS_DIR   = os.path.join(BASE_DIR, "datos")
PORTS_DIR   = os.path.join(DATOS_DIR, "portafolios")
BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")

UMBRAL_ENTRADA     = 6.5
UMBRAL_VIGILAR     = 4.5
DIAS_SIN_SENAL_MAX = 5

# ─────────────────────────────────────────────────────────────
# ZONAS HORARIAS
# ─────────────────────────────────────────────────────────────

TZ_COLOMBIA   = pytz.timezone("America/Bogota")
TZ_NUEVA_YORK = pytz.timezone("America/New_York")

def hora_colombia():
    """Hora actual en Colombia (maneja DST automáticamente)."""
    return datetime.now(TZ_COLOMBIA)

def hora_nueva_york():
    """Hora actual en Nueva York (maneja DST automáticamente)."""
    return datetime.now(TZ_NUEVA_YORK)

# ─────────────────────────────────────────────────────────────
# FUNCIONES DE TIEMPO
# ─────────────────────────────────────────────────────────────

def mercado_abierto():
    """
    NYSE abre 9:30am–3:00pm hora Colombia (ajustado para cuenta individual).
    Usa hora Nueva York para manejar DST correctamente.
    """
    ahora_ny = hora_nueva_york()
    if ahora_ny.weekday() >= 5:
        return False
    apertura = ahora_ny.replace(hour=9, minute=30, second=0, microsecond=0)
    cierre   = ahora_ny.replace(hour=16, minute=0, second=0, microsecond=0)
    return apertura <= ahora_ny <= cierre

def es_hora_precalculo():
    """
    True entre 8:00am y 8:10am hora Colombia.
    Ventana para descargar histórico y calcular rangos del día.
    """
    ahora = hora_colombia()
    if ahora.weekday() >= 5:
        return False
    inicio = ahora.replace(hour=8, minute=0, second=0, microsecond=0)
    fin    = ahora.replace(hour=8, minute=10, second=0, microsecond=0)
    return inicio <= ahora <= fin

def es_hora_buenos_dias():
    """True entre 8:15am y 8:25am hora Colombia."""
    ahora = hora_colombia()
    if ahora.weekday() >= 5:
        return False
    inicio = ahora.replace(hour=8, minute=15, second=0, microsecond=0)
    fin    = ahora.replace(hour=8, minute=25, second=0, microsecond=0)
    return inicio <= ahora <= fin

def es_hora_cierre():
    """True entre 4:00pm y 4:45pm hora Nueva York."""
    ahora_ny = hora_nueva_york()
    if ahora_ny.weekday() >= 5:
        return False
    inicio = ahora_ny.replace(hour=16, minute=0, second=0, microsecond=0)
    fin    = ahora_ny.replace(hour=16, minute=45, second=0, microsecond=0)
    return inicio <= ahora_ny <= fin

def es_viernes():
    return hora_colombia().weekday() == 4

def segundos_hasta_precalculo():
    """
    Calcula segundos hasta las 8:00am Colombia del próximo día hábil.
    Usa hora Colombia porque el precálculo es a las 8am Colombia.
    """
    ahora = hora_colombia()
    if ahora.weekday() >= 5:
        # Fin de semana — próximo lunes
        dias = 7 - ahora.weekday()
        prox = (ahora + timedelta(days=dias)).replace(
            hour=8, minute=0, second=0, microsecond=0
        )
    else:
        hoy_precalculo = ahora.replace(hour=8, minute=0, second=0, microsecond=0)
        if ahora < hoy_precalculo:
            prox = hoy_precalculo
        else:
            # Ya pasó el precálculo de hoy — calcular para mañana
            prox = (ahora + timedelta(days=1)).replace(
                hour=8, minute=0, second=0, microsecond=0
            )
            # Saltar fin de semana
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
    """Botones inline para que el usuario responda a una alerta."""
    return {
        "inline_keyboard": [[
            {"text": "✅ Ya entré",         "callback_data": f"entro:{ticker}"},
            {"text": "❌ No voy a entrar",  "callback_data": f"no_entro:{ticker}"},
            {"text": "📊 Sigue informando", "callback_data": f"sigue:{ticker}"},
        ]]
    }

# ─────────────────────────────────────────────────────────────
# FINNHUB — PRECIO EN TIEMPO REAL
# ─────────────────────────────────────────────────────────────

def finnhub_quote(ticker):
    """
    Precio en tiempo real desde Finnhub (plan Free).
    Retorna dict con: c=precio actual, o=apertura, h=max, l=min,
                      pc=cierre anterior, dp=cambio %
    """
    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=8
        )
        resp.raise_for_status()
        data   = resp.json()
        precio = data.get("c", 0)
        if not precio or precio == 0:
            print(f"⚠️ Finnhub sin precio para {ticker}")
            return None
        return data
    except Exception as e:
        print(f"❌ Finnhub quote error ({ticker}): {e}")
        return None

# ─────────────────────────────────────────────────────────────
# YFINANCE — HISTÓRICO PARA INDICADORES
# Solo se usa a las 8am, no durante el mercado
# ─────────────────────────────────────────────────────────────

def yfinance_historico(ticker, dias=90):
    """
    Histórico OHLC diario desde yfinance.
    Se llama UNA VEZ a las 8am para calcular indicadores fijos.
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
# PRECÁLCULO DE RANGOS — corre UNA VEZ a las 8am
# ─────────────────────────────────────────────────────────────

def precalcular_rangos(archivo, portafolio):
    """
    Descarga histórico y calcula indicadores fijos del día.
    Determina rangos de precio para ENTRAR y VIGILAR.
    Guarda en datos/portafolios/rangos_<archivo> para sobrevivir reinicios.

    Los indicadores RSI, MA20, MA50, tendencia y volumen son FIJOS
    durante el día — se calculan con datos del día anterior.
    Solo el precio cambia durante el mercado.
    """
    composicion = portafolio.get("composicion", {})
    tickers     = list(composicion.keys())
    if not tickers:
        return None

    print(f"  📐 Precalculando rangos para {portafolio['nombre']}...")
    rangos_hoy = {}
    hoy        = hora_colombia().strftime("%Y-%m-%d")

    for ticker in tickers:
        try:
            # Descarga histórico — solo aquí, solo a las 8am
            df = yfinance_historico(ticker, dias=90)
            if df is None:
                print(f"    ⚠️ Sin histórico para {ticker} — omitiendo")
                continue

            close  = df["Close"].squeeze()
            volume = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series([1] * len(df))

            # ── Indicadores fijos — no cambian durante el día ──

            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else ma20

            # Tendencia: % cambio últimos 20 días
            tend = round(
                ((float(close.iloc[-1]) - float(close.iloc[-20])) /
                 float(close.iloc[-20])) * 100, 2
            )

            # Volumen ratio
            vol_media = float(volume.rolling(20).mean().iloc[-1])
            vol_r     = round(float(volume.iloc[-1]) / vol_media, 2) if vol_media > 0 else 1.0

            # RSI 14 períodos
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss.replace(0, 1e-9)
            rsi   = round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

            # ── Score base — sin precio vs medias ──────────────
            # RSI + tendencia + volumen (los 3 fijos)
            score_base = 0.0
            if rsi < 30:            score_base += 3.0
            elif rsi < 45:          score_base += 2.5
            elif rsi < 55:          score_base += 1.5
            elif rsi < 65:          score_base += 0.5
            if -10 <= tend <= -3:   score_base += 2.5
            elif -3 < tend <= 0:    score_base += 1.5
            elif 0 < tend <= 3:     score_base += 1.0
            elif tend < -10:        score_base += 1.5
            if vol_r > 1.5:         score_base += 0.5
            score_base = round(score_base, 1)

            # ── Rangos de precio ───────────────────────────────
            # precio < MA20 suma +2.0 → ¿llega al umbral?
            # precio < MA50 suma +1.0 → ¿llega al umbral?
            puede_entrar  = (score_base + 2.0) >= UMBRAL_ENTRADA
            puede_vigilar = (score_base + 1.0) >= UMBRAL_VIGILAR

            rango_entrar  = round(ma20, 2) if puede_entrar  else None
            rango_vigilar = round(ma50, 2) if puede_vigilar else None

            rangos_hoy[ticker] = {
                "ma20":          round(ma20, 2),
                "ma50":          round(ma50, 2),
                "rsi":           rsi,
                "tendencia":     tend,
                "vol_ratio":     vol_r,
                "score_base":    score_base,
                "rango_entrar":  rango_entrar,
                "rango_vigilar": rango_vigilar,
                "puede_entrar":  puede_entrar,
                "puede_vigilar": puede_vigilar,
            }

            # Log claro en Railway
            if puede_entrar:
                estado_dia = f"🟢 puede ENTRAR si precio < ${rango_entrar}"
            elif puede_vigilar:
                estado_dia = f"🟡 puede VIGILAR si precio < ${rango_vigilar}"
            else:
                estado_dia = "⚪ NEUTRAL fijo hoy (score_base insuficiente)"

            print(f"    {ticker}: score_base={score_base} | RSI={rsi} | {estado_dia}")

        except Exception as e:
            print(f"    ❌ Error precalculando {ticker}: {e}")
            continue

    if not rangos_hoy:
        return None

    resultado = {
        "fecha":        hoy,
        "rangos":       rangos_hoy,
        "calculado_a":  hora_colombia().strftime("%Y-%m-%d %H:%M"),
        "portafolio":   portafolio.get("nombre", ""),
    }

    # Guardar en disco — sobrevive reinicios de Railway
    ruta = os.path.join(PORTS_DIR, f"rangos_{archivo}")
    try:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(resultado, f, indent=2, ensure_ascii=False)
        print(f"  ✅ Rangos guardados: {len(rangos_hoy)} activos")
    except Exception as e:
        print(f"  ❌ Error guardando rangos: {e}")

    return resultado

# ─────────────────────────────────────────────────────────────
# VIGILAR PRECIOS — corre cada 9 segundos durante el mercado
# ─────────────────────────────────────────────────────────────

def vigilar_precios(archivo, portafolio, rangos_del_dia):
    """
    Solo consulta precio actual a Finnhub.
    Compara precio vs rangos precalculados a las 8am.
    Si el precio cruza un rango → alerta Telegram inmediata.
    Guarda precios actualizados en estado para el display.
    """
    if not rangos_del_dia:
        return

    estado  = leer_estado(archivo)
    chat_id = chat_id_de(portafolio)
    hoy_str = hora_colombia().strftime("%Y-%m-%d")

    if "resultados_rt" not in estado:
        estado["resultados_rt"] = {}

    for ticker, rango in rangos_del_dia["rangos"].items():

        # ── Solo precio — una petición a Finnhub ──────────────
        quote = finnhub_quote(ticker)
        if not quote:
            continue

        precio = float(quote["c"])
        cambio = float(quote.get("dp", 0))

        # ── Determinar señal con rangos precalculados ──────────
        rango_entrar  = rango.get("rango_entrar")
        rango_vigilar = rango.get("rango_vigilar")

        if rango_entrar and precio < rango_entrar:
            senal_actual = "ENTRAR"
        elif rango_vigilar and precio < rango_vigilar:
            senal_actual = "VIGILAR"
        else:
            senal_actual = "NEUTRAL"

        # Score real con precio actual (para mostrar en display)
        score = rango["score_base"]
        if precio < rango["ma20"]:   score += 2.0
        elif precio < rango["ma50"]: score += 1.0
        score = round(min(score, 10.0), 1)

        # ── Actualizar estado para el display ─────────────────
        # El display lee esto cada vez que el browser pide /api/precios-rt
        estado["resultados_rt"][ticker] = {
            "ticker":        ticker,
            "precio":        round(precio, 2),
            "cambio_dia":    round(cambio, 2),
            "ma20":          rango["ma20"],
            "ma50":          rango["ma50"],
            "rsi":           rango["rsi"],
            "tendencia":     rango["tendencia"],
            "vol_ratio":     rango["vol_ratio"],
            "score_base":    rango["score_base"],
            "score":         score,
            "senal":         senal_actual,
            "rango_entrar":  rango_entrar,
            "rango_vigilar": rango_vigilar,
            "puede_entrar":  rango["puede_entrar"],
            "puede_vigilar": rango["puede_vigilar"],
            "timestamp":     hora_colombia().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # ── Alertas — solo si la señal es ENTRAR ──────────────
        if senal_actual == "ENTRAR":
            dec = decision_usuario(estado, ticker)

            # Silenciar según decisión del usuario
            if dec == "no_entro":
                continue
            if dec == "entro":
                continue

            # Anti-spam: máximo 3 alertas sin respuesta
            if ya_alerte_hoy(estado, ticker) and dec != "sigue":
                clave  = f"ciclos_sin_respuesta_{ticker}"
                ciclos = estado.get(clave, 0) + 1
                estado[clave] = ciclos
                if ciclos >= 3:
                    continue

            # Construir y enviar alerta
            msg = (
                f"🟢 <b>SEÑAL DE ENTRADA — {ticker}</b>\n\n"
                f"💵 Precio: <b>${precio:,.2f} USD</b> ({cambio:+.2f}% hoy)\n"
                f"🎯 Cruzó el rango de entrada (< ${rango_entrar:,.2f})\n\n"
                f"📊 Score: <b>{score}/10</b> · RSI: {rango['rsi']} · "
                f"Tendencia: {rango['tendencia']:+.1f}%\n"
                f"📈 MA20: ${rango['ma20']:,.2f} · MA50: ${rango['ma50']:,.2f}"
            )
            if dec == "sigue":
                msg += "\n\n<i>(Actualización — pediste seguir informado)</i>"

            telegram(chat_id, msg, reply_markup=teclado_decision(ticker))
            marcar_alerta_enviada(estado, ticker)
            estado[f"ciclos_sin_respuesta_{ticker}"] = 0
            print(f"  🟢 ALERTA: {ticker} @ ${precio} cruzó rango ${rango_entrar}")

    # Actualizar contadores de días sin señal
    hay_entradas = any(
        v.get("senal") == "ENTRAR"
        for v in estado["resultados_rt"].values()
    )
    if hay_entradas:
        estado["ultimo_dia_con_senal"]       = hoy_str
        estado["dias_consecutivos_sin_senal"] = 0
    else:
        ultimo = estado.get("ultimo_dia_con_senal")
        if ultimo and ultimo != hoy_str:
            try:
                dias = sum(
                    1 for i in range(
                        (datetime.strptime(hoy_str, "%Y-%m-%d") -
                         datetime.strptime(ultimo, "%Y-%m-%d")).days
                    )
                    if (datetime.strptime(ultimo, "%Y-%m-%d") +
                        timedelta(days=i+1)).weekday() < 5
                )
                estado["dias_consecutivos_sin_senal"] = dias
            except:
                pass

    # Predicción para el display
    vigilando = [
        t for t, v in estado["resultados_rt"].items()
        if v.get("senal") == "VIGILAR"
    ]
    entrando = [
        t for t, v in estado["resultados_rt"].items()
        if v.get("senal") == "ENTRAR"
    ]
    if entrando:
        estado["prediccion"] = f"🟢 {len(entrando)} entrada(s) detectada(s)"
    elif vigilando:
        estado["prediccion"] = f"👁 {len(vigilando)} en vigilancia"
    else:
        estado["prediccion"] = "⚪ Sin señales este ciclo"

    estado["timestamp"]         = hora_colombia().strftime("%Y-%m-%d %H:%M:%S")
    estado["nombre_portafolio"] = portafolio.get("nombre", "")

    # Convertir resultados_rt a lista para compatibilidad con display existente
    estado["resultados"] = list(estado["resultados_rt"].values())

    guardar_estado(archivo, estado)

# ─────────────────────────────────────────────────────────────
# CONTROL DE ALERTAS
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
                f"- {r['ticker']}: ${r['precio']} | RSI {r['rsi']} | "
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
                f"Recomendación especial, máximo 4 párrafos. Sin asteriscos."
            )
        elif tipo == "buenos_dias":
            tickers = list(portafolio.get("composicion", {}).keys())
            prompt = (
                f"Analista de {portafolio['propietario']}. "
                f"8:15am Colombia, NYSE abre en 15 minutos.\n"
                f"PORTAFOLIO: {', '.join(tickers)}\n"
                f"UN párrafo de buenos días, máximo 3 oraciones. Sin asteriscos."
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
        if not fn.endswith(".json") or fn.startswith("monitor_") or fn.startswith("rangos_"):
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
        print(f"⚠️ chat_id error: {e}")
    cid = portafolio.get("telegram_chat_id", "").strip()
    if cid:
        return cid
    print(f"⚠️ Sin chat_id para: {portafolio.get('nombre','?')}")
    return ""

# ─────────────────────────────────────────────────────────────
# BUENOS DÍAS
# ─────────────────────────────────────────────────────────────

def enviar_buenos_dias(archivo, portafolio):
    chat_id = chat_id_de(portafolio)
    if not chat_id:
        return

    # Leer rangos precalculados para incluir en el mensaje
    rangos     = _cargar_rangos_disco(archivo)
    tickers    = list(portafolio.get("composicion", {}).keys())
    nombre_port = portafolio.get("nombre", "tu portafolio")
    ahora      = hora_colombia()
    dia_semana = ["lunes", "martes", "miércoles", "jueves", "viernes"][ahora.weekday()]

    # Resumen de rangos del día
    resumen_rangos = ""
    if rangos:
        for ticker, r in rangos["rangos"].items():
            if r["puede_entrar"]:
                resumen_rangos += f"  🟢 {ticker}: entraría si cae bajo ${r['rango_entrar']:,.2f}\n"
            elif r["puede_vigilar"]:
                resumen_rangos += f"  🟡 {ticker}: vigilar si cae bajo ${r['rango_vigilar']:,.2f}\n"
            else:
                resumen_rangos += f"  ⚪ {ticker}: NEUTRAL hoy (indicadores no favorables)\n"

    msg = (
        f"☀️ <b>Buenos días — {dia_semana} {ahora.strftime('%d/%m')}</b>\n\n"
        f"📋 Portafolio: <b>{nombre_port}</b>\n\n"
        f"<b>Rangos calculados para hoy:</b>\n{resumen_rangos}\n"
        f"🔍 Monitoreando cada 9 segundos de 8:30am a 3:00pm.\n"
        f"Te aviso al instante si algún precio cruza su rango.\n\n"
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

def _cargar_rangos_disco(archivo):
    """Lee los rangos guardados en disco para este portafolio."""
    hoy  = hora_colombia().strftime("%Y-%m-%d")
    ruta = os.path.join(PORTS_DIR, f"rangos_{archivo}")
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            r = json.load(f)
        return r if r.get("fecha") == hoy else None
    except:
        return None

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

    lineas = [
        f"📋 <b>REPORTE DE CIERRE — {portafolio['nombre']}</b>",
        f"📅 {hoy_str}\n"
    ]
    for r in sorted(resultados, key=lambda x: x["score"], reverse=True):
        emoji      = {"ENTRAR": "🟢", "VIGILAR": "🟡", "NEUTRAL": "⚪"}.get(r["senal"], "⚪")
        cambio_str = f" ({r['cambio_dia']:+.2f}%)" if r.get("cambio_dia") is not None else ""
        lineas.append(
            f"{emoji} <b>{r['ticker']}</b> ${r['precio']:,.2f}{cambio_str}\n"
            f"   Score {r['score']}/10 | RSI {r['rsi']} | {r['tendencia']:+.1f}%"
        )

    entradas = [r for r in resultados if r["senal"] == "ENTRAR"]
    lineas.append(
        f"\n🎯 Señales hoy: {', '.join(r['ticker'] for r in entradas)}"
        if entradas else "\n⚪ Sin señales de entrada hoy"
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

    # Limpiar alertas del día
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
# WEBHOOK DE TELEGRAM
# ─────────────────────────────────────────────────────────────

def procesar_callback_telegram(callback_data, chat_id):
    """
    Procesa los botones inline del usuario.
    callback_data: "entro:AAPL", "no_entro:AAPL", "sigue:AAPL"
    """
    try:
        partes   = callback_data.split(":", 1)
        decision = partes[0]
        ticker   = partes[1] if len(partes) > 1 else ""
        if not ticker:
            return

        for fn in os.listdir(PORTS_DIR):
            if not fn.endswith(".json") or fn.startswith("monitor_") or fn.startswith("rangos_"):
                continue
            try:
                with open(os.path.join(PORTS_DIR, fn), "r", encoding="utf-8") as f:
                    p = json.load(f)
                if chat_id_de(p) == str(chat_id):
                    registrar_decision(fn, ticker, decision)
                    mensajes = {
                        "entro":    f"✅ Registrado: entraste a <b>{ticker}</b>. No te molesto más hoy.",
                        "no_entro": f"❌ Ok, no te aviso más de <b>{ticker}</b> hoy.",
                        "sigue":    f"📊 Perfecto, te aviso si el precio de <b>{ticker}</b> mejora."
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
    """
    Estados del loop:
    8:00am-8:10am  →  precalcular_rangos() UNA VEZ
    8:15am-8:25am  →  enviar buenos días
    8:30am-3:00pm  →  vigilar_precios() cada 9 segundos
    3:00pm-3:45pm  →  reporte de cierre
    resto          →  dormir hasta las 8am del próximo día hábil
    """
    buenos_enviado    = {}   # archivo → fecha último buenos días
    rangos_calculados = {}   # archivo → rangos del día (en RAM como caché)
    precalculo_hecho  = {}   # archivo → fecha del último precálculo
    cierre_enviado    = {}   # archivo → fecha del último cierre

    while True:
        try:
            portafolios = leer_portafolios_activos()
            ahora       = hora_colombia()
            hoy         = ahora.strftime("%Y-%m-%d")

            # ── Cargar rangos desde disco si Railway reinició ──
            # Esto corre siempre — si ya están en RAM no hace nada
            for archivo, _ in portafolios:
                if archivo not in rangos_calculados:
                    rangos = _cargar_rangos_disco(archivo)
                    if rangos:
                        rangos_calculados[archivo] = rangos
                        precalculo_hecho[archivo]  = hoy
                        print(f"  📂 Rangos cargados desde disco: {archivo}")

            # ── 8:00am — Precálculo de rangos ─────────────────
            if es_hora_precalculo():
                for archivo, _ in portafolios:
                    if precalculo_hecho.get(archivo) != hoy:
                        try:
                            with open(os.path.join(PORTS_DIR, archivo), "r", encoding="utf-8") as f:
                                pf = json.load(f)
                            resultado = precalcular_rangos(archivo, pf)
                            if resultado:
                                rangos_calculados[archivo] = resultado
                                precalculo_hecho[archivo]  = hoy
                        except Exception as e:
                            print(f"❌ Error precálculo {archivo}: {e}")
                time.sleep(60)

            # ── 8:15am — Buenos días ───────────────────────────
            elif es_hora_buenos_dias():
                for archivo, _ in portafolios:
                    if buenos_enviado.get(archivo) != hoy:
                        try:
                            with open(os.path.join(PORTS_DIR, archivo), "r", encoding="utf-8") as f:
                                pf = json.load(f)
                            enviar_buenos_dias(archivo, pf)
                        except Exception as e:
                            print(f"❌ Error buenos días {archivo}: {e}")
                        buenos_enviado[archivo] = hoy
                time.sleep(60)

            # ── 8:30am-3:00pm — Vigilancia cada 9 segundos ────
            elif mercado_abierto():
                for archivo, _ in portafolios:
                    rangos = rangos_calculados.get(archivo)
                    if not rangos:
                        print(f"  ⚠️ Sin rangos para {archivo} — esperando precálculo")
                        continue
                    try:
                        with open(os.path.join(PORTS_DIR, archivo), "r", encoding="utf-8") as f:
                            pf = json.load(f)
                        vigilar_precios(archivo, pf, rangos)
                        # Verificar alerta subóptima
                        estado = leer_estado(archivo)
                        verificar_alerta_suboptimal(archivo, pf, estado)
                    except Exception as e:
                        print(f"❌ Error vigilando {archivo}: {e}")

                time.sleep(9)   # ← cada 9 segundos

            # ── 4:00pm — Reporte de cierre ─────────────────────
            elif es_hora_cierre():
                for archivo, _ in portafolios:
                    if cierre_enviado.get(archivo) != hoy:
                        try:
                            with open(os.path.join(PORTS_DIR, archivo), "r", encoding="utf-8") as f:
                                pf = json.load(f)
                            estado = leer_estado(archivo)
                            reporte_cierre(archivo, pf, estado)
                            cierre_enviado[archivo] = hoy
                        except Exception as e:
                            print(f"❌ Error cierre {archivo}: {e}")
                time.sleep(60)

            # ── Mercado cerrado — dormir ───────────────────────
            else:
                segs = segundos_hasta_precalculo()
                horas = segs / 3600
                print(f"💤 Mercado cerrado. Próximo precálculo en {horas:.1f}h")
                time.sleep(min(segs, 300))   # máximo 5 minutos por si Railway reinicia

        except Exception as e:
            print(f"❌ Error loop monitor: {e}")
            time.sleep(60)