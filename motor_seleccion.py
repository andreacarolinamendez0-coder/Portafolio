"""
motor_seleccion.py
==================
Decide QUE activos entran al portafolio riesgoso. No decide pesos (eso es
ponderador.py) ni cuanto va a lo seguro (eso es perfilador.py).

EL PIPELINE
-----------
    1. Sortino sobre el HISTORICO COMPLETO  -> purga el peor 30%
    2. Correlacion parcial                  -> purga redundancias
    3. Cobertura por sector                 -> el mejor de cada sector

DONDE SE USA mu Y DONDE NO
--------------------------
Este es el unico modulo del motor que toca mu (retornos esperados), y lo hace
con cuidado, porque mu es casi inestimable. Medido sobre los datos reales:

    NVDA: mu = 46.7%, intervalo de confianza 95% = [12.4% , 81.1%]
    KO  : mu = 11.4%, intervalo 95% = [-1.4% , 24.2%]  <- ni el signo se sabe

    Años necesarios para que SE(mu) baje a 1 punto porcentual:
        NVDA 2,386 años | MSFT 732 años | KO 332 años

La razon es estructural, no de calidad de datos:

    SE(mu)    = sigma / sqrt(AÑOS)          <- solo mejora esperando
    SE(sigma) = sigma / sqrt(2 * OBS)       <- mejora midiendo mas seguido

Por eso mu solo se usa para una pregunta GRUESA ("¿esta en el tercio de
abajo?") y nunca para una FINA ("¿cual es el mejor?"). Con +-29% de error, la
gruesa sobrevive y la fina no.

VENTANA: Sortino usa TODO el historico. Medido: usar los ultimos 12 meses
empeora la prediccion del retorno futuro en 15.6%, y el ranking solo coincide
en 17/29 con el de largo plazo. Lo reciente ayuda al RIESGO (ver covarianza.py)
pero perjudica al RETORNO.
"""

import numpy as np
import pandas as pd

DIAS_TRADING_ANIO = 252


# ============================================================
# METRICAS
# ============================================================

def calcular_sortino(retornos: pd.DataFrame, mar_anual: float = 0.0) -> pd.Series:
    """Sortino anualizado por activo, sobre retornos log diarios.

        Sortino = (retorno medio anual - MAR) / desviacion downside anual

    Por que Sortino y no Sharpe: Sharpe castiga la volatilidad hacia ARRIBA
    igual que hacia abajo. A nadie le molesta ganar de mas.

    mar_anual: Minimum Acceptable Return anual, como fraccion (0.045 = 4.5%).
        Define que significa FRACASAR, y eso cambia la lista entera. Medido:
            MAR = 0%     -> gana SHY (nunca pierde plata, downside ~0)
            MAR = 4.5%   -> SHY desaparece, ganan LLY, LIN, NVDA
        Para el sobre RIESGOSO, MAR debe ser la tasa libre de riesgo: la
        seguridad ya la maneja el alfa del perfilador. Si el sobre riesgoso
        tambien trae SHY, tienes seguridad dos veces.

        AVISO DE UNIDADES: el MAR debe estar en la MISMA moneda y base que los
        retornos. Retornos en USD nominal -> MAR en USD nominal. Pasarle un CDT
        colombiano a retornos gringos es restar peras de manzanas.

    Detalle que casi todas las implementaciones equivocan: la desviacion
    downside divide entre TODAS las observaciones (Sortino & Price, 1994), no
    solo entre los dias negativos.

    Devuelve NaN (no infinito) si el activo nunca cayo bajo el MAR.
    """
    mar_diario = np.log1p(mar_anual) / DIAS_TRADING_ANIO
    exceso = retornos - mar_diario

    downside = np.minimum(exceso, 0.0)
    dd_anual = np.sqrt((downside ** 2).mean()) * np.sqrt(DIAS_TRADING_ANIO)

    exceso_anual = exceso.mean() * DIAS_TRADING_ANIO
    sortino = exceso_anual / dd_anual.replace(0.0, np.nan)
    return sortino.sort_values(ascending=False)


def calcular_sharpe(retornos: pd.DataFrame, tasa_libre_anual: float = 0.0) -> pd.Series:
    """Sharpe anualizado. Se conserva SOLO para comparar. El motor no lo usa."""
    mu = retornos.mean() * DIAS_TRADING_ANIO
    vol = retornos.std() * np.sqrt(DIAS_TRADING_ANIO)
    return ((mu - tasa_libre_anual) / vol).sort_values(ascending=False)


# ============================================================
# PASO 1 — PURGA POR SORTINO
# ============================================================

