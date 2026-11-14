"""
========================================================================================
PERSISTENCIA SQLITE DEL MÓDULO EXTENSIÓN (CERO LIBRERÍAS)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Tablas NUEVAS e independientes: no se altera ninguna tabla del flujo de reservas.
Las operaciones críticas usan UNA conexión/transacción (ACID real).
Dependencias: NINGUNA (Python Standard Library `sqlite3`, `time`)
========================================================================================
"""
import sqlite3
from src.db import abrir_conexion
import time
from typing import Optional, List
from src.models_extra import (Entrenador, Horario, Suplemento, ConsumoSuplemento,
                              InsumoLimpieza, MovimientoInsumo, ElementoPrestable, Prestamo,
                              HorarioGimnasio)
from src.interfaces_extra import (IEntrenadorRepository, ISuplementoRepository,
                                  IInsumoRepository, IPrestamoRepository, IGimnasioInfoRepository)
from src.logger import get_logger

logger = get_logger("RepositoriesExtra")


class SQLiteEntrenadorRepository(IEntrenadorRepository):
    """Entrenadores y sus horarios semanales."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with abrir_conexion(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS entrenadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                especialidad TEXT NOT NULL,
                activo INTEGER DEFAULT 1)""")
            c.execute("""CREATE TABLE IF NOT EXISTS horarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entrenador_id INTEGER NOT NULL REFERENCES entrenadores(id),
                dia TEXT NOT NULL,
                hora_inicio TEXT NOT NULL,
                hora_fin TEXT NOT NULL,
                actividad TEXT NOT NULL)""")
            c.execute("SELECT COUNT(*) FROM entrenadores")
            if c.fetchone()[0] == 0:
                # Entrenadores reales. Sus franjas se agregan desde /gestion (mientras tanto
                # se muestran disponibles en el horario general del gimnasio).
                c.executemany("INSERT INTO entrenadores (id, nombre, especialidad) VALUES (?, ?, ?)", [
                    (1, "Luis Henrique", "Entrenador"),
                    (2, "Carlos Pasos", "Entrenador"),
                ])
                logger.info("Entrenadores sembrados (Luis Henrique, Carlos Pasos).")

    def listar_entrenadores(self) -> List[Entrenador]:
        with abrir_conexion(self.db_path) as conn:
            rows = conn.execute("SELECT id, nombre, especialidad, activo FROM entrenadores WHERE activo = 1 ORDER BY id").fetchall()
            return [Entrenador(r[0], r[1], r[2], bool(r[3])) for r in rows]

    def buscar_entrenador(self, id_entrenador: int) -> Optional[Entrenador]:
        with abrir_conexion(self.db_path) as conn:
            r = conn.execute("SELECT id, nombre, especialidad, activo FROM entrenadores WHERE id = ?", (id_entrenador,)).fetchone()
            return Entrenador(r[0], r[1], r[2], bool(r[3])) if r else None

    def agregar_entrenador(self, nombre: str, especialidad: str) -> Entrenador:
        with abrir_conexion(self.db_path) as conn:
            cur = conn.execute("INSERT INTO entrenadores (nombre, especialidad) VALUES (?, ?)", (nombre, especialidad))
            return Entrenador(cur.lastrowid, nombre, especialidad, True)

    def listar_horarios(self) -> List[Horario]:
        with abrir_conexion(self.db_path) as conn:
            rows = conn.execute("""SELECT h.id, h.entrenador_id, e.nombre, h.dia, h.hora_inicio, h.hora_fin, h.actividad
                                   FROM horarios h JOIN entrenadores e ON e.id = h.entrenador_id
                                   WHERE e.activo = 1""").fetchall()
            return [Horario(*r) for r in rows]

    def agregar_horario(self, entrenador_id: int, dia: str, hora_inicio: str, hora_fin: str, actividad: str) -> Horario:
        with abrir_conexion(self.db_path) as conn:
            cur = conn.execute("""INSERT INTO horarios (entrenador_id, dia, hora_inicio, hora_fin, actividad)
                                  VALUES (?, ?, ?, ?, ?)""", (entrenador_id, dia, hora_inicio, hora_fin, actividad))
            nombre = conn.execute("SELECT nombre FROM entrenadores WHERE id = ?", (entrenador_id,)).fetchone()[0]
            return Horario(cur.lastrowid, entrenador_id, nombre, dia, hora_inicio, hora_fin, actividad)


