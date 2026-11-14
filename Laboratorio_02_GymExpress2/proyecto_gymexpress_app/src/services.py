"""
========================================================================================
CAPA DE SERVICIOS Y LÓGICA DE NEGOCIO (SRP, SAGA, IDEMPOTENCIA, COMPENSACIÓN INVERSA)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Patrón: Saga Pattern (Orchestrator), Idempotent Receiver, Fail-Fast con Validaciones
Buenas Prácticas: SoD, Inyección de Dependencias (DIP), Logging Estructurado
Dependencias: NINGUNA (Python Standard Library `time`, `json`, `typing`)
========================================================================================
"""
from typing import Optional

from src.models import Reserva, EstadoReserva
from src.interfaces import IServicioRepository, IReservaRepository, IOutboxRepository, IPasarelaPagos
from src.events import IEventPublisher, PublicadorNulo
from src.contexto_catalogo import CatalogoService
from src.contexto_reservas import ReservasService
from src.validators import Validator, ValidationError
from src.logger import get_logger

logger = get_logger("Services")


class GimnasioService:
    """
    Fachada de aplicación (Sesión 2): compone los dos Bounded Contexts.
      - Catálogo (soporte): CatalogoService, detrás del puerto ICatalogoPort.
      - Reservas (núcleo): ReservasService, que solo conoce el puerto.
    Conserva la firma pública original (OCP): el cuarto parámetro es opcional.
    """
    def __init__(self,
                 servicio_repo: IServicioRepository,
                 reserva_repo: IReservaRepository,
                 outbox_repo: IOutboxRepository,
                 event_publisher: Optional[IEventPublisher] = None):
        self.servicio_repo = servicio_repo
        self.reserva_repo = reserva_repo
        self.outbox_repo = outbox_repo
        self.event_publisher = event_publisher or PublicadorNulo()
        self.catalogo = CatalogoService(servicio_repo, self.event_publisher)
        self.reservas = ReservasService(self.catalogo, reserva_repo, outbox_repo, self.event_publisher)

    def listar_catalogo(self):
        """Consulta el catálogo completo de servicios del gimnasio."""
        return self.catalogo.listar()

    def crear_reserva(self, socio_id: str, socio_nombre: str, contacto: str,
                      items_req: list, idempotency_key: str) -> Reserva:
        return self.reservas.crear_reserva(socio_id, socio_nombre, contacto, items_req, idempotency_key)

    # Nombre histórico del monolito, conservado para no romper a los llamadores existentes
    crear_reserva_monolito = crear_reserva

    def registrar_pago(self, reserva: Reserva) -> Reserva:
        return self.reservas.registrar_pago(reserva)

    def confirmar_reserva(self, reserva: Reserva) -> Reserva:
        return self.reservas.confirmar(reserva)

    def compensar_reserva(self, reserva: Reserva, motivo: str) -> Reserva:
        return self.reservas.compensar(reserva, motivo)


class PasarelaPagosMock(IPasarelaPagos):
    """
    Simulador de Pasarela Financiera Externa (Mock).
    Soporta idempotencia en cobros y simulación deliberada de fallos para probar la Saga.
    """
    def __init__(self):
        self.cobros_procesados = {}

    def procesar_cobro(self, id_reserva: str, monto: float, idempotency_key: str, simular_falla: bool = False) -> bool:
        Validator.validar_monto(monto, "monto_cobro")

        if idempotency_key in self.cobros_procesados:
            logger.info(f"[Pasarela] Cobro idempotente ya registrado para key={idempotency_key}")
            return self.cobros_procesados[idempotency_key]["exito"]

        if simular_falla:
            logger.warning(f"❌ [Pasarela] Cobro RECHAZADO deliberadamente para reserva {id_reserva} (${monto:,.2f})")
            self.cobros_procesados[idempotency_key] = {"exito": False, "monto": monto, "motivo": "Fondos insuficientes"}
            return False

        logger.info(f"💳 [Pasarela] Cobro APROBADO para reserva {id_reserva} (${monto:,.2f})")
        self.cobros_procesados[idempotency_key] = {"exito": True, "monto": monto, "motivo": "Aprobado"}
        return True

    def reembolsar(self, id_reserva: str, monto: float) -> bool:
        logger.info(f"↩️ [Pasarela] Reembolso procesado para reserva {id_reserva} por ${monto:,.2f}")
        return True


