"""
Extiende demo_template.json con:
  1. Ronda de apertura movida a 2025-12-31 (TRM real 3757.08) -> ~7.5 meses de historial
  2. Dos ventas reales (NVDA 15-jul, GOOGL 5-ago) con TRM real, costo base calculado
     sobre el pool REAL de aportes que ya existan en tu archivo (no inventado).
  3. rebalanceo_metricas + proyeccion_al_aplicar.metricas, para que Seguimiento
     muestre el disparo de recomposición por desviación de parámetros.

Corre esto desde la carpeta Portafolio, con el venv activado:
    python extender_demo.py

Lee y sobreescribe: datos/portafolios/demo_template.json
Al final, corre tú misma:
    Copy-Item datos\\portafolios\\demo_template.json datos\\portafolios\\demo.json -Force
para que el cambio se vea sin esperar al próximo login.
"""
import json
from datetime import date, timedelta

RUTA = "datos/portafolios/demo_template.json"

with open(RUTA, encoding="utf-8") as f:
    d = json.load(f)

# ============================================================
# 1. Ronda de apertura extendida (TRM real, precios estimados)
# ============================================================
APERTURA_FECHA = "2025-12-31"
APERTURA_TRM = 3757.08  # Banco de la República, cierre 31 dic 2025 (confirmado por búsqueda)

# Precios estimados para esa fecha (NO buscados -- son cotización de acciones, no TRM;
# Andrea solo pidió TRM real para movimientos, así que esto queda marcado como estimación).
precios_apertura = {
    "GOOGL": 355.00, "MSFT": 380.00, "NVDA": 195.00,
    "VTI": 335.00, "SCHD": 25.80, "BTC-USD": 58000.00,
}
montos_apertura = {"GOOGL": 55, "MSFT": 55, "NVDA": 50, "VTI": 55, "SCHD": 40, "BTC-USD": 25}

nuevos_aportes = []
for tk, precio in precios_apertura.items():
    monto = montos_apertura[tk]
    frac = round(monto / precio, 6)
    nuevos_aportes.append({
        "fecha": APERTURA_FECHA, "activo": tk,
        "monto_usd": monto, "monto_cop": round(monto * APERTURA_TRM),
        "precio_usd": precio, "trm_dia": APERTURA_TRM,
        "fracciones": frac, "tipo": "demo", "id": f"{tk.lower().replace('-','')}20251231",
    })

d["aportes"] = nuevos_aportes + d.get("aportes", [])
d["fecha_inicio"] = APERTURA_FECHA

# Depósito correspondiente a la apertura
d.setdefault("depositos", [])
total_apertura_usd = sum(montos_apertura.values())
d["depositos"].insert(0, {
    "id": "deposito_apertura_extendida", "fecha": APERTURA_FECHA,
    "monto_cop": round(total_apertura_usd * APERTURA_TRM), "trm_real": APERTURA_TRM,
    "monto_usd": total_apertura_usd, "tipo": "apertura",
})

print(f"Aportes de apertura agregados: {len(nuevos_aportes)}, total ${total_apertura_usd} USD")

# ============================================================
# 2. Ventas -- costo base calculado sobre el pool REAL de tu archivo
# ============================================================
def pool_viva(aportes, ventas_previas, activo):
    frac = sum(a["fracciones"] for a in aportes if a["activo"] == activo)
    cop = sum(a["monto_cop"] for a in aportes if a["activo"] == activo)
    comision_cop = sum(a.get("comision", 0) * a.get("trm_dia", 0) for a in aportes if a["activo"] == activo)
    for v in ventas_previas:
        if v["activo"] == activo:
            frac -= v["fracciones"]
    return {"frac": frac, "cop": cop, "comision_cop": comision_cop}

d.setdefault("ventas", [])
ventas_nuevas = []

def registrar_venta(activo, fecha, fracciones, precio_venta, trm_dia, id_):
    pool = pool_viva(d["aportes"], d["ventas"] + ventas_nuevas, activo)
    if pool["frac"] < fracciones:
        print(f"AVISO: pool de {activo} tiene {pool['frac']:.6f} fracciones, "
              f"menor a las {fracciones} que se intentan vender -- se ajusta al pool disponible.")
        fracciones = round(pool["frac"] * 0.5, 6)  # vende la mitad de lo disponible, por seguridad
    monto_usd = round(fracciones * precio_venta, 2)
    comision = round(monto_usd * 0.01, 2)
    proceeds_usd = round(monto_usd - comision, 2)
    costo_base_cop = round(((pool["cop"] + pool["comision_cop"]) / pool["frac"]) * fracciones, 0)
    ganancia_realizada_cop = round(proceeds_usd * trm_dia - costo_base_cop, 0)
    venta = {
        "id": id_, "fecha": fecha, "activo": activo,
        "fracciones": round(fracciones, 8), "precio_venta_usd": precio_venta,
        "comision": comision, "proceeds_usd": proceeds_usd, "trm_dia": trm_dia,
        "costo_base_cop": costo_base_cop, "ganancia_realizada_cop": ganancia_realizada_cop,
        "tipo": "venta",
    }
    ventas_nuevas.append(venta)
    print(f"Venta {activo} {fecha}: {fracciones:.6f} fracc. a ${precio_venta} "
          f"-> ganancia {ganancia_realizada_cop:,.0f} COP")

