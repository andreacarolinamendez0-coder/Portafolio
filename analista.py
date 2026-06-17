import pandas as pd
import numpy as np
from scipy.optimize import minimize
from datetime import datetime
import warnings

warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURACIÓN
# ============================================================

CARPETA_PRECIOS = "datos/precios"
CARPETA_MACRO = "datos/macro"
CARPETA_REPORTES = "datos/reportes"

import os

os.makedirs(CARPETA_REPORTES, exist_ok=True)

# ============================================================
# PASO 1 — CARGAR DATOS
# ============================================================


def cargar_datos():
    print("📂 Cargando datos del Recolector...")
    precios = pd.read_parquet(f"{CARPETA_PRECIOS}/precios.parquet")
    trm = pd.read_parquet(f"{CARPETA_MACRO}/trm.parquet")
    inf_usa = pd.read_parquet(f"{CARPETA_MACRO}/inflacion_usa.parquet")
    inf_col = pd.read_parquet(f"{CARPETA_MACRO}/inflacion_col.parquet")
    risk_free = pd.read_parquet(f"{CARPETA_MACRO}/risk_free.parquet")
    tasa_banrep = pd.read_parquet(f"{CARPETA_MACRO}/tasa_banrep.parquet")
    tasa_banrep_actual = float(tasa_banrep["Tasa_Banrep"].iloc[-1])
    # CDT típico = Banrep - 0.75% (spread promedio bancos grandes)
    tasa_cdt = tasa_banrep_actual - 0.75

    print(f"✅ Tasa Banrep: {tasa_banrep_actual:.2f}% | CDT estimado: {tasa_cdt:.2f}%")
    print(f"✅ Precios: {precios.shape[0]} días, {precios.shape[1]} activos")
    print(f"✅ TRM: {trm.index.max().date()}")
    print(f"✅ Inflación USA: {inf_usa['Inflacion_USA'].iloc[-1]:.2f}%")
    print(f"✅ Inflación COL: {inf_col['Inflacion_COL'].iloc[-1]:.2f}%")
    print(f"✅ Tasa Libre de Riesgo: {risk_free['Risk_Free'].iloc[-1]:.2f}%")

    return precios, trm, inf_usa, inf_col, risk_free, tasa_cdt


# ============================================================
# PASO 2 — PANEL MAESTRO
# ============================================================


def construir_panel(precios, trm, inf_usa, inf_col, risk_free):
    print("\n🔧 Construyendo panel maestro mensual...")

    precios_m = precios.resample("ME").last()
    trm_m = trm.resample("ME").last()

    panel = precios_m.join(trm_m, how="inner")
    panel = panel.join(inf_col.reindex(panel.index, method="ffill"), how="left")
    panel = panel.join(inf_usa.reindex(panel.index, method="ffill"), how="left")
    panel = panel.join(risk_free.reindex(panel.index, method="ffill"), how="left")

    panel["Inflacion_COL"] = panel["Inflacion_COL"].ffill().fillna(5.0)
    panel["Inflacion_USA"] = panel["Inflacion_USA"].ffill().fillna(3.5)
    panel["Risk_Free"] = panel["Risk_Free"].ffill().fillna(3.7)

    panel["Spread_Inflacion"] = panel["Inflacion_COL"] - panel["Inflacion_USA"]

    def clasificar_tasa(rf):
        if rf < 2.0:
            return -1
        elif rf < 4.0:
            return 0
        else:
            return 1

    panel["Regimen_Tasas"] = panel["Risk_Free"].apply(clasificar_tasa)
    panel["TRM_Momentum"] = panel["TRM"].pct_change(3)

    ultimo = panel.iloc[-1]
    print(f"\n🌍 CONTEXTO MACRO ACTUAL:")
    print(f"   TRM hoy              : ${ultimo['TRM']:,.0f} COP/USD")
    print(f"   Inflación Colombia   : {ultimo['Inflacion_COL']:.2f}%")
    print(f"   Inflación USA        : {ultimo['Inflacion_USA']:.2f}%")
    print(
        f"   Spread (COL-USA)     : {ultimo['Spread_Inflacion']:.2f}% "
        f"{'⚠️ Alto — peso presionado' if ultimo['Spread_Inflacion'] > 3 else '✅ Normal'}"
    )
    print(
        f"   Tasa libre de riesgo : {ultimo['Risk_Free']:.2f}% "
        f"({'📈 Alta — bonos atractivos' if ultimo['Regimen_Tasas'] == 1 else '⚖️ Normal' if ultimo['Regimen_Tasas'] == 0 else '📉 Baja — acciones atractivas'})"
    )
    print(
        f"   TRM últimos 3 meses  : {ultimo['TRM_Momentum']*100:.1f}% "
        f"({'💵 Dólar subiendo' if ultimo['TRM_Momentum'] > 0 else '💵 Dólar bajando'})"
    )
    print(
        f"\n✅ Panel: {panel.shape[0]} meses | "
        f"{panel.index.min().date()} → {panel.index.max().date()}"
    )

    return panel


