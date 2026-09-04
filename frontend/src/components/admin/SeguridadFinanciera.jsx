/**
 * SeguridadFinanciera.jsx — Informe de control interno sobre el dinero.
 *
 * POR QUE ESTA PANTALLA EXISTE
 *
 *   Los controles que responden por el dinero existían todos, y estaban
 *   repartidos: la reconciliación y la integridad adentro del Libro mayor, el
 *   rastro de quién tocó plata adentro de Auditoría, y las llaves del dinero
 *   adentro de Recursos Humanos. Para saber si la aplicación estaba sana había
 *   que recorrer tres pantallas y saber de antemano qué buscar en cada una.
 *
 *   Y el más importante de todos no estaba en ninguna: la conciliación del
 *   pozo —`GET /admin/ledger/pozo`— estaba escrita, probada y expuesta, y no
 *   tenía pantalla. El control de solvencia de la plataforma funcionaba y
 *   nadie podía mirarlo.
 *
 * POR QUE SE VE COMO UN INFORME Y NO COMO UN TABLERO
 *
 *   Un tablero está hecho para mirarlo de reojo: colores grandes, una cifra
 *   enorme, la respuesta en tres segundos. Sirve para operar.
 *
 *   Esto no se usa para operar. Se usa para RESPONDER: ante un auditor, ante
 *   un proveedor de pagos que homologa, ante uno mismo cuando algo no cierra.
 *   Y para eso la forma que funciona es la del papel de trabajo: cada control
 *   con su identificador, su objetivo, su resultado, su evidencia y el alcance
 *   de lo que NO mira.
 *
 *   De ahí las decisiones de diseño, que no son estéticas:
 *
 *     · Identificadores fijos (C-01 … C-05). Se puede citar «la excepción del
 *       C-02» en un correo y todos saben de qué se habla.
 *     · Vocabulario de dictamen —CONFORME, EXCEPCIÓN, CON OBSERVACIONES, NO
 *       VERIFICADO— en vez de «Sí» y «No». Es el idioma en el que se contesta
 *       una homologación.
 *     · El color no lleva información solo: siempre hay una palabra al lado.
 *       Un informe que sólo se entiende en pantalla y a color no sirve
 *       impreso, ni para quien no distingue rojo de verde.
 *     · Cifras con numeración tabular y alineadas a la derecha, para que dos
 *       importes se puedan comparar de un vistazo por su forma.
 *     · Hoja de estilo de impresión: esto se imprime y se archiva.
 *
 * NO SABER NO ES ESTAR BIEN
 *
 *   Cada bloque se pide por separado y falla por separado. Si el pozo no
 *   contesta, el pozo queda NO VERIFICADO y las otras tres respuestas se
 *   muestran igual. Las dos alternativas eran peores: una pantalla en blanco
 *   por una consulta caída, o una tarjeta que se queda en verde porque el
 *   `catch` no la tocó. La segunda es la que hace daño: alguien la mira, la ve
 *   conforme y se va tranquilo.
 *
 *   La misma regla gobierna el dictamen del encabezado: nunca dice «conforme»
 *   si quedó algún control sin verificar. Eso vive en `utils/seguridadFinanciera.js`
 *   y tiene pruebas propias.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, ArrowRight, CheckCircle2, HelpCircle, KeyRound, Printer,
  RefreshCw, ShieldAlert,
} from 'lucide-react';
import api from '../../utils/api';
import ErrorBoundary from '../common/ErrorBoundary';
import {
  CONSULTAS, DICTAMEN_ETIQUETA, DICTAMEN_GENERAL_ETIQUETA, ETIQUETA_DEL_ACCESO,
  PERMISOS_QUE_MUEVEN_DINERO, PERMISOS_QUE_MUEVEN_LA_TASA, dictamen,
  llaverosDelDinero, resumen,
} from '../../utils/seguridadFinanciera';

/* ─── Sistema visual ───────────────────────────────────────────────────────
 *
 * Paleta institucional: neutros que hacen el trabajo y un solo azul profundo
 * como acento. Los cuatro colores de estado son sobrios a propósito —un
 * informe no se pinta, se lee— y ninguno aparece nunca sin su palabra al lado.
 */
const C = {
  tinta: '#0B1F33',
  texto: '#1F2D3D',
  segundo: '#5A6B7B',
  tenue: '#8A99A8',
  linea: '#DEE4EA',
  lineaFuerte: '#C3CEDA',
  lienzo: '#FFFFFF',
  fondo: '#F6F8FA',
  acento: '#14395E',
  conforme: '#0F6B41',
  excepcion: '#A11B1B',
  reparo: '#8A5A00',
  sinDato: '#5A6B7B',
};

