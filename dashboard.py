import dotenv

dotenv.load_dotenv()
from flask import Flask, request, session, jsonify
import pandas as pd
import json, os, requests, time, threading
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import yfinance as yf
from zoneinfo import ZoneInfo
import anthropic
import warnings
import math
from flask.json.provider import DefaultJSONProvider

warnings.filterwarnings("ignore")

from gestor_portafolio import (
    leer_portafolio,
    _leer_logs,
    _leer_usuarios,
    listar_portafolios_de_usuario,
    crear_portafolio_para_usuario,
    guardar_composicion,
    guardar_aporte,
    asegurar_ids_aportes,
    eliminar_aporte,
    editar_aporte,
    registrar_usuario,
    login_usuario,
    registrar_actividad,
    get_usuario,
    actualizar_usuario,
    resetear_password,
    desbloquear_usuario,
    eliminar_usuario,
    hash_password_secure,
    verify_password,
    _slug,
    get_usuario_por_email,
    huella_password_hash,
)

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import secrets, hashlib
from emails import enviar_pin_activacion, enviar_reset_password

TZ_NY = ZoneInfo("America/New_York")
TZ_COL = ZoneInfo("America/Bogota")


def mercado_abierto_ahora():
    ny = datetime.now(TZ_NY)
    if ny.weekday() >= 5:
        return False
    apertura = ny.replace(hour=9, minute=30, second=0, microsecond=0)
    cierre = ny.replace(hour=16, minute=0, second=0, microsecond=0)
    return apertura <= ny <= cierre


def arrancar_monitor():
    time.sleep(15)
    from monitor import iniciar_monitor

    iniciar_monitor()
    registrar_webhook_telegram()


threading.Thread(target=arrancar_monitor, daemon=True).start()

app = Flask(__name__)
# Ruta base absoluta para que funcione en Railway y en local
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATOS_DIR = os.path.join(BASE_DIR, "datos")
os.makedirs(os.path.join(DATOS_DIR, "macro"), exist_ok=True)
os.makedirs(os.path.join(DATOS_DIR, "precios"), exist_ok=True)
os.makedirs(os.path.join(DATOS_DIR, "portafolios"), exist_ok=True)
os.makedirs(os.path.join(DATOS_DIR, "Logs"), exist_ok=True)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("SECRET_KEY environment variable is not set")


class ProveedorJSONSeguro(DefaultJSONProvider):
    """JSON provider que convierte NaN/Infinity en None antes de serializar.
 
    JSON estandar no admite NaN ni Infinity. Sin esto, cualquier calculo que
    de NaN (division por cero, dato faltante) rompe el frontend entero.
    """
    def dumps(self, obj, **kwargs):
        return super().dumps(_limpiar_nan(obj), **kwargs)
 
