/**
 * Uso — qué usa la gente, para decidir con números y no con sensaciones.
 *
 * Dos fuentes, en una sola pantalla:
 *
 *   · Lo que ya estaba en la base: altas por semana, el embudo de
 *     verificación, cuentas activas, operaciones por tipo. Números que
 *     existían y nadie miraba juntos.
 *   · Lo que el servidor cuenta desde ahora: cada función que un cliente
 *     usa, por día, con cuántos pedidos y cuántas cuentas distintas. Sin
 *     cuerpo, sin parámetros: sólo la ruta. Ver backend/services/uso.py.
 *
 * Una función sin nombre puesto se muestra con su ruta cruda: es una ruta
 * nueva que nadie bautizó todavía, no un error.
 */
import { useState, useEffect } from 'react';
import { BarChart3, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../../utils/api';

const PERIODOS = [7, 30, 90];

const tarjeta = { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12, padding: '14px 16px' };
const rotulo = { fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4, color: '#6b7280', marginBottom: 4 };
const titulo = { fontSize: 15, fontWeight: 600, color: '#111827', margin: '0 0 10px 0' };

const fmtDia = (iso) => {
  if (!iso) return '—';
  const [, m, d] = iso.split('-');
  return `${d}/${m}`;
};

const porcentaje = (parte, todo) => (todo ? Math.round((parte / todo) * 100) : 0);

function Barra({ valor, maximo, color = '#6366f1' }) {
  const ancho = maximo ? Math.max(2, Math.round((valor / maximo) * 100)) : 0;
  return (
    <div style={{ height: 8, background: '#f3f4f6', borderRadius: 4, overflow: 'hidden' }}>
      <div style={{ width: `${ancho}%`, height: '100%', background: color, borderRadius: 4 }} />
    </div>
  );
}

function Cifra({ etiqueta, valor, detalle, testid }) {
  return (
    <div style={tarjeta} data-testid={testid}>
      <div style={rotulo}>{etiqueta}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: '#111827', lineHeight: 1.1 }}>{valor ?? '—'}</div>
      {detalle ? <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>{detalle}</div> : null}
    </div>
  );
}

