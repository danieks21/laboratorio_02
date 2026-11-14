"""
========================================================================================
SERVICIOS DEL MÓDULO EXTENSIÓN (SRP: un servicio por responsabilidad)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Reglas de negocio + validación Fail-Fast + idempotencia. Dependen solo de interfaces (DIP).
Dependencias: NINGUNA (Python Standard Library `time`, `uuid`)
========================================================================================
"""
import time
import uuid
from typing import List, Dict, Any, Optional
from src.models_extra import (Entrenador, Horario, Suplemento, ConsumoSuplemento,
                              InsumoLimpieza, MovimientoInsumo, ElementoPrestable, Prestamo)
from src.interfaces_extra import (IEntrenadorRepository, ISuplementoRepository,
                                  IInsumoRepository, IPrestamoRepository, IGimnasioInfoRepository)
from src.events import (IEventPublisher, PublicadorNulo, TipoEvento, OrigenEvento, crear_cloudevent, InsumoStockBajo)
from src.validators import Validator, ValidationError
from src.validators_extra import ValidatorExtra, DIAS_VALIDOS
from src.logger import get_logger

logger = get_logger("ServicesExtra")

MAX_UNIDADES_SUPLEMENTO = 5
MAX_UNIDADES_PRESTAMO = 3
MAX_UNIDADES_MOVIMIENTO_INSUMO = 500


def _nuevo_id(prefijo: str) -> str:
    """ID legible y único (el sufijo aleatorio evita colisiones en el mismo milisegundo)."""
    return f"{prefijo}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:4].upper()}"


class EntrenadorService:
    """Gestión y consulta de entrenadores y horarios."""
    def __init__(self, repo: IEntrenadorRepository):
        self.repo = repo

    def cartelera(self) -> List[Dict[str, Any]]:
        """Entrenadores con sus horarios ordenados por día y hora."""
        horarios = self.repo.listar_horarios()
        horarios.sort(key=lambda h: (DIAS_VALIDOS.index(h.dia), h.hora_inicio))
        resultado = []
        for e in self.repo.listar_entrenadores():
            resultado.append({
                "id": e.id, "nombre": e.nombre, "especialidad": e.especialidad,
                "horarios": [{"id": h.id, "dia": h.dia, "hora_inicio": h.hora_inicio,
                              "hora_fin": h.hora_fin, "actividad": h.actividad}
                             for h in horarios if h.entrenador_id == e.id]
            })
        return resultado

    def agregar_entrenador(self, nombre: str, especialidad: str) -> Entrenador:
        n = ValidatorExtra.validar_texto(nombre, "nombre", 60)
        esp = ValidatorExtra.validar_texto(especialidad, "especialidad", 80)
        if any(e.nombre.lower() == n.lower() for e in self.repo.listar_entrenadores()):
            raise ValidationError(f"Ya existe un entrenador llamado '{n}'.", campo="nombre")
        return self.repo.agregar_entrenador(n, esp)

    def agregar_horario(self, entrenador_id, dia, hora_inicio, hora_fin, actividad) -> Horario:
        eid = ValidatorExtra.validar_entero_id(entrenador_id, "entrenador_id")
        d = ValidatorExtra.validar_dia(dia)
        ini = ValidatorExtra.validar_hora(hora_inicio, "hora_inicio")
        fin = ValidatorExtra.validar_hora(hora_fin, "hora_fin")
        act = ValidatorExtra.validar_texto(actividad, "actividad", 60)
        if fin <= ini:
            raise ValidationError("La hora de fin debe ser posterior a la hora de inicio.", campo="hora_fin")
        if not self.repo.buscar_entrenador(eid):
            raise ValidationError(f"El entrenador {eid} no existe.", campo="entrenador_id")
        # Un entrenador no puede tener dos franjas que se crucen el mismo día
        for h in self.repo.listar_horarios():
            if h.entrenador_id == eid and h.dia == d and ini < h.hora_fin and fin > h.hora_inicio:
                raise ValidationError(
                    f"El horario se cruza con '{h.actividad}' ({h.hora_inicio}-{h.hora_fin}) del mismo entrenador.",
                    campo="hora_inicio")
        return self.repo.agregar_horario(eid, d, ini, fin, act)