# ============================================================
# PASO 3 — RETORNOS REALES
# ============================================================


def calcular_retornos_reales(panel, activos):
    print("\n📊 Calculando retornos reales con peso en momentum reciente...")

    precios_cop = panel[activos].multiply(panel["TRM"], axis=0)
    ret_nom = precios_cop.pct_change()
    inf_mensual = (1 + panel["Inflacion_COL"] / 100) ** (1 / 12) - 1
    ret_real = ((1 + ret_nom).divide((1 + inf_mensual), axis=0)) - 1
    ret_real = ret_real.dropna(how="all").fillna(0)

    ultimos_12 = ret_real.iloc[-12:]
    ret_ponderado = pd.concat([ret_real, ultimos_12], axis=0)

    print(f"   Historia total  : {len(ret_real)} meses")
    print(
        f"   Con momentum    : {len(ret_ponderado)} meses "
        f"(últimos 12 meses cuentan doble)"
    )

    return ret_ponderado


# ============================================================
# PASO 4 — OPTIMIZACIÓN
# ============================================================


def optimizar_portafolio(ret_real, panel, perfil, risk_free, inversion_inicial):
    print(f"\n🧠 Optimizando portafolio {perfil.upper()}...")

    rf = risk_free["Risk_Free"].iloc[-1] / 100

    tech_volatil = ["XLK", "QQQ", "NVDA", "BTC-USD", "ETH-USD", "SOL-USD"]
    cripto = ["BTC-USD", "ETH-USD", "SOL-USD"]
    defensivos = ["GLD", "TLT", "KO", "WMT", "JNJ"]
    agresivos_macro = ["NVDA", "MSFT", "GOOGL", "AMZN", "AAPL"]

    spread_inflacion = panel["Spread_Inflacion"].iloc[-1]
    trm_momentum = panel["TRM_Momentum"].iloc[-1]
    regimen = panel["Regimen_Tasas"].iloc[-1]

    def ajustar_media(media, regimen, spread, trm_mom):
        media_ajustada = media.copy()
        for activo in media.index:
            if regimen == 1:
                if activo in defensivos:
                    media_ajustada[activo] *= 1.10
                elif activo in agresivos_macro:
                    media_ajustada[activo] *= 0.92
            if spread > 3:
                media_ajustada[activo] *= 1.05
            if trm_mom > 0.02:
                media_ajustada[activo] *= 1.03
        return media_ajustada

    # Excluir criptos en conservador
    if perfil == "conservador":
        ret_real = ret_real[[a for a in ret_real.columns if a not in cripto]]
        print(f"   🚫 Criptos excluidas del perfil conservador")

    # Filtro de correlación
    print(f"   Eliminando activos redundantes por alta correlación...")
    corr_matrix = ret_real.corr()
    activos_unicos = list(ret_real.columns)
    sharpe_simple = (ret_real.mean() * 12) / (ret_real.std() * np.sqrt(12))
    eliminados = []

    for i in range(len(activos_unicos)):
        for j in range(i + 1, len(activos_unicos)):
            a1 = activos_unicos[i]
            a2 = activos_unicos[j]
            if a1 in eliminados or a2 in eliminados:
                continue
            if corr_matrix.loc[a1, a2] > 0.85:
                if sharpe_simple[a1] >= sharpe_simple[a2]:
                    eliminados.append(a2)
                    print(
                        f"   ⚠️  {a2} eliminado — correlación {corr_matrix.loc[a1,a2]:.2f} con {a1}"
                    )
                else:
                    eliminados.append(a1)
                    print(
                        f"   ⚠️  {a1} eliminado — correlación {corr_matrix.loc[a1,a2]:.2f} con {a2}"
                    )

    activos_limpios = [a for a in activos_unicos if a not in eliminados]
    ret_real = ret_real[activos_limpios]
    print(f"   Activos tras filtro de correlación: {len(activos_limpios)}")

    # Filtro de consistencia
    n_filas = len(ret_real)
    tercio = n_filas // 3
    retorno_p1 = ret_real.iloc[:tercio].mean() * 12
    retorno_p2 = ret_real.iloc[tercio : tercio * 2].mean() * 12
    retorno_p3 = ret_real.iloc[tercio * 2 :].mean() * 12

    consistencia = (
        (retorno_p1 > 0).astype(int)
        + (retorno_p2 > 0).astype(int)
        + (retorno_p3 > 0).astype(int)
    )
    activos_consistentes = consistencia[consistencia >= 2].index.tolist()
    print(f"   Activos que pasaron filtro de consistencia: {len(activos_consistentes)}")

    if len(activos_consistentes) < 3:
        activos_consistentes = ret_real.columns.tolist()

    ret_filtrado = ret_real[activos_consistentes]

    # Top 8 por Sharpe
    media_f = ret_filtrado.mean() * 12
    vol_f = ret_filtrado.std() * np.sqrt(12)
    sharpe_f = (media_f - rf) / vol_f
    top_8 = sharpe_f.nlargest(8).index.tolist()
    ret_top = ret_real[top_8]
    print(f"   Top 8 seleccionados: {top_8}")

    # Optimización
    media = ret_top.mean() * 12
    cov = ret_top.cov() * 12
    n = len(media)
    media = ajustar_media(media, regimen, spread_inflacion, trm_momentum)

    if perfil == "conservador":
        peso_max = 0.25
        peso_min = 0.05

        def objetivo(w):
            return np.sqrt(np.dot(w.T, np.dot(cov, w)))

        idx_tech = [i for i, a in enumerate(top_8) if a in tech_volatil]
        if idx_tech:
            idx_fijo = list(idx_tech)
            restricciones = [
                {"type": "eq", "fun": lambda w: np.sum(w) - 1},
                {"type": "ineq", "fun": lambda w, idx=idx_fijo: 0.20 - np.sum(w[idx])},
            ]
        else:
            restricciones = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    else:
        peso_max = 0.30
        peso_min = 0.05

        def objetivo(w):
            ret_p = np.sum(media * w)
            vol_p = np.sqrt(np.dot(w.T, np.dot(cov, w)))
            return -(ret_p - rf) / vol_p + 0.3 * np.sum(w**2)

        restricciones = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

    limites = [(peso_min, peso_max)] * n
    np.random.seed(42)
    w0 = np.array([1 / n] * n)

    resultado = minimize(
        objetivo,
        w0,
        method="SLSQP",
        bounds=limites,
        constraints=restricciones,
        options={"maxiter": 1000, "ftol": 1e-9},
    )

    pesos = pd.Series(resultado.x, index=top_8)
    top_5 = pesos.nlargest(5)
    top_5 = top_5 / top_5.sum()

    # Límite tech post-normalización en conservador
    if perfil == "conservador":
        tech_en_top5 = [a for a in top_5.index if a in tech_volatil]
        peso_tech_actual = top_5[tech_en_top5].sum()
        if peso_tech_actual > 0.20:
            exceso = peso_tech_actual - 0.20
            for activo in tech_en_top5:
                top_5[activo] -= exceso * (top_5[activo] / peso_tech_actual)
            no_tech = [a for a in top_5.index if a not in tech_volatil]
            for activo in no_tech:
                top_5[activo] += exceso / len(no_tech)
            print(f"   ✅ Límite tech: {peso_tech_actual*100:.1f}% → 20%")
        top_5 = top_5 / top_5.sum()

    return top_5, inversion_inicial


