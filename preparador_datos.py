"""
preparador_datos.py
====================
Módulo independiente que toma los precios crudos del recolector y los deja
listos para construir las redes (sectorial y de riesgo).

Flujo: recolector.py (precios.parquet) -> preparador_datos.py -> analista.py

5 capas:
    1. Ingesta      -> cargar_precios()
    2. Validación    -> validar_calidad()
    3. Transformación -> calcular_retornos_log()
    4. Alineación    -> alinear_fechas()
    5. Correlación   -> matriz_correlacion()

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
# CAPA 3 — TRANSFORMACIÓN A RETORNOS LOG
# ============================================================

def calcular_retornos_log(df_precios: pd.DataFrame, activos: list) -> pd.DataFrame:
    """Precio -> retorno logarítmico diario, solo para los activos válidos.
    ln(P_t / P_t-1). Aditivo en el tiempo, mejor comportamiento estadístico
    que el retorno simple."""
    df = df_precios[activos]
    retornos = np.log(df / df.shift(1))
    return retornos


# ============================================================
# CAPA 4 — ALINEACIÓN TEMPORAL
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
# CAPA 5 — MATRIZ DE CORRELACIÓN FINAL
# ============================================================

def matriz_correlacion(df_retornos_alineados: pd.DataFrame) -> pd.DataFrame:
    """Correlación de Pearson sobre retornos ya limpios y alineados.
    Esta matriz alimenta directamente la red de riesgo (Louvain, componentes, HRP)."""
    return df_retornos_alineados.corr()


# ============================================================
# ORQUESTADOR — corre las 5 capas en orden
# ============================================================

def preparar_universo() -> dict:
    """Punto de entrada único. Corre las 5 capas y devuelve todo lo que
    analista.py (o el módulo de redes) va a necesitar."""

    precios = cargar_precios()

    validacion = validar_calidad(precios)
    activos_validos = validacion["validos"]
    activos_excluidos = validacion["excluidos"]

    retornos_crudos = calcular_retornos_log(precios, activos_validos)
    retornos_alineados = alinear_fechas(retornos_crudos)

    correlacion = matriz_correlacion(retornos_alineados)

    sector_validos = {t: TICKER_SECTOR.get(t, "Sin clasificar") for t in activos_validos}

    return {
        "retornos": retornos_alineados,
        "correlacion": correlacion,
        "activos_validos": activos_validos,
        "activos_excluidos": activos_excluidos,
        "sector": sector_validos,
        "dias_alineados": len(retornos_alineados),
    }


if __name__ == "__main__":
    resultado = preparar_universo()
    print(f"Activos válidos: {len(resultado['activos_validos'])}")
    print(f"Activos excluidos: {len(resultado['activos_excluidos'])}")
    for ticker, razon in resultado["activos_excluidos"].items():
        print(f"  - {ticker}: {razon}")
    print(f"Días alineados para correlación: {resultado['dias_alineados']}")
    print(f"Forma de la matriz de correlación: {resultado['correlacion'].shape}")