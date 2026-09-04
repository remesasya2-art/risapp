/**
 * SeguridadFinanciera.jsx — El área donde se mira si la plata está.
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
 * LA DIFERENCIA ENTRE ESTA PANTALLA Y EL LIBRO MAYOR
 *
 *   El Libro mayor es contabilidad: el detalle, cuenta por cuenta y asiento
 *   por asiento. Esto es seguridad: cuatro preguntas y cuatro respuestas, y un
 *   camino al detalle para cuando alguna venga en rojo. Por eso la
 *   reconciliación y la integridad se muestran acá con el veredicto y las
 *   primeras filas, y el resto se mira allá — no se dibuja dos veces la misma
 *   tabla en dos lugares que después se desincronizan.
 *
 * NO SABER NO ES ESTAR BIEN
 *
 *   Cada bloque se pide por separado y falla por separado. Si el pozo no
 *   contesta, el pozo queda en gris —«no se pudo comprobar»— y las otras tres
 *   respuestas se muestran igual. Las dos alternativas eran peores: una
 *   pantalla en blanco por una consulta caída, o una tarjeta que se queda
 *   verde porque el `catch` no la tocó. La segunda es la que hace daño: alguien
 *   la mira, la ve verde y se va tranquilo.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, ArrowRight, CheckCircle2, HelpCircle, KeyRound, Landmark,
  RefreshCw, ScrollText, ShieldAlert, ShieldCheck,
} from 'lucide-react';
import api from '../../utils/api';
import ErrorBoundary from '../common/ErrorBoundary';
import {
  CONSULTAS, ETIQUETA_DEL_ACCESO, PERMISOS_QUE_MUEVEN_DINERO,
  PERMISOS_QUE_MUEVEN_LA_TASA, llaverosDelDinero, resumen,
} from '../../utils/seguridadFinanciera';

const COLOR = {
  borde: '#e5e7eb', suave: '#6b7280', texto: '#111827',
  primario: '#4F46E5', primarioSuave: '#eef0ff',
  alerta: '#b45309', alertaSuave: '#fffbeb', alertaBorde: '#fde68a',
  malo: '#b91c1c', maloSuave: '#fef2f2', maloBorde: '#fecaca',
  bien: '#15803d', bienSuave: '#f0fdf4', bienBorde: '#bbf7d0',
  gris: '#4b5563', grisSuave: '#f9fafb', grisBorde: '#e5e7eb',
};

const tarjeta = {
  backgroundColor: '#fff', borderRadius: '16px', padding: '18px',
  border: `1px solid ${COLOR.borde}`,
};

// El gris del desconocido es tan importante como el rojo del mal: es lo que
// impide que una consulta caída se lea como una respuesta buena.
const TONOS = {
  bien: [COLOR.bienSuave, COLOR.bienBorde, COLOR.bien, CheckCircle2],
  mal: [COLOR.maloSuave, COLOR.maloBorde, COLOR.malo, ShieldAlert],
  atencion: [COLOR.alertaSuave, COLOR.alertaBorde, COLOR.alerta, AlertTriangle],
  neutro: [COLOR.grisSuave, COLOR.grisBorde, COLOR.gris, KeyRound],
  desconocido: [COLOR.grisSuave, COLOR.grisBorde, COLOR.suave, HelpCircle],
  info: [COLOR.primarioSuave, '#c7d2fe', COLOR.primario, HelpCircle],
};

const RESPUESTA = {
  bien: 'Sí',
  mal: 'No',
  atencion: 'Con reparos',
  neutro: 'Sin novedad',
  desconocido: 'No se pudo comprobar',
};

function monto(valor) {
  if (valor === null || valor === undefined || valor === '') return '—';
  const n = Number(valor);
  if (!Number.isFinite(n)) return String(valor);
  return n.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fecha(d) {
  if (!d) return '—';
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return String(d);
  return dt.toLocaleString('es-VE', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

/* ─── Piezas ───────────────────────────────────────────────────────────── */

