import yfinance as yf
import pandas as pd
import requests
import json
import io
import os
from datetime import datetime, timedelta
import time

# ============================================================
# RUTAS ABSOLUTAS — funciona igual en local y en Railway
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATOS_DIR = os.path.join(BASE_DIR, "datos")

CARPETA_PRECIOS = os.path.join(DATOS_DIR, "precios")
CARPETA_MACRO = os.path.join(DATOS_DIR, "macro")
CARPETA_LOGS = os.path.join(DATOS_DIR, "Logs")

# ============================================================
# CONFIGURACIÓN — activos
# ============================================================

CRIPTO = ["BTC-USD", "ETH-USD", "SOL-USD"]

ACTIVOS_POR_SECTOR = {
    "Technology":              ["AAPL", "MSFT", "GOOGL", "NVDA", "AVGO"],
    "Communication Services":  ["META", "NFLX", "DIS", "TMUS"],
    "Consumer Cyclical":       ["AMZN", "TSLA", "HD", "MCD"],
    "Consumer Defensive":      ["WMT", "KO", "PG", "COST"],
    "Financial Services":      ["JPM", "V", "MA", "BAC"],
    "Healthcare":              ["LLY", "JNJ", "UNH", "ABBV"],
    "Industrials":             ["CAT", "BA", "GE", "HON"],
    "Energy":                  ["XOM", "CVX", "COP"],
    "Utilities":               ["NEE", "DUK", "SO"],
    "Real Estate":             ["PLD", "AMT"],
    "Basic Materials":         ["LIN", "FCX"],
}

ETFS = {
    "US Broad":      ["VOO", "VTI", "SPY", "QQQ", "IWM", "DIA"],
    "Sectoriales":   ["XLK", "XLF", "XLE", "XLV", "XLI", "XLP",
                      "XLY", "XLU", "XLB", "XLRE", "XLC"],
    "Bonos":         ["BND", "AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP"],
    "Internacional": ["VEA", "VWO", "EFA", "EEM", "VXUS"],
    "Commodities":   ["GLD", "GLDM", "SLV", "DBC"],
    "Dividendo":     ["SCHD", "VIG", "VYM", "DGRO"],
    "REITs":         ["VNQ"],
}

TICKER_SECTOR = {t: sector for sector, lst in ACTIVOS_POR_SECTOR.items() for t in lst}
TICKER_SECTOR.update({t: "ETF" for lst in ETFS.values() for t in lst})
TICKER_SECTOR.update({t: "Crypto" for t in CRIPTO})

ACTIVOS = sorted(set(TICKER_SECTOR.keys()))

def _esta_fresco(archivo, dias=1):
    if not os.path.exists(archivo):
        return False
    edad = datetime.now() - datetime.fromtimestamp(os.path.getmtime(archivo))
    return edad.days < dias

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


def recolectar_precios(forzar=False, dias=1, chunk=80):
    archivo = os.path.join(CARPETA_PRECIOS, "precios.parquet")

    if not forzar and _esta_fresco(archivo, dias):
        registrar("Precios frescos (ya descargados hoy) — omito descarga.", "INFO")
        return

    registrar("Iniciando descarga de precios...")
    tickers = ACTIVOS

    if os.path.exists(archivo):
        df_existente = pd.read_parquet(archivo)
        ultima_fecha = df_existente.index.max()
        inicio = ultima_fecha - timedelta(days=1)
        registrar(f"Datos existentes hasta {ultima_fecha.date()}. Descargando desde {inicio.date()}...")
    else:
        df_existente = pd.DataFrame()
        inicio = datetime.now() - timedelta(days=365 * 10)
        registrar("Primera descarga — obteniendo 10 años de historia...")

    fin = datetime.now()
    partes = []
    for i in range(0, len(tickers), chunk):
        lote = tickers[i:i + chunk]
        try:
            df = yf.download(lote, start=inicio, end=fin, auto_adjust=True, progress=False)["Close"]
            if isinstance(df, pd.Series):
                df = df.to_frame(lote[0])
            partes.append(df)
        except Exception as e:
            registrar(f"❌ Lote {i // chunk + 1} falló: {e}", "ERROR")
        time.sleep(2)

    if not partes:
        registrar("❌ No se pudo descargar ningún lote.", "ERROR")
        return

    df_nuevo = pd.concat(partes, axis=1)
    df_nuevo = df_nuevo.loc[:, ~df_nuevo.columns.duplicated()]
    df_nuevo = df_nuevo.dropna(how="all")

    if df_nuevo.empty:
        registrar("No hay datos nuevos hoy (mercado cerrado o fin de semana).", "AVISO")
        return

    if not df_existente.empty:
        df_final = pd.concat([df_existente, df_nuevo])
        df_final = df_final[~df_final.index.duplicated(keep="last")]
    else:
        df_final = df_nuevo

    df_final.sort_index(inplace=True)
    df_final.to_parquet(archivo)
    registrar(f"✅ Precios guardados. {len(df_nuevo)} días nuevos. Total: {len(df_final)} días.")


# ============================================================
# RECOLECTOR 2 — TRM COLOMBIA
# ============================================================


def recolectar_trm():
    registrar("Iniciando descarga de TRM...")
    archivo = os.path.join(CARPETA_MACRO, "trm.parquet")

    try:
        url = "https://www.datos.gov.co/resource/ceyp-9c7c.csv?$limit=10000"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)

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
        fred_key = os.environ.get("FRED_API_KEY", "")
        
        # FRED API — fuente oficial
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&api_key={fred_key}&file_type=json&sort_order=asc"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        datos = r.json()["observations"]

        from io import StringIO
        df = pd.DataFrame(datos)[["date", "value"]].rename(columns={"date": "Fecha", "value": "CPI"})
        df = pd.read_csv(StringIO(df.to_csv(index=False)))
        df.columns = ["Fecha", "CPI"]
        df["Fecha"] = pd.to_datetime(df["Fecha"])
        df = df.set_index("Fecha").sort_index()
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
            df = pd.DataFrame(
                {"Inflacion_USA": [3.5]}, index=[pd.Timestamp("2025-03-01")]
            )
            df.to_parquet(archivo)
            registrar("⚠️ Usando inflación USA de respaldo: 3.5% (marzo 2025)", "AVISO")