def _limpiar_nan(o):
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return None          # NaN/Infinity -> null (el frontend ya maneja null)
        return o
    if isinstance(o, dict):
        return {k: _limpiar_nan(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_limpiar_nan(v) for v in o]
    return o
 
# Activarlo (va inmediatamente despues de crear app):
app.json = ProveedorJSONSeguro(app)

# ============================================================
# UTILIDADES
# ============================================================


def verificar_acceso(archivo):
    username = session.get("username")
    if not username:
        return jsonify({"error": "No autorizado"}), 401
    p = leer_portafolio(archivo)
    if not p or p.get("owner") != username:
        return jsonify({"error": "No autorizado"}), 403
    return None


def _request_meta():
    ip = (
        request.headers.get("X-Forwarded-For", request.remote_addr or "—")
        .split(",")[0]
        .strip()
    )
    dispositivo = request.headers.get("User-Agent", "—")[:120]
    return ip, dispositivo


def anthropic_chat(messages, system="", max_tokens=300, temperature=0.5):
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    kwargs = {
        "model": "claude-sonnet-4-5",
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return resp.content[0].text


def cargar_macro():
    archivos = [
        os.path.join(DATOS_DIR, "macro/trm.parquet"),
        os.path.join(DATOS_DIR, "macro/inflacion_col.parquet"),
        os.path.join(DATOS_DIR, "macro/inflacion_usa.parquet"),
        os.path.join(DATOS_DIR, "macro/risk_free.parquet"),
        os.path.join(DATOS_DIR, "macro/tasa_banrep.parquet"),
    ]
    if any(not os.path.exists(f) for f in archivos):
        os.makedirs("datos/macro", exist_ok=True)
        os.makedirs("datos/precios", exist_ok=True)
        os.makedirs("datos/portafolios", exist_ok=True)
        from recolector import correr_todo

        try:
            correr_todo()
        except Exception as e:
            print(f"Error running recolector: {e}")
            return None
    try:
        trm = pd.read_parquet(os.path.join(DATOS_DIR, "macro/trm.parquet"))
        inf_col = pd.read_parquet(
            os.path.join(DATOS_DIR, "macro/inflacion_col.parquet")
        )
        inf_usa = pd.read_parquet(
            os.path.join(DATOS_DIR, "macro/inflacion_usa.parquet")
        )
        risk_free = pd.read_parquet(os.path.join(DATOS_DIR, "macro/risk_free.parquet"))
        banrep = pd.read_parquet(os.path.join(DATOS_DIR, "macro/tasa_banrep.parquet"))
        trm_actual = float(trm["TRM"].iloc[-1])
        trm_hace_mes = float(trm["TRM"].iloc[-22]) if len(trm) > 22 else trm_actual
        return {
            "trm": round(trm_actual, 2),
            "trm_cambio": round(((trm_actual - trm_hace_mes) / trm_hace_mes) * 100, 2),
            "inf_col": round(float(inf_col["Inflacion_COL"].iloc[-1]), 2),
            "inf_usa": round(float(inf_usa["Inflacion_USA"].iloc[-1]), 2),
            "risk_free": round(float(risk_free["Risk_Free"].iloc[-1]), 2),
            "banrep": round(float(banrep["Tasa_Banrep"].iloc[-1]), 2),
            "cdt": round(float(banrep["Tasa_Banrep"].iloc[-1]) - 0.75, 2),
            "spread": round(
                float(inf_col["Inflacion_COL"].iloc[-1])
                - float(inf_usa["Inflacion_USA"].iloc[-1]),
                2,
            ),
            "trm_hist": trm.tail(90),
        }
    except Exception as e:
        print(f"❌ Error macro: {e}")
        return None


def obtener_tasa_usd_eur():
    """EUR por 1 USD. Cacheada un día. Fuente: ECB vía Frankfurter (gratis, sin key)."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    cache = os.path.join(DATOS_DIR, "macro", "tasa_eur.json")
    if os.path.exists(cache):
        try:
            with open(cache, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("fecha") == hoy:
                return data["tasa"]
        except Exception:
            pass
    try:
        r = requests.get("https://api.frankfurter.app/latest",
                         params={"from": "USD", "to": "EUR"}, timeout=8)
        r.raise_for_status()
        tasa = r.json()["rates"]["EUR"]
        with open(cache, "w", encoding="utf-8") as f:
            json.dump({"fecha": hoy, "tasa": tasa}, f)
        return tasa
    except Exception:
        if os.path.exists(cache):
            try:
                with open(cache, encoding="utf-8") as f:
                    return json.load(f)["tasa"]
            except Exception:
                pass
        return None

def precio_actual_usd(ticker):
    try:
        hoy = datetime.now()
        df = yf.download(
            ticker,
            start=(hoy - timedelta(days=5)).strftime("%Y-%m-%d"),
            end=hoy.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            df = yf.download(
                ticker, period="5d", interval="1d", auto_adjust=True, progress=False
            )
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return float(df["Close"].iloc[-1])
    except Exception as e:
        print(f"Error fetching price for {ticker}: {e}")
        return None


def calcular_tiempo_real(portafolio):
    if not portafolio or not portafolio.get("aportes"):
        return None
    try:
        trm_actual = float(pd.read_parquet("datos/macro/trm.parquet")["TRM"].iloc[-1])
    except Exception:
        # Sin TRM oficial no se puede valorar en COP; devolver "no disponible"
        # en vez de cifras calculadas con una TRM inventada (4000).
        return None
    inf_anual = portafolio.get("inflacion_col", 4.90)
    pos_raw = {}
    for a in portafolio["aportes"]:
        tk = a["activo"]
        if tk not in pos_raw:
            pos_raw[tk] = {"fracciones": 0, "invertido": 0, "fecha_inicio": a["fecha"]}
        pos_raw[tk]["fracciones"] += a["fracciones"]
        pos_raw[tk]["invertido"] += a["monto_cop"]
    resultados = []
    total_inv = total_val = 0
    for tk, d in pos_raw.items():
        p = precio_actual_usd(tk)
        if p is None:
            continue
        val = d["fracciones"] * p * trm_actual
        años = (
            datetime.now() - datetime.strptime(d["fecha_inicio"], "%Y-%m-%d")
        ).days / 365.25
        inv_r = d["invertido"] / (1 + inf_anual / 100) ** años
        gan = val - inv_r
        resultados.append(
            {
                "activo": tk,
                "fracciones": round(d["fracciones"], 4),
                "precio_hoy": round(p, 2),
                "valor_hoy": round(val, 0),
                "invertido": round(inv_r, 0),
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


def _sistema_analista(portafolio, composicion, tiene_inv):
    """Construye el system prompt del analista. Único punto de verdad."""
    from recolector import ACTIVOS_POR_SECTOR

    composicion_actual_txt = ""
    if composicion:
        composicion_actual_txt = "COMPOSICIÓN ACTUAL:\n" + "\n".join(
            f"  - {a}: {v*100:.1f}%" for a, v in composicion.items()
        )

    if composicion:
        opcion_6 = (
            f"6. La composición de activos (redistribuir entre tus actuales: "
            f'{", ".join(composicion.keys())}, o agregar/quitar activos)'
        )
        instruccion_6 = (
            "Si elige opción 6: pregunta qué quiere cambiar de la composición actual. "
            'Luego genera el JSON incluyendo "activos" con la composición final. '
            'SIEMPRE incluye "activos" cuando hay composición existente.\n'
            'Ejemplo: {"accion":"analizar","perfil":"agresivo","inversion":2000000,'
            '"aporte_dca":200000,"frecuencia_meses":1,"horizonte":10,"es_nuevo":false,'
            '"activos":{"WMT":0.265,"LLY":0.212,"XLK":0.159,"GOOGL":0.154,"MSFT":0.110,"VTI":0.100}}'
        )
    else:
        opcion_6 = "6. Definir la composición de activos (aún no tienes ninguna — te sugiero una optimizada para tu perfil)"
        instruccion_6 = (
            "Si elige opción 6: genera INMEDIATAMENTE el JSON con es_nuevo=true "
            "usando los datos ya conocidos del portafolio. NO hagas más preguntas.\n"
            'Ejemplo: {"accion":"analizar","perfil":"agresivo","inversion":1000000,'
            '"aporte_dca":200000,"frecuencia_meses":1,"horizonte":10,"es_nuevo":true}'
        )

    sectores_disponibles = ", ".join(sorted(ACTIVOS_POR_SECTOR.keys()))

    return (
        f"Eres un analista financiero senior especializado en portafolios de renta variable americana "
        f"para inversionistas colombianos. Tu cliente es {portafolio['propietario']}.\n\n"
        f"PORTAFOLIO:\n"
        f"- Perfil: {portafolio.get('perfil', 'no definido')} "
        f"({'10 años, maximizar retorno ajustado por riesgo' if portafolio.get('perfil') == 'agresivo' else '5 años, menor volatilidad'})\n"
        f"- Capital: ${portafolio.get('inversion_inicial', 0):,.0f} COP\n"
        f"- DCA: ${portafolio.get('aporte_dca', 0):,.0f} COP cada {portafolio.get('frecuencia_meses', 1)} mes(es)\n"
        f"- Con inversiones: {'sí' if tiene_inv else 'no'}\n"
        f"{composicion_actual_txt}\n\n"
        f"TU ESTILO:\n"
        f"- Una pregunta a la vez. Nunca varias en un mismo mensaje.\n"
        f"- Tienes criterio: si algo no conviene al cliente, lo dices con datos antes de ejecutar.\n"
        f"- Nunca pides información que ya tienes arriba.\n\n"
        f"Tu universo base son grandes empresas (líderes por sector) en: {sectores_disponibles}, "
        f"más ETFs sectoriales/temáticos y un puñado de criptomonedas principales. "
        f"Si el usuario pide algo más nicho o específico (ej. un ETF de biotech, ciberseguridad, energía limpia) puedes sugerir tickers reales fuera de esa base — "
        f"el sistema los descarga automáticamente la primera vez que se usan, así que no te limites a la lista si el tema lo amerita. "
        f"Eso sí: usa siempre tickers reales y reconocibles, nunca inventes símbolos.\n\n"
        f'IMPORTANTE: "activos" SIEMPRE debe ser tickers reales de bolsa (ej. "NVDA","VWO","XLK"), nunca categorías ni descripciones ("tecnología disruptiva", "mercados emergentes"). '
        f"Si sugieres una distribución temática, tradúcela a una cantidad eficiente de tickers reales que representen bien esa categoría "
        f"(normalmente 4-6, para darle margen al motor de elegir los de mejor desempeño) antes de generar el JSON. "
        f"Si el usuario restringe el portafolio a una sola categoría (ej. \"solo tecnología\", \"solo ETFs de bonos\"), acláraselo antes de generar el JSON: "
        f"el resultado final será un portafolio concentrado (2-3 activos de esa categoría, los de mejor desempeño), pensado como complemento y no "
        f"como su único portafolio de inversión, porque este análisis no evalúa su interacción con otros sectores o activos que ya tenga.\n\n"
        f"FLUJO A — PORTAFOLIO NUEVO: recoge en orden (uno por mensaje): perfil → monto → DCA → horizonte. "
        f"Si en la conversación el usuario mencionó sectores, temas o tickers de interés, tradúcelos a una cantidad eficiente de tickers reales (normalmente 4-6) antes del JSON final.\n"
        f'Cuando tengas todo, responde SOLO el JSON. Si hubo preferencias de sector/tema, incluye "activos":\n'
        f'{{"accion":"analizar","perfil":"agresivo","inversion":1000000,"aporte_dca":0,"frecuencia_meses":1,"horizonte":10,"es_nuevo":true,'
        f'"activos":{{"ARKG":0.25,"NVDA":0.20,"HACK":0.15,"ICLN":0.15,"SMH":0.15,"GOOGL":0.10}}}}\n'
        f'Si NO mencionó preferencias de sector, omite "activos" y deja que el optimizador elija automáticamente.\n\n'
        f"FLUJO B — ACTUALIZAR EXISTENTE: ya tienes los datos. Pregunta UNA VEZ qué quiere cambiar. "
        f"Evalúa si el cambio tiene sentido para su perfil. Si es riesgoso, díselo antes de proceder. "
        f'Luego genera el JSON con los valores finales (actuales + cambios). SIEMPRE incluye "activos" en actualizaciones.\n\n'
        f"Presenta UNA VEZ estas opciones al usuario:\n"
        f"1. El monto total invertido (actualmente ${portafolio.get('inversion_inicial', 0):,.0f} COP)\n"
        f"2. El aporte periódico DCA (actualmente ${portafolio.get('aporte_dca', 0):,.0f} COP cada {portafolio.get('frecuencia_meses', 1)} mes(es))\n"
        f"3. La frecuencia del DCA\n"
        f"4. El perfil de riesgo (actualmente {portafolio.get('perfil', 'no definido')})\n"
        f"5. El horizonte de inversión (actualmente {portafolio.get('horizonte', 10)} años)\n"
        f"{opcion_6}\n\n"
        f"{instruccion_6}\n\n"
        f"REGLAS: Una pregunta por mensaje, pero acompáñala SIEMPRE de 1-2 frases que expliquen por qué la preguntas o qué implica, en lenguaje sencillo. "
        f"Educa mientras preguntas. No asumas que el usuario sabe qué es perfil de riesgo, DCA u horizonte: explícalos brevemente la primera vez. "
        f"Sé cálido y claro, no seco. Máximo 4-5 frases por mensaje. Cuando llegue el momento del JSON, responde EXCLUSIVAMENTE el JSON crudo. Sin texto antes. Sin texto después. Sin bloques markdown ```."
        f"Si agregas cualquier palabra al lado del JSON, el sistema falla y el usuario no recibe su propuesta."
        f"FORMATO CRÍTICO: PROHIBIDO usar asteriscos (*), guiones de lista, viñetas (•) o markdown. "
        f"Si necesitas enumerar, usa números seguidos de punto (1. 2. 3.) en líneas separadas, texto plano. Sin **negritas**. Horizonte entre 1 y 30, nunca 0."
        f"Cuando el usuario pida agregar/cambiar un activo después de una propuesta generada, "
        f"toma la composición real del último mensaje 'Propuesta generada' del historial como base, "
        f"NUNCA inventes tickers que no estén ahí. Para agregar un nuevo activo, redistribuye los pesos "
        f"proporcionalmente y emite el JSON con la nueva lista, el optimizador refinará los pesos finales.\n\n"
    )


def generar_analisis_trm(trm_hist):
    """Genera el texto de análisis IA de la TRM (sin HTML). Reusa la lógica de grafica_trm."""
    trm_values = trm_hist['TRM'].values.tolist()
    if len(trm_values) < 2:
        return ''
    try:
        noticias = []
        for termino in ["dolar peso colombiano TRM", "tasa cambio Colombia hoy"]:
            try:
                r = requests.get(
                    f"https://news.google.com/rss/search?q={termino.replace(' ','+')}&hl=es&gl=CO&ceid=CO:es",
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)
                for item in ET.fromstring(r.content).findall('.//item')[:2]:
                    t = item.find('title'); d = item.find('pubDate')
                    if t is not None:
                        noticias.append(f"- {t.text[:120]} ({d.text[:16] if d is not None else ''})")
            except Exception as e:
                print(f"News fetch failed: {e}")
                continue
        noticias_txt = '\n'.join(noticias) if noticias else 'Sin noticias recientes disponibles.'

        trm_series = pd.Series(trm_values)
        trm_hoy    = float(trm_values[-1])
        trm_ayer   = float(trm_values[-2]) if len(trm_values) > 1 else trm_hoy
        trm_7d     = float(trm_values[-7]) if len(trm_values) > 7 else trm_hoy
        trm_30d    = float(trm_values[-30]) if len(trm_values) > 30 else trm_hoy
        trm_90d    = float(trm_values[0])
        trm_max90  = max(trm_values)
        trm_min90  = min(trm_values)
        trm_ma7    = float(trm_series.rolling(7).mean().iloc[-1])
        trm_ma30   = float(trm_series.rolling(30).mean().iloc[-1])

        cambio_diario = ((trm_hoy - trm_ayer) / trm_ayer) * 100
        cambio_7d     = ((trm_hoy - trm_7d) / trm_7d) * 100
        cambio_30d    = ((trm_hoy - trm_30d) / trm_30d) * 100
        cambio_90d    = ((trm_hoy - trm_90d) / trm_90d) * 100
        distancia_max = ((trm_hoy - trm_max90) / trm_max90) * 100
        distancia_min = ((trm_hoy - trm_min90) / trm_min90) * 100

        tendencia = "alcista" if trm_hoy > trm_ma7 > trm_ma30 else \
                    "bajista" if trm_hoy < trm_ma7 < trm_ma30 else "lateral"
        volatilidad = float(trm_series.tail(30).std())
        vol_nivel   = "alta" if volatilidad > 80 else "moderada" if volatilidad > 40 else "baja"
        rango_90d   = trm_max90 - trm_min90
        posicion_rango = ((trm_hoy - trm_min90) / rango_90d * 100) if rango_90d > 0 else 50

        return anthropic_chat(
            [{'role': 'user', 'content':
              f'Eres analista cambiario senior del mercado colombiano. '
              f'Tienes los datos reales de la TRM de los últimos 90 días. Interprétalos.\n\n'
              f'DATOS TÉCNICOS DE LA TRM:\n'
              f'- Hoy: ${trm_hoy:,.0f} COP/USD\n'
              f'- Ayer: ${trm_ayer:,.0f} | Cambio diario: {cambio_diario:+.2f}%\n'
              f'- Hace 7 días: ${trm_7d:,.0f} | Cambio 7d: {cambio_7d:+.2f}%\n'
              f'- Hace 30 días: ${trm_30d:,.0f} | Cambio 30d: {cambio_30d:+.2f}%\n'
              f'- Hace 90 días: ${trm_90d:,.0f} | Cambio 90d: {cambio_90d:+.2f}%\n'
              f'- Máximo 90d: ${trm_max90:,.0f} ({distancia_max:+.1f}% vs hoy)\n'
              f'- Mínimo 90d: ${trm_min90:,.0f} ({distancia_min:+.1f}% vs hoy)\n'
              f'- Media móvil 7d: ${trm_ma7:,.0f} | Media móvil 30d: ${trm_ma30:,.0f}\n'
              f'- Tendencia: {tendencia}\n'
              f'- Volatilidad 30d: {vol_nivel} (σ = {volatilidad:,.0f} COP)\n'
              f'- Posición en rango 90d: {posicion_rango:.0f}% (0% = mínimo, 100% = máximo)\n\n'
              f'NOTICIAS RECIENTES:\n{noticias_txt}\n\n'
              f'Escribe exactamente 4 oraciones, en este orden:\n'
              f'1. SITUACIÓN ACTUAL: dónde está el peso HOY dentro de su rango de 90 días.\n'
              f'2. TENDENCIA: qué dice la relación precio vs medias móviles sobre la dirección del dólar.\n'
              f'3. CAUSA: según las noticias, qué factor está dominando el movimiento.\n'
              f'4. IMPLICACIÓN: qué significa para alguien que invierte en acciones americanas desde Colombia.\n\n'
              f'Reglas: usa los números exactos. Sin frases genéricas. Sin asteriscos. Español directo.'}],
            system=(
                'Eres analista cambiario senior del mercado colombiano con 15 años de experiencia. '
                'Das interpretaciones técnicas precisas, no descripciones de datos. '
                'Nunca inventas causas que no están en los datos o noticias.'),
            max_tokens=400, temperature=0.2)
    except Exception as e:
        print(f"Error análisis TRM: {e}")
        return ''


# ============================================================
# HELPERS
# ============================================================

@app.route("/api/analista-chat/<archivo>", methods=["POST"])
def api_analista_chat(archivo):
    if verificar_acceso(archivo):
        return jsonify({"respuesta": "No autorizado"})
    try:
        data = request.get_json()
        if not data:
            return jsonify({"respuesta": "Error: no se recibieron datos"})

        portafolio = leer_portafolio(archivo)
        composicion = portafolio.get("composicion", {})
        tiene_inv = len(portafolio.get("aportes", [])) > 0

        sistema = _sistema_analista(portafolio, composicion, tiene_inv)

        resp = anthropic_chat(
            data.get("historial", []), system=sistema, max_tokens=600, temperature=0.5
        )
        return jsonify({"respuesta": resp})
    except Exception as e:
        print(f"❌ api_analista_chat error: {e}")
        return jsonify({"respuesta": f"Error: {str(e)}"})


# ═══════════════════════════════════════════════════════════════════
# REEMPLAZO DE api_generar_propuesta  (lineas 1957-2164)
# ═══════════════════════════════════════════════════════════════════
# Cambios vs la version vieja:
#   - Ya NO usa cargar_datos/construir_panel/calcular_retornos_reales (bugs)
#   - Llama al motor nuevo via adaptador, que devuelve TODO calculado
#   - Las proyecciones usan la serie de retornos COP real del motor, sin el
#     bug de los 12 meses duplicados
#   - El reporte muestra los activos reales del motor, no un dummy

@app.route("/api/generar-propuesta/<archivo>", methods=["POST"])
def api_generar_propuesta(archivo):
    if verificar_acceso(archivo):
        return jsonify({"ok": False, "error": "No autorizado"})
    try:
        from adaptador_analista import generar_propuesta_completa

        data = request.get_json()
        perfil = data.get("perfil", "agresivo")
        inversion = float(data.get("inversion", 1000000))
        aporte_dca = float(data.get("aporte_dca", 0))
        freq = int(data.get("frecuencia_meses", 1))
        horizonte = int(data.get("horizonte", 10))
        if horizonte <= 0 or horizonte > 50:
            horizonte = 10

        portafolio = leer_portafolio(archivo)
        tiene_inv = len(portafolio.get("aportes", [])) > 0

        # --- Tickers fijos (si el analista IA propuso activos concretos) ---
        import re
        raw_activos = data.get("activos", {})
        if isinstance(raw_activos, list):
            raw_activos = {
                a.get("ticker"): a.get("porcentaje", a.get("peso", 0))
                for a in raw_activos
                if isinstance(a, dict) and a.get("ticker")
            }
        activos_propuestos = (
            {
                k: v for k, v in raw_activos.items()
                if isinstance(k, str) and isinstance(v, (int, float))
                and re.fullmatch(r"[A-Z]{1,6}(-USD)?", k)
            }
            if isinstance(raw_activos, dict) else {}
        )
        if raw_activos and not activos_propuestos:
            return jsonify({
                "ok": False,
                "error": 'El analista propuso categorías en vez de tickers reales '
                         '(ej. "Biotecnología" en vez de "IBB"). Pídele tickers concretos.',
            })

        # --- MOTOR NUEVO: hace todo (seleccion, pesos, perfil, proyecciones) ---
        resultado = generar_propuesta_completa(
            perfil=perfil,
            horizonte=horizonte,
            inversion=inversion,
            aporte_dca=aporte_dca,
            frecuencia_meses=freq,
            tickers_fijos=list(activos_propuestos.keys()) if activos_propuestos else None,
        )

        pesos_dict = resultado["pesos"]
        reporte_txt = resultado["reporte_txt"]

        # --- Filas editables ---
        filas_editables = ""
        for a, v in sorted(pesos_dict.items(), key=lambda x: x[1], reverse=True):
            pct = round(v * 100, 1)
            filas_editables += (
                f'<div class="fila-activo" data-ticker="{a}" style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.06)">'
                f'<span style="color:#f5f5f7;font-weight:500;width:80px;font-family:monospace;font-size:13px">{a}</span>'
                f'<div style="flex:1;background:rgba(0,113,227,0.15);border-radius:980px;height:6px;overflow:hidden">'
                f'<div class="barra-peso" style="background:#0071e3;height:100%;width:{pct}%;transition:width 0.3s"></div></div>'
                f'<input type="number" class="input-peso" value="{pct}" min="0" max="100" step="0.1" '
                f'style="width:65px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);'
                f'border-radius:6px;padding:4px 8px;color:#f5f5f7;font-size:12px;font-family:monospace;text-align:right">'
                f'<span style="color:#6e6e73;font-size:11px">%</span>'
                f'<button class="btn-quitar" style="background:rgba(255,69,58,0.1);border:1px solid rgba(255,69,58,0.2);'
                f'border-radius:6px;padding:3px 8px;cursor:pointer;color:#ff453a;font-size:11px">✕</button>'
                f"</div>"
            )

        reporte_html = (
            (
                f'<div style="margin-top:16px">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
                f'<span style="font-size:11px;color:#6e6e73;text-transform:uppercase;letter-spacing:0.05em">Proyecciones</span>'
                f'<button id="btn-recalcular" '
                f'style="padding:4px 12px;border-radius:6px;font-size:11px;font-family:DM Sans,sans-serif;cursor:pointer;'
                f'background:rgba(79,138,255,0.1);color:#4da3ff;border:1px solid rgba(79,138,255,0.3)">'
                f"↻ Recalcular proyecciones</button>"
                f"</div>"
                f'<div id="bloque-reporte" style="padding:14px 16px;background:rgba(255,255,255,0.03);'
                f"border:1px solid rgba(255,255,255,0.07);border-radius:12px;"
                f"font-family:monospace;font-size:11px;color:#a1a1a6;line-height:1.8;"
                f'overflow-x:auto;white-space:pre">{reporte_txt}</div>'
                f"</div>"
            )
            if reporte_txt else ""
        )

        dca_html = (
            f'<span>DCA: <strong style="color:#f5f5f7">${aporte_dca:,.0f} COP</strong></span>'
            if aporte_dca > 0 else ""
        )

        if tiene_inv:
            btns_html = '<button id="btn-nuevo" style="padding:10px 20px;border-radius:10px;font-size:13px;font-family:DM Sans,sans-serif;cursor:pointer;background:rgba(0,113,227,0.15);color:#4da3ff;border:1px solid rgba(0,113,227,0.3)">Crear como portafolio adicional</button>'
        else:
            btns_html = (
                '<button id="btn-reemplazar" style="padding:10px 20px;border-radius:10px;font-size:13px;font-family:DM Sans,sans-serif;cursor:pointer;background:rgba(0,113,227,0.15);color:#4da3ff;border:1px solid rgba(0,113,227,0.3)">Aplicar a este portafolio</button>'
                '<button id="btn-nuevo" style="padding:10px 20px;border-radius:10px;font-size:13px;font-family:DM Sans,sans-serif;cursor:pointer;background:rgba(255,255,255,0.05);color:#6e6e73;border:1px solid rgba(255,255,255,0.08)">Crear portafolio adicional</button>'
            )

        # --- Aviso del perfil (alfa y advertencia CDT) ---
        alfa = resultado.get("alfa")
        aviso_perfil = ""
        if alfa is not None:
            aviso_perfil = (
                f'<div style="margin-top:12px;padding:10px 12px;background:rgba(79,138,255,0.06);'
                f'border:1px solid rgba(79,138,255,0.2);border-radius:10px;font-size:11px;color:#a1a1a6">'
                f'Según tu tolerancia, <strong style="color:#4da3ff">{alfa*100:.0f}%</strong> va al '
                f'portafolio y <strong style="color:#4da3ff">{(1-alfa)*100:.0f}%</strong> a CDT. '
                f'{resultado.get("advertencia_cdt","")}</div>'
            )

        html = (
            '<div id="editor-composicion" style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:14px;padding:16px;margin-top:8px">'
            f'<p style="color:#6e6e73;font-size:10px;letter-spacing:0.06em;text-transform:uppercase;margin:0 0 4px">Propuesta optimizada · {perfil.upper()}</p>'
            '<p style="color:#4a5578;font-size:11px;margin:0 0 14px">Edita pesos, quita o agrega activos antes de aplicar</p>'
            f'<div id="lista-activos">{filas_editables}</div>'
            '<div style="margin-top:14px;padding:12px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:10px">'
            '<p style="color:#6e6e73;font-size:11px;margin:0 0 8px;text-transform:uppercase;letter-spacing:0.05em">+ Agregar activo</p>'
            '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
            '<input type="text" id="nuevo-ticker" placeholder="Ticker (ej: SCHD)" style="width:160px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:6px 10px;color:#f5f5f7;font-size:12px;font-family:monospace">'
            '<input type="number" id="nuevo-peso" placeholder="%" min="0" max="100" step="0.1" style="width:70px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:6px 10px;color:#f5f5f7;font-size:12px;text-align:right">'
            '<button id="btn-agregar" style="padding:6px 14px;border-radius:6px;background:rgba(0,113,227,0.15);color:#4da3ff;border:1px solid rgba(0,113,227,0.3);cursor:pointer;font-size:12px;font-family:DM Sans,sans-serif">Agregar</button>'
            '<span id="ticker-status" style="font-size:11px;color:#6e6e73"></span>'
            "</div></div>"
            '<div style="margin-top:12px;display:flex;align-items:center;justify-content:space-between">'
            '<span style="font-size:13px;color:#6e6e73">Total: <strong id="total-pesos" style="color:#f5f5f7">100.0%</strong></span>'
            '<span id="alerta-total" style="font-size:11px;color:#ff453a;display:none">⚠️ Debe sumar 100%</span>'
            "</div>"
            f"{reporte_html}"
            f"{aviso_perfil}"
            '<div style="margin-top:12px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.06);display:flex;gap:16px;font-size:12px;color:#6e6e73">'
            f'<span>Inversión: <strong style="color:#f5f5f7">${inversion:,.0f} COP</strong></span>'
            f"{dca_html}"
            f'<span>Horizonte: <strong style="color:#f5f5f7">{horizonte} años</strong></span>'
            "</div>"
            f'<div style="margin-top:16px;display:flex;gap:10px;flex-wrap:wrap" id="botones-propuesta">{btns_html}</div>'
            "</div>"
        )

        return jsonify({
            "ok": True,
            "html": html,
            "propuesta": {
                "pesos": pesos_dict,
                "perfil": perfil,
                "inversion": inversion,
                "aporte_dca": aporte_dca,
                "frecuencia_meses": freq,
                "horizonte": horizonte,
                "archivo": archivo,
                "alfa": alfa,
                "advertencia": resultado.get("advertencia_concentracion"),
            },
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": "Ocurrió un problema generando la propuesta. Intenta de nuevo o ajusta tu solicitud.",
        })


# ═══════════════════════════════════════════════════════════════════
# REEMPLAZO DE api_recalcular_proyecciones  (lineas 2167-2266)
# ═══════════════════════════════════════════════════════════════════
# El usuario edito pesos a mano. Recalcula proyecciones con esos pesos,
# usando la serie de retornos COP real del motor (sin bugs).

@app.route("/api/recalcular-proyecciones/<archivo>", methods=["POST"])
def api_recalcular_proyecciones(archivo):
    if verificar_acceso(archivo):
        return jsonify({"ok": False, "error": "No autorizado"})
    try:
        from analista import (
            cargar_datos,
            construir_panel,
            calcular_retornos_reales,
            generar_reporte,
            completar_precios,
        )

        data = request.get_json()
        pesos_raw = data.get("pesos", {})
        perfil = data.get("perfil", "agresivo")
        inversion = float(data.get("inversion", 1000000))
        aporte = float(data.get("aporte_dca", 0))
        freq = int(data.get("frecuencia_meses", 1))
        horizonte = int(data.get("horizonte", 10))

        precios, trm, inf_usa, inf_col, risk_free, tasa_cdt = cargar_datos()
        precios = completar_precios(precios, pesos_raw)
        panel = construir_panel(precios, trm, inf_usa, inf_col, risk_free)
        ret_real = calcular_retornos_reales(panel, list(precios.columns))

        pesos_con_historico = {
            k: v for k, v in pesos_raw.items() if k in ret_real.columns
        }
        pesos_sin_historico = {
            k: v for k, v in pesos_raw.items() if k not in ret_real.columns
        }

        inf_col_actual = float(
            pd.read_parquet(os.path.join(DATOS_DIR, "macro/inflacion_col.parquet"))[
                "Inflacion_COL"
            ].iloc[-1]
        )

        datos = None
        reporte_txt = ""
        if pesos_con_historico:
            from analista import calcular_datos_reporte

            total = sum(pesos_con_historico.values())
            pesos_norm = {k: v / total for k, v in pesos_con_historico.items()}
            pesos_series = pd.Series(pesos_norm)
            datos = calcular_datos_reporte(
                pesos=pesos_series,
                inversion_inicial=inversion,
                ret_real=ret_real,
                perfil=perfil,
                horizonte=horizonte,
                risk_free=risk_free,
                inflacion_col=inf_col_actual,
                tasa_cdt=float(tasa_cdt),
                aporte_periodico=aporte,
                frecuencia_meses=freq,
            )
            # Capturar el texto formateado del reporte
            import sys, io

            old = sys.stdout
            sys.stdout = buf = io.StringIO()
            try:
                generar_reporte(
                    pesos=pesos_series,
                    inversion_inicial=inversion,
                    ret_real=ret_real,
                    perfil=perfil,
                    horizonte=horizonte,
                    risk_free=risk_free,
                    inflacion_col=inf_col_actual,
                    tasa_cdt=float(tasa_cdt),
                    aporte_periodico=aporte,
                    frecuencia_meses=freq,
                )
            finally:
                sys.stdout = old
            reporte_txt = buf.getvalue()

        nota_nuevos = ""
        if pesos_sin_historico:
            tickers_nuevos = ", ".join(pesos_sin_historico.keys())
            nota_nuevos = (
                f"{tickers_nuevos} fue agregado manualmente. Las proyecciones corresponden "
                f"al resto del portafolio; su histórico estará disponible en el próximo análisis completo."
            )

        return jsonify(
            {
                "ok": True,
                "datos": datos,
                "reporte": reporte_txt,
                "nota_nuevos": nota_nuevos,
            }
        )

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/aplicar-propuesta/<archivo>", methods=["POST"])
def api_aplicar_propuesta(archivo):
    if verificar_acceso(archivo):
        return jsonify({"ok": False, "error": "No autorizado"})
    try:
        data = request.get_json()
        tipo = data.get("tipo", "reemplazar")
        pesos = data.get("pesos", {})
        perfil = data.get("perfil", "agresivo")
        inv = data.get("inversion", 1000000)
        aporte = data.get("aporte_dca", 0)
        freq = data.get("frecuencia_meses", 1)
        p = leer_portafolio(archivo)
        username = session.get("username")

        if tipo == "reemplazar":
            guardar_composicion(archivo, pesos)
            # Resetear monitor automáticamente al cambiar composición
            ruta_monitor = os.path.join(DATOS_DIR, "portafolios", f"monitor_{archivo}")
            if os.path.exists(ruta_monitor):
                os.remove(ruta_monitor)
                print(f"🔄 Monitor reseteado automáticamente: {archivo}")
            ruta = f"datos/portafolios/{archivo}"
            with open(ruta, "r", encoding="utf-8") as f:
                dp = json.load(f)
            dp.update(
                {
                    "inversion_inicial": inv,
                    "aporte_dca": aporte,
                    "frecuencia_meses": freq,
                    "perfil": perfil,
                }
            )
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(dp, f, indent=2, ensure_ascii=False)
            return jsonify(
                {
                    "ok": True,
                    "mensaje": "Portafolio actualizado.",
                    "redirigir": f"/seguimiento/{archivo}",
                }
            )

        elif tipo == "nuevo":
            base = f"{p['propietario']} {perfil.capitalize()} {datetime.now().strftime('%Y')}"
            nombre_n = base
            contador = 2
            while True:
                test = f"{nombre_n}-{contador}" if contador > 1 else nombre_n
                slug = _slug(test)
                if not os.path.exists(f"datos/portafolios/{slug}.json"):
                    nombre_n = test
                    break
                contador += 1
            na = crear_portafolio_para_usuario(
                username, nombre_n, perfil, p["propietario"], inv, aporte, freq
            )
            if not na:
                return jsonify(
                    {"ok": False, "error": "No se pudo crear el portafolio."}
                )
            nm = os.path.basename(na)
            guardar_composicion(nm, pesos)
            ip, dispositivo = _request_meta()
            registrar_actividad(
                 "portafolio_nuevo",
                 username,
                 detalle=f'Portafolio "{nombre_n}" creado',
                 ip=ip,
                 dispositivo=dispositivo,
             )
            # El portafolio nuevo empieza sin historial de monitor
            ruta_monitor = os.path.join(DATOS_DIR, "portafolios", f"monitor_{nm}")
            if os.path.exists(ruta_monitor):
                os.remove(ruta_monitor)
            return jsonify(
                {
                    "ok": True,
                    "mensaje": f'"{nombre_n}" creado exitosamente.',
                    "redirigir": f"/seguimiento/{nm}",
                }
            )

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/bot/<archivo>", methods=["POST"])
def api_bot(archivo):
    if verificar_acceso(archivo):
        return jsonify({"respuesta": "No autorizado"})
    try:
        data = request.get_json()
        mensaje = data.get("mensaje", "")
        p = leer_portafolio(archivo)
        macro = cargar_macro()
        mt = (
            f'TRM: ${macro["trm"]:,.0f}\nInflación: {macro["inf_col"]}%\nBanrep: {macro["banrep"]}%'
            if macro
            else ""
        )
        tr = calcular_tiempo_real(p)
        resumen_tr = ""
        if tr:
            resumen_tr = (
                f"ESTADO ACTUAL DEL PORTAFOLIO:\n"
                f'- Valor total hoy: ${tr["total_valor"]:,.0f} COP\n'
                f'- Invertido (real, deflactado): ${tr["total_invertido"]:,.0f} COP\n'
                f'- Ganancia real vs inflación: ${tr["ganancia_total"]:,.0f} COP ({tr["rentabilidad_total"]:+.2f}%)\n'
                f"- Posiciones:\n"
            )
            for pos in tr["posiciones"]:
                resumen_tr += (
                    f'  · {pos["activo"]}: ${pos["precio_hoy"]:,.2f} USD | '
                    f'Valor: ${pos["valor_hoy"]:,.0f} COP | '
                    f'Ganancia: ${pos["ganancia"]:,.0f} ({pos["rentabilidad"]:+.1f}%)\n'
                )
        else:
            composicion = p.get("composicion", {})
            if composicion:
                resumen_tr = (
                    f"COMPOSICIÓN OBJETIVO DEL PORTAFOLIO (sin inversiones registradas aún):\n"
                    f'- Inversión inicial planificada: ${p.get("inversion_inicial",0):,.0f} COP\n'
                    f"- Activos y pesos:\n"
                )
                for activo, peso in composicion.items():
                    precio = precio_actual_usd(activo)
                    precio_str = (
                        f"${precio:,.2f} USD" if precio else "precio no disponible"
                    )
                    monto_cop = p.get("inversion_inicial", 0) * peso
                    resumen_tr += f"  · {activo}: {peso*100:.1f}% — {precio_str} — asignación: ${monto_cop:,.0f} COP\n"
            else:
                resumen_tr = "Este portafolio aún no tiene composición ni inversiones registradas.\n"
        noticias_mercado = ""
        try:
            tickers = list(p.get("composicion", {}).keys())[:3]
            for tk in tickers:
                r = requests.get(
                    f"https://news.google.com/rss/search?q={tk}+stock&hl=es&gl=US&ceid=US:es",
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=5,
                )
                items = ET.fromstring(r.content).findall(".//item")[:1]
                for item in items:
                    t = item.find("title")
                    if t is not None:
                        noticias_mercado += f"- {tk}: {t.text[:80]}\n"
        except Exception as e:
            print(f"News fetch failed for {tk}: {e}")
        noticias_txt = (
            f"\nNOTICIAS RECIENTES DE TUS ACTIVOS:\n{noticias_mercado}"
            if noticias_mercado
            else ""
        )
        ctx = (
            f'Eres el asesor de inversiones personal de {p["propietario"]}, '
            f"con acceso completo a su portafolio en tiempo real. "
            f"Tu trabajo es dar análisis honestos, con criterio propio, sin rodeos.\n\n"
            f"PERFIL:\n"
            f'- Riesgo: {p["perfil"]} ({"largo plazo 10 años, acepta volatilidad" if p["perfil"] == "agresivo" else "mediano plazo 5 años, prioriza estabilidad"})\n'
            f'- Capital inicial: ${p.get("inversion_inicial", 0):,.0f} COP\n'
            f'- DCA: ${p.get("aporte_dca", 0):,.0f} COP cada {p.get("frecuencia_meses", 1)} mes(es)\n\n'
            f"PORTAFOLIO HOY:\n{resumen_tr}\n\n"
            f"MACRO:\n{mt}\n{noticias_txt}\n\n"
            f"INSTRUCCIONES:\n"
            f"- Usa los números reales. Nunca inventes cifras.\n"
            f"- Si gana: explica qué lo impulsa. Si pierde: sé honesto y pon en contexto largo plazo.\n"
            f'- Cuando pregunten "¿qué hago?": da una recomendación concreta, no "depende".\n'
            f"- Siempre compara contra inflación colombiana — eso es lo que realmente importa.\n"
            f"- Máximo 4 párrafos. Sin asteriscos. Sin bullets. Español directo."
        )
        resp = anthropic_chat(
            [{"role": "user", "content": mensaje}],
            system=ctx,
            max_tokens=800,
            temperature=0.4,
        )
        return jsonify({"respuesta": resp})
    except Exception as e:
        return jsonify({"respuesta": f"Error: {str(e)}"})


@app.route("/api/admin/reset-password", methods=["POST"])
def api_reset_password():
    if not session.get("es_admin"):
        return jsonify({"ok": False, "error": "No autorizado"})
    data = request.get_json()
    username = data.get("username")
    ok = resetear_password(username)
    return jsonify(
        {"ok": ok, "mensaje": f"Contraseña de {username} reseteada a: cambiar123"}
    )


@app.route("/api/admin/desbloquear", methods=["POST"])
def api_desbloquear():
    if not session.get("es_admin"):
        return jsonify({"ok": False, "error": "No autorizado"})
    data = request.get_json()
    ok = desbloquear_usuario(data.get("username"))
    return jsonify({"ok": ok})


@app.route("/api/admin/toggle-admin", methods=["POST"])
def api_toggle_admin():
    if not session.get("es_admin"):
        return jsonify({"ok": False, "error": "No autorizado"})
    data = request.get_json()
    ok = actualizar_usuario(
        data.get("username"), {"es_admin": data.get("es_admin", False)}
    )
    return jsonify({"ok": ok})


# ============================================================
# APIs
# ============================================================


@app.route("/api/eliminar-cuenta", methods=["POST"])
def api_eliminar_cuenta():
    if not session.get("username"):
        return jsonify({"ok": False, "error": "No autorizado"})
    username = session.get("username")
    # El admin no puede eliminarse a sí mismo
    if session.get("es_admin"):
        return jsonify(
            {
                "ok": False,
                "error": "El admin no puede eliminarse desde aquí. Hazlo desde el panel.",
            }
        )
    ok = eliminar_usuario(username)
    if ok:
        session.clear()
    return jsonify({"ok": ok})


@app.route("/api/admin/eliminar-usuario", methods=["POST"])
def api_admin_eliminar_usuario():
    if not session.get("es_admin"):
        return jsonify({"ok": False, "error": "No autorizado"})
    data = request.get_json()
    username = data.get("username")
    if username == session.get("username"):
        return jsonify({"ok": False, "error": "No puedes eliminarte a ti mismo"})
    ok = eliminar_usuario(username)
    if ok:
        ip, dispositivo = _request_meta()
        registrar_actividad(
            "eliminacion",
            username,
            detalle="Cuenta eliminada por admin",
            ip=ip,
            dispositivo=dispositivo,
        )
    return jsonify({"ok": ok})



@app.route("/api/eliminar-portafolio/<archivo>", methods=["POST"])
def api_eliminar_portafolio(archivo):
    if verificar_acceso(archivo):
        return jsonify({"ok": False, "error": "No autorizado"})
    try:
        # Leer el nombre antes de borrar, para el log
        try:
            p = leer_portafolio(archivo)
            nombre_port = p.get("nombre", archivo) if p else archivo
        except Exception:
            nombre_port = archivo
 
        ruta = f"datos/portafolios/{archivo}"
        ruta_monitor = f"datos/portafolios/monitor_{archivo}"
        if os.path.exists(ruta):
            os.remove(ruta)
        if os.path.exists(ruta_monitor):
            os.remove(ruta_monitor)
 
        # Registrar la eliminacion
        ip, dispositivo = _request_meta()
        registrar_actividad(
            "portafolio_eliminado",
            session.get("username", ""),
            detalle=f'Portafolio "{nombre_port}" eliminado',
            ip=ip,
            dispositivo=dispositivo,
        )
 
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})



@app.route("/api/fix-banrep")
def fix_banrep():
    if not session.get("es_admin"):
        return jsonify({"error": "No autorizado"})
    ruta = os.path.join(DATOS_DIR, "macro", "tasa_banrep.parquet")
    if os.path.exists(ruta):
        os.remove(ruta)
        return jsonify(
            {
                "ok": True,
                "mensaje": "Archivo borrado. Ahora haz clic en Actualizar datos.",
            }
        )
    return jsonify({"ok": False, "mensaje": "Archivo no encontrado"})


@app.route("/api/verificar-ticker/<ticker>")
def api_verificar_ticker(ticker):
    if not session.get("username"):
        return jsonify({"valido": False})
    try:
        hoy = datetime.now()
        df = yf.download(
            ticker,
            start=(hoy - timedelta(days=5)).strftime("%Y-%m-%d"),
            end=hoy.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            return jsonify({"valido": False})
        if hasattr(df.columns, "get_level_values"):
            df.columns = df.columns.get_level_values(0)
        precio = round(float(df["Close"].iloc[-1]), 2)
        try:
            info = yf.Ticker(ticker).info
            nombre = info.get("shortName", ticker)
        except:
            nombre = ticker
        # Verificar si ya está en el histórico
        precios_path = os.path.join(DATOS_DIR, "precios", "precios.parquet")
        es_nuevo = True
        if os.path.exists(precios_path):

            cols = pd.read_parquet(precios_path).columns.tolist()
            es_nuevo = ticker not in cols
        # Si es nuevo lanzar descarga en background
        if es_nuevo:

            def descargar_historico(tk):
                try:
                    hoy2 = datetime.now()
                    inicio = (hoy2 - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
                    df2 = yf.download(
                        tk,
                        start=inicio,
                        end=hoy2.strftime("%Y-%m-%d"),
                        interval="1d",
                        auto_adjust=True,
                        progress=False,
                    )
                    if df2.empty:
                        return
                    if hasattr(df2.columns, "get_level_values"):
                        df2.columns = df2.columns.get_level_values(0)
                    close = df2[["Close"]].rename(columns={"Close": tk})
                    if os.path.exists(precios_path):
                        existente = pd.read_parquet(precios_path)
                        if tk not in existente.columns:
                            nuevo = existente.join(close, how="outer")
                            nuevo.to_parquet(precios_path)
                            print(f"✅ Histórico de {tk} agregado")
                    else:
                        close.to_parquet(precios_path)
                    # Marcar como listo
                    listo_path = os.path.join(DATOS_DIR, f"ticker_listo_{tk}.flag")
                    open(listo_path, "w").close()
                except Exception as e:
                    print(f"❌ Error descargando histórico de {tk}: {e}")
                    # Marcar como fallido
                    listo_path = os.path.join(DATOS_DIR, f"ticker_listo_{tk}.flag")
                    open(listo_path, "w").close()

            threading.Thread(
                target=descargar_historico, args=(ticker,), daemon=True
            ).start()
        return jsonify(
            {"valido": True, "precio": precio, "nombre": nombre, "es_nuevo": es_nuevo}
        )
    except Exception as e:
        return jsonify({"valido": False, "error": str(e)})


@app.route("/api/ticker-listo/<ticker>")
def api_ticker_listo(ticker):
    """Verifica si el historico de un ticker nuevo ya terminó de descargarse."""
    if not session.get("username"):
        return jsonify({"listo": False})
    # Si ya estaba en el histórico desde el inicio, siempre listo
    precios_path = os.path.join(DATOS_DIR, "precios", "precios.parquet")
    if os.path.exists(precios_path):

        cols = pd.read_parquet(precios_path).columns.tolist()
        if ticker in cols:
            return jsonify({"listo": True})
    # Verificar flag
    flag = os.path.join(DATOS_DIR, f"ticker_listo_{ticker}.flag")
    listo = os.path.exists(flag)
    if listo:
        # Limpiar flag
        try:
            os.remove(flag)
        except Exception as e:
            print(f"Could not remove flag file: {e}")
    return jsonify({"listo": listo})


@app.route("/api/profile", methods=["GET"])
def get_profile():
    if not session.get("username"):
        return jsonify({"error": "No autorizado"})
    u = get_usuario(session["username"])
    if not u:
        return jsonify({"error": "Usuario no encontrado"})
    return jsonify(
        {
            "username": u.get("username"),
            "email": u.get("email"),
            "telegram_chat_id": u.get("telegram_chat_id", ""),
            "email_notifications": u.get("email_notifications", True),
        }
    )


@app.route("/api/profile", methods=["PUT"])
def update_profile():
    if not session.get("username"):
        return jsonify({"error": "No autorizado"})

    data = request.get_json()
    username = session["username"]
    campos = {}
    if "email" in data and data["email"]:
        campos["email"] = data["email"].strip()
    if "telegram_chat_id" in data:
        campos["telegram_chat_id"] = data["telegram_chat_id"].strip()
    if "email_notifications" in data:
        campos["email_notifications"] = data["email_notifications"]
    if "new_password" in data and data["new_password"]:
        u = get_usuario(username)
        ph = u.get("password_hash", "")
        cur = data.get("current_password", "")
        if not verify_password(ph, cur):
            return jsonify({"error": "Contraseña actual incorrecta"}), 400
        campos["password_hash"] = hash_password_secure(data["new_password"])
    if not campos:
        return jsonify({"error": "Sin cambios"}), 400
    ok = actualizar_usuario(username, campos)
    if ok:
        return jsonify({"ok": True, "mensaje": "Perfil actualizado correctamente"})
    return jsonify({"error": "Error actualizando perfil"}), 500


@app.route("/api/recolector", methods=["POST"])
def api_recolector():
    from recolector import correr_todo

    try:
        correr_todo()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/precios-rt/<path:archivo>")
def api_precios_rt(archivo):
    redir = verificar_acceso(archivo)
    if redir:
        return jsonify({"error": "No autorizado"})
    try:
        # Lee el estado que el monitor actualiza cada 9 segundos
        # No llama a Finnhub directamente — el monitor ya lo hizo
        ruta = os.path.join(DATOS_DIR, "portafolios", f"monitor_{archivo}")
        if not os.path.exists(ruta):
            return jsonify({"ok": False, "error": "Sin datos aún"})

        with open(ruta, "r", encoding="utf-8") as f:
            estado = json.load(f)

        resultados_rt = estado.get("resultados_rt", {})
        mercado_rt = mercado_abierto_ahora()

        precios = {}
        for ticker, r in resultados_rt.items():
            precios[ticker] = {
                "precio": r.get("precio", 0),
                "cambio_dia": r.get("cambio_dia", 0),
                "senal": r.get("senal", "NEUTRAL"),
                "score": r.get("score", 0),
                "rsi": r.get("rsi", 0),
                "ma20": r.get("ma20", 0),
                "ma50": r.get("ma50", 0),
                "rango_entrar": r.get("rango_entrar"),
                "rango_vigilar": r.get("rango_vigilar"),
                "puede_entrar": r.get("puede_entrar", False),
                "mercado_rt": mercado_rt,
                "timestamp": r.get("timestamp", ""),
            }
        
        # Si no hay precios en vivo (mercado cerrado), exponer los rangos calculados
        rangos_data = {}
        ruta_rangos = os.path.join(DATOS_DIR, "portafolios", f"rangos_{archivo}")
        if os.path.exists(ruta_rangos):
            try:
                with open(ruta_rangos, 'r', encoding='utf-8') as f:
                    rangos_data = json.load(f)
            except Exception:
                pass

        return jsonify({
            'ok':              True,
            'precios':         precios,
            'mercado_abierto': mercado_rt,
            'ultimo_update':   estado.get('timestamp', ''),
            'rangos':          rangos_data.get('rangos', {}),
            'rangos_fecha':    rangos_data.get('fecha', ''),
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/ultima-actualizacion")
def api_ultima_actualizacion():
    try:
        mtime = os.path.getmtime("datos/macro/trm.parquet")
        hora = datetime.fromtimestamp(mtime).strftime("%d %b %Y · %I:%M %p")
        return jsonify({"timestamp": hora})
    except Exception as e:
        print(f"Could not read TRM timestamp: {e}")
        return jsonify({"timestamp": "No disponible"})


# ============================================================
# WEBHOOK DE TELEGRAM
# ============================================================


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    """
    Recibe actualizaciones de Telegram (mensajes y callbacks de botones).
    IBKR no tiene nada que ver aquí — esto es para los botones
    "Ya entré / No voy a entrar / Sigue informando" del monitor.
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"ok": True})

        # ── Callback de botón inline ───────────────────────────
        if "callback_query" in data:
            cb = data["callback_query"]
            chat_id = str(cb["message"]["chat"]["id"])
            cb_data = cb.get("data", "")

            # Confirmar recepción a Telegram (evita que reenvíe)
            try:
                requests.post(
                    f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN', '')}/answerCallbackQuery",
                    json={"callback_query_id": cb["id"]},
                    timeout=5,
                )
            except:
                pass

            # Procesar decisión del usuario
            from monitor import procesar_callback_telegram

            procesar_callback_telegram(cb_data, chat_id)
            return jsonify({"ok": True})

        # ── Mensaje de texto (comandos futuros) ────────────────
        if "message" in data:
            msg = data["message"]
            chat_id = str(msg["chat"]["id"])
            texto = msg.get("text", "").strip().lower()

            # Comando /start — respuesta básica
            if texto == "/start":
                requests.post(
                    f"https://api.telegram.org/bot{os.environ.get('TELEGRAM_BOT_TOKEN', '')}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": f"👋 Hola! Tu Chat ID es: <b>{chat_id}</b>\n\nCópialo y pégalo en tu perfil del sistema para activar las alertas.",
                        "parse_mode": "HTML",
                    },
                    timeout=5,
                )

        return jsonify({"ok": True})

    except Exception as e:
        print(f"❌ Error webhook Telegram: {e}")
        return jsonify({"ok": True})  # Siempre devolver 200 a Telegram


