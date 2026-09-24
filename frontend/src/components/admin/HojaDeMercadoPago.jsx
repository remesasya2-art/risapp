/**
 * HojaDeMercadoPago.jsx — Qué nos avisó Mercado Pago, cuándo, y en qué terminó.
 *
 * POR QUE ESTA PANTALLA EXISTE
 *
 *   El 20 de septiembre de 2026 un cliente pagó con PIX y su envío no avanzó.
 *   Averiguar si Mercado Pago había llamado costó leer código: de todo lo que
 *   nos avisa no se guardaba nada, y la única huella era el registro del
 *   servidor — que se rota, que nadie abre a las tres de la mañana, y que no
 *   se puede filtrar por fecha ni buscar por referencia.
 *
 *   El historial está en `docs/incidentes/`.
 *
 * PARA QUE SE USA, EN CONCRETO
 *
 *   Un cliente dice «pagué y no me aparece». Con esto se contesta en treinta
 *   segundos y sin pedirle nada a nadie:
 *
 *     · ¿Mercado Pago avisó?   → si no hay fila, no avisó.
 *     · ¿Y qué pasó con eso?   → la columna dice si se acreditó o no, y por qué.
 *
 * SOLO MIRA. NO ACREDITA NADA.
 *
 *   Mover plata es una decisión de una persona y tiene que dejar rastro. Es la
 *   misma razón por la que `CobrosSinAcreditar` tampoco tiene un botón que
 *   arregle: un informe que además toca cosas es un informe que nadie se anima
 *   a abrir.
 *
 * LA LUPA BUSCA POR LOS TRES IDENTIFICADORES
 *
 *   Quien viene a buscar tiene UNO en la mano: el de Mercado Pago si lo sacó
 *   de su panel, nuestra referencia si lo sacó del cobro, o el de la operación
 *   si lo sacó del historial del cliente. Un campo por cada uno obligaría a
 *   saber cuál de los tres es — o sea, a saber cómo está hecho esto por dentro.
 */
import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  AlertTriangle, CheckCircle2, Clock, HelpCircle, RefreshCw, Search,
} from 'lucide-react';
import api from '../../utils/api';
import { fmt } from '../../utils/format';

const C = {
  linea: 'var(--en-oscuro-linea, #e5e7eb)',
  fondo: 'var(--en-oscuro-superficie-2, #f9fafb)',
  tinta: 'var(--en-oscuro-texto, #111827)',
  suave: 'var(--en-oscuro-texto-2, #6b7280)',
  tenue: 'var(--en-oscuro-texto-3, #9ca3af)',
  verde: 'var(--en-oscuro-exito, #047857)',
  verdeFondo: 'var(--en-oscuro-exito-suave, #ecfdf5)',
  ambar: '#b45309',
  ambarFondo: 'var(--en-oscuro-alerta-suave, #fffbeb)',
  rojo: 'var(--en-oscuro-error, #b91c1c)',
  rojoFondo: 'var(--en-oscuro-error-suave, #fef2f2)',
  azul: 'var(--en-oscuro-acento, #14395e)',
};

/* Los mismos cuatro desenlaces que guarda `services/hoja_de_mercadopago.py`.
   Si se agrega uno allá y no acá, cae en el de abajo y se ve, en vez de
   mostrarse en blanco. */
const DESENLACE = {
  acreditado: { texto: 'Se acreditó', color: C.verde, fondo: C.verdeFondo, Icono: CheckCircle2 },
  sin_acreditar: { texto: 'NO se acreditó', color: C.rojo, fondo: C.rojoFondo, Icono: AlertTriangle },
  ignorado: { texto: 'Nada que hacer', color: C.suave, fondo: C.fondo, Icono: HelpCircle },
  sin_terminar: { texto: 'Quedó a medias', color: C.ambar, fondo: C.ambarFondo, Icono: Clock },
};

const fechaHora = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'medium' });
};

/* De `<input type="datetime-local">` a lo que entiende el servidor. El campo
   da hora local sin zona; sin esto, «desde las 9» sería las 9 UTC y se
   perdería lo de la mañana de quien está en Brasil. */
const aISO = (valor) => (valor ? new Date(valor).toISOString() : undefined);

