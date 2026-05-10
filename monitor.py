"""
monitor.py — Motor de monitoreo de mercado
==========================================
- Corre en hilo daemon independiente
- Analiza portafolios con monitoreo_activo = True
- Alertas cada 15-20 min si hay posible entrada (Telegram + app)
- Buenos días a las 9:15am Colombia (antes de abrir)
- Reporte de cierre a las 4:00-4:45pm Colombia (Telegram + app)
- Recomendación de entrada subóptima si pasa 1 semana sin señal
"""

import os, json, time, threading, requests
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATOS_DIR = os.path.join(BASE_DIR, "datos")
PORTS_DIR = os.path.join(DATOS_DIR, "portafolios")
BOT_TOKEN = "8332465511:AAH-PlentkDhWWNenLGOdvJCLC6OXNEnrA8"

INTERVALO_MINUTOS   = 18   # cada cuántos minutos se analiza durante el día
UMBRAL_ENTRADA      = 6.5  # score mínimo para emitir alerta de entrada
DIAS_SIN_SENAL_MAX  = 5    # días hábiles sin señal antes de recomendar entrada subóptima

# ─────────────────────────────────────────────────────────────
# UTILIDADES DE TIEMPO
# ─────────────────────────────────────────────────────────────

def hora_colombia():
    """Hora actual en Colombia (UTC-5)."""
    return datetime.utcnow() - timedelta(hours=5)

def mercado_abierto():
    """NYSE abre 9:30am–4:00pm hora Colombia, lunes a viernes."""
    ahora = hora_colombia()
    if ahora.weekday() >= 5:
        return False
    apertura = ahora.replace(hour=9, minute=30, second=0, microsecond=0)
    cierre   = ahora.replace(hour=16, minute=0, second=0, microsecond=0)
    return apertura <= ahora <= cierre

def es_hora_buenos_dias():
    """True entre 9:00am y 9:25am Colombia — ventana de saludo pre-apertura."""
    ahora = hora_colombia()
    if ahora.weekday() >= 5:
        return False
    inicio = ahora.replace(hour=9, minute=0, second=0, microsecond=0)
    fin    = ahora.replace(hour=9, minute=25, second=0, microsecond=0)
    return inicio <= ahora <= fin

def es_hora_cierre():
    """True entre 4:00pm y 4:45pm Colombia (ventana de reporte de cierre)."""
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

def telegram(chat_id, texto):
    if not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# ─────────────────────────────────────────────────────────────
# ANÁLISIS TÉCNICO DE UN ACTIVO
# ─────────────────────────────────────────────────────────────