def registrar_webhook_telegram():
    """
    Registra la URL del webhook en Telegram automáticamente.
    Llama esta función desde arrancar_monitor() en dashboard.py.
    """
    try:
        # En Railway, la URL pública es la variable RAILWAY_STATIC_URL
        # o puedes ponerla manualmente como variable de entorno WEBHOOK_URL
        base_url = (
            os.environ.get("WEBHOOK_URL")
            or os.environ.get("RAILWAY_STATIC_URL")
            or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        )
        if not base_url:
            print(
                "⚠️ Sin URL pública para webhook de Telegram — configura WEBHOOK_URL en Railway"
            )
            return

        if not base_url.startswith("https://"):
            base_url = f"https://{base_url}"

        webhook_url = f"{base_url.rstrip('/')}/telegram-webhook"
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

        if not token:
            print("⚠️ Sin TELEGRAM_BOT_TOKEN para registrar webhook")
            return

        r = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url},
            timeout=10,
        )
        result = r.json()
        if result.get("ok"):
            print(f"✅ Webhook de Telegram registrado: {webhook_url}")
        else:
            print(f"⚠️ Error registrando webhook: {result.get('description')}")

    except Exception as e:
        print(f"❌ Error registrando webhook Telegram: {e}")


# ============================================================
# === API REST (frontend Next.js) ===
# ============================================================


