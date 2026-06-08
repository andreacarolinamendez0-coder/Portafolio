"""
scheduler.py — Tareas programadas
==================================
FIXES aplicados:
1. Estado persistido en disco (no variables en memoria que se pierden con reinicios)
2. calcular_tiempo_real_simple migrado a Finnhub (sin yfinance)
3. Buenos días y cierre se envían exactamente una vez por día
"""

import threading
import time
import os
import json
from datetime import datetime, timezone, timedelta
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_PORTAFOLIOS = os.path.join(BASE_DIR, "datos", "portafolios")
SCHEDULER_STATE = os.path.join(BASE_DIR, "datos", "scheduler_state.json")

# ─────────────────────────────────────────────────────────────
# ESTADO PERSISTENTE EN DISCO
# ─────────────────────────────────────────────────────────────


def leer_estado_scheduler():
    """Lee el estado del scheduler desde disco."""
    if os.path.exists(SCHEDULER_STATE):
        try:
            with open(SCHEDULER_STATE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def guardar_estado_scheduler(estado):
    """Guarda el estado del scheduler en disco."""
    os.makedirs(os.path.dirname(SCHEDULER_STATE), exist_ok=True)
    try:
        with open(SCHEDULER_STATE, "w", encoding="utf-8") as f:
            json.dump(estado, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Error guardando estado scheduler: {e}")


def ya_enviado_hoy(clave, hoy_str):
    """Verifica si ya se envió un mensaje identificado por clave hoy."""
    estado = leer_estado_scheduler()
    return estado.get(clave) == hoy_str


def marcar_enviado(clave, hoy_str):
    """Marca que ya se envió el mensaje de hoy."""
    estado = leer_estado_scheduler()
    estado[clave] = hoy_str
    guardar_estado_scheduler(estado)


# ─────────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────────


def hora_colombia():
    return datetime.now(timezone(timedelta(hours=-5)))


def enviar_telegram(chat_id, mensaje):
    if not chat_id or not TELEGRAM_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"❌ Error Telegram scheduler: {e}")


# ─────────────────────────────────────────────────────────────
# FINNHUB — precio actual
# ─────────────────────────────────────────────────────────────


def finnhub_precio(ticker):
    """Precio actual en tiempo real desde Finnhub."""
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_KEY},
            timeout=8,
        )
        data = r.json()
        precio = data.get("c", 0)
        return float(precio) if precio else None
    except Exception as e:
        print(f"❌ Finnhub precio {ticker}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# CÁLCULO TIEMPO REAL (Finnhub, sin yfinance)
# ─────────────────────────────────────────────────────────────


def calcular_tiempo_real_simple(portafolio):
    """
    Calcula valor actual del portafolio usando Finnhub.
    Reemplaza completamente el uso de yfinance.
    """
    try:
        import pandas as pd

        if not portafolio.get("aportes"):
            return None

        trm_path = os.path.join(BASE_DIR, "datos", "macro", "trm.parquet")
        try:
            trm_actual = float(pd.read_parquet(trm_path)["TRM"].iloc[-1])
        except:
            trm_actual = 4000

        inf_anual = portafolio.get("inflacion_col", 4.90)

        # Agrupar aportes por ticker
        pos_raw = {}
        for a in portafolio["aportes"]:
            tk = a["activo"]
            if tk not in pos_raw:
                pos_raw[tk] = {
                    "fracciones": 0,
                    "invertido": 0,
                    "fecha_inicio": a["fecha"],
                }
            pos_raw[tk]["fracciones"] += a["fracciones"]
            pos_raw[tk]["invertido"] += a["monto_cop"]

        resultados = []
        total_inv = total_val = 0

        for tk, d in pos_raw.items():
            precio = finnhub_precio(tk)
            if precio is None:
                print(f"⚠️ Sin precio Finnhub para {tk}, saltando")
                continue
            time.sleep(0.5)  # respetar rate limit Finnhub free (60 req/min)

            val = d["fracciones"] * precio * trm_actual
            años = (
                datetime.now() - datetime.strptime(d["fecha_inicio"], "%Y-%m-%d")
            ).days / 365.25
            inv_r = d["invertido"] / (1 + inf_anual / 100) ** años
            gan = val - inv_r

            resultados.append(
                {
                    "activo": tk,
                    "valor_hoy": round(val, 0),
                    "ganancia": round(gan, 0),
                    "rentabilidad": round((gan / inv_r * 100) if inv_r > 0 else 0, 2),
                }
            )
            total_inv += inv_r
            total_val += val

        if not resultados:
            return None

        return {
            "posiciones": resultados,
            "total_invertido": round(total_inv, 0),
            "total_valor": round(total_val, 0),
            "ganancia_total": round(total_val - total_inv, 0),
            "rentabilidad_total": round(
                (total_val - total_inv) / total_inv * 100 if total_inv > 0 else 0, 2
            ),
        }

    except Exception as e:
        print(f"❌ Error calcular tiempo real scheduler: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# CONSTRUCCIÓN DE MENSAJES
# ─────────────────────────────────────────────────────────────


def construir_mensaje_portafolio(
    portafolio, datos_tr, nombre_usuario, total_portafolios
):
    nombre = portafolio.get("nombre", "Mi Portafolio")
    perfil = portafolio.get("perfil", "").upper()

    encabezado = (
        f"📊 <b>Resumen diario — {nombre_usuario}</b>\n"
        f"📁 Portafolio: <b>{nombre}</b> · {perfil}\n"
        if total_portafolios > 1
        else f"📊 <b>Resumen diario — {nombre_usuario}</b>\n📁 {nombre} · {perfil}\n"
    )

    if not datos_tr:
        return (
            encabezado + "\n⏳ Sin inversiones registradas aún.\n"
            "Entra al sistema para registrar tu primera compra.\n\n"
            f"<i>Sistema de Portafolio · {datetime.now().strftime('%d %b %Y')}</i>"
        )

    gl = datos_tr["ganancia_total"]
    gl_pct = datos_tr["rentabilidad_total"]
    emoji_gl = "📈" if gl >= 0 else "📉"
    signo = "+" if gl >= 0 else ""

    lineas_activos = ""
    for pos in datos_tr["posiciones"]:
        emoji_pos = "🟢" if pos["ganancia"] >= 0 else "🔴"
        signo_pos = "+" if pos["rentabilidad"] >= 0 else ""
        lineas_activos += (
            f"  {emoji_pos} <b>{pos['activo']}</b> — "
            f"${pos['valor_hoy']:,.0f} COP "
            f"({signo_pos}{pos['rentabilidad']}%)\n"
        )

    # Señales del monitor
    senal_html = ""
    archivo = portafolio.get("_archivo", "")
    ruta_monitor = os.path.join(CARPETA_PORTAFOLIOS, f"monitor_{archivo}")
    if os.path.exists(ruta_monitor):
        try:
            with open(ruta_monitor, "r", encoding="utf-8") as f:
                m = json.load(f)
            resultados = m.get("resultados", [])
            entrar = [r["ticker"] for r in resultados if r.get("senal") == "ENTRAR"]
            vigilar = [r["ticker"] for r in resultados if r.get("senal") == "VIGILAR"]
            if entrar:
                senal_html += f"\n🟢 <b>Señal ENTRAR:</b> {', '.join(entrar)}"
            if vigilar:
                senal_html += f"\n🟡 <b>Vigilar:</b> {', '.join(vigilar)}"
        except:
            pass

    return (
        encabezado + f"\n💰 <b>Valor total:</b> ${datos_tr['total_valor']:,.0f} COP\n"
        f"📥 <b>Invertido:</b> ${datos_tr['total_invertido']:,.0f} COP\n"
        f"{emoji_gl} <b>Ganancia real:</b> {signo}${gl:,.0f} COP ({signo}{gl_pct}%)\n"
        f"\n<b>Posiciones:</b>\n{lineas_activos}"
        + senal_html
        + f"\n\n<i>Sistema de Portafolio · {datetime.now().strftime('%d %b %Y')}</i>"
    )


# ─────────────────────────────────────────────────────────────
# APERTURA (9:00am)
# ─────────────────────────────────────────────────────────────


def enviar_apertura():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ☀️ Enviando apertura...")
    try:
        from monitor import leer_portafolios_activos, chat_id_de

        portafolios = leer_portafolios_activos()

        for archivo, _ in portafolios:
            try:
                ruta = os.path.join(CARPETA_PORTAFOLIOS, archivo)
                with open(ruta, "r", encoding="utf-8") as f:
                    p = json.load(f)

                chat_id = chat_id_de(p)
                if not chat_id:
                    continue

                datos_tr = calcular_tiempo_real_simple(p)
                tickers = list(p.get("composicion", {}).keys())
                ahora = hora_colombia()
                dia = ["lunes", "martes", "miércoles", "jueves", "viernes"][
                    ahora.weekday()
                ]

                if datos_tr:
                    gl = datos_tr["ganancia_total"]
                    signo = "+" if gl >= 0 else ""
                    emoji = "📈" if gl >= 0 else "📉"
                    valor_html = (
                        f"\n💰 Portafolio ayer cierre: <b>${datos_tr['total_valor']:,.0f} COP</b>\n"
                        f"{emoji} Ganancia real: <b>{signo}${gl:,.0f} ({signo}{datos_tr['rentabilidad_total']}%)</b>"
                    )
                else:
                    valor_html = "\n💰 Sin inversiones registradas aún."

                msg = (
                    f"☀️ <b>Buenos días — {dia} {ahora.strftime('%d/%m')}</b>\n"
                    f"📋 <b>{p.get('nombre', 'Portafolio')}</b>"
                    f"{valor_html}\n\n"
                    f"🔍 Monitoreando: <b>{', '.join(tickers)}</b>\n"
                    f"⏰ En 30 min abre el NYSE. Te aviso si encuentro señales de entrada.\n\n"
                    f"<i>Responde a las alertas: 'ya entré', 'no voy a entrar', o 'sigue informando'</i>"
                )

                enviar_telegram(chat_id, msg)
                print(f"  ☀️ Apertura enviada: {p.get('nombre')}")

            except Exception as e:
                print(f"❌ Error apertura {archivo}: {e}")

    except Exception as e:
        print(f"❌ Error general apertura: {e}")


# ─────────────────────────────────────────────────────────────
# CIERRE (4:05pm)
# ─────────────────────────────────────────────────────────────


def enviar_cierre():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📋 Enviando cierre...")
    try:
        from monitor import leer_portafolios_activos, chat_id_de, leer_estado
        import anthropic

        portafolios = leer_portafolios_activos()

        for archivo, _ in portafolios:
            try:
                ruta = os.path.join(CARPETA_PORTAFOLIOS, archivo)
                with open(ruta, "r", encoding="utf-8") as f:
                    p = json.load(f)

                chat_id = chat_id_de(p)
                if not chat_id:
                    continue

                datos_tr = calcular_tiempo_real_simple(p)
                estado = leer_estado(archivo)
                resultados = estado.get("resultados", [])

                ahora = hora_colombia()
                es_viernes = ahora.weekday() == 4

                # Valor de cierre
                if datos_tr:
                    gl = datos_tr["ganancia_total"]
                    signo = "+" if gl >= 0 else ""
                    emoji = "📈" if gl >= 0 else "📉"
                    valor_html = (
                        f"💰 Cierre: <b>${datos_tr['total_valor']:,.0f} COP</b>\n"
                        f"{emoji} Ganancia real: <b>{signo}${gl:,.0f} ({signo}{datos_tr['rentabilidad_total']}%)</b>"
                    )
                else:
                    valor_html = "💰 Sin inversiones registradas."

                # Resumen de activos
                resumen_activos = ""
                if resultados:
                    for r in sorted(resultados, key=lambda x: x["score"], reverse=True):
                        em = {"ENTRAR": "🟢", "VIGILAR": "🟡", "NEUTRAL": "⚪"}.get(
                            r["senal"], "⚪"
                        )
                        cambio_str = (
                            f" ({r['cambio_dia']:+.2f}%)"
                            if r.get("cambio_dia") is not None
                            else ""
                        )
                        resumen_activos += (
                            f"{em} <b>{r['ticker']}</b> ${r['precio']:,.2f}{cambio_str} · "
                            f"Score {r['score']}/10 · RSI {r['rsi']}\n"
                        )

                # Análisis IA
                ia_txt = ""
                try:
                    client = anthropic.Anthropic(
                        api_key=os.environ.get("ANTHROPIC_API_KEY", "")
                    )
                    resumen_data = (
                        "\n".join(
                            f"- {r['ticker']}: ${r['precio']} | RSI {r['rsi']} | "
                            f"Score {r['score']}/10 | {r['senal']} | tendencia {r['tendencia']:+.1f}%"
                            for r in resultados
                        )
                        if resultados
                        else "Sin datos de mercado hoy."
                    )

                    entradas = [
                        r["ticker"] for r in resultados if r["senal"] == "ENTRAR"
                    ]
                    vigilar = [
                        r["ticker"] for r in resultados if r["senal"] == "VIGILAR"
                    ]

                    prompt = (
                        f"Eres el analista de {p.get('propietario', 'el inversor')}. "
                        f"Hoy cerraron estos activos:\n{resumen_data}\n\n"
                        f"Escribe exactamente 3 oraciones:\n"
                        f"1. Cómo estuvo el mercado hoy en general.\n"
                        f"2. El activo más destacado del día (con número).\n"
                        f"3. Qué vigilar mañana.\n"
                        f"Sin asteriscos. Sin bullets. Directo. Máximo 60 palabras."
                    )

                    if es_viernes:
                        prompt += (
                            "\n\nAgrega UN párrafo final de máximo 2 oraciones con el plan "
                            "para la semana que viene. Muy puntual."
                        )

                    resp = client.messages.create(
                        model="claude-sonnet-4-5",
                        max_tokens=200,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    ia_txt = resp.content[0].text.strip()
                except Exception as e:
                    print(f"❌ IA cierre error: {e}")

                dias_sin = estado.get("dias_consecutivos_sin_senal", 0)
                senal_resumen = ""
                if entradas:
                    senal_resumen = (
                        f"\n🎯 Señales de entrada hoy: <b>{', '.join(entradas)}</b>"
                    )
                elif vigilar:
                    senal_resumen = f"\n👁 En vigilancia: <b>{', '.join(vigilar)}</b>"
                else:
                    senal_resumen = "\n⚪ Sin señales de entrada hoy"

                if dias_sin > 0:
                    senal_resumen += f" · {dias_sin} días hábiles sin señal"

                msg = (
                    f"📋 <b>Cierre de mercado — {p.get('nombre', 'Portafolio')}</b>\n\n"
                    f"{valor_html}\n\n"
                    f"<b>Activos hoy:</b>\n{resumen_activos}"
                    f"{senal_resumen}\n\n" + (f"💬 {ia_txt}" if ia_txt else "")
                )

                # Limpiar alertas del día al cerrar
                _limpiar_alertas_hoy(archivo)

                enviar_telegram(chat_id, msg)
                print(f"  📋 Cierre enviado: {p.get('nombre')}")

            except Exception as e:
                print(f"❌ Error cierre {archivo}: {e}")

    except Exception as e:
        print(f"❌ Error general cierre: {e}")


# ─────────────────────────────────────────────────────────────
# LIMPIAR ALERTAS AL CIERRE
# ─────────────────────────────────────────────────────────────


def _limpiar_alertas_hoy(archivo):
    """Al cerrar el mercado, resetea las alertas del día para que mañana arranquen limpias."""
    try:
        ruta_monitor = os.path.join(CARPETA_PORTAFOLIOS, f"monitor_{archivo}")
        if os.path.exists(ruta_monitor):
            with open(ruta_monitor, "r", encoding="utf-8") as f:
                estado = json.load(f)
            estado["alertas_enviadas_hoy"] = {}
            estado["decisiones_usuario"] = {}
            with open(ruta_monitor, "w", encoding="utf-8") as f:
                json.dump(estado, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Error limpiando alertas: {e}")


# ─────────────────────────────────────────────────────────────
# LOOP PRINCIPAL — estado en disco, no en memoria
# ─────────────────────────────────────────────────────────────


def loop_scheduler():
    print("⏰ Scheduler iniciado")

    while True:
        try:
            ahora = hora_colombia()
            hoy = ahora.strftime("%Y-%m-%d")
            es_dia_habil = ahora.weekday() < 5
            hora = ahora.hour
            minuto = ahora.minute

            # ── Apertura: exactamente a las 9:00am ────────────
            if hora == 9 and minuto < 5 and es_dia_habil:
                clave = f"apertura_{hoy}"
                if not ya_enviado_hoy(clave, hoy):
                    enviar_apertura()
                    marcar_enviado(clave, hoy)

            # ── Cierre: exactamente a las 4:05pm ──────────────
            if hora == 16 and minuto >= 5 and minuto < 15 and es_dia_habil:
                clave = f"cierre_{hoy}"
                if not ya_enviado_hoy(clave, hoy):
                    enviar_cierre()
                    marcar_enviado(clave, hoy)

        except Exception as e:
            print(f"❌ Error en scheduler loop: {e}")

        time.sleep(60)  # revisar cada minuto


def iniciar_scheduler():
    t = threading.Thread(target=loop_scheduler, daemon=True, name="scheduler")
    t.start()
    return t
