import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import requests
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings("ignore")

from gestor_portafolio import (
    listar_portafolios,
    leer_portafolio,
    guardar_aporte,
    activar_portafolio,
)

# ============================================================
# CONFIGURACIÓN
# ============================================================

TELEGRAM_TOKEN = "8332465511:AAH-PlentkDhWWNenLGOdvJCLC6OXNEnrA8"
TELEGRAM_CHAT_ID = "6999614895"
CARPETA_PORT = "datos/portafolios"


def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Error Telegram: {e}")


# ============================================================
# UTILIDADES
# ============================================================


def leer_trm_actual():
    try:
        trm = pd.read_parquet("datos/macro/trm.parquet")
        return float(trm["TRM"].iloc[-1])
    except:
        return 4000.0


def leer_trm_historica(fecha_str):
    try:
        trm = pd.read_parquet("datos/macro/trm.parquet")
        fecha = pd.to_datetime(fecha_str)
        idx = trm.index.get_indexer([fecha], method="nearest")[0]
        return float(trm["TRM"].iloc[idx])
    except:
        return leer_trm_actual()


def leer_inflacion_col():
    try:
        inf = pd.read_parquet("datos/macro/inflacion_col.parquet")
        return float(inf["Inflacion_COL"].iloc[-1])
    except:
        return 4.90


def deflactar(valor_cop, fecha_str, inf_anual):
    fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
    años = (datetime.now() - fecha).days / 365.25
    return valor_cop / (1 + inf_anual / 100) ** años


