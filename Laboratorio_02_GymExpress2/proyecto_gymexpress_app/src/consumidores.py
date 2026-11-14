"""
========================================================================================
CONSUMIDORES DE EVENTOS (SUSCRIPTORES DEL EVENTBUS)
Cátedra: Ingeniería de Software 3 [IF0129] - Corporación Universitaria Remington
Reaccionan a los eventos sin que los contextos de Reservas y Catálogo los conozcan.
Todos son IDEMPOTENTES: el bus puede entregar un evento más de una vez (at-least-once) y
cada consumidor ignora los ids que ya procesó.
Dependencias: NINGUNA (Python Standard Library)
========================================================================================
"""
import threading
import time
from collections import OrderedDict, deque
from typing import List

from src.events import CloudEvent, TipoEvento
from src.logger import get_logger

logger = get_logger("Consumidores")


class _Dedup:
    """Memoria acotada de ids ya procesados."""

    def __init__(self, capacidad: int = 2000):
        self._vistos: "OrderedDict[str, None]" = OrderedDict()
        self._capacidad = capacidad

    def ya_visto(self, evento_id: str) -> bool:
        if evento_id in self._vistos:
            return True
        self._vistos[evento_id] = None
        if len(self._vistos) > self._capacidad:
            self._vistos.popitem(last=False)
        return False


class AuditoriaEventos:
    """Registra todos los eventos (suscripción comodín) para trazabilidad y monitoreo."""

    def __init__(self, capacidad: int = 500):
        self._eventos: deque = deque(maxlen=capacidad)
        self._dedup = _Dedup()
        self._cerrojo = threading.Lock()

    def __call__(self, evento: CloudEvent) -> None:
        with self._cerrojo:
            if self._dedup.ya_visto(evento.id):
                return
            self._eventos.append(evento)

    def recientes(self, n: int = 50) -> List[dict]:
        with self._cerrojo:
            return [e.to_dict() for e in list(self._eventos)[-n:]][::-1]

    def total(self) -> int:
        with self._cerrojo:
            return len(self._eventos)


class NotificadorSocios:
    """Avisa a socios y personal (simulado). `latencia_s` imita un servicio externo lento (correo, WhatsApp)."""

    TIPOS = (TipoEvento.RESERVA_CONFIRMADA, TipoEvento.RESERVA_COMPENSADA,
             TipoEvento.SERVICIO_CUPOS_BAJOS, TipoEvento.INSUMO_STOCK_BAJO)

    def __init__(self, latencia_s: float = 0.0, capacidad: int = 200):
        self.latencia_s = latencia_s
        self._enviadas: deque = deque(maxlen=capacidad)
        self._dedup = _Dedup()
        self._cerrojo = threading.Lock()

    def __call__(self, evento: CloudEvent) -> None:
        with self._cerrojo:
            if self._dedup.ya_visto(evento.id):
                return
        d = evento.data
        if evento.type == TipoEvento.RESERVA_CONFIRMADA:
            destino, mensaje = f"socio {d['socio_id']}", f"Tu reserva {d['id_reserva']} fue confirmada."
        elif evento.type == TipoEvento.RESERVA_COMPENSADA:
            destino, mensaje = f"socio {d['socio_id']}", f"No pudimos cobrar la reserva {d['id_reserva']}; el cupo fue liberado."
        elif evento.type == TipoEvento.SERVICIO_CUPOS_BAJOS:
            destino, mensaje = "personal", f"Quedan {d['cupos_restantes']} cupos en {d['servicio_codigo']}."
        else:
            destino, mensaje = "personal", f"Reponer {d['nombre']}: {d['stock_actual']} {d['unidad']} (mínimo {d['stock_minimo']})."
        if self.latencia_s:
            time.sleep(self.latencia_s)               # simula el servicio externo
        with self._cerrojo:
            self._enviadas.append({"hora": time.strftime("%Y-%m-%d %H:%M:%S"), "destino": destino,
                                   "mensaje": mensaje, "evento_id": evento.id})
        logger.info(f"📨 Notificación a {destino}: {mensaje}")

    def enviadas(self, n: int = 50) -> List[dict]:
        with self._cerrojo:
            return list(self._enviadas)[-n:][::-1]


class ConsumidorExternoSimulado:
    """Imita un sistema lento (facturación, inventario externo): se suscribe a todo y tarda `latencia_s`."""

    def __init__(self, nombre: str, latencia_s: float):
        self.nombre, self.latencia_s = nombre, latencia_s
        self.__name__ = nombre
        self.procesados = 0

    def __call__(self, evento: CloudEvent) -> None:
        time.sleep(self.latencia_s)
        self.procesados += 1


def registrar_consumidores(bus, auditoria: AuditoriaEventos, notificador: NotificadorSocios) -> None:
    """Cableado de suscripciones (lo invoca el Composition Root)."""
    bus.suscribir("*", auditoria)
    for tipo in NotificadorSocios.TIPOS:
        bus.suscribir(tipo, notificador)