export default function Uso() {
  const [dias, setDias] = useState(30);
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [vuelta, setVuelta] = useState(0);

  useEffect(() => {
    let vigente = true;
    setCargando(true);
    api.get(`/admin/uso?dias=${dias}`)
      .then((r) => { if (vigente) setDatos(r.data || null); })
      .catch((e) => { if (vigente) toast.error(e?.response?.data?.detail || 'No se pudo leer el uso'); })
      .finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, [dias, vuelta]);

  const base = datos?.base || {};
  const embudo = base.embudo || {};
  const activos = base.activos || {};
  const totales = base.totales || {};
  const semanas = base.altas_por_semana || [];
  const operaciones = base.operaciones || [];
  const funciones = datos?.funciones || [];
  const sinUso = datos?.sin_uso || [];
  const porDia = datos?.por_dia || [];

  const maxSemana = Math.max(0, ...semanas.map((s) => s.cuantos));
  const maxOperacion = Math.max(0, ...operaciones.map((o) => o.iniciadas));
  const maxFuncion = Math.max(0, ...funciones.map((f) => f.pedidos));
  const maxDia = Math.max(0, ...porDia.map((d) => d.pedidos));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }} data-testid="uso">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <BarChart3 size={20} color="#6366f1" />
        <h2 style={{ fontSize: 18, fontWeight: 700, color: '#111827', margin: 0 }}>Uso</h2>
        <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
          {PERIODOS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setDias(p)}
              data-testid={`uso-dias-${p}`}
              style={{
                padding: '6px 12px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer',
                border: '1px solid ' + (dias === p ? '#6366f1' : '#d1d5db'),
                background: dias === p ? '#eef2ff' : '#fff',
                color: dias === p ? '#4338ca' : '#374151',
              }}
            >
              {p} días
            </button>
          ))}
          <button
            type="button"
            onClick={() => setVuelta((v) => v + 1)}
            title="Volver a leer"
            style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer' }}
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {cargando && !datos ? (
        <div style={{ color: '#6b7280', fontSize: 14 }}>Leyendo…</div>
      ) : null}

      {datos ? (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            <Cifra etiqueta={`Altas en ${dias} días`} valor={embudo.registrados} testid="uso-altas" />
            <Cifra etiqueta="Activas en 7 días" valor={activos['7']} detalle="Cuentas que entraron" />
            <Cifra etiqueta="Activas en 30 días" valor={activos['30']} detalle="Cuentas que entraron" />
            <Cifra
              etiqueta="Verificadas"
              valor={totales.verificadas}
              detalle={`de ${totales.cuentas ?? '—'} cuentas en total`}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
            <div style={tarjeta} data-testid="uso-embudo">
              <h3 style={titulo}>Verificación de las cuentas nuevas</h3>
              {[
                ['Se registraron', embudo.registrados, '#6366f1'],
                ['Enviaron documentos', embudo.enviaron_documentos, '#0ea5e9'],
                ['Aprobadas', embudo.aprobados, '#16a34a'],
              ].map(([nombre, valor, color]) => (
                <div key={nombre} style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                    <span style={{ color: '#374151' }}>{nombre}</span>
                    <span style={{ color: '#111827', fontWeight: 600 }}>
                      {valor ?? 0}
                      <span style={{ color: '#9ca3af', fontWeight: 400 }}> · {porcentaje(valor, embudo.registrados)}%</span>
                    </span>
                  </div>
                  <Barra valor={valor || 0} maximo={embudo.registrados || 0} color={color} />
                </div>
              ))}
              <div style={{ fontSize: 12, color: '#6b7280' }}>
                En revisión: {embudo.en_revision ?? 0} · Rechazadas: {embudo.rechazados ?? 0}
              </div>
            </div>

            <div style={tarjeta} data-testid="uso-altas-semana">
              <h3 style={titulo}>Altas por semana</h3>
              {semanas.length === 0 ? <div style={{ fontSize: 13, color: '#6b7280' }}>Sin altas en el período.</div> : null}
              {semanas.map((s) => (
                <div key={s.semana} style={{ display: 'grid', gridTemplateColumns: '64px 1fr 40px', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: '#6b7280' }}>{fmtDia(s.semana)}</span>
                  <Barra valor={s.cuantos} maximo={maxSemana} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#111827', textAlign: 'right' }}>{s.cuantos}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={tarjeta} data-testid="uso-operaciones">
            <h3 style={titulo}>Operaciones en {dias} días</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(160px, 1fr) 2fr 80px 90px', gap: 8, fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 6 }}>
              <span>Operación</span><span /><span style={{ textAlign: 'right' }}>Iniciadas</span><span style={{ textAlign: 'right' }}>Terminadas</span>
            </div>
            {operaciones.map((o) => (
              <div key={o.nombre} style={{ display: 'grid', gridTemplateColumns: 'minmax(160px, 1fr) 2fr 80px 90px', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 13, color: '#111827' }}>{o.nombre}</span>
                <Barra valor={o.iniciadas} maximo={maxOperacion} color="#0ea5e9" />
                <span style={{ fontSize: 13, fontWeight: 600, textAlign: 'right' }}>{o.iniciadas}</span>
                <span style={{ fontSize: 13, color: '#6b7280', textAlign: 'right' }}>{o.terminadas ?? '—'}</span>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12 }}>
            <div style={tarjeta} data-testid="uso-funciones">
              <h3 style={titulo}>Funciones más usadas</h3>
              <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 10 }}>
                Pedidos de clientes con sesión, desde el {fmtDia(datos.desde)}. Sin el personal ni los sondeos automáticos.
              </div>
              {funciones.length === 0 ? (
                <div style={{ fontSize: 13, color: '#6b7280' }}>Todavía no hay nada contado en este período.</div>
              ) : null}
              {funciones.map((f) => (
                <div key={`${f.metodo} ${f.ruta}`} style={{ marginBottom: 10 }} data-testid={`uso-funcion-${f.metodo}-${f.ruta}`}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 13, marginBottom: 4 }}>
                    <span style={{ color: '#111827', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {f.nombre || <code style={{ fontSize: 12 }}>{f.metodo} {f.ruta}</code>}
                    </span>
                    <span style={{ whiteSpace: 'nowrap', color: '#111827', fontWeight: 600 }}>
                      {f.pedidos}
                      <span style={{ color: '#9ca3af', fontWeight: 400 }}> · {f.cuentas} {f.cuentas === 1 ? 'cuenta' : 'cuentas'}</span>
                    </span>
                  </div>
                  <Barra valor={f.pedidos} maximo={maxFuncion} />
                </div>
              ))}

              {sinUso.length > 0 ? (
                <div style={{ borderTop: '1px solid #e5e7eb', marginTop: 14, paddingTop: 12 }} data-testid="uso-sin-uso">
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#111827', marginBottom: 4 }}>
                    Nadie las usó en {dias} días
                  </div>
                  {/* El aviso va ARRIBA de la lista y no debajo: leído después,
                      la lista ya se interpretó como «esto sobra». */}
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 10 }}>
                    Una función en cero puede ser una que nadie necesita, o una a la que no se
                    llega porque el botón quedó escondido. El número no distingue las dos.
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {sinUso.map((n) => (
                      <span
                        key={n}
                        data-testid={`uso-sin-uso-${n}`}
                        style={{
                          fontSize: 12, color: '#6b7280', background: '#f9fafb',
                          border: '1px solid #e5e7eb', borderRadius: 6, padding: '3px 8px',
                        }}
                      >
                        {n}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>

            <div style={tarjeta} data-testid="uso-por-dia">
              <h3 style={titulo}>Por día</h3>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 120 }}>
                {porDia.map((d) => (
                  <div
                    key={d.dia}
                    title={`${fmtDia(d.dia)}: ${d.pedidos} pedidos, ${d.cuentas} cuentas`}
                    style={{
                      flex: 1, minWidth: 2, borderRadius: '3px 3px 0 0', background: d.pedidos ? '#6366f1' : '#e5e7eb',
                      height: `${maxDia ? Math.max(3, Math.round((d.pedidos / maxDia) * 100)) : 3}%`,
                    }}
                  />
                ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginTop: 6 }}>
                <span>{fmtDia(datos.desde)}</span>
                <span>{fmtDia(datos.hasta)}</span>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