class SagaOrquestadorReserva:
    """
    Orquestador Centralizado de Saga:
    Coordina transacciones compensables con garantía de consistencia eventual.
    Pasos:
      - T1: Reserva de cupo (Acción Compensable)
      - T2: Pasarela de Pagos (Punto de Decisión Pivot)
      - T3: Facturación y confirmación (Acción Retriable)
      - C1: Compensación Inversa (Devolución de cupos si T2 falla)
    """
    def __init__(self, gimnasio_service: GimnasioService, pasarela: IPasarelaPagos):
        self.gimnasio_service = gimnasio_service
        self.pasarela = pasarela

    def ejecutar_saga_reserva(self,
                              socio_id: str,
                              socio_nombre: str,
                              contacto: str,
                              items_req: list,
                              idempotency_key: str,
                              simular_falla_pago: bool = False) -> dict:
        """Ejecuta el flujo orquestado de la Saga con compensación automática."""
        log_saga = []
        reserva = None
        logger.info(f"🏁 Iniciando Saga para reserva del socio={socio_id}")

        try:
            # PASO T1: Crear Reserva y Bloquear Cupo (Local con Semantic Lock)
            reserva = self.gimnasio_service.crear_reserva_monolito(
                socio_id, socio_nombre, contacto, items_req, idempotency_key
            )
            msg_t1 = f"T1 [Cupos]: Reserva {reserva.id_reserva} creada con Semantic Lock (Total: ${reserva.total:,.2f})."
            log_saga.append(msg_t1)
            logger.info(msg_t1)

            # Si la reserva ya estaba completada o compensada previamente (idempotencia)
            if reserva.estado in [EstadoReserva.COMPLETADO, EstadoReserva.COMPENSADO]:
                log_saga.append(f"ℹ️ [Idempotencia]: Reserva ya procesada previamente con estado {reserva.estado.value}.")
                return {"exito": reserva.estado == EstadoReserva.COMPLETADO, "reserva": reserva, "log": log_saga}

            # PASO T2: Cobro en Pasarela Externa (Pivot Transaction)
            pay_key = f"PAY-{idempotency_key}"
            pago_ok = self.pasarela.procesar_cobro(
                reserva.id_reserva, reserva.total, pay_key, simular_falla=simular_falla_pago
            )
            if not pago_ok:
                raise RuntimeError("Falla en Pasarela de Pagos (Rechazo Financiero). Disparando Compensación Inversa (C1).")

            self.gimnasio_service.registrar_pago(reserva)
            msg_t2 = f"T2 [Pagos]: Débito de ${reserva.total:,.2f} exitoso en pasarela."
            log_saga.append(msg_t2)
            logger.info(msg_t2)

            # PASO T3: Facturación y Confirmación de la reserva
            self.gimnasio_service.confirmar_reserva(reserva)
            msg_t3 = "T3 [Facturación]: Factura emitida. Reserva confirmada. Saga completada exitosamente."
            log_saga.append(msg_t3)
            logger.info(msg_t3)

            return {"exito": True, "reserva": reserva, "log": log_saga}

        except ValidationError:
            # Errores de validación se propagan (la capa web los traduce a HTTP 422);
            # no hay nada que compensar porque nunca se bloqueó un cupo.
            raise

        except Exception as e:
            # COMPENSACIÓN INVERSA (C1): deshacer efectos secundarios
            err_msg = f"🚨 ERROR EN SAGA: {str(e)}"
            log_saga.append(err_msg)
            logger.error(err_msg)

            if reserva is not None:
                logger.warning(f"Iniciando Compensación C1 para Reserva {reserva.id_reserva}...")

                # C1: el servicio devuelve los cupos por el puerto del catálogo y marca COMPENSADO
                self.gimnasio_service.compensar_reserva(reserva, f"Aborto por falla en paso T2: {str(e)}")
                msg_c1 = "C1 [Compensación Cupos]: Cupos devueltos al gimnasio. Estado: COMPENSADO."
                log_saga.append(msg_c1)
                logger.info(msg_c1)

            return {"exito": False, "reserva": reserva, "log": log_saga, "error": str(e)}
