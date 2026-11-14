"""
========================================================================================
PRUEBAS DE LA SESIÓN 2: CLOUDEVENTS v1.0, EVENTBUS ASÍNCRONO Y BOUNDED CONTEXTS
Cátedra: Ingeniería de Software 3 [IF0129] - Corporación Universitaria Remington
Dependencias: NINGUNA (Python Standard Library)
========================================================================================
"""
import dataclasses
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.events import (CloudEvent, CloudEventInvalido, crear_cloudevent, TipoEvento, OrigenEvento,
                        ReservaCreada, PublicadorNulo)
from src.event_bus import InMemoryEventBus, PublicadorSincrono
from src.consumidores import AuditoriaEventos, NotificadorSocios, ConsumidorExternoSimulado, registrar_consumidores
from src.repositories import SQLiteServicioRepository, SQLiteReservaRepository, SQLiteOutboxRepository
from src.services import GimnasioService, PasarelaPagosMock, SagaOrquestadorReserva
from src.contexto_catalogo import CatalogoService
from src.validators import ValidationError


def evento(tipo=TipoEvento.RESERVA_CREADA, datos=None):
    return crear_cloudevent(tipo, OrigenEvento.RESERVAS, datos if datos is not None else {"id_reserva": "R1"})


class TestCloudEvent(unittest.TestCase):
    def test_atributos_obligatorios_y_valores_por_defecto(self):
        e = evento()
        d = e.to_dict()
        for atributo in ("specversion", "id", "source", "type"):
            self.assertIn(atributo, d)
        self.assertEqual(e.specversion, "1.0")
        self.assertEqual(uuid.UUID(e.id).version, 4)
        self.assertRegex(e.time, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")     # RFC 3339
        self.assertEqual(e.datacontenttype, "application/json")

    def test_es_inmutable(self):
        e = evento(datos={"anidado": {"a": 1}, "lista": [1, 2]})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            e.type = "otro.tipo.calificado"
        with self.assertRaises(TypeError):
            e.data["nuevo"] = 1
        with self.assertRaises(TypeError):
            e.data["anidado"]["a"] = 2
        self.assertEqual(e.data["lista"], (1, 2))             # las listas se vuelven tuplas
        self.assertIsInstance(hash(e), int)                    # se puede usar en conjuntos

    def test_validacion_estricta(self):
        base = dict(id=str(uuid.uuid4()), source="/gymexpress/reservas", type=TipoEvento.RESERVA_CREADA, data={})
        CloudEvent(**base)
        casos = {"specversion": "0.3", "id": "no-es-uuid", "source": "con espacios", "type": "reserva", "data": "texto"}
        for campo, valor in casos.items():
            with self.subTest(campo=campo):
                with self.assertRaises(CloudEventInvalido):
                    CloudEvent(**{**base, campo: valor})
        with self.assertRaises(CloudEventInvalido):
            CloudEvent(**{**base, "data": {"x": object()}})   # no serializable a JSON
        with self.assertRaises(CloudEventInvalido):
            CloudEvent(**{**base, "time": "ayer"})

    def test_serializacion_ida_y_vuelta(self):
        e = crear_cloudevent(TipoEvento.RESERVA_CREADA, OrigenEvento.RESERVAS,
                             ReservaCreada("R1", "1098765432", 45000.0, 2, "k-12345678"), subject="R1")
        copia = CloudEvent.from_json(e.to_json())
        self.assertEqual(copia, e)
        self.assertEqual(json.loads(e.to_json())["data"]["total"], 45000.0)
        with self.assertRaises(CloudEventInvalido):
            CloudEvent.from_dict({"id": e.id})
        with self.assertRaises(CloudEventInvalido):
            CloudEvent.from_json("{no es json")


class TestEventBus(unittest.TestCase):
    def setUp(self):
        self.bus = InMemoryEventBus(workers=4)

    def tearDown(self):
        self.bus.detener()

    def test_publicar_no_bloquea_aunque_el_consumidor_sea_lento(self):
        self.bus.suscribir(TipoEvento.RESERVA_CREADA, lambda e: time.sleep(0.3))
        t0 = time.perf_counter()
        self.assertTrue(self.bus.publicar(evento()))
        publicar_ms = (time.perf_counter() - t0) * 1000
        self.assertLess(publicar_ms, 25, "publicar() debe retornar sin esperar al consumidor (guía: <= 5 ms)")
        self.assertTrue(self.bus.esperar_entrega(3))
        self.assertEqual(self.bus.metricas()["entregas_ok"], 1)

    def test_despacho_concurrente(self):
        self.bus.suscribir(TipoEvento.RESERVA_CREADA, lambda e: time.sleep(0.25))
        t0 = time.perf_counter()
        for _ in range(4):
            self.bus.publicar(evento())
        self.assertTrue(self.bus.esperar_entrega(3))
        total = time.perf_counter() - t0
        self.assertLess(total, 0.75, "4 eventos de 250 ms con 4 workers deben tardar ~250 ms, no 1000 ms")

    def test_un_suscriptor_defectuoso_no_afecta_a_los_demas(self):
        recibidos = []

        def malo(e):
            raise RuntimeError("falla simulada")

        self.bus.suscribir(TipoEvento.RESERVA_CREADA, malo)
        self.bus.suscribir(TipoEvento.RESERVA_CREADA, lambda e: recibidos.append(e.id))
        e = evento()
        self.bus.publicar(e)
        self.assertTrue(self.bus.esperar_entrega(3))
        self.assertEqual(recibidos, [e.id])
        m = self.bus.metricas()
        self.assertEqual((m["entregas_ok"], m["entregas_fallidas"]), (1, 1))
        dl = self.bus.dead_letters()
        self.assertEqual(len(dl), 1)
        self.assertIn("falla simulada", dl[0]["error"])
        self.bus.publicar(evento())                              # el worker sigue vivo
        self.assertTrue(self.bus.esperar_entrega(3))
        self.assertEqual(len(recibidos), 2)

    def test_comodin_y_desuscribir(self):
        todos, creadas = [], []
        self.bus.suscribir("*", lambda e: todos.append(e.type))
        h = lambda e: creadas.append(e.id)
        self.bus.suscribir(TipoEvento.RESERVA_CREADA, h)
        self.bus.publicar(evento(TipoEvento.RESERVA_CREADA))
        self.bus.publicar(evento(TipoEvento.CUPOS_LIBERADOS))
        self.assertTrue(self.bus.esperar_entrega(3))
        self.assertEqual(len(todos), 2)
        self.assertEqual(len(creadas), 1)
        self.assertTrue(self.bus.desuscribir(TipoEvento.RESERVA_CREADA, h))
        self.assertFalse(self.bus.desuscribir(TipoEvento.RESERVA_CREADA, h))

    def test_orden_estricto_con_un_solo_worker(self):
        bus = InMemoryEventBus(workers=1)
        orden = []
        bus.suscribir("*", lambda e: orden.append(e.data["n"]))
        for n in range(30):
            bus.publicar(evento(datos={"n": n}))
        self.assertTrue(bus.esperar_entrega(3))
        bus.detener()
        self.assertEqual(orden, list(range(30)))

    def test_cola_llena_no_bloquea_y_rechaza(self):
        bus = InMemoryEventBus(workers=1, capacidad=2)
        liberar = threading.Event()
        bus.suscribir("*", lambda e: liberar.wait(2))
        aceptados = [bus.publicar(evento()) for _ in range(6)]
        self.assertIn(False, aceptados)
        self.assertGreaterEqual(bus.metricas()["rechazados"], 1)
        liberar.set()
        bus.detener()

    def test_detener_y_tipos_invalidos(self):
        bus = InMemoryEventBus(workers=2)
        bus.detener()
        self.assertFalse(bus.publicar(evento()))
        with self.assertRaises(TypeError):
            self.bus.publicar({"no": "es un CloudEvent"})
        with self.assertRaises(TypeError):
            self.bus.suscribir("x.y.z", "no invocable")

    def test_publicador_sincrono_espera_a_los_consumidores(self):
        pub = PublicadorSincrono()
        pub.suscribir("*", lambda e: time.sleep(0.1))
        pub.suscribir("*", lambda e: time.sleep(0.1))
        t0 = time.perf_counter()
        pub.publicar(evento())
        self.assertGreaterEqual(time.perf_counter() - t0, 0.2)       # T_sync = suma de los t_i


class TestConsumidores(unittest.TestCase):
    def test_idempotencia_por_id(self):
        aud, notif = AuditoriaEventos(), NotificadorSocios()
        e = crear_cloudevent(TipoEvento.RESERVA_CONFIRMADA, OrigenEvento.RESERVAS,
                             {"id_reserva": "R1", "socio_id": "1098765432", "total": 1.0})
        for _ in range(3):
            aud(e)
            notif(e)
        self.assertEqual(aud.total(), 1)
        self.assertEqual(len(notif.enviadas()), 1)


class BaseContextos(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "ctx.db")
        self.servicios = SQLiteServicioRepository(self.db)
        self.reservas = SQLiteReservaRepository(self.db)
        self.outbox = SQLiteOutboxRepository(self.db)
        self.bus = PublicadorSincrono()                          # determinista: sin hilos
        self.vistos = []
        self.bus.suscribir("*", lambda e: self.vistos.append(e))
        self.svc = GimnasioService(self.servicios, self.reservas, self.outbox, event_publisher=self.bus)
        self.saga = SagaOrquestadorReserva(self.svc, PasarelaPagosMock())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def tipos(self):
        return [e.type for e in self.vistos]

    def reservar(self, codigo="GYM-003", cant=1, key=None, falla=False):
        return self.saga.ejecutar_saga_reserva("1098765432", "Laura", "300", [{"codigo": codigo, "cantidad": cant}],
                                               key or "EV-" + uuid.uuid4().hex, simular_falla_pago=falla)


class TestBoundedContexts(BaseContextos):
    def test_saga_exitosa_publica_los_eventos_de_ambos_contextos(self):
        self.assertTrue(self.reservar()["exito"])
        self.assertEqual(self.tipos(), [TipoEvento.CUPOS_RESERVADOS, TipoEvento.RESERVA_CREADA, TipoEvento.RESERVA_CONFIRMADA])
        origenes = {e.type: e.source for e in self.vistos}
        self.assertEqual(origenes[TipoEvento.CUPOS_RESERVADOS], OrigenEvento.CATALOGO)       # contexto Catálogo
        self.assertEqual(origenes[TipoEvento.RESERVA_CREADA], OrigenEvento.RESERVAS)         # contexto Reservas

    def test_compensacion_libera_cupos_y_publica_eventos(self):
        antes = self.servicios.buscar_por_codigo("GYM-005").cupos_disponibles
        r = self.reservar("GYM-005", 2, falla=True)
        self.assertFalse(r["exito"])
        self.assertEqual(self.servicios.buscar_por_codigo("GYM-005").cupos_disponibles, antes)
        self.assertIn(TipoEvento.CUPOS_LIBERADOS, self.tipos())
        self.assertEqual(self.tipos()[-1], TipoEvento.RESERVA_COMPENSADA)

    def test_peticion_duplicada_no_republica_eventos(self):
        self.reservar(key="EV-DUP-0001")
        n = len(self.vistos)
        self.reservar(key="EV-DUP-0001")
        self.assertEqual(len(self.vistos), n)

    def test_el_outbox_guarda_el_envelope_cloudevent(self):
        self.reservar()
        fila = self.outbox.obtener_pendientes()[0]
        self.assertEqual(fila["event_type"], TipoEvento.RESERVA_CREADA)
        ce = CloudEvent.from_dict(fila["payload"])               # el payload ES un CloudEvent válido
        self.assertEqual(ce.source, OrigenEvento.RESERVAS)
        self.assertEqual(ce.subject, fila["aggregate_id"])

    def test_alerta_de_cupos_bajos_en_el_catalogo(self):
        self.servicios.actualizar_cupos("GYM-005", 4)
        self.reservar("GYM-005", 1)                              # quedan 3 = umbral
        self.assertIn(TipoEvento.SERVICIO_CUPOS_BAJOS, self.tipos())

    def test_el_catalogo_funciona_sin_el_contexto_de_reservas(self):
        catalogo = CatalogoService(self.servicios, self.bus)     # sin importar nada de Reservas
        self.assertTrue(catalogo.reservar_cupos("GYM-004", 2))
        catalogo.liberar_cupos("GYM-004", 2)
        self.assertEqual(self.servicios.buscar_por_codigo("GYM-004").cupos_disponibles, 15)

    def test_publicador_defectuoso_no_rompe_la_reserva(self):
        class Roto(PublicadorNulo):
            def publicar(self, evento):
                raise RuntimeError("bus caído")
        svc = GimnasioService(self.servicios, self.reservas, self.outbox, event_publisher=Roto())
        reserva = svc.crear_reserva("1098765432", "Laura", "300", [{"codigo": "GYM-004", "cantidad": 1}], "EV-ROTO-0001")
        self.assertEqual(reserva.total, 15000.0)


class TestConcurrenciaSinSobreventa(BaseContextos):
    def test_cupos_atomicos_con_40_clientes_simultaneos(self):
        """Antes de la Sesión 2 esto vendía más cupos de los existentes cuando había hilos."""
        self.servicios.actualizar_cupos("GYM-005", 10)

        def intento(i):
            try:
                return self.svc.crear_reserva("1098765432", "Carrera", "300",
                                              [{"codigo": "GYM-005", "cantidad": 1}], f"RACE-{i:04d}-{uuid.uuid4().hex}")
            except ValidationError:
                return None

        with ThreadPoolExecutor(max_workers=40) as ex:
            resultados = list(ex.map(intento, range(40)))
        aceptadas = [r for r in resultados if r]
        self.assertEqual(len(aceptadas), 10)
        self.assertEqual(self.servicios.buscar_por_codigo("GYM-005").cupos_disponibles, 0)
        self.assertEqual(len({r.id_reserva for r in aceptadas}), 10, "los ids de reserva deben ser únicos")


class TestRespuestaNoBloqueante(BaseContextos):
    def test_la_saga_responde_mucho_mas_rapido_con_el_bus_asincrono(self):
        def medir(publicador):
            for nombre in ("correo", "facturacion", "inventario"):
                publicador.suscribir("*", ConsumidorExternoSimulado(nombre, 0.05))
            svc = GimnasioService(self.servicios, self.reservas, self.outbox, event_publisher=publicador)
            saga = SagaOrquestadorReserva(svc, PasarelaPagosMock())
            t0 = time.perf_counter()
            saga.ejecutar_saga_reserva("1098765432", "Laura", "300", [{"codigo": "GYM-001", "cantidad": 1}], "T-" + uuid.uuid4().hex)
            return time.perf_counter() - t0

        t_sync = medir(PublicadorSincrono())
        bus = InMemoryEventBus(workers=4)
        t_async = medir(bus)
        self.assertTrue(bus.esperar_entrega(5))
        bus.detener()
        self.assertGreater(t_sync, 0.4)                          # 3 eventos x 3 consumidores x 50 ms = 450 ms
        self.assertLess(t_async, t_sync / 4)


class TestRutasDeEventos(unittest.TestCase):
    def test_rutas_eventos(self):
        import io
        from src.app_extras import ExtrasRouter

        class HandlerFalso:
            def __init__(self):
                self.estado, self.wfile, self.json = None, io.BytesIO(), None
            def send_response(self, c): self.estado = c
            def send_header(self, k, v): pass
            def end_headers(self): pass
            def _send_json(self, d, status=200): self.json, self.estado = d, status

        carpeta = tempfile.mkdtemp()
        bus = InMemoryEventBus(workers=1)
        aud, notif = AuditoriaEventos(), NotificadorSocios()
        registrar_consumidores(bus, aud, notif)
        try:
            router = ExtrasRouter(os.path.join(carpeta, "t.db"), publisher=bus, bus=bus, auditoria=aud, notificador=notif)
            bus.publicar(evento())
            bus.esperar_entrega(3)
            h = HandlerFalso()
            self.assertTrue(router.manejar_get(h, "/eventos", ""))
            self.assertIn("CloudEvents", h.wfile.getvalue().decode("utf-8"))
            h = HandlerFalso()
            self.assertTrue(router.manejar_get(h, "/api/eventos", ""))
            self.assertEqual(h.json[0]["type"], TipoEvento.RESERVA_CREADA)
            h = HandlerFalso()
            self.assertTrue(router.manejar_get(h, "/api/eventos/metricas", ""))
            self.assertEqual(h.json["publicados"], 1)
        finally:
            bus.detener()
            shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
