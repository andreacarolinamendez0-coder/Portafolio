import yfinance as yf
import pandas as pd
import requests
import re
import io
import os
from datetime import datetime, timedelta
import time

# ============================================================
# RUTAS ABSOLUTAS — funciona igual en local y en Railway
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATOS_DIR = os.path.join(BASE_DIR, "datos")
UA = {"User-Agent": "Mozilla/5.0"}

CARPETA_PRECIOS = os.path.join(DATOS_DIR, "precios")
CARPETA_MACRO = os.path.join(DATOS_DIR, "macro")
CARPETA_LOGS = os.path.join(DATOS_DIR, "Logs")

# ============================================================
# CONFIGURACIÓN — activos
# ============================================================

CRIPTO = ["BTC-USD", "ETH-USD", "SOL-USD"]

ACTIVOS_POR_SECTOR = {
    "Technology": ["AAPL", "MSFT", "GOOGL", "NVDA", "AVGO"],
    "Communication Services": ["META", "NFLX", "DIS", "TMUS", "CMCSA", "VZ"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW"],
    "Consumer Defensive": ["WMT", "KO", "PG", "COST", "PEP", "CL"],
    "Financial Services": ["JPM", "V", "MA", "BAC", "WFC", "GS"],
    "Healthcare": ["LLY", "JNJ", "UNH", "ABBV"],
    "Industrials": ["CAT", "BA", "GE", "HON", "LMT", "DE"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "PSX", "OXY"],
    "Utilities": ["NEE", "DUK", "SO", "AEP", "D"],
    "Real Estate": ["PLD", "AMT", "EQIX", "O"],
    "Basic Materials": ["LIN", "FCX", "NEM", "SHW", "APD", "ECL"],
}

ETFS = {
    "US Broad": ["VOO", "VTI", "SPY", "QQQ", "IWM", "DIA"],
    "Sectoriales": [
        "XLK",
        "XLF",
        "XLE",
        "XLV",
        "XLI",
        "XLP",
        "XLY",
        "XLU",
        "XLB",
        "XLRE",
        "XLC",
    ],
    "Bonos": ["BND", "AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP"],
    "Internacional": ["VEA", "VWO", "EFA", "EEM", "VXUS"],
    "Commodities": ["GLD", "GLDM", "SLV", "DBC"],
    "Dividendo": ["SCHD", "VIG", "VYM", "DGRO"],
    "REITs": ["VNQ"],
}

# Para cuando el usuario restringe el universo a un sector especifico (ej.
# "solo tecnologia"): un ETF sectorial SI cuenta como la misma categoria que
# las acciones de ese sector, asi que se remapea a su sector GICS equivalente.
# NO se usa en TICKER_SECTOR (abajo) -- ese debe seguir con la subcategoria de
# vehiculo para que cobertura_por_sector() los trate como cupos separados en
# el caso general no restringido.
ETF_SECTOR_EQUIVALENTE = {
    "XLK": "Technology", "XLF": "Financial Services", "XLE": "Energy",
    "XLV": "Healthcare", "XLI": "Industrials", "XLP": "Consumer Defensive",
    "XLY": "Consumer Cyclical", "XLU": "Utilities", "XLB": "Basic Materials",
    "XLRE": "Real Estate", "XLC": "Communication Services",
    "VNQ": "Real Estate",  # REIT, mismo sector que XLRE aunque vive en "REITs"
}

TODOS_LOS_ETFS = sorted(set(t for lst in ETFS.values() for t in lst))

TICKER_SECTOR = {t: sector for sector, lst in ACTIVOS_POR_SECTOR.items() for t in lst}
# Cada ETF hereda el nombre de su SUBCATEGORIA (la clave de ETFS), no el
# string generico "ETF". Con "ETF" unico, motor_seleccion.cobertura_por_sector()
# solo dejaba pasar UN ETF de los 36 (GLD, SHY, VEA, etc. competian por el
# mismo cupo), dejando el portafolio final sin bonos, oro/commodities ni
# exposicion internacional.
TICKER_SECTOR.update({t: sector for sector, lst in ETFS.items() for t in lst})
TICKER_SECTOR.update({t: "Crypto" for t in CRIPTO})

ACTIVOS = sorted(set(TICKER_SECTOR.keys()))

# Umbral de días de historia para considerar un ticker "ya establecido".
# Debajo de esto se trata como nuevo y se le baja historia completa.
UMBRAL_HISTORIA_SUFICIENTE = 200


def _esta_fresco(archivo, dias=1):
    if not os.path.exists(archivo):
        return False
    edad = datetime.now() - datetime.fromtimestamp(os.path.getmtime(archivo))
    return edad.days < dias



# ============================================================
# API DE ESTADISTICAS DEL BANCO DE LA REPUBLICA
# ============================================================
# Portal nuevo de Banrep. Devuelve la serie COMPLETA como pares
# [timestamp_ms, valor] en SERIES[0]["data"], mas metadata.
# Reemplaza el scraping de HTML con regex, que era indefendible.
#
# Para encontrar el idMenu de otra serie:
#   1. https://suameca.banrep.gov.co/estadisticas-economicas/catalogo
#   2. Click en la serie que quieras
#   3. La URL queda .../informacionSerie/{ID}/nombre_de_la_serie
#   4. Ese {ID} es el idMenu

BANREP_API = (
    "https://suameca.banrep.gov.co/estadisticas-economicas-back/rest"
    "/estadisticaEconomicaRestService/consultaMenuXId"
)

# El API exige Referer/Origin: es el backend interno del portal y solo responde
# a peticiones que parezcan venir de su propio frontend.
# OJO: si faltan, NO devuelve 403 - devuelve 200 con el cuerpo VACIO. Por eso
# raise_for_status() no sirve para detectar el fallo; hay que revisar el cuerpo.
BANREP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://suameca.banrep.gov.co/estadisticas-economicas/",
    "Origin": "https://suameca.banrep.gov.co",
}

