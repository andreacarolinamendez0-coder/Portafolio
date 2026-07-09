"""
motor_diversificacion.py
========================
Motor de selección de portafolio con DIVERSIFICACIÓN REAL en dos dimensiones.

El problema que resuelve: un optimizador por Sharpe puro sobre un universo
pequeño converge siempre a los mismos ganadores (tech de megacap), dando la
ilusión de portafolios distintos que en el fondo son el mismo.

La solución ataca los DOS tipos de riesgo por separado, porque son distintos:

  1. Riesgo NO SISTÉMICO (específico, diversificable) -> correlación PARCIAL.
     Evita meter dos activos que compartan riesgo propio (ej. V y MA, que son
     el mismo negocio de pagos). La parcial detecta esto aunque estén en
     sectores que parecen distintos, y NO castiga pares que solo comparten
     mercado (ej. XOM-CVX, cuya correlación simple es 0.86 pero parcial 0.06).

  2. Riesgo SISTÉMICO (de mercado, NO diversificable) -> cobertura por SECTOR.
     La parcial es ciega a esto por diseño (le quitamos el mercado). Por eso
     necesitamos el sector como proxy de "a qué escenario macro estás
     expuesto": garantiza variedad de exposición, que el portafolio no esté
     todo apostado al mismo tipo de escenario económico.

  Parcial EVITA duplicar riesgo propio. Sector GARANTIZA variedad de escenario.
  Son complementarios, no redundantes.

Resolución de redundancia (regla "cobertura protegida"):
  Cuando dos candidatos comparten riesgo no sistémico (parcial >= umbral):
  - Si ambos tienen respaldo en su sector -> elimina el de MENOR Sharpe.
  - Si uno es el único representante de su sector -> se protege (no se elimina
    aunque tenga menor Sharpe).
  - Si ambos son únicos de sus sectores -> se conservan y se marca aviso.

El Sharpe se calcula DENTRO de este motor, sobre todo el histórico.

Uso típico:
    from preparador_datos import preparar_universo
    from red_riesgo import matriz_correlacion_parcial
    from motor_diversificacion import seleccionar_portafolio
    import recolector as R

    datos = preparar_universo()
    pc = matriz_correlacion_parcial(datos["retornos"])

    resultado = seleccionar_portafolio(
        retornos=datos["retornos"],
        corr_parcial=pc,
        sector=datos["sector"],          # dict {ticker: sector}
        umbral_parcial=0.2,
        n_objetivo=8,
    )
"""

import os
import numpy as np
import pandas as pd

DIAS_TRADING_ANIO = 252


# ============================================================
# CÁLCULO DE SHARPE (sobre todo el histórico)
# ============================================================

def _cargar_tasa_libre_anual() -> float:
    """Lee risk_free.parquet (Treasury Bills, % anual) y devuelve la tasa
    libre como fracción decimal (4.5% -> 0.045). Importa recolector solo aquí
    dentro para no acoplar el módulo si se usa con tasa explícita."""
    try:
        import recolector as R
        archivo = os.path.join(R.CARPETA_MACRO, "risk_free.parquet")
        if not os.path.exists(archivo):
            return 0.0
        df = pd.read_parquet(archivo)
        return float(df["Risk_Free"].iloc[-1]) / 100.0
    except Exception:
        return 0.0


def calcular_sharpe(retornos: pd.DataFrame, tasa_libre_anual: float = None) -> pd.Series:
    """Sharpe anualizado por activo, sobre todo el histórico de retornos log.
    Sharpe = (retorno_medio_anual - tasa_libre) / volatilidad_anual"""
    if tasa_libre_anual is None:
        tasa_libre_anual = _cargar_tasa_libre_anual()

    retorno_medio_anual = retornos.mean() * DIAS_TRADING_ANIO
    volatilidad_anual = retornos.std() * np.sqrt(DIAS_TRADING_ANIO)
    sharpe = (retorno_medio_anual - tasa_libre_anual) / volatilidad_anual
    return sharpe.sort_values(ascending=False)


# ============================================================
# CAPA DE COBERTURA — variedad de exposición (por sector)
# ============================================================

def cobertura_por_sector(sharpe: pd.Series, sector: dict) -> list:
    """Toma el activo de mayor Sharpe de cada sector. Garantiza que la
    selección inicial toque distintos tipos de exposición sistémica, no solo
    el sector que concentra los mejores Sharpe individuales."""
    seleccion = []
    sectores_vistos = set()
    # sharpe ya viene ordenado desc: recorrer en ese orden toma el mejor de c/u
    for activo in sharpe.index:
        sec = sector.get(activo, "Sin clasificar")
        if sec not in sectores_vistos:
            seleccion.append(activo)
            sectores_vistos.add(sec)
    return seleccion


# ============================================================
# CAPA ANTI-REDUNDANCIA — riesgo no sistémico (por parcial)
# ============================================================

