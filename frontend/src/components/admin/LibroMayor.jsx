/**
 * LibroMayor.jsx — El libro contable.
 *
 * LO QUE HABIA
 *   Esta pantalla se llamaba «Libro mayor» y no era un libro mayor: era una
 *   reconciliación con dos botones. No se podía ver un asiento, ni una cuenta,
 *   ni un balance. La ruta que sí listaba movimientos exigía un `user_id` que
 *   la pantalla no tenía por dónde pedir.
 *
 * LO QUE HAY AHORA
 *   Los tres libros que la contabilidad pide —diario, mayor y balance de
 *   comprobación— y los dos controles que de verdad prueban algo: la
 *   reconciliación contra los saldos guardados y la verificación de integridad.
 *
 * POR QUE LA PANTALLA DICE LO QUE EL LIBRO NO GARANTIZA
 *   El balance cuadra por construcción: las dos partidas de cada asiento se
 *   derivan del tipo de movimiento. Una pantalla que muestra «✓ cuadra» sin esa
 *   aclaración le está diciendo a quien la mira que los datos están validados, y
 *   no lo están. El aviso no es humildad: es lo que evita una decisión tomada
 *   sobre una garantía que no existe.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import {
  AlertTriangle, BookOpen, Bitcoin, CheckCircle2, Download, FileSpreadsheet,
  Info, Layers, ScrollText, ShieldCheck, Table2,
} from 'lucide-react';
import api from '../../utils/api';
import LibroBtc from './LibroBtc';
import ErrorBoundary from '../common/ErrorBoundary';

const COLOR = {
  borde: '#e5e7eb', suave: '#6b7280', texto: '#111827',
  primario: '#4F46E5', primarioSuave: '#eef0ff',
  alerta: '#b45309', alertaSuave: '#fffbeb', alertaBorde: '#fde68a',
  malo: '#b91c1c', maloSuave: '#fef2f2', maloBorde: '#fecaca',
  bien: '#15803d', bienSuave: '#f0fdf4', bienBorde: '#bbf7d0',
};

const tarjeta = {
  backgroundColor: '#fff', borderRadius: '16px', padding: '18px',
  border: `1px solid ${COLOR.borde}`,
};

const HUSOS = [
  { min: -240, etiqueta: 'Caracas (UTC−4)' },
  { min: -180, etiqueta: 'Brasilia (UTC−3)' },
  { min: 0, etiqueta: 'UTC' },
];

const VISTAS = [
  { clave: 'balance', etiqueta: 'Balance de comprobación', Icono: Table2 },
  { clave: 'diario', etiqueta: 'Libro diario', Icono: ScrollText },
  { clave: 'mayor', etiqueta: 'Libro mayor', Icono: Layers },
  { clave: 'reconciliacion', etiqueta: 'Reconciliación', Icono: ShieldCheck },
  { clave: 'integridad', etiqueta: 'Integridad', Icono: AlertTriangle },
  { clave: 'btc', etiqueta: 'Órdenes BTC', Icono: Bitcoin },
];

const hoy = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
  .toISOString().slice(0, 10);

const primeroDelMes = () => {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1, 12).toISOString().slice(0, 10);
};

export default function LibroMayor() {
  const [vista, setVista] = useState('balance');
  const [desde, setDesde] = useState(primeroDelMes());
  const [hasta, setHasta] = useState(hoy());
  const [tz, setTz] = useState(-240);
  const [libro, setLibro] = useState('');
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [bajando, setBajando] = useState('');

  // Un contador de peticiones, NO una bandera de «montado».
  //
  // Lo que había era `const vivo = useRef(true)`, y el efecto lo ponía en
  // `true` al entrar y en `false` al salir. Con eso, cambiar de vista mientras
  // la anterior todavía estaba pidiendo dejaba pasar la respuesta VIEJA: la
  // limpieza lo ponía en `false` y el efecto nuevo lo volvía a poner en `true`
  // un instante después, así que cuando llegaba la respuesta de la vista
  // anterior el chequeo `if (!vivo.current) return` la dejaba entrar.
  //
  // Resultado: se dibujaba, por ejemplo, «Integridad» con los datos de
  // «Reconciliación». Y como esa vista lee `datos.hallazgos.length` —un campo
  // que la reconciliación no trae— el render tiraba un TypeError y React
  // desmontaba el árbol entero: PÁGINA EN BLANCO.
  //
  // Con un contador, cada carga se queda con su número y sólo escribe si sigue
  // siendo la última. Una respuesta que llega tarde se descarta, siempre.
  const peticion = useRef(0);

  const cargar = useCallback(async () => {
    if (vista === 'btc') return;
    const mia = ++peticion.current;
    setCargando(true);
    setDatos(null);
    const rutas = {
      balance: '/admin/ledger/balance',
      diario: '/admin/ledger/diario',
      mayor: '/admin/ledger/mayor',
      reconciliacion: '/admin/ledger/reconciliacion',
      integridad: '/admin/ledger/integridad',
    };
    const conFechas = ['balance', 'diario', 'mayor'].includes(vista);
    try {
      const { data } = await api.get(rutas[vista], {
        params: conFechas
          ? { desde, hasta, tz_min: tz, libro: libro || undefined, limite: 200 }
          : { libro: vista === 'reconciliacion' ? (libro || 'RIS') : (libro || undefined) },
      });
      if (peticion.current !== mia) return;   // llegó tarde: ya se pidió otra cosa
      setDatos(data);
    } catch (e) {
      if (peticion.current !== mia) return;
      toast.error(e?.response?.data?.detail || 'No se pudo leer el libro.');
    } finally {
      if (peticion.current === mia) setCargando(false);
    }
  }, [vista, desde, hasta, tz, libro]);

  useEffect(() => {
    (async () => { await cargar(); })();
    // Al desmontar —o al cambiar de vista— se invalida lo que esté en vuelo.
    return () => { peticion.current += 1; };
  }, [cargar]);

  const descargar = async (formato) => {
    setBajando(formato);
    try {
      const res = await api.get('/admin/ledger/balance', {
        params: { desde, hasta, tz_min: tz, libro: libro || undefined, formato },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `risapp_balance_${desde}_a_${hasta}.${formato}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('No se pudo descargar el balance.');
    } finally {
      setBajando('');
    }
  };

  const conFechas = ['balance', 'diario', 'mayor'].includes(vista);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        {VISTAS.map((v) => {
          const { clave, etiqueta, Icono } = v;
          const activa = vista === clave;
          return (
            <button key={clave} type="button" onClick={() => setVista(clave)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px',
                padding: '8px 14px', borderRadius: '10px', fontWeight: 700,
                fontSize: '14px', cursor: 'pointer',
                border: `1px solid ${activa ? COLOR.primario : COLOR.borde}`,
                backgroundColor: activa ? COLOR.primarioSuave : '#fff',
                color: activa ? COLOR.primario : COLOR.suave }}>
              <Icono size={15} /> {etiqueta}
            </button>
          );
        })}
      </div>

      {vista === 'btc' ? <LibroBtc /> : (
        <>
          <div style={tarjeta}>
            <h3 style={{ margin: '0 0 4px 0', fontSize: '16px', fontWeight: 700,
              display: 'flex', alignItems: 'center', gap: '8px' }}>
              <BookOpen size={17} /> {VISTAS.find((v) => v.clave === vista)?.etiqueta}
            </h3>
            <p style={{ margin: '0 0 14px 0', fontSize: '13px', color: COLOR.suave }}>
              {DESCRIPCIONES[vista]}
            </p>

            <div style={{ display: 'grid', gap: '12px',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
              {conFechas ? (
                <>
                  <Campo etiqueta="Desde">
                    <input type="date" value={desde} max={hasta} style={entrada}
                      onChange={(e) => setDesde(e.target.value)} />
                  </Campo>
                  <Campo etiqueta="Hasta">
                    <input type="date" value={hasta} min={desde} style={entrada}
                      onChange={(e) => setHasta(e.target.value)} />
                  </Campo>
                  <Campo etiqueta="El día corta en">
                    <select value={tz} style={entrada}
                      onChange={(e) => setTz(Number(e.target.value))}>
                      {HUSOS.map((h) => (
                        <option key={h.min} value={h.min}>{h.etiqueta}</option>
                      ))}
                    </select>
                  </Campo>
                </>
              ) : null}
              <Campo etiqueta="Libro">
                <select value={libro} style={entrada}
                  onChange={(e) => setLibro(e.target.value)}>
                  <option value="">Todos</option>
                  <option value="RIS">RIS</option>
                  <option value="USDT">USDT</option>
                  <option value="USDC">USDC</option>
                </select>
              </Campo>
            </div>

            {vista === 'balance' ? (
              <div style={{ display: 'flex', gap: '10px', marginTop: '14px',
                flexWrap: 'wrap' }}>
                <Boton onClick={() => descargar('xlsx')} cargando={bajando === 'xlsx'}
                  disabled={!datos}>
                  <FileSpreadsheet size={14} /> Excel para el contador
                </Boton>
                <Boton onClick={() => descargar('csv')} cargando={bajando === 'csv'}
                  disabled={!datos}>
                  <Download size={14} /> CSV
                </Boton>
              </div>
            ) : null}
          </div>

          {datos?.truncado ? (
            <Aviso tono="malo" titulo="Estas cifras están incompletas">
              El periodo superó el tope de lectura. Pedí el libro en tramos más
              cortos: los totales de abajo <strong>no son los totales reales</strong>.
            </Aviso>
          ) : null}

          {cargando ? (
            <div style={{ ...tarjeta, textAlign: 'center', color: COLOR.suave }}>
              Leyendo el libro…
            </div>
          ) : !datos ? null : (
            // Si una vista revienta al dibujarse, el error queda encerrado acá:
            // el menú y las demás secciones siguen andando, y el que lo ve tiene
            // un texto que puede pasar. Antes, cualquier excepción de render
            // dejaba la pantalla en blanco.
            <ErrorBoundary clave={vista} donde={`Libro mayor · ${vista}`}>
              {vista === 'balance' ? <Balance datos={datos} /> : null}
              {vista === 'diario' ? <Diario datos={datos} /> : null}
              {vista === 'mayor' ? <Mayor datos={datos} /> : null}
              {vista === 'reconciliacion' ? <Reconciliacion datos={datos} /> : null}
              {vista === 'integridad' ? <Integridad datos={datos} /> : null}
            </ErrorBoundary>
          )}
        </>
      )}
    </div>
  );
}

const DESCRIPCIONES = {
  balance: 'Sumas y saldos por cuenta. Es el estado que se le entrega al contador.',
  diario: 'Cada asiento del periodo, en el orden en que ocurrió, con sus dos partidas.',
  mayor: 'Los movimientos agrupados por cuenta, con el saldo que va dejando cada uno.',
  reconciliacion: 'El saldo guardado de cada usuario contra la suma de su libro. Sin tolerancia.',
  integridad: 'Los defectos que impedirían defender este libro ante un auditor.',
  btc: 'Órdenes directas de BTC. No tocan el saldo RIS y llevan su propio libro.',
};

/* ─── Balance de comprobación ──────────────────────────────────────────── */