class SuplementoService:
    """Catálogo de suplementos y registro de su consumo por los socios."""
    def __init__(self, repo: ISuplementoRepository):
        self.repo = repo

    def listar(self) -> List[Suplemento]:
        return self.repo.listar()

    def consumir(self, socio_id, socio_nombre, codigo, cantidad, idempotency_key) -> ConsumoSuplemento:
        s_id = Validator.validar_socio_id(socio_id)
        s_nombre = Validator.validar_no_vacio(socio_nombre, "socio_nombre")
        cod = ValidatorExtra.validar_codigo(codigo)
        cant = ValidatorExtra.validar_cantidad(cantidad, "cantidad", MAX_UNIDADES_SUPLEMENTO)
        key = Validator.validar_idempotency_key(idempotency_key)

        existente = self.repo.buscar_consumo_por_key(key)
        if existente:
            logger.warning(f"⚠️ [Idempotencia] Consumo duplicado ignorado: {existente.id_consumo}")
            return existente

        sup = self.repo.buscar_por_codigo(cod)
        if not sup:
            raise ValidationError(f"El suplemento '{cod}' no existe.", campo="codigo")

        consumo = ConsumoSuplemento(
            id_consumo=_nuevo_id("CON"), socio_id=s_id, socio_nombre=s_nombre,
            suplemento_codigo=sup.codigo, suplemento_nombre=sup.nombre, cantidad=cant,
            precio_unitario=sup.precio, total=round(sup.precio * cant, 2),
            idempotency_key=key, timestamp=time.time())
        if not self.repo.registrar_consumo_atomico(consumo):
            raise ValidationError(f"Stock insuficiente de '{sup.nombre}' para {cant} unidad(es).", campo="stock")
        logger.info(f"🥤 Consumo {consumo.id_consumo}: {cant} x {sup.nombre} (${consumo.total:,.0f}) socio={s_id}")
        return consumo

    def ajustar_stock(self, codigo, nuevo_stock) -> Suplemento:
        """Corrige el stock con el conteo físico (0 o más)."""
        cod = ValidatorExtra.validar_codigo(codigo)
        try:
            n = int(nuevo_stock)
        except (ValueError, TypeError):
            raise ValidationError("El stock debe ser un número entero.", campo="stock")
        if n < 0 or n > 100000:
            raise ValidationError("El stock debe estar entre 0 y 100000.", campo="stock")
        if not self.repo.fijar_stock(cod, n):
            raise ValidationError(f"El suplemento '{cod}' no existe.", campo="codigo")
        logger.info(f"📦 Stock de {cod} ajustado a {n}")
        return self.repo.buscar_por_codigo(cod)

    def consumos_de(self, socio_id) -> List[ConsumoSuplemento]:
        return self.repo.listar_consumos(Validator.validar_socio_id(socio_id))

    def consumos_todos(self) -> List[ConsumoSuplemento]:
        return self.repo.listar_consumos()


class InsumoService:
    """Inventario interno de limpieza (uso exclusivo del personal)."""
    def __init__(self, repo: IInsumoRepository, publisher: Optional[IEventPublisher] = None):
        self.repo = repo
        self.publisher = publisher or PublicadorNulo()

    def listar(self) -> List[InsumoLimpieza]:
        return self.repo.listar()

    def alertas(self) -> List[InsumoLimpieza]:
        """Insumos cuyo stock llegó al mínimo: hay que reponerlos."""
        return [i for i in self.repo.listar() if i.bajo_minimo]

    def registrar_movimiento(self, codigo, tipo, cantidad, motivo) -> InsumoLimpieza:
        cod = ValidatorExtra.validar_codigo(codigo)
        t = Validator.validar_no_vacio(tipo, "tipo").upper()
        if t not in ("USO", "REPOSICION"):
            raise ValidationError("El tipo debe ser USO o REPOSICION.", campo="tipo")
        cant = ValidatorExtra.validar_cantidad(cantidad, "cantidad", MAX_UNIDADES_MOVIMIENTO_INSUMO)
        mot = ValidatorExtra.validar_texto(motivo, "motivo", 120)
        insumo = self.repo.buscar_por_codigo(cod)
        if not insumo:
            raise ValidationError(f"El insumo '{cod}' no existe.", campo="codigo")
        if not self.repo.aplicar_movimiento_atomico(cod, t, cant, mot):
            raise ValidationError(
                f"No hay stock suficiente de '{insumo.nombre}' (disponible: {insumo.stock_actual} {insumo.unidad}).",
                campo="cantidad")
        actualizado = self.repo.buscar_por_codigo(cod)
        if actualizado.bajo_minimo:
            logger.warning(f"🧹 ALERTA: '{actualizado.nombre}' en {actualizado.stock_actual} {actualizado.unidad} (mínimo {actualizado.stock_minimo}).")
            if not insumo.bajo_minimo:                      # solo al CRUZAR el mínimo, no en cada movimiento
                try:
                    self.publisher.publicar(crear_cloudevent(
                        TipoEvento.INSUMO_STOCK_BAJO, OrigenEvento.INSUMOS,
                        InsumoStockBajo(actualizado.codigo, actualizado.nombre, actualizado.stock_actual,
                                        actualizado.stock_minimo, actualizado.unidad), subject=actualizado.codigo))
                except Exception as e:
                    logger.warning(f"No se pudo publicar insumo.stock_bajo: {type(e).__name__}: {e}")
        return actualizado

    def movimientos(self) -> List[MovimientoInsumo]:
        return self.repo.listar_movimientos()