def analizar_activo(ticker):
    try:
        hoy    = datetime.utcnow()
        inicio = (hoy - timedelta(days=90)).strftime("%Y-%m-%d")
        df = yf.download(ticker, start=inicio, end=hoy.strftime("%Y-%m-%d"),
                         interval="1d", auto_adjust=True, progress=False)
        if df is None or len(df) < 20:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close  = df["Close"].squeeze()
        volume = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series([1]*len(df))

        precio  = float(close.iloc[-1])
        ma20    = float(close.rolling(20).mean().iloc[-1])
        ma50    = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else ma20
        tend    = round(((precio - float(close.iloc[-20])) / float(close.iloc[-20])) * 100, 2)
        vol_r   = round(float(volume.iloc[-1]) / float(volume.rolling(20).mean().iloc[-1]), 2) if float(volume.rolling(20).mean().iloc[-1]) > 0 else 1.0

        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, 1e-9)
        rsi   = round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

        score = 0.0
        if rsi < 30:       score += 3.0
        elif rsi < 45:     score += 2.5
        elif rsi < 55:     score += 1.5
        elif rsi < 65:     score += 0.5
        if precio < ma20:  score += 2.0
        elif precio < ma50: score += 1.0
        if -10 <= tend <= -3:   score += 2.5
        elif -3 < tend <= 0:    score += 1.5
        elif 0 < tend <= 3:     score += 1.0
        elif tend < -10:        score += 1.5
        if vol_r > 1.5:    score += 0.5

        score = round(min(score, 10.0), 1)

        if score >= UMBRAL_ENTRADA:   senal = "ENTRAR"
        elif score >= 4.5:            senal = "VIGILAR"
        else:                         senal = "NEUTRAL"

        return {
            "ticker":    ticker,
            "precio":    round(precio, 2),
            "ma20":      round(ma20, 2),
            "ma50":      round(ma50, 2),
            "rsi":       rsi,
            "tendencia": tend,
            "vol_ratio": vol_r,
            "score":     score,
            "senal":     senal,
            "timestamp": hora_colombia().strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        print(f"❌ Error analizando {ticker}: {e}")
        return None

# ─────────────────────────────────────────────────────────────
# ANÁLISIS IA (Claude)
# ─────────────────────────────────────────────────────────────

def analisis_ia(resultados, portafolio, tipo="ciclo"):
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        resumen = ""
        for r in resultados:
            resumen += (f"- {r['ticker']}: ${r['precio']} | RSI {r['rsi']} | "
                        f"Score {r['score']}/10 | Señal {r['senal']} | "
                        f"Tendencia {r['tendencia']:+.1f}% | MA20 ${r['ma20']} | MA50 ${r['ma50']}\n")

        if tipo == "cierre":
            prompt = (
                f"Eres analista financiero de {portafolio['propietario']}. "
                f"Es el cierre del mercado NYSE hoy {hora_colombia().strftime('%A %d de %B')}.\n\n"
                f"MÉTRICAS FINALES DEL DÍA:\n{resumen}\n\n"
                f"Escribe un reporte de cierre en español, máximo 5 párrafos:\n"
                f"1. Resumen general del día\n"
                f"2. Activos que mostraron señales\n"
                f"3. Activos que hay que vigilar mañana\n"
                f"4. Recomendación concreta para la próxima sesión\n"
                f"5. Nivel de oportunidad general (bajo/medio/alto)\n"
                f"Sin asteriscos. Directo. Usa los números exactos."
            )
        elif tipo == "suboptimal":
            prompt = (
                f"Eres analista financiero de {portafolio['propietario']}. "
                f"Han pasado {DIAS_SIN_SENAL_MAX}+ días hábiles sin ninguna señal de entrada clara.\n\n"
                f"ESTADO ACTUAL DEL MERCADO:\n{resumen}\n\n"
                f"Escribe una recomendación especial en español, máximo 4 párrafos:\n"
                f"1. Por qué no ha habido señal ideal\n"
                f"2. Riesgo de esperar más vs entrar ahora\n"
                f"3. Qué activos son los mejores candidatos a pesar de no ser el momento perfecto\n"
                f"4. Recomendación final: ¿entrar parcialmente, esperar, o DCA?\n"
                f"Sin asteriscos. Con criterio propio. Directo."
            )
        elif tipo == "buenos_dias":
            tickers = list(portafolio.get("composicion", {}).keys())
            prompt = (
                f"Eres el analista de portafolio de {portafolio['propietario']}. "
                f"Son las 9:15am en Colombia, el mercado NYSE abre en 15 minutos.\n\n"
                f"PORTAFOLIO MONITOREADO: {', '.join(tickers)}\n\n"
                f"Escribe UN párrafo corto de buenos días (máximo 3 oraciones):\n"
                f"- Saluda brevemente\n"
                f"- Menciona qué vas a monitorear hoy\n"
                f"- Di que avisarás si encuentras algo\n"
                f"Tono: profesional pero cercano. Sin asteriscos. En español."
            )
        else:
            entradas = [r for r in resultados if r['senal'] == 'ENTRAR']
            prompt = (
                f"Analista de {portafolio['propietario']}. Ciclo de monitoreo {hora_colombia().strftime('%H:%M')}.\n\n"
                f"SEÑALES DETECTADAS:\n{resumen}\n\n"
                f"{'HAY ' + str(len(entradas)) + ' POSIBLE(S) ENTRADA(S): ' + ', '.join(r['ticker'] for r in entradas) if entradas else 'Sin entradas claras este ciclo.'}\n\n"
                f"2-3 oraciones máximo. Solo lo importante. Sin asteriscos."
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
# PERSISTENCIA DEL ESTADO DEL MONITOR
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
        print(f"❌ Error guardando estado monitor: {e}")

def leer_portafolios_activos():
    activos = []
    if not os.path.exists(PORTS_DIR):
        print(f"⚠️ Directorio no existe: {PORTS_DIR}")
        return activos
    for fn in os.listdir(PORTS_DIR):
        if not fn.endswith(".json") or fn.startswith("monitor_"):
            continue
        ruta = os.path.join(PORTS_DIR, fn)
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                p = json.load(f)
            tiene_monitor = p.get("monitoreo_activo", False)
            tiene_comp    = bool(p.get("composicion"))
            if tiene_monitor and tiene_comp:
                print(f"✅ Portafolio activo: {p.get('nombre','?')} — {len(p['composicion'])} activos")
                activos.append((fn, p))
            elif tiene_monitor and not tiene_comp:
                print(f"⚠️ {p.get('nombre','?')} tiene monitoreo ON pero SIN composición — no se monitorea")
        except Exception as e:
            print(f"❌ Error leyendo {fn}: {e}")
            continue
    if not activos:
        print("💤 Sin portafolios activos para monitorear")
    return activos

def chat_id_de(portafolio):
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
# MENSAJE DE BUENOS DÍAS
# ─────────────────────────────────────────────────────────────

def enviar_buenos_dias(archivo, portafolio):
    """Saludo pre-apertura con resumen de lo que se va a monitorear."""
    chat_id = chat_id_de(portafolio)
    if not chat_id:
        return

    tickers     = list(portafolio.get("composicion", {}).keys())
    nombre_port = portafolio.get("nombre", "tu portafolio")
    ahora       = hora_colombia()
    dia_semana  = ["lunes", "martes", "miércoles", "jueves", "viernes"][ahora.weekday()]

    # Mensaje base sin IA
    msg_base = (
        f"☀️ <b>Buenos días — {dia_semana} {ahora.strftime('%d/%m')}</b>\n\n"
        f"📋 Portafolio: <b>{nombre_port}</b>\n"
        f"🔍 Monitoreando: <b>{', '.join(tickers)}</b>\n\n"
        f"El mercado NYSE abre a las 9:30am. "
        f"Estaré analizando cada 18 minutos y te aviso si encuentro señales de entrada.\n\n"
        f"<i>Si no recibes alertas durante el día, significa que el mercado no ofrece "
        f"condiciones óptimas para entrar hoy.</i>"
    )

    # Enriquecer con IA si está disponible
    try:
        ia_saludo = analisis_ia([], portafolio, tipo="buenos_dias")
        if ia_saludo:
            msg_base += f"\n\n💬 <i>{ia_saludo}</i>"
    except:
        pass

    telegram(chat_id, msg_base)
    print(f"  ☀️ Buenos días enviado: {portafolio['nombre']}")

# ─────────────────────────────────────────────────────────────
# CICLO PRINCIPAL DE UN PORTAFOLIO
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
        time.sleep(0.5)

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
            msg = (
                f"🟢 <b>POSIBLE ENTRADA — {r['ticker']}</b>\n"
                f"📊 Score: <b>{r['score']}/10</b> | RSI: {r['rsi']}\n"
                f"💵 Precio: ${r['precio']:,} | MA20: ${r['ma20']:,} | MA50: ${r['ma50']:,}\n"
                f"📈 Tendencia 20d: {r['tendencia']:+.1f}% | Vol ratio: {r['vol_ratio']}x\n"
                f"🕐 {ahora_str}\n"
            )
            if ia_txt:
                msg += f"\n💬 <i>{ia_txt}</i>"
            telegram(chat_id, msg)
            print(f"  ✅ Alerta ENTRAR enviada: {r['ticker']}")

        estado["ultimo_dia_con_senal"] = hoy_str
        estado["dias_consecutivos_sin_senal"] = 0
    else:
        ultimo = estado.get("ultimo_dia_con_senal")
        if ultimo:
            try:
                dias = sum(1 for i in range(
                    (datetime.strptime(hoy_str, "%Y-%m-%d") -
                     datetime.strptime(ultimo, "%Y-%m-%d")).days
                ) if (datetime.strptime(ultimo, "%Y-%m-%d") + timedelta(days=i+1)).weekday() < 5)
                estado["dias_consecutivos_sin_senal"] = dias
            except:
                estado["dias_consecutivos_sin_senal"] = estado.get("dias_consecutivos_sin_senal", 0)
        else:
            estado["dias_consecutivos_sin_senal"] = estado.get("dias_consecutivos_sin_senal", 0) + 1

    estado["resultados"]        = resultados
    estado["timestamp"]         = ahora_str
    estado["prediccion"]        = (f"🟢 {len(entradas)} entrada(s) detectada(s)" if entradas
                                   else f"👁 {len(vigilar)} en vigilancia" if vigilar
                                   else "⚪ Sin señales este ciclo")
    estado["justificacion"]     = analisis_ia(resultados, portafolio, tipo="ciclo") if not entradas else ""
    estado["nombre_portafolio"] = portafolio["nombre"]

    guardar_estado(archivo, estado)
    return estado

# ─────────────────────────────────────────────────────────────
# REPORTE DE CIERRE (4:00–4:45pm)
# ─────────────────────────────────────────────────────────────

def reporte_cierre(archivo, portafolio, estado):
    resultados = estado.get("resultados", [])
    if not resultados:
        return

    chat_id  = chat_id_de(portafolio)
    hoy_str  = hora_colombia().strftime("%A %d de %B de %Y")
    dias_sin = estado.get("dias_consecutivos_sin_senal", 0)

    lineas = [f"📋 <b>REPORTE DE CIERRE — {portafolio['nombre']}</b>",
              f"📅 {hoy_str}\n"]
    for r in sorted(resultados, key=lambda x: x["score"], reverse=True):
        emoji = {"ENTRAR": "🟢", "VIGILAR": "🟡", "NEUTRAL": "⚪"}.get(r["senal"], "⚪")
        lineas.append(
            f"{emoji} <b>{r['ticker']}</b>  ${r['precio']:,}\n"
            f"   Score {r['score']}/10 | RSI {r['rsi']} | {r['tendencia']:+.1f}% | Vol {r['vol_ratio']}x"
        )

    entradas = [r for r in resultados if r["senal"] == "ENTRAR"]
    if entradas:
        lineas.append(f"\n🎯 Señales de entrada: {', '.join(r['ticker'] for r in entradas)}")
    else:
        lineas.append(f"\n⚪ Sin señales de entrada hoy")

    if dias_sin > 0:
        lineas.append(f"📆 Días hábiles sin señal: {dias_sin}")

    msg_numerico = "\n".join(lineas)
    ia_cierre    = analisis_ia(resultados, portafolio, tipo="cierre")

    msg_final = msg_numerico
    if ia_cierre:
        msg_final += f"\n\n💬 <b>Análisis:</b>\n<i>{ia_cierre}</i>"

    if dias_sin >= DIAS_SIN_SENAL_MAX and es_viernes():
        ia_sub = analisis_ia(resultados, portafolio, tipo="suboptimal")
        sub_msg = (
            f"\n\n⚠️ <b>ALERTA: {dias_sin} días sin señal ideal</b>\n"
            f"El mercado podría estar encareciendo. Considera una entrada parcial.\n"
        )
        if ia_sub:
            sub_msg += f"<i>{ia_sub}</i>"
        msg_final += sub_msg

    telegram(chat_id, msg_final)
    print(f"  📋 Reporte de cierre enviado: {portafolio['nombre']}")

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
    if not estado.get("alerta_suboptimal_semana") == hora_colombia().strftime("%Y-W%W"):
        ia_sub = analisis_ia(resultados, portafolio, tipo="suboptimal")
        estado["alerta_suboptimal"]        = ia_sub
        estado["alerta_suboptimal_semana"] = hora_colombia().strftime("%Y-W%W")
        estado["dias_sin_senal_display"]   = dias_sin
        guardar_estado(archivo, estado)

# ─────────────────────────────────────────────────────────────
# HILO PRINCIPAL DEL MONITOR
# ─────────────────────────────────────────────────────────────

_monitor_activo = False

def iniciar_monitor():
    global _monitor_activo
    if _monitor_activo:
        return
    _monitor_activo = True
    t = threading.Thread(target=_loop_monitor, daemon=True)
    t.start()
    print("🚀 Monitor iniciado")

def _loop_monitor():
    """
    Estados del loop:
    - 9:00–9:25am  → buenos días (una vez por día)
    - 9:30am–4:00pm → ciclo de análisis cada 18 min
    - 4:00–4:45pm  → reporte de cierre (una vez por día)
    - resto        → duerme hasta próxima apertura
    """
    ultimo_ciclo    = {}   # archivo -> datetime del último ciclo
    cierre_enviado  = {}   # archivo -> fecha
    buenos_enviado  = {}   # archivo -> fecha

    while True:
        try:
            portafolios = leer_portafolios_activos()
            ahora       = hora_colombia()
            hoy         = ahora.strftime("%Y-%m-%d")

            # ── Buenos días ────────────────────────────────
            if es_hora_buenos_dias():
                for archivo, portafolio in portafolios:
                    if buenos_enviado.get(archivo) != hoy:
                        try:
                            enviar_buenos_dias(archivo, portafolio)
                        except Exception as e:
                            print(f"❌ Error buenos días {archivo}: {e}")
                        buenos_enviado[archivo] = hoy
                time.sleep(60)

            # ── Mercado abierto: ciclos de análisis ────────
            elif mercado_abierto():
                for archivo, portafolio in portafolios:
                    ultimo = ultimo_ciclo.get(archivo)
                    if ultimo is None or (ahora - ultimo).total_seconds() >= INTERVALO_MINUTOS * 60:
                        try:
                            estado = ciclo_portafolio(archivo, portafolio)
                            if estado:
                                verificar_alerta_suboptimal(archivo, portafolio, estado)
                        except Exception as e:
                            print(f"❌ Error ciclo {archivo}: {e}")
                        ultimo_ciclo[archivo] = ahora
                time.sleep(60)

            # ── Reporte de cierre ──────────────────────────
            elif es_hora_cierre():
                for archivo, portafolio in portafolios:
                    if cierre_enviado.get(archivo) != hoy:
                        estado = leer_estado(archivo)
                        if estado:
                            try:
                                reporte_cierre(archivo, portafolio, estado)
                            except Exception as e:
                                print(f"❌ Error reporte cierre {archivo}: {e}")
                        cierre_enviado[archivo] = hoy
                time.sleep(60)

            # ── Mercado cerrado: dormir ────────────────────
            else:
                segs = segundos_hasta_apertura()
                print(f"💤 Mercado cerrado. Próxima apertura en {segs/3600:.1f}h")
                time.sleep(min(segs, 300))

        except Exception as e:
            print(f"❌ Error loop monitor: {e}")
            time.sleep(60)