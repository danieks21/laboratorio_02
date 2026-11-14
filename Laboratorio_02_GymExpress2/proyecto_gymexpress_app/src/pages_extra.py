"""
========================================================================================
PÁGINAS HTML DEL MÓDULO EXTENSIÓN (solo presentación, sin lógica de negocio)
  /usuario -> Portal del socio: entrenadores y horarios, suplementos, elementos prestables
  /gestion -> Panel interno: insumos de limpieza, préstamos activos, consumos, altas
Cátedra: Ingeniería de Software 3 [IF0129] - Uniremington
========================================================================================
"""

_ESTILO = r"""
    <style>
        :root { --bg:#111418; --surface:#1B2027; --primary:#F97316; --success:#10B981; --warning:#F59E0B;
                --danger:#EF4444; --text:#F8FAFC; --muted:#94A3B8; --border:#2F3744; }
        * { box-sizing:border-box; margin:0; padding:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
        body { background:var(--bg); color:var(--text); padding:20px; line-height:1.5; }
        .container { max-width:1200px; margin:0 auto; }
        header { display:flex; justify-content:space-between; align-items:center; border-bottom:2px solid var(--border);
                 padding-bottom:15px; margin-bottom:20px; flex-wrap:wrap; gap:10px; }
        .brand { font-size:1.5rem; font-weight:bold; color:var(--primary); }
        .nav a { color:var(--muted); text-decoration:none; font-size:.85rem; border:1px solid var(--border);
                 padding:5px 12px; border-radius:20px; margin-left:6px; }
        .nav a:hover { color:var(--text); border-color:var(--primary); }
        .grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
        @media (max-width:900px) { .grid { grid-template-columns:1fr; } }
        .card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:20px; margin-bottom:20px; overflow-x:auto; }
        .card-header { font-size:1.1rem; font-weight:bold; margin-bottom:15px; border-bottom:1px solid var(--border);
                       padding-bottom:8px; color:#FDBA74; }
        table { width:100%; border-collapse:collapse; font-size:.85rem; }
        th, td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--border); vertical-align:middle; }
        th { color:var(--muted); font-weight:600; }
        .btn { background:var(--primary); color:#fff; border:none; padding:7px 12px; border-radius:6px; cursor:pointer;
               font-size:.8rem; font-weight:bold; }
        .btn:hover { opacity:.9; }
        .btn-sec { background:#2F3744; }
        .field { margin-bottom:10px; }
        .field label { display:block; font-size:.8rem; color:var(--muted); margin-bottom:3px; }
        input, select { width:100%; padding:8px; background:#0D1015; border:1px solid var(--border); border-radius:6px;
                        color:#fff; font-size:.85rem; }
        td input[type=number] { width:64px; padding:5px; }
        .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
        .pill { padding:2px 9px; border-radius:12px; font-size:.75rem; font-weight:bold; display:inline-block; }
        .pill-ok { background:rgba(16,185,129,.2); color:var(--success); }
        .pill-bad { background:rgba(239,68,68,.2); color:var(--danger); }
        .pill-warn { background:rgba(245,158,11,.2); color:var(--warning); }
        .chip { display:inline-block; background:#0D1015; border:1px solid var(--border); border-radius:6px;
                padding:3px 8px; margin:2px 4px 2px 0; font-size:.78rem; }
        .entrenador { border-bottom:1px solid var(--border); padding:10px 0; }
        .entrenador:last-child { border-bottom:none; }
        .muted { color:var(--muted); font-size:.8rem; }
        #mensaje { position:sticky; top:8px; z-index:5; padding:10px 14px; border-radius:8px; margin-bottom:16px;
                   font-size:.9rem; display:none; }
        #mensaje.ok { display:block; background:rgba(16,185,129,.18); border:1px solid var(--success); }
        #mensaje.err { display:block; background:rgba(239,68,68,.18); border:1px solid var(--danger); }
    </style>
"""

