"""
preparador_datos.py
====================
Módulo independiente que toma los precios crudos del recolector y los deja
listos para construir las redes (sectorial y de riesgo).

Flujo: recolector.py (precios.parquet) -> preparador_datos.py -> analista.py

6 capas:
    1. Ingesta        -> cargar_precios()
    2. Validacion     -> validar_calidad()
    3. Calendario     -> recortar_a_calendario()   <- todos al calendario de bolsa
    4. Transformacion -> calcular_retornos_log()
    5. Alineacion     -> alinear_fechas()
    6. Correlacion    -> matriz_correlacion()

Uso típico:
    from preparador_datos import preparar_universo

    resultado = preparar_universo()
    resultado["retornos"]          # DataFrame de retornos log, limpio y alineado
    resultado["correlacion"]       # matriz de correlación final
    resultado["activos_validos"]   # lista de tickers que pasaron validación
    resultado["activos_excluidos"] # dict {ticker: razón de exclusión}
    resultado["sector"]            # dict {ticker: sector}  (heredado del recolector)
"""

import os
import numpy as np
import pandas as pd

# ============================================================
# CONFIGURACIÓN — importa rutas y etiquetas directo del recolector
# para no duplicar información (single source of truth)
# ============================================================

import recolector as R

CARPETA_PRECIOS = R.CARPETA_PRECIOS
TICKER_SECTOR = R.TICKER_SECTOR  # capa de sector, ya existe, se hereda tal cual

# Cripto opera 7 dias/semana; la bolsa 5. Para que todo viva en el mismo
# calendario hay que saber quien es quien. Se hereda del recolector.
TICKERS_CRIPTO = {t for t, s in TICKER_SECTOR.items() if s == "Crypto"}

# ------------------------------------------------------------
# SERIES DE CONTEXTO — no se pueden comprar
# ------------------------------------------------------------
# Sirven para que el analista sepa que hace el mercado, NO para invertir.
# NUNCA entran al selector de portafolio ni a la matriz de correlacion del
# universo invertible, y NO recortan la historia de nadie.
#
# El valor dice como se convierte la serie a "retorno":
#   "log"        -> ln(P_t / P_t-1). Para indices de PRECIO y para el VIX.
#   "diferencia" -> P_t - P_t-1. Para RENDIMIENTOS. ^TNX es el rendimiento del
#                   bono a 10 años EN PORCENTAJE, no un precio: si pasa de 4.50
#                   a 4.55 no "rindio 1.1%", subio 5 puntos basicos. Sacarle
#                   ln() seria peras con manzanas en la raiz.
#
# Se lee del recolector si esta definido alli (que es donde deberia vivir);
# si no, se usa este default.
CONTEXTO = getattr(R, "CONTEXTO", {
    "^VIX": "log",          # indice de volatilidad
    "^TNX": "diferencia",   # rendimiento del tesoro a 10 años, en %
    "CL=F": "log",          # futuro de crudo
    "NG=F": "log",          # futuro de gas natural
    "DX-Y.NYB":"log",
})

# Series que duplican a un invertible que ya esta en el universo. El indice
# ^GSPC y el ETF SPY son la misma cosa (correlacion 1.00): tener los dos solo
# ensucia la matriz. Se descartan.
REDUNDANTES = getattr(R, "REDUNDANTES", {
    "^GSPC": "duplica a SPY",
    "^DJI": "duplica a DIA",
    "^IXIC": "duplica a QQQ",
    "^RUT": "duplica a IMX",
})

# Proporcion minima de activos no-cripto VIVOS que deben reportar precio
# para considerar que ese dia la bolsa abrio.
UMBRAL_DIA_BOLSA = 0.5

# ------------------------------------------------------------
# Umbrales de validación — AJUSTABLES, decisión tuya
# ------------------------------------------------------------
MIN_DIAS_HISTORIA = 252        # ~1 año de trading, mínimo para correlación confiable
MAX_HUECO_CONSECUTIVO = 10     # días seguidos sin dato -> sospechoso
MIN_PRECIO_VALIDO = 0.0001     # precios <= 0 son error de fuente, no un activo barato


# ============================================================
# CAPA 1 — INGESTA
# ============================================================