class SQLiteSuplementoRepository(ISuplementoRepository):
    """Catálogo de suplementos y registro de su consumo."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with abrir_conexion(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS suplementos (
                codigo TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                precio REAL NOT NULL,
                stock_disponible INTEGER NOT NULL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS consumos_suplemento (
                id_consumo TEXT PRIMARY KEY,
                socio_id TEXT NOT NULL,
                socio_nombre TEXT NOT NULL,
                suplemento_codigo TEXT NOT NULL REFERENCES suplementos(codigo),
                suplemento_nombre TEXT NOT NULL,
                cantidad INTEGER NOT NULL,
                precio_unitario REAL NOT NULL,
                total REAL NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                timestamp REAL NOT NULL)""")
            c.execute("SELECT COUNT(*) FROM suplementos")
            if c.fetchone()[0] == 0:
                # Precios reales (COP). El stock inicial es un valor de partida: se corrige
                # con el conteo físico desde /gestion ("Stock de suplementos").
                c.executemany("INSERT INTO suplementos VALUES (?, ?, ?, ?, ?)", [
                    ("SUP-001", "Pre entreno (1 scoop)", "Una porción", 1000.0, 50),
                    ("SUP-002", "Pre entreno (tarro 200 g)", "Tarro cerrado de 200 g", 80000.0, 3),
                    ("SUP-003", "Proteína en polvo (1 scoop)", "Una porción", 2500.0, 50),
                    ("SUP-004", "Proteína en polvo (paquete 2 lb)", "Paquete cerrado de 2 libras", 90000.0, 3),
                    ("SUP-005", "Creatina (1 scoop)", "Una porción", 3000.0, 50),
                    ("SUP-006", "Creatina (tarro 600 g)", "Tarro cerrado de 600 g", 150000.0, 3),
                    ("SUP-007", "Agua en botella", "Botella individual", 2000.0, 48),
                ])
                logger.info("Catálogo de suplementos sembrado (7 productos).")

    _COLS_CONSUMO = ("id_consumo, socio_id, socio_nombre, suplemento_codigo, suplemento_nombre, "
                     "cantidad, precio_unitario, total, idempotency_key, timestamp")

    def listar(self) -> List[Suplemento]:
        with abrir_conexion(self.db_path) as conn:
            rows = conn.execute("SELECT codigo, nombre, descripcion, precio, stock_disponible FROM suplementos ORDER BY codigo").fetchall()
            return [Suplemento(*r) for r in rows]

    def buscar_por_codigo(self, codigo: str) -> Optional[Suplemento]:
        with abrir_conexion(self.db_path) as conn:
            r = conn.execute("SELECT codigo, nombre, descripcion, precio, stock_disponible FROM suplementos WHERE codigo = ?", (codigo,)).fetchone()
            return Suplemento(*r) if r else None

    def registrar_consumo_atomico(self, consumo: ConsumoSuplemento) -> bool:
        # Una sola conexión: si falla el INSERT, el descuento de stock se revierte (rollback)
        with abrir_conexion(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE suplementos SET stock_disponible = stock_disponible - ? WHERE codigo = ? AND stock_disponible >= ?",
                (consumo.cantidad, consumo.suplemento_codigo, consumo.cantidad))
            if cur.rowcount == 0:
                return False
            conn.execute(f"INSERT INTO consumos_suplemento ({self._COLS_CONSUMO}) VALUES (?,?,?,?,?,?,?,?,?,?)", (
                consumo.id_consumo, consumo.socio_id, consumo.socio_nombre, consumo.suplemento_codigo,
                consumo.suplemento_nombre, consumo.cantidad, consumo.precio_unitario, consumo.total,
                consumo.idempotency_key, consumo.timestamp))
            return True

    def fijar_stock(self, codigo: str, nuevo_stock: int) -> bool:
        with abrir_conexion(self.db_path) as conn:
            cur = conn.execute("UPDATE suplementos SET stock_disponible = ? WHERE codigo = ?", (nuevo_stock, codigo))
            return cur.rowcount > 0

    def buscar_consumo_por_key(self, key: str) -> Optional[ConsumoSuplemento]:
        with abrir_conexion(self.db_path) as conn:
            r = conn.execute(f"SELECT {self._COLS_CONSUMO} FROM consumos_suplemento WHERE idempotency_key = ?", (key,)).fetchone()
            return ConsumoSuplemento(*r) if r else None

    def listar_consumos(self, socio_id: Optional[str] = None) -> List[ConsumoSuplemento]:
        with abrir_conexion(self.db_path) as conn:
            if socio_id:
                rows = conn.execute(f"SELECT {self._COLS_CONSUMO} FROM consumos_suplemento WHERE socio_id = ? ORDER BY timestamp DESC", (socio_id,)).fetchall()
            else:
                rows = conn.execute(f"SELECT {self._COLS_CONSUMO} FROM consumos_suplemento ORDER BY timestamp DESC").fetchall()
            return [ConsumoSuplemento(*r) for r in rows]


