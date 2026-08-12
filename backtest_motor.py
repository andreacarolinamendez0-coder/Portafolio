"""
backtest_motor.py
==================
Backtest walk-forward del motor de seleccion/ponderacion (analista_motor.py).

Pregunta que responde (pedida por Andrea): ¿el pipeline actual (purga Sortino
+ purga parcial + cobertura sectorial + HRP, con vida_media=126,
umbral_parcial=0.20) le gana FUERA DE MUESTRA a alternativas mas simples, y
esos dos parametros estan razonablemente bien calibrados o son un caso de
overfitting de hiperparametros?

Metodo: para cada fecha de corte T, se "congela" el universo usando SOLO
datos <= T (via preparar_universo_hasta), se corre cada variante, y se
evalua el resultado con retornos REALES (nunca truncados) del periodo
T -> T+horizonte. No modifica ningun archivo del motor real — usa
analista_motor.construir_portafolio() y motor_seleccion/ponderador tal cual,
solo con distintos parametros y datos truncados por fuera.

LIMITACION HONESTA: con ~10 años de historia diaria, las ventanas de
evaluacion (63/126 dias habiles) se solapan entre si — no son verdaderamente
independientes. Sirve para descartar configuraciones claramente peores, no
para probar con solidez estadistica un optimo exacto.

Salida: backtest_motor_resultados.csv (raiz del repo, NO en datos/, que es
el volumen persistido de produccion) + resumen agregado impreso en consola.

100% computo local: sin red, sin Flask, sin el hilo de monitor.py. Seguro de
correr sin ninguna precaucion especial.
"""

import itertools
import warnings

import numpy as np
import pandas as pd

import preparador_datos as prep_datos
from preparador_datos import MIN_DIAS_HISTORIA
import analista_motor as am
import motor_seleccion as ms
import ponderador as pdr

warnings.filterwarnings("ignore")

VIDAS_MEDIA = [63, 126, 189, 252]
UMBRALES_PARCIAL = [0.10, 0.20, 0.30]
HORIZONTES = [63, 126]  # dias habiles aprox de evaluacion fuera de muestra
MAR_ANUAL = 0.045
FRECUENCIA_FOLDS_DIAS = 63  # ~1 fold cada 3 meses calendario


# ============================================================
# Congelar el universo en una fecha pasada, sin tocar preparador_datos.py
# ============================================================

def preparar_universo_hasta(fecha_corte: pd.Timestamp, precios_completo: pd.DataFrame) -> dict:
    """Monkeypatch temporal de cargar_precios() para que preparar_universo()
    solo vea datos <= fecha_corte. preparar_universo() no depende de
    datetime.now() en ningun punto (confirmado), asi que esto es
    equivalente a correr el motor "como si hoy fuera fecha_corte"."""
    recorte = precios_completo.loc[:fecha_corte].copy()
    original = prep_datos.cargar_precios

    def _truncado():
        return recorte

    prep_datos.cargar_precios = _truncado
    try:
        return prep_datos.preparar_universo()
    finally:
        prep_datos.cargar_precios = original


# ============================================================
# Evaluacion fuera de muestra con precios REALES (nunca truncados)
# ============================================================

def evaluar_ventana(pesos: pd.Series, precios_completo: pd.DataFrame,
                     fecha_corte: pd.Timestamp, horizonte_dias: int):
    tickers = [t for t in pesos.index if t in precios_completo.columns]
    if not tickers:
        return None
    w = pesos.reindex(tickers)
    w = w / w.sum()

    anteriores = precios_completo.index[precios_completo.index <= fecha_corte]
    if len(anteriores) == 0:
        return None
    ancla = anteriores[-1]

    ventana = precios_completo.loc[precios_completo.index >= ancla, tickers]
    ventana = ventana.iloc[: horizonte_dias + 1]
    if len(ventana) < horizonte_dias * 0.7:
        return None  # cerca del final de los datos, ventana incompleta

    ventana = ventana.dropna(how="any")
    if len(ventana) < 10:
        return None

    ret = np.log(ventana / ventana.shift(1)).dropna()
    if ret.empty:
        return None

    ret_port = pd.Series(ret[tickers].values @ w.values, index=ret.index)
    dias_reales = len(ret_port)
    retorno_total = float(ret_port.sum())
    retorno_anualizado = retorno_total * (252 / dias_reales)

    sortino = ms.calcular_sortino(ret_port.to_frame("p"), mar_anual=MAR_ANUAL)["p"]
    curva = ret_port.cumsum()
    max_drawdown = float((curva - curva.cummax()).min())

    return {
        "n_dias_reales": dias_reales,
        "retorno_total": retorno_total,
        "retorno_anualizado": retorno_anualizado,
        "sortino_realizado": float(sortino) if pd.notna(sortino) else None,
        "max_drawdown": max_drawdown,
    }