# Solo estas fuentes se consideran dato real y quedan protegidas.
# 'desconocida' (esquema viejo) y 'fallback' NO estan aqui a proposito.
FUENTES_CONFIABLES = {
    "banrep_api",
    "banco_mundial_anual",
    "fred",
    "treasury",
    "datos_gov_co",
}

ID_TASA_POLITICA = 59      # Tasa de politica monetaria, diaria, desde 1998-02-13
ID_INFLACION_TOTAL = None  # <-- PENDIENTE: buscar en el catalogo y poner el numero

# Rangos de sanidad. Si el dato cae fuera, es basura -> se rechaza.
# (La tasa de Banrep llego a 27% en 1998, por eso el techo es alto.)
RANGO_TASA_BANREP = (0.0, 40.0)
RANGO_INFLACION_COL = (-5.0, 60.0)


def _banrep_serie(id_menu: int, timeout: int = 20):
    """Descarga una serie completa del API de Banrep.

    Devuelve (DataFrame con indice Fecha y columna 'valor', metadata dict).
    Los timestamps vienen en milisegundos, a medianoche hora Bogota (UTC-5).
    """
    r = requests.get(
        BANREP_API, params={"idMenu": id_menu}, headers=BANREP_HEADERS, timeout=timeout
    )
    r.raise_for_status()

    # El API responde 200 con cuerpo vacio cuando rechaza la peticion (p.ej. si
    # faltan Referer/Origin). Hay que detectarlo a mano: el status no delata nada.
    if not r.text.strip():
        raise ValueError(
            f"El API devolvio 200 con cuerpo VACIO para idMenu={id_menu}. "
            "Suele significar que rechazo las cabeceras (Referer/Origin)."
        )

    js = r.json()
    series = js.get("SERIES") or []
    if not series:
        raise ValueError(f"El API no devolvio SERIES para idMenu={id_menu}")

    s = series[0]
    datos = s.get("data") or []
    if not datos:
        raise ValueError(f"La serie {id_menu} vino sin datos")

    df = pd.DataFrame(datos, columns=["ts", "valor"])
    df["Fecha"] = (
        pd.to_datetime(df["ts"], unit="ms", utc=True)
        .dt.tz_convert("America/Bogota")
        .dt.normalize()
        .dt.tz_localize(None)
    )
    df = df.set_index("Fecha")[["valor"]].sort_index()
    df = df[~df.index.duplicated(keep="last")].dropna()

    meta = {
        "nombre": s.get("nombre"),
        "unidad": s.get("unidad"),
        "periodicidad": s.get("descripcionPeriodicidad"),
        "fuente": s.get("fuente"),
        "ultimo_cargue": s.get("fechaUltimoCargue"),
        "ultimo_valor": s.get("valor"),
        "ultima_fecha": s.get("fecha"),
    }
    return df, meta


