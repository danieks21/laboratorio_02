"""
========================================================================================
ENRUTADOR HTTP DEL MÓDULO EXTENSIÓN (portal del socio /usuario y panel interno /gestion)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Se acopla al controlador existente con UNA línea por verbo HTTP: si la ruta no es suya,
devuelve False y el flujo original de reservas sigue exactamente igual (Open/Closed).
Sin lógica de negocio ni SQL (SoD): solo parsing, enrutamiento y serialización.
========================================================================================
"""
import json
import urllib.parse
from dataclasses import asdict
from src.repositories_extra import (SQLiteEntrenadorRepository, SQLiteSuplementoRepository,
                                    SQLiteInsumoRepository, SQLitePrestamoRepository,
                                    SQLiteGimnasioInfoRepository)
from src.services_extra import (EntrenadorService, SuplementoService, InsumoService,
                                PrestamoService, GimnasioInfoService)
from src.db_viewer import VisorBD
from src.validators import ValidationError
from src.pages_extra import PORTAL_USUARIO_HTML, PANEL_GESTION_HTML, BASEDATOS_HTML, PANEL_INTEGRADO_HTML, EVENTOS_HTML
from src.logger import get_logger

logger = get_logger("HTTP_Extras")


def _dict(obj) -> dict:
    return asdict(obj)


class ExtrasRouter:
    """Composition Root del módulo extensión + tabla de rutas."""
    def __init__(self, db_path: str, publisher=None, bus=None, auditoria=None, notificador=None):
        self.bus, self.auditoria, self.notificador = bus, auditoria, notificador
        self.entrenadores = EntrenadorService(SQLiteEntrenadorRepository(db_path))
        self.suplementos = SuplementoService(SQLiteSuplementoRepository(db_path))
        self.insumos = InsumoService(SQLiteInsumoRepository(db_path), publisher)
        self.prestamos = PrestamoService(SQLitePrestamoRepository(db_path))
        self.gimnasio = GimnasioInfoService(SQLiteGimnasioInfoRepository(db_path))
        self.visor = VisorBD(db_path)

    # ------------------------------ GET ------------------------------
    def manejar_get(self, h, path: str, query: str = "") -> bool:
        params = urllib.parse.parse_qs(query)
        socio_id = params.get("socio_id", [""])[0]

        rutas = {
            "/api/gimnasio": lambda: self.gimnasio.ficha(),
            "/api/entrenadores": lambda: self.entrenadores.cartelera(),
            "/api/suplementos": lambda: [_dict(s) for s in self.suplementos.listar()],
            "/api/suplementos/consumos": lambda: [_dict(c) for c in self.suplementos.consumos_de(socio_id)],
            "/api/elementos": lambda: [_dict(e) for e in self.prestamos.listar_elementos()],
            "/api/elementos/prestamos": lambda: [_dict(p) for p in self.prestamos.prestamos_de(socio_id)],
            "/api/gestion/insumos": lambda: [dict(_dict(i), bajo_minimo=i.bajo_minimo) for i in self.insumos.listar()],
            "/api/gestion/movimientos": lambda: [_dict(m) for m in self.insumos.movimientos()],
            "/api/gestion/prestamos-activos": lambda: [_dict(p) for p in self.prestamos.prestamos_activos()],
            "/api/gestion/consumos": lambda: [_dict(c) for c in self.suplementos.consumos_todos()],
            "/api/eventos": lambda: self.auditoria.recientes(50) if self.auditoria else [],
            "/api/eventos/metricas": lambda: self.bus.metricas() if self.bus else {},
            "/api/eventos/notificaciones": lambda: self.notificador.enviadas(30) if self.notificador else [],
            "/api/eventos/dead-letters": lambda: self.bus.dead_letters() if hasattr(self.bus, "dead_letters") else [],
            "/api/bd/resumen": lambda: self.visor.resumen(),
            "/api/bd/tabla": lambda: self._leer_tabla(params),
        }

        if path == "/usuario":
            self._html(h, PORTAL_USUARIO_HTML)
            return True
        if path == "/gestion":
            self._html(h, PANEL_GESTION_HTML)
            return True
        if path == "/eventos":
            self._html(h, EVENTOS_HTML)
            return True
        if path == "/panel":
            self._html(h, PANEL_INTEGRADO_HTML)
            return True
        if path == "/basedatos":
            self._html(h, BASEDATOS_HTML)
            return True
        if path in rutas:
            self._responder(h, rutas[path])
            return True
        return False

    # ------------------------------ POST ------------------------------
    def manejar_post(self, h) -> bool:
        rutas = {
            "/api/suplementos/consumo": lambda d: _dict(self.suplementos.consumir(
                d.get("socio_id"), d.get("socio_nombre"), d.get("codigo"), d.get("cantidad"), d.get("idempotency_key"))),
            "/api/elementos/prestamo": lambda d: _dict(self.prestamos.prestar(
                d.get("socio_id"), d.get("socio_nombre"), d.get("codigo"), d.get("cantidad"), d.get("idempotency_key"))),
            "/api/elementos/devolucion": lambda d: _dict(self.prestamos.devolver(
                d.get("id_prestamo"), d.get("socio_id"))),
            "/api/gestion/insumos/movimiento": lambda d: dict(
                _dict(i := self.insumos.registrar_movimiento(d.get("codigo"), d.get("tipo"), d.get("cantidad"), d.get("motivo"))),
                bajo_minimo=i.bajo_minimo),
            "/api/gestion/suplementos/stock": lambda d: _dict(self.suplementos.ajustar_stock(
                d.get("codigo"), d.get("stock"))),
            "/api/gestion/entrenadores": lambda d: _dict(self.entrenadores.agregar_entrenador(
                d.get("nombre"), d.get("especialidad"))),
            "/api/gestion/horarios": lambda d: _dict(self.entrenadores.agregar_horario(
                d.get("entrenador_id"), d.get("dia"), d.get("hora_inicio"), d.get("hora_fin"), d.get("actividad"))),
        }
        ruta = h.path.split("?")[0]
        if ruta not in rutas:
            return False

        try:
            length = int(h.headers.get("Content-Length", 0))
            data = json.loads(h.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("El cuerpo debe ser un objeto JSON.")
        except Exception as e:
            logger.error(f"JSON inválido en {ruta}: {e}")
            h._send_json({"exito": False, "error": f"JSON malformado: {e}"}, status=400)
            return True

        self._responder(h, lambda: rutas[ruta](data), con_exito=True)
        return True

    # ------------------------------ utilidades ------------------------------
    def _leer_tabla(self, params: dict) -> dict:
        nombre = params.get("nombre", [""])[0]
        try:
            limite = int(params.get("limite", ["200"])[0])
            return self.visor.leer_tabla(nombre, limite)
        except ValueError as e:
            raise ValidationError(str(e), campo="nombre")

    def _responder(self, h, accion, con_exito: bool = False):
        try:
            resultado = accion()
            h._send_json({"exito": True, "resultado": resultado} if con_exito else resultado)
        except ValidationError as ve:
            logger.warning(f"Validación: {ve}")
            h._send_json({"exito": False, "error": str(ve), "campo": getattr(ve, "campo", "")}, status=422)
        except Exception as ex:
            logger.error(f"Error inesperado: {ex}")
            h._send_json({"exito": False, "error": str(ex)}, status=500)

    @staticmethod
    def _html(h, contenido: str):
        h.send_response(200)
        h.send_header("Content-Type", "text/html; charset=utf-8")
        h.end_headers()
        h.wfile.write(contenido.encode("utf-8"))