class PrestamoService:
    """Préstamo y devolución de elementos para uso de los socios."""
    def __init__(self, repo: IPrestamoRepository):
        self.repo = repo

    def listar_elementos(self) -> List[ElementoPrestable]:
        return self.repo.listar_elementos()

    def prestar(self, socio_id, socio_nombre, codigo, cantidad, idempotency_key) -> Prestamo:
        s_id = Validator.validar_socio_id(socio_id)
        s_nombre = Validator.validar_no_vacio(socio_nombre, "socio_nombre")
        cod = ValidatorExtra.validar_codigo(codigo)
        cant = ValidatorExtra.validar_cantidad(cantidad, "cantidad", MAX_UNIDADES_PRESTAMO)
        key = Validator.validar_idempotency_key(idempotency_key)

        existente = self.repo.buscar_prestamo_por_key(key)
        if existente:
            logger.warning(f"⚠️ [Idempotencia] Préstamo duplicado ignorado: {existente.id_prestamo}")
            return existente

        elem = self.repo.buscar_elemento(cod)
        if not elem:
            raise ValidationError(f"El elemento '{cod}' no existe.", campo="codigo")

        # Regla de negocio: un socio no acumula más de MAX_UNIDADES_PRESTAMO unidades del mismo elemento
        ya_prestadas = sum(p.cantidad for p in self.repo.listar_prestamos(s_id, solo_activos=True)
                           if p.elemento_codigo == cod)
        if ya_prestadas + cant > MAX_UNIDADES_PRESTAMO:
            raise ValidationError(
                f"Ya tienes {ya_prestadas} unidad(es) de '{elem.nombre}'; el máximo por socio es {MAX_UNIDADES_PRESTAMO}.",
                campo="cantidad")

        prestamo = Prestamo(
            id_prestamo=_nuevo_id("PRE"), socio_id=s_id, socio_nombre=s_nombre,
            elemento_codigo=elem.codigo, elemento_nombre=elem.nombre, cantidad=cant,
            estado="PRESTADO", idempotency_key=key, fecha_prestamo=time.time())
        if not self.repo.registrar_prestamo_atomico(prestamo):
            raise ValidationError(f"No hay unidades disponibles de '{elem.nombre}'.", campo="stock")
        logger.info(f"🎽 Préstamo {prestamo.id_prestamo}: {cant} x {elem.nombre} a socio={s_id}")
        return prestamo

    def devolver(self, id_prestamo, socio_id) -> Prestamo:
        pid = Validator.validar_no_vacio(id_prestamo, "id_prestamo")
        s_id = Validator.validar_socio_id(socio_id)
        prestamo = self.repo.buscar_prestamo(pid)
        if not prestamo:
            raise ValidationError(f"El préstamo '{pid}' no existe.", campo="id_prestamo")
        if prestamo.socio_id != s_id:
            raise ValidationError("Ese préstamo pertenece a otro socio.", campo="socio_id")
        if not self.repo.devolver_atomico(pid, time.time()):
            raise ValidationError("Ese préstamo ya fue devuelto.", campo="id_prestamo")
        logger.info(f"↩️ Devolución del préstamo {pid} (socio={s_id})")
        return self.repo.buscar_prestamo(pid)

    def prestamos_de(self, socio_id) -> List[Prestamo]:
        return self.repo.listar_prestamos(Validator.validar_socio_id(socio_id))

    def prestamos_activos(self) -> List[Prestamo]:
        return self.repo.listar_prestamos(solo_activos=True)


class GimnasioInfoService:
    """Ficha pública del gimnasio: horario de atención, jefe y política de festivos."""
    def __init__(self, repo: IGimnasioInfoRepository):
        self.repo = repo

    def ficha(self) -> Dict[str, Any]:
        por_dia: Dict[str, list] = {}
        for h in self.repo.listar_horarios():
            por_dia.setdefault(h.dia, []).append({"hora_inicio": h.hora_inicio, "hora_fin": h.hora_fin})
        info = self.repo.obtener_info()
        return {
            "jefe": info.get("jefe", ""),
            "festivos": info.get("festivos", ""),
            "domingos": info.get("domingos", ""),
            "horarios": [{"dia": d, "franjas": sorted(por_dia[d], key=lambda f: f["hora_inicio"])}
                         for d in DIAS_VALIDOS if d in por_dia],
        }
