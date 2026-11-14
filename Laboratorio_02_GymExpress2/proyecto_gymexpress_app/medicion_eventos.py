"""
========================================================================================
MEDICIÓN DE LA GANANCIA ASÍNCRONA:   T_sync = sum(t_i)   -->   T_async = max(t_pub) <= 5 ms
Cátedra: Ingeniería de Software 3 [IF0129] - Corporación Universitaria Remington
Sesión 2 (Primer Parcial). Cuantifica, con el código real de GymExpress, cuánto tarda la respuesta
de una reserva cuando los consumidores de eventos (correo, facturación, inventario externo) son
lentos, comparando el despacho SÍNCRONO (mismo hilo) con el EventBus ASÍNCRONO.

  Parte A (en proceso): GimnasioService + Saga con consumidores de `latencia` ms cada uno.
  Parte B (HTTP real):  dos servidores (GYM_EVENTOS_MODO=sync / async) y clientes POST /api/reservas/saga.

Uso:   python3 medicion_eventos.py [--latencia-ms 50] [--n 15] [--json docs/resultados_eventos.json]
Dependencias: NINGUNA (Python Standard Library)
========================================================================================
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid

import prueba_carga as pc

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONSUMIDORES = ("correo", "facturacion", "inventario_externo")


def resumen(lat):
    return {"media": round(statistics.mean(lat), 1), "p50": round(pc.percentil(lat, 50), 1),
            "p95": round(pc.percentil(lat, 95), 1), "max": round(max(lat), 1)}


def parte_a(latencia_ms, n):
    """Mide el servicio directamente (sin HTTP)."""
    sys.path.insert(0, BASE_DIR)
    from src.repositories import SQLiteServicioRepository, SQLiteReservaRepository, SQLiteOutboxRepository
    from src.services import GimnasioService, PasarelaPagosMock, SagaOrquestadorReserva
    from src.event_bus import InMemoryEventBus, PublicadorSincrono
    from src.consumidores import ConsumidorExternoSimulado

    salida = {}
    for modo in ("sincrono", "asincrono"):
        tmp = tempfile.mkdtemp(prefix="gym_ev_")
        db = os.path.join(tmp, "t.db")
        bus = PublicadorSincrono() if modo == "sincrono" else InMemoryEventBus(workers=4)
        for nombre in CONSUMIDORES:
            bus.suscribir("*", ConsumidorExternoSimulado(nombre, latencia_ms / 1000))
        tiempos_publicar = []
        publicar_original = bus.publicar

        def medido(ev, _orig=publicar_original):
            t0 = time.perf_counter()
            r = _orig(ev)
            tiempos_publicar.append((time.perf_counter() - t0) * 1000)
            return r

        bus.publicar = medido
        servicios = SQLiteServicioRepository(db)
        svc = GimnasioService(servicios, SQLiteReservaRepository(db), SQLiteOutboxRepository(db), event_publisher=bus)
        saga = SagaOrquestadorReserva(svc, PasarelaPagosMock())
        servicios.actualizar_cupos("GYM-002", 10 ** 6)
        lat = []
        for _ in range(n):
            t0 = time.perf_counter()
            saga.ejecutar_saga_reserva("1098765432", "Medicion", "300", [{"codigo": "GYM-002", "cantidad": 1}],
                                       "MED-" + uuid.uuid4().hex)
            lat.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        bus.esperar_entrega(30)
        drenar = (time.perf_counter() - t0) * 1000
        if hasattr(bus, "detener"):
            bus.detener()
        salida[modo] = {"respuesta_saga_ms": resumen(lat), "publicar_ms": {"media": round(statistics.mean(tiempos_publicar), 3),
                        "p95": round(pc.percentil(tiempos_publicar, 95), 3), "max": round(max(tiempos_publicar), 3)},
                        "eventos_por_saga": round(len(tiempos_publicar) / n, 1), "espera_final_consumidores_ms": round(drenar, 1)}
        shutil.rmtree(tmp, ignore_errors=True)
    return salida


def levantar(modo, latencia_ms, tmp):
    destino = os.path.join(tmp, modo)
    shutil.copytree(BASE_DIR, destino, ignore=shutil.ignore_patterns("gymexpress.db*", "gymexpress_respaldo*", "__pycache__", "*.pyc"))
    puerto = pc.puerto_libre()
    codigo = ("import sys; sys.path.insert(0, '.');"
              "from src.app import run_server, servicio_repo;"
              "servicio_repo.actualizar_cupos('GYM-002', 10**6);"
              f"run_server(port={puerto})")
    entorno = dict(os.environ, GYM_EVENTOS_MODO=modo, GYM_LATENCIA_CONSUMIDORES_MS=str(latencia_ms))
    proc = subprocess.Popen([sys.executable, "-c", codigo], cwd=destino, env=entorno,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import socket
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", puerto), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return proc, puerto


def parte_b(latencia_ms, n):
    """Mide el endpoint HTTP real con cada modo de eventos."""
    salida = {}
    tmp = tempfile.mkdtemp(prefix="gym_ev_http_")
    try:
        for modo in ("sync", "async"):
            proc, puerto = levantar(modo, latencia_ms, tmp)
            try:
                lat = []
                for _ in range(n):
                    ms, estado = pc.peticion(puerto, "POST", "/api/reservas/saga", {
                        "socio_id": "1098765432", "socio_nombre": "Medicion", "contacto": "300",
                        "items": [{"codigo": "GYM-002", "cantidad": 1}], "idempotency_key": "HTTP-" + uuid.uuid4().hex})
                    if estado == 200:
                        lat.append(ms)
                time.sleep(latencia_ms * 12 / 1000)          # deja drenar a los consumidores antes de leer métricas
                _, estado = pc.peticion(puerto, "GET", "/api/eventos/metricas")
                salida["sincrono" if modo == "sync" else "asincrono"] = {"respuesta_http_ms": resumen(lat), "solicitudes_ok": len(lat)}
            finally:
                proc.terminate()
                proc.wait(timeout=10)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return salida


def main():
    import logging
    logging.disable(logging.CRITICAL)          # solo se imprimen las tablas de resultados
    latencia = float(sys.argv[sys.argv.index("--latencia-ms") + 1]) if "--latencia-ms" in sys.argv else 50.0
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 15
    print("=" * 96)
    print(f"GANANCIA ASÍNCRONA — {len(CONSUMIDORES)} consumidores externos de {latencia:g} ms cada uno, {n} reservas por modo")
    print("=" * 96)
    a = parte_a(latencia, n)
    print("PARTE A · servicio en proceso (respuesta de la Saga)")
    print(f"  {'Modo':<11}{'media ms':>10}{'p50 ms':>9}{'p95 ms':>9}{'máx ms':>9}   {'publicar() p95':>15}{'publicar() máx':>16}{'eventos/saga':>14}")
    for modo, d in a.items():
        r, p = d["respuesta_saga_ms"], d["publicar_ms"]
        print(f"  {modo:<11}{r['media']:>10}{r['p50']:>9}{r['p95']:>9}{r['max']:>9}   {p['p95']:>13} ms{p['max']:>14} ms{d['eventos_por_saga']:>14}")
    b = parte_b(latencia, n)
    print("\nPARTE B · endpoint HTTP real POST /api/reservas/saga")
    print(f"  {'Modo':<11}{'media ms':>10}{'p50 ms':>9}{'p95 ms':>9}{'máx ms':>9}")
    for modo, d in b.items():
        r = d["respuesta_http_ms"]
        print(f"  {modo:<11}{r['media']:>10}{r['p50']:>9}{r['p95']:>9}{r['max']:>9}")
    mejora = b["sincrono"]["respuesta_http_ms"]["media"] / b["asincrono"]["respuesta_http_ms"]["media"]
    reduccion = 100 * (1 - b["asincrono"]["respuesta_http_ms"]["media"] / b["sincrono"]["respuesta_http_ms"]["media"])
    print(f"\n  => Con consumidores lentos, la respuesta HTTP es {mejora:.1f}x más rápida (reducción de {reduccion:.0f} %).")
    if "--json" in sys.argv:
        destino = sys.argv[sys.argv.index("--json") + 1]
        os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
        with open(destino, "w", encoding="utf-8") as fh:
            json.dump({"latencia_consumidor_ms": latencia, "consumidores": len(CONSUMIDORES), "n": n,
                       "parte_a": a, "parte_b": b, "mejora_http_x": round(mejora, 1), "reduccion_http_pct": round(reduccion)},
                      fh, ensure_ascii=False, indent=2)
        print(f"JSON guardado en {destino}")


if __name__ == "__main__":
    main()
