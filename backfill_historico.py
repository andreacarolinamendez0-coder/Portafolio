"""backfill_historico.py — UNA SOLA VEZ: reconstruye el histórico de cada
portafolio desde la primera compra hasta el primer snapshot ya existente,
reusando el MISMO costo base que el cálculo en vivo (_pool_posicion_viva) y los
precios/TRM históricos que ya están en disco.

- No descarga nada (datos/precios/precios.parquet + datos/macro/trm.parquet).
- No toca el scheduler (sigue con el snapshot forward diario).
- Idempotente: dedup por fecha, re-correr no duplica.
- No cambia el frontend: solo agrega puntos a portafolio["historial"], que el
  chart ya grafica.

Uso:
    python backfill_historico.py            # todos los portafolios
    python backfill_historico.py archivo.json   # uno solo

Requiere SECRET_KEY en el entorno (lo exige importar dashboard) — en local sale
del .env; en Railway ya está.
"""
import os
import sys
import pandas as pd

# Cargar .env al entorno ANTES de importar dashboard (exige SECRET_KEY).
_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ENV):
    for _l in open(_ENV, encoding="utf-8"):
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import preparador_datos as prep
from dashboard import _pool_posicion_viva
from gestor_portafolio import CARPETA_PORTAFOLIOS, _es_portafolio_real, _leer, _escribir

TRM_PATH = os.path.join(os.path.dirname(CARPETA_PORTAFOLIOS), "macro", "trm.parquet")


def backfill_uno(archivo, precios, trm_serie, recompute=False):
    """Devuelve (n_puntos_reconstruidos, mensaje).
    recompute=False: solo rellena el hueco [1ª compra, primer snapshot), sin pisar
    puntos existentes. recompute=True: reconstruye TODO [1ª compra, hoy) desde las
    transacciones ACTUALES, reemplazando los puntos < hoy (conserva los de hoy en
    adelante = snapshot vivo del scheduler)."""
    ruta = os.path.join(CARPETA_PORTAFOLIOS, archivo)
    data = _leer(ruta)
    aportes = data.get("aportes", [])
    if not aportes:
        return 0, "sin aportes"
    ventas = data.get("ventas", [])
    tickers = sorted(set(a["activo"] for a in aportes))

    faltantes = [tk for tk in tickers if tk not in precios.columns]
    if faltantes:
        # Sin serie de precios no se puede reconstruir el valor sin subcontar
        # -> se salta el portafolio entero (mejor no rellenar que rellenar mal).
        return 0, f"SALTADO — tickers sin precios: {faltantes}"

    fecha_min = min(a["fecha"] for a in aportes if a.get("fecha"))
    historial = data.get("historial", [])
    hoy = pd.Timestamp.today().strftime("%Y-%m-%d")
    if recompute:
        # Reconstruye TODO hasta hoy inclusive desde las transacciones actuales.
        # Conserva solo puntos futuros (> hoy, no debería haber). Incluir hoy es
        # deliberado: el snapshot que grabó el scheduler puede estar viejo/con bug
        # (guardar_registro_diario deduplica por fecha y NUNCA lo sobreescribe), así
        # que el recompute es el único que puede sanar el punto de hoy.
        manana = (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        fecha_corte = manana
        fechas_a_saltar = set()
        conservar = [r for r in historial if r.get("fecha", "") > hoy]
    else:
        fechas_existentes = set(r.get("fecha") for r in historial)
        fecha_corte = min(fechas_existentes) if fechas_existentes else hoy
        fechas_a_saltar = fechas_existentes
        conservar = historial

    idx = precios.index
    dias = idx[(idx >= pd.Timestamp(fecha_min)) & (idx < pd.Timestamp(fecha_corte))]

    nuevos = []
    for D in dias:
        Dstr = D.strftime("%Y-%m-%d")
        if Dstr in fechas_a_saltar:
            continue  # modo normal: nunca pisa un snapshot real
        aportes_D = [a for a in aportes if a.get("fecha", "9999") <= Dstr]
        ventas_D = [v for v in ventas if v.get("fecha", "9999") <= Dstr]

        total_val = total_inv = 0.0
        dia_completo = True
        for tk in tickers:
            pool = _pool_posicion_viva(aportes_D, ventas_D, tk)
            if pool["frac"] <= 1e-9:
                continue  # sin posición viva de ese ticker ese día
            precio_D = precios.at[D, tk]
            if pd.isna(precio_D):
                dia_completo = False  # falta precio de un ticker vivo -> día inválido
                break
            total_val += pool["frac"] * float(precio_D)
            total_inv += pool["usd"]

        if not dia_completo or total_inv <= 1e-9:
            continue

        gan = total_val - total_inv
        pos = trm_serie.index.get_indexer([D], method="nearest")[0]
        trm_D = float(trm_serie.iloc[pos])
        nuevos.append({
            "fecha": Dstr,
            "resumen": {
                "total_valor": round(total_val, 2),
                "total_invertido": round(total_inv, 2),
                "ganancia_total": round(gan, 2),
                "rentabilidad_total": round(gan / total_inv * 100, 2),
            },
            "macro": {"trm": trm_D},
        })

    if not nuevos and not recompute:
        return 0, "nada que rellenar (histórico ya arranca en la 1ª compra)"

    data["historial"] = sorted(nuevos + conservar, key=lambda r: r["fecha"])
    _escribir(ruta, data)
    if not nuevos:
        return 0, "recompute: sin días reconstruibles (histórico dejado en hoy+)"
    rango = f"{nuevos[0]['fecha']} → {nuevos[-1]['fecha']}"
    return len(nuevos), (f"recompute {rango}" if recompute else f"desde {rango}")


def recomputar(archivo):
    """Recompute in-place el histórico de UN portafolio desde sus transacciones
    actuales. Pensado para llamarse desde un endpoint tras editar/eliminar un
    aporte/venta (auto-recompute). Carga precios+trm cada vez (~100 ms con cache
    caliente); barato para una acción tan rara como editar una transacción.
    Devuelve (n_puntos, mensaje). No relanza: el caller decide si loguea."""
    precios = prep.cargar_precios().ffill()
    trm_serie = pd.read_parquet(TRM_PATH)["TRM"].sort_index()
    return backfill_uno(archivo, precios, trm_serie, recompute=True)


def main():
    args = sys.argv[1:]
    recompute = "--recompute" in args
    args = [a for a in args if a != "--recompute"]

    precios = prep.cargar_precios().ffill()
    trm_serie = pd.read_parquet(TRM_PATH)["TRM"].sort_index()

    archivos = [args[0]] if args else [
        f for f in os.listdir(CARPETA_PORTAFOLIOS) if _es_portafolio_real(f)
    ]

    modo = "RECOMPUTE (reconstruye todo desde transacciones actuales)" if recompute else "backfill (rellena huecos)"
    print(f"=== {modo} ===")
    for archivo in archivos:
        try:
            n, msg = backfill_uno(archivo, precios, trm_serie, recompute=recompute)
            print(f"  {archivo}: {n} puntos — {msg}")
        except Exception as e:
            print(f"  {archivo}: ERROR — {e}")


if __name__ == "__main__":
    main()
