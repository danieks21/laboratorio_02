"""
========================================================================================
DOMINIO Y ENTIDADES DE NEGOCIO: GYMEXPRESS
Cátedra: Ingeniería de Software 3 [IF0129] - Corporación Universitaria Remington
Buenas Prácticas: Single Responsibility (SRP), Tipado Fuerte, Encapsulamiento, SoD
Dependencias: NINGUNA (Python Standard Library `dataclasses`, `enum`, `time`, `uuid`)
========================================================================================
"""
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
from typing import List, Dict, Any


class EstadoReserva(Enum):
    """
    Máquina de Estados de una Reserva en la Arquitectura Distribuida:
    - PENDIENTE: Solicitud recibida en el Controlador web.
    - CUPO_RESERVADO_SEMANTIC_LOCK: Cupo bloqueado en la base de datos local (Paso T1 de la Saga).
    - PAGADO: Cobro debitado satisfactoriamente en la pasarela (Paso T2).
    - FACTURADO: Factura emitida según normativa tributaria.
    - COMPLETADO: Saga completada con éxito (reserva confirmada).
    - CANCELADO: Reserva rechazada antes de procesarse.
    - COMPENSADO: Reversión exitosa tras una falla en la Saga (Compensación C1).
    """
    PENDIENTE = "PENDIENTE"
    CUPO_RESERVADO_SEMANTIC_LOCK = "CUPO_RESERVADO_SEMANTIC_LOCK"
    PAGADO = "PAGADO"
    FACTURADO = "FACTURADO"
    COMPLETADO = "COMPLETADO"
    CANCELADO = "CANCELADO"
    COMPENSADO = "COMPENSADO"


class TipoPago(Enum):
    """Métodos de pago soportados por la pasarela de pagos."""
    TARJETA_CREDITO = "TARJETA_CREDITO"
    TRANSFERENCIA_PSE = "TRANSFERENCIA_PSE"
    EFECTIVO_RECEPCION = "EFECTIVO_RECEPCION"


class TipoServicio(Enum):
    """Categorías de servicios que ofrece el gimnasio."""
    MEMBRESIA = "MEMBRESIA"
    CLASE_GRUPAL = "CLASE_GRUPAL"
    ENTRENAMIENTO_PERSONAL = "ENTRENAMIENTO_PERSONAL"


@dataclass
class Servicio:
    """
    Entidad de Negocio: Servicio del catálogo del gimnasio
    (membresía, clase grupal o sesión de entrenamiento personalizado).
    `cupos_disponibles` cumple el rol del stock de FarmaExpress: es el recurso
    limitado que no se puede sobrevender.
    """
    codigo: str
    nombre: str
    descripcion: str
    tipo: str
    precio: float
    cupos_disponibles: int
    requiere_valoracion: bool = False

    def tiene_cupo(self, cantidad: int) -> bool:
        """Verifica disponibilidad sin mutar estado."""
        return self.cupos_disponibles >= cantidad


@dataclass
class ItemReserva:
    """
    Objeto de Valor (Value Object): Representa un renglón de la reserva.
    Inmutable conceptualmente en el contexto de la reserva.
    """
    servicio_codigo: str
    cantidad: int
    precio_unitario: float

    @property
    def subtotal(self) -> float:
        """Calcula el valor parcial del renglón (precio * cantidad)."""
        return round(self.cantidad * self.precio_unitario, 2)


@dataclass
class Reserva:
    """
    Entidad Raíz del Agregado (Aggregate Root): Reserva
    Encapsula los ítems, el cálculo de totales, la clave de idempotencia
    y la trazabilidad auditable de todas las transiciones de estado.
    """
    id_reserva: str
    socio_id: str
    socio_nombre: str
    socio_contacto: str
    items: List[ItemReserva]
    estado: EstadoReserva = EstadoReserva.PENDIENTE
    total: float = 0.0
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    historial_estados: List[Dict[str, Any]] = field(default_factory=list)

    def calcular_total(self) -> float:
        """Recalcula y asigna la suma de subtotales de todos los ítems."""
        self.total = round(sum(item.subtotal for item in self.items), 2)
        return self.total

    def transicionar_a(self, nuevo_estado: EstadoReserva, motivo: str = ""):
        """
        Cambia el estado del agregado registrando la estampa de tiempo
        y el motivo para garantizar auditoría forense (Trazabilidad SoD).
        """
        self.estado = nuevo_estado
        self.historial_estados.append({
            "estado": nuevo_estado.value,
            "motivo": motivo,
            "timestamp": time.time(),
            "hora_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        })