def cargar_precios() -> pd.DataFrame:
    """Carga el parquet de precios tal como lo deja el recolector.
    No transforma nada, solo lee."""
    archivo = os.path.join(CARPETA_PRECIOS, "precios.parquet")
    if not os.path.exists(archivo):
        raise FileNotFoundError(
            f"No existe {archivo}. Corre recolector.recolectar_precios() primero."
        )
    df = pd.read_parquet(archivo)
    df.sort_index(inplace=True)
    return df


# ============================================================
# CAPA 2 — VALIDACIÓN DE CALIDAD
# ============================================================

def _hueco_maximo_consecutivo(serie: pd.Series) -> int:
    """Cuenta el hueco de NaN consecutivos más largo dentro del rango
    donde el activo ya tiene datos (ignora el NaN inicial antes del IPO/listado)."""
    valida = serie.dropna()
    if valida.empty:
        return len(serie)
    inicio = valida.index[0]
    tramo = serie.loc[inicio:]
    es_nan = tramo.isna()
    if not es_nan.any():
        return 0
    grupos = (~es_nan).cumsum()
    huecos = es_nan.groupby(grupos).sum()
    return int(huecos.max())


def validar_calidad(df_precios: pd.DataFrame) -> dict:
    """Evalúa cada ticker contra reglas explícitas y separa
    válidos de excluidos, guardando la razón de cada exclusión.

    Retorna:
        {
          "validos": [tickers...],
          "excluidos": {ticker: "razón"},
        }
    """
    validos = []
    excluidos = {}

    for ticker in df_precios.columns:
        serie = df_precios[ticker]
        dias_con_dato = serie.notna().sum()

        if dias_con_dato < MIN_DIAS_HISTORIA:
            excluidos[ticker] = (
                f"historia insuficiente ({dias_con_dato} días, mínimo {MIN_DIAS_HISTORIA})"
            )
            continue

        precios_no_positivos = (serie.dropna() <= MIN_PRECIO_VALIDO).sum()
        if precios_no_positivos > 0:
            excluidos[ticker] = f"{precios_no_positivos} precios en cero o negativos (error de fuente)"
            continue

        hueco = _hueco_maximo_consecutivo(serie)
        if hueco > MAX_HUECO_CONSECUTIVO:
            excluidos[ticker] = f"hueco de {hueco} días consecutivos sin dato"
            continue

        validos.append(ticker)

    return {"validos": validos, "excluidos": excluidos}



# ============================================================
# CAPA 3 — CALENDARIO MAESTRO (todos al calendario de la bolsa)
# ============================================================

def dias_de_bolsa(df_precios: pd.DataFrame, umbral: float = UMBRAL_DIA_BOLSA) -> pd.Series:
    """Marca que dias del indice son dias de bolsa.

    Regla: es dia de bolsa si (a) es dia de semana Y (b) al menos `umbral` de
    los activos NO-cripto que estan VIVOS ese dia reportan precio.

    Por que "vivos" y no "todos": muchos activos nacieron despues del inicio
    de la serie (XLC en 2018, GLDM en 2018). Si se exigiera mayoria sobre el
    total, los años iniciales se caerian por falta de activos que aun no
    existian, no porque la bolsa estuviera cerrada. Un activo que todavia no
    nace no vota.

    Por que mayoria y no "al menos uno": si algun ETF raro llegara a cotizar
    un feriado gringo, "al menos uno" metaria un dia falso al calendario.
    """
    excluir = TICKERS_CRIPTO | set(CONTEXTO) | set(REDUNDANTES)
    no_cripto = [c for c in df_precios.columns if c not in excluir]
    if not no_cripto:
        raise ValueError("No hay activos invertibles no-cripto para definir el calendario.")

    sub = df_precios[no_cripto]

    primero = sub.apply(lambda c: c.first_valid_index())
    ultimo = sub.apply(lambda c: c.last_valid_index())

    vivos = pd.DataFrame(
        {t: (sub.index >= primero[t]) & (sub.index <= ultimo[t]) for t in no_cripto},
        index=sub.index,
    )
    n_vivos = vivos.sum(axis=1)
    n_reportan = sub.notna().sum(axis=1)

    proporcion = n_reportan / n_vivos.replace(0, np.nan)
    entre_semana = pd.Series(sub.index.dayofweek < 5, index=sub.index)

    return entre_semana & (proporcion >= umbral)