_JS_COMUN = r"""
        const $ = id => document.getElementById(id);
        // Si la página está incrustada en el panel integrado, se oculta su barra de enlaces (las pestañas del panel la reemplazan).
        if (window.self !== window.top) { const nav = document.querySelector('.nav'); if (nav) nav.style.display = 'none'; }
        const DIAS = {LUNES:'Lunes',MARTES:'Martes',MIERCOLES:'Miércoles',JUEVES:'Jueves',VIERNES:'Viernes',SABADO:'Sábado',DOMINGO:'Domingo'};
        function esc(s) { return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
        function money(n) { return '$' + Number(n).toLocaleString('es-CO'); }
        function fecha(ts) { return ts ? new Date(ts * 1000).toLocaleString('es-CO') : '—'; }
        function nuevaKey(p) { return p + '-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8); }
        let timerMsg = null;
        function aviso(texto, ok) {
            const m = $('mensaje'); m.textContent = texto; m.className = ok ? 'ok' : 'err';
            clearTimeout(timerMsg); timerMsg = setTimeout(() => { m.className = ''; }, 6000);
        }
        async function api(url, body) {
            const opts = body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)};
            const r = await fetch(url, opts);
            const d = await r.json();
            return {ok: r.ok, data: d};
        }
        function horarioTexto(h) { return `${DIAS[h.dia] || h.dia} ${h.hora_inicio}–${h.hora_fin}`; }
        function hora12(hhmm) {
            const [h, m] = hhmm.split(':').map(Number);
            return `${h % 12 === 0 ? 12 : h % 12}:${String(m).padStart(2, '0')} ${h < 12 ? 'a. m.' : 'p. m.'}`;
        }
"""

PORTAL_USUARIO_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GymExpress — Portal del socio</title>
""" + _ESTILO + r"""
</head>
<body>
<div class="container">
    <header>
        <div>
            <div class="brand">🏋️ GymExpress · Portal del socio</div>
            <div class="muted">Entrenadores, horarios, suplementos y elementos para tu entrenamiento</div>
        </div>
        <div class="nav"><a href="/panel">Panel integrado</a><a href="/">Reservas</a><a href="/gestion">Panel interno</a><a href="/basedatos">Base de datos</a><a href="/eventos">Eventos</a></div>
    </header>

    <div id="mensaje"></div>

    <div class="card">
        <div class="card-header">👤 Tus datos</div>
        <div class="row">
            <div class="field"><label>Documento del socio</label><input id="soc-id" value="1098765432" oninput="cargarMio()"></div>
            <div class="field"><label>Nombre</label><input id="soc-nombre" value="Daniel Pérez"></div>
        </div>
    </div>

    <div class="grid">
        <div>
            <div class="card">
                <div class="card-header">🕒 Horario del gimnasio</div>
                <div id="horario-gym"></div>
            </div>
            <div class="card">
                <div class="card-header">🧑‍🏫 Entrenadores y horarios</div>
                <div id="entrenadores"></div>
            </div>
            <div class="card">
                <div class="card-header">🥤 Suplementos</div>
                <table>
                    <thead><tr><th>Producto</th><th>Precio</th><th>Disp.</th><th>Cant.</th><th></th></tr></thead>
                    <tbody id="suplementos"></tbody>
                </table>
            </div>
            <div class="card">
                <div class="card-header">🧾 Tus consumos de suplementos</div>
                <table>
                    <thead><tr><th>Fecha</th><th>Producto</th><th>Cant.</th><th>Total</th></tr></thead>
                    <tbody id="mis-consumos"></tbody>
                </table>
            </div>
        </div>
        <div>
            <div class="card">
                <div class="card-header">🎽 Elementos para usar durante tu visita</div>
                <table>
                    <thead><tr><th>Elemento</th><th>Disp.</th><th>Cant.</th><th></th></tr></thead>
                    <tbody id="elementos"></tbody>
                </table>
                <p class="muted" style="margin-top:8px;">Máximo 3 unidades por elemento. Devuélvelos en recepción al terminar.</p>
            </div>
            <div class="card">
                <div class="card-header">📦 Tus préstamos</div>
                <table>
                    <thead><tr><th>Elemento</th><th>Cant.</th><th>Estado</th><th></th></tr></thead>
                    <tbody id="mis-prestamos"></tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<script>
