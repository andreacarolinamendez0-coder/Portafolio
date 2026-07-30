import json
import os
import hashlib
import logging
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARPETA_PORTAFOLIOS = os.path.join(BASE_DIR, "datos", "portafolios")
os.makedirs(CARPETA_PORTAFOLIOS, exist_ok=True)

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
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


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
# GUARDAR COMPOSICIÓN
# ============================================================


def guardar_composicion(nombre_archivo, pesos_dict):
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    if not os.path.exists(ruta):
        print(f"❌ No existe el portafolio {nombre_archivo}")
        return
    data = _leer(ruta)
    data["composicion"] = pesos_dict
    data["fecha_ultima_actualizacion"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _escribir(ruta, data)
    print(f"✅ Composición guardada en '{data['nombre']}'.")


# ============================================================
# MANEJAR APORTES
# ============================================================


def guardar_aporte(nombre_archivo, aporte):
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    data = _leer(ruta)
    data["aportes"].append(aporte)
    _escribir(ruta, data)


def borrar_aportes(nombre_archivo):
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    data = _leer(ruta)
    data["aportes"] = []
    _escribir(ruta, data)
    return True


# ============================================================
# GUARDAR REGISTRO HISTÓRICO DIARIO
# ============================================================


def guardar_registro_diario(nombre_archivo, registro):
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    data = _leer(ruta)
    hoy = datetime.now().strftime("%Y-%m-%d")
    if hoy in [r["fecha"] for r in data.get("historial", [])]:
        return False
    data["historial"].append(registro)
    _escribir(ruta, data)
    return True


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