function Aviso({ tono = 'info', titulo, children }) {
  const [fondo, borde, color, Icono] = TONOS[tono] || TONOS.info;
  return (
    <div style={{ ...tarjeta, backgroundColor: fondo, borderColor: borde }}>
      <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
        <Icono size={18} color={color} style={{ flexShrink: 0, marginTop: '1px' }} />
        <div style={{ fontSize: '13px', color, lineHeight: 1.55 }}>
          <strong style={{ display: 'block', marginBottom: '3px' }}>{titulo}</strong>
          {children}
        </div>
      </div>
    </div>
  );
}

function Tabla({ cabeceras, filas, vacio = 'Nada que mostrar.' }) {
  return (
    <div style={{ ...tarjeta, padding: 0, overflow: 'hidden' }}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
          <thead>
            <tr style={{ backgroundColor: '#f9fafb' }}>
              {cabeceras.map((c) => (
                <th key={c} style={{ padding: '10px 12px', textAlign: 'left',
                  fontSize: '11px', fontWeight: 700, letterSpacing: '.4px',
                  textTransform: 'uppercase', color: COLOR.suave,
                  whiteSpace: 'nowrap' }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.length === 0 ? (
              <tr>
                <td colSpan={cabeceras.length} style={{ padding: '26px',
                  textAlign: 'center', color: COLOR.suave }}>{vacio}</td>
              </tr>
            ) : filas.map((fila, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${COLOR.borde}` }}>
                {fila.map((celda, j) => (
                  <td key={j} style={{ padding: '10px 12px', verticalAlign: 'top' }}>{celda}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Seccion(props) {
  const { clave, titulo, bajada, children, accion } = props;
  // Se saca aparte y no en la firma: el eslint de este repo no tiene el plugin
  // de React, así que no ve que un parámetro se use como etiqueta JSX y lo
  // marca sin usar. Como variable en mayúscula sí lo deja pasar.
  const Icono = props.Icono;
  return (
    <section style={{ display: 'grid', gap: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', flexWrap: 'wrap' }}>
        <Icono size={18} color={COLOR.primario} style={{ marginTop: '2px', flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: '240px' }}>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800, color: COLOR.texto }}>{titulo}</h3>
          {bajada ? (
            <p style={{ margin: '3px 0 0 0', fontSize: '13px', color: COLOR.suave, lineHeight: 1.5 }}>
              {bajada}
            </p>
          ) : null}
        </div>
        {accion}
      </div>
      {/* Un límite de error POR SECCION, no uno para toda la pantalla. Si el
          pozo devuelve una forma que este código no sabe leer, se rompe el
          pozo y las otras cuatro respuestas se siguen viendo. Un solo límite
          arriba convertiría cualquier campo inesperado en una pantalla sin
          ninguna respuesta. */}
      <ErrorBoundary clave={clave} donde={`Seguridad financiera · ${titulo}`}>
        {children}
      </ErrorBoundary>
    </section>
  );
}

function Enlace({ onClick, children }) {
  if (!onClick) return null;
  return (
    <button
      type="button"
      onClick={onClick}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '6px',
        padding: '8px 12px', borderRadius: '10px', border: `1px solid ${COLOR.borde}`,
        backgroundColor: '#fff', color: COLOR.primario, fontWeight: 700,
        fontSize: '13px', cursor: 'pointer' }}
    >
      {children} <ArrowRight size={14} />
    </button>
  );
}

function Veredicto({ item }) {
  const [fondo, borde, color, Icono] = TONOS[item.estado] || TONOS.desconocido;
  return (
    <div style={{ ...tarjeta, backgroundColor: fondo, borderColor: borde,
      display: 'grid', gap: '8px', alignContent: 'start' }}>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
        <Icono size={16} color={color} style={{ flexShrink: 0 }} />
        <span style={{ fontSize: '13px', fontWeight: 800, color: COLOR.texto, lineHeight: 1.35 }}>
          {item.pregunta}
        </span>
      </div>
      <p style={{ margin: 0, fontSize: '22px', fontWeight: 800, color }}>
        {RESPUESTA[item.estado] || RESPUESTA.desconocido}
      </p>
      {item.cifra !== null && item.cifra !== undefined ? (
        <p style={{ margin: 0, fontSize: '12px', color: COLOR.suave, fontVariantNumeric: 'tabular-nums' }}>
          {item.clave === 'pozo' ? monto(item.cifra) : item.cifra} {item.unidad}
        </p>
      ) : null}
      <p style={{ margin: 0, fontSize: '12px', color: COLOR.suave, lineHeight: 1.45 }}>
        {item.detalle}
      </p>
    </div>
  );
}

function NoSePudo({ que, error }) {
  return (
    <Aviso tono="desconocido" titulo={`No se pudo comprobar: ${que}`}>
      {error || 'La consulta no respondió.'} Mientras tanto esto no está
      verificado — <strong>no es lo mismo que estar bien</strong>. Probá
      «Actualizar»; si sigue igual, es un problema del servidor, no del dinero.
    </Aviso>
  );
}

/* ─── Bloques ──────────────────────────────────────────────────────────── */

function Pozo({ bloque }) {
  if (bloque.estado !== 'ok') return <NoSePudo que="la solvencia del pozo" error={bloque.error} />;
  const v = bloque.valor || {};
  const cubre = v.cubre === true;
  const cuentas = v.activo?.cuentas || [];
  const trabajo = Object.entries(v.capital_de_trabajo || {});

  return (
    <>
      <Aviso tono={cubre ? 'bien' : 'mal'}
        titulo={cubre
          ? `Los ${v.moneda} alcanzan para todo lo que se debe`
          : `Faltan ${monto(v.diferencia)} ${v.moneda}`}>
        La empresa debe <strong>{monto(v.pasivo?.total)}</strong> (la suma de los
        saldos de {v.pasivo?.usuarios_con_saldo} usuarios con saldo, sobre{' '}
        {v.pasivo?.usuarios_revisados} revisados) y tiene{' '}
        <strong>{monto(v.activo?.total)} {v.moneda}</strong> en las cuentas. La
        tolerancia es cero: un pozo que acepta un faltante «chico» es un pozo
        donde el faltante crece sin que nadie lo mire.
      </Aviso>

      {v.pasivo?.truncado ? (
        <Aviso tono="atencion" titulo="El recuento se cortó">
          Hay más usuarios de los que este control puede recorrer en una
          consulta. El pasivo informado es un piso, no el total.
        </Aviso>
      ) : null}

      <Tabla
        cabeceras={['Cuenta', 'Saldo', 'Tipo']}
        vacio="No hay cuentas en la moneda que respalda el pasivo."
        filas={cuentas.map((c) => [
          <span>{c.nombre || c.bank_id}</span>,
          <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700 }}>
            {monto(c.saldo)} {c.moneda}
          </span>,
          <span style={{ fontSize: '12px', color: COLOR.suave }}>
            {[c.es_pasarela ? 'Pasarela' : null, c.oculta ? 'Oculta del panel' : null]
              .filter(Boolean).join(' · ') || 'Cuenta propia'}
          </span>,
        ])}
      />

      {v.activo?.cuentas_ocultas > 0 ? (
        <p style={{ margin: 0, fontSize: '12px', color: COLOR.suave, lineHeight: 1.5 }}>
          {v.activo.cuentas_ocultas} de esas cuentas están ocultas del resto del
          panel. Se cuentan igual: esconder una cuenta no le saca la plata, y
          para una pregunta de solvencia el dinero es dinero.
        </p>
      ) : null}

      {trabajo.length > 0 ? (
        <Aviso tono="info" titulo="Capital de trabajo, informado aparte">
          {trabajo.map(([moneda, caja]) => (
            <div key={moneda}>
              <strong>{monto(caja.total)} {moneda}</strong> en {caja.cuentas}{' '}
              {caja.cuentas === 1 ? 'cuenta' : 'cuentas'}
            </div>
          ))}
          <p style={{ margin: '6px 0 0 0' }}>
            No entran en la cuenta de arriba y es a propósito: pagan operaciones
            cuyo RIS ya salió del saldo del usuario, así que no respaldan un
            pasivo. Sumarlos taparía un faltante de {v.moneda} con dinero que ya
            tiene dueño.
          </p>
        </Aviso>
      ) : null}

      {(v.no_incluido || []).length > 0 ? (
        <Aviso tono="info" titulo="Lo que este control NO mira">
          <ul style={{ margin: '4px 0 0 0', paddingLeft: '18px' }}>
            {v.no_incluido.map((t) => <li key={t}>{t}</li>)}
          </ul>
        </Aviso>
      ) : null}
    </>
  );
}

function Descuadres({ bloque, irAlLibro }) {
  if (bloque.estado !== 'ok') return <NoSePudo que="la reconciliación" error={bloque.error} />;
  const v = bloque.valor || {};
  const cuadra = v.cuadra === true;
  const primeros = (v.descuadres || []).slice(0, 5);
  const huerfanas = (v.lineas_sin_usuario || []).length;

  return (
    <>
      <Aviso tono={cuadra ? 'bien' : 'mal'}
        titulo={cuadra ? 'Cada saldo coincide con su libro'
          : `${v.descuadres_totales} cuentas no cuadran`}>
        Se revisaron {v.usuarios_revisados} usuarios contra {v.lineas_leidas}{' '}
        líneas. {cuadra
          ? 'Sin diferencias, y la tolerancia es cero.'
          : 'El saldo guardado no coincide con la suma de los asientos: el dinero registrado no es el dinero que la aplicación dice tener.'}
      </Aviso>

      {huerfanas > 0 ? (
        <Aviso tono="mal" titulo={`${huerfanas} líneas de plata contra nadie`}>
          Pertenecen a usuarios que ya no existen. Es un descuadre distinto y
          más grave que una diferencia de saldo.
        </Aviso>
      ) : null}

      {primeros.length > 0 ? (
        <Tabla
          cabeceras={['Usuario', 'Cuenta', 'Guardado', 'Libro', 'Diferencia']}
          filas={primeros.map((d) => [
            <span>{d.nombre || d.email || d.user_id}</span>,
            d.cuenta_contable,
            <span style={{ fontVariantNumeric: 'tabular-nums' }}>{monto(d.saldo_guardado)}</span>,
            <span style={{ fontVariantNumeric: 'tabular-nums' }}>{monto(d.suma_del_libro)}</span>,
            <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700, color: COLOR.malo }}>
              {monto(d.diferencia)}
            </span>,
          ])}
        />
      ) : null}

      {!cuadra ? (
        <Enlace onClick={irAlLibro ? () => irAlLibro('reconciliacion') : null}>
          Ver las {v.descuadres_totales} en el Libro mayor
        </Enlace>
      ) : null}
    </>
  );
}

const TONO_GRAVEDAD = { alta: 'mal', media: 'atencion', baja: 'info' };

function Integridad({ bloque, irAlLibro }) {
  if (bloque.estado !== 'ok') return <NoSePudo que="la integridad del libro" error={bloque.error} />;
  const v = bloque.valor || {};
  const hallazgos = v.hallazgos || [];

  return (
    <>
      <Aviso tono={v.sano ? 'bien' : 'mal'}
        titulo={v.sano ? 'No se encontraron defectos'
          : `${hallazgos.length} ${hallazgos.length === 1 ? 'tipo de defecto' : 'tipos de defecto'}`}>
        Se revisaron {v.lineas_revisadas} líneas. Nada se corrige
        automáticamente: <strong>un libro que se auto-corrige es un libro que
        nadie puede auditar</strong>.
      </Aviso>

      {hallazgos.slice(0, 4).map((h) => (
        <Aviso key={h.clave} tono={TONO_GRAVEDAD[h.gravedad] || 'info'}
          titulo={`${h.titulo} · ${h.cuantas}`}>
          {h.explicacion}
        </Aviso>
      ))}

      {hallazgos.length > 0 ? (
        <Enlace onClick={irAlLibro ? () => irAlLibro('integridad') : null}>
          Ver el detalle en el Libro mayor
        </Enlace>
      ) : null}
    </>
  );
}

function Llaves({ bloque }) {
  if (bloque.estado !== 'ok') return <NoSePudo que="quién tiene llaves del dinero" error={bloque.error} />;
  const llaveros = llaverosDelDinero(bloque.valor?.personal);
  const aMedias = llaveros.filter((f) => f.acceso !== 'listo');

  return (
    <>
      {aMedias.length > 0 ? (
        <Aviso tono="atencion"
          titulo={`${aMedias.length} con llaves y el acceso a medio terminar`}>
          No es un agujero abierto: el personal no consigue sesión sin segundo
          factor —el servidor le devuelve un enrolamiento, no una sesión—. Es
          trabajo pendiente de alta, no una puerta sin llave.
        </Aviso>
      ) : (
        <Aviso tono="bien" titulo="Todas las llaves están en cuentas aseguradas">
          Cada persona que puede mover dinero tiene su segundo factor puesto.
        </Aviso>
      )}

      <Tabla
        cabeceras={['Persona', 'Rol', 'Qué puede hacer', 'Acceso']}
        vacio="Nadie fuera del super administrador tiene llaves del dinero."
        filas={llaveros.map(({ persona, llaves, acceso }) => [
          <div>
            <div style={{ fontWeight: 700 }}>{persona.nombre || '—'}</div>
            <div style={{ fontSize: '12px', color: COLOR.suave }}>{persona.email}</div>
          </div>,
          <span style={{ fontSize: '12px' }}>{persona.rol}</span>,
          <div style={{ display: 'grid', gap: '2px', fontSize: '12px' }}>
            {llaves.porSerSuperAdmin ? (
              <span style={{ color: COLOR.suave }}>
                Todo, por ser super administrador
              </span>
            ) : (
              <>
                {llaves.dinero.map((p) => (
                  <span key={p} style={{ color: COLOR.malo, fontWeight: 600 }}>
                    {PERMISOS_QUE_MUEVEN_DINERO[p]}
                  </span>
                ))}
                {llaves.tasa.map((p) => (
                  <span key={p} style={{ color: COLOR.alerta }}>
                    {PERMISOS_QUE_MUEVEN_LA_TASA[p]}
                  </span>
                ))}
              </>
            )}
          </div>,
          <span style={{ fontSize: '12px',
            color: acceso === 'listo' ? COLOR.bien : COLOR.alerta }}>
            {ETIQUETA_DEL_ACCESO[acceso]}
          </span>,
        ])}
      />
    </>
  );
}

function Movimientos({ bloque }) {
  if (bloque.estado !== 'ok') return <NoSePudo que="el rastro de movimientos" error={bloque.error} />;
  const lineas = bloque.valor?.lineas || [];

  return (
    <Tabla
      cabeceras={['Cuándo', 'Qué', 'Quién', 'Sobre quién', 'Desde']}
      vacio="Nadie movió dinero a mano todavía."
      filas={lineas.map((l) => [
        <span style={{ whiteSpace: 'nowrap', fontSize: '12px' }}>{fecha(l.cuando)}</span>,
        <div>
          <div style={{ fontWeight: 600 }}>{l.etiqueta}</div>
          {l.exito === false ? (
            <div style={{ fontSize: '11px', color: COLOR.malo, fontWeight: 700 }}>Falló</div>
          ) : null}
        </div>,
        <div style={{ fontSize: '12px' }}>
          <div>{l.actor?.nombre || '—'}</div>
          <div style={{ color: COLOR.suave }}>{l.actor?.email || '—'}</div>
        </div>,
        <span style={{ fontSize: '12px' }}>{l.objetivo?.descripcion || l.objetivo?.id || '—'}</span>,
        <span style={{ fontSize: '12px', color: COLOR.suave, whiteSpace: 'nowrap' }}>
          {l.origen?.ip || '—'}{l.origen?.pais ? ` · ${l.origen.pais}` : ''}
        </span>,
      ])}
    />
  );
}

/* ─── La pantalla ──────────────────────────────────────────────────────── */

function Pantalla({ irAlLibro }) {
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [cuando, setCuando] = useState(null);

  // El mismo contador que el Libro mayor, por la misma razón: una respuesta
  // que llega tarde no puede escribir sobre una consulta más nueva.
  const peticion = useRef(0);

  const cargar = useCallback(async () => {
    const mia = ++peticion.current;
    setCargando(true);

    // `allSettled` y no `all`: con `all`, una consulta caída se lleva puestas
    // a las otras cuatro y la pantalla no muestra nada. Cada bloque responde
    // por sí mismo.
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
    // El `await` adentro de una función propia y no `cargar()` a secas: así el
    // setState no ocurre de forma sincrónica en el cuerpo del efecto. Es el
    // mismo patrón que el Libro mayor.
    (async () => { await cargar(); })();
    // Al desmontar se invalida lo que esté en vuelo: una respuesta que llega
    // después de cerrar la pantalla no tiene dónde escribir.
    return () => { peticion.current += 1; };
  }, [cargar]);

  const tarjetas = resumen(datos);

  return (
    <div style={{ display: 'grid', gap: '26px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: '260px' }}>
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: COLOR.texto }}>
            Seguridad financiera
          </h2>
          <p style={{ margin: '4px 0 0 0', fontSize: '13px', color: COLOR.suave, lineHeight: 1.55 }}>
            Cuatro preguntas sobre el dinero, y quién puede tocarlo. Esta
            pantalla sólo lee: no cambia ningún saldo ni corrige ningún asiento.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {cuando ? (
            <span style={{ fontSize: '12px', color: COLOR.suave }}>
              Al {fecha(cuando)}
            </span>
          ) : null}
          <button
            type="button"
            onClick={cargar}
            disabled={cargando}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '8px',
              padding: '10px 14px', borderRadius: '10px', border: 'none',
              backgroundColor: COLOR.primario, color: '#fff', fontWeight: 700,
              fontSize: '13px', cursor: cargando ? 'default' : 'pointer',
              opacity: cargando ? 0.6 : 1 }}
          >
            <RefreshCw size={15} style={{ animation: cargando ? 'spin 1s linear infinite' : 'none' }} />
            {cargando ? 'Comprobando…' : 'Actualizar'}
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gap: '12px',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
        {tarjetas.map((t) => <Veredicto key={t.clave} item={t} />)}
      </div>

      {datos ? (
        <>
          <Seccion
            Icono={Landmark}
            clave="pozo"
            titulo="¿Está toda la plata?"
            bajada="Con una cuenta ómnibus el dinero de todos vive en un solo pozo. La única forma de saber que está todo es comparar lo que se debe contra lo que hay. Es distinto de la reconciliación: un libro perfecto sobre un pozo vacío cuadra igual."
          >
            <Pozo bloque={datos.pozo} />
          </Seccion>

          <Seccion
            Icono={ShieldCheck}
            clave="reconciliacion"
            titulo="¿Cuadra cada cuenta con su libro?"
            bajada="El saldo guardado de cada usuario contra la suma de sus asientos. Si no cuadra, la aplicación perdió una línea."
          >
            <Descuadres bloque={datos.reconciliacion} irAlLibro={irAlLibro} />
          </Seccion>

          <Seccion
            Icono={AlertTriangle}
            clave="integridad"
            titulo="¿El libro se puede defender?"
            bajada="Los defectos que impedirían sostener el libro ante un auditor."
          >
            <Integridad bloque={datos.integridad} irAlLibro={irAlLibro} />
          </Seccion>

          <Seccion
            Icono={KeyRound}
            clave="personal"
            titulo="¿Quién tiene las llaves del dinero?"
            bajada="El personal que puede mover saldo o cambiar la tasa, y cómo está su acceso. El super administrador aparece siempre: los permisos existen para repartir trabajo, y él es de quien se reparte."
          >
            <Llaves bloque={datos.personal} />
          </Seccion>

          <Seccion
            Icono={ScrollText}
            clave="movimientos"
            titulo="¿Quién movió dinero a mano?"
            bajada="Los últimos asientos del libro de auditoría en la categoría dinero: ajustes de saldo, recargas y retiros aprobados o rechazados."
          >
            <Movimientos bloque={datos.movimientos} />
          </Seccion>
        </>
      ) : (
        <p style={{ color: COLOR.suave, fontSize: '13px' }}>Comprobando…</p>
      )}
    </div>
  );
}

export default function SeguridadFinanciera({ irAlLibro }) {
  return (
    <ErrorBoundary donde="Seguridad financiera">
      <Pantalla irAlLibro={irAlLibro} />
    </ErrorBoundary>
  );
}