# ============================================================
# PASO 5 — PROYECCIÓN CON DCA
# ============================================================


def proyectar_con_dca(
    ret_port,
    inversion_inicial,
    aporte_periodico,
    frecuencia_meses,
    horizonte_años,
    inflacion_col,
    tasa_cdt,
    n_sim=500,
):
    """
    Proyecta riqueza con y sin DCA.
    Todos los valores se expresan en PESOS DE HOY (deflactados).
    Compara contra CDT.
    """
    mu_m = ret_port.mean()
    sigma_m = ret_port.std()
    meses = horizonte_años * 12

    # Inflación mensual para deflactar
    inf_anual = inflacion_col / 100
    inf_mensual = (1 + inf_anual) ** (1 / 12) - 1

    # Tasa CDT mensual
    tasa_cdt_mensual = (1 + tasa_cdt / 100) ** (1 / 12) - 1

    np.random.seed(42)
    resultados_global = []
    resultados_dca = []
    resultados_cdt = []

    for _ in range(n_sim):
        # ── SUMA GLOBAL (portafolio) ──
        retornos = np.random.normal(mu_m, sigma_m, meses)
        valor = inversion_inicial
        for r in retornos:
            valor *= 1 + r
        # Deflactar a pesos de hoy
        valor_real = valor / (1 + inf_anual) ** horizonte_años
        resultados_global.append(valor_real)

        # ── DCA (portafolio con aportes) ──
        retornos = np.random.normal(mu_m, sigma_m, meses)
        valor = inversion_inicial
        for i, r in enumerate(retornos):
            valor *= 1 + r
            if aporte_periodico > 0 and i % frecuencia_meses == 0 and i > 0:
                valor += aporte_periodico
        valor_real = valor / (1 + inf_anual) ** horizonte_años
        resultados_dca.append(valor_real)

        # ── CDT (sin aportes adicionales) ──
        valor_cdt = inversion_inicial
        for _ in range(meses):
            valor_cdt *= 1 + tasa_cdt_mensual
        # CDT también se deflacta
        valor_cdt_real = valor_cdt / (1 + inf_anual) ** horizonte_años
        resultados_cdt.append(valor_cdt_real)

    def percentiles(res):
        r = sorted(res)
        return (r[int(n_sim * 0.10)], r[int(n_sim * 0.50)], r[int(n_sim * 0.90)])

    return (
        percentiles(resultados_global),
        percentiles(resultados_dca),
        percentiles(resultados_cdt),
    )