def _guardar_macro(df_nuevo, archivo, columna, fuente, rango):
    """Guarda una serie macro con trazabilidad y validacion.

    Reglas:
      - Cada fila lleva columna 'fuente' -> nunca se confunde dato real con fallback.
      - Se valida el rango. Fuera de rango = basura, se rechaza.
      - El indice es la FECHA DEL DATO, no la fecha de descarga.
      - Un fallback NUNCA pisa un dato real ya guardado.
    """
    lo, hi = rango
    fuera = df_nuevo[(df_nuevo[columna] < lo) | (df_nuevo[columna] > hi)]
    if len(fuera) > 0:
        registrar(
            f"AVISO: {len(fuera)} valores de {columna} fuera del rango {rango} - se descartan",
            "AVISO",
        )
        df_nuevo = df_nuevo[(df_nuevo[columna] >= lo) & (df_nuevo[columna] <= hi)]

    if df_nuevo.empty:
        registrar(f"Nada valido que guardar en {os.path.basename(archivo)}", "ERROR")
        return False

    df_nuevo = df_nuevo.copy()
    df_nuevo["fuente"] = fuente

    if os.path.exists(archivo):
        try:
            df_viejo = pd.read_parquet(archivo)

            # Esquema viejo (sin columna 'fuente'): indice = hora de descarga con
            # microsegundos, filas NaN, sin trazabilidad. Es basura -> se descarta.
            # No se protege: proteger datos malos es peor que no proteger nada.
            if "fuente" not in df_viejo.columns:
                registrar(
                    f"{os.path.basename(archivo)} viene del esquema viejo "
                    f"(sin columna 'fuente') - lo descarto y reescribo.",
                    "AVISO",
                )
            else:
                if fuente == "fallback":
                    # Un fallback jamas pisa datos de una fuente confiable.
                    reales = df_viejo[df_viejo["fuente"].isin(FUENTES_CONFIABLES)]
                    if not reales.empty:
                        registrar(
                            "Ya hay datos de fuente confiable - el fallback NO los pisa.",
                            "AVISO",
                        )
                        return False

                df_nuevo = df_nuevo.combine_first(df_viejo)
                # combine_first deja NaN en 'fuente' de las filas nuevas
                df_nuevo.loc[df_nuevo["fuente"].isna(), "fuente"] = fuente
        except Exception as e:
            registrar(f"No pude leer {archivo} ({e}) - lo reescribo", "AVISO")

    df_nuevo.sort_index(inplace=True)
    df_nuevo.to_parquet(archivo)
    return True


# ============================================================
# UTILIDADES
# ============================================================


def crear_carpetas():
    for carpeta in [
        CARPETA_PRECIOS,
        CARPETA_MACRO,
        CARPETA_LOGS,
        os.path.join(DATOS_DIR, "portafolios"),
        os.path.join(DATOS_DIR, "Reportes"),
        os.path.join(DATOS_DIR, "seguimiento"),
        os.path.join(DATOS_DIR, "historico"),
    ]:
        os.makedirs(carpeta, exist_ok=True)


def registrar(mensaje, tipo="INFO"):
    hoy = datetime.now().strftime("%Y-%m-%d")
    hora = datetime.now().strftime("%H:%M:%S")
    linea = f"[{hora}][{tipo}]{mensaje}\n"
    print(linea.strip())
    try:
        with open(
            os.path.join(CARPETA_LOGS, f"Log_{hoy}.txt"), "a", encoding="utf-8"
        ) as f:
            f.write(linea)
    except Exception:
        pass


# ============================================================
# RECOLECTOR 1 — PRECIOS DE ACCIONES
# ============================================================