@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    if session.get("username"):
        return jsonify({"ok": False, "error": "Ya hay una sesión activa"}), 400

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()
    telegram = (data.get("telegram") or "").strip()

    if not username or not email or not password:
        return (
            jsonify(
                {"ok": False, "error": "Nombre, email y contraseña son obligatorios."}
            ),
            400,
        )
    if len(password) < 6:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "La contraseña debe tener al menos 6 caracteres.",
                }
            ),
            400,
        )

    resultado = registrar_usuario(username, email, password, telegram)
    if resultado is not True:
        # registrar_usuario devuelve un string de error cuando falla
        return jsonify({"ok": False, "error": resultado}), 400

    # Éxito: enviar correo de activación y registrar actividad
    _enviar_activacion(username, email)
    ip, dispositivo = _request_meta()
    registrar_actividad(
        "registro_nuevo",
        username,
        email=email,
        detalle="Nuevo usuario registrado (API)",
        ip=ip,
        dispositivo=dispositivo,
    )

    return jsonify({"ok": True, "username": username, "requiere_activacion": True})

PIN_EXPIRA_MIN = 10          # vida del PIN de activación
PIN_INTENTOS_MAX = 5         # intentos fallidos antes de invalidar
REENVIO_ACTIVACION_SEG = 60 
CAP_ENVIOS = 5              # máximo de códigos enviados por ventana
VENTANA_ENVIOS_MIN = 60     # ventana en minutos (se reinicia el conteo)

