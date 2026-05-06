import yfinance as yf
import pandas as pd
import requests
import json
import io
import os
from datetime import datetime, timedelta

# ============================================================
# RUTAS ABSOLUTAS — funciona igual en local y en Railway
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATOS_DIR = os.path.join(BASE_DIR, "datos")

CARPETA_PRECIOS = os.path.join(DATOS_DIR, "precios")
CARPETA_MACRO   = os.path.join(DATOS_DIR, "macro")
CARPETA_LOGS    = os.path.join(DATOS_DIR, "Logs")

# ============================================================
# CONFIGURACIÓN — activos
# ============================================================

ACTIVOS = [
    'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META',
    'JPM', 'V', 'MA',
    'JNJ', 'LLY',
    'AMZN', 'WMT', 'KO',
    'XOM', 'CVX',
    'GLD', 'TLT',
    'VOO', 'VTI', 'VWO',
    'QQQ', 'XLK',
    'BTC-USD', 'ETH-USD', 'SOL-USD'
]

# ============================================================
# UTILIDADES
# ============================================================

def crear_carpetas():
    for carpeta in [
        CARPETA_PRECIOS, CARPETA_MACRO, CARPETA_LOGS,
        os.path.join(DATOS_DIR, "portafolios"),
        os.path.join(DATOS_DIR, "Reportes"),
        os.path.join(DATOS_DIR, "seguimiento"),
        os.path.join(DATOS_DIR, "historico"),
    ]:
        os.makedirs(carpeta, exist_ok=True)

def registrar(mensaje, tipo="INFO"):
    hoy  = datetime.now().strftime("%Y-%m-%d")
    hora = datetime.now().strftime("%H:%M:%S")
    linea = f"[{hora}][{tipo}]{mensaje}\n"
    print(linea.strip())
    try:
        with open(os.path.join(CARPETA_LOGS, f"Log_{hoy}.txt"), "a", encoding="utf-8") as f:
            f.write(linea)
    except Exception:
        pass

# ============================================================
# RECOLECTOR 1 — PRECIOS DE ACCIONES
# ============================================================

def recolectar_precios():
    registrar("Iniciando descarga de precios...")
    archivo = os.path.join(CARPETA_PRECIOS, "precios.parquet")

    if os.path.exists(archivo):
        df_existente = pd.read_parquet(archivo)
        ultima_fecha = df_existente.index.max()
        inicio = ultima_fecha + timedelta(days=1)
        registrar(f"Datos existentes hasta {ultima_fecha.date()}. Descargando desde {inicio.date()}...")
    else:
        df_existente = pd.DataFrame()
        inicio = datetime.now() - timedelta(days=365 * 10)
        registrar("Primera descarga — obteniendo 10 años de historia...")

    fin = datetime.now()

    try:
        df_nuevo = yf.download(ACTIVOS, start=inicio, end=fin, auto_adjust=True)['Close']
        df_nuevo = df_nuevo.dropna(how='all')

        if df_nuevo.empty:
            registrar("No hay datos nuevos hoy (mercado cerrado o fin de semana).", "AVISO")
            return

        if not df_existente.empty:
            df_final = pd.concat([df_existente, df_nuevo])
            df_final = df_final[~df_final.index.duplicated(keep='last')]
        else:
            df_final = df_nuevo

        df_final.sort_index(inplace=True)
        df_final.to_parquet(archivo)
        registrar(f"✅ Precios guardados. {len(df_nuevo)} días nuevos. Total: {len(df_final)} días.")

    except Exception as e:
        registrar(f"❌ Error descargando precios: {e}", "ERROR")

# ============================================================
# RECOLECTOR 2 — TRM COLOMBIA
# ============================================================

