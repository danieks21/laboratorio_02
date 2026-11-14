"""
========================================================================================
SUITE DE PRUEBAS UNITARIAS Y DE INTEGRACIÓN (TESTING NATIVO - CERO DEPENDENCIAS)
Cátedra: Ingeniería de Software 3 [IF0129] - Corporación Universitaria Remington
Pruebas: SOLID, ACID, Idempotencia, Saga Compensación Inversa, Validaciones Fail-Fast
Dependencias: NINGUNA (Python Standard Library `unittest`, `tempfile`, `os`, `shutil`)
========================================================================================
"""
import unittest
import tempfile
import os
import shutil
import json
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.models import Reserva, ItemReserva, EstadoReserva
from src.validators import Validator, ValidationError
from src.repositories import SQLiteServicioRepository, SQLiteReservaRepository, SQLiteOutboxRepository
from src.services import GimnasioService, PasarelaPagosMock, SagaOrquestadorReserva


class TestValidacionesNegocio(unittest.TestCase):
    """Pruebas para el módulo de validación defensiva (Fail-Fast)."""

    def test_socio_id_valido_e_invalido(self):
        self.assertEqual(Validator.validar_socio_id("1098765432"), "1098765432")
        self.assertEqual(Validator.validar_socio_id("SOC-001_A"), "SOC-001_A")

        with self.assertRaises(ValidationError):
            Validator.validar_socio_id("")
        with self.assertRaises(ValidationError):
            Validator.validar_socio_id("ab")
        with self.assertRaises(ValidationError):
            Validator.validar_socio_id("1098; DROP TABLE")

    def test_idempotency_key_validacion(self):
        self.assertEqual(Validator.validar_idempotency_key("IDEM-12345678"), "IDEM-12345678")
        with self.assertRaises(ValidationError):
            Validator.validar_idempotency_key("corta")

    def test_items_reserva_validacion(self):
        with self.assertRaises(ValidationError):
            Validator.validar_items_reserva([])

        with self.assertRaises(ValidationError):
            Validator.validar_items_reserva([{"codigo": "GYM-001", "cantidad": 0}])

        with self.assertRaises(ValidationError):
            Validator.validar_items_reserva([
                {"codigo": "GYM-001", "cantidad": 2},
                {"codigo": "GYM-001", "cantidad": 1}
            ])

        with self.assertRaises(ValidationError):
            Validator.validar_items_reserva([{"codigo": "GYM-001", "cantidad": 9999}])