def precio_actual_usd(ticker):
    try:
        hoy = datetime.now()
        inicio = (hoy - timedelta(days=5)).strftime("%Y-%m-%d")
        fin = hoy.strftime("%Y-%m-%d")
        df = yf.download(
            ticker,
            start=inicio,
            end=fin,
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            # Fallback: intentar con period
            df = yf.download(
                ticker, period="5d", interval="1d", auto_adjust=True, progress=False
            )
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return float(df["Close"].iloc[-1])
    except:
        return None


def precios_mercado(activos):
    print("   📡 Descargando precios actuales...")
    precios = {}
    for ticker in activos:
        precio = precio_actual_usd(ticker)
        if precio:
            precios[ticker] = precio
            print(f"   {ticker:<12} ${precio:,.2f} USD")
        else:
            print(f"   {ticker:<12} ⚠️ sin precio")
    return precios


# ============================================================
# PASO 1 — SELECCIONAR PORTAFOLIO
# ============================================================


def seleccionar_portafolio():
    """Muestra lista y permite seleccionar portafolio a revisar."""
    portafolios = listar_portafolios()

    if not portafolios:
        print("❌ No hay portafolios creados.")
        print("   Corre primero: python gestor_portafolio.py")
        return None, None

    print("\n📋 ¿Cuál portafolio quieres revisar?")
    for i, p in enumerate(portafolios, 1):
        estado = "🟢 ACTIVO" if p["activo"] else "⚪"
        print(
            f"   {i}. {estado} {p['nombre']} " f"({p['perfil']}) — {p['propietario']}"
        )

    num = int(input("\n   Escribe el número: ")) - 1
    if 0 <= num < len(portafolios):
        p_sel = portafolios[num]
        data = leer_portafolio(p_sel["archivo"])
        return p_sel["archivo"], data
    else:
        print("❌ Número inválido.")
        return None, None


# ============================================================
# PASO 2 — INICIALIZAR APORTES
# ============================================================


def inicializar_aportes(archivo, portafolio):
    """
    Si el portafolio no tiene aportes registrados,
    registra la inversión inicial con precios reales de hoy.
    """
    if portafolio.get("aportes") and len(portafolio["aportes"]) > 0:
        print(f"✅ {len(portafolio['aportes'])} aporte(s) registrado(s).")
        return portafolio

    print("\n🆕 PRIMER USO — Registrando inversión inicial")
    print("─" * 50)
    print("Usando precios actuales del mercado para calcular fracciones.\n")

    composicion = portafolio.get("composicion", {})
    if not composicion:
        print("⚠️ Este portafolio no tiene composición asignada.")
        print("   Corre primero el Analista 1 para asignarle una composición.")
        return portafolio

    inv_inicial = portafolio.get("inversion_inicial", 0)
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    trm_actual = leer_trm_actual()

    print(f"   Inversión inicial : ${inv_inicial:,.0f} COP")
    print(f"   TRM actual        : ${trm_actual:,.0f}")
    print(f"   Composición       : {list(composicion.keys())}\n")

    # Descargar precios actuales
    precios = precios_mercado(list(composicion.keys()))

    print(f"\n📋 DISTRIBUCIÓN INICIAL:")
    print(
        f"   {'Activo':<12} {'Peso':>6} {'Monto COP':>14} "
        f"{'Precio USD':>12} {'Fracciones':>12}"
    )
    print(f"   {'─'*60}")

    for activo, peso in composicion.items():
        monto_cop = inv_inicial * peso
        precio = precios.get(activo)

        if precio is None:
            print(f"   {activo:<12} ⚠️ sin precio — omitido")
            continue

        fracciones = monto_cop / (precio * trm_actual)

        print(
            f"   {activo:<12} {peso*100:>5.1f}% "
            f"${monto_cop:>13,.0f} "
            f"${precio:>11,.2f} "
            f"{fracciones:>11.4f}"
        )

        aporte = {
            "fecha": fecha_hoy,
            "activo": activo,
            "monto_cop": round(monto_cop, 0),
            "precio_usd": precio,
            "trm_dia": trm_actual,
            "fracciones": round(fracciones, 6),
            "tipo": "inicial",
        }
        guardar_aporte(archivo, aporte)

    # Recargar portafolio con los aportes guardados
    portafolio = leer_portafolio(archivo)
    print(f"\n✅ Inversión inicial registrada con precios reales.")
    return portafolio


# ============================================================
# PASO 3 — REGISTRAR NUEVOS APORTES
# ============================================================


def registrar_nuevos_aportes(archivo, portafolio):
    """Pregunta si hubo compras adicionales y las registra."""
    composicion = portafolio.get("composicion", {})
    todos_activos = list(composicion.keys())

    print("\n💰 ¿HICISTE COMPRAS ADICIONALES DESDE LA ÚLTIMA REVISIÓN?")
    tiene_nuevos = input("   Escribe SI o NO: ").upper()
    if tiene_nuevos != "SI":
        return portafolio

    continuar = True
    while continuar:
        print(f"\n   Activos del portafolio: {todos_activos}")
        activo = input("   ¿Qué activo compraste? ").upper().strip()

        if activo not in todos_activos:
            print(f"   ⚠️ {activo} no está en este portafolio.")
            continuar = input("   ¿Registrar otro? (SI/NO): ").upper() == "SI"
            continue

        fecha_str = input("   ¿En qué fecha compraste? (YYYY-MM-DD): ")
        monto_str = input("   ¿Cuánto invertiste en COP? ")
        usa_precio = input("   ¿Sabes el precio exacto? (SI/NO): ").upper()

        try:
            monto_cop = float(monto_str.replace(",", "").replace(".", ""))
            trm_dia = leer_trm_historica(fecha_str)

            if usa_precio == "SI":
                precio_str = input("   ¿A qué precio USD compraste? ")
                precio_usd = float(precio_str.replace(",", "."))
            else:
                precio_usd = precio_actual_usd(activo)
                print(f"   Usando precio actual: ${precio_usd:,.2f} USD")

            fracciones = monto_cop / (precio_usd * trm_dia)

            aporte = {
                "fecha": fecha_str,
                "activo": activo,
                "monto_cop": monto_cop,
                "precio_usd": precio_usd,
                "trm_dia": trm_dia,
                "fracciones": round(fracciones, 6),
                "tipo": "adicional",
            }
            guardar_aporte(archivo, aporte)
            print(
                f"   ✅ {activo}: {fracciones:.4f} fracciones @ "
                f"${precio_usd:,.2f} USD"
            )

        except Exception as e:
            print(f"   ❌ Error: {e}")

        continuar = input("\n   ¿Registrar otra compra? (SI/NO): ").upper() == "SI"

    portafolio = leer_portafolio(archivo)
    return portafolio


# ============================================================
# PASO 4 — CALCULAR ESTADO ACTUAL
# ============================================================


def calcular_estado_actual(portafolio):
    """Calcula el rendimiento real de cada posición."""
    print("\n📊 CALCULANDO ESTADO ACTUAL...")
    print("─" * 55)

    inf_anual = leer_inflacion_col()
    trm_actual = leer_trm_actual()
    print(f"   TRM actual: ${trm_actual:,.0f} | Inflación: {inf_anual:.1f}%\n")

    # Agrupar fracciones por activo
    fracciones_por_activo = {}
    invertido_por_activo = {}

    for aporte in portafolio.get("aportes", []):
        activo = aporte["activo"]
        if activo not in fracciones_por_activo:
            fracciones_por_activo[activo] = 0
            invertido_por_activo[activo] = []
        fracciones_por_activo[activo] += aporte["fracciones"]
        invertido_por_activo[activo].append(
            {
                "monto_cop": aporte["monto_cop"],
                "fecha": aporte["fecha"],
                "precio_usd": aporte["precio_usd"],
            }
        )

    # Precios actuales
    precios = precios_mercado(list(fracciones_por_activo.keys()))

    resultados = {}
    resumen = {"total_invertido_real": 0, "total_valor": 0}

    for activo, fracciones in fracciones_por_activo.items():
        precio_hoy = precios.get(activo)
        if precio_hoy is None:
            continue

        valor_nominal = fracciones * precio_hoy * trm_actual

        # Total invertido deflactado desde cada fecha
        total_inv_real = sum(
            deflactar(a["monto_cop"], a["fecha"], inf_anual)
            for a in invertido_por_activo[activo]
        )

        # Precio promedio ponderado
        total_monto = sum(a["monto_cop"] for a in invertido_por_activo[activo])
        precio_prom = sum(
            a["precio_usd"] * (a["monto_cop"] / total_monto)
            for a in invertido_por_activo[activo]
        )

        ganancia = valor_nominal - total_inv_real
        rentabilidad = (ganancia / total_inv_real * 100) if total_inv_real > 0 else 0

        emoji = "📈" if ganancia > 0 else "📉"
        print(f"   {emoji} {activo}")
        print(f"      Fracciones       : {fracciones:.4f}")
        print(f"      Precio entrada   : ${precio_prom:.2f} USD (prom.)")
        print(f"      Precio hoy       : ${precio_hoy:,.2f} USD")
        print(f"      Invertido (real) : ${total_inv_real:>12,.0f} COP")
        print(f"      Valor hoy        : ${valor_nominal:>12,.0f} COP")
        print(f"      Ganancia real    : ${ganancia:>+12,.0f} COP")
        print(f"      Rentabilidad     : {rentabilidad:+.1f}%\n")

        resultados[activo] = {
            "fracciones": round(fracciones, 6),
            "precio_entrada_prom": round(precio_prom, 2),
            "precio_actual": round(precio_hoy, 2),
            "total_invertido_real": round(total_inv_real, 0),
            "valor_nominal": round(valor_nominal, 0),
            "ganancia_real": round(ganancia, 0),
            "rentabilidad_pct": round(rentabilidad, 2),
        }

        resumen["total_invertido_real"] += total_inv_real
        resumen["total_valor"] += valor_nominal

    ganancia_global = resumen["total_valor"] - resumen["total_invertido_real"]
    rent_global = (
        (ganancia_global / resumen["total_invertido_real"] * 100)
        if resumen["total_invertido_real"] > 0
        else 0
    )

    print(f"{'='*55}")
    print(f"  RESUMEN — {portafolio['nombre']} ({portafolio['propietario']})")
    print(f"{'='*55}")
    print(f"  Total invertido (real) : ${resumen['total_invertido_real']:>12,.0f} COP")
    print(f"  Valor total hoy        : ${resumen['total_valor']:>12,.0f} COP")
    print(f"  Ganancia real total    : ${ganancia_global:>+12,.0f} COP")
    print(f"  Rentabilidad total     : {rent_global:+.1f}%")

    resultados["_resumen"] = {
        "total_invertido_real": round(resumen["total_invertido_real"], 0),
        "total_valor": round(resumen["total_valor"], 0),
        "ganancia_global": round(ganancia_global, 0),
        "rentabilidad_global": round(rent_global, 2),
    }

    return resultados


# ============================================================
# PASO 5 — DETECTAR DERIVA
# ============================================================


def detectar_deriva(portafolio, resultados):
    """Detecta si los pesos actuales se desviaron del objetivo."""
    print(f"\n⚖️  ANÁLISIS DE DERIVA DE PESOS:")

    composicion = portafolio.get("composicion", {})
    alertas_rebalanceo = []
    datos = {k: v for k, v in resultados.items() if k != "_resumen"}
    total_hoy = sum(v["valor_nominal"] for v in datos.values())

    if total_hoy == 0:
        return []

    print(
        f"\n   {'Activo':<12} {'Objetivo':>10} {'Actual':>10} "
        f"{'Deriva':>10}  Sugerencia"
    )
    print(f"   {'─'*65}")

    for activo, datos_activo in datos.items():
        peso_obj = composicion.get(activo, 0) * 100
        peso_actual = datos_activo["valor_nominal"] / total_hoy * 100
        deriva = peso_actual - peso_obj

        if abs(deriva) > 5:
            sugerencia = (
                "⚠️ Subió mucho — en próximo DCA no compres más"
                if deriva > 0
                else "⚠️ Bajó — en próximo DCA pon más aquí"
            )
            alertas_rebalanceo.append(
                {
                    "activo": activo,
                    "peso_objetivo": round(peso_obj, 1),
                    "peso_actual": round(peso_actual, 1),
                    "deriva": round(deriva, 1),
                    "sugerencia": sugerencia,
                }
            )
        else:
            sugerencia = "✅ En rango"

        print(
            f"   {activo:<12} "
            f"{peso_obj:>9.1f}% "
            f"{peso_actual:>9.1f}% "
            f"{'+' if deriva > 0 else ''}{deriva:>7.1f}%  "
            f"{sugerencia}"
        )

    return alertas_rebalanceo


# ============================================================
# PASO 6 — ENVIAR REPORTE TELEGRAM
# ============================================================


def enviar_reporte_telegram(portafolio, resultados, alertas):
    resumen = resultados.get("_resumen", {})
    if not resumen:
        return

    rent = resumen["rentabilidad_global"]
    emoji = "📈" if rent > 0 else "📉"

    mensaje = f"{emoji} <b>SEGUIMIENTO — {portafolio['nombre']}</b>\n"
    mensaje += f"👤 {portafolio['propietario']} | {portafolio['perfil'].upper()}\n"
    mensaje += f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    mensaje += f"💰 Invertido : ${resumen['total_invertido_real']:,.0f} COP\n"
    mensaje += f"💰 Valor hoy : ${resumen['total_valor']:,.0f} COP\n"
    mensaje += f"📊 Ganancia  : ${resumen['ganancia_global']:+,.0f} COP\n"
    mensaje += f"🏆 Rentabilidad: {'+' if rent > 0 else ''}{rent:.1f}%\n\n"

    datos = {k: v for k, v in resultados.items() if k != "_resumen"}
    for activo, d in datos.items():
        e = "📈" if d["ganancia_real"] > 0 else "📉"
        mensaje += (
            f"   {e} {activo}: "
            f"{'+' if d['rentabilidad_pct'] > 0 else ''}"
            f"{d['rentabilidad_pct']:.1f}% | "
            f"{d['fracciones']:.4f} acc.\n"
        )

    if alertas:
        mensaje += f"\n⚠️ <b>REBALANCEO SUGERIDO:</b>\n"
        for a in alertas:
            mensaje += f"   {a['activo']}: {a['sugerencia']}\n"
    else:
        mensaje += f"\n✅ Pesos en rango — sin rebalanceo necesario."

    mensaje += f"\n💡 Valores en pesos de hoy"
    enviar_telegram(mensaje)


# ============================================================
# EJECUCIÓN PRINCIPAL
# ============================================================

if __name__ == "__main__":
    import sys

    modo_auto = "--auto" in sys.argv

    print("=" * 55)
    print("📊 SEGUIMIENTO DE PORTAFOLIO")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🤖 Modo: {'AUTOMÁTICO' if modo_auto else 'MANUAL'}")
    print("=" * 55)

    if modo_auto:
        # En modo auto usa el portafolio activo directamente
        from gestor_portafolio import leer_portafolio_activo

        portafolio_data = leer_portafolio_activo()
        if not portafolio_data:
            print("❌ No hay portafolio activo.")
            exit()
        # Encontrar el archivo correspondiente
        portafolios = listar_portafolios()
        p_activo = next((p for p in portafolios if p["activo"]), None)
        if not p_activo:
            exit()
        archivo = p_activo["archivo"]
        portafolio = portafolio_data
    else:
        # En modo manual selecciona cuál revisar
        archivo, portafolio = seleccionar_portafolio()
        if not portafolio:
            exit()

    # Inicializar aportes si es primera vez
    portafolio = inicializar_aportes(archivo, portafolio)

    # Nuevos aportes solo en modo manual
    if not modo_auto:
        portafolio = registrar_nuevos_aportes(archivo, portafolio)

    # Calcular estado
    resultados = calcular_estado_actual(portafolio)

    # Deriva
    alertas = detectar_deriva(portafolio, resultados)
    if alertas:
        print(f"\n⚠️  {len(alertas)} activo(s) con deriva significativa.")
    else:
        print(f"\n✅ Pesos dentro de rango.")

    # Telegram
    enviar_reporte_telegram(portafolio, resultados, alertas)
    print(f"\n📱 Reporte enviado a Telegram.")
    print("=" * 55)