class SQLiteInsumoRepository(IInsumoRepository):
    """Inventario interno de insumos de limpieza y su bitácora de movimientos."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with abrir_conexion(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS insumos_limpieza (
                codigo TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                unidad TEXT NOT NULL,
                stock_actual INTEGER NOT NULL,
                stock_minimo INTEGER NOT NULL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS movimientos_insumo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                insumo_codigo TEXT NOT NULL REFERENCES insumos_limpieza(codigo),
                tipo TEXT NOT NULL,
                cantidad INTEGER NOT NULL,
                motivo TEXT NOT NULL,
                timestamp REAL NOT NULL)""")
            c.execute("SELECT COUNT(*) FROM insumos_limpieza")
            if c.fetchone()[0] == 0:
                # Insumos básicos de limpieza de un gimnasio. Cantidades de partida:
                # se ajustan con "Reposición" / "Uso" desde /gestion.
                c.executemany("INSERT INTO insumos_limpieza VALUES (?, ?, ?, ?, ?)", [
                    ("LIM-001", "Desinfectante multiusos", "litros", 10, 3),
                    ("LIM-002", "Toallas de papel", "rollos", 30, 10),
                    ("LIM-003", "Alcohol antiséptico", "litros", 8, 2),
                    ("LIM-004", "Bolsas de basura", "paquetes", 15, 5),
                    ("LIM-005", "Limpiador de colchonetas", "litros", 6, 2),
                    ("LIM-006", "Jabón líquido para manos", "litros", 5, 2),
                    ("LIM-007", "Escoba", "unidades", 3, 1),
                    ("LIM-008", "Trapero", "unidades", 3, 1),
                    ("LIM-009", "Limpiavidrios", "litros", 4, 1),
                    ("LIM-010", "Guantes de aseo", "pares", 6, 2),
                ])
                logger.info("Inventario de insumos de limpieza sembrado (10 insumos).")

    def listar(self) -> List[InsumoLimpieza]:
        with abrir_conexion(self.db_path) as conn:
            rows = conn.execute("SELECT codigo, nombre, unidad, stock_actual, stock_minimo FROM insumos_limpieza ORDER BY codigo").fetchall()
            return [InsumoLimpieza(*r) for r in rows]

    def buscar_por_codigo(self, codigo: str) -> Optional[InsumoLimpieza]:
        with abrir_conexion(self.db_path) as conn:
            r = conn.execute("SELECT codigo, nombre, unidad, stock_actual, stock_minimo FROM insumos_limpieza WHERE codigo = ?", (codigo,)).fetchone()
            return InsumoLimpieza(*r) if r else None

    def aplicar_movimiento_atomico(self, codigo: str, tipo: str, cantidad: int, motivo: str) -> bool:
        delta = -cantidad if tipo == "USO" else cantidad
        with abrir_conexion(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE insumos_limpieza SET stock_actual = stock_actual + ? WHERE codigo = ? AND stock_actual + ? >= 0",
                (delta, codigo, delta))
            if cur.rowcount == 0:
                return False
            conn.execute("INSERT INTO movimientos_insumo (insumo_codigo, tipo, cantidad, motivo, timestamp) VALUES (?,?,?,?,?)",
                         (codigo, tipo, cantidad, motivo, time.time()))
            return True

    def listar_movimientos(self, limite: int = 30) -> List[MovimientoInsumo]:
        with abrir_conexion(self.db_path) as conn:
            rows = conn.execute("""SELECT id, insumo_codigo, tipo, cantidad, motivo, timestamp
                                   FROM movimientos_insumo ORDER BY id DESC LIMIT ?""", (limite,)).fetchall()
            return [MovimientoInsumo(*r) for r in rows]


