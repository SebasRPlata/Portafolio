"""
database.py – Capa de datos (SQLite) del Sistema de Control, Auditoría e
Inventario de Equipos (IT Asset Management).

Tablas:
  - equipos        : inventario completo de activos (incluye ruta de imagen)
  - historial      : auditoría automática (crear / actualizar / eliminar / mantenimiento)
  - mantenimientos : bitácora de mantenimientos por equipo
"""
import getpass
import ipaddress
import random
import re
import shutil
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

# ──────────────────────────── Rutas ────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "database" / "inventario.db"
IMG_DIR = BASE_DIR / "assets" / "equipos"

# ──────────────────────────── Catálogos ────────────────────────────
TIPOS = ["Laptop", "PC de Escritorio", "Monitor", "Impresora", "Servidor",
         "Switch", "Router", "Access Point", "Tablet", "UPS"]
ESTADOS = ["Operativo", "En Mantenimiento", "En Almacén", "Dado de baja"]
DEPARTAMENTOS = ["Administración", "Contabilidad", "Ventas", "Logística",
                 "Recursos Humanos", "Gerencia", "Almacén", "TI"]
TIPOS_MANTENIMIENTO = ["Preventivo", "Correctivo", "Predictivo"]
ESTADOS_MANTENIMIENTO = ["Completado", "En proceso"]

CAMPOS = [
    "codigo_activo", "nombre_equipo", "tipo", "marca", "modelo", "num_serie",
    "procesador", "ram_gb", "almacenamiento", "sistema_operativo",
    "direccion_ip", "direccion_mac", "usuario_asignado", "departamento",
    "ubicacion", "estado", "fecha_compra", "garantia_hasta", "costo",
    "proveedor", "observaciones", "imagen_path",
]
OBLIGATORIOS = {
    "nombre_equipo": "Nombre del equipo", "tipo": "Tipo", "marca": "Marca",
    "modelo": "Modelo", "num_serie": "N.º de serie", "estado": "Estado",
}


