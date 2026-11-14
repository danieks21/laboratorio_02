"""
========================================================================================
CAPA DE ACCESO A DATOS (PERSISTENCIA ACID CON SQLITE NATIVO - CERO LIBRERÍAS)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Garantías: ACID (Atomicidad, Consistencia, Aislamiento, Durabilidad)
Patrón: Repository, Transactional Outbox Pattern
Dependencias: NINGUNA (Python Standard Library `sqlite3`, `json`, `time`, `typing`)
========================================================================================
"""
import sqlite3
from src.db import abrir_conexion
import json
import time
from typing import Optional, List, Dict, Any
from src.models import Servicio, Reserva, ItemReserva, EstadoReserva
from src.interfaces import IServicioRepository, IReservaRepository, IOutboxRepository
from src.logger import get_logger

logger = get_logger("Repositories")

_COLUMNAS_SERVICIO = "codigo, nombre, descripcion, tipo, precio, cupos_disponibles, requiere_valoracion"
_COLUMNAS_RESERVA = ("id_reserva, socio_id, socio_nombre, socio_contacto, estado, total, "
                     "idempotency_key, timestamp, items_json, historial_json")


class SQLiteServicioRepository(IServicioRepository):
    """
    Repositorio del Catálogo de Servicios del gimnasio.
    Maneja los cupos disponibles de membresías, clases y entrenamientos.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Inicializa la tabla y catálogo semilla con aislamiento WAL para concurrencia."""
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS servicios (
                    codigo TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    descripcion TEXT,
                    tipo TEXT,
                    precio REAL NOT NULL,
                    cupos_disponibles INTEGER NOT NULL,
                    requiere_valoracion INTEGER DEFAULT 0
                )
            """)
            conn.commit()
            self._seed_data(cursor, conn)

    def _seed_data(self, cursor: sqlite3.Cursor, conn: sqlite3.Connection):
        """Poblar datos iniciales canónicos si la tabla está vacía."""
        cursor.execute("SELECT COUNT(*) FROM servicios")
        if cursor.fetchone()[0] == 0:
            catalogo_inicial = [
                ("GYM-001", "Membresía Mensual", "Acceso libre a sala de máquinas por 30 días", "MEMBRESIA", 80000.0, 200, 0),
                ("GYM-002", "Membresía Trimestral", "Acceso libre a sala de máquinas por 90 días", "MEMBRESIA", 210000.0, 100, 0),
                ("GYM-003", "Spinning 6:00 pm", "Clase grupal de ciclismo indoor (60 min)", "CLASE_GRUPAL", 15000.0, 20, 0),
                ("GYM-004", "Funcional 7:00 am", "Clase grupal de entrenamiento funcional (60 min)", "CLASE_GRUPAL", 15000.0, 15, 0),
                ("GYM-005", "Entrenamiento Personalizado", "Sesión 1 a 1 con entrenador (requiere valoración)", "ENTRENAMIENTO_PERSONAL", 45000.0, 10, 1),
            ]
            cursor.executemany(f"""
                INSERT INTO servicios ({_COLUMNAS_SERVICIO})
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, catalogo_inicial)
            conn.commit()
            logger.info("Catálogo inicial sembrado con éxito (5 servicios de prueba).")

    @staticmethod
    def _fila_a_servicio(r) -> Servicio:
        return Servicio(r[0], r[1], r[2], r[3], r[4], r[5], bool(r[6]))

    def obtener_todos(self) -> List[Servicio]:
        """Consulta todos los servicios del catálogo."""
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {_COLUMNAS_SERVICIO} FROM servicios")
            return [self._fila_a_servicio(r) for r in cursor.fetchall()]

    def buscar_por_codigo(self, codigo: str) -> Optional[Servicio]:
        """Búsqueda por clave primaria (código del servicio)."""
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {_COLUMNAS_SERVICIO} FROM servicios WHERE codigo = ?", (codigo,))
            r = cursor.fetchone()
            return self._fila_a_servicio(r) if r else None

    def actualizar_cupos(self, codigo: str, nuevos_cupos: int) -> bool:
        """Actualiza los cupos de forma atómica."""
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE servicios SET cupos_disponibles = ? WHERE codigo = ?", (nuevos_cupos, codigo))
            conn.commit()
            return cursor.rowcount > 0

    def descontar_cupos(self, codigo: str, cantidad: int) -> bool:
        """UPDATE condicional: evita la sobreventa aunque varios hilos reserven a la vez."""
        with abrir_conexion(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE servicios SET cupos_disponibles = cupos_disponibles - ? WHERE codigo = ? AND cupos_disponibles >= ?",
                (cantidad, codigo, cantidad))
            return cur.rowcount > 0

    def reponer_cupos(self, codigo: str, cantidad: int) -> bool:
        with abrir_conexion(self.db_path) as conn:
            cur = conn.execute("UPDATE servicios SET cupos_disponibles = cupos_disponibles + ? WHERE codigo = ?",
                               (cantidad, codigo))
            return cur.rowcount > 0


