"""
========================================================================================
VALIDACIONES DEL MÓDULO EXTENSIÓN (ENTRENADORES, SUPLEMENTOS, INSUMOS, PRÉSTAMOS)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Patrón: Fail-Fast / SoD. Complementa a `validators.py` sin modificarlo.
Dependencias: NINGUNA (Python Standard Library `re`)
========================================================================================
"""
import re
from src.validators import ValidationError, Validator

DIAS_VALIDOS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]


class ValidatorExtra:
    """Reglas de validación específicas del módulo extensión."""

    @staticmethod
    def validar_cantidad(valor, campo: str, maximo: int) -> int:
        """Entero estrictamente positivo y no mayor a `maximo`."""
        try:
            n = int(valor)
        except (ValueError, TypeError):
            raise ValidationError(f"El campo '{campo}' debe ser un número entero.", campo=campo)
        if n <= 0:
            raise ValidationError(f"El campo '{campo}' debe ser mayor a 0 (recibido: {n}).", campo=campo)
        if n > maximo:
            raise ValidationError(f"El campo '{campo}' no puede superar {maximo} (recibido: {n}).", campo=campo)
        return n

    @staticmethod
    def validar_codigo(valor, campo: str = "codigo") -> str:
        """Código alfanumérico en mayúsculas (3 a 20 caracteres)."""
        c = Validator.validar_no_vacio(valor, campo).upper()
        if not re.match(r"^[A-Z0-9\-_]{3,20}$", c):
            raise ValidationError(f"El código '{c}' no es válido (3 a 20 caracteres alfanuméricos).", campo=campo)
        return c

    @staticmethod
    def validar_texto(valor, campo: str, max_len: int = 80) -> str:
        """Texto obligatorio con longitud máxima."""
        t = Validator.validar_no_vacio(valor, campo)
        if len(t) > max_len:
            raise ValidationError(f"El campo '{campo}' no puede superar {max_len} caracteres.", campo=campo)
        return t

    @staticmethod
    def validar_dia(valor) -> str:
        d = Validator.validar_no_vacio(valor, "dia").upper()
        if d not in DIAS_VALIDOS:
            raise ValidationError(f"Día inválido '{d}'. Use: {', '.join(DIAS_VALIDOS)}.", campo="dia")
        return d

    @staticmethod
    def validar_hora(valor, campo: str) -> str:
        """Formato HH:MM de 24 horas."""
        h = Validator.validar_no_vacio(valor, campo)
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", h):
            raise ValidationError(f"La hora '{h}' debe tener formato HH:MM (24 h).", campo=campo)
        return h

    @staticmethod
    def validar_entero_id(valor, campo: str) -> int:
        try:
            n = int(valor)
        except (ValueError, TypeError):
            raise ValidationError(f"El campo '{campo}' debe ser un identificador numérico.", campo=campo)
        if n <= 0:
            raise ValidationError(f"El campo '{campo}' debe ser positivo.", campo=campo)
        return n
