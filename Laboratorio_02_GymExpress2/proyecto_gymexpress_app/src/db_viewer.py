"""
========================================================================================
VISOR DE LA BASE DE DATOS (SOLO LECTURA)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Permite ver en el navegador (/basedatos) el contenido real del archivo SQLite del proyecto.
Seguridad: conexión en modo read-only y nombres de tabla validados contra sqlite_master
(nunca se concatena texto del usuario sin validar).
Dependencias: NINGUNA (Python Standard Library `sqlite3`, `pathlib`)
========================================================================================
"""
import sqlite3
from pathlib import Path
from src.db import abrir_conexion
from typing import Dict, Any, List

LIMITE_MAXIMO = 500


class VisorBD:
    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path).resolve())

    def _conectar(self):
        """Conexión de SOLO LECTURA que se cierra al terminar el bloque `with`."""
        return abrir_conexion(Path(self.db_path).as_uri() + "?mode=ro", solo_lectura=True)

    def _nombres_tablas(self, conn: sqlite3.Connection) -> List[str]:
        filas = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        return [f[0] for f in filas]

    def resumen(self) -> Dict[str, Any]:
        with self._conectar() as conn:
            tablas = [{"nombre": n, "filas": conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]}
                      for n in self._nombres_tablas(conn)]
        return {"ruta": self.db_path, "tablas": tablas}

    def leer_tabla(self, nombre: str, limite: int = 200) -> Dict[str, Any]:
        limite = max(1, min(int(limite), LIMITE_MAXIMO))
        with self._conectar() as conn:
            if nombre not in self._nombres_tablas(conn):
                raise ValueError(f"La tabla '{nombre}' no existe.")
            cur = conn.execute(f'SELECT * FROM "{nombre}" LIMIT ?', (limite,))
            columnas = [d[0] for d in cur.description]
            filas = [list(f) for f in cur.fetchall()]
            total = conn.execute(f'SELECT COUNT(*) FROM "{nombre}"').fetchone()[0]
        return {"tabla": nombre, "columnas": columnas, "filas": filas, "total": total, "limite": limite}
