"""
backtest_motor_robustez.py
===========================
Chequeo de robustez sobre backtest_motor_resultados.csv (ya generado por
backtest_motor.py). No vuelve a correr el motor -- solo reanaliza los
resultados guardados, para responder la objecion honesta que el propio
backtest_motor.py ya advertia: los 48 folds NO son independientes (se
solapan), asi que un promedio simple puede estar dominado por un puñado de
periodos parecidos.

Responde tres preguntas sobre el hallazgo "equal-weight le gana a HRP fuera
de muestra, sobre el mismo universo purgado":

1. ¿Se sostiene en un subconjunto de folds NO solapados (verdaderamente
   independientes entre si)?
2. ¿Es un patron consistente fold a fold (win-rate), o un promedio inflado
   por un par de folds extremos?
3. ¿HRP compensa con MENOS drawdown lo que pierde en retorno/Sortino? (la
   tabla original ya insinuaba esto: HRP tuvo drawdown promedio MENOR que
   equal-weight -- eso si seria el beneficio real de HRP, no el que se
   estaba buscando originalmente)
"""

import numpy as np
import pandas as pd
from scipy.stats import binomtest

df = pd.read_csv("backtest_motor_resultados.csv", parse_dates=["fecha_corte"])

produccion = df[(df.vida_media == 126) & (df.umbral_parcial == 0.20)].copy()
equal_w = df[df.variante == "equal_weight_universo_produccion"].copy()

pares = produccion.merge(
    equal_w, on=["fecha_corte", "horizonte_dias"], suffixes=("_hrp", "_eq")
)

print("=" * 78)
print("1) WIN-RATE fold a fold (todos los 48 folds, con solape)")
print("=" * 78)
for h in sorted(pares.horizonte_dias.unique()):
    sub = pares[pares.horizonte_dias == h]
    n = len(sub)
    gana_sortino = (sub.sortino_realizado_eq > sub.sortino_realizado_hrp).sum()
    gana_retorno = (sub.retorno_anualizado_eq > sub.retorno_anualizado_hrp).sum()
    gana_drawdown_hrp = (sub.max_drawdown_hrp > sub.max_drawdown_eq).sum()  # HRP menos negativo = mejor
    print(f"\nhorizonte={h} dias ({n} folds):")
    print(f"  equal-weight gana en Sortino realizado:  {gana_sortino}/{n} folds")
    print(f"  equal-weight gana en retorno anualizado: {gana_retorno}/{n} folds")
    print(f"  HRP tiene MENOR drawdown (mejor):        {gana_drawdown_hrp}/{n} folds")
    print(f"  drawdown promedio HRP:          {sub.max_drawdown_hrp.mean():.4f}")
    print(f"  drawdown promedio equal-weight: {sub.max_drawdown_eq.mean():.4f}")
    diff_dd = sub.max_drawdown_hrp - sub.max_drawdown_eq  # positivo = HRP menos negativo = HRP mejor
    print(f"  HRP tiene drawdown mas suave que equal-weight en {(diff_dd > 0).sum()}/{n} folds")

print("\n" + "=" * 78)
print("2) Subconjunto de folds NO solapados (independientes de verdad)")
print("=" * 78)
for h in sorted(pares.horizonte_dias.unique()):
    sub = pares[pares.horizonte_dias == h].sort_values("fecha_corte").reset_index(drop=True)
    margen_dias = int(h * 1.6)  # dias calendario aprox equivalentes al horizonte en dias habiles
    seleccionados = [sub.iloc[0]]
    for _, fila in sub.iloc[1:].iterrows():
        if (fila.fecha_corte - seleccionados[-1].fecha_corte).days >= margen_dias:
            seleccionados.append(fila)
    indep = pd.DataFrame(seleccionados)
    n = len(indep)
    gana_sortino = int((indep.sortino_realizado_eq > indep.sortino_realizado_hrp).sum())
    gana_dd_hrp = int((indep.max_drawdown_hrp > indep.max_drawdown_eq).sum())

    print(f"\nhorizonte={h} dias -- {n} folds independientes (de {len(sub)} totales)")
    print(f"  fechas usadas: {[d.date().isoformat() for d in indep.fecha_corte]}")
    print(f"  Sortino promedio HRP:          {indep.sortino_realizado_hrp.mean():.3f}")
    print(f"  Sortino promedio equal-weight: {indep.sortino_realizado_eq.mean():.3f}")
    print(f"  equal-weight gana en Sortino en {gana_sortino}/{n} folds independientes")
    print(f"  HRP tiene menor drawdown en {gana_dd_hrp}/{n} folds independientes")
    if n >= 5:
        test = binomtest(gana_sortino, n, p=0.5)
        print(f"  sign test (¿el win-rate de equal-weight es distinto de 50% al azar?): "
              f"p-valor={test.pvalue:.3f} (n chico, tomar como orientativo, no concluyente)")
    else:
        print("  muy pocos folds independientes para un sign test con algo de sentido")

print("\n" + "=" * 78)
print("3) Por año de la fecha de corte (periodos de estrés conocidos: 2018, 2020, 2022)")
print("=" * 78)
pares["anio"] = pares.fecha_corte.dt.year
for h in sorted(pares.horizonte_dias.unique()):
    print(f"\nhorizonte={h} dias:")
    sub = pares[pares.horizonte_dias == h]
    resumen = sub.groupby("anio").agg(
        folds=("fecha_corte", "count"),
        sortino_hrp=("sortino_realizado_hrp", "mean"),
        sortino_eq=("sortino_realizado_eq", "mean"),
        drawdown_hrp=("max_drawdown_hrp", "mean"),
        drawdown_eq=("max_drawdown_eq", "mean"),
    ).round(3)
    print(resumen.to_string())