def _enviar_activacion(username, email):
    """Genera/manda un PIN. Devuelve True si envió, o un string con el motivo si no."""
    u = get_usuario(username)
    if not u:
        return "Cuenta no encontrada."
    ahora = datetime.now()

    # Cooldown entre reenvíos
    ultimo = u.get("ultimo_envio_activacion")
    if ultimo:
        try:
            if ahora - datetime.strptime(ultimo, "%Y-%m-%d %H:%M:%S") < timedelta(seconds=REENVIO_ACTIVACION_SEG):
                return "Espera un momento antes de pedir otro código."
        except ValueError:
            pass

    # Tope total por ventana (anti email-bombing) — se reinicia pasada la ventana
    count = u.get("envios_activacion", 0)
    ventana = u.get("envios_ventana")
    if ventana:
        try:
            if ahora - datetime.strptime(ventana, "%Y-%m-%d %H:%M:%S") > timedelta(minutes=VENTANA_ENVIOS_MIN):
                count, ventana = 0, None   # ventana expiró → reinicia
        except ValueError:
            count, ventana = 0, None
    if count >= CAP_ENVIOS:
        return "Alcanzaste el límite de códigos. Intenta de nuevo en un rato."

    pin = f"{secrets.randbelow(1000000):06d}"
    if not enviar_pin_activacion(email, username, pin, PIN_EXPIRA_MIN):
        return "No se pudo enviar el correo. Intenta de nuevo."

    actualizar_usuario(username, {
        "pin_activacion": hashlib.sha256(pin.encode()).hexdigest(),
        "pin_expira": (ahora + timedelta(minutes=PIN_EXPIRA_MIN)).strftime("%Y-%m-%d %H:%M:%S"),
        "pin_intentos": 0,
        "ultimo_envio_activacion": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "envios_activacion": count + 1,
        "envios_ventana": ventana or ahora.strftime("%Y-%m-%d %H:%M:%S"),
    })
    return True

