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

  8:30am-3:00pm →  vigilar_precios()  CADA ~10-15 SEGUNDOS
                   Solo consulta precio actual a Finnhub
                   Compara precio vs rangos precalculados
                   Si cruza un rango → alerta Telegram inmediata
                   Guarda precio actualizado → el display lo lee

  3:00pm        →  reporte de cierre

FUENTES DE DATOS:
─────────────────────────────────────────────
  Finnhub  →  precio actual TIEMPO REAL cada ~10-15 segundos
  yfinance →  histórico 90 días UNA VEZ a las 8am
"""

import os, json, time, threading, requests
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from zoneinfo import ZoneInfo
import warnings

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATOS_DIR = os.path.join(BASE_DIR, "datos")
PORTS_DIR = os.path.join(DATOS_DIR, "portafolios")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")

UMBRAL_ENTRADA = 6.5
UMBRAL_VIGILAR = 4.5
DIAS_SIN_SENAL_MAX = 5
K_BOLLINGER = (
    2.0  # ancho de la banda inferior (σ). Subir = triggers más profundos/raros
)
PERSIST_POLLS = 3  # polls consecutivos bajo el rango antes de alertar (~30s)
REBOTE_MIN = 0.005  # rebote mínimo desde el mínimo intradía antes de alertar (0.5%)

# ── Lotes de alerta "ENTRAR" — espaciados por tiempo real, no por ciclos ──
TAMANO_LOTE_ALERTA = 3
INTERVALO_LOTE_ORIGINAL_MIN = 15
INTERVALO_LOTE_SIGUE_MIN = 20

COINGECKO_MAP = {
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
    "SOL-USD": "solana",
    "BNB-USD": "binancecoin",
    "XRP-USD": "ripple",
    "ADA-USD": "cardano",
    "DOGE-USD": "dogecoin",
    "AVAX-USD": "avalanche-2",
    "DOT-USD": "polkadot",
    "LTC-USD": "litecoin",
    "LINK-USD": "chainlink",
}

# ─────────────────────────────────────────────────────────────
# ZONAS HORARIAS
# ─────────────────────────────────────────────────────────────

TZ_COLOMBIA = ZoneInfo("America/Bogota")
TZ_NUEVA_YORK = ZoneInfo("America/New_York")


def hora_colombia():
    """Hora actual en Colombia (maneja DST automáticamente)."""
    return datetime.now(TZ_COLOMBIA)


def hora_nueva_york():
    """Hora actual en Nueva York (maneja DST automáticamente)."""
    return datetime.now(TZ_NUEVA_YORK)


# ─────────────────────────────────────────────────────────────
# FUNCIONES DE TIEMPO
# ─────────────────────────────────────────────────────────────


def _en_ventana(h_ini, m_ini, h_fin, m_fin, tz=TZ_COLOMBIA):
    ahora = datetime.now(tz)
    if ahora.weekday() >= 5:
        return False
    inicio = ahora.replace(hour=h_ini, minute=m_ini, second=0, microsecond=0)
    fin = ahora.replace(hour=h_fin, minute=m_fin, second=0, microsecond=0)
    return inicio <= ahora <= fin


def mercado_abierto():
    """
    NYSE abre 9:30am–3:00pm hora Colombia (ajustado para cuenta individual).
    Usa hora Nueva York para manejar DST correctamente.
    """
    ahora_ny = hora_nueva_york()
    if ahora_ny.weekday() >= 5:
        return False
    apertura = ahora_ny.replace(hour=9, minute=30, second=0, microsecond=0)
    cierre = ahora_ny.replace(hour=16, minute=0, second=0, microsecond=0)
    return apertura <= ahora_ny <= cierre


# True entre 8:00am y 8:10am hora Colombia. Ventana para descargar histórico y calcular rangos del día.
def es_hora_precalculo():
    return _en_ventana(8, 0, 8, 10)


# True entre 8:15am y 8:25am hora Colombia.
def es_hora_buenos_dias():
    return _en_ventana(8, 15, 8, 25)


# True entre 4:00pm y 4:45pm hora Nueva York.
def es_hora_cierre():
    return _en_ventana(16, 0, 16, 45, tz=TZ_NUEVA_YORK)


def _es_portafolio_real(fn):
    return fn.endswith(".json") and not fn.startswith(("monitor_", "rangos_"))


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
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10,
        )
    except Exception as e:
        print(f"❌ Telegram error: {e}")


def teclado_decision(ticker):
    """Botones inline para que el usuario responda a una alerta."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Ya entré", "callback_data": f"entro:{ticker}"},
                {"text": "❌ No voy a entrar", "callback_data": f"no_entro:{ticker}"},
                {"text": "📊 Sigue informando", "callback_data": f"sigue:{ticker}"},
            ]
        ]
    }


