import pandas as pd
import numpy as np
import json
import os
import requests
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings("ignore")
import yfinance as yf

from gestor_portafolio import (
    leer_portafolio_activo,
    listar_portafolios,
    guardar_registro_diario,
)

TELEGRAM_TOKEN = "8332465511:AAH-PlentkDhWWNenLGOdvJCLC6OXNEnrA8"
TELEGRAM_CHAT_ID = "6999614895"


def enviar_telegram(mensaje):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except:
        pass


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


def capturar_estado_hoy():
    hoy = datetime.now().strftime("%Y-%m-%d")
    print(f"📸 Capturando estado — {hoy}")

    # ── MACRO ──
    try:
        trm = pd.read_parquet("datos/macro/trm.parquet")
        inf_col = pd.read_parquet("datos/macro/inflacion_col.parquet")
        inf_usa = pd.read_parquet("datos/macro/inflacion_usa.parquet")
        risk_free = pd.read_parquet("datos/macro/risk_free.parquet")
        banrep = pd.read_parquet("datos/macro/tasa_banrep.parquet")

        trm_actual = float(trm["TRM"].iloc[-1])
        trm_hace_mes = float(trm["TRM"].iloc[-22]) if len(trm) > 22 else trm_actual

        macro = {
            "trm": round(trm_actual, 2),
            "trm_cambio": round(((trm_actual - trm_hace_mes) / trm_hace_mes) * 100, 2),
            "inf_col": round(float(inf_col["Inflacion_COL"].iloc[-1]), 2),
            "inf_usa": round(float(inf_usa["Inflacion_USA"].iloc[-1]), 2),
            "risk_free": round(float(risk_free["Risk_Free"].iloc[-1]), 2),
            "banrep": round(float(banrep["Tasa_Banrep"].iloc[-1]), 2),
            "cdt": round(float(banrep["Tasa_Banrep"].iloc[-1]) - 0.75, 2),
        }
        print(f"   ✅ Macro — TRM: ${macro['trm']:,.0f}")
    except Exception as e:
        print(f"   ❌ Error macro: {e}")
        macro = {}

    # ── PORTAFOLIOS ── registra todos, no solo el activo
    portafolios = listar_portafolios()
    if not portafolios:
        print("   ⚠️ No hay portafolios creados.")
        return

    for p_info in portafolios:
        archivo = p_info["archivo"]
        ruta = f"datos/portafolios/{archivo}"

        try:
            with open(ruta, "r") as f:
                portafolio = json.load(f)
        except:
            continue

        aportes = portafolio.get("aportes", [])
        if not aportes:
            print(f"   ⚠️ {portafolio['nombre']} — sin aportes registrados, omitido.")
            continue

        inf_anual = portafolio.get("inflacion_col", macro.get("inf_col", 4.90))
        trm_actual = macro.get("trm", 4000)

        # Agrupar fracciones
        fracciones_por_activo = {}
        invertido_por_activo = {}

        for aporte in aportes:
            activo = aporte["activo"]
            if activo not in fracciones_por_activo:
                fracciones_por_activo[activo] = 0
                invertido_por_activo[activo] = []
            fracciones_por_activo[activo] += aporte["fracciones"]
            invertido_por_activo[activo].append(aporte)

        posiciones = []
        total_inv = 0
        total_valor = 0

        for activo, fracciones in fracciones_por_activo.items():
            precio_hoy = precio_actual_usd(activo)
            if precio_hoy is None:
                continue

            valor_hoy = fracciones * precio_hoy * trm_actual
            inv_real = sum(
                a["monto_cop"]
                / (1 + inf_anual / 100)
                ** max(
                    (datetime.now() - datetime.strptime(a["fecha"], "%Y-%m-%d")).days
                    / 365.25,
                    0,
                )
                for a in invertido_por_activo[activo]
            )
            ganancia = valor_hoy - inv_real
            rentabilidad = (ganancia / inv_real * 100) if inv_real > 0 else 0

            posiciones.append(
                {
                    "activo": activo,
                    "fracciones": round(fracciones, 4),
                    "precio_usd": round(precio_hoy, 2),
                    "valor_cop": round(valor_hoy, 0),
                    "invertido": round(inv_real, 0),
                    "ganancia": round(ganancia, 0),
                    "rentabilidad": round(rentabilidad, 2),
                }
            )

            total_inv += inv_real
            total_valor += valor_hoy

            emoji = "📈" if ganancia > 0 else "📉"
            print(
                f"   {emoji} {portafolio['nombre']} | {activo}: "
                f"${precio_hoy:,.2f} | {rentabilidad:+.1f}%"
            )

        ganancia_total = total_valor - total_inv
        rent_total = (ganancia_total / total_inv * 100) if total_inv > 0 else 0

        registro = {
            "fecha": hoy,
            "hora": datetime.now().strftime("%H:%M"),
            "macro": macro,
            "posiciones": posiciones,
            "resumen": {
                "total_invertido": round(total_inv, 0),
                "total_valor": round(total_valor, 0),
                "ganancia_total": round(ganancia_total, 0),
                "rentabilidad_total": round(rent_total, 2),
            },
        }

        guardado = guardar_registro_diario(archivo, registro)

        if guardado:
            print(f"\n   ✅ {portafolio['nombre']} — registro guardado")
            print(
                f"      Invertido: ${total_inv:,.0f} | "
                f"Valor: ${total_valor:,.0f} | "
                f"Ganancia: ${ganancia_total:+,.0f} ({rent_total:+.1f}%)"
            )

            # Telegram por portafolio
            emoji = "📈" if ganancia_total > 0 else "📉"
            mensaje = (
                f"{emoji} <b>REGISTRO DIARIO</b>\n"
                f"📋 {portafolio['nombre']} — {portafolio['propietario']}\n"
                f"📅 {hoy}\n\n"
                f"💰 Invertido : ${total_inv:,.0f} COP\n"
                f"💰 Valor hoy : ${total_valor:,.0f} COP\n"
                f"📊 Ganancia  : ${ganancia_total:+,.0f} COP\n"
                f"🏆 Rentabilidad: {rent_total:+.1f}%\n\n"
                f"💱 TRM: ${macro.get('trm', 0):,.0f}"
            )
            enviar_telegram(mensaje)
        else:
            print(f"   ✅ {portafolio['nombre']} — ya registrado hoy.")


if __name__ == "__main__":
    print("=" * 50)
    print("📸 REGISTRADOR DIARIO")
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    capturar_estado_hoy()
    print("\n✅ REGISTRO COMPLETO")
