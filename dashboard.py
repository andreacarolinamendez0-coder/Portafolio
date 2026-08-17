import dotenv

dotenv.load_dotenv()
from flask import Flask, request, session, jsonify, redirect
import pandas as pd
import json, os, requests, time, threading, re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import quote as _url_quote
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
    username_por_telegram_chat_id,
    crear_portafolio_para_usuario,
    guardar_composicion,
    guardar_aporte,
    asegurar_ids_aportes,
    eliminar_aporte,
    editar_aporte,
    saldo_disponible,
    SaldoInsuficiente,
    guardar_deposito,
    editar_deposito,
    eliminar_deposito,
    asegurar_caja_inicial,
    PosicionInsuficiente,
    fracciones_disponibles,
    realizado_por_ticker,
    guardar_venta,
    editar_venta,
    eliminar_venta,
    guardar_analisis_historico,
    set_monitoreo,
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
    _LOCK,
    _LOCK_MONITOR,
    _escribir,
)

# Patron de validacion de tickers: 1-6 letras mayusculas, opcionalmente sufijo
# -USD (ej. cripto). Reutilizado en todos los endpoints que persisten
# composicion o interpolan tickers en texto/URLs (auditoria: validacion
# inconsistente entre endpoints).
PATRON_TICKER = re.compile(r"[A-Z]{1,6}(-USD)?")

# Banda de tolerancia de desviacion de PESOS (Seguimiento/Composicion) --
# regla 5/25 de Swedroe, estandar de la industria para bandas de rebalanceo:
# evita castigar por igual a un activo chico (peso meta bajo) y a uno grande
# con el mismo umbral fijo en puntos porcentuales. Se dispara la banda mas
# estricta de las dos: absoluta (5pp) o relativa (25% del propio peso meta).
# Multiplicador por perfil: agresivo tolera mas drift antes de alertar
# (coherente con dejar correr posiciones ganadoras), conservador corrige mas
# rapido. JUICIO editable, no estadistico -- mismo estilo que
# perfilador.TOPES_POR_PLAZO. IMPORTANTE: esta banda es SOLO para la Capa 1
# (el widget informativo/alerta de Composicion) -- desviacion de pesos por
# si sola NUNCA dispara la sugerencia de ir al Analista (ver
# evaluar_disparo_rebalanceo, que usa metricas reales, no pesos).
BANDA_PESO_ABSOLUTA_PP = 5.0
BANDA_PESO_RELATIVA_FRAC = 0.25
MULTIPLICADOR_BANDA_POR_PERFIL = {"conservador": 0.8, "moderado": 1.0, "agresivo": 1.3}

# UMBRAL_PROGRESO_MINIMO evita marcar desviacion mientras el portafolio
# todavia se esta construyendo (pocos tickers meta comprados aun) -- ahi la
# señal es ruido, no rebalanceo.
UMBRAL_PROGRESO_MINIMO = 90


def _banda_tolerancia_peso(peso_objetivo_frac, perfil):
    """Banda de tolerancia en puntos porcentuales para un activo con este
    peso objetivo (fraccion 0-1) y este perfil de riesgo. Ver comentario de
    BANDA_PESO_ABSOLUTA_PP arriba para la logica completa.

    Regla Swedroe real: gana la banda MAS ESTRICTA (mas chica) de las dos --
    para peso >= 20% la relativa (25%*peso) ya es >= 5pp, asi que la
    absoluta es la que ata primero; para peso < 20% es al reves. min(), no
    max() -- con max() casi nunca se alertaria en posiciones chicas, que es
    justo lo opuesto de lo que la regla busca (posiciones chicas deben
    corregirse con un drift proporcionalmente menor)."""
    banda_pp = min(BANDA_PESO_ABSOLUTA_PP, BANDA_PESO_RELATIVA_FRAC * (peso_objetivo_frac or 0) * 100)
    return banda_pp * MULTIPLICADOR_BANDA_POR_PERFIL.get(perfil, 1.0)

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


def arrancar_scheduler():
    time.sleep(15)
    from scheduler import iniciar_scheduler

    iniciar_scheduler()


threading.Thread(target=arrancar_monitor, daemon=True).start()
threading.Thread(target=arrancar_scheduler, daemon=True).start()

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


MAX_TOOL_ROUNDS = 3


