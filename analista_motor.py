"""
analista_motor.py
=================
Orquestador. Corre el pipeline completo y devuelve el portafolio final.

    preparador_datos  ->  universo limpio y alineado
        |
    covarianza EWMA (vida media 126)   <- riesgo de AHORA, no promedio de 5 años
        |
    Sortino (historico completo) -> purga el peor 30%
        |
    correlacion parcial -> purga redundancias (riesgo propio duplicado)
        |
    cobertura por sector -> el mejor de cada sector (frena la gravedad a bonos)
        |
    HRP -> pesos
        |
    perfilador -> alfa: cuanto al portafolio, cuanto al CDT

CADA VENTANA CON SU PROPOSITO (todo medido sobre los datos reales):

    Sortino    -> HISTORICO COMPLETO. La ventana corta empeora la prediccion
                  del retorno 15.6% y el ranking solo coincide 17/29.
    Covarianza -> PONDERADA AL RECIENTE. La equiponderada tiene 46% mas error
                  en volatilidad. La vol se agrupa en racimos (Engle, 1982).

DONDE ENTRA mu: solo en la purga de Sortino, y solo para una pregunta gruesa
("¿tercio de abajo?"). Nunca para "¿cual es el mejor?". Todo lo demas --
parcial, sector, HRP, alfa -- es 100% riesgo, cero mu.
"""

import numpy as np
import pandas as pd

import covarianza as cv
import red_riesgo as rr
import motor_seleccion as ms
import ponderador as pd_
import perfilador as pf


def construir_portafolio(
    retornos: pd.DataFrame,
    sector: dict,
    mar_anual: float = 0.045,
    vida_media: float = cv.VIDA_MEDIA_DEFECTO,
    fraccion_purga: float = 0.30,
    umbral_parcial: float = 0.20,
    solo_negativos: bool = False,
    saltar_cobertura_sector: bool = False,
) -> dict:
    """Construye el portafolio RIESGOSO. Igual para todos los perfiles.

    mar_anual: por defecto 4.5% (tasa libre USD nominal, que es la moneda de
        los retornos). Con MAR=0 el motor mete SHY de primero -- y la seguridad
        es trabajo del alfa, no del sobre riesgoso.
    """
    # --- Covarianza ponderada al reciente ---
    cov = cv.covarianza_robusta(retornos, vida_media=vida_media)

    # --- Correlacion parcial sobre esa covarianza ---
    parcial = rr.matriz_correlacion_parcial(cov["covarianza"])

    # --- Seleccion: Sortino -> parcial -> sector ---
    sel = ms.seleccionar(
        retornos=retornos,
        corr_parcial=parcial,
        sector=sector,
        mar_anual=mar_anual,
        fraccion_purga=fraccion_purga,
        umbral_parcial=umbral_parcial,
        solo_negativos=solo_negativos,
        saltar_cobertura_sector=saltar_cobertura_sector,
    )
    activos = sel["seleccion"]

    # --- HRP sobre la misma covarianza, restringida a los seleccionados ---
    cov_sel = cov["covarianza"].loc[activos, activos]
    hrp = pd_.ponderar_hrp(cov_sel)

    vol = pd_.volatilidad_portafolio(hrp["pesos"], cov_sel)

    detalle = pd.DataFrame({
        "activo": activos,
        "sector": [sector.get(a, "?") for a in activos],
        "peso": [round(float(hrp["pesos"][a]), 4) for a in activos],
        "sortino": [round(float(sel["sortino"][a]), 3) for a in activos],
        "vol_anual": [round(float(np.sqrt(cov_sel.loc[a, a] * 252)), 4) for a in activos],
    }).sort_values("peso", ascending=False).reset_index(drop=True)

    return {
        "pesos": hrp["pesos"],
        "detalle": detalle,
        "volatilidad_usd": vol,
        "n_efectivo": hrp["n_efectivo"],
        "covarianza": cov["covarianza"],
        "shrinkage": cov["shrinkage"],
        "T_efectivo": cov["T_efectivo"],
        "T_efectivo_sobre_N": cov["T_efectivo_sobre_N"],
        "correlacion_parcial": parcial,
        "seleccion": sel,
        "embudo": sel["embudo"],
        "parcial_maxima": sel["parcial_maxima_seleccion"],
    }


