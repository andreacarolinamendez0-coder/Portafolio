"""
Scheduler de tareas programadas — corre en background junto a la app.
"""
import threading
import time
import os
import json
from datetime import datetime
import requests

TELEGRAM_TOKEN      = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CARPETA_PORTAFOLIOS = "datos/portafolios"


def enviar_telegram(chat_id, mensaje):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": mensaje, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print(f"❌ Error Telegram scheduler: {e}")


def construir_mensaje_portafolio(portafolio, datos_tr, nombre_usuario, total_portafolios):
    nombre = portafolio.get("nombre", "Mi Portafolio")
    perfil = portafolio.get("perfil", "").upper()

    if total_portafolios > 1:
        encabezado = (
            f"📊 <b>Resumen diario — {nombre_usuario}</b>\n"
            f"📁 Portafolio: <b>{nombre}</b> · {perfil}\n"
        )
    else:
        encabezado = (
            f"📊 <b>Resumen diario — {nombre_usuario}</b>\n"
            f"📁 {nombre} · {perfil}\n"
        )

    if not datos_tr:
        return (
            encabezado +
            f"\n⏳ Sin inversiones registradas aún.\n"
            f"Entra al sistema para registrar tu primera compra.\n\n"
            f"<i>Sistema de Portafolio · {datetime.now().strftime('%d %b %Y')}</i>"
        )

    gl     = datos_tr["ganancia_total"]
    gl_pct = datos_tr["rentabilidad_total"]
    emoji_gl = "📈" if gl >= 0 else "📉"
    signo    = "+" if gl >= 0 else ""

    lineas_activos = ""
    for pos in datos_tr["posiciones"]:
        emoji_pos = "🟢" if pos["ganancia"] >= 0 else "🔴"
        signo_pos = "+" if pos["rentabilidad"] >= 0 else ""
        lineas_activos += (
            f"  {emoji_pos} <b>{pos['activo']}</b> — "
            f"${pos['valor_hoy']:,.0f} COP "
            f"({signo_pos}{pos['rentabilidad']}%)\n"
        )

    senal_html = ""
    archivo    = portafolio.get("_archivo", "")
    ruta_monitor = f"{CARPETA_PORTAFOLIOS}/monitor_{archivo}"
    if os.path.exists(ruta_monitor):
        try:
            with open(ruta_monitor, 'r', encoding='utf-8') as f:
                m = json.load(f)
            resultados = m.get("resultados", [])
            entrar  = [r["ticker"] for r in resultados if r.get("senal") == "ENTRAR"]
            vigilar = [r["ticker"] for r in resultados if r.get("senal") == "VIGILAR"]
            if entrar:
                senal_html += f"\n🟢 <b>Señal ENTRAR:</b> {', '.join(entrar)}"
            if vigilar:
                senal_html += f"\n🟡 <b>Vigilar:</b> {', '.join(vigilar)}"
        except:
            pass

    return (
        encabezado +
        f"\n💰 <b>Valor total:</b> ${datos_tr['total_valor']:,.0f} COP\n"
        f"📥 <b>Invertido:</b> ${datos_tr['total_invertido']:,.0f} COP\n"
        f"{emoji_gl} <b>Ganancia real:</b> {signo}${gl:,.0f} COP ({signo}{gl_pct}%)\n"
        f"\n<b>Posiciones:</b>\n{lineas_activos}"
        + senal_html +
        f"\n\n<i>Sistema de Portafolio · {datetime.now().strftime('%d %b %Y')}</i>"
    )


def calcular_tiempo_real_simple(portafolio):
    try:
        import pandas as pd
        import yfinance as yf
        from datetime import timedelta

        if not portafolio.get('aportes'):
            return None

        BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
        trm_path  = os.path.join(BASE_DIR, "datos", "macro", "trm.parquet")
        try:
            trm_actual = float(pd.read_parquet(trm_path)['TRM'].iloc[-1])
        except:
            trm_actual = 4000

        inf_anual = portafolio.get('inflacion_col', 4.90)
        pos_raw   = {}
        for a in portafolio['aportes']:
            tk = a['activo']
            if tk not in pos_raw:
                pos_raw[tk] = {'fracciones': 0, 'invertido': 0, 'fecha_inicio': a['fecha']}
            pos_raw[tk]['fracciones'] += a['fracciones']
            pos_raw[tk]['invertido']  += a['monto_cop']

        resultados = []
        total_inv = total_val = 0

        for tk, d in pos_raw.items():
            try:
                hoy = datetime.now()
                df  = yf.download(tk, start=(hoy - timedelta(days=5)).strftime("%Y-%m-%d"),
                                  end=hoy.strftime("%Y-%m-%d"), interval="1d",
                                  auto_adjust=True, progress=False)
                if df.empty:
                    continue
                if hasattr(df.columns, 'get_level_values'):
                    df.columns = df.columns.get_level_values(0)
                precio = float(df['Close'].iloc[-1])
            except:
                continue

            val   = d['fracciones'] * precio * trm_actual
            años  = (datetime.now() - datetime.strptime(d['fecha_inicio'], "%Y-%m-%d")).days / 365.25
            inv_r = d['invertido'] / (1 + inf_anual / 100) ** años
            gan   = val - inv_r

            resultados.append({
                'activo':       tk,
                'valor_hoy':    round(val, 0),
                'ganancia':     round(gan, 0),
                'rentabilidad': round((gan / inv_r * 100) if inv_r > 0 else 0, 2)
            })
            total_inv += inv_r
            total_val += val

        if not resultados:
            return None

        return {
            'posiciones':         resultados,
            'total_invertido':    round(total_inv, 0),
            'total_valor':        round(total_val, 0),
            'ganancia_total':     round(total_val - total_inv, 0),
            'rentabilidad_total': round((total_val - total_inv) / total_inv * 100 if total_inv > 0 else 0, 2)
        }
    except Exception as e:
        print(f"❌ Error calcular tiempo real scheduler: {e}")
        return None