# ============================================================
# RECOLECTOR 4 — INFLACIÓN COLOMBIA
# ============================================================


def recolectar_inflacion_col():
    registrar("Iniciando descarga de inflación Colombia...")
    archivo = os.path.join(CARPETA_MACRO, "inflacion_col.parquet")
    try:
        # DANE vía API pública del Banco Mundial
        url = (
            "https://api.worldbank.org/v2/country/CO/indicator/FP.CPI.TOTL.ZG"
            "?format=json&per_page=10&mrv=5"
        )
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
        registros = data[1]
        filas = []
        for rec in registros:
            if rec.get("value") is not None:
                filas.append(
                    {
                        "Fecha": pd.Timestamp(f"{rec['date']}-12-01"),
                        "Inflacion_COL": float(rec["value"]),
                    }
                )
        if not filas:
            raise ValueError("Sin datos del Banco Mundial")
        df = pd.DataFrame(filas).set_index("Fecha").sort_index()
        df.to_parquet(archivo)
        ultimo = df["Inflacion_COL"].iloc[-1]
        fecha_ultimo = df.index[-1].strftime("%Y")
        registrar(
            f"✅ Inflación COL guardada. Último dato: {ultimo:.2f}% ({fecha_ultimo})"
        )
    except Exception as e:
        registrar(
            f"⚠️ Banco Mundial falló: {e} — intentando fuente alternativa", "AVISO"
        )
        try:
            # Alternativa: db.nomics con serie del FMI
            url2 = "https://api.db.nomics.world/v22/series/WB/WDI/A.FP.CPI.TOTL.ZG.COL?observations=1"
            r2 = requests.get(url2, timeout=15)
            data2 = r2.json()
            periods = data2["series"]["docs"][0]["period"]
            values = data2["series"]["docs"][0]["value"]
            filas2 = []
            for p, v in zip(periods, values):
                if v is not None:
                    try:
                        filas2.append(
                            {
                                "Fecha": pd.Timestamp(f"{p}-12-01"),
                                "Inflacion_COL": float(v),
                            }
                        )
                    except:
                        continue
            if not filas2:
                raise ValueError("Sin datos en alternativa")
            df2 = pd.DataFrame(filas2).set_index("Fecha").sort_index()
            df2.to_parquet(archivo)
            ultimo2 = df2["Inflacion_COL"].iloc[-1]
            registrar(f"✅ Inflación COL (alternativa) guardada: {ultimo2:.2f}%")
        except Exception as e2:
            registrar(f"❌ Ambas fuentes fallaron: {e2}", "ERROR")
            if not os.path.exists(archivo):
                df_fb = pd.DataFrame(
                    {"Inflacion_COL": [5.68]}, index=[pd.Timestamp("2024-12-01")]
                )
                df_fb.to_parquet(archivo)
                registrar(
                    "⚠️ Usando inflación COL de respaldo: 5.68% (abril 2026)", "AVISO"
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
    registrar("Iniciando descarga de tasa Banrep...")
    archivo = os.path.join(CARPETA_MACRO, "tasa_banrep.parquet")
    tasa = None

    if os.path.exists(archivo):
        try:
            df_prev = pd.read_parquet(archivo)
            ultima = df_prev.index.max()
            if ultima.date() == datetime.now().date():
                tasa_hoy = float(df_prev["Tasa_Banrep"].iloc[-1])
                registrar(f"✅ Tasa Banrep ya descargada hoy: {tasa_hoy:.2f}%")
                return
        except Exception:
            pass

        try:
            url = "https://www.banrep.gov.co/es/estadisticas/tasas-de-interes-del-banco-de-la-republica"
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=15)

            import re

            matches = re.findall(r"(\d+[.,]\d+)\s*%", response.text)
            registrar(
                f"DEBUG todos los porcentajes encontrados: {matches[:20]}", "INFO"
            )

            if matches:
                tasa = float(matches[0].replace(",", "."))
                registrar(f"✅ Tasa Banrep extraída del sitio web: {tasa:.2f}%")
            else:
                raise ValueError("No se encontró la tasa en el HTML")

        except Exception:
            tasa = 11.25
            registrar(f"⚠️ Usando tasa Banrep de respaldo: {tasa}%", "AVISO")

    df = pd.DataFrame({"Tasa_Banrep": [tasa]}, index=[pd.Timestamp.now()])

    if os.path.exists(archivo):
        df_existente = pd.read_parquet(archivo)
        df = pd.concat([df_existente, df])
        df = df[~df.index.duplicated(keep="last")]

    df.sort_index(inplace=True)
    df.to_parquet(archivo)
    registrar(f"✅ Tasa Banrep guardada: {tasa:.2f}%")


# ============================================================
# EJECUCIÓN PRINCIPAL
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 RECOLECTOR DE DATOS — INICIANDO")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    crear_carpetas()
    recolectar_precios(forzar=True, dias=1)
    recolectar_trm()
    recolectar_inflacion_usa()
    recolectar_inflacion_col()
    recolectar_tasa_libre_riesgo()
    recolectar_tasa_banrep()

    print("=" * 50)
    print("✅ RECOLECCIÓN COMPLETA")
    print("=" * 50)