""" + _JS_COMUN + r"""
    function socio() { return {id: $('soc-id').value.trim(), nombre: $('soc-nombre').value.trim()}; }

    function renderHorarioGym(f) {
        // Agrupa días consecutivos con las mismas franjas: "Lunes a Sábado: ..."
        const textoDe = d => d.franjas.map(x => `${hora12(x.hora_inicio)} – ${hora12(x.hora_fin)}`).join('  y  ');
        const grupos = [];
        f.horarios.forEach(d => {
            const t = textoDe(d), ult = grupos[grupos.length - 1];
            if (ult && ult.texto === t) ult.hasta = d.dia; else grupos.push({desde: d.dia, hasta: d.dia, texto: t});
        });
        let html = grupos.map(g => `<p><strong>${esc(g.desde === g.hasta ? DIAS[g.desde] : DIAS[g.desde] + ' a ' + DIAS[g.hasta])}:</strong> ${esc(g.texto)}</p>`).join('');
        if (f.festivos) html += `<p><strong>Festivos:</strong> ${esc(f.festivos)}</p>`;
        if (f.domingos) html += `<p><strong>Domingos:</strong> ${esc(f.domingos)}</p>`;
        if (f.jefe) html += `<p class="muted" style="margin-top:8px;">Administración: ${esc(f.jefe)}</p>`;
        return html;
    }

    async function cargarPublico() {
        $('horario-gym').innerHTML = renderHorarioGym((await api('/api/gimnasio')).data);
        const ent = (await api('/api/entrenadores')).data;
        $('entrenadores').innerHTML = ent.map(e => `
            <div class="entrenador">
                <strong>${esc(e.nombre)}</strong> <span class="muted">· ${esc(e.especialidad)}</span><br>
                ${e.horarios.length ? e.horarios.map(h => `<span class="chip">${esc(h.actividad)} · ${esc(horarioTexto(h))}</span>`).join('') : '<span class="muted">Disponible en el horario del gimnasio</span>'}
            </div>`).join('');

        const sup = (await api('/api/suplementos')).data;
        $('suplementos').innerHTML = sup.map(s => `
            <tr>
                <td><strong>${esc(s.nombre)}</strong><br><span class="muted">${esc(s.descripcion || '')}</span></td>
                <td>${money(s.precio)}</td>
                <td>${s.stock_disponible > 0 ? '<span class="pill pill-ok">' + s.stock_disponible + '</span>' : '<span class="pill pill-bad">Agotado</span>'}</td>
                <td><input type="number" min="1" max="5" value="1" id="cant-${esc(s.codigo)}"></td>
                <td><button class="btn" data-sup="${esc(s.codigo)}" ${s.stock_disponible > 0 ? '' : 'disabled'}>Registrar</button></td>
            </tr>`).join('');

        const ele = (await api('/api/elementos')).data;
        $('elementos').innerHTML = ele.map(e => `
            <tr>
                <td><strong>${esc(e.nombre)}</strong></td>
                <td>${e.cantidad_disponible > 0 ? '<span class="pill pill-ok">' + e.cantidad_disponible + ' / ' + e.cantidad_total + '</span>' : '<span class="pill pill-bad">Sin unidades</span>'}</td>
                <td><input type="number" min="1" max="3" value="1" id="pre-${esc(e.codigo)}"></td>
                <td><button class="btn" data-ele="${esc(e.codigo)}" ${e.cantidad_disponible > 0 ? '' : 'disabled'}>Pedir</button></td>
            </tr>`).join('');
    }

    async function cargarMio() {
        const id = socio().id;
        const vacio = '<tr><td colspan="4" class="muted">Escribe un documento válido para ver tu historial.</td></tr>';
        if (id.length < 4) { $('mis-consumos').innerHTML = vacio; $('mis-prestamos').innerHTML = vacio; return; }
        const q = encodeURIComponent(id);
        const cons = await api('/api/suplementos/consumos?socio_id=' + q);
        $('mis-consumos').innerHTML = cons.ok && cons.data.length
            ? cons.data.map(c => `<tr><td>${esc(fecha(c.timestamp))}</td><td>${esc(c.suplemento_nombre)}</td><td>${c.cantidad}</td><td>${money(c.total)}</td></tr>`).join('')
            : '<tr><td colspan="4" class="muted">Aún no has registrado consumos.</td></tr>';
        const pre = await api('/api/elementos/prestamos?socio_id=' + q);
        $('mis-prestamos').innerHTML = pre.ok && pre.data.length
            ? pre.data.map(p => `<tr><td>${esc(p.elemento_nombre)}</td><td>${p.cantidad}</td>
                <td><span class="pill ${p.estado === 'PRESTADO' ? 'pill-warn' : 'pill-ok'}">${esc(p.estado)}</span></td>
                <td>${p.estado === 'PRESTADO' ? `<button class="btn btn-sec" data-dev="${esc(p.id_prestamo)}">Devolver</button>` : ''}</td></tr>`).join('')
            : '<tr><td colspan="4" class="muted">No tienes préstamos.</td></tr>';
    }

    async function refrescar() { await cargarPublico(); await cargarMio(); }

    document.addEventListener('click', async (ev) => {
        const b = ev.target.closest('button'); if (!b) return;
        const s = socio();
        let r;
        if (b.dataset.sup) {
            r = await api('/api/suplementos/consumo', {socio_id: s.id, socio_nombre: s.nombre, codigo: b.dataset.sup,
                cantidad: parseInt($('cant-' + b.dataset.sup).value), idempotency_key: nuevaKey('SUP')});
            if (r.ok) aviso(`Registrado: ${r.data.resultado.cantidad} × ${r.data.resultado.suplemento_nombre} (${money(r.data.resultado.total)})`, true);
        } else if (b.dataset.ele) {
            r = await api('/api/elementos/prestamo', {socio_id: s.id, socio_nombre: s.nombre, codigo: b.dataset.ele,
                cantidad: parseInt($('pre-' + b.dataset.ele).value), idempotency_key: nuevaKey('PRE')});
            if (r.ok) aviso(`Préstamo registrado: ${r.data.resultado.cantidad} × ${r.data.resultado.elemento_nombre}`, true);
        } else if (b.dataset.dev) {
            r = await api('/api/elementos/devolucion', {id_prestamo: b.dataset.dev, socio_id: s.id});
            if (r.ok) aviso('Elemento devuelto. ¡Gracias!', true);
        } else { return; }
        if (!r.ok) aviso(r.data.error || 'No se pudo completar la acción.', false);
        await refrescar();
    });

    window.onload = refrescar;
