"""
red_riesgo.py
=============
Capa de RIESGO del portafolio basada en CORRELACIÓN PARCIAL.

Por qué correlación parcial y no correlación simple:
  La correlación simple entre dos activos mezcla dos cosas:
    - riesgo SISTÉMICO (de mercado): ambos caen porque cae todo el mercado.
      Esto NO se diversifica, se sobrevive con horizonte y con clases de
      activo distintas.
    - riesgo NO SISTÉMICO (específico): vínculo propio entre los dos activos,
      más allá del mercado. ESTO sí se diversifica, y es lo único que está
      en nuestras manos.
  La correlación parcial descuenta el efecto del mercado (y de todos los demás
  activos) y deja solo el vínculo directo. Es, en la práctica, un medidor de
  riesgo NO sistémico compartido — justo lo que queremos no duplicar.

  Ejemplo real (datos de Andrea):
    MSFT-JPM  -> correlación simple 0.26, parcial -0.08  (sin vínculo propio)
    JPM-BAC   -> correlación simple 0.84, parcial  0.26  (mismo negocio bancario)
    XOM-CVX   -> correlación simple 0.86, parcial  0.06  (solo mercado, no propio)
  De 815 pares con correlación simple > 0.5, solo 14 mantienen parcial > 0.5:
  el resto era puro riesgo de mercado.

Método de cálculo:
  Se estima la matriz de precisión (inversa de la covarianza) con shrinkage
  Ledoit-Wolf, que regulariza la inversión y la vuelve numéricamente estable
  incluso con muchos activos correlacionados. La correlación parcial se deriva
  de esa matriz de precisión.

Uso típico:
    from preparador_datos import preparar_universo
    from red_riesgo import (
        matriz_correlacion_parcial, identificar_redundancias,
        identificar_hedges, activos_diversificadores
    )

    datos = preparar_universo()
    pc = matriz_correlacion_parcial(datos["retornos"])

    redundantes = identificar_redundancias(pc, umbral=0.2)
    hedges = identificar_hedges(pc, umbral=0.2)
    diversificadores = activos_diversificadores(pc, umbral=0.2)
"""

import numpy as np
import pandas as pd
import networkx as nx
from sklearn.covariance import LedoitWolf


UMBRAL_DEFAULT = 0.2


# ============================================================
# CÁLCULO DE LA CORRELACIÓN PARCIAL
# ============================================================

def matriz_correlacion_parcial(retornos: pd.DataFrame) -> pd.DataFrame:
    """Correlación parcial regularizada (Ledoit-Wolf) entre todos los activos.

    retornos: DataFrame de retornos log diarios, ya limpio y alineado
              (el que produce preparador_datos.py).

    Devuelve una matriz simétrica con la correlación parcial de cada par.
    Diagonal = 1.0.

    Interpretación del signo:
      parcial > 0  -> comparten riesgo NO sistémico (vínculo propio; redundancia)
      parcial < 0  -> cobertura natural (se protegen entre sí)
      parcial ~ 0  -> sin vínculo propio (su co-movimiento era solo de mercado)
    """
    X = retornos.values

    # Matriz de precisión = inversa regularizada de la covarianza.
    # El shrinkage de Ledoit-Wolf estabiliza la inversión (evita el problema
    # de matriz casi-singular con activos muy correlacionados).
    lw = LedoitWolf().fit(X)
    precision = lw.precision_

    # Correlación parcial a partir de la precisión:
    #   pc_ij = -P_ij / sqrt(P_ii * P_jj)
    d = np.sqrt(np.diag(precision))
    pc = -precision / np.outer(d, d)
    np.fill_diagonal(pc, 1.0)

    return pd.DataFrame(pc, index=retornos.columns, columns=retornos.columns)


def shrinkage_aplicado(retornos: pd.DataFrame) -> float:
    """Devuelve el coeficiente de shrinkage que Ledoit-Wolf necesitó.
    Cercano a 0 = datos sanos, la parcial es confiable.
    Cercano a 1 = datos ruidosos/pocos, la parcial se apoyó mucho en la
    regularización (interpretar con cautela)."""
    lw = LedoitWolf().fit(retornos.values)
    return float(lw.shrinkage_)


# ============================================================
# IDENTIFICACIÓN DE PARES
# ============================================================