function Balance({ datos }) {
  return (
    <>
      {/* El aviso va ARRIBA del número, no al pie: quien mira «✓ cuadra» sin
          leer esto se lleva una garantía que el libro no da. */}
      <Aviso tono="info" titulo="Este balance cuadra por construcción">
        Las dos partidas de cada asiento se derivan del tipo de movimiento, así que
        el debe <strong>siempre</strong> va a igualar al haber. Que cuadre no prueba
        que los datos estén bien: lo que sí prueba algo son las pestañas de{' '}
        <strong>Reconciliación</strong> e <strong>Integridad</strong>.
      </Aviso>

      <div style={{ ...tarjeta, display: 'grid', gap: '12px',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
        {Object.entries(datos.por_grupo || {}).map(([grupo, saldo]) => (
          <div key={grupo} style={{ border: `1px solid ${COLOR.borde}`,
            borderRadius: '12px', padding: '12px 14px' }}>
            <p style={{ margin: 0, fontSize: '12px', fontWeight: 700,
              color: COLOR.suave, textTransform: 'uppercase',
              letterSpacing: '.4px' }}>{grupo}</p>
            <p style={{ margin: '6px 0 0 0', fontSize: '20px', fontWeight: 800 }}>
              {saldo}
            </p>
          </div>
        ))}
      </div>

      <Tabla
        cabeceras={['Código', 'Cuenta', 'Tipo', 'Suma debe', 'Suma haber', 'Saldo']}
        filas={(datos.cuentas || []).map((c) => [
          <span style={{ fontFamily: 'monospace' }}>{c.codigo}</span>,
          c.nombre,
          <Etiqueta texto={c.tipo} />,
          <Numero valor={c.suma_debe} />,
          <Numero valor={c.suma_haber} />,
          <Numero valor={c.saldo} fuerte />,
        ])}
        pie={['', 'TOTALES', '', <Numero valor={datos.total_debe} fuerte />,
          <Numero valor={datos.total_haber} fuerte />, '']}
      />
    </>
  );
}

/* ─── Libro diario ─────────────────────────────────────────────────────── */

function Diario({ datos }) {
  return (
    <>
      {datos.sin_clasificar > 0 ? (
        <Aviso tono="alerta" titulo={`${datos.sin_clasificar} asientos sin clasificar`}>
          Su tipo de movimiento no está en el plan de cuentas, así que van a la
          cuenta puente <strong>5.1.99</strong>. Aparecen igual —desaparecerlos
          sería peor— pero hay que clasificarlos para que el balance signifique algo.
        </Aviso>
      ) : null}

      <div style={{ ...tarjeta, display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
        <Dato titulo="Asientos" valor={datos.asientos_totales} />
        <Dato titulo="Suma del debe" valor={datos.suma_debe} />
        <Dato titulo="Suma del haber" valor={datos.suma_haber} />
      </div>

      <Tabla
        cabeceras={['#', 'Fecha', 'Glosa', 'Debe', 'Haber', 'Monto', 'Referencia', 'Usuario']}
        filas={(datos.asientos || []).map((a) => [
          a.numero,
          <span style={{ whiteSpace: 'nowrap' }}>{a.fecha}</span>,
          <span>{a.glosa}{!a.clasificado
            ? <strong style={{ color: COLOR.alerta }}> · sin clasificar</strong> : ''}</span>,
          <Cuenta c={a.debe} />,
          <Cuenta c={a.haber} />,
          <Numero valor={a.monto} fuerte sufijo={a.moneda} />,
          <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>{a.referencia}</span>,
          a.usuario,
        ])}
      />
      {datos.hay_mas ? (
        <p style={{ fontSize: '12px', color: COLOR.suave, textAlign: 'center' }}>
          Hay más asientos de los que caben acá. Acotá el periodo.
        </p>
      ) : null}
    </>
  );
}

/* ─── Libro mayor ──────────────────────────────────────────────────────── */

function Mayor({ datos }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {(datos.cuentas || []).map((c) => (
        <details key={c.codigo} style={tarjeta}>
          <summary style={{ cursor: 'pointer', display: 'flex', gap: '12px',
            alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>{c.codigo}</span>
            <span style={{ fontWeight: 700 }}>{c.nombre}</span>
            <Etiqueta texto={c.tipo} />
            <span style={{ marginLeft: 'auto', fontWeight: 800 }}>{c.saldo}</span>
          </summary>
          <div style={{ marginTop: '12px' }}>
            <Tabla
              cabeceras={['Fecha', 'Glosa', 'Referencia', 'Usuario', 'Debe', 'Haber', 'Saldo']}
              filas={(c.movimientos || []).map((m) => [
                <span style={{ whiteSpace: 'nowrap' }}>{m.fecha}</span>,
                m.glosa,
                <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>{m.referencia}</span>,
                m.usuario,
                <Numero valor={m.debe} />,
                <Numero valor={m.haber} />,
                <Numero valor={m.saldo} fuerte />,
              ])}
            />
            {c.hay_mas_movimientos ? (
              <p style={{ fontSize: '12px', color: COLOR.suave }}>
                Hay más movimientos de los que caben acá.
              </p>
            ) : null}
          </div>
        </details>
      ))}
    </div>
  );
}

/* ─── Reconciliación ───────────────────────────────────────────────────── */

function Reconciliacion({ datos }) {
  const sano = datos.cuadra;
  return (
    <>
      <Aviso tono={sano ? 'bien' : 'malo'}
        titulo={sano ? 'El libro cuadra contra los saldos'
          : `${datos.descuadres_totales} cuentas no cuadran`}>
        {sano
          ? `Se revisaron ${datos.usuarios_revisados} usuarios contra ${datos.lineas_leidas} líneas del libro. Sin diferencias, y la tolerancia es cero.`
          : 'El saldo guardado no coincide con la suma del libro. Cada fila es una cuenta donde el dinero registrado no es el dinero que la app dice tener.'}
      </Aviso>

      {(datos.lineas_sin_usuario || []).length > 0 ? (
        <Aviso tono="malo" titulo="Hay plata registrada contra nadie">
          Estas líneas pertenecen a usuarios que ya no existen. Es un descuadre
          distinto y más grave que una diferencia de saldo.
          <Tabla
            cabeceras={['Usuario', 'Cuenta', 'Suma del libro']}
            filas={datos.lineas_sin_usuario.map((h) => [
              <span style={{ fontFamily: 'monospace' }}>{h.user_id}</span>,
              h.cuenta, <Numero valor={h.suma_del_libro} fuerte />,
            ])}
          />
        </Aviso>
      ) : null}

      {(datos.descuadres || []).length > 0 ? (
        <Tabla
          cabeceras={['Usuario', 'Email', 'Cuenta', 'Saldo guardado', 'Suma del libro', 'Diferencia']}
          filas={datos.descuadres.map((d) => [
            d.nombre || d.user_id, d.email, d.cuenta_contable,
            <Numero valor={d.saldo_guardado} />,
            <Numero valor={d.suma_del_libro} />,
            <Numero valor={d.diferencia} fuerte />,
          ])}
        />
      ) : null}
    </>
  );
}

/* ─── Integridad ───────────────────────────────────────────────────────── */

const TONO_GRAVEDAD = { alta: 'malo', media: 'alerta', baja: 'info' };

function Integridad({ datos }) {
  return (
    <>
      {/* `datos.hallazgos` va protegido como el resto del archivo. Era el único
          acceso crudo que quedaba, y por eso una respuesta inesperada acá
          rompía el render en vez de dibujar de menos. */}
      <Aviso tono={datos.sano ? 'bien' : 'malo'}
        titulo={datos.sano ? 'No se encontraron defectos'
          : `${(datos.hallazgos || []).length} tipos de defecto`}>
        Se revisaron {datos.lineas_revisadas} líneas. Nada se corrige
        automáticamente: <strong>un libro que se auto-corrige es un libro que
        nadie puede auditar</strong>.
      </Aviso>

      {(datos.hallazgos || []).map((h) => (
        <Aviso key={h.clave} tono={TONO_GRAVEDAD[h.gravedad] || 'info'}
          titulo={`${h.titulo} · ${h.cuantas}`}>
          {h.explicacion}
          {h.ejemplos?.length ? (
            <ul style={{ margin: '8px 0 0 0', paddingLeft: '18px',
              fontFamily: 'monospace', fontSize: '12px' }}>
              {h.ejemplos.map((e) => <li key={e}>{e}</li>)}
            </ul>
          ) : null}
        </Aviso>
      ))}

      {/* Lo que el libro TODAVIA no puede probar. Va acá y no escondido en una
          nota: son las cuatro cosas que un auditor va a pedir. */}
      <div style={{ ...tarjeta, backgroundColor: '#f9fafb' }}>
        <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', fontWeight: 700,
          display: 'flex', alignItems: 'center', gap: '7px' }}>
          <Info size={15} /> Lo que este libro todavía no puede probar
        </h4>
        <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px',
          color: COLOR.suave, lineHeight: 1.7 }}>
          {(datos.limitaciones || []).map((t) => <li key={t}>{t}</li>)}
        </ul>
      </div>
    </>
  );
}

/* ─── Piezas ───────────────────────────────────────────────────────────── */

const entrada = {
  width: '100%', padding: '9px 11px', borderRadius: '10px',
  border: `1px solid ${COLOR.borde}`, fontSize: '13px', backgroundColor: '#fff',
  boxSizing: 'border-box', color: COLOR.texto,
};

function Campo({ etiqueta, children }) {
  return (
    <label style={{ display: 'block' }}>
      <span style={{ display: 'block', fontSize: '12px', fontWeight: 600,
        color: COLOR.suave, marginBottom: '5px' }}>{etiqueta}</span>
      {children}
    </label>
  );
}

function Boton({ children, onClick, cargando, disabled }) {
  const inactivo = cargando || disabled;
  return (
    <button type="button" onClick={onClick} disabled={inactivo}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '7px',
        padding: '9px 15px', borderRadius: '10px', fontSize: '13px',
        fontWeight: 600, cursor: inactivo ? 'not-allowed' : 'pointer',
        border: `1px solid ${COLOR.borde}`, backgroundColor: '#fff',
        color: COLOR.texto, opacity: inactivo ? 0.5 : 1 }}>
      {cargando ? 'Trabajando…' : children}
    </button>
  );
}