</script>
</body>
</html>
"""

PANEL_GESTION_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GymExpress — Panel interno</title>
""" + _ESTILO + r"""
</head>
<body>
<div class="container">
    <header>
        <div>
            <div class="brand">🛠️ GymExpress · Panel interno</div>
            <div class="muted">Insumos de limpieza, préstamos activos, consumos de suplementos y altas de personal</div>
        </div>
        <div class="nav"><a href="/panel">Panel integrado</a><a href="/">Reservas</a><a href="/usuario">Portal del socio</a><a href="/basedatos">Base de datos</a><a href="/eventos">Eventos</a></div>
    </header>

    <div id="mensaje"></div>

    <div class="grid">
        <div>
            <div class="card">
                <div class="card-header">🧹 Insumos de limpieza</div>
                <table>
                    <thead><tr><th>Insumo</th><th>Stock</th><th>Mínimo</th><th>Estado</th></tr></thead>
                    <tbody id="insumos"></tbody>
                </table>
            </div>
            <div class="card">
                <div class="card-header">➕ Registrar uso o reposición</div>
                <div class="row">
                    <div class="field"><label>Insumo</label><select id="mov-insumo"></select></div>
                    <div class="field"><label>Tipo</label>
                        <select id="mov-tipo"><option value="USO">Uso</option><option value="REPOSICION">Reposición</option></select></div>
                </div>
                <div class="row">
                    <div class="field"><label>Cantidad</label><input type="number" id="mov-cant" value="1" min="1"></div>
                    <div class="field"><label>Motivo</label><input id="mov-motivo" value="Limpieza de la sala de máquinas"></div>
                </div>
                <button class="btn" id="btn-mov">Registrar movimiento</button>
            </div>
            <div class="card">
                <div class="card-header">📦 Stock de suplementos</div>
                <table>
                    <thead><tr><th>Producto</th><th>Precio</th><th>Stock</th></tr></thead>
                    <tbody id="stock-sup"></tbody>
                </table>
                <div class="row" style="margin-top:12px;">
                    <div class="field"><label>Producto</label><select id="stk-sup"></select></div>
                    <div class="field"><label>Stock real (conteo físico)</label><input type="number" id="stk-valor" min="0" value="0"></div>
                </div>
                <button class="btn" id="btn-stk">Actualizar stock</button>
            </div>
            <div class="card">
                <div class="card-header">📜 Últimos movimientos de insumos</div>
                <table>
                    <thead><tr><th>Fecha</th><th>Insumo</th><th>Tipo</th><th>Cant.</th><th>Motivo</th></tr></thead>
                    <tbody id="movimientos"></tbody>
                </table>
            </div>
        </div>
        <div>
            <div class="card">
                <div class="card-header">🎽 Préstamos activos</div>
                <table>
                    <thead><tr><th>Socio</th><th>Elemento</th><th>Cant.</th><th>Desde</th></tr></thead>
                    <tbody id="prestamos"></tbody>
                </table>
            </div>
            <div class="card">
                <div class="card-header">🥤 Consumo de suplementos <span class="muted" id="total-ventas"></span></div>
                <table>
                    <thead><tr><th>Fecha</th><th>Socio</th><th>Producto</th><th>Cant.</th><th>Total</th></tr></thead>
                    <tbody id="consumos"></tbody>
                </table>
            </div>
            <div class="card">
                <div class="card-header">🧑‍🏫 Nuevo entrenador</div>
                <div class="row">
                    <div class="field"><label>Nombre</label><input id="ent-nombre" placeholder="Nombre y apellido"></div>
                    <div class="field"><label>Especialidad</label><input id="ent-esp" placeholder="Ej: Yoga y movilidad"></div>
                </div>
                <button class="btn" id="btn-ent">Agregar entrenador</button>
            </div>
            <div class="card">
                <div class="card-header">🕒 Nuevo horario</div>
                <div class="row">
                    <div class="field"><label>Entrenador</label><select id="hor-ent"></select></div>
                    <div class="field"><label>Actividad</label><input id="hor-act" placeholder="Ej: Spinning"></div>
                </div>
                <div class="row">
                    <div class="field"><label>Día</label><select id="hor-dia"></select></div>
                    <div class="field"><label>Inicio / Fin</label>
                        <div class="row"><input type="time" id="hor-ini" value="06:00"><input type="time" id="hor-fin" value="07:00"></div></div>
                </div>
                <button class="btn" id="btn-hor">Agregar horario</button>
            </div>
        </div>
    </div>
</div>

<script>
""" + _JS_COMUN + r"""
    $('hor-dia').innerHTML = Object.entries(DIAS).map(([k, v]) => `<option value="${k}">${v}</option>`).join('');

    async function cargar() {
        const ins = (await api('/api/gestion/insumos')).data;
        $('insumos').innerHTML = ins.map(i => `
            <tr><td><strong>${esc(i.nombre)}</strong><br><span class="muted">${esc(i.codigo)} · ${esc(i.unidad)}</span></td>
                <td>${i.stock_actual}</td><td>${i.stock_minimo}</td>
                <td>${i.bajo_minimo ? '<span class="pill pill-bad">Reponer</span>' : '<span class="pill pill-ok">OK</span>'}</td></tr>`).join('');
        const sel = $('mov-insumo').value;
        $('mov-insumo').innerHTML = ins.map(i => `<option value="${esc(i.codigo)}">${esc(i.nombre)} (${i.stock_actual} ${esc(i.unidad)})</option>`).join('');
        if (sel) $('mov-insumo').value = sel;

        const nombres = Object.fromEntries(ins.map(i => [i.codigo, i.nombre]));
        const mov = (await api('/api/gestion/movimientos')).data;
        $('movimientos').innerHTML = mov.length ? mov.map(m => `
            <tr><td>${esc(fecha(m.timestamp))}</td><td>${esc(nombres[m.insumo_codigo] || m.insumo_codigo)}</td>
                <td><span class="pill ${m.tipo === 'USO' ? 'pill-warn' : 'pill-ok'}">${esc(m.tipo)}</span></td>
                <td>${m.cantidad}</td><td>${esc(m.motivo)}</td></tr>`).join('')
            : '<tr><td colspan="5" class="muted">Sin movimientos todavía.</td></tr>';

        const sup = (await api('/api/suplementos')).data;
        $('stock-sup').innerHTML = sup.map(s => `
            <tr><td>${esc(s.nombre)}</td><td>${money(s.precio)}</td>
                <td><span class="pill ${s.stock_disponible > 5 ? 'pill-ok' : (s.stock_disponible > 0 ? 'pill-warn' : 'pill-bad')}">${s.stock_disponible}</span></td></tr>`).join('');
        const selSup = $('stk-sup').value;
        $('stk-sup').innerHTML = sup.map(s => `<option value="${esc(s.codigo)}">${esc(s.nombre)}</option>`).join('');
        if (selSup) $('stk-sup').value = selSup;

        const pre = (await api('/api/gestion/prestamos-activos')).data;
        $('prestamos').innerHTML = pre.length ? pre.map(p => `
            <tr><td>${esc(p.socio_nombre)}<br><span class="muted">${esc(p.socio_id)}</span></td>
                <td>${esc(p.elemento_nombre)}</td><td>${p.cantidad}</td><td>${esc(fecha(p.fecha_prestamo))}</td></tr>`).join('')
            : '<tr><td colspan="4" class="muted">No hay elementos prestados.</td></tr>';

        const con = (await api('/api/gestion/consumos')).data;
        $('total-ventas').textContent = con.length ? '· Total: ' + money(con.reduce((a, c) => a + c.total, 0)) : '';
        $('consumos').innerHTML = con.length ? con.slice(0, 15).map(c => `
            <tr><td>${esc(fecha(c.timestamp))}</td><td>${esc(c.socio_nombre)}</td><td>${esc(c.suplemento_nombre)}</td>
                <td>${c.cantidad}</td><td>${money(c.total)}</td></tr>`).join('')
            : '<tr><td colspan="5" class="muted">Sin consumos registrados.</td></tr>';

        const ent = (await api('/api/entrenadores')).data;
        const selEnt = $('hor-ent').value;
        $('hor-ent').innerHTML = ent.map(e => `<option value="${e.id}">${esc(e.nombre)}</option>`).join('');
        if (selEnt) $('hor-ent').value = selEnt;
    }

    async function accion(promesa, textoOk) {
        const r = await promesa;
        aviso(r.ok ? textoOk : (r.data.error || 'No se pudo completar la acción.'), r.ok);
        if (r.ok) await cargar();
        return r.ok;
    }

    $('btn-mov').onclick = () => accion(api('/api/gestion/insumos/movimiento', {
        codigo: $('mov-insumo').value, tipo: $('mov-tipo').value,
        cantidad: parseInt($('mov-cant').value), motivo: $('mov-motivo').value.trim()}), 'Movimiento registrado.');

    $('btn-stk').onclick = () => accion(api('/api/gestion/suplementos/stock', {
        codigo: $('stk-sup').value, stock: parseInt($('stk-valor').value)}), 'Stock actualizado.');

    $('btn-ent').onclick = async () => {
        if (await accion(api('/api/gestion/entrenadores', {nombre: $('ent-nombre').value.trim(), especialidad: $('ent-esp').value.trim()}), 'Entrenador agregado.')) {
            $('ent-nombre').value = ''; $('ent-esp').value = '';
        }
    };

    $('btn-hor').onclick = () => accion(api('/api/gestion/horarios', {
        entrenador_id: parseInt($('hor-ent').value), dia: $('hor-dia').value, actividad: $('hor-act').value.trim(),
        hora_inicio: $('hor-ini').value, hora_fin: $('hor-fin').value}), 'Horario agregado.');

    window.onload = cargar;
</script>
</body>
</html>
"""


