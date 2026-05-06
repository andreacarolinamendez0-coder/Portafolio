import yfinance as yf
import pandas as pd
import requests 
import json
import io
import os
from datetime import datetime, timedelta
# ============================================================
# CONFIGURACIÓN — aquí defines los activos
# ============================================================

ACTIVOS = [
    'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META', #Tecnología
    'JPM', 'V', 'MA',                            # Financiero
    'JNJ', 'LLY',                                # Salud
    'AMZN', 'WMT', 'KO',                         # Consumo
    'XOM', 'CVX',                                # Energía
    'GLD', 'TLT',                                # Oro y Bonos
    'VOO', 'VTI', 'VWO',                          # ETFs core
    'QQQ', 'XLK',                                # índices de Tecnología
    'BTC-USD', 'ETH-USD', 'SOL-USD'              # Criptomonedas
]

CARPETA_PRECIOS = "Datos/Precios"
CARPETA_MACRO = "Datos/Macro"
CARPETA_LOGS = "Datos/Logs"


# ============================================================
# UTILIDADES
# ============================================================

def registrar(mensaje, tipo="INFO"):
    """Guarda cada evento en el log del día."""
    hoy= datetime.now().strftime("%Y-%m-%d")
    hora= datetime.now().strftime("%H:%M:%S")
    linea= f"[{hora}][{tipo}]{mensaje}\n"
    print(linea.strip())
    with open (f"{CARPETA_LOGS}/Log_{hoy}.txt","a", encoding="utf-8") as f:
        f.write(linea)

def crear_carpetas():
    """Crea las carpetas si no existen."""
    for carpeta in [CARPETA_PRECIOS, CARPETA_MACRO, CARPETA_LOGS]:
        os.makedirs(carpeta, exist_ok=True)

# ============================================================
# RECOLECTOR 1 — PRECIOS DE ACCIONES
# ============================================================

def recolectar_precios():
    registrar("Iniciando descarga de precios...")
    archivo= f"{CARPETA_PRECIOS}/precios.parquet"

    #¿Ya tenemos datos guardados?
    if os.path.exists(archivo):
        df_existente = pd.read_parquet(archivo)
        ultima_fecha = df_existente.index.max()
        inicio = ultima_fecha + timedelta(days=1)
        registrar(f"Datos existentes hasta {ultima_fecha.date()}. Descargando desde {inicio.date()}...")
    else:
        df_existente = pd.DataFrame()
        inicio = datetime.now() - timedelta(days=365*10)
        registrar("Primera descarga -  obteniendo 10 años de historia...")
    fin = datetime.now()

    #Descarga solo lo nuevo
    try:
        df_nuevo = yf.download(ACTIVOS, start=inicio, end=fin, auto_adjust=True)['Close']
        df_nuevo = df_nuevo.dropna(how='all')

        if df_nuevo.empty:
            registrar("No hay datos neuvos hoy (mercado cerrado o fin de semana).", "AVISO")
            return
        
        #Unimos con lo existente
        if not df_existente.empty:
            df_final= pd.concat([df_existente, df_nuevo])
            df_final = df_final[~df_final.index.duplicated(keep='last')]
        else:
            df_final = df_nuevo

        df_final.sort_index(inplace=True)
        df_final.to_parquet(archivo)
        registrar(f" ✅ Precios guardados. {len(df_nuevo)} días nuevos. Total: {len(df_final)} días.")
    
    except Exception as e:
        registrar (f" ❌ Error descargando precios:{e}, ERROR")

# ============================================================
# RECOLECTOR 2 — TRM COLOMBIA
# ============================================================

def recolectar_trm():
    registrar("Iniciando descarga de TRM...")
    archivo=f"{CARPETA_MACRO}/trm.parquet"

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
    archivo = f"{CARPETA_MACRO}/inflacion_usa.parquet"

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
    archivo = f"{CARPETA_MACRO}/inflacion_col.parquet"

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
    archivo = f"{CARPETA_MACRO}/risk_free.parquet"

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
# RECOLECTOR 6 — TASA BANCO DE LA REPÚBLICA - CDT = Tasa BanRep-0.5%-1%
# ============================================================

def recolectar_tasa_banrep():
    registrar("Iniciando descarga de tasa Banrep...")
    archivo = f"{CARPETA_MACRO}/tasa_banrep.parquet"
    tasa = None

    
    # Si ya descargamos hoy, usar ese dato directamente
    if os.path.exists(archivo):
        try:
            df_prev = pd.read_parquet(archivo)
            ultima  = df_prev.index.max()
            if ultima.date() == datetime.now().date():
                tasa_hoy = float(df_prev['Tasa_Banrep'].iloc[-1])
                registrar(f"✅ Tasa Banrep ya descargada hoy: {tasa_hoy:.2f}%")
                return  # No volver a descargar
        except: pass

    try:
        # Intentamos con la API de series estadísticas del Banrep
        url = "https://www.banrep.gov.co/es/estadisticas/tasas-de-interes-del-banco-de-la-republica"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)

        # Si no funciona la API, buscamos en el HTML el dato actual
        import re
        texto = response.text
        patron = r'(\d+[.,]\d+)\s*%'
        matches = re.findall(patron, texto)

        if matches:
            tasa = float(matches[0].replace(',', '.'))
            registrar(f"✅ Tasa Banrep extraída del sitio web: {tasa:.2f}%")
        else:
            raise ValueError("No se encontró la tasa en el HTML")

    except Exception:
        # Backup con tasa actual conocida — actualizar manualmente si cambia
        # Última tasa Banrep: 11.25% (vigente desde febrero 2024)
        tasa = 11.25
        registrar(f"⚠️ Usando tasa Banrep de respaldo: {tasa}%", "AVISO")

    # Guardamos el dato
    df = pd.DataFrame(
        {'Tasa_Banrep': [tasa]},
        index=[pd.Timestamp.now()]
    )

    # Si ya existe el archivo, agregamos el nuevo dato
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

import os
os.makedirs("datos/macro", exist_ok=True)
os.makedirs("datos/precios", exist_ok=True)
os.makedirs("datos/portafolios", exist_ok=True)
os.makedirs("datos/Logs", exist_ok=True)
os.makedirs("datos/Reportes", exist_ok=True)
os.makedirs("datos/seguimiento", exist_ok=True)
os.makedirs("datos/historico", exist_ok=True)

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
    