const TONOS = {
  info: [COLOR.primarioSuave, COLOR.borde, COLOR.texto, Info],
  bien: [COLOR.bienSuave, COLOR.bienBorde, COLOR.bien, CheckCircle2],
  alerta: [COLOR.alertaSuave, COLOR.alertaBorde, COLOR.alerta, AlertTriangle],
  malo: [COLOR.maloSuave, COLOR.maloBorde, COLOR.malo, AlertTriangle],
};

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

function Dato({ titulo, valor }) {
  return (
    <div>
      <p style={{ margin: 0, fontSize: '12px', fontWeight: 700, color: COLOR.suave,
        textTransform: 'uppercase', letterSpacing: '.4px' }}>{titulo}</p>
      <p style={{ margin: '4px 0 0 0', fontSize: '20px', fontWeight: 800 }}>{valor}</p>
    </div>
  );
}

function Cuenta({ c }) {
  return (
    <span style={{ whiteSpace: 'nowrap' }}>
      <span style={{ fontFamily: 'monospace', fontSize: '12px',
        color: COLOR.suave }}>{c.codigo}</span>{' '}
      <span style={{ fontSize: '12px' }}>{c.nombre}</span>
    </span>
  );
}

function Numero({ valor, fuerte, sufijo }) {
  if (!valor && valor !== 0) return <span style={{ color: COLOR.suave }}>—</span>;
  return (
    <span style={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums',
      fontWeight: fuerte ? 700 : 400 }}>
      {valor}{sufijo ? <span style={{ fontSize: '11px', color: COLOR.suave }}> {sufijo}</span> : null}
    </span>
  );
}

function Etiqueta({ texto }) {
  return (
    <span style={{ fontSize: '11px', fontWeight: 700, padding: '2px 8px',
      borderRadius: '999px', backgroundColor: '#f3f4f6', color: COLOR.suave,
      textTransform: 'uppercase', letterSpacing: '.3px' }}>{texto}</span>
  );
}

function Tabla({ cabeceras, filas, pie }) {
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
              <tr><td colSpan={cabeceras.length} style={{ padding: '28px',
                textAlign: 'center', color: COLOR.suave }}>
                No hay movimientos en este periodo.
              </td></tr>
            ) : filas.map((fila, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${COLOR.borde}` }}>
                {fila.map((celda, j) => (
                  <td key={j} style={{ padding: '9px 12px', verticalAlign: 'top' }}>
                    {celda}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {pie ? (
            <tfoot>
              <tr style={{ borderTop: `2px solid ${COLOR.texto}`,
                backgroundColor: '#f9fafb' }}>
                {pie.map((celda, j) => (
                  <td key={j} style={{ padding: '10px 12px', fontWeight: 700 }}>
                    {celda}
                  </td>
                ))}
              </tr>
            </tfoot>
          ) : null}
        </table>
      </div>
    </div>
  );
}
