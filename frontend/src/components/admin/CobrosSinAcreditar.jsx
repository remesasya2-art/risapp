/**
 * CobrosSinAcreditar.jsx — ¿Hay alguien esperando plata que ya pagó?
 *
 * POR QUE ESTA PANTALLA EXISTE
 *
 *   Un pago de Mercado Pago se acredita por dos caminos —el aviso del servidor
 *   de Mercado Pago y la pantalla del cliente, que pregunta mientras espera— y
 *   quien PAGA Y CIERRA LA PANTALLA cae en el medio de los dos: su plata salió
 *   de su cuenta y en la app no aparece.
 *
 *   No había forma de enterarse. Nadie reclama lo que no sabe que perdió, así
 *   que el defecto es silencioso por diseño y la única manera de encontrarlo es
 *   ir a preguntar. Eso hace esta pantalla, y nada más: `services/
 *   cobros_sin_acreditar.py` explica por qué el juez es el libro mayor.
 *
 * POR QUE HAY QUE PULSAR UN BOTON Y NO SE CARGA SOLA
 *
 *   Cada revisión le hace a Mercado Pago una consulta por cada pago sospechoso.
 *   Eso sale por la red, cuesta segundos y la API de Mercado Pago tiene límites.
 *   Una pantalla que se revisa sola cada vez que alguien entra al panel castiga
 *   a la pasarela por la que entra toda la plata de la app.
 *
 * Y POR QUE NO HAY NINGUN BOTON QUE ACREDITE
 *
 *   Porque mover plata es una decisión de una persona y tiene que dejar rastro.
 *   Un informe que además arregla es un informe que nadie se anima a correr
 *   —«¿y si toca algo?»— y una pantalla que no se corre no encuentra nada.
 *   Acreditar es un paso aparte, con su registro en el libro de auditoría.
 *
 * LAS DOS TABLAS SON DOS PROBLEMAS DISTINTOS
 *
 *   Arriba, lo que hay que acreditar: Mercado Pago cobró y la app tampoco lo da
 *   por cobrado. Abajo, lo que hay que asentar: la app ya le dio el saldo al
 *   cliente y lo que falta es la línea del libro. Un solo total mezclando las
 *   dos no significa ni una cosa ni la otra, y es el que alguien usaría para
 *   decidir.
 *
 * NO SABER NO ES ESTAR BIEN
 *
 *   Si Mercado Pago no está configurado, o no contestó por algunos pagos, o el
 *   tope recortó la lista, eso se dice arriba y en grande. Una pantalla vacía
 *   por no haber podido preguntar se lee exactamente igual que una pantalla
 *   vacía porque todo está bien, y son cosas opuestas.
 */
import { useState } from 'react';
import toast from 'react-hot-toast';
import {
  AlertTriangle, CheckCircle2, Clock, CreditCard, HelpCircle, QrCode, Search,
} from 'lucide-react';
import api from '../../utils/api';
import { fmt } from '../../utils/format';

const C = {
  linea: '#e5e7eb',
  fondo: '#f9fafb',
  tinta: '#111827',
  suave: '#6b7280',
  tenue: '#9ca3af',
  verde: '#047857',
  verdeFondo: '#ecfdf5',
  ambar: '#b45309',
  ambarFondo: '#fffbeb',
  rojo: '#b91c1c',
  rojoFondo: '#fef2f2',
  azul: '#14395e',
};

// Cuánta ventana se puede pedir. Los mismos topes que hace cumplir el
// servidor, para que la pantalla no ofrezca lo que la ruta va a recortar.
const VENTANAS = [7, 30, 90, 180, 365];

const fechaHora = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString('es-VE', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
};

// El estado que la app tenía anotado, en palabras. Se muestra porque explica
// POR QUE se perdió: «vencido» es alguien que pagó el código QR después de los
// siete minutos, y «pendiente» es alguien que pagó y cerró la pantalla.
const ESTADOS = {
  pending: 'pendiente',
  expired: 'vencido',
  cancelled: 'cancelado',
  paid: 'pagado',
  approved: 'aprobado',
  in_process: 'en proceso',
  rejected: 'rechazado',
};

const Aviso = ({ tono, children }) => {
  const paleta = {
    mal: { color: C.rojo, fondo: C.rojoFondo, Icono: AlertTriangle },
    ojo: { color: C.ambar, fondo: C.ambarFondo, Icono: AlertTriangle },
    bien: { color: C.verde, fondo: C.verdeFondo, Icono: CheckCircle2 },
  }[tono];
  const { Icono } = paleta;
  return (
    <div style={{
      display: 'flex', gap: 8, alignItems: 'flex-start', padding: '10px 12px',
      borderRadius: 10, backgroundColor: paleta.fondo, color: paleta.color,
      fontSize: 13, lineHeight: 1.5, border: `1px solid ${paleta.color}22`,
    }}>
      <Icono size={15} style={{ flexShrink: 0, marginTop: 2 }} />
      <div>{children}</div>
    </div>
  );
};