RESET_MAX_AGE = 900  # 15 minutos


def _serializer_reset():
    return URLSafeTimedSerializer(app.secret_key, salt="reset-password")


def _solicitar_reset(email):
    """Genera token y manda el correo. Silencioso si el email no existe."""
    username, u = get_usuario_por_email(email)
    if not username:
        return
    token = _serializer_reset().dumps(
        {"u": username, "fp": huella_password_hash(u["password_hash"])}
    )
    app_url = os.environ.get("APP_URL", "").rstrip("/")
    enviar_reset_password(
        email, f"{app_url}/reset-password?token={token}", RESET_MAX_AGE // 60
    )
    ip, dispositivo = _request_meta()
    registrar_actividad(
        "reset_solicitado", username, email=email,
        detalle="Solicitud de reset de contraseña", ip=ip, dispositivo=dispositivo,
    )


def _aplicar_reset(token, password):
    """Aplica el reset. Devuelve None si ok, o el string de error."""
    if len(password) < 6:
        return "La contraseña debe tener al menos 6 caracteres."
    try:
        payload = _serializer_reset().loads(token, max_age=RESET_MAX_AGE)
    except SignatureExpired:
        return "El enlace venció. Solicita uno nuevo."
    except BadSignature:
        return "Enlace inválido."

    username = payload.get("u", "")
    u = get_usuario(username)
    if not u or huella_password_hash(u["password_hash"]) != payload.get("fp"):
        return "Este enlace ya fue usado. Solicita uno nuevo."

    # Resetear también desbloquea: quien olvidó la clave suele haberse bloqueado intentando
    actualizar_usuario(username, {
        "password_hash": hash_password_secure(password),
        "intentos_fallidos": 0,
        "bloqueado_hasta": None,
    })
    ip, dispositivo = _request_meta()
    registrar_actividad(
        "reset_completado", username, email=u.get("email", ""),
        detalle="Contraseña restablecida", ip=ip, dispositivo=dispositivo,
    )
    return None

