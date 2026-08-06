"""
adaptador_analista.py
=====================
Conecta el motor nuevo con la interfaz que ya tiene analista.py.

QUE REEMPLAZA
-------------
optimizar_portafolio() — la vieja tenia estos bugs documentados:
  - fillna(0): fabricaba retornos donde no habia datos
  - duplicar ultimos 12 meses: corrompía media, vol y drawdown
  - ajustar_media(1.10, 0.92): numeros inventados sin calibracion
  - rf del T-bill vs retornos reales COP: peras con manzanas
  - top_n = pesos.nlargest(5): rompia la optimizacion

QUE NO TOCA
-----------
  - calcular_retornos_reales()   <- se llama igual, solo se ignoran sus bugs
  - calcular_datos_reporte()     <- se llama igual, con entradas corregidas
  - generar_reporte()            <- sin cambios
  - proyectar_con_dca()          <- sin cambios

CONVERSION DE RETORNOS
----------------------
calcular_datos_reporte() espera retornos MENSUALES SIMPLES en COP REAL.
El motor nuevo produce retornos DIARIOS LOG en USD NOMINAL.

Conversion correcta:
  1. diario log USD  -> mensual log USD  (resample: suma de logs del mes)
  2. mensual log USD -> mensual simple USD  (exp - 1)
  3. simple USD      -> simple COP  (multiplicar por (1 + ret_TRM_mensual))
  4. simple COP nom  -> simple COP real  (dividir por (1 + inf_mensual))

Se hace sobre el portafolio agregado (serie de 1 dimension), no activo por
activo, para que calcular_datos_reporte() lo reciba en el formato que ya
conoce: una Serie de retornos mensuales del portafolio.

PERFIL -> PERDIDA TOLERADA
--------------------------
Puente temporal hasta que el onboarding pregunte L directamente.
Los numeros son un juicio — no estan derivados de ninguna formula.
"""

import numpy as np
import pandas as pd

import analista_motor as am
import perfilador as pf

PERDIDA_POR_PERFIL = {
    "conservador": 0.07,
    "moderado":    0.15,
    "agresivo":    0.25,
}

AÑOS_POR_HORIZONTE = {
    "corto":  2,
    "medio":  5,
    "largo": 15,
}

ADVERTENCIA_CONCENTRACION_CATEGORIA = (
    "Este portafolio se concentra en una o dos categorías/sectores de "
    "activos, tal como lo pediste, con los de mejor desempeño dentro de "
    "esa(s) categoría(s). No debe usarse como tu único portafolio de "
    "inversión: este análisis no evalúa su interacción con otros sectores o "
    "activos que puedas tener. Úsalo con cautela, idealmente como "
    "complemento si ya cuentas con otras inversiones diversificadas."
)

MAR_ANUAL    = 0.045
VIDA_MEDIA   = 126


def _ret_mensual_cop_real(
    pesos: pd.Series,
    retornos_diarios_usd: pd.DataFrame,
    trm: pd.Series,
    inflacion_col_mensual: pd.Series,
) -> pd.Series:
    """Convierte retornos diarios log USD -> mensuales simples COP real.

    Esta es la conversion que hace calcular_retornos_reales() de analista.py,
    pero sin los dos bugs:
      - NO hace fillna(0)
      - NO duplica los ultimos 12 meses
    """
    # 1. Serie diaria log del portafolio en USD
    activos = list(pesos.index)
    w = pesos.values
    r_diario_log = (retornos_diarios_usd[activos] * w).sum(axis=1)

    # 2. Agregar a mensual: suma de logs del mes = log del retorno del mes
    r_mens_log = r_diario_log.resample("ME").sum()

    # 3. Log -> simple USD
    r_mens_usd = np.expm1(r_mens_log)

    # 4. TRM mensual: log de TRM diaria, agregado igual
    r_trm_mens = np.expm1(np.log1p(trm).resample("ME").sum())

    # 5. USD -> COP nominal
    #    OJO: alinear SOLO sobre los meses del portafolio. La TRM tiene historia
    #    desde 1991 (415 meses) y el portafolio desde 2019 (80 meses). Multiplicar
    #    series con indices distintos mete NaN en los meses sin traslape, y esos
    #    NaN rompen el cumprod del drawdown (daba -98% falso). Se reindexa la TRM
    #    al indice del portafolio ANTES de operar.
    r_trm_alineada = r_trm_mens.reindex(r_mens_usd.index)
    r_mens_cop_nom = (1 + r_mens_usd) * (1 + r_trm_alineada) - 1

    # 6. COP nominal -> COP real
    inf_m = inflacion_col_mensual.reindex(r_mens_cop_nom.index, method="ffill")
    r_mens_cop_real = (1 + r_mens_cop_nom) / (1 + inf_m) - 1

    # Si el ultimo mes es parcial (pocos dias de bolsa) su retorno esta
    # subestimado; no lo botamos, pero si quedaran NaN por bordes, fuera.
    return r_mens_cop_real.dropna()


