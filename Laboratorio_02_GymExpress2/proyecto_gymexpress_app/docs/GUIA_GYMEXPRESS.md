# 🏋️ GYMEXPRESS MVP — Adaptación de FarmaExpress a un gimnasio
**Asignatura:** [IF0129] Ingeniería de Software 3 | Corporación Universitaria Remington
**Tecnología:** Python 3.10+ estándar, SQLite (WAL), servidor `http.server`. Cero librerías externas.

## Ejecución
```bash
python3 main.py                              # http://localhost:8086
python3 -m unittest tests/test_gymexpress.py # 10 tests, todos deben pasar (OK)
```

## Mapeo FarmaExpress → GymExpress
| FarmaExpress | GymExpress |
|---|---|
| `Producto` / `stock_disponible` / `requiere_receta` | `Servicio` / `cupos_disponibles` / `requiere_valoracion` |
| `Pedido`, `ItemPedido`, `EstadoPedido` | `Reserva`, `ItemReserva`, `EstadoReserva` |
| `cliente_*`, `direccion` | `socio_*`, `contacto` |
| `IProductoRepository`, `IPedidoRepository` | `IServicioRepository`, `IReservaRepository` |
| `FarmaciaService` | `GimnasioService` |
| `SagaOrquestadorMatriculaPedido` | `SagaOrquestadorReserva` |
| `RESERVADO_SEMANTIC_LOCK` | `CUPO_RESERVADO_SEMANTIC_LOCK` |
| `/api/productos`, `/api/pedidos`, `/api/pedidos/saga` | `/api/servicios`, `/api/reservas`, `/api/reservas/saga` |

## Catálogo semilla
GYM-001 Membresía Mensual · GYM-002 Membresía Trimestral · GYM-003 Spinning 6:00 pm · GYM-004 Funcional 7:00 am · GYM-005 Entrenamiento Personalizado.

## Cambios respecto al código base
1. `ValidationError` ahora se propaga desde la Saga y la capa web responde HTTP 422 (antes la Saga la capturaba y respondía 200 con `exito: false`).
2. Los repositorios reconstruyen el agregado con un único método (`_fila_a_reserva`) en lugar de repetir el código en cada consulta.
3. El dashboard escapa el HTML de los datos que muestra (`esc()`) y el log de la Saga usa `textContent`.
4. El límite por renglón pasó de 500 (venta minorista) a 10 (cupos por reserva).

---

# Módulo extensión: entrenadores, suplementos, limpieza y elementos de uso

Se añadió **sin modificar** el flujo de reservas. Solo se tocaron 3 puntos de enganche: 1 línea de import y 1 de composición en `app.py`, 1 `if` en `do_GET` y 1 en `do_POST`, más 1 línea informativa en `main.py`.

## Espacios nuevos
| URL | Para quién | Qué hace |
|---|---|---|
| `/` | Administración | Reservas con Saga (sin cambios) |
| `/usuario` | Socio | Ver entrenadores y horarios, registrar consumo de suplementos (con precios), pedir y devolver elementos |
| `/gestion` | Personal | Insumos de limpieza (uso, reposición, alerta de stock mínimo), préstamos activos, consumos, alta de entrenadores y horarios |

## Archivos nuevos (uno por responsabilidad)
`models_extra.py` · `interfaces_extra.py` · `repositories_extra.py` · `services_extra.py` · `validators_extra.py` · `app_extras.py` (rutas) · `pages_extra.py` (HTML) · `tests/test_extras.py`

## Tablas nuevas (independientes de las de reservas)
`entrenadores`, `horarios`, `suplementos`, `consumos_suplemento`, `insumos_limpieza`, `movimientos_insumo`, `elementos_prestables`, `prestamos`.