@app.before_request
def _validar_sesion():
    """La huella del hash viaja en la sesión: si la contraseña cambió, la sesión muere.
    Es lo que hace que un reset expulse al atacante que ya tenía cookie."""
    username = session.get("username")
    if not username:
        return
    u = get_usuario(username)
    if not u or session.get("fp") != huella_password_hash(u["password_hash"]):
        session.clear()


@app.route("/api/auth/verify-pin", methods=["POST"])
def api_auth_verify_pin():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    pin = (data.get("pin") or "").strip()

    username, u = get_usuario_por_email(email)
    if not u:
        return jsonify({"ok": False, "error": "Cuenta no encontrada."}), 400

    if not u.get("email_verificado"):
        pin_hash = u.get("pin_activacion")
        expira = u.get("pin_expira")
        intentos = u.get("pin_intentos", 0)
        if not pin_hash or not expira:
            return jsonify({"ok": False, "error": "No hay un código activo. Pide uno nuevo."}), 400
        try:
            vencido = datetime.now() > datetime.strptime(expira, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            vencido = True
        if vencido:
            return jsonify({"ok": False, "error": "El código venció. Pide uno nuevo."}), 400
        if intentos >= PIN_INTENTOS_MAX:
            return jsonify({"ok": False, "error": "Demasiados intentos. Pide un código nuevo.", "bloqueado": True}), 400
        if hashlib.sha256(pin.encode()).hexdigest() != pin_hash:
            actualizar_usuario(username, {"pin_intentos": intentos + 1})
            return jsonify({"ok": False, "error": "Código incorrecto."}), 400
        actualizar_usuario(username, {
            "email_verificado": True,
            "pin_activacion": None, "pin_expira": None, "pin_intentos": 0,
        })

    # AUTO-LOGIN (recién verificado o ya verificado): abre sesión igual que el login
    session["username"] = username
    session["fp"] = huella_password_hash(u["password_hash"])
    session["es_admin"] = u.get("es_admin", False)
    session.permanent = True
    ip, dispositivo = _request_meta()
    registrar_actividad("activacion_ok", username, email=email,
                        detalle="Cuenta activada por PIN (auto-login)", ip=ip, dispositivo=dispositivo)
    return jsonify({"ok": True, "username": username})


@app.route("/api/auth/resend-pin", methods=["POST"])
def api_auth_resend_pin():
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip()
    username, u = get_usuario_por_email(email)
    if username and not u.get("email_verificado"):
        res = _enviar_activacion(username, email)
        if res is not True:
            return jsonify({"ok": False, "error": res}), 429
    return jsonify({"ok": True})

@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")
    usuario = login_usuario(email, password)
    ip, dispositivo = _request_meta()

    if usuario and not usuario.get("bloqueado") and not usuario.get("email_verificado", True):
        _enviar_activacion(usuario["username"], usuario["email"])
        return jsonify({"ok": False, "error": "Tu cuenta no está activada. Te enviamos un código.",
                        "requiere_activacion": True, "email": usuario["email"]}), 403
    elif usuario and not usuario.get("bloqueado"):
        session["username"] = usuario["username"]
        session["fp"] = huella_password_hash(usuario["password_hash"])
        session["es_admin"] = usuario.get("es_admin", False)
        session.permanent = True
        registrar_actividad(
            "login_ok",
            usuario["username"],
            email=email,
            detalle="Login API",
            ip=ip,
            dispositivo=dispositivo,
        )
        return jsonify(
            {
                "ok": True,
                "username": usuario["username"],
                "es_admin": usuario.get("es_admin", False),
            }
        )

    if usuario and usuario.get("bloqueado"):
        minutos = usuario.get("minutos", 15)
        registrar_actividad(
            "login_fail",
            usuario.get("username", email),
            email=email,
            detalle=f"Cuenta bloqueada — {minutos} min",
            ip=ip,
            dispositivo=dispositivo,
        )
        return (
            jsonify(
                {
                    "ok": False,
                    "error": f"Cuenta bloqueada. Intenta en {minutos} minuto(s).",
                }
            ),
            403,
        )

    registrar_actividad(
        "login_fail",
        email,
        email=email,
        detalle="Contraseña incorrecta",
        ip=ip,
        dispositivo=dispositivo,
    )
    return jsonify({"ok": False, "error": "Email o contraseña incorrectos."}), 401


@app.route("/api/auth/me")
def api_auth_me():
    username = session.get("username")
    if not username:
        return jsonify({"authenticated": False}), 401
    return jsonify(
        {
            "authenticated": True,
            "username": username,
            "es_admin": session.get("es_admin", False),
        }
    )


@app.route("/api/portafolios", methods=["GET", "POST"])
def api_portafolios():
    username = session.get("username")
    if not username:
        return jsonify({"error": "No autorizado"}), 401

    if request.method == "GET":
        portafolios = listar_portafolios_de_usuario(username)
        return jsonify({"portafolios": portafolios})

    data = request.get_json(silent=True) or {}
    nombre = data.get("nombre", "").strip()
    perfil = data.get("perfil", "agresivo")
    propietario = data.get("propietario", username).strip()
    inversion = float(data.get("inversion_inicial", data.get("inversion", 0)) or 0)
    aporte = float(data.get("aporte_dca", 0) or 0)
    frecuencia = int(data.get("frecuencia_meses", 0) or 0)

    if not nombre:
        return jsonify({"error": "El nombre del portafolio es obligatorio"}), 400

    archivo = crear_portafolio_para_usuario(
        username, nombre, perfil, propietario, inversion, aporte, frecuencia
    )
    if not archivo:
        return jsonify({"ok": False, "error": "No se pudo crear el portafolio"}), 500
    # devolver solo el nombre del archivo (sin la carpeta) para que el frontend
    # lo use en las rutas /portafolio/<archivo>
    import os as _os
    return jsonify({"ok": True, "archivo": _os.path.basename(archivo)})


@app.route("/api/dashboard/<archivo>")
def api_dashboard(archivo):
    username = session.get("username")
    if not username:
        return jsonify({"error": "No autorizado"}), 401

    portafolio = leer_portafolio(archivo)
    if not portafolio or portafolio.get("owner") != username:
        return jsonify({"error": "No encontrado"}), 404

    tiempo_real = calcular_tiempo_real(portafolio)
    macro = cargar_macro()

    
    if macro:
        macro_json = {k: v for k, v in macro.items() if k != 'trm_hist'}
        if 'trm_hist' in macro:
            trm_df = macro['trm_hist']
            macro_json['trm_hist'] = {
                'fechas':  [str(f)[:10] for f in trm_df.index],
                'valores': trm_df['TRM'].values.tolist(),
            }
        macro_json['tasa_eur'] = obtener_tasa_usd_eur()   # EUR por 1 USD
        # 'trm' ya está en macro_json (COP por 1 USD) → sirve para dividir COP→USD

    return jsonify({
        'portafolio': {
            'nombre':       portafolio.get('nombre'),
            'propietario':  portafolio.get('propietario'),
            'perfil':       portafolio.get('perfil'),
            'fecha_inicio': portafolio.get('fecha_inicio'),
        },
        'composicion': portafolio.get('composicion', {}),
        'tiempo_real': tiempo_real,
        'macro':       macro_json,
        'historico': portafolio.get('historial',[]),
    })

@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/auth/forgot-password", methods=["POST"])
def api_auth_forgot_password():
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip()
    _solicitar_reset(email)
    # Misma respuesta exista o no el email — no revelar qué correos están registrados
    return jsonify({"ok": True})


@app.route("/api/auth/reset-password", methods=["POST"])
def api_auth_reset_password():
    data = request.get_json(silent=True) or {}
    error = _aplicar_reset(
        (data.get("token") or "").strip(), (data.get("password") or "").strip()
    )
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True})

