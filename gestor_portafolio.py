import json
import os
from datetime import datetime

CARPETA_PORTAFOLIOS = "datos/portafolios"
os.makedirs(CARPETA_PORTAFOLIOS, exist_ok=True)

# ============================================================
# LISTAR PORTAFOLIOS
# ============================================================

def listar_portafolios():
    """Lista todos los portafolios disponibles."""
    archivos = [f for f in os.listdir(CARPETA_PORTAFOLIOS)
                if f.endswith('.json')]

    if not archivos:
        return []

    portafolios = []
    for archivo in archivos:
        try:
            with open(f"{CARPETA_PORTAFOLIOS}/{archivo}", 'r') as f:
                data = json.load(f)
            portafolios.append({
                'archivo':    archivo,
                'nombre':     data.get('nombre', archivo),
                'perfil':     data.get('perfil', 'desconocido'),
                'propietario': data.get('propietario', ''),
                'fecha_inicio': data.get('fecha_inicio', ''),
                'activo':     data.get('activo', False)
            })
        except:
            continue

    return portafolios

# ============================================================
# CREAR PORTAFOLIO NUEVO
# ============================================================

def crear_portafolio(nombre, perfil, propietario, inversion_inicial,
                     aporte_dca=0, frecuencia_meses=0):
    """Crea un nuevo portafolio independiente."""

    # Nombre de archivo limpio
    nombre_archivo = (nombre.lower()
                     .replace(' ', '_')
                     .replace('á','a').replace('é','e')
                     .replace('í','i').replace('ó','o')
                     .replace('ú','u'))
    archivo = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}.json"

    # Verificar si ya existe
    if os.path.exists(archivo):
        print(f"⚠️ Ya existe un portafolio con ese nombre.")
        return None

    portafolio = {
        "nombre":           nombre,
        "perfil":           perfil,
        "propietario":      propietario,
        "fecha_inicio":     datetime.now().strftime("%Y-%m-%d"),
        "inversion_inicial": inversion_inicial,
        "aporte_dca":       aporte_dca,
        "frecuencia_meses": frecuencia_meses,
        "activo":           False,
        "composicion":      {},
        "aportes":          [],
        "historial":        []
    }

    with open(archivo, 'w') as f:
        json.dump(portafolio, f, indent=2, ensure_ascii=False)

    print(f"✅ Portafolio '{nombre}' creado para {propietario}.")
    return archivo

# ============================================================
# ACTIVAR PORTAFOLIO
# ============================================================