def _pares_redundantes(candidatos, corr_parcial, umbral):
    """Pares de la selección con correlación PARCIAL positiva >= umbral:
    comparten riesgo no sistémico. Negativa NO es redundancia (es cobertura)."""
    pares = []
    for i, a in enumerate(candidatos):
        for b in candidatos[i + 1:]:
            pc = corr_parcial.loc[a, b]
            if pd.notna(pc) and pc >= umbral:
                pares.append((a, b, float(pc)))
    pares.sort(key=lambda x: x[2], reverse=True)
    return pares


def _buscar_reemplazo(seleccion, corr_parcial, umbral, universo_ordenado):
    """Primer activo (mejor Sharpe disponible) que no esté ya en la selección
    y que no sea redundante (parcial) con nadie de la selección."""
    for cand in universo_ordenado:
        if cand in seleccion:
            continue
        redundante = False
        for a in seleccion:
            pc = corr_parcial.loc[cand, a]
            if pd.notna(pc) and pc >= umbral:
                redundante = True
                break
        if not redundante:
            return cand
    return None


def resolver_redundancia(candidatos, corr_parcial, sharpe, sector, umbral, universo_ordenado):
    """Aplica cobertura protegida hasta que no queden redundancias resolubles."""
    seleccion = list(candidatos)
    avisos = []
    eliminados = []

    def es_unico_de_su_sector(activo, sel):
        sec = sector.get(activo, "Sin clasificar")
        mismos = [a for a in sel if sector.get(a, "Sin clasificar") == sec]
        return len(mismos) <= 1

    max_iter = len(candidatos) * 3
    for _ in range(max_iter):
        pares = _pares_redundantes(seleccion, corr_parcial, umbral)
        if not pares:
            break

        resuelto_algo = False
        for a, b, pc in pares:
            a_unico = es_unico_de_su_sector(a, seleccion)
            b_unico = es_unico_de_su_sector(b, seleccion)

            if a_unico and b_unico:
                aviso = (
                    f"{a} y {b} comparten riesgo no sistémico (parcial {pc:.2f}) "
                    f"pero cada uno es único representante de su sector. Se "
                    f"conservan ambos; diversificación real menor a la aparente."
                )
                if aviso not in avisos:
                    avisos.append(aviso)
                continue

            if a_unico:
                a_eliminar = b
            elif b_unico:
                a_eliminar = a
            else:
                a_eliminar = a if sharpe[a] < sharpe[b] else b

            otro = b if a_eliminar == a else a
            seleccion.remove(a_eliminar)
            eliminados.append(
                (a_eliminar, f"comparte riesgo con {otro} (parcial {pc:.2f}), menor Sharpe")
            )

            reemplazo = _buscar_reemplazo(seleccion, corr_parcial, umbral, universo_ordenado)
            if reemplazo:
                seleccion.append(reemplazo)

            resuelto_algo = True
            break

        if not resuelto_algo:
            break

    return {"seleccion_final": seleccion, "avisos": avisos, "eliminados": eliminados}


# ============================================================
# ORQUESTADOR
# ============================================================

def seleccionar_portafolio(
    retornos: pd.DataFrame,
    corr_parcial: pd.DataFrame,
    sector: dict,
    umbral_parcial: float = 0.2,
    n_objetivo: int = 8,
    tasa_libre_anual: float = None,
) -> dict:
    """Pipeline completo de diversificación real.

    1. Sharpe (histórico completo).
    2. Cobertura por sector: mejor Sharpe de cada sector (variedad de exposición
       sistémica).
    3. Relleno hasta n_objetivo con mejores Sharpe restantes.
    4. Anti-redundancia por correlación parcial (evitar duplicar riesgo no
       sistémico), con cobertura de sector protegida.
    """
    sharpe = calcular_sharpe(retornos, tasa_libre_anual)
    universo_ordenado = sharpe.index.tolist()

    # Capa de cobertura (variedad de exposición sistémica)
    seleccion = cobertura_por_sector(sharpe, sector)

    # Recortar: si hay más sectores que n_objetivo, quedarnos con los de mejor
    # Sharpe (la cobertura ya priorizó el mejor de cada sector)
    if len(seleccion) > n_objetivo:
        seleccion = sorted(seleccion, key=lambda a: sharpe[a], reverse=True)[:n_objetivo]

    # Rellenar si faltan (menos sectores que n_objetivo)
    for cand in universo_ordenado:
        if len(seleccion) >= n_objetivo:
            break
        if cand not in seleccion:
            seleccion.append(cand)

    # Capa anti-redundancia (riesgo no sistémico)
    resultado = resolver_redundancia(
        candidatos=seleccion,
        corr_parcial=corr_parcial,
        sharpe=sharpe,
        sector=sector,
        umbral=umbral_parcial,
        universo_ordenado=universo_ordenado,
    )

    seleccion_final = resultado["seleccion_final"]

    detalle = pd.DataFrame({
        "activo": seleccion_final,
        "sharpe": [round(float(sharpe[a]), 3) for a in seleccion_final],
        "sector": [sector.get(a, "Sin clasificar") for a in seleccion_final],
    }).sort_values("sharpe", ascending=False).reset_index(drop=True)

    return {
        "seleccion": seleccion_final,
        "detalle": detalle,
        "avisos": resultado["avisos"],
        "eliminados": resultado["eliminados"],
        "sharpe_completo": sharpe,
    }