// Las palabras vienen del módulo de lógica —son lo que se cita, y tienen
// prueba propia—; acá se les pone color e ícono, que es lo único de esto que
// es presentación.
const DICTAMEN = {
  bien: { color: C.conforme, Icono: CheckCircle2 },
  mal: { color: C.excepcion, Icono: ShieldAlert },
  atencion: { color: C.reparo, Icono: AlertTriangle },
  neutro: { color: C.segundo, Icono: KeyRound },
  desconocido: { color: C.sinDato, Icono: HelpCircle },
};

const COLOR_GENERAL = {
  conforme: C.conforme,
  observaciones: C.reparo,
  sin_verificar: C.sinDato,
  excepcion: C.excepcion,
};

// Identificadores fijos. No se reordenan ni se renumeran: la gracia de un
// identificador es que signifique lo mismo el mes que viene.
const CODIGO = {
  pozo: 'C-01',
  reconciliacion: 'C-02',
  integridad: 'C-03',
  llaves: 'C-04',
  movimientos: 'C-05',
  cofre: 'C-06',
};

const HOJA = `
.sf { --sf-linea: ${C.linea}; color: ${C.texto};
      font-variant-numeric: tabular-nums lining-nums;
      font-feature-settings: "tnum" 1, "lnum" 1; }
.sf h2, .sf h3 { color: ${C.tinta}; }
.sf table { border-collapse: collapse; width: 100%; }
.sf .sf-num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.sf .sf-boton { transition: background-color .12s ease, border-color .12s ease; }
.sf .sf-boton:hover:not(:disabled) { background-color: ${C.fondo}; border-color: ${C.lineaFuerte}; }
.sf .sf-boton-primario:hover:not(:disabled) { background-color: #0E2A46; border-color: #0E2A46; }
.sf .sf-fila:hover { background-color: ${C.fondo}; }
.sf .sf-enlace:hover { border-color: ${C.acento}; }
.sf :focus-visible { outline: 2px solid ${C.acento}; outline-offset: 2px; }

/* Esto se imprime y se archiva: sin botones, sin cortes en medio de un
   control, y con las líneas que el papel necesita para separar. */
@media print {
  .sf-no-imprimir { display: none !important; }
  .sf { font-size: 11pt; }
  .sf-control { break-inside: avoid; page-break-inside: avoid; }
  .sf-tarjeta { border: 1px solid #999 !important; box-shadow: none !important; }
}
`;

const marco = {
  backgroundColor: C.lienzo,
  border: `1px solid ${C.linea}`,
  borderRadius: '6px',
};

const microEtiqueta = {
  fontSize: '10.5px', fontWeight: 700, letterSpacing: '.09em',
  textTransform: 'uppercase', color: C.tenue, margin: 0,
};

/* ─── Formato ──────────────────────────────────────────────────────────── */

function monto(valor) {
  if (valor === null || valor === undefined || valor === '') return '—';
  const n = Number(valor);
  if (!Number.isFinite(n)) return String(valor);
  return n.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function entero(valor) {
  const n = Number(valor);
  return Number.isFinite(n) ? n.toLocaleString('es-VE') : '—';
}

function fecha(d, conSegundos = false) {
  if (!d) return '—';
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return String(d);
  return dt.toLocaleString('es-VE', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: false,
    ...(conSegundos ? { second: '2-digit' } : {}),
  });
}

/* ─── Piezas ───────────────────────────────────────────────────────────── */

function Sello({ estado, tamano = 'normal' }) {
  const d = DICTAMEN[estado] || DICTAMEN.desconocido;
  const chico = tamano === 'chico';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '6px',
      color: d.color, fontWeight: 700, whiteSpace: 'nowrap',
      fontSize: chico ? '11px' : '12px',
      letterSpacing: '.06em', textTransform: 'uppercase',
    }}>
      <d.Icono size={chico ? 13 : 15} strokeWidth={2.2} style={{ flexShrink: 0 }} />
      {DICTAMEN_ETIQUETA[estado] || DICTAMEN_ETIQUETA.desconocido}
    </span>
  );
}

function Nota({ estado = 'info', titulo, children }) {
  const color = { mal: C.excepcion, atencion: C.reparo, bien: C.conforme,
    desconocido: C.sinDato, info: C.acento }[estado] || C.acento;
  return (
    <div style={{
      borderLeft: `3px solid ${color}`, backgroundColor: C.fondo,
      padding: '11px 14px', borderRadius: '0 4px 4px 0',
    }}>
      {titulo ? (
        <p style={{ margin: '0 0 3px 0', fontSize: '12.5px', fontWeight: 700, color }}>
          {titulo}
        </p>
      ) : null}
      <div style={{ fontSize: '12.5px', color: C.texto, lineHeight: 1.6 }}>{children}</div>
    </div>
  );
}

