"""
backtest_motor_robustez_grid.py
=================================
Mismo chequeo de independencia que backtest_motor_robustez.py, aplicado
esta vez al barrido de vida_media/umbral_parcial (no a HRP vs equal-weight).
Pregunta: la ventaja de vida_media=189-252 + umbral=0.10 sobre la config de
produccion (126/0.20) que se vio en el backtest completo (48 folds
solapados) -- ¿se sostiene en el subconjunto de folds independientes, o es
el mismo tipo de espejismo que ya desinflo el hallazgo de HRP vs
equal-weight?

Reanaliza backtest_motor_resultados.csv, no vuelve a correr el motor.
"""

import pandas as pd
from scipy.stats import binomtest

df = pd.read_csv("backtest_motor_resultados.csv", parse_dates=["fecha_corte"])
grid = df[df.variante.str.startswith("grid_")].copy()

PRODUCCION = (126.0, 0.20)


def folds_independientes(sub: pd.DataFrame, horizonte: int) -> pd.DataFrame:
    """Mismo criterio que backtest_motor_robustez.py: se queda con fechas de
    corte espaciadas al menos horizonte*1.6 dias calendario entre si, para
    que las ventanas de evaluacion (T -> T+horizonte) no se solapen."""
    fechas = sorted(sub.fecha_corte.unique())
    margen = pd.Timedelta(days=int(horizonte * 1.6))
    elegidas = [fechas[0]]
    for f in fechas[1:]:
        if (f - elegidas[-1]) >= margen:
            elegidas.append(f)
    return sub[sub.fecha_corte.isin(elegidas)]


for horizonte in sorted(grid.horizonte_dias.unique()):
    print("=" * 78)
    print(f"HORIZONTE = {horizonte} dias")
    print("=" * 78)
    sub_h = grid[grid.horizonte_dias == horizonte]

    # --- Ranking con TODOS los folds (solapados), para comparar contra el original ---
    completo = sub_h.groupby(["vida_media", "umbral_parcial"]).agg(
        folds=("sortino_realizado", "count"),
        sortino_prom=("sortino_realizado", "mean"),
    ).sort_values("sortino_prom", ascending=False)
    print("\nRanking con los 48 folds completos (solapados):")
    print(completo.to_string())
    ganador_completo = completo.index[0]

    # --- Ranking SOLO con folds independientes ---
    indep = folds_independientes(sub_h, horizonte)
    n_fechas_indep = indep.fecha_corte.nunique()
    ranking_indep = indep.groupby(["vida_media", "umbral_parcial"]).agg(
        folds=("sortino_realizado", "count"),
        sortino_prom=("sortino_realizado", "mean"),
    ).sort_values("sortino_prom", ascending=False)
    print(f"\nRanking con SOLO folds independientes ({n_fechas_indep} fechas de corte, "
          f"sin solape entre ventanas de evaluacion):")
    print(ranking_indep.to_string())

    print(f"\n¿Produccion (126/0.20) sigue siendo de las peores/mejores?")
    posicion_completo = list(completo.index).index(PRODUCCION) + 1
    posicion_indep = list(ranking_indep.index).index(PRODUCCION) + 1
    print(f"  Posicion de 126/0.20 con folds completos:     {posicion_completo}/{len(completo)}")
    print(f"  Posicion de 126/0.20 con folds independientes: {posicion_indep}/{len(ranking_indep)}")

    # --- Comparacion pareada: produccion vs el "ganador" del ranking completo, SOLO en folds independientes ---
    ganador_vm, ganador_um = ganador_completo
    if ganador_completo != PRODUCCION:
        prod_rows = indep[(indep.vida_media == 126.0) & (indep.umbral_parcial == 0.20)][
            ["fecha_corte", "sortino_realizado"]
        ].rename(columns={"sortino_realizado": "sortino_produccion"})
        ganador_rows = indep[(indep.vida_media == ganador_vm) & (indep.umbral_parcial == ganador_um)][
            ["fecha_corte", "sortino_realizado"]
        ].rename(columns={"sortino_realizado": "sortino_ganador"})
        pareado = prod_rows.merge(ganador_rows, on="fecha_corte")
        n = len(pareado)
        gana_ganador = int((pareado.sortino_ganador > pareado.sortino_produccion).sum())
        print(f"\n  Comparacion pareada, SOLO folds independientes: produccion (126/0.20) "
              f"vs el 'ganador' del ranking completo (vida_media={ganador_vm}, umbral={ganador_um})")
        print(f"  El 'ganador' le gana a produccion en {gana_ganador}/{n} folds independientes")
        if n >= 5:
            test = binomtest(gana_ganador, n, p=0.5)
            print(f"  sign test: p-valor={test.pvalue:.3f} (n chico, orientativo)")
        else:
            print("  muy pocos folds independientes para un sign test con sentido")
    print()