def anthropic_chat(messages, system="", max_tokens=300, temperature=0.5, tools=None, tool_executor=None):
    """Llama al modelo. Si `tools`+`tool_executor` se pasan, soporta un loop
    corto de tool use: el modelo puede pedir ejecutar una tool, se le devuelve
    el resultado, y puede seguir iterando hasta MAX_TOOL_ROUNDS antes de dar
    su respuesta final en texto.

    NOTA: `temperature` nunca se pasó a client.messages.create() en la version
    original de esta funcion (no se sabe si fue deliberado). Se preserva ese
    mismo comportamiento aqui: no se agrega a kwargs, para no introducir un
    cambio de comportamiento no solicitado.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    msgs = list(messages)
    resp = None
    for _ in range(MAX_TOOL_ROUNDS):
        kwargs = {
            "model": "claude-sonnet-4-5",
            "max_tokens": max_tokens,
            "messages": msgs,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        resp = client.messages.create(**kwargs)
        if resp.stop_reason != "tool_use" or not tool_executor:
            return "".join(b.text for b in resp.content if b.type == "text")

        msgs.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                resultado = tool_executor(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(resultado, ensure_ascii=False, default=str),
                })
        msgs.append({"role": "user", "content": tool_results})

    # Se agotaron las rondas sin respuesta de texto final - fallback.
    if resp is not None:
        texto = "".join(b.text for b in resp.content if b.type == "text")
        if texto:
            return texto
    return "No pude completar la consulta al motor a tiempo, ¿puedes reformular tu pregunta?"


def _tool_simular_propuesta(input_):
    """Ejecuta el motor cuantitativo real (adaptador_analista.generar_propuesta_completa)
    y devuelve un resumen LIGERO pensado para que el modelo lo lea antes de
    mencionar tickers/pesos concretos al usuario. Nunca lanza excepcion: si
    algo falla, devuelve un dict de error legible por el modelo.
    """
    try:
        from adaptador_analista import generar_propuesta_completa

        activos_ancla = input_.get("activos_ancla")
        forzar_exacto = bool(input_.get("forzar_exacto")) and bool(activos_ancla)
        # forzar_exacto: restringe el universo a EXACTAMENTE activos_ancla (nada
        # de busqueda adicional), y esos mismos tickers quedan ademas protegidos
        # de las purgas dentro de ese universo chico -- ver el comentario en
        # adaptador_analista._cargar_todo_para_motor sobre como se combinan
        # tickers_fijos y activos_ancla.
        tickers_fijos = (
            activos_ancla if forzar_exacto
            else (input_.get("tickers_candidatos") if not activos_ancla else None)
        )
        resultado = generar_propuesta_completa(
            perfil=input_.get("perfil"),
            horizonte=input_.get("horizonte", 10),
            inversion=input_.get("inversion"),
            aporte_dca=input_.get("aporte_dca", 0),
            frecuencia_meses=input_.get("frecuencia_meses", 1),
            tickers_fijos=tickers_fijos,
            activos_ancla=activos_ancla,
        )

        pesos = resultado.get("pesos") or {}
        pesos_reales = {k: round(float(v), 3) for k, v in pesos.items()}

        candidatos = input_.get("tickers_candidatos") or []
        ancla_set = set(activos_ancla or [])
        # activos_ancla tambien puede faltar del resultado si nunca tuvo
        # historico descargado (motor_seleccion.seleccionar_anclado filtra el
        # ancla contra retornos.columns antes de protegerla) -- sin esto, un
        # ticker que se prometio "nunca se purga" desaparecia mudo, sin
        # ninguna explicacion, justo el caso que forzar_exacto no deberia
        # permitir.
        excluidos = [t for t in list(candidatos) + list(ancla_set) if t not in pesos_reales]
        excluidos = list(dict.fromkeys(excluidos))  # sin duplicados, mismo orden

        motivos_todos = resultado.get("motivos_exclusion") or {}
        motivos_exclusion = {t: motivos_todos[t] for t in excluidos if t in motivos_todos}
        # Excluidos que ni siquiera aparecen en motivos_todos nunca entraron
        # al universo del motor (sin historico descargado, o ticker
        # invalido/inventado) -- no fueron purgados por ningun paso de
        # seleccion, asi que el modelo no tendria ningun hecho que dar.
        for t in excluidos:
            if t in motivos_exclusion:
                continue
            if t in ancla_set:
                motivos_exclusion[t] = (
                    f"'{t}' no tiene histórico de precios descargado todavía, así que nunca "
                    f"entró al universo evaluado por el motor -- no se pudo incluir en la "
                    f"simulación pese a haberlo pedido como ancla. Necesita descargarse primero "
                    f"(agregarlo manualmente desde la propuesta) antes de poder forzarlo."
                )
            else:
                motivos_exclusion[t] = (
                    f"No hay historico de precios descargado para '{t}' todavia: nunca "
                    f"entro al universo evaluado por el motor (no fue purgado por ningun "
                    f"paso de seleccion, simplemente no hay datos para evaluarlo)."
                )

        return {
            "pesos_reales": pesos_reales,
            "tickers_candidatos_excluidos": excluidos,
            "motivos_exclusion": motivos_exclusion,
            "alfa": resultado.get("alfa"),
            "metricas": resultado.get("datos", {}).get("metricas"),
            "advertencia_cdt": resultado.get("advertencia_cdt") or None,
            "advertencia_concentracion": resultado.get("advertencia_concentracion"),
        }
    except Exception as e:
        return {
            "error": f"No se pudo simular la propuesta con el motor real: {e}",
        }


def cargar_macro():
    archivos = [
        os.path.join(DATOS_DIR, "macro/trm.parquet"),
        os.path.join(DATOS_DIR, "macro/inflacion_col.parquet"),
        os.path.join(DATOS_DIR, "macro/inflacion_usa.parquet"),
        os.path.join(DATOS_DIR, "macro/risk_free.parquet"),
        os.path.join(DATOS_DIR, "macro/tasa_banrep.parquet"),
    ]
    if any(not os.path.exists(f) for f in archivos):
        os.makedirs(os.path.join(DATOS_DIR, "macro"), exist_ok=True)
        os.makedirs(os.path.join(DATOS_DIR, "precios"), exist_ok=True)
        os.makedirs(os.path.join(DATOS_DIR, "portafolios"), exist_ok=True)
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


def _pool_posicion_viva(aportes, ventas, ticker):
    """Recorre aportes+ventas de un ticker en orden CRONOLOGICO manteniendo un
    pool de (fracciones, costo_usd, costo_cop, comision_cop) que se reduce
    PROPORCIONALMENTE en cada venta (al costo promedio del momento, no solo
    resta fracciones). Sin esto, vender el 100% de un ticker y volver a
    comprarlo "diluye" el costo base con el precio del lote viejo ya vendido
    (bug de auditoria: costo real $300 se reportaba como $133, rentabilidad
    1259% en vez de la real). fecha_inicio queda como la fecha del lote
    actualmente abierto (se resetea si el pool llega a cero) en vez de "el
    primer aporte en orden de insercion" -- corrige tambien el caso de
    aportes registrados fuera de orden cronologico (backfill de compras
    viejas), que antes daban una fecha_inicio incorrecta."""
    eventos = sorted(
        [
            {
                "tipo": "compra", "fecha": a["fecha"], "frac": float(a["fracciones"]),
                "usd": float(a["monto_usd"]), "cop": float(a["monto_cop"]),
                "comision_cop": float(a.get("comision", 0)) * float(a.get("trm_dia", 0)),
            }
            for a in aportes if a.get("activo") == ticker
        ]
        + [
            {"tipo": "venta", "fecha": v["fecha"], "frac": float(v.get("fracciones", 0))}
            for v in ventas if v.get("activo") == ticker
        ],
        key=lambda e: e["fecha"],
    )
    frac = usd = cop = comision_cop = 0.0
    fecha_inicio = None
    for e in eventos:
        if e["tipo"] == "compra":
            if frac <= 1e-9:
                fecha_inicio = e["fecha"]  # nuevo lote (o el primero)
            frac += e["frac"]
            usd += e["usd"]
            cop += e["cop"]
            comision_cop += e["comision_cop"]
        else:
            if frac > 1e-9:
                frac_vendida = min(e["frac"], frac)
                proporcion = frac_vendida / frac
                usd -= usd * proporcion
                cop -= cop * proporcion
                comision_cop -= comision_cop * proporcion
                frac -= frac_vendida
            if frac <= 1e-9:
                frac = usd = cop = comision_cop = 0.0
    return {"frac": frac, "usd": usd, "cop": cop, "comision_cop": comision_cop, "fecha_inicio": fecha_inicio}


def _trayectoria_rentabilidad_posicion(aportes, ventas, ticker, fecha_inicio, precios_serie):
    """Serie diaria de rentabilidad de la posicion viva de `ticker` desde
    `fecha_inicio` (el mismo valor que ya calcula _pool_posicion_viva para el
    lote actualmente abierto), respetando el COSTO PROMEDIO PONDERADO vigente
    en cada momento -- no solo el precio de mercado puro desde la primera
    compra. Corrige la inconsistencia entre drawdown_real (antes: precio puro)
    y rentabilidad_real (ya usaba el pool cronologico via _pool_posicion_viva):
    si compraste el mismo ticker en dos momentos distintos, el drawdown que
    viviste TU como inversionista no es el mismo que vivio el activo en
    bolsa, porque tu costo base cambio con la segunda compra.

    Reimplementa el recorrido cronologico de eventos de forma AISLADA (no
    reusa _pool_posicion_viva directamente) para no arriesgar esa funcion, ya
    en el camino critico de costo base/ganancias -- pero como recibe el mismo
    `fecha_inicio` que ya calculo ahi, el punto de partida siempre coincide, y
    por construccion no puede haber otro reseteo de pool dentro de
    [fecha_inicio, hoy] (si lo hubiera habido, fecha_inicio ya reflejaria ese
    reseteo mas reciente).

    Con una sola compra en el periodo, esta serie es (precio / costo) - 1, un
    multiplo escalar POSITIVO y CONSTANTE del precio -- el drawdown de una
    serie y el de cualquier multiplo escalar positivo de ella son iguales, asi
    que el caso simple (sin DCA) da EXACTAMENTE el mismo numero que antes. Con
    2+ compras, el costo promedio SI cambia en cada compra nueva, y ahi es
    donde este calculo diverge del precio puro (correctamente)."""
    eventos = sorted(
        [
            {"fecha": a["fecha"], "frac": float(a["fracciones"]), "usd": float(a["monto_usd"])}
            for a in aportes if a.get("activo") == ticker and a["fecha"] >= fecha_inicio
        ]
        + [
            {"fecha": v["fecha"], "frac": -float(v.get("fracciones", 0)), "usd": 0.0}
            for v in ventas if v.get("activo") == ticker and v["fecha"] >= fecha_inicio
        ],
        key=lambda e: e["fecha"],
    )
    if not eventos:
        return None

    frac = usd = 0.0
    fechas_evt, frac_evt, usd_evt = [], [], []
    for e in eventos:
        if e["frac"] >= 0:
            frac += e["frac"]
            usd += e["usd"]
        elif frac > 1e-9:
            frac_vendida = min(-e["frac"], frac)
            usd -= usd * (frac_vendida / frac)
            frac -= frac_vendida
        fechas_evt.append(e["fecha"])
        frac_evt.append(frac)
        usd_evt.append(usd)

    serie_precio = precios_serie.loc[fecha_inicio:].dropna()
    if serie_precio.empty:
        return None

    idx_eventos = pd.to_datetime(fechas_evt)
    frac_en_t = pd.Series(frac_evt, index=idx_eventos).reindex(serie_precio.index, method="ffill")
    usd_en_t = pd.Series(usd_evt, index=idx_eventos).reindex(serie_precio.index, method="ffill")

    valor_en_t = frac_en_t * serie_precio
    valido = usd_en_t > 1e-9  # NaN > 1e-9 es False -- excluye fechas antes del primer evento
    rent_en_t = ((valor_en_t - usd_en_t) / usd_en_t)[valido]
    return rent_en_t.dropna()


def calcular_tiempo_real(portafolio):
    if not portafolio or not portafolio.get("aportes"):
        return None
    inf_anual = portafolio.get("inflacion_col", 4.90)
    # TRM de hoy: best-effort. Sin ella el núcleo USD sigue vivo; solo se
    # anulan las columnas de efecto (dif. cambio / inflación).
    try:
        trm_hoy = float(pd.read_parquet("datos/macro/trm.parquet")["TRM"].iloc[-1])
    except Exception:
        trm_hoy = None

    ventas = portafolio.get("ventas", [])
    tickers = sorted(set(a["activo"] for a in portafolio["aportes"]))
    pos_raw = {}
    for tk in tickers:
        pool = _pool_posicion_viva(portafolio["aportes"], ventas, tk)
        if pool["frac"] > 1e-9:
            pos_raw[tk] = pool

    resultados = []
    total_inv = total_val = 0.0
    total_fx = total_infl = 0.0
    hay_efecto = trm_hoy is not None
    for tk, d in pos_raw.items():
        frac_viva = d["frac"]  # ya neteado de ventas por _pool_posicion_viva
        p = precio_actual_usd(tk)
        if p is None:
            continue
        inv = d["usd"]                     # invertido USD (costo base vivo, ya neteado)
        val = frac_viva * p                # valor USD hoy
        gan = val - inv                    # ganancia USD (P&L de posición)

        fx_cop = infl_cop = None
        if hay_efecto:
            trm_prom = d["cop"] / d["usd"] if d["usd"] else 0.0
            fx_cop = inv * (trm_hoy - trm_prom)   # ganancia/pérdida por FX en pesos
            años = (datetime.now() - datetime.strptime(d["fecha_inicio"], "%Y-%m-%d")).days / 365.25
            val_cop = val * trm_hoy
            infl_cop = val_cop * (1 - 1 / (1 + inf_anual / 100) ** años)  # erosión poder adquisitivo
            total_fx += fx_cop
            total_infl += infl_cop

        resultados.append(
            {
                "activo": tk,
                "fracciones": round(frac_viva, 4),
                "fecha_inicio": d["fecha_inicio"],
                "precio_hoy": round(p, 2),
                "valor_hoy": round(val, 2),
                "invertido": round(inv, 2),
                "ganancia": round(gan, 2),
                "rentabilidad": round((gan / inv * 100) if inv > 0 else 0, 2),
                "fx_cop": round(fx_cop, 0) if fx_cop is not None else None,
                "inflacion_cop": round(infl_cop, 0) if infl_cop is not None else None,
            }
        )
        total_inv += inv
        total_val += val
    if not resultados:
        return None
    return {
        "posiciones": resultados,
        "total_invertido": round(total_inv, 2),
        "total_valor": round(total_val, 2),
        "ganancia_total": round(total_val - total_inv, 2),
        "rentabilidad_total": round(
            (total_val - total_inv) / total_inv * 100 if total_inv > 0 else 0, 2
        ),
        "fx_cop_total": round(total_fx, 0) if hay_efecto else None,
        "inflacion_cop_total": round(total_infl, 0) if hay_efecto else None,
    }


def calcular_composicion_real(tiempo_real):
    """{ticker: peso} a partir de valor_hoy/total_valor -- la composicion
    REAL actual, derivada de calcular_tiempo_real(). Distinta de
    portafolio["composicion"], que es la META (la que dejo la ultima
    propuesta aplicada)."""
    if not tiempo_real or not tiempo_real.get("total_valor"):
        return {}
    total = tiempo_real["total_valor"]
    if total <= 0:
        return {}
    return {p["activo"]: round(p["valor_hoy"] / total, 4) for p in tiempo_real["posiciones"]}


def calcular_desviacion_composicion(portafolio, tiempo_real):
    """Compara composicion real vs meta -- SOLO desviacion de PESOS (Capa 1,
    el widget informativo/alerta de Composicion). Devuelve {"aplica": False}
    mientras el portafolio todavia se esta construyendo (progreso de entrada
    por debajo de UMBRAL_PROGRESO_MINIMO) -- comparar peso real vs meta no
    tiene sentido todavia si la mayoria de los tickers meta ni siquiera se
    han comprado. Progreso intersectado contra la meta VIGENTE (un ticker
    comprado que ya no esta en la meta no cuenta como progreso) -- misma
    formula que usa /api/seguimiento para su "Progreso de entradas".

    IMPORTANTE: esta funcion ya NO decide si hay que ir al Analista --
    desviacion de pesos por si sola nunca dispara esa sugerencia (ver
    evaluar_disparo_rebalanceo, que usa metricas reales persistidas, no
    esto). El campo "necesita_rebalanceo" que existia aqui se retiro."""
    composicion = portafolio.get("composicion") or {}
    aportes = portafolio.get("aportes") or []
    entrados = set(a["activo"] for a in aportes)
    total_meta = len(composicion)
    progreso_pct = (len(entrados & set(composicion)) / total_meta * 100) if total_meta else 0

    if not composicion or progreso_pct < UMBRAL_PROGRESO_MINIMO:
        return {"aplica": False, "progreso_pct": round(progreso_pct, 1)}

    pesos_reales = calcular_composicion_real(tiempo_real)
    if not pesos_reales:
        return {"aplica": False, "progreso_pct": round(progreso_pct, 1)}

    perfil = portafolio.get("perfil", "moderado")
    tickers = set(pesos_reales) | set(composicion)
    desviaciones = {
        t: round((pesos_reales.get(t, 0) - composicion.get(t, 0)) * 100, 1)
        for t in tickers
    }
    desviacion_total = round(sum(abs(v) for v in desviaciones.values()) / 2, 1)
    activos_desviados = {
        t: v for t, v in desviaciones.items()
        if abs(v) >= _banda_tolerancia_peso(composicion.get(t, 0), perfil)
    }

    return {
        "aplica": True,
        "progreso_pct": round(progreso_pct, 1),
        "desviacion_total_pp": desviacion_total,
        "activos_desviados": activos_desviados,
    }


def calcular_metricas_reales_por_activo(portafolio, tiempo_real):
    """Fila por activo: peso meta/real, rentabilidad real (ya calculada por
    calcular_tiempo_real), volatilidad y drawdown REALES desde la fecha de
    compra (sobre precios reales, USD), y 'lo que vio el motor' (Sortino
    historico + volatilidad historica que motor_seleccion.py uso al
    seleccionar/ponderar el activo) -- ver adaptador_analista.
    metricas_historicas_por_activo para por que NUNCA se inventa una
    rentabilidad proyectada por activo individual."""
    if not tiempo_real or not tiempo_real.get("posiciones"):
        return []

    import numpy as np
    import preparador_datos as prep
    from adaptador_analista import metricas_historicas_por_activo

    composicion = portafolio.get("composicion") or {}
    total = tiempo_real.get("total_valor") or 0
    perfil = portafolio.get("perfil", "moderado")

    try:
        precios = prep.cargar_precios()
    except Exception as e:
        print(f"⚠️ No se pudo cargar precios para metricas reales por activo: {e}")
        precios = None

    tickers = [p["activo"] for p in tiempo_real["posiciones"]]
    motor = metricas_historicas_por_activo(tickers)

    filas = []
    for pos in tiempo_real["posiciones"]:
        tk = pos["activo"]
        # Estado derivado (nunca se guarda aparte): en_meta si sigue en la
        # composicion vigente; fuera_meta_con_posicion en cualquier otro caso
        # -- por definicion, si tiene posicion viva (tiempo_real["posiciones"]
        # ya solo trae vivas) y no esta en la meta, esta "fuera de meta con
        # posicion", sin importar si quedo formalmente registrado en
        # activos_fuera_meta (portafolios de antes de este cambio pueden
        # tener el caso sin ese registro -- se cae al mismo estado igual,
        # no se pierde el activo). "cerrado" nunca aparece aqui.
        estado = "en_meta" if tk in composicion else "fuera_meta_con_posicion"
        vol_real = dd_real = None
        if precios is not None and tk in precios.columns:
            try:
                serie = precios[tk].loc[pos["fecha_inicio"]:].dropna()
                if len(serie) >= 5:
                    ret = np.log(serie / serie.shift(1)).dropna()
                    if len(ret) >= 2:
                        vol_real = round(float(ret.std() * np.sqrt(252)) * 100, 2)

                # drawdown_real: consciente del costo promedio ponderado (como
                # rentabilidad_real), no solo el precio puro desde la primera
                # compra -- ver _trayectoria_rentabilidad_posicion.
                rent_posicion = _trayectoria_rentabilidad_posicion(
                    portafolio.get("aportes", []), portafolio.get("ventas", []),
                    tk, pos["fecha_inicio"], precios[tk],
                )
                if rent_posicion is not None and len(rent_posicion) >= 2:
                    indice = 1 + rent_posicion
                    dd_real = round(float((indice / indice.cummax() - 1).min()) * 100, 2)
            except Exception as e:
                print(f"⚠️ No se pudo calcular vol/drawdown real de {tk}: {e}")

        # Sugerencia de correccion en USD (Capa 1 del spec de rebalanceo,
        # 2026-08-14) -- SOLO para activos con peso meta (en_meta): un
        # fuera_meta_con_posicion no tiene contra que compararse. Calcula
        # contra el valor total ACTUAL del portafolio (peso objetivo es una
        # proporcion del capital de hoy, no del capital cuando se armo la
        # composicion) -- nunca fuerza nada, es solo informativo.
        peso_meta = composicion.get(tk)
        accion_sugerida = monto_sugerido_usd = fracciones_sugeridas = banda_pp = dentro_de_banda = None
        if peso_meta is not None and total > 0:
            valor_objetivo = peso_meta * total
            delta_usd = valor_objetivo - pos["valor_hoy"]
            delta_pp = abs(pos["valor_hoy"] / total * 100 - peso_meta * 100)
            banda_pp = round(_banda_tolerancia_peso(peso_meta, perfil), 2)
            dentro_de_banda = delta_pp <= banda_pp
            if abs(delta_usd) > 0.01:
                accion_sugerida = "comprar" if delta_usd > 0 else "vender"
                monto_sugerido_usd = round(abs(delta_usd), 2)
                if pos["precio_hoy"]:
                    fracciones_sugeridas = round(abs(delta_usd) / pos["precio_hoy"], 4)

        filas.append({
            "activo": tk,
            "estado": estado,
            "peso_meta": composicion.get(tk),
            "peso_real": round(pos["valor_hoy"] / total, 4) if total > 0 else None,
            "rentabilidad_real": pos["rentabilidad"],
            "volatilidad_real": vol_real,
            "drawdown_real": dd_real,
            "sortino_historico_motor": motor.get(tk, {}).get("sortino_historico"),
            "volatilidad_historica_motor": motor.get(tk, {}).get("volatilidad_historica"),
            "accion_sugerida": accion_sugerida,
            "monto_sugerido_usd": monto_sugerido_usd,
            "fracciones_sugeridas": fracciones_sugeridas,
            "banda_pp": banda_pp,
            "dentro_de_banda": dentro_de_banda,
        })
    return filas


# ── Capa 2: disparo de rebalanceo por METRICAS (no por pesos) ──
# Spec de Andrea 2026-08-14: la unica señal automatica legitima para sugerir
# ir al Analista es que el desempeño REAL del portafolio (volatilidad,
# drawdown) se haya desviado de forma persistente de lo que la proyeccion
# esperaba -- nunca la desviacion de pesos por si sola. "Persistente" se
# mide con un contador de dias consecutivos fuera de rango, actualizado una
# vez al dia por scheduler.py (_dia_fuera_de_rango_metricas) y leido aqui
# (evaluar_disparo_rebalanceo) por los endpoints.
UMBRAL_VOL_MULTIPLICADOR = 1.4    # punto medio del rango 1.3-1.5x del spec
DIAS_HABILES_HYSTERESIS = 4       # punto medio de 3-5 dias del spec


def _dia_fuera_de_rango_metricas(portafolio, pesos_reales, tiempo_real):
    """Compara metricas reales de HOY contra proyeccion_congelada (nunca
    viva -- ver Contexto del plan: correr el motor completo a diario en
    scheduler.py seria el primer trabajo pesado real de ese loop, y
    compararse contra un blanco que se mueve solo no captura bien
    "persistentemente fuera de lo esperado"). Devuelve:
      - None: no evaluable todavia (sin congelada guardada, o sin suficiente
        historial real -- MIN_MESES de metricas_reales_portafolio). No es
        "esta bien", es "no hay con que comparar".
      - False: evaluado, dentro de rango.
      - "volatilidad" | "drawdown": evaluado, fuera de rango, y por que."""
    congelada = (portafolio.get("proyeccion_al_aplicar") or {}).get("metricas")
    if not congelada:
        return None
    if not pesos_reales or not tiempo_real or not tiempo_real.get("posiciones"):
        return None

    from adaptador_analista import metricas_reales_portafolio, PERDIDA_POR_PERFIL

    fecha_min = min((p["fecha_inicio"] for p in tiempo_real["posiciones"]), default=None)
    if not fecha_min:
        return None
    real = metricas_reales_portafolio(pesos_reales, fecha_min, portafolio.get("historial", []))
    if not real:
        return None

    perfil = portafolio.get("perfil", "moderado")
    if congelada.get("volatilidad") and real["volatilidad"] > congelada["volatilidad"] * UMBRAL_VOL_MULTIPLICADOR:
        return "volatilidad"
    if real["max_drawdown"] < -PERDIDA_POR_PERFIL.get(perfil, 0.15) * 100:
        return "drawdown"
    return False


def evaluar_disparo_rebalanceo(portafolio):
    """Lee el contador que scheduler.py actualiza una vez al dia y decide si
    ya corresponde sugerir ir al Analista. O(1), no recalcula nada -- el
    trabajo pesado (metricas reales) ya lo hizo el scheduler."""
    estado = portafolio.get("rebalanceo_metricas") or {}
    dias = estado.get("dias_fuera_de_rango", 0)
    disparar = dias >= DIAS_HABILES_HYSTERESIS
    return {
        "disparar": disparar,
        "motivo": estado.get("motivo") if disparar else None,
        "dias_fuera_de_rango": dias,
    }


SIMULAR_PROPUESTA_TOOL = {
    "name": "simular_propuesta",
    "description": (
        "Corre el motor cuantitativo real (purga por Sortino, correlación, "
        "cobertura sectorial, HRP) sobre un conjunto de tickers candidatos y "
        "devuelve la composición y pesos REALES que resultarían. Úsala SIEMPRE "
        "antes de mencionar un ticker o porcentaje concreto al usuario — nunca "
        "inventes cifras de memoria."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "perfil": {
                "type": "string",
                "enum": ["conservador", "moderado", "agresivo"],
            },
            "inversion": {"type": "number"},
            "aporte_dca": {"type": "number"},
            "frecuencia_meses": {"type": "integer"},
            "horizonte": {"type": "integer"},
            "tickers_candidatos": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Tickers que el usuario está considerando incluir. Si se "
                    "omite, el motor usa su universo completo."
                ),
            },
            "activos_ancla": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "SOLO cuando el usuario confirmó explícitamente partir de su "
                    "portafolio actual para editarlo: tickers que YA tiene y deben "
                    "mantenerse en la propuesta pase lo que pase en la simulación "
                    "(el motor los ancla y busca en TODO el universo la mejor forma "
                    "de agregar/ajustar el resto alrededor de ellos). NUNCA uses "
                    "esto en una propuesta nueva."
                ),
            },
            "forzar_exacto": {
                "type": "boolean",
                "description": (
                    "true SOLO cuando el usuario, pese a una advertencia tuya, insiste "
                    "en ver las proyecciones de una lista específica y cerrada de "
                    "tickers (ej. dijiste que el motor sugiere 10 activos nuevos y el "
                    "usuario pide ver solo 4 en concreto + los que ya tiene). Con "
                    "true, usa 'activos_ancla' con ESA lista completa (los que ya "
                    "tiene + los nuevos que pidió) — el motor NO busca ni agrega nada "
                    "más allá de esos tickers, y ninguno de ellos se purga: la "
                    "simulación refleja EXACTAMENTE lo que el usuario pidió, para que "
                    "lo vea y decida con datos reales en vez de quedarse solo con tu "
                    "advertencia."
                ),
            },
        },
        "required": ["perfil", "inversion"],
    },
}


def _ejecutar_tool(nombre, input_):
    """Dispatch generico de tools para anthropic_chat. Hoy solo hay una tool,
    pero se deja la forma generica por si se agregan mas despues."""
    if nombre == "simular_propuesta":
        return _tool_simular_propuesta(input_)
    return {"error": f"Tool desconocida: {nombre}"}


# ── Tools de Atom (chat libre /api/bot) — Fase 4 del plan de asistente
# inmersivo: darle capacidad de ACTUAR (consultar datos puntuales, navegar),
# no solo describir lo que ya tiene en el contexto inicial del prompt. ──

CONSULTAR_POSICION_TOOL = {
    "name": "consultar_posicion",
    "description": (
        "Consulta el detalle exacto de la posición actual del usuario en un "
        "ticker específico (fracciones, precio de hoy, valor, ganancia, "
        "rentabilidad, fecha de inicio de la posición). Úsala cuando el "
        "usuario pregunte por un activo puntual en vez de repetir de memoria "
        "el resumen general que ya tienes en el contexto."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Símbolo bursátil, ej. 'NVDA'."},
        },
        "required": ["ticker"],
    },
}

CONSULTAR_SENAL_MONITOR_TOOL = {
    "name": "consultar_senal_monitor",
    "description": (
        "Consulta la señal técnica actual de Monitor para un ticker (ENTRAR/"
        "VIGILAR/NEUTRAL de compra, o si hay señal de venta activa, con RSI). "
        "Úsala cuando el usuario pregunte si es buen momento para comprar o "
        "vender algo puntual."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Símbolo bursátil, ej. 'NVDA'."},
        },
        "required": ["ticker"],
    },
}

NAVEGAR_DESTINOS = {
    "dashboard":    "",
    "analista":     "/analista",
    "seguimiento":  "/seguimiento",
    "monitor":      "/monitor",
    "config":       "/config",
}

NAVEGAR_TOOL = {
    "name": "navegar",
    "description": (
        "Lleva al usuario directamente a otra pantalla de la app, en vez de "
        "solo decirle a dónde ir. Úsala cuando el usuario pida explícitamente "
        "ir a algún lado (ej. 'llévame a Monitor', 'quiero ver Seguimiento') "
        "o cuando resuelva de forma natural lo que está pidiendo (ej. si pide "
        "cambiar su composición, navégalo al Analista después de explicarle "
        "por qué)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "destino": {
                "type": "string",
                "enum": list(NAVEGAR_DESTINOS.keys()),
                "description": "Pantalla destino dentro del portafolio actual.",
            },
        },
        "required": ["destino"],
    },
}

BOT_TOOLS = [CONSULTAR_POSICION_TOOL, CONSULTAR_SENAL_MONITOR_TOOL, NAVEGAR_TOOL]


def _tool_consultar_posicion(portafolio, input_):
    ticker = (input_.get("ticker") or "").strip().upper()
    tr = calcular_tiempo_real(portafolio)
    if not tr or not tr.get("posiciones"):
        return {"error": "Este portafolio todavía no tiene inversiones registradas."}
    for pos in tr["posiciones"]:
        if pos["activo"].upper() == ticker:
            return {
                "activo":         pos["activo"],
                "fracciones":     pos["fracciones"],
                "precio_hoy":     pos["precio_hoy"],
                "valor_hoy":      pos["valor_hoy"],
                "ganancia":       pos["ganancia"],
                "rentabilidad":   pos["rentabilidad"],
                "fecha_inicio":   pos.get("fecha_inicio"),
            }
    return {"error": f"El usuario no tiene una posición abierta en '{ticker}'."}


def _tool_consultar_senal_monitor(archivo, input_):
    """Lee los mismos archivos de estado que ya usa /api/precios-rt
    (datos/portafolios/monitor_<archivo> para señal en vivo, rangos_<archivo>
    como fallback precalculado del día si el mercado está cerrado) — no hay
    llamada nueva a Finnhub, es lectura del cache que el monitor ya escribe."""
    ticker = (input_.get("ticker") or "").strip().upper()
    ruta_monitor = os.path.join(DATOS_DIR, "portafolios", f"monitor_{archivo}")
    if os.path.exists(ruta_monitor):
        try:
            with open(ruta_monitor, "r", encoding="utf-8") as f:
                estado = json.load(f)
            r = estado.get("resultados_rt", {}).get(ticker)
            if r:
                return {
                    "fuente":         "en_vivo",
                    "senal_compra":   r.get("senal", "NEUTRAL"),
                    "senal_venta":    r.get("senal_venta", "NEUTRAL"),
                    "rsi":            r.get("rsi"),
                    "puede_entrar":   r.get("puede_entrar", False),
                    "puede_vender":   r.get("puede_vender", False),
                }
        except Exception:
            pass
    ruta_rangos = os.path.join(DATOS_DIR, "portafolios", f"rangos_{archivo}")
    if os.path.exists(ruta_rangos):
        try:
            with open(ruta_rangos, "r", encoding="utf-8") as f:
                rangos_data = json.load(f)
            r = rangos_data.get("rangos", {}).get(ticker)
            if r:
                return {
                    "fuente":        "rango_precalculado_del_dia",
                    "fecha":         rangos_data.get("fecha"),
                    "rsi":           r.get("rsi"),
                    "puede_entrar":  r.get("puede_entrar", False),
                    "puede_vigilar": r.get("puede_vigilar", False),
                    "puede_vender":  r.get("puede_vender", False),
                }
        except Exception:
            pass
    return {"error": f"Todavía no hay datos de Monitor para '{ticker}' (puede que no esté siendo vigilado)."}


def _tool_navegar(input_):
    destino = (input_.get("destino") or "").strip().lower()
    if destino not in NAVEGAR_DESTINOS:
        return {"error": f"Destino desconocido: '{destino}'. Usa uno de: {', '.join(NAVEGAR_DESTINOS)}."}
    return {"ok": True, "destino": destino}


def _ejecutar_tool_bot(portafolio, archivo, accion_capturada):
    """Dispatch de tools para /api/bot. `accion_capturada` es un dict mutable
    que el caller (api_bot) inspecciona DESPUES de que anthropic_chat termine
    su loop -- es el unico canal para que una tool (navegar) le diga algo
    estructurado al frontend, ya que anthropic_chat solo devuelve texto."""
    def ejecutar(nombre, input_):
        if nombre == "consultar_posicion":
            return _tool_consultar_posicion(portafolio, input_)
        if nombre == "consultar_senal_monitor":
            return _tool_consultar_senal_monitor(archivo, input_)
        if nombre == "navegar":
            resultado = _tool_navegar(input_)
            if resultado.get("ok"):
                accion_capturada["tipo"] = "navegar"
                accion_capturada["destino"] = resultado["destino"]
            return resultado
        return {"error": f"Tool desconocida: {nombre}"}
    return ejecutar


def _sistema_analista(portafolio, composicion, tiene_inv, motivo=None):
    """Construye el system prompt del analista. Único punto de verdad.

    motivo: opcional (ej. "rebalanceo") cuando el usuario llega desde otra
    parte de la app con un contexto especifico -- ver AvisoSeguimiento en el
    frontend. Se RECALCULA aqui mismo con datos reales, nunca se confia en
    lo que mande el cliente."""
    from recolector import ACTIVOS_POR_SECTOR

    motivo_txt = ""
    if motivo == "rebalanceo":
        tiempo_real = calcular_tiempo_real(portafolio)
        desviacion = calcular_desviacion_composicion(portafolio, tiempo_real)
        if desviacion.get("aplica") and desviacion.get("activos_desviados"):
            detalle = ", ".join(
                f"{t} ({'+' if v > 0 else ''}{v}pp vs meta)"
                for t, v in desviacion["activos_desviados"].items()
            )
            motivo_txt = (
                f"CONTEXTO DE ENTRADA: el usuario llega a esta conversación desde Seguimiento, "
                f"que detectó que la composición real de su portafolio se desvió de la meta "
                f"(desviación total: {desviacion['desviacion_total_pp']} puntos porcentuales). "
                f"Activos desviados: {detalle}. Reconoce esto DIRECTAMENTE en tu primer mensaje "
                f"(qué se desvió y por qué podría importar), no le preguntes qué quiere lograr "
                f"como si fuera una conversación nueva sin motivo.\n\n"
            )

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
            "Si elige opción 6: primero pregunta EXPLÍCITAMENTE, en un mensaje aparte, si quiere "
            f'partir de su portafolio actual ({", ".join(composicion.keys())}) y ajustar desde ahí '
            "(agregar/quitar activos mientras conserva el resto), o si prefiere una propuesta "
            "completamente nueva evaluando todo el universo desde cero. No lo asumas, pregúntalo.\n"
            'Si confirma partir de su base actual: llama simular_propuesta con "activos_ancla" = '
            "los tickers que confirmó mantener (todos los actuales, o un subconjunto si quiere "
            "soltar alguno) para ver la mejor forma real de sumar lo que pide sobre el universo "
            'completo. Luego genera el JSON final incluyendo ese mismo "activos_ancla" -- NO '
            'adivines pesos finales en "activos", el motor los recalcula.\n'
            'Ejemplo: {"accion":"analizar","perfil":"agresivo","inversion":2000000,'
            '"aporte_dca":200000,"frecuencia_meses":1,"horizonte":10,"es_nuevo":false,'
            '"activos_ancla":["WMT","VTI"]}\n'
            "Si prefiere empezar de cero: procede como con un portafolio nuevo (ver FLUJO A), "
            'con "activos" solo si hubo preferencias de tema/sector, sin "activos_ancla".'
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
        f"{motivo_txt}"
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
        f"- Tienes criterio: si algo no conviene al cliente, lo dices con datos antes de ejecutar. Pero "
        f"la advertencia INFORMA, no bloquea: si el usuario insiste después de escucharla, ofrécele "
        f"modelar exactamente lo que pide (con forzar_exacto, ver HERRAMIENTA simular_propuesta) para "
        f"que decida viendo las proyecciones reales, no dejes la conversación trabada en el desacuerdo.\n"
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
        f'Luego genera el JSON con los valores finales (actuales + cambios). Si el cambio NO toca la '
        f'composición (monto, DCA, frecuencia, perfil u horizonte), incluye "activos" con la composición '
        f'actual sin modificar, para no perderla. Si el cambio SÍ toca la composición, es la opción 6: '
        f"sigue esas instrucciones en su lugar (activos_ancla si confirmó partir de su base, nunca "
        f'pesos adivinados en "activos").\n\n'
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
        f"Cuando el usuario pida agregar/cambiar un activo después de una propuesta ya generada en esta "
        f"conversación, pregunta si quiere mantener esa composición como base o partir de cero. Si "
        f"mantiene la base, usa 'activos_ancla' con los tickers de esa propuesta que confirme conservar "
        f"(tomados del último mensaje 'Propuesta generada' del historial, NUNCA inventes tickers que no "
        f"estén ahí) tanto al llamar simular_propuesta como en el JSON final -- no adivines pesos a mano, "
        f"el motor los recalcula sobre el universo completo con esos tickers protegidos.\n\n"
        f"HERRAMIENTA simular_propuesta — USO OBLIGATORIO: nunca menciones un ticker o un porcentaje "
        f"final de una propuesta (en texto o en el JSON) sin haber llamado antes a la herramienta "
        f"simular_propuesta y usar EXACTAMENTE lo que devolvió esa llamada (pesos_reales, alfa, métricas). "
        f"No los inventes ni los redondees de memoria. Úsala también para responder preguntas hipotéticas "
        f"del usuario durante la conversación (ej. '¿y si agrego MSFT?', '¿qué pasa si quito XLK?'), no solo "
        f"al final. Si simular_propuesta excluyó alguno de los tickers candidatos, revisa 'motivos_exclusion' "
        f"en su respuesta y explícaselo al usuario con ese hecho concreto, en vez de especular. "
        f"Recuerda: 'activos_ancla' es SOLO para editar un portafolio existente sobre el universo completo "
        f"(el usuario confirmó mantener esos tickers); 'tickers_candidatos' restringe el universo a un tema "
        f"o categoría concreta para una propuesta nueva. No los mezcles ni confundas su propósito.\n"
        f"SI EL USUARIO INSISTE PESE A TU ADVERTENCIA: cuando ya le explicaste un riesgo (ej. el motor "
        f"sugiere sumar 10 activos nuevos y el usuario pide ver solo 4 específicos + los que ya tiene) y "
        f"aun así quiere ver esa composición concreta, NO le niegues la simulación ni insistas en la "
        f"advertencia — llama simular_propuesta con 'activos_ancla' = esa lista completa (actuales + "
        f"nuevos que pidió) y 'forzar_exacto'=true, para que el motor no busque nada de más y ninguno de "
        f"esos tickers se purgue: la respuesta refleja EXACTAMENTE lo que pidió, con datos reales, para "
        f"que decida él. Aplica lo mismo al emitir el JSON final si confirma que quiere aplicarla así.\n"
        f'El JSON de ejemplo embebido arriba en este prompt (con pesos como "0.265", "0.212") es SOLO un '
        f"ejemplo de FORMATO — no son cifras reales, nunca las repitas ni las imites como si lo fueran; el "
        f'campo "activos" que finalmente emitas debe reflejar (o ser compatible con) lo que devolvió '
        f"simular_propuesta, no el ejemplo.\n\n"
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


def generar_analisis_historico(historial, portafolio):
    """Genera el texto de análisis IA sobre la TRAYECTORIA del portafolio
    (tendencia, no foto del día de hoy). Mismo patrón que generar_analisis_trm,
    sin la parte de noticias (no aplica a un portafolio individual)."""
    if not historial or len(historial) < 2:
        return ''
    try:
        valores    = [r['resumen']['total_valor'] for r in historial]
        invertido  = [r['resumen']['total_invertido'] for r in historial]
        ganancia   = [r['resumen']['ganancia_total'] for r in historial]
        fechas     = [r['fecha'] for r in historial]

        valor_hoy    = valores[-1]
        n7  = min(7, len(valores))
        n30 = min(30, len(valores))

        # Igual que el frontend (calcularHitos en page.tsx): el cambio del
        # rango se mide sobre ganancia_total contra el invertido AL INICIO del
        # rango, no sobre total_valor -- total_valor sube con cada aporte
        # nuevo (DCA) aunque no haya rendimiento real, y eso inflaba el
        # "cambio en los ultimos N registros" que le llega al modelo.
        ganancia_7d, invertido_7d   = ganancia[-n7], invertido[-n7]
        ganancia_30d, invertido_30d = ganancia[-n30], invertido[-n30]
        cambio_7d  = ((ganancia[-1] - ganancia_7d) / invertido_7d * 100) if invertido_7d else 0
        cambio_30d = ((ganancia[-1] - ganancia_30d) / invertido_30d * 100) if invertido_30d else 0

        # Día a día (entre registros consecutivos guardados, puede haber huecos
        # si el scheduler no alcanzó a correr) para mejor/peor día y racha.
        # Sobre ganancia_total, no total_valor -- misma razon que arriba: un
        # dia de aporte nuevo no es un "mejor dia" de rendimiento real.
        deltas = [ganancia[i] - ganancia[i - 1] for i in range(1, len(ganancia))]
        mejor_i = max(range(len(deltas)), key=lambda i: deltas[i])
        peor_i  = min(range(len(deltas)), key=lambda i: deltas[i])
        mejor_dia, mejor_valor = fechas[mejor_i + 1], deltas[mejor_i]
        peor_dia, peor_valor   = fechas[peor_i + 1], deltas[peor_i]

        racha = 0
        for d in reversed(deltas):
            if d > 0:
                racha += 1
            else:
                break

        rentabilidad_hoy = historial[-1]['resumen']['rentabilidad_total']
        perfil = portafolio.get('perfil', 'moderado')
        nombre = portafolio.get('nombre', 'el portafolio')

        return anthropic_chat(
            [{'role': 'user', 'content':
              f'Eres analista de inversiones. Tienes el histórico real de valor de un portafolio '
              f'("{nombre}", perfil {perfil}) desde que se empezó a registrar.\n\n'
              f'DATOS:\n'
              f'- Días registrados: {len(historial)} (desde {fechas[0]})\n'
              f'- Invertido actual: ${invertido[-1]:,.0f} USD\n'
              f'- Valor real hoy: ${valor_hoy:,.0f} USD\n'
              f'- Rentabilidad total: {rentabilidad_hoy:+.2f}%\n'
              f'- Cambio en los últimos {n7} registros: {cambio_7d:+.2f}%\n'
              f'- Cambio en los últimos {n30} registros: {cambio_30d:+.2f}%\n'
              f'- Mejor día: {mejor_dia} ({mejor_valor:+,.0f} USD)\n'
              f'- Peor día: {peor_dia} ({peor_valor:+,.0f} USD)\n'
              f'- Racha actual: {racha} días consecutivos ganando\n\n'
              f'Escribe exactamente 3 oraciones, en este orden:\n'
              f'1. TENDENCIA: cómo se ha movido el valor real en el período registrado.\n'
              f'2. CONSISTENCIA: qué dice la racha y el mejor/peor día sobre qué tan volátil ha sido el camino.\n'
              f'3. LECTURA: qué tan alineado está esto con lo esperable para un perfil {perfil} (sin prometer nada a futuro).\n\n'
              f'Reglas: usa los números exactos. Sin frases genéricas. Sin asteriscos. Español directo.'}],
            system=(
                'Eres un analista de portafolios senior. Interpretas la trayectoria real de un portafolio '
                'con honestidad, sin exagerar buenos resultados ni alarmar por variaciones normales del '
                'mercado. Nunca prometes rendimientos futuros.'),
            max_tokens=350, temperature=0.2)
    except Exception as e:
        print(f"Error análisis histórico: {e}")
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
        bloqueo = bloquear_si_demo_portafolio(portafolio)
        if bloqueo:
            return bloqueo
        composicion = portafolio.get("composicion", {})
        tiene_inv = len(portafolio.get("aportes", [])) > 0
        motivo = data.get("motivo")

        sistema = _sistema_analista(portafolio, composicion, tiene_inv, motivo=motivo)

        resp = anthropic_chat(
            data.get("historial", []),
            system=sistema,
            max_tokens=600,
            temperature=0.5,
            tools=[SIMULAR_PROPUESTA_TOOL],
            tool_executor=_ejecutar_tool,
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
        freq = int(data.get("frecuencia_meses", 1) or 1)
        if freq < 1:
            freq = 1
        horizonte = int(data.get("horizonte", 10))
        if horizonte <= 0 or horizonte > 50:
            horizonte = 10

        portafolio = leer_portafolio(archivo)
        bloqueo = bloquear_si_demo_portafolio(portafolio)
        if bloqueo:
            return bloqueo
        tiene_inv = len(portafolio.get("aportes", [])) > 0

        # --- Tickers fijos (si el analista IA propuso activos concretos) ---
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
                and PATRON_TICKER.fullmatch(k)
            }
            if isinstance(raw_activos, dict) else {}
        )
        if raw_activos and not activos_propuestos:
            return jsonify({
                "ok": False,
                "error": 'El analista propuso categorías en vez de tickers reales '
                         '(ej. "Biotecnología" en vez de "IBB"). Pídele tickers concretos.',
            })

        # --- Activos ancla (edicion de un portafolio existente) ---
        raw_ancla = data.get("activos_ancla") or []
        activos_ancla = (
            [t for t in raw_ancla if isinstance(t, str) and PATRON_TICKER.fullmatch(t)]
            or None
        )
        # forzar_exacto=true: el usuario insistio en ver EXACTAMENTE esa lista
        # pese a una advertencia -- se restringe el universo a activos_ancla
        # (nadie mas compite) y ademas quedan protegidos de las purgas dentro
        # de ese universo chico, asi que ninguno de los tickers pedidos se
        # cae. Sin forzar_exacto, activos_ancla solo ancla sobre el universo
        # COMPLETO (el motor puede sumar mas alla de lo pedido).
        forzar_exacto = bool(data.get("forzar_exacto")) and bool(activos_ancla)
        tickers_fijos = (
            activos_ancla if forzar_exacto
            else (
                list(activos_propuestos.keys())
                if (activos_propuestos and not activos_ancla) else None
            )
        )

        # --- MOTOR NUEVO: hace todo (seleccion, pesos, perfil, proyecciones) ---
        resultado = generar_propuesta_completa(
            perfil=perfil,
            horizonte=horizonte,
            inversion=inversion,
            aporte_dca=aporte_dca,
            frecuencia_meses=freq,
            tickers_fijos=tickers_fijos,
            activos_ancla=activos_ancla,
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
        from adaptador_analista import recalcular_con_pesos

        bloqueo = bloquear_si_demo_portafolio(leer_portafolio(archivo))
        if bloqueo:
            return bloqueo

        data = request.get_json()
        pesos_raw = data.get("pesos", {})
        perfil = data.get("perfil", "agresivo")
        inversion = float(data.get("inversion", 1000000))
        aporte = float(data.get("aporte_dca", 0))
        freq = int(data.get("frecuencia_meses", 1) or 1)
        if freq < 1:
            freq = 1
        horizonte = int(data.get("horizonte", 10))

        if not isinstance(pesos_raw, dict) or not all(
            isinstance(k, str) and PATRON_TICKER.fullmatch(k)
            and isinstance(v, (int, float))
            for k, v in pesos_raw.items()
        ):
            return jsonify({
                "ok": False,
                "error": "Uno o más tickers o pesos no son válidos.",
            }), 400

        resultado = recalcular_con_pesos(
            pesos_usuario=pesos_raw,
            perfil=perfil,
            inversion=inversion,
            aporte_dca=aporte,
            frecuencia_meses=freq,
            horizonte=horizonte,
        )

        return jsonify(
            {
                "ok": True,
                "datos": resultado["datos"],
                "reporte": resultado["reporte_txt"],
                "nota_nuevos": resultado["nota_nuevos"],
            }
        )

    except Exception as e:
        print(f"❌ api_recalcular_proyecciones error: {e}")
        return jsonify({
            "ok": False,
            "error": "Ocurrió un error al procesar la solicitud.",
        })


def _calcular_proyeccion_para_guardar(pesos, perfil, inv, aporte, freq, horizonte):
    """Recalcula datos (metricas/proyecciones) sobre los pesos FINALES que se
    van a aplicar -- no se confia en ningun 'datos' que mande el cliente, que
    podria estar desactualizado si el usuario edito pesos despues de generar
    la propuesta original. Reutiliza recalcular_con_pesos (el mismo motor de
    /api/recalcular-proyecciones), nunca lanza excepcion hacia arriba."""
    try:
        from adaptador_analista import recalcular_con_pesos

        resultado = recalcular_con_pesos(pesos, perfil, inv, aporte, freq, horizonte)
        return resultado.get("datos")
    except Exception as e:
        print(f"⚠️ No se pudo calcular la proyección a guardar junto con la composición: {e}")
        return None


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
        horizonte = data.get("horizonte", 10)
        p = leer_portafolio(archivo)
        bloqueo = bloquear_si_demo_portafolio(p)
        if bloqueo:
            return bloqueo
        username = session.get("username")

        if not isinstance(pesos, dict) or not all(
            isinstance(k, str) and PATRON_TICKER.fullmatch(k)
            and isinstance(v, (int, float))
            for k, v in pesos.items()
        ):
            return jsonify({
                "ok": False,
                "error": "Uno o más tickers o pesos no son válidos.",
            }), 400

        if tipo == "reemplazar":
            if not pesos or abs(sum(pesos.values()) - 1.0) > 0.01:
                return jsonify({
                    "ok": False,
                    "error": "Los pesos deben sumar 100% (±1%) antes de aplicar la propuesta.",
                }), 400

            proyeccion = _calcular_proyeccion_para_guardar(pesos, perfil, inv, aporte, freq, horizonte)

            # Activos que salen de la meta pero el usuario sigue sosteniendo en
            # la practica -> pasan a "fuera de meta con posicion", no desaparecen.
            # Solo ocurre aqui (el usuario ACEPTO/aplico la propuesta) -- nunca
            # por un recalculo automatico de pesos.
            composicion_vieja = p.get("composicion", {})
            fuera_meta_nuevo = dict(p.get("activos_fuera_meta", {}))
            hoy_fm = datetime.now().strftime("%Y-%m-%d")
            for t in set(composicion_vieja) - set(pesos):
                if fracciones_disponibles(p, t) > 1e-9:
                    fuera_meta_nuevo[t] = {
                        "fecha_salida": hoy_fm,
                        "peso_anterior": composicion_vieja[t],
                    }
            for t in list(fuera_meta_nuevo):
                if t in pesos:  # reingreso a la meta -> ya no aplica
                    del fuera_meta_nuevo[t]

            guardar_composicion(archivo, pesos, proyeccion=proyeccion, activos_fuera_meta=fuera_meta_nuevo)
            # Resetear monitor automáticamente al cambiar composición
            ruta_monitor = os.path.join(DATOS_DIR, "portafolios", f"monitor_{archivo}")
            if os.path.exists(ruta_monitor):
                os.remove(ruta_monitor)
                print(f"🔄 Monitor reseteado automáticamente: {archivo}")
            ruta = os.path.join(DATOS_DIR, "portafolios", archivo)
            with _LOCK:
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
                _escribir(ruta, dp)
            return jsonify(
                {
                    "ok": True,
                    "mensaje": "Portafolio actualizado.",
                    "redirigir": f"/seguimiento/{archivo}",
                }
            )

        elif tipo == "nuevo":
            if not pesos or abs(sum(pesos.values()) - 1.0) > 0.01:
                return jsonify({
                    "ok": False,
                    "error": "Los pesos deben sumar 100% (±1%) antes de aplicar la propuesta.",
                }), 400

            base = f"{p['propietario']} {perfil.capitalize()} {datetime.now().strftime('%Y')}"
            nombre_n = base
            contador = 2
            while True:
                test = f"{nombre_n}-{contador}" if contador > 1 else nombre_n
                slug = _slug(test)
                if not os.path.exists(os.path.join(DATOS_DIR, "portafolios", f"{slug}.json")):
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
            proyeccion = _calcular_proyeccion_para_guardar(pesos, perfil, inv, aporte, freq, horizonte)
            guardar_composicion(nm, pesos, proyeccion=proyeccion)
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

        else:
            return jsonify({
                "ok": False,
                "error": f"Tipo de propuesta inválido: {tipo}",
            }), 400

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


def _construir_contexto_atom(p, incluir_navegar=True):
    """System prompt de Atom -- unico punto de verdad, usado tanto por
    /api/bot (chat web) como por el webhook de Telegram, para que ambos
    canales sean la MISMA mente y no dos prompts que se desincronizan con
    el tiempo. `incluir_navegar` se apaga en Telegram: no hay pantalla a la
    que navegar dentro de un chat."""
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
                f"https://news.google.com/rss/search?q={_url_quote(tk)}+stock&hl=es&gl=US&ceid=US:es",
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
    herramientas_txt = (
        f"- consultar_posicion / consultar_senal_monitor: úsalas para responder sobre un "
        f"activo puntual con datos exactos en vez de estimar de memoria el resumen de arriba.\n"
    )
    if incluir_navegar:
        herramientas_txt += (
            f"- navegar: úsala cuando el usuario pida ir a otra pantalla, o cuando sea la acción "
            f"natural para resolver lo que pide (ej. pide cambiar su composición → navégalo al "
            f"Analista después de explicarle por qué). No la uses si solo está preguntando algo "
            f"informativo sin pedir moverse."
        )
    return (
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
        f"- Máximo 4 párrafos. Sin asteriscos. Sin bullets. Español directo.\n\n"
        f"HERRAMIENTAS:\n{herramientas_txt}"
    )


@app.route("/api/bot/<archivo>", methods=["POST"])
def api_bot(archivo):
    if verificar_acceso(archivo):
        return jsonify({"respuesta": "No autorizado"})
    try:
        data = request.get_json()
        mensaje = data.get("mensaje", "")
        historial = data.get("historial") or [{"role": "user", "content": mensaje}]
        p = leer_portafolio(archivo)
        bloqueo = bloquear_si_demo_portafolio(p)
        if bloqueo:
            return bloqueo
        ctx = _construir_contexto_atom(p, incluir_navegar=True)
        accion_capturada = {}
        resp = anthropic_chat(
            historial,
            system=ctx,
            max_tokens=800,
            temperature=0.4,
            tools=BOT_TOOLS,
            tool_executor=_ejecutar_tool_bot(p, archivo, accion_capturada),
        )
        return jsonify({"respuesta": resp, "accion": accion_capturada or None})
    except Exception as e:
        print(f"❌ api_bot error: {e}")
        return jsonify({"respuesta": "Ocurrió un error al procesar la solicitud."})


@app.route("/api/admin/reset-password", methods=["POST"])
def api_reset_password():
    if not session.get("es_admin"):
        return jsonify({"ok": False, "error": "No autorizado"})
    data = request.get_json()
    username = data.get("username")
    ok = resetear_password(username)
    if ok:
        return jsonify(
            {"ok": True, "mensaje": f"Contraseña de {username} reseteada a: cambiar123"}
        )
    return jsonify(
        {"ok": False, "error": f"No se encontró el usuario {username}."}
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
    bloqueo = bloquear_si_demo_cuenta()
    if bloqueo:
        return bloqueo
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
            p = None
            nombre_port = archivo

        # Fail-closed: sin un portafolio valido en mano no se puede verificar
        # si es la cuenta demo, asi que no se procede a borrar. Esto cubre
        # tanto el error de lectura (except de arriba) como el caso en que
        # leer_portafolio no lanza pero igual devuelve falsy -- ningun camino
        # llega al borrado real sin pasar por bloquear_si_demo_portafolio.
        if p is None:
            return jsonify({"error": "No se pudo verificar el portafolio antes de eliminarlo."}), 500

        bloqueo = bloquear_si_demo_portafolio(p)
        if bloqueo:
            return bloqueo

        ruta = os.path.join(DATOS_DIR, "portafolios", archivo)
        ruta_monitor = os.path.join(DATOS_DIR, "portafolios", f"monitor_{archivo}")
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
                listo_path = os.path.join(DATOS_DIR, f"ticker_listo_{tk}.flag")

                def _marcar(estado):
                    with open(listo_path, "w") as f:
                        f.write(estado)

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
                        print(f"❌ Descarga vacía para {tk}")
                        _marcar("error")
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
                    _marcar("ok")
                except Exception as e:
                    print(f"❌ Error descargando histórico de {tk}: {e}")
                    _marcar("error")

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
            return jsonify({"listo": True, "exito": True})
    # Verificar flag
    flag = os.path.join(DATOS_DIR, f"ticker_listo_{ticker}.flag")
    listo = os.path.exists(flag)
    exito = True
    if listo:
        try:
            with open(flag, "r") as f:
                exito = f.read().strip() == "ok"
        except Exception as e:
            print(f"Could not read flag file: {e}")
        # Limpiar flag
        try:
            os.remove(flag)
        except Exception as e:
            print(f"Could not remove flag file: {e}")
    return jsonify({"listo": listo, "exito": exito})


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
    bloqueo = bloquear_si_demo_cuenta()
    if bloqueo:
        return bloqueo

    data = request.get_json()
    username = session["username"]
    campos = {}
    if "email" in data and data["email"]:
        campos["email"] = data["email"].strip()

    # chat_id anterior — para detectar si es una conexión nueva/distinta y
    # disparar el saludo de bienvenida de Telegram (ver más abajo).
    chat_id_anterior = ""
    if "telegram_chat_id" in data:
        u_actual = get_usuario(username)
        chat_id_anterior = (
            (u_actual.get("telegram_chat_id") or "").strip() if u_actual else ""
        )
        campos["telegram_chat_id"] = (data.get("telegram_chat_id") or "").strip()
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
        # ── Saludo automático de Telegram al conectar/cambiar el chat_id ──
        # Dispara cuando se guarda un telegram_chat_id nuevo o distinto al
        # que ya tenía el usuario (cubre la primera conexión y un cambio de
        # chat_id posterior). telegram_chat_id es un campo del USUARIO, no
        # de cada portafolio individual — un mismo usuario puede tener
        # varios portafolios con distinto monitoreo_activo, así que el
        # mensaje resume si AL MENOS UNO ya tiene el monitoreo activo en
        # vez de listar cada portafolio (mantiene el mensaje simple).
        nuevo_chat_id = campos.get("telegram_chat_id", "")
        if nuevo_chat_id and nuevo_chat_id != chat_id_anterior:
            try:
                from monitor import telegram

                portafolios_usuario = listar_portafolios_de_usuario(username)
                hay_monitoreo_activo = any(
                    p.get("monitoreo_activo") for p in portafolios_usuario
                )
                if hay_monitoreo_activo:
                    saludo = (
                        "👋 ¡Hola! Ya conecté tu Telegram y tu monitoreo ya está "
                        "activo. En cuanto hagamos la próxima ronda de análisis, "
                        "te aviso por aquí."
                    )
                else:
                    saludo = (
                        "👋 ¡Hola! Ya conecté tu Telegram. Activa el monitoreo de "
                        "tu portafolio para que te empiece a mandar alertas por "
                        "aquí."
                    )
                telegram(nuevo_chat_id, saludo)
            except Exception as e:
                print(f"⚠️ No se pudo enviar saludo de bienvenida por Telegram: {e}")
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
            portafolio_sin_datos = leer_portafolio(archivo) or {}
            return jsonify({
                "ok": False, "error": "Sin datos aún",
                "composicion": portafolio_sin_datos.get('composicion', {}),
                "tickers_con_posicion": sorted(set(
                    a['activo'] for a in portafolio_sin_datos.get('aportes', [])
                )),
                "monitoreo": portafolio_sin_datos.get('monitoreo', {}).get('activos', {}),
                "activos_fuera_meta": portafolio_sin_datos.get('activos_fuera_meta', {}),
            })

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
                "banda_inf": r.get("banda_inf", 0),
                "tendencia": r.get("tendencia", 0),
                "vol_ratio": r.get("vol_ratio", 0),
                "macd_hist": r.get("macd_hist", 0),
                "hist_subiendo": r.get("hist_subiendo", False),
                "score_base": r.get("score_base", 0),
                "puede_vigilar": r.get("puede_vigilar", False),
                "mercado_rt": mercado_rt,
                "timestamp": r.get("timestamp", ""),
                # ── Venta (nuevo) ──
                "banda_sup": r.get("banda_sup"),
                "rango_vender": r.get("rango_vender"),
                "puede_vender": r.get("puede_vender", False),
                "costo_promedio": r.get("costo_promedio"),
                "ganancia_pct": r.get("ganancia_pct"),
                "senal_venta": r.get("senal_venta", "NEUTRAL"),
                "monitorea_compra": r.get("monitorea_compra", False),
                "monitorea_venta": r.get("monitorea_venta", False),
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

        # Composicion/aportes/monitoreo -- el frontend arma con esto la
        # sugerencia "ya compraste, ¿desactivar compra?" y los chips de
        # activación por activo, sin pedir un endpoint aparte (ya se hace
        # polling a este cada 4s).
        portafolio_completo = leer_portafolio(archivo) or {}
        composicion = portafolio_completo.get('composicion', {})
        tickers_con_posicion = sorted(set(
            a['activo'] for a in portafolio_completo.get('aportes', [])
        ))
        monitoreo = portafolio_completo.get('monitoreo', {}).get('activos', {})
        activos_fuera_meta = portafolio_completo.get('activos_fuera_meta', {})

        return jsonify({
            'ok':              True,
            'precios':         precios,
            'mercado_abierto': mercado_rt,
            'ultimo_update':   estado.get('timestamp', ''),
            'rangos':          rangos_data.get('rangos', {}),
            'rangos_fecha':    rangos_data.get('fecha', ''),
            'macd_sin_confirmacion_total': estado.get('macd_sin_confirmacion_total', 0),
            'composicion':          composicion,
            'tickers_con_posicion': tickers_con_posicion,
            'monitoreo':            monitoreo,
            'activos_fuera_meta':   activos_fuera_meta,
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/ultima-actualizacion")
def api_ultima_actualizacion():
    try:
        mtime = os.path.getmtime(os.path.join(DATOS_DIR, "macro", "trm.parquet"))
        hora = datetime.fromtimestamp(mtime).strftime("%d %b %Y · %I:%M %p")
        return jsonify({"timestamp": hora})
    except Exception as e:
        print(f"Could not read TRM timestamp: {e}")
        return jsonify({"timestamp": "No disponible"})


# ============================================================
# WEBHOOK DE TELEGRAM
# ============================================================


def _responder_atom_telegram(chat_id, texto_usuario):
    """Rama de texto libre del webhook de Telegram -- antes cualquier mensaje
    que no fuera '/start' se ignoraba en silencio (ver el comentario viejo
    "Mensaje de texto (comandos futuros)"). Resuelve chat_id -> usuario ->
    portafolio activo y responde con la MISMA mente de Atom que ya usa
    /api/bot (_construir_contexto_atom) -- Telegram es un canal mas, no un
    asistente aparte.

    Simplificaciones deliberadas de este primer corte (alcance de Fase 4,
    documentadas en BITACORA.md):
    - Sin memoria entre mensajes de Telegram -- cada mensaje es una
      conversación de un solo turno (a diferencia del chat web, que sí
      arrastra historial vía useAtomChat).
    - Si el usuario tiene más de un portafolio activo, se usa el primero y
      se aclara cuál en la respuesta, en vez de preguntarle cuál por
      Telegram antes de responder (evita mantener estado de conversación
      entre mensajes, que habría sido una feature bastante más grande).
    - Sin la tool 'navegar' (no aplica -- no hay pantalla a la que navegar
      dentro de un chat de Telegram).
    """
    from monitor import telegram

    try:
        username = username_por_telegram_chat_id(chat_id)
        if not username:
            telegram(chat_id, "No encuentro tu cuenta conectada. Entra a tu perfil en la app y confirma tu Chat ID primero.")
            return
        portafolios = [pf for pf in listar_portafolios_de_usuario(username) if pf.get("activo")]
        if not portafolios:
            telegram(chat_id, "Todavía no tienes portafolios activos conectados.")
            return

        archivo = portafolios[0]["archivo"]
        prefijo = (
            f"(Sobre tu portafolio '{portafolios[0]['nombre']}' — tienes más de uno activo)\n\n"
            if len(portafolios) > 1 else ""
        )
        p = leer_portafolio(archivo)
        ctx = _construir_contexto_atom(p, incluir_navegar=False)
        resp = anthropic_chat(
            [{"role": "user", "content": texto_usuario}],
            system=ctx,
            max_tokens=600,
            temperature=0.4,
            tools=[CONSULTAR_POSICION_TOOL, CONSULTAR_SENAL_MONITOR_TOOL],
            tool_executor=_ejecutar_tool_bot(p, archivo, {}),
        )
        telegram(chat_id, prefijo + resp)
    except Exception as e:
        print(f"❌ Error respondiendo a Atom por Telegram: {e}")
        telegram(chat_id, "Tuve un problema respondiendo tu pregunta, intenta de nuevo.")


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

        # ── Mensaje de texto ────────────────────────────────────
        if "message" in data:
            msg = data["message"]
            chat_id = str(msg["chat"]["id"])
            texto_original = msg.get("text", "").strip()
            texto = texto_original.lower()

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
            elif texto_original:
                # Cualquier otro texto se trata como pregunta libre a Atom.
                _responder_atom_telegram(chat_id, texto_original)

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
    if username == "demo":
        return "Esta es una cuenta de demostración — acción no disponible."
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
    resetear_demo_si_aplica(username)          # ← NUEVO
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

def resetear_demo_si_aplica(username):
    """Si el usuario que acaba de loguear es 'demo', restaura su portafolio
    al estado original — evita que quede desconfigurado por visitantes anteriores."""
    if username == "demo":
        import shutil, os
        origen = "datos/portafolios/demo_template.json"
        destino = "datos/portafolios/demo.json"
        if os.path.exists(origen):
            shutil.copyfile(origen, destino)

def bloquear_si_demo_portafolio(portafolio):
    """403 si el portafolio pertenece a la cuenta demo. Usar en cualquier ruta
    que reciba <archivo> y modifique/borre algo de ese portafolio."""
    if portafolio.get("owner") == "demo":
        return jsonify({"error": "Esta es una cuenta de demostración — no se pueden guardar cambios."}), 403
    return None

def bloquear_si_demo_cuenta():
    """403 si la sesión activa es la cuenta demo. Usar en rutas que actúan
    sobre la cuenta misma, no sobre un portafolio (borrar cuenta, cambiar
    perfil, crear portafolios nuevos, reset de contraseña)."""
    if session.get("username") == "demo":
        return jsonify({"error": "Esta es una cuenta de demostración — acción no disponible."}), 403
    return None

@app.route("/demo", methods=["GET"])
def auto_login_demo():
    """Auto-login de un clic para la cuenta demo (link de correo, ej. para
    reclutadores) -- arma la sesion EXACTAMENTE igual que api_auth_login /
    api_auth_verify_pin (mismas 3 claves), porque _validar_sesion exige que
    session["fp"] coincida con el hash real del usuario o mata la sesion en
    el primer request siguiente. GET a proposito: tiene que funcionar con un
    solo clic desde un correo, sin formulario -- aceptable porque la cuenta
    demo ya no tiene nada mutable que proteger (ver bloquear_si_demo_*)."""
    u = get_usuario("demo")
    if not u:
        return "Demo no disponible por el momento.", 404

    session["username"] = u["username"]
    session["fp"] = huella_password_hash(u["password_hash"])
    session["es_admin"] = u.get("es_admin", False)
    session.permanent = True

    resetear_demo_si_aplica(u["username"])

    ip, dispositivo = _request_meta()
    registrar_actividad("login_demo", u["username"], detalle="Auto-login vía /demo", ip=ip, dispositivo=dispositivo)

    # Mismo destino al que el frontend navega tras un login normal exitoso
    # (frontend/src/app/login/page.tsx:56 -- router.push(`/portafolio/${archivo}`)).
    # No hay vista Flask que redirigir con url_for: es una ruta de Next.js: se
    # redirige por path plano, y el rewrite de /demo en next.config.ts hace
    # que la cookie de sesion quede en el dominio correcto (ver next.config.ts).
    return redirect("/portafolio/demo.json")

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
        resetear_demo_si_aplica(usuario["username"])
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

    bloqueo = bloquear_si_demo_cuenta()
    if bloqueo:
        return bloqueo

    try:
        data = request.get_json(silent=True) or {}
        nombre = (data.get("nombre") or "").strip()
        perfil = data.get("perfil", "agresivo")
        propietario = (data.get("propietario") or username).strip()
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
    except Exception as e:
        print(f"❌ api_portafolios POST error: {e}")
        return jsonify({"ok": False, "error": "No se pudo crear el portafolio."}), 400


@app.route("/api/dashboard/<archivo>")
def api_dashboard(archivo):
    username = session.get("username")
    if not username:
        return jsonify({"error": "No autorizado"}), 401

    portafolio = leer_portafolio(archivo)
    if not portafolio or portafolio.get("owner") != username:
        return jsonify({"error": "No encontrado"}), 404

    asegurar_caja_inicial(archivo)          
    portafolio = leer_portafolio(archivo)

    tiempo_real = calcular_tiempo_real(portafolio)
    macro = cargar_macro()

    # macro puede venir None (red caída, parquet corrupto, deploy fresco sin
    # recolector corrido aún). Inicializar aquí para degradar con gracia:
    # la respuesta incluye 'macro': null en vez de tumbar el endpoint con
    # NameError al referenciar macro_json sin definir.
    macro_json = None
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
            'monitoreo_activo': portafolio.get('monitoreo_activo', False),
        },
        'composicion': portafolio.get('composicion', {}),
        'tiempo_real': tiempo_real,
        'saldo_usd':   saldo_disponible(portafolio),
        'macro':       macro_json,
        'historico': portafolio.get('historial',[]),
        'desviacion_composicion': calcular_desviacion_composicion(portafolio, tiempo_real),
        'disparo_rebalanceo': evaluar_disparo_rebalanceo(portafolio),
    })

@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/auth/forgot-password", methods=["POST"])
def api_auth_forgot_password():
    email = ((request.get_json(silent=True) or {}).get("email") or "").strip()
    username_solicitado, _u = get_usuario_por_email(email)
    if username_solicitado == "demo":
        return jsonify({"error": "Esta es una cuenta de demostración — acción no disponible."}), 403
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
    bloqueo = bloquear_si_demo_portafolio(portafolio)
    if bloqueo:
        return bloqueo

    data = request.get_json(silent=True) or {}

    ruta = os.path.join(DATOS_DIR, "portafolios", archivo)

    mensajes = []

    with _LOCK:
        with open(ruta, "r", encoding="utf-8") as f:
            d = json.load(f)

        if "divisa" in data:
            divisa = (data.get("divisa") or "USD").strip().upper()
            if divisa not in ("USD", "EUR", "COP"):
                return jsonify({"error": "Divisa no válida"}), 400
            d["divisa"] = divisa
            mensajes.append(f"Divisa cambiada a {divisa}")

        if "nombre" in data:
            nombre = (data.get("nombre") or "").strip()
            if not nombre:
                return jsonify({"error": "El nombre no puede estar vacío"}), 400
            d["nombre"] = nombre
            mensajes.append("Nombre actualizado")

            # Sincronizar el nombre en el estado del monitor, si existe
            # Escritura atómica (.tmp + os.replace, vía _escribir) — evita
            # dejar el archivo de estado del monitor truncado/corrupto si el
            # proceso muere a mitad del json.dump.
            ruta_monitor = os.path.join(DATOS_DIR, "portafolios", f"monitor_{archivo}")
            if os.path.exists(ruta_monitor):
                try:
                    with _LOCK_MONITOR:
                        with open(ruta_monitor, "r", encoding="utf-8") as f:
                            estado = json.load(f)
                        estado["nombre_portafolio"] = nombre
                        _escribir(ruta_monitor, estado)
                except Exception:
                    pass

        _escribir(ruta, d)

    return jsonify(
        {
            "ok": True,
            "mensaje": " / ".join(mensajes) or "Sin cambios",
            "divisa": d.get("divisa", "USD"),
            "nombre": d.get("nombre", ""),
        }
    )


def _armar_aporte_desde_form(data, composicion, activos_fuera_meta=None):
    """Parsea, valida y calcula un aporte desde el body del form de seguimiento.
    Usa SIEMPRE la TRM oficial para el cálculo (trm_real es solo trazabilidad).
    Devuelve (aporte, None) si todo bien, o (None, (respuesta_error, status)).

    Valida contra composicion UNION activos_fuera_meta -- un ticker que salio
    de la meta pero el usuario sigue sosteniendo (aceptado via
    api_aplicar_propuesta) debe poder seguir recibiendo compras nuevas
    (promediar/aumentar posicion). Antes de este fix, comprar mas de un
    activo que ya no estaba en la meta vigente fallaba con "Ese activo no
    pertenece a este portafolio" aunque el propio formulario lo ofreciera
    como opcion ("agregar más")."""
    activo = data.get("activo", "").upper()
    universo_valido = {c.upper() for c in composicion} | {t.upper() for t in (activos_fuera_meta or {})}
    if activo not in universo_valido:
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

    # Comisión: 1% del monto USD si la compra es fraccionada; editable (override
    # desde el form). Sale del saldo pero NO entra al costo/valor de la posición.
    frac_entera = abs(fracciones - round(fracciones)) < 1e-9
    comision_raw = data.get("comision")
    if comision_raw not in (None, ""):
        comision = round(float(str(comision_raw).replace(",", ".")), 2)
        if comision < 0:
            return None, (jsonify({"error": "La comisión no puede ser negativa"}), 400)
    else:
        comision = 0.0 if frac_entera else round(monto_usd * 0.01, 2)

    precio_usd = round(monto_usd / fracciones, 4)
    try:
        trm_df = pd.read_parquet(os.path.join(DATOS_DIR, "macro", "trm.parquet"))
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
        "comision": comision,        
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
    asegurar_caja_inicial(archivo)  # crea depósito de apertura la 1ª vez    
    portafolio = leer_portafolio(archivo)
    composicion = portafolio.get("composicion", {})

    if request.method == "POST":
        bloqueo = bloquear_si_demo_portafolio(portafolio)
        if bloqueo:
            return bloqueo
        data = request.get_json(silent=True) or {}
        try:
            aporte, err = _armar_aporte_desde_form(
                data, composicion, portafolio.get("activos_fuera_meta", {})
            )
            if err:
                return err
            guardar_aporte(archivo, aporte)
            portafolio = leer_portafolio(archivo)
        except Exception as e:
            print(f"❌ api_seguimiento error: {e}")
            return jsonify({"error": "Ocurrió un error al procesar la solicitud."}), 400

    # GET (y respuesta tras POST): armar el estado completo
    aportes = portafolio.get("aportes", [])
    entrados = list(set(a["activo"] for a in aportes))
    pendientes = [a for a in composicion if a not in entrados]
    total_a = len(composicion)
    # Progreso intersectado contra la meta VIGENTE (misma formula que
    # calcular_desviacion_composicion) -- un ticker comprado que ya no esta
    # en la meta no cuenta como progreso. "entrados" en si (lista completa,
    # sin intersectar) se deja intacta abajo porque alimenta el selector de
    # "vender/agregar mas" del formulario, que si debe listar TODO lo que el
    # usuario posee, este o no en la meta actual.
    total_e = len(set(entrados) & set(composicion))
    pct = int(total_e / total_a * 100) if total_a > 0 else 0

    pendientes_data = [
        {
            "activo": a,
            "peso": composicion.get(a, 0),
            "precio_usd": precio_actual_usd(a) or 0,
        }
        for a in pendientes
    ]

    # --- Comparacion proyectado vs real (composicion + metricas) ---
    tiempo_real = calcular_tiempo_real(portafolio)
    pesos_reales = calcular_composicion_real(tiempo_real)
    por_activo = calcular_metricas_reales_por_activo(portafolio, tiempo_real)
    desviacion = calcular_desviacion_composicion(portafolio, tiempo_real)

    # --- Proyeccion CONGELADA: snapshot fijo del momento en que se aplico la
    # composicion vigente (guardado_al_aplicar). Sirve para auditar que tan
    # bien predijo el modelo -- nunca se recalcula. ---
    proyeccion_guardada = portafolio.get("proyeccion_al_aplicar") or {}
    proyeccion_congelada = (
        {**proyeccion_guardada["metricas"], "fecha": proyeccion_guardada.get("fecha")}
        if proyeccion_guardada.get("metricas") else None
    )

    perfil_p = portafolio.get("perfil", "moderado")
    inv_p = portafolio.get("inversion_inicial", 1000000)
    aporte_p = portafolio.get("aporte_dca", 0)
    freq_p = portafolio.get("frecuencia_meses", 1)
    horizonte_p = portafolio.get("horizonte", 10)

    def _viva(pesos):
        """Proyeccion VIVA: mismo motor, siempre recalculada bajo demanda
        (nunca se cachea) sobre los pesos que se le pasen -- ver plan de
        Seguimiento 2026-08-14."""
        if not pesos:
            return None
        r = _calcular_proyeccion_para_guardar(pesos, perfil_p, inv_p, aporte_p, freq_p, horizonte_p)
        return r["metricas"] if r and r.get("metricas") else None

    from adaptador_analista import metricas_reales_portafolio

    def _real(pesos, tickers_permitidos=None):
        """Metricas reales agregadas sobre un subconjunto de posiciones
        (tickers_permitidos=None -> todas). Renormaliza los pesos al
        subconjunto antes de pasarlos al motor."""
        if not pesos or not tiempo_real:
            return None
        sub = ({t: w for t, w in pesos.items() if t in tickers_permitidos}
               if tickers_permitidos is not None else dict(pesos))
        suma = sum(sub.values())
        if suma <= 0:
            return None
        sub = {t: w / suma for t, w in sub.items()}
        posiciones_sub = [p for p in tiempo_real["posiciones"] if p["activo"] in sub]
        fecha_min = min((p["fecha_inicio"] for p in posiciones_sub), default=None)
        if not fecha_min:
            return None
        return metricas_reales_portafolio(sub, fecha_min, historial=portafolio.get("historial", []))

    comparacion = {
        "composicion_meta": composicion,
        "composicion_real": pesos_reales,
        "por_activo": por_activo,
        "desviacion_composicion": desviacion,
        "disparo_rebalanceo": evaluar_disparo_rebalanceo(portafolio),
        # Panel "Portafolio objetivo": solo activos EN META vigente.
        "objetivo": {
            "proyeccion_congelada": proyeccion_congelada,
            "proyeccion_viva": _viva(composicion),
            "real": _real(pesos_reales, set(composicion)),
        },
        # Panel "Portafolio real": TODO lo que el usuario sostiene hoy,
        # incluidos los activos fuera de meta con posicion activa.
        "actual": {
            "proyeccion_viva": _viva(pesos_reales),
            "real": _real(pesos_reales),
        },
    }

    _macro = cargar_macro() or {}
    return jsonify(
        {
            "nombre": portafolio.get("nombre"),
            "divisa": portafolio.get("divisa", "USD"),
            "trm": _macro.get("trm", 0),
            "tasa_eur": obtener_tasa_usd_eur(),
            "depositos": portafolio.get("depositos", []),
            "saldo_usd": saldo_disponible(portafolio),
            "composicion": composicion,
            "progreso": {"entrados": total_e, "total": total_a, "pct": pct},
            "pendientes": pendientes_data,
            "entrados": entrados,
            "aportes": aportes,
            "ventas": portafolio.get("ventas", []),
            "realizado": realizado_por_ticker(portafolio),
            "comparacion": comparacion,
        }
    )


@app.route("/api/seguimiento/<archivo>/aporte/<aporte_id>", methods=["PUT", "DELETE"])
def api_seguimiento_aporte(archivo, aporte_id):
    if verificar_acceso(archivo):
        return jsonify({"error": "No autorizado"}), 401

    bloqueo = bloquear_si_demo_portafolio(leer_portafolio(archivo))
    if bloqueo:
        return bloqueo

    if request.method == "DELETE":
        if not eliminar_aporte(archivo, aporte_id):
            return jsonify({"error": "Aporte no encontrado"}), 404
        return jsonify({"ok": True})

    # PUT — editar: recalcula con la TRM oficial, igual que un registro.
    data = request.get_json(silent=True) or {}
    try:
        p_actual = leer_portafolio(archivo)
        composicion = p_actual.get("composicion", {})
        campos, err = _armar_aporte_desde_form(
            data, composicion, p_actual.get("activos_fuera_meta", {})
        )
        if err:
            return err
        if not editar_aporte(archivo, aporte_id, campos):
            return jsonify({"error": "Aporte no encontrado"}), 404
        return jsonify({"ok": True})
    except SaldoInsuficiente as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"❌ api_seguimiento_aporte error: {e}")
        return jsonify({"error": "Ocurrió un error al procesar la solicitud."}), 400

def _armar_deposito_desde_form(data):
    """Depósito en USD (lo que se añadió a la cuenta del broker).
    Devuelve (deposito, None) o (None, (err, status))."""
    fecha = data.get("fecha", datetime.now().strftime("%Y-%m-%d"))
    monto_usd = float(str(data.get("monto_usd", "0")).replace(",", "."))
    if monto_usd <= 0:
        return None, (jsonify({"error": "El monto en USD debe ser mayor a 0"}), 400)
    return {"fecha": fecha, "monto_usd": round(monto_usd, 2), "tipo": "deposito"}, None


@app.route("/api/depositos/<archivo>", methods=["POST"])
def api_depositos(archivo):
    if verificar_acceso(archivo):
        return jsonify({"error": "No autorizado"}), 401
    bloqueo = bloquear_si_demo_portafolio(leer_portafolio(archivo))
    if bloqueo:
        return bloqueo
    asegurar_caja_inicial(archivo)
    data = request.get_json(silent=True) or {}
    try:
        deposito, err = _armar_deposito_desde_form(data)
        if err:
            return err
        guardar_deposito(archivo, deposito)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 400


@app.route("/api/depositos/<archivo>/<deposito_id>", methods=["PUT", "DELETE"])
def api_depositos_uno(archivo, deposito_id):
    if verificar_acceso(archivo):
        return jsonify({"error": "No autorizado"}), 401
    bloqueo = bloquear_si_demo_portafolio(leer_portafolio(archivo))
    if bloqueo:
        return bloqueo
    try:
        if request.method == "DELETE":
            if not eliminar_deposito(archivo, deposito_id):
                return jsonify({"error": "Depósito no encontrado"}), 404
            return jsonify({"ok": True})
        # PUT
        data = request.get_json(silent=True) or {}
        deposito, err = _armar_deposito_desde_form(data)
        if err:
            return err
        if not editar_deposito(archivo, deposito_id, deposito):
            return jsonify({"error": "Depósito no encontrado"}), 404
        return jsonify({"ok": True})
    except SaldoInsuficiente as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 400


def _armar_venta_desde_form(data, portafolio, excluir_venta_id=None):
    """Parsea/valida/computa una venta. Costo promedio calculado sobre el POOL
    VIVO del ticker (_pool_posicion_viva: aportes menos ventas previas ya
    registradas, en orden cronologico, no la suma de TODOS los aportes
    historicos sin importar cuanto ya se vendio -- ese era el bug que diluia
    el costo base al vender todo y volver a comprar). TRM oficial del día;
    producto neto de comisión → caja; ganancia realizada = producto_COP
    (antes de comisión) − costo base.

    excluir_venta_id: al EDITAR una venta ya existente, esa misma venta sigue
    en portafolio["ventas"] -- se excluye del pool para no restarla dos veces
    (una vez como "ya vendida" y otra como la operacion que se esta armando).
    Devuelve (venta, None) o (None, (err, status))."""
    activo = data.get("activo", "").upper()
    fecha = data.get("fecha", datetime.now().strftime("%Y-%m-%d"))
    fracciones = float(str(data.get("fracciones", "0")).replace(",", "."))
    monto_usd = float(str(data.get("monto_usd", "0")).replace(",", "."))
    if fracciones <= 0 or monto_usd <= 0:
        return None, (jsonify({"error": "Las fracciones y el monto de la venta deben ser mayores a 0"}), 400)
    precio_venta = round(monto_usd / fracciones, 4)

    frac_entera = abs(fracciones - round(fracciones)) < 1e-9
    comision_raw = data.get("comision")
    if comision_raw not in (None, ""):
        comision = round(float(str(comision_raw).replace(",", ".")), 2)
        if comision < 0:
            return None, (jsonify({"error": "La comisión no puede ser negativa"}), 400)
    else:
        comision = 0.0 if frac_entera else round(monto_usd * 0.01, 2)

    ventas_previas = [
        v for v in portafolio.get("ventas", []) if v.get("id") != excluir_venta_id
    ]
    pool = _pool_posicion_viva(portafolio.get("aportes", []), ventas_previas, activo)
    if pool["frac"] <= 1e-9:
        return None, (jsonify({"error": f"No tienes posición en {activo}"}), 400)
    costo_base_cop = round(((pool["cop"] + pool["comision_cop"]) / pool["frac"]) * fracciones, 0)

    try:
        trm_df = pd.read_parquet("datos/macro/trm.parquet")
        idx = trm_df.index.get_indexer([pd.to_datetime(fecha)], method="nearest")[0]
        trm_dia = float(trm_df["TRM"].iloc[idx])
    except Exception:
        return None, (jsonify({
            "error": "No hay TRM oficial disponible para esa fecha. "
                     "Intenta más tarde o revisa la fecha."
        }), 400)

    return {
        "fecha": fecha,
        "activo": activo,
        "fracciones": round(fracciones, 8),
        "precio_venta_usd": precio_venta,
        "comision": comision,
        "proceeds_usd": round(monto_usd - comision, 2),
        "trm_dia": trm_dia,
        "costo_base_cop": costo_base_cop,
        "ganancia_realizada_cop": round((monto_usd - comision) * trm_dia - costo_base_cop, 0),
        "tipo": "venta",
    }, None


@app.route("/api/ventas/<archivo>", methods=["POST"])
def api_ventas(archivo):
    if verificar_acceso(archivo):
        return jsonify({"error": "No autorizado"}), 401
    bloqueo = bloquear_si_demo_portafolio(leer_portafolio(archivo))
    if bloqueo:
        return bloqueo
    asegurar_caja_inicial(archivo)
    data = request.get_json(silent=True) or {}
    try:
        venta, err = _armar_venta_desde_form(data, leer_portafolio(archivo))
        if err:
            return err
        guardar_venta(archivo, venta)
        return jsonify({"ok": True})
    except (PosicionInsuficiente, SaldoInsuficiente) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"}), 400


@app.route("/api/ventas/<archivo>/<venta_id>", methods=["PUT", "DELETE"])
def api_ventas_una(archivo, venta_id):
    if verificar_acceso(archivo):
        return jsonify({"error": "No autorizado"}), 401
    bloqueo = bloquear_si_demo_portafolio(leer_portafolio(archivo))
    if bloqueo:
        return bloqueo
    try:
        if request.method == "DELETE":
            if not eliminar_venta(archivo, venta_id):
                return jsonify({"error": "Venta no encontrada"}), 404
            return jsonify({"ok": True})
        # PUT
        data = request.get_json(silent=True) or {}
        venta, err = _armar_venta_desde_form(data, leer_portafolio(archivo), excluir_venta_id=venta_id)
        if err:
            return err
        if not editar_venta(archivo, venta_id, venta):
            return jsonify({"error": "Venta no encontrada"}), 404
        return jsonify({"ok": True})
    except (PosicionInsuficiente, SaldoInsuficiente) as e:
        return jsonify({"error": str(e)}), 400
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


@app.route('/api/historico-analisis/<archivo>')
def api_historico_analisis(archivo):
    username = session.get('username')
    if not username:
        return jsonify({'error': 'No autorizado'}), 401

    portafolio = leer_portafolio(archivo)
    if not portafolio or portafolio.get('owner') != username:
        return jsonify({'error': 'No encontrado'}), 404

    hoy = datetime.now().strftime("%Y-%m-%d")
    cache = portafolio.get('analisis_historico') or {}

    # Cuenta demo: nunca regenerar (llamada real y de pago a Anthropic) ni
    # escribir en disco -- sirve el texto ya cacheado tal cual esté, sin
    # importar si la fecha del caché es de hoy.
    if portafolio.get('owner') == 'demo':
        return jsonify({'analisis': cache.get('texto'), 'fecha': cache.get('fecha'), 'cacheado': True})

    if cache.get('fecha') == hoy and cache.get('texto'):
        return jsonify({'analisis': cache['texto'], 'fecha': hoy, 'cacheado': True})

    analisis = generar_analisis_historico(portafolio.get('historial', []), portafolio)
    if analisis:
        guardar_analisis_historico(archivo, analisis, hoy)

    return jsonify({'analisis': analisis, 'fecha': hoy, 'cacheado': False})


@app.route('/api/portafolios/<archivo>/activar', methods=['POST'])
def api_activar_portafolio_json(archivo):
    if verificar_acceso(archivo):
        return jsonify({'ok': False, 'error': 'No autorizado'}), 401
    try:
        # "Activar" desde Config equivale al toggle maestro de Monitor:
        # compra=True para toda la composición, venta=True para lo que ya
        # tiene posición. Sin exclusividad -- varios portafolios pueden
        # estar monitoreados a la vez (decisión de esta ampliación).
        portafolio = leer_portafolio(archivo)
        bloqueo = bloquear_si_demo_portafolio(portafolio)
        if bloqueo:
            return bloqueo
        composicion = portafolio.get('composicion', {})
        tickers_con_posicion = set(a['activo'] for a in portafolio.get('aportes', []))

        set_monitoreo(archivo, list(composicion.keys()), 'compra', True)
        set_monitoreo(archivo, [t for t in composicion if t in tickers_con_posicion], 'venta', True)

        d = leer_portafolio(archivo)

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
        portafolio = leer_portafolio(archivo)
        bloqueo = bloquear_si_demo_portafolio(portafolio)
        if bloqueo:
            return bloqueo
        composicion = portafolio.get('composicion', {})
        set_monitoreo(archivo, list(composicion.keys()), 'compra', False)
        set_monitoreo(archivo, list(composicion.keys()), 'venta', False)
        return jsonify({'ok': True, 'activo': False})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/monitor/<archivo>/toggle', methods=['POST'])
def api_monitor_toggle(archivo):
    """Activa/desactiva monitoreo de compra o venta, a nivel de portafolio
    completo (ambito='portafolio') o de un activo puntual (ambito='activo').
    No excluyente: un activo puede tener compra Y venta en True a la vez."""
    if verificar_acceso(archivo):
        return jsonify({'error': 'No autorizado'}), 401

    data = request.get_json(silent=True) or {}
    tipo = data.get('tipo')
    valor = bool(data.get('valor'))
    activo = data.get('activo')
    ambito = data.get('ambito') or ('activo' if activo else 'portafolio')

    if tipo not in ('compra', 'venta'):
        return jsonify({'error': "tipo debe ser 'compra' o 'venta'"}), 400

    portafolio = leer_portafolio(archivo)
    if not portafolio:
        return jsonify({'error': 'No encontrado'}), 404
    composicion = portafolio.get('composicion', {})
    activos_fuera_meta = portafolio.get('activos_fuera_meta', {})
    tickers_con_posicion = set(a['activo'] for a in portafolio.get('aportes', []))

    if ambito == 'activo':
        # Tambien se acepta un ticker "fuera de meta con posicion" (salio de
        # la composicion vigente pero el usuario lo sigue teniendo, ver
        # api_aplicar_propuesta) -- antes solo se podia togglear compra/venta
        # de tickers en la meta actual.
        if not activo or (activo not in composicion and activo not in activos_fuera_meta):
            return jsonify({'error': 'Ese activo no es parte de la composición'}), 404
        if tipo == 'venta' and valor and activo not in tickers_con_posicion:
            return jsonify({'error': 'No se puede monitorear venta de un activo sin posición'}), 400
        tickers_objetivo = [activo]
    else:
        if tipo == 'compra':
            tickers_objetivo = list(composicion.keys())
        else:
            # Acción masiva de venta: se filtra en silencio a los tickers
            # con posición -- no es un error pedir "venta para todos" desde
            # el toggle maestro aunque algunos no tengan posición todavía.
            tickers_objetivo = [t for t in composicion if t in tickers_con_posicion]

    monitoreo = set_monitoreo(archivo, tickers_objetivo, tipo, valor)
    return jsonify({'ok': True, 'monitoreo': monitoreo})

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
