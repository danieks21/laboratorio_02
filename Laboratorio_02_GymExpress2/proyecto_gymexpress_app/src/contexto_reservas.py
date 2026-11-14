"""
========================================================================================
BOUNDED CONTEXT: RESERVAS (SUBDOMINIO NÚCLEO)
Cátedra: Ingeniería de Software 3 [IF0129] - Corporación Universitaria Remington
Sesión 2 (Primer Parcial). Dueño de: reservas, su ciclo de vida y su historial.
Frontera: habla con el Catálogo SOLO a través del puerto ICatalogoPort (sin importar el
contexto de Catálogo ni su repositorio) y comunica lo ocurrido con eventos CloudEvents.
Dependencias del proyecto: interfaces, models, validators, events, logger
========================================================================================
"""
import time
import uuid
import json
from typing import Optional

from src.events import (IEventPublisher, PublicadorNulo, TipoEvento, OrigenEvento, crear_cloudevent,
                        ReservaCreada, ReservaConfirmada, ReservaCompensada)
from src.interfaces import ICatalogoPort, IReservaRepository, IOutboxRepository
from src.models import Reserva, ItemReserva, EstadoReserva
from src.validators import Validator, ValidationError
from src.logger import get_logger

logger = get_logger("ContextoReservas")


class ReservasService:
    """Casos de uso del núcleo: crear, registrar pago, confirmar y compensar una reserva."""

    def __init__(self, catalogo: ICatalogoPort, reserva_repo: IReservaRepository,
                 outbox_repo: IOutboxRepository, publisher: Optional[IEventPublisher] = None):
        self._catalogo = catalogo
        self._reservas = reserva_repo
        self._outbox = outbox_repo
        self._publisher = publisher or PublicadorNulo()

    # ------------------------------------------------------------------ crear
    def crear_reserva(self, socio_id: str, socio_nombre: str, contacto: str,
                      items_req: list, idempotency_key: str) -> Reserva:
        """
        Validación Fail-Fast -> idempotencia -> consulta de precios/cupos por el puerto del catálogo
        -> bloqueo atómico de cupos -> persistencia -> Outbox (envelope CloudEvent) -> evento al bus.
        """
        s_id = Validator.validar_socio_id(socio_id)
        s_nombre = Validator.validar_no_vacio(socio_nombre, "socio_nombre")
        s_contacto = Validator.validar_no_vacio(contacto, "contacto")
        i_key = Validator.validar_idempotency_key(idempotency_key)
        items_validados = Validator.validar_items_reserva(items_req)

        logger.info(f"Procesando reserva para socio={s_id} con key={i_key}")
        existente = self._reservas.buscar_por_idempotency_key(i_key)
        if existente:
            logger.warning(f"⚠️ [Idempotencia] Petición duplicada detectada. Retornando reserva existente {existente.id_reserva}")
            return existente

        items = []
        for it in items_validados:
            serv = self._catalogo.consultar(it["codigo"])
            if not serv:
                logger.error(f"Validación de catálogo fallida: el código '{it['codigo']}' no existe.")
                raise ValidationError(f"El servicio '{it['codigo']}' no existe en el catálogo del gimnasio.", campo="codigo")
            if not serv.tiene_cupo(it["cantidad"]):
                logger.error(f"Cupos insuficientes para {serv.nombre} ({serv.codigo}). Solicitado: {it['cantidad']}, Disponible: {serv.cupos_disponibles}")
                raise ValidationError(
                    f"Cupos insuficientes para '{serv.nombre}'. Solicitado: {it['cantidad']}, Disponible: {serv.cupos_disponibles}",
                    campo="cupos")
            items.append(ItemReserva(serv.codigo, it["cantidad"], serv.precio))

        reserva = Reserva(
            id_reserva=f"RES-{int(time.time() * 1000)}-{uuid.uuid4().hex[:4].upper()}",
            socio_id=s_id, socio_nombre=s_nombre, socio_contacto=s_contacto,
            items=items, estado=EstadoReserva.PENDIENTE, idempotency_key=i_key)
        reserva.calcular_total()
        reserva.transicionar_a(EstadoReserva.CUPO_RESERVADO_SEMANTIC_LOCK, "Cupo reservado preventivamente (Semantic Lock)")

        # Bloqueo atómico de cupos; si falla un renglón (otro cliente se adelantó) se revierten los previos
        bloqueados = []
        for it in items:
            if not self._catalogo.reservar_cupos(it.servicio_codigo, it.cantidad):
                for previo in bloqueados:
                    self._catalogo.liberar_cupos(previo.servicio_codigo, previo.cantidad)
                raise ValidationError(f"Cupos insuficientes para '{it.servicio_codigo}': otro socio reservó primero.",
                                      campo="cupos")
            bloqueados.append(it)

        self._reservas.guardar(reserva)
        logger.info(f"✅ Reserva {reserva.id_reserva} registrada exitosamente. Total=${reserva.total:,.2f}")

        evento = crear_cloudevent(
            TipoEvento.RESERVA_CREADA, OrigenEvento.RESERVAS,
            ReservaCreada(reserva.id_reserva, reserva.socio_id, reserva.total, len(reserva.items), reserva.idempotency_key),
            subject=reserva.id_reserva)
        self._outbox.registrar_evento(aggregate_id=reserva.id_reserva, event_type=evento.type, payload_json=evento.to_json())
        self._emitir(evento)
        return reserva

    # ------------------------------------------------------------------ ciclo de vida (usado por la Saga)
    def registrar_pago(self, reserva: Reserva) -> Reserva:
        reserva.transicionar_a(EstadoReserva.PAGADO, "Cobro aprobado por pasarela financiera")
        self._reservas.guardar(reserva)
        return reserva

    def confirmar(self, reserva: Reserva) -> Reserva:
        reserva.transicionar_a(EstadoReserva.COMPLETADO, "Reserva facturada y confirmada")
        self._reservas.guardar(reserva)
        self._emitir(crear_cloudevent(TipoEvento.RESERVA_CONFIRMADA, OrigenEvento.RESERVAS,
                                      ReservaConfirmada(reserva.id_reserva, reserva.socio_id, reserva.total),
                                      subject=reserva.id_reserva))
        return reserva

    def compensar(self, reserva: Reserva, motivo: str) -> Reserva:
        """Compensación C1: devuelve los cupos por el puerto del catálogo y marca la reserva COMPENSADO."""
        for it in reserva.items:
            self._catalogo.liberar_cupos(it.servicio_codigo, it.cantidad)
        reserva.transicionar_a(EstadoReserva.COMPENSADO, motivo)
        self._reservas.guardar(reserva)
        self._emitir(crear_cloudevent(TipoEvento.RESERVA_COMPENSADA, OrigenEvento.RESERVAS,
                                      ReservaCompensada(reserva.id_reserva, reserva.socio_id, motivo),
                                      subject=reserva.id_reserva))
        return reserva

    def _emitir(self, evento) -> None:
        """Publicar nunca debe romper la operación de negocio (manejo defensivo)."""
        try:
            self._publisher.publicar(evento)
        except Exception as e:
            logger.warning(f"No se pudo publicar {evento.type}: {type(e).__name__}: {e}")