def recolectar_trm():
    registrar("Iniciando descarga de TRM...")
    archivo = os.path.join(CARPETA_MACRO, "trm.parquet")

    try:
        url = "https://www.datos.gov.co/resource/ceyp-9c7c.csv?$limit=10000"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)

        df = pd.read_csv(io.StringIO(response.text))
        df['Fecha'] = pd.to_datetime(df['vigenciadesde'])
        df = df.set_index('Fecha').sort_index()
        df = df[['valor']].rename(columns={'valor': 'TRM'})
        df = df[~df.index.duplicated(keep='first')]

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
        url = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'
        payload = {
            "seriesid": ["CUUR0000SA0"],
            "startyear": "2015",
            "endyear": str(datetime.now().year),
            "registrationkey": "267979a140dc42af90f378bbdf482785"
        }
        response = requests.post(url, data=json.dumps(payload),
                                 headers={'Content-type': 'application/json'}, timeout=15)
        json_data = response.json()

        data_list = []
        for row in json_data['Results']['series'][0]['data']:
            if row['value'] in ['-', '']:
                continue
            mes = row['period'][1:]
            data_list.append({
                'Fecha': pd.to_datetime(f"{row['year']}-{mes}-01"),
                'CPI': float(row['value'])
            })

        df = pd.DataFrame(data_list).set_index('Fecha').sort_index()
        df['Inflacion_USA'] = df['CPI'].pct_change(12) * 100
        df = df[['Inflacion_USA']].dropna()

        df.to_parquet(archivo)
        registrar(f"✅ Inflación USA guardada. Último dato: {df['Inflacion_USA'].iloc[-1]:.2f}%")

    except Exception as e:
        registrar(f"❌ Error descargando inflación USA: {e}", "ERROR")

# ============================================================
# RECOLECTOR 4 — INFLACIÓN COLOMBIA
# ============================================================

def recolectar_inflacion_col():
    registrar("Iniciando descarga de inflación Colombia...")
    archivo = os.path.join(CARPETA_MACRO, "inflacion_col.parquet")

    try:
        url = "https://api.db.nomics.world/v22/series/IMF/CPI/M.CO.PCPI_PC_CP_A_PT.csv"
        response = requests.get(url, timeout=15)
        df = pd.read_csv(io.StringIO(response.text))

        df = df.rename(columns={'period': 'Fecha'})
        col_valor = [c for c in df.columns if c not in
                     ['Fecha', 'series_code', 'series_name']][-1]
        df = df.rename(columns={col_valor: 'Inflacion_COL'})
        df['Fecha'] = pd.to_datetime(df['Fecha'])
        df = df.set_index('Fecha').sort_index()
        df = df[['Inflacion_COL']].dropna()

        df.to_parquet(archivo)
        registrar(f"✅ Inflación COL guardada. Último dato: {df['Inflacion_COL'].iloc[-1]:.2f}%")

    except Exception as e:
        registrar(f"❌ Error descargando inflación COL: {e}", "ERROR")

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

        df = pd.DataFrame(data['data'])
        df['Fecha'] = pd.to_datetime(df['record_date'])
        df['Risk_Free'] = pd.to_numeric(df['avg_interest_rate_amt'], errors='coerce')
        df = df.set_index('Fecha')[['Risk_Free']].sort_index().dropna()

        df.to_parquet(archivo)
        registrar(f"✅ Tasa libre de riesgo guardada. Último dato: {df['Risk_Free'].iloc[-1]:.2f}%")

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
            ultima  = df_prev.index.max()
            if ultima.date() == datetime.now().date():
                tasa_hoy = float(df_prev['Tasa_Banrep'].iloc[-1])
                registrar(f"✅ Tasa Banrep ya descargada hoy: {tasa_hoy:.2f}%")
                return
        except Exception:
            pass

        try:
            url = "https://www.banrep.gov.co/es/estadisticas/tasas-de-interes-del-banco-de-la-republica"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=15)

            import re
            matches = re.findall(r'(\d+[.,]\d+)\s*%', response.text)
            registrar(f"DEBUG todos los porcentajes encontrados: {matches[:20]}", "INFO")

            if matches:
                tasa = float(matches[0].replace(',', '.'))
                registrar(f"✅ Tasa Banrep extraída del sitio web: {tasa:.2f}%")
            else:
                raise ValueError("No se encontró la tasa en el HTML")

        except Exception:
            tasa = 11.25
            registrar(f"⚠️ Usando tasa Banrep de respaldo: {tasa}%", "AVISO")

    df = pd.DataFrame({'Tasa_Banrep': [tasa]}, index=[pd.Timestamp.now()])

    if os.path.exists(archivo):
        df_existente = pd.read_parquet(archivo)
        df = pd.concat([df_existente, df])
        df = df[~df.index.duplicated(keep='last')]

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
    recolectar_precios()
    recolectar_trm()
    recolectar_inflacion_usa()
    recolectar_inflacion_col()
    recolectar_tasa_libre_riesgo()
    recolectar_tasa_banrep()

    print("=" * 50)
    print("✅ RECOLECCIÓN COMPLETA")
    print("=" * 50)