## API
| Método y ruta | Uso |
|---|---|
| `GET /api/entrenadores` | Entrenadores con sus horarios |
| `GET /api/suplementos` | Catálogo con precios y stock |
| `POST /api/suplementos/consumo` | `{socio_id, socio_nombre, codigo, cantidad, idempotency_key}` |
| `GET /api/suplementos/consumos?socio_id=` | Consumos de un socio |
| `GET /api/elementos` | Elementos prestables y disponibilidad |
| `POST /api/elementos/prestamo` / `devolucion` | Prestar y devolver |
| `GET /api/elementos/prestamos?socio_id=` | Préstamos de un socio |
| `GET /api/gestion/insumos`, `movimientos`, `prestamos-activos`, `consumos` | Consultas internas |
| `POST /api/gestion/insumos/movimiento` | `{codigo, tipo: USO\|REPOSICION, cantidad, motivo}` |
| `POST /api/gestion/entrenadores`, `/api/gestion/horarios` | Altas |

## Reglas de negocio
- Suplementos: máximo 5 unidades por registro; idempotencia por `idempotency_key`; el stock nunca queda negativo.
- Préstamos: máximo 3 unidades por elemento y socio; solo el dueño puede devolver; no se devuelve dos veces.
- Insumos: no se permite stock negativo; alerta cuando `stock_actual <= stock_minimo`.
- Horarios: formato `HH:MM`, fin posterior al inicio y sin cruces para un mismo entrenador y día.

## Atomicidad
Consumo de suplemento, préstamo, devolución y movimiento de insumo usan **una sola transacción SQLite** (descuento de inventario + registro del historial), con un `UPDATE ... WHERE stock >= cantidad` que evita la sobreventa incluso con peticiones simultáneas.

## Datos de ejemplo (editables)
Los nombres de entrenadores, precios (COP) y cantidades son de ejemplo. Los entrenadores y horarios se cambian desde `/gestion`; los precios y el stock se editan en `repositories_extra.py` (sección `seed`) antes de la primera ejecución, o borrando `gymexpress.db` para regenerarla.

## Pruebas
```bash
python3 -m unittest discover -s tests -p "test_*.py"   # 24 pruebas (10 de reservas + 14 del módulo extensión)
```

---

# Datos reales del gimnasio y visor de la base de datos

## Datos cargados
- **Entrenadores:** Luis Henrique, Carlos Pasos. **Administración:** Roman Tercero.
- **Horario:** lunes a sábado 5:00 a. m.–1:00 p. m. y 2:00 p. m.–9:30 p. m.; festivos medio día; domingos cerrado (supuesto).
- **Suplementos (COP):** Pre entreno 1 scoop $1.000 · tarro 200 g $80.000 · Proteína 1 scoop $2.500 · paquete 2 lb $90.000 · Creatina 1 scoop $3.000 · tarro 600 g $150.000 · Agua en botella $2.000.
- **Objetos prestables:** Colchonetas 5 · Apoyo (cojín) para barra 3 · Ligas 4 · Seguros 8 · Cinturones 4 · Rodilleras 3.
- **Limpieza:** 10 insumos básicos (desinfectante, alcohol, toallas de papel, bolsas de basura, limpiador de colchonetas, jabón de manos, escoba, trapero, limpiavidrios, guantes de aseo).
- Los **stocks** de suplementos y limpieza son valores de partida: se corrigen en `/gestion`.

## Dónde está la base de datos
Un único archivo SQLite, **`gymexpress.db`**, en la carpeta del proyecto. Se crea sola al ejecutar `python3 main.py` y es la misma que usan todas las páginas.

## Cómo verla
| Forma | Cómo |
|---|---|
| En el navegador | `http://localhost:8086/basedatos` (todas las tablas, solo lectura) |
| En la terminal | `python3 ver_bd.py` (o `python3 ver_bd.py suplementos`) |
| Con programa externo | Abrir `gymexpress.db` con DB Browser for SQLite |

## Reiniciar con los datos iniciales
Si ya habías ejecutado una versión anterior, la base conserva los datos de ejemplo viejos. Con el servidor detenido: `python3 reiniciar_bd.py` (guarda un respaldo y elimina la base), luego `python3 main.py`.