def _descargar_lote(tickers, inicio, fin, chunk=20, pausa=8, reintentos=2):
    """Descarga una lista de tickers en lotes pequenos con pausa entre ellos.

    Yahoo Finance aplica rate limiting cuando se piden muchos tickers a la vez.
    Sintoma: tickers validos aparecen como "possibly delisted". Solucion: lotes
    mas chicos (20) y pausa mas larga (8s). Reintenta los fallidos una vez.

    chunk=20  : Yahoo aguanta bien lotes de 20; con 80 corta al azar.
    pausa=8   : 2s no es suficiente entre lotes grandes.
    reintentos: si un ticker falla en el lote, se reintenta solo.
    """
    partes = []
    fallidos = []

    for i in range(0, len(tickers), chunk):
        lote = tickers[i : i + chunk]
        try:
            df = yf.download(
                lote, start=inicio, end=fin, auto_adjust=True, progress=False
            )["Close"]
            if isinstance(df, pd.Series):
                df = df.to_frame(lote[0])
            # detectar cuales fallaron dentro del lote
            vacios = [t for t in lote if t not in df.columns or df[t].notna().sum() == 0]
            if vacios:
                fallidos.extend(vacios)
            partes.append(df)
        except Exception as e:
            registrar(f"Lote fallo ({lote[:3]}...): {e}", "ERROR")
            fallidos.extend(lote)
        time.sleep(pausa)

    # Reintentar fallidos uno por uno
    if fallidos and reintentos > 0:
        registrar(f"Reintentando {len(fallidos)} tickers fallidos uno por uno...")
        for t in fallidos:
            time.sleep(4)
            try:
                df = yf.download(
                    [t], start=inicio, end=fin, auto_adjust=True, progress=False
                )["Close"]
                if isinstance(df, pd.Series):
                    df = df.to_frame(t)
                if df[t].notna().sum() > 0:
                    partes.append(df)
                    registrar(f"Reintento exitoso: {t}")
                else:
                    registrar(f"Sin datos tras reintento: {t}", "AVISO")
            except Exception as e:
                registrar(f"Reintento fallo para {t}: {e}", "ERROR")

    return partes


def recolectar_precios(forzar=False, dias=1, chunk=20):
    """
    Descarga precios distinguiendo entre:
    - Tickers NUEVOS (no existían en el parquet, o existían pero con menos de
      UMBRAL_HISTORIA_SUFICIENTE días de dato real — ej. quedaron a medias por
      una corrida anterior fallida): reciben 10 años completos de historia.
    - Tickers EXISTENTES (ya tenían historia suficiente): solo se actualizan
      desde la última fecha disponible, para no re-descargar todo cada vez.

    La fusión final usa combine_first() en vez de concat + drop_duplicates,
    para que la actualización sea celda por celda y nunca borre accidentalmente
    historia de un ticker que no se estaba actualizando en ese lote.
    """
    archivo = os.path.join(CARPETA_PRECIOS, "precios.parquet")

    if not forzar and _esta_fresco(archivo, dias):
        registrar("Precios frescos (ya descargados hoy) — omito descarga.", "INFO")
        return

    registrar("Iniciando descarga de precios...")
    tickers = ACTIVOS
    fin = datetime.now()

    if os.path.exists(archivo):
        df_existente = pd.read_parquet(archivo)
    else:
        df_existente = pd.DataFrame()

    # --- Separar tickers nuevos de existentes, por ticker, no por archivo global ---
    if not df_existente.empty:
        tickers_existentes = [
            t
            for t in tickers
            if t in df_existente.columns
            and df_existente[t].notna().sum() >= UMBRAL_HISTORIA_SUFICIENTE
        ]
    else:
        tickers_existentes = []

    tickers_nuevos = [t for t in tickers if t not in tickers_existentes]

    partes = []

    # --- Tickers nuevos: historia completa (10 años) ---
    if tickers_nuevos:
        registrar(
            f"Tickers nuevos detectados ({len(tickers_nuevos)}): "
            f"{tickers_nuevos} — descargando 10 años de historia..."
        )
        inicio_nuevos = fin - timedelta(days=365 * 10)
        partes += _descargar_lote(tickers_nuevos, inicio_nuevos, fin, chunk)
    else:
        registrar("No hay tickers nuevos por descargar.")

    # --- Tickers existentes: solo incremental desde la última fecha ---
    if tickers_existentes:
        ultima_fecha = df_existente[tickers_existentes].dropna(how="all").index.max()
        inicio_existentes = ultima_fecha - timedelta(days=1)
        registrar(
            f"Actualizando {len(tickers_existentes)} tickers existentes "
            f"desde {inicio_existentes.date()}..."
        )
        partes += _descargar_lote(tickers_existentes, inicio_existentes, fin, chunk)

    if not partes:
        registrar("❌ No se pudo descargar ningún lote.", "ERROR")
        return

    df_nuevo = pd.concat(partes, axis=1)
    df_nuevo = df_nuevo.loc[:, ~df_nuevo.columns.duplicated()]
    df_nuevo = df_nuevo.dropna(how="all")

    if df_nuevo.empty:
        registrar("No hay datos nuevos hoy (mercado cerrado o fin de semana).", "AVISO")
        return

    # --- Fusión celda por celda: df_nuevo manda, df_existente rellena huecos ---
    if not df_existente.empty:
        df_final = df_nuevo.combine_first(df_existente)
    else:
        df_final = df_nuevo

    df_final.sort_index(inplace=True)
    df_final.to_parquet(archivo)
    registrar(
        f"✅ Precios guardados. {len(tickers_nuevos)} tickers nuevos con historia completa, "
        f"{len(tickers_existentes)} actualizados. Total: {len(df_final)} días, "
        f"{len(df_final.columns)} activos."
    )