def separar_universo(df_precios: pd.DataFrame) -> dict:
    """Parte las columnas en tres grupos, por lo que SON:

      invertibles -> se pueden comprar. Son los unicos que ve el selector.
      contexto    -> ^VIX, ^TNX, futuros. Informan, no se compran.
      redundantes -> duplican a un invertible (^GSPC vs SPY). Se botan.

    Sin esta separacion pasaban dos cosas malas:
      1. El selector podia meter ^VIX al portafolio. Nada se lo impedia.
      2. Una serie de contexto con poca historia recortaba, via
         dropna(how="any"), la historia de TODOS los invertibles.
    """
    cols = list(df_precios.columns)
    redundantes = [c for c in cols if c in REDUNDANTES]
    contexto = [c for c in cols if c in CONTEXTO]
    invertibles = [c for c in cols if c not in REDUNDANTES and c not in CONTEXTO]
    return {
        "invertibles": invertibles,
        "contexto": contexto,
        "redundantes": redundantes,
    }


def calcular_contexto(df_precios: pd.DataFrame, columnas: list) -> pd.DataFrame:
    """Convierte las series de contexto a variacion, cada una con su regla.

    OJO: el resultado NO es comparable con los retornos de los invertibles ni
    entre si. ^TNX viene en puntos porcentuales; ^VIX en retorno log. Estan
    juntos en un DataFrame por comodidad, no porque compartan unidad. Nunca
    los metas a una matriz de correlacion con los retornos de precios.
    """
    salida = {}
    for c in columnas:
        regla = CONTEXTO.get(c, "log")
        serie = df_precios[c]

        if regla == "diferencia":
            # Un rendimiento SI puede ser negativo (o cero): no se valida signo.
            salida[c] = serie.diff()          # cambio en puntos porcentuales
        else:
            # log() de un precio <= 0 da NaN y lanza RuntimeWarning. Pasa de
            # verdad: CL=F (futuro de crudo) cotizo NEGATIVO en abril de 2020.
            # Las series de contexto no pasan por validar_calidad(), asi que
            # hay que blindarlas aqui: los no-positivos se marcan NaN a
            # proposito, en vez de dejar que numpy los convierta con warning.
            limpia = serie.where(serie > 0)
            salida[c] = np.log(limpia / limpia.shift(1))

    return pd.DataFrame(salida, index=df_precios.index)


def recortar_a_calendario(df_precios: pd.DataFrame) -> pd.DataFrame:
    """Deja SOLO los dias de bolsa. Los precios de sabado y domingo de cripto
    se descartan del grid; los del viernes y el lunes se quedan.

    Consecuencia (que es el objetivo): despues de esto, el retorno del lunes de
    Bitcoin es ln(lunes/viernes) -- abarca el fin de semana entero -- igual que
    el de AAPL. Misma fila, mismo periodo, comparables.

    Lo que se pierde: el viaje de cripto DENTRO del fin de semana. Si el
    mercado esta cerrado, ese viaje de ida y vuelta no toco tu patrimonio del
    lunes; lo que importa es donde amanecio el lunes contra el cierre del
    viernes, y eso si queda capturado.
    """
    mask = dias_de_bolsa(df_precios)
    return df_precios.loc[mask]


# ============================================================
# CAPA 4 — TRANSFORMACIÓN A RETORNOS LOG
# ============================================================

def calcular_retornos_log(df_precios: pd.DataFrame, activos: list) -> pd.DataFrame:
    """Precio -> retorno logaritmico: ln(P_t / P_t-1).

    OJO: esto asume que df_precios YA paso por recortar_a_calendario(), es
    decir, que el indice son solo dias de bolsa. Sobre ese grid, shift(1)
    apunta al dia de bolsa anterior y hace lo correcto para todos:

      - BTC el lunes  -> shift(1) = viernes -> ln(lun/vie), abarca el finde
      - AAPL el lunes -> shift(1) = viernes -> ln(lun/vie), mismo periodo
      - hueco interno (accion suspendida mie y jue): el viernes shift(1)
        apunta a jueves = NaN -> retorno NaN. No inventa nada.

    Si se aplicara sobre el grid CRUDO (con sabados y domingos de cripto),
    shift(1) del lunes apuntaria al domingo, donde las acciones no existen, y
    se destruirian todos los lunes. Ese bug ya nos paso.

    Retorno log y no simple: es aditivo en el tiempo y se porta mejor
    estadisticamente.
    """
    df = df_precios[activos]
    return np.log(df / df.shift(1))