@app.route("/api/config/<archivo>", methods=["GET", "PUT"])
def api_config(archivo):
    if verificar_acceso(archivo):
        return jsonify({"error": "No autorizado"}), 401

    portafolio = leer_portafolio(archivo)
    if not portafolio:
        return jsonify({"error": "No encontrado"}), 404

    if request.method == 'GET':
        return jsonify({
            'nombre': portafolio.get('nombre'),
            'activo': portafolio.get('monitoreo_activo', False),
            'divisa': portafolio.get('divisa', 'USD'),
            'perfil': portafolio.get('perfil', 'agresivo'),
            'propietario': portafolio.get('propietario', ''),
            'fecha_inicio': portafolio.get('fecha_inicio', ''),
        })

    # PUT: guardar divisa y/o nombre
    data = request.get_json(silent=True) or {}

    ruta = f"datos/portafolios/{archivo}"
    with open(ruta, "r", encoding="utf-8") as f:
        d = json.load(f)

    mensajes = []

    if "divisa" in data:
        divisa = data.get("divisa", "USD").strip().upper()
        if divisa not in ("USD", "EUR", "COP"):
            return jsonify({"error": "Divisa no válida"}), 400
        d["divisa"] = divisa
        mensajes.append(f"Divisa cambiada a {divisa}")

    if "nombre" in data:
        nombre = data.get("nombre", "").strip()
        if not nombre:
            return jsonify({"error": "El nombre no puede estar vacío"}), 400
        d["nombre"] = nombre
        mensajes.append("Nombre actualizado")

        # Sincronizar el nombre en el estado del monitor, si existe
        ruta_monitor = os.path.join(DATOS_DIR, "portafolios", f"monitor_{archivo}")
        if os.path.exists(ruta_monitor):
            try:
                with open(ruta_monitor, "r", encoding="utf-8") as f:
                    estado = json.load(f)
                estado["nombre_portafolio"] = nombre
                with open(ruta_monitor, "w", encoding="utf-8") as f:
                    json.dump(estado, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

    return jsonify(
        {
            "ok": True,
            "mensaje": " / ".join(mensajes) or "Sin cambios",
            "divisa": d.get("divisa", "USD"),
            "nombre": d.get("nombre", ""),
        }
    )


def _armar_aporte_desde_form(data, composicion):
    """Parsea, valida y calcula un aporte desde el body del form de seguimiento.
    Usa SIEMPRE la TRM oficial para el cálculo (trm_real es solo trazabilidad).
    Devuelve (aporte, None) si todo bien, o (None, (respuesta_error, status))."""
    activo = data.get("activo", "").upper()
    if activo not in {c.upper() for c in composicion}:
        return None, (jsonify({"error": "Ese activo no pertenece a este portafolio"}), 400)
    fecha = data.get("fecha", datetime.now().strftime("%Y-%m-%d"))
    monto_usd = float(str(data.get("monto_usd", "0")).replace(",", "."))
    fracciones = float(str(data.get("fracciones", "0")).replace(",", "."))
    if monto_usd <= 0 or fracciones <= 0:
        return None, (jsonify({"error": "El monto y las fracciones deben ser mayores a 0"}), 400)

    # TRM real (opcional): solo trazabilidad, NO entra al cálculo.
    trm_real_raw = data.get("trm_real")
    trm_real = None
    if trm_real_raw not in (None, ""):
        trm_real = float(str(trm_real_raw).replace(",", "."))
        if trm_real <= 0:
            return None, (jsonify({"error": "La TRM ingresada debe ser mayor a 0"}), 400)

    precio_usd = round(monto_usd / fracciones, 4)
    try:
        trm_df = pd.read_parquet("datos/macro/trm.parquet")
        idx = trm_df.index.get_indexer([pd.to_datetime(fecha)], method="nearest")[0]
        trm_dia = float(trm_df["TRM"].iloc[idx])
    except Exception:
        return None, (jsonify({
            "error": "No hay TRM oficial disponible para esa fecha. "
                     "No se registró la compra; intenta más tarde o revisa la fecha."
        }), 400)
    monto_cop = round(monto_usd * trm_dia, 0)

    aporte = {
        "fecha": fecha,
        "activo": activo,
        "monto_usd": round(monto_usd, 2),
        "monto_cop": monto_cop,
        "precio_usd": precio_usd,
        "trm_dia": trm_dia,
        "fracciones": round(fracciones, 8),
        "tipo": "manual",
    }
    if trm_real is not None:
        aporte["trm_real"] = trm_real  # solo trazabilidad, no calcula
    return aporte, None


@app.route("/api/seguimiento/<archivo>", methods=["GET", "POST"])
def api_seguimiento(archivo):
    if verificar_acceso(archivo):
        return jsonify({"error": "No autorizado"}), 401

    asegurar_ids_aportes(archivo)  # backfill de ids en aportes viejos
    portafolio = leer_portafolio(archivo)
    composicion = portafolio.get("composicion", {})

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        try:
            aporte, err = _armar_aporte_desde_form(data, composicion)
            if err:
                return err
            guardar_aporte(archivo, aporte)
            portafolio = leer_portafolio(archivo)
        except Exception as e:
            return jsonify({"error": f"Error: {str(e)}"}), 400

    # GET (y respuesta tras POST): armar el estado completo
    aportes = portafolio.get("aportes", [])
    entrados = list(set(a["activo"] for a in aportes))
    pendientes = [a for a in composicion if a not in entrados]
    total_a = len(composicion)
    total_e = len(entrados)
    pct = int(total_e / total_a * 100) if total_a > 0 else 0

    pendientes_data = [
        {
            "activo": a,
            "peso": composicion.get(a, 0),
            "precio_usd": precio_actual_usd(a) or 0,
        }
        for a in pendientes
    ]

    return jsonify(
        {
            "nombre": portafolio.get("nombre"),
            "composicion": composicion,
            "progreso": {"entrados": total_e, "total": total_a, "pct": pct},
            "pendientes": pendientes_data,
            "entrados": entrados,
            "aportes": aportes,
        }
    )


@app.route("/api/seguimiento/<archivo>/aporte/<aporte_id>", methods=["PUT", "DELETE"])
def api_seguimiento_aporte(archivo, aporte_id):
    if verificar_acceso(archivo):
        return jsonify({"error": "No autorizado"}), 401

    if request.method == "DELETE":
        if not eliminar_aporte(archivo, aporte_id):
            return jsonify({"error": "Aporte no encontrado"}), 404
        return jsonify({"ok": True})

    # PUT — editar: recalcula con la TRM oficial, igual que un registro.
    data = request.get_json(silent=True) or {}
    try:
        composicion = leer_portafolio(archivo).get("composicion", {})
        campos, err = _armar_aporte_desde_form(data, composicion)
        if err:
            return err
        if not editar_aporte(archivo, aporte_id, campos):
            return jsonify({"error": "Aporte no encontrado"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 400


@app.route('/api/trm-analisis')
def api_trm_analisis():
    username = session.get('username')
    if not username:
        return jsonify({'error': 'No autorizado'}), 401

    hoy = datetime.now().strftime("%Y-%m-%d")
    ruta_cache = os.path.join(DATOS_DIR, "macro/trm_analisis.json")

    # ¿Hay análisis de hoy ya guardado?
    try:
        if os.path.exists(ruta_cache):
            with open(ruta_cache, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            if cache.get('fecha') == hoy and cache.get('texto'):
                return jsonify({'analisis': cache['texto'], 'fecha': hoy, 'cacheado': True})
    except Exception as e:
        print(f"Error leyendo cache TRM: {e}")

    # No hay de hoy → generar
    macro = cargar_macro()
    if not macro or 'trm_hist' not in macro:
        return jsonify({'analisis': '', 'error': 'Sin datos de TRM'}), 200

    analisis = generar_analisis_trm(macro['trm_hist'])

    # Guardar en cache con la fecha de hoy
    try:
        os.makedirs(os.path.dirname(ruta_cache), exist_ok=True)
        with open(ruta_cache, 'w', encoding='utf-8') as f:
            json.dump({'fecha': hoy, 'texto': analisis}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error guardando cache TRM: {e}")

    return jsonify({'analisis': analisis, 'fecha': hoy, 'cacheado': False})

@app.route('/api/portafolios/<archivo>/activar', methods=['POST'])
def api_activar_portafolio_json(archivo):
    if verificar_acceso(archivo):
        return jsonify({'ok': False, 'error': 'No autorizado'}), 401
    try:
        ruta = f'datos/portafolios/{archivo}'
        with open(ruta, 'r', encoding='utf-8') as f:
            d = json.load(f)

        d['monitoreo_activo'] = True

        # Exclusividad: solo un portafolio activo a la vez (igual que api_toggle_monitor)
        username = session.get('username', '')
        for p in listar_portafolios_de_usuario(username):
            if p['archivo'] != archivo:
                otra = f'datos/portafolios/{p["archivo"]}'
                try:
                    with open(otra, 'r', encoding='utf-8') as f2:
                        o = json.load(f2)
                    if o.get('monitoreo_activo'):
                        o['monitoreo_activo'] = False
                        with open(otra, 'w', encoding='utf-8') as f2:
                            json.dump(o, f2, indent=2, ensure_ascii=False)
                except Exception:
                    pass

        with open(ruta, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=2, ensure_ascii=False)

        # Primer ciclo SIN hilo — corre ya y muestra errores
        try:
            import monitor
            print(f"🔧 Activando {archivo} | composición: {list(d.get('composicion', {}).keys())}")
            rangos = monitor.precalcular_rangos(archivo, d)
            if rangos:
                print(f"✅ Rangos calculados para {archivo}")
                if monitor.mercado_abierto():
                    monitor.vigilar_precios(archivo, d, rangos)
                    print(f"✅ Vigilancia inicial OK")
            else:
                print(f"⚠️ precalcular_rangos devolvió None — revisa la composición")
        except Exception as e:
            import traceback
            print(f"❌ Error en primer ciclo: {e}")
            traceback.print_exc()

        return jsonify({'ok': True, 'activo': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/portafolios/<archivo>/desactivar', methods=['POST'])
def api_desactivar_portafolio_json(archivo):
    if verificar_acceso(archivo):
        return jsonify({'ok': False, 'error': 'No autorizado'}), 401
    try:
        ruta = f'datos/portafolios/{archivo}'
        with open(ruta, 'r', encoding='utf-8') as f:
            d = json.load(f)
        d['monitoreo_activo'] = False
        with open(ruta, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        return jsonify({'ok': True, 'activo': False})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route("/api/admin/usuarios", methods=["GET"])
def api_admin_listar_usuarios():
    """Todos los usuarios con su info, SIN el hash de contraseña.
 
    Agrega dos datos calculados que el admin necesita para vigilar:
      - bloqueado: si la cuenta esta bloqueada AHORA (compara la fecha)
      - n_portafolios: cuantos portafolios tiene ese usuario
    """
    if not session.get("es_admin"):
        return jsonify({"ok": False, "error": "No autorizado"}), 403
 
    from datetime import datetime
 
    usuarios = _leer_usuarios()
    ahora = datetime.now()
    lista = []
 
    for uname, u in usuarios.items():
        username = u.get("username", uname)
 
        # ¿bloqueado ahora mismo? (no solo si tiene fecha, sino si aun no pasa)
        bloqueado = False
        bh = u.get("bloqueado_hasta")
        if bh:
            try:
                bloqueado = datetime.fromisoformat(bh) > ahora
            except Exception:
                bloqueado = False
 
        # portafolios del usuario (reusa la funcion del gestor)
        try:
            n_port = len(listar_portafolios_de_usuario(username))
        except Exception:
            n_port = 0
 
        lista.append({
            "username": username,
            "email": u.get("email", ""),
            "es_admin": bool(u.get("es_admin", False)),
            "fecha_registro": u.get("fecha_registro", ""),
            "ultimo_login": u.get("ultimo_login", ""),
            "intentos_fallidos": u.get("intentos_fallidos", 0),
            "bloqueado": bloqueado,
            "email_notifications": bool(u.get("email_notifications", True)),
            "n_portafolios": n_port,
        })
 
    # admins primero, luego por ultimo login mas reciente
    lista.sort(key=lambda x: (not x["es_admin"], x["ultimo_login"] or ""), reverse=False)
 
    return jsonify({"ok": True, "usuarios": lista, "total": len(lista)})
 
@app.route("/api/admin/actividad", methods=["GET"])
def api_admin_actividad():
    """Actividad reciente del log, mas nueva primero.
 
    ?limite=N   (default 50)
    ?tipo=X     filtra por tipo de evento (login_ok, registro, eliminacion...)
    """
    if not session.get("es_admin"):
        return jsonify({"ok": False, "error": "No autorizado"}), 403
 
    try:
        logs = _leer_logs()
    except Exception:
        logs = []
 
    if not isinstance(logs, list):
        logs = []
 
    filtro_tipo = request.args.get("tipo")
    if filtro_tipo:
        logs = [l for l in logs if l.get("tipo") == filtro_tipo]
 
    try:
        limite = int(request.args.get("limite", 50))
    except ValueError:
        limite = 50
 
    recientes = list(reversed(logs))[:limite]
 
    from collections import Counter
    tipos = Counter(l.get("tipo", "desconocido") for l in logs)
 
    return jsonify({
        "ok": True,
        "actividad": recientes,
        "total": len(logs),
        "resumen_tipos": dict(tipos),
    })

if __name__=="__main__":
    print("="*55)
    print("🌐 DASHBOARD INICIANDO...")
    print("   http://localhost:5000")
    print("=" * 55)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