# ============================================================
# RECOLECTOR 2 — TRM COLOMBIA
# ============================================================


def recolectar_trm():
    registrar("Iniciando descarga de TRM...")
    archivo = os.path.join(CARPETA_MACRO, "trm.parquet")

    try:
        url = "https://www.datos.gov.co/resource/ceyp-9c7c.csv?$limit=10000"
        response = requests.get(url, headers=UA, timeout=15)

        df = pd.read_csv(io.StringIO(response.text))
        df["Fecha"] = pd.to_datetime(df["vigenciadesde"])
        df = df.set_index("Fecha").sort_index()
        df = df[["valor"]].rename(columns={"valor": "TRM"})
        df = df[~df.index.duplicated(keep="first")]

        df.to_parquet(archivo)
        registrar(f"✅ TRM guardada. Último valor: ${df['TRM'].iloc[-1]:,.2f}")

    except Exception as e:
        registrar(f"❌ Error descargando TRM: {e}", "ERROR")


# ============================================================
# RECOLECTOR 3 — INFLACIÓN USA
# ============================================================


def recolectar_inflacion_usa():
    registrar("Iniciando descarga de inflación USA...")
    archivo = os.path.join(CARPETA_MACRO, "inflacion_usa.parquet")
    try:
        # FRED API — fuente oficial
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()

        df = (
            pd.read_csv(io.StringIO(r.text), parse_dates=["observation_date"])
            .rename(columns={"observation_date": "Fecha", "CPIAUCSL": "CPI"})
            .set_index("Fecha")
            .sort_index()
        )
        df["CPI"] = pd.to_numeric(df["CPI"], errors="coerce")
        df = df.dropna()
        df["Inflacion_USA"] = df["CPI"].pct_change(12) * 100
        df = df[["Inflacion_USA"]].dropna()
        df.to_parquet(archivo)
        ultimo = df["Inflacion_USA"].iloc[-1]
        fecha_ultimo = df.index[-1].strftime("%Y-%m")
        registrar(
            f"✅ Inflación USA guardada. Último dato: {ultimo:.2f}% ({fecha_ultimo})"
        )
    except Exception as e:
        registrar(f"❌ Error descargando inflación USA: {e}", "ERROR")
        # Fallback: usar valor conocido si falla todo
        if not os.path.exists(archivo):
            df = pd.DataFrame({"Inflacion_USA": [3.5]}, index=[pd.Timestamp.now()])
            df.to_parquet(archivo)
            registrar("⚠️ Usando inflación USA de respaldo: 3.5%", "AVISO")