function Tabla({ cabeceras, filas, vacio = 'Sin registros.' }) {
  return (
    <div style={{ ...marco, overflow: 'hidden' }}>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr style={{ borderBottom: `1px solid ${C.lineaFuerte}` }}>
              {cabeceras.map((c) => {
                const num = typeof c === 'object';
                const texto = num ? c.texto : c;
                return (
                  <th key={texto} className={num ? 'sf-num' : undefined}
                    style={{ ...microEtiqueta, padding: '9px 14px',
                      textAlign: num ? 'right' : 'left', whiteSpace: 'nowrap' }}>
                    {texto}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {filas.length === 0 ? (
              <tr>
                <td colSpan={cabeceras.length} style={{ padding: '26px 14px',
                  textAlign: 'center', color: C.tenue, fontSize: '12.5px' }}>{vacio}</td>
              </tr>
            ) : filas.map((fila, i) => (
              <tr key={i} className="sf-fila"
                style={{ borderTop: i === 0 ? 'none' : `1px solid ${C.linea}` }}>
                {fila.map((celda, j) => {
                  const num = typeof cabeceras[j] === 'object';
                  return (
                    <td key={j} className={num ? 'sf-num' : undefined}
                      style={{ padding: '10px 14px', verticalAlign: 'top',
                        fontSize: '12.5px', color: C.texto }}>{celda}</td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Cifra({ etiqueta, valor, sufijo, destacada, color }) {
  return (
    <div>
      <p style={microEtiqueta}>{etiqueta}</p>
      <p className="sf-num" style={{
        margin: '5px 0 0 0', textAlign: 'left',
        fontSize: destacada ? '24px' : '19px',
        fontWeight: destacada ? 700 : 600,
        color: color || C.tinta, lineHeight: 1.15,
      }}>
        {valor}
        {sufijo ? (
          <span style={{ fontSize: '12px', fontWeight: 600, color: C.tenue,
            marginLeft: '5px', letterSpacing: '.04em' }}>{sufijo}</span>
        ) : null}
      </p>
    </div>
  );
}

function Enlace({ onClick, children }) {
  if (!onClick) return null;
  return (
    <button type="button" onClick={onClick} className="sf-enlace sf-no-imprimir"
      style={{ display: 'inline-flex', alignItems: 'center', gap: '7px',
        padding: '8px 13px', borderRadius: '5px', border: `1px solid ${C.linea}`,
        backgroundColor: C.lienzo, color: C.acento, fontWeight: 600,
        fontSize: '12.5px', cursor: 'pointer' }}>
      {children} <ArrowRight size={13} />
    </button>
  );
}

function Boton(props) {
  const { onClick, disabled, primario, children } = props;
  // Aparte y no en la firma: el eslint de este repo no tiene el plugin de
  // React, así que no ve que un parámetro se use como etiqueta JSX. Como
  // variable en mayúscula sí lo deja pasar.
  const Icono = props.Icono;
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      className={`sf-boton sf-no-imprimir${primario ? ' sf-boton-primario' : ''}`}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: '7px',
        padding: '9px 15px', borderRadius: '5px',
        border: `1px solid ${primario ? C.acento : C.linea}`,
        backgroundColor: primario ? C.acento : C.lienzo,
        color: primario ? '#fff' : C.texto,
        fontWeight: 600, fontSize: '12.5px',
        cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.55 : 1,
      }}>
      <Icono size={14} />{children}
    </button>
  );
}

function Control({ clave, titulo, objetivo, estado, informativo, children, accion }) {
  return (
    <section className="sf-control" style={{ ...marco, padding: 0, overflow: 'hidden' }}>
      <header style={{
        display: 'flex', alignItems: 'flex-start', gap: '14px', flexWrap: 'wrap',
        padding: '14px 18px', borderBottom: `1px solid ${C.linea}`,
        backgroundColor: C.fondo,
      }}>
        <div style={{ flex: 1, minWidth: '260px' }}>
          <p style={{ ...microEtiqueta, color: C.acento }}>{CODIGO[clave]}</p>
          <h3 style={{ margin: '3px 0 0 0', fontSize: '15px', fontWeight: 700 }}>{titulo}</h3>
          <p style={{ margin: '5px 0 0 0', fontSize: '12.5px', color: C.segundo,
            lineHeight: 1.6, maxWidth: '76ch' }}>{objetivo}</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {accion}
          {estado ? <Sello estado={estado} /> : null}
          {informativo ? (
            <span style={{ ...microEtiqueta, color: C.segundo, whiteSpace: 'nowrap' }}>
              Informativo · sin dictamen
            </span>
          ) : null}
        </div>
      </header>
      <div style={{ padding: '18px', display: 'grid', gap: '14px' }}>
        {/* Un límite de error POR CONTROL. Si el pozo devuelve una forma que
            este código no sabe leer, se rompe el pozo y los otros cuatro se
            siguen viendo. Un solo límite arriba convertiría cualquier campo
            inesperado en un informe sin ninguna respuesta. */}
        <ErrorBoundary clave={clave} donde={`Seguridad financiera · ${CODIGO[clave]}`}>
          {children}
        </ErrorBoundary>
      </div>
    </section>
  );
}

function NoVerificado({ que, error }) {
  return (
    <Nota estado="desconocido" titulo={`No se pudo verificar: ${que}`}>
      {error || 'La consulta no respondió.'} Este control queda <strong>sin
      verificar</strong>, que no es lo mismo que conforme: no hay base para
      afirmar nada sobre esta parte. Volvé a ejecutar el informe; si persiste,
      el problema está en el servidor, no en el dinero.
    </Nota>
  );
}

/* ─── C-01 · Solvencia ─────────────────────────────────────────────────── */

function Pozo({ bloque }) {
  if (bloque.estado !== 'ok') return <NoVerificado que="la solvencia" error={bloque.error} />;
  const v = bloque.valor || {};
  const cubre = v.cubre === true;
  const cuentas = v.activo?.cuentas || [];
  const trabajo = Object.entries(v.capital_de_trabajo || {});

  return (
    <>
      {/* El estado de situación, leído como se lee un balance: obligación,
          respaldo, y la diferencia entre los dos. */}
      <div style={{ ...marco, backgroundColor: C.fondo, padding: '18px',
        display: 'grid', gap: '16px',
        gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
        <Cifra etiqueta={`Pasivo · ${v.moneda || ''}`} valor={monto(v.pasivo?.total)} />
        <Cifra etiqueta={`Activo de respaldo · ${v.moneda || ''}`} valor={monto(v.activo?.total)} />
        <Cifra etiqueta="Diferencia" valor={monto(v.diferencia)} destacada
          color={cubre ? C.conforme : C.excepcion} sufijo={v.moneda} />
      </div>

      <p style={{ margin: 0, fontSize: '12.5px', color: C.segundo, lineHeight: 1.65 }}>
        El pasivo es la suma de los saldos de <strong>{entero(v.pasivo?.usuarios_con_saldo)}</strong>{' '}
        usuarios con saldo, sobre <strong>{entero(v.pasivo?.usuarios_revisados)}</strong>{' '}
        revisados. La tolerancia es <strong>cero</strong>: un pozo que acepta un
        faltante «chico» es un pozo donde el faltante crece sin que nadie lo mire.
      </p>

      {v.pasivo?.truncado ? (
        <Nota estado="atencion" titulo="Limitación al alcance: el recuento se cortó">
          Hay más usuarios de los que este control puede recorrer en una sola
          consulta. El pasivo informado es un piso, no el total.
        </Nota>
      ) : null}

      <Tabla
        cabeceras={['Cuenta de respaldo', { texto: 'Saldo' }, 'Naturaleza']}
        vacio="No hay cuentas en la moneda que respalda el pasivo."
        filas={cuentas.map((c) => [
          <span style={{ fontWeight: 600 }}>{c.nombre || c.bank_id}</span>,
          <span style={{ fontWeight: 600 }}>{monto(c.saldo)} <span
            style={{ color: C.tenue, fontSize: '11px' }}>{c.moneda}</span></span>,
          <span style={{ color: C.segundo }}>
            {[c.es_pasarela ? 'Pasarela' : 'Cuenta propia',
              c.oculta ? 'oculta del panel' : null].filter(Boolean).join(' · ')}
          </span>,
        ])}
      />

      {v.activo?.cuentas_ocultas > 0 ? (
        <p style={{ margin: 0, fontSize: '12px', color: C.segundo, lineHeight: 1.6 }}>
          {v.activo.cuentas_ocultas === 1
            ? 'Una de esas cuentas está oculta'
            : `${entero(v.activo.cuentas_ocultas)} de esas cuentas están ocultas`}{' '}
          del resto del panel. Se computan igual: esconder una cuenta no le saca
          la plata, y para una pregunta de solvencia el dinero es dinero.
        </p>
      ) : null}

      {trabajo.length > 0 ? (
        <Nota titulo="Capital de trabajo — informado por separado">
          {trabajo.map(([moneda, caja]) => (
            <div key={moneda} style={{ fontVariantNumeric: 'tabular-nums' }}>
              <strong>{monto(caja.total)} {moneda}</strong> en {entero(caja.cuentas)}{' '}
              {caja.cuentas === 1 ? 'cuenta' : 'cuentas'}
            </div>
          ))}
          <p style={{ margin: '7px 0 0 0' }}>
            No integra el activo de respaldo, y es a propósito: paga operaciones
            cuyo RIS ya salió del saldo del usuario, así que no respalda un
            pasivo. Sumarlo taparía un faltante de {v.moneda} con dinero que ya
            tiene dueño.
          </p>
        </Nota>
      ) : null}

      {(v.no_incluido || []).length > 0 ? (
        <Nota titulo="Alcance: lo que este control no comprende">
          <ul style={{ margin: '4px 0 0 0', paddingLeft: '17px' }}>
            {v.no_incluido.map((t) => <li key={t} style={{ marginBottom: '3px' }}>{t}</li>)}
          </ul>
        </Nota>
      ) : null}
    </>
  );
}

/* ─── C-02 · Reconciliación ────────────────────────────────────────────── */

function Descuadres({ bloque, irAlLibro }) {
  if (bloque.estado !== 'ok') return <NoVerificado que="la reconciliación" error={bloque.error} />;
  const v = bloque.valor || {};
  const cuadra = v.cuadra === true;
  const primeros = (v.descuadres || []).slice(0, 5);
  const huerfanas = (v.lineas_sin_usuario || []).length;

  return (
    <>
      <div style={{ display: 'grid', gap: '16px',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <Cifra etiqueta="Usuarios revisados" valor={entero(v.usuarios_revisados)} />
        <Cifra etiqueta="Asientos leídos" valor={entero(v.lineas_leidas)} />
        <Cifra etiqueta="Cuentas sin cuadrar" valor={entero(v.descuadres_totales)} destacada
          color={cuadra ? C.conforme : C.excepcion} />
      </div>

      <p style={{ margin: 0, fontSize: '12.5px', color: C.segundo, lineHeight: 1.65 }}>
        {cuadra
          ? 'Cada saldo guardado coincide con la suma de sus asientos. Tolerancia cero.'
          : 'El saldo guardado no coincide con la suma de los asientos: el dinero registrado no es el dinero que la aplicación dice tener.'}
      </p>

      {huerfanas > 0 ? (
        <Nota estado="mal" titulo={`${entero(huerfanas)} asientos sin titular`}>
          Pertenecen a usuarios que ya no existen. Es un descuadre distinto y
          más grave que una diferencia de saldo: hay plata registrada contra
          nadie.
        </Nota>
      ) : null}

      {primeros.length > 0 ? (
        <>
          <Tabla
            cabeceras={['Usuario', 'Cuenta contable', { texto: 'Saldo guardado' },
              { texto: 'Suma del libro' }, { texto: 'Diferencia' }]}
            filas={primeros.map((d) => [
              <div>
                <div style={{ fontWeight: 600 }}>{d.nombre || d.user_id}</div>
                {d.email ? <div style={{ color: C.tenue, fontSize: '11.5px' }}>{d.email}</div> : null}
              </div>,
              <span style={{ color: C.segundo }}>{d.cuenta_contable}</span>,
              monto(d.saldo_guardado),
              monto(d.suma_del_libro),
              <span style={{ fontWeight: 700, color: C.excepcion }}>{monto(d.diferencia)}</span>,
            ])}
          />
          {v.descuadres_totales > primeros.length ? (
            <p style={{ margin: 0, fontSize: '12px', color: C.tenue }}>
              Se muestran {primeros.length} de {entero(v.descuadres_totales)}.
            </p>
          ) : null}
        </>
      ) : null}

      {!cuadra ? (
        <Enlace onClick={irAlLibro ? () => irAlLibro('reconciliacion') : null}>
          Ver el detalle completo en el Libro mayor
        </Enlace>
      ) : null}
    </>
  );
}

/* ─── C-03 · Integridad ────────────────────────────────────────────────── */

const GRAVEDAD = { alta: 'mal', media: 'atencion', baja: 'info' };

function Integridad({ bloque, irAlLibro }) {
  if (bloque.estado !== 'ok') return <NoVerificado que="la integridad del libro" error={bloque.error} />;
  const v = bloque.valor || {};
  const hallazgos = v.hallazgos || [];

  return (
    <>
      <div style={{ display: 'grid', gap: '16px',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <Cifra etiqueta="Asientos revisados" valor={entero(v.lineas_revisadas)} />
        <Cifra etiqueta="Tipos de defecto" valor={entero(hallazgos.length)} destacada
          color={v.sano ? C.conforme : C.excepcion} />
      </div>

      <p style={{ margin: 0, fontSize: '12.5px', color: C.segundo, lineHeight: 1.65 }}>
        Nada se corrige automáticamente: <strong>un libro que se auto-corrige es
        un libro que nadie puede auditar</strong>. Los defectos se informan para
        que se resuelvan con un asiento, no borrando el anterior.
      </p>

      {hallazgos.slice(0, 4).map((h) => (
        <Nota key={h.clave} estado={GRAVEDAD[h.gravedad] || 'info'}
          titulo={`${h.titulo} — ${entero(h.cuantas)} ${h.cuantas === 1 ? 'caso' : 'casos'}`}>
          {h.explicacion}
        </Nota>
      ))}

      {hallazgos.length > 0 ? (
        <Enlace onClick={irAlLibro ? () => irAlLibro('integridad') : null}>
          Ver el detalle completo en el Libro mayor
        </Enlace>
      ) : null}
    </>
  );
}

/* ─── C-04 · Llaves del dinero ─────────────────────────────────────────── */

function Llaves({ bloque }) {
  if (bloque.estado !== 'ok') return <NoVerificado que="las llaves del dinero" error={bloque.error} />;
  const llaveros = llaverosDelDinero(bloque.valor?.personal);
  const aMedias = llaveros.filter((f) => f.acceso !== 'listo');

  return (
    <>
      <div style={{ display: 'grid', gap: '16px',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <Cifra etiqueta="Con llaves del dinero" valor={entero(llaveros.length)} destacada />
        <Cifra etiqueta="Acceso sin terminar" valor={entero(aMedias.length)}
          color={aMedias.length > 0 ? C.reparo : C.conforme} />
      </div>

      {aMedias.length > 0 ? (
        <Nota estado="atencion" titulo="Altas de acceso sin completar">
          No constituye una exposición: el personal no obtiene sesión sin
          segundo factor —el servidor devuelve un enrolamiento, no una sesión—.
          Es trabajo de alta pendiente, no una puerta sin llave.
        </Nota>
      ) : (
        <Nota estado="bien" titulo="Todas las llaves están en cuentas aseguradas">
          Cada persona que puede mover dinero tiene su segundo factor activo.
        </Nota>
      )}

      <Tabla
        cabeceras={['Persona', 'Rol', 'Facultades sobre el dinero', 'Estado del acceso']}
        vacio="Nadie fuera del super administrador tiene llaves del dinero."
        filas={llaveros.map(({ persona, llaves, acceso }) => [
          <div>
            <div style={{ fontWeight: 600 }}>{persona.nombre || '—'}</div>
            <div style={{ color: C.tenue, fontSize: '11.5px' }}>{persona.email}</div>
          </div>,
          <span style={{ ...microEtiqueta, color: C.segundo, letterSpacing: '.05em' }}>
            {persona.rol}
          </span>,
          <div style={{ display: 'grid', gap: '3px' }}>
            {llaves.porSerSuperAdmin ? (
              <span style={{ color: C.segundo }}>
                Todas las facultades, por ser super administrador
              </span>
            ) : (
              <>
                {llaves.dinero.map((p) => (
                  <span key={p} style={{ color: C.excepcion, fontWeight: 600 }}>
                    {PERMISOS_QUE_MUEVEN_DINERO[p]}
                  </span>
                ))}
                {llaves.tasa.map((p) => (
                  <span key={p} style={{ color: C.reparo }}>
                    {PERMISOS_QUE_MUEVEN_LA_TASA[p]}
                  </span>
                ))}
              </>
            )}
          </div>,
          <span style={{ color: acceso === 'listo' ? C.conforme : C.reparo, fontWeight: 500 }}>
            {ETIQUETA_DEL_ACCESO[acceso]}
          </span>,
        ])}
      />
    </>
  );
}

/* ─── C-05 · Movimientos manuales ──────────────────────────────────────── */

function Movimientos({ bloque }) {
  if (bloque.estado !== 'ok') return <NoVerificado que="el rastro de movimientos" error={bloque.error} />;
  const lineas = bloque.valor?.lineas || [];

  return (
    <>
      <Tabla
        cabeceras={['Fecha y hora', 'Acto', 'Autorizante', 'Sujeto', 'Origen']}
        vacio="No se registran movimientos manuales de dinero."
        filas={lineas.map((l) => [
          <span style={{ whiteSpace: 'nowrap', color: C.segundo }}>{fecha(l.cuando)}</span>,
          <div>
            <div style={{ fontWeight: 600 }}>{l.etiqueta}</div>
            {l.exito === false ? (
              <div style={{ ...microEtiqueta, color: C.excepcion, marginTop: '2px' }}>
                No prosperó
              </div>
            ) : null}
          </div>,
          <div>
            <div>{l.actor?.nombre || '—'}</div>
            <div style={{ color: C.tenue, fontSize: '11.5px' }}>{l.actor?.email || '—'}</div>
          </div>,
          <span style={{ color: C.segundo }}>
            {l.objetivo?.descripcion || l.objetivo?.id || '—'}
          </span>,
          <span style={{ color: C.tenue, whiteSpace: 'nowrap', fontSize: '11.5px' }}>
            {l.origen?.ip || '—'}{l.origen?.pais ? ` · ${l.origen.pais}` : ''}
          </span>,
        ])}
      />
      <p style={{ margin: 0, fontSize: '12px', color: C.tenue, lineHeight: 1.6 }}>
        Extracto del libro de auditoría, categoría dinero. El libro se escribe y
        no se edita ni se borra: el módulo no ofrece ninguna función para
        hacerlo.
      </p>
    </>
  );
}

/* ─── Encabezado del informe ───────────────────────────────────────────── */

function Encabezado({ tarjetas, cuando, cargando, cargar }) {
  const d = dictamen(tarjetas);
  const etiquetaGeneral = DICTAMEN_GENERAL_ETIQUETA[d.estado]
    || DICTAMEN_GENERAL_ETIQUETA.sin_verificar;
  const colorGeneral = COLOR_GENERAL[d.estado] || COLOR_GENERAL.sin_verificar;

  const partes = [
    d.excepciones > 0 ? `${d.excepciones} ${d.excepciones === 1 ? 'excepción' : 'excepciones'}` : null,
    d.noVerificados > 0 ? `${d.noVerificados} sin verificar` : null,
    d.observaciones > 0 ? `${d.observaciones} con observaciones` : null,
    d.conformes > 0 ? `${d.conformes} conforme${d.conformes === 1 ? '' : 's'}` : null,
  ].filter(Boolean);

  return (
    <header style={{ ...marco, overflow: 'hidden' }}>
      <div style={{ padding: '20px 22px 18px', borderBottom: `1px solid ${C.linea}`,
        display: 'flex', gap: '18px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: '280px' }}>
          <p style={{ ...microEtiqueta, color: C.acento }}>Informe de control interno</p>
          <h2 style={{ margin: '5px 0 0 0', fontSize: '22px', fontWeight: 700,
            letterSpacing: '-.01em' }}>Seguridad financiera</h2>
          <p style={{ margin: '7px 0 0 0', fontSize: '13px', color: C.segundo,
            lineHeight: 1.6, maxWidth: '74ch' }}>
            Cinco controles sobre la integridad del dinero y sobre quién puede
            moverlo. De sólo lectura: este informe no modifica ningún saldo ni
            corrige ningún asiento.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '9px', flexWrap: 'wrap' }}>
          <Boton onClick={cargar} disabled={cargando} primario Icono={RefreshCw}>
            {cargando ? 'Ejecutando…' : 'Ejecutar controles'}
          </Boton>
          <Boton onClick={() => window.print()} Icono={Printer}>Imprimir</Boton>
        </div>
      </div>

      <dl style={{ margin: 0, padding: '14px 22px', backgroundColor: C.fondo,
        display: 'grid', gap: '16px', alignItems: 'start',
        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
        <div>
          <dt style={microEtiqueta}>Emitido</dt>
          <dd style={{ margin: '4px 0 0 0', fontSize: '13px', fontWeight: 600 }}>
            {cuando ? fecha(cuando, true) : '—'}
          </dd>
        </div>
        <div>
          <dt style={microEtiqueta}>Alcance</dt>
          <dd style={{ margin: '4px 0 0 0', fontSize: '13px', fontWeight: 600 }}>
            5 controles · 4 con dictamen
          </dd>
        </div>
        <div>
          <dt style={microEtiqueta}>Dictamen general</dt>
          <dd style={{ margin: '4px 0 0 0', fontSize: '13px', fontWeight: 700,
            color: colorGeneral }}>{etiquetaGeneral}</dd>
        </div>
        <div style={{ gridColumn: 'span 2', minWidth: '200px' }}>
          <dt style={microEtiqueta}>Resultado</dt>
          <dd style={{ margin: '4px 0 0 0', fontSize: '13px', color: C.segundo }}>
            {partes.length ? partes.join(' · ') : 'Sin ejecutar'}
          </dd>
        </div>
      </dl>
    </header>
  );
}

function Tablero({ tarjetas }) {
  return (
    <div style={{ ...marco, overflow: 'hidden' }}>
      {tarjetas.map((t, i) => (
        <div key={t.clave} style={{
          display: 'grid', gap: '10px', alignItems: 'center',
          gridTemplateColumns: 'minmax(0, 1fr) auto',
          padding: '13px 18px',
          borderTop: i === 0 ? 'none' : `1px solid ${C.linea}`,
        }}>
          <div style={{ minWidth: 0 }}>
            <p style={{ ...microEtiqueta, color: C.acento }}>{CODIGO[t.clave]}</p>
            <p style={{ margin: '3px 0 0 0', fontSize: '13.5px', fontWeight: 600,
              color: C.tinta }}>{t.pregunta}</p>
            <p style={{ margin: '3px 0 0 0', fontSize: '12px', color: C.tenue,
              lineHeight: 1.5 }}>{t.detalle}</p>
          </div>
          <div style={{ textAlign: 'right', display: 'grid', gap: '4px', justifyItems: 'end' }}>
            <Sello estado={t.estado} tamano="chico" />
            {t.cifra !== null && t.cifra !== undefined ? (
              <span className="sf-num" style={{ fontSize: '13px', color: C.segundo }}>
                {t.clave === 'pozo' ? monto(t.cifra)
                  : t.clave === 'cofre' ? t.cifra          /* la huella es texto */
                    : entero(t.cifra)}{' '}
                <span style={{ color: C.tenue, fontSize: '11px' }}>{t.unidad}</span>
              </span>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── El informe ───────────────────────────────────────────────────────── */

function Informe({ irAlLibro }) {
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [cuando, setCuando] = useState(null);

  // Un contador de peticiones, no una bandera de montado: una respuesta que
  // llega tarde no puede escribir sobre una ejecución más nueva.
  const peticion = useRef(0);

  const cargar = useCallback(async () => {
    const mia = ++peticion.current;
    setCargando(true);

    // `allSettled` y no `all`: con `all`, una consulta caída se lleva puestas a
    // las otras cuatro y el informe no muestra nada. Cada control responde por
    // sí mismo.
    const respuestas = await Promise.allSettled(
      CONSULTAS.map((c) => api.get(c.ruta, { params: c.params })),
    );
    if (peticion.current !== mia) return;

    const armado = {};
    CONSULTAS.forEach((c, i) => {
      const r = respuestas[i];
      armado[c.clave] = r.status === 'fulfilled'
        ? { estado: 'ok', valor: r.value?.data }
        : { estado: 'error', error: r.reason?.response?.data?.detail || r.reason?.message };
    });

    setDatos(armado);
    setCuando(new Date());
    setCargando(false);
  }, []);

  useEffect(() => {
    // El `await` dentro de una función propia, y no `cargar()` a secas: así el
    // setState no ocurre de forma sincrónica en el cuerpo del efecto.
    (async () => { await cargar(); })();
    // Al desmontar se invalida lo que esté en vuelo: una respuesta que llega
    // después de cerrar la pantalla no tiene dónde escribir.
    return () => { peticion.current += 1; };
  }, [cargar]);

  const tarjetas = resumen(datos);

  return (
    <div className="sf" style={{ display: 'grid', gap: '18px' }}>
      <style>{HOJA}</style>

      <Encabezado tarjetas={tarjetas} cuando={cuando} cargando={cargando} cargar={cargar} />

      <div>
        <p style={{ ...microEtiqueta, marginBottom: '8px' }}>
          Resumen de dictámenes · C-01 a C-04
        </p>
        <Tablero tarjetas={tarjetas} />
      </div>

      {datos ? (
        <>
          <Control
            clave="pozo"
            titulo="Solvencia de la cuenta ómnibus"
            objetivo="Comprobar que por cada unidad de saldo que la empresa debe a sus usuarios existe respaldo real en las cuentas. Es distinto de la reconciliación: un libro perfecto sobre un pozo vacío cuadra igual."
            estado={tarjetas.find((t) => t.clave === 'pozo')?.estado}
          >
            <Pozo bloque={datos.pozo} />
          </Control>

          <Control
            clave="reconciliacion"
            titulo="Reconciliación de saldos contra el libro"
            objetivo="Comprobar que el saldo guardado de cada usuario coincide exactamente con la suma de sus asientos. Si no coincide, la aplicación perdió o duplicó un registro."
            estado={tarjetas.find((t) => t.clave === 'reconciliacion')?.estado}
          >
            <Descuadres bloque={datos.reconciliacion} irAlLibro={irAlLibro} />
          </Control>

          <Control
            clave="integridad"
            titulo="Integridad del libro mayor"
            objetivo="Detectar los defectos que impedirían sostener el libro ante un auditor: asientos incompletos, saldos que no encadenan, referencias rotas."
            estado={tarjetas.find((t) => t.clave === 'integridad')?.estado}
          >
            <Integridad bloque={datos.integridad} irAlLibro={irAlLibro} />
          </Control>

          <Control
            clave="llaves"
            titulo="Segregación de funciones sobre el dinero"
            objetivo="Identificar a todo el personal facultado para mover saldo o modificar la tasa, y el estado de aseguramiento de su acceso. El super administrador figura siempre: los permisos existen para repartir trabajo, y él es de quien se reparte."
            estado={tarjetas.find((t) => t.clave === 'llaves')?.estado}
          >
            <Llaves bloque={datos.personal} />
          </Control>

          <Control
            clave="movimientos"
            titulo="Movimientos manuales de dinero"
            objetivo="Dejar a la vista los últimos actos de intervención humana sobre el dinero: ajustes de saldo, y recargas y retiros aprobados o rechazados, con su autorizante y su origen."
            informativo
          >
            <Movimientos bloque={datos.movimientos} />
          </Control>

          <footer style={{ borderTop: `1px solid ${C.linea}`, paddingTop: '14px' }}>
            <p style={{ margin: 0, fontSize: '11.5px', color: C.tenue, lineHeight: 1.7 }}>
              Informe generado por la propia plataforma a partir de sus registros
              contables y de auditoría, en el momento indicado en el encabezado.
              Los importes se calculan con aritmética decimal exacta y tolerancia
              cero. Un control marcado <strong>no verificado</strong> significa
              que la consulta no respondió: no equivale a conforme.
              Acceso restringido al super administrador.
            </p>
          </footer>
        </>
      ) : (
        <p style={{ color: C.tenue, fontSize: '13px' }}>Ejecutando controles…</p>
      )}
    </div>
  );
}

export default function SeguridadFinanciera({ irAlLibro }) {
  return (
    <ErrorBoundary donde="Seguridad financiera">
      <Informe irAlLibro={irAlLibro} />
    </ErrorBoundary>
  );
}
