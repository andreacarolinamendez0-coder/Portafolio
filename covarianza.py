"""
covarianza.py
=============
Estimacion de la matriz de covarianza con ponderacion exponencial hacia el
pasado reciente, mas shrinkage.

POR QUE PONDERAR AL RECIENTE
----------------------------
La volatilidad se agrupa en racimos: periodos turbulentos siguen a periodos
turbulentos (Engle, 1982 -- Nobel 2003). El riesgo de HOY se parece mas al de
hace un mes que al promedio de los ultimos 5 años.

Medido sobre los datos reales de este proyecto (96 activos, 1296 dias,
prediccion a 126 dias, 32 ventanas rodando):

    vida media    T_eff/N    err VOL    err CORR
    21 dias          0.6      5.717%     0.1713
    63 dias          1.9      5.390%     0.1559
    126 dias         3.7      5.477%     0.1492   <- elegida
    252 dias         6.0      6.034%     0.1540
    504 dias         7.7      6.735%     0.1650
    equiponderada    8.6      7.895%     0.1832   <- la PEOR

La equiponderada (el default de pandas/numpy, y lo que usaba este proyecto)
es la peor de todas: 46% mas error en volatilidad que la mejor.

POR QUE 126 DIAS Y NO 63
------------------------
63 dias gana en volatilidad, pero deja T_eff = 182 para 96 activos (T_eff/N =
1.9). La correlacion parcial exige INVERTIR esa matriz; con 1.9 observaciones
efectivas por activo la inversa es ruido amplificado. 126 dias da T_eff/N =
3.7, gana en correlaciones (que es lo que mas usan la parcial y HRP) y queda a
1.6% del mejor en volatilidad.

OJO: NO es "usar solo los ultimos 126 dias". Entran TODOS los dias; los de hace
126 pesan la mitad que los de hoy, los de hace 252 pesan un cuarto, y asi. Nada
se bota. Esa es la diferencia entre enfatizar lo reciente y truncar la historia:
truncar te deja en T/N = 1.3 y rompe la matriz.

EL PLAZO DE INVERSION NO TOCA ESTO
----------------------------------
Esta ponderacion se usa SIEMPRE, para todos los perfiles y todos los plazos.
No es una concesion al inversionista de corto plazo: es simplemente una mejor
medicion del riesgo actual. El riesgo de NVDA hoy es el que es, sin importar
cuanto tiempo pienses tenerlo. El plazo decide CUANTO agarras (el alfa), no
con que termometro mides.
"""

import numpy as np
import pandas as pd

VIDA_MEDIA_DEFECTO = 126  # dias; calibrado empiricamente, ver docstring


def pesos_exponenciales(n_obs: int, vida_media: float = VIDA_MEDIA_DEFECTO) -> np.ndarray:
    """Pesos que decaen exponencialmente hacia el pasado, normalizados a sumar 1.

    vida_media: dias hacia atras donde el peso cae a la mitad.
                None -> pesos iguales (equiponderado).
    """
    if vida_media is None:
        w = np.ones(n_obs)
    else:
        if vida_media <= 0:
            raise ValueError("vida_media debe ser positiva")
        lam = 0.5 ** (1.0 / vida_media)
        # el ultimo dato (mas reciente) pesa 1; hacia atras decae
        w = lam ** np.arange(n_obs - 1, -1, -1)
    return w / w.sum()


def tamano_efectivo(pesos: np.ndarray) -> float:
    """Numero EFECTIVO de observaciones: 1 / sum(w^2).

    Con pesos iguales da n. Con pesos exponenciales da (1+lam)/(1-lam), que es
    bastante menos. Es el costo escondido de ponderar: ganas reactividad y
    pierdes muestra. Si T_efectivo / n_activos es chico, la matriz no se puede
    invertir de forma confiable.
    """
    return float(1.0 / np.sum(pesos ** 2))