function Desenlace({ como }) {
  const d = DESENLACE[como] || {
    texto: como || '—', color: C.suave, fondo: C.fondo, Icono: HelpCircle };
  const { Icono } = d;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 9px', borderRadius: 20, fontSize: 12, fontWeight: 600,
      background: d.fondo, color: d.color, whiteSpace: 'nowrap',
    }}>
      <Icono size={12} /> {d.texto}
    </span>
  );
}

export default function HojaDeMercadoPago() {
  const [desde, setDesde] = useState('');
  const [hasta, setHasta] = useState('');
  const [texto, setTexto] = useState('');
  const [soloProblemas, setSoloProblemas] = useState(false);
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [pagina, setPagina] = useState(1);

  const traer = useCallback((aPagina = 1) => {
    setCargando(true);
    api.get('/admin/hoja-mercadopago', {
      params: {
        desde: aISO(desde),
        hasta: aISO(hasta),
        buscar: texto.trim() || undefined,
        como_termino: soloProblemas ? 'sin_acreditar' : undefined,
        pagina: aPagina,
        por_pagina: 50,
      },
    })
      .then(({ data }) => { setDatos(data); setPagina(aPagina); })
      .catch((e) => toast.error(e.response?.data?.detail
        || 'No se pudo abrir la hoja. Reintentá en un momento.'))
      .finally(() => setCargando(false));
  }, [desde, hasta, texto, soloProblemas]);

  // La primera carga sale en un microtask y no en el cuerpo del efecto: así
  // el `setState` de adentro no ocurre de forma sincrónica durante el montaje.
  // Mismo patrón que `Send.jsx`, y por el mismo motivo.
  useEffect(() => {
    const t = setTimeout(() => traer(1), 0);
    return () => clearTimeout(t);
    // Sólo al montar: después se trae cuando alguien aprieta buscar. Traer en
    // cada tecla le haría una consulta al servidor por letra.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filas = datos?.filas || [];
  const paginas = datos ? Math.ceil(datos.total / datos.por_pagina) : 1;

  return (
    <div data-testid="hoja-mercadopago">
      <div style={{ marginBottom: 18, maxWidth: 680 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: C.tinta, margin: 0 }}>
          Pagos de Mercado Pago
        </h2>
        <p style={{ fontSize: 13, color: C.suave, margin: '6px 0 0 0', lineHeight: 1.6 }}>
          Todo lo que Mercado Pago nos avisa queda acá, termine como termine.
          Si un cliente dice que pagó y no le aparece, buscá su referencia:{' '}
          <strong style={{ color: C.tinta }}>si no hay fila, Mercado Pago no
          avisó</strong>; si la hay, la última columna dice qué pasó.{' '}
          <strong style={{ color: C.tinta }}>Sólo mira: no acredita nada.</strong>
        </p>
      </div>

      {/* ── La lupa y el filtro de fecha ──────────────────────────────── */}
      <form
        onSubmit={(e) => { e.preventDefault(); traer(1); }}
        style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end',
          marginBottom: 16, padding: 14, background: C.fondo,
          border: `1px solid ${C.linea}`, borderRadius: 12 }}
      >
        <label style={{ flex: '1 1 240px' }}>
          <span style={{ display: 'block', fontSize: 12, color: C.suave, marginBottom: 4 }}>
            Buscar por referencia
          </span>
          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: C.tenue }} />
            <input
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              data-testid="hoja-buscar"
              placeholder="venv_… · tx_… · el número de Mercado Pago"
              style={{ width: '100%', padding: '9px 10px 9px 30px', fontSize: 13,
                border: `1px solid ${C.linea}`, borderRadius: 9,
                boxSizing: 'border-box' }}
            />
          </div>
        </label>

        <label>
          <span style={{ display: 'block', fontSize: 12, color: C.suave, marginBottom: 4 }}>
            Desde
          </span>
          <input type="datetime-local" value={desde} data-testid="hoja-desde"
            onChange={(e) => setDesde(e.target.value)}
            style={{ padding: '9px 10px', fontSize: 13,
              border: `1px solid ${C.linea}`, borderRadius: 9 }} />
        </label>

        <label>
          <span style={{ display: 'block', fontSize: 12, color: C.suave, marginBottom: 4 }}>
            Hasta
          </span>
          <input type="datetime-local" value={hasta} data-testid="hoja-hasta"
            onChange={(e) => setHasta(e.target.value)}
            style={{ padding: '9px 10px', fontSize: 13,
              border: `1px solid ${C.linea}`, borderRadius: 9 }} />
        </label>

        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
          fontSize: 13, color: C.tinta, paddingBottom: 9 }}>
          <input type="checkbox" checked={soloProblemas} data-testid="hoja-solo-problemas"
            onChange={(e) => setSoloProblemas(e.target.checked)} />
          Sólo los que no se acreditaron
        </label>

        <button type="submit" disabled={cargando} data-testid="hoja-aplicar"
          style={{ padding: '9px 18px', fontSize: 13, fontWeight: 600,
            background: C.azul, color: '#fff', border: 'none', borderRadius: 9,
            cursor: cargando ? 'default' : 'pointer', opacity: cargando ? 0.6 : 1,
            display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <RefreshCw size={13} /> {cargando ? 'Buscando…' : 'Buscar'}
        </button>
      </form>

      {/* ── Las filas ─────────────────────────────────────────────────── */}
      {datos && filas.length === 0 ? (
        <p style={{ fontSize: 13, color: C.suave, padding: '28px 0',
          textAlign: 'center' }} data-testid="hoja-vacia">
          No hay ningún aviso con esos filtros.{' '}
          {texto ? <strong style={{ color: C.tinta }}>
            Si buscaste una referencia y no aparece, Mercado Pago nunca avisó
            de ese pago.</strong> : null}
        </p>
      ) : null}

      {filas.length ? (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: 'left', color: C.suave, fontSize: 12 }}>
                  <th style={{ padding: '8px 10px' }}>Llegó</th>
                  <th style={{ padding: '8px 10px' }}>Mercado Pago</th>
                  <th style={{ padding: '8px 10px' }}>Nuestra referencia</th>
                  <th style={{ padding: '8px 10px', textAlign: 'right' }}>Monto</th>
                  <th style={{ padding: '8px 10px' }}>En qué terminó</th>
                </tr>
              </thead>
              <tbody>
                {filas.map((f) => (
                  <tr key={f.anotacion_id}
                    style={{ borderTop: `1px solid ${C.linea}` }}>
                    <td style={{ padding: '10px', color: C.suave,
                      whiteSpace: 'nowrap' }}>{fechaHora(f.llego_a_las)}</td>
                    <td style={{ padding: '10px', fontFamily: 'monospace',
                      fontSize: 12 }}>{f.mp_payment_id || '—'}</td>
                    <td style={{ padding: '10px', fontFamily: 'monospace',
                      fontSize: 12 }}>
                      {f.referencia || '—'}
                      {f.transaction_id ? (
                        <span style={{ display: 'block', color: C.tenue }}>
                          {f.transaction_id}
                        </span>
                      ) : null}
                    </td>
                    <td style={{ padding: '10px', textAlign: 'right',
                      fontVariantNumeric: 'tabular-nums' }}>
                      {f.monto != null ? `R$ ${fmt(f.monto)}` : '—'}
                    </td>
                    <td style={{ padding: '10px' }}>
                      <Desenlace como={f.como_termino} />
                      {/* EL MOTIVO VA AL LADO Y NO ESCONDIDO: «no se acreditó»
                          sin el porqué obliga a abrir el registro, que es lo
                          que esta pantalla existe para no tener que hacer. */}
                      {f.motivo ? (
                        <span style={{ display: 'block', color: C.suave,
                          fontSize: 12, marginTop: 4 }}>{f.motivo}</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {paginas > 1 ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10,
              justifyContent: 'center', marginTop: 16 }}>
              <button onClick={() => traer(pagina - 1)} disabled={pagina <= 1}
                data-testid="hoja-anterior"
                style={{ padding: '6px 14px', fontSize: 13, borderRadius: 8,
                  border: `1px solid ${C.linea}`, background: 'var(--en-oscuro-superficie, #fff)',
                  cursor: pagina <= 1 ? 'default' : 'pointer' }}>
                Anterior
              </button>
              <span style={{ fontSize: 13, color: C.suave }}>
                {pagina} de {paginas} · {datos.total} avisos
              </span>
              <button onClick={() => traer(pagina + 1)} disabled={pagina >= paginas}
                data-testid="hoja-siguiente"
                style={{ padding: '6px 14px', fontSize: 13, borderRadius: 8,
                  border: `1px solid ${C.linea}`, background: 'var(--en-oscuro-superficie, #fff)',
                  cursor: pagina >= paginas ? 'default' : 'pointer' }}>
                Siguiente
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