class SQLitePrestamoRepository(IPrestamoRepository):
    """Elementos prestables a los socios y sus préstamos."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with abrir_conexion(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS elementos_prestables (
                codigo TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                cantidad_total INTEGER NOT NULL,
                cantidad_disponible INTEGER NOT NULL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS prestamos (
                id_prestamo TEXT PRIMARY KEY,
                socio_id TEXT NOT NULL,
                socio_nombre TEXT NOT NULL,
                elemento_codigo TEXT NOT NULL REFERENCES elementos_prestables(codigo),
                elemento_nombre TEXT NOT NULL,
                cantidad INTEGER NOT NULL,
                estado TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                fecha_prestamo REAL NOT NULL,
                fecha_devolucion REAL)""")
            c.execute("SELECT COUNT(*) FROM elementos_prestables")
            if c.fetchone()[0] == 0:
                # Objetos reales del gimnasio (cantidad total = cantidad disponible al inicio)
                c.executemany("INSERT INTO elementos_prestables VALUES (?, ?, ?, ?)", [
                    ("ELE-001", "Colchoneta", 5, 5),
                    ("ELE-002", "Apoyo (cojín) para barra", 3, 3),
                    ("ELE-003", "Ligas", 4, 4),
                    ("ELE-004", "Seguros", 8, 8),
                    ("ELE-005", "Cinturones", 4, 4),
                    ("ELE-006", "Rodilleras", 3, 3),
                ])
                logger.info("Elementos prestables sembrados (6 tipos).")

    _COLS_PRESTAMO = ("id_prestamo, socio_id, socio_nombre, elemento_codigo, elemento_nombre, cantidad, "
                      "estado, idempotency_key, fecha_prestamo, fecha_devolucion")

    def listar_elementos(self) -> List[ElementoPrestable]:
        with abrir_conexion(self.db_path) as conn:
            rows = conn.execute("SELECT codigo, nombre, cantidad_total, cantidad_disponible FROM elementos_prestables ORDER BY codigo").fetchall()
            return [ElementoPrestable(*r) for r in rows]

    def buscar_elemento(self, codigo: str) -> Optional[ElementoPrestable]:
        with abrir_conexion(self.db_path) as conn:
            r = conn.execute("SELECT codigo, nombre, cantidad_total, cantidad_disponible FROM elementos_prestables WHERE codigo = ?", (codigo,)).fetchone()
            return ElementoPrestable(*r) if r else None

    def registrar_prestamo_atomico(self, p: Prestamo) -> bool:
        with abrir_conexion(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE elementos_prestables SET cantidad_disponible = cantidad_disponible - ? WHERE codigo = ? AND cantidad_disponible >= ?",
                (p.cantidad, p.elemento_codigo, p.cantidad))
            if cur.rowcount == 0:
                return False
            conn.execute(f"INSERT INTO prestamos ({self._COLS_PRESTAMO}) VALUES (?,?,?,?,?,?,?,?,?,?)", (
                p.id_prestamo, p.socio_id, p.socio_nombre, p.elemento_codigo, p.elemento_nombre,
                p.cantidad, p.estado, p.idempotency_key, p.fecha_prestamo, p.fecha_devolucion))
            return True

    def devolver_atomico(self, id_prestamo: str, fecha: float) -> bool:
        with abrir_conexion(self.db_path) as conn:
            r = conn.execute("SELECT elemento_codigo, cantidad FROM prestamos WHERE id_prestamo = ? AND estado = 'PRESTADO'", (id_prestamo,)).fetchone()
            if not r:
                return False
            conn.execute("UPDATE prestamos SET estado = 'DEVUELTO', fecha_devolucion = ? WHERE id_prestamo = ?", (fecha, id_prestamo))
            conn.execute("UPDATE elementos_prestables SET cantidad_disponible = cantidad_disponible + ? WHERE codigo = ?", (r[1], r[0]))
            return True

    def buscar_prestamo(self, id_prestamo: str) -> Optional[Prestamo]:
        with abrir_conexion(self.db_path) as conn:
            r = conn.execute(f"SELECT {self._COLS_PRESTAMO} FROM prestamos WHERE id_prestamo = ?", (id_prestamo,)).fetchone()
            return Prestamo(*r) if r else None

    def buscar_prestamo_por_key(self, key: str) -> Optional[Prestamo]:
        with abrir_conexion(self.db_path) as conn:
            r = conn.execute(f"SELECT {self._COLS_PRESTAMO} FROM prestamos WHERE idempotency_key = ?", (key,)).fetchone()
            return Prestamo(*r) if r else None

    def listar_prestamos(self, socio_id: Optional[str] = None, solo_activos: bool = False) -> List[Prestamo]:
        condiciones, params = [], []
        if socio_id:
            condiciones.append("socio_id = ?"); params.append(socio_id)
        if solo_activos:
            condiciones.append("estado = 'PRESTADO'")
        where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
        with abrir_conexion(self.db_path) as conn:
            rows = conn.execute(f"SELECT {self._COLS_PRESTAMO} FROM prestamos {where} ORDER BY fecha_prestamo DESC", params).fetchall()
            return [Prestamo(*r) for r in rows]


