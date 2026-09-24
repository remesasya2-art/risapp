/**
 * Calculadora — convertir sin entrar a ningún flujo.
 *
 * POR QUE EXISTE
 *
 *   Pedido del dueño del proyecto: desde el inicio, sin empezar «Gastar en
 *   Venezuela» ni «Gastar en Brasil», poder ver cuánto son unos reales en
 *   bolívares, cuántos dólares al BCV son esos bolívares, y al revés: escribir
 *   dólares al BCV o bolívares y ver el resto. Antes, para saberlo había que
 *   arrancar un envío y llegar hasta la cotización.
 *
 * LAS CUENTAS NO ESTAN ACA
 *
 *   Están en `utils/calculadora.js`, que se prueba con node y números
 *   exactos. Esto dibuja: tres casillas atadas, el selector del sentido, las
 *   dos tasas con las que calcula, y el botón que lleva al flujo del sentido
 *   elegido. La tasa del USDT no va: el dueño la sacó, porque no hay un flujo
 *   donde el cliente pague con USDT y mostrarla sólo confunde.
 *
 * LAS TASAS SALEN DE `RateContext`, NO DE UN PEDIDO PROPIO
 *
 *   Es la misma consulta que ya alimenta la tira de indicadores y la tarjeta
 *   de saldo. Si `/rate` no contestó, `tasaDisponible` viene en falso y la
 *   calculadora lo dice en vez de calcular con el relleno.
 *
 * ORIENTATIVO, Y LO DICE
 *
 *   La tasa del envío se congela al cotizar, y fuera del horario tiene su
 *   ajuste. Lo que muestra esto es la tasa de este momento; la del envío es
 *   la que la persona ve al cotizar. Por eso el pie de la tarjeta lo aclara.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Calculator, ArrowUpRight } from 'lucide-react';
import { useRate } from '../../contexts/RateContext';
import { fmt, fmtAntiguedadHoras } from '../../utils/format';
import {
  A_VENEZUELA, A_BRASIL, REALES, BOLIVARES, DOLARES_BCV,
  aNumero, tasaDelSentido, convertir,
} from '../../utils/calculadora';

const SENTIDOS = [
  { clave: A_VENEZUELA, etiqueta: 'Brasil → Venezuela', ruta: '/send', boton: 'Enviar a Venezuela' },
  { clave: A_BRASIL, etiqueta: 'Venezuela → Brasil', ruta: '/send-reais', boton: 'Enviar a Brasil' },
];

const CASILLAS = [
  { clave: REALES, etiqueta: 'Reales', simbolo: 'R$', testid: 'calc-brl' },
  { clave: BOLIVARES, etiqueta: 'Bolívares', simbolo: 'Bs', testid: 'calc-ves' },
  { clave: DOLARES_BCV, etiqueta: 'Dólares al BCV', simbolo: '$', testid: 'calc-usd' },
];

export default function Calculadora({ isMobile = false }) {
  const { rates, tasaDisponible } = useRate();
  const [sentido, setSentido] = useState(A_VENEZUELA);
  const [origen, setOrigen] = useState(REALES);
  const [escrito, setEscrito] = useState('');

  const tasa = tasaDelSentido(rates, sentido, tasaDisponible);
  const bcv = Number(rates?.bcv_usd_ves) || 0;
  const bcvVencida = rates?.bcv_vencida === true;

  const monto = aNumero(escrito);
  const cuenta = convertir({ origen, monto, tasa, bcv });
  const hayCuenta = monto > 0 && tasa > 0;
  const elSentido = SENTIDOS.find((s) => s.clave === sentido);

  // Al tocar otra casilla, lo que ahí se veía calculado pasa a ser lo escrito,
  // para que la persona lo corrija desde ese número y no desde cero.
  const tomarCasilla = (clave) => {
    if (origen === clave) return;
    const valor = cuenta[clave];
    setOrigen(clave);
    setEscrito(valor > 0 ? String(valor).replace('.', ',') : '');
  };

  return (
    <div data-testid="calculadora" style={{
      backgroundColor: 'var(--en-oscuro-superficie, #ffffff)', borderRadius: '22px', border: '1px solid var(--en-oscuro-linea, #eef0f4)',
      boxShadow: '0 8px 24px rgba(91,79,233,0.10), 0 1px 3px rgba(0,0,0,0.03)', overflow: 'hidden',
      display: 'flex', flexDirection: 'column',
    }}>
      <div style={{ height: '4px', background: 'linear-gradient(90deg, #3B3A9E 0%, #8B7FFF 50%, var(--en-oscuro-acento, #5B4FE9) 100%)' }} />
      <div style={{ padding: isMobile ? '20px' : '24px', display: 'flex', flexDirection: 'column', gap: '12px', flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: 40, height: 40, borderRadius: 12, backgroundColor: 'var(--en-oscuro-acento-suave, rgba(91,79,233,0.10))',
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            <Calculator size={20} color="#5B4FE9" strokeWidth={1.8} />
          </div>
          <div>
            <p style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)' }}>Calculadora</p>
            <p style={{ margin: 0, fontSize: '11px', color: 'var(--en-oscuro-texto-3, #9ca3af)' }}>Escribí en cualquier casilla; las otras se calculan solas</p>
          </div>
        </div>

        {/* El sentido del envío: cambia la tasa y el botón de abajo */}
        <div role="radiogroup" aria-label="Sentido del envío" data-testid="calc-sentido"
          style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', padding: '4px',
            background: 'var(--en-oscuro-superficie-2, #f3f4f6)', borderRadius: '12px' }}>
          {SENTIDOS.map((s) => {
            const activo = s.clave === sentido;
            return (
              <button key={s.clave} type="button" role="radio" aria-checked={activo}
                data-testid={`calc-${s.clave}`} onClick={() => setSentido(s.clave)}
                style={{
                  padding: '8px 6px', borderRadius: '9px', border: 'none', cursor: 'pointer',
                  fontSize: '12.5px', fontWeight: 700,
                  background: activo ? 'var(--en-oscuro-superficie-3, #ffffff)' : 'transparent',
                  color: activo ? 'var(--en-oscuro-acento, #5B4FE9)' : 'var(--en-oscuro-texto-2, #6b7280)',
                  boxShadow: activo ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                }}>
                {s.etiqueta}
              </button>
            );
          })}
        </div>

        {!tasaDisponible ? (
          <p data-testid="calc-sin-tasa" style={{
            margin: 0, padding: '12px 14px', borderRadius: '12px', fontSize: '13px', lineHeight: 1.5,
            background: 'var(--en-oscuro-alerta-suave, #fffbeb)', border: '1px solid var(--en-oscuro-alerta-borde, #fde68a)', color: 'var(--en-oscuro-alerta, #92400e)',
          }}>
            No pudimos obtener la tasa. Sin ella preferimos no mostrarte una cuenta que después cambie.
          </p>
        ) : null}

        {CASILLAS.map((c) => {
          const esOrigen = origen === c.clave;
          const valor = esOrigen ? escrito : (hayCuenta && cuenta[c.clave] > 0 ? fmt(cuenta[c.clave]) : '');
          return (
            <label key={c.clave} style={{ display: 'block' }}>
              <span style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--en-oscuro-texto-3, #9ca3af)', marginBottom: '5px' }}>
                {c.etiqueta}
              </span>
              <span style={{
                display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 12px', borderRadius: '12px',
                border: `1.5px solid ${esOrigen ? 'var(--en-oscuro-acento, #5B4FE9)' : 'var(--en-oscuro-linea, #eef0f4)'}`,
                background: esOrigen ? 'var(--en-oscuro-superficie, #fff)' : 'var(--en-oscuro-superficie-2, #f9fafb)',
              }}>
                <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--en-oscuro-acento, #5B4FE9)', minWidth: '28px' }}>{c.simbolo}</span>
                <input
                  inputMode="decimal" placeholder="0,00" data-testid={c.testid}
                  value={valor} disabled={!tasaDisponible}
                  onFocus={() => tomarCasilla(c.clave)}
                  onChange={(e) => { setOrigen(c.clave); setEscrito(e.target.value); }}
                  style={{
                    flex: 1, minWidth: 0, border: 'none', outline: 'none', background: 'transparent',
                    fontSize: '17px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)', fontVariantNumeric: 'tabular-nums',
                  }}
                />
              </span>
            </label>
          );
        })}

        {/* Las dos tasas con las que calcula */}
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: '8px', marginTop: '2px' }}>
          <Tasa testid="calc-tasa-envio"
            valor={tasa > 0 ? `1 R$ = ${fmt(tasa)} Bs` : 'Sin tasa'}
            nombre={sentido === A_BRASIL ? 'Tasa Venezuela → Brasil' : 'Tasa Brasil → Venezuela'} />
          <Tasa valor={bcv > 0 ? `1 $ = ${fmt(bcv)} Bs` : 'BCV sin dato'}
            nombre={bcvVencida ? `BCV ${fmtAntiguedadHoras(rates?.bcv_edad_horas)}` : 'Referencia BCV'}
            alerta={bcvVencida} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', marginTop: 'auto', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '12px', color: 'var(--en-oscuro-texto-2, #6b7280)' }}>
            Sólo orientativo: la tasa del envío se fija al cotizar.
          </span>
          {/* El monto escrito viaja al flujo, para no tipearlo dos veces. En
              reales en los dos sentidos: es la moneda en que las dos pantallas
              de envío toman el monto. Con la casilla vacía, sin parámetro. */}
          <Link to={hayCuenta ? `${elSentido.ruta}?monto=${cuenta.brl}` : elSentido.ruta}
            data-testid="calc-ir-al-envio" style={{
            display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '10px 14px', borderRadius: '12px',
            fontWeight: 700, fontSize: '13px', color: 'var(--en-oscuro-acento, #5B4FE9)', textDecoration: 'none',
            border: '1.5px solid var(--en-oscuro-acento-borde, rgba(91,79,233,0.25))',
          }}>
            <ArrowUpRight size={16} strokeWidth={2.5} /> {elSentido.boton}
          </Link>
        </div>
      </div>
    </div>
  );
}

function Tasa({ valor, nombre, alerta = false, testid }) {
  return (
    <div data-testid={testid} style={{
      padding: '8px 10px', borderRadius: '10px', border: '1px solid var(--en-oscuro-linea, #eef0f4)',
      background: 'linear-gradient(135deg, var(--en-oscuro-acento-suave, rgba(91,79,233,0.05)) 0%, rgba(59,58,158,0.03) 100%)',
      display: 'flex', flexDirection: 'column', lineHeight: 1.15,
    }}>
      <span style={{ fontSize: '12.5px', fontWeight: 700, color: 'var(--en-oscuro-texto, #111827)', whiteSpace: 'nowrap' }}>{valor}</span>
      <span style={{ fontSize: '10.5px', color: alerta ? 'var(--en-oscuro-alerta, #b45309)' : 'var(--en-oscuro-texto-3, #9ca3af)', marginTop: '2px' }}>{nombre}</span>
    </div>
  );
}