def _restringir_universo(retornos, sector, tickers_fijos):
    """Aplica tickers_fijos al universo. Devuelve (retornos, sector,
    saltar_cobertura_sector).

    Tres casos, en este orden (el orden importa: ver comentario en el paso 2):
      1. Sin tickers_fijos, o <2 validos: sin cambios (comportamiento actual).
      2. Tras remapear ETFs sectoriales a su sector GICS equivalente, el
         universo pedido queda en <=2 categorias distintas: es un pedido de
         sector(es) concentrado(s) (ej. "solo tecnologia", con o sin ETF
         sectorial mezclado). Se usa el sector remapeado, sin expandir el
         universo.
      3. Si NO colapsa en <=2 categorias tras el remapeo Y todos los tickers
         son ETFs: es un pedido de vehiculo puro (ej. "solo ETFs", sin tema).
         Se expande a TODO el universo de ETFs disponible, evaluado solo por
         rendimiento (saltar_cobertura_sector=True).

    El check de "todos son ETF" va DESPUES del check de <=2 categorias: si
    fuera al reves, un pedido de "solo bonos" (ya son <=1 categoria hoy)
    terminaria expandiendose innecesariamente a los ~39 ETFs conocidos.
    """
    import preparador_datos as prep

    if not tickers_fijos:
        return retornos, sector, False

    cols = [t for t in tickers_fijos if t in retornos.columns]
    if len(cols) < 2:
        return retornos, sector, False

    sector_efectivo = {
        t: prep.ETF_SECTOR_EQUIVALENTE.get(t, sector.get(t, "Sin clasificar"))
        for t in cols
    }

    if len(set(sector_efectivo.values())) <= 2:
        return retornos[cols], sector_efectivo, False

    if all(t in prep.TODOS_LOS_ETFS for t in cols):
        cols_etf = [t for t in prep.TODOS_LOS_ETFS if t in retornos.columns]
        sector_etf = {t: sector.get(t, "Sin clasificar") for t in cols_etf}
        return retornos[cols_etf], sector_etf, True

    return retornos[cols], sector_efectivo, False


