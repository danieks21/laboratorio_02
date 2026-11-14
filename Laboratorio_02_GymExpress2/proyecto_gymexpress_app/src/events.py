"""
========================================================================================
EVENTOS DE DOMINIO BAJO LA ESPECIFICACIÓN CNCF CLOUDEVENTS v1.0
Cátedra: Ingeniería de Software 3 [IF0129] - Corporación Universitaria Remington
Sesión 2 (Primer Parcial): contrato de mensajes entre los Bounded Contexts de GymExpress.

Atributos obligatorios (CloudEvents v1.0, sección 3.1): specversion, id, source, type.
Atributos opcionales usados: time (RFC 3339), datacontenttype, subject.

Decisiones de diseño:
  - Inmutable: el evento es una dataclass congelada y `data` se guarda como mapeo de solo
    lectura (copia profunda), de modo que ningún consumidor puede alterar lo que otro recibe.
  - Validación estricta (Fail-Fast): un evento mal formado no se puede construir.
  - `time` es un texto RFC 3339 (así lo exige la especificación), no un float.
  - Este módulo no depende de ningún otro módulo del proyecto (es el contrato estable).
Dependencias: NINGUNA (Python Standard Library)
========================================================================================
"""
import json
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict, is_dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Mapping, Optional

SPECVERSION = "1.0"
PREFIJO_TIPO = "co.edu.uniremington.gymexpress"

_RE_TIPO = re.compile(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_]*){2,}$")          # nombre calificado (DNS inverso)
_RE_SOURCE = re.compile(r"^\S+$")                                           # URI-reference sin espacios
_RE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")  # RFC 3339


class TipoEvento:
    """Catálogo de tipos de evento (nombres calificados)."""
    RESERVA_CREADA = f"{PREFIJO_TIPO}.reserva.creada"
    RESERVA_CONFIRMADA = f"{PREFIJO_TIPO}.reserva.confirmada"
    RESERVA_COMPENSADA = f"{PREFIJO_TIPO}.reserva.compensada"
    CUPOS_RESERVADOS = f"{PREFIJO_TIPO}.cupos.reservados"
    CUPOS_LIBERADOS = f"{PREFIJO_TIPO}.cupos.liberados"
    SERVICIO_CUPOS_BAJOS = f"{PREFIJO_TIPO}.servicio.cupos_bajos"
    INSUMO_STOCK_BAJO = f"{PREFIJO_TIPO}.insumo.stock_bajo"


class OrigenEvento:
    """`source` de cada Bounded Context (URI-reference)."""
    RESERVAS = "/gymexpress/reservas"
    CATALOGO = "/gymexpress/catalogo"
    INSUMOS = "/gymexpress/insumos"


class CloudEventInvalido(ValueError):
    """El evento no cumple la especificación CloudEvents v1.0."""


# ------------------------------- inmutabilidad -------------------------------
def _congelar(valor: Any) -> Any:
    if isinstance(valor, Mapping):
        return MappingProxyType({str(k): _congelar(v) for k, v in valor.items()})
    if isinstance(valor, (list, tuple)):
        return tuple(_congelar(v) for v in valor)
    return valor


def _descongelar(valor: Any) -> Any:
    if isinstance(valor, Mapping):
        return {k: _descongelar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_descongelar(v) for v in valor]
    return valor


