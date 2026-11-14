"""
========================================================================================
BOUNDED CONTEXT: CATÁLOGO DE SERVICIOS (SUBDOMINIO DE SOPORTE)
Cátedra: Ingeniería de Software 3 [IF0129] - Corporación Universitaria Remington
Sesión 2 (Primer Parcial). Dueño de: servicios, precios y cupos.
Frontera: expone el puerto ICatalogoPort y publica eventos CloudEvents. NO conoce el contexto
de Reservas (ni lo importa); solo depende de su repositorio abstracto y del puerto de eventos.
Dependencias del proyecto: interfaces, models, events, logger
========================================================================================
"""
from typing import List, Optional

from src.events import (IEventPublisher, PublicadorNulo, TipoEvento, OrigenEvento, crear_cloudevent,
                        CuposReservados, CuposLiberados, ServicioCuposBajos)
from src.interfaces import ICatalogoPort, IServicioRepository
from src.models import Servicio
from src.logger import get_logger

logger = get_logger("ContextoCatalogo")

UMBRAL_CUPOS_BAJOS = 3


class CatalogoService(ICatalogoPort):
    """Adaptador en proceso del puerto del catálogo."""

    def __init__(self, servicio_repo: IServicioRepository, publisher: Optional[IEventPublisher] = None,
                 umbral_cupos_bajos: int = UMBRAL_CUPOS_BAJOS):
        self._repo = servicio_repo
        self._publisher = publisher or PublicadorNulo()
        self._umbral = umbral_cupos_bajos

    def listar(self) -> List[Servicio]:
        return self._repo.obtener_todos()

    def consultar(self, codigo: str) -> Optional[Servicio]:
        return self._repo.buscar_por_codigo(codigo)

    def reservar_cupos(self, codigo: str, cantidad: int) -> bool:
        if not self._repo.descontar_cupos(codigo, cantidad):
            return False
        restantes = self._repo.buscar_por_codigo(codigo).cupos_disponibles
        self._emitir(TipoEvento.CUPOS_RESERVADOS, CuposReservados(codigo, cantidad, restantes), codigo)
        if restantes <= self._umbral:
            self._emitir(TipoEvento.SERVICIO_CUPOS_BAJOS, ServicioCuposBajos(codigo, restantes, self._umbral), codigo)
        return True

    def liberar_cupos(self, codigo: str, cantidad: int) -> None:
        if self._repo.reponer_cupos(codigo, cantidad):
            restantes = self._repo.buscar_por_codigo(codigo).cupos_disponibles
            self._emitir(TipoEvento.CUPOS_LIBERADOS, CuposLiberados(codigo, cantidad, restantes), codigo)

    def _emitir(self, tipo: str, payload, subject: str) -> None:
        """Publicar nunca debe romper la operación de negocio (manejo defensivo)."""
        try:
            self._publisher.publicar(crear_cloudevent(tipo, OrigenEvento.CATALOGO, payload, subject=subject))
        except Exception as e:
            logger.warning(f"No se pudo publicar {tipo}: {type(e).__name__}: {e}")
