"""
perfilador.py
=============
Decide ALFA: que fraccion de la plata va al portafolio riesgoso y cuanta al CDT.

    plata_total = alfa * portafolio_riesgoso + (1 - alfa) * CDT

Esta es la decision mas grande de todo el sistema. Todos los usuarios tienen el
MISMO portafolio riesgoso (misma composicion, mismos pesos); lo unico que
cambia entre tu tia y tu primo es alfa. Ella tiene 30% de el, el tiene 70%.
Eso es separacion en dos fondos (Tobin).

ORDEN: este modulo corre DESPUES del motor y de HRP, no antes. Necesita el
sigma del portafolio ya construido, y ese sigma solo existe cuando ya sabes
que activos y con que pesos.

POR QUE TOLERANCIA A LA PERDIDA Y NO MERTON
-------------------------------------------
La formula clasica de Merton es:

    w* = (mu - r) / (gamma * sigma^2)

y depende de mu, que es casi inestimable. Medido sobre este universo, con el
MISMO gamma=5:

    con mu-r = 8%  ->  w* = 86%
    con mu-r = 5%  ->  w* = 54%
    con mu-r = 3%  ->  w* = 32%

El supuesto de retorno DOMINA a la perilla del perfil. La formula de tolerancia
a la perdida no usa mu:

    alfa = L / (1.645 * sigma)

Solo necesita sigma (que se mide con error < 1 punto porcentual) y L (la
perdida que el cliente tolera, que es una DECISION suya, no una estimacion).
Cambiar mu de 8% a 3% no mueve esta formula ni un poco.

El 1.645 es el percentil 5% de la normal: "en el peor año de cada 20".

EL SIGMA VA EN PESOS COLOMBIANOS
--------------------------------
Medido sobre los datos reales: la correlacion entre CUALQUIERA de los 96
activos y la TRM es ~0.017 (rango -0.036 a +0.078). Cero de 96 tienen
correlacion bajo -0.1.

Eso significa que el dolar NO CUBRE nada: el riesgo de la TRM se SUMA limpio.

    sigma^2_COP = sigma^2_USD + sigma^2_TRM + 2*cov   , con cov ~ 0
    SPY:  17.74% en USD  ->  22.33% en COP

Medir en dolares le esconde ~4.6 puntos de volatilidad a un colombiano. Este
modulo calcula sigma sobre la serie del portafolio YA convertida a pesos, sin
suponer nada: se suma el retorno de la TRM al del portafolio y se mide.

EL PLAZO ENTRA COMO TOPE, NO COMO VENTANA DE DATOS
--------------------------------------------------
El plazo NO cambia que activos son buenos ni como se miden. Cambia cuanto
puedes agarrar. Razones medidas:

  - Samuelson (1969): con retornos independientes y utilidad CRRA, la
    asignacion optima NO depende del horizonte. Es un teorema.
  - La escotilla seria la reversion a la media. Se probo con estos datos
    (test de varianza de Lo-MacKinlay): p-valores entre 0.08 y 0.15. Nunca
    significativo. No esta.
  - Con la formula de shortfall y sigma=19%: plazo 1 año -> alfa 62%;
    plazo 10 años -> alfa 61%. Un punto de diferencia.

Lo unico real es la LIQUIDEZ: si necesitas la plata en una fecha cierta y
cercana, no puedes exponerla. Eso es un tope duro, no una perilla estadistica.
Los topes de TOPES_POR_PLAZO son un JUICIO, no una derivacion, y estan puestos
para que los discutas y los cambies.
"""

import numpy as np
import pandas as pd

Z_95 = 1.645          # percentil 5% de la normal estandar
DIAS_TRADING_ANIO = 252

# Topes de alfa segun cuando necesitas la plata.
# ESTO ES UN JUICIO, NO UNA FORMULA. Ver el docstring: el efecto estadistico
# del plazo es ~1 punto. Estos topes son prudencia de liquidez, no matematica.
TOPES_POR_PLAZO = {
    1: 0.00,    # la necesitas este año -> no la expongas
    2: 0.30,
    3: 0.50,
    5: 0.75,
    99: 1.00,   # 6+ años -> sin tope
}


def tope_por_plazo(anios: float) -> float:
    """Tope duro de alfa segun el horizonte. Es prudencia de liquidez."""
    for limite in sorted(TOPES_POR_PLAZO):
        if anios <= limite:
            return TOPES_POR_PLAZO[limite]
    return 1.0


def serie_portafolio(pesos: pd.Series, retornos: pd.DataFrame) -> pd.Series:
    """Retorno diario del portafolio riesgoso, en la moneda de `retornos`."""
    activos = list(pesos.index)
    w = pesos.values
    return (retornos[activos] * w).sum(axis=1)