# ============================================================
# CAPA 5 — ALINEACIÓN TEMPORAL
# ============================================================

def alinear_fechas(df_retornos: pd.DataFrame, excluir_fines_de_semana: bool = True) -> pd.DataFrame:
    """Resuelve el problema cripto (7 días) vs acciones (5 días).

    Estrategia: se queda solo con fechas donde TODOS los activos tienen dato
    (inner join real, no solo por índice compartido). Esto automáticamente
    excluye fines de semana, porque ahí las acciones tienen NaN.

    Si excluir_fines_de_semana=False, se hace forward-fill en vez de eliminar
    la fila — útil si algún día quieres conservar el movimiento de cripto
    del fin de semana. Por defecto lo dejamos en False conceptualmente,
    porque para calcular correlación necesitas la fila completa.
    """
    if excluir_fines_de_semana:
        # dropna(how="any") = solo quedan filas donde absolutamente todos
        # los activos tienen retorno calculado ese día
        alineado = df_retornos.dropna(how="any")
    else:
        alineado = df_retornos.ffill().dropna(how="any")

    return alineado


# ============================================================
# CAPA 6 — MATRIZ DE CORRELACIÓN FINAL
# ============================================================

def matriz_correlacion(df_retornos_alineados: pd.DataFrame) -> pd.DataFrame:
    """Correlación de Pearson sobre retornos ya limpios y alineados.
    Esta matriz alimenta directamente la red de riesgo (Louvain, componentes, HRP)."""
    return df_retornos_alineados.corr()


# ============================================================
# ORQUESTADOR — corre las 5 capas en orden
# ============================================================

def preparar_universo() -> dict:
    """Punto de entrada unico. Corre las capas en orden y devuelve todo lo que
    el selector y el analista van a necesitar.

    Orden (el orden importa):
      1. cargar precios crudos
      2. separar invertibles / contexto / redundantes
      3. calendario maestro (solo lo definen los invertibles no-cripto)
      4. validar calidad de los invertibles
      5. retornos log de los invertibles
      6. alinear
      7. correlacion  <- SOLO invertibles
      8. contexto por aparte, con su propia regla de transformacion
    """
    precios = cargar_precios()
    grupos = separar_universo(precios)

    # Calendario maestro. Lo definen SOLO los invertibles no-cripto: una serie
    # de contexto no debe poder alterar que dias existen.
    precios_bolsa = recortar_a_calendario(precios)

    # --- Universo invertible ---
    precios_inv = precios_bolsa[grupos["invertibles"]]
    validacion = validar_calidad(precios_inv)
    activos_validos = validacion["validos"]
    activos_excluidos = validacion["excluidos"]

    retornos_crudos = calcular_retornos_log(precios_bolsa, activos_validos)
    retornos_alineados = alinear_fechas(retornos_crudos)
    correlacion = matriz_correlacion(retornos_alineados)

    # --- Contexto: mismo calendario, transformacion propia, SIN alinear ---
    # No se alinea con dropna(how="any") a proposito: si al VIX le falta un dia
    # no tiene por que costarle ese dia a los 110 invertibles.
    contexto = calcular_contexto(precios_bolsa, grupos["contexto"])
    contexto = contexto.reindex(retornos_alineados.index)

    sector_validos = {t: TICKER_SECTOR.get(t, "Sin clasificar") for t in activos_validos}

    return {
        "retornos": retornos_alineados,
        "correlacion": correlacion,
        "activos_validos": activos_validos,
        "activos_excluidos": activos_excluidos,
        "sector": sector_validos,
        "contexto": contexto,
        "contexto_reglas": {c: CONTEXTO[c] for c in grupos["contexto"]},
        "redundantes_descartados": {c: REDUNDANTES[c] for c in grupos["redundantes"]},
        "dias_alineados": len(retornos_alineados),
        "dias_de_bolsa": len(precios_bolsa),
        "dias_crudos": len(precios),
    }


if __name__ == "__main__":
    resultado = preparar_universo()
    print(f"Activos válidos: {len(resultado['activos_validos'])}")
    print(f"Activos excluidos: {len(resultado['activos_excluidos'])}")
    for ticker, razon in resultado["activos_excluidos"].items():
        print(f"  - {ticker}: {razon}")
    print(f"Días alineados para correlación: {resultado['dias_alineados']}")
    print(f"Forma de la matriz de correlación: {resultado['correlacion'].shape}")