def recomendar(
    retornos: pd.DataFrame,
    sector: dict,
    retorno_trm: pd.Series,
    perdida_tolerada: float,
    anios_horizonte: float = 99,
    capital: float = None,
    cdt_nominal: float = None,
    inflacion_col: float = None,
    **kwargs,
) -> dict:
    """Pipeline completo: portafolio riesgoso + alfa del usuario."""
    port = construir_portafolio(retornos, sector, **kwargs)

    perfil = pf.perfilar(
        pesos=port["pesos"],
        retornos=retornos,
        retorno_trm=retorno_trm,
        perdida_tolerada=perdida_tolerada,
        anios_horizonte=anios_horizonte,
        cdt_nominal=cdt_nominal,
        inflacion_col=inflacion_col,
        capital=capital,
    )

    final = port["detalle"].copy()
    final["peso_final"] = (final["peso"] * perfil["alfa"]).round(4)
    if capital is not None:
        final["monto"] = (final["peso_final"] * capital).round(0)

    return {"portafolio": port, "perfil": perfil, "asignacion_final": final}


def imprimir(res: dict):
    """Reporte legible del resultado de recomendar()."""
    p, perf, fin = res["portafolio"], res["perfil"], res["asignacion_final"]

    print("=" * 72)
    print("EMBUDO DE SELECCION")
    print("=" * 72)
    for k, v in p["embudo"].items():
        print(f"   {k:<22} {v:>4}")
    print()
    print(f"   covarianza: shrinkage={p['shrinkage']:.3f} | "
          f"T_efectivo={p['T_efectivo']:.0f} | T_eff/N={p['T_efectivo_sobre_N']:.1f}")
    print(f"   parcial maxima entre seleccionados: {p['parcial_maxima']:.3f}")

    print()
    print("=" * 72)
    print("PORTAFOLIO RIESGOSO  (igual para todos los perfiles)")
    print("=" * 72)
    print(p["detalle"].to_string(index=False))
    print()
    print(f"   volatilidad en USD : {p['volatilidad_usd']:.2%}")
    print(f"   N efectivo         : {p['n_efectivo']:.1f}")

    r = perf["riesgo"]
    print()
    print("=" * 72)
    print("RIESGO EN PESOS COLOMBIANOS")
    print("=" * 72)
    print(f"   sigma en USD          : {r['sigma_usd']:>7.2%}")
    print(f"   sigma de la TRM       : {r['sigma_trm']:>7.2%}")
    print(f"   corr(portafolio, TRM) : {r['corr_portafolio_trm']:>7.3f}")
    print(f"   sigma en COP          : {r['sigma_cop']:>7.2%}")
    print(f"   -> la TRM agrega {r['aporte_trm_pp']:+.2f} puntos de volatilidad")

    print()
    print("=" * 72)
    print("PERFIL")
    print("=" * 72)
    print(f"   alfa por tolerancia : {perf['alfa_por_tolerancia']:>7.1%}")
    print(f"   alfa por plazo      : {perf['alfa_por_plazo']:>7.1%}")
    print(f"   ALFA FINAL          : {perf['alfa']:>7.1%}   (manda: {perf['restriccion_que_manda']})")
    print(f"   al CDT              : {perf['en_cdt']:>7.1%}")

    if "advertencia_cdt" in perf:
        print()
        print("   ADVERTENCIA:")
        for linea in _envolver(perf["advertencia_cdt"], 66):
            print(f"      {linea}")

    if "montos" in perf:
        m = perf["montos"]
        print()
        print("=" * 72)
        print("CONFIRMACION EN PESOS")
        print("=" * 72)
        for linea in _envolver(m["pregunta_de_confirmacion"], 66):
            print(f"   {linea}")

    print()
    print("=" * 72)
    print("ASIGNACION FINAL")
    print("=" * 72)
    print(fin.to_string(index=False))


def _envolver(texto, ancho):
    palabras, linea, out = texto.split(), "", []
    for p in palabras:
        if len(linea) + len(p) + 1 > ancho:
            out.append(linea); linea = p
        else:
            linea = f"{linea} {p}".strip()
    if linea:
        out.append(linea)
    return out