def enviar_resumenes_diarios():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📨 Enviando resúmenes diarios...")
    try:
        BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
        usuarios_path = os.path.join(BASE_DIR, "datos", "usuarios.json")

        if not os.path.exists(usuarios_path):
            print("❌ No existe usuarios.json")
            return

        with open(usuarios_path, 'r', encoding='utf-8') as f:
            usuarios = json.load(f)

        for username, usuario in usuarios.items():
            chat_id = usuario.get("telegram_chat_id", "").strip()
            if not chat_id:
                continue

            portafolios_usuario = []
            if os.path.exists(CARPETA_PORTAFOLIOS):
                for archivo in os.listdir(CARPETA_PORTAFOLIOS):
                    if archivo.endswith('.json') and not archivo.startswith('monitor_'):
                        try:
                            ruta = f"{CARPETA_PORTAFOLIOS}/{archivo}"
                            with open(ruta, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            if data.get('owner') == username:
                                data['_archivo'] = archivo
                                portafolios_usuario.append(data)
                        except:
                            continue

            if not portafolios_usuario:
                continue

            total = len(portafolios_usuario)

            if total > 1:
                enviar_telegram(chat_id,
                    f"☀️ <b>Buenos días, {username}!</b>\n"
                    f"Tienes <b>{total} portafolios</b> activos. "
                    f"Aquí va el resumen de cada uno 👇"
                )
                time.sleep(1)

            for portafolio in portafolios_usuario:
                datos_tr = calcular_tiempo_real_simple(portafolio)
                mensaje  = construir_mensaje_portafolio(portafolio, datos_tr, username, total)
                enviar_telegram(chat_id, mensaje)
                time.sleep(1)

            print(f"✅ Resumen enviado a {username} ({total} portafolios)")

    except Exception as e:
        print(f"❌ Error en enviar_resumenes_diarios: {e}")


def enviar_buenos_dias_monitor():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ☀️ Enviando buenos días del monitor...")
    try:
        from monitor import enviar_buenos_dias, leer_portafolios_activos
        portafolios = leer_portafolios_activos()
        for archivo, portafolio in portafolios:
            try:
                ruta = os.path.join(CARPETA_PORTAFOLIOS, archivo)
                with open(ruta, 'r', encoding='utf-8') as f:
                    portafolio_fresco = json.load(f)
                enviar_buenos_dias(archivo, portafolio_fresco)
            except Exception as e:
                print(f"❌ Error buenos días {archivo}: {e}")
    except Exception as e:
        print(f"❌ Error general buenos días monitor: {e}")


def enviar_cierre_monitor():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📋 Enviando reportes de cierre...")
    try:
        from monitor import leer_portafolios_activos, leer_estado, reporte_cierre
        portafolios = leer_portafolios_activos()
        for archivo, portafolio in portafolios:
            try:
                ruta = os.path.join(CARPETA_PORTAFOLIOS, archivo)
                with open(ruta, 'r', encoding='utf-8') as f:
                    portafolio_fresco = json.load(f)
                estado = leer_estado(archivo)
                if estado:
                    reporte_cierre(archivo, portafolio_fresco, estado)
                else:
                    print(f"⚠️ Sin estado de monitor para {archivo}")
            except Exception as e:
                print(f"❌ Error cierre {archivo}: {e}")
    except Exception as e:
        print(f"❌ Error general cierre monitor: {e}")


def loop_scheduler():
    print("⏰ Scheduler iniciado")
    enviado_resumen = None
    enviado_buenos  = None
    enviado_cierre  = None

    while True:
        try:
            from datetime import timezone, timedelta
            utc_minus5 = timezone(timedelta(hours=-5))
            ahora = datetime.now(utc_minus5)
            hoy   = ahora.date()
            es_dia_habil = ahora.weekday() < 5

            # 8:00am o después — resumen diario de valor
            if ahora.hour >= 8 and enviado_resumen != hoy:
                enviar_resumenes_diarios()
                enviado_resumen = hoy

            # 9:00am o después — buenos días monitor (días hábiles)
            if ahora.hour >= 9 and es_dia_habil and enviado_buenos != hoy:
                enviar_buenos_dias_monitor()
                enviado_buenos = hoy

            # 4:05pm o después — reporte de cierre (días hábiles)
            if (ahora.hour > 16 or (ahora.hour == 16 and ahora.minute >= 5)) and es_dia_habil and enviado_cierre != hoy:
                enviar_cierre_monitor()
                enviado_cierre = hoy

        except Exception as e:
            print(f"❌ Error en scheduler loop: {e}")
        time.sleep(60)


def iniciar_scheduler():
    t = threading.Thread(target=loop_scheduler, daemon=True, name="scheduler")
    t.start()
    return t