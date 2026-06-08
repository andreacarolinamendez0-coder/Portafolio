import json
import os
import hashlib
from datetime import datetime

CARPETA_PORTAFOLIOS = "datos/portafolios"
os.makedirs(CARPETA_PORTAFOLIOS, exist_ok=True)

# ============================================================
# UTILIDADES
# ============================================================


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def _leer(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def _escribir(ruta, data):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================
# LISTAR PORTAFOLIOS
# ============================================================


def listar_portafolios():
    archivos = [
        f
        for f in os.listdir(CARPETA_PORTAFOLIOS)
        if f.endswith(".json") and not f.startswith("monitor_")
    ]
    portafolios = []
    for archivo in archivos:
        try:
            data = _leer(f"{CARPETA_PORTAFOLIOS}/{archivo}")

            # Leer último análisis del monitor si existe
            ruta_monitor = f"{CARPETA_PORTAFOLIOS}/monitor_{archivo}"
            ultimo_monitor = None
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
                except:
                    pass

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
        except:
            continue
    return portafolios


# ============================================================
# CREAR PORTAFOLIO
# ============================================================


def crear_portafolio(
    nombre,
    perfil,
    propietario,
    inversion_inicial,
    aporte_dca=0,
    frecuencia_meses=0,
    password="1234",
    email="",
    telegram_chat_id="",
):
    nombre_archivo = (
        nombre.lower()
        .replace(" ", "_")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    archivo = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}.json"

    if os.path.exists(archivo):
        print(f"⚠️ Ya existe un portafolio con ese nombre.")
        return None

    portafolio = {
        "nombre": nombre,
        "perfil": perfil,
        "propietario": propietario,
        "password_hash": hash_password(password),
        "email": email,
        "telegram_chat_id": telegram_chat_id,
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
    print(f"✅ Portafolio '{nombre}' creado para {propietario}.")
    return archivo


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
        except:
            print(f"❌ Error leyendo {nombre_archivo}: {e}")
            return None


# ============================================================
# LEER PORTAFOLIO ACTIVO
# ============================================================


def leer_portafolio_activo():
    for archivo in os.listdir(CARPETA_PORTAFOLIOS):
        if archivo.endswith(".json") and not archivo.startswith("monitor_"):
            try:
                data = _leer(f"{CARPETA_PORTAFOLIOS}/{archivo}")
                if data.get("activo", False):
                    return data
            except:
                continue
    print("⚠️ No hay portafolio activo.")
    return None


# ============================================================
# VERIFICAR PASSWORD
# ============================================================


def verificar_password(nombre_archivo, password):
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    try:
        data = _leer(ruta)
        return data.get("password_hash") == hash_password(password)
    except:
        return False


# ============================================================
# BUSCAR PORTAFOLIOS POR PASSWORD
# ============================================================


def buscar_portafolios_por_password(password):
    ph = hash_password(password)
    resultados = []
    for archivo in os.listdir(CARPETA_PORTAFOLIOS):
        if not archivo.endswith(".json") or archivo.startswith("monitor_"):
            continue
        try:
            data = _leer(f"{CARPETA_PORTAFOLIOS}/{archivo}")
            if data.get("password_hash") == ph:
                resultados.append(
                    {
                        "archivo": archivo,
                        "nombre": data["nombre"],
                        "perfil": data["perfil"],
                        "propietario": data["propietario"],
                    }
                )
        except:
            continue
    return resultados


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
# MENÚ INTERACTIVO
# ============================================================


def menu_portafolios():
    print("\n" + "=" * 50)
    print("  GESTOR DE PORTAFOLIOS")
    print("=" * 50)

    portafolios = listar_portafolios()

    if portafolios:
        print(f"\n📋 Portafolios disponibles ({len(portafolios)}):")
        for i, p in enumerate(portafolios, 1):
            estado = "🟢 ACTIVO" if p["activo"] else "⚪"
            print(
                f"   {i}. {estado} {p['nombre']} ({p['perfil']}) — {p['propietario']}"
            )
    else:
        print("\n📭 No hay portafolios creados aún.")

    print("\n¿Qué quieres hacer?")
    print("   1. Crear portafolio nuevo")
    print("   2. Activar un portafolio")
    print("   3. Salir")

    opcion = input("\nEscribe 1, 2 o 3: ").strip()

    if opcion == "1":
        print("\n📝 CREAR PORTAFOLIO NUEVO")
        nombre = input("   Nombre (ej: Agresivo Andrea 2026): ")
        propietario = input("   Propietario (ej: Andrea): ")
        print("   Perfil: 1=Conservador | 2=Agresivo")
        perfil_op = input("   Escribe 1 o 2: ")
        perfil = "conservador" if perfil_op == "1" else "agresivo"
        inv_str = input("   Inversión inicial en COP: ")
        inv = float(inv_str.replace(",", "").replace(".", ""))
        tiene_dca = input("   ¿Tendrá DCA periódico? (SI/NO): ").upper()
        if tiene_dca == "SI":
            ap_str = input("   ¿Cuánto por aporte en COP? ")
            aporte = float(ap_str.replace(",", "").replace(".", ""))
            print("   Frecuencia: 1=Mensual | 3=Trimestral | 12=Anual")
            freq = int(input("   Escribe 1, 3 o 12: "))
        else:
            aporte = 0
            freq = 0
        password = input("   Contraseña: ")
        crear_portafolio(nombre, perfil, propietario, inv, aporte, freq, password)

    elif opcion == "2":
        if not portafolios:
            print("❌ No hay portafolios para activar.")
            return
        num = int(input("\n   ¿Cuál número quieres activar? ")) - 1
        if 0 <= num < len(portafolios):
            activar_portafolio(portafolios[num]["archivo"])
        else:
            print("❌ Número inválido.")


if __name__ == "__main__":
    menu_portafolios()

# ============================================================
# GESTIÓN DE USUARIOS (NUEVO)
# ============================================================

ARCHIVO_USUARIOS = "datos/usuarios.json"


def _leer_usuarios():
    if not os.path.exists(ARCHIVO_USUARIOS):
        # Admin por defecto
        usuarios = {
            "admin": {
                "username": "admin",
                "email": "admin@portafolio.com",
                "password_hash": hash_password("admin123"),
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


def registrar_usuario(username, email, password, telegram_chat_id=""):
    """Registra un nuevo usuario. Retorna True si ok, string de error si falla."""
    usuarios = _leer_usuarios()
    if username in usuarios:
        return "Ese nombre de usuario ya existe."
    for u in usuarios.values():
        if u["email"] == email:
            return "Ese email ya está registrado."
    usuarios[username] = {
        "username": username,
        "email": email,
        "password_hash": hash_password(password),
        "telegram_chat_id": telegram_chat_id,
        "fecha_registro": datetime.now().strftime("%Y-%m-%d"),
        "es_admin": False,
    }
    _escribir_usuarios(usuarios)
    return True


def login_usuario(email, password):
    from datetime import datetime, timedelta

    usuarios = _leer_usuarios()
    ph = hash_password(password)

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
    if u["password_hash"] == ph:
        # Login exitoso — resetear intentos
        usuarios[usuario_key]["intentos_fallidos"] = 0
        usuarios[usuario_key]["bloqueado_hasta"] = None
        usuarios[usuario_key]["ultimo_login"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        _escribir_usuarios(usuarios)
        return u

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
    usuarios[username]["password_hash"] = hash_password(nueva_password)
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
    archivos = [
        f
        for f in os.listdir(CARPETA_PORTAFOLIOS)
        if f.endswith(".json") and not f.startswith("monitor_")
    ]
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
        except:
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
    nombre_archivo = (
        nombre.lower()
        .replace(" ", "_")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    archivo = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}.json"
    if os.path.exists(archivo):
        return None  # ya existe

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

ARCHIVO_LOGS_ACTIVIDAD = "datos/logs_actividad.json"


def _leer_logs():
    if not os.path.exists(ARCHIVO_LOGS_ACTIVIDAD):
        return []
    try:
        return _leer(ARCHIVO_LOGS_ACTIVIDAD)
    except:
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
            if archivo.endswith(".json") and not archivo.startswith("monitor_"):
                try:
                    data = _leer(f"{CARPETA_PORTAFOLIOS}/{archivo}")
                    if data.get("owner") == username:
                        os.remove(f"{CARPETA_PORTAFOLIOS}/{archivo}")
                        # Eliminar monitor si existe
                        monitor = f"{CARPETA_PORTAFOLIOS}/monitor_{archivo}"
                        if os.path.exists(monitor):
                            os.remove(monitor)
                except:
                    continue
    # Eliminar usuario
    del usuarios[username]
    _escribir_usuarios(usuarios)
    return True
