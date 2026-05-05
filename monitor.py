import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import requests
import threading
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

CARPETA    = "datos/portafolios"
TELEGRAM_TOKEN = "8332465511:AAH-PlentkDhWWNenLGOdvJCLC6OXNEnrA8"
GROQ_API_KEY   = "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"

# ── Horario NYSE en hora Colombia (EST+1) ──
def mercado_abierto():
    ahora = datetime.now()
    # NYSE opera L-V 9:30am-4:00pm EST = 9:30am-4:00pm hora Colombia
    if ahora.weekday() >= 5:  # Sábado=5, Domingo=6
        return False
    hora_decimal = ahora.hour + ahora.minute / 60
    return 9.5 <= hora_decimal < 16.0

# ── Enviar alerta ──
def enviar_telegram(chat_id, mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"
        }, timeout=10)
    except: pass

def enviar_email(email, asunto, mensaje):
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        gmail_user = os.environ.get('GMAIL_USER', '')
        gmail_pass = os.environ.get('GMAIL_PASS', '')
        if not gmail_user or not gmail_pass:
            return
        msg            = MIMEMultipart()
        msg['From']    = gmail_user
        msg['To']      = email
        msg['Subject'] = asunto
        msg.attach(MIMEText(mensaje, 'plain'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
    except: pass

# ── Calcular señales técnicas ──
def calcular_senales(ticker):
    try:
        hoy    = datetime.now()
        inicio = (hoy - timedelta(days=200)).strftime("%Y-%m-%d")
        df = yf.download(ticker, start=inicio, end=hoy.strftime("%Y-%m-%d"),
                        interval="1d", auto_adjust=True, progress=False)
        if df.empty or len(df) < 50:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close  = df['Close'].squeeze()
        volume = df['Volume'].squeeze()

        # RSI
        delta  = close.diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rs     = gain / loss
        rsi    = float((100 - 100 / (1 + rs)).iloc[-1])

        # MACD
        ema12  = close.ewm(span=12).mean()
        ema26  = close.ewm(span=26).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_v = float(macd.iloc[-1])
        sig_v  = float(signal.iloc[-1])

        # Bollinger
        ma20   = close.rolling(20).mean()
        std20  = close.rolling(20).std()
        bb_up  = float((ma20 + 2*std20).iloc[-1])
        bb_low = float((ma20 - 2*std20).iloc[-1])
        precio = float(close.iloc[-1])

        # Medias móviles
        ma50   = float(close.rolling(50).mean().iloc[-1])
        ma200  = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else ma50

        # Volumen
        vol_avg = float(volume.rolling(20).mean().iloc[-1])
        vol_hoy = float(volume.iloc[-1])
        vol_ratio = vol_hoy / vol_avg if vol_avg > 0 else 1

        # Score
        score = 0
        if rsi < 35:   score += 3
        elif rsi < 45: score += 2
        elif rsi < 55: score += 1
        if macd_v > sig_v:  score += 2
        if precio < bb_low: score += 2
        if precio > ma50:   score += 1
        if vol_ratio > 1.2: score += 1

        # Señal
        if score >= 7:   senal = "ENTRAR"
        elif score >= 4: senal = "VIGILAR"
        else:            senal = "NEUTRAL"

        # Tendencia mensual
        hace_mes = float(close.iloc[-22]) if len(close) > 22 else precio
        tendencia = ((precio - hace_mes) / hace_mes) * 100

        return {
            "ticker":     ticker,
            "precio":     round(precio, 2),
            "rsi":        round(rsi, 1),
            "macd":       round(macd_v, 4),
            "macd_signal":round(sig_v, 4),
            "bb_low":     round(bb_low, 2),
            "bb_up":      round(bb_up, 2),
            "ma50":       round(ma50, 2),
            "ma200":      round(ma200, 2),
            "vol_ratio":  round(vol_ratio, 2),
            "score":      score,
            "senal":      senal,
            "tendencia":  round(tendencia, 2)
        }
    except:
        return None

# ── Generar justificación IA ──
def generar_justificacion(resultados, portafolio):
    try:
        from groq import Groq
        resumen = ""
        for r in resultados:
            resumen += (
                f"{r['ticker']}: ${r['precio']:,.2f} | RSI {r['rsi']} | "
                f"Score {r['score']}/10 | Señal: {r['senal']} | "
                f"Tendencia mensual: {r['tendencia']:+.1f}%\n"
            )

        entradas = [r for r in resultados if r['senal'] == 'ENTRAR']
        vigilar  = [r for r in resultados if r['senal'] == 'VIGILAR']

        prompt = (
            f"Portafolio: {portafolio['nombre']} ({portafolio['perfil']})\n\n"
            f"ANÁLISIS TÉCNICO ACTUAL:\n{resumen}\n\n"
            f"En máximo 4 oraciones:\n"
            f"1. Estado general del portafolio ahora mismo\n"
            f"2. Si hay activos para entrar HOY, cuáles y por qué\n"
            f"3. Si no hay entradas hoy, qué vigilar esta semana\n"
            f"4. Recomendación concreta de acción\n"
            f"Sin asteriscos. Sin bullets. Español directo."
        )

        resp = Groq(api_key=GROQ_API_KEY).chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[
                {'role': 'system', 'content': 'Eres analista técnico. Solo datos reales. Sin inventar.'},
                {'role': 'user', 'content': prompt}
            ],
            max_tokens=200, temperature=0.3
        )
        justificacion = resp.choices[0].message.content

        # Predicción del día
        if entradas:
            prediccion = f"✅ Posible entrada HOY en: {', '.join(r['ticker'] for r in entradas)}"
        elif vigilar:
            prediccion = f"👁 Vigilar de cerca: {', '.join(r['ticker'] for r in vigilar)}"
        else:
            prediccion = "⏳ Sin oportunidades claras por ahora. Esperar próximo análisis."

        return justificacion, prediccion

    except Exception as e:
        return "Error generando análisis.", "No disponible."

# ── Analizar un portafolio ──
def analizar_portafolio(archivo):
    try:
        ruta = f"{CARPETA}/{archivo}"
        with open(ruta, 'r', encoding='utf-8') as f:
            portafolio = json.load(f)

        composicion = portafolio.get('composicion', {})
        if not composicion:
            return

        activos   = list(composicion.keys())
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Analizando {portafolio['nombre']}...")

        resultados = []
        for ticker in activos:
            r = calcular_senales(ticker)
            if r:
                resultados.append(r)
                estado = {"ENTRAR": "🟢", "VIGILAR": "🟡", "NEUTRAL": "⚪"}.get(r['senal'], "⚪")
                print(f"  {estado} {ticker}: RSI {r['rsi']} | Score {r['score']}/10 | {r['senal']}")

        if not resultados:
            return

        justificacion, prediccion = generar_justificacion(resultados, portafolio)

        # Guardar resultado
        monitor_data = {
            "archivo":       archivo,
            "nombre":        portafolio['nombre'],
            "timestamp":     timestamp,
            "resultados":    resultados,
            "justificacion": justificacion,
            "prediccion":    prediccion
        }

        ruta_monitor = f"{CARPETA}/monitor_{archivo}"
        with open(ruta_monitor, 'w', encoding='utf-8') as f:
            json.dump(monitor_data, f, indent=2, ensure_ascii=False)

        # Alertas
        entradas = [r for r in resultados if r['senal'] == 'ENTRAR']
        if entradas:
            msg = (
                f"🔔 <b>ALERTA DE ENTRADA — {portafolio['nombre']}</b>\n"
                f"📅 {timestamp}\n\n"
            )
            for r in entradas:
                msg += f"✅ <b>{r['ticker']}</b> — ${r['precio']:,.2f}\n"
                msg += f"   RSI: {r['rsi']} | Score: {r['score']}/10\n\n"
            msg += f"💬 {justificacion}\n\n{prediccion}"

            chat_id = portafolio.get('telegram_chat_id', '')
            email   = portafolio.get('email', '')
            if chat_id: enviar_telegram(chat_id, msg)
            if email:   enviar_email(email, f"Alerta entrada — {portafolio['nombre']}", msg)

        print(f"  📊 {prediccion}")

    except Exception as e:
        print(f"Error analizando {archivo}: {e}")

# ── Loop principal ──
def loop_monitor():
    print("🔍 Monitor iniciado")
    ultimo_analisis = {}  # archivo -> timestamp ultimo analisis

    while True:
        ahora = datetime.now()
        es_horario = mercado_abierto()

        # Leer portafolios con monitoreo activo
        try:
            portafolios_activos = []
            for archivo in os.listdir(CARPETA):
                if not archivo.endswith('.json') or archivo.startswith('monitor_'):
                    continue
                try:
                    with open(f"{CARPETA}/{archivo}", 'r', encoding='utf-8') as f:
                        p = json.load(f)
                    if p.get('monitoreo_activo') and p.get('composicion'):
                        portafolios_activos.append(archivo)
                except:
                    continue
        except:
            time.sleep(60)
            continue

        if not portafolios_activos:
            time.sleep(60)
            continue

        if es_horario:
            # Analizar cada portafolio activo
            for archivo in portafolios_activos:
                ultimo = ultimo_analisis.get(archivo)
                # Solo analizar si pasaron 15 minutos desde el último
                if ultimo and (ahora - ultimo).total_seconds() < 900:
                    continue
                # Analizar en thread separado para no bloquear los demás portafolios
                t = threading.Thread(target=analizar_portafolio, args=(archivo,), daemon=True)
                t.start()
                ultimo_analisis[archivo] = ahora
            time.sleep(60)  # Revisar cada minuto si ya pasaron 15

        else:
            # Mercado cerrado — notificar una vez por día al abrir y al cerrar
            hora = ahora.strftime("%H:%M")
            # Notificar al cierre (4:01 PM) y solo una vez
            if hora == "16:01":
                for archivo in portafolios_activos:
                    try:
                        with open(f"{CARPETA}/{archivo}", 'r', encoding='utf-8') as f:
                            p = json.load(f)
                        msg = (
                            f"🔔 <b>{p['nombre']}</b>\n"
                            f"🔒 Mercado cerrado — NYSE cerró a las 4:00 PM\n"
                            f"📅 Próxima sesión: mañana a las 9:30 AM\n"
                            f"💤 El monitor reanudará el análisis mañana."
                        )
                        if p.get('telegram_chat_id'):
                            enviar_telegram(p['telegram_chat_id'], msg)
                        if p.get('email'):
                            enviar_email(p['email'], f"Mercado cerrado — {p['nombre']}", msg)

                        # Actualizar archivo monitor con estado cerrado
                        ruta_m = f"{CARPETA}/monitor_{archivo}"
                        monitor_data = {
                            "archivo": archivo,
                            "nombre": p['nombre'],
                            "timestamp": ahora.strftime("%Y-%m-%d %H:%M:%S"),
                            "mercado_abierto": False,
                            "resultados": [],
                            "justificacion": "Mercado cerrado. NYSE opera de 9:30 AM a 4:00 PM hora Colombia.",
                            "prediccion": "⏳ El análisis reanudará mañana a las 9:30 AM."
                        }
                        with open(ruta_m, 'w', encoding='utf-8') as f:
                            json.dump(monitor_data, f, indent=2, ensure_ascii=False)
                    except:
                        continue

            # Notificar al abrir (9:30 AM) y solo una vez
            elif hora == "09:30":
                for archivo in portafolios_activos:
                    try:
                        with open(f"{CARPETA}/{archivo}", 'r', encoding='utf-8') as f:
                            p = json.load(f)
                        msg = (
                            f"🔔 <b>{p['nombre']}</b>\n"
                            f"🟢 Mercado abierto — NYSE abrió a las 9:30 AM\n"
                            f"🔍 Iniciando monitoreo cada 15 minutos.\n"
                            f"📊 Recibirás alertas cuando haya oportunidades de entrada."
                        )
                        if p.get('telegram_chat_id'):
                            enviar_telegram(p['telegram_chat_id'], msg)
                        if p.get('email'):
                            enviar_email(p['email'], f"Mercado abierto — {p['nombre']}", msg)
                    except:
                        continue

            time.sleep(60)  # Revisar cada minuto fuera de horario

# ── Iniciar como thread ──
def iniciar_monitor():
    t = threading.Thread(target=loop_monitor, daemon=True)
    t.start()
    return t