def covarianza_ewma(
    retornos: pd.DataFrame,
    vida_media: float = VIDA_MEDIA_DEFECTO,
) -> dict:
    """Covarianza con ponderacion exponencial, SIN shrinkage.

    Devuelve dict con la matriz, los pesos, T_efectivo y T_efectivo/N.
    """
    X = retornos.values
    T, N = X.shape
    w = pesos_exponenciales(T, vida_media)

    mu = (w[:, None] * X).sum(axis=0)      # media ponderada
    Xc = X - mu
    S = (Xc * w[:, None]).T @ Xc           # covarianza ponderada

    T_eff = tamano_efectivo(w)
    return {
        "covarianza": pd.DataFrame(S, index=retornos.columns, columns=retornos.columns),
        "pesos": w,
        "T_efectivo": T_eff,
        "T_efectivo_sobre_N": T_eff / N,
        "vida_media": vida_media,
    }


def _objetivo_correlacion_constante(S: np.ndarray) -> np.ndarray:
    """Matriz objetivo de Ledoit-Wolf (2004): misma varianza de cada activo,
    pero TODAS las correlaciones iguales al promedio.

    Es el objetivo correcto para portafolios: conserva las volatilidades
    individuales (que se miden bien) y solo regulariza las correlaciones (que
    se miden mal). Un objetivo diagonal seria peor: asumiria correlacion cero,
    que es falso y destruiria la informacion de diversificacion.
    """
    d = np.sqrt(np.diag(S))
    C = np.array(S / np.outer(d, d), copy=True)
    n = C.shape[0]
    iu = np.triu_indices(n, 1)
    c_bar = C[iu].mean()
    C_obj = np.full((n, n), c_bar)
    np.fill_diagonal(C_obj, 1.0)
    return C_obj * np.outer(d, d)


def covarianza_robusta(
    retornos: pd.DataFrame,
    vida_media: float = VIDA_MEDIA_DEFECTO,
    shrinkage: float = None,
) -> dict:
    """Covarianza EWMA + shrinkage hacia correlacion constante.

    S_final = (1 - delta) * S_ewma + delta * S_objetivo

    Por que hace falta shrinkage ADEMAS de la ponderacion: al ponderar bajamos
    T_efectivo (de 830 a 351 con vida media 126), asi que la matriz queda mas
    flaca de lo que aparenta y su inversa -- que es lo que necesita la
    correlacion parcial -- se vuelve inestable. El shrinkage la endereza.

    shrinkage: None -> se estima con la regla de Ledoit-Wolf adaptada a los
               pesos. Un numero entre 0 y 1 lo fija a mano.
    """
    base = covarianza_ewma(retornos, vida_media)
    S = base["covarianza"].values
    X = retornos.values
    T, N = X.shape
    w = base["pesos"]

    S_obj = _objetivo_correlacion_constante(S)

    if shrinkage is None:
        # Ledoit-Wolf: delta ~ (dispersion de la estimacion) / (distancia al objetivo)
        # Adaptado a pesos: T se reemplaza por T_efectivo.
        mu = (w[:, None] * X).sum(axis=0)
        Xc = X - mu
        T_eff = base["T_efectivo"]

        # pi: varianza de los elementos de S
        pi_mat = np.zeros((N, N))
        for i in range(T):
            d = np.outer(Xc[i], Xc[i]) - S
            pi_mat += w[i] * d ** 2
        pi = pi_mat.sum()

        # gamma: distancia al cuadrado entre S y el objetivo
        gamma = np.sum((S_obj - S) ** 2)

        delta = 0.0 if gamma <= 0 else float(np.clip((pi / T_eff) / gamma, 0.0, 1.0))
    else:
        delta = float(np.clip(shrinkage, 0.0, 1.0))

    S_final = (1 - delta) * S + delta * S_obj

    return {
        "covarianza": pd.DataFrame(S_final, index=retornos.columns, columns=retornos.columns),
        "shrinkage": delta,
        "T_efectivo": base["T_efectivo"],
        "T_efectivo_sobre_N": base["T_efectivo_sobre_N"],
        "vida_media": vida_media,
    }


def matriz_correlacion_desde_cov(S: pd.DataFrame) -> pd.DataFrame:
    """Covarianza -> correlacion."""
    d = np.sqrt(np.diag(S.values))
    C = np.array(S.values / np.outer(d, d), copy=True)
    np.fill_diagonal(C, 1.0)
    return pd.DataFrame(C, index=S.index, columns=S.columns)