# ──────────────────────────── Conexión ────────────────────────────
@contextmanager
def conexion():
    """Abre una conexión SQLite; confirma al salir o revierte si hay error."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def inicializar_bd():
    """Crea tablas e índices; si la BD está vacía, la llena con 100 equipos."""
    estados_sql = ", ".join(f"'{e}'" for e in ESTADOS)
    with conexion() as con:
        con.executescript(f"""
            CREATE TABLE IF NOT EXISTS equipos (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_activo       TEXT NOT NULL UNIQUE,
                nombre_equipo       TEXT NOT NULL,
                tipo                TEXT NOT NULL,
                marca               TEXT NOT NULL,
                modelo              TEXT NOT NULL,
                num_serie           TEXT NOT NULL UNIQUE,
                procesador          TEXT DEFAULT '',
                ram_gb              INTEGER DEFAULT 0,
                almacenamiento      TEXT DEFAULT '',
                sistema_operativo   TEXT DEFAULT '',
                direccion_ip        TEXT DEFAULT '',
                direccion_mac       TEXT DEFAULT '',
                usuario_asignado    TEXT DEFAULT '',
                departamento        TEXT DEFAULT '',
                ubicacion           TEXT DEFAULT '',
                estado              TEXT NOT NULL DEFAULT 'Operativo'
                                    CHECK (estado IN ({estados_sql})),
                fecha_compra        TEXT DEFAULT '',
                garantia_hasta      TEXT DEFAULT '',
                costo               REAL DEFAULT 0,
                proveedor           TEXT DEFAULT '',
                observaciones       TEXT DEFAULT '',
                imagen_path         TEXT DEFAULT '',
                fecha_registro      TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS historial (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                equipo_id       INTEGER,
                codigo_activo   TEXT,
                accion          TEXT NOT NULL,
                detalle         TEXT DEFAULT '',
                usuario_sistema TEXT DEFAULT '',
                fecha           TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS mantenimientos (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                equipo_id   INTEGER NOT NULL
                            REFERENCES equipos(id) ON DELETE CASCADE,
                fecha       TEXT NOT NULL,
                tipo        TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                tecnico     TEXT DEFAULT '',
                costo       REAL DEFAULT 0,
                estado      TEXT NOT NULL DEFAULT 'Completado'
            );

            CREATE INDEX IF NOT EXISTS idx_equipos_tipo    ON equipos(tipo);
            CREATE INDEX IF NOT EXISTS idx_equipos_estado  ON equipos(estado);
            CREATE INDEX IF NOT EXISTS idx_equipos_usuario ON equipos(usuario_asignado);
            CREATE INDEX IF NOT EXISTS idx_hist_equipo     ON historial(equipo_id);
            CREATE INDEX IF NOT EXISTS idx_mant_equipo     ON mantenimientos(equipo_id);
        """)
        if con.execute("SELECT COUNT(*) FROM equipos").fetchone()[0] == 0:
            _sembrar(con, 100)


# ──────────────────────────── Validación ────────────────────────────
def normalizar(datos):
    """Devuelve un dict con todos los campos limpios y con el tipo correcto."""
    d = {c: datos.get(c, "") for c in CAMPOS}
    for k, v in d.items():
        if isinstance(v, str):
            d[k] = v.strip()
    d["direccion_mac"] = d["direccion_mac"].upper().replace("-", ":")
    try:
        d["ram_gb"] = int(d["ram_gb"] or 0)
    except (ValueError, TypeError):
        raise ValueError("La RAM debe ser un número entero (GB).")
    try:
        d["costo"] = float(str(d["costo"]).replace(",", ".") or 0)
    except (ValueError, TypeError):
        raise ValueError("El costo debe ser un número (ej. 2450.50).")
    return d


def validar(datos):
    """Retorna un mensaje de error o None si los datos son válidos."""
    try:
        d = normalizar(datos)
    except ValueError as e:
        return str(e)

    for campo, etiqueta in OBLIGATORIOS.items():
        if not d[campo]:
            return f"El campo «{etiqueta}» es obligatorio."
    if d["estado"] not in ESTADOS:
        return "Estado no válido."
    if d["ram_gb"] < 0 or d["costo"] < 0:
        return "RAM y costo no pueden ser negativos."
    if d["direccion_ip"]:
        try:
            ipaddress.ip_address(d["direccion_ip"])
        except ValueError:
            return "La dirección IP no es válida (ej. 192.168.1.25)."
    if d["direccion_mac"] and not re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", d["direccion_mac"]):
        return "La MAC no es válida (ej. A4:5E:60:1B:22:C3)."
    for campo, etiqueta in (("fecha_compra", "Fecha de compra"), ("garantia_hasta", "Garantía hasta")):
        if d[campo]:
            try:
                datetime.strptime(d[campo], "%Y-%m-%d")
            except ValueError:
                return f"«{etiqueta}» debe tener el formato AAAA-MM-DD."
    if d["fecha_compra"] and d["garantia_hasta"] and d["garantia_hasta"] < d["fecha_compra"]:
        return "La garantía no puede vencer antes de la fecha de compra."
    return None


# ──────────────────────────── Imágenes ────────────────────────────
def guardar_imagen(origen, codigo):
    """Copia la imagen a assets/equipos/ y devuelve su ruta relativa."""
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(origen).suffix.lower() or ".png"
    destino = IMG_DIR / f"{codigo}_{int(time.time() * 1000)}{ext}"
    shutil.copy2(origen, destino)
    return destino.relative_to(BASE_DIR).as_posix()


def ruta_imagen(rel):
    """Ruta absoluta de una imagen guardada (o None)."""
    return BASE_DIR / rel if rel else None


def borrar_imagen(rel):
    try:
        p = ruta_imagen(rel)
        if p and p.is_file() and IMG_DIR in p.parents:
            p.unlink()
    except OSError:
        pass


# ──────────────────────────── Auditoría ────────────────────────────
def _log(con, equipo_id, codigo, accion, detalle=""):
    con.execute(
        "INSERT INTO historial (equipo_id, codigo_activo, accion, detalle, usuario_sistema) "
        "VALUES (?, ?, ?, ?, ?)",
        (equipo_id, codigo, accion, detalle, getpass.getuser()),
    )


# ──────────────────────────── CRUD ────────────────────────────
def siguiente_codigo():
    """Código de activo que se asignará al próximo equipo (ACT-0101, ...)."""
    with conexion() as con:
        fila = con.execute("SELECT seq FROM sqlite_sequence WHERE name='equipos'").fetchone()
    return f"ACT-{(fila['seq'] if fila else 0) + 1:04d}"


def crear_equipo(datos):
    """CREATE. Retorna (ok, mensaje, nuevo_id)."""
    error = validar(datos)
    if error:
        return False, error, None
    d = normalizar(datos)
    try:
        with conexion() as con:
            if not d["codigo_activo"]:
                n = (con.execute("SELECT COALESCE(MAX(id),0)+1 FROM equipos").fetchone()[0])
                d["codigo_activo"] = f"ACT-{n:04d}"
            cols = ", ".join(CAMPOS)
            marcas = ", ".join(f":{c}" for c in CAMPOS)
            cur = con.execute(f"INSERT INTO equipos ({cols}) VALUES ({marcas})", d)
            _log(con, cur.lastrowid, d["codigo_activo"], "CREAR",
                 f"{d['tipo']} {d['marca']} {d['modelo']} · serie {d['num_serie']}")
            return True, "Equipo registrado correctamente.", cur.lastrowid
    except sqlite3.IntegrityError as e:
        if "num_serie" in str(e):
            return False, "El número de serie ya está registrado.", None
        if "codigo_activo" in str(e):
            return False, "El código de activo ya existe.", None
        return False, f"Error de integridad: {e}", None
    except sqlite3.Error as e:
        return False, f"Error de BD: {e}", None


def obtener_equipo(equipo_id):
    """READ (uno)."""
    with conexion() as con:
        return con.execute("SELECT * FROM equipos WHERE id = ?", (equipo_id,)).fetchone()


def obtener_equipos(texto="", tipo="Todos", estado="Todos"):
    """READ (lista) con búsqueda y filtros."""
    sql, params = "SELECT * FROM equipos WHERE 1=1", []
    if texto.strip():
        like = f"%{texto.strip()}%"
        sql += (" AND (codigo_activo LIKE ? OR nombre_equipo LIKE ? OR marca LIKE ? OR modelo LIKE ?"
                " OR num_serie LIKE ? OR usuario_asignado LIKE ? OR direccion_ip LIKE ?"
                " OR departamento LIKE ?)")
        params += [like] * 8
    if tipo and tipo != "Todos":
        sql += " AND tipo = ?"
        params.append(tipo)
    if estado and estado != "Todos":
        sql += " AND estado = ?"
        params.append(estado)
    sql += " ORDER BY id"
    with conexion() as con:
        return con.execute(sql, params).fetchall()


def actualizar_equipo(equipo_id, datos):
    """UPDATE. Registra en el historial qué campos cambiaron. Retorna (ok, mensaje)."""
    error = validar(datos)
    if error:
        return False, error
    d = normalizar(datos)
    try:
        with conexion() as con:
            actual = con.execute("SELECT * FROM equipos WHERE id = ?", (equipo_id,)).fetchone()
            if actual is None:
                return False, "El equipo ya no existe."
            d["codigo_activo"] = actual["codigo_activo"]
            cambios = [f"{c}: {actual[c]!r} → {d[c]!r}"
                       for c in CAMPOS if c != "imagen_path" and actual[c] != d[c]]
            if actual["imagen_path"] != d["imagen_path"]:
                cambios.append("imagen modificada")
            if not cambios:
                return True, "No hay cambios que guardar."
            sets = ", ".join(f"{c} = :{c}" for c in CAMPOS)
            d["id"] = equipo_id
            con.execute(
                f"UPDATE equipos SET {sets}, fecha_actualizacion = datetime('now','localtime') "
                "WHERE id = :id", d)
            _log(con, equipo_id, d["codigo_activo"], "ACTUALIZAR", "; ".join(cambios)[:1000])
        return True, "Equipo actualizado correctamente."
    except sqlite3.IntegrityError as e:
        if "num_serie" in str(e):
            return False, "Ese número de serie ya pertenece a otro equipo."
        return False, f"Error de integridad: {e}"
    except sqlite3.Error as e:
        return False, f"Error de BD: {e}"


def eliminar_equipo(equipo_id):
    """DELETE. Borra también su imagen; el historial se conserva. Retorna (ok, mensaje)."""
    try:
        with conexion() as con:
            fila = con.execute("SELECT codigo_activo, nombre_equipo, imagen_path FROM equipos "
                               "WHERE id = ?", (equipo_id,)).fetchone()
            if fila is None:
                return False, "El equipo ya no existe."
            con.execute("DELETE FROM equipos WHERE id = ?", (equipo_id,))
            _log(con, equipo_id, fila["codigo_activo"], "ELIMINAR", fila["nombre_equipo"])
        borrar_imagen(fila["imagen_path"])
        return True, "Equipo eliminado."
    except sqlite3.Error as e:
        return False, f"Error de BD: {e}"


# ──────────────────────────── Consultas auxiliares ────────────────────────────
def listar_tipos():
    with conexion() as con:
        return [r[0] for r in con.execute("SELECT DISTINCT tipo FROM equipos ORDER BY tipo")]


def estadisticas():
    """Datos para las tarjetas del panel superior."""
    hoy = date.today()
    limite = (hoy + timedelta(days=60)).isoformat()
    hoy = hoy.isoformat()
    with conexion() as con:
        total = con.execute("SELECT COUNT(*) FROM equipos").fetchone()[0]
        por_estado = {r["estado"]: r["n"] for r in
                      con.execute("SELECT estado, COUNT(*) AS n FROM equipos GROUP BY estado")}
        valor = con.execute("SELECT COALESCE(SUM(costo),0) FROM equipos "
                            "WHERE estado != 'Dado de baja'").fetchone()[0]
        vencidas = con.execute("SELECT COUNT(*) FROM equipos WHERE garantia_hasta != '' "
                               "AND garantia_hasta < ? AND estado != 'Dado de baja'", (hoy,)).fetchone()[0]
        por_vencer = con.execute("SELECT COUNT(*) FROM equipos WHERE garantia_hasta BETWEEN ? AND ? "
                                 "AND estado != 'Dado de baja'", (hoy, limite)).fetchone()[0]
    return {"total": total, "por_estado": por_estado, "valor": valor,
            "vencidas": vencidas, "por_vencer": por_vencer}


def obtener_historial(equipo_id=None, limite=500):
    sql, params = "SELECT * FROM historial", []
    if equipo_id:
        sql += " WHERE equipo_id = ?"
        params.append(equipo_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)
    with conexion() as con:
        return con.execute(sql, params).fetchall()


def registrar_mantenimiento(equipo_id, tipo, descripcion, tecnico="", costo=0.0,
                            estado="Completado", fecha=None):
    """
    Registra un mantenimiento. Si queda 'En proceso' el equipo pasa a
    'En Mantenimiento'; si se marca 'Completado' y el equipo estaba en
    mantenimiento, vuelve a 'Operativo'. Retorna (ok, mensaje).
    """
    if not descripcion.strip():
        return False, "La descripción es obligatoria."
    try:
        costo = float(str(costo).replace(",", ".") or 0)
    except ValueError:
        return False, "El costo debe ser un número."
    try:
        with conexion() as con:
            eq = con.execute("SELECT codigo_activo, estado FROM equipos WHERE id = ?",
                             (equipo_id,)).fetchone()
            if eq is None:
                return False, "El equipo no existe."
            con.execute(
                "INSERT INTO mantenimientos (equipo_id, fecha, tipo, descripcion, tecnico, costo, estado) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (equipo_id, fecha or date.today().isoformat(), tipo,
                 descripcion.strip(), tecnico.strip(), costo, estado))
            nuevo = None
            if estado == "En proceso" and eq["estado"] != "En Mantenimiento":
                nuevo = "En Mantenimiento"
            elif estado == "Completado" and eq["estado"] == "En Mantenimiento":
                nuevo = "Operativo"
            if nuevo:
                con.execute("UPDATE equipos SET estado = ?, fecha_actualizacion = "
                            "datetime('now','localtime') WHERE id = ?", (nuevo, equipo_id))
            _log(con, equipo_id, eq["codigo_activo"], "MANTENIMIENTO",
                 f"{tipo} ({estado}): {descripcion.strip()[:200]}"
                 + (f" → estado del equipo: {nuevo}" if nuevo else ""))
        return True, "Mantenimiento registrado."
    except sqlite3.Error as e:
        return False, f"Error de BD: {e}"


def obtener_mantenimientos(equipo_id=None, limite=500):
    sql = ("SELECT m.*, e.codigo_activo, e.nombre_equipo FROM mantenimientos m "
           "JOIN equipos e ON e.id = m.equipo_id")
    params = []
    if equipo_id:
        sql += " WHERE m.equipo_id = ?"
        params.append(equipo_id)
    sql += " ORDER BY m.fecha DESC, m.id DESC LIMIT ?"
    params.append(limite)
    with conexion() as con:
        return con.execute(sql, params).fetchall()


# ──────────────────────────── Datos de ejemplo (100 equipos) ────────────────────────────
# (tipo, prefijo, marca, modelo, costo_min, costo_max, perfil, peso)
CATALOGO = [
    ("Laptop", "LAP", "Dell", "Latitude 5420", 2900, 4300, "pc", 8),
    ("Laptop", "LAP", "HP", "ProBook 450 G8", 2600, 3800, "pc", 8),
    ("Laptop", "LAP", "Lenovo", "ThinkPad E14 Gen 3", 2700, 3900, "pc", 7),
    ("Laptop", "LAP", "ASUS", "VivoBook 15 X515", 1900, 2800, "pc", 4),
    ("Laptop", "LAP", "Acer", "Aspire 5 A515", 1800, 2600, "pc", 3),
    ("PC de Escritorio", "PC", "Dell", "OptiPlex 3080 SFF", 2400, 3400, "pc", 8),
    ("PC de Escritorio", "PC", "HP", "ProDesk 400 G7", 2300, 3300, "pc", 6),
    ("PC de Escritorio", "PC", "Lenovo", "ThinkCentre M70s", 2200, 3100, "pc", 5),
    ("Monitor", "MON", "Dell", "P2422H", 550, 800, "monitor", 8),
    ("Monitor", "MON", "LG", "24MK430H", 450, 650, "monitor", 5),
    ("Monitor", "MON", "Samsung", "S24R350", 480, 700, "monitor", 4),
    ("Impresora", "IMP", "HP", "LaserJet Pro M404dn", 1100, 1700, "impresora", 4),
    ("Impresora", "IMP", "Epson", "EcoTank L3250", 650, 950, "impresora", 3),
    ("Impresora", "IMP", "Brother", "HL-L2350DW", 600, 900, "impresora", 2),
    ("Servidor", "SRV", "Dell", "PowerEdge T150", 5500, 8500, "servidor", 2),
    ("Servidor", "SRV", "HP", "ProLiant ML30 Gen10", 5000, 7800, "servidor", 1),
    ("Switch", "SW", "TP-Link", "TL-SG1024D", 250, 420, "red", 2),
    ("Switch", "SW", "Cisco", "SG350-28", 1800, 2800, "red", 1),
    ("Router", "RT", "MikroTik", "hAP ac2", 260, 380, "red", 1),
    ("Access Point", "AP", "Ubiquiti", "UniFi U6-Lite", 380, 520, "red", 2),
    ("Tablet", "TAB", "Samsung", "Galaxy Tab A8", 750, 1100, "movil", 2),
    ("UPS", "UPS", "APC", "Back-UPS BX650", 220, 380, "ups", 3),
]
USUARIOS = [
    "Carlos Mendoza Quispe", "María Fernanda Torres", "Luis Alberto Ramos", "Ana Lucía Vargas",
    "José Antonio Flores", "Rosa Elena Castillo", "Miguel Ángel Rojas", "Carmen Rosa Huamán",
    "Jorge Luis Paredes", "Patricia Salazar Díaz", "Diego Alonso Chávez", "Lucía Valdivia Soto",
    "Pedro Pablo Gutiérrez", "Sofía Milagros Cruz", "Ricardo Núñez Bravo", "Gabriela Medina León",
    "Fernando Campos Vega", "Daniela Ortiz Ponce", "Héctor Rivera Sánchez", "Valeria Paz Delgado",
    "Andrés Felipe Lozano", "Karla Jiménez Arce", "Raúl Espinoza Cano", "Milagros Tello Ríos",
]
PROVEEDORES = ["Deltron S.A.", "Intcomex Perú", "Ingram Micro", "Hiraoka Corp.",
               "Tecnomega S.A.C.", "Compumarket Perú", "Sistemas Perú S.A.C."]
UBICACIONES = ["Sede Central - Piso 1", "Sede Central - Piso 2", "Sede Central - Piso 3",
               "Sede Central - Piso 4", "Sede Callao - Oficina", "Sede Arequipa"]
TECNICOS = ["Soporte TI", "Mesa de Ayuda", "Proveedor externo"]
CPUS = ["Intel Core i3-10110U", "Intel Core i5-1135G7", "Intel Core i5-10400",
        "Intel Core i7-1165G7", "AMD Ryzen 5 5500U", "AMD Ryzen 5 5600G"]
DISCOS = ["SSD 256 GB", "SSD 512 GB", "SSD 1 TB", "HDD 1 TB", "SSD NVMe 512 GB"]
SISTEMAS = ["Windows 10 Pro", "Windows 11 Pro", "Windows 11 Home", "Ubuntu 22.04 LTS"]
OBS = {
    "Operativo": ["", "Equipo en buen estado.", "Mantenimiento preventivo realizado.",
                  "Sin incidencias reportadas.", "Se recomienda cambio de pasta térmica.", ""],
    "En Mantenimiento": ["Falla reportada por el usuario, en diagnóstico.",
                         "Pendiente de repuesto.", "Ingresó por lentitud y reinicios."],
    "En Almacén": ["Disponible para reasignación.", "Equipo de reserva.", "Recién formateado."],
    "Dado de baja": ["Fuera de vida útil.", "Daño irreparable en placa.", "Pendiente de disposición final."],
}
DESC_CORRECTIVO = ["Cambio de disco por falla SMART", "Reemplazo de fuente de poder",
                   "Reparación de pantalla / bisagras", "Reinstalación de sistema operativo",
                   "Cambio de batería", "Limpieza y reemplazo de ventilador"]
ALFABETO = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
PERFILES_IP = {"pc", "servidor", "red", "impresora"}


def _specs(perfil, rng):
    """(procesador, ram_gb, almacenamiento, sistema_operativo) según el tipo de equipo."""
    if perfil == "pc":
        return (rng.choice(CPUS), rng.choice([4, 8, 8, 16, 16, 32]),
                rng.choice(DISCOS), rng.choice(SISTEMAS))
    if perfil == "servidor":
        return ("Intel Xeon E-2314", rng.choice([32, 64]), "2 × SSD 480 GB (RAID 1)",
                "Windows Server 2022")
    if perfil in ("red", "impresora"):
        return ("", 0, "", f"Firmware {rng.randint(1, 3)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}")
    if perfil == "movil":
        return ("Qualcomm Snapdragon 680", 4, "64 GB", "Android 13")
    return ("", 0, "", "")


def _sembrar(con, n=100, semilla=2026):
    """Genera n equipos de ejemplo (determinista: siempre los mismos datos)."""
    rng = random.Random(semilla)
    contadores, series, ips = {}, set(), set()
    hoy = date.today()
    inicio = date(2020, 1, 1)
    rango = (date(2025, 10, 31) - inicio).days
    pesos = [c[7] for c in CATALOGO]
    cols = ", ".join(CAMPOS)
    marcas_sql = ", ".join(f":{c}" for c in CAMPOS)

    for i in range(1, n + 1):
        tipo, pref, marca, modelo, cmin, cmax, perfil, _ = rng.choices(CATALOGO, weights=pesos)[0]
        contadores[pref] = contadores.get(pref, 0) + 1
        estado = rng.choices(ESTADOS, weights=[72, 12, 9, 7])[0]
        compra = inicio + timedelta(days=rng.randint(0, rango))
        garantia = compra + timedelta(days=365 * rng.choice([1, 2, 3]))

        while True:
            serie = marca[:2].upper() + "".join(rng.choices(ALFABETO, k=9))
            if serie not in series:
                series.add(serie)
                break

        ip = mac = ""
        if perfil in PERFILES_IP:
            while True:
                ip = f"192.168.{rng.choice([1, 10, 20])}.{rng.randint(10, 250)}"
                if ip not in ips:
                    ips.add(ip)
                    break
        if perfil in PERFILES_IP or perfil == "movil":
            mac = ":".join(f"{rng.randint(0, 255):02X}" for _ in range(6))

        cpu, ram, disco, so = _specs(perfil, rng)
        es_infra = perfil in ("servidor", "red", "ups")

        if estado == "En Almacén":
            usuario, depto, ubic = "Sin asignar", "TI", "Almacén de TI"
        elif estado == "Dado de baja":
            usuario, depto, ubic = "Sin asignar", "TI", "Depósito de bajas"
        elif es_infra:
            usuario, depto, ubic = "Administrador TI", "TI", "Sala de servidores"
        else:
            usuario, depto, ubic = (rng.choice(USUARIOS), rng.choice(DEPARTAMENTOS),
                                    rng.choice(UBICACIONES))

        d = {
            "codigo_activo": f"ACT-{i:04d}",
            "nombre_equipo": f"{pref}-{contadores[pref]:03d}",
            "tipo": tipo, "marca": marca, "modelo": modelo, "num_serie": serie,
            "procesador": cpu, "ram_gb": ram, "almacenamiento": disco, "sistema_operativo": so,
            "direccion_ip": ip, "direccion_mac": mac,
            "usuario_asignado": usuario, "departamento": depto, "ubicacion": ubic,
            "estado": estado, "fecha_compra": compra.isoformat(),
            "garantia_hasta": garantia.isoformat(),
            "costo": float(rng.randint(cmin, cmax)),
            "proveedor": rng.choice(PROVEEDORES),
            "observaciones": rng.choice(OBS[estado]),
            "imagen_path": "",
        }
        con.execute(f"INSERT INTO equipos ({cols}) VALUES ({marcas_sql})", d)

    # Auditoría inicial
    con.execute("INSERT INTO historial (equipo_id, codigo_activo, accion, detalle, usuario_sistema) "
                "SELECT id, codigo_activo, 'CREAR', 'Carga inicial de datos de ejemplo', 'sistema' "
                "FROM equipos")

    # Mantenimientos de ejemplo
    for f in con.execute("SELECT id, estado, fecha_compra FROM equipos").fetchall():
        if f["estado"] == "En Mantenimiento":
            fecha = (hoy - timedelta(days=rng.randint(1, 25))).isoformat()
            con.execute("INSERT INTO mantenimientos (equipo_id, fecha, tipo, descripcion, tecnico, costo, estado) "
                        "VALUES (?, ?, 'Correctivo', ?, ?, ?, 'En proceso')",
                        (f["id"], fecha, rng.choice(DESC_CORRECTIVO), rng.choice(TECNICOS),
                         float(rng.choice([0, 80, 120, 250]))))
        elif f["estado"] == "Operativo" and rng.random() < 0.3:
            fecha = max((hoy - timedelta(days=rng.randint(30, 300))).isoformat(), f["fecha_compra"])
            con.execute("INSERT INTO mantenimientos (equipo_id, fecha, tipo, descripcion, tecnico, costo, estado) "
                        "VALUES (?, ?, 'Preventivo', 'Limpieza interna, actualización de SO y revisión de discos', "
                        "?, ?, 'Completado')",
                        (f["id"], fecha, rng.choice(TECNICOS), float(rng.choice([0, 40, 60]))))