def optimizar_portafolio(
    ret_real=None,
    panel=None,
    perfil: str = "moderado",
    risk_free=None,
    inversion_inicial=None,
    tickers_fijos=None,
    horizonte=10,
    **kwargs,
):
    """Reemplaza optimizar_portafolio() de analista.py.

    COMPATIBLE CON LA FIRMA VIEJA que usa dashboard.py:
        optimizar_portafolio(ret_real, panel, perfil, risk_free, inversion, tickers_fijos=...)

    Devuelve (pesos, inversion_inicial) -- una tupla, como la version vieja --
    para que dashboard.py no tenga que cambiar. Toda la logica nueva (motor,
    perfilador, conversion a COP real) corre por dentro.

    Reconstruye los inputs del motor nuevo a partir de `panel`, que ya trae
    precios mensuales, TRM e inflacion. Para los retornos DIARIOS que el motor
    necesita, vuelve a leer el parquet de precios (panel es mensual y el motor
    trabaja diario).
    """
    import numpy as np
    import os
    import preparador_datos as prep

    # --- Inputs del motor desde el pipeline diario ---
    universo = prep.preparar_universo()
    retornos_diarios = universo["retornos"]
    sector = universo["sector"]

    # Si el usuario fijo tickers, restringir el universo a esos (los que existan)
    retornos_diarios, sector, saltar_cobertura_sector = _restringir_universo(
        retornos_diarios, sector, tickers_fijos
    )

    # TRM diaria en log-retornos (desde panel o desde el parquet)
    import pandas as _pd
    trm_full = _pd.read_parquet("datos/macro/trm.parquet").sort_index()
    retorno_trm = np.log(trm_full["TRM"] / trm_full["TRM"].shift(1)).dropna()

    # Inflacion COL mensual (fraccion) y anual
    inf_df = _pd.read_parquet("datos/macro/inflacion_col.parquet").sort_index()
    inflacion_col_mensual = (inf_df["Inflacion_COL"] / 100).resample("ME").last().ffill()
    inflacion_col_anual = float(inf_df["Inflacion_COL"].iloc[-1]) / 100

    # CDT desde tasa banrep
    try:
        tb = _pd.read_parquet("datos/macro/tasa_banrep.parquet")
        if "fuente" in tb.columns:
            tb = tb[tb["fuente"] != "fallback"]
        cdt_nominal = (float(tb["Tasa_Banrep"].iloc[-1]) - 0.75) / 100
    except Exception:
        cdt_nominal = None

    resultado = _construir(
        perfil=perfil,
        horizonte=horizonte,
        retornos=retornos_diarios,
        sector=sector,
        retorno_trm=retorno_trm,
        inflacion_col_mensual=inflacion_col_mensual,
        cdt_nominal=cdt_nominal,
        inflacion_col_anual=inflacion_col_anual,
        capital=inversion_inicial,
        saltar_cobertura_sector=saltar_cobertura_sector,
    )

    # Guardar el resultado completo en un atributo para que la ruta lo lea si quiere
    optimizar_portafolio.ultimo_resultado = resultado

    # La firma vieja devuelve (pesos, inversion)
    return resultado["pesos"], inversion_inicial


def _construir(
    perfil: str,
    horizonte,
    retornos: pd.DataFrame,
    sector: dict,
    retorno_trm: pd.Series,
    inflacion_col_mensual: pd.Series,
    cdt_nominal: float = None,
    inflacion_col_anual: float = None,
    capital: float = None,
    fraccion_purga: float = 0.30,
    umbral_parcial: float = 0.20,
    saltar_cobertura_sector: bool = False,
) -> dict:
    """Logica real. horizonte: int (años) o string."""
    perfil_norm = perfil.lower().strip()
    if perfil_norm not in PERDIDA_POR_PERFIL:
        raise ValueError(
            f"Perfil '{perfil}' desconocido. Opciones: {list(PERDIDA_POR_PERFIL)}"
        )

    if isinstance(horizonte, str):
        anios = AÑOS_POR_HORIZONTE.get(horizonte.lower().strip(), 5)
    else:
        anios = int(horizonte)

    perdida_tolerada = PERDIDA_POR_PERFIL[perfil_norm]

    # --- Motor nuevo ---
    resultado = am.recomendar(
        retornos=retornos,
        sector=sector,
        retorno_trm=retorno_trm,
        perdida_tolerada=perdida_tolerada,
        anios_horizonte=anios,
        capital=capital,
        cdt_nominal=cdt_nominal,
        inflacion_col=inflacion_col_anual,
        mar_anual=MAR_ANUAL,
        vida_media=VIDA_MEDIA,
        fraccion_purga=fraccion_purga,
        umbral_parcial=umbral_parcial,
        saltar_cobertura_sector=saltar_cobertura_sector,
    )

    port = resultado["portafolio"]
    perf = resultado["perfil"]
    pesos = port["pesos"]

    # --- Retornos mensuales COP real para calcular_datos_reporte() ---
    ret_mens_cop_real = _ret_mensual_cop_real(
        pesos, retornos, retorno_trm, inflacion_col_mensual
    )

    return {
        # Para generar_reporte / calcular_datos_reporte
        "pesos":              pesos,
        "ret_mens_cop_real":  ret_mens_cop_real,

        # Perfil
        "perfil":             perfil_norm,
        "horizonte":          anios,
        "perdida_tolerada":   perdida_tolerada,
        "alfa":               perf["alfa"],
        "en_cdt":             perf["en_cdt"],

        # Riesgo en COP
        "volatilidad_cop":    perf["riesgo"]["sigma_cop"],
        "sigma_trm_pp":       perf["riesgo"]["aporte_trm_pp"],

        # Advertencias
        "advertencia_cdt":    perf.get("advertencia_cdt"),
        "montos":             perf.get("montos"),

        # Trazabilidad del motor
        "detalle":            port["detalle"],
        "embudo":             port["embudo"],
        "parcial_maxima":     port["parcial_maxima"],
        "shrinkage":          port["shrinkage"],
        "seleccion":          port["seleccion"],
    }