def _ahora_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ------------------------------- el evento -------------------------------
@dataclass(frozen=True)
class CloudEvent:
    """Evento CNCF CloudEvents v1.0 inmutable, con validación estricta y serialización JSON."""
    id: str
    source: str
    type: str
    data: Mapping[str, Any] = field(hash=False)
    specversion: str = SPECVERSION
    time: Optional[str] = None
    datacontenttype: str = "application/json"
    subject: Optional[str] = None

    def __post_init__(self):
        if self.specversion != SPECVERSION:
            raise CloudEventInvalido(f"specversion debe ser '{SPECVERSION}' (recibido: {self.specversion!r}).")
        if not isinstance(self.id, str) or not self.id.strip():
            raise CloudEventInvalido("El atributo obligatorio 'id' no puede estar vacío.")
        try:
            uuid.UUID(self.id)
        except ValueError:
            raise CloudEventInvalido(f"'id' debe ser un UUID (recibido: {self.id!r}).")
        if not isinstance(self.source, str) or not _RE_SOURCE.match(self.source):
            raise CloudEventInvalido(f"'source' debe ser una URI-reference sin espacios (recibido: {self.source!r}).")
        if not isinstance(self.type, str) or not _RE_TIPO.match(self.type):
            raise CloudEventInvalido(
                f"'type' debe ser un nombre calificado como '{PREFIJO_TIPO}.reserva.creada' (recibido: {self.type!r}).")
        if not isinstance(self.data, Mapping):
            raise CloudEventInvalido("'data' debe ser un objeto (diccionario) serializable a JSON.")
        if self.subject is not None and (not isinstance(self.subject, str) or not self.subject.strip()):
            raise CloudEventInvalido("'subject', si se envía, no puede estar vacío.")
        object.__setattr__(self, "data", _congelar(self.data))
        try:
            json.dumps(_descongelar(self.data))
        except (TypeError, ValueError) as e:
            raise CloudEventInvalido(f"'data' no es serializable a JSON: {e}")
        if self.time is None:
            object.__setattr__(self, "time", _ahora_rfc3339())
        elif not isinstance(self.time, str) or not _RE_TIME.match(self.time):
            raise CloudEventInvalido(f"'time' debe cumplir RFC 3339 (recibido: {self.time!r}).")

    # ---- serialización ----
    def to_dict(self) -> dict:
        d = {"specversion": self.specversion, "id": self.id, "source": self.source, "type": self.type,
             "time": self.time, "datacontenttype": self.datacontenttype, "data": _descongelar(self.data)}
        if self.subject:
            d["subject"] = self.subject
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "CloudEvent":
        if not isinstance(d, Mapping):
            raise CloudEventInvalido("El evento debe ser un objeto JSON.")
        for obligatorio in ("specversion", "id", "source", "type"):
            if obligatorio not in d:
                raise CloudEventInvalido(f"Falta el atributo obligatorio '{obligatorio}'.")
        return cls(id=d["id"], source=d["source"], type=d["type"], data=d.get("data", {}),
                   specversion=d["specversion"], time=d.get("time"),
                   datacontenttype=d.get("datacontenttype", "application/json"), subject=d.get("subject"))

    @classmethod
    def from_json(cls, texto: str) -> "CloudEvent":
        try:
            return cls.from_dict(json.loads(texto))
        except json.JSONDecodeError as e:
            raise CloudEventInvalido(f"JSON inválido: {e}")


def crear_cloudevent(tipo: str, origen: str, payload: Any, subject: Optional[str] = None) -> CloudEvent:
    """Fábrica: genera el UUID4 y la marca de tiempo. `payload` puede ser un dict o una dataclass."""
    datos = asdict(payload) if is_dataclass(payload) and not isinstance(payload, type) else payload
    return CloudEvent(id=str(uuid.uuid4()), source=origen, type=tipo, data=datos, subject=subject)


# ------------------------------- payloads tipados (inmutables) -------------------------------
@dataclass(frozen=True)
class ReservaCreada:
    id_reserva: str
    socio_id: str
    total: float
    items_count: int
    idempotency_key: str


@dataclass(frozen=True)
class ReservaConfirmada:
    id_reserva: str
    socio_id: str
    total: float


@dataclass(frozen=True)
class ReservaCompensada:
    id_reserva: str
    socio_id: str
    motivo: str


@dataclass(frozen=True)
class CuposReservados:
    servicio_codigo: str
    cantidad: int
    cupos_restantes: int


@dataclass(frozen=True)
class CuposLiberados:
    servicio_codigo: str
    cantidad: int
    cupos_restantes: int


@dataclass(frozen=True)
class ServicioCuposBajos:
    servicio_codigo: str
    cupos_restantes: int
    umbral: int


@dataclass(frozen=True)
class InsumoStockBajo:
    codigo: str
    nombre: str
    stock_actual: int
    stock_minimo: int
    unidad: str


# ------------------------------- puerto de publicación -------------------------------
class IEventPublisher(ABC):
    """Puerto que usan los contextos para publicar eventos sin conocer el bus concreto (DIP)."""

    @abstractmethod
    def publicar(self, evento: CloudEvent) -> bool:
        """Entrega el evento al mecanismo de despacho. True si fue aceptado."""
        pass


class PublicadorNulo(IEventPublisher):
    """Null Object: se usa cuando no se configura ningún bus (los contextos siguen funcionando)."""

    def publicar(self, evento: CloudEvent) -> bool:
        return True