class SQLiteGimnasioInfoRepository(IGimnasioInfoRepository):
    """Horario de atención y datos generales del gimnasio."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with abrir_conexion(self.db_path) as conn:
            c = conn.cursor()
            c.execute("""CREATE TABLE IF NOT EXISTS horario_gimnasio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dia TEXT NOT NULL,
                hora_inicio TEXT NOT NULL,
                hora_fin TEXT NOT NULL)""")
            c.execute("""CREATE TABLE IF NOT EXISTS gimnasio_info (
                clave TEXT PRIMARY KEY,
                valor TEXT NOT NULL)""")
            c.execute("SELECT COUNT(*) FROM horario_gimnasio")
            if c.fetchone()[0] == 0:
                franjas = []
                for dia in ("LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"):
                    franjas.append((dia, "05:00", "13:00"))
                    franjas.append((dia, "14:00", "21:30"))
                c.executemany("INSERT INTO horario_gimnasio (dia, hora_inicio, hora_fin) VALUES (?, ?, ?)", franjas)
                c.executemany("INSERT OR IGNORE INTO gimnasio_info (clave, valor) VALUES (?, ?)", [
                    ("jefe", "Roman Tercero"),
                    ("festivos", "Medio día"),
                    ("domingos", "Cerrado"),
                ])
                logger.info("Horario del gimnasio sembrado (lunes a sábado, dos franjas).")

    def listar_horarios(self) -> List[HorarioGimnasio]:
        with abrir_conexion(self.db_path) as conn:
            rows = conn.execute("SELECT id, dia, hora_inicio, hora_fin FROM horario_gimnasio ORDER BY id").fetchall()
            return [HorarioGimnasio(*r) for r in rows]

    def obtener_info(self) -> dict:
        with abrir_conexion(self.db_path) as conn:
            return {k: v for k, v in conn.execute("SELECT clave, valor FROM gimnasio_info").fetchall()}
