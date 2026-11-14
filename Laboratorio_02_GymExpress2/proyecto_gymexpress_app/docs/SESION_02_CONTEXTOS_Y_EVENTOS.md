# Sesión 2 (Primer Parcial): descomposición del monolito y eventos CNCF CloudEvents v1.0
**Proyecto:** GymExpress (adaptación de FarmaExpress) · **Asignatura:** Ingeniería de Software 3 [IF0129]

## 1. Qué se pidió y qué se hizo

| La guía pide | Equivalente en GymExpress | Dónde está |
|---|---|---|
| Analizar el acoplamiento de `crear_pedido_monolito()` | `GimnasioService.crear_reserva_monolito()` | Cuaderno, Paso 1 |
| Separar el núcleo (Dispensación/Órdenes) del soporte (Catálogo/Precios) | Contexto **Reservas** (núcleo) y contexto **Catálogo** (soporte) | `src/contexto_reservas.py`, `src/contexto_catalogo.py` |
| Dataclass inmutable CloudEvents v1.0 con serialización | `CloudEvent` congelado, con validación estricta y JSON ida y vuelta | `src/events.py` |
| EventBus asíncrono no bloqueante (`queue.Queue` + hilos daemon) | `InMemoryEventBus` | `src/event_bus.py` |
| Notificar a los suscriptores | Consumidores idempotentes: auditoría, notificaciones, alertas | `src/consumidores.py` |
| Tests base en verde | Los 10 tests base siguen intactos y en verde | `tests/test_gymexpress.py` |
| Cuaderno ejecutado con reflexiones y autograder en verde | Cuaderno con ambos oráculos en 5.0 / 5.0 | `02_Laboratorio_02_…ipynb` |

## 2. Cómo está organizado (Bounded Contexts)

```
           Interfaz web ──► SagaOrquestadorReserva ──► GimnasioService (fachada)
                                                         │            │
                              ┌──────────────────────────┘            └──────────────┐
                              ▼                                                      ▼
                  CONTEXTO RESERVAS (núcleo)                        CONTEXTO CATÁLOGO (soporte)
                  contexto_reservas.py                              contexto_catalogo.py
                              │  usa el PUERTO ICatalogoPort  ◄── lo implementa ──────┘
                              │
                              └──► publica CloudEvents por el puerto IEventPublisher ◄──── también el Catálogo
                                                         │
                                                         ▼
                                       InMemoryEventBus (cola + hilos daemon)
                                                         │ despacha en segundo plano
                                                         ▼
                              Consumidores: AuditoriaEventos · NotificadorSocios
```

Reglas de frontera (las verifica `auditoria_metricas.py`, 13 de 13 reglas se cumplen):
1. Los dos contextos **no se importan entre sí**; Reservas solo conoce el puerto `ICatalogoPort`.
2. Ningún contexto importa el bus concreto: usan `IEventPublisher` (el cableado ocurre en `app.py`).
3. `events.py` no depende de ningún otro módulo (es el contrato estable).
4. No hay dependencias circulares.

**Qué es síncrono y qué es asíncrono.** Reservar el cupo sigue siendo síncrono (por el puerto, con un `UPDATE` atómico), porque debe ser consistente. Todo lo secundario (avisos, auditoría, alertas) viaja por eventos y no hace esperar al cliente.

## 3. Catálogo de eventos (`co.edu.uniremington.gymexpress.…`)

| Tipo | Origen (`source`) | Lo publica | Lo consumen |
|---|---|---|---|
| `reserva.creada` (también queda en el Outbox) | `/gymexpress/reservas` | Reservas | Auditoría |
| `reserva.confirmada` | `/gymexpress/reservas` | Reservas (Saga) | Auditoría, Notificador |
| `reserva.compensada` | `/gymexpress/reservas` | Reservas (Saga) | Auditoría, Notificador |
| `cupos.reservados` / `cupos.liberados` | `/gymexpress/catalogo` | Catálogo | Auditoría |
| `servicio.cupos_bajos` (≤ 3 cupos) | `/gymexpress/catalogo` | Catálogo | Auditoría, Notificador |
| `insumo.stock_bajo` | `/gymexpress/insumos` | Servicio de insumos | Auditoría, Notificador |

## 4. Decisiones frente al código de referencia de la guía

- `CloudEvent` **inmutable** (`frozen=True` y `data` de solo lectura): la rúbrica pide payload inmutable.
- `time` en **RFC 3339** (texto), como define la especificación, en lugar de `float`.
- `to_dict()` **sin efectos secundarios** (la referencia modificaba el evento).
- El bus **no traga errores** (la versión base usaba `except Exception: pass`): registra en log y en *dead-letter*, y un suscriptor defectuoso no afecta a los demás.
- Cola **acotada**: si se llena, `publicar()` rechaza sin bloquear.
- **OCP:** el publicador es un parámetro opcional de `GimnasioService`; ninguna firma pública cambió. `crear_reserva_monolito` se conserva como alias.

## 5. Resultados medidos (`python3 medicion_eventos.py`)

Con 3 consumidores externos lentos de 50 ms (correo, facturación, inventario), cada uno recibe los 3 eventos de la reserva:

| Medida | Síncrono | Asíncrono |
|---|---|---|
| Respuesta de la reserva (servicio, media) | ≈ 466 ms | ≈ 9 ms |
| Respuesta HTTP real `POST /api/reservas/saga` (media) | ≈ 469 ms | ≈ 10 ms |
| `publicar()` p95 | - | ≈ 0,04 ms (límite de la guía: 5 ms) |

La respuesta HTTP es unas 45 veces más rápida (reducción cercana al 98 %). Las cifras varían unos milisegundos entre corridas.

## 6. Mejora adicional: sobreventa corregida
En la Actividad 1 se demostró que, con hilos, 40 clientes lograban 40 reservas sobre 10 cupos. Ahora el descuento de cupos es un `UPDATE … WHERE cupos >= cantidad` atómico y hay una prueba con 40 clientes simultáneos: se aceptan exactamente 10. También los ids de reserva son únicos (antes dos reservas en el mismo milisegundo podían chocar).

## 7. Cómo ejecutarlo
```bash
python3 main.py                                   # panel integrado: http://localhost:8086/panel (pestaña "Eventos")
python3 -m unittest discover -s tests -p "test_*.py"   # 62 pruebas
python3 -m unittest tests/test_gymexpress.py           # los 10 tests base (regla de gobierno)
python3 auditoria_metricas.py                      # 13 reglas de arquitectura
python3 medicion_eventos.py                        # T_sync frente a T_async
```
Variables de entorno solo para demostrar: `GYM_EVENTOS_MODO=sync|async` y `GYM_LATENCIA_CONSUMIDORES_MS=50`.

## 8. Limitaciones (para la sustentación)
- El bus es **en memoria**: si el proceso se cae, los eventos pendientes se pierden. El Outbox guarda el evento `reserva.creada`, pero **no hay todavía un relay** que lo republique.
- Los dos contextos **comparten el mismo archivo SQLite**. Es una etapa transitoria: no se importan ni leen las tablas del otro, pero el siguiente paso sería una base por contexto.
- Con varios workers, el orden entre eventos distintos no está garantizado (con `workers=1` sí).
- No hay autenticación ni cifrado de campos (los eventos solo llevan identificadores y totales).
