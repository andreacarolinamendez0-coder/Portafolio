import json
import os
import hashlib
import logging
import threading
import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_PORTAFOLIOS = os.path.join(BASE_DIR, "datos", "portafolios")
os.makedirs(CARPETA_PORTAFOLIOS, exist_ok=True)

# Lock en proceso para serializar el read-modify-write de los archivos de
# portafolio: evita que dos requests casi simultáneos (doble clic, dos pestañas)
# lean el mismo JSON, ambos hagan append, y se pierda un aporte (gana el último
# en escribir). Combinado con la escritura atómica de _escribir, deja el flujo
# consistente en un solo proceso.
# ponytail: lock global en-proceso. Cubre los hilos de un mismo worker (Flask
# threaded + el hilo del monitor). NO cubre varios procesos/workers de gunicorn
# — para eso haría falta un file lock (fcntl/msvcrt) o la migración a Postgres,
# que da transacciones reales.
_LOCK = threading.Lock()

# Lock DEDICADO para los archivos de estado del monitor (monitor_<archivo>.json).
# Separado de _LOCK a propósito: vigilar_precios() retiene este lock durante
# todo un ciclo de vigilancia (que incluye llamadas HTTP a Telegram, potencialmente
# lentas), y no debe bloquear las operaciones financieras de portafolio (aportes,
# depósitos, ventas) que usan _LOCK. RLock porque se toma tanto alrededor de
# vigilar_precios()/registrar_decision() completos como, potencialmente, dentro
# de leer_estado/guardar_estado si se llaman directo desde el mismo hilo.
_LOCK_MONITOR = threading.RLock()

# ============================================================
# UTILIDADES
# ============================================================


def hash_password(password):
    # Legacy unsalted SHA-256 — only used for reading old hashes during migration
    return hashlib.sha256(password.encode()).hexdigest()


def hash_password_secure(password):
    return generate_password_hash(password)


def _is_legacy_hash(h):
    """Returns True if the hash is old-style (plain SHA-256 hex, 64 chars)."""
    return len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def verify_password(stored_hash, password):
    """Verify password against either legacy SHA-256 or modern werkzeug hash."""
    if _is_legacy_hash(stored_hash):
        return stored_hash == hash_password(password)
    return check_password_hash(stored_hash, password)

def huella_password_hash(password_hash):
    """Huella corta y estable del hash de una contraseña. Usada para invalidar
    tokens de reset: al cambiar la clave cambia el hash, y con él la huella.
    """
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def get_usuario_por_email(email):
    """Busca un usuario por email. Devuelve (username, usuario) o (None, None)."""
    for username, u in _leer_usuarios().items():
        if u.get("email") == email:
            return username, u
    return None, None

