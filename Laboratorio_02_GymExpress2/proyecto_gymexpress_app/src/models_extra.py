"""
========================================================================================
ENTIDADES DEL MÓDULO EXTENSIÓN: ENTRENADORES, SUPLEMENTOS, INSUMOS DE LIMPIEZA, PRÉSTAMOS
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Complementa a `models.py` sin modificarlo (Open/Closed Principle).
Dependencias: NINGUNA (Python Standard Library `dataclasses`, `typing`)
========================================================================================
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Entrenador:
    """Entrenador del gimnasio."""
    id: int
    nombre: str
    especialidad: str
    activo: bool = True


@dataclass
class Horario:
    """Franja semanal en la que un entrenador atiende una actividad."""
    id: int
    entrenador_id: int
    entrenador_nombre: str
    dia: str
    hora_inicio: str
    hora_fin: str
    actividad: str


@dataclass
class Suplemento:
    """Suplemento que se vende por porción en recepción."""
    codigo: str
    nombre: str
    descripcion: str
    precio: float
    stock_disponible: int


@dataclass
class ConsumoSuplemento:
    """Registro de consumo (compra) de un suplemento por un socio."""
    id_consumo: str
    socio_id: str
    socio_nombre: str
    suplemento_codigo: str
    suplemento_nombre: str
    cantidad: int
    precio_unitario: float
    total: float
    idempotency_key: str
    timestamp: float


@dataclass
class InsumoLimpieza:
    """Insumo de limpieza del inventario interno (uso exclusivo del personal)."""
    codigo: str
    nombre: str
    unidad: str
    stock_actual: int
    stock_minimo: int

    @property
    def bajo_minimo(self) -> bool:
        """True cuando el stock llegó o cayó por debajo del mínimo recomendado."""
        return self.stock_actual <= self.stock_minimo


@dataclass
class MovimientoInsumo:
    """Bitácora de uso o reposición de un insumo de limpieza."""
    id: int
    insumo_codigo: str
    tipo: str            # USO | REPOSICION
    cantidad: int
    motivo: str
    timestamp: float


@dataclass
class ElementoPrestable:
    """Elemento que el socio puede usar durante su visita (toalla, candado, guantes...)."""
    codigo: str
    nombre: str
    cantidad_total: int
    cantidad_disponible: int


@dataclass
class Prestamo:
    """Préstamo de un elemento a un socio; se cierra al devolverlo."""
    id_prestamo: str
    socio_id: str
    socio_nombre: str
    elemento_codigo: str
    elemento_nombre: str
    cantidad: int
    estado: str          # PRESTADO | DEVUELTO
    idempotency_key: str
    fecha_prestamo: float
    fecha_devolucion: Optional[float] = None


@dataclass
class HorarioGimnasio:
    """Franja de atención del gimnasio (puede haber varias por día, p. ej. con pausa al mediodía)."""
    id: int
    dia: str
    hora_inicio: str
    hora_fin: str
