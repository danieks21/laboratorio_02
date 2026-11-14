"""
========================================================================================
PRUEBAS DEL MÓDULO EXTENSIÓN: ENTRENADORES, SUPLEMENTOS, INSUMOS DE LIMPIEZA, PRÉSTAMOS
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Ejecutar: python3 -m unittest tests/test_extras.py   (o `python3 -m unittest discover tests`)
Dependencias: NINGUNA (Python Standard Library)
========================================================================================
"""
import unittest
import tempfile
import os
import shutil
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.validators import ValidationError
from src.validators_extra import ValidatorExtra
from src.repositories_extra import (SQLiteEntrenadorRepository, SQLiteSuplementoRepository,
                                    SQLiteInsumoRepository, SQLitePrestamoRepository)
from src.services_extra import (EntrenadorService, SuplementoService, InsumoService,
                                PrestamoService, GimnasioInfoService)
from src.repositories_extra import SQLiteGimnasioInfoRepository
from src.db_viewer import VisorBD
from src.db import abrir_conexion


class BaseExtras(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        db = os.path.join(self.dir, "test_extras.db")
        self.sup_repo = SQLiteSuplementoRepository(db)
        self.ins_repo = SQLiteInsumoRepository(db)
        self.pre_repo = SQLitePrestamoRepository(db)
        self.entrenadores = EntrenadorService(SQLiteEntrenadorRepository(db))
        self.suplementos = SuplementoService(self.sup_repo)
        self.insumos = InsumoService(self.ins_repo)
        self.prestamos = PrestamoService(self.pre_repo)
        self.gimnasio = GimnasioInfoService(SQLiteGimnasioInfoRepository(db))
        self.visor = VisorBD(db)
        self.db = db

    def tearDown(self):
        shutil.rmtree(self.dir)


class TestValidacionesExtra(unittest.TestCase):
    def test_cantidad_hora_dia_codigo(self):
        self.assertEqual(ValidatorExtra.validar_cantidad("3", "c", 5), 3)
        for malo in (0, -1, 6, "x", None):
            with self.assertRaises(ValidationError):
                ValidatorExtra.validar_cantidad(malo, "c", 5)
        self.assertEqual(ValidatorExtra.validar_hora("07:30", "h"), "07:30")
        for malo in ("7:30", "25:00", "07:60", ""):
            with self.assertRaises(ValidationError):
                ValidatorExtra.validar_hora(malo, "h")
        self.assertEqual(ValidatorExtra.validar_dia("lunes"), "LUNES")
        with self.assertRaises(ValidationError):
            ValidatorExtra.validar_dia("FUNDAY")
        self.assertEqual(ValidatorExtra.validar_codigo("sup-001"), "SUP-001")
        with self.assertRaises(ValidationError):
            ValidatorExtra.validar_codigo("a; DROP TABLE")


class TestEntrenadores(BaseExtras):
    def test_entrenadores_reales_sembrados_sin_franjas_propias(self):
        cart = self.entrenadores.cartelera()
        self.assertEqual([e["nombre"] for e in cart], ["Luis Henrique", "Carlos Pasos"])
        self.assertTrue(all(e["horarios"] == [] for e in cart))

    def test_agregar_entrenador_y_horarios_ordenados(self):
        luis = self.entrenadores.cartelera()[0]["id"]
        self.entrenadores.agregar_horario(luis, "viernes", "06:00", "08:00", "Sala")
        self.entrenadores.agregar_horario(luis, "lunes", "06:00", "08:00", "Sala")
        luis_cart = self.entrenadores.cartelera()[0]
        self.assertEqual([h["dia"] for h in luis_cart["horarios"]], ["LUNES", "VIERNES"])
        nuevo = self.entrenadores.agregar_entrenador("Sofía Ramírez", "Yoga")
        self.assertEqual(self.entrenadores.agregar_horario(nuevo.id, "martes", "17:00", "18:00", "Yoga").entrenador_nombre,
                         "Sofía Ramírez")

    def test_rechaza_duplicado_cruce_y_horas_invertidas(self):
        luis = self.entrenadores.cartelera()[0]["id"]
        self.entrenadores.agregar_horario(luis, "LUNES", "07:00", "08:00", "Sala")
        with self.assertRaises(ValidationError):
            self.entrenadores.agregar_entrenador("luis henrique", "Otra")
        with self.assertRaises(ValidationError):   # se cruza con 07:00-08:00 del mismo entrenador y día
            self.entrenadores.agregar_horario(luis, "LUNES", "07:30", "08:30", "Boxeo")
        with self.assertRaises(ValidationError):
            self.entrenadores.agregar_horario(luis, "LUNES", "10:00", "09:00", "Boxeo")
        with self.assertRaises(ValidationError):
            self.entrenadores.agregar_horario(999, "LUNES", "10:00", "11:00", "Boxeo")


class TestFichaGimnasio(BaseExtras):
    def test_horario_real_lunes_a_sabado_dos_franjas(self):
        f = self.gimnasio.ficha()
        self.assertEqual(f["jefe"], "Roman Tercero")
        self.assertEqual(f["festivos"], "Medio día")
        self.assertEqual([d["dia"] for d in f["horarios"]],
                         ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO"])
        for d in f["horarios"]:
            self.assertEqual(d["franjas"], [{"hora_inicio": "05:00", "hora_fin": "13:00"},
                                            {"hora_inicio": "14:00", "hora_fin": "21:30"}])


class TestConexiones(BaseExtras):
    def test_abrir_conexion_cierra_y_hace_rollback(self):
        import sqlite3
        with abrir_conexion(self.db) as conn:
            conn.execute("UPDATE suplementos SET stock_disponible = 77 WHERE codigo = 'SUP-001'")
        with self.assertRaises(sqlite3.ProgrammingError):    # conexión cerrada
            conn.execute("SELECT 1")
        try:
            with abrir_conexion(self.db) as conn2:
                conn2.execute("UPDATE suplementos SET stock_disponible = 5 WHERE codigo = 'SUP-001'")
                raise RuntimeError("falla simulada")
        except RuntimeError:
            pass
        self.assertEqual(self.sup_repo.buscar_por_codigo("SUP-001").stock_disponible, 77)   # rollback aplicado


class TestVisorBD(BaseExtras):
    def test_resumen_lista_las_tablas_con_sus_filas(self):
        r = self.visor.resumen()
        tablas = {t["nombre"]: t["filas"] for t in r["tablas"]}
        self.assertEqual(tablas["entrenadores"], 2)
        self.assertEqual(tablas["suplementos"], 7)
        self.assertEqual(tablas["elementos_prestables"], 6)
        self.assertEqual(tablas["insumos_limpieza"], 10)
        self.assertEqual(tablas["horario_gimnasio"], 12)

    def test_lee_tabla_y_rechaza_nombres_no_validos(self):
        d = self.visor.leer_tabla("suplementos")
        self.assertIn("precio", d["columnas"])
        self.assertEqual(d["total"], 7)
        for malo in ("no_existe", "suplementos; DROP TABLE suplementos", 'x" OR "1"="1'):
            with self.assertRaises(ValueError):
                self.visor.leer_tabla(malo)

    def test_es_solo_lectura(self):
        import sqlite3
        with self.visor._conectar() as conn:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM suplementos")


class TestSuplementos(BaseExtras):
    def test_consumo_descuenta_stock_y_calcula_total(self):
        antes = self.sup_repo.buscar_por_codigo("SUP-001")
        c = self.suplementos.consumir("1098765432", "Laura", "SUP-001", 2, "SUP-KEY-0001")
        self.assertEqual(c.total, antes.precio * 2)
        self.assertEqual(self.sup_repo.buscar_por_codigo("SUP-001").stock_disponible, antes.stock_disponible - 2)
        self.assertEqual(len(self.suplementos.consumos_de("1098765432")), 1)
        self.assertEqual(self.suplementos.consumos_de("5555555555"), [])

    def test_precios_reales_del_catalogo(self):
        precios = {s.nombre: s.precio for s in self.suplementos.listar()}
        self.assertEqual(precios["Pre entreno (1 scoop)"], 1000)
        self.assertEqual(precios["Pre entreno (tarro 200 g)"], 80000)
        self.assertEqual(precios["Proteína en polvo (1 scoop)"], 2500)
        self.assertEqual(precios["Proteína en polvo (paquete 2 lb)"], 90000)
        self.assertEqual(precios["Creatina (1 scoop)"], 3000)
        self.assertEqual(precios["Creatina (tarro 600 g)"], 150000)
        self.assertEqual(precios["Agua en botella"], 2000)

    def test_ajustar_stock_con_conteo_fisico(self):
        self.assertEqual(self.suplementos.ajustar_stock("SUP-007", 24).stock_disponible, 24)
        for malo in (-1, "x", 999999):
            with self.assertRaises(ValidationError):
                self.suplementos.ajustar_stock("SUP-007", malo)
        with self.assertRaises(ValidationError):
            self.suplementos.ajustar_stock("SUP-999", 5)

    def test_idempotencia_no_descuenta_dos_veces(self):
        antes = self.sup_repo.buscar_por_codigo("SUP-002").stock_disponible
        a = self.suplementos.consumir("1098765432", "Laura", "SUP-002", 1, "SUP-KEY-0002")
        b = self.suplementos.consumir("1098765432", "Laura", "SUP-002", 1, "SUP-KEY-0002")
        self.assertEqual(a.id_consumo, b.id_consumo)
        self.assertEqual(self.sup_repo.buscar_por_codigo("SUP-002").stock_disponible, antes - 1)

    def test_stock_insuficiente_no_altera_inventario_ni_historial(self):
        with abrir_conexion(self.sup_repo.db_path) as conn:
            conn.execute("UPDATE suplementos SET stock_disponible = 1 WHERE codigo = 'SUP-004'")
        with self.assertRaises(ValidationError):
            self.suplementos.consumir("1098765432", "Laura", "SUP-004", 2, "SUP-KEY-0003")
        self.assertEqual(self.sup_repo.buscar_por_codigo("SUP-004").stock_disponible, 1)
        self.assertEqual(self.suplementos.consumos_todos(), [])

    def test_rechaza_codigo_inexistente_y_cantidad_excesiva(self):
        with self.assertRaises(ValidationError):
            self.suplementos.consumir("1098765432", "Laura", "SUP-999", 1, "SUP-KEY-0004")
        with self.assertRaises(ValidationError):
            self.suplementos.consumir("1098765432", "Laura", "SUP-001", 50, "SUP-KEY-0005")


class TestInsumosLimpieza(BaseExtras):
    def test_uso_reposicion_y_alerta(self):
        self.assertEqual(self.insumos.alertas(), [])
        i = self.insumos.registrar_movimiento("LIM-001", "USO", 7, "Limpieza general")   # 10 -> 3 (= mínimo)
        self.assertEqual(i.stock_actual, 3)
        self.assertTrue(i.bajo_minimo)
        self.assertEqual([x.codigo for x in self.insumos.alertas()], ["LIM-001"])
        i = self.insumos.registrar_movimiento("LIM-001", "REPOSICION", 5, "Compra semanal")
        self.assertEqual(i.stock_actual, 8)
        self.assertFalse(i.bajo_minimo)
        self.assertEqual(len(self.insumos.movimientos()), 2)

    def test_catalogo_basico_de_limpieza(self):
        nombres = {i.nombre for i in self.insumos.listar()}
        for esperado in ("Desinfectante multiusos", "Escoba", "Trapero", "Jabón líquido para manos", "Bolsas de basura"):
            self.assertIn(esperado, nombres)

    def test_no_permite_stock_negativo(self):
        with self.assertRaises(ValidationError):
            self.insumos.registrar_movimiento("LIM-003", "USO", 9, "Exceso")             # hay 8
        self.assertEqual(self.ins_repo.buscar_por_codigo("LIM-003").stock_actual, 8)
        self.assertEqual(self.insumos.movimientos(), [])
        with self.assertRaises(ValidationError):
            self.insumos.registrar_movimiento("LIM-003", "OTRO", 1, "x")


class TestPrestamos(BaseExtras):
    def test_objetos_reales_con_sus_cantidades(self):
        cant = {e.nombre: e.cantidad_total for e in self.prestamos.listar_elementos()}
        self.assertEqual(cant, {"Colchoneta": 5, "Apoyo (cojín) para barra": 3, "Ligas": 4,
                                "Seguros": 8, "Cinturones": 4, "Rodilleras": 3})

    def test_prestar_y_devolver_restituye_disponibilidad(self):
        total = self.pre_repo.buscar_elemento("ELE-001").cantidad_disponible
        p = self.prestamos.prestar("1098765432", "Daniel", "ELE-001", 2, "PRE-KEY-0001")
        self.assertEqual(self.pre_repo.buscar_elemento("ELE-001").cantidad_disponible, total - 2)
        self.assertEqual(len(self.prestamos.prestamos_activos()), 1)
        d = self.prestamos.devolver(p.id_prestamo, "1098765432")
        self.assertEqual(d.estado, "DEVUELTO")
        self.assertEqual(self.pre_repo.buscar_elemento("ELE-001").cantidad_disponible, total)
        self.assertEqual(self.prestamos.prestamos_activos(), [])

    def test_no_se_devuelve_dos_veces_ni_ajeno(self):
        p = self.prestamos.prestar("1098765432", "Daniel", "ELE-002", 1, "PRE-KEY-0002")
        with self.assertRaises(ValidationError):
            self.prestamos.devolver(p.id_prestamo, "9999999999")
        self.prestamos.devolver(p.id_prestamo, "1098765432")
        with self.assertRaises(ValidationError):
            self.prestamos.devolver(p.id_prestamo, "1098765432")
        self.assertEqual(self.pre_repo.buscar_elemento("ELE-002").cantidad_disponible, 3)

    def test_limite_por_socio_e_idempotencia(self):
        self.prestamos.prestar("1098765432", "Daniel", "ELE-003", 3, "PRE-KEY-0003")
        with self.assertRaises(ValidationError):
            self.prestamos.prestar("1098765432", "Daniel", "ELE-003", 1, "PRE-KEY-0004")
        a = self.prestamos.prestar("2222222222", "Ana", "ELE-004", 1, "PRE-KEY-0005")
        b = self.prestamos.prestar("2222222222", "Ana", "ELE-004", 1, "PRE-KEY-0005")
        self.assertEqual(a.id_prestamo, b.id_prestamo)
        self.assertEqual(self.pre_repo.buscar_elemento("ELE-004").cantidad_disponible, 7)

    def test_sin_unidades_disponibles(self):
        with abrir_conexion(self.pre_repo.db_path) as conn:
            conn.execute("UPDATE elementos_prestables SET cantidad_disponible = 0 WHERE codigo = 'ELE-005'")
        with self.assertRaises(ValidationError):
            self.prestamos.prestar("1098765432", "Daniel", "ELE-005", 1, "PRE-KEY-0006")
        self.assertEqual(self.prestamos.prestamos_de("1098765432"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