# ============================================================
# FUNCIONES DE ALTO NIVEL PARA EL DASHBOARD
# ============================================================
# Encapsulan TODO el pipeline para que las rutas de Flask no tengan que
# saber nada del motor. Devuelven diccionarios listos para jsonify.

def _cargar_todo_para_motor(tickers_fijos=None):
    """Lee parquets y arma los inputs del motor. Un solo lugar."""
    import numpy as np
    import pandas as pd
    import preparador_datos as prep

    universo = prep.preparar_universo()
    retornos = universo["retornos"]
    sector = universo["sector"]

    retornos, sector, saltar_cobertura_sector = _restringir_universo(
        retornos, sector, tickers_fijos
    )

    trm = pd.read_parquet("datos/macro/trm.parquet").sort_index()
    ret_trm = np.log(trm["TRM"] / trm["TRM"].shift(1)).dropna()

    inf_df = pd.read_parquet("datos/macro/inflacion_col.parquet").sort_index()
    # Inflacion_COL viene como variacion ANUAL en porcentaje (ej 6.14 = 6.14%/año).
    # Para deflactar retornos MENSUALES hay que convertir esa tasa anual a su
    # equivalente mensual: (1+anual)^(1/12) - 1. Antes se dividia /100 y se usaba
    # tal cual mes a mes -> se restaba ~11% CADA mes -> retorno anual -65% falso.
    inf_anual_frac = (inf_df["Inflacion_COL"] / 100).resample("ME").last().ffill()
    inf_col_m = (1 + inf_anual_frac) ** (1/12) - 1
    inf_col_anual = float(inf_df["Inflacion_COL"].iloc[-1]) / 100

    try:
        tb = pd.read_parquet("datos/macro/tasa_banrep.parquet")
        if "fuente" in tb.columns:
            tb = tb[tb["fuente"] != "fallback"]
        cdt_nominal = (float(tb["Tasa_Banrep"].iloc[-1]) - 0.75) / 100
    except Exception:
        cdt_nominal = 0.105

    return {
        "retornos": retornos, "sector": sector, "ret_trm": ret_trm,
        "inf_col_m": inf_col_m, "inf_col_anual": inf_col_anual,
        "cdt_nominal": cdt_nominal, "saltar_cobertura_sector": saltar_cobertura_sector,
    }