def sigma_en_pesos(
    pesos: pd.Series,
    retornos: pd.DataFrame,
    retorno_trm: pd.Series,
) -> dict:
    """Volatilidad anualizada del portafolio EN PESOS COLOMBIANOS.

    En retornos logaritmicos la conversion es una identidad exacta:

        r_COP = r_USD + r_TRM

    No se supone nada sobre la correlacion: se construye la serie en pesos y se
    mide. Devuelve tambien el desglose para que puedas ver cuanto aporta la TRM.
    """
    p_usd = serie_portafolio(pesos, retornos)
    df = pd.concat([p_usd.rename("usd"), retorno_trm.rename("trm")], axis=1).dropna()

    if len(df) < 60:
        raise ValueError(
            f"Solo {len(df)} dias en comun entre el portafolio y la TRM. "
            "Revisa que la TRM cubra el mismo periodo."
        )

    raiz = np.sqrt(DIAS_TRADING_ANIO)
    s_usd = float(df["usd"].std() * raiz)
    s_trm = float(df["trm"].std() * raiz)
    s_cop = float((df["usd"] + df["trm"]).std() * raiz)
    corr = float(df["usd"].corr(df["trm"]))

    return {
        "sigma_cop": s_cop,
        "sigma_usd": s_usd,
        "sigma_trm": s_trm,
        "corr_portafolio_trm": corr,
        "aporte_trm_pp": (s_cop - s_usd) * 100,
        "dias": len(df),
    }


def calcular_alfa(
    perdida_tolerada: float,
    sigma_cop: float,
    anios_horizonte: float = 99,
) -> dict:
    """Alfa = fraccion al portafolio riesgoso.

        alfa_tolerancia = L / (1.645 * sigma)
        alfa            = min(alfa_tolerancia, tope_por_plazo, 1.0)

    perdida_tolerada: fraccion positiva. 0.15 = "aguanto perder 15% en un año
                      malo sin vender".
    """
    if not 0 < perdida_tolerada < 1:
        raise ValueError("perdida_tolerada debe estar entre 0 y 1 (0.15 = 15%)")
    if sigma_cop <= 0:
        raise ValueError("sigma_cop debe ser positivo")

    a_tol = perdida_tolerada / (Z_95 * sigma_cop)
    a_plazo = tope_por_plazo(anios_horizonte)
    alfa = min(a_tol, a_plazo, 1.0)

    manda = "tolerancia"
    if a_plazo < a_tol and a_plazo < 1.0:
        manda = "plazo"
    elif a_tol >= 1.0 and a_plazo >= 1.0:
        manda = "tope del 100%"

    return {
        "alfa": alfa,
        "alfa_por_tolerancia": a_tol,
        "alfa_por_plazo": a_plazo,
        "restriccion_que_manda": manda,
        "en_cdt": 1.0 - alfa,
    }


def perfilar(
    pesos: pd.Series,
    retornos: pd.DataFrame,
    retorno_trm: pd.Series,
    perdida_tolerada: float,
    anios_horizonte: float = 99,
    cdt_nominal: float = None,
    inflacion_col: float = None,
    capital: float = None,
) -> dict:
    """Punto de entrada. Mide sigma en pesos, calcula alfa y arma el reporte.

    cdt_nominal / inflacion_col: opcionales, como fracciones (0.1125 = 11.25%).
        Si los pasas, se calcula el CDT REAL y se agrega una ADVERTENCIA sobre
        que tan flaca es la prima de riesgo. No cambian el alfa -- solo informan.

    capital: opcional. Si lo pasas, el reporte muestra los montos en pesos, que
        es como hay que preguntarle a una persona de verdad. Esta documentado
        que la gente dice tolerar 20% y vende en panico al 12%; los porcentajes
        no se sienten, los pesos si.
    """
    riesgo = sigma_en_pesos(pesos, retornos, retorno_trm)
    a = calcular_alfa(perdida_tolerada, riesgo["sigma_cop"], anios_horizonte)

    rep = {**a, "riesgo": riesgo}

    if cdt_nominal is not None and inflacion_col is not None:
        cdt_real = (1 + cdt_nominal) / (1 + inflacion_col) - 1
        rep["cdt_real"] = cdt_real
        rep["advertencia_cdt"] = (
            f"El CDT paga {cdt_real:.1%} real sin riesgo. El retorno real de "
            f"largo plazo de las acciones ronda 5-7%, asi que la prima que te "
            f"queda por asumir {riesgo['sigma_cop']:.1%} de volatilidad es de "
            f"apenas {0.055 - cdt_real:+.1%}. Esto puede cambiar cuando bajen "
            f"las tasas: hoy Banrep esta restrictivo peleando la inflacion."
        )

    if capital is not None:
        monto_riesgoso = capital * a["alfa"]
        perdida_pesos = capital * perdida_tolerada
        rep["montos"] = {
            "capital": capital,
            "al_portafolio": monto_riesgoso,
            "al_cdt": capital - monto_riesgoso,
            "perdida_tolerada_pesos": perdida_pesos,
            "pregunta_de_confirmacion": (
                f"Vas a poner ${monto_riesgoso:,.0f} en el mercado. En un mal "
                f"año (1 de cada 20) esos ${capital:,.0f} se vuelven "
                f"${capital - perdida_pesos:,.0f}. ¿Aguantas sin vender?"
            ),
        }

    return rep