# ============================================================
# Fechas de corte
# ============================================================

def generar_fechas_corte(precios_completo: pd.DataFrame) -> list:
    fechas = precios_completo.index.sort_values()
    margen_inicio = pd.Timedelta(days=int(MIN_DIAS_HISTORIA * 1.6) + 60)
    margen_fin = pd.Timedelta(days=int(max(HORIZONTES) * 1.6))

    inicio = fechas[0] + margen_inicio
    fin = fechas[-1] - margen_fin
    if fin <= inicio:
        raise RuntimeError("No hay suficiente historia para ningun fold de backtest.")

    candidatas = pd.date_range(inicio, fin, freq=f"{FRECUENCIA_FOLDS_DIAS}D")
    cortes = []
    for c in candidatas:
        disponibles = fechas[fechas <= c]
        if len(disponibles):
            cortes.append(disponibles[-1])
    return sorted(set(cortes))


# ============================================================
# Un fold: corre todas las variantes y evalua
# ============================================================

def correr_fold(fecha_corte: pd.Timestamp, precios_completo: pd.DataFrame) -> list:
    filas = []
    try:
        datos = preparar_universo_hasta(fecha_corte, precios_completo)
    except Exception as e:
        print(f"  [{fecha_corte.date()}] preparar_universo_hasta fallo: {e}")
        return filas

    retornos, sector = datos["retornos"], datos["sector"]
    if retornos.shape[1] < 10 or len(retornos) < 100:
        print(f"  [{fecha_corte.date()}] universo insuficiente, se salta el fold "
              f"({retornos.shape[1]} activos, {len(retornos)} dias)")
        return filas

    variantes = []

    # --- Barrido de parametros (incluye la config de produccion 126/0.20) ---
    resultado_produccion = None
    for vida_media, umbral in itertools.product(VIDAS_MEDIA, UMBRALES_PARCIAL):
        try:
            res = am.construir_portafolio(
                retornos, sector, mar_anual=MAR_ANUAL,
                vida_media=vida_media, umbral_parcial=umbral,
            )
        except Exception as e:
            print(f"  [{fecha_corte.date()}] vida_media={vida_media} umbral={umbral} fallo: {e}")
            continue
        etiqueta = f"grid_vm{vida_media}_um{umbral}"
        variantes.append((etiqueta, vida_media, umbral, res["pesos"], res["n_efectivo"]))
        if vida_media == 126 and umbral == 0.20:
            resultado_produccion = res

    # --- Baseline: HRP crudo, sin ninguna purga ---
    try:
        res_crudo = am.construir_portafolio(
            retornos, sector, mar_anual=MAR_ANUAL, vida_media=126,
            fraccion_purga=0.0, umbral_parcial=1.01, saltar_cobertura_sector=True,
        )
        variantes.append(("hrp_crudo_sin_purga", None, None, res_crudo["pesos"], res_crudo["n_efectivo"]))
    except Exception as e:
        print(f"  [{fecha_corte.date()}] hrp_crudo fallo: {e}")

    # --- Baseline: equal-weight sobre el MISMO universo purgado de produccion ---
    if resultado_produccion is not None:
        activos_prod = resultado_produccion["seleccion"]["seleccion"]
        pesos_iguales = pdr.pesos_iguales(activos_prod)
        variantes.append(("equal_weight_universo_produccion", None, None, pesos_iguales, float(len(activos_prod))))

    for etiqueta, vida_media, umbral, pesos, n_efectivo in variantes:
        for horizonte in HORIZONTES:
            metricas = evaluar_ventana(pesos, precios_completo, fecha_corte, horizonte)
            if metricas is None:
                continue
            filas.append({
                "fecha_corte": fecha_corte.date().isoformat(),
                "variante": etiqueta,
                "vida_media": vida_media,
                "umbral_parcial": umbral,
                "horizonte_dias": horizonte,
                "n_seleccionados": len(pesos),
                "n_efectivo": round(n_efectivo, 2),
                **metricas,
            })

    return filas