# ============================================================
# RECOLECTOR 4 — INFLACIÓN COLOMBIA
# ============================================================


def recolectar_inflacion_col():
    """Inflacion total de Colombia (variacion 12 meses).

    PRIMARIA: API de Banrep (mensual, al dia). Requiere poner el idMenu en
    ID_INFLACION_TOTAL - buscalo en el catalogo del portal.

    RESPALDO: Banco Mundial. OJO - es ANUAL y con ~18 meses de rezago. Queda
    marcado como fuente='banco_mundial_anual' para que el analista sepa que
    esta consumiendo un dato grueso y viejo, no inflacion mensual al dia.
    """
    registrar("Iniciando descarga de inflacion Colombia...")
    archivo = os.path.join(CARPETA_MACRO, "inflacion_col.parquet")

    # --- Fuente primaria: API de Banrep ---
    if ID_INFLACION_TOTAL is not None:
        try:
            df, meta = _banrep_serie(ID_INFLACION_TOTAL)
            df = df.rename(columns={"valor": "Inflacion_COL"})
            ok = _guardar_macro(
                df, archivo, "Inflacion_COL", "banrep_api", RANGO_INFLACION_COL
            )
            if ok:
                registrar(
                    f"OK Inflacion COL desde el API. Ultimo: {meta['ultimo_valor']}% "
                    f"({meta['ultima_fecha']}) | {len(df)} datos "
                    f"({meta['periodicidad']}) desde {df.index.min().date()}"
                )
                return
        except Exception as e:
            registrar(f"Fallo el API de Banrep para inflacion: {e}", "ERROR")
    else:
        registrar(
            "ID_INFLACION_TOTAL sin configurar - uso Banco Mundial (anual, con rezago).",
            "AVISO",
        )

    # --- Respaldo: Banco Mundial (anual, rezagado) ---
    try:
        url = (
            "https://api.worldbank.org/v2/country/CO/indicator/FP.CPI.TOTL.ZG"
            "?format=json&per_page=100"
        )
        r = requests.get(url, headers=UA, timeout=15)
        data = r.json()
        filas = [
            {
                "Fecha": pd.Timestamp(f"{rec['date']}-12-31"),
                "Inflacion_COL": float(rec["value"]),
            }
            for rec in data[1]
            if rec.get("value") is not None
        ]
        if not filas:
            raise ValueError("Sin datos del Banco Mundial")

        df = pd.DataFrame(filas).set_index("Fecha").sort_index()
        ok = _guardar_macro(
            df, archivo, "Inflacion_COL", "banco_mundial_anual", RANGO_INFLACION_COL
        )
        if ok:
            registrar(
                f"Inflacion COL desde Banco Mundial: {df['Inflacion_COL'].iloc[-1]:.2f}% "
                f"({df.index[-1].year}). ANUAL Y CON REZAGO - marcada como tal.",
                "AVISO",
            )
        return
    except Exception as e:
        registrar(f"Tambien fallo el Banco Mundial: {e}", "ERROR")

    # --- Ultimo recurso, marcado ---
    df_fb = pd.DataFrame(
        {"Inflacion_COL": [6.14]}, index=[pd.Timestamp("2026-06-30")]
    )
    if _guardar_macro(df_fb, archivo, "Inflacion_COL", "fallback", RANGO_INFLACION_COL):
        registrar(
            "OJO: inflacion COL de RESPALDO (6.14%, junio 2026). "
            "Marcada fuente='fallback'. NO usar para calculos serios.",
            "AVISO",
        )


# ============================================================
# RECOLECTOR 5 — TASA LIBRE DE RIESGO
# ============================================================


