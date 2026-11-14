"""
========================================================================================
UTILIDAD DE CONEXIÓN SQLITE (cierre explícito de recursos)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
El gestor de contexto nativo `with sqlite3.connect(...)` confirma (commit) o revierte
(rollback) la transacción, pero NO cierra la conexión. `abrir_conexion` hace ambas cosas:
transacción atómica + cierre garantizado (evita ResourceWarning y fugas de descriptores).
Dependencias: NINGUNA (Python Standard Library `sqlite3`, `contextlib`)
========================================================================================
"""
import sqlite3
from contextlib import contextmanager


@contextmanager
def abrir_conexion(db_path: str, solo_lectura: bool = False):
    """Abre una conexión, la usa como transacción y SIEMPRE la cierra al salir."""
    conn = sqlite3.connect(db_path, uri=solo_lectura)
    try:
        with conn:          # commit si todo sale bien, rollback si hay excepción
            yield conn
    finally:
        conn.close()
