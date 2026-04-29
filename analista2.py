import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import os
import time
import schedule
from datetime import datetime, time as dtime, timedelta
import warnings
warnings.filterwarnings('ignore')

from gestor_portafolio import leer_portafolio_activo

# ============================================================
# CONFIGURACIÓN TELEGRAM
# ============================================================

TELEGRAM_TOKEN   = "8332465511:AAH-PlentkDhWWNenLGOdvJCLC6OXNEnrA8"
TELEGRAM_CHAT_ID = "6999614895"

def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Error Telegram: {e}")

def notificacion_windows(titulo, mensaje):
    try:
        from plyer import notification
        notification.notify(title=titulo, message=mensaje, timeout=10)
    except:
        pass

# ============================================================
# HORARIO DE MERCADO
# ============================================================

def mercado_abierto():
    ahora = datetime.now()
    if ahora.weekday() >= 5:
        return False
    apertura = dtime(9, 30)
    cierre   = dtime(16, 0)
    return apertura <= ahora.time() <= cierre

# ============================================================
# CALCULAR SEÑALES TÉCNICAS
# ============================================================

def calcular_senales(ticker):
    try:
        hoy = datetime.now()
        hist_d = yf.download(ticker,
                            start=(hoy - timedelta(days=180)).strftime("%Y-%m-%d"),
                            end=hoy.strftime("%Y-%m-%d"),
                            interval="1d", auto_adjust=True, progress=False)
        hist_w = yf.download(ticker,
                            start=(hoy - timedelta(days=730)).strftime("%Y-%m-%d"),
                            end=hoy.strftime("%Y-%m-%d"),
                            interval="1wk", auto_adjust=True, progress=False)
        try:
            hist_m = yf.download(ticker,
                                start=(hoy - timedelta(days=1825)).strftime("%Y-%m-%d"),
                                end=hoy.strftime("%Y-%m-%d"),
                                interval="1mo", auto_adjust=True, progress=False)
            if hist_m.empty or len(hist_m) < 3:
                hist_m = hist_w
        except:
            hist_m = hist_w
        # Fallback: si falla con fechas explícitas, intentar con period
        
        if hist_d.empty or len(hist_d) < 50:
            try:
                inicio_alt = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")
                hist_d = yf.download(ticker, start=inicio_alt,
                                    end=datetime.now().strftime("%Y-%m-%d"),
                                    interval="1d", auto_adjust=True, progress=False)
                if hist_d.empty or len(hist_d) < 50:
                    hist_d = yf.download(ticker, period="6mo", interval="1d",
                                       auto_adjust=True, progress=False)
                if hist_d.empty or len(hist_d) < 50:
                    return None
            except:
                return None
        
        if hist_d.empty or len(hist_d) < 50:
            try:
                hist_d = yf.download(ticker, period="6mo", interval="1d",
                                    auto_adjust=True, progress=False)
                if hist_d.empty or len(hist_d) < 50:
                    return None
            except:
                return None

        for df in (hist_d, hist_w, hist_m):
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

        close_d = hist_d['Close']
        close_w = hist_w['Close']
        close_m = hist_m['Close']
        vol_d   = hist_d['Volume']

        def rsi(serie, periodos=14):
            delta   = serie.diff()
            ganancia = delta.clip(lower=0).rolling(periodos).mean()
            perdida  = (-delta.clip(upper=0)).rolling(periodos).mean()
            rs = ganancia / perdida.replace(0, np.nan)
            return round((100 - 100 / (1 + rs)).iloc[-1], 1)

        rsi_d = rsi(close_d)
        rsi_w = rsi(close_w) if len(close_w) >= 14 else 50.0

        ema12       = close_d.ewm(span=12, adjust=False).mean()
        ema26       = close_d.ewm(span=26, adjust=False).mean()
        macd_line   = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_val    = round(macd_line.iloc[-1], 4)
        macd_sig    = round(signal_line.iloc[-1], 4)
        cruce_alcista = (macd_line.iloc[-1] > signal_line.iloc[-1] and
                         macd_line.iloc[-2] <= signal_line.iloc[-2])

        ma20      = close_d.rolling(20).mean()
        std20     = close_d.rolling(20).std()
        ma50      = round(close_d.rolling(50).mean().iloc[-1], 2)
        banda_inf = round((ma20 - 2 * std20).iloc[-1], 2)

        tendencia_mensual = 1 if len(close_m) >= 3 and close_m.iloc[-1] > close_m.iloc[-3] else 0
        tendencia_semanal = 1 if len(close_w) >= 4 and close_w.iloc[-1] > close_w.iloc[-4] else 0

        vol_prom      = vol_d.rolling(20).mean().iloc[-1]
        ratio_volumen = round(vol_d.iloc[-1] / vol_prom, 2) if vol_prom > 0 else 1.0
        precio_actual = round(close_d.iloc[-1], 2)

        score   = 0
        razones = []

        if rsi_d < 40:
            score += 2; razones.append(f"RSI diario sobrevendido ({rsi_d})")
        elif rsi_d < 50:
            score += 1; razones.append(f"RSI diario en zona de valor ({rsi_d})")

        if precio_actual <= banda_inf * 1.02:
            score += 2; razones.append("Precio en/cerca de banda inferior Bollinger")

        if precio_actual <= ma50 * 1.01:
            score += 1; razones.append("Precio en soporte MA50")

        if cruce_alcista:
            score += 2; razones.append("Cruce alcista MACD")
        elif macd_val > macd_sig:
            score += 1; razones.append("MACD sobre señal")

        if tendencia_mensual == 1:
            score += 1; razones.append("Tendencia mensual alcista")
        if tendencia_semanal == 1:
            score += 1; razones.append("Tendencia semanal alcista")
        if ratio_volumen > 1.5:
            score += 1; razones.append(f"Volumen elevado ({ratio_volumen}x promedio)")

        senal = "🟢 ENTRAR" if score >= 6 else "🟡 VIGILAR" if score >= 3 else "⚪ NEUTRAL"

        return {
            'ticker': ticker, 'precio_actual': precio_actual, 'senal': senal,
            'rsi_diario': rsi_d, 'rsi_semanal': rsi_w,
            'tendencia_mensual': tendencia_mensual, 'tendencia_semanal': tendencia_semanal,
            'banda_inf': banda_inf, 'ma50': ma50,
            'macd': macd_val, 'macd_señal': macd_sig, 'cruce_alcista': cruce_alcista,
            'ratio_volumen': ratio_volumen, 'score': score, 'razones': razones,
        }

    except Exception as e:
        print(f"Error procesando {ticker}: {e}")
        return None