# ============================================================
# Main
# ============================================================

def main():
    precios_completo = prep_datos.cargar_precios()
    print(f"Rango de datos: {precios_completo.index.min().date()} -> "
          f"{precios_completo.index.max().date()} ({len(precios_completo)} filas)")

    fechas_corte = generar_fechas_corte(precios_completo)
    print(f"Folds generados: {len(fechas_corte)} "
          f"(cada ~{FRECUENCIA_FOLDS_DIAS} dias calendario)\n"
          "ADVERTENCIA: las ventanas de evaluacion se solapan entre folds -- "
          "no son independientes, sirve para descartar configuraciones malas, "
          "no para un test estadistico riguroso de significancia.\n")

    todas_las_filas = []
    for i, fecha_corte in enumerate(fechas_corte, 1):
        print(f"Fold {i}/{len(fechas_corte)} -- corte {fecha_corte.date()}")
        todas_las_filas.extend(correr_fold(fecha_corte, precios_completo))

    if not todas_las_filas:
        print("\nNo se generó ningún resultado. Revisa los datos disponibles.")
        return

    df = pd.DataFrame(todas_las_filas)
    df.to_csv("backtest_motor_resultados.csv", index=False)
    print(f"\nGuardado: backtest_motor_resultados.csv ({len(df)} filas)")

    print("\n" + "=" * 78)
    print("RESUMEN — pregunta 1: ¿el pipeline le gana a los baselines fuera de muestra?")
    print("=" * 78)
    produccion = df[(df.vida_media == 126) & (df.umbral_parcial == 0.20)].copy()
    produccion["variante"] = "produccion_126_0.20"
    comparacion = pd.concat([
        produccion,
        df[df.variante.isin(["hrp_crudo_sin_purga", "equal_weight_universo_produccion"])],
    ])
    resumen1 = comparacion.groupby(["variante", "horizonte_dias"]).agg(
        folds=("retorno_anualizado", "count"),
        retorno_anualizado_prom=("retorno_anualizado", "mean"),
        sortino_realizado_prom=("sortino_realizado", "mean"),
        max_drawdown_prom=("max_drawdown", "mean"),
        n_efectivo_prom=("n_efectivo", "mean"),
    ).round(4)
    print(resumen1.to_string())

    print("\n" + "=" * 78)
    print("RESUMEN — pregunta 2: ¿126/0.20 es de los mejores parámetros del barrido?")
    print("=" * 78)
    grid = df[df.variante.str.startswith("grid_")]
    resumen2 = grid.groupby(["vida_media", "umbral_parcial", "horizonte_dias"]).agg(
        folds=("retorno_anualizado", "count"),
        retorno_anualizado_prom=("retorno_anualizado", "mean"),
        sortino_realizado_prom=("sortino_realizado", "mean"),
        max_drawdown_prom=("max_drawdown", "mean"),
    ).round(4)
    print(resumen2.to_string())

    print("\nRanking por sortino_realizado_prom promedio (dentro de cada horizonte):")
    for h in HORIZONTES:
        sub = resumen2.xs(h, level="horizonte_dias").sort_values(
            "sortino_realizado_prom", ascending=False)
        print(f"\n  horizonte={h} dias:")
        print(sub.to_string())


if __name__ == "__main__":
    main()
