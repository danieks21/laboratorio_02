"""
========================================================================================
CAPA WEB Y CONTROLADOR HTTP NATIVO (PYTHON HTTP.SERVER - CERO DEPENDENCIAS)
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
Provee API REST + Dashboard Web interactivo. No contiene lógica de negocio ni SQL (SoD).
========================================================================================
"""
import os
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from src.repositories import SQLiteServicioRepository, SQLiteReservaRepository, SQLiteOutboxRepository
from src.services import GimnasioService, PasarelaPagosMock, SagaOrquestadorReserva
from src.validators import ValidationError
from src.app_extras import ExtrasRouter
from src.event_bus import InMemoryEventBus, PublicadorSincrono
from src.consumidores import AuditoriaEventos, NotificadorSocios, ConsumidorExternoSimulado, registrar_consumidores
from src.logger import get_logger

logger = get_logger("HTTP_Server")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gymexpress.db")

# Composición de dependencias (Composition Root)
servicio_repo = SQLiteServicioRepository(DB_PATH)
reserva_repo = SQLiteReservaRepository(DB_PATH)
outbox_repo = SQLiteOutboxRepository(DB_PATH)
pasarela = PasarelaPagosMock()

# --- Bus de eventos (Sesión 2). Variables de entorno solo para medir y demostrar (ver medicion_eventos.py):
#     GYM_EVENTOS_MODO = async (por defecto) | sync      GYM_LATENCIA_CONSUMIDORES_MS = latencia de cada consumidor externo simulado
_modo_eventos = os.environ.get("GYM_EVENTOS_MODO", "async").strip().lower()
_latencia_ms = float(os.environ.get("GYM_LATENCIA_CONSUMIDORES_MS", "0") or 0)
event_bus = PublicadorSincrono() if _modo_eventos == "sync" else InMemoryEventBus()
auditoria_eventos = AuditoriaEventos()
notificador_socios = NotificadorSocios()
registrar_consumidores(event_bus, auditoria_eventos, notificador_socios)
if _latencia_ms > 0:                       # simula sistemas externos lentos (correo, facturación, inventario)
    for _nombre in ("correo", "facturacion", "inventario_externo"):
        event_bus.suscribir("*", ConsumidorExternoSimulado(_nombre, _latencia_ms / 1000.0))