const Celda = ({ children, derecha, ancho }) => (
  <td style={{
    padding: '10px 12px', borderBottom: `1px solid ${C.linea}`, fontSize: 13,
    color: C.tinta, textAlign: derecha ? 'right' : 'left',
    fontVariantNumeric: derecha ? 'tabular-nums' : 'normal',
    whiteSpace: ancho ? 'normal' : 'nowrap',
  }}>
    {children}
  </td>
);

const Encabezado = ({ children, derecha }) => (
  <th style={{
    padding: '8px 12px', borderBottom: `2px solid ${C.linea}`, fontSize: 11,
    color: C.suave, textAlign: derecha ? 'right' : 'left',
    textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 700,
  }}>
    {children}
  </th>
);

function Tabla({ filas }) {
  return (
    <div style={{ overflowX: 'auto', border: `1px solid ${C.linea}`, borderRadius: 12 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
        <thead>
          <tr style={{ backgroundColor: C.fondo }}>
            <Encabezado>Cuenta</Encabezado>
            <Encabezado>Medio</Encabezado>
            <Encabezado derecha>Cobrado en MP</Encabezado>
            <Encabezado derecha>Según la app</Encabezado>
            <Encabezado>La app lo tenía como</Encabezado>
            <Encabezado>Cuándo se generó</Encabezado>
            <Encabezado>N° en Mercado Pago</Encabezado>
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => {
            const distinto = f.monto_en_mercadopago !== f.monto_en_la_app;
            return (
              <tr key={`${f.medio}-${f.pago}`}>
                {/* La CUENTA arriba y el nombre de quien pagó abajo, y no
                    al revés: la cuenta es la que se busca en el panel para ir
                    a arreglar la fila, y nunca falta. El nombre del cliente es
                    texto libre —en PIX puede ser un tercero— y en los pagos
                    viejos está vacío. Cuando esta columna mostraba sólo el
                    nombre, las tres únicas filas que aparecieron en producción
                    salieron todas con un guión. */}
                <Celda ancho>
                  <div style={{ fontWeight: 600 }}>{f.cuenta || '—'}</div>
                  {f.cliente && (
                    <div style={{ fontSize: 12, color: C.suave, marginTop: 2 }}>
                      pagó {f.cliente}
                    </div>
                  )}
                </Celda>
                <Celda>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: C.suave }}>
                    {f.medio === 'PIX' ? <QrCode size={13} /> : <CreditCard size={13} />}
                    {f.medio}
                  </span>
                </Celda>
                <Celda derecha>
                  <strong>R$ {fmt(f.monto_en_mercadopago)}</strong>
                </Celda>
                <Celda derecha>
                  <span style={{ color: distinto ? C.ambar : C.tenue }}>
                    R$ {fmt(f.monto_en_la_app)}
                    {/* Si los dos montos no coinciden hay algo más que revisar
                        que el crédito faltante, y esconderlo sería esconder el
                        único lugar donde eso se ve. */}
                    {distinto && ' ⚠'}
                  </span>
                </Celda>
                <Celda>{ESTADOS[f.estado_en_la_app] || f.estado_en_la_app || '—'}</Celda>
                <Celda>{fechaHora(f.cuando)}</Celda>
                <Celda>
                  <code style={{ fontSize: 12, color: C.suave }}>{f.pago_en_mercadopago}</code>
                </Celda>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function CobrosSinAcreditar() {
  const [dias, setDias] = useState(30);
  const [informe, setInforme] = useState(null);
  const [revisando, setRevisando] = useState(false);

  const revisar = () => {
    setRevisando(true);
    api.get('/admin/ledger/cobros-sin-acreditar', { params: { dias } })
      .then(({ data }) => setInforme(data))
      .catch((error) => {
        toast.error(error.response?.data?.detail
          || 'No se pudo revisar los cobros. Reintentá en un momento.');
      })
      .finally(() => setRevisando(false));
  };

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        gap: 16, flexWrap: 'wrap', marginBottom: 18,
      }}>
        <div style={{ maxWidth: 620 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: C.tinta, margin: 0 }}>
            Cobros sin acreditar
          </h2>
          <p style={{ fontSize: 13, color: C.suave, margin: '6px 0 0 0', lineHeight: 1.6 }}>
            Le pregunta a Mercado Pago, pago por pago, si ese cobro se hizo de
            verdad, y lo compara contra el libro mayor. Encuentra a quien pagó y
            cerró la pantalla antes de que la app se enterara.{' '}
            <strong style={{ color: C.tinta }}>Sólo mira: no acredita nada.</strong>
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 13, color: C.suave }}>
            Últimos{' '}
            <select
              value={dias}
              onChange={(e) => setDias(Number(e.target.value))}
              disabled={revisando}
              style={{
                padding: '7px 8px', borderRadius: 8, border: `1px solid ${C.linea}`,
                fontSize: 13, color: C.tinta, backgroundColor: '#fff',
              }}
            >
              {VENTANAS.map((d) => <option key={d} value={d}>{d} días</option>)}
            </select>
          </label>
          <button
            onClick={revisar}
            disabled={revisando}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, padding: '9px 16px',
              borderRadius: 10, border: 'none', backgroundColor: C.azul, color: '#fff',
              fontWeight: 600, fontSize: 13.5, cursor: revisando ? 'default' : 'pointer',
              opacity: revisando ? 0.65 : 1,
            }}
          >
            <Search size={14} /> {revisando ? 'Revisando…' : 'Revisar'}
          </button>
        </div>
      </div>

      {revisando && (
        <p style={{ fontSize: 13, color: C.suave, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Clock size={14} /> Preguntándole a Mercado Pago uno por uno. Puede tardar
          unos segundos.
        </p>
      )}

      {!informe && !revisando && (
        <div style={{
          padding: '32px 20px', textAlign: 'center', borderRadius: 12,
          border: `1px dashed ${C.linea}`, backgroundColor: C.fondo,
          color: C.suave, fontSize: 14,
        }}>
          {/* El ícono va en su propia caja centrada y no suelto con
              `textAlign: center`: el reset de Tailwind («preflight», que entra
              por el `@import "tailwindcss"` de index.css) le pone
              `display: block` a todos los `svg`, y un bloque no lo centra el
              `text-align` del padre. Se iba solo al margen izquierdo mientras
              el texto quedaba centrado. */}
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}>
            <HelpCircle size={22} color={C.tenue} />
          </div>
          <div>Todavía no se revisó nada. Pulsá «Revisar».</div>
        </div>
      )}

      {informe && !revisando && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Lo que no se pudo saber va PRIMERO, antes de cualquier cifra. Una
              lista vacía debajo de «no se pudo preguntar» no es una buena
              noticia, y tiene que leerse en ese orden. */}
          {!informe.pudo_preguntar && (
            <Aviso tono="mal">
              <strong>Mercado Pago no está configurado en este servidor.</strong> No se
              le pudo preguntar por ningún pago, así que este informe no dice que
              esté todo bien: dice que no se sabe.
            </Aviso>
          )}
          {informe.sin_respuesta > 0 && (
            <Aviso tono="ojo">
              <strong>{informe.sin_respuesta} pago(s) sin respuesta de Mercado Pago.</strong>{' '}
              No se sabe si se cobraron. No están contados en las listas de abajo.
            </Aviso>
          )}
          {informe.sin_mirar > 0 && (
            <Aviso tono="ojo">
              <strong>Quedaron {informe.sin_mirar} pago(s) sin mirar</strong> porque se
              alcanzó el tope de {informe.tope} consultas. Se miraron los más viejos
              primero. Para llegar al resto, revisá con una ventana más corta.
            </Aviso>
          )}

          <div style={{ fontSize: 13, color: C.suave }}>
            Se revisaron{' '}
            <strong style={{ color: C.tinta }}>{informe.mirados}</strong> pago(s) de los
            últimos {informe.dias} días que el libro mayor no registra.
          </div>

          <section>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: C.tinta, margin: '0 0 4px 0' }}>
              Cobrado y no acreditado
            </h3>
            <p style={{ fontSize: 12.5, color: C.suave, margin: '0 0 10px 0' }}>
              Mercado Pago cobró, la app tampoco lo da por cobrado. Esto es plata que
              se le debe a un cliente.
            </p>
            {informe.cuantos === 0 ? (
              <Aviso tono={informe.pudo_preguntar ? 'bien' : 'ojo'}>
                No apareció ningún cobro sin acreditar en los últimos {informe.dias} días.
              </Aviso>
            ) : (
              <>
                <div style={{
                  display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10,
                  color: C.rojo,
                }}>
                  <span style={{ fontSize: 24, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                    R$ {fmt(informe.total_brl)}
                  </span>
                  <span style={{ fontSize: 13 }}>en {informe.cuantos} cobro(s)</span>
                </div>
                <Tabla filas={informe.cobros} />
              </>
            )}
          </section>

          {informe.cuantos_descuadres > 0 && (
            <section>
              <h3 style={{ fontSize: 15, fontWeight: 700, color: C.tinta, margin: '0 0 4px 0' }}>
                Acreditado y sin asentar en el libro
              </h3>
              <p style={{ fontSize: 12.5, color: C.suave, margin: '0 0 10px 0' }}>
                Mercado Pago cobró y el cliente ya tiene su saldo, pero el libro mayor
                no tiene la línea. Acá no falta plata: falta el asiento, y por eso va
                aparte y no suma al total de arriba.
              </p>
              <div style={{
                display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10,
                color: C.ambar,
              }}>
                <span style={{ fontSize: 20, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                  R$ {fmt(informe.total_descuadres_brl)}
                </span>
                <span style={{ fontSize: 13 }}>
                  en {informe.cuantos_descuadres} pago(s)
                </span>
              </div>
              <Tabla filas={informe.descuadres} />
            </section>
          )}
        </div>
      )}
    </div>
  );
}
