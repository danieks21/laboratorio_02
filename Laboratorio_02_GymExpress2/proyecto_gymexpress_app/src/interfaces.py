"""
========================================================================================
INTERFACES Y ABSTRACCIONES (DIP - DEPENDENCY INVERSION PRINCIPLE)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Garantiza el desacoplamiento entre Lógica de Negocio y Persistencia / IO
========================================================================================
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from src.models import Servicio, Reserva


class IServicioRepository(ABC):
    """Contrato abstracto para la persistencia del catálogo de servicios del gimnasio."""

    @abstractmethod
    def obtener_todos(self) -> List[Servicio]:
        """Recupera la totalidad de los servicios ofrecidos."""
        pass

    @abstractmethod
    def buscar_por_codigo(self, codigo: str) -> Optional[Servicio]:
        """Obtiene un servicio específico por su código único."""
        pass

    @abstractmethod
    def actualizar_cupos(self, codigo: str, nuevos_cupos: int) -> bool:
        """Actualiza los cupos disponibles del servicio."""
        pass

    @abstractmethod
    def descontar_cupos(self, codigo: str, cantidad: int) -> bool:
        """Descuento ATÓMICO y condicional (cupos >= cantidad). False si no hay cupos suficientes."""
        pass

    @abstractmethod
    def reponer_cupos(self, codigo: str, cantidad: int) -> bool:
        """Devolución ATÓMICA de cupos (compensación). False si el servicio no existe."""
        pass


class IReservaRepository(ABC):
    """Contrato abstracto para la persistencia del agregado Reserva."""

    @abstractmethod
    def guardar(self, reserva: Reserva) -> bool:
        """Inserta o actualiza una reserva en el medio de almacenamiento."""
        pass

    @abstractmethod
    def buscar_por_id(self, id_reserva: str) -> Optional[Reserva]:
        """Busca una reserva por su identificador primario."""
        pass

    @abstractmethod
    def buscar_por_idempotency_key(self, key: str) -> Optional[Reserva]:
        """Permite deduplicar peticiones mediante la clave de idempotencia."""
        pass

    @abstractmethod
    def listar_todos(self) -> List[Reserva]:
        """Lista la totalidad de reservas para reportería y auditoría."""
        pass

    @abstractmethod
    def actualizar_estado(self, id_reserva: str, nuevo_estado: str, motivo: str) -> bool:
        """Actualiza el estado de la reserva y su bitácora."""
        pass


class IOutboxRepository(ABC):
    """
    Contrato abstracto para el Transactional Outbox Pattern (Garantía Dual-Write).
    Permite publicar eventos en un broker sin riesgo de inconsistencia distribuida.
    """

    @abstractmethod
    def registrar_evento(self, aggregate_id: str, event_type: str, payload_json: str) -> bool:
        """Inserta un evento en la tabla de Outbox."""
        pass

    @abstractmethod
    def obtener_pendientes(self) -> List[Dict[str, Any]]:
        """Recupera eventos que aún no han sido enviados al broker."""
        pass

    @abstractmethod
    def marcar_publicado(self, event_id: str) -> bool:
        """Marca el evento como despachado exitosamente."""
        pass


class IPasarelaPagos(ABC):
    """
    Contrato abstracto para la integración con pasarelas de pago externas.
    Desacopla el servicio de la implementación concreta (PSE, Wompi, etc.).
    """

    @abstractmethod
    def procesar_cobro(self, id_reserva: str, monto: float, idempotency_key: str, simular_falla: bool = False) -> bool:
        """Debita el monto solicitado retornando True si es exitoso o False si es rechazado."""
        pass

    @abstractmethod
    def reembolsar(self, id_reserva: str, monto: float) -> bool:
        """Ejecuta la compensación financiera si se requiere devolver los fondos."""
        pass


class ICatalogoPort(ABC):
    """
    Puerto del contexto de CATÁLOGO (subdominio de soporte) que consume el contexto de RESERVAS (núcleo).
    Hoy lo implementa un adaptador en el mismo proceso; mañana podría ser un cliente HTTP a un
    microservicio sin cambiar una sola línea del contexto de Reservas.
    """

    @abstractmethod
    def listar(self) -> List[Servicio]:
        """Catálogo completo con precios y cupos."""
        pass

    @abstractmethod
    def consultar(self, codigo: str) -> Optional[Servicio]:
        """Servicio por código (precio vigente y cupos)."""
        pass

    @abstractmethod
    def reservar_cupos(self, codigo: str, cantidad: int) -> bool:
        """Bloquea cupos de forma atómica. False si no hay suficientes."""
        pass

    @abstractmethod
    def liberar_cupos(self, codigo: str, cantidad: int) -> None:
        """Devuelve cupos (compensación de la Saga)."""
        pass