BASEDATOS_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GymExpress — Base de datos</title>
""" + _ESTILO + r"""
    <style>
        .layout { display:grid; grid-template-columns:260px 1fr; gap:20px; }
        @media (max-width:900px) { .layout { grid-template-columns:1fr; } }
        .tabla-item { display:flex; justify-content:space-between; width:100%; text-align:left; background:#0D1015;
                      border:1px solid var(--border); color:var(--text); padding:9px 12px; border-radius:6px;
                      margin-bottom:6px; cursor:pointer; font-size:.85rem; }
        .tabla-item:hover, .tabla-item.activa { border-color:var(--primary); }
        .tabla-item span { color:var(--muted); }
        td.celda { max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-family:monospace; font-size:.78rem; }
        .vacio { color:var(--muted); font-style:italic; }
        code.ruta { background:#0D1015; border:1px solid var(--border); padding:3px 8px; border-radius:6px; font-size:.78rem; word-break:break-all; }
    </style>
</head>
<body>
<div class="container">
    <header>
        <div>
            <div class="brand">🗄️ GymExpress · Base de datos</div>
            <div class="muted">Contenido real del archivo SQLite del proyecto (solo lectura)</div>
        </div>
        <div class="nav"><a href="/panel">Panel integrado</a><a href="/">Reservas</a><a href="/usuario">Portal del socio</a><a href="/gestion">Panel interno</a><a href="/eventos">Eventos</a></div>
    </header>

    <div class="card">
        <div class="muted">Archivo de la base de datos:</div>
        <code class="ruta" id="ruta"></code>
        <p class="muted" style="margin-top:8px;">Se crea automáticamente al iniciar el servidor, dentro de la carpeta del proyecto.
        También puedes abrirlo con DB Browser for SQLite o con <code>python3 ver_bd.py</code>.</p>
    </div>

    <div class="layout">
        <div class="card">
            <div class="card-header">Tablas</div>
            <div id="lista-tablas"></div>
            <button class="btn btn-sec" id="btn-refrescar" style="width:100%; margin-top:6px;">↻ Actualizar</button>
        </div>
        <div class="card">
            <div class="card-header" id="titulo-tabla">Selecciona una tabla</div>
            <div id="contenido"></div>
        </div>
    </div>
</div>

<script>
""" + _JS_COMUN + r"""
    let activa = null;

    function celda(v) {
        if (v === null) return '<td class="celda vacio">NULL</td>';
        const t = String(v);
        return `<td class="celda" title="${esc(t)}">${esc(t.length > 90 ? t.slice(0, 90) + '…' : t)}</td>`;
    }

    async function cargarResumen() {
        const d = (await api('/api/bd/resumen')).data;
        $('ruta').textContent = d.ruta;
        $('lista-tablas').innerHTML = d.tablas.map(t =>
            `<button class="tabla-item ${t.nombre === activa ? 'activa' : ''}" data-tabla="${esc(t.nombre)}">${esc(t.nombre)}<span>${t.filas}</span></button>`).join('');
    }

    async function verTabla(nombre) {
        activa = nombre;
        const r = await api('/api/bd/tabla?nombre=' + encodeURIComponent(nombre) + '&limite=200');
        if (!r.ok) { aviso(r.data.error || 'No se pudo leer la tabla.', false); return; }
        const d = r.data;
        $('titulo-tabla').textContent = `${d.tabla} — ${d.total} fila(s)` + (d.total > d.filas.length ? ` (mostrando ${d.filas.length})` : '');
        $('contenido').innerHTML = d.filas.length
            ? `<table><thead><tr>${d.columnas.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>
               <tbody>${d.filas.map(f => `<tr>${f.map(celda).join('')}</tr>`).join('')}</tbody></table>`
            : '<p class="muted">La tabla está vacía.</p>';
        await cargarResumen();
    }

    document.addEventListener('click', ev => {
        const b = ev.target.closest('button'); if (!b) return;
        if (b.dataset.tabla) verTabla(b.dataset.tabla);
        if (b.id === 'btn-refrescar') { cargarResumen().then(() => activa && verTabla(activa)); }
    });

    window.onload = async () => { await cargarResumen(); const primera = document.querySelector('[data-tabla]'); if (primera) verTabla(primera.dataset.tabla); };
</script>
</body>
</html>
"""


# Página integrada: los módulos operativos se muestran en una misma pantalla mediante pestañas.
# El visor de base de datos conserva su ruta independiente (/basedatos).
PANEL_INTEGRADO_HTML = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GymExpress | Panel integrado</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#111418;color:#f8fafc;font-family:Segoe UI,Arial,sans-serif}
header{padding:18px 24px;border-bottom:1px solid #303744;background:#171b21;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
h1{font-size:22px;color:#fb923c;margin:0}small{color:#94a3b8}.tabs{display:flex;gap:8px;flex-wrap:wrap;padding:14px 24px;background:#171b21;border-bottom:1px solid #303744}
button,a.tab{font:inherit;cursor:pointer;color:#cbd5e1;background:#202630;border:1px solid #394252;border-radius:8px;padding:10px 14px;text-decoration:none}
button.active{background:#f97316;color:#fff;border-color:#f97316}button:hover,a.tab:hover{border-color:#f97316;color:#fff}
main{padding:14px 18px}.module{display:none;width:100%;height:calc(100vh - 145px);min-height:600px;border:1px solid #303744;border-radius:10px;background:#111418}.module.active{display:block}
@media(max-width:600px){header{padding:14px}.tabs{padding:10px}main{padding:8px}.module{height:calc(100vh - 205px);min-height:550px}}
</style></head><body>
<header><div><h1>🏋️ GymExpress MVP</h1><small>Panel integrado · Reservas, socios, suplementos e inventario</small></div><small>Todo en una sola pestaña</small></header>
<nav class="tabs" aria-label="Módulos de GymExpress">
<button class="active" data-target="reservas">Reservas y membresías</button>
<button data-target="socios">Portal del socio</button>
<button data-target="gestion">Gestión e inventario</button>
<button data-target="basedatos">Base de datos</button>
<button data-target="eventos">Eventos</button>
</nav><main>
<iframe class="module active" id="reservas" src="/" title="Reservas y membresías"></iframe>
<iframe class="module" id="socios" src="/usuario" title="Portal del socio" loading="lazy"></iframe>
<iframe class="module" id="gestion" src="/gestion" title="Gestión e inventario" loading="lazy"></iframe>
<iframe class="module" id="basedatos" src="/basedatos" title="Base de datos" loading="lazy"></iframe>
<iframe class="module" id="eventos" src="/eventos" title="Eventos" loading="lazy"></iframe>
</main><script>
// Actualiza los datos de la pestaña que se abre (mismo origen: se llama a la función de carga de esa página).
function actualizar(frame){
 try{
  const w=frame.contentWindow, f=w.refrescar||w.cargar||w.cargarDatos;
  if(f){f();}else{const b=w.document.getElementById('btn-refrescar'); if(b){b.click();}}
 }catch(e){}
}
document.querySelectorAll('button[data-target]').forEach(b=>b.addEventListener('click',()=>{
 document.querySelectorAll('button[data-target]').forEach(x=>x.classList.toggle('active',x===b));
 document.querySelectorAll('iframe.module').forEach(f=>f.classList.toggle('active',f.id===b.dataset.target));
 actualizar(document.getElementById(b.dataset.target));
}));
</script></body></html>"""


EVENTOS_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GymExpress — Eventos CloudEvents</title>
""" + _ESTILO + r"""
    <style>
        .tarjetas { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:12px; margin-bottom:20px; }
        .tarjeta { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:12px 14px; }
        .tarjeta .n { font-size:1.6rem; font-weight:bold; color:#FDBA74; }
        .tarjeta .t { font-size:.75rem; color:var(--muted); }
        tr.ev { cursor:pointer; } tr.ev:hover td { background:#202733; }
        pre.json { background:#0D1015; border:1px solid var(--border); border-radius:6px; padding:10px; font-size:.75rem;
                   white-space:pre-wrap; word-break:break-all; margin:6px 0 2px 0; }
        code.tipo { font-size:.78rem; }
    </style>
</head>
<body>
<div class="container">
    <header>
        <div>
            <div class="brand">📡 GymExpress · Eventos CloudEvents v1.0</div>
            <div class="muted">Mensajes que los contextos de Reservas y Catálogo publican en el EventBus</div>
        </div>
        <div class="nav"><a href="/panel">Panel integrado</a><a href="/">Reservas</a><a href="/usuario">Portal del socio</a><a href="/gestion">Panel interno</a><a href="/basedatos">Base de datos</a></div>
    </header>
    <div id="mensaje"></div>
    <div class="tarjetas" id="tarjetas"></div>
    <div class="grid">
        <div class="card">
            <div class="card-header">🧾 Últimos eventos (clic para ver el JSON)</div>
            <table>
                <thead><tr><th>Hora</th><th>Tipo</th><th>Origen</th><th>Sujeto</th></tr></thead>
                <tbody id="eventos"></tbody>
            </table>
        </div>
        <div>
            <div class="card">
                <div class="card-header">📨 Notificaciones enviadas por los consumidores</div>
                <table>
                    <thead><tr><th>Hora</th><th>Destino</th><th>Mensaje</th></tr></thead>
                    <tbody id="notificaciones"></tbody>
                </table>
            </div>
            <div class="card">
                <div class="card-header">⚠️ Entregas fallidas (dead-letter)</div>
                <table>
                    <thead><tr><th>Hora</th><th>Consumidor</th><th>Error</th></tr></thead>
                    <tbody id="fallidas"></tbody>
                </table>
            </div>
        </div>
    </div>
</div>
<script>
""" + _JS_COMUN + r"""
    const abiertos = new Set();
    let ultimos = [];
    function corto(t) { return t.replace('co.edu.uniremington.gymexpress.', ''); }

    function pintarEventos() {
        $('eventos').innerHTML = ultimos.length ? ultimos.map(e => `
            <tr class="ev" data-id="${esc(e.id)}"><td>${esc(e.time.slice(11, 23))}</td><td><code class="tipo">${esc(corto(e.type))}</code></td>
                <td>${esc(e.source)}</td><td>${esc(e.subject || '')}</td></tr>
            ${abiertos.has(e.id) ? `<tr><td colspan="4"><pre class="json">${esc(JSON.stringify(e, null, 2))}</pre></td></tr>` : ''}`).join('')
            : '<tr><td colspan="4" class="muted">Aún no hay eventos: crea una reserva para generarlos.</td></tr>';
    }

    async function cargar() {
        const m = (await api('/api/eventos/metricas')).data;
        const items = [['Publicados', m.publicados], ['Entregas OK', m.entregas_ok], ['Entregas fallidas', m.entregas_fallidas],
                       ['Rechazados', m.rechazados], ['Pendientes', m.pendientes], ['Workers', m.workers], ['Modo', m.modo]];
        $('tarjetas').innerHTML = items.map(([t, n]) => `<div class="tarjeta"><div class="n">${esc(n ?? '-')}</div><div class="t">${t}</div></div>`).join('');
        ultimos = (await api('/api/eventos')).data;
        pintarEventos();
        const nt = (await api('/api/eventos/notificaciones')).data;
        $('notificaciones').innerHTML = nt.length ? nt.map(n => `<tr><td>${esc(n.hora.slice(11))}</td><td>${esc(n.destino)}</td><td>${esc(n.mensaje)}</td></tr>`).join('')
            : '<tr><td colspan="3" class="muted">Sin notificaciones.</td></tr>';
        const dl = (await api('/api/eventos/dead-letters')).data;
        $('fallidas').innerHTML = dl.length ? dl.map(d => `<tr><td>${esc(d.hora.slice(11))}</td><td>${esc(d.handler)}</td><td>${esc(d.error)}</td></tr>`).join('')
            : '<tr><td colspan="3" class="muted">Ninguna.</td></tr>';
    }

    document.addEventListener('click', ev => {
        const fila = ev.target.closest('tr.ev'); if (!fila) return;
        const id = fila.dataset.id;
        abiertos.has(id) ? abiertos.delete(id) : abiertos.add(id);
        pintarEventos();
    });
    window.onload = () => { cargar(); setInterval(cargar, 3000); };
</script>
</body>
</html>
"""