def _leer(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def _escribir(ruta, data):
    # Escritura atómica: se escribe a un .tmp y se renombra con os.replace
    # (atómico en el mismo filesystem). Un crash a mitad deja el .tmp incompleto
    # pero el archivo original intacto — nunca queda un JSON a medias/corrupto.
    tmp = f"{ruta}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)


def _es_portafolio_real(fn):
    return fn.endswith(".json") and not fn.startswith(("monitor_", "rangos_"))


def _slug(nombre):
    s = nombre.lower().replace(" ", "_")
    for a, b in [
        ("á", "a"),
        ("é", "e"),
        ("í", "i"),
        ("ó", "o"),
        ("ú", "u"),
        ("ñ", "n"),
    ]:
        s = s.replace(a, b)
    return s


# ============================================================
# LISTAR PORTAFOLIOS
# ============================================================


def listar_portafolios():
    archivos = [f for f in os.listdir(CARPETA_PORTAFOLIOS) if _es_portafolio_real(f)]
    portafolios = []
    for archivo in archivos:
        try:
            data = _leer(f"{CARPETA_PORTAFOLIOS}/{archivo}")

            # Leer último análisis del monitor si existe
            ruta_monitor = f"{CARPETA_PORTAFOLIOS}/monitor_{archivo}"
            ultima_senal = "—"
            ultimo_ts = "—"
            if os.path.exists(ruta_monitor):
                try:
                    m = _leer(ruta_monitor)
                    ultimo_ts = m.get("timestamp", "—")
                    resultados = m.get("resultados", [])
                    if resultados:
                        senales = [r.get("senal", "") for r in resultados]
                        if "ENTRAR" in senales:
                            ultima_senal = "🟢 ENTRAR"
                        elif "VIGILAR" in senales:
                            ultima_senal = "🟡 VIGILAR"
                        else:
                            ultima_senal = "⚪ NEUTRAL"
                except Exception as e:
                    logger.warning(f"Could not read monitor file {ruta_monitor}: {e}")

            portafolios.append(
                {
                    "archivo": archivo,
                    "nombre": data.get("nombre", archivo),
                    "perfil": data.get("perfil", "desconocido"),
                    "propietario": data.get("propietario", ""),
                    "fecha_inicio": data.get("fecha_inicio", ""),
                    "activo": data.get("activo", False),
                    "owner": data.get("owner", "—"),
                    "monitoreo_activo": data.get("monitoreo_activo", False),
                    "ultima_senal": ultima_senal,
                    "ultimo_analisis": ultimo_ts,
                }
            )
        except Exception as e:
            logger.warning(f"Could not read portfolio {archivo}: {e}")
            continue
    return portafolios


# ============================================================
# LEER PORTAFOLIO
# ============================================================


def leer_portafolio(nombre_archivo):
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    if not os.path.exists(ruta):
        print(f"❌ No existe el portafolio {nombre_archivo}")
        return None
    try:
        return _leer(ruta)
    except Exception as e:
        # Intentar con latin-1 como fallback
        try:
            with open(ruta, "r", encoding="latin-1") as f:
                data = json.load(f)
            # Re-guardar en utf-8 limpio
            _escribir(ruta, data)
            print(f"⚠️ Portafolio {nombre_archivo} re-guardado en UTF-8.")
            return data
        except Exception as e2:
            logger.error(f"Error reading {nombre_archivo}: {e}, fallback error: {e2}")
            return None


# ============================================================
# LEER PORTAFOLIO ACTIVO
# ============================================================


def leer_portafolio_activo():
    for archivo in os.listdir(CARPETA_PORTAFOLIOS):
        if _es_portafolio_real(archivo):
            try:
                data = _leer(f"{CARPETA_PORTAFOLIOS}/{archivo}")
                if data.get("activo", False):
                    return data
            except Exception as e:
                logger.warning(f"Could not read portfolio file {archivo}: {e}")
                continue
    print("⚠️ No hay portafolio activo.")
    return None


# ============================================================
# ACTIVAR PORTAFOLIO
# ============================================================


def activar_portafolio(nombre_archivo):
    # Solo activa el monitoreo_activo del seleccionado — no toca los demás
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    data = _leer(ruta)
    data["activo"] = True
    data["monitoreo_activo"] = True
    _escribir(ruta, data)
    print(f"✅ Portafolio '{data['nombre']}' activado para monitoreo.")
    return data


# ============================================================
# MONITOREO GRANULAR (compra/venta, por activo)
# ============================================================


def set_monitoreo(nombre_archivo, tickers, tipo, valor):
    """Unica funcion que escribe data["monitoreo"]["activos"] -- fuente de
    verdad del monitoreo granular por activo (compra/venta independientes,
    no excluyentes). Setea monitoreo.activos[t][tipo]=valor para cada t en
    tickers (crea la entrada si no existe) y recalcula monitoreo_activo, el
    gate legado que sigue usando monitor.py:leer_portafolios_activos() para
    decidir que portafolios ni mirar -- se deriva SIEMPRE de este mapa, para
    no repetir la duplicacion de estado que ya existe entre "activo" y
    "monitoreo_activo" (dos booleanos sueltos que pueden desincronizarse).

    tipo: "compra" | "venta". Devuelve el mapa "monitoreo" actualizado."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        mon = data.setdefault("monitoreo", {"activos": {}})
        activos_map = mon.setdefault("activos", {})
        for t in tickers:
            entry = activos_map.setdefault(t, {"compra": False, "venta": False})
            entry[tipo] = valor
        data["monitoreo_activo"] = any(
            e.get("compra") or e.get("venta") for e in activos_map.values()
        )
        _escribir(ruta, data)
        return data["monitoreo"]


# ============================================================
# GUARDAR COMPOSICIÓN
# ============================================================


def guardar_composicion(nombre_archivo, pesos_dict, proyeccion=None, activos_fuera_meta=None):
    """proyeccion: opcional, snapshot de datos["metricas"]/datos["proyecciones"]
    (adaptador_analista._construir_datos_reporte) al momento de aplicar. Se
    guarda tal cual bajo "proyeccion_al_aplicar" -- es la proyeccion CONGELADA,
    punto de referencia fijo para auditar que tan bien predijo el modelo (ver
    proyeccion "viva", que se recalcula bajo demanda en dashboard.py y nunca
    se guarda aqui).

    activos_fuera_meta: opcional, dict {ticker: {"fecha_salida", "peso_anterior"}}
    -- activos que salieron de la composicion pero el usuario sigue sosteniendo
    en la practica (el llamador, dashboard.py:api_aplicar_propuesta, decide
    cuales aplican). Si se pasa, REEMPLAZA el mapa completo (el llamador ya
    resuelve altas/bajas antes de llamar). Si es None, no se toca.

    Cada llamada agrega un snapshot append-only a "historico_composiciones"
    -- nunca se edita, solo crece -- para poder reconstruir cuando cada activo
    cambio de estado."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    if not os.path.exists(ruta):
        print(f"❌ No existe el portafolio {nombre_archivo}")
        return
    with _LOCK:
        data = _leer(ruta)
        data["composicion"] = pesos_dict
        data["fecha_ultima_actualizacion"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        if activos_fuera_meta is not None:
            data["activos_fuera_meta"] = activos_fuera_meta
        data.setdefault("historico_composiciones", []).append({
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "composicion": pesos_dict,
        })
        if proyeccion is not None:
            data["proyeccion_al_aplicar"] = {
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "metricas": proyeccion.get("metricas"),
                "proyecciones": proyeccion.get("proyecciones"),
            }
        _escribir(ruta, data)
    print(f"✅ Composición guardada en '{data['nombre']}'.")


# ============================================================
# CAJA / SALDO
# ============================================================


class SaldoInsuficiente(Exception):
    """Se lanza cuando una operación dejaría el saldo de caja en negativo."""
    pass


class PosicionInsuficiente(Exception):
    """Se lanza al intentar vender más fracciones de las que se tienen."""
    pass


def saldo_disponible(data):
    """Saldo en USD = depósitos + producto de ventas − (compras + comisiones de
    compra). Derivado, no se guarda."""
    dep = sum(float(d.get("monto_usd", 0)) for d in data.get("depositos", []))
    ventas = sum(float(v.get("proceeds_usd", 0)) for v in data.get("ventas", []))
    gastado = sum(
        float(a.get("monto_usd", 0)) + float(a.get("comision", 0))
        for a in data.get("aportes", [])
    )
    return round(dep + ventas - gastado, 2)


def fracciones_disponibles(data, activo):
    """Fracciones de un ticker disponibles para vender: Σ compras − Σ ventas."""
    comprado = sum(float(a.get("fracciones", 0)) for a in data.get("aportes", []) if a.get("activo") == activo)
    vendido = sum(float(v.get("fracciones", 0)) for v in data.get("ventas", []) if v.get("activo") == activo)
    return round(comprado - vendido, 8)


def realizado_por_ticker(data):
    """Ganancia realizada (COP) agregada por ticker + total."""
    por_ticker = {}
    for v in data.get("ventas", []):
        tk = v.get("activo")
        por_ticker[tk] = por_ticker.get(tk, 0.0) + float(v.get("ganancia_realizada_cop", 0))
    por_ticker = {tk: round(g, 0) for tk, g in por_ticker.items()}
    return {"por_ticker": por_ticker, "total": round(sum(por_ticker.values()), 0)}


# ============================================================
# MANEJAR APORTES
# ============================================================


def guardar_aporte(nombre_archivo, aporte):
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        costo = float(aporte.get("monto_usd", 0)) + float(aporte.get("comision", 0))
        if saldo_disponible(data) - costo < -0.005:  # tolerancia de centavos
            raise SaldoInsuficiente(
                f"Saldo insuficiente: la compra cuesta US${costo:,.2f} y tienes "
                f"US${saldo_disponible(data):,.2f}. Registra un depósito primero."
            )
        aporte.setdefault("id", secrets.token_hex(6))  # id estable para editar/eliminar
        data["aportes"].append(aporte)
        _escribir(ruta, data)


def asegurar_ids_aportes(nombre_archivo):
    """Backfill idempotente: da un id estable a los aportes viejos que no lo
    tengan, para poder editarlos/eliminarlos individualmente."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        cambio = False
        for a in data.get("aportes", []):
            if "id" not in a:
                a["id"] = secrets.token_hex(6)
                cambio = True
        if cambio:
            _escribir(ruta, data)


def eliminar_aporte(nombre_archivo, aporte_id):
    """Elimina un aporte por id. Devuelve True si lo encontró y borró."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        aportes = data.get("aportes", [])
        quedan = [a for a in aportes if a.get("id") != aporte_id]
        if len(quedan) == len(aportes):
            return False
        data["aportes"] = quedan
        _escribir(ruta, data)
    return True


def editar_aporte(nombre_archivo, aporte_id, campos):
    """Reemplaza los campos de un aporte por id (conservando su id).
    Devuelve True si lo encontró y actualizó. Lanza SaldoInsuficiente si la
    edición dejaría el saldo negativo."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        for a in data.get("aportes", []):
            if a.get("id") == aporte_id:
                costo_viejo = float(a.get("monto_usd", 0)) + float(a.get("comision", 0))
                costo_nuevo = float(campos.get("monto_usd", 0)) + float(campos.get("comision", 0))
                if saldo_disponible(data) + costo_viejo - costo_nuevo < -0.005:
                    raise SaldoInsuficiente(
                        "Saldo insuficiente para esa edición: dejaría la caja en negativo."
                    )
                a.clear()
                a.update(campos)
                a["id"] = aporte_id
                _escribir(ruta, data)
                return True
    return False


# ============================================================
# MANEJAR DEPÓSITOS / CAJA
# ============================================================


def guardar_deposito(nombre_archivo, deposito):
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        deposito.setdefault("id", secrets.token_hex(6))
        data.setdefault("depositos", []).append(deposito)
        _escribir(ruta, data)


def editar_deposito(nombre_archivo, deposito_id, campos):
    """Reemplaza los campos de un depósito por id. Lanza SaldoInsuficiente si
    dejaría el saldo negativo. Devuelve True si lo encontró."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        for d in data.get("depositos", []):
            if d.get("id") == deposito_id:
                usd_viejo = float(d.get("monto_usd", 0))
                usd_nuevo = float(campos.get("monto_usd", 0))
                if saldo_disponible(data) - usd_viejo + usd_nuevo < -0.005:
                    raise SaldoInsuficiente(
                        "No puedes reducir ese depósito: dejaría el saldo negativo "
                        "(ya usaste esa plata en compras)."
                    )
                tipo = d.get("tipo", "deposito")
                d.clear()
                d.update(campos)
                d["id"] = deposito_id
                d.setdefault("tipo", tipo)
                _escribir(ruta, data)
                return True
    return False


def eliminar_deposito(nombre_archivo, deposito_id):
    """Elimina un depósito por id. Lanza SaldoInsuficiente si dejaría el saldo
    negativo. Devuelve True si lo encontró y borró."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        deps = data.get("depositos", [])
        dep = next((d for d in deps if d.get("id") == deposito_id), None)
        if dep is None:
            return False
        if saldo_disponible(data) - float(dep.get("monto_usd", 0)) < -0.005:
            raise SaldoInsuficiente(
                "No puedes eliminar ese depósito: dejaría el saldo negativo "
                "(ya usaste esa plata en compras)."
            )
        data["depositos"] = [d for d in deps if d.get("id") != deposito_id]
        _escribir(ruta, data)
    return True


def asegurar_caja_inicial(nombre_archivo):
    """Reconciliación única (idempotente): si hay compras pero la caja no se ha
    inicializado, crea un depósito de apertura = Σ compras existentes (USD) para
    que el saldo arranque en 0. Marcada con la bandera caja_inicializada."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        if data.get("caja_inicializada"):
            return
        aportes = data.get("aportes", [])
        if aportes:
            usd = round(sum(float(a.get("monto_usd", 0)) for a in aportes), 2)
            cop = round(sum(float(a.get("monto_cop", 0)) for a in aportes), 0)
            fecha_ap = min(
                (a["fecha"] for a in aportes if a.get("fecha")),
                default=datetime.now().strftime("%Y-%m-%d"),
            )
            data.setdefault("depositos", []).append({
                "id": secrets.token_hex(6),
                "fecha": fecha_ap,
                "monto_cop": cop,
                "trm_real": round(cop / usd, 2) if usd else 0,
                "monto_usd": usd,
                "tipo": "apertura",
            })
        data["caja_inicializada"] = True
        _escribir(ruta, data)


# ============================================================
# MANEJAR VENTAS
# ============================================================


def guardar_venta(nombre_archivo, venta):
    """Registra una venta. Lanza PosicionInsuficiente si intentas vender más
    fracciones de las que tienes de ese ticker."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        venta.setdefault("id", secrets.token_hex(6))
        venta.setdefault("tipo", "venta")
        activo = venta.get("activo")
        hipot = {**data, "ventas": list(data.get("ventas", [])) + [venta]}
        if fracciones_disponibles(hipot, activo) < -1e-6:
            disp = fracciones_disponibles(data, activo)
            raise PosicionInsuficiente(
                f"No tienes suficientes fracciones de {activo}: disponibles "
                f"{disp}, intentas vender {float(venta.get('fracciones', 0))}."
            )
        data.setdefault("ventas", []).append(venta)
        _escribir(ruta, data)


def editar_venta(nombre_archivo, venta_id, campos):
    """Reemplaza una venta por id (conservando id/tipo). Lanza
    PosicionInsuficiente o SaldoInsuficiente si la edición viola un invariante.
    Devuelve True si la encontró."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        ventas = data.get("ventas", [])
        idx = next((i for i, v in enumerate(ventas) if v.get("id") == venta_id), None)
        if idx is None:
            return False
        nueva = {**campos, "id": venta_id, "tipo": ventas[idx].get("tipo", "venta")}
        hipot = {**data, "ventas": [nueva if i == idx else v for i, v in enumerate(ventas)]}
        activo = nueva.get("activo")
        if fracciones_disponibles(hipot, activo) < -1e-6:
            raise PosicionInsuficiente(
                f"No tienes suficientes fracciones de {activo} para esa venta."
            )
        if saldo_disponible(hipot) < -0.005:
            raise SaldoInsuficiente("Esa edición dejaría el saldo negativo.")
        ventas[idx] = nueva
        _escribir(ruta, data)
        return True


def eliminar_venta(nombre_archivo, venta_id):
    """Elimina una venta por id. Lanza SaldoInsuficiente si su producto ya se
    usó y quitarlo dejaría el saldo negativo. Devuelve True si la encontró."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        ventas = data.get("ventas", [])
        v = next((x for x in ventas if x.get("id") == venta_id), None)
        if v is None:
            return False
        hipot = {**data, "ventas": [x for x in ventas if x.get("id") != venta_id]}
        if saldo_disponible(hipot) < -0.005:
            raise SaldoInsuficiente(
                "No puedes eliminar esa venta: su producto ya se usó y el saldo "
                "quedaría negativo."
            )
        data["ventas"] = hipot["ventas"]
        _escribir(ruta, data)
    return True


# ============================================================
# GUARDAR REGISTRO HISTÓRICO DIARIO
# ============================================================


def guardar_registro_diario(nombre_archivo, registro):
    """Agrega un snapshot diario a data["historial"], deduplicado por
    registro["fecha"] (si no viene, cae a datetime.now() del servidor).
    La llama scheduler.py una vez al dia por portafolio -- dedup por fecha
    la hace segura de invocar mas de una vez sin duplicar filas."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        historial = data.setdefault("historial", [])
        fecha = registro.get("fecha") or datetime.now().strftime("%Y-%m-%d")
        if fecha in [r["fecha"] for r in historial]:
            return False
        historial.append(registro)
        _escribir(ruta, data)
        return True


def guardar_analisis_historico(nombre_archivo, texto, fecha):
    """Cachea el analisis de Atom sobre el historico DENTRO del portafolio
    (a diferencia del analisis de TRM, que es global a la app, este es
    especifico de cada portafolio)."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with _LOCK:
        data = _leer(ruta)
        data["analisis_historico"] = {"fecha": fecha, "texto": texto}
        _escribir(ruta, data)


# ============================================================
# GESTIÓN DE USUARIOS (NUEVO)
# ============================================================

ARCHIVO_USUARIOS = os.path.join(BASE_DIR, "datos", "usuarios.json")


def _leer_usuarios():
    if not os.path.exists(ARCHIVO_USUARIOS):
        # Admin por defecto
        usuarios = {
            "admin": {
                "username": "admin",
                "email": "admin@portafolio.com",
                "password_hash": hash_password_secure("admin123"),
                "telegram_chat_id": "",
                "fecha_registro": datetime.now().strftime("%Y-%m-%d"),
                "es_admin": True,
            }
        }
        _escribir(ARCHIVO_USUARIOS, usuarios)
        return usuarios
    return _leer(ARCHIVO_USUARIOS)


def _escribir_usuarios(usuarios):
    _escribir(ARCHIVO_USUARIOS, usuarios)

DIAS_PURGA_NO_VERIFICADO = 7  # borrar registros no verificados más viejos que esto


def _purgar_no_verificados_vencidos(usuarios):
    """Borra del dict los no verificados más viejos que la ventana. Muta `usuarios`,
    devuelve cuántos borró. No toca verificados ni legacy (email_verificado
    ausente = True = intocable)."""
    limite = datetime.now() - timedelta(days=DIAS_PURGA_NO_VERIFICADO)
    vencidos = []
    for username, u in usuarios.items():
        if u.get("email_verificado", True):
            continue
        try:
            registrado = datetime.strptime(u.get("fecha_registro", ""), "%Y-%m-%d")
        except ValueError:
            continue   # sin fecha parseable → no arriesgar, dejar
        if registrado < limite:
            vencidos.append(username)
    for username in vencidos:
        del usuarios[username]
    return len(vencidos)


def registrar_usuario(username, email, password, telegram_chat_id=""):
    """Registra un nuevo usuario. Retorna True si ok, string de error si falla."""
    usuarios = _leer_usuarios()
    _purgar_no_verificados_vencidos(usuarios)   # libera emails/usernames abandonados
    if username in usuarios:
        return "Ese nombre de usuario ya existe."
    if username in usuarios:
        return "Ese nombre de usuario ya existe."
    for u in usuarios.values():
        if u["email"] == email:
            return "Ese email ya está registrado."
    usuarios[username] = {
        "username": username,
        "email": email,
        "password_hash": hash_password_secure(password),
        "telegram_chat_id": telegram_chat_id,
        "fecha_registro": datetime.now().strftime("%Y-%m-%d"),
        "es_admin": False,
        "email_verificado": False,
    }
    _escribir_usuarios(usuarios)
    return True


def login_usuario(email, password):

    usuarios = _leer_usuarios()

    # Buscar usuario por email
    usuario_key = None
    for key, u in usuarios.items():
        if u["email"] == email:
            usuario_key = key
            break

    if not usuario_key:
        return None

    u = usuarios[usuario_key]

    # Verificar si está bloqueado
    bloqueado_hasta = u.get("bloqueado_hasta")
    if bloqueado_hasta:
        hasta = datetime.strptime(bloqueado_hasta, "%Y-%m-%d %H:%M:%S")
        if datetime.now() < hasta:
            minutos = int((hasta - datetime.now()).total_seconds() / 60) + 1
            return {"bloqueado": True, "minutos": minutos, "username": u["username"]}
        else:
            # Desbloquear automáticamente si ya pasó el tiempo
            usuarios[usuario_key]["bloqueado_hasta"] = None
            usuarios[usuario_key]["intentos_fallidos"] = 0
            _escribir_usuarios(usuarios)

    # Verificar contraseña
    if verify_password(u["password_hash"], password):
        # Login exitoso — resetear intentos
        usuarios[usuario_key]["intentos_fallidos"] = 0
        usuarios[usuario_key]["bloqueado_hasta"] = None
        usuarios[usuario_key]["ultimo_login"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        # Upgrade legacy hash to secure hash on successful login
        if _is_legacy_hash(u["password_hash"]):
            usuarios[usuario_key]["password_hash"] = hash_password_secure(password)
        _escribir_usuarios(usuarios)
        return usuarios[usuario_key]

    # Contraseña incorrecta — sumar intento
    intentos = u.get("intentos_fallidos", 0) + 1
    usuarios[usuario_key]["intentos_fallidos"] = intentos

    if intentos >= 5:
        hasta = datetime.now() + timedelta(minutes=15)
        usuarios[usuario_key]["bloqueado_hasta"] = hasta.strftime("%Y-%m-%d %H:%M:%S")
        _escribir_usuarios(usuarios)
        return {"bloqueado": True, "minutos": 15, "username": u["username"]}

    _escribir_usuarios(usuarios)
    return None


def desbloquear_usuario(username):
    usuarios = _leer_usuarios()
    if username not in usuarios:
        return False
    usuarios[username]["intentos_fallidos"] = 0
    usuarios[username]["bloqueado_hasta"] = None
    _escribir_usuarios(usuarios)
    return True


def get_usuario(username):
    usuarios = _leer_usuarios()
    return usuarios.get(username)


def resetear_password(username, nueva_password="cambiar123"):
    usuarios = _leer_usuarios()
    if username not in usuarios:
        return False
    usuarios[username]["password_hash"] = hash_password_secure(nueva_password)
    _escribir_usuarios(usuarios)
    return True


def actualizar_usuario(username, campos):
    """Actualiza campos del usuario (email, telegram_chat_id, password_hash)."""
    usuarios = _leer_usuarios()
    if username not in usuarios:
        return False
    usuarios[username].update(campos)
    _escribir_usuarios(usuarios)
    return True


def listar_portafolios_de_usuario(username):
    """Lista solo los portafolios que pertenecen a este usuario."""
    archivos = [f for f in os.listdir(CARPETA_PORTAFOLIOS) if _es_portafolio_real(f)]
    resultado = []
    for archivo in archivos:
        try:
            data = _leer(f"{CARPETA_PORTAFOLIOS}/{archivo}")
            if data.get("owner") == username:
                resultado.append(
                    {
                        "archivo": archivo,
                        "nombre": data.get("nombre", archivo),
                        "perfil": data.get("perfil", "desconocido"),
                        "propietario": data.get("propietario", ""),
                        "fecha_inicio": data.get("fecha_inicio", ""),
                        "activo": data.get("activo", False),
                        "monitoreo_activo": data.get("monitoreo_activo", False),
                    }
                )
        except Exception as e:
            logger.warning(f"Could not read portfolio {archivo}: {e}")
            continue
    return resultado


def crear_portafolio_para_usuario(
    username,
    nombre,
    perfil,
    propietario,
    inversion_inicial,
    aporte_dca=0,
    frecuencia_meses=0,
):
    """Igual que crear_portafolio pero agrega el campo owner."""
    # El nombre de archivo incluye el usuario para que dos personas puedan
    # tener un portafolio con el mismo nombre sin chocar.
    nombre_archivo = f"{_slug(username)}_{_slug(nombre)}"
    archivo = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}.json"
    if os.path.exists(archivo):
        # Ya existe uno con ese nombre PARA ESTE usuario: agrega sufijo numerico
        n = 2
        while os.path.exists(f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}_{n}.json"):
            n += 1
        nombre_archivo = f"{nombre_archivo}_{n}"
        archivo = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}.json"

    portafolio = {
        "owner": username,  # ← CAMPO NUEVO
        "nombre": nombre,
        "perfil": perfil,
        "propietario": propietario,
        "password_hash": "",  # ya no se usa para auth
        "email": "",
        "telegram_chat_id": "",
        "fecha_inicio": datetime.now().strftime("%Y-%m-%d"),
        "inversion_inicial": inversion_inicial,
        "aporte_dca": aporte_dca,
        "frecuencia_meses": frecuencia_meses,
        "activo": False,
        "monitoreo_activo": False,
        "composicion": {},
        "aportes": [],
        "historial": [],
    }
    _escribir(archivo, portafolio)
    return archivo


# ============================================================
# LOGS DE ACTIVIDAD (NUEVO)
# ============================================================

ARCHIVO_LOGS_ACTIVIDAD = os.path.join(BASE_DIR, "datos", "logs_actividad.json")


def _leer_logs():
    if not os.path.exists(ARCHIVO_LOGS_ACTIVIDAD):
        return []
    try:
        return _leer(ARCHIVO_LOGS_ACTIVIDAD)
    except Exception as e:
        logger.warning(f"Could not read activity logs: {e}")
        return []


def registrar_actividad(tipo, username, email="", detalle="", ip="", dispositivo=""):
    """
    tipo: 'login_ok', 'login_fail', 'registro_nuevo', 'logout'
    """
    logs = _leer_logs()
    logs.append(
        {
            "tipo": tipo,
            "username": username,
            "email": email,
            "detalle": detalle,
            "ip": ip,
            "dispositivo": dispositivo,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    # Mantener solo los últimos 500 registros
    if len(logs) > 500:
        logs = logs[-500:]
    _escribir(ARCHIVO_LOGS_ACTIVIDAD, logs)


def eliminar_usuario(username):
    """Elimina el usuario y todos sus portafolios."""
    usuarios = _leer_usuarios()
    if username not in usuarios:
        return False
    # Eliminar portafolios del usuario
    if os.path.exists(CARPETA_PORTAFOLIOS):
        for archivo in os.listdir(CARPETA_PORTAFOLIOS):
            if _es_portafolio_real(archivo):
                try:
                    data = _leer(f"{CARPETA_PORTAFOLIOS}/{archivo}")
                    if data.get("owner") == username:
                        os.remove(f"{CARPETA_PORTAFOLIOS}/{archivo}")
                        # Eliminar monitor si existe
                        monitor = f"{CARPETA_PORTAFOLIOS}/monitor_{archivo}"
                        if os.path.exists(monitor):
                            os.remove(monitor)
                except Exception as e:
                    logger.warning(
                        f"Could not process portfolio {archivo} during user deletion: {e}"
                    )
                    continue
    # Eliminar usuario
    del usuarios[username]
    _escribir_usuarios(usuarios)
    return True