def _proyeccion_montecarlo(ret_mens_cop_real, inversion, aporte, freq, horizonte,
                           inf_col_anual, cdt_nominal):
    """Monte Carlo sobre la serie de retornos MENSUALES COP REAL del motor.
    Reemplaza proyectar_con_dca usando datos sin bugs."""
    import numpy as np

    mu_m = float(ret_mens_cop_real.mean())
    sigma_m = float(ret_mens_cop_real.std())
    meses = horizonte * 12
    n_sim = 500

    tasa_cdt_m = (1 + cdt_nominal) ** (1/12) - 1
    # el CDT ya esta en nominal COP; lo pasamos a real dividiendo por inflacion
    valor_cdt = inversion * (1 + tasa_cdt_m) ** meses
    valor_cdt_real = valor_cdt / (1 + inf_col_anual) ** horizonte

    valor_cdt_dca = inversion
    for i in range(meses):
        valor_cdt_dca *= (1 + tasa_cdt_m)
        if aporte > 0 and i % freq == 0 and i > 0:
            valor_cdt_dca += aporte
    valor_cdt_dca_real = valor_cdt_dca / (1 + inf_col_anual) ** horizonte

    np.random.seed(42)
    glob, dca = [], []
    for _ in range(n_sim):
        rs = np.random.normal(mu_m, sigma_m, meses)
        v = inversion
        for r in rs:
            v *= (1 + r)
        glob.append(v)  # ya es real: ret_mens_cop_real ya esta deflactado

        rs = np.random.normal(mu_m, sigma_m, meses)
        v = inversion
        for i, r in enumerate(rs):
            v *= (1 + r)
            if aporte > 0 and i % freq == 0 and i > 0:
                v += aporte
        dca.append(v)

    def pct(res):
        r = sorted(res)
        return (r[int(n_sim*0.10)], r[int(n_sim*0.50)], r[int(n_sim*0.90)])

    return pct(glob), pct(dca), valor_cdt_real, valor_cdt_dca_real


