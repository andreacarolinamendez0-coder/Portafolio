"""
Corrige el desastre de los dos scripts anteriores: reconstruye el historial
sintético completo (2025-12-31 -> el dia antes del ultimo punto real) en UN
SOLO PASO, con una curva suave que converge hacia el unico punto que sabemos
que es real y verificado (2026-08-16, coincide con lo que Dashboard mostro).

No usa rampas sobre datos ya escritos -- calcula todo de nuevo, de una vez,
para que no haya ninguna costura entre tramos generados por separado.

Corre esto desde la carpeta Portafolio, con el venv activado:
    python reconstruir_historial_limpio.py

Ojo: opera sobre datos/portafolios/demo.json directamente (no el template),
porque ahi es donde vive el punto real del 16 de agosto que queremos conservar.
Al final, copia el resultado tambien al template.
"""
import json
import random
from datetime import date, timedelta

RUTA_DEMO = "datos/portafolios/demo.json"
RUTA_TEMPLATE = "datos/portafolios/demo_template.json"

# El unico punto que confiamos: coincide con lo que Andrea vio en vivo en Dashboard.
FECHA_ANCLA_REAL = "2026-08-16"

with open(RUTA_DEMO, encoding="utf-8") as f:
    d = json.load(f)

historial_actual = d.get("historial", [])
punto_real = next((h for h in historial_actual if h["fecha"] == FECHA_ANCLA_REAL), None)
if punto_real is None:
    raise SystemExit(
        f"No encontre la fecha ancla {FECHA_ANCLA_REAL} en el historial actual. "
        f"Revisa a mano cual es tu ultimo punto confiable y ajusta FECHA_ANCLA_REAL."
    )

print(f"Punto ancla confirmado ({FECHA_ANCLA_REAL}): {punto_real['resumen']}")

fecha_inicio = date.fromisoformat(d["fecha_inicio"])
fecha_ancla = date.fromisoformat(FECHA_ANCLA_REAL)

# --- invertido real en cada fecha: aportes acumulados - proceeds de ventas ---
def invertido_a_fecha(portafolio, fecha_limite_str):
    aportado = sum(a["monto_usd"] for a in portafolio.get("aportes", [])
                   if a["fecha"] <= fecha_limite_str)
    vendido = sum(v["proceeds_usd"] for v in portafolio.get("ventas", [])
                  if v["fecha"] <= fecha_limite_str)
    return round(aportado - vendido, 2)

# --- TRM interpolada entre anclas reales ya confirmadas en sesiones anteriores ---
anclas_trm = [
    (date(2025,12,31), 3757.08), (date(2026,5,15), 3700), (date(2026,6,20), 3600),
    (date(2026,7,1), 3550), (date(2026,7,15), 3252.11), (date(2026,8,5), 3204.51),
    (date(2026,8,16), 3238.19),
]
def trm_interp(f):
    for i in range(len(anclas_trm)-1):
        d1,v1 = anclas_trm[i]; d2,v2 = anclas_trm[i+1]
        if d1 <= f <= d2:
            frac = (f-d1).days / max((d2-d1).days,1)
            return round(v1+(v2-v1)*frac, 2)
    return anclas_trm[-1][1] if f > anclas_trm[-1][0] else anclas_trm[0][1]

# --- rentabilidad objetivo del punto ancla, para que la rampa converja ahi ---
rent_objetivo = punto_real["resumen"]["rentabilidad_total"]

random.seed(11)
nuevo_historial = []
f = fecha_inicio
total_dias = (fecha_ancla - fecha_inicio).days

while f < fecha_ancla:
    fecha_str = f.isoformat()
    inv = invertido_a_fecha(d, fecha_str)
    if inv <= 0:
        f += timedelta(days=7)
        continue

    t = (f - fecha_inicio).days / max(total_dias, 1)  # 0 -> 1, progreso hacia el ancla
    rent_base = rent_objetivo * t                        # rampa lineal SUAVE hacia el objetivo
    ruido = random.uniform(-3.0, 3.0) * (1 - t * 0.5)    # ruido que se reduce cerca del ancla
    rent = round(rent_base + ruido, 2)

    valor = round(inv * (1 + rent / 100), 2)
    nuevo_historial.append({
        "fecha": fecha_str,
        "resumen": {
            "total_valor": valor, "total_invertido": inv,
            "ganancia_total": round(valor - inv, 2),
            "rentabilidad_total": round((valor - inv) / inv * 100, 2),
        },
        "macro": {"trm": trm_interp(f)},
    })
    f += timedelta(days=7)

nuevo_historial.append(punto_real)  # el ancla real, intacta

d["historial"] = nuevo_historial

with open(RUTA_DEMO, "w", encoding="utf-8") as f_out:
    json.dump(d, f_out, ensure_ascii=False, indent=2)
with open(RUTA_TEMPLATE, "w", encoding="utf-8") as f_out:
    json.dump(d, f_out, ensure_ascii=False, indent=2)

print(f"\nHistorial reconstruido de una sola pasada: {len(nuevo_historial)} puntos totales.")
print(f"Primer punto: {nuevo_historial[0]['resumen']}")
print(f"Ultimo punto (ancla real, sin tocar): {nuevo_historial[-1]['resumen']}")
print("\nGuardado en demo.json Y demo_template.json.")
print("IMPORTANTE: borra 'analisis_historico' del JSON o pide que se regenere -- "
      "el texto que tiene ahora mismo describe el historial roto anterior (+488%), "
      "va a sonar incoherente contra los numeros nuevos hasta que se regenere.")