# ============================================================
# PASO 6 — REPORTE FINAL
# ============================================================

def calcular_datos_reporte(
    pesos,
    inversion_inicial,
    ret_real,
    perfil,
    horizonte,
    risk_free,
    inflacion_col,
    tasa_cdt,
    aporte_periodico=0,
    frecuencia_meses=1,
):
    """Calcula las métricas y proyecciones y las DEVUELVE como dict (sin imprimir)."""
    rf = risk_free["Risk_Free"].iloc[-1] / 100
    activos_port = pesos.index.tolist()
    ret_port = ret_real[activos_port].dot(pesos)
    ret_anual = ret_port.mean() * 12
    vol_anual = ret_port.std() * np.sqrt(12)
    sharpe = (ret_anual - rf) / vol_anual
    cumprod = (ret_port + 1).cumprod()
    max_dd = (cumprod / cumprod.cummax() - 1).min()

    años_proyeccion = sorted(set([3, 5, horizonte]))
    proyecciones = []
    for años in años_proyeccion:
        sin_dca, con_dca, cdt_p = proyectar_con_dca(
            ret_port, inversion_inicial, aporte_periodico,
            frecuencia_meses, años, inflacion_col, tasa_cdt,
        )
        n_aportes = (años * 12 // frecuencia_meses) if aporte_periodico > 0 else 0
        total_aportado = inversion_inicial + (aporte_periodico * n_aportes)
        cdt_nominal = inversion_inicial * (1 + tasa_cdt / 100) ** años
        cdt_real = cdt_nominal / (1 + inflacion_col / 100) ** años
        cdt_real_dca = cdt_real + (aporte_periodico * n_aportes) / (1 + inflacion_col / 100) ** años

        proyecciones.append({
            "anios": años,
            "total_aportado": round(total_aportado, 0),
            "sin_dca": {"pesimista": round(sin_dca[0], 0), "base": round(sin_dca[1], 0), "optimista": round(sin_dca[2], 0)},
            "con_dca": {"pesimista": round(con_dca[0], 0), "base": round(con_dca[1], 0), "optimista": round(con_dca[2], 0)} if aporte_periodico > 0 else None,
            "cdt_real": round(cdt_real, 0),
            "cdt_real_dca": round(cdt_real_dca, 0) if aporte_periodico > 0 else None,
            "ventaja_vs_cdt": round(sin_dca[1] - cdt_real, 0),
            "ventaja_dca_vs_cdt": round(con_dca[1] - cdt_real_dca, 0) if aporte_periodico > 0 else None,
        })

    return {
        "perfil": perfil,
        "horizonte": horizonte,
        "composicion": {a: round(float(p), 4) for a, p in pesos.sort_values(ascending=False).items()},
        "metricas": {
            "retorno_anual": round(ret_anual * 100, 2),
            "volatilidad": round(vol_anual * 100, 2),
            "sharpe": round(float(sharpe), 2),
            "max_drawdown": round(max_dd * 100, 2),
        },
        "inflacion_col": round(inflacion_col, 1),
        "cdt_ref": round(tasa_cdt, 2),
        "inversion_inicial": round(inversion_inicial, 0),
        "aporte_dca": round(aporte_periodico, 0),
        "frecuencia_meses": frecuencia_meses,
        "proyecciones": proyecciones,
    }

def generar_reporte(
    pesos,
    inversion_inicial,
    ret_real,
    perfil,
    horizonte,
    risk_free,
    inflacion_col,
    tasa_cdt,
    aporte_periodico=0,
    frecuencia_meses=1,
):
    # Un solo lugar calcula: reusa calcular_datos_reporte
    d = calcular_datos_reporte(
        pesos=pesos, inversion_inicial=inversion_inicial, ret_real=ret_real,
        perfil=perfil, horizonte=horizonte, risk_free=risk_free,
        inflacion_col=inflacion_col, tasa_cdt=tasa_cdt,
        aporte_periodico=aporte_periodico, frecuencia_meses=frecuencia_meses,
    )
    m = d["metricas"]
    freq_texto = {1: "mensual", 3: "trimestral", 12: "anual"}

    print(f"\n{'='*65}")
    print(f"  PORTAFOLIO {perfil.upper()} — HORIZONTE {horizonte} AÑOS")
    print(f"{'='*65}")

    print(f"\n📊 COMPOSICIÓN:")
    for activo, peso in d["composicion"].items():
        barra = "█" * int(peso * 30)
        print(f"   {activo:<12} {peso*100:5.1f}%  {barra}")

    print(f"\n📈 MÉTRICAS:")
    print(f"   Retorno anual esperado : {m['retorno_anual']:.2f}%")
    print(f"   Volatilidad anual      : {m['volatilidad']:.2f}%")
    print(f"   Sharpe ratio           : {m['sharpe']:.2f}")
    print(f"   Max Drawdown           : {m['max_drawdown']:.2f}%")

    print(f"\n💡 NOTA: Todos los valores están en PESOS DE HOY")
    print(f"   (deflactados con inflación Colombia {inflacion_col:.1f}% anual)")
    print(f"   CDT de referencia: {tasa_cdt:.2f}% anual")

    print(f"\n💰 PROYECCIÓN (inversión inicial ${inversion_inicial:,.0f} COP):")
    for p in d["proyecciones"]:
        años = p["anios"]
        if aporte_periodico > 0:
            extra = f" (total aportado: ${p['total_aportado']:,.0f})"
        else:
            extra = ""
        print(f"\n   📅 En {años} años{extra}:")
        print(f"   {'─'*60}")
        print(f"   {'Escenario':<28} {'Pesimista':>12} {'Base':>12} {'Optimista':>12}")
        print(f"   {'─'*60}")
        s = p["sin_dca"]
        print(
            f"   {'Portafolio (sin aportes)':<28} "
            f"${s['pesimista']:>10,.0f} ${s['base']:>10,.0f} ${s['optimista']:>10,.0f}"
        )
        if aporte_periodico > 0 and p["con_dca"]:
            c = p["con_dca"]
            freq = freq_texto.get(frecuencia_meses, f"c/{frecuencia_meses}m")
            print(
                f"   {'Portafolio + DCA '+freq:<28} "
                f"${c['pesimista']:>10,.0f} ${c['base']:>10,.0f} ${c['optimista']:>10,.0f}"
            )
        print(f"   {'CDT (referencia)':<28} {'':>12} ${p['cdt_real']:>10,.0f} {'':>12}")
        if aporte_periodico > 0 and p["cdt_real_dca"] is not None:
            print(f"   {'CDT + aportes':<28} {'':>12} ${p['cdt_real_dca']:>10,.0f} {'':>12}")
        print(f"   {'─'*60}")
        print(f"   💡 Ventaja portafolio vs CDT (base): ${p['ventaja_vs_cdt']:>10,.0f}")
        if aporte_periodico > 0 and p["ventaja_dca_vs_cdt"] is not None:
            print(f"   💡 Ventaja DCA vs CDT+aportes (base): ${p['ventaja_dca_vs_cdt']:>10,.0f}")

    # Guardar reporte
    fecha = datetime.now().strftime("%Y%m%d")
    archivo = f"{CARPETA_REPORTES}/reporte_{perfil}_{fecha}.csv"
    pd.DataFrame({
        "Activo": list(d["composicion"].keys()),
        "Peso_%": [round(v * 100, 2) for v in d["composicion"].values()],
    }).to_csv(archivo, index=False)
    print(f"\n💾 Reporte guardado: {archivo}")

# ============================================================
# EJECUCIÓN PRINCIPAL
# ============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("🤖 ANALISTA — INICIANDO")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    # ── ACTUALIZAR DATOS ANTES DE ANALIZAR ──
    print("\n🔄 Actualizando datos del mercado...")
    import subprocess

    subprocess.run(["python", "recolector.py"], check=False)
    print("✅ Datos actualizados.\n")

    # ── LEER PORTAFOLIO ACTIVO ──
    from gestor_portafolio import leer_portafolio_activo, guardar_composicion

    portafolio_activo = leer_portafolio_activo()
    if not portafolio_activo:
        print("❌ No hay portafolio activo.")
        print("   Corre primero: python gestor_portafolio.py")
        exit()

    perfil_activo = portafolio_activo["perfil"]
    nombre = portafolio_activo["nombre"]
    propietario = portafolio_activo["propietario"]
    archivo = (
        portafolio_activo.get("archivo")
        or nombre.lower()
        .replace(" ", "_")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        + ".json"
    )

    print(f"\n📋 Portafolio activo: {nombre} ({perfil_activo}) — {propietario}")

    # ── INVERSIÓN INTERACTIVA ──
    inv_inicial = portafolio_activo.get("inversion_inicial", 0)
    aporte_dca = portafolio_activo.get("aporte_dca", 0)
    freq_dca = portafolio_activo.get("frecuencia_meses", 1)

    print(f"\n💰 CONFIGURACIÓN DE INVERSIÓN")
    print(f"─" * 40)
    print(f"   (del portafolio activo)")
    print(f"   Inversión inicial : ${inv_inicial:,.0f} COP")
    if aporte_dca > 0:
        freq_texto = {1: "mensual", 3: "trimestral", 12: "anual"}
        print(
            f"   Aporte DCA        : ${aporte_dca:,.0f} COP "
            f"({freq_texto.get(freq_dca, 'periódico')})"
        )

    # Permitir cambiar montos si se quiere simular diferente
    cambiar = input("\n   ¿Quieres simular con montos diferentes? (SI/NO): ").upper()
    if cambiar == "SI":
        inv_str = input("   Inversión inicial en COP: ")
        inv_inicial = float(inv_str.replace(",", "").replace(".", ""))
        tiene_dca = input("   ¿Con DCA? (SI/NO): ").upper()
        if tiene_dca == "SI":
            ap_str = input("   ¿Cuánto por aporte? ")
            aporte_dca = float(ap_str.replace(",", "").replace(".", ""))
            print("   1=Mensual | 3=Trimestral | 12=Anual")
            freq_dca = int(input("   Frecuencia: "))
        else:
            aporte_dca = 0
            freq_dca = 1

    inversion_inicial = inv_inicial
    aporte_periodico = aporte_dca
    frecuencia_meses = freq_dca if freq_dca > 0 else 1

    # ── CARGAR DATOS ──
    precios, trm, inf_usa, inf_col, risk_free, tasa_cdt = cargar_datos()
    activos = [c for c in precios.columns if c not in ["JPMV", "META"]]
    panel = construir_panel(precios, trm, inf_usa, inf_col, risk_free)
    ret_real = calcular_retornos_reales(panel, activos)

    inflacion_col_actual = float(
        pd.read_parquet(f"{CARPETA_MACRO}/inflacion_col.parquet")["Inflacion_COL"].iloc[
            -1
        ]
    )

    # ── OPTIMIZAR SOLO EL PERFIL ACTIVO ──
    horizonte = 5 if perfil_activo == "conservador" else 10

    pesos, inv = optimizar_portafolio(
        ret_real, panel, perfil_activo, risk_free, inversion_inicial
    )

    generar_reporte(
        pesos,
        inversion_inicial,
        ret_real,
        perfil_activo,
        horizonte=horizonte,
        risk_free=risk_free,
        inflacion_col=inflacion_col_actual,
        tasa_cdt=tasa_cdt,
        aporte_periodico=aporte_periodico,
        frecuencia_meses=frecuencia_meses,
    )

    # ── GUARDAR COMPOSICIÓN AUTOMÁTICAMENTE ──
    guardar_composicion(archivo, pesos.to_dict())
    print(f"\n✅ Composición guardada automáticamente en '{nombre}'.")
    print("\n✅ ANÁLISIS COMPLETO")
