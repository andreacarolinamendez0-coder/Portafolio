"""
inspeccionar_datos.py
=====================
Imprime la base capa por capa para que puedas VERIFICAR con los ojos que los
datos estan normalizados, alineados y limpios. No calcula nada nuevo: solo
muestra lo que preparador_datos.py esta produciendo.

Uso:
    python inspeccionar_datos.py
    python inspeccionar_datos.py AAPL MSFT BTC-USD    -> hace zoom en esos tickers
"""

import sys
import numpy as np
import pandas as pd

import preparador_datos as prep

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

MUESTRA = sys.argv[1:] or ["AAPL", "BTC-USD", "SHY"]


def titulo(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


# ============================================================
titulo("CAPA 1 — PRECIOS CRUDOS (lo que deja el recolector)")

precios = prep.cargar_precios()
print(f"forma            : {precios.shape[0]} filas x {precios.shape[1]} activos")
print(f"rango de fechas  : {precios.index.min().date()}  ->  {precios.index.max().date()}")
print(f"tipo de indice   : {type(precios.index).__name__}")
print(f"ordenado?        : {precios.index.is_monotonic_increasing}")
print(f"fechas repetidas : {precios.index.duplicated().sum()}")

fds = precios.index.dayofweek >= 5
print(f"\nfilas en fin de semana : {fds.sum():>5}   (solo cripto opera)")
print(f"filas entre semana     : {(~fds).sum():>5}")

print(f"\nmuestra de precios crudos ({', '.join(MUESTRA)}):")
cols = [c for c in MUESTRA if c in precios.columns]
print(precios[cols].tail(4).to_string())

print("\nESCALAS CRUDAS — aqui se ve por que NO se puede correlacionar precios:")
esc = pd.DataFrame({
    "ultimo_precio": precios.iloc[-1],
    "min_historico": precios.min(),
    "max_historico": precios.max(),
})
print(esc.loc[esc["ultimo_precio"].nlargest(3).index].round(2).to_string())
print(esc.loc[esc["ultimo_precio"].nsmallest(3).index].round(2).to_string())


# ============================================================
titulo("CAPA 2 — SEPARACION DEL UNIVERSO")

grupos = prep.separar_universo(precios)
print(f"invertibles : {len(grupos['invertibles'])}   <- lo unico que ve el selector")
print(f"contexto    : {grupos['contexto']}")
for c in grupos["contexto"]:
    print(f"    {c:<8} -> transformacion: {prep.CONTEXTO[c]}")
print(f"redundantes : {grupos['redundantes']}  (se descartan)")
for c in grupos["redundantes"]:
    print(f"    {c:<8} -> {prep.REDUNDANTES[c]}")


# ============================================================
titulo("CAPA 3 — CALENDARIO MAESTRO")

precios_bolsa = prep.recortar_a_calendario(precios)
print(f"antes : {len(precios)} filas (con fines de semana de cripto)")
print(f"despues: {len(precios_bolsa)} filas (solo dias de bolsa)")
print(f"descartadas: {len(precios) - len(precios_bolsa)}")
anios = (precios_bolsa.index.max() - precios_bolsa.index.min()).days / 365.25
print(f"dias por año: {len(precios_bolsa)/anios:.0f}   (esperado ~252)")
d = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"]
cnt = pd.Series(precios_bolsa.index.dayofweek).value_counts().sort_index()
print("por dia: " + "  ".join(f"{d[i]}={v}" for i, v in cnt.items()))
print("   ^ si algun dia sale en 0, el calendario esta mal")


# ============================================================
titulo("CAPA 4 — VALIDACION DE CALIDAD (solo invertibles)")

val = prep.validar_calidad(precios_bolsa[grupos["invertibles"]])
print(f"umbrales: min historia={prep.MIN_DIAS_HISTORIA} dias | "
      f"hueco max={prep.MAX_HUECO_CONSECUTIVO} dias | precio min={prep.MIN_PRECIO_VALIDO}")
print(f"\nvalidos  : {len(val['validos'])}")
print(f"excluidos: {len(val['excluidos'])}")
for t, razon in val["excluidos"].items():
    print(f"   - {t}: {razon}")


# ============================================================
titulo("CAPA 5 — TRANSFORMACION A RETORNOS LOG")

ret_crudos = prep.calcular_retornos_log(precios_bolsa, val["validos"])
print("formula: ln(P_t / P_t-1)")
print("\nPRUEBA de que la transformacion es correcta (recalculo a mano):")
t = cols[0]
p = precios_bolsa[t].dropna()
manual = np.log(p.iloc[-1] / p.iloc[-2])
delmodulo = ret_crudos[t].dropna().iloc[-1]
print(f"   {t}: precio_ayer={p.iloc[-2]:.4f}  precio_hoy={p.iloc[-1]:.4f}")
print(f"        ln(hoy/ayer) a mano = {manual:.8f}")
print(f"        lo que da el modulo = {delmodulo:.8f}")
print(f"        coinciden?          = {np.isclose(manual, delmodulo)}")

print(f"\nmuestra de retornos log ({', '.join(cols)}):")
print(ret_crudos[cols].tail(4).to_string())

print("\nPERAS CON PERAS — ahora todos viven en la misma escala:")
comp = pd.DataFrame({
    "precio_hoy": precios_bolsa[cols].iloc[-1],
    "retorno_medio_diario": ret_crudos[cols].mean(),
    "vol_diaria": ret_crudos[cols].std(),
})
print(comp.to_string())
print("   ^ precios en escalas totalmente distintas, retornos en la misma")


# ============================================================
titulo("CAPA 6 — ALINEACION TEMPORAL  (aqui esta el problema)")

ret_alineados = prep.alinear_fechas(ret_crudos)
print(f"antes de alinear : {ret_crudos.shape[0]} filas x {ret_crudos.shape[1]} activos")
print(f"despues          : {ret_alineados.shape[0]} filas x {ret_alineados.shape[1]} activos")
print(f"rango final      : {ret_alineados.index.min().date()} -> {ret_alineados.index.max().date()}")

perdidas = ret_crudos.shape[0] - ret_alineados.shape[0]
print(f"\nfilas descartadas: {perdidas}  ({perdidas/ret_crudos.shape[0]:.0%} del total)")

print("\nQUIEN CAUSA EL RECORTE (activos que arrancan tarde):")
arranques = ret_crudos.apply(lambda c: c.first_valid_index()).sort_values()
tarde = arranques.tail(6)
for tk, f in tarde.items():
    print(f"   {tk:<10} arranca {f.date()}")
print(f"\n   -> dropna(how='any') exige que TODOS tengan dato el mismo dia.")
print(f"      El que arranca mas tarde ({arranques.index[-1]}, {arranques.iloc[-1].date()})")
print(f"      define el arranque de TODOS.")

sin_tarde = [c for c in ret_crudos.columns if c not in arranques.tail(3).index]
alt = ret_crudos[sin_tarde].dropna(how="any")
print(f"\n   COSTO REAL: excluyendo los 3 mas tardios ({list(arranques.tail(3).index)}),")
print(f"   pasarias de {ret_alineados.shape[0]} a {alt.shape[0]} dias "
      f"(+{alt.shape[0]-ret_alineados.shape[0]}) con {len(sin_tarde)} activos.")

print("\nverificacion de la alineacion:")
print(f"   quedan NaN?          : {ret_alineados.isna().sum().sum()}")
print(f"   fines de semana?     : {(ret_alineados.index.dayofweek>=5).sum()}")
print(f"   fechas duplicadas?   : {ret_alineados.index.duplicated().sum()}")
print(f"   todas las filas completas? : {(ret_alineados.notna().all(axis=1)).all()}")

print(f"\nmuestra alineada ({', '.join(cols)}) — misma fila, mismo dia, misma unidad:")
print(ret_alineados[cols].tail(4).to_string())


# ============================================================
titulo("CAPA 7 — MATRIZ DE CORRELACION (solo invertibles)")

corr = prep.matriz_correlacion(ret_alineados)
print(f"forma      : {corr.shape}")
print(f"simetrica? : {np.allclose(corr.values, corr.values.T)}")
print(f"diagonal=1?: {np.allclose(np.diag(corr.values), 1.0)}")
print(f"rango      : [{corr.values.min():.3f}, {corr.values[~np.eye(len(corr),dtype=bool)].max():.3f}]")

print(f"\nesquina de la matriz ({', '.join(cols)}):")
print(corr.loc[cols, cols].round(3).to_string())


# ============================================================
titulo("RESUMEN")

res = prep.preparar_universo()
print(f"activos validos   : {len(res['activos_validos'])}")
print(f"activos excluidos : {len(res['activos_excluidos'])}")
print(f"dias alineados    : {res['dias_alineados']}")
print(f"matriz correlacion: {res['correlacion'].shape}   (solo invertibles)")
print(f"dias crudos       : {res['dias_crudos']}")
print(f"dias de bolsa     : {res['dias_de_bolsa']}")
print(f"contexto          : {list(res['contexto'].columns)}")
print(f"descartados       : {res['redundantes_descartados']}")
print(f"\nsectores presentes:")
s = pd.Series(res["sector"]).value_counts()
print(s.to_string())