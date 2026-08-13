"""
scheduler.py — jobs periódicos que NO dependen de que alguien abra la app.

Hoy tiene un único job: registrar un snapshot diario de cada portafolio en
su historial (ver gestor_portafolio.guardar_registro_diario), para que la
pestaña Histórico no tenga huecos aunque nadie entre a la app ese día.

Patrón calcado del de monitor.py (thread daemon + loop `while True` con
sleep), pero sin ventanas horarias: cada 5 minutos revisa, portafolio por
portafolio, si ya existe un snapshot de HOY en su historial. Si Railway
reinicia el proceso justo a medianoche, el próximo tick (máximo 5 min
después) lo recupera solo — así se garantiza un punto por día sin huecos,
sin depender de que el reinicio caiga fuera de una ventana fija.

Antes de tocar precios en vivo (calcular_tiempo_real hace llamadas reales
a yfinance), primero se revisa en disco si el snapshot de hoy ya existe —
así el tick de cada 5 minutos es barato el resto del día, solo hace el
trabajo pesado una vez por portafolio por día.
"""
import time
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

TZ_COL = ZoneInfo("America/Bogota")
INTERVALO_TICK_SEG = 300  # 5 minutos

_scheduler_activo = False


def hora_colombia():
    return datetime.now(TZ_COL)


def _snapshot_portafolio(archivo):
    """Registra el snapshot de HOY para un portafolio, si todavía no existe.
    Reutiliza calcular_tiempo_real/cargar_macro (dashboard.py) — mismos
    cálculos que ya usa /api/dashboard, para que el número guardado sea
    idéntico al que vería el usuario si abriera la app en este momento."""
    from gestor_portafolio import leer_portafolio, guardar_registro_diario

    portafolio = leer_portafolio(archivo)
    if not portafolio:
        return

    hoy = hora_colombia().strftime("%Y-%m-%d")
    ya_registrado = hoy in [r.get("fecha") for r in portafolio.get("historial", [])]
    if ya_registrado:
        return  # nada que hacer -- evita llamadas a precios en vivo de más

    from dashboard import calcular_tiempo_real, cargar_macro

    tiempo_real = calcular_tiempo_real(portafolio)
    if not tiempo_real:
        return  # portafolio sin inversiones vivas todavía, nada que registrar

    macro = cargar_macro()
    trm = None
    if macro and "trm" in macro:
        try:
            trm = float(macro["trm"])
        except (TypeError, ValueError):
            trm = None

    registro = {
        "fecha": hoy,
        "resumen": {
            "total_valor": tiempo_real["total_valor"],
            "total_invertido": tiempo_real["total_invertido"],
            "ganancia_total": tiempo_real["ganancia_total"],
            "rentabilidad_total": tiempo_real["rentabilidad_total"],
        },
        "macro": {"trm": trm} if trm is not None else None,
    }
    guardar_registro_diario(archivo, registro)


def _snapshot_todos_los_portafolios():
    from gestor_portafolio import listar_portafolios

    for p in listar_portafolios():
        archivo = p.get("archivo")
        if not archivo:
            continue
        try:
            _snapshot_portafolio(archivo)
        except Exception as e:
            print(f"⚠️ scheduler: no se pudo registrar snapshot de {archivo}: {e}")


def _loop_scheduler():
    while True:
        try:
            _snapshot_todos_los_portafolios()
        except Exception as e:
            print(f"⚠️ scheduler: error en el loop diario: {e}")
        time.sleep(INTERVALO_TICK_SEG)


def iniciar_scheduler():
    global _scheduler_activo
    if _scheduler_activo:
        return
    _scheduler_activo = True
    threading.Thread(target=_loop_scheduler, daemon=True).start()
    print("🗓️ Scheduler iniciado")