def recolectar_tasa_libre_riesgo():
    registrar("Iniciando descarga de tasa libre de riesgo...")
    archivo = os.path.join(CARPETA_MACRO, "risk_free.parquet")

    try:
        url = (
            "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
            "/v2/accounting/od/avg_interest_rates"
            "?filter=security_desc:eq:Treasury Bills,record_date:gte:2015-01-01"
            "&page[size]=10000&sort=-record_date"
        )
        response = requests.get(url, timeout=15)
        data = response.json()

        df = pd.DataFrame(data["data"])
        df["Fecha"] = pd.to_datetime(df["record_date"])
        df["Risk_Free"] = pd.to_numeric(df["avg_interest_rate_amt"], errors="coerce")
        df = df.set_index("Fecha")[["Risk_Free"]].sort_index().dropna()

        df.to_parquet(archivo)
        registrar(
            f"✅ Tasa libre de riesgo guardada. Último dato: {df['Risk_Free'].iloc[-1]:.2f}%"
        )

    except Exception as e:
        registrar(f"❌ Error descargando tasa libre de riesgo: {e}", "ERROR")


# ============================================================
# RECOLECTOR 6 — TASA BANCO DE LA REPÚBLICA
# ============================================================


def recolectar_tasa_banrep():
    """Tasa de politica monetaria del Banco de la Republica.

    Fuente: API oficial de estadisticas de Banrep (serie 59), diaria desde 1998.
    Antes esto scrapeaba HTML con un regex que agarraba el PRIMER porcentaje de
    la pagina - podia ser cualquier numero y no habia forma de saber si acerto.
    """
    registrar("Iniciando descarga de tasa Banrep...")
    archivo = os.path.join(CARPETA_MACRO, "tasa_banrep.parquet")

    if _esta_fresco(archivo, dias=1):
        registrar("Tasa Banrep ya descargada hoy - omito.")
        return

    try:
        df, meta = _banrep_serie(ID_TASA_POLITICA)
        df = df.rename(columns={"valor": "Tasa_Banrep"})
        ok = _guardar_macro(df, archivo, "Tasa_Banrep", "banrep_api", RANGO_TASA_BANREP)
        if ok:
            registrar(
                f"OK Tasa Banrep desde el API. Ultimo: {meta['ultimo_valor']}% "
                f"({meta['ultima_fecha']}) | {len(df)} datos desde {df.index.min().date()}"
            )
        return
    except Exception as e:
        registrar(f"Fallo el API de Banrep: {e}", "ERROR")

    # Fallback: SOLO si no hay ningun dato real guardado. Y queda MARCADO.
    df_fb = pd.DataFrame({"Tasa_Banrep": [12.0]}, index=[pd.Timestamp("2026-06-30")])
    if _guardar_macro(df_fb, archivo, "Tasa_Banrep", "fallback", RANGO_TASA_BANREP):
        registrar(
            "OJO: tasa Banrep de RESPALDO (12.0%, vigente desde 2026-06-30). "
            "Marcada fuente='fallback'. NO usar para calculos serios.",
            "AVISO",
        )


def leer_macro(nombre, columna, permitir_fallback=False):
    """Lector con conciencia de la fuente. Uselo en vez de leer el parquet
    directo, para no consumir un fallback creyendo que es dato real.

    Devuelve (valor, fecha, fuente) o (None, None, None) si no hay dato usable.
    """
    archivo = os.path.join(CARPETA_MACRO, nombre)
    if not os.path.exists(archivo):
        return None, None, None
    try:
        df = pd.read_parquet(archivo)
        if "fuente" not in df.columns:
            df["fuente"] = "desconocida"
        if not permitir_fallback:
            df = df[df["fuente"] != "fallback"]
        if df.empty:
            return None, None, None
        df = df.sort_index()
        return float(df.iloc[-1][columna]), df.index[-1], str(df.iloc[-1]["fuente"])
    except Exception:
        return None, None, None


# ============================================================
# EJECUCIÓN PRINCIPAL
# ============================================================
def correr_todo(forzar=False):
    crear_carpetas()
    recolectar_precios(forzar=forzar)
    recolectar_trm()
    recolectar_inflacion_usa()
    recolectar_inflacion_col()
    recolectar_tasa_libre_riesgo()
    recolectar_tasa_banrep()


if __name__ == "__main__":
    print("=" * 50)
    print("🤖 RECOLECTOR DE DATOS — INICIANDO")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    correr_todo()

    print("=" * 50)
    print("✅ RECOLECCIÓN COMPLETA")
    print("=" * 50)