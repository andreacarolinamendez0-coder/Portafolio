"""
ponderador.py
=============
HRP (Hierarchical Risk Parity) — Lopez de Prado, 2016.

Decide CUANTO va a cada activo ya seleccionado. No decide quien entra (eso es
motor_seleccion.py) ni cuanto va a lo seguro (eso es perfilador.py).

POR QUE HRP Y NO UN OPTIMIZADOR
-------------------------------
Un optimizador (Markowitz, minima varianza) resuelve un problema de esquina: le
das una funcion objetivo y va al maximo, aunque el maximo sea absurdo. Medido
sobre este universo:

    minimizar semivarianza  ->  97.5% en SHY.  N efectivo = 1.1
    minimizar varianza      ->  91.9% en bonos. N efectivo = 2.7
    HRP                     ->  58.5% en bonos. N efectivo = 8.6

Los tres son metodos "sin mu". La diferencia es que HRP NO OPTIMIZA: aplica una
regla fija de biseccion bajando por un arbol. Un reparto proporcional nunca
puede darle 100% a un lado -- cada hoja recibe algo por construccion.

Pero OJO: HRP tiene la misma gravedad hacia los bonos, solo mas debil (58.5%
sigue siendo mucho). Por eso la cobertura por sector de motor_seleccion.py NO
es opcional: es lo que frena esa gravedad antes de que HRP pondere.

POR QUE CORRELACION SIMPLE Y NO PARCIAL
---------------------------------------
Deliberado. Para SELECCIONAR importa el porque (parcial): no quieres pagar dos
veces por el mismo riesgo propio. Para PONDERAR importa cuanto pierdes si caen
juntos, sin importar por que caen juntos. Si dos activos se hunden a la vez, tu
plata se hunde igual sea por el mercado o por su negocio. Ahi manda la simple.

LOS TRES PASOS
--------------
1. Clustering jerarquico: agrupa por distancia d = sqrt(0.5*(1-corr))
2. Quasi-diagonalizacion: reordena para que los parecidos queden juntos
3. Biseccion recursiva: baja por el arbol repartiendo por varianza inversa
"""

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, to_tree
from scipy.spatial.distance import squareform


def _distancia(corr: pd.DataFrame) -> np.ndarray:
    """Correlacion -> distancia metrica: d = sqrt(0.5 * (1 - corr)).

    Es una metrica de verdad (cumple la desigualdad triangular), no un invento:
    corr=1 -> d=0 (identicos), corr=0 -> d=0.707, corr=-1 -> d=1 (opuestos).
    """
    d = np.sqrt(np.clip(0.5 * (1.0 - corr.values), 0.0, None))
    np.fill_diagonal(d, 0.0)
    d = (d + d.T) / 2.0          # forzar simetria exacta contra ruido numerico
    return d


def _orden_quasidiagonal(nodo) -> list:
    """Recorre el arbol y devuelve las hojas en orden: los parecidos quedan
    adyacentes. Es lo que permite que la biseccion corte por grupos reales."""
    if nodo.is_leaf():
        return [nodo.id]
    return _orden_quasidiagonal(nodo.get_left()) + _orden_quasidiagonal(nodo.get_right())


def _varianza_cluster(cov: np.ndarray, idx: list) -> float:
    """Varianza de un sub-cluster ponderado por varianza inversa."""
    sub = cov[np.ix_(idx, idx)]
    ivp = 1.0 / np.diag(sub)
    ivp /= ivp.sum()
    return float(ivp @ sub @ ivp)


def _biseccion(cov: np.ndarray, orden: list) -> np.ndarray:
    """Biseccion recursiva: baja por el arbol partiendo cada grupo en dos y
    repartiendo entre las mitades segun su varianza inversa.

        alpha = 1 - var(izq) / (var(izq) + var(der))

    La mitad menos volatil recibe MAS, pero nunca TODO: por eso no degenera.
    """
    n = cov.shape[0]
    w = np.ones(n)
    grupos = [list(range(n))]

    while grupos:
        nuevos = []
        for g in grupos:
            if len(g) <= 1:
                continue
            mitad = len(g) // 2
            izq, der = g[:mitad], g[mitad:]
            v_izq = _varianza_cluster(cov, izq)
            v_der = _varianza_cluster(cov, der)
            alpha = 1.0 - v_izq / (v_izq + v_der)
            for i in izq:
                w[i] *= alpha
            for i in der:
                w[i] *= (1.0 - alpha)
            nuevos += [izq, der]
        grupos = nuevos

    return w


def ponderar_hrp(
    covarianza: pd.DataFrame,
    metodo_linkage: str = "average",
) -> dict:
    """HRP sobre una covarianza ya estimada.

    covarianza: la de covarianza.covarianza_robusta(), restringida a los
                activos seleccionados. Ponderada al reciente y con shrinkage.

    metodo_linkage: 'average' por defecto, NO 'single'. El single linkage sufre
                    de chaining (encadena clusters por un solo vecino cercano y
                    arma cadenas largas sin sentido). Lopez de Prado usa single
                    en el paper original; average es mas robusto en la practica.
    """
    activos = list(covarianza.index)
    n = len(activos)
    if n == 1:
        return {"pesos": pd.Series([1.0], index=activos), "orden": activos}

    d = np.sqrt(np.diag(covarianza.values))
    C = np.array(covarianza.values / np.outer(d, d), copy=True)
    np.fill_diagonal(C, 1.0)
    corr = pd.DataFrame(C, index=activos, columns=activos)

    dist = _distancia(corr)
    Z = linkage(squareform(dist, checks=False), method=metodo_linkage)
    raiz = to_tree(Z)
    orden = _orden_quasidiagonal(raiz)

    cov_ord = covarianza.values[np.ix_(orden, orden)]
    w_ord = _biseccion(cov_ord, list(range(n)))

    pesos = pd.Series(0.0, index=activos)
    for pos, i in enumerate(orden):
        pesos.iloc[i] = w_ord[pos]
    pesos /= pesos.sum()

    return {
        "pesos": pesos.sort_values(ascending=False),
        "orden": [activos[i] for i in orden],
        "linkage": Z,
        "n_efectivo": float(1.0 / (pesos ** 2).sum()),
    }


def pesos_iguales(activos: list) -> pd.Series:
    """1/N. Comparador: DeMiguel et al. (2009) mostraron que le gana a muchos
    optimizadores fuera de muestra. Si HRP no le gana a esto, HRP no sirve."""
    return pd.Series(1.0 / len(activos), index=activos)


def pesos_varianza_inversa(covarianza: pd.DataFrame) -> pd.Series:
    """Varianza inversa sin clustering. Comparador: aisla cuanto aporta el
    arbol de HRP por encima de solo mirar volatilidades."""
    ivp = 1.0 / np.diag(covarianza.values)
    ivp /= ivp.sum()
    return pd.Series(ivp, index=covarianza.index).sort_values(ascending=False)


def volatilidad_portafolio(pesos: pd.Series, covarianza: pd.DataFrame,
                           dias: int = 252) -> float:
    """Volatilidad ANUALIZADA del portafolio. w' Sigma w."""
    w = pesos.reindex(covarianza.index).values
    return float(np.sqrt(w @ covarianza.values @ w) * np.sqrt(dias))