## Pruebas
`python3 -m unittest discover -s tests -p "test_*.py"` → 32 pruebas.

---

# Actividad 1: auditoría arquitectónica (scripts y artefactos)

Todo usa solo la biblioteca estándar de Python (sin `pip install`). Se verificó con un análisis de los 25 archivos `.py`: ninguna importación externa.

| Entregable | Artefacto | Cómo ejecutarlo |
|---|---|---|
| 1. Modelo C4 (niveles 1, 2 y 3) | `docs/c4/*.puml` y `*.png` | Regenerar imágenes (opcional, requiere Java): `java -jar plantuml.jar -tpng docs/c4/*.puml` |
| 2. Métricas de Martin (Ca, Ce, I, A, D) y reglas SoD/DIP | `auditoria_metricas.py` | `python3 auditoria_metricas.py --json docs/auditoria_metricas.json` |
| 3. Latencia P99 y cuellos de botella | `prueba_carga.py` | `python3 prueba_carga.py --json docs/resultados_carga.json` |
| 3. Comparación de configuraciones del servidor y prueba de sobreventa | `experimento_escalamiento.py` | `python3 experimento_escalamiento.py --json docs/resultados_experimento.json` |
| Evidencia | `docs/capturas/`, `docs/graficas/`, `docs/evidencia/` | - |

Los scripts de carga trabajan sobre una copia temporal: no modifican `gymexpress.db`.

## Cambios de esta etapa
1. `src/db.py`: `abrir_conexion` (transacción + cierre garantizado). Todos los repositorios la usan.
2. `src/app.py`: `GymExpressServer` con `request_queue_size = 128` (antes 5: P99 de ~1 s y conexiones rechazadas con 10 o más clientes).
3. `main.py`: corregido el mensaje de pruebas.
4. Pruebas: 36 en total (`tests/test_servidor.py` añade la cola del servidor y la compilación de todos los archivos).

## Advertencia de diseño
No cambiar a `ThreadingHTTPServer` mientras el descuento de cupos no sea atómico: el experimento mostró sobreventa (40 reservas aceptadas con 10 cupos).

---

# Panel integrado y navegación en una sola pestaña

- **`/panel`** (es la página que abre `main.py`): reúne en pestañas Reservas, Portal del socio, Gestión e inventario y Base de datos. Cada pestaña actualiza sus datos al abrirse.
- Ninguna página abre ventanas nuevas: no hay `target="_blank"` ni `window.open`. Una prueba automática lo vigila (`tests/test_servidor.py`) y `docs/evidencia/verificacion_misma_pestana.txt` registra la comprobación con un navegador real.
- Dentro del panel, las páginas ocultan su barra de enlaces (las pestañas la reemplazan). Fuera del panel, los enlaces de la barra navegan en la misma pestaña e incluyen "Panel integrado".
- Nota: al ejecutar `python3 main.py`, el navegador decide si abre una pestaña nueva o reutiliza una existente; si ya tienes `localhost:8086` abierto, basta con recargarlo.
- Pruebas: 39 en total.

---

# Sesión 2 (Primer Parcial): Bounded Contexts y eventos CloudEvents v1.0

Resumen completo en `docs/SESION_02_CONTEXTOS_Y_EVENTOS.md`.

- Contextos: `src/contexto_reservas.py` (núcleo) y `src/contexto_catalogo.py` (soporte), unidos solo por el puerto `ICatalogoPort`.
- Eventos: `src/events.py` (CloudEvents v1.0 inmutable), `src/event_bus.py` (bus asíncrono), `src/consumidores.py`.
- Monitor: pestaña **Eventos** del panel (`/eventos`, `/api/eventos`, `/api/eventos/metricas`).
- Medición: `python3 medicion_eventos.py`. Cuaderno: `02_Laboratorio_02_Primer_Parcial_Monolito_Microservicios_Uniremington.ipynb`.
- Pruebas: 62 (los 10 tests base siguen en verde).