class SQLiteReservaRepository(IReservaRepository):
    """
    Repositorio de Reservas con persistencia de agregados completos en JSON.
    Garantiza durabilidad e integridad de la clave de idempotencia única.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reservas (
                    id_reserva TEXT PRIMARY KEY,
                    socio_id TEXT NOT NULL,
                    socio_nombre TEXT NOT NULL,
                    socio_contacto TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    total REAL NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    timestamp REAL NOT NULL,
                    items_json TEXT NOT NULL,
                    historial_json TEXT NOT NULL
                )
            """)
            conn.commit()

    @staticmethod
    def _fila_a_reserva(r) -> Reserva:
        """Reconstruye el agregado Reserva desde una fila (evita repetir código en cada consulta)."""
        items = [ItemReserva(it["codigo"], it["cantidad"], it["precio"]) for it in json.loads(r[8])]
        return Reserva(
            id_reserva=r[0], socio_id=r[1], socio_nombre=r[2], socio_contacto=r[3],
            items=items, estado=EstadoReserva(r[4]), total=r[5], idempotency_key=r[6],
            timestamp=r[7], historial_estados=json.loads(r[9])
        )

    def guardar(self, reserva: Reserva) -> bool:
        """Guarda o actualiza la reserva en la base de datos."""
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            items_data = [{"codigo": it.servicio_codigo, "cantidad": it.cantidad, "precio": it.precio_unitario} for it in reserva.items]
            cursor.execute(f"""
                INSERT OR REPLACE INTO reservas ({_COLUMNAS_RESERVA})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reserva.id_reserva,
                reserva.socio_id,
                reserva.socio_nombre,
                reserva.socio_contacto,
                reserva.estado.value,
                reserva.total,
                reserva.idempotency_key,
                reserva.timestamp,
                json.dumps(items_data),
                json.dumps(reserva.historial_estados)
            ))
            conn.commit()
            return True

    def buscar_por_id(self, id_reserva: str) -> Optional[Reserva]:
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {_COLUMNAS_RESERVA} FROM reservas WHERE id_reserva = ?", (id_reserva,))
            r = cursor.fetchone()
            return self._fila_a_reserva(r) if r else None

    def buscar_por_idempotency_key(self, key: str) -> Optional[Reserva]:
        """Consulta deduplicadora para evitar reprocesamiento accidental."""
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {_COLUMNAS_RESERVA} FROM reservas WHERE idempotency_key = ?", (key,))
            r = cursor.fetchone()
            return self._fila_a_reserva(r) if r else None

    def listar_todos(self) -> List[Reserva]:
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {_COLUMNAS_RESERVA} FROM reservas ORDER BY timestamp DESC")
            return [self._fila_a_reserva(r) for r in cursor.fetchall()]

    def actualizar_estado(self, id_reserva: str, nuevo_estado: str, motivo: str) -> bool:
        reserva = self.buscar_por_id(id_reserva)
        if not reserva:
            return False
        reserva.transicionar_a(EstadoReserva(nuevo_estado), motivo)
        return self.guardar(reserva)


class SQLiteOutboxRepository(IOutboxRepository):
    """
    Implementación del Transactional Outbox Pattern en SQLite.
    Garantiza que ningún evento de dominio se pierda o desincronice
    en arquitecturas orientadas a eventos (Dual-Write Prevention).
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS outbox_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    aggregate_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    published INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def registrar_evento(self, aggregate_id: str, event_type: str, payload_json: str) -> bool:
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO outbox_events (aggregate_id, event_type, payload_json, timestamp, published)
                VALUES (?, ?, ?, ?, 0)
            """, (aggregate_id, event_type, payload_json, time.time()))
            conn.commit()
            return True

    def obtener_pendientes(self) -> List[Dict[str, Any]]:
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, aggregate_id, event_type, payload_json, timestamp, published
                FROM outbox_events WHERE published = 0 ORDER BY id ASC
            """)
            return [{
                "id": r[0],
                "aggregate_id": r[1],
                "event_type": r[2],
                "payload": json.loads(r[3]),
                "timestamp": r[4],
                "published": bool(r[5])
            } for r in cursor.fetchall()]

    def marcar_publicado(self, event_id: str) -> bool:
        with abrir_conexion(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE outbox_events SET published = 1 WHERE id = ?", (event_id,))
            conn.commit()
            return cursor.rowcount > 0