def purgar_peores(
    retornos: pd.DataFrame,
    fraccion: float = 0.30,
    mar_anual: float = 0.0,
) -> dict:
    """Elimina la peor `fraccion` del universo por Sortino.

    Por que purgar por abajo y no elegir por arriba: ver el docstring del
    modulo. En resumen, "¿esta en el tercio de abajo?" es una pregunta que mu
    puede responder pese a su ruido; "¿cual es el mejor?" no lo es.

    OJO CON EL PERCENTIL: purgar el 30% NO separa buenos de malos, corta por un
    percentil. Medido con MAR=0 sobre los 96 activos: de los 29 purgados, solo
    4 tenian Sortino negativo (PFE, NKE, BA, DIS). Los otros 25 estaban entre
    0.17 y 0.63 -- positivos, solo mas abajo. Si quieres purgar solo a los que
    de verdad pierden contra el MAR, usa `purgar_negativos()`.

    Los activos con Sortino NaN (nunca cayeron bajo el MAR) NO se purgan: no hay
    evidencia de que sean malos. Se conservan y se reportan aparte.
    """
    if not 0.0 <= fraccion < 1.0:
        raise ValueError("fraccion debe estar entre 0 y 1")

    sortino = calcular_sortino(retornos, mar_anual)
    sin_ratio = sortino[sortino.isna()].index.tolist()
    con_ratio = sortino.dropna()

    n_fuera = int(round(len(con_ratio) * fraccion))
    if n_fuera == 0:
        return {
            "sobreviven": con_ratio.index.tolist() + sin_ratio,
            "eliminados": pd.DataFrame(columns=["activo", "sortino"]),
            "sin_ratio": sin_ratio,
            "sortino": sortino,
        }

    sobreviven = con_ratio.index[:-n_fuera].tolist()
    fuera = con_ratio.index[-n_fuera:]

    eliminados = pd.DataFrame(
        {"activo": list(fuera), "sortino": [round(float(con_ratio[a]), 3) for a in fuera]}
    )

    return {
        "sobreviven": sobreviven + sin_ratio,
        "eliminados": eliminados,
        "sin_ratio": sin_ratio,
        "sortino": sortino,
    }


def purgar_negativos(retornos: pd.DataFrame, mar_anual: float = 0.0) -> dict:
    """Alternativa a purgar_peores: elimina SOLO los que pierden contra el MAR.

    Criterio absoluto en vez de percentil. No bota nada que este ganando, pero
    tampoco garantiza cuantos quedan.
    """
    sortino = calcular_sortino(retornos, mar_anual)
    sin_ratio = sortino[sortino.isna()].index.tolist()
    con_ratio = sortino.dropna()

    malos = con_ratio[con_ratio < 0]
    sobreviven = con_ratio[con_ratio >= 0].index.tolist() + sin_ratio

    eliminados = pd.DataFrame(
        {"activo": malos.index.tolist(), "sortino": malos.round(3).tolist()}
    )
    return {
        "sobreviven": sobreviven,
        "eliminados": eliminados,
        "sin_ratio": sin_ratio,
        "sortino": sortino,
    }


# ============================================================
# PASO 2 — PURGA POR REDUNDANCIA (correlacion parcial)
# ============================================================

def purgar_redundantes(
    candidatos: list,
    corr_parcial: pd.DataFrame,
    metrica: pd.Series,
    umbral: float = 0.20,
) -> dict:
    """De cada par con correlacion PARCIAL alta, elimina el de peor metrica.

    Correlacion parcial alta = comparten riesgo PROPIO = estas cargando el
    mismo riesgo dos veces sin cobrar por la segunda.

    Se usa parcial y no simple a proposito: XOM y CVX tienen correlacion simple
    0.86 pero parcial 0.06 -- no son redundantes, solo comparten el mercado, y
    el mercado si te lo paga. Botar una seria botar diversificacion.

    Procesa los pares de mayor a menor parcial, y salta los que ya fueron
    eliminados (para no botar los dos miembros de un trio).
    """
    vivos = list(candidatos)
    eliminados = []

    sub = corr_parcial.loc[vivos, vivos]
    n = len(vivos)
    iu = np.triu_indices(n, 1)
    pares = [
        (vivos[i], vivos[j], float(sub.values[i, j]))
        for i, j in zip(*iu)
        if sub.values[i, j] > umbral
    ]
    pares.sort(key=lambda x: -x[2])

    for a, b, pc in pares:
        if a not in vivos or b not in vivos:
            continue  # uno ya salio en un par anterior
        ma = metrica.get(a, -np.inf)
        mb = metrica.get(b, -np.inf)
        fuera = a if ma < mb else b
        queda = b if fuera == a else a
        vivos.remove(fuera)
        eliminados.append(
            {"eliminado": fuera, "por": queda, "parcial": round(pc, 3),
             "metrica_eliminado": round(float(metrica.get(fuera, np.nan)), 3),
             "metrica_conservado": round(float(metrica.get(queda, np.nan)), 3)}
        )

    return {
        "sobreviven": vivos,
        "eliminados": pd.DataFrame(eliminados) if eliminados
                      else pd.DataFrame(columns=["eliminado", "por", "parcial"]),
    }