def _construir_datos_reporte(ret_mens, pesos_dict, inversion, aporte, freq,
                             horizonte, inf_col_anual, cdt_nominal):
    """Arma el dict de datos + texto del reporte, con la serie del motor."""
    import numpy as np

    ret_anual = float(ret_mens.mean() * 12)
    vol_anual = float(ret_mens.std() * np.sqrt(12))
    rf_real = (1 + cdt_nominal) / (1 + inf_col_anual) - 1   # CDT real como libre de riesgo
    sharpe = (ret_anual - rf_real) / vol_anual if vol_anual > 0 else 0.0
    cumprod = (ret_mens + 1).cumprod()
    max_dd = float((cumprod / cumprod.cummax() - 1).min())

    proyecciones = []
    for anios in sorted(set([3, 5, horizonte])):
        sin_dca, con_dca, cdt_r, cdt_r_dca = _proyeccion_montecarlo(
            ret_mens, inversion, aporte, freq, anios, inf_col_anual, cdt_nominal
        )
        n_aportes = (anios * 12 // freq) if aporte > 0 else 0
        total_ap = inversion + aporte * n_aportes
        proyecciones.append({
            "anios": anios,
            "total_aportado": round(total_ap, 0),
            "sin_dca": {"pesimista": round(sin_dca[0],0), "base": round(sin_dca[1],0), "optimista": round(sin_dca[2],0)},
            "con_dca": ({"pesimista": round(con_dca[0],0), "base": round(con_dca[1],0), "optimista": round(con_dca[2],0)} if aporte > 0 else None),
            "cdt_real": round(cdt_r, 0),
            "cdt_real_dca": round(cdt_r_dca, 0) if aporte > 0 else None,
            "ventaja_vs_cdt": round(sin_dca[1] - cdt_r, 0),
            "ventaja_dca_vs_cdt": round(con_dca[1] - cdt_r_dca, 0) if aporte > 0 else None,
        })

    datos = {
        "metricas": {
            "retorno_anual": round(ret_anual*100, 2),
            "volatilidad": round(vol_anual*100, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd*100, 2),
        },
        "composicion": {a: round(float(p), 4) for a, p in
                        sorted(pesos_dict.items(), key=lambda x: -x[1])},
        "proyecciones": proyecciones,
    }

    # Texto del reporte
    L = []
    L.append(f"MÉTRICAS (COP real)")
    L.append(f"  Retorno anual : {datos['metricas']['retorno_anual']:.2f}%")
    L.append(f"  Volatilidad   : {datos['metricas']['volatilidad']:.2f}%")
    L.append(f"  Sharpe (vs CDT): {datos['metricas']['sharpe']:.2f}")
    L.append(f"  Max Drawdown  : {datos['metricas']['max_drawdown']:.2f}%")
    L.append("")
    for p in proyecciones:
        L.append(f"En {p['anios']} años:")
        s = p["sin_dca"]
        L.append(f"  Portafolio: ${s['pesimista']:,.0f} / ${s['base']:,.0f} / ${s['optimista']:,.0f}")
        L.append(f"  CDT ref   : ${p['cdt_real']:,.0f}")
        L.append(f"  Ventaja vs CDT: ${p['ventaja_vs_cdt']:,.0f}")
        L.append("")
    reporte_txt = "\n".join(L)

    return datos, reporte_txt


def generar_propuesta_completa(perfil, horizonte, inversion, aporte_dca=0,
                                frecuencia_meses=1, tickers_fijos=None):
    """TODO el pipeline para /api/generar-propuesta. Devuelve dict listo."""
    ins = _cargar_todo_para_motor(tickers_fijos)

    res = _construir(
        perfil=perfil, horizonte=horizonte,
        retornos=ins["retornos"], sector=ins["sector"],
        retorno_trm=ins["ret_trm"], inflacion_col_mensual=ins["inf_col_m"],
        cdt_nominal=ins["cdt_nominal"], inflacion_col_anual=ins["inf_col_anual"],
        capital=inversion,
        saltar_cobertura_sector=ins["saltar_cobertura_sector"],
    )

    pesos = res["pesos"]
    ret_mens = _ret_mensual_cop_real(pesos, ins["retornos"], ins["ret_trm"], ins["inf_col_m"])

    datos, reporte_txt = _construir_datos_reporte(
        ret_mens, pesos.to_dict(), inversion, aporte_dca, frecuencia_meses,
        horizonte, ins["inf_col_anual"], ins["cdt_nominal"]
    )

    sector_concentrado = bool(res["seleccion"].get("sector_concentrado"))

    return {
        "pesos": pesos.to_dict(),
        "reporte_txt": reporte_txt,
        "datos": datos,
        "alfa": res.get("alfa"),
        "advertencia_cdt": res.get("advertencia_cdt") or "",
        "advertencia_concentracion": (
            ADVERTENCIA_CONCENTRACION_CATEGORIA if sector_concentrado else None
        ),
    }


def recalcular_con_pesos(pesos_usuario, perfil, inversion, aporte_dca=0,
                          frecuencia_meses=1, horizonte=10):
    """Para /api/recalcular-proyecciones. El usuario edito pesos a mano."""
    import pandas as pd
    ins = _cargar_todo_para_motor(tickers_fijos=list(pesos_usuario.keys()))

    # Normalizar pesos del usuario y quedarse con los que tienen historia
    con_hist = {k: v for k, v in pesos_usuario.items() if k in ins["retornos"].columns}
    sin_hist = {k: v for k, v in pesos_usuario.items() if k not in ins["retornos"].columns}

    if not con_hist:
        return {"datos": None, "reporte_txt": "Sin activos con histórico.",
                "nota_nuevos": ", ".join(sin_hist.keys())}

    total = sum(con_hist.values())
    pesos = pd.Series({k: v/total for k, v in con_hist.items()})

    ret_mens = _ret_mensual_cop_real(pesos, ins["retornos"], ins["ret_trm"], ins["inf_col_m"])
    datos, reporte_txt = _construir_datos_reporte(
        ret_mens, pesos.to_dict(), inversion, aporte_dca, frecuencia_meses,
        horizonte, ins["inf_col_anual"], ins["cdt_nominal"]
    )

    nota = ""
    if sin_hist:
        nota = (f"{', '.join(sin_hist.keys())} agregado manualmente. Las proyecciones "
                f"corresponden al resto; su histórico estará en el próximo análisis.")

    return {"datos": datos, "reporte_txt": reporte_txt, "nota_nuevos": nota}