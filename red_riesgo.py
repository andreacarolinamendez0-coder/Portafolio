"""
red_riesgo.py
=============
Correlacion parcial: separa el riesgo PROPIO del riesgo DE MERCADO.

EL PROBLEMA QUE RESUELVE
------------------------
La correlacion simple no distingue dos cosas muy distintas. Medido en datos
reales de este proyecto:

    XOM y CVX  -> corr simple 0.86  ->  corr PARCIAL 0.06
    JPM y BAC  -> corr simple 0.84  ->  corr PARCIAL 0.26
    MSFT y JPM -> corr simple 0.26  ->  corr PARCIAL -0.08

XOM y CVX parecian gemelas (0.86) pero casi todo eso era "el mercado subio":
sin el mercado no les queda nada en comun (0.06). JPM y BAC si comparten algo
propio (0.26): son el mismo negocio.

De 815 pares con correlacion simple > 0.5, solo 14 mantienen parcial > 0.5.

POR QUE IMPORTA
---------------
El mercado NO paga por el riesgo propio: es diversificable, y lo que se elimina
gratis no tiene prima. Tener NVDA y AMD es cargar el riesgo propio de los
semiconductores DOS VECES sin cobrar por la segunda. Riesgo regalado.

El riesgo sistemico SI lo pagan -- es la prima de riesgo -- y no se puede
esquivar. Por eso el objetivo del motor no es "minimizar riesgo" (eso degenera:
medido sobre este universo da 97.5% en SHY, o sea una cuenta de ahorros) sino
ELIMINAR EL RIESGO QUE NO PAGAN y repartir el que si.

MATEMATICA
----------
Sale de la matriz de PRECISION, la inversa de la covarianza:

    P = Sigma^-1
    corr_parcial(i,j) = -P_ij / sqrt(P_ii * P_jj)

El detalle critico: hay que INVERTIR la covarianza. Con 96 activos esa inversa
amplifica el ruido brutalmente si la matriz esta flaca. Por eso este modulo NO
calcula su propia covarianza: recibe la de covarianza.py, ya ponderada al
reciente y con shrinkage. Sin ese shrinkage la inversa es ficcion numerica.

NOTA HISTORICA: una version anterior usaba Louvain para armar "comunidades" de
activos. Se descarto: la modularidad daba 0.09 (comunidades practicamente
inexistentes) y todo dependia de un umbral arbitrario e inestable. La
correlacion parcial hace el trabajo sin inventar grupos.
"""

import numpy as np
import pandas as pd

UMBRAL_REDUNDANCIA = 0.20   # parcial arriba de esto = comparten riesgo propio
UMBRAL_HEDGE = -0.20        # parcial abajo de esto = se cubren entre si


def matriz_correlacion_parcial(covarianza: pd.DataFrame) -> pd.DataFrame:
    """Covarianza -> correlacion parcial, via la matriz de precision.

    covarianza: DEBE venir regularizada (covarianza.covarianza_robusta()).
                Si le pasas una covarianza muestral cruda, la inversa amplifica
                el ruido y el resultado no significa nada.
    """
    S = covarianza.values

    ev = np.linalg.eigvalsh(S)
    if ev.min() <= 0:
        raise ValueError(
            f"La covarianza no es definida positiva (autovalor min {ev.min():.2e}). "
            "No se puede invertir de forma confiable. Usa covarianza_robusta()."
        )

    P = np.linalg.inv(S)
    d = np.sqrt(np.diag(P))
    C = np.array(-P / np.outer(d, d), copy=True)
    np.fill_diagonal(C, 1.0)

    return pd.DataFrame(C, index=covarianza.index, columns=covarianza.columns)


def _pares(matriz: pd.DataFrame, condicion) -> pd.DataFrame:
    """Pares (i<j) que cumplen la condicion, ordenados por |valor|."""
    n = len(matriz)
    iu = np.triu_indices(n, 1)
    nombres = matriz.index

    filas = [
        {"activo_a": nombres[i], "activo_b": nombres[j], "parcial": round(float(v), 4)}
        for i, j, v in zip(iu[0], iu[1], matriz.values[iu])
        if condicion(v)
    ]
    df = pd.DataFrame(filas)
    if df.empty:
        return pd.DataFrame(columns=["activo_a", "activo_b", "parcial"])
    orden = df["parcial"].abs().sort_values(ascending=False).index
    return df.reindex(orden).reset_index(drop=True)


def identificar_redundancias(corr_parcial, umbral=UMBRAL_REDUNDANCIA) -> pd.DataFrame:
    """Pares que comparten riesgo PROPIO: tener los dos es pagar dos veces."""
    return _pares(corr_parcial, lambda v: v > umbral)


def identificar_hedges(corr_parcial, umbral=UMBRAL_HEDGE) -> pd.DataFrame:
    """Pares con parcial NEGATIVA: se cubren mas alla del mercado.
    Diversificacion genuina, no accidental."""
    return _pares(corr_parcial, lambda v: v < umbral)


def activos_diversificadores(corr_parcial, umbral=UMBRAL_REDUNDANCIA) -> list:
    """Activos sin ningun vinculo propio fuerte con nadie: su riesgo es todo
    suyo. Aportan diversificacion pura."""
    V = corr_parcial.to_numpy(copy=True)
    np.fill_diagonal(V, 0.0)
    maxima = pd.Series(np.abs(V).max(axis=0), index=corr_parcial.index)
    return maxima[maxima < umbral].index.tolist()


def resumen_red(corr_parcial, umbral=UMBRAL_REDUNDANCIA) -> dict:
    """Retrato de la estructura de riesgo propio del universo."""
    V = corr_parcial.to_numpy(copy=True)
    vals = V[np.triu_indices(len(V), 1)]

    return {
        "n_activos": len(corr_parcial),
        "n_pares": len(vals),
        "redundancias": identificar_redundancias(corr_parcial, umbral),
        "hedges": identificar_hedges(corr_parcial, -umbral),
        "diversificadores": activos_diversificadores(corr_parcial, umbral),
        "parcial_media_abs": float(np.nanmean(np.abs(vals))),
        "parcial_maxima": float(np.nanmax(vals)),
        "parcial_minima": float(np.nanmin(vals)),
    }