# ============================================================
# PASO 3 — COBERTURA POR SECTOR
# ============================================================

def cobertura_por_sector(candidatos: list, metrica: pd.Series, sector: dict) -> dict:
    """Toma el mejor activo de CADA sector segun `metrica`.

    Este paso es el que define la composicion, y es el que evita que HRP se
    derrumbe hacia los bonos. Medido: HRP sobre los 96 activos sin filtro de
    sector pone 58.5% en bonos (SHY solo se lleva 31.7%). Con cobertura, los
    bonos reciben 1 cupo entre ~18.

    Por que aqui mu casi no importa: la metrica solo desempata DENTRO de cada
    sector, entre hermanos que correlacionan ~0.9 (elegir AGG en vez de BND
    casi no cambia el portafolio). La decision grande -- que entre UN bono --
    la toma la taxonomia, no la metrica. A mu nunca se le hace la pregunta fina.

    NO se recorta a un n_objetivo a proposito. Si forzaras "8 de 18 sectores",
    la metrica (ruidosa) decidiria cuales 10 sectores MUEREN -- y esa si es una
    pregunta fina que mu no puede responder. Eso explicaba la inestabilidad de
    0.64 entre ventanas que medimos. Dejando un cupo por sector, ninguno muere.
    """
    seleccion = []
    vistos = set()
    detalle = []

    # recorrer en orden de metrica descendente toma el mejor de cada sector
    orden = [a for a in metrica.index if a in set(candidatos)]
    for activo in orden:
        s = sector.get(activo, "Sin clasificar")
        if s not in vistos:
            vistos.add(s)
            seleccion.append(activo)
            detalle.append({"sector": s, "elegido": activo,
                            "metrica": round(float(metrica[activo]), 3)})

    return {
        "seleccion": seleccion,
        "detalle": pd.DataFrame(detalle),
        "sectores_cubiertos": sorted(vistos),
    }


# ============================================================
# ORQUESTADOR DE LA SELECCION
# ============================================================

def seleccionar(
    retornos: pd.DataFrame,
    corr_parcial: pd.DataFrame,
    sector: dict,
    mar_anual: float = 0.0,
    fraccion_purga: float = 0.30,
    umbral_parcial: float = 0.20,
    solo_negativos: bool = False,
) -> dict:
    """Corre los 3 pasos y devuelve la lista final de activos + trazabilidad.

    solo_negativos: True -> purga solo los de Sortino negativo en vez del
                    percentil. Criterio absoluto en vez de relativo.
    """
    # --- Paso 1: purga por Sortino (historico completo) ---
    if solo_negativos:
        p1 = purgar_negativos(retornos, mar_anual)
    else:
        p1 = purgar_peores(retornos, fraccion_purga, mar_anual)
    sortino = p1["sortino"]

    # --- Paso 2: purga por redundancia (parcial) ---
    p2 = purgar_redundantes(p1["sobreviven"], corr_parcial, sortino, umbral_parcial)

    # --- Paso 3: cobertura por sector ---
    p3 = cobertura_por_sector(p2["sobreviven"], sortino, sector)

    final = p3["seleccion"]
    # .copy() de un slice puede devolver una vista de solo lectura; forzamos
    # un array propio antes de tocarle la diagonal.
    sub = corr_parcial.loc[final, final].to_numpy(copy=True)
    np.fill_diagonal(sub, 0.0)

    return {
        "seleccion": final,
        "sortino": sortino,
        "paso1_purga_sortino": p1,
        "paso2_purga_parcial": p2,
        "paso3_cobertura_sector": p3,
        "embudo": {
            "universo": len(retornos.columns),
            "tras_purga_sortino": len(p1["sobreviven"]),
            "tras_purga_parcial": len(p2["sobreviven"]),
            "final": len(final),
        },
        "parcial_maxima_seleccion": float(np.abs(sub).max()) if len(final) > 1 else 0.0,
    }