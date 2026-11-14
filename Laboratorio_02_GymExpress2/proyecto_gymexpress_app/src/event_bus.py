"""
========================================================================================
EVENTBUS ASÍNCRONO NO BLOQUEANTE EN MEMORIA
Cátedra: Ingeniería de Software 3 [IF0129] - Corporación Universitaria Remington
Sesión 2 (Primer Parcial): despacho concurrente de eventos CloudEvents.

Modelo formal de la guía:   T_sync = sum(t_i)   -->   T_async = max(t_pub) <= 5 ms
  - `publicar()` solo encola (queue.Queue) y retorna: el hilo HTTP no espera a los consumidores.
  - N hilos daemon (workers) sacan eventos de la cola y los despachan: eventos distintos se
    procesan en paralelo. Con workers=1 se garantiza orden estricto.
  - Defensa: la falla de un suscriptor se registra (log + dead-letter) y no afecta a los demás
    ni detiene al worker. Nada se traga en silencio.
  - Cola acotada: si se llena, `publicar()` NO bloquea; rechaza el evento y lo contabiliza.
Dependencias: NINGUNA (Python Standard Library `queue`, `threading`, `time`, `collections`)
========================================================================================
"""
import queue
import threading
import time
from collections import deque
from typing import Callable, Dict, List

from src.events import CloudEvent, IEventPublisher
from src.logger import get_logger

logger = get_logger("EventBus")

Handler = Callable[[CloudEvent], None]
COMODIN = "*"          # suscripción a todos los tipos
_CENTINELA = object()  # señal de apagado para los workers


class _RegistroSuscriptores:
    """Suscripciones por tipo de evento, seguras entre hilos."""

    def __init__(self):
        self._suscriptores: Dict[str, List[Handler]] = {}
        self._cerrojo = threading.Lock()

    def suscribir(self, tipo_evento: str, handler: Handler) -> None:
        if not callable(handler):
            raise TypeError("El suscriptor debe ser invocable.")
        with self._cerrojo:
            self._suscriptores.setdefault(tipo_evento, []).append(handler)

    def desuscribir(self, tipo_evento: str, handler: Handler) -> bool:
        with self._cerrojo:
            lista = self._suscriptores.get(tipo_evento, [])
            if handler in lista:
                lista.remove(handler)
                return True
            return False

    def _destinatarios(self, tipo_evento: str) -> List[Handler]:
        with self._cerrojo:                      # copia: se puede suscribir mientras se despacha
            return list(self._suscriptores.get(tipo_evento, [])) + list(self._suscriptores.get(COMODIN, []))


class InMemoryEventBus(_RegistroSuscriptores, IEventPublisher):
    """Bus de eventos en memoria: publicación inmediata, despacho en segundo plano."""

    def __init__(self, workers: int = 4, capacidad: int = 10000, nombre: str = "gym-bus", iniciar: bool = True):
        super().__init__()
        if workers < 1:
            raise ValueError("workers debe ser >= 1")
        self.nombre, self.workers = nombre, workers
        self._cola: "queue.Queue" = queue.Queue(maxsize=capacidad)
        self._contadores = {"publicados": 0, "entregas_ok": 0, "entregas_fallidas": 0, "rechazados": 0}
        self._cerrojo_contadores = threading.Lock()
        self._dead_letters: deque = deque(maxlen=100)
        self._hilos: List[threading.Thread] = []
        self._detenido = False
        if iniciar:
            self.iniciar()

    # ----------------------------- ciclo de vida -----------------------------
    def iniciar(self) -> None:
        if self._hilos:
            return
        for i in range(self.workers):
            t = threading.Thread(target=self._worker, name=f"{self.nombre}-worker-{i + 1}", daemon=True)
            t.start()
            self._hilos.append(t)

    def detener(self, timeout: float = 5.0) -> None:
        """Apagado ordenado: termina de despachar lo pendiente y detiene los workers."""
        self._detenido = True
        for _ in self._hilos:
            self._cola.put(_CENTINELA)
        for t in self._hilos:
            t.join(timeout)
        self._hilos = []

    # ----------------------------- publicación -----------------------------
    def publicar(self, evento: CloudEvent) -> bool:
        """No bloquea: encola y retorna. False si el bus está detenido o la cola está llena."""
        if not isinstance(evento, CloudEvent):
            raise TypeError("Solo se pueden publicar instancias de CloudEvent.")
        if self._detenido:
            logger.warning(f"Bus detenido: evento {evento.id} rechazado.")
            return False
        try:
            self._cola.put_nowait(evento)
        except queue.Full:
            self._sumar("rechazados")
            logger.error(f"Cola llena: evento {evento.type} ({evento.id}) rechazado sin bloquear al llamador.")
            return False
        self._sumar("publicados")
        return True

    # ----------------------------- despacho -----------------------------
    def _worker(self) -> None:
        while True:
            item = self._cola.get()
            try:
                if item is _CENTINELA:
                    return
                self._despachar(item)
            finally:
                self._cola.task_done()

    def _despachar(self, evento: CloudEvent) -> None:
        for handler in self._destinatarios(evento.type):
            nombre = getattr(handler, "__name__", handler.__class__.__name__)
            try:
                handler(evento)
                self._sumar("entregas_ok")
            except Exception as e:                       # un suscriptor defectuoso no afecta a los demás
                self._sumar("entregas_fallidas")
                self._dead_letters.append({"evento_id": evento.id, "type": evento.type,
                                           "handler": nombre, "error": f"{type(e).__name__}: {e}",
                                           "hora": time.strftime("%Y-%m-%d %H:%M:%S")})
                logger.error(f"Suscriptor '{nombre}' falló con {evento.type} ({evento.id}): {type(e).__name__}: {e}")

    # ----------------------------- observabilidad -----------------------------
    def esperar_entrega(self, timeout: float = 5.0) -> bool:
        """Espera a que la cola quede vacía y todo despachado (útil en pruebas y apagado)."""
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if self._cola.unfinished_tasks == 0:
                return True
            time.sleep(0.002)
        return self._cola.unfinished_tasks == 0

    def metricas(self) -> dict:
        with self._cerrojo_contadores:
            m = dict(self._contadores)
        m.update({"pendientes": self._cola.unfinished_tasks, "workers": self.workers,
                  "modo": "asincrono", "dead_letters": len(self._dead_letters)})
        return m

    def dead_letters(self) -> List[dict]:
        return list(self._dead_letters)

    def _sumar(self, clave: str) -> None:
        with self._cerrojo_contadores:
            self._contadores[clave] += 1


class PublicadorSincrono(_RegistroSuscriptores, IEventPublisher):
    """
    Despacho en el MISMO hilo del llamador (T_sync = suma de los t_i de cada consumidor).
    Existe para comparar contra el bus asíncrono y como doble de prueba determinista.
    """

    def __init__(self):
        super().__init__()
        self._contadores = {"publicados": 0, "entregas_ok": 0, "entregas_fallidas": 0, "rechazados": 0}

    def publicar(self, evento: CloudEvent) -> bool:
        self._contadores["publicados"] += 1
        for handler in self._destinatarios(evento.type):
            try:
                handler(evento)
                self._contadores["entregas_ok"] += 1
            except Exception as e:
                self._contadores["entregas_fallidas"] += 1
                logger.error(f"Suscriptor falló (modo síncrono): {type(e).__name__}: {e}")
        return True

    def esperar_entrega(self, timeout: float = 5.0) -> bool:
        return True

    def metricas(self) -> dict:
        m = dict(self._contadores)
        m.update({"pendientes": 0, "workers": 0, "modo": "sincrono", "dead_letters": 0})
        return m