# ============================================================
# REVISIÓN COMPLETA DEL PORTAFOLIO
# ============================================================

def revisar_portafolio():
    if not mercado_abierto():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Mercado cerrado — esperando...")
        return

    print(f"\n{'='*55}")
    print(f"🔍 ANALISTA 2 — REVISIÓN {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    portafolio = leer_portafolio_activo()
    if not portafolio:
        return

    composicion = portafolio.get('composicion', {})
    if not composicion:
        print("⚠️ El portafolio activo no tiene composición asignada.")
        print("   Corre primero el Analista 1.")
        return
    todos = list(composicion.keys())
    print(f"   Portafolio: {portafolio['nombre']} ({portafolio['perfil']}) — {portafolio['propietario']}")

    alertas_entrada = []
    senales_todos   = {}

    for ticker in todos:
        print(f"   Analizando {ticker}...", end=" ")
        senal = calcular_senales(ticker)
        if senal is None:
            print("sin datos")
            continue
        senales_todos[ticker] = senal
        print(f"{senal['senal']} | RSI: {senal['rsi_diario']} | "
              f"Precio: ${senal['precio_actual']}")
        if senal['senal'] == "🟢 ENTRAR":
            alertas_entrada.append(senal)

    # ── ALERTAS DE ENTRADA ──
    if alertas_entrada:
        print(f"\n🚨 {len(alertas_entrada)} OPORTUNIDAD(ES) DE ENTRADA DETECTADA(S)")
        for senal in alertas_entrada:
            perfil = [portafolio['perfil'].capitalize()]

            mensaje = (
                f"🟢 <b>OPORTUNIDAD DE ENTRADA — ALTA CONVICCIÓN</b>\n\n"
                f"📊 Activo: <b>{senal['ticker']}</b>\n"
                f"💼 Portafolio: {' + '.join(perfil)}\n"
                f"💰 Precio actual: ${senal['precio_actual']}\n"
                f"📉 Rango de entrada: ${senal['banda_inf']} — ${senal['ma50']}\n\n"
                f"📋 <b>Análisis multi-marco:</b>\n"
                f"   📅 Tendencia mensual: {'✅ Alcista' if senal['tendencia_mensual'] == 1 else '⚖️ Neutral'}\n"
                f"   📅 Tendencia semanal: {'✅ Alcista' if senal['tendencia_semanal'] == 1 else '🔄 Corrección'}\n"
                f"   📊 RSI diario: {senal['rsi_diario']} | RSI semanal: {senal['rsi_semanal']}\n"
                f"   📈 MACD: {senal['macd']:.4f} | Señal: {senal['macd_señal']:.4f} "
                f"{'⚡ CRUCE ALCISTA' if senal['cruce_alcista'] else ''}\n"
                f"   📦 Volumen: {senal['ratio_volumen']}x del promedio\n"
                f"   🏆 Score: {senal['score']}/10\n\n"
                f"📋 <b>Razones:</b>\n" +
                "\n".join([f"   • {r}" for r in senal['razones']]) +
                f"\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            enviar_telegram(mensaje)
            notificacion_windows("🟢 Oportunidad de entrada",
                                f"{senal['ticker']} — ${senal['precio_actual']}")
            print(f"   📱 Alerta enviada para {senal['ticker']}")

    # ── REPORTE DE RUTINA (siempre se envía) ──
    if not alertas_entrada:
        print(f"\n✅ Sin oportunidades de entrada en este momento.")

    # Mensaje de estado completo — SIEMPRE a Telegram
    tend_texto = {1: "📈", -1: "📉", 0: "➡️"}
    mensaje_rutina = (
        f"📊 <b>REVISIÓN {datetime.now().strftime('%H:%M')} — "
        f"{'⚡ HAY ENTRADAS' if alertas_entrada else 'SIN ENTRADAS'}</b>\n\n"
    )
    for ticker, senal in senales_todos.items():
        tend_m = tend_texto.get(senal['tendencia_mensual'], "➡️")
        mensaje_rutina += (
            f"{senal['senal']} <b>{ticker}</b> "
            f"${senal['precio_actual']} | "
            f"RSI: {senal['rsi_diario']} | "
            f"{tend_m}\n"
        )
    mensaje_rutina += f"\n🔄 Próxima revisión en 15 minutos."
    enviar_telegram(mensaje_rutina)

    print(f"{'='*55}")

# ============================================================
# LOOP PRINCIPAL
# ============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("🤖 ANALISTA 2 — MONITOR DE MERCADO ACTIVO")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("⏰ Revisando cada 15 minutos en horario de mercado")
    print("   NYSE: Lunes-Viernes 9:30am - 4:00pm (hora Colombia)")
    print("=" * 55)

    revisar_portafolio()
    schedule.every(15).minutes.do(revisar_portafolio)

    while True:
        schedule.run_pending()
        time.sleep(60)