# ─────────────────────────────────────────────────────────────
# COINGECKO — PRECIO EN TIEMPO REAL
# ─────────────────────────────────────────────────────────────


def coingecko_quote(ticker):
    """Precio crypto desde CoinGecko — gratis, sin API key."""
    coin_id = COINGECKO_MAP.get(ticker)
    if not coin_id:
        return None
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json().get(coin_id, {})
        precio = data.get("usd", 0)
        cambio = data.get("usd_24h_change", 0)
        if not precio:
            print(f"⚠️ CoinGecko sin precio para {ticker}")
            return None
        # Retorna formato compatible con finnhub_quote
        return {"c": precio, "dp": round(cambio, 2)}
    except Exception as e:
        print(f"❌ CoinGecko error ({ticker}): {e}")
        return None


# ─────────────────────────────────────────────────────────────
# FINNHUB — PRECIO EN TIEMPO REAL
# ─────────────────────────────────────────────────────────────


def finnhub_quote(ticker):
    """
    Precio en tiempo real desde Finnhub (plan Free).
    Retorna dict con: c=precio actual, o=apertura, h=max, l=min,
                      pc=cierre anterior, dp=cambio %
    """
    if ticker in COINGECKO_MAP:
        return coingecko_quote(ticker)

    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
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
        hoy = datetime.now(timezone.utc)
        inicio = (hoy - timedelta(days=dias)).strftime("%Y-%m-%d")
        df = yf.download(
            ticker,
            start=inicio,
            end=hoy.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=True,
            progress=False,
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
# INDICADORES TÉCNICOS
# ─────────────────────────────────────────────────────────────


def _macd_bollinger(close, k=K_BOLLINGER):
    """Banda inferior de Bollinger y dirección del histograma MACD.

    Devuelve (banda_inferior, histograma_actual, histograma_subiendo).
    - banda_inferior = MA20 - k·σ20  → trigger de entrada adaptado a la
      volatilidad de cada activo (BTC no dispara con 2%, AAPL sí).
    - histograma_subiendo = el momentum ya está girando al alza (MACD hist
      del último día > el del día anterior). Confirmación anti-cuchillo.
    """
    ma20 = close.rolling(20).mean().iloc[-1]
    std20 = close.rolling(20).std().iloc[-1]
    banda_inf = float(ma20 - k * std20)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    hist = macd_line - macd_line.ewm(span=9, adjust=False).mean()
    return banda_inf, float(hist.iloc[-1]), bool(hist.iloc[-1] > hist.iloc[-2])


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
    tickers = list(composicion.keys())
    if not tickers:
        return None

    print(f"  📐 Precalculando rangos para {portafolio['nombre']}...")
    rangos_hoy = {}
    hoy = hora_colombia().strftime("%Y-%m-%d")

    for ticker in tickers:
        try:
            # Descarga histórico — solo aquí, solo a las 8am
            df = yfinance_historico(ticker, dias=90)
            if df is None:
                print(f"    ⚠️ Sin histórico para {ticker} — omitiendo")
                continue

            close = df["Close"].squeeze()
            volume = (
                df["Volume"].squeeze()
                if "Volume" in df.columns
                else pd.Series([1] * len(df))
            )

            # ── Indicadores fijos — no cambian durante el día ──

            ma20 = float(close.rolling(20).mean().iloc[-1])
            ma50 = (
                float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else ma20
            )

            # Tendencia: % cambio últimos 20 días
            tend = round(
                (
                    (float(close.iloc[-1]) - float(close.iloc[-20]))
                    / float(close.iloc[-20])
                )
                * 100,
                2,
            )

            # Volumen ratio
            vol_media = float(volume.rolling(20).mean().iloc[-1])
            vol_r = (
                round(float(volume.iloc[-1]) / vol_media, 2) if vol_media > 0 else 1.0
            )

            # RSI 14 períodos
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss.replace(0, 1e-9)
            rsi = round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

            # ── Score base — sin precio vs medias ──────────────
            # RSI + tendencia + volumen (los 3 fijos)
            score_base = 0.0
            if rsi < 30:
                score_base += 3.0
            elif rsi < 45:
                score_base += 2.5
            elif rsi < 55:
                score_base += 1.5
            elif rsi < 65:
                score_base += 0.5
            if -10 <= tend <= -3:
                score_base += 2.5
            elif -3 < tend <= 0:
                score_base += 1.5
            elif 0 < tend <= 3:
                score_base += 1.0
            elif tend < -10:
                score_base += 1.5
            if vol_r > 1.5:
                score_base += 0.5
            score_base = round(score_base, 1)

            # ── Bollinger inferior + confirmación MACD ─────────
            banda_inf, macd_hist, hist_subiendo = _macd_bollinger(close)

            # ── Rangos de precio ───────────────────────────────
            # ENTRAR exige score suficiente Y momentum girando (MACD).
            # El trigger es la banda inferior de Bollinger — se adapta a la
            # volatilidad de cada activo, no la MA20 fija.
            # ponytail: MACD es un gate duro. Si te quedas sin señales,
            # cambiar "and hist_subiendo" por sumar +0.5 al score_base.
            puede_entrar = (score_base + 2.0) >= UMBRAL_ENTRADA and hist_subiendo
            puede_vigilar = (score_base + 1.0) >= UMBRAL_VIGILAR

            rango_entrar = round(banda_inf, 2) if puede_entrar else None
            rango_vigilar = round(ma50, 2) if puede_vigilar else None

            rangos_hoy[ticker] = {
                "ma20": round(ma20, 2),
                "ma50": round(ma50, 2),
                "banda_inf": round(banda_inf, 2),
                "rsi": rsi,
                "tendencia": tend,
                "vol_ratio": vol_r,
                "macd_hist": round(macd_hist, 4),
                "hist_subiendo": hist_subiendo,
                "score_base": score_base,
                "rango_entrar": rango_entrar,
                "rango_vigilar": rango_vigilar,
                "puede_entrar": puede_entrar,
                "puede_vigilar": puede_vigilar,
            }

            # Log claro en Railway
            if puede_entrar:
                estado_dia = f"🟢 puede ENTRAR si precio < ${rango_entrar} (banda inf, momentum ↑)"
            elif puede_vigilar:
                estado_dia = f"🟡 puede VIGILAR si precio < ${rango_vigilar}"
            else:
                motivo = "momentum ↓" if not hist_subiendo else "score bajo"
                estado_dia = f"⚪ NEUTRAL fijo hoy ({motivo})"

            print(f"    {ticker}: score_base={score_base} | RSI={rsi} | {estado_dia}")

        except Exception as e:
            print(f"    ❌ Error precalculando {ticker}: {e}")
            continue

    if not rangos_hoy:
        return None

    resultado = {
        "fecha": hoy,
        "rangos": rangos_hoy,
        "calculado_a": hora_colombia().strftime("%Y-%m-%d %H:%M"),
        "portafolio": portafolio.get("nombre", ""),
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
# VIGILAR PRECIOS — corre cada ~10-15 segundos durante el mercado
# ─────────────────────────────────────────────────────────────


def vigilar_precios(archivo, portafolio, rangos_del_dia, precios_cache=None):
    """
    Solo consulta precio actual a Finnhub.
    Compara precio vs rangos precalculados a las 8am.
    Si el precio cruza un rango → alerta Telegram inmediata.
    Guarda precios actualizados en estado para el display.
    """
    if not rangos_del_dia:
        return

    # Import perezoso — mismo patrón que chat_id_de() usa para get_usuario,
    # evita cualquier problema de import circular a nivel de módulo.
    from gestor_portafolio import _LOCK_MONITOR

    with _LOCK_MONITOR:
        estado = leer_estado(archivo)
        chat_id = chat_id_de(portafolio)
        hoy_str = hora_colombia().strftime("%Y-%m-%d")

        if "resultados_rt" not in estado:
            estado["resultados_rt"] = {}

        # Reset de mínimos, persistencia y lotes de alerta al cambiar de día
        if estado.get("dia_intradia") != hoy_str:
            for k in [
                k
                for k in estado
                if k.startswith(("min_intradia_", "persist_entrar_"))
            ]:
                del estado[k]
            estado["lotes_alerta"] = {}
            estado["dia_intradia"] = hoy_str

        for ticker, rango in rangos_del_dia["rangos"].items():

            # ── Solo precio — una petición a Finnhub ──────────────
            # Usar precio del cache — ya consultado una vez arriba
            quote = precios_cache.get(ticker) if precios_cache else finnhub_quote(ticker)
            if not quote:
                continue

            precio = float(quote["c"])
            cambio = float(quote.get("dp", 0))

            # ── Mínimo intradía + rebote ──────────────────────────
            # Mientras haga nuevos mínimos, NO alertamos (aún está cayendo).
            min_key = f"min_intradia_{ticker}"
            if estado.get(min_key) is None or precio < estado[min_key]:
                estado[min_key] = precio
            min_dia = estado[min_key]
            rebote = (precio - min_dia) / min_dia if min_dia else 0.0

            # ── [temporal] ¿el gate de MACD tapó una señal real? ──
            # Cuenta 1x por ticker/día cuando el precio SÍ tocó la banda
            # y lo único que faltó para ENTRAR fue el MACD subiendo.
            if (
                not rango.get("puede_entrar")
                and rango.get("score_base", 0) >= UMBRAL_ENTRADA - 2.0
                and not rango.get("hist_subiendo")
                and rango.get("banda_inf")
                and precio < rango["banda_inf"]
            ):
                vetos = estado.setdefault("macd_vetos", {})
                if vetos.get(ticker) != hoy_str:
                    vetos[ticker] = hoy_str
                    estado["macd_vetos_total"] = estado.get("macd_vetos_total", 0) + 1
                    print(f"  🔬 MACD-veto: {ticker} @ ${precio:.2f} < banda "
                          f"${rango['banda_inf']:.2f} (score {rango['score_base']}, "
                          f"total={estado['macd_vetos_total']})")

            # ── Determinar señal con rangos precalculados ──────────
            rango_entrar = rango.get("rango_entrar")
            rango_vigilar = rango.get("rango_vigilar")

            if rango_entrar and precio < rango_entrar:
                senal_actual = "ENTRAR"
            elif rango_vigilar and precio < rango_vigilar:
                senal_actual = "VIGILAR"
            else:
                senal_actual = "NEUTRAL"

            # ── Persistencia: N polls consecutivos en ENTRAR ──────
            # Filtra ticks malos de Finnhub y flash-dips de un solo ciclo.
            clave_persist = f"persist_entrar_{ticker}"
            if senal_actual == "ENTRAR":
                estado[clave_persist] = estado.get(clave_persist, 0) + 1
            else:
                estado[clave_persist] = 0

            # Score real con precio actual (para mostrar en display)
            score = rango["score_base"]
            if precio < rango["ma20"]:
                score += 2.0
            elif precio < rango["ma50"]:
                score += 1.0
            score = round(min(score, 10.0), 1)

            # ── Actualizar estado para el display ─────────────────
            # El display lee esto cada vez que el browser pide /api/precios-rt
            estado["resultados_rt"][ticker] = {
                "ticker": ticker,
                "precio": round(precio, 2),
                "cambio_dia": round(cambio, 2),
                "ma20": rango["ma20"],
                "ma50": rango["ma50"],
                "banda_inf": rango.get("banda_inf"),
                "rsi": rango["rsi"],
                "tendencia": rango["tendencia"],
                "vol_ratio": rango["vol_ratio"],
                "macd_hist": rango.get("macd_hist"),
                "hist_subiendo": rango.get("hist_subiendo"),
                "score_base": rango["score_base"],
                "score": score,
                "senal": senal_actual,
                "rango_entrar": rango_entrar,
                "rango_vigilar": rango_vigilar,
                "puede_entrar": rango["puede_entrar"],
                "puede_vigilar": rango["puede_vigilar"],
                "timestamp": hora_colombia().strftime("%Y-%m-%d %H:%M:%S"),
            }

            # ── Alertas — solo si la señal es ENTRAR ──────────────
            if (
                senal_actual == "ENTRAR"
                and chat_id
                and estado.get(clave_persist, 0) >= PERSIST_POLLS
                and rebote >= REBOTE_MIN
            ):
                dec = decision_usuario(estado, ticker)

                # Silenciar según decisión del usuario
                if dec in ("no_entro", "entro"):
                    continue

                # ── Lotes de alerta espaciados por tiempo real ─────
                # Máximo TAMANO_LOTE_ALERTA alertas por lote. Al agotar el
                # lote se re-pregunta con teclado_decision en vez de quedar
                # en silencio o spamear cada ciclo del loop (~10-40s).
                lote = estado.setdefault("lotes_alerta", {}).setdefault(
                    ticker,
                    {
                        "enviadas": 0,
                        "ultima_alerta_ts": None,
                        "origen": "original",
                        "prompt_pendiente": False,
                    },
                )

                # Ya se agotó el lote y se re-preguntó — esperar respuesta
                if lote["prompt_pendiente"]:
                    continue

                # Espaciado por tiempo real (no por ciclos del loop)
                intervalo_min = (
                    INTERVALO_LOTE_SIGUE_MIN
                    if lote["origen"] == "sigue"
                    else INTERVALO_LOTE_ORIGINAL_MIN
                )
                if lote["ultima_alerta_ts"] is not None:
                    transcurrido = hora_colombia() - datetime.fromisoformat(
                        lote["ultima_alerta_ts"]
                    )
                    if transcurrido.total_seconds() < intervalo_min * 60:
                        continue

                # Construir y enviar alerta
                msg = (
                    f"🟢 <b>SEÑAL DE ENTRADA — {ticker}</b>\n\n"
                    f"💵 Precio: <b>${precio:,.2f} USD</b> ({cambio:+.2f}% hoy)\n"
                    f"🎯 Cruzó la banda inferior Bollinger (&lt; ${rango_entrar:,.2f})\n"
                    f"📉 Momentum MACD girando al alza ✓\n"
                    f"📈 Rebotó {rebote*100:.1f}% desde el mínimo de hoy (${min_dia:,.2f})\n\n"
                    f"📊 Score: <b>{score}/10</b> · RSI: {rango['rsi']} · "
                    f"Tendencia: {rango['tendencia']:+.1f}%\n"
                    f"📈 MA20: ${rango['ma20']:,.2f} · MA50: ${rango['ma50']:,.2f}"
                )
                if lote["origen"] == "sigue":
                    msg += "\n\n<i>(Actualización — pediste seguir informado)</i>"

                print(f"  📨 Intentando enviar alerta a chat_id='{chat_id}' para {ticker}")
                telegram(chat_id, msg, reply_markup=teclado_decision(ticker))
                print(f"  🟢 ALERTA: {ticker} @ ${precio} cruzó rango ${rango_entrar}")

                lote["enviadas"] += 1
                lote["ultima_alerta_ts"] = hora_colombia().isoformat()

                if lote["enviadas"] >= TAMANO_LOTE_ALERTA:
                    telegram(
                        chat_id,
                        f"🔁 <b>{ticker}</b> sigue en rango de entrada — van "
                        f"{TAMANO_LOTE_ALERTA} avisos.\n¿Sigo informando?",
                        reply_markup=teclado_decision(ticker),
                    )
                    lote["prompt_pendiente"] = True
                    print(f"  🔁 Re-pregunta enviada para {ticker} tras {TAMANO_LOTE_ALERTA} avisos")

        # Actualizar contadores de días sin señal
        hay_entradas = any(
            v.get("senal") == "ENTRAR" for v in estado["resultados_rt"].values()
        )
        if hay_entradas:
            estado["ultimo_dia_con_senal"] = hoy_str
            estado["dias_consecutivos_sin_senal"] = 0
        else:
            ultimo = estado.get("ultimo_dia_con_senal")
            if ultimo and ultimo != hoy_str:
                try:
                    d_hoy = datetime.strptime(hoy_str, "%Y-%m-%d")
                    d_ult = datetime.strptime(ultimo, "%Y-%m-%d")
                    dias = sum(
                        1
                        for i in range((d_hoy - d_ult).days)
                        if (d_ult + timedelta(days=i + 1)).weekday() < 5
                    )
                    estado["dias_consecutivos_sin_senal"] = dias
                except:
                    pass

        # Predicción para el display
        vigilando = [
            t for t, v in estado["resultados_rt"].items() if v.get("senal") == "VIGILAR"
        ]
        entrando = [
            t for t, v in estado["resultados_rt"].items() if v.get("senal") == "ENTRAR"
        ]
        if entrando:
            estado["prediccion"] = f"🟢 {len(entrando)} entrada(s) detectada(s)"
        elif vigilando:
            estado["prediccion"] = f"👁 {len(vigilando)} en vigilancia"
        else:
            estado["prediccion"] = "⚪ Sin señales este ciclo"

        estado["timestamp"] = hora_colombia().strftime("%Y-%m-%d %H:%M:%S")
        estado["nombre_portafolio"] = portafolio.get("nombre", "")

        # Convertir resultados_rt a lista para compatibilidad con display existente
        estado["resultados"] = list(estado["resultados_rt"].values())

        guardar_estado(archivo, estado)


# ─────────────────────────────────────────────────────────────
# CONTROL DE ALERTAS
# ─────────────────────────────────────────────────────────────


def decision_usuario(estado, ticker):
    """Retorna 'entro', 'no_entro', 'sigue', o None."""
    hoy = hora_colombia().strftime("%Y-%m-%d")
    decisiones = estado.get("decisiones_usuario", {})
    entrada = decisiones.get(ticker, {})
    if entrada.get("fecha") == hoy:
        return entrada.get("decision")
    return None


def registrar_decision(archivo, ticker, decision):
    """Guarda la decisión del usuario. Llamado desde el webhook de Telegram."""
    # Import perezoso — mismo patrón que chat_id_de() usa para get_usuario.
    from gestor_portafolio import _LOCK_MONITOR

    with _LOCK_MONITOR:
        estado = leer_estado(archivo)
        hoy = hora_colombia().strftime("%Y-%m-%d")
        if "decisiones_usuario" not in estado:
            estado["decisiones_usuario"] = {}
        estado["decisiones_usuario"][ticker] = {"decision": decision, "fecha": hoy}

        if decision == "sigue":
            # Reabre un lote NUEVO de alertas para este ticker, espaciado
            # por INTERVALO_LOTE_SIGUE_MIN en vez del intervalo original.
            lote = estado.setdefault("lotes_alerta", {}).setdefault(ticker, {})
            lote["enviadas"] = 0
            lote["ultima_alerta_ts"] = None
            lote["origen"] = "sigue"
            lote["prompt_pendiente"] = False

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
            messages=[{"role": "user", "content": prompt}],
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
    """Escritura atómica: escribe a un .tmp y renombra con os.replace (atómico
    en el mismo filesystem) — evita que un crash a mitad de json.dump deje el
    archivo de estado truncado/corrupto (leer_estado lo tragaría en silencio
    con su except: pass). Reusa el mismo patrón de _escribir() en
    gestor_portafolio.py."""
    ruta = os.path.join(PORTS_DIR, f"monitor_{archivo}")
    try:
        from gestor_portafolio import _escribir

        _escribir(ruta, estado)
    except Exception as e:
        print(f"❌ Error guardando estado: {e}")


def leer_portafolios_activos():
    activos = []
    if not os.path.exists(PORTS_DIR):
        return activos
    for fn in os.listdir(PORTS_DIR):
        if not _es_portafolio_real(fn):
            continue
        ruta = os.path.join(PORTS_DIR, fn)
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                p = json.load(f)
            if p.get("monitoreo_activo") and p.get("composicion"):
                print(
                    f"✅ Portafolio activo: {p.get('nombre','?')} — {len(p['composicion'])} activos"
                )
                activos.append((fn, p))
        except:
            continue
    if not activos:
        print("💤 Sin portafolios activos")
    return activos


def chat_id_de(portafolio):
    try:
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
    rangos = _cargar_rangos_disco(archivo)
    tickers = list(portafolio.get("composicion", {}).keys())
    nombre_port = portafolio.get("nombre", "tu portafolio")
    ahora = hora_colombia()
    dia_semana = ["lunes", "martes", "miércoles", "jueves", "viernes"][ahora.weekday()]

    # Resumen de rangos del día
    resumen_rangos = ""
    if rangos:
        for ticker, r in rangos["rangos"].items():
            if r["puede_entrar"]:
                resumen_rangos += (
                    f"  🟢 {ticker}: entraría si cae bajo ${r['rango_entrar']:,.2f}\n"
                )
            elif r["puede_vigilar"]:
                resumen_rangos += (
                    f"  🟡 {ticker}: vigilar si cae bajo ${r['rango_vigilar']:,.2f}\n"
                )
            else:
                resumen_rangos += (
                    f"  ⚪ {ticker}: NEUTRAL hoy (indicadores no favorables)\n"
                )

    msg = (
        f"☀️ <b>Buenos días — {dia_semana} {ahora.strftime('%d/%m')}</b>\n\n"
        f"📋 Portafolio: <b>{nombre_port}</b>\n\n"
        f"<b>Rangos calculados para hoy:</b>\n{resumen_rangos}\n"
        f"🔍 Monitoreando cada ~10-15 segundos de 8:30am a 3:00pm.\n"
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
    hoy = hora_colombia().strftime("%Y-%m-%d")
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

    chat_id = chat_id_de(portafolio)
    hoy_str = hora_colombia().strftime("%A %d de %B de %Y")
    dias_sin = estado.get("dias_consecutivos_sin_senal", 0)

    lineas = [
        f"📋 <b>REPORTE DE CIERRE — {portafolio['nombre']}</b>",
        f"📅 {hoy_str}\n",
    ]
    for r in sorted(resultados, key=lambda x: x["score"], reverse=True):
        emoji = {"ENTRAR": "🟢", "VIGILAR": "🟡", "NEUTRAL": "⚪"}.get(r["senal"], "⚪")
        cambio_str = (
            f" ({r['cambio_dia']:+.2f}%)" if r.get("cambio_dia") is not None else ""
        )
        lineas.append(
            f"{emoji} <b>{r['ticker']}</b> ${r['precio']:,.2f}{cambio_str}\n"
            f"   Score {r['score']}/10 | RSI {r['rsi']} | {r['tendencia']:+.1f}%"
        )

    entradas = [r for r in resultados if r["senal"] == "ENTRAR"]
    lineas.append(
        f"\n🎯 Señales hoy: {', '.join(r['ticker'] for r in entradas)}"
        if entradas
        else "\n⚪ Sin señales de entrada hoy"
    )
    if dias_sin > 0:
        lineas.append(f"📆 Días sin señal: {dias_sin}")

    ia_cierre = analisis_ia(resultados, portafolio, tipo="cierre")
    msg_final = "\n".join(lineas)
    if ia_cierre:
        msg_final += f"\n\n💬 <b>Análisis:</b>\n<i>{ia_cierre}</i>"

    if dias_sin >= DIAS_SIN_SENAL_MAX and hora_colombia().weekday() == 4:
        ia_sub = analisis_ia(resultados, portafolio, tipo="suboptimal")
        msg_final += f"\n\n⚠️ <b>ALERTA: {dias_sin} días sin señal ideal</b>\n" + (
            f"<i>{ia_sub}</i>" if ia_sub else ""
        )

    telegram(chat_id, msg_final)
    print(f"  📋 Reporte cierre enviado: {portafolio['nombre']}")

    # Limpiar alertas del día
    estado["lotes_alerta"] = {}
    estado["decisiones_usuario"] = {}
    for k in [
        k
        for k in estado
        if k.startswith(("persist_entrar_", "min_intradia_"))
    ]:
        del estado[k]

    estado["reporte_cierre"] = msg_final
    estado["reporte_cierre_fecha"] = hora_colombia().strftime("%Y-%m-%d")
    estado["cierre_enviado_hoy"] = hora_colombia().strftime("%Y-%m-%d")
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
        estado["alerta_suboptimal"] = ia_sub
        estado["alerta_suboptimal_semana"] = semana
        estado["dias_sin_senal_display"] = dias_sin
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
        partes = callback_data.split(":", 1)
        decision = partes[0]
        ticker = partes[1] if len(partes) > 1 else ""
        if not ticker:
            return

        for fn in os.listdir(PORTS_DIR):
            if not _es_portafolio_real(fn):
                continue
            try:
                with open(os.path.join(PORTS_DIR, fn), "r", encoding="utf-8") as f:
                    p = json.load(f)
                if chat_id_de(p) == str(chat_id):
                    registrar_decision(fn, ticker, decision)
                    mensajes = {
                        "entro": f"✅ Registrado: entraste a <b>{ticker}</b>. No te molesto más hoy.",
                        "no_entro": f"❌ Ok, no te aviso más de <b>{ticker}</b> hoy.",
                        "sigue": f"📊 Perfecto, te aviso si el precio de <b>{ticker}</b> mejora.",
                    }
                    telegram(
                        str(chat_id), mensajes.get(decision, "Decisión registrada.")
                    )
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
    8:30am-3:00pm  →  vigilar_precios() cada ~10-15 segundos
    3:00pm-3:45pm  →  reporte de cierre
    resto          →  dormir hasta las 8am del próximo día hábil
    """
    buenos_enviado = {}  # archivo → fecha último buenos días
    rangos_calculados = {}  # archivo → rangos del día (en RAM como caché)
    precalculo_hecho = {}  # archivo → fecha del último precálculo
    cierre_enviado = {}  # archivo → fecha del último cierre

    portafolios = []  # ← cache en RAM
    ultima_recarga = 0  # ← fecha del último scan de disco

    while True:
        try:
            ahora = hora_colombia()
            hoy = ahora.strftime("%Y-%m-%d")

            # ── Recargar portafolios cada 5 minutos ──────
            if time.time() - ultima_recarga > 300:
                portafolios = leer_portafolios_activos()
                ultima_recarga = time.time()

            # ── Cargar rangos desde disco si Railway reinició ──
            # Esto corre siempre — si ya están en RAM no hace nada
            for archivo, _ in portafolios:
                if archivo not in rangos_calculados:
                    rangos = _cargar_rangos_disco(archivo)
                    if rangos:
                        rangos_calculados[archivo] = rangos
                        precalculo_hecho[archivo] = hoy
                        print(f"  📂 Rangos cargados desde disco: {archivo}")

            # ── 8:00am — Precálculo de rangos ─────────────────
            if es_hora_precalculo():
                for archivo, pf in portafolios:
                    if precalculo_hecho.get(archivo) != hoy:
                        try:
                            resultado = precalcular_rangos(archivo, pf)
                            if resultado:
                                rangos_calculados[archivo] = resultado
                                precalculo_hecho[archivo] = hoy
                        except Exception as e:
                            print(f"❌ Error precálculo {archivo}: {e}")
                time.sleep(60)

            # ── 8:15am — Buenos días ───────────────────────────
            elif es_hora_buenos_dias():
                for archivo, pf in portafolios:
                    if buenos_enviado.get(archivo) != hoy:
                        try:
                            enviar_buenos_dias(archivo, pf)
                        except Exception as e:
                            print(f"❌ Error buenos días {archivo}: {e}")
                        buenos_enviado[archivo] = hoy
                time.sleep(60)

            # ── 8:30am-3:00pm — Vigilancia cada ~10-15 segundos ────
            elif mercado_abierto():
                # Recolectar todos los tickers únicos entre portafolios activos
                tickers_unicos = {}  # ticker → precio (se consulta UNA vez)
                for archivo, pf in portafolios:
                    rangos = rangos_calculados.get(archivo)
                    if not rangos:
                        continue
                    for ticker in rangos["rangos"]:
                        if ticker not in tickers_unicos:
                            tickers_unicos[ticker] = None

                # Consultar Finnhub UNA vez por ticker
                for ticker in tickers_unicos:
                    quote = finnhub_quote(ticker)
                    tickers_unicos[ticker] = quote
                    time.sleep(0.5)  # ← respetar rate limit: ~60 req/min

                # Procesar cada portafolio con los precios ya obtenidos
                for archivo, pf in portafolios:
                    rangos = rangos_calculados.get(archivo)
                    if not rangos:
                        print(f"  ⚠️ Sin rangos para {archivo} — esperando precálculo")
                        continue
                    try:
                        vigilar_precios(
                            archivo, pf, rangos, precios_cache=tickers_unicos
                        )
                        estado = leer_estado(archivo)
                        verificar_alerta_suboptimal(archivo, pf, estado)
                    except Exception as e:
                        print(f"❌ Error vigilando {archivo}: {e}")

                time.sleep(9)  # ← cada ~10-15 segundos

            # ── 4:00pm — Reporte de cierre ─────────────────────
            elif es_hora_cierre():
                for archivo, pf in portafolios:
                    if cierre_enviado.get(archivo) != hoy:
                        try:
                            estado = leer_estado(archivo)
                            reporte_cierre(archivo, pf, estado)
                            cierre_enviado[archivo] = hoy
                        except Exception as e:
                            print(f"❌ Error cierre {archivo}: {e}")
                time.sleep(60)

            # ── Mercado cerrado — dormir ───────────────────────
            else:
                segs = segundos_hasta_precalculo()
                print(f"💤 Mercado cerrado. Próximo precálculo en {segs/3600:.1f}h")
                time.sleep(min(segs, 300))

        except Exception as e:
            print(f"❌ Error loop monitor: {e}")
            time.sleep(60)
