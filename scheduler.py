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


def enviar_apertura():
    """9:00am — valor actual + activos a monitorear hoy."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ☀️ Enviando mensaje de apertura...")
    try:
        from monitor import leer_portafolios_activos, chat_id_de
        portafolios = leer_portafolios_activos()

        for archivo, portafolio in portafolios:
            try:
                ruta = os.path.join(CARPETA_PORTAFOLIOS, archivo)
                with open(ruta, 'r', encoding='utf-8') as f:
                    p = json.load(f)

                chat_id = chat_id_de(p)
                if not chat_id:
                    continue

                # Valor actual del portafolio
                datos_tr = calcular_tiempo_real_simple(p)
                tickers  = list(p.get('composicion', {}).keys())

                from datetime import datetime as dt
                ahora     = dt.utcnow().replace(tzinfo=None) - __import__('datetime').timedelta(hours=5)
                dia       = ["lunes","martes","miércoles","jueves","viernes"][ahora.weekday()]
                fecha_str = ahora.strftime('%d/%m')

                if datos_tr:
                    gl     = datos_tr['ganancia_total']
                    signo  = "+" if gl >= 0 else ""
                    emoji  = "📈" if gl >= 0 else "📉"
                    valor_html = (
                        f"\n💰 Portafolio hoy: <b>${datos_tr['total_valor']:,.0f} COP</b>\n"
                        f"{emoji} Ganancia real: <b>{signo}${gl:,.0f} ({signo}{datos_tr['rentabilidad_total']}%)</b>"
                    )
                else:
                    valor_html = "\n💰 Sin inversiones registradas aún."

                msg = (
                    f"☀️ <b>Buenos días — {dia} {fecha_str}</b>\n"
                    f"📋 <b>{p.get('nombre','Portafolio')}</b>"
                    f"{valor_html}\n\n"
                    f"🔍 Monitoreando: <b>{', '.join(tickers)}</b>\n"
                    f"⏰ En 30 min abre el NYSE. Te aviso si encuentro señales de entrada."
                )

                enviar_telegram(chat_id, msg)
                print(f"  ☀️ Apertura enviada: {p.get('nombre')}")

            except Exception as e:
                print(f"❌ Error apertura {archivo}: {e}")

    except Exception as e:
        print(f"❌ Error general apertura: {e}")


def enviar_cierre():
    """4:05pm — valor de cierre + resumen del mercado + plan si es viernes."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📋 Enviando mensaje de cierre...")
    try:
        from monitor import leer_portafolios_activos, chat_id_de, leer_estado
        import anthropic, os as _os

        portafolios = leer_portafolios_activos()

        for archivo, portafolio in portafolios:
            try:
                ruta = os.path.join(CARPETA_PORTAFOLIOS, archivo)
                with open(ruta, 'r', encoding='utf-8') as f:
                    p = json.load(f)

                chat_id = chat_id_de(p)
                if not chat_id:
                    continue

                datos_tr  = calcular_tiempo_real_simple(p)
                estado    = leer_estado(archivo)
                resultados = estado.get('resultados', [])

                from datetime import datetime as dt
                ahora      = dt.utcnow() - __import__('datetime').timedelta(hours=5)
                es_viernes = ahora.weekday() == 4

                # Valor de cierre
                if datos_tr:
                    gl    = datos_tr['ganancia_total']
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
                    for r in sorted(resultados, key=lambda x: x['score'], reverse=True):
                        em = {"ENTRAR":"🟢","VIGILAR":"🟡","NEUTRAL":"⚪"}.get(r['senal'],'⚪')
                        resumen_activos += (
                            f"{em} <b>{r['ticker']}</b> ${r['precio']:,.2f} · "
                            f"Score {r['score']}/10 · RSI {r['rsi']}\n"
                        )

                # Análisis IA — corto y puntual
                ia_txt = ""
                try:
                    client = anthropic.Anthropic(api_key=_os.environ.get("ANTHROPIC_API_KEY",""))
                    resumen_data = "\n".join(
                        f"- {r['ticker']}: ${r['precio']} | RSI {r['rsi']} | Score {r['score']}/10 | {r['senal']} | tendencia {r['tendencia']:+.1f}%"
                        for r in resultados
                    ) if resultados else "Sin datos de mercado hoy."

                    entradas = [r['ticker'] for r in resultados if r['senal'] == 'ENTRAR']
                    vigilar  = [r['ticker'] for r in resultados if r['senal'] == 'VIGILAR']

                    prompt_base = (
                        f"Eres el analista de {p.get('propietario','el inversor')}. "
                        f"Hoy cerraron estos activos:\n{resumen_data}\n\n"
                        f"Escribe exactamente 3 oraciones:\n"
                        f"1. Cómo estuvo el mercado hoy en general (una frase).\n"
                        f"2. El activo más destacado del día, positivo o negativo (una frase con número).\n"
                        f"3. Qué vigilar mañana (una frase concreta).\n"
                        f"Sin asteriscos. Sin bullets. Directo. Máximo 60 palabras en total."
                    )

                    if es_viernes:
                        prompt_base += (
                            f"\n\nAdemás agrega UN párrafo final de máximo 2 oraciones con el plan "
                            f"para la semana que viene: qué activos priorizar y si el momento es "
                            f"favorable para entrar o esperar. Muy puntual."
                        )

                    resp = client.messages.create(
                        model="claude-sonnet-4-5",
                        max_tokens=200,
                        messages=[{"role":"user","content": prompt_base}]
                    )
                    ia_txt = resp.content[0].text.strip()
                except Exception as e:
                    print(f"❌ IA cierre error: {e}")

                # Armar mensaje final
                dias_sin = estado.get('dias_consecutivos_sin_senal', 0)
                senal_resumen = ""
                if entradas:
                    senal_resumen = f"\n🎯 Señales de entrada hoy: <b>{', '.join(entradas)}</b>"
                elif vigilar:
                    senal_resumen = f"\n👁 En vigilancia: <b>{', '.join(vigilar)}</b>"
                else:
                    senal_resumen = f"\n⚪ Sin señales de entrada hoy"

                if dias_sin > 0:
                    senal_resumen += f" · {dias_sin} días hábiles sin señal"

                msg = (
                    f"📋 <b>Cierre de mercado — {p.get('nombre','Portafolio')}</b>\n\n"
                    f"{valor_html}\n\n"
                    f"<b>Activos hoy:</b>\n{resumen_activos}"
                    f"{senal_resumen}\n\n"
                    f"💬 {ia_txt}"
                )

                enviar_telegram(chat_id, msg)
                print(f"  📋 Cierre enviado: {p.get('nombre')}")

            except Exception as e:
                print(f"❌ Error cierre {archivo}: {e}")

    except Exception as e:
        print(f"❌ Error general cierre: {e}")


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

            # 9:00am o después — apertura (días hábiles)
            if ahora.hour >= 9 and es_dia_habil and enviado_buenos != hoy:
                enviar_apertura()
            enviado_buenos = hoy

            # 4:05pm o después — cierre (días hábiles)
            if (ahora.hour > 16 or (ahora.hour == 16 and ahora.minute >= 5)) and es_dia_habil and enviado_cierre != hoy:
                enviar_cierre()
            enviado_cierre = hoy

        except Exception as e:
            print(f"❌ Error en scheduler loop: {e}")
        time.sleep(60)


def iniciar_scheduler():
    t = threading.Thread(target=loop_scheduler, daemon=True, name="scheduler")
    t.start()
    return t