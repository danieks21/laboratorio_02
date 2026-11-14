"""
========================================================================================
INTERFACES DEL MÓDULO EXTENSIÓN (DIP - DEPENDENCY INVERSION PRINCIPLE)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Las operaciones que tocan inventario + historial se declaran ATÓMICAS: el repositorio
las ejecuta en una sola transacción SQLite (a diferencia del flujo de reservas).
========================================================================================
"""
from abc import ABC, abstractmethod
from typing import Optional, List
from src.models_extra import (Entrenador, Horario, Suplemento, ConsumoSuplemento,
                              InsumoLimpieza, MovimientoInsumo, ElementoPrestable, Prestamo,
                              HorarioGimnasio)


class IEntrenadorRepository(ABC):
    @abstractmethod
    def listar_entrenadores(self) -> List[Entrenador]: pass

    @abstractmethod
    def buscar_entrenador(self, id_entrenador: int) -> Optional[Entrenador]: pass

    @abstractmethod
    def agregar_entrenador(self, nombre: str, especialidad: str) -> Entrenador: pass

    @abstractmethod
    def listar_horarios(self) -> List[Horario]: pass

    @abstractmethod
    def agregar_horario(self, entrenador_id: int, dia: str, hora_inicio: str,
                        hora_fin: str, actividad: str) -> Horario: pass


class ISuplementoRepository(ABC):
    @abstractmethod
    def listar(self) -> List[Suplemento]: pass

    @abstractmethod
    def buscar_por_codigo(self, codigo: str) -> Optional[Suplemento]: pass

    @abstractmethod
    def registrar_consumo_atomico(self, consumo: ConsumoSuplemento) -> bool:
        """Descuenta stock y guarda el consumo en UNA transacción. False si no hay stock suficiente."""
        pass

    @abstractmethod
    def fijar_stock(self, codigo: str, nuevo_stock: int) -> bool:
        """Corrige el stock de un suplemento (conteo físico). False si el código no existe."""
        pass

    @abstractmethod
    def buscar_consumo_por_key(self, key: str) -> Optional[ConsumoSuplemento]: pass

    @abstractmethod
    def listar_consumos(self, socio_id: Optional[str] = None) -> List[ConsumoSuplemento]: pass


class IInsumoRepository(ABC):
    @abstractmethod
    def listar(self) -> List[InsumoLimpieza]: pass

    @abstractmethod
    def buscar_por_codigo(self, codigo: str) -> Optional[InsumoLimpieza]: pass

    @abstractmethod
    def aplicar_movimiento_atomico(self, codigo: str, tipo: str, cantidad: int, motivo: str) -> bool:
        """Ajusta el stock y registra el movimiento en UNA transacción. False si el stock quedaría negativo."""
        pass

    @abstractmethod
    def listar_movimientos(self, limite: int = 30) -> List[MovimientoInsumo]: pass


class IPrestamoRepository(ABC):
    @abstractmethod
    def listar_elementos(self) -> List[ElementoPrestable]: pass

    @abstractmethod
    def buscar_elemento(self, codigo: str) -> Optional[ElementoPrestable]: pass

    @abstractmethod
    def registrar_prestamo_atomico(self, prestamo: Prestamo) -> bool:
        """Descuenta disponibilidad y guarda el préstamo en UNA transacción. False si no hay unidades."""
        pass

    @abstractmethod
    def devolver_atomico(self, id_prestamo: str, fecha: float) -> bool:
        """Marca DEVUELTO y repone disponibilidad en UNA transacción. False si no estaba PRESTADO."""
        pass

    @abstractmethod
    def buscar_prestamo(self, id_prestamo: str) -> Optional[Prestamo]: pass

    @abstractmethod
    def buscar_prestamo_por_key(self, key: str) -> Optional[Prestamo]: pass

    @abstractmethod
    def listar_prestamos(self, socio_id: Optional[str] = None, solo_activos: bool = False) -> List[Prestamo]: pass


class IGimnasioInfoRepository(ABC):
    """Datos generales del gimnasio: horario de atención, jefe, política de festivos."""

    @abstractmethod
    def listar_horarios(self) -> List[HorarioGimnasio]: pass

    @abstractmethod
    def obtener_info(self) -> dict: pass