# Venta 1: NVDA, toma de utilidad -- TRM real 15 jul 2026
registrar_venta("NVDA", "2026-07-15", fracciones=0.08, precio_venta=232.50,
                 trm_dia=3252.11, id_="venta_nvda_20260715")

# Venta 2: GOOGL -- TRM real 5 ago 2026
registrar_venta("GOOGL", "2026-08-05", fracciones=0.04, precio_venta=405.00,
                 trm_dia=3204.51, id_="venta_googl_20260805")

d["ventas"] = d["ventas"] + ventas_nuevas

# ============================================================
# 3. Historial extendido (semanal, sintético, TRM interpolada entre anclas reales)
# ============================================================
anclas_trm = [
    (date(2025,12,31), 3757.08), (date(2026,5,15), 3700), (date(2026,6,20), 3600),
    (date(2026,7,1), 3550), (date(2026,7,15), 3252.11), (date(2026,8,5), 3204.51),
    (date(2026,8,14), 3157.0),
]
def trm_interp(f):
    for i in range(len(anclas_trm)-1):
        d1,v1 = anclas_trm[i]; d2,v2 = anclas_trm[i+1]
        if d1 <= f <= d2:
            frac = (f-d1).days / max((d2-d1).days,1)
            return round(v1+(v2-v1)*frac, 2)
    return anclas_trm[-1][1]

historial_viejo = d.get("historial", [])
primera_fecha_vieja = date.fromisoformat(historial_viejo[0]["fecha"]) if historial_viejo else date(2026,5,15)

nuevo_historial = []
f = date.fromisoformat(APERTURA_FECHA)
while f < primera_fecha_vieja:
    dias = (f - date.fromisoformat(APERTURA_FECHA)).days
    invertido = sum(a["monto_usd"] for a in d["aportes"] if date.fromisoformat(a["fecha"]) <= f)
    tendencia = 1 + 0.0006 * dias
    valor = round(invertido * tendencia, 2) if invertido > 0 else 0.0
    nuevo_historial.append({
        "fecha": f.isoformat(),
        "resumen": {
            "total_valor": valor, "total_invertido": round(invertido, 2),
            "ganancia_total": round(valor - invertido, 2),
            "rentabilidad_total": round((valor-invertido)/invertido*100, 2) if invertido > 0 else 0,
        },
        "macro": {"trm": trm_interp(f)},
    })
    f += timedelta(days=7)

d["historial"] = nuevo_historial + historial_viejo
print(f"Historial extendido: +{len(nuevo_historial)} semanas nuevas antes de las {len(historial_viejo)} existentes")

# ============================================================
# 4. Disparo de recomposición por desviación de métricas
# ============================================================
d["rebalanceo_metricas"] = {
    "dias_fuera_de_rango": 5,   # >= DIAS_HABILES_HYSTERESIS (4) -> dispara
    "motivo": "volatilidad",   # el código solo acepta "volatilidad" o "drawdown"
    "fecha": "2026-08-14",
}

# Proyección congelada -- la que compara evaluar_disparo_rebalanceo / _dia_fuera_de_rango_metricas.
# Valores plausibles, NO calculados por el motor real -- son el "blanco" contra el que
# se supone que la realidad ya se desvió lo suficiente para disparar.
d["proyeccion_al_aplicar"] = {
    "metricas": {
        "retorno_anual": 0.085,
        "volatilidad": 0.162,
        "max_drawdown": -0.221,
        "sharpe": 0.34,
    }
}
print("rebalanceo_metricas y proyeccion_al_aplicar.metricas agregados -- Seguimiento debería mostrar el disparo.")

# ============================================================
# Guardar
# ============================================================
with open(RUTA, "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print(f"\nGuardado en {RUTA}")
print("Ahora corre: Copy-Item datos\\portafolios\\demo_template.json datos\\portafolios\\demo.json -Force")