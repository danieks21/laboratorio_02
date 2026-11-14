"""
Prueba de configuración del servidor HTTP (mejora incremental de la Actividad 1).
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from http.server import HTTPServer, ThreadingHTTPServer
from src.app import GymExpressServer


class TestServidor(unittest.TestCase):
    def test_cola_de_conexiones_ampliada(self):
        self.assertGreaterEqual(GymExpressServer.request_queue_size, 128)
        self.assertGreater(GymExpressServer.request_queue_size, HTTPServer.request_queue_size)

    def test_sigue_siendo_monohilo_mientras_el_stock_no_sea_atomico(self):
        # Con hilos las reservas pueden sobrevender cupos (ver experimento_escalamiento.py).
        # Si algún día se cambia a ThreadingHTTPServer, primero hay que volver atómico el descuento de cupos.
        self.assertFalse(issubclass(GymExpressServer, ThreadingHTTPServer))


class TestPanelIntegrado(unittest.TestCase):
    def test_ruta_panel_devuelve_las_pestanas(self):
        import io
        import shutil
        import tempfile
        from src.app_extras import ExtrasRouter

        class HandlerFalso:
            def __init__(self):
                self.estado, self.cabeceras, self.wfile = None, {}, io.BytesIO()
            def send_response(self, codigo): self.estado = codigo
            def send_header(self, k, v): self.cabeceras[k] = v
            def end_headers(self): pass

        carpeta = tempfile.mkdtemp()
        try:
            router = ExtrasRouter(os.path.join(carpeta, "t.db"))
            h = HandlerFalso()
            self.assertTrue(router.manejar_get(h, "/panel", ""))
            cuerpo = h.wfile.getvalue().decode("utf-8")
            self.assertEqual(h.estado, 200)
            for ruta in ('src="/"', 'src="/usuario"', 'src="/gestion"', 'src="/basedatos"'):
                self.assertIn(ruta, cuerpo)
        finally:
            shutil.rmtree(carpeta, ignore_errors=True)


class TestMismaPestana(unittest.TestCase):
    def test_ninguna_pagina_abre_ventanas_nuevas(self):
        """Todas las páginas deben abrirse en la misma pestaña: sin target=_blank ni window.open."""
        from src.app import HTML_DASHBOARD
        from src import pages_extra
        paginas = {"/": HTML_DASHBOARD, "/usuario": pages_extra.PORTAL_USUARIO_HTML,
                   "/gestion": pages_extra.PANEL_GESTION_HTML, "/basedatos": pages_extra.BASEDATOS_HTML,
                   "/panel": pages_extra.PANEL_INTEGRADO_HTML, "/eventos": pages_extra.EVENTOS_HTML}
        for ruta, contenido in paginas.items():
            with self.subTest(pagina=ruta):
                self.assertNotIn('target="_blank"', contenido)
                self.assertNotIn("target='_blank'", contenido)
                self.assertNotIn("window.open(", contenido)

    def test_panel_incluye_la_base_de_datos_como_pestana(self):
        from src import pages_extra
        self.assertIn('data-target="basedatos"', pages_extra.PANEL_INTEGRADO_HTML)
        self.assertIn('id="basedatos"', pages_extra.PANEL_INTEGRADO_HTML)


class TestSintaxis(unittest.TestCase):
    def test_todos_los_archivos_python_compilan(self):
        """Red de seguridad: ningún .py del proyecto (incluido main.py) debe tener errores de sintaxis."""
        for carpeta, _, archivos in os.walk(BASE_DIR):
            if any(parte in carpeta for parte in ("__pycache__", ".git")):
                continue
            for nombre in archivos:
                if nombre.endswith(".py"):
                    ruta = os.path.join(carpeta, nombre)
                    with open(ruta, encoding="utf-8") as fh:
                        compile(fh.read(), ruta, "exec")      # SyntaxError si el archivo está roto


if __name__ == "__main__":
    unittest.main(verbosity=2)