gimnasio_service = GimnasioService(servicio_repo, reserva_repo, outbox_repo, event_publisher=event_bus)
saga_orquestador = SagaOrquestadorReserva(gimnasio_service, pasarela)
extras_router = ExtrasRouter(DB_PATH, publisher=event_bus, bus=event_bus,
                             auditoria=auditoria_eventos, notificador=notificador_socios)  # Módulo extensión

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GymExpress MVP — Ingeniería de Software 3 | Uniremington</title>
    <style>
        :root {
            --bg-dark: #111418;
            --surface: #1B2027;
            --primary: #F97316;
            --success: #10B981;
            --warning: #F59E0B;
            --danger: #EF4444;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --border: #2F3744;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        body { background: var(--bg-dark); color: var(--text-main); padding: 20px; line-height: 1.5; }
        .container { max-width: 1200px; margin: 0 auto; }
        header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid var(--border); padding-bottom: 15px; margin-bottom: 25px; flex-wrap: wrap; gap: 10px; }
        .brand { font-size: 1.5rem; font-weight: bold; color: var(--primary); }
        .badge { background: #20262F; border: 1px solid var(--border); padding: 5px 12px; border-radius: 20px; font-size: 0.8rem; color: var(--text-muted); }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
        .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 20px; overflow-x: auto; }
        .card-header { font-size: 1.1rem; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid var(--border); padding-bottom: 8px; color: #FDBA74; }
        table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid var(--border); }
        th { color: var(--text-muted); font-weight: 600; }
        .btn { background: var(--primary); color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: bold; transition: 0.2s; }
        .btn:hover { opacity: 0.9; }
        .status-pill { padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: bold; display: inline-block; }
        .status-COMPLETADO { background: rgba(16, 185, 129, 0.2); color: var(--success); }
        .status-COMPENSADO { background: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .status-CUPO_RESERVADO_SEMANTIC_LOCK { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .terminal { background: #07090C; border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-family: monospace; font-size: 0.8rem; color: #FDBA74; max-height: 220px; overflow-y: auto; white-space: pre-wrap; }
        .input-group { margin-bottom: 12px; }
        .input-group label { display: block; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 4px; }
        .input-group input, .input-group select { width: 100%; padding: 8px; background: #0D1015; border: 1px solid var(--border); border-radius: 6px; color: white; font-size: 0.85rem; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <div class="brand">🏋️ GymExpress MVP</div>
                <div style="font-size: 0.85rem; color: var(--text-muted);">Reservas y membresías · Transacciones ACID & Orquestador Saga</div>
            </div>
            <div class="badge">Uniremington — Ing. de Software 3 [IF0129]</div>
        </header>

        <div class="grid">
            <div>
                <div class="card">
                    <div class="card-header">📋 Catálogo de Servicios (Cupos en Tiempo Real)</div>
                    <table>
                        <thead>
                            <tr><th>Código</th><th>Servicio</th><th>Precio</th><th>Cupos</th><th>Acción</th></tr>
                        </thead>
                        <tbody id="catalogo-body"></tbody>
                    </table>
                </div>

                <div class="card">
                    <div class="card-header">🧾 Simulador de Reserva Transaccional (Saga Flow)</div>
                    <form id="form-reserva">
                        <div class="input-group">
                            <label>Documento del Socio:</label>
                            <input type="text" id="soc-id" value="1098765432" required>
                        </div>
                        <div class="input-group">
                            <label>Nombre del Socio:</label>
                            <input type="text" id="soc-nombre" value="Daniel Pérez" required>
                        </div>
                        <div class="input-group">
                            <label>Contacto (teléfono o correo):</label>
                            <input type="text" id="soc-contacto" value="3001234567" required>
                        </div>
                        <div class="input-group">
                            <label>Servicio a Reservar:</label>
                            <select id="res-serv-select"></select>
                        </div>
                        <div class="input-group">
                            <label>Cantidad (cupos / sesiones):</label>
                            <input type="number" id="res-cant" value="1" min="1" max="10">
                        </div>
                        <div class="input-group" style="margin-top: 15px;">
                            <label style="color: var(--warning); font-weight: bold; cursor: pointer;">
                                <input type="checkbox" id="check-simular-falla" style="width:auto;"> 🚨 Simular Falla en Pasarela de Pagos (Disparar Compensación C1)
                            </label>
                        </div>
                        <button type="submit" class="btn" style="width: 100%; padding: 10px; margin-top: 5px;">🚀 Ejecutar Transacción (T1 → T2 → T3)</button>
                    </form>
                </div>
            </div>

            <div>
                <div class="card">
                    <div class="card-header">🔄 Trazabilidad de la Máquina de Estados (Consola Saga)</div>
                    <div class="terminal" id="saga-log">> Sistema iniciado. Esperando reservas del gimnasio...</div>
                </div>

                <div class="card">
                    <div class="card-header">📦 Historial de Reservas y Estados</div>
                    <table>
                        <thead>
                            <tr><th>ID</th><th>Socio</th><th>Total</th><th>Estado</th></tr>
                        </thead>
                        <tbody id="reservas-body"></tbody>
                    </table>
                </div>

                <div class="card">
                    <div class="card-header">📬 Tabla Outbox Transaccional (Eventos Pendientes)</div>
                    <table>
                        <thead>
                            <tr><th>ID</th><th>Tipo Evento</th><th>Estado</th></tr>
                        </thead>
                        <tbody id="outbox-body"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
        function esc(s) {
            return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
        }

        async function cargarDatos() {
            const servs = await (await fetch('/api/servicios')).json();
            const catBody = document.getElementById('catalogo-body');
            const select = document.getElementById('res-serv-select');
            const seleccionado = select.value;
            catBody.innerHTML = '';
            select.innerHTML = '';
            servs.forEach(s => {
                catBody.innerHTML += `<tr>
                    <td><code>${esc(s.codigo)}</code></td>
                    <td><strong>${esc(s.nombre)}</strong><br><small style="color:var(--text-muted)">${esc(s.tipo)}</small></td>
                    <td>$${s.precio.toLocaleString()}</td>
                    <td style="color:${s.cupos_disponibles < 5 ? '#EF4444' : '#10B981'}; font-weight:bold;">${s.cupos_disponibles}</td>
                    <td><button class="btn" style="padding:4px 8px; font-size:0.75rem;" onclick="seleccionarServicio('${esc(s.codigo)}')">Elegir</button></td>
                </tr>`;
                select.innerHTML += `<option value="${esc(s.codigo)}">${esc(s.nombre)} ($${s.precio.toLocaleString()}) - Cupos: ${s.cupos_disponibles}</option>`;
            });
            if (seleccionado) select.value = seleccionado;

            const reservas = await (await fetch('/api/reservas')).json();
            const resBody = document.getElementById('reservas-body');
            resBody.innerHTML = '';
            reservas.forEach(r => {
                resBody.innerHTML += `<tr>
                    <td><code>${esc(r.id_reserva)}</code></td>
                    <td>${esc(r.socio_nombre)}</td>
                    <td>$${r.total.toLocaleString()}</td>
                    <td><span class="status-pill status-${esc(r.estado)}">${esc(r.estado)}</span></td>
                </tr>`;
            });

            const outbox = await (await fetch('/api/outbox')).json();
            const outBody = document.getElementById('outbox-body');
            outBody.innerHTML = '';
            outbox.forEach(o => {
                outBody.innerHTML += `<tr>
                    <td>#${o.id}</td>
                    <td><code style="font-size:0.75rem;">${esc(o.event_type)}</code></td>
                    <td><span style="color:#10B981;">✓ Capturado</span></td>
                </tr>`;
            });
        }

        function seleccionarServicio(cod) {
            document.getElementById('res-serv-select').value = cod;
        }

        document.getElementById('form-reserva').addEventListener('submit', async (e) => {
            e.preventDefault();
            const logBox = document.getElementById('saga-log');
            logBox.textContent = '> Iniciando Transacción Distribuida...\\n';

            const payload = {
                socio_id: document.getElementById('soc-id').value.trim(),
                socio_nombre: document.getElementById('soc-nombre').value.trim(),
                contacto: document.getElementById('soc-contacto').value.trim(),
                items: [{
                    codigo: document.getElementById('res-serv-select').value,
                    cantidad: parseInt(document.getElementById('res-cant').value)
                }],
                idempotency_key: 'IDEM-' + Date.now(),
                simular_falla: document.getElementById('check-simular-falla').checked
            };

            const res = await fetch('/api/reservas/saga', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            logBox.textContent = '';
            if (data.log) {
                data.log.forEach(l => { logBox.textContent += '> ' + l + '\\n'; });
            } else if (data.error) {
                logBox.textContent += '> ❌ ERROR: ' + data.error + '\\n';
            }

            await cargarDatos();
        });

        window.onload = cargarDatos;
    </script>
</body>
</html>
"""


def _reserva_a_dict(reserva) -> dict:
    """Serializa el agregado Reserva a un dict apto para JSON (solo presentación)."""
    d = reserva.__dict__.copy()
    d["estado"] = reserva.estado.value
    d["items"] = [it.__dict__ for it in reserva.items]
    return d


class GymExpressHTTPHandler(BaseHTTPRequestHandler):
    """
    Controlador HTTP Nativo (SoD - Plano de Presentación Web).
    Se encarga exclusivamente del parsing de solicitudes HTTP, enrutamiento,
    captura de errores de validación y serialización de respuestas JSON.
    """
    def log_message(self, format, *args):
        logger.debug(f"{self.address_string()} - {format % args}")

    def do_GET(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path

        if extras_router.manejar_get(self, path, url_parsed.query):
            return

        if path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))

        elif path == "/api/servicios":
            self._send_json([s.__dict__ for s in gimnasio_service.listar_catalogo()])

        elif path == "/api/reservas":
            self._send_json([_reserva_a_dict(r) for r in reserva_repo.listar_todos()])

        elif path == "/api/outbox":
            self._send_json(outbox_repo.obtener_pendientes())

        else:
            self.send_error(404, "Ruta no encontrada")

    def do_POST(self):
        if extras_router.manejar_post(self):
            return

        if self.path != "/api/reservas/saga":
            self.send_error(404, "Endpoint no soportado")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception as e:
            logger.error(f"Error parseando JSON de entrada: {e}")
            self._send_json({"exito": False, "error": f"JSON malformado: {str(e)}"}, status=400)
            return

        try:
            resultado = saga_orquestador.ejecutar_saga_reserva(
                socio_id=data.get("socio_id", ""),
                socio_nombre=data.get("socio_nombre", ""),
                contacto=data.get("contacto", ""),
                items_req=data.get("items", []),
                idempotency_key=data.get("idempotency_key", ""),
                simular_falla_pago=data.get("simular_falla", False)
            )

            res_json = {"exito": resultado["exito"], "log": resultado["log"]}
            if resultado.get("reserva"):
                res_json["reserva"] = _reserva_a_dict(resultado["reserva"])
            self._send_json(res_json)

        except ValidationError as ve:
            logger.warning(f"Error de validación defensiva en petición POST: {ve}")
            self._send_json({
                "exito": False,
                "error": str(ve),
                "campo": getattr(ve, "campo", ""),
                "log": [f"❌ Error de Validación: {str(ve)}"]
            }, status=422)

        except Exception as ex:
            logger.error(f"Error inesperado en ejecución de Saga: {ex}")
            self._send_json({
                "exito": False,
                "error": str(ex),
                "log": [f"🚨 Error Interno del Servidor: {str(ex)}"]
            }, status=500)

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


class GymExpressServer(HTTPServer):
    """
    Servidor HTTP con cola de conexiones ampliada.
    `http.server.HTTPServer` hereda `request_queue_size = 5` de socketserver: con 10 o más
    clientes simultáneos la cola se desborda y Linux retransmite el SYN al cabo de ~1 s,
    lo que disparaba el P99 a ~1000 ms y provocaba conexiones rechazadas (ver docs/resultados_experimento.json).
    Con 128 el mismo servidor de un solo hilo atiende 20 clientes sin errores.
    """
    request_queue_size = 128


def run_server(port: int = 8086):
    """Lanza el servidor HTTP nativo en el puerto especificado."""
    server = GymExpressServer(("0.0.0.0", port), GymExpressHTTPHandler)
    logger.info(f"🚀 Servidor GymExpress Web activo en: http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Deteniendo servidor GymExpress limpiamente...")
        server.server_close()