def activar_portafolio(nombre_archivo):
    """
    Activa un portafolio para monitoreo.
    Solo uno puede estar activo a la vez por perfil.
    """
    # Desactivar todos primero
    for archivo in os.listdir(CARPETA_PORTAFOLIOS):
        if archivo.endswith('.json'):
            ruta = f"{CARPETA_PORTAFOLIOS}/{archivo}"
            try:
                with open(ruta, 'r') as f:
                    data = json.load(f)
                data['activo'] = False
                with open(ruta, 'w') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except:
                continue

    # Activar el seleccionado
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with open(ruta, 'r') as f:
        data = json.load(f)
    data['activo'] = True
    with open(ruta, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Portafolio '{data['nombre']}' activado para monitoreo.")
    return data

# ============================================================
# LEER PORTAFOLIO ACTIVO
# ============================================================

def leer_portafolio_activo():
    """Lee el portafolio actualmente activo."""
    for archivo in os.listdir(CARPETA_PORTAFOLIOS):
        if archivo.endswith('.json'):
            ruta = f"{CARPETA_PORTAFOLIOS}/{archivo}"
            try:
                with open(ruta, 'r') as f:
                    data = json.load(f)
                if data.get('activo', False):
                    return data
            except:
                continue

    print("⚠️ No hay portafolio activo.")
    return None

# ============================================================
# LEER PORTAFOLIO POR NOMBRE
# ============================================================

def leer_portafolio(nombre_archivo):
    """Lee un portafolio específico por nombre de archivo."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    if not os.path.exists(ruta):
        print(f"❌ No existe el portafolio {nombre_archivo}")
        return None
    with open(ruta, 'r') as f:
        return json.load(f)

# ============================================================
# GUARDAR COMPOSICIÓN (lo llama el Analista 1)
# ============================================================

def guardar_composicion(nombre_archivo, pesos_dict):
    """
    Guarda la composición sugerida por el Analista 1
    en un portafolio específico.
    """
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    if not os.path.exists(ruta):
        print(f"❌ No existe el portafolio {nombre_archivo}")
        return

    with open(ruta, 'r') as f:
        data = json.load(f)

    data['composicion'] = pesos_dict
    data['fecha_ultima_actualizacion'] = datetime.now().strftime("%Y-%m-%d %H:%M")

    with open(ruta, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Composición guardada en '{data['nombre']}'.")

# ============================================================
# GUARDAR APORTE (lo llama el Seguimiento)
# ============================================================

def guardar_aporte(nombre_archivo, aporte):
    """Agrega un aporte de inversión al portafolio."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with open(ruta, 'r') as f:
        data = json.load(f)

    data['aportes'].append(aporte)

    with open(ruta, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ============================================================
# GUARDAR REGISTRO HISTÓRICO DIARIO
# ============================================================

def guardar_registro_diario(nombre_archivo, registro):
    """Agrega un registro diario al historial del portafolio."""
    ruta = f"{CARPETA_PORTAFOLIOS}/{nombre_archivo}"
    with open(ruta, 'r') as f:
        data = json.load(f)

    # Verificar si ya existe registro de hoy
    hoy = datetime.now().strftime("%Y-%m-%d")
    fechas_existentes = [r['fecha'] for r in data.get('historial', [])]

    if hoy in fechas_existentes:
        return False  # Ya existe

    data['historial'].append(registro)

    with open(ruta, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return True

# ============================================================
# MENÚ INTERACTIVO (para uso desde terminal)
# ============================================================

def menu_portafolios():
    """Menú interactivo para gestionar portafolios."""
    print("\n" + "="*50)
    print("  GESTOR DE PORTAFOLIOS")
    print("="*50)

    portafolios = listar_portafolios()

    if portafolios:
        print(f"\n📋 Portafolios disponibles ({len(portafolios)}):")
        for i, p in enumerate(portafolios, 1):
            estado = "🟢 ACTIVO" if p['activo'] else "⚪"
            print(f"   {i}. {estado} {p['nombre']} "
                  f"({p['perfil']}) — {p['propietario']}")
    else:
        print("\n📭 No hay portafolios creados aún.")

    print("\n¿Qué quieres hacer?")
    print("   1. Crear portafolio nuevo")
    print("   2. Activar un portafolio")
    print("   3. Salir")

    opcion = input("\nEscribe 1, 2 o 3: ").strip()

    if opcion == '1':
        print("\n📝 CREAR PORTAFOLIO NUEVO")
        nombre      = input("   Nombre (ej: Agresivo Andrea 2026): ")
        propietario = input("   Propietario (ej: Andrea): ")
        print("   Perfil: 1=Conservador | 2=Agresivo")
        perfil_op   = input("   Escribe 1 o 2: ")
        perfil      = 'conservador' if perfil_op == '1' else 'agresivo'
        inv_str     = input("   Inversión inicial en COP: ")
        inv         = float(inv_str.replace(',', '').replace('.', ''))

        tiene_dca = input("   ¿Tendrá DCA periódico? (SI/NO): ").upper()
        if tiene_dca == 'SI':
            ap_str = input("   ¿Cuánto por aporte en COP? ")
            aporte = float(ap_str.replace(',', '').replace('.', ''))
            print("   Frecuencia: 1=Mensual | 3=Trimestral | 12=Anual")
            freq   = int(input("   Escribe 1, 3 o 12: "))
        else:
            aporte = 0
            freq   = 0

        crear_portafolio(nombre, perfil, propietario, inv, aporte, freq)

    elif opcion == '2':
        if not portafolios:
            print("❌ No hay portafolios para activar.")
            return
        num = int(input("\n   ¿Cuál número quieres activar? ")) - 1
        if 0 <= num < len(portafolios):
            activar_portafolio(portafolios[num]['archivo'])
        else:
            print("❌ Número inválido.")

if __name__ == "__main__":
    menu_portafolios()