class TestPersistenciaYACID(unittest.TestCase):
    """Pruebas de persistencia e integridad en SQLite aislado."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_gym.db")
        self.servicio_repo = SQLiteServicioRepository(self.db_path)
        self.reserva_repo = SQLiteReservaRepository(self.db_path)
        self.outbox_repo = SQLiteOutboxRepository(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_seed_servicios_y_actualizacion_cupos(self):
        servicios = self.servicio_repo.obtener_todos()
        self.assertEqual(len(servicios), 5, "El catálogo inicial debe sembrar 5 servicios")

        mensual = self.servicio_repo.buscar_por_codigo("GYM-001")
        self.assertIsNotNone(mensual)
        self.assertEqual(mensual.cupos_disponibles, 200)

        self.servicio_repo.actualizar_cupos("GYM-001", 195)
        self.assertEqual(self.servicio_repo.buscar_por_codigo("GYM-001").cupos_disponibles, 195)

    def test_guardar_y_recuperar_reserva(self):
        reserva = Reserva(
            id_reserva="RES-TEST-001",
            socio_id="1098765432",
            socio_nombre="Carlos Alférez",
            socio_contacto="3001234567",
            items=[ItemReserva("GYM-003", 2, 15000.0)],
            estado=EstadoReserva.CUPO_RESERVADO_SEMANTIC_LOCK,
            idempotency_key="IDEM-TEST-1111"
        )
        reserva.calcular_total()
        self.reserva_repo.guardar(reserva)

        recuperada = self.reserva_repo.buscar_por_id("RES-TEST-001")
        self.assertIsNotNone(recuperada)
        self.assertEqual(recuperada.total, 30000.0)
        self.assertEqual(recuperada.estado, EstadoReserva.CUPO_RESERVADO_SEMANTIC_LOCK)
        self.assertEqual(len(recuperada.items), 1)

    def test_outbox_transactional_pattern(self):
        self.outbox_repo.registrar_evento("RES-TEST-001", "reserva.creada", json.dumps({"monto": 30000}))
        pendientes = self.outbox_repo.obtener_pendientes()
        self.assertEqual(len(pendientes), 1)
        self.assertEqual(pendientes[0]["aggregate_id"], "RES-TEST-001")

        self.outbox_repo.marcar_publicado(pendientes[0]["id"])
        self.assertEqual(len(self.outbox_repo.obtener_pendientes()), 0)


class TestSagaYLogicaNegocio(unittest.TestCase):
    """Pruebas del Orquestador Saga, Idempotencia y Compensación Inversa C1."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_gym_saga.db")
        self.servicio_repo = SQLiteServicioRepository(self.db_path)
        self.reserva_repo = SQLiteReservaRepository(self.db_path)
        self.outbox_repo = SQLiteOutboxRepository(self.db_path)
        self.service = GimnasioService(self.servicio_repo, self.reserva_repo, self.outbox_repo)
        self.pasarela = PasarelaPagosMock()
        self.saga = SagaOrquestadorReserva(self.service, self.pasarela)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_saga_flujo_feliz_completado(self):
        """Caso 1: T1 -> T2 -> T3 completado satisfactoriamente."""
        cupos_iniciales = self.servicio_repo.buscar_por_codigo("GYM-003").cupos_disponibles  # 20

        resultado = self.saga.ejecutar_saga_reserva(
            socio_id="1098765432",
            socio_nombre="Laura Gómez",
            contacto="3109876543",
            items_req=[{"codigo": "GYM-003", "cantidad": 2}],
            idempotency_key="IDEM-EXITO-001",
            simular_falla_pago=False
        )

        self.assertTrue(resultado["exito"])
        self.assertEqual(resultado["reserva"].estado, EstadoReserva.COMPLETADO)
        self.assertEqual(self.servicio_repo.buscar_por_codigo("GYM-003").cupos_disponibles, cupos_iniciales - 2)
        self.assertEqual(len(self.outbox_repo.obtener_pendientes()), 1)

    def test_saga_compensacion_inversa_cuando_falla_pago(self):
        """Caso 2: T1 (Reserva) -> T2 Falla -> C1 (Cupos devueltos y estado COMPENSADO)."""
        cupos_iniciales = self.servicio_repo.buscar_por_codigo("GYM-005").cupos_disponibles  # 10

        resultado = self.saga.ejecutar_saga_reserva(
            socio_id="1098765432",
            socio_nombre="Marcos Ruiz",
            contacto="3201112233",
            items_req=[{"codigo": "GYM-005", "cantidad": 2}],
            idempotency_key="IDEM-FALLA-PAGO-001",
            simular_falla_pago=True
        )

        self.assertFalse(resultado["exito"])
        self.assertEqual(resultado["reserva"].estado, EstadoReserva.COMPENSADO)
        self.assertEqual(
            self.servicio_repo.buscar_por_codigo("GYM-005").cupos_disponibles,
            cupos_iniciales,
            "Los cupos deben regresar al valor original tras la compensación C1"
        )

    def test_garantia_de_idempotencia(self):
        """Caso 3: Dos peticiones con la misma idempotency_key no descuentan cupos dos veces."""
        cupos_iniciales = self.servicio_repo.buscar_por_codigo("GYM-004").cupos_disponibles  # 15
        key_unica = "IDEM-REPEAT-777"
        args = dict(
            socio_id="1098765432", socio_nombre="Valeria Ríos", contacto="3150001122",
            items_req=[{"codigo": "GYM-004", "cantidad": 2}],
            idempotency_key=key_unica, simular_falla_pago=False
        )

        res_1 = self.saga.ejecutar_saga_reserva(**args)
        res_2 = self.saga.ejecutar_saga_reserva(**args)

        self.assertEqual(res_1["reserva"].id_reserva, res_2["reserva"].id_reserva)
        self.assertEqual(self.servicio_repo.buscar_por_codigo("GYM-004").cupos_disponibles, cupos_iniciales - 2)

    def test_no_sobrevende_cupos(self):
        """Caso 4: servicio inexistente o cupos insuficientes fallan con ValidationError sin alterar el inventario."""
        with self.assertRaises(ValidationError):
            self.saga.ejecutar_saga_reserva(
                socio_id="1098765432", socio_nombre="Ana Torres", contacto="3000000000",
                items_req=[{"codigo": "GYM-999", "cantidad": 1}],
                idempotency_key="IDEM-NOEXISTE-01"
            )
        self.servicio_repo.actualizar_cupos("GYM-005", 1)
        with self.assertRaises(ValidationError):
            self.saga.ejecutar_saga_reserva(
                socio_id="1098765432", socio_nombre="Ana Torres", contacto="3000000000",
                items_req=[{"codigo": "GYM-005", "cantidad": 2}],
                idempotency_key="IDEM-SOBREVENTA-01"
            )
        self.assertEqual(self.servicio_repo.buscar_por_codigo("GYM-005").cupos_disponibles, 1)


if __name__ == "__main__":
    print("=" * 80)
    print("🧪 EJECUTANDO SUITE DE PRUEBAS AUTOMATIZADAS DE GYMEXPRESS")
    print("Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington")
    print("=" * 80)
    unittest.main(verbosity=2)