def identificar_redundancias(corr_parcial: pd.DataFrame, umbral: float = UMBRAL_DEFAULT) -> list:
    """Pares con correlación parcial POSITIVA >= umbral: comparten riesgo
    NO sistémico, son redundantes en el sentido que importa para diversificar.

    Devuelve lista de (activo1, activo2, parcial), ordenada de mayor a menor
    (el más redundante primero)."""
    pares = []
    tickers = corr_parcial.columns.tolist()
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            pc = corr_parcial.loc[a, b]
            if pd.notna(pc) and pc >= umbral:
                pares.append((a, b, float(pc)))
    pares.sort(key=lambda x: x[2], reverse=True)
    return pares


def identificar_hedges(corr_parcial: pd.DataFrame, umbral: float = UMBRAL_DEFAULT) -> list:
    """Pares con correlación parcial NEGATIVA <= -umbral: cobertura natural.
    El Analista los usa al revés — si tienes uno, el otro te protege.

    Devuelve lista de (activo1, activo2, parcial), ordenada de más negativo
    a menos (la mejor cobertura primero)."""
    pares = []
    tickers = corr_parcial.columns.tolist()
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            pc = corr_parcial.loc[a, b]
            if pd.notna(pc) and pc <= -umbral:
                pares.append((a, b, float(pc)))
    pares.sort(key=lambda x: x[2])  # más negativo primero
    return pares


def activos_diversificadores(corr_parcial: pd.DataFrame, umbral: float = UMBRAL_DEFAULT) -> list:
    """Activos SIN ningún vínculo propio (positivo o negativo) por encima del
    umbral con nadie. Su riesgo es puramente idiosincrático o de mercado, pero
    no comparten riesgo NO sistémico con ningún otro activo del universo.

    Son diversificadores puros: agregarlos no duplica el riesgo específico de
    nada más. (En los datos de Andrea: DBC y SHY a umbral 0.15.)"""
    tickers = corr_parcial.columns.tolist()
    diversificadores = []
    for a in tickers:
        tiene_vinculo = False
        for b in tickers:
            if a == b:
                continue
            pc = corr_parcial.loc[a, b]
            if pd.notna(pc) and abs(pc) >= umbral:
                tiene_vinculo = True
                break
        if not tiene_vinculo:
            diversificadores.append(a)
    return diversificadores


# ============================================================
# GRAFO (para visualización / análisis estructural)
# ============================================================

def construir_grafo_parcial(corr_parcial: pd.DataFrame, umbral: float = UMBRAL_DEFAULT) -> nx.Graph:
    """Grafo de riesgo no sistémico: un nodo por activo, una arista si la
    correlación parcial (en valor absoluto) supera el umbral. El peso guarda
    el valor con signo (positivo = riesgo compartido, negativo = cobertura).

    Los activos sin vínculo (diversificadores) quedan como nodos aislados."""
    G = nx.Graph()
    G.add_nodes_from(corr_parcial.columns)

    tickers = corr_parcial.columns.tolist()
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            pc = corr_parcial.loc[a, b]
            if pd.notna(pc) and abs(pc) >= umbral:
                G.add_edge(a, b, weight=float(pc))

    return G


# ============================================================
# RESUMEN RÁPIDO
# ============================================================

def resumen_red(corr_parcial: pd.DataFrame, umbral: float = UMBRAL_DEFAULT) -> dict:
    """Panorama rápido de la red a un umbral dado."""
    redundantes = identificar_redundancias(corr_parcial, umbral)
    hedges = identificar_hedges(corr_parcial, umbral)
    diversificadores = activos_diversificadores(corr_parcial, umbral)

    return {
        "umbral": umbral,
        "n_redundancias": len(redundantes),
        "n_hedges": len(hedges),
        "n_diversificadores": len(diversificadores),
        "diversificadores": diversificadores,
        "top_redundancias": redundantes[:10],
        "top_hedges": hedges[:10],
    }


if __name__ == "__main__":
    # Prueba con datos sintéticos: dos activos con vínculo propio fuerte y
    # el resto solo ligado por un factor de mercado común.
    np.random.seed(0)
    n = 800
    mercado = np.random.randn(n)
    tickers = [f"A{i}" for i in range(8)]
    data = {}
    for t in tickers:
        data[t] = 0.6 * mercado + np.random.randn(n)
    # Vínculo propio fuerte entre A0 y A1 (más allá del mercado)
    data["A1"] = data["A1"] + 0.8 * data["A0"]
    df = pd.DataFrame(data)

    pc = matriz_correlacion_parcial(df)
    print("Shrinkage:", round(shrinkage_aplicado(df), 4))
    print("\nRedundancias (parcial > 0.2):")
    for a, b, v in identificar_redundancias(pc, 0.2):
        print(f"  {a}-{b}: {v:.2f}")
    print("\nDiversificadores:", activos_diversificadores(pc, 0.2))